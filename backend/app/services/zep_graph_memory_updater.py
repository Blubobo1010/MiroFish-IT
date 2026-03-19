"""
Servizio di aggiornamento memoria del grafo Zep
Aggiorna dinamicamente le attività degli Agent della simulazione nel grafo Zep
"""

import os
import time
import threading
import json
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass
from datetime import datetime
from queue import Queue, Empty

from zep_cloud.client import Zep

from ..config import Config
from ..utils.logger import get_logger

logger = get_logger('mirofish.zep_graph_memory_updater')


@dataclass
class AgentActivity:
    """Record di attività dell'Agent"""
    platform: str           # twitter / reddit
    agent_id: int
    agent_name: str
    action_type: str        # CREATE_POST, LIKE_POST, etc.
    action_args: Dict[str, Any]
    round_num: int
    timestamp: str
    
    def to_episode_text(self) -> str:
        """
        Converte l'attività in una descrizione testuale inviabile a Zep

        Utilizza un formato in linguaggio naturale per consentire a Zep di estrarre entità e relazioni
        Non aggiunge prefissi relativi alla simulazione per evitare aggiornamenti fuorvianti del grafo
        """
        # Genera descrizioni diverse in base ai diversi tipi di azione
        action_descriptions = {
            "CREATE_POST": self._describe_create_post,
            "LIKE_POST": self._describe_like_post,
            "DISLIKE_POST": self._describe_dislike_post,
            "REPOST": self._describe_repost,
            "QUOTE_POST": self._describe_quote_post,
            "FOLLOW": self._describe_follow,
            "CREATE_COMMENT": self._describe_create_comment,
            "LIKE_COMMENT": self._describe_like_comment,
            "DISLIKE_COMMENT": self._describe_dislike_comment,
            "SEARCH_POSTS": self._describe_search,
            "SEARCH_USER": self._describe_search_user,
            "MUTE": self._describe_mute,
        }
        
        describe_func = action_descriptions.get(self.action_type, self._describe_generic)
        description = describe_func()
        
        # Restituisce direttamente il formato "nome agent: descrizione attività" senza prefisso di simulazione
        return f"{self.agent_name}: {description}"
    
    def _describe_create_post(self) -> str:
        content = self.action_args.get("content", "")
        if content:
            return f"ha pubblicato un post: \"{content}\""
        return "ha pubblicato un post"
    
    def _describe_like_post(self) -> str:
        """Like al post - include testo originale e informazioni sull'autore"""
        post_content = self.action_args.get("post_content", "")
        post_author = self.action_args.get("post_author_name", "")

        if post_content and post_author:
            return f"ha messo like al post di {post_author}: \"{post_content}\""
        elif post_content:
            return f"ha messo like a un post: \"{post_content}\""
        elif post_author:
            return f"ha messo like a un post di {post_author}"
        return "ha messo like a un post"
    
    def _describe_dislike_post(self) -> str:
        """Dislike al post - include testo originale e informazioni sull'autore"""
        post_content = self.action_args.get("post_content", "")
        post_author = self.action_args.get("post_author_name", "")

        if post_content and post_author:
            return f"ha messo dislike al post di {post_author}: \"{post_content}\""
        elif post_content:
            return f"ha messo dislike a un post: \"{post_content}\""
        elif post_author:
            return f"ha messo dislike a un post di {post_author}"
        return "ha messo dislike a un post"
    
    def _describe_repost(self) -> str:
        """Condivisione post - include contenuto originale e informazioni sull'autore"""
        original_content = self.action_args.get("original_content", "")
        original_author = self.action_args.get("original_author_name", "")

        if original_content and original_author:
            return f"ha condiviso il post di {original_author}: \"{original_content}\""
        elif original_content:
            return f"ha condiviso un post: \"{original_content}\""
        elif original_author:
            return f"ha condiviso un post di {original_author}"
        return "ha condiviso un post"
    
    def _describe_quote_post(self) -> str:
        """Citazione post - include contenuto originale, informazioni sull'autore e commento di citazione"""
        original_content = self.action_args.get("original_content", "")
        original_author = self.action_args.get("original_author_name", "")
        quote_content = self.action_args.get("quote_content", "") or self.action_args.get("content", "")

        base = ""
        if original_content and original_author:
            base = f"ha citato il post di {original_author} \"{original_content}\""
        elif original_content:
            base = f"ha citato un post \"{original_content}\""
        elif original_author:
            base = f"ha citato un post di {original_author}"
        else:
            base = "ha citato un post"

        if quote_content:
            base += f", commentando: \"{quote_content}\""
        return base
    
    def _describe_follow(self) -> str:
        """Segui utente - include il nome dell'utente seguito"""
        target_user_name = self.action_args.get("target_user_name", "")

        if target_user_name:
            return f"ha iniziato a seguire l'utente \"{target_user_name}\""
        return "ha iniziato a seguire un utente"
    
    def _describe_create_comment(self) -> str:
        """Pubblica commento - include contenuto del commento e informazioni sul post commentato"""
        content = self.action_args.get("content", "")
        post_content = self.action_args.get("post_content", "")
        post_author = self.action_args.get("post_author_name", "")

        if content:
            if post_content and post_author:
                return f"ha commentato il post di {post_author} \"{post_content}\": \"{content}\""
            elif post_content:
                return f"ha commentato il post \"{post_content}\": \"{content}\""
            elif post_author:
                return f"ha commentato un post di {post_author}: \"{content}\""
            return f"ha commentato: \"{content}\""
        return "ha pubblicato un commento"
    
    def _describe_like_comment(self) -> str:
        """Like al commento - include contenuto del commento e informazioni sull'autore"""
        comment_content = self.action_args.get("comment_content", "")
        comment_author = self.action_args.get("comment_author_name", "")

        if comment_content and comment_author:
            return f"ha messo like al commento di {comment_author}: \"{comment_content}\""
        elif comment_content:
            return f"ha messo like a un commento: \"{comment_content}\""
        elif comment_author:
            return f"ha messo like a un commento di {comment_author}"
        return "ha messo like a un commento"
    
    def _describe_dislike_comment(self) -> str:
        """Dislike al commento - include contenuto del commento e informazioni sull'autore"""
        comment_content = self.action_args.get("comment_content", "")
        comment_author = self.action_args.get("comment_author_name", "")

        if comment_content and comment_author:
            return f"ha messo dislike al commento di {comment_author}: \"{comment_content}\""
        elif comment_content:
            return f"ha messo dislike a un commento: \"{comment_content}\""
        elif comment_author:
            return f"ha messo dislike a un commento di {comment_author}"
        return "ha messo dislike a un commento"
    
    def _describe_search(self) -> str:
        """Ricerca post - include le parole chiave di ricerca"""
        query = self.action_args.get("query", "") or self.action_args.get("keyword", "")
        return f"ha cercato \"{query}\"" if query else "ha effettuato una ricerca"
    
    def _describe_search_user(self) -> str:
        """Ricerca utente - include le parole chiave di ricerca"""
        query = self.action_args.get("query", "") or self.action_args.get("username", "")
        return f"ha cercato l'utente \"{query}\"" if query else "ha cercato un utente"
    
    def _describe_mute(self) -> str:
        """Silenzia utente - include il nome dell'utente silenziato"""
        target_user_name = self.action_args.get("target_user_name", "")

        if target_user_name:
            return f"ha silenziato l'utente \"{target_user_name}\""
        return "ha silenziato un utente"
    
    def _describe_generic(self) -> str:
        # Per tipi di azione sconosciuti, genera una descrizione generica
        return f"ha eseguito l'operazione {self.action_type}"


