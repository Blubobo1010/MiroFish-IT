"""
Generatore intelligente di configurazione simulazione
Utilizza LLM per generare automaticamente parametri dettagliati di simulazione in base a requisiti, contenuto documenti e informazioni del grafo
Implementa automazione completa senza necessita' di impostazione manuale dei parametri

Adotta strategia di generazione a fasi, evitando che contenuti troppo lunghi generati in una volta causino fallimenti:
1. Generare configurazione temporale
2. Generare configurazione eventi
3. Generare configurazione Agent in lotti
4. Generare configurazione piattaforma
"""

import json
import math
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass, field, asdict
from datetime import datetime

from openai import OpenAI

from ..config import Config
from ..utils.logger import get_logger
from .zep_entity_reader import EntityNode, ZepEntityReader

logger = get_logger('mirofish.simulation_config')

# Configurazione fuso orario cinese (ora di Pechino)
CHINA_TIMEZONE_CONFIG = {
    # Fascia notturna profonda (quasi nessuna attivita')
    "dead_hours": [0, 1, 2, 3, 4, 5],
    # Fascia mattutina (risveglio graduale)
    "morning_hours": [6, 7, 8],
    # Fascia lavorativa
    "work_hours": [9, 10, 11, 12, 13, 14, 15, 16, 17, 18],
    # Picco serale (massima attivita')
    "peak_hours": [19, 20, 21, 22],
    # Fascia notturna (attivita' in calo)
    "night_hours": [23],
    # Coefficienti di attivita'
    "activity_multipliers": {
        "dead": 0.05,      # Quasi nessuno nelle ore piccole
        "morning": 0.4,    # Mattina, attivita' graduale
        "work": 0.7,       # Fascia lavorativa, media
        "peak": 1.5,       # Picco serale
        "night": 0.5       # Notte tarda, in calo
    }
}


@dataclass
class AgentActivityConfig:
    """Configurazione attivita' di un singolo Agent"""
    agent_id: int
    entity_uuid: str
    entity_name: str
    entity_type: str

    # Configurazione livello di attivita' (0.0-1.0)
    activity_level: float = 0.5  # Livello di attivita' complessivo

    # Frequenza messaggi (numero previsto di messaggi per ora)
    posts_per_hour: float = 1.0
    comments_per_hour: float = 2.0

    # Fasce orarie attive (formato 24 ore, 0-23)
    active_hours: List[int] = field(default_factory=lambda: list(range(8, 23)))

    # Velocita' di risposta (ritardo di reazione agli eventi caldi, unita': minuti simulati)
    response_delay_min: int = 5
    response_delay_max: int = 60

    # Tendenza sentimentale (da -1.0 a 1.0, negativo a positivo)
    sentiment_bias: float = 0.0

    # Posizione (atteggiamento verso argomenti specifici)
    stance: str = "neutral"  # supportive, opposing, neutral, observer

    # Peso di influenza (determina la probabilita' che i messaggi vengano visti da altri Agent)
    influence_weight: float = 1.0


@dataclass  
class TimeSimulationConfig:
    """Configurazione temporale simulazione (basata sulle abitudini cinesi)"""
    # Durata totale simulazione (ore simulate)
    total_simulation_hours: int = 72  # Default 72 ore simulate (3 giorni)

    # Tempo rappresentato per turno (minuti simulati) - default 60 minuti (1 ora), velocita' accelerata
    minutes_per_round: int = 60

    # Intervallo numero Agent attivati per ora
    agents_per_hour_min: int = 5
    agents_per_hour_max: int = 20

    # Fascia di picco (19-22, orario piu' attivo per i cinesi)
    peak_hours: List[int] = field(default_factory=lambda: [19, 20, 21, 22])
    peak_activity_multiplier: float = 1.5

    # Fascia di bassa attivita' (0-5, quasi nessuna attivita')
    off_peak_hours: List[int] = field(default_factory=lambda: [0, 1, 2, 3, 4, 5])
    off_peak_activity_multiplier: float = 0.05  # Attivita' estremamente bassa nelle ore piccole

    # Fascia mattutina
    morning_hours: List[int] = field(default_factory=lambda: [6, 7, 8])
    morning_activity_multiplier: float = 0.4

    # Fascia lavorativa
    work_hours: List[int] = field(default_factory=lambda: [9, 10, 11, 12, 13, 14, 15, 16, 17, 18])
    work_activity_multiplier: float = 0.7


@dataclass
class EventConfig:
    """Configurazione eventi"""
    # Eventi iniziali (eventi attivati all'inizio della simulazione)
    initial_posts: List[Dict[str, Any]] = field(default_factory=list)

    # Eventi programmati (eventi attivati a tempi specifici)
    scheduled_events: List[Dict[str, Any]] = field(default_factory=list)

    # Parole chiave argomenti di tendenza
    hot_topics: List[str] = field(default_factory=list)

    # Direzione narrativa dell'opinione pubblica
    narrative_direction: str = ""


