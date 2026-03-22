"""
Analisi risultati test Caro-Benzina — confronto 3 condizioni.

Legge le azioni da ciascuna condizione e confronta:
- Volume e tipo di azioni per regione
- Contenuto dei post (analisi keyword per le 5 dimensioni)
- Differenziazione regionale per condizione
- Metriche per il paper (diversita, correlazione con attese)

Uso:
    cd backend
    python3 data/test_caro_benzina/analyze_results.py
"""

import json
import os
import re
import sys
from collections import Counter, defaultdict

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROFILES_DIR = os.path.join(SCRIPT_DIR, 'profiles')


def load_json(path):
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def load_jsonl(path):
    """Carica file JSONL (una riga JSON per linea)."""
    entries = []
    if not os.path.exists(path):
        return entries
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return entries


# ---------- Keyword per le 5 dimensioni ----------

DIMENSION_KEYWORDS = {
    'mobility': [
        'auto', 'macchina', 'benzina', 'gasolio', 'carburante', 'pieno',
        'metro', 'bus', 'treno', 'tram', 'bici', 'bicicletta', 'carsharing',
        'car sharing', 'spostament', 'pendolar', 'guido', 'guidare',
        'trasporto pubblico', 'tpl', 'abbonamento', 'a piedi', 'camminare'
    ],
    'discretionary_spending': [
        'ristorant', 'pizz', 'bar', 'caffe', 'aperitiv', 'cena fuori',
        'abbigliamento', 'vestit', 'scarpe', 'shopping', 'beauty', 'estetist',
        'parrucchier', 'palestra', 'cinema', 'teatro', 'vacanz', 'weekend',
        'uscit', 'svago', 'divertiment', 'taglio', 'rinunci', 'eliminat'
    ],
    'purchase_channel': [
        'online', 'amazon', 'e-commerce', 'ecommerce', 'internet',
        'negozio', 'bottega', 'mercato', 'supermercato', 'discount',
        'consegna a domicilio', 'delivery', 'ordine online', 'spesa online',
        'acquist', 'compro', 'comprare'
    ],
    'brand_choice': [
        'marca', 'brand', 'premium', 'lusso', 'discount', 'lidl', 'eurospin',
        'aldi', 'md', 'penny', 'marca del distributore', 'primo prezzo',
        'risparmio', 'economico', 'sottomarca', 'qualita', 'prodotto locale'
    ],
    'prioritization': [
        'priorit', 'prima cosa', 'essenziale', 'necessario', 'indispensabile',
        'sacrific', 'rinunci', 'togliere', 'eliminare', 'proteggo', 'protegge',
        'alimentar', 'bollette', 'affitto', 'mutuo', 'medicine', 'salute',
        'figli', 'scuola', 'ultimo', 'prima', 'poi'
    ]
}


def get_agent_region(agent_name, profiles):
    """Determina la regione di un agente dal nome."""
    for p in profiles:
        if p['name'] == agent_name:
            return p.get('comune_name', ''), p.get('nuts2_region', '')
    return '', ''


def classify_region(comune_name, agent_templates):
    """Classifica un agente per regione usando i template."""
    for region_code, agents in agent_templates.items():
        if region_code.startswith('_'):
            continue
        for a in agents:
            if a['comune_name'] == comune_name:
                return region_code
    return 'unknown'


def count_dimension_mentions(text, dimension_keywords):
    """Conta menzioni di keyword per dimensione in un testo."""
    text_lower = text.lower()
    counts = {}
    for dim, keywords in dimension_keywords.items():
        count = sum(1 for kw in keywords if kw in text_lower)
        counts[dim] = count
    return counts


