"""
Esecutore simulazione OASIS
Esegue la simulazione in background registrando le azioni di ogni Agent, con supporto monitoraggio stato in tempo reale
"""

import os
import sys
import json
import time
import asyncio
import threading
import subprocess
import signal
import atexit
from typing import Dict, Any, List, Optional, Union
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from queue import Queue

from ..config import Config
from ..utils.logger import get_logger
from .zep_graph_memory_updater import ZepGraphMemoryManager
from .simulation_ipc import SimulationIPCClient, CommandType, IPCResponse

logger = get_logger('mirofish.simulation_runner')

# Flag per indicare se la funzione di pulizia e' gia' registrata
_cleanup_registered = False

# Rilevamento piattaforma
IS_WINDOWS = sys.platform == 'win32'


class RunnerStatus(str, Enum):
    """Stato dell'esecutore"""
    IDLE = "idle"
    STARTING = "starting"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPING = "stopping"
    STOPPED = "stopped"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class AgentAction:
    """Registro azione Agent"""
    round_num: int
    timestamp: str
    platform: str  # twitter / reddit
    agent_id: int
    agent_name: str
    action_type: str  # CREATE_POST, LIKE_POST, etc.
    action_args: Dict[str, Any] = field(default_factory=dict)
    result: Optional[str] = None
    success: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "round_num": self.round_num,
            "timestamp": self.timestamp,
            "platform": self.platform,
            "agent_id": self.agent_id,
            "agent_name": self.agent_name,
            "action_type": self.action_type,
            "action_args": self.action_args,
            "result": self.result,
            "success": self.success,
        }


@dataclass
class RoundSummary:
    """Riepilogo per turno"""
    round_num: int
    start_time: str
    end_time: Optional[str] = None
    simulated_hour: int = 0
    twitter_actions: int = 0
    reddit_actions: int = 0
    active_agents: List[int] = field(default_factory=list)
    actions: List[AgentAction] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "round_num": self.round_num,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "simulated_hour": self.simulated_hour,
            "twitter_actions": self.twitter_actions,
            "reddit_actions": self.reddit_actions,
            "active_agents": self.active_agents,
            "actions_count": len(self.actions),
            "actions": [a.to_dict() for a in self.actions],
        }


@dataclass
class SimulationRunState:
    """Stato esecuzione simulazione (tempo reale)"""
    simulation_id: str
    runner_status: RunnerStatus = RunnerStatus.IDLE

    # Informazioni progresso
    current_round: int = 0
    total_rounds: int = 0
    simulated_hours: int = 0
    total_simulation_hours: int = 0

    # Turni e tempo simulato indipendenti per piattaforma (per visualizzazione parallela doppia piattaforma)
    twitter_current_round: int = 0
    reddit_current_round: int = 0
    twitter_simulated_hours: int = 0
    reddit_simulated_hours: int = 0

    # Stato piattaforma
    twitter_running: bool = False
    reddit_running: bool = False
    twitter_actions_count: int = 0
    reddit_actions_count: int = 0

    # Stato completamento piattaforma (tramite rilevamento evento simulation_end in actions.jsonl)
    twitter_completed: bool = False
    reddit_completed: bool = False

    # Riepilogo per turno
    rounds: List[RoundSummary] = field(default_factory=list)

    # Azioni recenti (per visualizzazione in tempo reale nel frontend)
    recent_actions: List[AgentAction] = field(default_factory=list)
    max_recent_actions: int = 50

    # Timestamp
    started_at: Optional[str] = None
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    completed_at: Optional[str] = None

    # Informazioni errore
    error: Optional[str] = None

    # ID processo (per arresto)
    process_pid: Optional[int] = None

    def add_action(self, action: AgentAction):
        """Aggiungi azione alla lista azioni recenti"""
        self.recent_actions.insert(0, action)
        if len(self.recent_actions) > self.max_recent_actions:
            self.recent_actions = self.recent_actions[:self.max_recent_actions]

        if action.platform == "twitter":
            self.twitter_actions_count += 1
        else:
            self.reddit_actions_count += 1

        self.updated_at = datetime.now().isoformat()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "simulation_id": self.simulation_id,
            "runner_status": self.runner_status.value,
            "current_round": self.current_round,
            "total_rounds": self.total_rounds,
            "simulated_hours": self.simulated_hours,
            "total_simulation_hours": self.total_simulation_hours,
            "progress_percent": round(self.current_round / max(self.total_rounds, 1) * 100, 1),
            # Turni e tempo indipendenti per piattaforma
            "twitter_current_round": self.twitter_current_round,
            "reddit_current_round": self.reddit_current_round,
            "twitter_simulated_hours": self.twitter_simulated_hours,
            "reddit_simulated_hours": self.reddit_simulated_hours,
            "twitter_running": self.twitter_running,
            "reddit_running": self.reddit_running,
            "twitter_completed": self.twitter_completed,
            "reddit_completed": self.reddit_completed,
            "twitter_actions_count": self.twitter_actions_count,
            "reddit_actions_count": self.reddit_actions_count,
            "total_actions_count": self.twitter_actions_count + self.reddit_actions_count,
            "started_at": self.started_at,
            "updated_at": self.updated_at,
            "completed_at": self.completed_at,
            "error": self.error,
            "process_pid": self.process_pid,
        }

    def to_detail_dict(self) -> Dict[str, Any]:
        """Informazioni dettagliate con azioni recenti"""
        result = self.to_dict()
        result["recent_actions"] = [a.to_dict() for a in self.recent_actions]
        result["rounds_count"] = len(self.rounds)
        return result


