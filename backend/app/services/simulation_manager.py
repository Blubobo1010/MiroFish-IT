"""
Gestore simulazione OASIS
Gestisce simulazioni parallele su doppia piattaforma Twitter e Reddit
Utilizza script preimpostati + generazione intelligente parametri di configurazione tramite LLM
"""

import os
import json
import shutil
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from ..config import Config
from ..utils.logger import get_logger
from .zep_entity_reader import ZepEntityReader, FilteredEntities
from .oasis_profile_generator import OasisProfileGenerator, OasisAgentProfile
from .simulation_config_generator import SimulationConfigGenerator, SimulationParameters

logger = get_logger('mirofish.simulation')


class SimulationStatus(str, Enum):
    """Stato della simulazione"""
    CREATED = "created"
    PREPARING = "preparing"
    READY = "ready"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"      # Simulazione fermata manualmente
    COMPLETED = "completed"  # Simulazione completata naturalmente
    FAILED = "failed"


class PlatformType(str, Enum):
    """Tipo di piattaforma"""
    TWITTER = "twitter"
    REDDIT = "reddit"


@dataclass
class SimulationState:
    """Stato della simulazione"""
    simulation_id: str
    project_id: str
    graph_id: str

    # Stato abilitazione piattaforme
    enable_twitter: bool = True
    enable_reddit: bool = True

    # Stato
    status: SimulationStatus = SimulationStatus.CREATED

    # Dati fase di preparazione
    entities_count: int = 0
    profiles_count: int = 0
    entity_types: List[str] = field(default_factory=list)

    # Informazioni generazione configurazione
    config_generated: bool = False
    config_reasoning: str = ""

    # Dati runtime
    current_round: int = 0
    twitter_status: str = "not_started"
    reddit_status: str = "not_started"

    # Timestamp
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())

    # Informazioni errore
    error: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Dizionario stato completo (uso interno)"""
        return {
            "simulation_id": self.simulation_id,
            "project_id": self.project_id,
            "graph_id": self.graph_id,
            "enable_twitter": self.enable_twitter,
            "enable_reddit": self.enable_reddit,
            "status": self.status.value,
            "entities_count": self.entities_count,
            "profiles_count": self.profiles_count,
            "entity_types": self.entity_types,
            "config_generated": self.config_generated,
            "config_reasoning": self.config_reasoning,
            "current_round": self.current_round,
            "twitter_status": self.twitter_status,
            "reddit_status": self.reddit_status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "error": self.error,
        }
    
    def to_simple_dict(self) -> Dict[str, Any]:
        """Dizionario stato semplificato (per risposta API)"""
        return {
            "simulation_id": self.simulation_id,
            "project_id": self.project_id,
            "graph_id": self.graph_id,
            "status": self.status.value,
            "entities_count": self.entities_count,
            "profiles_count": self.profiles_count,
            "entity_types": self.entity_types,
            "config_generated": self.config_generated,
            "error": self.error,
        }


class SimulationManager:
    """
    Gestore simulazione

    Funzionalita' principali:
    1. Leggere e filtrare entita' dal grafo Zep
    2. Generare OASIS Agent Profile
    3. Generare intelligentemente parametri di configurazione simulazione tramite LLM
    4. Preparare tutti i file necessari per gli script preimpostati
    """

    # Directory di archiviazione dati simulazione
    SIMULATION_DATA_DIR = os.path.join(
        os.path.dirname(__file__), 
        '../../uploads/simulations'
    )
    
    def __init__(self):
        # Assicurarsi che la directory esista
        os.makedirs(self.SIMULATION_DATA_DIR, exist_ok=True)

        # Cache stato simulazione in memoria
        self._simulations: Dict[str, SimulationState] = {}
    
    def _get_simulation_dir(self, simulation_id: str) -> str:
        """Ottieni directory dati simulazione"""
        sim_dir = os.path.join(self.SIMULATION_DATA_DIR, simulation_id)
        os.makedirs(sim_dir, exist_ok=True)
        return sim_dir
    
    def _save_simulation_state(self, state: SimulationState):
        """Salva stato simulazione su file"""
        sim_dir = self._get_simulation_dir(state.simulation_id)
        state_file = os.path.join(sim_dir, "state.json")
        
        state.updated_at = datetime.now().isoformat()
        
        with open(state_file, 'w', encoding='utf-8') as f:
            json.dump(state.to_dict(), f, ensure_ascii=False, indent=2)
        
        self._simulations[state.simulation_id] = state
    
    def _load_simulation_state(self, simulation_id: str) -> Optional[SimulationState]:
        """Carica stato simulazione da file"""
        if simulation_id in self._simulations:
            return self._simulations[simulation_id]
        
        sim_dir = self._get_simulation_dir(simulation_id)
        state_file = os.path.join(sim_dir, "state.json")
        
        if not os.path.exists(state_file):
            return None
        
        with open(state_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        state = SimulationState(
            simulation_id=simulation_id,
            project_id=data.get("project_id", ""),
            graph_id=data.get("graph_id", ""),
            enable_twitter=data.get("enable_twitter", True),
            enable_reddit=data.get("enable_reddit", True),
            status=SimulationStatus(data.get("status", "created")),
            entities_count=data.get("entities_count", 0),
            profiles_count=data.get("profiles_count", 0),
            entity_types=data.get("entity_types", []),
            config_generated=data.get("config_generated", False),
            config_reasoning=data.get("config_reasoning", ""),
            current_round=data.get("current_round", 0),
            twitter_status=data.get("twitter_status", "not_started"),
            reddit_status=data.get("reddit_status", "not_started"),
            created_at=data.get("created_at", datetime.now().isoformat()),
            updated_at=data.get("updated_at", datetime.now().isoformat()),
            error=data.get("error"),
        )
        
        self._simulations[simulation_id] = state
        return state
    
    def create_simulation(
        self,
        project_id: str,
        graph_id: str,
        enable_twitter: bool = True,
        enable_reddit: bool = True,
    ) -> SimulationState:
        """
        Crea una nuova simulazione

        Args:
            project_id: ID progetto
            graph_id: ID grafo Zep
            enable_twitter: Abilitare simulazione Twitter
            enable_reddit: Abilitare simulazione Reddit

        Returns:
            SimulationState
        """
        import uuid
        simulation_id = f"sim_{uuid.uuid4().hex[:12]}"
        
        state = SimulationState(
            simulation_id=simulation_id,
            project_id=project_id,
            graph_id=graph_id,
            enable_twitter=enable_twitter,
            enable_reddit=enable_reddit,
            status=SimulationStatus.CREATED,
        )
        
        self._save_simulation_state(state)
        logger.info(f"Simulazione creata: {simulation_id}, project={project_id}, graph={graph_id}")
        
        return state
    
    def prepare_simulation(
        self,
        simulation_id: str,
        simulation_requirement: str,
        document_text: str,
        defined_entity_types: Optional[List[str]] = None,
        use_llm_for_profiles: bool = True,
        progress_callback: Optional[callable] = None,
        parallel_profile_count: int = 3,
        nuts2_region: Optional[str] = None
    ) -> SimulationState:
        """
        Prepara l'ambiente di simulazione (completamente automatizzato)

        Passaggi:
        1. Leggere e filtrare entita' dal grafo Zep
        2. Generare OASIS Agent Profile per ogni entita' (miglioramento LLM opzionale, supporto parallelo)
        3. Generare intelligentemente parametri di configurazione simulazione tramite LLM (tempo, attivita', frequenza messaggi, ecc.)
        4. Salvare file di configurazione e file Profile
        5. Copiare script preimpostati nella directory simulazione

        Args:
            simulation_id: ID simulazione
            simulation_requirement: Descrizione requisiti simulazione (per generazione configurazione LLM)
            document_text: Contenuto documento originale (per comprensione contesto LLM)
            defined_entity_types: Tipi di entita' predefiniti (opzionale)
            use_llm_for_profiles: Utilizzare LLM per generare profili dettagliati
            progress_callback: Funzione callback progresso (stage, progress, message)
            parallel_profile_count: Numero di profili da generare in parallelo, default 3

        Returns:
            SimulationState
        """
        state = self._load_simulation_state(simulation_id)
        if not state:
            raise ValueError(f"Simulazione non esistente: {simulation_id}")

        try:
            state.status = SimulationStatus.PREPARING
            self._save_simulation_state(state)

            sim_dir = self._get_simulation_dir(simulation_id)

            # ========== Fase 1: Lettura e filtraggio entita' ==========
            if progress_callback:
                progress_callback("reading", 0, "Connessione al grafo Zep...")
            
            reader = ZepEntityReader()
            
            if progress_callback:
                progress_callback("reading", 30, "Lettura dati nodi...")
            
            filtered = reader.filter_defined_entities(
                graph_id=state.graph_id,
                defined_entity_types=defined_entity_types,
                enrich_with_edges=True
            )
            
            state.entities_count = filtered.filtered_count
            state.entity_types = list(filtered.entity_types)
            
            if progress_callback:
                progress_callback(
                    "reading", 100,
                    f"Completato, {filtered.filtered_count} entita' in totale",
                    current=filtered.filtered_count,
                    total=filtered.filtered_count
                )
            
            if filtered.filtered_count == 0:
                state.status = SimulationStatus.FAILED
                state.error = "Nessuna entita' trovata che soddisfi i criteri, verificare che il grafo sia costruito correttamente"
                self._save_simulation_state(state)
                return state
            
            # ========== Fase 2: Generazione Agent Profile ==========
            total_entities = len(filtered.entities)
            
            if progress_callback:
                progress_callback(
                    "generating_profiles", 0,
                    "Inizio generazione...",
                    current=0,
                    total=total_entities
                )
            
            # Crea generatore profili con calibrazione ICF
            generator = OasisProfileGenerator(graph_id=state.graph_id, nuts2_region=nuts2_region)
            
            def profile_progress(current, total, msg):
                if progress_callback:
                    progress_callback(
                        "generating_profiles", 
                        int(current / total * 100), 
                        msg,
                        current=current,
                        total=total,
                        item_name=msg
                    )
            
            # Impostare percorso file per salvataggio in tempo reale (priorita' formato JSON Reddit)
            realtime_output_path = None
            realtime_platform = "reddit"
            if state.enable_reddit:
                realtime_output_path = os.path.join(sim_dir, "reddit_profiles.json")
                realtime_platform = "reddit"
            elif state.enable_twitter:
                realtime_output_path = os.path.join(sim_dir, "twitter_profiles.csv")
                realtime_platform = "twitter"
            
            profiles = generator.generate_profiles_from_entities(
                entities=filtered.entities,
                use_llm=use_llm_for_profiles,
                progress_callback=profile_progress,
                graph_id=state.graph_id,  # Passare graph_id per ricerca Zep
                parallel_count=parallel_profile_count,  # Numero generazione parallela
                realtime_output_path=realtime_output_path,  # Percorso salvataggio in tempo reale
                output_platform=realtime_platform  # Formato output
            )
            
            state.profiles_count = len(profiles)
            
            # Salva file Profile (nota: Twitter usa formato CSV, Reddit usa formato JSON)
            # Reddit e' gia' stato salvato in tempo reale durante la generazione, qui si salva di nuovo per garantire completezza
            if progress_callback:
                progress_callback(
                    "generating_profiles", 95,
                    "Salvataggio file Profile...",
                    current=total_entities,
                    total=total_entities
                )
            
            if state.enable_reddit:
                generator.save_profiles(
                    profiles=profiles,
                    file_path=os.path.join(sim_dir, "reddit_profiles.json"),
                    platform="reddit"
                )
            
            if state.enable_twitter:
                # Twitter usa formato CSV! Questo e' un requisito di OASIS
                generator.save_profiles(
                    profiles=profiles,
                    file_path=os.path.join(sim_dir, "twitter_profiles.csv"),
                    platform="twitter"
                )
            
            if progress_callback:
                progress_callback(
                    "generating_profiles", 100,
                    f"Completato, {len(profiles)} Profile in totale",
                    current=len(profiles),
                    total=len(profiles)
                )
            
            # ========== Fase 3: Generazione intelligente configurazione simulazione tramite LLM ==========
            if progress_callback:
                progress_callback(
                    "generating_config", 0,
                    "Analisi requisiti simulazione...",
                    current=0,
                    total=3
                )
            
            config_generator = SimulationConfigGenerator()
            
            if progress_callback:
                progress_callback(
                    "generating_config", 30,
                    "Invocazione LLM per generazione configurazione...",
                    current=1,
                    total=3
                )
            
            sim_params = config_generator.generate_config(
                simulation_id=simulation_id,
                project_id=state.project_id,
                graph_id=state.graph_id,
                simulation_requirement=simulation_requirement,
                document_text=document_text,
                entities=filtered.entities,
                enable_twitter=state.enable_twitter,
                enable_reddit=state.enable_reddit
            )
            
            if progress_callback:
                progress_callback(
                    "generating_config", 70,
                    "Salvataggio file di configurazione...",
                    current=2,
                    total=3
                )
            
            # Salva file di configurazione
            config_path = os.path.join(sim_dir, "simulation_config.json")
            with open(config_path, 'w', encoding='utf-8') as f:
                f.write(sim_params.to_json())
            
            state.config_generated = True
            state.config_reasoning = sim_params.generation_reasoning
            
            if progress_callback:
                progress_callback(
                    "generating_config", 100,
                    "Generazione configurazione completata",
                    current=3,
                    total=3
                )
            
            # Nota: gli script di esecuzione rimangono nella directory backend/scripts/, non vengono piu' copiati nella directory simulazione
            # All'avvio della simulazione, simulation_runner eseguira' gli script dalla directory scripts/

            # Aggiorna stato
            state.status = SimulationStatus.READY
            self._save_simulation_state(state)
            
            logger.info(f"Preparazione simulazione completata: {simulation_id}, "
                       f"entities={state.entities_count}, profiles={state.profiles_count}")
            
            return state
            
        except Exception as e:
            logger.error(f"Preparazione simulazione fallita: {simulation_id}, error={str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            state.status = SimulationStatus.FAILED
            state.error = str(e)
            self._save_simulation_state(state)
            raise
    
    def get_simulation(self, simulation_id: str) -> Optional[SimulationState]:
        """Ottieni stato simulazione"""
        return self._load_simulation_state(simulation_id)
    
    def list_simulations(self, project_id: Optional[str] = None) -> List[SimulationState]:
        """Elenca tutte le simulazioni"""
        simulations = []
        
        if os.path.exists(self.SIMULATION_DATA_DIR):
            for sim_id in os.listdir(self.SIMULATION_DATA_DIR):
                # Salta file nascosti (es. .DS_Store) e file non-directory
                sim_path = os.path.join(self.SIMULATION_DATA_DIR, sim_id)
                if sim_id.startswith('.') or not os.path.isdir(sim_path):
                    continue
                
                state = self._load_simulation_state(sim_id)
                if state:
                    if project_id is None or state.project_id == project_id:
                        simulations.append(state)
        
        return simulations
    
    def get_profiles(self, simulation_id: str, platform: str = "reddit") -> List[Dict[str, Any]]:
        """Ottieni Agent Profile della simulazione"""
        state = self._load_simulation_state(simulation_id)
        if not state:
            raise ValueError(f"Simulazione non esistente: {simulation_id}")

        sim_dir = self._get_simulation_dir(simulation_id)
        profile_path = os.path.join(sim_dir, f"{platform}_profiles.json")
        
        if not os.path.exists(profile_path):
            return []
        
        with open(profile_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def get_simulation_config(self, simulation_id: str) -> Optional[Dict[str, Any]]:
        """Ottieni configurazione simulazione"""
        sim_dir = self._get_simulation_dir(simulation_id)
        config_path = os.path.join(sim_dir, "simulation_config.json")
        
        if not os.path.exists(config_path):
            return None
        
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def get_run_instructions(self, simulation_id: str) -> Dict[str, str]:
        """Ottieni istruzioni di esecuzione"""
        sim_dir = self._get_simulation_dir(simulation_id)
        config_path = os.path.join(sim_dir, "simulation_config.json")
        scripts_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../scripts'))
        
        return {
            "simulation_dir": sim_dir,
            "scripts_dir": scripts_dir,
            "config_file": config_path,
            "commands": {
                "twitter": f"python {scripts_dir}/run_twitter_simulation.py --config {config_path}",
                "reddit": f"python {scripts_dir}/run_reddit_simulation.py --config {config_path}",
                "parallel": f"python {scripts_dir}/run_parallel_simulation.py --config {config_path}",
            },
            "instructions": (
                f"1. Attivare ambiente conda: conda activate MiroFish\n"
                f"2. Eseguire simulazione (script in {scripts_dir}):\n"
                f"   - Eseguire solo Twitter: python {scripts_dir}/run_twitter_simulation.py --config {config_path}\n"
                f"   - Eseguire solo Reddit: python {scripts_dir}/run_reddit_simulation.py --config {config_path}\n"
                f"   - Eseguire doppia piattaforma in parallelo: python {scripts_dir}/run_parallel_simulation.py --config {config_path}"
            )
        }
