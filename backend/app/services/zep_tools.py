"""
Servizio strumenti di ricerca Zep
Incapsula ricerca su grafi, lettura nodi, query sugli archi e altri strumenti, utilizzati dal Report Agent

Strumenti di ricerca principali (ottimizzati):
1. InsightForge (ricerca approfondita) - La ricerca ibrida più potente, genera automaticamente sotto-domande e ricerca multi-dimensionale
2. PanoramaSearch (ricerca ad ampio raggio) - Ottiene la visione completa, inclusi contenuti scaduti
3. QuickSearch (ricerca semplice) - Ricerca rapida
"""

import time
import json
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field

from zep_cloud.client import Zep

from ..config import Config
from ..utils.logger import get_logger
from ..utils.llm_client import LLMClient
from ..utils.zep_paging import fetch_all_nodes, fetch_all_edges

logger = get_logger('mirofish.zep_tools')


@dataclass
class SearchResult:
    """Risultato di ricerca"""
    facts: List[str]
    edges: List[Dict[str, Any]]
    nodes: List[Dict[str, Any]]
    query: str
    total_count: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "facts": self.facts,
            "edges": self.edges,
            "nodes": self.nodes,
            "query": self.query,
            "total_count": self.total_count
        }

    def to_text(self) -> str:
        """Converte in formato testo, comprensibile dal LLM"""
        text_parts = [f"Query di ricerca: {self.query}", f"Trovate {self.total_count} informazioni pertinenti"]

        if self.facts:
            text_parts.append("\n### Fatti pertinenti:")
            for i, fact in enumerate(self.facts, 1):
                text_parts.append(f"{i}. {fact}")

        return "\n".join(text_parts)


@dataclass
class NodeInfo:
    """Informazioni sul nodo"""
    uuid: str
    name: str
    labels: List[str]
    summary: str
    attributes: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "uuid": self.uuid,
            "name": self.name,
            "labels": self.labels,
            "summary": self.summary,
            "attributes": self.attributes
        }

    def to_text(self) -> str:
        """Converte in formato testo"""
        entity_type = next((l for l in self.labels if l not in ["Entity", "Node"]), "Tipo sconosciuto")
        return f"Entità: {self.name} (Tipo: {entity_type})\nRiepilogo: {self.summary}"


@dataclass
class EdgeInfo:
    """Informazioni sull'arco"""
    uuid: str
    name: str
    fact: str
    source_node_uuid: str
    target_node_uuid: str
    source_node_name: Optional[str] = None
    target_node_name: Optional[str] = None
    # Informazioni temporali
    created_at: Optional[str] = None
    valid_at: Optional[str] = None
    invalid_at: Optional[str] = None
    expired_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "uuid": self.uuid,
            "name": self.name,
            "fact": self.fact,
            "source_node_uuid": self.source_node_uuid,
            "target_node_uuid": self.target_node_uuid,
            "source_node_name": self.source_node_name,
            "target_node_name": self.target_node_name,
            "created_at": self.created_at,
            "valid_at": self.valid_at,
            "invalid_at": self.invalid_at,
            "expired_at": self.expired_at
        }

    def to_text(self, include_temporal: bool = False) -> str:
        """Converte in formato testo"""
        source = self.source_node_name or self.source_node_uuid[:8]
        target = self.target_node_name or self.target_node_uuid[:8]
        base_text = f"Relazione: {source} --[{self.name}]--> {target}\nFatto: {self.fact}"

        if include_temporal:
            valid_at = self.valid_at or "Sconosciuto"
            invalid_at = self.invalid_at or "Ad oggi"
            base_text += f"\nValidità: {valid_at} - {invalid_at}"
            if self.expired_at:
                base_text += f" (Scaduto: {self.expired_at})"

        return base_text

    @property
    def is_expired(self) -> bool:
        """Se è scaduto"""
        return self.expired_at is not None

    @property
    def is_invalid(self) -> bool:
        """Se è invalidato"""
        return self.invalid_at is not None


@dataclass
class InsightForgeResult:
    """
    Risultato della ricerca approfondita (InsightForge)
    Contiene i risultati di ricerca per più sotto-domande e l'analisi integrata
    """
    query: str
    simulation_requirement: str
    sub_queries: List[str]

    # Risultati di ricerca per ogni dimensione
    semantic_facts: List[str] = field(default_factory=list)  # Risultati ricerca semantica
    entity_insights: List[Dict[str, Any]] = field(default_factory=list)  # Approfondimenti sulle entità
    relationship_chains: List[str] = field(default_factory=list)  # Catene di relazioni

    # Informazioni statistiche
    total_facts: int = 0
    total_entities: int = 0
    total_relationships: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "query": self.query,
            "simulation_requirement": self.simulation_requirement,
            "sub_queries": self.sub_queries,
            "semantic_facts": self.semantic_facts,
            "entity_insights": self.entity_insights,
            "relationship_chains": self.relationship_chains,
            "total_facts": self.total_facts,
            "total_entities": self.total_entities,
            "total_relationships": self.total_relationships
        }

    def to_text(self) -> str:
        """Converte in formato testo dettagliato, comprensibile dal LLM"""
        text_parts = [
            f"## Analisi approfondita per previsioni future",
            f"Domanda di analisi: {self.query}",
            f"Scenario di previsione: {self.simulation_requirement}",
            f"\n### Statistiche dati di previsione",
            f"- Fatti di previsione pertinenti: {self.total_facts}",
            f"- Entità coinvolte: {self.total_entities}",
            f"- Catene di relazioni: {self.total_relationships}"
        ]

        # Sotto-domande
        if self.sub_queries:
            text_parts.append(f"\n### Sotto-domande analizzate")
            for i, sq in enumerate(self.sub_queries, 1):
                text_parts.append(f"{i}. {sq}")

        # Risultati ricerca semantica
        if self.semantic_facts:
            text_parts.append(f"\n### [Fatti chiave] (citare questi testi originali nel report)")
            for i, fact in enumerate(self.semantic_facts, 1):
                text_parts.append(f"{i}. \"{fact}\"")

        # Approfondimenti sulle entità
        if self.entity_insights:
            text_parts.append(f"\n### [Entità principali]")
            for entity in self.entity_insights:
                text_parts.append(f"- **{entity.get('name', 'Sconosciuto')}** ({entity.get('type', 'Entità')})")
                if entity.get('summary'):
                    text_parts.append(f"  Riepilogo: \"{entity.get('summary')}\"")
                if entity.get('related_facts'):
                    text_parts.append(f"  Fatti correlati: {len(entity.get('related_facts', []))}")

        # Catene di relazioni
        if self.relationship_chains:
            text_parts.append(f"\n### [Catene di relazioni]")
            for chain in self.relationship_chains:
                text_parts.append(f"- {chain}")

        return "\n".join(text_parts)


