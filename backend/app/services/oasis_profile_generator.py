"""
Generatore di Profili Agente OASIS — MiroFish-IT
Converte le entità del grafo Zep in profili agente per la piattaforma OASIS.

Con calibrazione istituzionale ICF:
1. Recupero Zep per arricchire il contesto delle entità
2. Prompt ottimizzati per persona dettagliate in italiano
3. Iniezione di dati regionali NUTS-2 (Hofstede, Schwartz, economici, demografici)
4. Distinzione tra entità individuali e gruppi/istituzioni
"""

import json
import random
import time
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from datetime import datetime

from openai import OpenAI
from zep_cloud.client import Zep

from ..config import Config
from ..utils.logger import get_logger
from .zep_entity_reader import EntityNode, ZepEntityReader
from .calibration_service import CalibrationService

logger = get_logger('mirofish.oasis_profile')


@dataclass
class OasisAgentProfile:
    """Struttura dati profilo agente OASIS."""
    # Campi essenziali
    user_id: int
    user_name: str
    name: str
    bio: str
    persona: str

    # Campi opzionali - formato Reddit
    karma: int = 1000

    # Campi opzionali - formato Twitter
    friend_count: int = 100
    follower_count: int = 150
    statuses_count: int = 500

    # Informazioni persona
    age: Optional[int] = None
    gender: Optional[str] = None
    mbti: Optional[str] = None
    country: Optional[str] = None
    profession: Optional[str] = None
    interested_topics: List[str] = field(default_factory=list)

    # Calibrazione regionale ICF
    nuts2_region: Optional[str] = None

    # Entità sorgente
    source_entity_uuid: Optional[str] = None
    source_entity_type: Optional[str] = None
    
    created_at: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d"))
    
    def to_reddit_format(self) -> Dict[str, Any]:
        """Converte in formato Reddit."""
        profile = {
            "user_id": self.user_id,
            "username": self.user_name,
            "name": self.name,
            "bio": self.bio,
            "persona": self.persona,
            "karma": self.karma,
            "created_at": self.created_at,
        }

        if self.age:
            profile["age"] = self.age
        if self.gender:
            profile["gender"] = self.gender
        if self.mbti:
            profile["mbti"] = self.mbti
        if self.country:
            profile["country"] = self.country
        if self.profession:
            profile["profession"] = self.profession
        if self.interested_topics:
            profile["interested_topics"] = self.interested_topics
        if self.nuts2_region:
            profile["nuts2_region"] = self.nuts2_region

        return profile
    
    def to_twitter_format(self) -> Dict[str, Any]:
        """Converte in formato Twitter."""
        profile = {
            "user_id": self.user_id,
            "username": self.user_name,
            "name": self.name,
            "bio": self.bio,
            "persona": self.persona,
            "friend_count": self.friend_count,
            "follower_count": self.follower_count,
            "statuses_count": self.statuses_count,
            "created_at": self.created_at,
        }
        
        # Aggiungi informazioni aggiuntive sulla persona
        if self.age:
            profile["age"] = self.age
        if self.gender:
            profile["gender"] = self.gender
        if self.mbti:
            profile["mbti"] = self.mbti
        if self.country:
            profile["country"] = self.country
        if self.profession:
            profile["profession"] = self.profession
        if self.interested_topics:
            profile["interested_topics"] = self.interested_topics
        
        return profile
    
    def to_dict(self) -> Dict[str, Any]:
        """Converte in formato dizionario completo"""
        return {
            "user_id": self.user_id,
            "user_name": self.user_name,
            "name": self.name,
            "bio": self.bio,
            "persona": self.persona,
            "karma": self.karma,
            "friend_count": self.friend_count,
            "follower_count": self.follower_count,
            "statuses_count": self.statuses_count,
            "age": self.age,
            "gender": self.gender,
            "mbti": self.mbti,
            "country": self.country,
            "profession": self.profession,
            "interested_topics": self.interested_topics,
            "source_entity_uuid": self.source_entity_uuid,
            "source_entity_type": self.source_entity_type,
            "created_at": self.created_at,
        }


