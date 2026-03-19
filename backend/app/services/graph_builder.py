"""
Servizio di costruzione del grafo
Interfaccia 2: Utilizza l'API Zep per costruire un Standalone Graph
"""

import os
import uuid
import time
import threading
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass

from zep_cloud.client import Zep
from zep_cloud import EpisodeData, EntityEdgeSourceTarget

from ..config import Config
from ..models.task import TaskManager, TaskStatus
from ..utils.zep_paging import fetch_all_nodes, fetch_all_edges
from .text_processor import TextProcessor


@dataclass
class GraphInfo:
    """Informazioni sul grafo"""
    graph_id: str
    node_count: int
    edge_count: int
    entity_types: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "graph_id": self.graph_id,
            "node_count": self.node_count,
            "edge_count": self.edge_count,
            "entity_types": self.entity_types,
        }


class GraphBuilderService:
    """
    Servizio di costruzione del grafo
    Responsabile della chiamata all'API Zep per costruire il grafo della conoscenza
    """

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or Config.ZEP_API_KEY
        if not self.api_key:
            raise ValueError("ZEP_API_KEY non configurata")

        self.client = Zep(api_key=self.api_key)
        self.task_manager = TaskManager()

    def build_graph_async(
        self,
        text: str,
        ontology: Dict[str, Any],
        graph_name: str = "MiroFish Graph",
        chunk_size: int = 500,
        chunk_overlap: int = 50,
        batch_size: int = 3
    ) -> str:
        """
        Costruzione asincrona del grafo

        Args:
            text: Testo di input
            ontology: Definizione dell'ontologia (output dell'interfaccia 1)
            graph_name: Nome del grafo
            chunk_size: Dimensione del blocco di testo
            chunk_overlap: Dimensione della sovrapposizione tra blocchi
            batch_size: Numero di blocchi per ogni lotto

        Returns:
            ID del task
        """
        # Crea il task
        task_id = self.task_manager.create_task(
            task_type="graph_build",
            metadata={
                "graph_name": graph_name,
                "chunk_size": chunk_size,
                "text_length": len(text),
            }
        )

        # Esegue la costruzione in un thread in background
        thread = threading.Thread(
            target=self._build_graph_worker,
            args=(task_id, text, ontology, graph_name, chunk_size, chunk_overlap, batch_size)
        )
        thread.daemon = True
        thread.start()

        return task_id

    def _build_graph_worker(
        self,
        task_id: str,
        text: str,
        ontology: Dict[str, Any],
        graph_name: str,
        chunk_size: int,
        chunk_overlap: int,
        batch_size: int
    ):
        """Thread di lavoro per la costruzione del grafo"""
        try:
            self.task_manager.update_task(
                task_id,
                status=TaskStatus.PROCESSING,
                progress=5,
                message="Inizio costruzione del grafo..."
            )

            # 1. Crea il grafo
            graph_id = self.create_graph(graph_name)
            self.task_manager.update_task(
                task_id,
                progress=10,
                message=f"Grafo creato: {graph_id}"
            )

            # 2. Imposta l'ontologia
            self.set_ontology(graph_id, ontology)
            self.task_manager.update_task(
                task_id,
                progress=15,
                message="Ontologia impostata"
            )

            # 3. Suddivisione del testo in blocchi
            chunks = TextProcessor.split_text(text, chunk_size, chunk_overlap)
            total_chunks = len(chunks)
            self.task_manager.update_task(
                task_id,
                progress=20,
                message=f"Testo suddiviso in {total_chunks} blocchi"
            )

            # 4. Invio dati a lotti
            episode_uuids = self.add_text_batches(
                graph_id, chunks, batch_size,
                lambda msg, prog: self.task_manager.update_task(
                    task_id,
                    progress=20 + int(prog * 0.4),  # 20-60%
                    message=msg
                )
            )

            # 5. Attesa del completamento dell'elaborazione Zep
            self.task_manager.update_task(
                task_id,
                progress=60,
                message="In attesa dell'elaborazione dati da parte di Zep..."
            )

            self._wait_for_episodes(
                episode_uuids,
                lambda msg, prog: self.task_manager.update_task(
                    task_id,
                    progress=60 + int(prog * 0.3),  # 60-90%
                    message=msg
                )
            )

            # 6. Recupero informazioni sul grafo
            self.task_manager.update_task(
                task_id,
                progress=90,
                message="Recupero informazioni sul grafo..."
            )

            graph_info = self._get_graph_info(graph_id)

            # Completato
            self.task_manager.complete_task(task_id, {
                "graph_id": graph_id,
                "graph_info": graph_info.to_dict(),
                "chunks_processed": total_chunks,
            })

        except Exception as e:
            import traceback
            error_msg = f"{str(e)}\n{traceback.format_exc()}"
            self.task_manager.fail_task(task_id, error_msg)

    def create_graph(self, name: str) -> str:
        """Crea un grafo Zep (metodo pubblico)"""
        graph_id = f"mirofish_{uuid.uuid4().hex[:16]}"

        self.client.graph.create(
            graph_id=graph_id,
            name=name,
            description="MiroFish Social Simulation Graph"
        )

        return graph_id

    def set_ontology(self, graph_id: str, ontology: Dict[str, Any]):
        """Imposta l'ontologia del grafo (metodo pubblico)"""
        import warnings
        from typing import Optional
        from pydantic import Field
        from zep_cloud.external_clients.ontology import EntityModel, EntityText, EdgeModel

        # Sopprime gli avvisi di Pydantic v2 relativi a Field(default=None)
        # Questo utilizzo e' richiesto dall'SDK Zep, l'avviso proviene dalla creazione dinamica delle classi e puo' essere ignorato in sicurezza
        warnings.filterwarnings('ignore', category=UserWarning, module='pydantic')

        # Nomi riservati di Zep, non utilizzabili come nomi di attributi
        RESERVED_NAMES = {'uuid', 'name', 'group_id', 'name_embedding', 'summary', 'created_at'}

        def safe_attr_name(attr_name: str) -> str:
            """Converte i nomi riservati in nomi sicuri"""
            if attr_name.lower() in RESERVED_NAMES:
                return f"entity_{attr_name}"
            return attr_name

        # Creazione dinamica dei tipi di entita'
        entity_types = {}
        for entity_def in ontology.get("entity_types", []):
            name = entity_def["name"]
            description = entity_def.get("description", f"A {name} entity.")

            # Crea il dizionario degli attributi e le annotazioni di tipo (necessarie per Pydantic v2)
            attrs = {"__doc__": description}
            annotations = {}

            for attr_def in entity_def.get("attributes", []):
                attr_name = safe_attr_name(attr_def["name"])  # Usa il nome sicuro
                attr_desc = attr_def.get("description", attr_name)
                # L'API Zep richiede la description nel Field, e' obbligatoria
                attrs[attr_name] = Field(description=attr_desc, default=None)
                annotations[attr_name] = Optional[EntityText]  # Annotazione di tipo

            attrs["__annotations__"] = annotations

            # Creazione dinamica della classe
            entity_class = type(name, (EntityModel,), attrs)
            entity_class.__doc__ = description
            entity_types[name] = entity_class

        # Creazione dinamica dei tipi di relazione
        edge_definitions = {}
        for edge_def in ontology.get("edge_types", []):
            name = edge_def["name"]
            description = edge_def.get("description", f"A {name} relationship.")

            # Crea il dizionario degli attributi e le annotazioni di tipo
            attrs = {"__doc__": description}
            annotations = {}

            for attr_def in edge_def.get("attributes", []):
                attr_name = safe_attr_name(attr_def["name"])  # Usa il nome sicuro
                attr_desc = attr_def.get("description", attr_name)
                # L'API Zep richiede la description nel Field, e' obbligatoria
                attrs[attr_name] = Field(description=attr_desc, default=None)
                annotations[attr_name] = Optional[str]  # Gli attributi delle relazioni usano il tipo str

            attrs["__annotations__"] = annotations

            # Creazione dinamica della classe
            class_name = ''.join(word.capitalize() for word in name.split('_'))
            edge_class = type(class_name, (EdgeModel,), attrs)
            edge_class.__doc__ = description

            # Costruzione dei source_targets
            source_targets = []
            for st in edge_def.get("source_targets", []):
                source_targets.append(
                    EntityEdgeSourceTarget(
                        source=st.get("source", "Entity"),
                        target=st.get("target", "Entity")
                    )
                )

            if source_targets:
                edge_definitions[name] = (edge_class, source_targets)

        # Chiamata all'API Zep per impostare l'ontologia
        if entity_types or edge_definitions:
            self.client.graph.set_ontology(
                graph_ids=[graph_id],
                entities=entity_types if entity_types else None,
                edges=edge_definitions if edge_definitions else None,
            )

    def add_text_batches(
        self,
        graph_id: str,
        chunks: List[str],
        batch_size: int = 3,
        progress_callback: Optional[Callable] = None
    ) -> List[str]:
        """Aggiunge testo al grafo a lotti, restituisce la lista degli uuid di tutti gli episode"""
        episode_uuids = []
        total_chunks = len(chunks)

        for i in range(0, total_chunks, batch_size):
            batch_chunks = chunks[i:i + batch_size]
            batch_num = i // batch_size + 1
            total_batches = (total_chunks + batch_size - 1) // batch_size

            if progress_callback:
                progress = (i + len(batch_chunks)) / total_chunks
                progress_callback(
                    f"Invio lotto {batch_num}/{total_batches} ({len(batch_chunks)} blocchi)...",
                    progress
                )

            # Costruzione dei dati episode
            episodes = [
                EpisodeData(data=chunk, type="text")
                for chunk in batch_chunks
            ]

            # Invio a Zep
            try:
                batch_result = self.client.graph.add_batch(
                    graph_id=graph_id,
                    episodes=episodes
                )

                # Raccolta degli uuid degli episode restituiti
                if batch_result and isinstance(batch_result, list):
                    for ep in batch_result:
                        ep_uuid = getattr(ep, 'uuid_', None) or getattr(ep, 'uuid', None)
                        if ep_uuid:
                            episode_uuids.append(ep_uuid)

                # Evita richieste troppo rapide
                time.sleep(1)

            except Exception as e:
                if progress_callback:
                    progress_callback(f"Invio del lotto {batch_num} fallito: {str(e)}", 0)
                raise

        return episode_uuids

    def _wait_for_episodes(
        self,
        episode_uuids: List[str],
        progress_callback: Optional[Callable] = None,
        timeout: int = 600
    ):
        """Attende il completamento dell'elaborazione di tutti gli episode (verificando lo stato processed di ciascuno)"""
        if not episode_uuids:
            if progress_callback:
                progress_callback("Nessuna attesa necessaria (nessun episode)", 1.0)
            return

        start_time = time.time()
        pending_episodes = set(episode_uuids)
        completed_count = 0
        total_episodes = len(episode_uuids)

        if progress_callback:
            progress_callback(f"Inizio attesa elaborazione di {total_episodes} blocchi di testo...", 0)

        while pending_episodes:
            if time.time() - start_time > timeout:
                if progress_callback:
                    progress_callback(
                        f"Timeout per alcuni blocchi di testo, completati {completed_count}/{total_episodes}",
                        completed_count / total_episodes
                    )
                break

            # Verifica lo stato di elaborazione di ogni episode
            for ep_uuid in list(pending_episodes):
                try:
                    episode = self.client.graph.episode.get(uuid_=ep_uuid)
                    is_processed = getattr(episode, 'processed', False)

                    if is_processed:
                        pending_episodes.remove(ep_uuid)
                        completed_count += 1

                except Exception as e:
                    # Ignora gli errori di singole query, continua
                    pass

            elapsed = int(time.time() - start_time)
            if progress_callback:
                progress_callback(
                    f"Elaborazione Zep in corso... {completed_count}/{total_episodes} completati, {len(pending_episodes)} in attesa ({elapsed}s)",
                    completed_count / total_episodes if total_episodes > 0 else 0
                )

            if pending_episodes:
                time.sleep(3)  # Verifica ogni 3 secondi

        if progress_callback:
            progress_callback(f"Elaborazione completata: {completed_count}/{total_episodes}", 1.0)

    def _get_graph_info(self, graph_id: str) -> GraphInfo:
        """Recupera le informazioni sul grafo"""
        # Recupera i nodi (con paginazione)
        nodes = fetch_all_nodes(self.client, graph_id)

        # Recupera le relazioni (con paginazione)
        edges = fetch_all_edges(self.client, graph_id)

        # Conta i tipi di entita'
        entity_types = set()
        for node in nodes:
            if node.labels:
                for label in node.labels:
                    if label not in ["Entity", "Node"]:
                        entity_types.add(label)

        return GraphInfo(
            graph_id=graph_id,
            node_count=len(nodes),
            edge_count=len(edges),
            entity_types=list(entity_types)
        )

    def get_graph_data(self, graph_id: str) -> Dict[str, Any]:
        """
        Recupera i dati completi del grafo (con informazioni dettagliate)

        Args:
            graph_id: ID del grafo

        Returns:
            Dizionario contenente nodi e relazioni, incluse informazioni temporali, attributi e altri dati dettagliati
        """
        nodes = fetch_all_nodes(self.client, graph_id)
        edges = fetch_all_edges(self.client, graph_id)

        # Crea la mappatura dei nodi per ottenere i nomi dei nodi
        node_map = {}
        for node in nodes:
            node_map[node.uuid_] = node.name or ""

        nodes_data = []
        for node in nodes:
            # Recupera la data di creazione
            created_at = getattr(node, 'created_at', None)
            if created_at:
                created_at = str(created_at)

            nodes_data.append({
                "uuid": node.uuid_,
                "name": node.name,
                "labels": node.labels or [],
                "summary": node.summary or "",
                "attributes": node.attributes or {},
                "created_at": created_at,
            })

        edges_data = []
        for edge in edges:
            # Recupera le informazioni temporali
            created_at = getattr(edge, 'created_at', None)
            valid_at = getattr(edge, 'valid_at', None)
            invalid_at = getattr(edge, 'invalid_at', None)
            expired_at = getattr(edge, 'expired_at', None)

            # Recupera gli episodes
            episodes = getattr(edge, 'episodes', None) or getattr(edge, 'episode_ids', None)
            if episodes and not isinstance(episodes, list):
                episodes = [str(episodes)]
            elif episodes:
                episodes = [str(e) for e in episodes]

            # Recupera il fact_type
            fact_type = getattr(edge, 'fact_type', None) or edge.name or ""

            edges_data.append({
                "uuid": edge.uuid_,
                "name": edge.name or "",
                "fact": edge.fact or "",
                "fact_type": fact_type,
                "source_node_uuid": edge.source_node_uuid,
                "target_node_uuid": edge.target_node_uuid,
                "source_node_name": node_map.get(edge.source_node_uuid, ""),
                "target_node_name": node_map.get(edge.target_node_uuid, ""),
                "attributes": edge.attributes or {},
                "created_at": str(created_at) if created_at else None,
                "valid_at": str(valid_at) if valid_at else None,
                "invalid_at": str(invalid_at) if invalid_at else None,
                "expired_at": str(expired_at) if expired_at else None,
                "episodes": episodes or [],
            })

        return {
            "graph_id": graph_id,
            "nodes": nodes_data,
            "edges": edges_data,
            "node_count": len(nodes_data),
            "edge_count": len(edges_data),
        }

    def delete_graph(self, graph_id: str):
        """Elimina il grafo"""
        self.client.graph.delete(graph_id=graph_id)
