"""
Modulo di comunicazione IPC per la simulazione
Per la comunicazione inter-processo tra il backend Flask e lo script di simulazione

Implementa un semplice schema comando/risposta tramite il file system:
1. Flask scrive i comandi nella directory commands/
2. Lo script di simulazione interroga la directory comandi, esegue i comandi e scrive le risposte nella directory responses/
3. Flask interroga la directory risposte per ottenere i risultati
"""

import os
import json
import time
import uuid
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from ..utils.logger import get_logger

logger = get_logger('mirofish.simulation_ipc')


class CommandType(str, Enum):
    """Tipo di comando"""
    INTERVIEW = "interview"           # Intervista singolo Agent
    BATCH_INTERVIEW = "batch_interview"  # Intervista batch
    CLOSE_ENV = "close_env"           # Chiudi ambiente


class CommandStatus(str, Enum):
    """Stato del comando"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class IPCCommand:
    """Comando IPC"""
    command_id: str
    command_type: CommandType
    args: Dict[str, Any]
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "command_id": self.command_id,
            "command_type": self.command_type.value,
            "args": self.args,
            "timestamp": self.timestamp
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'IPCCommand':
        return cls(
            command_id=data["command_id"],
            command_type=CommandType(data["command_type"]),
            args=data.get("args", {}),
            timestamp=data.get("timestamp", datetime.now().isoformat())
        )


@dataclass
class IPCResponse:
    """Risposta IPC"""
    command_id: str
    status: CommandStatus
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "command_id": self.command_id,
            "status": self.status.value,
            "result": self.result,
            "error": self.error,
            "timestamp": self.timestamp
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'IPCResponse':
        return cls(
            command_id=data["command_id"],
            status=CommandStatus(data["status"]),
            result=data.get("result"),
            error=data.get("error"),
            timestamp=data.get("timestamp", datetime.now().isoformat())
        )


class SimulationIPCClient:
    """
    Client IPC della simulazione (usato lato Flask)

    Per inviare comandi al processo di simulazione e attendere le risposte
    """

    def __init__(self, simulation_dir: str):
        """
        Inizializza il client IPC

        Args:
            simulation_dir: Directory dati simulazione
        """
        self.simulation_dir = simulation_dir
        self.commands_dir = os.path.join(simulation_dir, "ipc_commands")
        self.responses_dir = os.path.join(simulation_dir, "ipc_responses")

        # Assicura che le directory esistano
        os.makedirs(self.commands_dir, exist_ok=True)
        os.makedirs(self.responses_dir, exist_ok=True)

    def send_command(
        self,
        command_type: CommandType,
        args: Dict[str, Any],
        timeout: float = 60.0,
        poll_interval: float = 0.5
    ) -> IPCResponse:
        """
        Invia comando e attende risposta

        Args:
            command_type: Tipo di comando
            args: Parametri del comando
            timeout: Tempo di timeout (secondi)
            poll_interval: Intervallo di polling (secondi)

        Returns:
            IPCResponse

        Raises:
            TimeoutError: Timeout in attesa della risposta
        """
        command_id = str(uuid.uuid4())
        command = IPCCommand(
            command_id=command_id,
            command_type=command_type,
            args=args
        )

        # Scrivi file comando
        command_file = os.path.join(self.commands_dir, f"{command_id}.json")
        with open(command_file, 'w', encoding='utf-8') as f:
            json.dump(command.to_dict(), f, ensure_ascii=False, indent=2)

        logger.info(f"Comando IPC inviato: {command_type.value}, command_id={command_id}")

        # Attendi risposta
        response_file = os.path.join(self.responses_dir, f"{command_id}.json")
        start_time = time.time()

        while time.time() - start_time < timeout:
            if os.path.exists(response_file):
                try:
                    with open(response_file, 'r', encoding='utf-8') as f:
                        response_data = json.load(f)
                    response = IPCResponse.from_dict(response_data)

                    # Pulisci file comando e risposta
                    try:
                        os.remove(command_file)
                        os.remove(response_file)
                    except OSError:
                        pass

                    logger.info(f"Risposta IPC ricevuta: command_id={command_id}, status={response.status.value}")
                    return response
                except (json.JSONDecodeError, KeyError) as e:
                    logger.warning(f"Analisi risposta fallita: {e}")

            time.sleep(poll_interval)

        # Timeout
        logger.error(f"Timeout in attesa risposta IPC: command_id={command_id}")

        # Pulisci file comando
        try:
            os.remove(command_file)
        except OSError:
            pass

        raise TimeoutError(f"Timeout in attesa risposta comando ({timeout} secondi)")

    def send_interview(
        self,
        agent_id: int,
        prompt: str,
        platform: str = None,
        timeout: float = 60.0
    ) -> IPCResponse:
        """
        Invia comando intervista singolo Agent

        Args:
            agent_id: Agent ID
            prompt: Domanda dell'intervista
            platform: Piattaforma specificata (opzionale)
                - "twitter": Intervista solo piattaforma Twitter
                - "reddit": Intervista solo piattaforma Reddit
                - None: In simulazione doppia piattaforma intervista entrambe, in singola piattaforma intervista quella attiva
            timeout: Tempo di timeout

        Returns:
            IPCResponse, il campo result contiene il risultato dell'intervista
        """
        args = {
            "agent_id": agent_id,
            "prompt": prompt
        }
        if platform:
            args["platform"] = platform

        return self.send_command(
            command_type=CommandType.INTERVIEW,
            args=args,
            timeout=timeout
        )

    def send_batch_interview(
        self,
        interviews: List[Dict[str, Any]],
        platform: str = None,
        timeout: float = 120.0
    ) -> IPCResponse:
        """
        Invia comando intervista batch

        Args:
            interviews: Lista interviste, ogni elemento contiene {"agent_id": int, "prompt": str, "platform": str (opzionale)}
            platform: Piattaforma predefinita (opzionale, viene sovrascritta dal platform di ogni singola intervista)
                - "twitter": Intervista predefinita solo piattaforma Twitter
                - "reddit": Intervista predefinita solo piattaforma Reddit
                - None: In simulazione doppia piattaforma, ogni Agent viene intervistato su entrambe le piattaforme
            timeout: Tempo di timeout

        Returns:
            IPCResponse, il campo result contiene tutti i risultati delle interviste
        """
        args = {"interviews": interviews}
        if platform:
            args["platform"] = platform

        return self.send_command(
            command_type=CommandType.BATCH_INTERVIEW,
            args=args,
            timeout=timeout
        )

    def send_close_env(self, timeout: float = 30.0) -> IPCResponse:
        """
        Invia comando chiusura ambiente

        Args:
            timeout: Tempo di timeout

        Returns:
            IPCResponse
        """
        return self.send_command(
            command_type=CommandType.CLOSE_ENV,
            args={},
            timeout=timeout
        )

    def check_env_alive(self) -> bool:
        """
        Verifica se l'ambiente di simulazione e' attivo

        Controlla tramite il file env_status.json
        """
        status_file = os.path.join(self.simulation_dir, "env_status.json")
        if not os.path.exists(status_file):
            return False

        try:
            with open(status_file, 'r', encoding='utf-8') as f:
                status = json.load(f)
            return status.get("status") == "alive"
        except (json.JSONDecodeError, OSError):
            return False


class SimulationIPCServer:
    """
    Server IPC della simulazione (usato lato script di simulazione)

    Interroga la directory comandi, esegue i comandi e restituisce le risposte
    """

    def __init__(self, simulation_dir: str):
        """
        Inizializza il server IPC

        Args:
            simulation_dir: Directory dati simulazione
        """
        self.simulation_dir = simulation_dir
        self.commands_dir = os.path.join(simulation_dir, "ipc_commands")
        self.responses_dir = os.path.join(simulation_dir, "ipc_responses")

        # Assicura che le directory esistano
        os.makedirs(self.commands_dir, exist_ok=True)
        os.makedirs(self.responses_dir, exist_ok=True)

        # Stato dell'ambiente
        self._running = False

    def start(self):
        """Segna il server come in esecuzione"""
        self._running = True
        self._update_env_status("alive")

    def stop(self):
        """Segna il server come arrestato"""
        self._running = False
        self._update_env_status("stopped")

    def _update_env_status(self, status: str):
        """Aggiorna il file di stato dell'ambiente"""
        status_file = os.path.join(self.simulation_dir, "env_status.json")
        with open(status_file, 'w', encoding='utf-8') as f:
            json.dump({
                "status": status,
                "timestamp": datetime.now().isoformat()
            }, f, ensure_ascii=False, indent=2)

    def poll_commands(self) -> Optional[IPCCommand]:
        """
        Interroga la directory comandi, restituisce il primo comando in attesa

        Returns:
            IPCCommand oppure None
        """
        if not os.path.exists(self.commands_dir):
            return None

        # Ottieni i file comando ordinati per data
        command_files = []
        for filename in os.listdir(self.commands_dir):
            if filename.endswith('.json'):
                filepath = os.path.join(self.commands_dir, filename)
                command_files.append((filepath, os.path.getmtime(filepath)))

        command_files.sort(key=lambda x: x[1])

        for filepath, _ in command_files:
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                return IPCCommand.from_dict(data)
            except (json.JSONDecodeError, KeyError, OSError) as e:
                logger.warning(f"Lettura file comando fallita: {filepath}, {e}")
                continue

        return None

    def send_response(self, response: IPCResponse):
        """
        Invia risposta

        Args:
            response: Risposta IPC
        """
        response_file = os.path.join(self.responses_dir, f"{response.command_id}.json")
        with open(response_file, 'w', encoding='utf-8') as f:
            json.dump(response.to_dict(), f, ensure_ascii=False, indent=2)

        # Elimina file comando
        command_file = os.path.join(self.commands_dir, f"{response.command_id}.json")
        try:
            os.remove(command_file)
        except OSError:
            pass

    def send_success(self, command_id: str, result: Dict[str, Any]):
        """Invia risposta di successo"""
        self.send_response(IPCResponse(
            command_id=command_id,
            status=CommandStatus.COMPLETED,
            result=result
        ))

    def send_error(self, command_id: str, error: str):
        """Invia risposta di errore"""
        self.send_response(IPCResponse(
            command_id=command_id,
            status=CommandStatus.FAILED,
            error=error
        ))