@dataclass
class PanoramaResult:
    """
    Risultato della ricerca ad ampio raggio (Panorama)
    Contiene tutte le informazioni pertinenti, inclusi i contenuti scaduti
    """
    query: str

    # Tutti i nodi
    all_nodes: List[NodeInfo] = field(default_factory=list)
    # Tutti gli archi (inclusi quelli scaduti)
    all_edges: List[EdgeInfo] = field(default_factory=list)
    # Fatti attualmente validi
    active_facts: List[str] = field(default_factory=list)
    # Fatti scaduti/invalidati (registro storico)
    historical_facts: List[str] = field(default_factory=list)

    # Statistiche
    total_nodes: int = 0
    total_edges: int = 0
    active_count: int = 0
    historical_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "query": self.query,
            "all_nodes": [n.to_dict() for n in self.all_nodes],
            "all_edges": [e.to_dict() for e in self.all_edges],
            "active_facts": self.active_facts,
            "historical_facts": self.historical_facts,
            "total_nodes": self.total_nodes,
            "total_edges": self.total_edges,
            "active_count": self.active_count,
            "historical_count": self.historical_count
        }

    def to_text(self) -> str:
        """Converte in formato testo (versione completa, senza troncamento)"""
        text_parts = [
            f"## Risultati ricerca ad ampio raggio (Vista panoramica futura)",
            f"Query: {self.query}",
            f"\n### Informazioni statistiche",
            f"- Nodi totali: {self.total_nodes}",
            f"- Archi totali: {self.total_edges}",
            f"- Fatti attualmente validi: {self.active_count}",
            f"- Fatti storici/scaduti: {self.historical_count}"
        ]

        # Fatti attualmente validi (output completo, senza troncamento)
        if self.active_facts:
            text_parts.append(f"\n### [Fatti attualmente validi] (testo originale dei risultati di simulazione)")
            for i, fact in enumerate(self.active_facts, 1):
                text_parts.append(f"{i}. \"{fact}\"")

        # Fatti storici/scaduti (output completo, senza troncamento)
        if self.historical_facts:
            text_parts.append(f"\n### [Fatti storici/scaduti] (registro del processo evolutivo)")
            for i, fact in enumerate(self.historical_facts, 1):
                text_parts.append(f"{i}. \"{fact}\"")

        # Entità chiave (output completo, senza troncamento)
        if self.all_nodes:
            text_parts.append(f"\n### [Entità coinvolte]")
            for node in self.all_nodes:
                entity_type = next((l for l in node.labels if l not in ["Entity", "Node"]), "Entità")
                text_parts.append(f"- **{node.name}** ({entity_type})")

        return "\n".join(text_parts)


@dataclass
class AgentInterview:
    """Risultato dell'intervista di un singolo Agent"""
    agent_name: str
    agent_role: str  # Tipo di ruolo (es.: studente, insegnante, media, ecc.)
    agent_bio: str  # Biografia
    question: str  # Domanda dell'intervista
    response: str  # Risposta dell'intervista
    key_quotes: List[str] = field(default_factory=list)  # Citazioni chiave

    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent_name": self.agent_name,
            "agent_role": self.agent_role,
            "agent_bio": self.agent_bio,
            "question": self.question,
            "response": self.response,
            "key_quotes": self.key_quotes
        }

    def to_text(self) -> str:
        text = f"**{self.agent_name}** ({self.agent_role})\n"
        # Mostra la bio completa dell'agent, senza troncamento
        text += f"_Biografia: {self.agent_bio}_\n\n"
        text += f"**Q:** {self.question}\n\n"
        text += f"**A:** {self.response}\n"
        if self.key_quotes:
            text += "\n**Citazioni chiave:**\n"
            for quote in self.key_quotes:
                # Pulizia dei vari tipi di virgolette
                clean_quote = quote.replace('\u201c', '').replace('\u201d', '').replace('"', '')
                clean_quote = clean_quote.replace('\u300c', '').replace('\u300d', '')
                clean_quote = clean_quote.strip()
                # Rimuovi la punteggiatura iniziale
                while clean_quote and clean_quote[0] in '，,；;：:、。！？\n\r\t ':
                    clean_quote = clean_quote[1:]
                # Filtra contenuti spazzatura con numeri di domanda (domanda 1-9)
                skip = False
                for d in '123456789':
                    if f'\u95ee\u9898{d}' in clean_quote:
                        skip = True
                        break
                if skip:
                    continue
                # Tronca contenuti troppo lunghi (troncamento al punto, non troncamento rigido)
                if len(clean_quote) > 150:
                    dot_pos = clean_quote.find('\u3002', 80)
                    if dot_pos > 0:
                        clean_quote = clean_quote[:dot_pos + 1]
                    else:
                        clean_quote = clean_quote[:147] + "..."
                if clean_quote and len(clean_quote) >= 10:
                    text += f'> "{clean_quote}"\n'
        return text


@dataclass
class InterviewResult:
    """
    Risultato dell'intervista (Interview)
    Contiene le risposte dell'intervista di più Agent simulati
    """
    interview_topic: str  # Tema dell'intervista
    interview_questions: List[str]  # Lista delle domande dell'intervista

    # Agent selezionati per l'intervista
    selected_agents: List[Dict[str, Any]] = field(default_factory=list)
    # Risposte dell'intervista di ogni Agent
    interviews: List[AgentInterview] = field(default_factory=list)

    # Motivazione della selezione degli Agent
    selection_reasoning: str = ""
    # Riepilogo integrato dell'intervista
    summary: str = ""

    # Statistiche
    total_agents: int = 0
    interviewed_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "interview_topic": self.interview_topic,
            "interview_questions": self.interview_questions,
            "selected_agents": self.selected_agents,
            "interviews": [i.to_dict() for i in self.interviews],
            "selection_reasoning": self.selection_reasoning,
            "summary": self.summary,
            "total_agents": self.total_agents,
            "interviewed_count": self.interviewed_count
        }

    def to_text(self) -> str:
        """Converte in formato testo dettagliato, per la comprensione del LLM e la citazione nel report"""
        text_parts = [
            "## Report dell'intervista approfondita",
            f"**Tema dell'intervista:** {self.interview_topic}",
            f"**Numero di intervistati:** {self.interviewed_count} / {self.total_agents} Agent simulati",
            "\n### Motivazione della selezione degli intervistati",
            self.selection_reasoning or "(Selezione automatica)",
            "\n---",
            "\n### Trascrizione dell'intervista",
        ]

        if self.interviews:
            for i, interview in enumerate(self.interviews, 1):
                text_parts.append(f"\n#### Intervista #{i}: {interview.agent_name}")
                text_parts.append(interview.to_text())
                text_parts.append("\n---")
        else:
            text_parts.append("(Nessuna trascrizione di intervista)\n\n---")

        text_parts.append("\n### Riepilogo dell'intervista e punti di vista principali")
        text_parts.append(self.summary or "(Nessun riepilogo)")

        return "\n".join(text_parts)


