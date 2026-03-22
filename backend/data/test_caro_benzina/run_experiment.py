"""
Esegui il test Caro-Benzina su MiroFish-IT — 3 condizioni sperimentali.

Usa le API MiroFish-IT con profili pre-costruiti (prebuilt_profiles_path).
Il backend deve essere in esecuzione (npm run dev).

Questo script:
1. Per ogni condizione (A, B, C):
   a. Crea simulazione via API
   b. Prepara con profili pre-costruiti (salta Zep + generazione LLM)
   c. Lancia simulazione OASIS via API
2. Monitora il progresso in tempo reale
3. Salva indice esperimento per l'analisi

Uso:
    # Assicurati che il backend sia in esecuzione (npm run dev)
    python3 backend/data/test_caro_benzina/run_experiment.py [--condition A|B|C|all] [--base-url http://localhost:5001]

Prerequisiti:
    - Backend MiroFish-IT in esecuzione su localhost:5001
    - .env configurato con LLM_API_KEY, LLM_BASE_URL, LLM_MODEL_NAME, ZEP_API_KEY
    - Profili generati (python3 backend/data/test_caro_benzina/generate_profiles.py)
"""

import argparse
import json
import os
import sys
import time
import urllib.request
import urllib.error

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROFILES_DIR = os.path.join(SCRIPT_DIR, 'profiles')
SEED_DOC_PATH = os.path.join(SCRIPT_DIR, 'seed_document.md')

CONDITIONS = {
    'A': {
        'label': 'Baseline',
        'file': 'condition_a_baseline.json',
        'description': 'Profilo generico senza dati reali'
    },
    'B': {
        'label': 'Country-level',
        'file': 'condition_b_country.json',
        'description': 'Dati nazionali aggregati'
    },
    'C': {
        'label': 'NUTS-2 Full',
        'file': 'condition_c_nuts2.json',
        'description': 'Profilo calibrato con 4 strati ICF'
    }
}

SIMULATION_REQUIREMENT = (
    "Simula le reazioni dei consumatori italiani all'aumento del 20% "
    "del prezzo del carburante in 2 settimane. Osserva le 5 dimensioni: "
    "mobilita, spesa discrezionale, canale d'acquisto, scelta di marca, "
    "prioritizzazione. Gli agenti devono discutere tra loro sulle "
    "piattaforme social, condividere le proprie esperienze e strategie "
    "di adattamento alla crisi carburante."
)