@dataclass
class PlatformConfig:
    """Configurazione specifica della piattaforma"""
    platform: str  # twitter or reddit

    # Pesi algoritmo di raccomandazione
    recency_weight: float = 0.4  # Freschezza temporale
    popularity_weight: float = 0.3  # Popolarita'
    relevance_weight: float = 0.3  # Rilevanza

    # Soglia di viralita' (numero di interazioni per attivare la diffusione)
    viral_threshold: int = 10

    # Intensita' effetto camera d'eco (grado di aggregazione opinioni simili)
    echo_chamber_strength: float = 0.5


@dataclass
class SimulationParameters:
    """Configurazione completa dei parametri di simulazione"""
    # Informazioni base
    simulation_id: str
    project_id: str
    graph_id: str
    simulation_requirement: str
    
    # Configurazione temporale
    time_config: TimeSimulationConfig = field(default_factory=TimeSimulationConfig)

    # Lista configurazione Agent
    agent_configs: List[AgentActivityConfig] = field(default_factory=list)

    # Configurazione eventi
    event_config: EventConfig = field(default_factory=EventConfig)

    # Configurazione piattaforma
    twitter_config: Optional[PlatformConfig] = None
    reddit_config: Optional[PlatformConfig] = None
    
    # Configurazione LLM
    llm_model: str = ""
    llm_base_url: str = ""
    
    # Metadati generazione
    generated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    generation_reasoning: str = ""  # Spiegazione ragionamento LLM
    
    def to_dict(self) -> Dict[str, Any]:
        """Converti in dizionario"""
        time_dict = asdict(self.time_config)
        return {
            "simulation_id": self.simulation_id,
            "project_id": self.project_id,
            "graph_id": self.graph_id,
            "simulation_requirement": self.simulation_requirement,
            "time_config": time_dict,
            "agent_configs": [asdict(a) for a in self.agent_configs],
            "event_config": asdict(self.event_config),
            "twitter_config": asdict(self.twitter_config) if self.twitter_config else None,
            "reddit_config": asdict(self.reddit_config) if self.reddit_config else None,
            "llm_model": self.llm_model,
            "llm_base_url": self.llm_base_url,
            "generated_at": self.generated_at,
            "generation_reasoning": self.generation_reasoning,
        }
    
    def to_json(self, indent: int = 2) -> str:
        """Converti in stringa JSON"""
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)