class SimulationRunner:
    """
    Esecutore simulazione

    Responsabile di:
    1. Eseguire la simulazione OASIS in un processo in background
    2. Analizzare i log di esecuzione, registrando le azioni di ogni Agent
    3. Fornire interfaccia di interrogazione stato in tempo reale
    4. Supportare operazioni di pausa/arresto/ripresa
    """

    # Directory archiviazione stato esecuzione
    RUN_STATE_DIR = os.path.join(
        os.path.dirname(__file__),
        '../../uploads/simulations'
    )

    # Directory script
    SCRIPTS_DIR = os.path.join(
        os.path.dirname(__file__),
        '../../scripts'
    )

    # Stato esecuzione in memoria
    _run_states: Dict[str, SimulationRunState] = {}
    _processes: Dict[str, subprocess.Popen] = {}
    _action_queues: Dict[str, Queue] = {}
    _monitor_threads: Dict[str, threading.Thread] = {}
    _stdout_files: Dict[str, Any] = {}  # Handle file stdout
    _stderr_files: Dict[str, Any] = {}  # Handle file stderr

    # Configurazione aggiornamento memoria grafo
    _graph_memory_enabled: Dict[str, bool] = {}  # simulation_id -> enabled

    @classmethod
    def get_run_state(cls, simulation_id: str) -> Optional[SimulationRunState]:
        """Ottieni stato esecuzione"""
        if simulation_id in cls._run_states:
            return cls._run_states[simulation_id]

        # Tentativo di caricamento da file
        state = cls._load_run_state(simulation_id)
        if state:
            cls._run_states[simulation_id] = state
        return state

    @classmethod
    def _load_run_state(cls, simulation_id: str) -> Optional[SimulationRunState]:
        """Carica stato esecuzione da file"""
        state_file = os.path.join(cls.RUN_STATE_DIR, simulation_id, "run_state.json")
        if not os.path.exists(state_file):
            return None

        try:
            with open(state_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            state = SimulationRunState(
                simulation_id=simulation_id,
                runner_status=RunnerStatus(data.get("runner_status", "idle")),
                current_round=data.get("current_round", 0),
                total_rounds=data.get("total_rounds", 0),
                simulated_hours=data.get("simulated_hours", 0),
                total_simulation_hours=data.get("total_simulation_hours", 0),
                # Turni e tempo indipendenti per piattaforma
                twitter_current_round=data.get("twitter_current_round", 0),
                reddit_current_round=data.get("reddit_current_round", 0),
                twitter_simulated_hours=data.get("twitter_simulated_hours", 0),
                reddit_simulated_hours=data.get("reddit_simulated_hours", 0),
                twitter_running=data.get("twitter_running", False),
                reddit_running=data.get("reddit_running", False),
                twitter_completed=data.get("twitter_completed", False),
                reddit_completed=data.get("reddit_completed", False),
                twitter_actions_count=data.get("twitter_actions_count", 0),
                reddit_actions_count=data.get("reddit_actions_count", 0),
                started_at=data.get("started_at"),
                updated_at=data.get("updated_at", datetime.now().isoformat()),
                completed_at=data.get("completed_at"),
                error=data.get("error"),
                process_pid=data.get("process_pid"),
            )

            # Carica azioni recenti
            actions_data = data.get("recent_actions", [])
            for a in actions_data:
                state.recent_actions.append(AgentAction(
                    round_num=a.get("round_num", 0),
                    timestamp=a.get("timestamp", ""),
                    platform=a.get("platform", ""),
                    agent_id=a.get("agent_id", 0),
                    agent_name=a.get("agent_name", ""),
                    action_type=a.get("action_type", ""),
                    action_args=a.get("action_args", {}),
                    result=a.get("result"),
                    success=a.get("success", True),
                ))

            return state
        except Exception as e:
            logger.error(f"Caricamento stato esecuzione fallito: {str(e)}")
            return None

    @classmethod
    def _save_run_state(cls, state: SimulationRunState):
        """Salva stato esecuzione su file"""
        sim_dir = os.path.join(cls.RUN_STATE_DIR, state.simulation_id)
        os.makedirs(sim_dir, exist_ok=True)
        state_file = os.path.join(sim_dir, "run_state.json")

        data = state.to_detail_dict()

        with open(state_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        cls._run_states[state.simulation_id] = state

    @classmethod
    def start_simulation(
        cls,
        simulation_id: str,
        platform: str = "parallel",  # twitter / reddit / parallel
        max_rounds: int = None,  # Numero massimo turni simulazione (opzionale, per troncare simulazioni troppo lunghe)
        enable_graph_memory_update: bool = False,  # Se aggiornare le attivita' nel grafo Zep
        graph_id: str = None  # ID grafo Zep (necessario quando si abilita l'aggiornamento grafo)
    ) -> SimulationRunState:
        """
        Avvia simulazione

        Args:
            simulation_id: ID simulazione
            platform: Piattaforma di esecuzione (twitter/reddit/parallel)
            max_rounds: Numero massimo turni simulazione (opzionale, per troncare simulazioni troppo lunghe)
            enable_graph_memory_update: Se aggiornare dinamicamente le attivita' Agent nel grafo Zep
            graph_id: ID grafo Zep (necessario quando si abilita l'aggiornamento grafo)

        Returns:
            SimulationRunState
        """
        # Verifica se gia' in esecuzione
        existing = cls.get_run_state(simulation_id)
        if existing and existing.runner_status in [RunnerStatus.RUNNING, RunnerStatus.STARTING]:
            raise ValueError(f"Simulazione gia' in esecuzione: {simulation_id}")

        # Carica configurazione simulazione
        sim_dir = os.path.join(cls.RUN_STATE_DIR, simulation_id)
        config_path = os.path.join(sim_dir, "simulation_config.json")

        if not os.path.exists(config_path):
            raise ValueError(f"Configurazione simulazione non esistente, chiamare prima l'interfaccia /prepare")

        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)

        # Inizializza stato esecuzione
        time_config = config.get("time_config", {})
        total_hours = time_config.get("total_simulation_hours", 72)
        minutes_per_round = time_config.get("minutes_per_round", 30)
        total_rounds = int(total_hours * 60 / minutes_per_round)

        # Se specificato numero massimo turni, tronca
        if max_rounds is not None and max_rounds > 0:
            original_rounds = total_rounds
            total_rounds = min(total_rounds, max_rounds)
            if total_rounds < original_rounds:
                logger.info(f"Turni troncati: {original_rounds} -> {total_rounds} (max_rounds={max_rounds})")

        state = SimulationRunState(
            simulation_id=simulation_id,
            runner_status=RunnerStatus.STARTING,
            total_rounds=total_rounds,
            total_simulation_hours=total_hours,
            started_at=datetime.now().isoformat(),
        )

        cls._save_run_state(state)

        # Se abilitato aggiornamento memoria grafo, crea l'aggiornatore
        if enable_graph_memory_update:
            if not graph_id:
                raise ValueError("Quando si abilita l'aggiornamento memoria grafo, e' necessario fornire graph_id")

            try:
                ZepGraphMemoryManager.create_updater(simulation_id, graph_id)
                cls._graph_memory_enabled[simulation_id] = True
                logger.info(f"Aggiornamento memoria grafo abilitato: simulation_id={simulation_id}, graph_id={graph_id}")
            except Exception as e:
                logger.error(f"Creazione aggiornatore memoria grafo fallita: {e}")
                cls._graph_memory_enabled[simulation_id] = False
        else:
            cls._graph_memory_enabled[simulation_id] = False

        # Determina quale script eseguire (script nella directory backend/scripts/)
        if platform == "twitter":
            script_name = "run_twitter_simulation.py"
            state.twitter_running = True
        elif platform == "reddit":
            script_name = "run_reddit_simulation.py"
            state.reddit_running = True
        else:
            script_name = "run_parallel_simulation.py"
            state.twitter_running = True
            state.reddit_running = True

        script_path = os.path.join(cls.SCRIPTS_DIR, script_name)

        if not os.path.exists(script_path):
            raise ValueError(f"Script non esistente: {script_path}")

        # Crea coda azioni
        action_queue = Queue()
        cls._action_queues[simulation_id] = action_queue

        # Avvia processo simulazione
        try:
            # Costruisci comando di esecuzione, usa percorso completo
            # Nuova struttura log:
            #   twitter/actions.jsonl - Log azioni Twitter
            #   reddit/actions.jsonl  - Log azioni Reddit
            #   simulation.log        - Log processo principale

            cmd = [
                sys.executable,  # Interprete Python
                script_path,
                "--config", config_path,  # Usa percorso completo file di configurazione
            ]

            # Se specificato numero massimo turni, aggiungilo ai parametri della riga di comando
            if max_rounds is not None and max_rounds > 0:
                cmd.extend(["--max-rounds", str(max_rounds)])

            # Crea file log principale, evita che il buffer della pipe stdout/stderr si riempia bloccando il processo
            main_log_path = os.path.join(sim_dir, "simulation.log")
            main_log_file = open(main_log_path, 'w', encoding='utf-8')

            # Imposta variabili d'ambiente del sottoprocesso, assicura codifica UTF-8 su Windows
            # Questo risolve i problemi di librerie di terze parti (come OASIS) che leggono file senza specificare la codifica
            env = os.environ.copy()
            env['PYTHONUTF8'] = '1'  # Supportato da Python 3.7+, fa si' che tutti gli open() usino UTF-8 di default
            env['PYTHONIOENCODING'] = 'utf-8'  # Assicura che stdout/stderr usino UTF-8

            # Imposta la directory di lavoro sulla directory di simulazione (i file come database verranno generati qui)
            # Usa start_new_session=True per creare un nuovo gruppo di processi, assicurando la terminazione di tutti i sottoprocessi tramite os.killpg
            process = subprocess.Popen(
                cmd,
                cwd=sim_dir,
                stdout=main_log_file,
                stderr=subprocess.STDOUT,  # stderr va nello stesso file
                text=True,
                encoding='utf-8',  # Specifica esplicitamente la codifica
                bufsize=1,
                env=env,  # Passa variabili d'ambiente con impostazioni UTF-8
                start_new_session=True,  # Crea nuovo gruppo di processi, assicura terminazione di tutti i processi correlati alla chiusura del server
            )

            # Salva gli handle dei file per chiuderli successivamente
            cls._stdout_files[simulation_id] = main_log_file
            cls._stderr_files[simulation_id] = None  # Non serve piu' uno stderr separato

            state.process_pid = process.pid
            state.runner_status = RunnerStatus.RUNNING
            cls._processes[simulation_id] = process
            cls._save_run_state(state)

            # Avvia thread di monitoraggio
            monitor_thread = threading.Thread(
                target=cls._monitor_simulation,
                args=(simulation_id,),
                daemon=True
            )
            monitor_thread.start()
            cls._monitor_threads[simulation_id] = monitor_thread

            logger.info(f"Simulazione avviata con successo: {simulation_id}, pid={process.pid}, platform={platform}")

        except Exception as e:
            state.runner_status = RunnerStatus.FAILED
            state.error = str(e)
            cls._save_run_state(state)
            raise

        return state

    @classmethod
    def _monitor_simulation(cls, simulation_id: str):
        """Monitora il processo di simulazione, analizza il log delle azioni"""
        sim_dir = os.path.join(cls.RUN_STATE_DIR, simulation_id)

        # Nuova struttura log: log azioni separati per piattaforma
        twitter_actions_log = os.path.join(sim_dir, "twitter", "actions.jsonl")
        reddit_actions_log = os.path.join(sim_dir, "reddit", "actions.jsonl")

        process = cls._processes.get(simulation_id)
        state = cls.get_run_state(simulation_id)

        if not process or not state:
            return

        twitter_position = 0
        reddit_position = 0

        try:
            while process.poll() is None:  # Il processo e' ancora in esecuzione
                # Leggi log azioni Twitter
                if os.path.exists(twitter_actions_log):
                    twitter_position = cls._read_action_log(
                        twitter_actions_log, twitter_position, state, "twitter"
                    )

                # Leggi log azioni Reddit
                if os.path.exists(reddit_actions_log):
                    reddit_position = cls._read_action_log(
                        reddit_actions_log, reddit_position, state, "reddit"
                    )

                # Aggiorna stato
                cls._save_run_state(state)
                time.sleep(2)

            # Dopo la terminazione del processo, leggi il log un'ultima volta
            if os.path.exists(twitter_actions_log):
                cls._read_action_log(twitter_actions_log, twitter_position, state, "twitter")
            if os.path.exists(reddit_actions_log):
                cls._read_action_log(reddit_actions_log, reddit_position, state, "reddit")

            # Processo terminato
            exit_code = process.returncode

            if exit_code == 0:
                state.runner_status = RunnerStatus.COMPLETED
                state.completed_at = datetime.now().isoformat()
                logger.info(f"Simulazione completata: {simulation_id}")
            else:
                state.runner_status = RunnerStatus.FAILED
                # Leggi informazioni errore dal file log principale
                main_log_path = os.path.join(sim_dir, "simulation.log")
                error_info = ""
                try:
                    if os.path.exists(main_log_path):
                        with open(main_log_path, 'r', encoding='utf-8') as f:
                            error_info = f.read()[-2000:]  # Prendi gli ultimi 2000 caratteri
                except Exception:
                    pass
                state.error = f"Codice di uscita processo: {exit_code}, errore: {error_info}"
                logger.error(f"Simulazione fallita: {simulation_id}, error={state.error}")

            state.twitter_running = False
            state.reddit_running = False
            cls._save_run_state(state)

        except Exception as e:
            logger.error(f"Eccezione nel thread di monitoraggio: {simulation_id}, error={str(e)}")
            state.runner_status = RunnerStatus.FAILED
            state.error = str(e)
            cls._save_run_state(state)

        finally:
            # Arresta l'aggiornatore memoria grafo
            if cls._graph_memory_enabled.get(simulation_id, False):
                try:
                    ZepGraphMemoryManager.stop_updater(simulation_id)
                    logger.info(f"Aggiornamento memoria grafo arrestato: simulation_id={simulation_id}")
                except Exception as e:
                    logger.error(f"Arresto aggiornatore memoria grafo fallito: {e}")
                cls._graph_memory_enabled.pop(simulation_id, None)

            # Pulisci risorse processo
            cls._processes.pop(simulation_id, None)
            cls._action_queues.pop(simulation_id, None)

            # Chiudi handle file log
            if simulation_id in cls._stdout_files:
                try:
                    cls._stdout_files[simulation_id].close()
                except Exception:
                    pass
                cls._stdout_files.pop(simulation_id, None)
            if simulation_id in cls._stderr_files and cls._stderr_files[simulation_id]:
                try:
                    cls._stderr_files[simulation_id].close()
                except Exception:
                    pass
                cls._stderr_files.pop(simulation_id, None)

    @classmethod
    def _read_action_log(
        cls,
        log_path: str,
        position: int,
        state: SimulationRunState,
        platform: str
    ) -> int:
        """
        Leggi il file log delle azioni

        Args:
            log_path: Percorso file log
            position: Posizione ultima lettura
            state: Oggetto stato esecuzione
            platform: Nome piattaforma (twitter/reddit)

        Returns:
            Nuova posizione di lettura
        """
        # Verifica se l'aggiornamento memoria grafo e' abilitato
        graph_memory_enabled = cls._graph_memory_enabled.get(state.simulation_id, False)
        graph_updater = None
        if graph_memory_enabled:
            graph_updater = ZepGraphMemoryManager.get_updater(state.simulation_id)

        try:
            with open(log_path, 'r', encoding='utf-8') as f:
                f.seek(position)
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            action_data = json.loads(line)

                            # Gestisci voci di tipo evento
                            if "event_type" in action_data:
                                event_type = action_data.get("event_type")

                                # Rileva evento simulation_end, segna piattaforma come completata
                                if event_type == "simulation_end":
                                    if platform == "twitter":
                                        state.twitter_completed = True
                                        state.twitter_running = False
                                        logger.info(f"Simulazione Twitter completata: {state.simulation_id}, total_rounds={action_data.get('total_rounds')}, total_actions={action_data.get('total_actions')}")
                                    elif platform == "reddit":
                                        state.reddit_completed = True
                                        state.reddit_running = False
                                        logger.info(f"Simulazione Reddit completata: {state.simulation_id}, total_rounds={action_data.get('total_rounds')}, total_actions={action_data.get('total_actions')}")

                                    # Verifica se tutte le piattaforme abilitate sono completate
                                    # Se e' stata eseguita una sola piattaforma, controlla solo quella
                                    # Se sono state eseguite entrambe, devono essere completate entrambe
                                    all_completed = cls._check_all_platforms_completed(state)
                                    if all_completed:
                                        state.runner_status = RunnerStatus.COMPLETED
                                        state.completed_at = datetime.now().isoformat()
                                        logger.info(f"Simulazione completata su tutte le piattaforme: {state.simulation_id}")

                                # Aggiorna informazioni turno (dall'evento round_end)
                                elif event_type == "round_end":
                                    round_num = action_data.get("round", 0)
                                    simulated_hours = action_data.get("simulated_hours", 0)

                                    # Aggiorna turni e tempo indipendenti per piattaforma
                                    if platform == "twitter":
                                        if round_num > state.twitter_current_round:
                                            state.twitter_current_round = round_num
                                        state.twitter_simulated_hours = simulated_hours
                                    elif platform == "reddit":
                                        if round_num > state.reddit_current_round:
                                            state.reddit_current_round = round_num
                                        state.reddit_simulated_hours = simulated_hours

                                    # Il turno complessivo prende il massimo delle due piattaforme
                                    if round_num > state.current_round:
                                        state.current_round = round_num
                                    # Il tempo complessivo prende il massimo delle due piattaforme
                                    state.simulated_hours = max(state.twitter_simulated_hours, state.reddit_simulated_hours)

                                continue

                            action = AgentAction(
                                round_num=action_data.get("round", 0),
                                timestamp=action_data.get("timestamp", datetime.now().isoformat()),
                                platform=platform,
                                agent_id=action_data.get("agent_id", 0),
                                agent_name=action_data.get("agent_name", ""),
                                action_type=action_data.get("action_type", ""),
                                action_args=action_data.get("action_args", {}),
                                result=action_data.get("result"),
                                success=action_data.get("success", True),
                            )
                            state.add_action(action)

                            # Aggiorna turno
                            if action.round_num and action.round_num > state.current_round:
                                state.current_round = action.round_num

                            # Se l'aggiornamento memoria grafo e' abilitato, invia l'attivita' a Zep
                            if graph_updater:
                                graph_updater.add_activity_from_dict(action_data, platform)

                        except json.JSONDecodeError:
                            pass
                return f.tell()
        except Exception as e:
            logger.warning(f"Lettura log azioni fallita: {log_path}, error={e}")
            return position

    @classmethod
    def _check_all_platforms_completed(cls, state: SimulationRunState) -> bool:
        """
        Verifica se tutte le piattaforme abilitate hanno completato la simulazione

        Determina se una piattaforma e' abilitata controllando l'esistenza del file actions.jsonl corrispondente

        Returns:
            True se tutte le piattaforme abilitate sono completate
        """
        sim_dir = os.path.join(cls.RUN_STATE_DIR, state.simulation_id)
        twitter_log = os.path.join(sim_dir, "twitter", "actions.jsonl")
        reddit_log = os.path.join(sim_dir, "reddit", "actions.jsonl")

        # Verifica quali piattaforme sono abilitate (tramite esistenza del file)
        twitter_enabled = os.path.exists(twitter_log)
        reddit_enabled = os.path.exists(reddit_log)

        # Se la piattaforma e' abilitata ma non completata, restituisci False
        if twitter_enabled and not state.twitter_completed:
            return False
        if reddit_enabled and not state.reddit_completed:
            return False

        # Almeno una piattaforma e' abilitata e completata
        return twitter_enabled or reddit_enabled

    @classmethod
    def _terminate_process(cls, process: subprocess.Popen, simulation_id: str, timeout: int = 10):
        """
        Termina il processo e i suoi sottoprocessi in modo cross-platform

        Args:
            process: Processo da terminare
            simulation_id: ID simulazione (per il log)
            timeout: Tempo di attesa per l'uscita del processo (secondi)
        """
        if IS_WINDOWS:
            # Windows: usa il comando taskkill per terminare l'albero dei processi
            # /F = termina forzatamente, /T = termina l'albero dei processi (inclusi i sottoprocessi)
            logger.info(f"Terminazione albero processi (Windows): simulation={simulation_id}, pid={process.pid}")
            try:
                # Prima prova terminazione gentile
                subprocess.run(
                    ['taskkill', '/PID', str(process.pid), '/T'],
                    capture_output=True,
                    timeout=5
                )
                try:
                    process.wait(timeout=timeout)
                except subprocess.TimeoutExpired:
                    # Terminazione forzata
                    logger.warning(f"Il processo non risponde, terminazione forzata: {simulation_id}")
                    subprocess.run(
                        ['taskkill', '/F', '/PID', str(process.pid), '/T'],
                        capture_output=True,
                        timeout=5
                    )
                    process.wait(timeout=5)
            except Exception as e:
                logger.warning(f"taskkill fallito, tentativo con terminate: {e}")
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
        else:
            # Unix: usa la terminazione per gruppo di processi
            # Dato che si usa start_new_session=True, l'ID del gruppo di processi coincide con il PID del processo principale
            pgid = os.getpgid(process.pid)
            logger.info(f"Terminazione gruppo processi (Unix): simulation={simulation_id}, pgid={pgid}")

            # Prima invia SIGTERM all'intero gruppo di processi
            os.killpg(pgid, signal.SIGTERM)

            try:
                process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                # Se dopo il timeout non si e' ancora chiuso, invia forzatamente SIGKILL
                logger.warning(f"Il gruppo processi non risponde a SIGTERM, terminazione forzata: {simulation_id}")
                os.killpg(pgid, signal.SIGKILL)
                process.wait(timeout=5)

    @classmethod
    def stop_simulation(cls, simulation_id: str) -> SimulationRunState:
        """Arresta simulazione"""
        state = cls.get_run_state(simulation_id)
        if not state:
            raise ValueError(f"Simulazione non esistente: {simulation_id}")

        if state.runner_status not in [RunnerStatus.RUNNING, RunnerStatus.PAUSED]:
            raise ValueError(f"Simulazione non in esecuzione: {simulation_id}, status={state.runner_status}")

        state.runner_status = RunnerStatus.STOPPING
        cls._save_run_state(state)

        # Termina processo
        process = cls._processes.get(simulation_id)
        if process and process.poll() is None:
            try:
                cls._terminate_process(process, simulation_id)
            except ProcessLookupError:
                # Il processo non esiste piu'
                pass
            except Exception as e:
                logger.error(f"Terminazione gruppo processi fallita: {simulation_id}, error={e}")
                # Fallback: termina direttamente il processo
                try:
                    process.terminate()
                    process.wait(timeout=5)
                except Exception:
                    process.kill()

        state.runner_status = RunnerStatus.STOPPED
        state.twitter_running = False
        state.reddit_running = False
        state.completed_at = datetime.now().isoformat()
        cls._save_run_state(state)

        # Arresta aggiornatore memoria grafo
        if cls._graph_memory_enabled.get(simulation_id, False):
            try:
                ZepGraphMemoryManager.stop_updater(simulation_id)
                logger.info(f"Aggiornamento memoria grafo arrestato: simulation_id={simulation_id}")
            except Exception as e:
                logger.error(f"Arresto aggiornatore memoria grafo fallito: {e}")
            cls._graph_memory_enabled.pop(simulation_id, None)

        logger.info(f"Simulazione arrestata: {simulation_id}")
        return state

    @classmethod
    def _read_actions_from_file(
        cls,
        file_path: str,
        default_platform: Optional[str] = None,
        platform_filter: Optional[str] = None,
        agent_id: Optional[int] = None,
        round_num: Optional[int] = None
    ) -> List[AgentAction]:
        """
        Leggi azioni da un singolo file di azioni

        Args:
            file_path: Percorso file log azioni
            default_platform: Piattaforma predefinita (usata quando il record azione non ha il campo platform)
            platform_filter: Filtra per piattaforma
            agent_id: Filtra per Agent ID
            round_num: Filtra per turno
        """
        if not os.path.exists(file_path):
            return []

        actions = []

        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue

                try:
                    data = json.loads(line)

                    # Salta record non-azione (come eventi simulation_start, round_start, round_end, ecc.)
                    if "event_type" in data:
                        continue

                    # Salta record senza agent_id (non sono azioni Agent)
                    if "agent_id" not in data:
                        continue

                    # Ottieni piattaforma: priorita' al platform nel record, altrimenti usa il predefinito
                    record_platform = data.get("platform") or default_platform or ""

                    # Filtra
                    if platform_filter and record_platform != platform_filter:
                        continue
                    if agent_id is not None and data.get("agent_id") != agent_id:
                        continue
                    if round_num is not None and data.get("round") != round_num:
                        continue

                    actions.append(AgentAction(
                        round_num=data.get("round", 0),
                        timestamp=data.get("timestamp", ""),
                        platform=record_platform,
                        agent_id=data.get("agent_id", 0),
                        agent_name=data.get("agent_name", ""),
                        action_type=data.get("action_type", ""),
                        action_args=data.get("action_args", {}),
                        result=data.get("result"),
                        success=data.get("success", True),
                    ))

                except json.JSONDecodeError:
                    continue

        return actions

    @classmethod
    def get_all_actions(
        cls,
        simulation_id: str,
        platform: Optional[str] = None,
        agent_id: Optional[int] = None,
        round_num: Optional[int] = None
    ) -> List[AgentAction]:
        """
        Ottieni lo storico completo delle azioni di tutte le piattaforme (senza limite di paginazione)

        Args:
            simulation_id: ID simulazione
            platform: Filtra per piattaforma (twitter/reddit)
            agent_id: Filtra per Agent
            round_num: Filtra per turno

        Returns:
            Lista completa delle azioni (ordinata per timestamp, le piu' recenti prima)
        """
        sim_dir = os.path.join(cls.RUN_STATE_DIR, simulation_id)
        actions = []

        # Leggi file azioni Twitter (imposta automaticamente platform come twitter in base al percorso file)
        twitter_actions_log = os.path.join(sim_dir, "twitter", "actions.jsonl")
        if not platform or platform == "twitter":
            actions.extend(cls._read_actions_from_file(
                twitter_actions_log,
                default_platform="twitter",  # Compila automaticamente il campo platform
                platform_filter=platform,
                agent_id=agent_id,
                round_num=round_num
            ))

        # Leggi file azioni Reddit (imposta automaticamente platform come reddit in base al percorso file)
        reddit_actions_log = os.path.join(sim_dir, "reddit", "actions.jsonl")
        if not platform or platform == "reddit":
            actions.extend(cls._read_actions_from_file(
                reddit_actions_log,
                default_platform="reddit",  # Compila automaticamente il campo platform
                platform_filter=platform,
                agent_id=agent_id,
                round_num=round_num
            ))

        # Se i file separati per piattaforma non esistono, prova a leggere il vecchio formato a file singolo
        if not actions:
            actions_log = os.path.join(sim_dir, "actions.jsonl")
            actions = cls._read_actions_from_file(
                actions_log,
                default_platform=None,  # Il file in formato vecchio dovrebbe avere il campo platform
                platform_filter=platform,
                agent_id=agent_id,
                round_num=round_num
            )

        # Ordina per timestamp (le piu' recenti prima)
        actions.sort(key=lambda x: x.timestamp, reverse=True)

        return actions

    @classmethod
    def get_actions(
        cls,
        simulation_id: str,
        limit: int = 100,
        offset: int = 0,
        platform: Optional[str] = None,
        agent_id: Optional[int] = None,
        round_num: Optional[int] = None
    ) -> List[AgentAction]:
        """
        Ottieni storico azioni (con paginazione)

        Args:
            simulation_id: ID simulazione
            limit: Limite numero risultati
            offset: Offset
            platform: Filtra per piattaforma
            agent_id: Filtra per Agent
            round_num: Filtra per turno

        Returns:
            Lista azioni
        """
        actions = cls.get_all_actions(
            simulation_id=simulation_id,
            platform=platform,
            agent_id=agent_id,
            round_num=round_num
        )

        # Paginazione
        return actions[offset:offset + limit]

    @classmethod
    def get_timeline(
        cls,
        simulation_id: str,
        start_round: int = 0,
        end_round: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Ottieni timeline della simulazione (riepilogo per turno)

        Args:
            simulation_id: ID simulazione
            start_round: Turno iniziale
            end_round: Turno finale

        Returns:
            Informazioni riepilogative per ogni turno
        """
        actions = cls.get_actions(simulation_id, limit=10000)

        # Raggruppa per turno
        rounds: Dict[int, Dict[str, Any]] = {}

        for action in actions:
            round_num = action.round_num

            if round_num < start_round:
                continue
            if end_round is not None and round_num > end_round:
                continue

            if round_num not in rounds:
                rounds[round_num] = {
                    "round_num": round_num,
                    "twitter_actions": 0,
                    "reddit_actions": 0,
                    "active_agents": set(),
                    "action_types": {},
                    "first_action_time": action.timestamp,
                    "last_action_time": action.timestamp,
                }

            r = rounds[round_num]

            if action.platform == "twitter":
                r["twitter_actions"] += 1
            else:
                r["reddit_actions"] += 1

            r["active_agents"].add(action.agent_id)
            r["action_types"][action.action_type] = r["action_types"].get(action.action_type, 0) + 1
            r["last_action_time"] = action.timestamp

        # Converti in lista
        result = []
        for round_num in sorted(rounds.keys()):
            r = rounds[round_num]
            result.append({
                "round_num": round_num,
                "twitter_actions": r["twitter_actions"],
                "reddit_actions": r["reddit_actions"],
                "total_actions": r["twitter_actions"] + r["reddit_actions"],
                "active_agents_count": len(r["active_agents"]),
                "active_agents": list(r["active_agents"]),
                "action_types": r["action_types"],
                "first_action_time": r["first_action_time"],
                "last_action_time": r["last_action_time"],
            })

        return result

    @classmethod
    def get_agent_stats(cls, simulation_id: str) -> List[Dict[str, Any]]:
        """
        Ottieni statistiche per ogni Agent

        Returns:
            Lista statistiche Agent
        """
        actions = cls.get_actions(simulation_id, limit=10000)

        agent_stats: Dict[int, Dict[str, Any]] = {}

        for action in actions:
            agent_id = action.agent_id

            if agent_id not in agent_stats:
                agent_stats[agent_id] = {
                    "agent_id": agent_id,
                    "agent_name": action.agent_name,
                    "total_actions": 0,
                    "twitter_actions": 0,
                    "reddit_actions": 0,
                    "action_types": {},
                    "first_action_time": action.timestamp,
                    "last_action_time": action.timestamp,
                }

            stats = agent_stats[agent_id]
            stats["total_actions"] += 1

            if action.platform == "twitter":
                stats["twitter_actions"] += 1
            else:
                stats["reddit_actions"] += 1

            stats["action_types"][action.action_type] = stats["action_types"].get(action.action_type, 0) + 1
            stats["last_action_time"] = action.timestamp

        # Ordina per numero totale azioni
        result = sorted(agent_stats.values(), key=lambda x: x["total_actions"], reverse=True)

        return result

    @classmethod
    def cleanup_simulation_logs(cls, simulation_id: str) -> Dict[str, Any]:
        """
        Pulisci i log di esecuzione della simulazione (per forzare il riavvio della simulazione)

        Elimina i seguenti file:
        - run_state.json
        - twitter/actions.jsonl
        - reddit/actions.jsonl
        - simulation.log
        - stdout.log / stderr.log
        - twitter_simulation.db (database simulazione)
        - reddit_simulation.db (database simulazione)
        - env_status.json (stato ambiente)

        Nota: non elimina i file di configurazione (simulation_config.json) e i file profile

        Args:
            simulation_id: ID simulazione

        Returns:
            Informazioni risultato pulizia
        """
        import shutil

        sim_dir = os.path.join(cls.RUN_STATE_DIR, simulation_id)

        if not os.path.exists(sim_dir):
            return {"success": True, "message": "La directory simulazione non esiste, nessuna pulizia necessaria"}

        cleaned_files = []
        errors = []

        # Lista file da eliminare (inclusi file database)
        files_to_delete = [
            "run_state.json",
            "simulation.log",
            "stdout.log",
            "stderr.log",
            "twitter_simulation.db",  # Database piattaforma Twitter
            "reddit_simulation.db",   # Database piattaforma Reddit
            "env_status.json",        # File stato ambiente
        ]

        # Lista directory da pulire (contengono log azioni)
        dirs_to_clean = ["twitter", "reddit"]

        # Elimina file
        for filename in files_to_delete:
            file_path = os.path.join(sim_dir, filename)
            if os.path.exists(file_path):
                try:
                    os.remove(file_path)
                    cleaned_files.append(filename)
                except Exception as e:
                    errors.append(f"Eliminazione {filename} fallita: {str(e)}")

        # Pulisci log azioni nelle directory delle piattaforme
        for dir_name in dirs_to_clean:
            dir_path = os.path.join(sim_dir, dir_name)
            if os.path.exists(dir_path):
                actions_file = os.path.join(dir_path, "actions.jsonl")
                if os.path.exists(actions_file):
                    try:
                        os.remove(actions_file)
                        cleaned_files.append(f"{dir_name}/actions.jsonl")
                    except Exception as e:
                        errors.append(f"Eliminazione {dir_name}/actions.jsonl fallita: {str(e)}")

        # Pulisci stato esecuzione in memoria
        if simulation_id in cls._run_states:
            del cls._run_states[simulation_id]

        logger.info(f"Pulizia log simulazione completata: {simulation_id}, file eliminati: {cleaned_files}")

        return {
            "success": len(errors) == 0,
            "cleaned_files": cleaned_files,
            "errors": errors if errors else None
        }

    # Flag per prevenire pulizia duplicata
    _cleanup_done = False

    @classmethod
    def cleanup_all_simulations(cls):
        """
        Pulisci tutti i processi di simulazione in esecuzione

        Chiamato alla chiusura del server, assicura che tutti i sottoprocessi vengano terminati
        """
        # Previeni pulizia duplicata
        if cls._cleanup_done:
            return
        cls._cleanup_done = True

        # Verifica se c'e' qualcosa da pulire (evita log inutili per processi vuoti)
        has_processes = bool(cls._processes)
        has_updaters = bool(cls._graph_memory_enabled)

        if not has_processes and not has_updaters:
            return  # Niente da pulire, ritorna silenziosamente

        logger.info("Pulizia di tutti i processi di simulazione in corso...")

        # Prima arresta tutti gli aggiornatori memoria grafo (stop_all stampa i propri log internamente)
        try:
            ZepGraphMemoryManager.stop_all()
        except Exception as e:
            logger.error(f"Arresto aggiornatore memoria grafo fallito: {e}")
        cls._graph_memory_enabled.clear()

        # Copia il dizionario per evitare modifiche durante l'iterazione
        processes = list(cls._processes.items())

        for simulation_id, process in processes:
            try:
                if process.poll() is None:  # Il processo e' ancora in esecuzione
                    logger.info(f"Terminazione processo simulazione: {simulation_id}, pid={process.pid}")

                    try:
                        # Usa il metodo di terminazione cross-platform
                        cls._terminate_process(process, simulation_id, timeout=5)
                    except (ProcessLookupError, OSError):
                        # Il processo potrebbe non esistere piu', prova terminazione diretta
                        try:
                            process.terminate()
                            process.wait(timeout=3)
                        except Exception:
                            process.kill()

                    # Aggiorna run_state.json
                    state = cls.get_run_state(simulation_id)
                    if state:
                        state.runner_status = RunnerStatus.STOPPED
                        state.twitter_running = False
                        state.reddit_running = False
                        state.completed_at = datetime.now().isoformat()
                        state.error = "Server chiuso, simulazione terminata"
                        cls._save_run_state(state)

                    # Aggiorna anche state.json, imposta stato a stopped
                    try:
                        sim_dir = os.path.join(cls.RUN_STATE_DIR, simulation_id)
                        state_file = os.path.join(sim_dir, "state.json")
                        logger.info(f"Tentativo aggiornamento state.json: {state_file}")
                        if os.path.exists(state_file):
                            with open(state_file, 'r', encoding='utf-8') as f:
                                state_data = json.load(f)
                            state_data['status'] = 'stopped'
                            state_data['updated_at'] = datetime.now().isoformat()
                            with open(state_file, 'w', encoding='utf-8') as f:
                                json.dump(state_data, f, indent=2, ensure_ascii=False)
                            logger.info(f"state.json aggiornato a stopped: {simulation_id}")
                        else:
                            logger.warning(f"state.json non esiste: {state_file}")
                    except Exception as state_err:
                        logger.warning(f"Aggiornamento state.json fallito: {simulation_id}, error={state_err}")

            except Exception as e:
                logger.error(f"Pulizia processo fallita: {simulation_id}, error={e}")

        # Pulisci handle file
        for simulation_id, file_handle in list(cls._stdout_files.items()):
            try:
                if file_handle:
                    file_handle.close()
            except Exception:
                pass
        cls._stdout_files.clear()

        for simulation_id, file_handle in list(cls._stderr_files.items()):
            try:
                if file_handle:
                    file_handle.close()
            except Exception:
                pass
        cls._stderr_files.clear()

        # Pulisci stato in memoria
        cls._processes.clear()
        cls._action_queues.clear()

        logger.info("Pulizia processi simulazione completata")

    @classmethod
    def register_cleanup(cls):
        """
        Registra la funzione di pulizia

        Chiamato all'avvio dell'applicazione Flask, assicura che alla chiusura del server tutti i processi di simulazione vengano puliti
        """
        global _cleanup_registered

        if _cleanup_registered:
            return

        # In modalita' debug Flask, registra la pulizia solo nel sottoprocesso reloader (il processo che esegue effettivamente l'app)
        # WERKZEUG_RUN_MAIN=true indica che e' il sottoprocesso reloader
        # Se non e' in modalita' debug, questa variabile d'ambiente non esiste, e bisogna comunque registrare
        is_reloader_process = os.environ.get('WERKZEUG_RUN_MAIN') == 'true'
        is_debug_mode = os.environ.get('FLASK_DEBUG') == '1' or os.environ.get('WERKZEUG_RUN_MAIN') is not None

        # In modalita' debug, registra solo nel sottoprocesso reloader; in modalita' non-debug, registra sempre
        if is_debug_mode and not is_reloader_process:
            _cleanup_registered = True  # Segna come registrato, impedisce al sottoprocesso di riprovare
            return

        # Salva i gestori di segnale originali
        original_sigint = signal.getsignal(signal.SIGINT)
        original_sigterm = signal.getsignal(signal.SIGTERM)
        # SIGHUP esiste solo su sistemi Unix (macOS/Linux), non su Windows
        original_sighup = None
        has_sighup = hasattr(signal, 'SIGHUP')
        if has_sighup:
            original_sighup = signal.getsignal(signal.SIGHUP)

        def cleanup_handler(signum=None, frame=None):
            """Gestore segnale: prima pulisce i processi di simulazione, poi chiama il gestore originale"""
            # Stampa log solo quando ci sono processi da pulire
            if cls._processes or cls._graph_memory_enabled:
                logger.info(f"Segnale {signum} ricevuto, inizio pulizia...")
            cls.cleanup_all_simulations()

            # Chiama il gestore di segnale originale, lascia che Flask esca normalmente
            if signum == signal.SIGINT and callable(original_sigint):
                original_sigint(signum, frame)
            elif signum == signal.SIGTERM and callable(original_sigterm):
                original_sigterm(signum, frame)
            elif has_sighup and signum == signal.SIGHUP:
                # SIGHUP: inviato alla chiusura del terminale
                if callable(original_sighup):
                    original_sighup(signum, frame)
                else:
                    # Comportamento predefinito: uscita normale
                    sys.exit(0)
            else:
                # Se il gestore originale non e' invocabile (come SIG_DFL), usa il comportamento predefinito
                raise KeyboardInterrupt

        # Registra gestore atexit (come backup)
        atexit.register(cls.cleanup_all_simulations)

        # Registra gestori di segnale (solo nel thread principale)
        try:
            # SIGTERM: segnale predefinito del comando kill
            signal.signal(signal.SIGTERM, cleanup_handler)
            # SIGINT: Ctrl+C
            signal.signal(signal.SIGINT, cleanup_handler)
            # SIGHUP: chiusura terminale (solo sistemi Unix)
            if has_sighup:
                signal.signal(signal.SIGHUP, cleanup_handler)
        except ValueError:
            # Non nel thread principale, si puo' usare solo atexit
            logger.warning("Impossibile registrare i gestori di segnale (non nel thread principale), si usa solo atexit")

        _cleanup_registered = True

    @classmethod
    def get_running_simulations(cls) -> List[str]:
        """
        Ottieni la lista degli ID di tutte le simulazioni in esecuzione
        """
        running = []
        for sim_id, process in cls._processes.items():
            if process.poll() is None:
                running.append(sim_id)
        return running

    # ============== Funzionalita' Interview ==============

    @classmethod
    def check_env_alive(cls, simulation_id: str) -> bool:
        """
        Verifica se l'ambiente di simulazione e' attivo (puo' ricevere comandi Interview)

        Args:
            simulation_id: ID simulazione

        Returns:
            True indica che l'ambiente e' attivo, False indica che l'ambiente e' chiuso
        """
        sim_dir = os.path.join(cls.RUN_STATE_DIR, simulation_id)
        if not os.path.exists(sim_dir):
            return False

        ipc_client = SimulationIPCClient(sim_dir)
        return ipc_client.check_env_alive()

    @classmethod
    def get_env_status_detail(cls, simulation_id: str) -> Dict[str, Any]:
        """
        Ottieni informazioni dettagliate sullo stato dell'ambiente di simulazione

        Args:
            simulation_id: ID simulazione

        Returns:
            Dizionario dettagli stato, include status, twitter_available, reddit_available, timestamp
        """
        sim_dir = os.path.join(cls.RUN_STATE_DIR, simulation_id)
        status_file = os.path.join(sim_dir, "env_status.json")

        default_status = {
            "status": "stopped",
            "twitter_available": False,
            "reddit_available": False,
            "timestamp": None
        }

        if not os.path.exists(status_file):
            return default_status

        try:
            with open(status_file, 'r', encoding='utf-8') as f:
                status = json.load(f)
            return {
                "status": status.get("status", "stopped"),
                "twitter_available": status.get("twitter_available", False),
                "reddit_available": status.get("reddit_available", False),
                "timestamp": status.get("timestamp")
            }
        except (json.JSONDecodeError, OSError):
            return default_status

    @classmethod
    def interview_agent(
        cls,
        simulation_id: str,
        agent_id: int,
        prompt: str,
        platform: str = None,
        timeout: float = 60.0
    ) -> Dict[str, Any]:
        """
        Intervista un singolo Agent

        Args:
            simulation_id: ID simulazione
            agent_id: Agent ID
            prompt: Domanda dell'intervista
            platform: Piattaforma specificata (opzionale)
                - "twitter": Intervista solo piattaforma Twitter
                - "reddit": Intervista solo piattaforma Reddit
                - None: In simulazione doppia piattaforma intervista entrambe, restituisce risultato integrato
            timeout: Tempo di timeout (secondi)

        Returns:
            Dizionario risultato intervista

        Raises:
            ValueError: Simulazione non esistente o ambiente non in esecuzione
            TimeoutError: Timeout in attesa della risposta
        """
        sim_dir = os.path.join(cls.RUN_STATE_DIR, simulation_id)
        if not os.path.exists(sim_dir):
            raise ValueError(f"Simulazione non esistente: {simulation_id}")

        ipc_client = SimulationIPCClient(sim_dir)

        if not ipc_client.check_env_alive():
            raise ValueError(f"L'ambiente di simulazione non e' in esecuzione o e' chiuso, impossibile eseguire l'Interview: {simulation_id}")

        logger.info(f"Invio comando Interview: simulation_id={simulation_id}, agent_id={agent_id}, platform={platform}")

        response = ipc_client.send_interview(
            agent_id=agent_id,
            prompt=prompt,
            platform=platform,
            timeout=timeout
        )

        if response.status.value == "completed":
            return {
                "success": True,
                "agent_id": agent_id,
                "prompt": prompt,
                "result": response.result,
                "timestamp": response.timestamp
            }
        else:
            return {
                "success": False,
                "agent_id": agent_id,
                "prompt": prompt,
                "error": response.error,
                "timestamp": response.timestamp
            }

    @classmethod
    def interview_agents_batch(
        cls,
        simulation_id: str,
        interviews: List[Dict[str, Any]],
        platform: str = None,
        timeout: float = 120.0
    ) -> Dict[str, Any]:
        """
        Intervista batch di piu' Agent

        Args:
            simulation_id: ID simulazione
            interviews: Lista interviste, ogni elemento contiene {"agent_id": int, "prompt": str, "platform": str (opzionale)}
            platform: Piattaforma predefinita (opzionale, viene sovrascritta dal platform di ogni singola intervista)
                - "twitter": Intervista predefinita solo piattaforma Twitter
                - "reddit": Intervista predefinita solo piattaforma Reddit
                - None: In simulazione doppia piattaforma, ogni Agent viene intervistato su entrambe le piattaforme
            timeout: Tempo di timeout (secondi)

        Returns:
            Dizionario risultato intervista batch

        Raises:
            ValueError: Simulazione non esistente o ambiente non in esecuzione
            TimeoutError: Timeout in attesa della risposta
        """
        sim_dir = os.path.join(cls.RUN_STATE_DIR, simulation_id)
        if not os.path.exists(sim_dir):
            raise ValueError(f"Simulazione non esistente: {simulation_id}")

        ipc_client = SimulationIPCClient(sim_dir)

        if not ipc_client.check_env_alive():
            raise ValueError(f"L'ambiente di simulazione non e' in esecuzione o e' chiuso, impossibile eseguire l'Interview: {simulation_id}")

        logger.info(f"Invio comando Interview batch: simulation_id={simulation_id}, count={len(interviews)}, platform={platform}")

        response = ipc_client.send_batch_interview(
            interviews=interviews,
            platform=platform,
            timeout=timeout
        )

        if response.status.value == "completed":
            return {
                "success": True,
                "interviews_count": len(interviews),
                "result": response.result,
                "timestamp": response.timestamp
            }
        else:
            return {
                "success": False,
                "interviews_count": len(interviews),
                "error": response.error,
                "timestamp": response.timestamp
            }

    @classmethod
    def interview_all_agents(
        cls,
        simulation_id: str,
        prompt: str,
        platform: str = None,
        timeout: float = 180.0
    ) -> Dict[str, Any]:
        """
        Intervista tutti gli Agent (intervista globale)

        Usa la stessa domanda per intervistare tutti gli Agent nella simulazione

        Args:
            simulation_id: ID simulazione
            prompt: Domanda dell'intervista (stessa domanda per tutti gli Agent)
            platform: Piattaforma specificata (opzionale)
                - "twitter": Intervista solo piattaforma Twitter
                - "reddit": Intervista solo piattaforma Reddit
                - None: In simulazione doppia piattaforma, ogni Agent viene intervistato su entrambe le piattaforme
            timeout: Tempo di timeout (secondi)

        Returns:
            Dizionario risultato intervista globale
        """
        sim_dir = os.path.join(cls.RUN_STATE_DIR, simulation_id)
        if not os.path.exists(sim_dir):
            raise ValueError(f"Simulazione non esistente: {simulation_id}")

        # Ottieni informazioni di tutti gli Agent dal file di configurazione
        config_path = os.path.join(sim_dir, "simulation_config.json")
        if not os.path.exists(config_path):
            raise ValueError(f"Configurazione simulazione non esistente: {simulation_id}")

        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)

        agent_configs = config.get("agent_configs", [])
        if not agent_configs:
            raise ValueError(f"Nessun Agent nella configurazione simulazione: {simulation_id}")

        # Costruisci lista interviste batch
        interviews = []
        for agent_config in agent_configs:
            agent_id = agent_config.get("agent_id")
            if agent_id is not None:
                interviews.append({
                    "agent_id": agent_id,
                    "prompt": prompt
                })

        logger.info(f"Invio comando Interview globale: simulation_id={simulation_id}, agent_count={len(interviews)}, platform={platform}")

        return cls.interview_agents_batch(
            simulation_id=simulation_id,
            interviews=interviews,
            platform=platform,
            timeout=timeout
        )

    @classmethod
    def close_simulation_env(
        cls,
        simulation_id: str,
        timeout: float = 30.0
    ) -> Dict[str, Any]:
        """
        Chiudi l'ambiente di simulazione (senza arrestare il processo di simulazione)

        Invia comando di chiusura ambiente alla simulazione, facendola uscire in modo ordinato dalla modalita' attesa comandi

        Args:
            simulation_id: ID simulazione
            timeout: Tempo di timeout (secondi)

        Returns:
            Dizionario risultato operazione
        """
        sim_dir = os.path.join(cls.RUN_STATE_DIR, simulation_id)
        if not os.path.exists(sim_dir):
            raise ValueError(f"Simulazione non esistente: {simulation_id}")

        ipc_client = SimulationIPCClient(sim_dir)

        if not ipc_client.check_env_alive():
            return {
                "success": True,
                "message": "L'ambiente e' gia' chiuso"
            }

        logger.info(f"Invio comando chiusura ambiente: simulation_id={simulation_id}")

        try:
            response = ipc_client.send_close_env(timeout=timeout)

            return {
                "success": response.status.value == "completed",
                "message": "Comando chiusura ambiente inviato",
                "result": response.result,
                "timestamp": response.timestamp
            }
        except TimeoutError:
            # Il timeout potrebbe essere dovuto al fatto che l'ambiente si sta chiudendo
            return {
                "success": True,
                "message": "Comando chiusura ambiente inviato (timeout in attesa risposta, l'ambiente potrebbe essere in fase di chiusura)"
            }

    @classmethod
    def _get_interview_history_from_db(
        cls,
        db_path: str,
        platform_name: str,
        agent_id: Optional[int] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Ottieni storico Interview da un singolo database"""
        import sqlite3

        if not os.path.exists(db_path):
            return []

        results = []

        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()

            if agent_id is not None:
                cursor.execute("""
                    SELECT user_id, info, created_at
                    FROM trace
                    WHERE action = 'interview' AND user_id = ?
                    ORDER BY created_at DESC
                    LIMIT ?
                """, (agent_id, limit))
            else:
                cursor.execute("""
                    SELECT user_id, info, created_at
                    FROM trace
                    WHERE action = 'interview'
                    ORDER BY created_at DESC
                    LIMIT ?
                """, (limit,))

            for user_id, info_json, created_at in cursor.fetchall():
                try:
                    info = json.loads(info_json) if info_json else {}
                except json.JSONDecodeError:
                    info = {"raw": info_json}

                results.append({
                    "agent_id": user_id,
                    "response": info.get("response", info),
                    "prompt": info.get("prompt", ""),
                    "timestamp": created_at,
                    "platform": platform_name
                })

            conn.close()

        except Exception as e:
            logger.error(f"Lettura storico Interview fallita ({platform_name}): {e}")

        return results

    @classmethod
    def get_interview_history(
        cls,
        simulation_id: str,
        platform: str = None,
        agent_id: Optional[int] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Ottieni storico Interview (lettura dal database)

        Args:
            simulation_id: ID simulazione
            platform: Tipo piattaforma (reddit/twitter/None)
                - "reddit": Ottieni solo lo storico della piattaforma Reddit
                - "twitter": Ottieni solo lo storico della piattaforma Twitter
                - None: Ottieni lo storico di entrambe le piattaforme
            agent_id: Specifica Agent ID (opzionale, ottieni solo lo storico di quell'Agent)
            limit: Limite numero risultati per piattaforma

        Returns:
            Lista storico Interview
        """
        sim_dir = os.path.join(cls.RUN_STATE_DIR, simulation_id)

        results = []

        # Determina le piattaforme da interrogare
        if platform in ("reddit", "twitter"):
            platforms = [platform]
        else:
            # Senza specificare platform, interroga entrambe le piattaforme
            platforms = ["twitter", "reddit"]

        for p in platforms:
            db_path = os.path.join(sim_dir, f"{p}_simulation.db")
            platform_results = cls._get_interview_history_from_db(
                db_path=db_path,
                platform_name=p,
                agent_id=agent_id,
                limit=limit
            )
            results.extend(platform_results)

        # Ordina per timestamp decrescente
        results.sort(key=lambda x: x.get("timestamp", ""), reverse=True)

        # Se sono state interrogate piu' piattaforme, limita il totale
        if len(platforms) > 1 and len(results) > limit:
            results = results[:limit]

        return results