def analyze_condition(actions, profiles, condition_label, agent_templates):
    """Analizza le azioni di una condizione."""
    print(f"\n{'=' * 60}")
    print(f"  Condizione: {condition_label}")
    print(f"{'=' * 60}")

    if not actions:
        print("  Nessuna azione trovata.")
        return {}

    # Filtra solo azioni di agenti (no eventi di sistema)
    agent_actions = [a for a in actions if 'agent_name' in a and a.get('success', True)]
    system_events = [a for a in actions if 'event_type' in a]

    print(f"  Azioni totali: {len(actions)}")
    print(f"  Azioni agenti: {len(agent_actions)}")
    print(f"  Eventi sistema: {len(system_events)}")

    # Distribuzione tipi azione
    action_types = Counter(a.get('action_type', 'unknown') for a in agent_actions)
    print(f"\n  Tipi azione: {dict(action_types)}")

    # Post e commenti (contenuto testuale)
    content_actions = [
        a for a in agent_actions
        if a.get('action_type') in ('CREATE_POST', 'CREATE_COMMENT')
        and a.get('action_args', {}).get('content')
    ]
    print(f"  Post/commenti con contenuto: {len(content_actions)}")

    # Analisi per regione
    region_stats = defaultdict(lambda: {
        'n_actions': 0,
        'n_posts': 0,
        'content_length_total': 0,
        'dimension_mentions': Counter()
    })

    for a in agent_actions:
        agent_name = a.get('agent_name', '')
        comune, nuts2 = get_agent_region(agent_name, profiles)
        region = classify_region(comune, agent_templates) if comune else 'unknown'

        region_stats[region]['n_actions'] += 1

        content = a.get('action_args', {}).get('content', '')
        if content:
            region_stats[region]['n_posts'] += 1
            region_stats[region]['content_length_total'] += len(content)

            dims = count_dimension_mentions(content, DIMENSION_KEYWORDS)
            for dim, count in dims.items():
                region_stats[region]['dimension_mentions'][dim] += count

    # Report per regione
    print(f"\n  --- Per regione ---")
    region_names = {'ITC4': 'Lombardia', 'ITF3': 'Campania', 'ITG1': 'Sicilia'}

    for region in ['ITC4', 'ITF3', 'ITG1']:
        stats = region_stats.get(region, {})
        n_actions = stats.get('n_actions', 0)
        n_posts = stats.get('n_posts', 0)
        avg_len = (stats.get('content_length_total', 0) / n_posts) if n_posts > 0 else 0

        print(f"\n  {region_names.get(region, region)} ({region}):")
        print(f"    Azioni: {n_actions}, Post/commenti: {n_posts}, Lunghezza media: {avg_len:.0f} car")

        dims = stats.get('dimension_mentions', Counter())
        if dims:
            print(f"    Dimensioni menzionate:")
            for dim in ['mobility', 'discretionary_spending', 'purchase_channel', 'brand_choice', 'prioritization']:
                bar = '#' * min(dims.get(dim, 0), 30)
                print(f"      {dim:<25} {dims.get(dim, 0):>3} {bar}")

    # Analisi diversita regionale (varianza tra regioni)
    print(f"\n  --- Diversita regionale ---")
    for dim in DIMENSION_KEYWORDS:
        values = []
        for region in ['ITC4', 'ITF3', 'ITG1']:
            stats = region_stats.get(region, {})
            n_posts = stats.get('n_posts', 1)
            mentions = stats.get('dimension_mentions', Counter()).get(dim, 0)
            values.append(mentions / max(n_posts, 1))  # normalizzato per post

        if values:
            mean_val = sum(values) / len(values)
            variance = sum((v - mean_val) ** 2 for v in values) / len(values)
            print(f"    {dim:<25} varianza: {variance:.4f}  valori: {[f'{v:.2f}' for v in values]}")

    return {
        'n_actions': len(agent_actions),
        'n_content': len(content_actions),
        'action_types': dict(action_types),
        'region_stats': {
            r: {
                'n_actions': s.get('n_actions', 0),
                'n_posts': s.get('n_posts', 0),
                'dimensions': dict(s.get('dimension_mentions', {}))
            }
            for r, s in region_stats.items()
        }
    }