class ZepGraphMemoryUpdater:
    """
    Aggiornatore della memoria del grafo Zep

    Monitora i file di log delle azioni della simulazione e aggiorna in tempo reale le attività degli agent nel grafo Zep.
    Raggruppa per piattaforma, inviando in batch a Zep ogni BATCH_SIZE attività accumulate.

    Tutti i comportamenti significativi vengono aggiornati in Zep, action_args contiene informazioni di contesto complete:
    - Testo originale dei post con like/dislike
    - Testo originale dei post condivisi/citati
    - Nome utente seguito/silenziato
    - Testo originale dei commenti con like/dislike
    """

    # Dimensione del batch (quante attività accumulare per piattaforma prima dell'invio)
    BATCH_SIZE = 5
    
    # Mappatura nomi piattaforma (per la visualizzazione in console)
    PLATFORM_DISPLAY_NAMES = {
        'twitter': 'Mondo1',
        'reddit': 'Mondo2',
    }

    # Intervallo di invio (secondi), per evitare richieste troppo rapide
    SEND_INTERVAL = 0.5
    
    # Configurazione retry
    MAX_RETRIES = 3
    RETRY_DELAY = 2  # secondi
    
    def __init__(self, graph_id: str, api_key: Optional[str] = None):
        """
        Inizializza l'aggiornatore

        Args:
            graph_id: ID del grafo Zep
            api_key: Zep API Key (opzionale, predefinito dalla configurazione)
        """
        self.graph_id = graph_id
        self.api_key = api_key or Config.ZEP_API_KEY
        
        if not self.api_key:
            raise ValueError("ZEP_API_KEY non configurata")
        
        self.client = Zep(api_key=self.api_key)
        
        # Coda delle attività
        self._activity_queue: Queue = Queue()
        
        # Buffer delle attività raggruppate per piattaforma (ogni piattaforma accumula fino a BATCH_SIZE e poi invia in batch)
        self._platform_buffers: Dict[str, List[AgentActivity]] = {
            'twitter': [],
            'reddit': [],
        }
        self._buffer_lock = threading.Lock()
        
        # Flag di controllo
        self._running = False
        self._worker_thread: Optional[threading.Thread] = None
        
        # Statistiche
        self._total_activities = 0  # Numero di attività effettivamente aggiunte alla coda
        self._total_sent = 0        # Numero di batch inviati con successo a Zep
        self._total_items_sent = 0  # Numero di attività inviate con successo a Zep
        self._failed_count = 0      # Numero di batch con invio fallito
        self._skipped_count = 0     # Numero di attività filtrate e saltate (DO_NOTHING)
        
        logger.info(f"ZepGraphMemoryUpdater inizializzazione completata: graph_id={graph_id}, batch_size={self.BATCH_SIZE}")
    
    def _get_platform_display_name(self, platform: str) -> str:
        """Ottiene il nome visualizzato della piattaforma"""
        return self.PLATFORM_DISPLAY_NAMES.get(platform.lower(), platform)
    
    def start(self):
        """Avvia il thread di lavoro in background"""
        if self._running:
            return
        
        self._running = True
        self._worker_thread = threading.Thread(
            target=self._worker_loop,
            daemon=True,
            name=f"ZepMemoryUpdater-{self.graph_id[:8]}"
        )
        self._worker_thread.start()
        logger.info(f"ZepGraphMemoryUpdater avviato: graph_id={self.graph_id}")
    
    def stop(self):
        """Arresta il thread di lavoro in background"""
        self._running = False
        
        # Invia le attività rimanenti
        self._flush_remaining()

        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=10)

        logger.info(f"ZepGraphMemoryUpdater arrestato: graph_id={self.graph_id}, "
                   f"total_activities={self._total_activities}, "
                   f"batches_sent={self._total_sent}, "
                   f"items_sent={self._total_items_sent}, "
                   f"failed={self._failed_count}, "
                   f"skipped={self._skipped_count}")
    
    def add_activity(self, activity: AgentActivity):
        """
        Aggiunge un'attività dell'agent alla coda

        Tutti i comportamenti significativi vengono aggiunti alla coda, tra cui:
        - CREATE_POST (pubblicazione post)
        - CREATE_COMMENT (commento)
        - QUOTE_POST (citazione post)
        - SEARCH_POSTS (ricerca post)
        - SEARCH_USER (ricerca utente)
        - LIKE_POST/DISLIKE_POST (like/dislike post)
        - REPOST (condivisione)
        - FOLLOW (segui)
        - MUTE (silenzia)
        - LIKE_COMMENT/DISLIKE_COMMENT (like/dislike commento)

        action_args contiene informazioni di contesto complete (testo originale del post, nome utente, ecc.).

        Args:
            activity: record di attività dell'Agent
        """
        # Salta le attività di tipo DO_NOTHING
        if activity.action_type == "DO_NOTHING":
            self._skipped_count += 1
            return
        
        self._activity_queue.put(activity)
        self._total_activities += 1
        logger.debug(f"Attività aggiunta alla coda Zep: {activity.agent_name} - {activity.action_type}")
    
    def add_activity_from_dict(self, data: Dict[str, Any], platform: str):
        """
        Aggiunge un'attività dai dati del dizionario

        Args:
            data: dati del dizionario analizzati da actions.jsonl
            platform: nome della piattaforma (twitter/reddit)
        """
        # Salta le voci di tipo evento
        if "event_type" in data:
            return
        
        activity = AgentActivity(
            platform=platform,
            agent_id=data.get("agent_id", 0),
            agent_name=data.get("agent_name", ""),
            action_type=data.get("action_type", ""),
            action_args=data.get("action_args", {}),
            round_num=data.get("round", 0),
            timestamp=data.get("timestamp", datetime.now().isoformat()),
        )
        
        self.add_activity(activity)
    
    def _worker_loop(self):
        """Ciclo di lavoro in background - invio batch di attività a Zep per piattaforma"""
        while self._running or not self._activity_queue.empty():
            try:
                # Tenta di ottenere un'attività dalla coda (timeout 1 secondo)
                try:
                    activity = self._activity_queue.get(timeout=1)
                    
                    # Aggiungi l'attività al buffer della piattaforma corrispondente
                    platform = activity.platform.lower()
                    with self._buffer_lock:
                        if platform not in self._platform_buffers:
                            self._platform_buffers[platform] = []
                        self._platform_buffers[platform].append(activity)
                        
                        # Verifica se la piattaforma ha raggiunto la dimensione del batch
                        if len(self._platform_buffers[platform]) >= self.BATCH_SIZE:
                            batch = self._platform_buffers[platform][:self.BATCH_SIZE]
                            self._platform_buffers[platform] = self._platform_buffers[platform][self.BATCH_SIZE:]
                            # Invia dopo aver rilasciato il lock
                            self._send_batch_activities(batch, platform)
                            # Intervallo tra invii per evitare richieste troppo rapide
                            time.sleep(self.SEND_INTERVAL)
                    
                except Empty:
                    pass
                    
            except Exception as e:
                logger.error(f"Eccezione nel ciclo di lavoro: {e}")
                time.sleep(1)
    
    def _send_batch_activities(self, activities: List[AgentActivity], platform: str):
        """
        Invio batch di attività al grafo Zep (unite in un unico testo)

        Args:
            activities: lista delle attività Agent
            platform: nome della piattaforma
        """
        if not activities:
            return
        
        # Unisci più attività in un unico testo, separato da a-capo
        episode_texts = [activity.to_episode_text() for activity in activities]
        combined_text = "\n".join(episode_texts)
        
        # Invio con retry
        for attempt in range(self.MAX_RETRIES):
            try:
                self.client.graph.add(
                    graph_id=self.graph_id,
                    type="text",
                    data=combined_text
                )
                
                self._total_sent += 1
                self._total_items_sent += len(activities)
                display_name = self._get_platform_display_name(platform)
                logger.info(f"Invio batch di {len(activities)} attività {display_name} al grafo {self.graph_id} riuscito")
                logger.debug(f"Anteprima contenuto batch: {combined_text[:200]}...")
                return
                
            except Exception as e:
                if attempt < self.MAX_RETRIES - 1:
                    logger.warning(f"Invio batch a Zep fallito (tentativo {attempt + 1}/{self.MAX_RETRIES}): {e}")
                    time.sleep(self.RETRY_DELAY * (attempt + 1))
                else:
                    logger.error(f"Invio batch a Zep fallito dopo {self.MAX_RETRIES} tentativi: {e}")
                    self._failed_count += 1
    
    def _flush_remaining(self):
        """Invia le attività rimanenti nella coda e nel buffer"""
        # Prima elabora le attività rimanenti nella coda e aggiungile al buffer
        while not self._activity_queue.empty():
            try:
                activity = self._activity_queue.get_nowait()
                platform = activity.platform.lower()
                with self._buffer_lock:
                    if platform not in self._platform_buffers:
                        self._platform_buffers[platform] = []
                    self._platform_buffers[platform].append(activity)
            except Empty:
                break
        
        # Poi invia le attività rimanenti nei buffer di ogni piattaforma (anche se inferiori a BATCH_SIZE)
        with self._buffer_lock:
            for platform, buffer in self._platform_buffers.items():
                if buffer:
                    display_name = self._get_platform_display_name(platform)
                    logger.info(f"Invio delle {len(buffer)} attività rimanenti della piattaforma {display_name}")
                    self._send_batch_activities(buffer, platform)
            # Svuota tutti i buffer
            for platform in self._platform_buffers:
                self._platform_buffers[platform] = []
    
    def get_stats(self) -> Dict[str, Any]:
        """Ottiene le informazioni statistiche"""
        with self._buffer_lock:
            buffer_sizes = {p: len(b) for p, b in self._platform_buffers.items()}
        
        return {
            "graph_id": self.graph_id,
            "batch_size": self.BATCH_SIZE,
            "total_activities": self._total_activities,  # Totale attività aggiunte alla coda
            "batches_sent": self._total_sent,            # Numero di batch inviati con successo
            "items_sent": self._total_items_sent,        # Numero di attività inviate con successo
            "failed_count": self._failed_count,          # Numero di batch con invio fallito
            "skipped_count": self._skipped_count,        # Numero di attività filtrate e saltate (DO_NOTHING)
            "queue_size": self._activity_queue.qsize(),
            "buffer_sizes": buffer_sizes,                # Dimensione buffer per piattaforma
            "running": self._running,
        }