def api_call(base_url, endpoint, data=None, method='POST'):
    """Chiamata API al backend MiroFish-IT."""
    url = f"{base_url}{endpoint}"
    headers = {'Content-Type': 'application/json'}

    if data is not None:
        body = json.dumps(data).encode('utf-8')
        req = urllib.request.Request(url, data=body, headers=headers, method=method)
    else:
        req = urllib.request.Request(url, headers=headers, method='GET')

    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            return json.loads(resp.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        body = e.read().decode('utf-8', errors='replace')
        print(f"    HTTP {e.code}: {body[:500]}")
        return None
    except urllib.error.URLError as e:
        print(f"    Errore connessione: {e.reason}")
        return None


def wait_for_preparation(base_url, simulation_id, task_id, timeout=600):
    """Attende il completamento della preparazione."""
    start = time.time()
    last_msg = ""

    while time.time() - start < timeout:
        resp = api_call(base_url, '/api/simulation/prepare/status', {
            'simulation_id': simulation_id,
            'task_id': task_id
        })

        if not resp or not resp.get('success'):
            time.sleep(3)
            continue

        data = resp['data']
        status = data.get('status', '')
        msg = data.get('message', '')
        progress = data.get('progress', 0)

        if msg != last_msg:
            print(f"    [{progress:>3}%] {msg}")
            last_msg = msg

        if status in ('ready', 'completed'):
            return True
        if status == 'failed':
            print(f"    ERRORE: {data.get('error', 'sconosciuto')}")
            return False
        if data.get('already_prepared'):
            return True

        time.sleep(3)

    print(f"    TIMEOUT: preparazione non completata in {timeout}s")
    return False


def wait_for_simulation(base_url, simulation_id, timeout=3600):
    """Attende il completamento della simulazione."""
    start = time.time()
    last_round = -1

    while time.time() - start < timeout:
        resp = api_call(base_url, f'/api/simulation/{simulation_id}/run-status', method='GET')

        if not resp or not resp.get('success'):
            time.sleep(5)
            continue

        data = resp['data']
        status = data.get('runner_status', '')
        current_round = data.get('reddit_current_round', data.get('current_round', 0))
        total_rounds = data.get('total_rounds', '?')
        actions = data.get('reddit_actions_count', data.get('total_actions_count', 0))

        if current_round != last_round:
            print(f"    Round {current_round}/{total_rounds} — {actions} azioni")
            last_round = current_round

        if status in ('COMPLETED', 'completed'):
            print(f"    Simulazione completata! {actions} azioni totali")
            return True
        if status in ('FAILED', 'failed', 'STOPPED', 'stopped'):
            print(f"    Simulazione terminata con stato: {status}")
            return status == 'STOPPED'  # stopped e' OK se l'utente ha fermato

        time.sleep(5)

    print(f"    TIMEOUT: simulazione non completata in {timeout}s")
    return False


def run_condition(base_url, condition_id, project_id, graph_id):
    """Esegue una singola condizione sperimentale."""
    cond = CONDITIONS[condition_id]
    profiles_path = os.path.abspath(os.path.join(PROFILES_DIR, cond['file']))

    if not os.path.exists(profiles_path):
        print(f"    ERRORE: Profili non trovati: {profiles_path}")
        return None

    # 1. Crea simulazione
    print(f"  1. Creazione simulazione...")
    resp = api_call(base_url, '/api/simulation/create', {
        'project_id': project_id,
        'graph_id': graph_id,
        'enable_twitter': False,
        'enable_reddit': True
    })

    if not resp or not resp.get('success'):
        print(f"    ERRORE creazione: {resp}")
        return None

    simulation_id = resp['data']['simulation_id']
    print(f"    Simulation ID: {simulation_id}")

    # 2. Prepara con profili pre-costruiti
    print(f"  2. Preparazione con profili pre-costruiti ({cond['label']})...")
    print(f"    File: {profiles_path}")

    resp = api_call(base_url, '/api/simulation/prepare', {
        'simulation_id': simulation_id,
        'simulation_requirement': SIMULATION_REQUIREMENT,
        'prebuilt_profiles_path': profiles_path,
        'force_regenerate': True
    })

    if not resp or not resp.get('success'):
        print(f"    ERRORE preparazione: {resp}")
        return None

    task_id = resp['data'].get('task_id')
    already_prepared = resp['data'].get('already_prepared', False)

    if already_prepared:
        print(f"    Preparazione gia' completata")
    elif task_id:
        print(f"    Task ID: {task_id}")
        success = wait_for_preparation(base_url, simulation_id, task_id)
        if not success:
            return None

    # 3. Avvia simulazione (max 5 round per il pilota)
    print(f"  3. Avvio simulazione (max_rounds=5)...")
    resp = api_call(base_url, '/api/simulation/start', {
        'simulation_id': simulation_id,
        'platform': 'reddit',
        'max_rounds': 5,
        'force': True
    })

    if not resp or not resp.get('success'):
        print(f"    ERRORE avvio: {resp}")
        return None

    print(f"    Simulazione avviata!")

    # 4. Attendi completamento
    print(f"  4. Monitoraggio...")
    success = wait_for_simulation(base_url, simulation_id)

    return {
        'simulation_id': simulation_id,
        'condition': condition_id,
        'label': cond['label'],
        'profiles_path': profiles_path,
        'success': success
    }


def main():
    parser = argparse.ArgumentParser(
        description='Esegui test Caro-Benzina su MiroFish-IT (via API)'
    )
    parser.add_argument('--condition', type=str, default='all',
                       choices=['A', 'B', 'C', 'all'],
                       help='Condizione da eseguire (default: all)')
    parser.add_argument('--base-url', type=str, default='http://localhost:5001',
                       help='URL base del backend MiroFish-IT')
    parser.add_argument('--project-id', type=str, default=None,
                       help='ID progetto esistente (se omesso, usa un ID di test)')
    parser.add_argument('--graph-id', type=str, default=None,
                       help='ID grafo Zep esistente (se omesso, usa un ID fittizio)')
    args = parser.parse_args()

    print("=" * 70)
    print("  MiroFish-IT — Test Caro-Benzina (via API)")
    print(f"  Backend: {args.base_url}")
    print("=" * 70)

    # Verifica connessione backend
    print(f"\n  Verifica connessione backend...")
    try:
        req = urllib.request.Request(f"{args.base_url}/api/simulation/list",
                                     headers={'Content-Type': 'application/json'},
                                     method='GET')
        with urllib.request.urlopen(req, timeout=5) as resp:
            print(f"    Backend raggiungibile (HTTP {resp.status})")
    except Exception as e:
        print(f"    ERRORE: Backend non raggiungibile su {args.base_url}")
        print(f"    Assicurati che sia in esecuzione (npm run dev)")
        print(f"    Dettaglio: {e}")
        sys.exit(1)

    # Verifica profili generati
    for cond_id, cond_info in CONDITIONS.items():
        path = os.path.join(PROFILES_DIR, cond_info['file'])
        if not os.path.exists(path):
            print(f"\n  ERRORE: Profili mancanti per condizione {cond_id}")
            print(f"  Esegui prima: python3 backend/data/test_caro_benzina/generate_profiles.py")
            sys.exit(1)

    # ID progetto e grafo
    project_id = args.project_id or 'test_caro_benzina'
    graph_id = args.graph_id or 'graph_caro_benzina'

    # Determina condizioni
    if args.condition == 'all':
        conditions_to_run = ['A', 'B', 'C']
    else:
        conditions_to_run = [args.condition]

    results = {}
    from datetime import datetime

    for cond_id in conditions_to_run:
        cond = CONDITIONS[cond_id]
        print(f"\n{'=' * 70}")
        print(f"  CONDIZIONE {cond_id}: {cond['label']}")
        print(f"  {cond['description']}")
        print(f"{'=' * 70}")

        result = run_condition(args.base_url, cond_id, project_id, graph_id)
        results[cond_id] = result

        if result and result['success']:
            print(f"\n  Condizione {cond_id} completata con successo!")
        else:
            print(f"\n  Condizione {cond_id} FALLITA")

    # Riepilogo
    print(f"\n{'=' * 70}")
    print(f"  RIEPILOGO TEST CARO-BENZINA")
    print(f"{'=' * 70}")

    for cond_id in conditions_to_run:
        result = results.get(cond_id)
        if result:
            status = "OK" if result['success'] else "ERRORE"
            print(f"  {cond_id} ({result['label']}): {status} — sim_id={result['simulation_id']}")
        else:
            print(f"  {cond_id}: FALLITA (nessun risultato)")

    # Salva indice
    experiment_index = {
        'experiment_id': f"caro_benzina_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
        'conditions': {
            cond_id: {
                'label': CONDITIONS[cond_id]['label'],
                'sim_id': r['simulation_id'] if r else None,
                'sim_dir': None,  # Determinato dal backend
                'success': r['success'] if r else False
            }
            for cond_id, r in results.items()
        },
        'base_url': args.base_url,
        'created_at': datetime.now().isoformat()
    }

    index_path = os.path.join(SCRIPT_DIR, 'last_experiment.json')
    with open(index_path, 'w', encoding='utf-8') as f:
        json.dump(experiment_index, f, ensure_ascii=False, indent=2)

    print(f"\n  Indice salvato: {index_path}")
    print(f"\n  Per analizzare i risultati:")
    print(f"  python3 backend/data/test_caro_benzina/analyze_results.py")
    print(f"{'=' * 70}")


if __name__ == '__main__':
    main()