def main():
    print("=" * 70)
    print("  MiroFish-IT — Analisi Risultati Test Caro-Benzina")
    print("=" * 70)

    # Carica indice esperimento
    index_path = os.path.join(SCRIPT_DIR, 'last_experiment.json')
    if not os.path.exists(index_path):
        print("\n  ERRORE: File last_experiment.json non trovato.")
        print("  Esegui prima: python3 data/test_caro_benzina/run_experiment.py")
        sys.exit(1)

    experiment = load_json(index_path)
    agent_templates = load_json(os.path.join(SCRIPT_DIR, 'agent_templates.json'))

    print(f"\n  Esperimento: {experiment['experiment_id']}")
    print(f"  Round: {experiment['max_rounds']}")

    all_results = {}

    for cond_id, cond_data in experiment['conditions'].items():
        sim_dir = cond_data['sim_dir']
        label = cond_data['label']

        # Carica azioni
        actions_path = os.path.join(sim_dir, 'reddit', 'actions.jsonl')
        actions = load_jsonl(actions_path)

        # Carica profili della condizione
        profile_file = CONDITIONS_MAP.get(cond_id, '')
        profiles_path = os.path.join(PROFILES_DIR, profile_file)
        profiles = load_json(profiles_path) if os.path.exists(profiles_path) else []

        results = analyze_condition(actions, profiles, f"{cond_id} — {label}", agent_templates)
        all_results[cond_id] = results

    # Confronto tra condizioni
    print(f"\n{'=' * 70}")
    print(f"  CONFRONTO TRA CONDIZIONI")
    print(f"{'=' * 70}")

    print(f"\n  {'Metrica':<30} {'A (Baseline)':>15} {'B (Country)':>15} {'C (NUTS-2)':>15}")
    print(f"  {'-' * 75}")

    for metric in ['n_actions', 'n_content']:
        values = [str(all_results.get(c, {}).get(metric, 0)) for c in ['A', 'B', 'C']]
        label = 'Azioni totali' if metric == 'n_actions' else 'Post/commenti'
        print(f"  {label:<30} {values[0]:>15} {values[1]:>15} {values[2]:>15}")

    # Diversita tra regioni per condizione
    print(f"\n  --- Diversita regionale (varianza normalizzata) ---")
    print(f"  Una varianza piu alta nella Condizione C indica maggiore")
    print(f"  differenziazione regionale = migliore calibrazione ICF.")

    for dim in DIMENSION_KEYWORDS:
        print(f"\n  {dim}:")
        for cond_id in ['A', 'B', 'C']:
            rs = all_results.get(cond_id, {}).get('region_stats', {})
            values = []
            for region in ['ITC4', 'ITF3', 'ITG1']:
                n_posts = rs.get(region, {}).get('n_posts', 1)
                mentions = rs.get(region, {}).get('dimensions', {}).get(dim, 0)
                values.append(mentions / max(n_posts, 1))

            mean_val = sum(values) / max(len(values), 1)
            variance = sum((v - mean_val) ** 2 for v in values) / max(len(values), 1)
            print(f"    {cond_id} ({CONDITIONS_MAP_LABELS[cond_id]:<12}): var={variance:.4f}  {[f'{v:.2f}' for v in values]}")

    print(f"\n{'=' * 70}")
    print(f"  IPOTESI DA VERIFICARE:")
    print(f"  - Condizione C dovrebbe avere varianza regionale PIU ALTA di A e B")
    print(f"  - Agenti Sicilia/Campania (C) dovrebbero menzionare piu 'mobilita' e 'prioritizzazione'")
    print(f"  - Agenti Lombardia (C) dovrebbero menzionare piu 'canale d'acquisto' e 'scelta di marca'")
    print(f"  - Condizioni A e B dovrebbero produrre reazioni piu uniformi tra regioni")
    print(f"{'=' * 70}")


# Mappature
CONDITIONS_MAP = {
    'A': 'condition_a_baseline.json',
    'B': 'condition_b_country.json',
    'C': 'condition_c_nuts2.json'
}

CONDITIONS_MAP_LABELS = {
    'A': 'Baseline',
    'B': 'Country',
    'C': 'NUTS-2'
}


if __name__ == '__main__':
    main()
