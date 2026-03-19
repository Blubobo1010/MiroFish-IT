<div align="center">

<img src="./static/image/MiroFish_logo_compressed.jpeg" alt="MiroFish-IT Logo" width="75%"/>

**MiroFish-IT** — Fork italiano di MiroFish con calibrazione istituzionale
</br>
<em>Italian fork of MiroFish with Institutional Calibration Framework (ICF) for EU data at NUTS-2 regional granularity</em>

[![Fork of MiroFish](https://img.shields.io/badge/fork%20of-MiroFish%20(35K+%20⭐)-DAA520?style=flat-square)](https://github.com/666ghj/MiroFish)
[![License: AGPL-3.0](https://img.shields.io/badge/License-AGPL--3.0-blue?style=flat-square)](./LICENSE)
[![Python](https://img.shields.io/badge/Python-3.11%20|%203.12-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![NUTS-2 Regions](https://img.shields.io/badge/NUTS--2-21%20regioni%20IT-1A936F?style=flat-square)](https://ec.europa.eu/eurostat/web/nuts)

[English](./README-EN.md) | **Italiano** | [Guida all'uso](./GUIDA.md)

</div>

## Panoramica

**MiroFish-IT** è un fork italiano di [MiroFish](https://github.com/666ghj/MiroFish), il motore di simulazione multi-agente basato su intelligenza artificiale. Questo fork aggiunge la **calibrazione istituzionale** degli agenti utilizzando dati EU reali a granularità regionale NUTS-2, permettendo simulazioni più realistiche per il contesto italiano ed europeo.

> **Upstream**: [666ghj/MiroFish](https://github.com/666ghj/MiroFish) (35K+ stelle) — motore di predizione basato su intelligenza collettiva multi-agente
>
> **Cosa aggiunge questo fork**: profili agente calibrati su dati economici, culturali e demografici delle 21 regioni italiane

### Institutional Calibration Framework (ICF)

Il framework ICF calibra ogni agente simulato su 4 livelli di dati reali:

| Livello | Fonti dati | Indicatori |
|---------|-----------|------------|
| **Economico** | Eurostat SDMX, Banca d'Italia IBF | PIL, PPS, occupazione, reddito, ricchezza, risparmio |
| **Culturale** | Hofstede 6D, Schwartz/ESS Round 10 | PDI, IDV, MAS, UAI, LTO, IVR + 10 valori base |
| **Demografico** | ISTAT Noi Italia / BES | Età mediana, istruzione, disoccupazione, internet, sport |
| **Sociale** | ESS Round 10 | Fiducia interpersonale, istituzionale, soddisfazione vita |

La calibrazione produce **differenze comportamentali misurabili** tra agenti di regioni diverse:

| Dimensione | Nord (es. Lombardia) | Sud (es. Campania) |
|-----------|---------------------|-------------------|
| Reddito medio | €39.800/anno | €25.800/anno |
| Hofstede PDI | 45 (egualitario) | 55 (gerarchico) |
| Hofstede IDV | 81 (individualista) | 68 (collettivista) |
| Disoccupazione | 4,6% | 17,8% |
| Stile comunicativo | Riservato, diretto | Espressivo, caloroso |

## Workflow

1. **Costruzione Grafo**: Estrazione seed, iniezione memoria individuale/collettiva, costruzione GraphRAG
2. **Configurazione Ambiente**: Estrazione relazioni entità, generazione persona **con calibrazione ICF**, configurazione agenti
3. **Simulazione**: Simulazione parallela su doppia piattaforma, parsing requisiti di predizione, aggiornamento dinamico memoria temporale
4. **Generazione Report**: ReportAgent con strumenti avanzati per interazione profonda con l'ambiente post-simulazione
5. **Interazione**: Chat con qualsiasi agente nel mondo simulato, interazione con ReportAgent

## Quick Start

### Prerequisiti

| Strumento | Versione | Descrizione | Verifica |
|-----------|----------|-------------|----------|
| **Node.js** | 18+ | Runtime frontend, include npm | `node -v` |
| **Python** | ≥3.11, ≤3.12 | Runtime backend | `python --version` |
| **uv** | Latest | Gestore pacchetti Python | `uv --version` |

### 1. Configura variabili d'ambiente

```bash
cp .env.example .env
# Modifica .env e inserisci le API key necessarie
```

**Variabili richieste:**

```env
# Configurazione API LLM (supporta qualsiasi LLM con formato OpenAI SDK)
LLM_API_KEY=your_api_key
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL_NAME=gpt-4o

# Configurazione Zep Cloud
# Quota mensile gratuita sufficiente per uso base: https://app.getzep.com/
ZEP_API_KEY=your_zep_api_key
```

### 2. Installa dipendenze

```bash
# Installazione completa (root + frontend + backend)
npm run setup:all
```

### 3. Pipeline dati di calibrazione (opzionale)

```bash
cd backend/data/scripts
python run_pipeline.py
```

Questo scarica e processa i dati di calibrazione dalle fonti istituzionali (Eurostat, ISTAT, Banca d'Italia, ESS). I dati pre-processati sono già inclusi nel repository.

### 4. Avvia i servizi

```bash
npm run dev
```

- Frontend: `http://localhost:3000`
- Backend API: `http://localhost:5001`

### Seed Demo

Un demo preconfigurato è disponibile in `backend/data/seed_demo/`:

- **Scenario**: Dibattito sul Superbonus 110% — impatto regionale Nord/Centro/Sud
- **7 agenti** calibrati ICF su 5 regioni italiane (Lombardia, Emilia-Romagna, Lazio, Campania, Sicilia)
- Validazione: `python backend/data/seed_demo/validate_demo.py`

### API di calibrazione

Per specificare una regione NUTS-2 durante la preparazione della simulazione:

```json
POST /api/simulation/prepare
{
  "simulation_id": "sim_xxxx",
  "nuts2_region": "ITC4"
}
```

Codici NUTS-2 supportati: `ITC1`–`ITC4`, `ITH1`–`ITH5`, `ITI1`–`ITI4`, `ITF1`–`ITF6`, `ITG1`–`ITG2` (21 regioni italiane).

## Struttura progetto — differenze dal fork originale

```
backend/
├── app/services/
│   ├── calibration_service.py          # NUOVO — Servizio calibrazione ICF
│   └── oasis_profile_generator.py      # MODIFICATO — Iniezione calibrazione regionale
├── data/
│   ├── processed/
│   │   ├── calibration_profiles.json   # NUOVO — Profili NUTS-2 (21 regioni)
│   │   └── calibration_texts.json      # NUOVO — Testi calibrazione per prompt
│   ├── raw/                            # NUOVO — Dati grezzi da fonti istituzionali
│   │   ├── eurostat/
│   │   ├── istat/
│   │   ├── bankitalia/
│   │   ├── hofstede/
│   │   └── ess/
│   ├── scripts/                        # NUOVO — Pipeline raccolta dati
│   └── seed_demo/                      # NUOVO — Demo italiano preconfigurato
frontend/
└── src/                                # MODIFICATO — UI tradotta in italiano
```

## Fonti dati

| Fonte | Istituzione | Licenza | Aggiornamento |
|-------|------------|---------|---------------|
| [Eurostat SDMX API](https://ec.europa.eu/eurostat/) | Commissione Europea | Open data | Annuale |
| [ISTAT Noi Italia / BES](https://www.istat.it/) | Istituto Nazionale di Statistica | Open data | Annuale |
| [Banca d'Italia IBF](https://www.bancaditalia.it/) | Banca d'Italia | Open data | Biennale |
| [Hofstede Insights](https://www.hofstede-insights.com/) | Hofstede Insights | Published research | Stabile |
| [European Social Survey](https://www.europeansocialsurvey.org/) | ESS ERIC | Open data | Biennale |

## Riconoscimenti

**MiroFish-IT** è costruito su [MiroFish](https://github.com/666ghj/MiroFish) di 666ghj e sul motore di simulazione [OASIS](https://github.com/camel-ai/oasis) di CAMEL-AI. Un ringraziamento sincero a entrambi i team per i loro contributi open-source.

Il framework di calibrazione istituzionale (ICF) utilizza dati aperti di Eurostat, ISTAT, Banca d'Italia ed European Social Survey.

## Paper

> 📄 Paper arXiv in preparazione: *"Institutional Calibration Framework for Synthetic Populations"* — framework sperimentale a 3 condizioni (Baseline vs Country vs NUTS-2 Full) con Cultural Turing Test.

## Autore

**[Andrea Lorini](https://github.com/Blubobo1010)** — ricerca sulla calibrazione istituzionale di popolazioni sintetiche per mercati europei.
Contatto: [andrea@ai-audit.it](mailto:andrea@ai-audit.it)

## Licenza

Licenza [AGPL-3.0](./LICENSE) — stessa licenza del repository upstream MiroFish.