class OasisProfileGenerator:
    """
    Generatore profili OASIS con calibrazione istituzionale ICF.

    Converte entità Zep in profili agente OASIS calibrati regionalmente.
    Supporta iniezione di dati NUTS-2 (Hofstede, Schwartz, economici, demografici).
    """

    MBTI_TYPES = [
        "INTJ", "INTP", "ENTJ", "ENTP",
        "INFJ", "INFP", "ENFJ", "ENFP",
        "ISTJ", "ISFJ", "ESTJ", "ESFJ",
        "ISTP", "ISFP", "ESTP", "ESFP"
    ]

    COUNTRIES = [
        "Italia", "Germania", "Francia", "Spagna", "Regno Unito",
        "Stati Uniti", "Svizzera", "Austria", "Belgio", "Paesi Bassi"
    ]

    INDIVIDUAL_ENTITY_TYPES = [
        "student", "alumni", "professor", "person", "publicfigure",
        "expert", "faculty", "official", "journalist", "activist"
    ]

    GROUP_ENTITY_TYPES = [
        "university", "governmentagency", "organization", "ngo",
        "mediaoutlet", "company", "institution", "group", "community"
    ]

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model_name: Optional[str] = None,
        zep_api_key: Optional[str] = None,
        graph_id: Optional[str] = None,
        nuts2_region: Optional[str] = None
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

        # Client Zep per arricchire il contesto
        self.zep_api_key = zep_api_key or Config.ZEP_API_KEY
        self.zep_client = None
        self.graph_id = graph_id

        if self.zep_api_key:
            try:
                self.zep_client = Zep(api_key=self.zep_api_key)
            except Exception as e:
                logger.warning(f"Inizializzazione client Zep fallita: {e}")

        # Calibrazione istituzionale ICF
        self.nuts2_region = nuts2_region
        self.calibration = CalibrationService()
        if self.calibration.is_loaded:
            logger.info(f"Calibrazione ICF attiva — {len(self.calibration.available_regions)} regioni disponibili")
            if self.nuts2_region:
                logger.info(f"Regione di default: {self.nuts2_region} ({self.calibration.get_region_name(self.nuts2_region)})")
        else:
            logger.warning("Dati di calibrazione ICF non disponibili — profili non calibrati")
    
    def generate_profile_from_entity(
        self,
        entity: EntityNode,
        user_id: int,
        use_llm: bool = True,
        nuts2_region: Optional[str] = None
    ) -> OasisAgentProfile:
        """
        Genera un profilo agente OASIS da un'entità Zep.

        Args:
            entity: nodo entità Zep
            user_id: ID utente per OASIS
            use_llm: se usare LLM per persona dettagliate
            nuts2_region: codice NUTS-2 per calibrazione regionale (override)
        """
        entity_type = entity.get_entity_type() or "Entity"

        name = entity.name
        user_name = self._generate_username(name)

        # Determina regione per calibrazione
        region = nuts2_region or self.nuts2_region
        if not region and self.calibration.is_loaded:
            # Assegna una regione casuale se non specificata
            region = self.calibration.get_random_region()

        # Costruisci contesto dall'entità
        context = self._build_entity_context(entity)

        # Aggiungi contesto di calibrazione regionale
        if region and self.calibration.is_loaded:
            cal_context = self.calibration.build_agent_calibration_context(region)
            if cal_context:
                context = context + "\n\n" + cal_context

        if use_llm:
            profile_data = self._generate_profile_with_llm(
                entity_name=name,
                entity_type=entity_type,
                entity_summary=entity.summary,
                entity_attributes=entity.attributes,
                context=context,
                nuts2_region=region
            )
        else:
            profile_data = self._generate_profile_rule_based(
                entity_name=name,
                entity_type=entity_type,
                entity_summary=entity.summary,
                entity_attributes=entity.attributes,
                nuts2_region=region
            )

        return OasisAgentProfile(
            user_id=user_id,
            user_name=user_name,
            name=name,
            bio=profile_data.get("bio", f"{entity_type}: {name}"),
            persona=profile_data.get("persona", entity.summary or f"Un(a) {entity_type} di nome {name}."),
            karma=profile_data.get("karma", random.randint(500, 5000)),
            friend_count=profile_data.get("friend_count", random.randint(50, 500)),
            follower_count=profile_data.get("follower_count", random.randint(100, 1000)),
            statuses_count=profile_data.get("statuses_count", random.randint(100, 2000)),
            age=profile_data.get("age"),
            gender=profile_data.get("gender"),
            mbti=profile_data.get("mbti"),
            country=profile_data.get("country", "Italia"),
            profession=profile_data.get("profession"),
            interested_topics=profile_data.get("interested_topics", []),
            nuts2_region=region,
            source_entity_uuid=entity.uuid,
            source_entity_type=entity_type,
        )
    
    def _generate_username(self, name: str) -> str:
        """Genera il nome utente"""
        # Rimuovi caratteri speciali, converti in minuscolo
        username = name.lower().replace(" ", "_")
        username = ''.join(c for c in username if c.isalnum() or c == '_')
        
        # Aggiungi suffisso casuale per evitare duplicati
        suffix = random.randint(100, 999)
        return f"{username}_{suffix}"
    
    def _search_zep_for_entity(self, entity: EntityNode) -> Dict[str, Any]:
        """
        Utilizza la funzionalità di ricerca ibrida del grafo Zep per ottenere informazioni ricche sull'entità

        Zep non ha un'interfaccia di ricerca ibrida integrata, è necessario cercare edges e nodes separatamente e poi unire i risultati.
        Utilizza richieste parallele per migliorare l'efficienza.

        Args:
            entity: oggetto nodo entità

        Returns:
            Dizionario contenente facts, node_summaries, context
        """
        import concurrent.futures
        
        if not self.zep_client:
            return {"facts": [], "node_summaries": [], "context": ""}
        
        entity_name = entity.name
        
        results = {
            "facts": [],
            "node_summaries": [],
            "context": ""
        }
        
        # È necessario avere graph_id per effettuare la ricerca
        if not self.graph_id:
            logger.debug(f"Ricerca Zep saltata: graph_id non impostato")
            return results
        
        comprehensive_query = f"Tutte le informazioni, attività, eventi, relazioni e contesto su {entity_name}"
        
        def search_edges():
            """Ricerca archi (fatti/relazioni) - con meccanismo di retry"""
            max_retries = 3
            last_exception = None
            delay = 2.0
            
            for attempt in range(max_retries):
                try:
                    return self.zep_client.graph.search(
                        query=comprehensive_query,
                        graph_id=self.graph_id,
                        limit=30,
                        scope="edges",
                        reranker="rrf"
                    )
                except Exception as e:
                    last_exception = e
                    if attempt < max_retries - 1:
                        logger.debug(f"Ricerca archi Zep tentativo {attempt + 1} fallito: {str(e)[:80]}, nuovo tentativo...")
                        time.sleep(delay)
                        delay *= 2
                    else:
                        logger.debug(f"Ricerca archi Zep fallita dopo {max_retries} tentativi: {e}")
            return None
        
        def search_nodes():
            """Ricerca nodi (riassunti entità) - con meccanismo di retry"""
            max_retries = 3
            last_exception = None
            delay = 2.0
            
            for attempt in range(max_retries):
                try:
                    return self.zep_client.graph.search(
                        query=comprehensive_query,
                        graph_id=self.graph_id,
                        limit=20,
                        scope="nodes",
                        reranker="rrf"
                    )
                except Exception as e:
                    last_exception = e
                    if attempt < max_retries - 1:
                        logger.debug(f"Ricerca nodi Zep tentativo {attempt + 1} fallito: {str(e)[:80]}, nuovo tentativo...")
                        time.sleep(delay)
                        delay *= 2
                    else:
                        logger.debug(f"Ricerca nodi Zep fallita dopo {max_retries} tentativi: {e}")
            return None
        
        try:
            # Esegui ricerca edges e nodes in parallelo
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
                edge_future = executor.submit(search_edges)
                node_future = executor.submit(search_nodes)
                
                # Ottieni i risultati
                edge_result = edge_future.result(timeout=30)
                node_result = node_future.result(timeout=30)
            
            # Elabora i risultati della ricerca archi
            all_facts = set()
            if edge_result and hasattr(edge_result, 'edges') and edge_result.edges:
                for edge in edge_result.edges:
                    if hasattr(edge, 'fact') and edge.fact:
                        all_facts.add(edge.fact)
            results["facts"] = list(all_facts)
            
            # Elabora i risultati della ricerca nodi
            all_summaries = set()
            if node_result and hasattr(node_result, 'nodes') and node_result.nodes:
                for node in node_result.nodes:
                    if hasattr(node, 'summary') and node.summary:
                        all_summaries.add(node.summary)
                    if hasattr(node, 'name') and node.name and node.name != entity_name:
                        all_summaries.add(f"Entità correlata: {node.name}")
            results["node_summaries"] = list(all_summaries)
            
            # Costruisci il contesto complessivo
            context_parts = []
            if results["facts"]:
                context_parts.append("Informazioni fattuali:\n" + "\n".join(f"- {f}" for f in results["facts"][:20]))
            if results["node_summaries"]:
                context_parts.append("Entità correlate:\n" + "\n".join(f"- {s}" for s in results["node_summaries"][:10]))
            results["context"] = "\n\n".join(context_parts)
            
            logger.info(f"Ricerca ibrida Zep completata: {entity_name}, ottenuti {len(results['facts'])} fatti, {len(results['node_summaries'])} nodi correlati")
            
        except concurrent.futures.TimeoutError:
            logger.warning(f"Ricerca Zep timeout ({entity_name})")
        except Exception as e:
            logger.warning(f"Ricerca Zep fallita ({entity_name}): {e}")
        
        return results
    
    def _build_entity_context(self, entity: EntityNode) -> str:
        """
        Costruisce le informazioni di contesto complete dell'entità

        Include:
        1. Informazioni sugli archi dell'entità (fatti)
        2. Informazioni dettagliate sui nodi correlati
        3. Informazioni ricche ottenute dalla ricerca ibrida Zep
        """
        context_parts = []
        
        # 1. Aggiungi informazioni sugli attributi dell'entità
        if entity.attributes:
            attrs = []
            for key, value in entity.attributes.items():
                if value and str(value).strip():
                    attrs.append(f"- {key}: {value}")
            if attrs:
                context_parts.append("### Attributi entità\n" + "\n".join(attrs))
        
        # 2. Aggiungi informazioni sugli archi correlati (fatti/relazioni)
        existing_facts = set()
        if entity.related_edges:
            relationships = []
            for edge in entity.related_edges:  # Senza limitazione di quantità
                fact = edge.get("fact", "")
                edge_name = edge.get("edge_name", "")
                direction = edge.get("direction", "")
                
                if fact:
                    relationships.append(f"- {fact}")
                    existing_facts.add(fact)
                elif edge_name:
                    if direction == "outgoing":
                        relationships.append(f"- {entity.name} --[{edge_name}]--> (entità correlata)")
                    else:
                        relationships.append(f"- (entità correlata) --[{edge_name}]--> {entity.name}")
            
            if relationships:
                context_parts.append("### Fatti e relazioni correlati\n" + "\n".join(relationships))
        
        # 3. Aggiungi informazioni dettagliate sui nodi correlati
        if entity.related_nodes:
            related_info = []
            for node in entity.related_nodes:  # Senza limitazione di quantità
                node_name = node.get("name", "")
                node_labels = node.get("labels", [])
                node_summary = node.get("summary", "")
                
                # Filtra le etichette predefinite
                custom_labels = [l for l in node_labels if l not in ["Entity", "Node"]]
                label_str = f" ({', '.join(custom_labels)})" if custom_labels else ""
                
                if node_summary:
                    related_info.append(f"- **{node_name}**{label_str}: {node_summary}")
                else:
                    related_info.append(f"- **{node_name}**{label_str}")
            
            if related_info:
                context_parts.append("### Informazioni entità correlate\n" + "\n".join(related_info))
        
        # 4. Utilizza la ricerca ibrida Zep per ottenere informazioni più ricche
        zep_results = self._search_zep_for_entity(entity)
        
        if zep_results.get("facts"):
            # Deduplicazione: escludi fatti già esistenti
            new_facts = [f for f in zep_results["facts"] if f not in existing_facts]
            if new_facts:
                context_parts.append("### Fatti recuperati da Zep\n" + "\n".join(f"- {f}" for f in new_facts[:15]))
        
        if zep_results.get("node_summaries"):
            context_parts.append("### Nodi correlati recuperati da Zep\n" + "\n".join(f"- {s}" for s in zep_results["node_summaries"][:10]))
        
        return "\n\n".join(context_parts)
    
    def _is_individual_entity(self, entity_type: str) -> bool:
        """Determina se è un'entità di tipo individuale"""
        return entity_type.lower() in self.INDIVIDUAL_ENTITY_TYPES
    
    def _is_group_entity(self, entity_type: str) -> bool:
        """Determina se è un'entità di tipo gruppo/istituzione"""
        return entity_type.lower() in self.GROUP_ENTITY_TYPES
    
    def _generate_profile_with_llm(
        self,
        entity_name: str,
        entity_type: str,
        entity_summary: str,
        entity_attributes: Dict[str, Any],
        context: str,
        nuts2_region: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Genera persona dettagliate tramite LLM con calibrazione istituzionale.
        """

        is_individual = self._is_individual_entity(entity_type)

        if is_individual:
            prompt = self._build_individual_persona_prompt(
                entity_name, entity_type, entity_summary, entity_attributes, context,
                nuts2_region=nuts2_region
            )
        else:
            prompt = self._build_group_persona_prompt(
                entity_name, entity_type, entity_summary, entity_attributes, context,
                nuts2_region=nuts2_region
            )

        # Tentativi multipli con temperatura decrescente
        max_attempts = 3
        last_error = None

        for attempt in range(max_attempts):
            try:
                response = self.client.chat.completions.create(
                    model=self.model_name,
                    messages=[
                        {"role": "system", "content": self._get_system_prompt(is_individual, nuts2_region)},
                        {"role": "user", "content": prompt}
                    ],
                    response_format={"type": "json_object"},
                    temperature=0.7 - (attempt * 0.1)
                )
                
                content = response.choices[0].message.content
                
                # Verifica se è stato troncato (finish_reason non è 'stop')
                finish_reason = response.choices[0].finish_reason
                if finish_reason == 'length':
                    logger.warning(f"Output LLM troncato (tentativo {attempt+1}), tentativo di riparazione...")
                    content = self._fix_truncated_json(content)
                
                # Tenta di analizzare il JSON
                try:
                    result = json.loads(content)
                    
                    # Verifica i campi obbligatori
                    if "bio" not in result or not result["bio"]:
                        result["bio"] = entity_summary[:200] if entity_summary else f"{entity_type}: {entity_name}"
                    if "persona" not in result or not result["persona"]:
                        result["persona"] = entity_summary or f"{entity_name} è un/una {entity_type}."
                    
                    return result
                    
                except json.JSONDecodeError as je:
                    logger.warning(f"Analisi JSON fallita (tentativo {attempt+1}): {str(je)[:80]}")
                    
                    # Tenta di riparare il JSON
                    result = self._try_fix_json(content, entity_name, entity_type, entity_summary)
                    if result.get("_fixed"):
                        del result["_fixed"]
                        return result
                    
                    last_error = je
                    
            except Exception as e:
                logger.warning(f"Chiamata LLM fallita (tentativo {attempt+1}): {str(e)[:80]}")
                last_error = e
                import time
                time.sleep(1 * (attempt + 1))  # backoff esponenziale
        
        logger.warning(f"Generazione persona tramite LLM fallita ({max_attempts} tentativi): {last_error}, utilizzo generazione basata su regole")
        return self._generate_profile_rule_based(
            entity_name, entity_type, entity_summary, entity_attributes
        )
    
    def _fix_truncated_json(self, content: str) -> str:
        """Ripara il JSON troncato (output troncato dal limite max_tokens)"""
        import re
        
        # Se il JSON è troncato, tenta di chiuderlo
        content = content.strip()
        
        # Calcola le parentesi non chiuse
        open_braces = content.count('{') - content.count('}')
        open_brackets = content.count('[') - content.count(']')
        
        # Verifica se ci sono stringhe non chiuse
        # Controllo semplice: se dopo l'ultimo virgolette non c'è virgola o parentesi di chiusura, la stringa potrebbe essere troncata
        if content and content[-1] not in '",}]':
            # Tenta di chiudere la stringa
            content += '"'
        
        # Chiudi le parentesi
        content += ']' * open_brackets
        content += '}' * open_braces
        
        return content
    
    def _try_fix_json(self, content: str, entity_name: str, entity_type: str, entity_summary: str = "") -> Dict[str, Any]:
        """Tenta di riparare il JSON danneggiato"""
        import re
        
        # 1. Prima tenta di riparare il caso di troncamento
        content = self._fix_truncated_json(content)
        
        # 2. Tenta di estrarre la parte JSON
        json_match = re.search(r'\{[\s\S]*\}', content)
        if json_match:
            json_str = json_match.group()
            
            # 3. Gestisci il problema degli a-capo nelle stringhe
            # Trova tutti i valori stringa e sostituisci gli a-capo al loro interno
            def fix_string_newlines(match):
                s = match.group(0)
                # Sostituisci gli a-capo reali nella stringa con spazi
                s = s.replace('\n', ' ').replace('\r', ' ')
                # Sostituisci spazi in eccesso
                s = re.sub(r'\s+', ' ', s)
                return s
            
            # Trova i valori stringa JSON
            json_str = re.sub(r'"[^"\\]*(?:\\.[^"\\]*)*"', fix_string_newlines, json_str)
            
            # 4. Tenta l'analisi
            try:
                result = json.loads(json_str)
                result["_fixed"] = True
                return result
            except json.JSONDecodeError as e:
                # 5. Se fallisce ancora, tenta una riparazione più aggressiva
                try:
                    # Rimuovi tutti i caratteri di controllo
                    json_str = re.sub(r'[\x00-\x1f\x7f-\x9f]', ' ', json_str)
                    # Sostituisci tutti gli spazi bianchi consecutivi
                    json_str = re.sub(r'\s+', ' ', json_str)
                    result = json.loads(json_str)
                    result["_fixed"] = True
                    return result
                except:
                    pass
        
        # 6. Tenta di estrarre informazioni parziali dal contenuto
        bio_match = re.search(r'"bio"\s*:\s*"([^"]*)"', content)
        persona_match = re.search(r'"persona"\s*:\s*"([^"]*)', content)  # potrebbe essere troncato
        
        bio = bio_match.group(1) if bio_match else (entity_summary[:200] if entity_summary else f"{entity_type}: {entity_name}")
        persona = persona_match.group(1) if persona_match else (entity_summary or f"{entity_name} è un/una {entity_type}.")
        
        # Se è stato estratto contenuto significativo, segna come riparato
        if bio_match or persona_match:
            logger.info(f"Estratte informazioni parziali dal JSON danneggiato")
            return {
                "bio": bio,
                "persona": persona,
                "_fixed": True
            }
        
        # 7. Fallimento completo, restituisci la struttura di base
        logger.warning(f"Riparazione JSON fallita, restituzione struttura di base")
        return {
            "bio": entity_summary[:200] if entity_summary else f"{entity_type}: {entity_name}",
            "persona": entity_summary or f"{entity_name} è un/una {entity_type}."
        }
    
    def _get_system_prompt(self, is_individual: bool, nuts2_region: Optional[str] = None) -> str:
        """Restituisce il system prompt per la generazione persona."""
        base_prompt = (
            "Sei un esperto nella creazione di profili utente per simulazioni sociali. "
            "Genera persona dettagliate e realistiche in italiano, coerenti con il contesto fornito. "
            "Devi restituire JSON valido. Tutti i valori stringa non devono contenere caratteri di a-capo non escaped. "
            "Usa l'italiano per tutti i campi testuali."
        )

        if nuts2_region and self.calibration.is_loaded:
            region_name = self.calibration.get_region_name(nuts2_region)
            zone = self.calibration.get_cultural_zone(nuts2_region)
            base_prompt += (
                f"\n\nIMPORTANTE — Calibrazione regionale: l'agente è localizzato in {region_name} "
                f"(zona {zone} Italia, codice NUTS-2: {nuts2_region}). "
                "Il profilo DEVE riflettere le caratteristiche economiche, culturali e demografiche "
                "di questa regione, come specificato nel contesto di calibrazione fornito. "
                "I valori Hofstede e Schwartz devono influenzare la personalità, lo stile comunicativo "
                "e gli atteggiamenti dell'agente."
            )

        return base_prompt
    
    def _build_individual_persona_prompt(
        self,
        entity_name: str,
        entity_type: str,
        entity_summary: str,
        entity_attributes: Dict[str, Any],
        context: str,
        nuts2_region: Optional[str] = None
    ) -> str:
        """Costruisce il prompt per entità individuali con calibrazione ICF."""

        attrs_str = json.dumps(entity_attributes, ensure_ascii=False) if entity_attributes else "Nessuno"
        context_str = context[:5000] if context else "Nessun contesto aggiuntivo"

        region_note = ""
        if nuts2_region and self.calibration.is_loaded:
            region_name = self.calibration.get_region_name(nuts2_region)
            region_note = f"\nRegione di residenza: {region_name} ({nuts2_region})"

        return f"""Genera un profilo dettagliato di utente social media per questa entità, riproducendo al massimo la realtà esistente.

Nome entità: {entity_name}
Tipo entità: {entity_type}
Descrizione: {entity_summary}
Attributi: {attrs_str}{region_note}

Informazioni di contesto:
{context_str}

Genera un JSON con i seguenti campi:

1. bio: presentazione per social media, circa 200 caratteri
2. persona: descrizione dettagliata della persona (circa 2000 caratteri, testo continuo), deve includere:
   - Informazioni di base (età, professione, istruzione, luogo di residenza)
   - Background personale (esperienze significative, relazioni con eventi, reti sociali)
   - Tratti di personalità (tipo MBTI, carattere, modo di esprimere emozioni)
   - Comportamento sui social media (frequenza post, preferenze contenuti, stile di interazione, particolarità linguistiche)
   - Posizioni e opinioni (atteggiamento verso i temi, cosa lo irrita o lo commuove)
   - Caratteristiche uniche (modi di dire, esperienze particolari, hobby)
   - Memoria personale (relazione con gli eventi in corso, azioni e reazioni già compiute)
   - Influenza culturale regionale (se presente nel contesto di calibrazione, rifletti i valori e comportamenti della regione)
3. age: età (numero intero)
4. gender: sesso, in inglese: "male" o "female"
5. mbti: tipo MBTI (es. INTJ, ENFP)
6. country: nazione (in italiano, es. "Italia")
7. profession: professione
8. interested_topics: array di argomenti di interesse

Importante:
- Tutti i valori devono essere stringhe o numeri, niente caratteri di a-capo
- persona deve essere un testo continuo e coerente
- Usa l'italiano per tutti i campi testuali (tranne gender che deve essere "male" o "female" in inglese)
- I contenuti devono essere coerenti con le informazioni dell'entità e il contesto di calibrazione regionale
- age deve essere un intero valido, gender deve essere "male" o "female"
"""

    def _build_group_persona_prompt(
        self,
        entity_name: str,
        entity_type: str,
        entity_summary: str,
        entity_attributes: Dict[str, Any],
        context: str,
        nuts2_region: Optional[str] = None
    ) -> str:
        """Costruisce il prompt per entità gruppo/istituzione con calibrazione ICF."""

        attrs_str = json.dumps(entity_attributes, ensure_ascii=False) if entity_attributes else "Nessuno"
        context_str = context[:5000] if context else "Nessun contesto aggiuntivo"

        region_note = ""
        if nuts2_region and self.calibration.is_loaded:
            region_name = self.calibration.get_region_name(nuts2_region)
            region_note = f"\nSede/Regione di riferimento: {region_name} ({nuts2_region})"

        return f"""Genera un profilo dettagliato di account social media per questa istituzione/gruppo, riproducendo al massimo la realtà esistente.

Nome entità: {entity_name}
Tipo entità: {entity_type}
Descrizione: {entity_summary}
Attributi: {attrs_str}{region_note}

Informazioni di contesto:
{context_str}

Genera un JSON con i seguenti campi:

1. bio: presentazione account ufficiale, circa 200 caratteri, professionale e appropriata
2. persona: descrizione dettagliata dell'account (circa 2000 caratteri, testo continuo), deve includere:
   - Informazioni istituzionali (nome ufficiale, natura, background, funzioni principali)
   - Posizionamento account (tipo, pubblico target, funzione principale)
   - Stile comunicativo (caratteristiche linguistiche, espressioni tipiche, argomenti tabù)
   - Caratteristiche dei contenuti (tipi, frequenza pubblicazione, orari di attività)
   - Posizioni e atteggiamenti (posizione ufficiale sui temi chiave, gestione delle controversie)
   - Note speciali (profilo del gruppo rappresentato, abitudini operative)
   - Memoria istituzionale (relazione con gli eventi in corso, azioni e reazioni già compiute)
   - Contesto regionale (se presente nel contesto di calibrazione, rifletti il contesto socio-economico della regione)
3. age: fisso a 30 (età virtuale account istituzionale)
4. gender: fisso "other" (account istituzionale)
5. mbti: tipo MBTI per descrivere lo stile dell'account (es. ISTJ = rigoroso e conservatore)
6. country: nazione (in italiano, es. "Italia")
7. profession: descrizione della funzione istituzionale
8. interested_topics: array di aree di interesse

Importante:
- Tutti i valori devono essere stringhe o numeri, niente valori null
- persona deve essere un testo continuo e coerente, senza caratteri di a-capo
- Usa l'italiano (tranne gender che deve essere "other" in inglese)
- age deve essere l'intero 30, gender deve essere la stringa "other"
- Lo stile comunicativo deve essere coerente con il ruolo istituzionale"""
    
    def _generate_profile_rule_based(
        self,
        entity_name: str,
        entity_type: str,
        entity_summary: str,
        entity_attributes: Dict[str, Any],
        nuts2_region: Optional[str] = None
    ) -> Dict[str, Any]:
        """Genera un profilo base tramite regole (fallback senza LLM)."""

        entity_type_lower = entity_type.lower()
        country = "Italia"

        # Aggiungi contesto regionale se disponibile
        region_note = ""
        if nuts2_region and self.calibration.is_loaded:
            region_name = self.calibration.get_region_name(nuts2_region)
            region_note = f" Residente in {region_name}."

        if entity_type_lower in ["student", "alumni"]:
            return {
                "bio": f"{entity_type} con interessi in ambito accademico e questioni sociali.",
                "persona": f"{entity_name} è uno/a {entity_type.lower()} attivamente impegnato/a in discussioni accademiche e sociali. Condivide prospettive e si connette con i coetanei.{region_note}",
                "age": random.randint(18, 30),
                "gender": random.choice(["male", "female"]),
                "mbti": random.choice(self.MBTI_TYPES),
                "country": country,
                "profession": "Studente",
                "interested_topics": ["Istruzione", "Questioni sociali", "Tecnologia"],
            }

        elif entity_type_lower in ["publicfigure", "expert", "faculty"]:
            return {
                "bio": f"Esperto/a e opinion leader nel proprio campo.",
                "persona": f"{entity_name} è un/una {entity_type.lower()} riconosciuto/a che condivide analisi e opinioni su temi importanti. È noto/a per la propria competenza e influenza nel dibattito pubblico.{region_note}",
                "age": random.randint(35, 60),
                "gender": random.choice(["male", "female"]),
                "mbti": random.choice(["ENTJ", "INTJ", "ENTP", "INTP"]),
                "country": country,
                "profession": entity_attributes.get("occupation", "Esperto"),
                "interested_topics": ["Politica", "Economia", "Cultura e società"],
            }

        elif entity_type_lower in ["mediaoutlet", "socialmediaplatform"]:
            return {
                "bio": f"Account ufficiale di {entity_name}. Notizie e aggiornamenti.",
                "persona": f"{entity_name} è un'entità mediatica che riporta notizie e facilita il dibattito pubblico. L'account condivide aggiornamenti tempestivi e interagisce con il pubblico sugli eventi correnti.{region_note}",
                "age": 30,
                "gender": "other",
                "mbti": "ISTJ",
                "country": country,
                "profession": "Media",
                "interested_topics": ["Notizie generali", "Attualità", "Affari pubblici"],
            }

        elif entity_type_lower in ["university", "governmentagency", "ngo", "organization"]:
            return {
                "bio": f"Account ufficiale di {entity_name}.",
                "persona": f"{entity_name} è un'entità istituzionale che comunica posizioni ufficiali, annunci e si relaziona con gli stakeholder su temi rilevanti.{region_note}",
                "age": 30,
                "gender": "other",
                "mbti": "ISTJ",
                "country": country,
                "profession": entity_type,
                "interested_topics": ["Politiche pubbliche", "Comunità", "Comunicati ufficiali"],
            }

        else:
            return {
                "bio": entity_summary[:150] if entity_summary else f"{entity_type}: {entity_name}",
                "persona": entity_summary or f"{entity_name} è un/una {entity_type.lower()} che partecipa a discussioni sociali.{region_note}",
                "age": random.randint(25, 50),
                "gender": random.choice(["male", "female"]),
                "mbti": random.choice(self.MBTI_TYPES),
                "country": country,
                "profession": entity_type,
                "interested_topics": ["Generale", "Questioni sociali"],
            }
    
    def set_graph_id(self, graph_id: str):
        """Imposta l'ID del grafo per la ricerca Zep"""
        self.graph_id = graph_id
    
    def generate_profiles_from_entities(
        self,
        entities: List[EntityNode],
        use_llm: bool = True,
        progress_callback: Optional[callable] = None,
        graph_id: Optional[str] = None,
        parallel_count: int = 5,
        realtime_output_path: Optional[str] = None,
        output_platform: str = "reddit"
    ) -> List[OasisAgentProfile]:
        """
        Genera Agent Profile in batch dalle entità (supporta generazione parallela)

        Args:
            entities: Lista delle entità
            use_llm: Se usare LLM per generare persona dettagliate
            progress_callback: Funzione di callback progresso (current, total, message)
            graph_id: ID del grafo, usato per il recupero Zep per ottenere contesto più ricco
            parallel_count: Numero di generazioni parallele, predefinito 5
            realtime_output_path: Percorso file per scrittura in tempo reale (se fornito, scrive ogni volta che ne genera uno)
            output_platform: Formato piattaforma di output ("reddit" o "twitter")

        Returns:
            Lista di Agent Profile
        """
        import concurrent.futures
        from threading import Lock
        
        # Imposta graph_id per il recupero Zep
        if graph_id:
            self.graph_id = graph_id

        total = len(entities)
        profiles = [None] * total  # Pre-alloca la lista per mantenere l'ordine
        completed_count = [0]  # Usa una lista per poterla modificare nella closure
        lock = Lock()

        # Funzione ausiliaria per scrittura file in tempo reale
        def save_profiles_realtime():
            """Salva in tempo reale i profili generati su file"""
            if not realtime_output_path:
                return

            with lock:
                # Filtra i profili già generati
                existing_profiles = [p for p in profiles if p is not None]
                if not existing_profiles:
                    return

                try:
                    if output_platform == "reddit":
                        # Formato Reddit JSON
                        profiles_data = [p.to_reddit_format() for p in existing_profiles]
                        with open(realtime_output_path, 'w', encoding='utf-8') as f:
                            json.dump(profiles_data, f, ensure_ascii=False, indent=2)
                    else:
                        # Formato Twitter CSV
                        import csv
                        profiles_data = [p.to_twitter_format() for p in existing_profiles]
                        if profiles_data:
                            fieldnames = list(profiles_data[0].keys())
                            with open(realtime_output_path, 'w', encoding='utf-8', newline='') as f:
                                writer = csv.DictWriter(f, fieldnames=fieldnames)
                                writer.writeheader()
                                writer.writerows(profiles_data)
                except Exception as e:
                    logger.warning(f"Salvataggio in tempo reale dei profili fallito: {e}")
        
        def generate_single_profile(idx: int, entity: EntityNode) -> tuple:
            """Funzione worker per generare un singolo profilo"""
            entity_type = entity.get_entity_type() or "Entity"

            try:
                profile = self.generate_profile_from_entity(
                    entity=entity,
                    user_id=idx,
                    use_llm=use_llm
                )

                # Output in tempo reale della persona generata su console e log
                self._print_generated_profile(entity.name, entity_type, profile)

                return idx, profile, None

            except Exception as e:
                logger.error(f"Generazione persona per l'entità {entity.name} fallita: {str(e)}")
                # Crea un profilo di base
                fallback_profile = OasisAgentProfile(
                    user_id=idx,
                    user_name=self._generate_username(entity.name),
                    name=entity.name,
                    bio=f"{entity_type}: {entity.name}",
                    persona=entity.summary or f"A participant in social discussions.",
                    source_entity_uuid=entity.uuid,
                    source_entity_type=entity_type,
                )
                return idx, fallback_profile, str(e)
        
        logger.info(f"Inizio generazione parallela di {total} persona Agent (parallelismo: {parallel_count})...")
        print(f"\n{'='*60}")
        print(f"Inizio generazione persona Agent - totale {total} entità, parallelismo: {parallel_count}")
        print(f"{'='*60}\n")

        # Esecuzione parallela con thread pool
        with concurrent.futures.ThreadPoolExecutor(max_workers=parallel_count) as executor:
            # Invia tutte le attività
            future_to_entity = {
                executor.submit(generate_single_profile, idx, entity): (idx, entity)
                for idx, entity in enumerate(entities)
            }

            # Raccogli i risultati
            for future in concurrent.futures.as_completed(future_to_entity):
                idx, entity = future_to_entity[future]
                entity_type = entity.get_entity_type() or "Entity"
                
                try:
                    result_idx, profile, error = future.result()
                    profiles[result_idx] = profile
                    
                    with lock:
                        completed_count[0] += 1
                        current = completed_count[0]
                    
                    # Scrittura file in tempo reale
                    save_profiles_realtime()

                    if progress_callback:
                        progress_callback(
                            current,
                            total,
                            f"Completato {current}/{total}: {entity.name} ({entity_type})"
                        )

                    if error:
                        logger.warning(f"[{current}/{total}] {entity.name} usa persona di riserva: {error}")
                    else:
                        logger.info(f"[{current}/{total}] Persona generata con successo: {entity.name} ({entity_type})")

                except Exception as e:
                    logger.error(f"Eccezione durante l'elaborazione dell'entità {entity.name}: {str(e)}")
                    with lock:
                        completed_count[0] += 1
                    profiles[idx] = OasisAgentProfile(
                        user_id=idx,
                        user_name=self._generate_username(entity.name),
                        name=entity.name,
                        bio=f"{entity_type}: {entity.name}",
                        persona=entity.summary or "A participant in social discussions.",
                        source_entity_uuid=entity.uuid,
                        source_entity_type=entity_type,
                    )
                    # Scrittura file in tempo reale (anche per persona di riserva)
                    save_profiles_realtime()

        print(f"\n{'='*60}")
        print(f"Generazione persona completata! Generati {len([p for p in profiles if p])} Agent")
        print(f"{'='*60}\n")
        
        return profiles
    
    def _print_generated_profile(self, entity_name: str, entity_type: str, profile: OasisAgentProfile):
        """Output in tempo reale della persona generata su console (contenuto completo, senza troncamento)"""
        separator = "-" * 70

        # Costruisci il contenuto completo dell'output (senza troncamento)
        topics_str = ', '.join(profile.interested_topics) if profile.interested_topics else 'nessuno'

        output_lines = [
            f"\n{separator}",
            f"[Generato] {entity_name} ({entity_type})",
            f"{separator}",
            f"Nome utente: {profile.user_name}",
            f"",
            f"[Biografia]",
            f"{profile.bio}",
            f"",
            f"[Persona dettagliata]",
            f"{profile.persona}",
            f"",
            f"[Attributi base]",
            f"Età: {profile.age} | Genere: {profile.gender} | MBTI: {profile.mbti}",
            f"Professione: {profile.profession} | Paese: {profile.country}",
            f"Argomenti di interesse: {topics_str}",
            separator
        ]

        output = "\n".join(output_lines)

        # Output solo su console (evita duplicati, il logger non stampa più il contenuto completo)
        print(output)
    
    def save_profiles(
        self,
        profiles: List[OasisAgentProfile],
        file_path: str,
        platform: str = "reddit"
    ):
        """
        Salva i profili su file (seleziona il formato corretto in base alla piattaforma)

        Requisiti formato piattaforma OASIS:
        - Twitter: formato CSV
        - Reddit: formato JSON

        Args:
            profiles: Lista dei profili
            file_path: Percorso del file
            platform: Tipo di piattaforma ("reddit" o "twitter")
        """
        if platform == "twitter":
            self._save_twitter_csv(profiles, file_path)
        else:
            self._save_reddit_json(profiles, file_path)
    
    def _save_twitter_csv(self, profiles: List[OasisAgentProfile], file_path: str):
        """
        Salva i profili Twitter in formato CSV (conforme ai requisiti ufficiali OASIS)

        Campi CSV richiesti da OASIS Twitter:
        - user_id: ID utente (partendo da 0 in base all'ordine CSV)
        - name: Nome reale dell'utente
        - username: Nome utente nel sistema
        - user_char: Descrizione dettagliata della persona (iniettata nel system prompt LLM, guida il comportamento dell'Agent)
        - description: Breve biografia pubblica (mostrata nella pagina profilo utente)

        Differenza tra user_char e description:
        - user_char: Uso interno, system prompt LLM, determina come l'Agent pensa e agisce
        - description: Visualizzazione esterna, biografia visibile agli altri utenti
        """
        import csv
        
        # Assicura che l'estensione del file sia .csv
        if not file_path.endswith('.csv'):
            file_path = file_path.replace('.json', '.csv')

        with open(file_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)

            # Scrivi l'intestazione richiesta da OASIS
            headers = ['user_id', 'name', 'username', 'user_char', 'description']
            writer.writerow(headers)

            # Scrivi le righe di dati
            for idx, profile in enumerate(profiles):
                # user_char: persona completa (bio + persona), per il system prompt LLM
                user_char = profile.bio
                if profile.persona and profile.persona != profile.bio:
                    user_char = f"{profile.bio} {profile.persona}"
                # Gestisci i caratteri di a-capo (nel CSV sostituiti con spazi)
                user_char = user_char.replace('\n', ' ').replace('\r', ' ')

                # description: breve biografia, per la visualizzazione esterna
                description = profile.bio.replace('\n', ' ').replace('\r', ' ')

                row = [
                    idx,                    # user_id: ID sequenziale partendo da 0
                    profile.name,           # name: nome reale
                    profile.user_name,      # username: nome utente
                    user_char,              # user_char: persona completa (uso interno LLM)
                    description             # description: breve biografia (visualizzazione esterna)
                ]
                writer.writerow(row)

        logger.info(f"Salvati {len(profiles)} profili Twitter in {file_path} (formato CSV OASIS)")
    
    def _normalize_gender(self, gender: Optional[str]) -> str:
        """
        Normalizza il campo gender nel formato inglese richiesto da OASIS

        OASIS richiede: male, female, other
        """
        if not gender:
            return "other"

        gender_lower = gender.lower().strip()

        # Mappatura valori
        gender_map = {
            "maschio": "male",
            "femmina": "female",
            "istituzione": "other",
            "altro": "other",
            # Valori inglesi già presenti
            "male": "male",
            "female": "female",
            "other": "other",
        }
        
        return gender_map.get(gender_lower, "other")
    
    def _save_reddit_json(self, profiles: List[OasisAgentProfile], file_path: str):
        """
        Salva i profili Reddit in formato JSON

        Usa un formato coerente con to_reddit_format(), assicurando che OASIS possa leggerlo correttamente.
        Deve includere il campo user_id, che è la chiave per il matching di OASIS agent_graph.get_agent()!

        Campi obbligatori:
        - user_id: ID utente (intero, usato per il matching con poster_agent_id in initial_posts)
        - username: Nome utente
        - name: Nome visualizzato
        - bio: Biografia
        - persona: Persona dettagliata
        - age: Età (intero)
        - gender: "male", "female", o "other"
        - mbti: Tipo MBTI
        - country: Paese
        """
        data = []
        for idx, profile in enumerate(profiles):
            # Usa un formato coerente con to_reddit_format()
            item = {
                "user_id": profile.user_id if profile.user_id is not None else idx,  # Chiave: deve includere user_id
                "username": profile.user_name,
                "name": profile.name,
                "bio": profile.bio[:150] if profile.bio else f"{profile.name}",
                "persona": profile.persona or f"{profile.name} is a participant in social discussions.",
                "karma": profile.karma if profile.karma else 1000,
                "created_at": profile.created_at,
                # Campi obbligatori OASIS - assicura che tutti abbiano valori predefiniti
                "age": profile.age if profile.age else 30,
                "gender": self._normalize_gender(profile.gender),
                "mbti": profile.mbti if profile.mbti else "ISTJ",
                "country": profile.country if profile.country else "Italia",
            }

            # Campi opzionali
            if profile.profession:
                item["profession"] = profile.profession
            if profile.interested_topics:
                item["interested_topics"] = profile.interested_topics
            
            data.append(item)
        
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        logger.info(f"Salvati {len(profiles)} profili Reddit in {file_path} (formato JSON, con campo user_id)")

    # Mantieni il vecchio nome del metodo come alias, per retrocompatibilità
    def save_profiles_to_json(
        self,
        profiles: List[OasisAgentProfile],
        file_path: str,
        platform: str = "reddit"
    ):
        """[Deprecato] Usa il metodo save_profiles()"""
        logger.warning("save_profiles_to_json è deprecato, usa il metodo save_profiles")
        self.save_profiles(profiles, file_path, platform)

