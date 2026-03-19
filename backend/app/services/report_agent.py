"""
Servizio Report Agent
Utilizza LangChain + Zep per implementare la generazione di report di simulazione in modalita' ReACT

Funzionalita':
1. Genera report basati sui requisiti di simulazione e sulle informazioni del grafo Zep
2. Prima pianifica la struttura dell'indice, poi genera sezione per sezione
3. Ogni sezione adotta la modalita' ReACT con piu' cicli di ragionamento e riflessione
4. Supporta la conversazione con l'utente, invocando autonomamente strumenti di ricerca durante il dialogo
"""

import os
import json
import time
import re
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from ..config import Config
from ..utils.llm_client import LLMClient
from ..utils.logger import get_logger
from .zep_tools import (
    ZepToolsService,
    SearchResult,
    InsightForgeResult,
    PanoramaResult,
    InterviewResult
)

logger = get_logger('mirofish.report_agent')


class ReportLogger:
    """
    Registratore di log dettagliati per il Report Agent

    Genera un file agent_log.jsonl nella cartella del report, registrando ogni azione dettagliata.
    Ogni riga e' un oggetto JSON completo, contenente timestamp, tipo di azione, contenuto dettagliato, ecc.
    """

    def __init__(self, report_id: str):
        """
        Inizializza il registratore di log

        Args:
            report_id: ID del report, usato per determinare il percorso del file di log
        """
        self.report_id = report_id
        self.log_file_path = os.path.join(
            Config.UPLOAD_FOLDER, 'reports', report_id, 'agent_log.jsonl'
        )
        self.start_time = datetime.now()
        self._ensure_log_file()

    def _ensure_log_file(self):
        """Assicura che la directory del file di log esista"""
        log_dir = os.path.dirname(self.log_file_path)
        os.makedirs(log_dir, exist_ok=True)

    def _get_elapsed_time(self) -> float:
        """Ottiene il tempo trascorso dall'inizio (in secondi)"""
        return (datetime.now() - self.start_time).total_seconds()

    def log(
        self,
        action: str,
        stage: str,
        details: Dict[str, Any],
        section_title: str = None,
        section_index: int = None
    ):
        """
        Registra una voce di log

        Args:
            action: Tipo di azione, come 'start', 'tool_call', 'llm_response', 'section_complete', ecc.
            stage: Fase corrente, come 'planning', 'generating', 'completed'
            details: Dizionario con il contenuto dettagliato, non troncato
            section_title: Titolo della sezione corrente (opzionale)
            section_index: Indice della sezione corrente (opzionale)
        """
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "elapsed_seconds": round(self._get_elapsed_time(), 2),
            "report_id": self.report_id,
            "action": action,
            "stage": stage,
            "section_title": section_title,
            "section_index": section_index,
            "details": details
        }

        # Scrittura in append nel file JSONL
        with open(self.log_file_path, 'a', encoding='utf-8') as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + '\n')

    def log_start(self, simulation_id: str, graph_id: str, simulation_requirement: str):
        """Registra l'inizio della generazione del report"""
        self.log(
            action="report_start",
            stage="pending",
            details={
                "simulation_id": simulation_id,
                "graph_id": graph_id,
                "simulation_requirement": simulation_requirement,
                "message": "Inizio del task di generazione del report"
            }
        )

    def log_planning_start(self):
        """Registra l'inizio della pianificazione della struttura"""
        self.log(
            action="planning_start",
            stage="planning",
            details={"message": "Inizio pianificazione della struttura del report"}
        )

    def log_planning_context(self, context: Dict[str, Any]):
        """Registra le informazioni di contesto ottenute durante la pianificazione"""
        self.log(
            action="planning_context",
            stage="planning",
            details={
                "message": "Recupero delle informazioni di contesto della simulazione",
                "context": context
            }
        )

    def log_planning_complete(self, outline_dict: Dict[str, Any]):
        """Registra il completamento della pianificazione della struttura"""
        self.log(
            action="planning_complete",
            stage="planning",
            details={
                "message": "Pianificazione della struttura completata",
                "outline": outline_dict
            }
        )

    def log_section_start(self, section_title: str, section_index: int):
        """Registra l'inizio della generazione di una sezione"""
        self.log(
            action="section_start",
            stage="generating",
            section_title=section_title,
            section_index=section_index,
            details={"message": f"Inizio generazione sezione: {section_title}"}
        )

    def log_react_thought(self, section_title: str, section_index: int, iteration: int, thought: str):
        """Registra il processo di ragionamento ReACT"""
        self.log(
            action="react_thought",
            stage="generating",
            section_title=section_title,
            section_index=section_index,
            details={
                "iteration": iteration,
                "thought": thought,
                "message": f"Ragionamento ReACT - Ciclo {iteration}"
            }
        )

    def log_tool_call(
        self,
        section_title: str,
        section_index: int,
        tool_name: str,
        parameters: Dict[str, Any],
        iteration: int
    ):
        """Registra la chiamata a uno strumento"""
        self.log(
            action="tool_call",
            stage="generating",
            section_title=section_title,
            section_index=section_index,
            details={
                "iteration": iteration,
                "tool_name": tool_name,
                "parameters": parameters,
                "message": f"Chiamata strumento: {tool_name}"
            }
        )

    def log_tool_result(
        self,
        section_title: str,
        section_index: int,
        tool_name: str,
        result: str,
        iteration: int
    ):
        """Registra il risultato della chiamata allo strumento (contenuto completo, non troncato)"""
        self.log(
            action="tool_result",
            stage="generating",
            section_title=section_title,
            section_index=section_index,
            details={
                "iteration": iteration,
                "tool_name": tool_name,
                "result": result,  # Risultato completo, non troncato
                "result_length": len(result),
                "message": f"Risultato restituito dallo strumento {tool_name}"
            }
        )

    def log_llm_response(
        self,
        section_title: str,
        section_index: int,
        response: str,
        iteration: int,
        has_tool_calls: bool,
        has_final_answer: bool
    ):
        """Registra la risposta del LLM (contenuto completo, non troncato)"""
        self.log(
            action="llm_response",
            stage="generating",
            section_title=section_title,
            section_index=section_index,
            details={
                "iteration": iteration,
                "response": response,  # Risposta completa, non troncata
                "response_length": len(response),
                "has_tool_calls": has_tool_calls,
                "has_final_answer": has_final_answer,
                "message": f"Risposta LLM (chiamata strumento: {has_tool_calls}, risposta finale: {has_final_answer})"
            }
        )

    def log_section_content(
        self,
        section_title: str,
        section_index: int,
        content: str,
        tool_calls_count: int
    ):
        """Registra il completamento della generazione del contenuto della sezione (solo contenuto, non rappresenta il completamento dell'intera sezione)"""
        self.log(
            action="section_content",
            stage="generating",
            section_title=section_title,
            section_index=section_index,
            details={
                "content": content,  # Contenuto completo, non troncato
                "content_length": len(content),
                "tool_calls_count": tool_calls_count,
                "message": f"Generazione contenuto sezione {section_title} completata"
            }
        )

    def log_section_full_complete(
        self,
        section_title: str,
        section_index: int,
        full_content: str
    ):
        """
        Registra il completamento della generazione della sezione

        Il frontend dovrebbe monitorare questo log per determinare se una sezione e' veramente completata e ottenere il contenuto completo
        """
        self.log(
            action="section_complete",
            stage="generating",
            section_title=section_title,
            section_index=section_index,
            details={
                "content": full_content,
                "content_length": len(full_content),
                "message": f"Generazione sezione {section_title} completata"
            }
        )

    def log_report_complete(self, total_sections: int, total_time_seconds: float):
        """Registra il completamento della generazione del report"""
        self.log(
            action="report_complete",
            stage="completed",
            details={
                "total_sections": total_sections,
                "total_time_seconds": round(total_time_seconds, 2),
                "message": "Generazione del report completata"
            }
        )

    def log_error(self, error_message: str, stage: str, section_title: str = None):
        """Registra un errore"""
        self.log(
            action="error",
            stage=stage,
            section_title=section_title,
            section_index=None,
            details={
                "error": error_message,
                "message": f"Errore riscontrato: {error_message}"
            }
        )


class ReportConsoleLogger:
    """
    Registratore di log console per il Report Agent

    Scrive i log in stile console (INFO, WARNING, ecc.) nel file console_log.txt nella cartella del report.
    Questi log sono diversi da agent_log.jsonl, essendo output in formato testo puro.
    """

    def __init__(self, report_id: str):
        """
        Inizializza il registratore di log console

        Args:
            report_id: ID del report, usato per determinare il percorso del file di log
        """
        self.report_id = report_id
        self.log_file_path = os.path.join(
            Config.UPLOAD_FOLDER, 'reports', report_id, 'console_log.txt'
        )
        self._ensure_log_file()
        self._file_handler = None
        self._setup_file_handler()

    def _ensure_log_file(self):
        """Assicura che la directory del file di log esista"""
        log_dir = os.path.dirname(self.log_file_path)
        os.makedirs(log_dir, exist_ok=True)

    def _setup_file_handler(self):
        """Configura il file handler per scrivere i log contemporaneamente su file"""
        import logging

        # Crea il file handler
        self._file_handler = logging.FileHandler(
            self.log_file_path,
            mode='a',
            encoding='utf-8'
        )
        self._file_handler.setLevel(logging.INFO)

        # Usa lo stesso formato conciso della console
        formatter = logging.Formatter(
            '[%(asctime)s] %(levelname)s: %(message)s',
            datefmt='%H:%M:%S'
        )
        self._file_handler.setFormatter(formatter)

        # Aggiunge ai logger relativi al report_agent
        loggers_to_attach = [
            'mirofish.report_agent',
            'mirofish.zep_tools',
        ]

        for logger_name in loggers_to_attach:
            target_logger = logging.getLogger(logger_name)
            # Evita di aggiungere duplicati
            if self._file_handler not in target_logger.handlers:
                target_logger.addHandler(self._file_handler)

    def close(self):
        """Chiude il file handler e lo rimuove dal logger"""
        import logging

        if self._file_handler:
            loggers_to_detach = [
                'mirofish.report_agent',
                'mirofish.zep_tools',
            ]

            for logger_name in loggers_to_detach:
                target_logger = logging.getLogger(logger_name)
                if self._file_handler in target_logger.handlers:
                    target_logger.removeHandler(self._file_handler)

            self._file_handler.close()
            self._file_handler = None

    def __del__(self):
        """Assicura la chiusura del file handler durante la distruzione"""
        self.close()


class ReportStatus(str, Enum):
    """Stato del report"""
    PENDING = "pending"
    PLANNING = "planning"
    GENERATING = "generating"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class ReportSection:
    """Sezione del report"""
    title: str
    content: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "content": self.content
        }

    def to_markdown(self, level: int = 2) -> str:
        """Converte in formato Markdown"""
        md = f"{'#' * level} {self.title}\n\n"
        if self.content:
            md += f"{self.content}\n\n"
        return md


@dataclass
class ReportOutline:
    """Struttura del report"""
    title: str
    summary: str
    sections: List[ReportSection]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "summary": self.summary,
            "sections": [s.to_dict() for s in self.sections]
        }

    def to_markdown(self) -> str:
        """Converte in formato Markdown"""
        md = f"# {self.title}\n\n"
        md += f"> {self.summary}\n\n"
        for section in self.sections:
            md += section.to_markdown()
        return md


