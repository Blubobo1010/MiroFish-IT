# MiroFish-IT — Guida all'Uso

> Guida completa all'utilizzo di MiroFish-IT, il motore di simulazione multi-agente con calibrazione istituzionale italiana.

---

## Indice

1. [Requisiti e installazione](#1-requisiti-e-installazione)
2. [Configurazione ambiente](#2-configurazione-ambiente)
3. [Avvio dei servizi](#3-avvio-dei-servizi)
4. [Flusso di lavoro — Passo per passo](#4-flusso-di-lavoro--passo-per-passo)
   - [Passo 1: Caricamento documenti](#passo-1-caricamento-documenti)
   - [Passo 2: Costruzione del Knowledge Graph](#passo-2-costruzione-del-knowledge-graph)
   - [Passo 3: Configurazione ambiente simulazione](#passo-3-configurazione-ambiente-simulazione)
   - [Passo 4: Esecuzione della simulazione](#passo-4-esecuzione-della-simulazione)
   - [Passo 5: Generazione del report](#passo-5-generazione-del-report)
   - [Passo 6: Interazione avanzata](#passo-6-interazione-avanzata)
5. [Calibrazione istituzionale (ICF)](#5-calibrazione-istituzionale-icf)
   - [Cosa calibra](#cosa-calibra)
   - [Come funziona](#come-funziona)
   - [Uso via API](#uso-via-api)
   - [Regioni disponibili](#regioni-disponibili)
6. [Pipeline dati istituzionali](#6-pipeline-dati-istituzionali)
7. [Seed demo — Superbonus 110%](#7-seed-demo--superbonus-110)
8. [Configurazione LLM](#8-configurazione-llm)
9. [Risoluzione problemi](#9-risoluzione-problemi)

---

## 1. Requisiti e installazione

### Software necessario

| Strumento | Versione | Descrizione |
|-----------|----------|-------------|
| **Node.js** | 18+ | Runtime frontend (include npm) |
| **Python** | 3.11 o 3.12 | Runtime backend (3.13+ non supportato) |
| **uv** | Ultima | Gestore pacchetti Python |

> **Nota**: Python 3.13 e 3.14 non sono compatibili. Se hai una versione più recente, usa [pyenv](https://github.com/pyenv/pyenv) per installare Python 3.12.

### Installazione

```bash
# Clona il repository
git clone https://github.com/Blubobo1010/MiroFish-IT.git
cd MiroFish-IT

# Installazione completa (frontend + backend)
npm run setup:all
```

Oppure installa separatamente:

```bash
npm run setup           # Dipendenze Node.js (root + frontend)
npm run setup:backend   # Dipendenze Python (crea virtual environment)
```

---

## 2. Configurazione ambiente

### File `.env`

Copia il file di esempio e inserisci le tue API key:

```bash
cp .env.example .env
```

### Variabili obbligatorie

```env
# API LLM — qualsiasi provider compatibile con OpenAI SDK
LLM_API_KEY=la_tua_api_key
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL_NAME=gpt-4o
```

**Provider LLM supportati** (qualsiasi API con formato OpenAI SDK):

| Provider | BASE_URL | Modello consigliato |
|----------|----------|-------------------|
| OpenAI | `https://api.openai.com/v1` | `gpt-4o` o `gpt-4o-mini` |
| Anthropic (via proxy) | dipende dal proxy | `claude-sonnet-4-20250514` |
| Alibaba Qwen | `https://dashscope.aliyuncs.com/compatible-mode/v1` | `qwen-plus` |
| DeepSeek | `https://api.deepseek.com/v1` | `deepseek-chat` |

> **Attenzione ai costi**: la simulazione effettua molte chiamate LLM. Inizia con simulazioni brevi (< 40 round) per stimare i costi.

### Zep Cloud (memoria grafo)

```env
ZEP_API_KEY=la_tua_zep_api_key
```

Zep Cloud gestisce il knowledge graph e la memoria degli agenti. Registrati gratuitamente su [app.getzep.com](https://app.getzep.com/) — la quota gratuita mensile è sufficiente per un uso base.

### Variabili opzionali

```env
# LLM secondario per operazioni veloci (opzionale)
LLM_BOOST_API_KEY=optional
LLM_BOOST_BASE_URL=optional
LLM_BOOST_MODEL_NAME=optional
```

---

## 3. Avvio dei servizi

```bash
# Avvia frontend e backend insieme
npm run dev
```

| Servizio | URL |
|----------|-----|
| Frontend | http://localhost:3000 |
| Backend API | http://localhost:5001 |

Per avviare separatamente:

```bash
npm run backend    # Solo backend (porta 5001)
npm run frontend   # Solo frontend (porta 3000)
```

### Docker (alternativa)

```bash
cp .env.example .env    # Configura le variabili
docker compose up -d    # Avvia i container
```

---

## 4. Flusso di lavoro — Passo per passo

MiroFish-IT guida l'utente attraverso 5 passi sequenziali, dalla preparazione dei documenti fino all'interazione con gli agenti simulati.

### Passo 1: Caricamento documenti

**Pagina**: Homepage (`http://localhost:3000`)

1. **Carica documenti**: trascina o clicca per caricare uno o più file. Formati supportati:
   - PDF
   - Markdown (.md)
   - Testo (.txt)

2. **Descrivi lo scenario**: nel campo di testo, descrivi in linguaggio naturale cosa vuoi simulare. Esempi:
   - *"Simula la reazione dell'opinione pubblica italiana all'annuncio di un aumento delle tasse universitarie"*
   - *"Come reagirebbero i cittadini di diverse regioni italiane a una riforma delle pensioni?"*
   - *"Simula il dibattito sul Superbonus 110% tra contribuenti, imprese edili e istituzioni"*

3. **Avvia**: clicca il pulsante **"Avvia Motore"**

> **Suggerimento**: documenti più dettagliati producono simulazioni più ricche. Includi report, articoli, dati di contesto.

---

### Passo 2: Costruzione del Knowledge Graph

**Pagina**: Vista Processo (automatica dopo il caricamento)

Il sistema esegue automaticamente tre fasi:

1. **Generazione ontologia**: l'LLM analizza i documenti e identifica tipi di entità (persone, organizzazioni, eventi) e tipi di relazione
2. **Costruzione grafo**: Zep costruisce il knowledge graph, estraendo entità e relazioni dai documenti
3. **Completamento**: il grafo è pronto

**Cosa vedi**:
- **Pannello sinistro**: visualizzazione interattiva del grafo in tempo reale (nodi = entità, archi = relazioni)
- **Pannello destro**: progresso della costruzione con dettagli su ogni fase

**Interazione**:
- Clicca sui nodi per vedere i dettagli di un'entità
- Clicca sugli archi per vedere le relazioni
- Usa lo zoom (rotella del mouse) per esplorare il grafo
- Il pulsante ↗ attiva la vista a schermo intero

Quando il grafo è completo, clicca **"Configura Ambiente"** per procedere.

---

### Passo 3: Configurazione ambiente simulazione

**Pagina**: Vista Processo — Step 2

Il sistema genera automaticamente i profili degli agenti e la configurazione della simulazione. Questo passo ha 5 fasi:

#### Fase 1 — Inizializzazione
Creazione dell'istanza di simulazione. Automatica.

#### Fase 2 — Generazione profili agente
Il sistema crea un profilo dettagliato per ogni entità estratta dal grafo:

- **Nome, età, professione, MBTI**
- **Bio**: presentazione breve per social media
- **Persona**: descrizione dettagliata del carattere, background, stile comunicativo (circa 2000 caratteri)
- **Argomenti di interesse**
- **Calibrazione regionale**: se attiva, i profili riflettono i dati economici, culturali e demografici della regione NUTS-2

> Clicca su un profilo nell'elenco per vedere tutti i dettagli in un pannello espandibile.

#### Fase 3 — Configurazione simulazione
L'LLM genera i parametri della simulazione:

- **Configurazione temporale**: durata totale, minuti per round, orari di picco
- **Configurazione per agente**: frequenza post/commenti, ore attive, livello di attività, orientamento del sentimento
- **Algoritmo di raccomandazione**: pesi per recenza, popolarità, rilevanza + soglia viralità e forza camera eco

#### Fase 4 — Orchestrazione iniziale
Definizione dei post iniziali che innescano la simulazione, temi caldi e direzione narrativa.

#### Fase 5 — Pronto per la simulazione
- Puoi scegliere il numero di round (automatico o personalizzato)
- Il preset consigliato è 40 round
- Clicca **"Avvia Simulazione"** per partire

---

### Passo 4: Esecuzione della simulazione

**Pagina**: Vista Simulazione

La simulazione esegue su due piattaforme parallele:

| Piattaforma | Tipo | Comportamenti simulati |
|-------------|------|----------------------|
| **Info Plaza** (Twitter-like) | Feed in tempo reale | Post, Like, Repost, Citazioni, Follow |
| **Topics Community** (Reddit-like) | Forum tematico | Post, Commenti, Upvote, Downvote |

**Cosa vedi**:
- Stato di ogni piattaforma (round corrente, azioni eseguite, progresso)
- Grafo che si aggiorna in tempo reale con le nuove interazioni
- Contatore totale agenti e azioni

**Controlli**:
- Puoi avviare/fermare ogni piattaforma indipendentemente
- Slider velocità (0,5x — 2x)

Quando tutti i round sono completati, appare il pulsante **"Vai al Report"**.

---

### Passo 5: Generazione del report

**Pagina**: Vista Report

Il **ReportAgent** analizza automaticamente i risultati della simulazione e genera un report dettagliato che include:

- Analisi delle dinamiche emerse
- Temi dominanti e posizioni degli agenti
- Previsioni basate sulle tendenze simulate
- Citazioni chiave dagli agenti

La generazione è completamente automatica — attendi il completamento.

---

### Passo 6: Interazione avanzata

**Pagina**: Vista Interazione

Dopo la simulazione, puoi interagire direttamente con:

- **Singoli agenti**: fai domande a qualsiasi agente nel mondo simulato. Risponderanno in base alla loro persona, alle esperienze vissute durante la simulazione e alla loro memoria
- **ReportAgent**: il sistema analista che può rispondere a domande sull'intera simulazione

**Esempi di domande**:
- *"Come hai reagito all'annuncio del governo?"*
- *"Quali sono i tuoi principali timori riguardo questa misura?"*
- *"Puoi riassumere le posizioni dominanti emerse dalla simulazione?"*

---

## 5. Calibrazione istituzionale (ICF)

La caratteristica distintiva di MiroFish-IT è la **calibrazione istituzionale**: ogni agente simulato è calibrato su dati reali delle regioni italiane.

### Cosa calibra

| Livello | Dati | Effetto sulla simulazione |
|---------|------|--------------------------|
| **Economico** | Reddito, ricchezza, risparmio, occupazione | Influenza le preoccupazioni economiche e il livello di rischio percepito |
| **Culturale (Hofstede 6D)** | Distanza dal potere, individualismo, mascolinità, avversione all'incertezza, orientamento al lungo termine, indulgenza | Influenza stile comunicativo, rispetto della gerarchia, propensione al rischio |
| **Culturale (Schwartz)** | 10 valori base + 4 valori di ordine superiore | Influenza le priorità valoriali (benevolenza, sicurezza, universalismo) |
| **Demografico** | Età mediana, istruzione, internet, sport, volontariato | Influenza il livello di digitalizzazione e partecipazione sociale |
| **Sociale** | Fiducia interpersonale e istituzionale, soddisfazione vita | Influenza l'atteggiamento verso le istituzioni e gli altri |

### Come funziona

Quando viene specificata una regione NUTS-2, il sistema:

1. Carica il profilo di calibrazione della regione
2. Genera un contesto testuale che include tutti gli indicatori regionali
3. Inietta il contesto nel prompt LLM durante la generazione della persona dell'agente
4. Aggiunge indicazioni comportamentali basate sui punteggi Hofstede

**Esempio concreto — agente di Lombardia vs Campania**:

| Aspetto | Lombardia (ITC4) | Campania (ITF3) |
|---------|-----------------|-----------------|
| Reddito medio | EUR 39.800/anno | EUR 25.800/anno |
| Hofstede PDI | 45 → egualitario, mette in discussione l'autorità | 55 → rispetto gerarchia, deferenza |
| Hofstede IDV | 81 → individualista, autonomia personale | 68 → collettivista, legami familiari |
| Hofstede UAI | 72 → tolleranza moderata per l'ambiguità | 80 → forte bisogno di regole e sicurezza |
| Stile comunicativo | Riservato e diretto | Espressivo e caloroso |
| Disoccupazione | 4,6% | 17,8% |

### Uso via API

Per specificare la regione durante la preparazione della simulazione:

```bash
curl -X POST http://localhost:5001/api/simulation/prepare \
  -H "Content-Type: application/json" \
  -d '{
    "simulation_id": "sim_xxxx",
    "nuts2_region": "ITC4",
    "use_llm_for_profiles": true,
    "parallel_profile_count": 5
  }'
```

Se `nuts2_region` non viene specificato, il sistema assegna automaticamente una regione casuale a ogni agente per creare diversità regionale.

### Regioni disponibili

| Codice | Regione | Zona |
|--------|---------|------|
| ITC1 | Piemonte | Nord |
| ITC2 | Valle d'Aosta | Nord |
| ITC3 | Liguria | Nord |
| ITC4 | Lombardia | Nord |
| ITH1 | P.A. Bolzano | Nord |
| ITH2 | P.A. Trento | Nord |
| ITH3 | Veneto | Nord |
| ITH4 | Friuli-Venezia Giulia | Nord |
| ITH5 | Emilia-Romagna | Nord |
| ITI1 | Toscana | Centro |
| ITI2 | Umbria | Centro |
| ITI3 | Marche | Centro |
| ITI4 | Lazio | Centro |
| ITF1 | Abruzzo | Sud |
| ITF2 | Molise | Sud |
| ITF3 | Campania | Sud |
| ITF4 | Puglia | Sud |
| ITF5 | Basilicata | Sud |
| ITF6 | Calabria | Sud |
| ITG1 | Sicilia | Sud |
| ITG2 | Sardegna | Sud |

---

## 6. Pipeline dati istituzionali

I dati di calibrazione sono pre-inclusi nel repository, ma puoi aggiornarli eseguendo la pipeline:

```bash
cd backend/data/scripts
python run_pipeline.py
```

La pipeline raccoglie dati da 5 fonti:

| Passo | Fonte | Output |
|-------|-------|--------|
| 1 | Hofstede Insights | 6 dimensioni culturali nazionali + modulazione regionale |
| 2 | Eurostat SDMX API | PIL, PPS, occupazione, popolazione, reddito per NUTS-2 |
| 3 | ISTAT | Demografia, istruzione, stile di vita per regione |
| 4 | Banca d'Italia IBF | Reddito, ricchezza, risparmio per macro-area |
| 5 | European Social Survey | Valori Schwartz, fiducia, benessere per Italia |
| 6 | Build | Profili unificati di calibrazione (21 regioni) |

**Output**:
- `backend/data/processed/calibration_profiles.json` — profili strutturati per regione
- `backend/data/processed/calibration_texts.json` — testi di calibrazione per iniezione nel prompt

**Opzioni**:
```bash
python run_pipeline.py --skip-eurostat     # Salta Eurostat (utile offline)
```

---

## 7. Seed demo — Superbonus 110%

Un demo preconfigurato è incluso in `backend/data/seed_demo/` per testare il sistema senza dover eseguire la pipeline completa.

**Scenario**: dibattito italiano sul Superbonus 110%, con agenti che rappresentano diverse posizioni e regioni.

**7 agenti**:

| Agente | Professione | Regione | Posizione |
|--------|------------|---------|-----------|
| Marco Ferretti | Ingegnere edile | Lombardia | Sostenitore critico |
| Anna Benedetti | Economista | Emilia-Romagna | Critica (costo/debito) |
| Giuseppe Esposito | Impresario edile | Campania | Forte sostenitore |
| Lucia Romano | Commercialista | Lazio | Neutrale (focus normativo) |
| Salvatore Ferrara | Pensionato | Sicilia | Beneficiario grato |
| Confindustria Lombardia | Istituzione | Lombardia | Posizione articolata |
| Maria Teresa Colombo | Insegnante | Lombardia | Contribuente scettica |

**Validazione**:
```bash
python backend/data/seed_demo/validate_demo.py
```

---

## 8. Configurazione LLM

### Scelta del modello

La qualità della simulazione dipende fortemente dal modello LLM:

| Modello | Qualità persona | Velocità | Costo | Note |
|---------|----------------|----------|-------|------|
| GPT-4o | Eccellente | Media | Alto | Miglior rapporto qualità/versatilità |
| GPT-4o-mini | Buona | Veloce | Basso | Ottimo per test e sviluppo |
| Claude Sonnet | Eccellente | Media | Medio | Ottime persona in italiano |
| Qwen-plus | Buona | Veloce | Basso | Buon rapporto qualità/prezzo |
| DeepSeek Chat | Buona | Veloce | Molto basso | Economico per grandi simulazioni |

### Stima costi

Per una simulazione tipica con 20 agenti e 40 round:
- **Generazione profili**: ~20 chiamate LLM (1 per agente)
- **Configurazione**: ~3 chiamate LLM
- **Simulazione**: ~800 chiamate LLM (20 agenti × 40 round)
- **Report**: ~10-20 chiamate LLM

**Stima totale**: ~850 chiamate → circa $2-5 con GPT-4o, $0.20-0.50 con GPT-4o-mini.

---

## 9. Risoluzione problemi

### Il backend non si avvia

**Errore**: `ModuleNotFoundError: No module named 'flask'`
```bash
cd backend
uv sync   # Reinstalla le dipendenze nel virtual environment
```

**Errore**: Python 3.13+ non supportato
```bash
pyenv install 3.12.10
pyenv local 3.12.10
```

### Errore circolare `types.py`

Se vedi `ImportError: cannot import name 'Enum'`, stai eseguendo Python dalla directory root del progetto. Il file `types.py` nella root confligge con la libreria standard. Esegui sempre dalla directory `backend/`:

```bash
cd backend
.venv/bin/python ...
```

### Eurostat API restituisce errori

L'API Eurostat potrebbe essere temporaneamente non disponibile. Usa il flag `--skip-eurostat`:
```bash
python run_pipeline.py --skip-eurostat
```

I dati pre-processati restano disponibili in `backend/data/processed/`.

### La generazione profili è lenta

La generazione avviene in parallelo (default: 5 agenti simultanei). Puoi aumentare il parallelismo:

```json
POST /api/simulation/prepare
{
  "simulation_id": "sim_xxxx",
  "parallel_profile_count": 10
}
```

### Zep Cloud non risponde

Verifica la tua `ZEP_API_KEY` in `.env`. La quota gratuita di Zep ha limiti mensili — verifica il tuo utilizzo su [app.getzep.com](https://app.getzep.com/).

---

*MiroFish-IT — Calibrazione istituzionale per simulazioni multi-agente nel contesto italiano ed europeo.*
