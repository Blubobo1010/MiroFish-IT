"""
Servizio di generazione dell'ontologia
Interfaccia 1: Analizza il contenuto testuale e genera definizioni di tipi di entita' e relazioni adatte alla simulazione sociale
"""

import json
from typing import Dict, Any, List, Optional
from ..utils.llm_client import LLMClient


# Prompt di sistema per la generazione dell'ontologia
ONTOLOGY_SYSTEM_PROMPT = """Sei un esperto professionista nella progettazione di ontologie per grafi della conoscenza. Il tuo compito e' analizzare il contenuto testuale fornito e i requisiti di simulazione, progettando tipi di entita' e tipi di relazioni adatti alla **simulazione dell'opinione pubblica sui social media**.

**Importante: devi produrre dati in formato JSON valido, senza alcun altro contenuto.**

## Contesto del compito principale

Stiamo costruendo un **sistema di simulazione dell'opinione pubblica sui social media**. In questo sistema:
- Ogni entita' e' un "account" o "soggetto" che puo' esprimersi, interagire e diffondere informazioni sui social media
- Le entita' si influenzano reciprocamente, condividono, commentano e rispondono
- Dobbiamo simulare le reazioni delle varie parti coinvolte negli eventi di opinione pubblica e i percorsi di diffusione delle informazioni

Pertanto, **le entita' devono essere soggetti realmente esistenti che possono esprimersi e interagire sui social media**:

**Possono essere**:
- Individui specifici (personaggi pubblici, parti coinvolte, opinion leader, esperti e studiosi, persone comuni)
- Aziende e imprese (inclusi i loro account ufficiali)
- Organizzazioni e istituzioni (universita', associazioni, ONG, sindacati, ecc.)
- Dipartimenti governativi, enti regolatori
- Enti mediatici (giornali, emittenti televisive, media indipendenti, siti web)
- Le piattaforme social media stesse
- Rappresentanti di gruppi specifici (come associazioni di ex-alunni, fan club, gruppi di difesa dei diritti, ecc.)

**Non possono essere**:
- Concetti astratti (come "opinione pubblica", "emozione", "tendenza")
- Temi/argomenti (come "integrita' accademica", "riforma dell'istruzione")
- Opinioni/atteggiamenti (come "sostenitori", "oppositori")

## Formato di output

Produci un output in formato JSON con la seguente struttura:

```json
{
    "entity_types": [
        {
            "name": "Nome del tipo di entita' (inglese, PascalCase)",
            "description": "Breve descrizione (inglese, massimo 100 caratteri)",
            "attributes": [
                {
                    "name": "nome_attributo (inglese, snake_case)",
                    "type": "text",
                    "description": "Descrizione dell'attributo"
                }
            ],
            "examples": ["Esempio entita' 1", "Esempio entita' 2"]
        }
    ],
    "edge_types": [
        {
            "name": "Nome del tipo di relazione (inglese, UPPER_SNAKE_CASE)",
            "description": "Breve descrizione (inglese, massimo 100 caratteri)",
            "source_targets": [
                {"source": "Tipo entita' sorgente", "target": "Tipo entita' destinazione"}
            ],
            "attributes": []
        }
    ],
    "analysis_summary": "Breve analisi descrittiva del contenuto testuale (in italiano)"
}
```

## Linee guida di progettazione (estremamente importanti!)

### 1. Progettazione dei tipi di entita' - Da rispettare rigorosamente

**Requisito di quantita': esattamente 10 tipi di entita'**

**Requisito di struttura gerarchica (deve includere sia tipi specifici che tipi di fallback)**:

I tuoi 10 tipi di entita' devono includere i seguenti livelli:

A. **Tipi di fallback (obbligatori, da inserire come ultimi 2 della lista)**:
   - `Person`: Tipo di fallback per qualsiasi individuo. Quando una persona non rientra in altri tipi piu' specifici, viene classificata qui.
   - `Organization`: Tipo di fallback per qualsiasi organizzazione. Quando un'organizzazione non rientra in altri tipi piu' specifici, viene classificata qui.

B. **Tipi specifici (8, progettati in base al contenuto testuale)**:
   - Progetta tipi piu' specifici per i ruoli principali che appaiono nel testo
   - Esempio: se il testo riguarda un evento accademico, puoi avere `Student`, `Professor`, `University`
   - Esempio: se il testo riguarda un evento commerciale, puoi avere `Company`, `CEO`, `Employee`

**Perche' servono i tipi di fallback**:
- Nel testo appaiono vari personaggi, come "insegnanti di scuola", "passanti", "un certo utente della rete"
- Se non c'e' un tipo specifico corrispondente, devono essere classificati come `Person`
- Analogamente, piccole organizzazioni, gruppi temporanei, ecc. devono essere classificati come `Organization`

**Principi di progettazione dei tipi specifici**:
- Identifica i tipi di ruolo ad alta frequenza o chiave nel testo
- Ogni tipo specifico deve avere confini chiari, evitando sovrapposizioni
- La description deve chiarire la differenza tra questo tipo e il tipo di fallback

### 2. Progettazione dei tipi di relazione

- Quantita': 6-10
- Le relazioni devono riflettere connessioni reali nelle interazioni sui social media
- Assicurati che i source_targets delle relazioni coprano i tipi di entita' definiti

### 3. Progettazione degli attributi

- 1-3 attributi chiave per ogni tipo di entita'
- **Attenzione**: I nomi degli attributi non possono utilizzare `name`, `uuid`, `group_id`, `created_at`, `summary` (sono parole riservate del sistema)
- Si consiglia di usare: `full_name`, `title`, `role`, `position`, `location`, `description`, ecc.

## Riferimento per i tipi di entita'

**Categoria individui (specifici)**:
- Student: Studente
- Professor: Professore/Studioso
- Journalist: Giornalista
- Celebrity: Personaggio famoso/Influencer
- Executive: Dirigente
- Official: Funzionario governativo
- Lawyer: Avvocato
- Doctor: Medico

**Categoria individui (fallback)**:
- Person: Qualsiasi individuo (usato quando non rientra nei tipi specifici sopra indicati)

**Categoria organizzazioni (specifici)**:
- University: Universita'
- Company: Azienda/Impresa
- GovernmentAgency: Ente governativo
- MediaOutlet: Ente mediatico
- Hospital: Ospedale
- School: Scuola primaria e secondaria
- NGO: Organizzazione non governativa

**Categoria organizzazioni (fallback)**:
- Organization: Qualsiasi organizzazione (usata quando non rientra nei tipi specifici sopra indicati)

## Riferimento per i tipi di relazione

- WORKS_FOR: Lavora per
- STUDIES_AT: Studia presso
- AFFILIATED_WITH: Affiliato a
- REPRESENTS: Rappresenta
- REGULATES: Regola
- REPORTS_ON: Riporta su
- COMMENTS_ON: Commenta su
- RESPONDS_TO: Risponde a
- SUPPORTS: Supporta
- OPPOSES: Si oppone a
- COLLABORATES_WITH: Collabora con
- COMPETES_WITH: Compete con
"""