class SimulationConfigGenerator:
    """
    Generatore intelligente di configurazione simulazione

    Utilizza LLM per analizzare requisiti simulazione, contenuto documenti, informazioni entita' del grafo,
    generando automaticamente la configurazione ottimale dei parametri di simulazione

    Adotta strategia di generazione a fasi:
    1. Generare configurazione temporale e configurazione eventi (leggera)
    2. Generare configurazione Agent in lotti (10-20 per lotto)
    3. Generare configurazione piattaforma
    """

    # Numero massimo caratteri contesto
    MAX_CONTEXT_LENGTH = 50000
    # Numero di Agent per lotto
    AGENTS_PER_BATCH = 15

    # Lunghezza troncamento contesto per ogni fase (caratteri)
    TIME_CONFIG_CONTEXT_LENGTH = 10000   # Configurazione temporale
    EVENT_CONFIG_CONTEXT_LENGTH = 8000   # Configurazione eventi
    ENTITY_SUMMARY_LENGTH = 300          # Riepilogo entita'
    AGENT_SUMMARY_LENGTH = 300           # Riepilogo entita' nella configurazione Agent
    ENTITIES_PER_TYPE_DISPLAY = 20       # Numero entita' visualizzate per tipo
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model_name: Optional[str] = None
    ):
        self.api_key = api_key or Config.LLM_API_KEY
        self.base_url = base_url or Config.LLM_BASE_URL
        self.model_name = model_name or Config.LLM_MODEL_NAME
        
        if not self.api_key:
            raise ValueError("LLM_API_KEY non configurata")
        
        self.client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url
        )
    
    def generate_config(
        self,
        simulation_id: str,
        project_id: str,
        graph_id: str,
        simulation_requirement: str,
        document_text: str,
        entities: List[EntityNode],
        enable_twitter: bool = True,
        enable_reddit: bool = True,
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
    ) -> SimulationParameters:
        """
        Genera intelligentemente la configurazione completa della simulazione (generazione a fasi)

        Args:
            simulation_id: ID simulazione
            project_id: ID progetto
            graph_id: ID grafo
            simulation_requirement: Descrizione requisiti simulazione
            document_text: Contenuto documento originale
            entities: Lista entita' filtrate
            enable_twitter: Abilitare Twitter
            enable_reddit: Abilitare Reddit
            progress_callback: Funzione callback progresso(current_step, total_steps, message)

        Returns:
            SimulationParameters: Parametri di simulazione completi
        """
        logger.info(f"Inizio generazione intelligente configurazione simulazione: simulation_id={simulation_id}, num_entita={len(entities)}")
        
        # Calcola numero totale di passi
        num_batches = math.ceil(len(entities) / self.AGENTS_PER_BATCH)
        total_steps = 3 + num_batches  # Configurazione temporale + configurazione eventi + N lotti Agent + configurazione piattaforma
        current_step = 0
        
        def report_progress(step: int, message: str):
            nonlocal current_step
            current_step = step
            if progress_callback:
                progress_callback(step, total_steps, message)
            logger.info(f"[{step}/{total_steps}] {message}")
        
        # 1. Costruisci informazioni di contesto base
        context = self._build_context(
            simulation_requirement=simulation_requirement,
            document_text=document_text,
            entities=entities
        )
        
        reasoning_parts = []
        
        # ========== Passo 1: Generazione configurazione temporale ==========
        report_progress(1, "Generazione configurazione temporale...")
        num_entities = len(entities)
        time_config_result = self._generate_time_config(context, num_entities)
        time_config = self._parse_time_config(time_config_result, num_entities)
        reasoning_parts.append(f"Configurazione temporale: {time_config_result.get('reasoning', 'successo')}")

        # ========== Passo 2: Generazione configurazione eventi ==========
        report_progress(2, "Generazione configurazione eventi e argomenti di tendenza...")
        event_config_result = self._generate_event_config(context, simulation_requirement, entities)
        event_config = self._parse_event_config(event_config_result)
        reasoning_parts.append(f"Configurazione eventi: {event_config_result.get('reasoning', 'successo')}")

        # ========== Passi 3-N: Generazione configurazione Agent in lotti ==========
        all_agent_configs = []
        for batch_idx in range(num_batches):
            start_idx = batch_idx * self.AGENTS_PER_BATCH
            end_idx = min(start_idx + self.AGENTS_PER_BATCH, len(entities))
            batch_entities = entities[start_idx:end_idx]
            
            report_progress(
                3 + batch_idx,
                f"Generazione configurazione Agent ({start_idx + 1}-{end_idx}/{len(entities)})..."
            )
            
            batch_configs = self._generate_agent_configs_batch(
                context=context,
                entities=batch_entities,
                start_idx=start_idx,
                simulation_requirement=simulation_requirement
            )
            all_agent_configs.extend(batch_configs)
        
        reasoning_parts.append(f"Configurazione Agent: generati con successo {len(all_agent_configs)}")

        # ========== Assegnazione Agent pubblicatore ai post iniziali ==========
        logger.info("Assegnazione Agent pubblicatore appropriato ai post iniziali...")
        event_config = self._assign_initial_post_agents(event_config, all_agent_configs)
        assigned_count = len([p for p in event_config.initial_posts if p.get("poster_agent_id") is not None])
        reasoning_parts.append(f"Assegnazione post iniziali: {assigned_count} post assegnati a pubblicatori")

        # ========== Ultimo passo: Generazione configurazione piattaforma ==========
        report_progress(total_steps, "Generazione configurazione piattaforma...")
        twitter_config = None
        reddit_config = None
        
        if enable_twitter:
            twitter_config = PlatformConfig(
                platform="twitter",
                recency_weight=0.4,
                popularity_weight=0.3,
                relevance_weight=0.3,
                viral_threshold=10,
                echo_chamber_strength=0.5
            )
        
        if enable_reddit:
            reddit_config = PlatformConfig(
                platform="reddit",
                recency_weight=0.3,
                popularity_weight=0.4,
                relevance_weight=0.3,
                viral_threshold=15,
                echo_chamber_strength=0.6
            )
        
        # Costruisci parametri finali
        params = SimulationParameters(
            simulation_id=simulation_id,
            project_id=project_id,
            graph_id=graph_id,
            simulation_requirement=simulation_requirement,
            time_config=time_config,
            agent_configs=all_agent_configs,
            event_config=event_config,
            twitter_config=twitter_config,
            reddit_config=reddit_config,
            llm_model=self.model_name,
            llm_base_url=self.base_url,
            generation_reasoning=" | ".join(reasoning_parts)
        )
        
        logger.info(f"Generazione configurazione simulazione completata: {len(params.agent_configs)} configurazioni Agent")
        
        return params
    
    def _build_context(
        self,
        simulation_requirement: str,
        document_text: str,
        entities: List[EntityNode]
    ) -> str:
        """Costruisci contesto LLM, troncato alla lunghezza massima"""

        # Riepilogo entita'
        entity_summary = self._summarize_entities(entities)
        
        # Costruisci contesto
        context_parts = [
            f"## Requisiti simulazione\n{simulation_requirement}",
            f"\n## Informazioni entita' ({len(entities)})\n{entity_summary}",
        ]

        current_length = sum(len(p) for p in context_parts)
        remaining_length = self.MAX_CONTEXT_LENGTH - current_length - 500  # Margine di 500 caratteri
        
        if remaining_length > 0 and document_text:
            doc_text = document_text[:remaining_length]
            if len(document_text) > remaining_length:
                doc_text += "\n...(documento troncato)"
            context_parts.append(f"\n## Contenuto documento originale\n{doc_text}")
        
        return "\n".join(context_parts)
    
    def _summarize_entities(self, entities: List[EntityNode]) -> str:
        """Genera riepilogo entita'"""
        lines = []
        
        # Raggruppa per tipo
        by_type: Dict[str, List[EntityNode]] = {}
        for e in entities:
            t = e.get_entity_type() or "Unknown"
            if t not in by_type:
                by_type[t] = []
            by_type[t].append(e)
        
        for entity_type, type_entities in by_type.items():
            lines.append(f"\n### {entity_type} ({len(type_entities)})")
            # Utilizza quantita' di visualizzazione e lunghezza riepilogo configurate
            display_count = self.ENTITIES_PER_TYPE_DISPLAY
            summary_len = self.ENTITY_SUMMARY_LENGTH
            for e in type_entities[:display_count]:
                summary_preview = (e.summary[:summary_len] + "...") if len(e.summary) > summary_len else e.summary
                lines.append(f"- {e.name}: {summary_preview}")
            if len(type_entities) > display_count:
                lines.append(f"  ... e altri {len(type_entities) - display_count}")
        
        return "\n".join(lines)
    
    def _call_llm_with_retry(self, prompt: str, system_prompt: str) -> Dict[str, Any]:
        """Chiamata LLM con retry, include logica di riparazione JSON"""
        import re
        
        max_attempts = 3
        last_error = None
        
        for attempt in range(max_attempts):
            try:
                response = self.client.chat.completions.create(
                    model=self.model_name,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": prompt}
                    ],
                    response_format={"type": "json_object"},
                    temperature=0.7 - (attempt * 0.1)  # Abbassa la temperatura ad ogni retry
                    # Non impostare max_tokens, lasciare libero LLM
                )
                
                content = response.choices[0].message.content
                finish_reason = response.choices[0].finish_reason
                
                # Verifica se troncato
                if finish_reason == 'length':
                    logger.warning(f"Output LLM troncato (attempt {attempt+1})")
                    content = self._fix_truncated_json(content)
                
                # Tentativo di parsing JSON
                try:
                    return json.loads(content)
                except json.JSONDecodeError as e:
                    logger.warning(f"Parsing JSON fallito (attempt {attempt+1}): {str(e)[:80]}")

                    # Tentativo di riparazione JSON
                    fixed = self._try_fix_config_json(content)
                    if fixed:
                        return fixed
                    
                    last_error = e
                    
            except Exception as e:
                logger.warning(f"Chiamata LLM fallita (attempt {attempt+1}): {str(e)[:80]}")
                last_error = e
                import time
                time.sleep(2 * (attempt + 1))
        
        raise last_error or Exception("Chiamata LLM fallita")
    
    def _fix_truncated_json(self, content: str) -> str:
        """Ripara JSON troncato"""
        content = content.strip()
        
        # Calcola parentesi non chiuse
        open_braces = content.count('{') - content.count('}')
        open_brackets = content.count('[') - content.count(']')
        
        # Verifica stringhe non chiuse
        if content and content[-1] not in '",}]':
            content += '"'
        
        # Chiudi parentesi
        content += ']' * open_brackets
        content += '}' * open_braces
        
        return content
    
    def _try_fix_config_json(self, content: str) -> Optional[Dict[str, Any]]:
        """Tentativo di riparazione JSON configurazione"""
        import re
        
        # Ripara caso troncato
        content = self._fix_truncated_json(content)
        
        # Estrai parte JSON
        json_match = re.search(r'\{[\s\S]*\}', content)
        if json_match:
            json_str = json_match.group()
            
            # Rimuovi caratteri di a capo nelle stringhe
            def fix_string(match):
                s = match.group(0)
                s = s.replace('\n', ' ').replace('\r', ' ')
                s = re.sub(r'\s+', ' ', s)
                return s
            
            json_str = re.sub(r'"[^"\\]*(?:\\.[^"\\]*)*"', fix_string, json_str)
            
            try:
                return json.loads(json_str)
            except:
                # Tentativo di rimuovere tutti i caratteri di controllo
                json_str = re.sub(r'[\x00-\x1f\x7f-\x9f]', ' ', json_str)
                json_str = re.sub(r'\s+', ' ', json_str)
                try:
                    return json.loads(json_str)
                except:
                    pass
        
        return None
    
    def _generate_time_config(self, context: str, num_entities: int) -> Dict[str, Any]:
        """Genera configurazione temporale"""
        # Utilizza lunghezza troncamento contesto configurata
        context_truncated = context[:self.TIME_CONFIG_CONTEXT_LENGTH]
        
        # Calcola valore massimo consentito (90% del numero agent)
        max_agents_allowed = max(1, int(num_entities * 0.9))
        
        prompt = f"""In base ai seguenti requisiti di simulazione, genera la configurazione temporale della simulazione.

{context_truncated}

## Compito
Genera il JSON della configurazione temporale.

### Principi base (solo come riferimento, da adattare in base all'evento specifico e al gruppo di partecipanti):
- Il gruppo utenti e' cinese, deve rispettare le abitudini dell'ora di Pechino
- Ore 0-5: quasi nessuna attivita' (coefficiente attivita' 0.05)
- Ore 6-8: attivita' graduale (coefficiente attivita' 0.4)
- Ore lavorative 9-18: attivita' media (coefficiente attivita' 0.7)
- Ore serali 19-22: periodo di picco (coefficiente attivita' 1.5)
- Dopo le 23: attivita' in calo (coefficiente attivita' 0.5)
- Regola generale: bassa attivita' nelle ore piccole, aumento mattutino, media nelle ore lavorative, picco serale
- **Importante**: i valori di esempio seguenti sono solo riferimenti, devi adattare le fasce orarie in base alla natura dell'evento e alle caratteristiche dei partecipanti
  - Esempio: il picco degli studenti potrebbe essere 21-23; i media attivi tutto il giorno; le istituzioni ufficiali solo in orario lavorativo
  - Esempio: argomenti caldi improvvisi potrebbero causare discussioni anche di notte, off_peak_hours puo' essere accorciato

### Formato JSON di ritorno (senza markdown)

Esempio:
{{
    "total_simulation_hours": 72,
    "minutes_per_round": 60,
    "agents_per_hour_min": 5,
    "agents_per_hour_max": 50,
    "peak_hours": [19, 20, 21, 22],
    "off_peak_hours": [0, 1, 2, 3, 4, 5],
    "morning_hours": [6, 7, 8],
    "work_hours": [9, 10, 11, 12, 13, 14, 15, 16, 17, 18],
    "reasoning": "Spiegazione configurazione temporale per questo evento"
}}

Descrizione campi:
- total_simulation_hours (int): Durata totale simulazione, 24-168 ore, breve per eventi improvvisi, lungo per argomenti persistenti
- minutes_per_round (int): Durata per turno, 30-120 minuti, consigliato 60 minuti
- agents_per_hour_min (int): Numero minimo Agent attivati per ora (intervallo: 1-{max_agents_allowed})
- agents_per_hour_max (int): Numero massimo Agent attivati per ora (intervallo: 1-{max_agents_allowed})
- peak_hours (array int): Fascia di picco, da adattare al gruppo di partecipanti dell'evento
- off_peak_hours (array int): Fascia di bassa attivita', generalmente notte/alba
- morning_hours (array int): Fascia mattutina
- work_hours (array int): Fascia lavorativa
- reasoning (string): Breve spiegazione del perche' di questa configurazione"""

        system_prompt = "Sei un esperto di simulazione social media. Restituisci formato JSON puro, la configurazione temporale deve rispettare le abitudini cinesi."
        
        try:
            return self._call_llm_with_retry(prompt, system_prompt)
        except Exception as e:
            logger.warning(f"Generazione LLM configurazione temporale fallita: {e}, utilizzo configurazione predefinita")
            return self._get_default_time_config(num_entities)
    
    def _get_default_time_config(self, num_entities: int) -> Dict[str, Any]:
        """Ottieni configurazione temporale predefinita (abitudini cinesi)"""
        return {
            "total_simulation_hours": 72,
            "minutes_per_round": 60,  # 1 ora per turno, velocità temporale accelerata
            "agents_per_hour_min": max(1, num_entities // 15),
            "agents_per_hour_max": max(5, num_entities // 5),
            "peak_hours": [19, 20, 21, 22],
            "off_peak_hours": [0, 1, 2, 3, 4, 5],
            "morning_hours": [6, 7, 8],
            "work_hours": [9, 10, 11, 12, 13, 14, 15, 16, 17, 18],
            "reasoning": "Configurazione predefinita abitudini cinesi (1 ora per turno)"
        }
    
    def _parse_time_config(self, result: Dict[str, Any], num_entities: int) -> TimeSimulationConfig:
        """Analizza risultato configurazione temporale, e verifica che agents_per_hour non superi il numero totale di agent"""
        # Ottieni valori originali
        agents_per_hour_min = result.get("agents_per_hour_min", max(1, num_entities // 15))
        agents_per_hour_max = result.get("agents_per_hour_max", max(5, num_entities // 5))
        
        # Verifica e correggi: assicurarsi che non superi il numero totale di agent
        if agents_per_hour_min > num_entities:
            logger.warning(f"agents_per_hour_min ({agents_per_hour_min}) supera il numero totale di Agent ({num_entities}), corretto")
            agents_per_hour_min = max(1, num_entities // 10)
        
        if agents_per_hour_max > num_entities:
            logger.warning(f"agents_per_hour_max ({agents_per_hour_max}) supera il numero totale di Agent ({num_entities}), corretto")
            agents_per_hour_max = max(agents_per_hour_min + 1, num_entities // 2)
        
        # Assicurarsi che min < max
        if agents_per_hour_min >= agents_per_hour_max:
            agents_per_hour_min = max(1, agents_per_hour_max // 2)
            logger.warning(f"agents_per_hour_min >= max, corretto a {agents_per_hour_min}")
        
        return TimeSimulationConfig(
            total_simulation_hours=result.get("total_simulation_hours", 72),
            minutes_per_round=result.get("minutes_per_round", 60),  # Default 1 ora per turno
            agents_per_hour_min=agents_per_hour_min,
            agents_per_hour_max=agents_per_hour_max,
            peak_hours=result.get("peak_hours", [19, 20, 21, 22]),
            off_peak_hours=result.get("off_peak_hours", [0, 1, 2, 3, 4, 5]),
            off_peak_activity_multiplier=0.05,  # Quasi nessuno nelle ore piccole
            morning_hours=result.get("morning_hours", [6, 7, 8]),
            morning_activity_multiplier=0.4,
            work_hours=result.get("work_hours", list(range(9, 19))),
            work_activity_multiplier=0.7,
            peak_activity_multiplier=1.5
        )
    
    def _generate_event_config(
        self, 
        context: str, 
        simulation_requirement: str,
        entities: List[EntityNode]
    ) -> Dict[str, Any]:
        """Genera configurazione eventi"""

        # Ottieni lista tipi entita' disponibili, come riferimento per LLM
        entity_types_available = list(set(
            e.get_entity_type() or "Unknown" for e in entities
        ))
        
        # Elenca nomi entita' rappresentativi per ogni tipo
        type_examples = {}
        for e in entities:
            etype = e.get_entity_type() or "Unknown"
            if etype not in type_examples:
                type_examples[etype] = []
            if len(type_examples[etype]) < 3:
                type_examples[etype].append(e.name)
        
        type_info = "\n".join([
            f"- {t}: {', '.join(examples)}" 
            for t, examples in type_examples.items()
        ])
        
        # Utilizza lunghezza troncamento contesto configurata
        context_truncated = context[:self.EVENT_CONFIG_CONTEXT_LENGTH]

        prompt = f"""In base ai seguenti requisiti di simulazione, genera la configurazione eventi.

Requisiti simulazione: {simulation_requirement}

{context_truncated}

## Tipi entita' disponibili ed esempi
{type_info}

## Compito
Genera il JSON della configurazione eventi:
- Estrai parole chiave degli argomenti di tendenza
- Descrivi la direzione di sviluppo dell'opinione pubblica
- Progetta il contenuto dei post iniziali, **ogni post deve specificare poster_type (tipo di pubblicatore)**

**Importante**: poster_type deve essere selezionato dai "tipi entita' disponibili" sopra, cosi' i post iniziali possono essere assegnati all'Agent appropriato per la pubblicazione.
Esempio: dichiarazioni ufficiali dovrebbero essere pubblicate dal tipo Official/University, notizie da MediaOutlet, opinioni degli studenti da Student.

Formato JSON di ritorno (senza markdown):
{{
    "hot_topics": ["parola_chiave1", "parola_chiave2", ...],
    "narrative_direction": "<descrizione direzione opinione pubblica>",
    "initial_posts": [
        {{"content": "contenuto post", "poster_type": "tipo entita' (deve essere selezionato dai tipi disponibili)"}},
        ...
    ],
    "reasoning": "<breve spiegazione>"
}}"""

        system_prompt = "Sei un esperto di analisi dell'opinione pubblica. Restituisci formato JSON puro. Nota che poster_type deve corrispondere esattamente ai tipi entita' disponibili."
        
        try:
            return self._call_llm_with_retry(prompt, system_prompt)
        except Exception as e:
            logger.warning(f"Generazione LLM configurazione eventi fallita: {e}, utilizzo configurazione predefinita")
            return {
                "hot_topics": [],
                "narrative_direction": "",
                "initial_posts": [],
                "reasoning": "Configurazione predefinita"
            }
    
    def _parse_event_config(self, result: Dict[str, Any]) -> EventConfig:
        """Analizza risultato configurazione eventi"""
        return EventConfig(
            initial_posts=result.get("initial_posts", []),
            scheduled_events=[],
            hot_topics=result.get("hot_topics", []),
            narrative_direction=result.get("narrative_direction", "")
        )
    
    def _assign_initial_post_agents(
        self,
        event_config: EventConfig,
        agent_configs: List[AgentActivityConfig]
    ) -> EventConfig:
        """
        Assegna l'Agent pubblicatore appropriato ai post iniziali

        Abbina l'agent_id piu' adatto in base al poster_type di ogni post
        """
        if not event_config.initial_posts:
            return event_config
        
        # Costruisci indice agent per tipo entita'
        agents_by_type: Dict[str, List[AgentActivityConfig]] = {}
        for agent in agent_configs:
            etype = agent.entity_type.lower()
            if etype not in agents_by_type:
                agents_by_type[etype] = []
            agents_by_type[etype].append(agent)
        
        # Tabella di mappatura tipi (gestisce diversi formati che LLM potrebbe produrre)
        type_aliases = {
            "official": ["official", "university", "governmentagency", "government"],
            "university": ["university", "official"],
            "mediaoutlet": ["mediaoutlet", "media"],
            "student": ["student", "person"],
            "professor": ["professor", "expert", "teacher"],
            "alumni": ["alumni", "person"],
            "organization": ["organization", "ngo", "company", "group"],
            "person": ["person", "student", "alumni"],
        }
        
        # Registra indice agent gia' usato per ogni tipo, evitando di riutilizzare lo stesso agent
        used_indices: Dict[str, int] = {}
        
        updated_posts = []
        for post in event_config.initial_posts:
            poster_type = post.get("poster_type", "").lower()
            content = post.get("content", "")
            
            # Tentativo di trovare un agent corrispondente
            matched_agent_id = None

            # 1. Corrispondenza diretta
            if poster_type in agents_by_type:
                agents = agents_by_type[poster_type]
                idx = used_indices.get(poster_type, 0) % len(agents)
                matched_agent_id = agents[idx].agent_id
                used_indices[poster_type] = idx + 1
            else:
                # 2. Corrispondenza tramite alias
                for alias_key, aliases in type_aliases.items():
                    if poster_type in aliases or alias_key == poster_type:
                        for alias in aliases:
                            if alias in agents_by_type:
                                agents = agents_by_type[alias]
                                idx = used_indices.get(alias, 0) % len(agents)
                                matched_agent_id = agents[idx].agent_id
                                used_indices[alias] = idx + 1
                                break
                    if matched_agent_id is not None:
                        break
            
            # 3. Se ancora non trovato, usa l'agent con influenza piu' alta
            if matched_agent_id is None:
                logger.warning(f"Nessun Agent corrispondente trovato per il tipo '{poster_type}', utilizzo Agent con influenza piu' alta")
                if agent_configs:
                    # Ordina per influenza, seleziona quello con influenza piu' alta
                    sorted_agents = sorted(agent_configs, key=lambda a: a.influence_weight, reverse=True)
                    matched_agent_id = sorted_agents[0].agent_id
                else:
                    matched_agent_id = 0
            
            updated_posts.append({
                "content": content,
                "poster_type": post.get("poster_type", "Unknown"),
                "poster_agent_id": matched_agent_id
            })
            
            logger.info(f"Assegnazione post iniziale: poster_type='{poster_type}' -> agent_id={matched_agent_id}")
        
        event_config.initial_posts = updated_posts
        return event_config
    
    def _generate_agent_configs_batch(
        self,
        context: str,
        entities: List[EntityNode],
        start_idx: int,
        simulation_requirement: str
    ) -> List[AgentActivityConfig]:
        """Genera configurazione Agent in lotti"""

        # Costruisci informazioni entita' (utilizza lunghezza riepilogo configurata)
        entity_list = []
        summary_len = self.AGENT_SUMMARY_LENGTH
        for i, e in enumerate(entities):
            entity_list.append({
                "agent_id": start_idx + i,
                "entity_name": e.name,
                "entity_type": e.get_entity_type() or "Unknown",
                "summary": e.summary[:summary_len] if e.summary else ""
            })
        
        prompt = f"""In base alle seguenti informazioni, genera la configurazione di attivita' social media per ogni entita'.

Requisiti simulazione: {simulation_requirement}

## Lista entita'
```json
{json.dumps(entity_list, ensure_ascii=False, indent=2)}
```

## Compito
Genera la configurazione attivita' per ogni entita', nota:
- **Orari conformi alle abitudini cinesi**: quasi nessuna attivita' ore 0-5, massima attivita' ore 19-22
- **Istituzioni ufficiali** (University/GovernmentAgency): attivita' bassa(0.1-0.3), attivi in orario lavorativo(9-17), risposta lenta(60-240 minuti), influenza alta(2.5-3.0)
- **Media** (MediaOutlet): attivita' media(0.4-0.6), attivi tutto il giorno(8-23), risposta veloce(5-30 minuti), influenza alta(2.0-2.5)
- **Individui** (Student/Person/Alumni): attivita' alta(0.6-0.9), principalmente attivi di sera(18-23), risposta veloce(1-15 minuti), influenza bassa(0.8-1.2)
- **Personaggi pubblici/Esperti**: attivita' media(0.4-0.6), influenza medio-alta(1.5-2.0)

Formato JSON di ritorno (senza markdown):
{{
    "agent_configs": [
        {{
            "agent_id": <deve corrispondere all'input>,
            "activity_level": <0.0-1.0>,
            "posts_per_hour": <frequenza post>,
            "comments_per_hour": <frequenza commenti>,
            "active_hours": [<lista ore attive, considerare abitudini cinesi>],
            "response_delay_min": <ritardo risposta minimo in minuti>,
            "response_delay_max": <ritardo risposta massimo in minuti>,
            "sentiment_bias": <da -1.0 a 1.0>,
            "stance": "<supportive/opposing/neutral/observer>",
            "influence_weight": <peso di influenza>
        }},
        ...
    ]
}}"""

        system_prompt = "Sei un esperto di analisi comportamentale sui social media. Restituisci JSON puro, la configurazione deve rispettare le abitudini cinesi."
        
        try:
            result = self._call_llm_with_retry(prompt, system_prompt)
            llm_configs = {cfg["agent_id"]: cfg for cfg in result.get("agent_configs", [])}
        except Exception as e:
            logger.warning(f"Generazione LLM lotto configurazione Agent fallita: {e}, utilizzo generazione basata su regole")
            llm_configs = {}
        
        # Costruisci oggetti AgentActivityConfig
        configs = []
        for i, entity in enumerate(entities):
            agent_id = start_idx + i
            cfg = llm_configs.get(agent_id, {})
            
            # Se LLM non ha generato, usa generazione basata su regole
            if not cfg:
                cfg = self._generate_agent_config_by_rule(entity)
            
            config = AgentActivityConfig(
                agent_id=agent_id,
                entity_uuid=entity.uuid,
                entity_name=entity.name,
                entity_type=entity.get_entity_type() or "Unknown",
                activity_level=cfg.get("activity_level", 0.5),
                posts_per_hour=cfg.get("posts_per_hour", 0.5),
                comments_per_hour=cfg.get("comments_per_hour", 1.0),
                active_hours=cfg.get("active_hours", list(range(9, 23))),
                response_delay_min=cfg.get("response_delay_min", 5),
                response_delay_max=cfg.get("response_delay_max", 60),
                sentiment_bias=cfg.get("sentiment_bias", 0.0),
                stance=cfg.get("stance", "neutral"),
                influence_weight=cfg.get("influence_weight", 1.0)
            )
            configs.append(config)
        
        return configs
    
    def _generate_agent_config_by_rule(self, entity: EntityNode) -> Dict[str, Any]:
        """Genera configurazione singolo Agent basata su regole (abitudini cinesi)"""
        entity_type = (entity.get_entity_type() or "Unknown").lower()
        
        if entity_type in ["university", "governmentagency", "ngo"]:
            # Istituzioni ufficiali: attivita' in orario lavorativo, bassa frequenza, alta influenza
            return {
                "activity_level": 0.2,
                "posts_per_hour": 0.1,
                "comments_per_hour": 0.05,
                "active_hours": list(range(9, 18)),  # 9:00-17:59
                "response_delay_min": 60,
                "response_delay_max": 240,
                "sentiment_bias": 0.0,
                "stance": "neutral",
                "influence_weight": 3.0
            }
        elif entity_type in ["mediaoutlet"]:
            # Media: attivita' tutto il giorno, frequenza media, alta influenza
            return {
                "activity_level": 0.5,
                "posts_per_hour": 0.8,
                "comments_per_hour": 0.3,
                "active_hours": list(range(7, 24)),  # 7:00-23:59
                "response_delay_min": 5,
                "response_delay_max": 30,
                "sentiment_bias": 0.0,
                "stance": "observer",
                "influence_weight": 2.5
            }
        elif entity_type in ["professor", "expert", "official"]:
            # Esperti/Professori: attivita' lavorativa+serale, frequenza media
            return {
                "activity_level": 0.4,
                "posts_per_hour": 0.3,
                "comments_per_hour": 0.5,
                "active_hours": list(range(8, 22)),  # 8:00-21:59
                "response_delay_min": 15,
                "response_delay_max": 90,
                "sentiment_bias": 0.0,
                "stance": "neutral",
                "influence_weight": 2.0
            }
        elif entity_type in ["student"]:
            # Studenti: principalmente serali, alta frequenza
            return {
                "activity_level": 0.8,
                "posts_per_hour": 0.6,
                "comments_per_hour": 1.5,
                "active_hours": [8, 9, 10, 11, 12, 13, 18, 19, 20, 21, 22, 23],  # Mattina+sera
                "response_delay_min": 1,
                "response_delay_max": 15,
                "sentiment_bias": 0.0,
                "stance": "neutral",
                "influence_weight": 0.8
            }
        elif entity_type in ["alumni"]:
            # Alumni: principalmente serali
            return {
                "activity_level": 0.6,
                "posts_per_hour": 0.4,
                "comments_per_hour": 0.8,
                "active_hours": [12, 13, 19, 20, 21, 22, 23],  # Pausa pranzo+sera
                "response_delay_min": 5,
                "response_delay_max": 30,
                "sentiment_bias": 0.0,
                "stance": "neutral",
                "influence_weight": 1.0
            }
        else:
            # Persona comune: picco serale
            return {
                "activity_level": 0.7,
                "posts_per_hour": 0.5,
                "comments_per_hour": 1.2,
                "active_hours": [9, 10, 11, 12, 13, 18, 19, 20, 21, 22, 23],  # Giorno+sera
                "response_delay_min": 2,
                "response_delay_max": 20,
                "sentiment_bias": 0.0,
                "stance": "neutral",
                "influence_weight": 1.0
            }
    

