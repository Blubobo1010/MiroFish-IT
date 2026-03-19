<div align="center">

<img src="./static/image/MiroFish_logo_compressed.jpeg" alt="MiroFish-IT Logo" width="75%"/>

**MiroFish-IT** — Italian fork of MiroFish with institutional calibration
</br>
<em>Multi-agent simulation with EU institutional data at NUTS-2 regional granularity</em>

**English** | [Italiano](./README.md) | [User Guide (IT)](./GUIDA.md)

</div>

## Overview

**MiroFish-IT** is an Italian fork of [MiroFish](https://github.com/666ghj/MiroFish), the AI-powered multi-agent simulation engine. This fork adds **institutional calibration** of agent profiles using real EU data at NUTS-2 regional granularity, enabling more realistic simulations for the Italian and European context.

> **Upstream**: [666ghj/MiroFish](https://github.com/666ghj/MiroFish) (35K+ stars) — swarm intelligence prediction engine
>
> **What this fork adds**: agent profiles calibrated on economic, cultural, and demographic data from Italy's 21 NUTS-2 regions

### Institutional Calibration Framework (ICF)

The ICF calibrates each simulated agent on 4 layers of real-world data:

| Layer | Data Sources | Indicators |
|-------|-------------|------------|
| **Economic** | Eurostat SDMX, Bank of Italy IBF | GDP, PPS, employment, income, wealth, savings |
| **Cultural** | Hofstede 6D, Schwartz/ESS Round 10 | PDI, IDV, MAS, UAI, LTO, IVR + 10 basic values |
| **Demographic** | ISTAT (Italian Statistics) | Median age, education, unemployment, internet access |
| **Social** | ESS Round 10 | Interpersonal trust, institutional trust, life satisfaction |

Calibration produces **measurable behavioral differences** between agents from different regions:

| Dimension | North (e.g., Lombardy) | South (e.g., Campania) |
|-----------|----------------------|----------------------|
| Mean income | EUR 39,800/year | EUR 25,800/year |
| Hofstede PDI | 45 (egalitarian) | 55 (hierarchical) |
| Hofstede IDV | 81 (individualist) | 68 (collectivist) |
| Unemployment | 4.6% | 17.8% |
| Communication style | Reserved, direct | Expressive, warm |

## Workflow

1. **Graph Building**: Seed extraction, individual/collective memory injection, GraphRAG construction
2. **Environment Setup**: Entity relationship extraction, persona generation **with ICF calibration**, agent configuration
3. **Simulation**: Dual-platform parallel simulation, auto-parse prediction requirements, dynamic temporal memory updates
4. **Report Generation**: ReportAgent with rich toolset for deep post-simulation interaction
5. **Deep Interaction**: Chat with any agent in the simulated world, interact with ReportAgent

## Quick Start

### Prerequisites

| Tool | Version | Description | Check |
|------|---------|-------------|-------|
| **Node.js** | 18+ | Frontend runtime, includes npm | `node -v` |
| **Python** | >=3.11, <=3.12 | Backend runtime | `python --version` |
| **uv** | Latest | Python package manager | `uv --version` |

### 1. Configure environment variables

```bash
cp .env.example .env
# Edit .env and fill in the required API keys
```

**Required variables:**

```env
# LLM API Configuration (supports any OpenAI SDK-compatible LLM)
LLM_API_KEY=your_api_key
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL_NAME=gpt-4o

# Zep Cloud Configuration
# Free monthly quota sufficient for basic usage: https://app.getzep.com/
ZEP_API_KEY=your_zep_api_key
```

### 2. Install dependencies

```bash
# One-click install (root + frontend + backend)
npm run setup:all
```

### 3. Calibration data pipeline (optional)

```bash
cd backend/data/scripts
python run_pipeline.py
```

Downloads and processes calibration data from institutional sources (Eurostat, ISTAT, Bank of Italy, ESS). Pre-processed data is already included in the repository.

### 4. Start services

```bash
npm run dev
```

- Frontend: `http://localhost:3000`
- Backend API: `http://localhost:5001`

### Seed Demo

A pre-configured Italian demo is available in `backend/data/seed_demo/`:

- **Scenario**: Debate on the Italian Superbonus 110% tax incentive — regional North/Center/South impact
- **7 agents** ICF-calibrated across 5 Italian regions (Lombardy, Emilia-Romagna, Lazio, Campania, Sicily)
- Validate: `python backend/data/seed_demo/validate_demo.py`

### Calibration API

To specify a NUTS-2 region during simulation preparation:

```json
POST /api/simulation/prepare
{
  "simulation_id": "sim_xxxx",
  "nuts2_region": "ITC4"
}
```

Supported NUTS-2 codes: `ITC1`–`ITC4`, `ITH1`–`ITH5`, `ITI1`–`ITI4`, `ITF1`–`ITF6`, `ITG1`–`ITG2` (21 Italian regions).

## Project Structure — differences from upstream

```
backend/
├── app/services/
│   ├── calibration_service.py          # NEW — ICF calibration service
│   └── oasis_profile_generator.py      # MODIFIED — Regional calibration injection
├── data/
│   ├── processed/
│   │   ├── calibration_profiles.json   # NEW — NUTS-2 profiles (21 regions)
│   │   └── calibration_texts.json      # NEW — Calibration texts for prompt injection
│   ├── raw/                            # NEW — Raw institutional data
│   │   ├── eurostat/
│   │   ├── istat/
│   │   ├── bankitalia/
│   │   ├── hofstede/
│   │   └── ess/
│   ├── scripts/                        # NEW — Data collection pipeline
│   └── seed_demo/                      # NEW — Pre-configured Italian demo
frontend/
└── src/                                # MODIFIED — UI translated to Italian
```

## Data Sources

| Source | Institution | License | Update Frequency |
|--------|-----------|---------|-----------------|
| [Eurostat SDMX API](https://ec.europa.eu/eurostat/) | European Commission | Open data | Annual |
| [ISTAT Noi Italia / BES](https://www.istat.it/) | Italian National Statistics | Open data | Annual |
| [Bank of Italy IBF](https://www.bancaditalia.it/) | Bank of Italy | Open data | Biennial |
| [Hofstede Insights](https://www.hofstede-insights.com/) | Hofstede Insights | Published research | Stable |
| [European Social Survey](https://www.europeansocialsurvey.org/) | ESS ERIC | Open data | Biennial |

## Acknowledgments

**MiroFish-IT** is built on [MiroFish](https://github.com/666ghj/MiroFish) by 666ghj and the [OASIS](https://github.com/camel-ai/oasis) simulation engine by CAMEL-AI. Sincere thanks to both teams for their open-source contributions.

The Institutional Calibration Framework (ICF) uses open data from Eurostat, ISTAT, Bank of Italy, and the European Social Survey.

## Author

**Andrea Lorini** — research on institutional calibration of synthetic populations for European markets.

## License

This project is released under the same license as the upstream MiroFish repository.