class OntologyGenerator:
    """
    Generatore di ontologia
    Analizza il contenuto testuale e genera definizioni di tipi di entita' e relazioni
    """

    def __init__(self, llm_client: Optional[LLMClient] = None):
        self.llm_client = llm_client or LLMClient()

    def generate(
        self,
        document_texts: List[str],
        simulation_requirement: str,
        additional_context: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Genera la definizione dell'ontologia

        Args:
            document_texts: Lista di testi dei documenti
            simulation_requirement: Descrizione dei requisiti di simulazione
            additional_context: Contesto aggiuntivo

        Returns:
            Definizione dell'ontologia (entity_types, edge_types, ecc.)
        """
        # Costruisce il messaggio utente
        user_message = self._build_user_message(
            document_texts,
            simulation_requirement,
            additional_context
        )

        messages = [
            {"role": "system", "content": ONTOLOGY_SYSTEM_PROMPT},
            {"role": "user", "content": user_message}
        ]

        # Chiamata al LLM
        result = self.llm_client.chat_json(
            messages=messages,
            temperature=0.3,
            max_tokens=4096
        )

        # Validazione e post-elaborazione
        result = self._validate_and_process(result)

        return result

    # Lunghezza massima del testo inviato al LLM (50.000 caratteri)
    MAX_TEXT_LENGTH_FOR_LLM = 50000

    def _build_user_message(
        self,
        document_texts: List[str],
        simulation_requirement: str,
        additional_context: Optional[str]
    ) -> str:
        """Costruisce il messaggio utente"""

        # Unisce i testi
        combined_text = "\n\n---\n\n".join(document_texts)
        original_length = len(combined_text)

        # Se il testo supera i 50.000 caratteri, viene troncato (influisce solo sul contenuto inviato al LLM, non sulla costruzione del grafo)
        if len(combined_text) > self.MAX_TEXT_LENGTH_FOR_LLM:
            combined_text = combined_text[:self.MAX_TEXT_LENGTH_FOR_LLM]
            combined_text += f"\n\n...(Testo originale di {original_length} caratteri, troncato ai primi {self.MAX_TEXT_LENGTH_FOR_LLM} caratteri per l'analisi dell'ontologia)..."

        message = f"""## Requisiti di simulazione

{simulation_requirement}

## Contenuto del documento

{combined_text}
"""

        if additional_context:
            message += f"""
## Note aggiuntive

{additional_context}
"""

        message += """
In base al contenuto sopra indicato, progetta i tipi di entita' e i tipi di relazione adatti alla simulazione dell'opinione pubblica sociale.

**Regole da rispettare obbligatoriamente**:
1. Devi produrre esattamente 10 tipi di entita'
2. Gli ultimi 2 devono essere tipi di fallback: Person (fallback individui) e Organization (fallback organizzazioni)
3. I primi 8 sono tipi specifici progettati in base al contenuto testuale
4. Tutti i tipi di entita' devono essere soggetti che possono esprimersi nella realta', non concetti astratti
5. I nomi degli attributi non possono utilizzare parole riservate come name, uuid, group_id, ecc., usa full_name, org_name, ecc. come alternativa
"""

        return message

    def _validate_and_process(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """Validazione e post-elaborazione del risultato"""

        # Assicura che i campi necessari esistano
        if "entity_types" not in result:
            result["entity_types"] = []
        if "edge_types" not in result:
            result["edge_types"] = []
        if "analysis_summary" not in result:
            result["analysis_summary"] = ""

        # Validazione dei tipi di entita'
        for entity in result["entity_types"]:
            if "attributes" not in entity:
                entity["attributes"] = []
            if "examples" not in entity:
                entity["examples"] = []
            # Assicura che la description non superi i 100 caratteri
            if len(entity.get("description", "")) > 100:
                entity["description"] = entity["description"][:97] + "..."

        # Validazione dei tipi di relazione
        for edge in result["edge_types"]:
            if "source_targets" not in edge:
                edge["source_targets"] = []
            if "attributes" not in edge:
                edge["attributes"] = []
            if len(edge.get("description", "")) > 100:
                edge["description"] = edge["description"][:97] + "..."

        # Limiti dell'API Zep: massimo 10 tipi di entita' personalizzati, massimo 10 tipi di relazione personalizzati
        MAX_ENTITY_TYPES = 10
        MAX_EDGE_TYPES = 10

        # Definizione dei tipi di fallback
        person_fallback = {
            "name": "Person",
            "description": "Any individual person not fitting other specific person types.",
            "attributes": [
                {"name": "full_name", "type": "text", "description": "Full name of the person"},
                {"name": "role", "type": "text", "description": "Role or occupation"}
            ],
            "examples": ["ordinary citizen", "anonymous netizen"]
        }

        organization_fallback = {
            "name": "Organization",
            "description": "Any organization not fitting other specific organization types.",
            "attributes": [
                {"name": "org_name", "type": "text", "description": "Name of the organization"},
                {"name": "org_type", "type": "text", "description": "Type of organization"}
            ],
            "examples": ["small business", "community group"]
        }

        # Verifica se i tipi di fallback sono gia' presenti
        entity_names = {e["name"] for e in result["entity_types"]}
        has_person = "Person" in entity_names
        has_organization = "Organization" in entity_names

        # Tipi di fallback da aggiungere
        fallbacks_to_add = []
        if not has_person:
            fallbacks_to_add.append(person_fallback)
        if not has_organization:
            fallbacks_to_add.append(organization_fallback)

        if fallbacks_to_add:
            current_count = len(result["entity_types"])
            needed_slots = len(fallbacks_to_add)

            # Se l'aggiunta supererebbe i 10, rimuovi alcuni tipi esistenti
            if current_count + needed_slots > MAX_ENTITY_TYPES:
                # Calcola quanti rimuovere
                to_remove = current_count + needed_slots - MAX_ENTITY_TYPES
                # Rimuovi dalla fine (mantieni i tipi specifici piu' importanti all'inizio)
                result["entity_types"] = result["entity_types"][:-to_remove]

            # Aggiungi i tipi di fallback
            result["entity_types"].extend(fallbacks_to_add)

        # Verifica finale per non superare i limiti (programmazione difensiva)
        if len(result["entity_types"]) > MAX_ENTITY_TYPES:
            result["entity_types"] = result["entity_types"][:MAX_ENTITY_TYPES]

        if len(result["edge_types"]) > MAX_EDGE_TYPES:
            result["edge_types"] = result["edge_types"][:MAX_EDGE_TYPES]

        return result

    def generate_python_code(self, ontology: Dict[str, Any]) -> str:
        """
        Converte la definizione dell'ontologia in codice Python (simile a ontology.py)

        Args:
            ontology: Definizione dell'ontologia

        Returns:
            Stringa di codice Python
        """
        code_lines = [
            '"""',
            'Definizioni personalizzate dei tipi di entita\'',
            'Generato automaticamente da MiroFish per la simulazione dell\'opinione pubblica sociale',
            '"""',
            '',
            'from pydantic import Field',
            'from zep_cloud.external_clients.ontology import EntityModel, EntityText, EdgeModel',
            '',
            '',
            '# ============== Definizioni dei tipi di entita\' ==============',
            '',
        ]

        # Genera i tipi di entita'
        for entity in ontology.get("entity_types", []):
            name = entity["name"]
            desc = entity.get("description", f"A {name} entity.")

            code_lines.append(f'class {name}(EntityModel):')
            code_lines.append(f'    """{desc}"""')

            attrs = entity.get("attributes", [])
            if attrs:
                for attr in attrs:
                    attr_name = attr["name"]
                    attr_desc = attr.get("description", attr_name)
                    code_lines.append(f'    {attr_name}: EntityText = Field(')
                    code_lines.append(f'        description="{attr_desc}",')
                    code_lines.append(f'        default=None')
                    code_lines.append(f'    )')
            else:
                code_lines.append('    pass')

            code_lines.append('')
            code_lines.append('')

        code_lines.append('# ============== Definizioni dei tipi di relazione ==============')
        code_lines.append('')

        # Genera i tipi di relazione
        for edge in ontology.get("edge_types", []):
            name = edge["name"]
            # Converte in nome classe PascalCase
            class_name = ''.join(word.capitalize() for word in name.split('_'))
            desc = edge.get("description", f"A {name} relationship.")

            code_lines.append(f'class {class_name}(EdgeModel):')
            code_lines.append(f'    """{desc}"""')

            attrs = edge.get("attributes", [])
            if attrs:
                for attr in attrs:
                    attr_name = attr["name"]
                    attr_desc = attr.get("description", attr_name)
                    code_lines.append(f'    {attr_name}: EntityText = Field(')
                    code_lines.append(f'        description="{attr_desc}",')
                    code_lines.append(f'        default=None')
                    code_lines.append(f'    )')
            else:
                code_lines.append('    pass')

            code_lines.append('')
            code_lines.append('')

        # Genera il dizionario dei tipi
        code_lines.append('# ============== Configurazione dei tipi ==============')
        code_lines.append('')
        code_lines.append('ENTITY_TYPES = {')
        for entity in ontology.get("entity_types", []):
            name = entity["name"]
            code_lines.append(f'    "{name}": {name},')
        code_lines.append('}')
        code_lines.append('')
        code_lines.append('EDGE_TYPES = {')
        for edge in ontology.get("edge_types", []):
            name = edge["name"]
            class_name = ''.join(word.capitalize() for word in name.split('_'))
            code_lines.append(f'    "{name}": {class_name},')
        code_lines.append('}')
        code_lines.append('')

        # Genera la mappatura source_targets delle relazioni
        code_lines.append('EDGE_SOURCE_TARGETS = {')
        for edge in ontology.get("edge_types", []):
            name = edge["name"]
            source_targets = edge.get("source_targets", [])
            if source_targets:
                st_list = ', '.join([
                    f'{{"source": "{st.get("source", "Entity")}", "target": "{st.get("target", "Entity")}"}}'
                    for st in source_targets
                ])
                code_lines.append(f'    "{name}": [{st_list}],')
        code_lines.append('}')

        return '\n'.join(code_lines)