@dataclass
class Report:
    """Report completo"""
    report_id: str
    simulation_id: str
    graph_id: str
    simulation_requirement: str
    status: ReportStatus
    outline: Optional[ReportOutline] = None
    markdown_content: str = ""
    created_at: str = ""
    completed_at: str = ""
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "report_id": self.report_id,
            "simulation_id": self.simulation_id,
            "graph_id": self.graph_id,
            "simulation_requirement": self.simulation_requirement,
            "status": self.status.value,
            "outline": self.outline.to_dict() if self.outline else None,
            "markdown_content": self.markdown_content,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
            "error": self.error
        }


# ═══════════════════════════════════════════════════════════════
# Costanti dei template dei Prompt
# ═══════════════════════════════════════════════════════════════

# ── Descrizioni degli strumenti ──

TOOL_DESC_INSIGHT_FORGE = """\
【Ricerca approfondita - Strumento di ricerca potente】
Questa e' la nostra potente funzione di ricerca, progettata per l'analisi approfondita. Essa:
1. Scompone automaticamente la tua domanda in sotto-domande multiple
2. Cerca informazioni nel grafo di simulazione da molteplici dimensioni
3. Integra i risultati di ricerca semantica, analisi delle entita' e tracciamento delle catene di relazioni
4. Restituisce i contenuti di ricerca piu' completi e approfonditi

【Scenari di utilizzo】
- Necessita' di analisi approfondita su un argomento
- Necessita' di comprendere molteplici aspetti di un evento
- Necessita' di ottenere materiale ricco a supporto delle sezioni del report

【Contenuto restituito】
- Testo originale dei fatti rilevanti (citabile direttamente)
- Insight sulle entita' principali
- Analisi delle catene di relazioni"""

TOOL_DESC_PANORAMA_SEARCH = """\
【Ricerca ad ampio raggio - Vista panoramica】
Questo strumento serve per ottenere una visione completa dei risultati della simulazione, particolarmente adatto per comprendere l'evoluzione degli eventi. Esso:
1. Recupera tutti i nodi e le relazioni pertinenti
2. Distingue tra fatti attualmente validi e fatti storici/scaduti
3. Ti aiuta a comprendere come si e' evoluta l'opinione pubblica

【Scenari di utilizzo】
- Necessita' di comprendere lo sviluppo completo di un evento
- Necessita' di confrontare i cambiamenti dell'opinione pubblica in diverse fasi
- Necessita' di ottenere informazioni complete su entita' e relazioni

【Contenuto restituito】
- Fatti attualmente validi (ultimi risultati della simulazione)
- Fatti storici/scaduti (registro dell'evoluzione)
- Tutte le entita' coinvolte"""

TOOL_DESC_QUICK_SEARCH = """\
【Ricerca semplice - Ricerca rapida】
Strumento di ricerca rapido e leggero, adatto per query informative semplici e dirette.

【Scenari di utilizzo】
- Necessita' di trovare rapidamente un'informazione specifica
- Necessita' di verificare un fatto
- Ricerca informativa semplice

【Contenuto restituito】
- Lista dei fatti piu' rilevanti rispetto alla query"""

TOOL_DESC_INTERVIEW_AGENTS = """\
【Intervista approfondita - Intervista reale agli Agent (doppia piattaforma)】
Invoca l'API di intervista dell'ambiente di simulazione OASIS per intervistare gli Agent in simulazione reale!
Non si tratta di una simulazione LLM, ma di una vera chiamata all'interfaccia di intervista per ottenere le risposte originali degli Agent simulati.
Per impostazione predefinita, l'intervista avviene simultaneamente su Twitter e Reddit, per ottenere prospettive piu' complete.

Flusso funzionale:
1. Legge automaticamente i file dei profili per conoscere tutti gli Agent simulati
2. Seleziona intelligentemente gli Agent piu' rilevanti per il tema dell'intervista (studenti, media, ufficiali, ecc.)
3. Genera automaticamente le domande dell'intervista
4. Invoca /api/simulation/interview/batch per condurre interviste reali su entrambe le piattaforme
5. Integra tutti i risultati dell'intervista, fornendo un'analisi multi-prospettiva

【Scenari di utilizzo】
- Necessita' di comprendere le opinioni da diverse prospettive (cosa pensano gli studenti? Cosa dicono i media? Qual e' la posizione ufficiale?)
- Necessita' di raccogliere opinioni e posizioni da piu' parti
- Necessita' di ottenere risposte reali dagli Agent simulati (dall'ambiente di simulazione OASIS)
- Vuoi rendere il report piu' vivace, includendo "trascrizioni di interviste"

【Contenuto restituito】
- Informazioni sull'identita' degli Agent intervistati
- Risposte degli Agent su entrambe le piattaforme Twitter e Reddit
- Citazioni chiave (citabili direttamente)
- Riepilogo dell'intervista e confronto delle opinioni

【Importante】E' necessario che l'ambiente di simulazione OASIS sia in esecuzione per utilizzare questa funzionalita'!"""

# ── Prompt per la pianificazione della struttura ──

PLAN_SYSTEM_PROMPT = """\
Sei un esperto nella redazione di «Report di Previsione Futura», dotato di una «visione divina» sul mondo simulato — puoi osservare il comportamento, le dichiarazioni e le interazioni di ogni Agent nella simulazione.

【Concetto fondamentale】
Abbiamo costruito un mondo simulato e vi abbiamo iniettato specifici «requisiti di simulazione» come variabili. I risultati dell'evoluzione del mondo simulato rappresentano previsioni su possibili scenari futuri. Cio' che stai osservando non sono "dati sperimentali", ma una "prova generale del futuro".

【Il tuo compito】
Redigere un «Report di Previsione Futura» che risponda a:
1. Nelle condizioni da noi impostate, cosa e' accaduto nel futuro?
2. Come hanno reagito e agito le varie categorie di Agent (gruppi di persone)?
3. Quali tendenze e rischi meritevoli di attenzione rivela questa simulazione?

【Posizionamento del report】
- Questo e' un report di previsione futura basato su simulazione, che rivela "se cosi', cosa succedera'"
- Focalizzato sui risultati della previsione: andamento degli eventi, reazioni dei gruppi, fenomeni emergenti, rischi potenziali
- Le parole e le azioni degli Agent nel mondo simulato sono previsioni del comportamento futuro dei gruppi umani
- Non e' un'analisi della situazione attuale del mondo reale
- Non e' una rassegna generica dell'opinione pubblica

【Limite sul numero di sezioni】
- Minimo 2 sezioni, massimo 5 sezioni
- Non servono sotto-sezioni, ogni sezione contiene direttamente il contenuto completo
- Il contenuto deve essere conciso, focalizzato sulle scoperte predittive chiave
- La struttura delle sezioni e' progettata autonomamente in base ai risultati della previsione

Produci la struttura del report in formato JSON, come segue:
{
    "title": "Titolo del report",
    "summary": "Riepilogo del report (una frase che sintetizza la scoperta predittiva chiave)",
    "sections": [
        {
            "title": "Titolo della sezione",
            "description": "Descrizione del contenuto della sezione"
        }
    ]
}

Nota: l'array sections deve contenere minimo 2, massimo 5 elementi!"""

PLAN_USER_PROMPT_TEMPLATE = """\
【Impostazione dello scenario predittivo】
La variabile iniettata nel mondo simulato (requisito di simulazione): {simulation_requirement}

【Scala del mondo simulato】
- Numero di entita' partecipanti alla simulazione: {total_nodes}
- Numero di relazioni generate tra le entita': {total_edges}
- Distribuzione dei tipi di entita': {entity_types}
- Numero di Agent attivi: {total_entities}

【Campione di fatti futuri previsti dalla simulazione】
{related_facts_json}

Osserva questa prova generale del futuro con «visione divina»:
1. Nelle condizioni da noi impostate, quale stato ha presentato il futuro?
2. Come hanno reagito e agito le varie categorie di persone (Agent)?
3. Quali tendenze future meritevoli di attenzione rivela questa simulazione?

In base ai risultati della previsione, progetta la struttura delle sezioni del report piu' adeguata.

【Promemoria】Numero di sezioni del report: minimo 2, massimo 5, il contenuto deve essere conciso e focalizzato sulle scoperte predittive chiave."""

# ── Prompt per la generazione delle sezioni ──