class ZepToolsService:
    """
    Servizio strumenti di ricerca Zep

    [Strumenti di ricerca principali - Ottimizzati]
    1. insight_forge - Ricerca approfondita (il più potente, genera automaticamente sotto-domande, ricerca multi-dimensionale)
    2. panorama_search - Ricerca ad ampio raggio (ottiene la visione completa, inclusi contenuti scaduti)
    3. quick_search - Ricerca semplice (ricerca rapida)
    4. interview_agents - Intervista approfondita (intervista Agent simulati, ottiene prospettive multiple)

    [Strumenti di base]
    - search_graph - Ricerca semantica sul grafo
    - get_all_nodes - Ottiene tutti i nodi del grafo
    - get_all_edges - Ottiene tutti gli archi del grafo (con informazioni temporali)
    - get_node_detail - Ottiene informazioni dettagliate sul nodo
    - get_node_edges - Ottiene gli archi relativi a un nodo
    - get_entities_by_type - Ottiene entità per tipo
    - get_entity_summary - Ottiene il riepilogo delle relazioni di un'entità
    """

    # Configurazione dei tentativi
    MAX_RETRIES = 3
    RETRY_DELAY = 2.0

    def __init__(self, api_key: Optional[str] = None, llm_client: Optional[LLMClient] = None):
        self.api_key = api_key or Config.ZEP_API_KEY
        if not self.api_key:
            raise ValueError("ZEP_API_KEY non configurata")

        self.client = Zep(api_key=self.api_key)
        # Client LLM utilizzato da InsightForge per generare sotto-domande
        self._llm_client = llm_client
        logger.info("ZepToolsService inizializzato con successo")

    @property
    def llm(self) -> LLMClient:
        """Inizializzazione lazy del client LLM"""
        if self._llm_client is None:
            self._llm_client = LLMClient()
        return self._llm_client

    def _call_with_retry(self, func, operation_name: str, max_retries: int = None):
        """Chiamata API con meccanismo di retry"""
        max_retries = max_retries or self.MAX_RETRIES
        last_exception = None
        delay = self.RETRY_DELAY

        for attempt in range(max_retries):
            try:
                return func()
            except Exception as e:
                last_exception = e
                if attempt < max_retries - 1:
                    logger.warning(
                        f"Zep {operation_name} tentativo {attempt + 1} fallito: {str(e)[:100]}, "
                        f"nuovo tentativo tra {delay:.1f} secondi..."
                    )
                    time.sleep(delay)
                    delay *= 2
                else:
                    logger.error(f"Zep {operation_name} ancora fallito dopo {max_retries} tentativi: {str(e)}")

        raise last_exception

    def search_graph(
        self,
        graph_id: str,
        query: str,
        limit: int = 10,
        scope: str = "edges"
    ) -> SearchResult:
        """
        Ricerca semantica sul grafo

        Utilizza la ricerca ibrida (semantica+BM25) per cercare informazioni pertinenti nel grafo.
        Se l'API di ricerca di Zep Cloud non è disponibile, degrada alla corrispondenza locale per parole chiave.

        Args:
            graph_id: ID del grafo (Standalone Graph)
            query: Query di ricerca
            limit: Numero di risultati da restituire
            scope: Ambito di ricerca, "edges" o "nodes"

        Returns:
            SearchResult: Risultato della ricerca
        """
        logger.info(f"Ricerca sul grafo: graph_id={graph_id}, query={query[:50]}...")

        # Tentativo di utilizzo dell'API di ricerca Zep Cloud
        try:
            search_results = self._call_with_retry(
                func=lambda: self.client.graph.search(
                    graph_id=graph_id,
                    query=query,
                    limit=limit,
                    scope=scope,
                    reranker="cross_encoder"
                ),
                operation_name=f"Ricerca sul grafo(graph={graph_id})"
            )

            facts = []
            edges = []
            nodes = []

            # Analisi dei risultati di ricerca sugli archi
            if hasattr(search_results, 'edges') and search_results.edges:
                for edge in search_results.edges:
                    if hasattr(edge, 'fact') and edge.fact:
                        facts.append(edge.fact)
                    edges.append({
                        "uuid": getattr(edge, 'uuid_', None) or getattr(edge, 'uuid', ''),
                        "name": getattr(edge, 'name', ''),
                        "fact": getattr(edge, 'fact', ''),
                        "source_node_uuid": getattr(edge, 'source_node_uuid', ''),
                        "target_node_uuid": getattr(edge, 'target_node_uuid', ''),
                    })

            # Analisi dei risultati di ricerca sui nodi
            if hasattr(search_results, 'nodes') and search_results.nodes:
                for node in search_results.nodes:
                    nodes.append({
                        "uuid": getattr(node, 'uuid_', None) or getattr(node, 'uuid', ''),
                        "name": getattr(node, 'name', ''),
                        "labels": getattr(node, 'labels', []),
                        "summary": getattr(node, 'summary', ''),
                    })
                    # Il riepilogo del nodo conta anche come fatto
                    if hasattr(node, 'summary') and node.summary:
                        facts.append(f"[{node.name}]: {node.summary}")

            logger.info(f"Ricerca completata: trovati {len(facts)} fatti pertinenti")

            return SearchResult(
                facts=facts,
                edges=edges,
                nodes=nodes,
                query=query,
                total_count=len(facts)
            )

        except Exception as e:
            logger.warning(f"API di ricerca Zep fallita, degradazione alla ricerca locale: {str(e)}")
            # Degradazione: utilizzo della corrispondenza locale per parole chiave
            return self._local_search(graph_id, query, limit, scope)

    def _local_search(
        self,
        graph_id: str,
        query: str,
        limit: int = 10,
        scope: str = "edges"
    ) -> SearchResult:
        """
        Ricerca locale per corrispondenza di parole chiave (come soluzione di degradazione per l'API di ricerca Zep)

        Ottiene tutti gli archi/nodi, poi esegue la corrispondenza per parole chiave localmente

        Args:
            graph_id: ID del grafo
            query: Query di ricerca
            limit: Numero di risultati da restituire
            scope: Ambito di ricerca

        Returns:
            SearchResult: Risultato della ricerca
        """
        logger.info(f"Utilizzo ricerca locale: query={query[:30]}...")

        facts = []
        edges_result = []
        nodes_result = []

        # Estrazione delle parole chiave dalla query (tokenizzazione semplice)
        query_lower = query.lower()
        keywords = [w.strip() for w in query_lower.replace(',', ' ').replace('，', ' ').split() if len(w.strip()) > 1]

        def match_score(text: str) -> int:
            """Calcola il punteggio di corrispondenza tra testo e query"""
            if not text:
                return 0
            text_lower = text.lower()
            # Corrispondenza completa della query
            if query_lower in text_lower:
                return 100
            # Corrispondenza per parole chiave
            score = 0
            for keyword in keywords:
                if keyword in text_lower:
                    score += 10
            return score

        try:
            if scope in ["edges", "both"]:
                # Ottieni tutti gli archi e cerca corrispondenze
                all_edges = self.get_all_edges(graph_id)
                scored_edges = []
                for edge in all_edges:
                    score = match_score(edge.fact) + match_score(edge.name)
                    if score > 0:
                        scored_edges.append((score, edge))

                # Ordina per punteggio
                scored_edges.sort(key=lambda x: x[0], reverse=True)

                for score, edge in scored_edges[:limit]:
                    if edge.fact:
                        facts.append(edge.fact)
                    edges_result.append({
                        "uuid": edge.uuid,
                        "name": edge.name,
                        "fact": edge.fact,
                        "source_node_uuid": edge.source_node_uuid,
                        "target_node_uuid": edge.target_node_uuid,
                    })

            if scope in ["nodes", "both"]:
                # Ottieni tutti i nodi e cerca corrispondenze
                all_nodes = self.get_all_nodes(graph_id)
                scored_nodes = []
                for node in all_nodes:
                    score = match_score(node.name) + match_score(node.summary)
                    if score > 0:
                        scored_nodes.append((score, node))

                scored_nodes.sort(key=lambda x: x[0], reverse=True)

                for score, node in scored_nodes[:limit]:
                    nodes_result.append({
                        "uuid": node.uuid,
                        "name": node.name,
                        "labels": node.labels,
                        "summary": node.summary,
                    })
                    if node.summary:
                        facts.append(f"[{node.name}]: {node.summary}")

            logger.info(f"Ricerca locale completata: trovati {len(facts)} fatti pertinenti")

        except Exception as e:
            logger.error(f"Ricerca locale fallita: {str(e)}")

        return SearchResult(
            facts=facts,
            edges=edges_result,
            nodes=nodes_result,
            query=query,
            total_count=len(facts)
        )

    def get_all_nodes(self, graph_id: str) -> List[NodeInfo]:
        """
        Ottiene tutti i nodi del grafo (con paginazione)

        Args:
            graph_id: ID del grafo

        Returns:
            Lista dei nodi
        """
        logger.info(f"Recupero di tutti i nodi del grafo {graph_id}...")

        nodes = fetch_all_nodes(self.client, graph_id)

        result = []
        for node in nodes:
            node_uuid = getattr(node, 'uuid_', None) or getattr(node, 'uuid', None) or ""
            result.append(NodeInfo(
                uuid=str(node_uuid) if node_uuid else "",
                name=node.name or "",
                labels=node.labels or [],
                summary=node.summary or "",
                attributes=node.attributes or {}
            ))

        logger.info(f"Recuperati {len(result)} nodi")
        return result

    def get_all_edges(self, graph_id: str, include_temporal: bool = True) -> List[EdgeInfo]:
        """
        Ottiene tutti gli archi del grafo (con paginazione, incluse informazioni temporali)

        Args:
            graph_id: ID del grafo
            include_temporal: Se includere le informazioni temporali (predefinito True)

        Returns:
            Lista degli archi (include created_at, valid_at, invalid_at, expired_at)
        """
        logger.info(f"Recupero di tutti gli archi del grafo {graph_id}...")

        edges = fetch_all_edges(self.client, graph_id)

        result = []
        for edge in edges:
            edge_uuid = getattr(edge, 'uuid_', None) or getattr(edge, 'uuid', None) or ""
            edge_info = EdgeInfo(
                uuid=str(edge_uuid) if edge_uuid else "",
                name=edge.name or "",
                fact=edge.fact or "",
                source_node_uuid=edge.source_node_uuid or "",
                target_node_uuid=edge.target_node_uuid or ""
            )

            # Aggiunta informazioni temporali
            if include_temporal:
                edge_info.created_at = getattr(edge, 'created_at', None)
                edge_info.valid_at = getattr(edge, 'valid_at', None)
                edge_info.invalid_at = getattr(edge, 'invalid_at', None)
                edge_info.expired_at = getattr(edge, 'expired_at', None)

            result.append(edge_info)

        logger.info(f"Recuperati {len(result)} archi")
        return result

    def get_node_detail(self, node_uuid: str) -> Optional[NodeInfo]:
        """
        Ottiene le informazioni dettagliate di un singolo nodo

        Args:
            node_uuid: UUID del nodo

        Returns:
            Informazioni sul nodo o None
        """
        logger.info(f"Recupero dettagli nodo: {node_uuid[:8]}...")

        try:
            node = self._call_with_retry(
                func=lambda: self.client.graph.node.get(uuid_=node_uuid),
                operation_name=f"Recupero dettagli nodo(uuid={node_uuid[:8]}...)"
            )

            if not node:
                return None

            return NodeInfo(
                uuid=getattr(node, 'uuid_', None) or getattr(node, 'uuid', ''),
                name=node.name or "",
                labels=node.labels or [],
                summary=node.summary or "",
                attributes=node.attributes or {}
            )
        except Exception as e:
            logger.error(f"Recupero dettagli nodo fallito: {str(e)}")
            return None

    def get_node_edges(self, graph_id: str, node_uuid: str) -> List[EdgeInfo]:
        """
        Ottiene tutti gli archi relativi a un nodo

        Ottiene tutti gli archi del grafo, poi filtra quelli relativi al nodo specificato

        Args:
            graph_id: ID del grafo
            node_uuid: UUID del nodo

        Returns:
            Lista degli archi
        """
        logger.info(f"Recupero archi relativi al nodo {node_uuid[:8]}...")

        try:
            # Ottieni tutti gli archi del grafo, poi filtra
            all_edges = self.get_all_edges(graph_id)

            result = []
            for edge in all_edges:
                # Verifica se l'arco è relativo al nodo specificato (come sorgente o destinazione)
                if edge.source_node_uuid == node_uuid or edge.target_node_uuid == node_uuid:
                    result.append(edge)

            logger.info(f"Trovati {len(result)} archi relativi al nodo")
            return result

        except Exception as e:
            logger.warning(f"Recupero archi del nodo fallito: {str(e)}")
            return []

    def get_entities_by_type(
        self,
        graph_id: str,
        entity_type: str
    ) -> List[NodeInfo]:
        """
        Ottiene entità per tipo

        Args:
            graph_id: ID del grafo
            entity_type: Tipo di entità (es. Student, PublicFigure, ecc.)

        Returns:
            Lista delle entità del tipo specificato
        """
        logger.info(f"Recupero entità di tipo {entity_type}...")

        all_nodes = self.get_all_nodes(graph_id)

        filtered = []
        for node in all_nodes:
            # Verifica se le labels contengono il tipo specificato
            if entity_type in node.labels:
                filtered.append(node)

        logger.info(f"Trovate {len(filtered)} entità di tipo {entity_type}")
        return filtered

    def get_entity_summary(
        self,
        graph_id: str,
        entity_name: str
    ) -> Dict[str, Any]:
        """
        Ottiene il riepilogo delle relazioni di un'entità specificata

        Cerca tutte le informazioni relative all'entità e genera un riepilogo

        Args:
            graph_id: ID del grafo
            entity_name: Nome dell'entità

        Returns:
            Informazioni di riepilogo dell'entità
        """
        logger.info(f"Recupero riepilogo relazioni dell'entità {entity_name}...")

        # Prima cerca le informazioni relative all'entità
        search_result = self.search_graph(
            graph_id=graph_id,
            query=entity_name,
            limit=20
        )

        # Cerca l'entità tra tutti i nodi
        all_nodes = self.get_all_nodes(graph_id)
        entity_node = None
        for node in all_nodes:
            if node.name.lower() == entity_name.lower():
                entity_node = node
                break

        related_edges = []
        if entity_node:
            # Passa il parametro graph_id
            related_edges = self.get_node_edges(graph_id, entity_node.uuid)

        return {
            "entity_name": entity_name,
            "entity_info": entity_node.to_dict() if entity_node else None,
            "related_facts": search_result.facts,
            "related_edges": [e.to_dict() for e in related_edges],
            "total_relations": len(related_edges)
        }

    def get_graph_statistics(self, graph_id: str) -> Dict[str, Any]:
        """
        Ottiene le informazioni statistiche del grafo

        Args:
            graph_id: ID del grafo

        Returns:
            Informazioni statistiche
        """
        logger.info(f"Recupero statistiche del grafo {graph_id}...")

        nodes = self.get_all_nodes(graph_id)
        edges = self.get_all_edges(graph_id)

        # Distribuzione dei tipi di entità
        entity_types = {}
        for node in nodes:
            for label in node.labels:
                if label not in ["Entity", "Node"]:
                    entity_types[label] = entity_types.get(label, 0) + 1

        # Distribuzione dei tipi di relazione
        relation_types = {}
        for edge in edges:
            relation_types[edge.name] = relation_types.get(edge.name, 0) + 1

        return {
            "graph_id": graph_id,
            "total_nodes": len(nodes),
            "total_edges": len(edges),
            "entity_types": entity_types,
            "relation_types": relation_types
        }

    def get_simulation_context(
        self,
        graph_id: str,
        simulation_requirement: str,
        limit: int = 30
    ) -> Dict[str, Any]:
        """
        Ottiene le informazioni di contesto relative alla simulazione

        Ricerca completa di tutte le informazioni pertinenti ai requisiti della simulazione

        Args:
            graph_id: ID del grafo
            simulation_requirement: Descrizione dei requisiti della simulazione
            limit: Limite di quantità per ogni tipo di informazione

        Returns:
            Informazioni di contesto della simulazione
        """
        logger.info(f"Recupero contesto simulazione: {simulation_requirement[:50]}...")

        # Cerca le informazioni relative ai requisiti della simulazione
        search_result = self.search_graph(
            graph_id=graph_id,
            query=simulation_requirement,
            limit=limit
        )

        # Ottieni le statistiche del grafo
        stats = self.get_graph_statistics(graph_id)

        # Ottieni tutti i nodi entità
        all_nodes = self.get_all_nodes(graph_id)

        # Filtra le entità con tipo effettivo (non nodi Entity puri)
        entities = []
        for node in all_nodes:
            custom_labels = [l for l in node.labels if l not in ["Entity", "Node"]]
            if custom_labels:
                entities.append({
                    "name": node.name,
                    "type": custom_labels[0],
                    "summary": node.summary
                })

        return {
            "simulation_requirement": simulation_requirement,
            "related_facts": search_result.facts,
            "graph_statistics": stats,
            "entities": entities[:limit],  # Limita la quantità
            "total_entities": len(entities)
        }

    # ========== Strumenti di ricerca principali (ottimizzati) ==========

    def insight_forge(
        self,
        graph_id: str,
        query: str,
        simulation_requirement: str,
        report_context: str = "",
        max_sub_queries: int = 5
    ) -> InsightForgeResult:
        """
        [InsightForge - Ricerca approfondita]

        La funzione di ricerca ibrida più potente, scompone automaticamente le domande e ricerca su più dimensioni:
        1. Utilizza il LLM per scomporre la domanda in più sotto-domande
        2. Esegue una ricerca semantica per ogni sotto-domanda
        3. Estrae le entità pertinenti e ottiene le loro informazioni dettagliate
        4. Traccia le catene di relazioni
        5. Integra tutti i risultati, generando approfondimenti

        Args:
            graph_id: ID del grafo
            query: Domanda dell'utente
            simulation_requirement: Descrizione dei requisiti della simulazione
            report_context: Contesto del report (opzionale, per una generazione più precisa delle sotto-domande)
            max_sub_queries: Numero massimo di sotto-domande

        Returns:
            InsightForgeResult: Risultato della ricerca approfondita
        """
        logger.info(f"InsightForge ricerca approfondita: {query[:50]}...")

        result = InsightForgeResult(
            query=query,
            simulation_requirement=simulation_requirement,
            sub_queries=[]
        )

        # Passo 1: Utilizzo del LLM per generare sotto-domande
        sub_queries = self._generate_sub_queries(
            query=query,
            simulation_requirement=simulation_requirement,
            report_context=report_context,
            max_queries=max_sub_queries
        )
        result.sub_queries = sub_queries
        logger.info(f"Generate {len(sub_queries)} sotto-domande")

        # Passo 2: Ricerca semantica per ogni sotto-domanda
        all_facts = []
        all_edges = []
        seen_facts = set()

        for sub_query in sub_queries:
            search_result = self.search_graph(
                graph_id=graph_id,
                query=sub_query,
                limit=15,
                scope="edges"
            )

            for fact in search_result.facts:
                if fact not in seen_facts:
                    all_facts.append(fact)
                    seen_facts.add(fact)

            all_edges.extend(search_result.edges)

        # Ricerca anche sulla domanda originale
        main_search = self.search_graph(
            graph_id=graph_id,
            query=query,
            limit=20,
            scope="edges"
        )
        for fact in main_search.facts:
            if fact not in seen_facts:
                all_facts.append(fact)
                seen_facts.add(fact)

        result.semantic_facts = all_facts
        result.total_facts = len(all_facts)

        # Passo 3: Estrazione degli UUID delle entità pertinenti dagli archi, recupero info solo per queste entità (non tutti i nodi)
        entity_uuids = set()
        for edge_data in all_edges:
            if isinstance(edge_data, dict):
                source_uuid = edge_data.get('source_node_uuid', '')
                target_uuid = edge_data.get('target_node_uuid', '')
                if source_uuid:
                    entity_uuids.add(source_uuid)
                if target_uuid:
                    entity_uuids.add(target_uuid)

        # Recupero dettagli di tutte le entità pertinenti (senza limite di quantità, output completo)
        entity_insights = []
        node_map = {}  # Per la costruzione successiva delle catene di relazioni

        for uuid in list(entity_uuids):  # Elabora tutte le entità, senza troncamento
            if not uuid:
                continue
            try:
                # Recupero individuale delle informazioni di ogni nodo pertinente
                node = self.get_node_detail(uuid)
                if node:
                    node_map[uuid] = node
                    entity_type = next((l for l in node.labels if l not in ["Entity", "Node"]), "Entità")

                    # Recupero di tutti i fatti relativi all'entità (senza troncamento)
                    related_facts = [
                        f for f in all_facts
                        if node.name.lower() in f.lower()
                    ]

                    entity_insights.append({
                        "uuid": node.uuid,
                        "name": node.name,
                        "type": entity_type,
                        "summary": node.summary,
                        "related_facts": related_facts  # Output completo, senza troncamento
                    })
            except Exception as e:
                logger.debug(f"Recupero nodo {uuid} fallito: {e}")
                continue

        result.entity_insights = entity_insights
        result.total_entities = len(entity_insights)

        # Passo 4: Costruzione di tutte le catene di relazioni (senza limite di quantità)
        relationship_chains = []
        for edge_data in all_edges:  # Elabora tutti gli archi, senza troncamento
            if isinstance(edge_data, dict):
                source_uuid = edge_data.get('source_node_uuid', '')
                target_uuid = edge_data.get('target_node_uuid', '')
                relation_name = edge_data.get('name', '')

                source_name = node_map.get(source_uuid, NodeInfo('', '', [], '', {})).name or source_uuid[:8]
                target_name = node_map.get(target_uuid, NodeInfo('', '', [], '', {})).name or target_uuid[:8]

                chain = f"{source_name} --[{relation_name}]--> {target_name}"
                if chain not in relationship_chains:
                    relationship_chains.append(chain)

        result.relationship_chains = relationship_chains
        result.total_relationships = len(relationship_chains)

        logger.info(f"InsightForge completato: {result.total_facts} fatti, {result.total_entities} entità, {result.total_relationships} relazioni")
        return result

    def _generate_sub_queries(
        self,
        query: str,
        simulation_requirement: str,
        report_context: str = "",
        max_queries: int = 5
    ) -> List[str]:
        """
        Utilizza il LLM per generare sotto-domande

        Scompone una domanda complessa in più sotto-domande che possono essere cercate indipendentemente
        """
        system_prompt = """Sei un esperto professionista nell'analisi delle domande. Il tuo compito è scomporre una domanda complessa in più sotto-domande che possono essere osservate indipendentemente nel mondo simulato.

Requisiti:
1. Ogni sotto-domanda deve essere sufficientemente specifica per trovare comportamenti o eventi degli Agent nel mondo simulato
2. Le sotto-domande devono coprire diverse dimensioni della domanda originale (es.: chi, cosa, perché, come, quando, dove)
3. Le sotto-domande devono essere pertinenti allo scenario di simulazione
4. Restituisci in formato JSON: {"sub_queries": ["sotto-domanda 1", "sotto-domanda 2", ...]}"""

        user_prompt = f"""Contesto dei requisiti di simulazione:
{simulation_requirement}

{f"Contesto del report: {report_context[:500]}" if report_context else ""}

Per favore scomponi la seguente domanda in {max_queries} sotto-domande:
{query}

Restituisci la lista delle sotto-domande in formato JSON."""

        try:
            response = self.llm.chat_json(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.3
            )

            sub_queries = response.get("sub_queries", [])
            # Assicura che sia una lista di stringhe
            return [str(sq) for sq in sub_queries[:max_queries]]

        except Exception as e:
            logger.warning(f"Generazione sotto-domande fallita: {str(e)}, utilizzo sotto-domande predefinite")
            # Degradazione: restituisce varianti basate sulla domanda originale
            return [
                query,
                f"Principali partecipanti di {query}",
                f"Cause e impatti di {query}",
                f"Processo di sviluppo di {query}"
            ][:max_queries]

    def panorama_search(
        self,
        graph_id: str,
        query: str,
        include_expired: bool = True,
        limit: int = 50
    ) -> PanoramaResult:
        """
        [PanoramaSearch - Ricerca ad ampio raggio]

        Ottiene la vista panoramica completa, inclusi tutti i contenuti pertinenti e le informazioni storiche/scadute:
        1. Ottiene tutti i nodi pertinenti
        2. Ottiene tutti gli archi (inclusi quelli scaduti/invalidati)
        3. Classifica e organizza le informazioni attuali e storiche

        Questo strumento è adatto a scenari in cui è necessario comprendere la visione completa di un evento o tracciare il processo evolutivo.

        Args:
            graph_id: ID del grafo
            query: Query di ricerca (per l'ordinamento per pertinenza)
            include_expired: Se includere contenuti scaduti (predefinito True)
            limit: Limite sul numero di risultati restituiti

        Returns:
            PanoramaResult: Risultato della ricerca ad ampio raggio
        """
        logger.info(f"PanoramaSearch ricerca ad ampio raggio: {query[:50]}...")

        result = PanoramaResult(query=query)

        # Ottieni tutti i nodi
        all_nodes = self.get_all_nodes(graph_id)
        node_map = {n.uuid: n for n in all_nodes}
        result.all_nodes = all_nodes
        result.total_nodes = len(all_nodes)

        # Ottieni tutti gli archi (con informazioni temporali)
        all_edges = self.get_all_edges(graph_id, include_temporal=True)
        result.all_edges = all_edges
        result.total_edges = len(all_edges)

        # Classificazione dei fatti
        active_facts = []
        historical_facts = []

        for edge in all_edges:
            if not edge.fact:
                continue

            # Aggiunta nomi delle entità ai fatti
            source_name = node_map.get(edge.source_node_uuid, NodeInfo('', '', [], '', {})).name or edge.source_node_uuid[:8]
            target_name = node_map.get(edge.target_node_uuid, NodeInfo('', '', [], '', {})).name or edge.target_node_uuid[:8]

            # Verifica se scaduto/invalidato
            is_historical = edge.is_expired or edge.is_invalid

            if is_historical:
                # Fatto storico/scaduto, aggiunta marcatore temporale
                valid_at = edge.valid_at or "Sconosciuto"
                invalid_at = edge.invalid_at or edge.expired_at or "Sconosciuto"
                fact_with_time = f"[{valid_at} - {invalid_at}] {edge.fact}"
                historical_facts.append(fact_with_time)
            else:
                # Fatto attualmente valido
                active_facts.append(edge.fact)

        # Ordinamento per pertinenza basato sulla query
        query_lower = query.lower()
        keywords = [w.strip() for w in query_lower.replace(',', ' ').replace('，', ' ').split() if len(w.strip()) > 1]

        def relevance_score(fact: str) -> int:
            fact_lower = fact.lower()
            score = 0
            if query_lower in fact_lower:
                score += 100
            for kw in keywords:
                if kw in fact_lower:
                    score += 10
            return score

        # Ordina e limita la quantità
        active_facts.sort(key=relevance_score, reverse=True)
        historical_facts.sort(key=relevance_score, reverse=True)

        result.active_facts = active_facts[:limit]
        result.historical_facts = historical_facts[:limit] if include_expired else []
        result.active_count = len(active_facts)
        result.historical_count = len(historical_facts)

        logger.info(f"PanoramaSearch completato: {result.active_count} validi, {result.historical_count} storici")
        return result

    def quick_search(
        self,
        graph_id: str,
        query: str,
        limit: int = 10
    ) -> SearchResult:
        """
        [QuickSearch - Ricerca semplice]

        Strumento di ricerca rapido e leggero:
        1. Chiama direttamente la ricerca semantica di Zep
        2. Restituisce i risultati più pertinenti
        3. Adatto a esigenze di ricerca semplici e dirette

        Args:
            graph_id: ID del grafo
            query: Query di ricerca
            limit: Numero di risultati da restituire

        Returns:
            SearchResult: Risultato della ricerca
        """
        logger.info(f"QuickSearch ricerca semplice: {query[:50]}...")

        # Chiama direttamente il metodo search_graph esistente
        result = self.search_graph(
            graph_id=graph_id,
            query=query,
            limit=limit,
            scope="edges"
        )

        logger.info(f"QuickSearch completato: {result.total_count} risultati")
        return result

    def interview_agents(
        self,
        simulation_id: str,
        interview_requirement: str,
        simulation_requirement: str = "",
        max_agents: int = 5,
        custom_questions: List[str] = None
    ) -> InterviewResult:
        """
        [InterviewAgents - Intervista approfondita]

        Chiama l'API reale di intervista OASIS, intervistando gli Agent in esecuzione nella simulazione:
        1. Legge automaticamente i file dei profili, per conoscere tutti gli Agent simulati
        2. Utilizza il LLM per analizzare i requisiti dell'intervista, selezionando intelligentemente gli Agent più pertinenti
        3. Utilizza il LLM per generare le domande dell'intervista
        4. Chiama l'interfaccia /api/simulation/interview/batch per l'intervista reale (intervista simultanea su entrambe le piattaforme)
        5. Integra tutti i risultati dell'intervista, generando un report dell'intervista

        [Importante] Questa funzionalità richiede che l'ambiente di simulazione sia in esecuzione (ambiente OASIS non chiuso)

        [Scenari di utilizzo]
        - Necessità di comprendere le opinioni su un evento da diverse prospettive di ruolo
        - Necessità di raccogliere opinioni e punti di vista da più parti
        - Necessità di ottenere risposte reali dagli Agent simulati (non simulate dal LLM)

        Args:
            simulation_id: ID della simulazione (per localizzare i file dei profili e chiamare l'API di intervista)
            interview_requirement: Descrizione dei requisiti dell'intervista (non strutturata, es. "comprendere l'opinione degli studenti sull'evento")
            simulation_requirement: Contesto dei requisiti della simulazione (opzionale)
            max_agents: Numero massimo di Agent da intervistare
            custom_questions: Domande personalizzate per l'intervista (opzionale, se non fornite vengono generate automaticamente)

        Returns:
            InterviewResult: Risultato dell'intervista
        """
        from .simulation_runner import SimulationRunner

        logger.info(f"InterviewAgents intervista approfondita (API reale): {interview_requirement[:50]}...")

        result = InterviewResult(
            interview_topic=interview_requirement,
            interview_questions=custom_questions or []
        )

        # Passo 1: Lettura dei file dei profili
        profiles = self._load_agent_profiles(simulation_id)

        if not profiles:
            logger.warning(f"File dei profili non trovato per la simulazione {simulation_id}")
            result.summary = "File dei profili degli Agent da intervistare non trovato"
            return result

        result.total_agents = len(profiles)
        logger.info(f"Caricati {len(profiles)} profili Agent")

        # Passo 2: Utilizzo del LLM per selezionare gli Agent da intervistare (restituisce lista di agent_id)
        selected_agents, selected_indices, selection_reasoning = self._select_agents_for_interview(
            profiles=profiles,
            interview_requirement=interview_requirement,
            simulation_requirement=simulation_requirement,
            max_agents=max_agents
        )

        result.selected_agents = selected_agents
        result.selection_reasoning = selection_reasoning
        logger.info(f"Selezionati {len(selected_agents)} Agent per l'intervista: {selected_indices}")

        # Passo 3: Generazione delle domande dell'intervista (se non fornite)
        if not result.interview_questions:
            result.interview_questions = self._generate_interview_questions(
                interview_requirement=interview_requirement,
                simulation_requirement=simulation_requirement,
                selected_agents=selected_agents
            )
            logger.info(f"Generate {len(result.interview_questions)} domande per l'intervista")

        # Unisci le domande in un unico prompt di intervista
        combined_prompt = "\n".join([f"{i+1}. {q}" for i, q in enumerate(result.interview_questions)])

        # Aggiunta prefisso ottimizzato per vincolare il formato di risposta dell'Agent
        INTERVIEW_PROMPT_PREFIX = (
            "Stai partecipando a un'intervista. Per favore rispondi alle seguenti domande "
            "basandoti sul tuo profilo, tutti i ricordi passati e le azioni intraprese, "
            "in formato testo semplice.\n"
            "Requisiti di risposta:\n"
            "1. Rispondi direttamente in linguaggio naturale, non chiamare alcuno strumento\n"
            "2. Non restituire formato JSON o formato di chiamata strumenti\n"
            "3. Non utilizzare titoli Markdown (come #, ##, ###)\n"
            "4. Rispondi a ogni domanda in ordine numerico, iniziando ogni risposta con 'Domanda X:' (dove X è il numero della domanda)\n"
            "5. Separa le risposte alle diverse domande con una riga vuota\n"
            "6. Le risposte devono avere contenuto sostanziale, almeno 2-3 frasi per ogni domanda\n\n"
        )
        optimized_prompt = f"{INTERVIEW_PROMPT_PREFIX}{combined_prompt}"

        # Passo 4: Chiamata all'API reale di intervista (senza specificare platform, intervista su entrambe le piattaforme per impostazione predefinita)
        try:
            # Costruzione della lista di interviste in batch (senza specificare platform, intervista su entrambe le piattaforme)
            interviews_request = []
            for agent_idx in selected_indices:
                interviews_request.append({
                    "agent_id": agent_idx,
                    "prompt": optimized_prompt  # Utilizzo del prompt ottimizzato
                    # Senza specificare platform, l'API intervistarà su entrambe le piattaforme twitter e reddit
                })

            logger.info(f"Chiamata API intervista in batch (entrambe le piattaforme): {len(interviews_request)} Agent")

            # Chiamata al metodo di intervista in batch di SimulationRunner (senza passare platform, intervista su entrambe le piattaforme)
            api_result = SimulationRunner.interview_agents_batch(
                simulation_id=simulation_id,
                interviews=interviews_request,
                platform=None,  # Senza specificare platform, intervista su entrambe le piattaforme
                timeout=180.0   # Timeout più lungo necessario per entrambe le piattaforme
            )

            logger.info(f"Risposta API intervista: {api_result.get('interviews_count', 0)} risultati, success={api_result.get('success')}")

            # Verifica se la chiamata API ha avuto successo
            if not api_result.get("success", False):
                error_msg = api_result.get("error", "Errore sconosciuto")
                logger.warning(f"Risposta API intervista fallita: {error_msg}")
                result.summary = f"Chiamata API intervista fallita: {error_msg}. Verificare lo stato dell'ambiente di simulazione OASIS."
                return result

            # Passo 5: Analisi dei risultati restituiti dall'API, costruzione degli oggetti AgentInterview
            # Formato di ritorno in modalità doppia piattaforma: {"twitter_0": {...}, "reddit_0": {...}, "twitter_1": {...}, ...}
            api_data = api_result.get("result", {})
            results_dict = api_data.get("results", {}) if isinstance(api_data, dict) else {}

            for i, agent_idx in enumerate(selected_indices):
                agent = selected_agents[i]
                agent_name = agent.get("realname", agent.get("username", f"Agent_{agent_idx}"))
                agent_role = agent.get("profession", "Sconosciuto")
                agent_bio = agent.get("bio", "")

                # Ottieni i risultati dell'intervista dell'Agent su entrambe le piattaforme
                twitter_result = results_dict.get(f"twitter_{agent_idx}", {})
                reddit_result = results_dict.get(f"reddit_{agent_idx}", {})

                twitter_response = twitter_result.get("response", "")
                reddit_response = reddit_result.get("response", "")

                # Pulizia di eventuali wrapper JSON di chiamata strumenti
                twitter_response = self._clean_tool_call_response(twitter_response)
                reddit_response = self._clean_tool_call_response(reddit_response)

                # Mostra sempre il marcatore di entrambe le piattaforme
                twitter_text = twitter_response if twitter_response else "(Nessuna risposta ottenuta da questa piattaforma)"
                reddit_text = reddit_response if reddit_response else "(Nessuna risposta ottenuta da questa piattaforma)"
                response_text = f"[Risposta piattaforma Twitter]\n{twitter_text}\n\n[Risposta piattaforma Reddit]\n{reddit_text}"

                # Estrazione delle citazioni chiave (dalle risposte di entrambe le piattaforme)
                import re
                combined_responses = f"{twitter_response} {reddit_response}"

                # Pulizia del testo di risposta: rimozione marcatori, numeri, Markdown e altri disturbi
                clean_text = re.sub(r'#{1,6}\s+', '', combined_responses)
                clean_text = re.sub(r'\{[^}]*tool_name[^}]*\}', '', clean_text)
                clean_text = re.sub(r'[*_`|>~\-]{2,}', '', clean_text)
                clean_text = re.sub(r'问题\d+[：:]\s*', '', clean_text)
                clean_text = re.sub(r'【[^】]+】', '', clean_text)

                # Strategia 1 (principale): Estrai frasi complete con contenuto sostanziale
                sentences = re.split(r'[。！？]', clean_text)
                meaningful = [
                    s.strip() for s in sentences
                    if 20 <= len(s.strip()) <= 150
                    and not re.match(r'^[\s\W，,；;：:、]+', s.strip())
                    and not s.strip().startswith(('{', '问题'))
                ]
                meaningful.sort(key=len, reverse=True)
                key_quotes = [s + "。" for s in meaningful[:3]]

                # Strategia 2 (supplementare): Testo lungo all'interno di virgolette cinesi correttamente accoppiate
                if not key_quotes:
                    paired = re.findall(r'\u201c([^\u201c\u201d]{15,100})\u201d', clean_text)
                    paired += re.findall(r'\u300c([^\u300c\u300d]{15,100})\u300d', clean_text)
                    key_quotes = [q for q in paired if not re.match(r'^[，,；;：:、]', q)][:3]

                interview = AgentInterview(
                    agent_name=agent_name,
                    agent_role=agent_role,
                    agent_bio=agent_bio[:1000],  # Limite bio ampliato
                    question=combined_prompt,
                    response=response_text,
                    key_quotes=key_quotes[:5]
                )
                result.interviews.append(interview)

            result.interviewed_count = len(result.interviews)

        except ValueError as e:
            # Ambiente di simulazione non in esecuzione
            logger.warning(f"Chiamata API intervista fallita (ambiente non in esecuzione?): {e}")
            result.summary = f"Intervista fallita: {str(e)}. L'ambiente di simulazione potrebbe essere chiuso, assicurarsi che l'ambiente OASIS sia in esecuzione."
            return result
        except Exception as e:
            logger.error(f"Eccezione nella chiamata API intervista: {e}")
            import traceback
            logger.error(traceback.format_exc())
            result.summary = f"Errore durante il processo di intervista: {str(e)}"
            return result

        # Passo 6: Generazione del riepilogo dell'intervista
        if result.interviews:
            result.summary = self._generate_interview_summary(
                interviews=result.interviews,
                interview_requirement=interview_requirement
            )

        logger.info(f"InterviewAgents completato: intervistati {result.interviewed_count} Agent (entrambe le piattaforme)")
        return result

    @staticmethod
    def _clean_tool_call_response(response: str) -> str:
        """Pulisce i wrapper JSON di chiamata strumenti dalla risposta dell'Agent, estraendo il contenuto effettivo"""
        if not response or not response.strip().startswith('{'):
            return response
        text = response.strip()
        if 'tool_name' not in text[:80]:
            return response
        import re as _re
        try:
            data = json.loads(text)
            if isinstance(data, dict) and 'arguments' in data:
                for key in ('content', 'text', 'body', 'message', 'reply'):
                    if key in data['arguments']:
                        return str(data['arguments'][key])
        except (json.JSONDecodeError, KeyError, TypeError):
            match = _re.search(r'"content"\s*:\s*"((?:[^"\\]|\\.)*)"', text)
            if match:
                return match.group(1).replace('\\n', '\n').replace('\\"', '"')
        return response

    def _load_agent_profiles(self, simulation_id: str) -> List[Dict[str, Any]]:
        """Carica i file dei profili degli Agent della simulazione"""
        import os
        import csv

        # Costruzione del percorso del file dei profili
        sim_dir = os.path.join(
            os.path.dirname(__file__),
            f'../../uploads/simulations/{simulation_id}'
        )

        profiles = []

        # Prova prima a leggere il formato JSON Reddit
        reddit_profile_path = os.path.join(sim_dir, "reddit_profiles.json")
        if os.path.exists(reddit_profile_path):
            try:
                with open(reddit_profile_path, 'r', encoding='utf-8') as f:
                    profiles = json.load(f)
                logger.info(f"Caricati {len(profiles)} profili da reddit_profiles.json")
                return profiles
            except Exception as e:
                logger.warning(f"Lettura reddit_profiles.json fallita: {e}")

        # Prova a leggere il formato CSV Twitter
        twitter_profile_path = os.path.join(sim_dir, "twitter_profiles.csv")
        if os.path.exists(twitter_profile_path):
            try:
                with open(twitter_profile_path, 'r', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        # Conversione dal formato CSV al formato unificato
                        profiles.append({
                            "realname": row.get("name", ""),
                            "username": row.get("username", ""),
                            "bio": row.get("description", ""),
                            "persona": row.get("user_char", ""),
                            "profession": "Sconosciuto"
                        })
                logger.info(f"Caricati {len(profiles)} profili da twitter_profiles.csv")
                return profiles
            except Exception as e:
                logger.warning(f"Lettura twitter_profiles.csv fallita: {e}")

        return profiles

    def _select_agents_for_interview(
        self,
        profiles: List[Dict[str, Any]],
        interview_requirement: str,
        simulation_requirement: str,
        max_agents: int
    ) -> tuple:
        """
        Utilizza il LLM per selezionare gli Agent da intervistare

        Returns:
            tuple: (selected_agents, selected_indices, reasoning)
                - selected_agents: Lista delle informazioni complete degli Agent selezionati
                - selected_indices: Lista degli indici degli Agent selezionati (per la chiamata API)
                - reasoning: Motivazione della selezione
        """

        # Costruzione della lista riepilogativa degli Agent
        agent_summaries = []
        for i, profile in enumerate(profiles):
            summary = {
                "index": i,
                "name": profile.get("realname", profile.get("username", f"Agent_{i}")),
                "profession": profile.get("profession", "Sconosciuto"),
                "bio": profile.get("bio", "")[:200],
                "interested_topics": profile.get("interested_topics", [])
            }
            agent_summaries.append(summary)

        system_prompt = """Sei un esperto professionista nella pianificazione di interviste. Il tuo compito è selezionare, dalla lista degli Agent simulati, i soggetti più adatti all'intervista in base ai requisiti.

Criteri di selezione:
1. L'identità/professione dell'Agent è pertinente al tema dell'intervista
2. L'Agent potrebbe avere un punto di vista unico o di valore
3. Selezionare prospettive diversificate (es.: a favore, contrari, neutrali, professionisti, ecc.)
4. Dare priorità ai ruoli direttamente correlati all'evento

Restituisci in formato JSON:
{
    "selected_indices": [lista degli indici degli Agent selezionati],
    "reasoning": "spiegazione della motivazione della selezione"
}"""

        user_prompt = f"""Requisiti dell'intervista:
{interview_requirement}

Contesto della simulazione:
{simulation_requirement if simulation_requirement else "Non fornito"}

Lista degli Agent selezionabili (totale {len(agent_summaries)}):
{json.dumps(agent_summaries, ensure_ascii=False, indent=2)}

Per favore seleziona al massimo {max_agents} Agent più adatti all'intervista e spiega la motivazione della selezione."""

        try:
            response = self.llm.chat_json(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.3
            )

            selected_indices = response.get("selected_indices", [])[:max_agents]
            reasoning = response.get("reasoning", "Selezione automatica basata sulla pertinenza")

            # Ottieni le informazioni complete degli Agent selezionati
            selected_agents = []
            valid_indices = []
            for idx in selected_indices:
                if 0 <= idx < len(profiles):
                    selected_agents.append(profiles[idx])
                    valid_indices.append(idx)

            return selected_agents, valid_indices, reasoning

        except Exception as e:
            logger.warning(f"Selezione Agent tramite LLM fallita, utilizzo selezione predefinita: {e}")
            # Degradazione: seleziona i primi N
            selected = profiles[:max_agents]
            indices = list(range(min(max_agents, len(profiles))))
            return selected, indices, "Utilizzo della strategia di selezione predefinita"

    def _generate_interview_questions(
        self,
        interview_requirement: str,
        simulation_requirement: str,
        selected_agents: List[Dict[str, Any]]
    ) -> List[str]:
        """Utilizza il LLM per generare le domande dell'intervista"""

        agent_roles = [a.get("profession", "Sconosciuto") for a in selected_agents]

        system_prompt = """Sei un giornalista/intervistatore professionista. Genera 3-5 domande approfondite per l'intervista in base ai requisiti.

Requisiti per le domande:
1. Domande aperte che incoraggiano risposte dettagliate
2. Domande che possono avere risposte diverse per ruoli diversi
3. Copertura di più dimensioni: fatti, opinioni, sentimenti, ecc.
4. Linguaggio naturale, come in un'intervista reale
5. Ogni domanda entro 50 caratteri, concisa e chiara
6. Domande dirette, senza descrizioni di contesto o prefissi

Restituisci in formato JSON: {"questions": ["domanda 1", "domanda 2", ...]}"""

        user_prompt = f"""Requisiti dell'intervista: {interview_requirement}

Contesto della simulazione: {simulation_requirement if simulation_requirement else "Non fornito"}

Ruoli degli intervistati: {', '.join(agent_roles)}

Per favore genera 3-5 domande per l'intervista."""

        try:
            response = self.llm.chat_json(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.5
            )

            return response.get("questions", [f"Riguardo a {interview_requirement}, qual è la sua opinione?"])

        except Exception as e:
            logger.warning(f"Generazione domande intervista fallita: {e}")
            return [
                f"Riguardo a {interview_requirement}, qual è il suo punto di vista?",
                "Che impatto ha questa questione su di lei o sul gruppo che rappresenta?",
                "Come pensa si dovrebbe risolvere o migliorare questo problema?"
            ]

    def _generate_interview_summary(
        self,
        interviews: List[AgentInterview],
        interview_requirement: str
    ) -> str:
        """Genera il riepilogo dell'intervista"""

        if not interviews:
            return "Nessuna intervista completata"

        # Raccolta di tutti i contenuti dell'intervista
        interview_texts = []
        for interview in interviews:
            interview_texts.append(f"[{interview.agent_name} ({interview.agent_role})]\n{interview.response[:500]}")

        system_prompt = """Sei un redattore giornalistico professionista. Genera un riepilogo dell'intervista basato sulle risposte di più intervistati.

Requisiti del riepilogo:
1. Sintetizza i punti di vista principali di ogni parte
2. Evidenzia i punti di consenso e di disaccordo
3. Metti in risalto le citazioni di valore
4. Obiettivo e neutrale, senza favorire nessuna parte
5. Entro 1000 caratteri

Vincoli di formato (da rispettare obbligatoriamente):
- Utilizza paragrafi di testo semplice, separati da righe vuote
- Non utilizzare titoli Markdown (come #, ##, ###)
- Non utilizzare linee divisorie (come ---, ***)
- Per citare le parole originali degli intervistati utilizza le virgolette
- Puoi utilizzare **grassetto** per evidenziare parole chiave, ma non utilizzare altra sintassi Markdown"""

        user_prompt = f"""Tema dell'intervista: {interview_requirement}

Contenuto dell'intervista:
{"".join(interview_texts)}

Per favore genera il riepilogo dell'intervista."""

        try:
            summary = self.llm.chat(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.3,
                max_tokens=800
            )
            return summary

        except Exception as e:
            logger.warning(f"Generazione riepilogo intervista fallita: {e}")
            # Degradazione: concatenazione semplice
            return f"Intervistati {len(interviews)} soggetti, tra cui: " + ", ".join([i.agent_name for i in interviews])