class ZepGraphMemoryManager:
    """
    Gestore degli aggiornatori di memoria del grafo Zep per simulazioni multiple

    Ogni simulazione può avere la propria istanza di aggiornatore
    """
    
    _updaters: Dict[str, ZepGraphMemoryUpdater] = {}
    _lock = threading.Lock()
    
    @classmethod
    def create_updater(cls, simulation_id: str, graph_id: str) -> ZepGraphMemoryUpdater:
        """
        Crea un aggiornatore di memoria del grafo per una simulazione

        Args:
            simulation_id: ID della simulazione
            graph_id: ID del grafo Zep

        Returns:
            Istanza di ZepGraphMemoryUpdater
        """
        with cls._lock:
            # Se esiste già, arresta prima quello vecchio
            if simulation_id in cls._updaters:
                cls._updaters[simulation_id].stop()
            
            updater = ZepGraphMemoryUpdater(graph_id)
            updater.start()
            cls._updaters[simulation_id] = updater
            
            logger.info(f"Aggiornatore memoria grafo creato: simulation_id={simulation_id}, graph_id={graph_id}")
            return updater
    
    @classmethod
    def get_updater(cls, simulation_id: str) -> Optional[ZepGraphMemoryUpdater]:
        """Ottiene l'aggiornatore della simulazione"""
        return cls._updaters.get(simulation_id)
    
    @classmethod
    def stop_updater(cls, simulation_id: str):
        """Arresta e rimuove l'aggiornatore della simulazione"""
        with cls._lock:
            if simulation_id in cls._updaters:
                cls._updaters[simulation_id].stop()
                del cls._updaters[simulation_id]
                logger.info(f"Aggiornatore memoria grafo arrestato: simulation_id={simulation_id}")
    
    # Flag per prevenire chiamate ripetute a stop_all
    _stop_all_done = False
    
    @classmethod
    def stop_all(cls):
        """Arresta tutti gli aggiornatori"""
        # Previeni chiamate ripetute
        if cls._stop_all_done:
            return
        cls._stop_all_done = True
        
        with cls._lock:
            if cls._updaters:
                for simulation_id, updater in list(cls._updaters.items()):
                    try:
                        updater.stop()
                    except Exception as e:
                        logger.error(f"Arresto aggiornatore fallito: simulation_id={simulation_id}, error={e}")
                cls._updaters.clear()
            logger.info("Tutti gli aggiornatori di memoria del grafo sono stati arrestati")
    
    @classmethod
    def get_all_stats(cls) -> Dict[str, Dict[str, Any]]:
        """Ottiene le informazioni statistiche di tutti gli aggiornatori"""
        return {
            sim_id: updater.get_stats() 
            for sim_id, updater in cls._updaters.items()
        }