SECTION_SYSTEM_PROMPT_TEMPLATE = """\
Sei un esperto nella redazione di «Report di Previsione Futura» e stai scrivendo una sezione del report.

Titolo del report: {report_title}
Riepilogo del report: {report_summary}
Scenario predittivo (requisito di simulazione): {simulation_requirement}

Sezione da redigere: {section_title}

═══════════════════════════════════════════════════════════════
【Concetto fondamentale】
═══════════════════════════════════════════════════════════════

Il mondo simulato e' una prova generale del futuro. Abbiamo iniettato condizioni specifiche (requisiti di simulazione) nel mondo simulato,
e il comportamento e le interazioni degli Agent nella simulazione sono previsioni del comportamento futuro dei gruppi umani.

Il tuo compito e':
- Rivelare cosa e' accaduto nel futuro nelle condizioni impostate
- Prevedere come hanno reagito e agito le varie categorie di persone (Agent)
- Scoprire tendenze, rischi e opportunita' future meritevoli di attenzione

Non scrivere un'analisi della situazione attuale del mondo reale
Focalizzati su "cosa succedera' in futuro" — i risultati della simulazione sono il futuro previsto

═══════════════════════════════════════════════════════════════
【Regole piu' importanti - Da rispettare obbligatoriamente】
═══════════════════════════════════════════════════════════════

1. 【Devi invocare gli strumenti per osservare il mondo simulato】
   - Stai osservando la prova generale del futuro con «visione divina»
   - Tutto il contenuto deve provenire da eventi e parole/azioni degli Agent nel mondo simulato
   - E' vietato usare le tue conoscenze per scrivere il contenuto del report
   - Ogni sezione richiede almeno 3 chiamate agli strumenti (massimo 5) per osservare il mondo simulato, che rappresenta il futuro

2. 【Devi citare le parole e le azioni originali degli Agent】
   - Le dichiarazioni e i comportamenti degli Agent sono previsioni del comportamento futuro dei gruppi umani
   - Usa il formato di citazione nel report per mostrare queste previsioni, ad esempio:
     > "Un certo gruppo esprimerebbe: contenuto originale..."
   - Queste citazioni sono le prove fondamentali delle previsioni della simulazione

3. 【Coerenza linguistica - Il contenuto citato deve essere tradotto nella lingua del report】
   - Il contenuto restituito dagli strumenti potrebbe contenere espressioni in inglese o miste inglese-italiano
   - Se il requisito di simulazione e il materiale originale sono in italiano, il report deve essere scritto interamente in italiano
   - Quando citi contenuti in inglese o misti restituiti dagli strumenti, devi tradurli in italiano fluente prima di inserirli nel report
   - La traduzione deve preservare il significato originale, assicurando un'espressione naturale e scorrevole
   - Questa regola si applica sia al testo principale che ai blocchi di citazione (formato >)

4. 【Presentazione fedele dei risultati della previsione】
   - Il contenuto del report deve riflettere i risultati della simulazione che rappresentano il futuro nel mondo simulato
   - Non aggiungere informazioni che non esistono nella simulazione
   - Se le informazioni su un certo aspetto sono insufficienti, dichiaralo onestamente

═══════════════════════════════════════════════════════════════
【Specifiche di formato - Estremamente importanti!】
═══════════════════════════════════════════════════════════════

【Una sezione = unita' minima di contenuto】
- Ogni sezione e' l'unita' minima di suddivisione del report
- Vietato usare qualsiasi titolo Markdown (#, ##, ###, ####, ecc.) all'interno della sezione
- Vietato aggiungere il titolo principale della sezione all'inizio del contenuto
- Il titolo della sezione viene aggiunto automaticamente dal sistema, tu devi solo scrivere il testo puro
- Usa **grassetto**, separazione dei paragrafi, citazioni, liste per organizzare il contenuto, ma non usare titoli

【Esempio corretto】
```
Questa sezione analizza le dinamiche di diffusione dell'opinione pubblica dell'evento. Attraverso un'analisi approfondita dei dati di simulazione, abbiamo scoperto...

**Fase di innesco iniziale**

Weibo, come primo scenario dell'opinione pubblica, ha svolto la funzione centrale di prima diffusione delle informazioni:

> "Weibo ha contribuito al 68% del volume iniziale di diffusione..."

**Fase di amplificazione emotiva**

La piattaforma Douyin ha ulteriormente amplificato l'impatto dell'evento:

- Forte impatto visivo
- Alta risonanza emotiva
```

【Esempio errato】
```
## Riepilogo esecutivo          <- Errore! Non aggiungere alcun titolo
### Uno, Fase iniziale     <- Errore! Non usare ### per sotto-sezioni
#### 1.1 Analisi dettagliata   <- Errore! Non usare #### per sotto-divisioni

Questa sezione analizza...
```

═══════════════════════════════════════════════════════════════
【Strumenti di ricerca disponibili】(3-5 chiamate per sezione)
═══════════════════════════════════════════════════════════════

{tools_description}

【Suggerimenti per l'uso degli strumenti - Usa strumenti diversi in modo misto, non usare solo uno】
- insight_forge: Analisi approfondita, scomposizione automatica delle domande e ricerca multi-dimensionale di fatti e relazioni
- panorama_search: Ricerca panoramica ad ampio raggio, per comprendere il quadro completo dell'evento, la timeline e l'evoluzione
- quick_search: Verifica rapida di un punto informativo specifico
- interview_agents: Intervista gli Agent simulati, per ottenere opinioni in prima persona e reazioni reali da diversi ruoli

═══════════════════════════════════════════════════════════════
【Flusso di lavoro】
═══════════════════════════════════════════════════════════════

Ogni risposta puo' fare solo una delle due cose seguenti (non entrambe contemporaneamente):

Opzione A - Invocare uno strumento:
Esprimi il tuo ragionamento, poi invoca uno strumento nel seguente formato:
<tool_call>
{{"name": "nome_strumento", "parameters": {{"nome_parametro": "valore_parametro"}}}}
</tool_call>
Il sistema eseguira' lo strumento e ti restituira' il risultato. Non devi e non puoi scrivere tu stesso il risultato dello strumento.

Opzione B - Produrre il contenuto finale:
Quando hai ottenuto informazioni sufficienti tramite gli strumenti, inizia con "Final Answer:" per produrre il contenuto della sezione.

Severamente vietato:
- Includere contemporaneamente chiamata a strumento e Final Answer nella stessa risposta
- Inventare risultati degli strumenti (Observation), tutti i risultati degli strumenti sono iniettati dal sistema
- Invocare piu' di uno strumento per risposta

═══════════════════════════════════════════════════════════════
【Requisiti per il contenuto della sezione】
═══════════════════════════════════════════════════════════════

1. Il contenuto deve essere basato sui dati di simulazione recuperati dagli strumenti
2. Citare abbondantemente il testo originale per mostrare i risultati della simulazione
3. Usa il formato Markdown (ma e' vietato usare titoli):
   - Usa **testo in grassetto** per evidenziare i punti importanti (al posto dei sotto-titoli)
   - Usa liste (- o 1.2.3.) per organizzare i punti chiave
   - Usa righe vuote per separare i diversi paragrafi
   - Vietato usare #, ##, ###, #### o qualsiasi altra sintassi di titolo
4. 【Formato delle citazioni - Devono essere paragrafi autonomi】
   Le citazioni devono essere paragrafi indipendenti, con una riga vuota prima e dopo, non mescolate nel testo:

   Formato corretto:
   ```
   La risposta dell'istituzione e' stata considerata priva di sostanza.

   > "La modalita' di risposta dell'istituzione appare rigida e lenta nel contesto dei social media in rapida evoluzione."

   Questa valutazione riflette il malcontento generale del pubblico.
   ```

   Formato errato:
   ```
   La risposta dell'istituzione e' stata considerata priva di sostanza. > "La modalita' di risposta dell'istituzione..." Questa valutazione riflette...
   ```
5. Mantieni la coerenza logica con le altre sezioni
6. 【Evita ripetizioni】Leggi attentamente il contenuto delle sezioni gia' completate di seguito, non ripetere le stesse informazioni
7. 【Ribadisco】Non aggiungere alcun titolo! Usa **grassetto** al posto dei sotto-titoli"""

SECTION_USER_PROMPT_TEMPLATE = """\
Contenuto delle sezioni gia' completate (leggi attentamente per evitare ripetizioni):
{previous_content}

═══════════════════════════════════════════════════════════════
【Compito corrente】Redigere la sezione: {section_title}
═══════════════════════════════════════════════════════════════

【Promemoria importanti】
1. Leggi attentamente le sezioni gia' completate sopra, evita di ripetere gli stessi contenuti!
2. Prima di iniziare devi invocare gli strumenti per ottenere dati di simulazione
3. Usa strumenti diversi in modo misto, non usare solo uno
4. Il contenuto del report deve provenire dai risultati della ricerca, non usare le tue conoscenze

【Avviso formato - Da rispettare obbligatoriamente】
- Non scrivere alcun titolo (#, ##, ###, #### sono tutti vietati)
- Non scrivere "{section_title}" come incipit
- Il titolo della sezione viene aggiunto automaticamente dal sistema
- Scrivi direttamente il testo, usa **grassetto** al posto dei sotto-titoli

Per iniziare:
1. Prima ragiona (Thought) su quali informazioni servono per questa sezione
2. Poi invoca uno strumento (Action) per ottenere dati di simulazione
3. Dopo aver raccolto informazioni sufficienti, produci il Final Answer (solo testo, senza alcun titolo)"""

# ── Template dei messaggi nel ciclo ReACT ──

REACT_OBSERVATION_TEMPLATE = """\
Observation (risultati della ricerca):

═══ Risultato dello strumento {tool_name} ═══
{result}

═══════════════════════════════════════════════════════════════
Strumenti invocati {tool_calls_count}/{max_tool_calls} volte (usati: {used_tools_str}){unused_hint}
- Se le informazioni sono sufficienti: inizia con "Final Answer:" per produrre il contenuto della sezione (devi citare il testo originale sopra)
- Se servono piu' informazioni: invoca uno strumento per continuare la ricerca
═══════════════════════════════════════════════════════════════"""

REACT_INSUFFICIENT_TOOLS_MSG = (
    "【Attenzione】Hai invocato solo {tool_calls_count} volte gli strumenti, ne servono almeno {min_tool_calls}."
    "Invoca altri strumenti per ottenere piu' dati di simulazione, poi produci il Final Answer. {unused_hint}"
)

REACT_INSUFFICIENT_TOOLS_MSG_ALT = (
    "Attualmente hai invocato solo {tool_calls_count} volte gli strumenti, ne servono almeno {min_tool_calls}."
    "Invoca uno strumento per ottenere dati di simulazione. {unused_hint}"
)

REACT_TOOL_LIMIT_MSG = (
    "Il numero di chiamate agli strumenti ha raggiunto il limite ({tool_calls_count}/{max_tool_calls}), non puoi piu' invocare strumenti. "
    'Produci immediatamente il contenuto della sezione iniziando con "Final Answer:" basandoti sulle informazioni gia ottenute.'
)

REACT_UNUSED_TOOLS_HINT = "\nNon hai ancora usato: {unused_list}, si consiglia di provare strumenti diversi per ottenere informazioni da piu' angolazioni"

REACT_FORCE_FINAL_MSG = "Raggiunto il limite di chiamate agli strumenti, produci direttamente il Final Answer: e genera il contenuto della sezione."

# ── Prompt per la Chat ──

CHAT_SYSTEM_PROMPT_TEMPLATE = """\
Sei un assistente di previsione simulata conciso ed efficiente.

【Contesto】
Condizioni di previsione: {simulation_requirement}

【Report di analisi gia' generato】
{report_content}

【Regole】
1. Rispondi prioritariamente basandoti sul contenuto del report sopra
2. Rispondi direttamente alla domanda, evita ragionamenti prolissi
3. Invoca gli strumenti per cercare ulteriori dati solo quando il contenuto del report non e' sufficiente per rispondere
4. Le risposte devono essere concise, chiare e organizzate

【Strumenti disponibili】(usa solo quando necessario, massimo 1-2 invocazioni)
{tools_description}

【Formato di invocazione degli strumenti】
<tool_call>
{{"name": "nome_strumento", "parameters": {{"nome_parametro": "valore_parametro"}}}}
</tool_call>

【Stile di risposta】
- Conciso e diretto, senza lunghe dissertazioni
- Usa il formato > per citare contenuti chiave
- Dai prima la conclusione, poi spiega le ragioni"""

CHAT_OBSERVATION_SUFFIX = "\n\nRispondi alla domanda in modo conciso."


# ═══════════════════════════════════════════════════════════════
# Classe principale ReportAgent
# ═══════════════════════════════════════════════════════════════


