"""
Validazione test Caro-Benzina — verifica coerenza profili,
distribuzione demografica, e differenziazione tra condizioni.
"""

import json
import os
import sys
from collections import Counter

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROFILES_DIR = os.path.join(SCRIPT_DIR, 'profiles')
PROCESSED_DIR = os.path.join(SCRIPT_DIR, '..', 'processed')


def load_json(path):
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def main():
    print("=" * 70)
    print("  MiroFish-IT — Validazione Test Caro-Benzina")
    print("=" * 70)

    # Carica dati
    templates = load_json(os.path.join(SCRIPT_DIR, 'agent_templates.json'))
    scenario = load_json(os.path.join(SCRIPT_DIR, 'scenario.json'))
    scenario_cal = load_json(os.path.join(SCRIPT_DIR, 'scenario_calibration.json'))
    calibration = load_json(os.path.join(PROCESSED_DIR, 'calibration_profiles.json'))

    cond_a = load_json(os.path.join(PROFILES_DIR, 'condition_a_baseline.json'))
    cond_b = load_json(os.path.join(PROFILES_DIR, 'condition_b_country.json'))
    cond_c = load_json(os.path.join(PROFILES_DIR, 'condition_c_nuts2.json'))

    errors = []

    # 1. Verifica conteggi
    print(f"\n--- Conteggio profili ---")
    for label, profiles in [('A', cond_a), ('B', cond_b), ('C', cond_c)]:
        print(f"  Condizione {label}: {len(profiles)} profili")
        if len(profiles) != 60:
            errors.append(f"Condizione {label}: attesi 60 profili, trovati {len(profiles)}")

    # 2. Distribuzione regionale
    print(f"\n--- Distribuzione regionale (per condizione) ---")
    for label, profiles in [('A', cond_a), ('B', cond_b), ('C', cond_c)]:
        regions = Counter()
        for p in profiles:
            # Determina regione dal comune_name o nuts2_region
            for region_code in ['ITC4', 'ITF3', 'ITG1']:
                region_names = [t['comune_name'] for t in templates.get(region_code, [])]
                if p.get('comune_name') in region_names:
                    regions[region_code] += 1
                    break
        print(f"  Condizione {label}: {dict(regions)}")
        for r in ['ITC4', 'ITF3', 'ITG1']:
            if regions.get(r, 0) != 20:
                errors.append(f"Condizione {label}, regione {r}: attesi 20, trovati {regions.get(r, 0)}")

    # 3. Distribuzione demografica
    print(f"\n--- Distribuzione demografica (su 60 agenti) ---")
    all_agents = []
    for region_code in ['ITC4', 'ITF3', 'ITG1']:
        all_agents.extend(templates[region_code])

    genders = Counter(a['gender'] for a in all_agents)
    age_brackets = Counter()
    for a in all_agents:
        if a['age'] < 30:
            age_brackets['18-29'] += 1
        elif a['age'] < 45:
            age_brackets['30-44'] += 1
        elif a['age'] < 60:
            age_brackets['45-59'] += 1
        else:
            age_brackets['60+'] += 1

    education = Counter(a['education'] for a in all_agents)
    comune_types = Counter(a['comune_type'] for a in all_agents)
    auto_counts = Counter(a['n_auto'] for a in all_agents)

    print(f"  Genere: {dict(genders)}")
    print(f"  Fasce eta: {dict(age_brackets)}")
    print(f"  Tipo comune: {dict(comune_types)}")
    print(f"  Auto possedute: {dict(auto_counts)}")

    # 4. Lunghezza persona — confronto tra condizioni
    print(f"\n--- Lunghezza media persona (caratteri) ---")
    for label, profiles in [('A', cond_a), ('B', cond_b), ('C', cond_c)]:
        lengths = [len(p['persona']) for p in profiles]
        avg = sum(lengths) / len(lengths)
        min_l = min(lengths)
        max_l = max(lengths)
        print(f"  Condizione {label}: media {avg:.0f}, min {min_l}, max {max_l}")

    if sum(len(p['persona']) for p in cond_a) >= sum(len(p['persona']) for p in cond_c):
        errors.append("Condizione A non dovrebbe avere persona piu lunghe di Condizione C")

    # 5. Verifica differenziazione — parole chiave
    print(f"\n--- Verifica differenziazione tra condizioni ---")

    # Condizione A non dovrebbe contenere dati specifici
    region_markers = ['EUR/l', 'UAI=', 'IDV=', 'EUR/anno']
    a_has_data = sum(1 for p in cond_a if any(m in p['persona'] for m in region_markers))
    b_has_data = sum(1 for p in cond_b if any(m in p['persona'] for m in region_markers))
    c_has_data = sum(1 for p in cond_c if any(m in p['persona'] for m in region_markers))

    print(f"  Profili con dati quantitativi: A={a_has_data}/60, B={b_has_data}/60, C={c_has_data}/60")

    if a_has_data > 0:
        errors.append(f"Condizione A contiene {a_has_data} profili con dati quantitativi (dovrebbe essere 0)")

    # Condizione C dovrebbe contenere nomi propri
    names_in_c = sum(1 for p in cond_c if p['name'] in p['persona'])
    names_in_a = sum(1 for p in cond_a if p['name'] in p['persona'])
    print(f"  Nomi propri nella persona: A={names_in_a}/60, C={names_in_c}/60")

    # Condizione C dovrebbe contenere nomi di comuni
    comuni_in_c = sum(1 for p in cond_c if p.get('comune_name', '') in p['persona'])
    comuni_in_a = sum(1 for p in cond_a if p.get('comune_name', '') in p['persona'])
    print(f"  Nomi comuni nella persona: A={comuni_in_a}/60, C={comuni_in_c}/60")

    # 6. Confronto economico tra regioni (Condizione C)
    print(f"\n--- Confronto reddito agenti per regione (Condizione C) ---")
    for region_code, region_name in [('ITC4', 'Lombardia'), ('ITF3', 'Campania'), ('ITG1', 'Sicilia')]:
        agents = templates[region_code]
        incomes = [a['income_net_eur'] for a in agents if a['income_net_eur'] > 0]
        avg_income = sum(incomes) / len(incomes) if incomes else 0
        print(f"  {region_name} ({region_code}): reddito medio agenti {avg_income:,.0f} EUR, "
              f"calibrazione ICF {calibration[region_code]['layers']['economic']['ibf']['net_income_mean']:,} EUR")

    # 7. Verifica coerenza scenario
    print(f"\n--- Coerenza scenario ---")
    print(f"  Titolo: {scenario['title']}")
    print(f"  Regioni: {len(scenario['regions_involved'])}")
    print(f"  Dimensioni reazione: {len(scenario['reaction_dimensions'])}")
    print(f"  Fonti ground truth: {len(scenario['ground_truth_sources'])}")

    if scenario['agents_per_region'] != 20:
        errors.append(f"scenario.json agents_per_region dovrebbe essere 20, trovato {scenario['agents_per_region']}")
    if scenario['total_agents'] != 180:
        errors.append(f"scenario.json total_agents dovrebbe essere 180, trovato {scenario['total_agents']}")

    # 8. Verifica che scenario_calibration abbia tutte le regioni
    for r in ['ITC4', 'ITF3', 'ITG1']:
        if r not in scenario_cal:
            errors.append(f"Regione {r} mancante in scenario_calibration.json")
        else:
            required_fields = ['benzina_self_eur_l', 'gasolio_self_eur_l', 'variazione_2_settimane_pct',
                             'incidenza_carburante_pct_budget', 'uso_tpl_pct', 'acquisti_online_pct']
            for field in required_fields:
                if field not in scenario_cal[r]:
                    errors.append(f"Campo {field} mancante per {r} in scenario_calibration.json")

    # Risultato
    print(f"\n{'=' * 70}")
    if errors:
        print(f"  ATTENZIONE: {len(errors)} problemi trovati:")
        for e in errors:
            print(f"    - {e}")
    else:
        print("  VALIDAZIONE OK — test Caro-Benzina pronto per la simulazione")
    print(f"{'=' * 70}")

    return len(errors) == 0


if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)