class ReportAgent:
    """
    Report Agent - Agent per la generazione di report di simulazione

    Adotta la modalita' ReACT (Reasoning + Acting):
    1. Fase di pianificazione: analizza i requisiti di simulazione, pianifica la struttura dell'indice del report
    2. Fase di generazione: genera il contenuto sezione per sezione, ogni sezione puo' invocare strumenti piu' volte per ottenere informazioni
    3. Fase di riflessione: verifica la completezza e l'accuratezza del contenuto
    """

    # Numero massimo di chiamate agli strumenti (per sezione)
    MAX_TOOL_CALLS_PER_SECTION = 5

    # Numero massimo di cicli di riflessione
    MAX_REFLECTION_ROUNDS = 3

    # Numero massimo di chiamate agli strumenti nella conversazione
    MAX_TOOL_CALLS_PER_CHAT = 2

    def __init__(
        self,
        graph_id: str,
        simulation_id: str,
        simulation_requirement: str,
        llm_client: Optional[LLMClient] = None,
        zep_tools: Optional[ZepToolsService] = None
    ):
        """
        Inizializzazione del Report Agent

        Args:
            graph_id: ID del grafo
            simulation_id: ID della simulazione
            simulation_requirement: Descrizione dei requisiti di simulazione
            llm_client: Client LLM (opzionale)
            zep_tools: Servizio strumenti Zep (opzionale)
        """
        self.graph_id = graph_id
        self.simulation_id = simulation_id
        self.simulation_requirement = simulation_requirement

        self.llm = llm_client or LLMClient()
        self.zep_tools = zep_tools or ZepToolsService()

        # Definizione degli strumenti
        self.tools = self._define_tools()

        # Registratore di log (inizializzato in generate_report)
        self.report_logger: Optional[ReportLogger] = None
        # Registratore di log console (inizializzato in generate_report)
        self.console_logger: Optional[ReportConsoleLogger] = None

        logger.info(f"ReportAgent inizializzato: graph_id={graph_id}, simulation_id={simulation_id}")

    def _define_tools(self) -> Dict[str, Dict[str, Any]]:
        """Definisce gli strumenti disponibili"""
        return {
            "insight_forge": {
                "name": "insight_forge",
                "description": TOOL_DESC_INSIGHT_FORGE,
                "parameters": {
                    "query": "La domanda o l'argomento che vuoi analizzare in profondita'",
                    "report_context": "Contesto della sezione corrente del report (opzionale, aiuta a generare sotto-domande piu' precise)"
                }
            },
            "panorama_search": {
                "name": "panorama_search",
                "description": TOOL_DESC_PANORAMA_SEARCH,
                "parameters": {
                    "query": "Query di ricerca, usata per l'ordinamento per rilevanza",
                    "include_expired": "Se includere contenuti scaduti/storici (predefinito True)"
                }
            },
            "quick_search": {
                "name": "quick_search",
                "description": TOOL_DESC_QUICK_SEARCH,
                "parameters": {
                    "query": "Stringa di query di ricerca",
                    "limit": "Numero di risultati restituiti (opzionale, predefinito 10)"
                }
            },
            "interview_agents": {
                "name": "interview_agents",
                "description": TOOL_DESC_INTERVIEW_AGENTS,
                "parameters": {
                    "interview_topic": "Tema o requisito dell'intervista (es.: 'Comprendere l'opinione degli studenti sull'incidente della formaldeide nei dormitori')",
                    "max_agents": "Numero massimo di Agent da intervistare (opzionale, predefinito 5, massimo 10)"
                }
            }
        }

    def _execute_tool(self, tool_name: str, parameters: Dict[str, Any], report_context: str = "") -> str:
        """
        Esegue la chiamata a uno strumento

        Args:
            tool_name: Nome dello strumento
            parameters: Parametri dello strumento
            report_context: Contesto del report (usato per InsightForge)

        Returns:
            Risultato dell'esecuzione dello strumento (formato testo)
        """
        logger.info(f"Esecuzione strumento: {tool_name}, parametri: {parameters}")

        try:
            if tool_name == "insight_forge":
                query = parameters.get("query", "")
                ctx = parameters.get("report_context", "") or report_context
                result = self.zep_tools.insight_forge(
                    graph_id=self.graph_id,
                    query=query,
                    simulation_requirement=self.simulation_requirement,
                    report_context=ctx
                )
                return result.to_text()

            elif tool_name == "panorama_search":
                # Ricerca ad ampio raggio - Ottieni il quadro completo
                query = parameters.get("query", "")
                include_expired = parameters.get("include_expired", True)
                if isinstance(include_expired, str):
                    include_expired = include_expired.lower() in ['true', '1', 'yes']
                result = self.zep_tools.panorama_search(
                    graph_id=self.graph_id,
                    query=query,
                    include_expired=include_expired
                )
                return result.to_text()

            elif tool_name == "quick_search":
                # Ricerca semplice - Ricerca rapida
                query = parameters.get("query", "")
                limit = parameters.get("limit", 10)
                if isinstance(limit, str):
                    limit = int(limit)
                result = self.zep_tools.quick_search(
                    graph_id=self.graph_id,
                    query=query,
                    limit=limit
                )
                return result.to_text()

            elif tool_name == "interview_agents":
                # Intervista approfondita - Invoca l'API reale di intervista OASIS per ottenere risposte dagli Agent simulati (doppia piattaforma)
                interview_topic = parameters.get("interview_topic", parameters.get("query", ""))
                max_agents = parameters.get("max_agents", 5)
                if isinstance(max_agents, str):
                    max_agents = int(max_agents)
                max_agents = min(max_agents, 10)
                result = self.zep_tools.interview_agents(
                    simulation_id=self.simulation_id,
                    interview_requirement=interview_topic,
                    simulation_requirement=self.simulation_requirement,
                    max_agents=max_agents
                )
                return result.to_text()

            # ========== Strumenti legacy per compatibilita' (reindirizzamento interno ai nuovi strumenti) ==========

            elif tool_name == "search_graph":
                # Reindirizzamento a quick_search
                logger.info("search_graph reindirizzato a quick_search")
                return self._execute_tool("quick_search", parameters, report_context)

            elif tool_name == "get_graph_statistics":
                result = self.zep_tools.get_graph_statistics(self.graph_id)
                return json.dumps(result, ensure_ascii=False, indent=2)

            elif tool_name == "get_entity_summary":
                entity_name = parameters.get("entity_name", "")
                result = self.zep_tools.get_entity_summary(
                    graph_id=self.graph_id,
                    entity_name=entity_name
                )
                return json.dumps(result, ensure_ascii=False, indent=2)

            elif tool_name == "get_simulation_context":
                # Reindirizzamento a insight_forge, perche' e' piu' potente
                logger.info("get_simulation_context reindirizzato a insight_forge")
                query = parameters.get("query", self.simulation_requirement)
                return self._execute_tool("insight_forge", {"query": query}, report_context)

            elif tool_name == "get_entities_by_type":
                entity_type = parameters.get("entity_type", "")
                nodes = self.zep_tools.get_entities_by_type(
                    graph_id=self.graph_id,
                    entity_type=entity_type
                )
                result = [n.to_dict() for n in nodes]
                return json.dumps(result, ensure_ascii=False, indent=2)

            else:
                return f"Strumento sconosciuto: {tool_name}. Usa uno dei seguenti strumenti: insight_forge, panorama_search, quick_search"

        except Exception as e:
            logger.error(f"Esecuzione strumento fallita: {tool_name}, errore: {str(e)}")
            return f"Esecuzione strumento fallita: {str(e)}"

    # Insieme dei nomi di strumenti validi, usato per la validazione nel parsing di fallback del JSON non incapsulato
    VALID_TOOL_NAMES = {"insight_forge", "panorama_search", "quick_search", "interview_agents"}

    def _parse_tool_calls(self, response: str) -> List[Dict[str, Any]]:
        """
        Analizza le chiamate agli strumenti dalla risposta del LLM

        Formati supportati (per priorita'):
        1. <tool_call>{"name": "tool_name", "parameters": {...}}</tool_call>
        2. JSON non incapsulato (la risposta intera o una singola riga e' un JSON di chiamata strumento)
        """
        tool_calls = []

        # Formato 1: Stile XML (formato standard)
        xml_pattern = r'<tool_call>\s*(\{.*?\})\s*</tool_call>'
        for match in re.finditer(xml_pattern, response, re.DOTALL):
            try:
                call_data = json.loads(match.group(1))
                tool_calls.append(call_data)
            except json.JSONDecodeError:
                pass

        if tool_calls:
            return tool_calls

        # Formato 2: Fallback - Il LLM ha prodotto direttamente un JSON non incapsulato (senza tag <tool_call>)
        # Tentato solo quando il formato 1 non ha trovato corrispondenze, per evitare false corrispondenze con JSON nel testo
        stripped = response.strip()
        if stripped.startswith('{') and stripped.endswith('}'):
            try:
                call_data = json.loads(stripped)
                if self._is_valid_tool_call(call_data):
                    tool_calls.append(call_data)
                    return tool_calls
            except json.JSONDecodeError:
                pass

        # La risposta potrebbe contenere testo di ragionamento + JSON non incapsulato, prova a estrarre l'ultimo oggetto JSON
        json_pattern = r'(\{"(?:name|tool)"\s*:.*?\})\s*$'
        match = re.search(json_pattern, stripped, re.DOTALL)
        if match:
            try:
                call_data = json.loads(match.group(1))
                if self._is_valid_tool_call(call_data):
                    tool_calls.append(call_data)
            except json.JSONDecodeError:
                pass

        return tool_calls

    def _is_valid_tool_call(self, data: dict) -> bool:
        """Verifica se il JSON analizzato e' una chiamata strumento valida"""
        # Supporta entrambi i formati: {"name": ..., "parameters": ...} e {"tool": ..., "params": ...}
        tool_name = data.get("name") or data.get("tool")
        if tool_name and tool_name in self.VALID_TOOL_NAMES:
            # Uniforma i nomi delle chiavi a name / parameters
            if "tool" in data:
                data["name"] = data.pop("tool")
            if "params" in data and "parameters" not in data:
                data["parameters"] = data.pop("params")
            return True
        return False

    def _get_tools_description(self) -> str:
        """Genera il testo descrittivo degli strumenti"""
        desc_parts = ["Strumenti disponibili:"]
        for name, tool in self.tools.items():
            params_desc = ", ".join([f"{k}: {v}" for k, v in tool["parameters"].items()])
            desc_parts.append(f"- {name}: {tool['description']}")
            if params_desc:
                desc_parts.append(f"  Parametri: {params_desc}")
        return "\n".join(desc_parts)

    def plan_outline(
        self,
        progress_callback: Optional[Callable] = None
    ) -> ReportOutline:
        """
        Pianifica la struttura del report

        Usa il LLM per analizzare i requisiti di simulazione e pianificare la struttura dell'indice del report

        Args:
            progress_callback: Funzione di callback per il progresso

        Returns:
            ReportOutline: Struttura del report
        """
        logger.info("Inizio pianificazione della struttura del report...")

        if progress_callback:
            progress_callback("planning", 0, "Analisi dei requisiti di simulazione in corso...")

        # Prima ottiene il contesto della simulazione
        context = self.zep_tools.get_simulation_context(
            graph_id=self.graph_id,
            simulation_requirement=self.simulation_requirement
        )

        if progress_callback:
            progress_callback("planning", 30, "Generazione della struttura del report in corso...")

        system_prompt = PLAN_SYSTEM_PROMPT
        user_prompt = PLAN_USER_PROMPT_TEMPLATE.format(
            simulation_requirement=self.simulation_requirement,
            total_nodes=context.get('graph_statistics', {}).get('total_nodes', 0),
            total_edges=context.get('graph_statistics', {}).get('total_edges', 0),
            entity_types=list(context.get('graph_statistics', {}).get('entity_types', {}).keys()),
            total_entities=context.get('total_entities', 0),
            related_facts_json=json.dumps(context.get('related_facts', [])[:10], ensure_ascii=False, indent=2),
        )

        try:
            response = self.llm.chat_json(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.3
            )

            if progress_callback:
                progress_callback("planning", 80, "Analisi della struttura in corso...")

            # Analisi della struttura
            sections = []
            for section_data in response.get("sections", []):
                sections.append(ReportSection(
                    title=section_data.get("title", ""),
                    content=""
                ))

            outline = ReportOutline(
                title=response.get("title", "Report di Analisi della Simulazione"),
                summary=response.get("summary", ""),
                sections=sections
            )

            if progress_callback:
                progress_callback("planning", 100, "Pianificazione della struttura completata")

            logger.info(f"Pianificazione della struttura completata: {len(sections)} sezioni")
            return outline

        except Exception as e:
            logger.error(f"Pianificazione della struttura fallita: {str(e)}")
            # Restituisce una struttura predefinita (3 sezioni, come fallback)
            return ReportOutline(
                title="Report di Previsione Futura",
                summary="Analisi delle tendenze e dei rischi futuri basata sulla previsione simulata",
                sections=[
                    ReportSection(title="Scenario predittivo e scoperte chiave"),
                    ReportSection(title="Analisi predittiva del comportamento dei gruppi"),
                    ReportSection(title="Prospettive sulle tendenze e avvisi sui rischi")
                ]
            )

    def _generate_section_react(
        self,
        section: ReportSection,
        outline: ReportOutline,
        previous_sections: List[str],
        progress_callback: Optional[Callable] = None,
        section_index: int = 0
    ) -> str:
        """
        Genera il contenuto di una singola sezione usando la modalita' ReACT

        Ciclo ReACT:
        1. Thought (Ragionamento) - Analizza quali informazioni sono necessarie
        2. Action (Azione) - Invoca strumenti per ottenere informazioni
        3. Observation (Osservazione) - Analizza i risultati restituiti dagli strumenti
        4. Ripete fino a quando le informazioni sono sufficienti o si raggiunge il numero massimo
        5. Final Answer (Risposta finale) - Genera il contenuto della sezione

        Args:
            section: La sezione da generare
            outline: La struttura completa
            previous_sections: Contenuto delle sezioni precedenti (per mantenere la coerenza)
            progress_callback: Callback per il progresso
            section_index: Indice della sezione (per la registrazione dei log)

        Returns:
            Contenuto della sezione (formato Markdown)
        """
        logger.info(f"Generazione ReACT della sezione: {section.title}")

        # Registra il log di inizio sezione
        if self.report_logger:
            self.report_logger.log_section_start(section.title, section_index)

        system_prompt = SECTION_SYSTEM_PROMPT_TEMPLATE.format(
            report_title=outline.title,
            report_summary=outline.summary,
            simulation_requirement=self.simulation_requirement,
            section_title=section.title,
            tools_description=self._get_tools_description(),
        )

        # Costruisce il prompt utente - ogni sezione completata viene passata con un massimo di 4000 caratteri
        if previous_sections:
            previous_parts = []
            for sec in previous_sections:
                # Ogni sezione massimo 4000 caratteri
                truncated = sec[:4000] + "..." if len(sec) > 4000 else sec
                previous_parts.append(truncated)
            previous_content = "\n\n---\n\n".join(previous_parts)
        else:
            previous_content = "(Questa e' la prima sezione)"

        user_prompt = SECTION_USER_PROMPT_TEMPLATE.format(
            previous_content=previous_content,
            section_title=section.title,
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]

        # Ciclo ReACT
        tool_calls_count = 0
        max_iterations = 5  # Numero massimo di iterazioni
        min_tool_calls = 3  # Numero minimo di chiamate agli strumenti
        conflict_retries = 0  # Conteggio conflitti consecutivi tra chiamata strumento e Final Answer
        used_tools = set()  # Registra gli strumenti gia' invocati
        all_tools = {"insight_forge", "panorama_search", "quick_search", "interview_agents"}

        # Contesto del report, usato per la generazione delle sotto-domande di InsightForge
        report_context = f"Titolo della sezione: {section.title}\nRequisito di simulazione: {self.simulation_requirement}"

        for iteration in range(max_iterations):
            if progress_callback:
                progress_callback(
                    "generating",
                    int((iteration / max_iterations) * 100),
                    f"Ricerca approfondita e redazione in corso ({tool_calls_count}/{self.MAX_TOOL_CALLS_PER_SECTION})"
                )

            # Chiamata al LLM
            response = self.llm.chat(
                messages=messages,
                temperature=0.5,
                max_tokens=4096
            )

            # Verifica se il LLM ha restituito None (eccezione API o contenuto vuoto)
            if response is None:
                logger.warning(f"Sezione {section.title} iterazione {iteration + 1}: il LLM ha restituito None")
                # Se ci sono ancora iterazioni disponibili, aggiungi un messaggio e riprova
                if iteration < max_iterations - 1:
                    messages.append({"role": "assistant", "content": "(risposta vuota)"})
                    messages.append({"role": "user", "content": "Per favore continua a generare il contenuto."})
                    continue
                # Anche l'ultima iterazione ha restituito None, esci dal ciclo per la chiusura forzata
                break

            logger.debug(f"Risposta LLM: {response[:200]}...")

            # Analizza una volta, riutilizza il risultato
            tool_calls = self._parse_tool_calls(response)
            has_tool_calls = bool(tool_calls)
            has_final_answer = "Final Answer:" in response

            # ── Gestione conflitto: il LLM ha prodotto sia chiamata strumento che Final Answer ──
            if has_tool_calls and has_final_answer:
                conflict_retries += 1
                logger.warning(
                    f"Sezione {section.title} ciclo {iteration+1}: "
                    f"il LLM ha prodotto sia chiamata strumento che Final Answer (conflitto n. {conflict_retries})"
                )

                if conflict_retries <= 2:
                    # Prime due volte: scarta questa risposta, chiedi al LLM di rispondere di nuovo
                    messages.append({"role": "assistant", "content": response})
                    messages.append({
                        "role": "user",
                        "content": (
                            "【Errore di formato】Hai incluso contemporaneamente una chiamata strumento e il Final Answer nella stessa risposta, cio' non e' permesso.\n"
                            "Ogni risposta puo' fare solo una delle due cose seguenti:\n"
                            "- Invocare uno strumento (produrre un blocco <tool_call>, senza scrivere Final Answer)\n"
                            "- Produrre il contenuto finale (iniziare con 'Final Answer:', senza includere <tool_call>)\n"
                            "Per favore rispondi di nuovo, facendo solo una delle due cose."
                        ),
                    })
                    continue
                else:
                    # Terza volta: gestione degradata, tronca alla prima chiamata strumento, esecuzione forzata
                    logger.warning(
                        f"Sezione {section.title}: {conflict_retries} conflitti consecutivi, "
                        "degradazione a troncamento ed esecuzione della prima chiamata strumento"
                    )
                    first_tool_end = response.find('</tool_call>')
                    if first_tool_end != -1:
                        response = response[:first_tool_end + len('</tool_call>')]
                        tool_calls = self._parse_tool_calls(response)
                        has_tool_calls = bool(tool_calls)
                    has_final_answer = False
                    conflict_retries = 0

            # Registra il log della risposta LLM
            if self.report_logger:
                self.report_logger.log_llm_response(
                    section_title=section.title,
                    section_index=section_index,
                    response=response,
                    iteration=iteration + 1,
                    has_tool_calls=has_tool_calls,
                    has_final_answer=has_final_answer
                )

            # ── Caso 1: il LLM ha prodotto il Final Answer ──
            if has_final_answer:
                # Numero insufficiente di chiamate agli strumenti, rifiuta e chiedi di continuare a usare gli strumenti
                if tool_calls_count < min_tool_calls:
                    messages.append({"role": "assistant", "content": response})
                    unused_tools = all_tools - used_tools
                    unused_hint = f"(Questi strumenti non sono ancora stati usati, si consiglia di provarli: {', '.join(unused_tools)})" if unused_tools else ""
                    messages.append({
                        "role": "user",
                        "content": REACT_INSUFFICIENT_TOOLS_MSG.format(
                            tool_calls_count=tool_calls_count,
                            min_tool_calls=min_tool_calls,
                            unused_hint=unused_hint,
                        ),
                    })
                    continue

                # Conclusione normale
                final_answer = response.split("Final Answer:")[-1].strip()
                logger.info(f"Sezione {section.title} generazione completata (chiamate strumenti: {tool_calls_count})")

                if self.report_logger:
                    self.report_logger.log_section_content(
                        section_title=section.title,
                        section_index=section_index,
                        content=final_answer,
                        tool_calls_count=tool_calls_count
                    )
                return final_answer

            # ── Caso 2: il LLM ha tentato di invocare uno strumento ──
            if has_tool_calls:
                # Quota strumenti esaurita -> informa chiaramente, richiedi il Final Answer
                if tool_calls_count >= self.MAX_TOOL_CALLS_PER_SECTION:
                    messages.append({"role": "assistant", "content": response})
                    messages.append({
                        "role": "user",
                        "content": REACT_TOOL_LIMIT_MSG.format(
                            tool_calls_count=tool_calls_count,
                            max_tool_calls=self.MAX_TOOL_CALLS_PER_SECTION,
                        ),
                    })
                    continue

                # Esegui solo la prima chiamata strumento
                call = tool_calls[0]
                if len(tool_calls) > 1:
                    logger.info(f"Il LLM ha tentato di invocare {len(tool_calls)} strumenti, eseguendo solo il primo: {call['name']}")

                if self.report_logger:
                    self.report_logger.log_tool_call(
                        section_title=section.title,
                        section_index=section_index,
                        tool_name=call["name"],
                        parameters=call.get("parameters", {}),
                        iteration=iteration + 1
                    )

                result = self._execute_tool(
                    call["name"],
                    call.get("parameters", {}),
                    report_context=report_context
                )

                if self.report_logger:
                    self.report_logger.log_tool_result(
                        section_title=section.title,
                        section_index=section_index,
                        tool_name=call["name"],
                        result=result,
                        iteration=iteration + 1
                    )

                tool_calls_count += 1
                used_tools.add(call['name'])

                # Costruisci il suggerimento sugli strumenti non utilizzati
                unused_tools = all_tools - used_tools
                unused_hint = ""
                if unused_tools and tool_calls_count < self.MAX_TOOL_CALLS_PER_SECTION:
                    unused_hint = REACT_UNUSED_TOOLS_HINT.format(unused_list=", ".join(unused_tools))

                messages.append({"role": "assistant", "content": response})
                messages.append({
                    "role": "user",
                    "content": REACT_OBSERVATION_TEMPLATE.format(
                        tool_name=call["name"],
                        result=result,
                        tool_calls_count=tool_calls_count,
                        max_tool_calls=self.MAX_TOOL_CALLS_PER_SECTION,
                        used_tools_str=", ".join(used_tools),
                        unused_hint=unused_hint,
                    ),
                })
                continue

            # ── Caso 3: ne' chiamata strumento ne' Final Answer ──
            messages.append({"role": "assistant", "content": response})

            if tool_calls_count < min_tool_calls:
                # Numero insufficiente di chiamate agli strumenti, suggerisci strumenti non ancora usati
                unused_tools = all_tools - used_tools
                unused_hint = f"(Questi strumenti non sono ancora stati usati, si consiglia di provarli: {', '.join(unused_tools)})" if unused_tools else ""

                messages.append({
                    "role": "user",
                    "content": REACT_INSUFFICIENT_TOOLS_MSG_ALT.format(
                        tool_calls_count=tool_calls_count,
                        min_tool_calls=min_tool_calls,
                        unused_hint=unused_hint,
                    ),
                })
                continue

            # Le chiamate agli strumenti sono sufficienti, il LLM ha prodotto contenuto ma senza il prefisso "Final Answer:"
            # Accetta direttamente questo contenuto come risposta finale, senza ulteriori iterazioni vuote
            logger.info(f"Sezione {section.title} prefisso 'Final Answer:' non rilevato, accettazione diretta dell'output LLM come contenuto finale (chiamate strumenti: {tool_calls_count})")
            final_answer = response.strip()

            if self.report_logger:
                self.report_logger.log_section_content(
                    section_title=section.title,
                    section_index=section_index,
                    content=final_answer,
                    tool_calls_count=tool_calls_count
                )
            return final_answer

        # Raggiunto il numero massimo di iterazioni, generazione forzata del contenuto
        logger.warning(f"Sezione {section.title} raggiunto il numero massimo di iterazioni, generazione forzata")
        messages.append({"role": "user", "content": REACT_FORCE_FINAL_MSG})

        response = self.llm.chat(
            messages=messages,
            temperature=0.5,
            max_tokens=4096
        )

        # Verifica se il LLM ha restituito None durante la chiusura forzata
        if response is None:
            logger.error(f"Sezione {section.title} il LLM ha restituito None durante la chiusura forzata, uso del messaggio di errore predefinito")
            final_answer = f"(Generazione di questa sezione fallita: il LLM ha restituito una risposta vuota, si prega di riprovare)"
        elif "Final Answer:" in response:
            final_answer = response.split("Final Answer:")[-1].strip()
        else:
            final_answer = response

        # Registra il log di completamento della generazione del contenuto della sezione
        if self.report_logger:
            self.report_logger.log_section_content(
                section_title=section.title,
                section_index=section_index,
                content=final_answer,
                tool_calls_count=tool_calls_count
            )

        return final_answer

    def generate_report(
        self,
        progress_callback: Optional[Callable[[str, int, str], None]] = None,
        report_id: Optional[str] = None
    ) -> Report:
        """
        Genera il report completo (output in tempo reale sezione per sezione)

        Ogni sezione viene salvata immediatamente su file dopo il completamento, senza attendere il completamento dell'intero report.
        Struttura dei file:
        reports/{report_id}/
            meta.json       - Metadati del report
            outline.json    - Struttura del report
            progress.json   - Progresso della generazione
            section_01.md   - Sezione 1
            section_02.md   - Sezione 2
            ...
            full_report.md  - Report completo

        Args:
            progress_callback: Funzione di callback per il progresso (stage, progress, message)
            report_id: ID del report (opzionale, se non fornito viene generato automaticamente)

        Returns:
            Report: Report completo
        """
        import uuid

        # Se non e' stato fornito un report_id, ne genera uno automaticamente
        if not report_id:
            report_id = f"report_{uuid.uuid4().hex[:12]}"
        start_time = datetime.now()

        report = Report(
            report_id=report_id,
            simulation_id=self.simulation_id,
            graph_id=self.graph_id,
            simulation_requirement=self.simulation_requirement,
            status=ReportStatus.PENDING,
            created_at=datetime.now().isoformat()
        )

        # Lista dei titoli delle sezioni completate (per il tracciamento del progresso)
        completed_section_titles = []

        try:
            # Inizializzazione: crea la cartella del report e salva lo stato iniziale
            ReportManager._ensure_report_folder(report_id)

            # Inizializza il registratore di log (log strutturato agent_log.jsonl)
            self.report_logger = ReportLogger(report_id)
            self.report_logger.log_start(
                simulation_id=self.simulation_id,
                graph_id=self.graph_id,
                simulation_requirement=self.simulation_requirement
            )

            # Inizializza il registratore di log console (console_log.txt)
            self.console_logger = ReportConsoleLogger(report_id)

            ReportManager.update_progress(
                report_id, "pending", 0, "Inizializzazione del report...",
                completed_sections=[]
            )
            ReportManager.save_report(report)

            # Fase 1: Pianificazione della struttura
            report.status = ReportStatus.PLANNING
            ReportManager.update_progress(
                report_id, "planning", 5, "Inizio pianificazione della struttura del report...",
                completed_sections=[]
            )

            # Registra il log di inizio pianificazione
            self.report_logger.log_planning_start()

            if progress_callback:
                progress_callback("planning", 0, "Inizio pianificazione della struttura del report...")

            outline = self.plan_outline(
                progress_callback=lambda stage, prog, msg:
                    progress_callback(stage, prog // 5, msg) if progress_callback else None
            )
            report.outline = outline

            # Registra il log di completamento della pianificazione
            self.report_logger.log_planning_complete(outline.to_dict())

            # Salva la struttura su file
            ReportManager.save_outline(report_id, outline)
            ReportManager.update_progress(
                report_id, "planning", 15, f"Pianificazione della struttura completata, {len(outline.sections)} sezioni in totale",
                completed_sections=[]
            )
            ReportManager.save_report(report)

            logger.info(f"Struttura salvata su file: {report_id}/outline.json")

            # Fase 2: Generazione sezione per sezione (salvataggio per sezione)
            report.status = ReportStatus.GENERATING

            total_sections = len(outline.sections)
            generated_sections = []  # Salva il contenuto per il contesto

            for i, section in enumerate(outline.sections):
                section_num = i + 1
                base_progress = 20 + int((i / total_sections) * 70)

                # Aggiorna il progresso
                ReportManager.update_progress(
                    report_id, "generating", base_progress,
                    f"Generazione sezione in corso: {section.title} ({section_num}/{total_sections})",
                    current_section=section.title,
                    completed_sections=completed_section_titles
                )

                if progress_callback:
                    progress_callback(
                        "generating",
                        base_progress,
                        f"Generazione sezione in corso: {section.title} ({section_num}/{total_sections})"
                    )

                # Genera il contenuto della sezione principale
                section_content = self._generate_section_react(
                    section=section,
                    outline=outline,
                    previous_sections=generated_sections,
                    progress_callback=lambda stage, prog, msg:
                        progress_callback(
                            stage,
                            base_progress + int(prog * 0.7 / total_sections),
                            msg
                        ) if progress_callback else None,
                    section_index=section_num
                )

                section.content = section_content
                generated_sections.append(f"## {section.title}\n\n{section_content}")

                # Salva la sezione
                ReportManager.save_section(report_id, section_num, section)
                completed_section_titles.append(section.title)

                # Registra il log di completamento della sezione
                full_section_content = f"## {section.title}\n\n{section_content}"

                if self.report_logger:
                    self.report_logger.log_section_full_complete(
                        section_title=section.title,
                        section_index=section_num,
                        full_content=full_section_content.strip()
                    )

                logger.info(f"Sezione salvata: {report_id}/section_{section_num:02d}.md")

                # Aggiorna il progresso
                ReportManager.update_progress(
                    report_id, "generating",
                    base_progress + int(70 / total_sections),
                    f"Sezione {section.title} completata",
                    current_section=None,
                    completed_sections=completed_section_titles
                )

            # Fase 3: Assemblaggio del report completo
            if progress_callback:
                progress_callback("generating", 95, "Assemblaggio del report completo in corso...")

            ReportManager.update_progress(
                report_id, "generating", 95, "Assemblaggio del report completo in corso...",
                completed_sections=completed_section_titles
            )

            # Usa ReportManager per assemblare il report completo
            report.markdown_content = ReportManager.assemble_full_report(report_id, outline)
            report.status = ReportStatus.COMPLETED
            report.completed_at = datetime.now().isoformat()

            # Calcola il tempo totale
            total_time_seconds = (datetime.now() - start_time).total_seconds()

            # Registra il log di completamento del report
            if self.report_logger:
                self.report_logger.log_report_complete(
                    total_sections=total_sections,
                    total_time_seconds=total_time_seconds
                )

            # Salva il report finale
            ReportManager.save_report(report)
            ReportManager.update_progress(
                report_id, "completed", 100, "Generazione del report completata",
                completed_sections=completed_section_titles
            )

            if progress_callback:
                progress_callback("completed", 100, "Generazione del report completata")

            logger.info(f"Generazione del report completata: {report_id}")

            # Chiudi il registratore di log console
            if self.console_logger:
                self.console_logger.close()
                self.console_logger = None

            return report

        except Exception as e:
            logger.error(f"Generazione del report fallita: {str(e)}")
            report.status = ReportStatus.FAILED
            report.error = str(e)

            # Registra il log di errore
            if self.report_logger:
                self.report_logger.log_error(str(e), "failed")

            # Salva lo stato di fallimento
            try:
                ReportManager.save_report(report)
                ReportManager.update_progress(
                    report_id, "failed", -1, f"Generazione del report fallita: {str(e)}",
                    completed_sections=completed_section_titles
                )
            except Exception:
                pass  # Ignora gli errori di salvataggio

            # Chiudi il registratore di log console
            if self.console_logger:
                self.console_logger.close()
                self.console_logger = None

            return report

    def chat(
        self,
        message: str,
        chat_history: List[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """
        Conversazione con il Report Agent

        Durante la conversazione l'Agent puo' invocare autonomamente strumenti di ricerca per rispondere alle domande

        Args:
            message: Messaggio dell'utente
            chat_history: Cronologia della conversazione

        Returns:
            {
                "response": "Risposta dell'Agent",
                "tool_calls": [Lista degli strumenti invocati],
                "sources": [Fonti delle informazioni]
            }
        """
        logger.info(f"Conversazione Report Agent: {message[:50]}...")

        chat_history = chat_history or []

        # Ottiene il contenuto del report gia' generato
        report_content = ""
        try:
            report = ReportManager.get_report_by_simulation(self.simulation_id)
            if report and report.markdown_content:
                # Limita la lunghezza del report per evitare un contesto troppo lungo
                report_content = report.markdown_content[:15000]
                if len(report.markdown_content) > 15000:
                    report_content += "\n\n... [Contenuto del report troncato] ..."
        except Exception as e:
            logger.warning(f"Recupero del contenuto del report fallito: {e}")

        system_prompt = CHAT_SYSTEM_PROMPT_TEMPLATE.format(
            simulation_requirement=self.simulation_requirement,
            report_content=report_content if report_content else "(Nessun report disponibile)",
            tools_description=self._get_tools_description(),
        )

        # Costruisci i messaggi
        messages = [{"role": "system", "content": system_prompt}]

        # Aggiungi la cronologia della conversazione
        for h in chat_history[-10:]:  # Limita la lunghezza della cronologia
            messages.append(h)

        # Aggiungi il messaggio dell'utente
        messages.append({
            "role": "user",
            "content": message
        })

        # Ciclo ReACT (versione semplificata)
        tool_calls_made = []
        max_iterations = 2  # Riduci il numero di iterazioni

        for iteration in range(max_iterations):
            response = self.llm.chat(
                messages=messages,
                temperature=0.5
            )

            # Analizza le chiamate agli strumenti
            tool_calls = self._parse_tool_calls(response)

            if not tool_calls:
                # Nessuna chiamata strumento, restituisci direttamente la risposta
                clean_response = re.sub(r'<tool_call>.*?</tool_call>', '', response, flags=re.DOTALL)
                clean_response = re.sub(r'\[TOOL_CALL\].*?\)', '', clean_response)

                return {
                    "response": clean_response.strip(),
                    "tool_calls": tool_calls_made,
                    "sources": [tc.get("parameters", {}).get("query", "") for tc in tool_calls_made]
                }

            # Esegui le chiamate agli strumenti (limita il numero)
            tool_results = []
            for call in tool_calls[:1]:  # Massimo 1 esecuzione per ciclo
                if len(tool_calls_made) >= self.MAX_TOOL_CALLS_PER_CHAT:
                    break
                result = self._execute_tool(call["name"], call.get("parameters", {}))
                tool_results.append({
                    "tool": call["name"],
                    "result": result[:1500]  # Limita la lunghezza del risultato
                })
                tool_calls_made.append(call)

            # Aggiungi i risultati ai messaggi
            messages.append({"role": "assistant", "content": response})
            observation = "\n".join([f"[Risultato {r['tool']}]\n{r['result']}" for r in tool_results])
            messages.append({
                "role": "user",
                "content": observation + CHAT_OBSERVATION_SUFFIX
            })

        # Raggiunta l'iterazione massima, ottieni la risposta finale
        final_response = self.llm.chat(
            messages=messages,
            temperature=0.5
        )

        # Pulisci la risposta
        clean_response = re.sub(r'<tool_call>.*?</tool_call>', '', final_response, flags=re.DOTALL)
        clean_response = re.sub(r'\[TOOL_CALL\].*?\)', '', clean_response)

        return {
            "response": clean_response.strip(),
            "tool_calls": tool_calls_made,
            "sources": [tc.get("parameters", {}).get("query", "") for tc in tool_calls_made]
        }


class ReportManager:
    """
    Gestore dei report

    Responsabile della persistenza e del recupero dei report

    Struttura dei file (output per sezione):
    reports/
      {report_id}/
        meta.json          - Metadati e stato del report
        outline.json       - Struttura del report
        progress.json      - Progresso della generazione
        section_01.md      - Sezione 1
        section_02.md      - Sezione 2
        ...
        full_report.md     - Report completo
    """

    # Directory di archiviazione dei report
    REPORTS_DIR = os.path.join(Config.UPLOAD_FOLDER, 'reports')

    @classmethod
    def _ensure_reports_dir(cls):
        """Assicura che la directory radice dei report esista"""
        os.makedirs(cls.REPORTS_DIR, exist_ok=True)

    @classmethod
    def _get_report_folder(cls, report_id: str) -> str:
        """Ottiene il percorso della cartella del report"""
        return os.path.join(cls.REPORTS_DIR, report_id)

    @classmethod
    def _ensure_report_folder(cls, report_id: str) -> str:
        """Assicura che la cartella del report esista e restituisce il percorso"""
        folder = cls._get_report_folder(report_id)
        os.makedirs(folder, exist_ok=True)
        return folder

    @classmethod
    def _get_report_path(cls, report_id: str) -> str:
        """Ottiene il percorso del file dei metadati del report"""
        return os.path.join(cls._get_report_folder(report_id), "meta.json")

    @classmethod
    def _get_report_markdown_path(cls, report_id: str) -> str:
        """Ottiene il percorso del file Markdown del report completo"""
        return os.path.join(cls._get_report_folder(report_id), "full_report.md")

    @classmethod
    def _get_outline_path(cls, report_id: str) -> str:
        """Ottiene il percorso del file della struttura"""
        return os.path.join(cls._get_report_folder(report_id), "outline.json")

    @classmethod
    def _get_progress_path(cls, report_id: str) -> str:
        """Ottiene il percorso del file del progresso"""
        return os.path.join(cls._get_report_folder(report_id), "progress.json")

    @classmethod
    def _get_section_path(cls, report_id: str, section_index: int) -> str:
        """Ottiene il percorso del file Markdown della sezione"""
        return os.path.join(cls._get_report_folder(report_id), f"section_{section_index:02d}.md")

    @classmethod
    def _get_agent_log_path(cls, report_id: str) -> str:
        """Ottiene il percorso del file di log dell'Agent"""
        return os.path.join(cls._get_report_folder(report_id), "agent_log.jsonl")

    @classmethod
    def _get_console_log_path(cls, report_id: str) -> str:
        """Ottiene il percorso del file di log console"""
        return os.path.join(cls._get_report_folder(report_id), "console_log.txt")

    @classmethod
    def get_console_log(cls, report_id: str, from_line: int = 0) -> Dict[str, Any]:
        """
        Ottiene il contenuto del log console

        Questo e' il log di output console (INFO, WARNING, ecc.) durante la generazione del report,
        diverso dal log strutturato agent_log.jsonl.

        Args:
            report_id: ID del report
            from_line: Da quale riga iniziare la lettura (per recupero incrementale, 0 significa dall'inizio)

        Returns:
            {
                "logs": [Lista delle righe di log],
                "total_lines": Numero totale di righe,
                "from_line": Numero della riga iniziale,
                "has_more": Se ci sono altri log
            }
        """
        log_path = cls._get_console_log_path(report_id)

        if not os.path.exists(log_path):
            return {
                "logs": [],
                "total_lines": 0,
                "from_line": 0,
                "has_more": False
            }

        logs = []
        total_lines = 0

        with open(log_path, 'r', encoding='utf-8') as f:
            for i, line in enumerate(f):
                total_lines = i + 1
                if i >= from_line:
                    # Mantieni la riga di log originale, rimuovi il carattere di fine riga
                    logs.append(line.rstrip('\n\r'))

        return {
            "logs": logs,
            "total_lines": total_lines,
            "from_line": from_line,
            "has_more": False  # Lettura completata fino alla fine
        }

    @classmethod
    def get_console_log_stream(cls, report_id: str) -> List[str]:
        """
        Ottiene il log console completo (recupero completo in una volta)

        Args:
            report_id: ID del report

        Returns:
            Lista delle righe di log
        """
        result = cls.get_console_log(report_id, from_line=0)
        return result["logs"]

    @classmethod
    def get_agent_log(cls, report_id: str, from_line: int = 0) -> Dict[str, Any]:
        """
        Ottiene il contenuto del log dell'Agent

        Args:
            report_id: ID del report
            from_line: Da quale riga iniziare la lettura (per recupero incrementale, 0 significa dall'inizio)

        Returns:
            {
                "logs": [Lista delle voci di log],
                "total_lines": Numero totale di righe,
                "from_line": Numero della riga iniziale,
                "has_more": Se ci sono altri log
            }
        """
        log_path = cls._get_agent_log_path(report_id)

        if not os.path.exists(log_path):
            return {
                "logs": [],
                "total_lines": 0,
                "from_line": 0,
                "has_more": False
            }

        logs = []
        total_lines = 0

        with open(log_path, 'r', encoding='utf-8') as f:
            for i, line in enumerate(f):
                total_lines = i + 1
                if i >= from_line:
                    try:
                        log_entry = json.loads(line.strip())
                        logs.append(log_entry)
                    except json.JSONDecodeError:
                        # Salta le righe con errore di parsing
                        continue

        return {
            "logs": logs,
            "total_lines": total_lines,
            "from_line": from_line,
            "has_more": False  # Lettura completata fino alla fine
        }

    @classmethod
    def get_agent_log_stream(cls, report_id: str) -> List[Dict[str, Any]]:
        """
        Ottiene il log completo dell'Agent (recupero completo in una volta)

        Args:
            report_id: ID del report

        Returns:
            Lista delle voci di log
        """
        result = cls.get_agent_log(report_id, from_line=0)
        return result["logs"]

    @classmethod
    def save_outline(cls, report_id: str, outline: ReportOutline) -> None:
        """
        Salva la struttura del report

        Chiamato immediatamente dopo il completamento della fase di pianificazione
        """
        cls._ensure_report_folder(report_id)

        with open(cls._get_outline_path(report_id), 'w', encoding='utf-8') as f:
            json.dump(outline.to_dict(), f, ensure_ascii=False, indent=2)

        logger.info(f"Struttura salvata: {report_id}")

    @classmethod
    def save_section(
        cls,
        report_id: str,
        section_index: int,
        section: ReportSection
    ) -> str:
        """
        Salva una singola sezione

        Chiamato immediatamente dopo il completamento di ogni sezione, per l'output sezione per sezione

        Args:
            report_id: ID del report
            section_index: Indice della sezione (a partire da 1)
            section: Oggetto sezione

        Returns:
            Percorso del file salvato
        """
        cls._ensure_report_folder(report_id)

        # Costruisce il contenuto Markdown della sezione - pulisce eventuali titoli duplicati
        cleaned_content = cls._clean_section_content(section.content, section.title)
        md_content = f"## {section.title}\n\n"
        if cleaned_content:
            md_content += f"{cleaned_content}\n\n"

        # Salva il file
        file_suffix = f"section_{section_index:02d}.md"
        file_path = os.path.join(cls._get_report_folder(report_id), file_suffix)
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(md_content)

        logger.info(f"Sezione salvata: {report_id}/{file_suffix}")
        return file_path

    @classmethod
    def _clean_section_content(cls, content: str, section_title: str) -> str:
        """
        Pulisce il contenuto della sezione

        1. Rimuove le righe di titolo Markdown duplicate all'inizio del contenuto rispetto al titolo della sezione
        2. Converte tutti i titoli di livello ### e inferiore in testo in grassetto

        Args:
            content: Contenuto originale
            section_title: Titolo della sezione

        Returns:
            Contenuto pulito
        """
        import re

        if not content:
            return content

        content = content.strip()
        lines = content.split('\n')
        cleaned_lines = []
        skip_next_empty = False

        for i, line in enumerate(lines):
            stripped = line.strip()

            # Verifica se e' una riga di titolo Markdown
            heading_match = re.match(r'^(#{1,6})\s+(.+)$', stripped)

            if heading_match:
                level = len(heading_match.group(1))
                title_text = heading_match.group(2).strip()

                # Verifica se e' un titolo duplicato rispetto al titolo della sezione (nelle prime 5 righe)
                if i < 5:
                    if title_text == section_title or title_text.replace(' ', '') == section_title.replace(' ', ''):
                        skip_next_empty = True
                        continue

                # Converte tutti i livelli di titolo (#, ##, ###, ####, ecc.) in grassetto
                # Perche' il titolo della sezione e' aggiunto dal sistema, il contenuto non dovrebbe avere alcun titolo
                cleaned_lines.append(f"**{title_text}**")
                cleaned_lines.append("")  # Aggiungi riga vuota
                continue

            # Se la riga precedente era un titolo saltato e la riga corrente e' vuota, salta anche questa
            if skip_next_empty and stripped == '':
                skip_next_empty = False
                continue

            skip_next_empty = False
            cleaned_lines.append(line)

        # Rimuovi le righe vuote iniziali
        while cleaned_lines and cleaned_lines[0].strip() == '':
            cleaned_lines.pop(0)

        # Rimuovi le linee separatrici iniziali
        while cleaned_lines and cleaned_lines[0].strip() in ['---', '***', '___']:
            cleaned_lines.pop(0)
            # Rimuovi anche le righe vuote dopo il separatore
            while cleaned_lines and cleaned_lines[0].strip() == '':
                cleaned_lines.pop(0)

        return '\n'.join(cleaned_lines)

    @classmethod
    def update_progress(
        cls,
        report_id: str,
        status: str,
        progress: int,
        message: str,
        current_section: str = None,
        completed_sections: List[str] = None
    ) -> None:
        """
        Aggiorna il progresso della generazione del report

        Il frontend puo' ottenere il progresso in tempo reale leggendo progress.json
        """
        cls._ensure_report_folder(report_id)

        progress_data = {
            "status": status,
            "progress": progress,
            "message": message,
            "current_section": current_section,
            "completed_sections": completed_sections or [],
            "updated_at": datetime.now().isoformat()
        }

        with open(cls._get_progress_path(report_id), 'w', encoding='utf-8') as f:
            json.dump(progress_data, f, ensure_ascii=False, indent=2)

    @classmethod
    def get_progress(cls, report_id: str) -> Optional[Dict[str, Any]]:
        """Ottiene il progresso della generazione del report"""
        path = cls._get_progress_path(report_id)

        if not os.path.exists(path):
            return None

        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)

    @classmethod
    def get_generated_sections(cls, report_id: str) -> List[Dict[str, Any]]:
        """
        Ottiene la lista delle sezioni gia' generate

        Restituisce le informazioni di tutti i file di sezione salvati
        """
        folder = cls._get_report_folder(report_id)

        if not os.path.exists(folder):
            return []

        sections = []
        for filename in sorted(os.listdir(folder)):
            if filename.startswith('section_') and filename.endswith('.md'):
                file_path = os.path.join(folder, filename)
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()

                # Analizza l'indice della sezione dal nome del file
                parts = filename.replace('.md', '').split('_')
                section_index = int(parts[1])

                sections.append({
                    "filename": filename,
                    "section_index": section_index,
                    "content": content
                })

        return sections

    @classmethod
    def assemble_full_report(cls, report_id: str, outline: ReportOutline) -> str:
        """
        Assembla il report completo

        Assembla il report completo dai file delle sezioni salvate e esegue la pulizia dei titoli
        """
        folder = cls._get_report_folder(report_id)

        # Costruisci l'intestazione del report
        md_content = f"# {outline.title}\n\n"
        md_content += f"> {outline.summary}\n\n"
        md_content += f"---\n\n"

        # Leggi tutti i file delle sezioni in ordine
        sections = cls.get_generated_sections(report_id)
        for section_info in sections:
            md_content += section_info["content"]

        # Post-elaborazione: pulisci i problemi di titoli nell'intero report
        md_content = cls._post_process_report(md_content, outline)

        # Salva il report completo
        full_path = cls._get_report_markdown_path(report_id)
        with open(full_path, 'w', encoding='utf-8') as f:
            f.write(md_content)

        logger.info(f"Report completo assemblato: {report_id}")
        return md_content

    @classmethod
    def _post_process_report(cls, content: str, outline: ReportOutline) -> str:
        """
        Post-elaborazione del contenuto del report

        1. Rimuove i titoli duplicati
        2. Mantiene il titolo principale del report (#) e i titoli delle sezioni (##), rimuove gli altri livelli di titolo (###, ####, ecc.)
        3. Pulisce le righe vuote in eccesso e i separatori

        Args:
            content: Contenuto originale del report
            outline: Struttura del report

        Returns:
            Contenuto elaborato
        """
        import re

        lines = content.split('\n')
        processed_lines = []
        prev_was_heading = False

        # Raccoglie tutti i titoli delle sezioni dalla struttura
        section_titles = set()
        for section in outline.sections:
            section_titles.add(section.title)

        i = 0
        while i < len(lines):
            line = lines[i]
            stripped = line.strip()

            # Verifica se e' una riga di titolo
            heading_match = re.match(r'^(#{1,6})\s+(.+)$', stripped)

            if heading_match:
                level = len(heading_match.group(1))
                title = heading_match.group(2).strip()

                # Verifica se e' un titolo duplicato (titolo con lo stesso contenuto nelle ultime 5 righe)
                is_duplicate = False
                for j in range(max(0, len(processed_lines) - 5), len(processed_lines)):
                    prev_line = processed_lines[j].strip()
                    prev_match = re.match(r'^(#{1,6})\s+(.+)$', prev_line)
                    if prev_match:
                        prev_title = prev_match.group(2).strip()
                        if prev_title == title:
                            is_duplicate = True
                            break

                if is_duplicate:
                    # Salta il titolo duplicato e le righe vuote successive
                    i += 1
                    while i < len(lines) and lines[i].strip() == '':
                        i += 1
                    continue

                # Gestione dei livelli di titolo:
                # - # (livello=1) mantiene solo il titolo principale del report
                # - ## (livello=2) mantiene i titoli delle sezioni
                # - ### e inferiori (livello>=3) convertiti in testo in grassetto

                if level == 1:
                    if title == outline.title:
                        # Mantieni il titolo principale del report
                        processed_lines.append(line)
                        prev_was_heading = True
                    elif title in section_titles:
                        # Titolo di sezione che ha erroneamente usato #, correggi in ##
                        processed_lines.append(f"## {title}")
                        prev_was_heading = True
                    else:
                        # Altri titoli di primo livello convertiti in grassetto
                        processed_lines.append(f"**{title}**")
                        processed_lines.append("")
                        prev_was_heading = False
                elif level == 2:
                    if title in section_titles or title == outline.title:
                        # Mantieni il titolo della sezione
                        processed_lines.append(line)
                        prev_was_heading = True
                    else:
                        # Titoli di secondo livello non di sezione convertiti in grassetto
                        processed_lines.append(f"**{title}**")
                        processed_lines.append("")
                        prev_was_heading = False
                else:
                    # Titoli di livello ### e inferiore convertiti in testo in grassetto
                    processed_lines.append(f"**{title}**")
                    processed_lines.append("")
                    prev_was_heading = False

                i += 1
                continue

            elif stripped == '---' and prev_was_heading:
                # Salta i separatori che seguono immediatamente un titolo
                i += 1
                continue

            elif stripped == '' and prev_was_heading:
                # Dopo un titolo mantieni solo una riga vuota
                if processed_lines and processed_lines[-1].strip() != '':
                    processed_lines.append(line)
                prev_was_heading = False

            else:
                processed_lines.append(line)
                prev_was_heading = False

            i += 1

        # Pulisci le righe vuote consecutive multiple (mantieni al massimo 2)
        result_lines = []
        empty_count = 0
        for line in processed_lines:
            if line.strip() == '':
                empty_count += 1
                if empty_count <= 2:
                    result_lines.append(line)
            else:
                empty_count = 0
                result_lines.append(line)

        return '\n'.join(result_lines)

    @classmethod
    def save_report(cls, report: Report) -> None:
        """Salva i metadati e il report completo"""
        cls._ensure_report_folder(report.report_id)

        # Salva i metadati in JSON
        with open(cls._get_report_path(report.report_id), 'w', encoding='utf-8') as f:
            json.dump(report.to_dict(), f, ensure_ascii=False, indent=2)

        # Salva la struttura
        if report.outline:
            cls.save_outline(report.report_id, report.outline)

        # Salva il report completo in Markdown
        if report.markdown_content:
            with open(cls._get_report_markdown_path(report.report_id), 'w', encoding='utf-8') as f:
                f.write(report.markdown_content)

        logger.info(f"Report salvato: {report.report_id}")

    @classmethod
    def get_report(cls, report_id: str) -> Optional[Report]:
        """Ottiene il report"""
        path = cls._get_report_path(report_id)

        if not os.path.exists(path):
            # Compatibilita' con il vecchio formato: verifica i file archiviati direttamente nella directory reports
            old_path = os.path.join(cls.REPORTS_DIR, f"{report_id}.json")
            if os.path.exists(old_path):
                path = old_path
            else:
                return None

        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # Ricostruisci l'oggetto Report
        outline = None
        if data.get('outline'):
            outline_data = data['outline']
            sections = []
            for s in outline_data.get('sections', []):
                sections.append(ReportSection(
                    title=s['title'],
                    content=s.get('content', '')
                ))
            outline = ReportOutline(
                title=outline_data['title'],
                summary=outline_data['summary'],
                sections=sections
            )

        # Se markdown_content e' vuoto, prova a leggere da full_report.md
        markdown_content = data.get('markdown_content', '')
        if not markdown_content:
            full_report_path = cls._get_report_markdown_path(report_id)
            if os.path.exists(full_report_path):
                with open(full_report_path, 'r', encoding='utf-8') as f:
                    markdown_content = f.read()

        return Report(
            report_id=data['report_id'],
            simulation_id=data['simulation_id'],
            graph_id=data['graph_id'],
            simulation_requirement=data['simulation_requirement'],
            status=ReportStatus(data['status']),
            outline=outline,
            markdown_content=markdown_content,
            created_at=data.get('created_at', ''),
            completed_at=data.get('completed_at', ''),
            error=data.get('error')
        )

    @classmethod
    def get_report_by_simulation(cls, simulation_id: str) -> Optional[Report]:
        """Ottiene il report in base all'ID della simulazione"""
        cls._ensure_reports_dir()

        for item in os.listdir(cls.REPORTS_DIR):
            item_path = os.path.join(cls.REPORTS_DIR, item)
            # Nuovo formato: cartella
            if os.path.isdir(item_path):
                report = cls.get_report(item)
                if report and report.simulation_id == simulation_id:
                    return report
            # Compatibilita' con il vecchio formato: file JSON
            elif item.endswith('.json'):
                report_id = item[:-5]
                report = cls.get_report(report_id)
                if report and report.simulation_id == simulation_id:
                    return report

        return None

    @classmethod
    def list_reports(cls, simulation_id: Optional[str] = None, limit: int = 50) -> List[Report]:
        """Lista i report"""
        cls._ensure_reports_dir()

        reports = []
        for item in os.listdir(cls.REPORTS_DIR):
            item_path = os.path.join(cls.REPORTS_DIR, item)
            # Nuovo formato: cartella
            if os.path.isdir(item_path):
                report = cls.get_report(item)
                if report:
                    if simulation_id is None or report.simulation_id == simulation_id:
                        reports.append(report)
            # Compatibilita' con il vecchio formato: file JSON
            elif item.endswith('.json'):
                report_id = item[:-5]
                report = cls.get_report(report_id)
                if report:
                    if simulation_id is None or report.simulation_id == simulation_id:
                        reports.append(report)

        # Ordina per data di creazione decrescente
        reports.sort(key=lambda r: r.created_at, reverse=True)

        return reports[:limit]

    @classmethod
    def delete_report(cls, report_id: str) -> bool:
        """Elimina il report (intera cartella)"""
        import shutil

        folder_path = cls._get_report_folder(report_id)

        # Nuovo formato: elimina l'intera cartella
        if os.path.exists(folder_path) and os.path.isdir(folder_path):
            shutil.rmtree(folder_path)
            logger.info(f"Cartella del report eliminata: {report_id}")
            return True

        # Compatibilita' con il vecchio formato: elimina singoli file
        deleted = False
        old_json_path = os.path.join(cls.REPORTS_DIR, f"{report_id}.json")
        old_md_path = os.path.join(cls.REPORTS_DIR, f"{report_id}.md")

        if os.path.exists(old_json_path):
            os.remove(old_json_path)
            deleted = True
        if os.path.exists(old_md_path):
            os.remove(old_md_path)
            deleted = True

        return deleted
