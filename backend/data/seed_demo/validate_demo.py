"""
Validazione seed demo italiano — verifica che i profili siano
coerenti con i dati di calibrazione ICF regionali.
"""

import json
import os
import sys

DEMO_DIR = os.path.dirname(os.path.abspath(__file__))
PROCESSED_DIR = os.path.join(DEMO_DIR, '..', 'processed')


def load_json(path):
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def main():
    print("=" * 70)
    print("  MiroFish-IT — Validazione Seed Demo Italiano")
    print("  Scenario: Dibattito Superbonus 110%")
    print("=" * 70)

    # Carica dati
    profiles = load_json(os.path.join(DEMO_DIR, 'reddit_profiles.json'))
    scenario = load_json(os.path.join(DEMO_DIR, 'scenario.json'))
    calibration = load_json(os.path.join(PROCESSED_DIR, 'calibration_profiles.json'))

    print(f"\nScenario: {scenario['title']}")
    print(f"Agenti: {len(profiles)}")
    print(f"Regioni coinvolte: {len(scenario['regions_involved'])}")
    print(f"Profili calibrazione disponibili: {len(calibration)}")

    # Valida ogni profilo
    print(f"\n{'Nome':<30} {'Regione':<8} {'Zona':<8} {'Età':<5} {'Professione':<30} {'MBTI':<5}")
    print("-" * 90)

    errors = []
    for p in profiles:
        region = p.get('nuts2_region')
        cal = calibration.get(region, {})
        zone = cal.get('cultural_zone', '?')
        name = p['name']

        print(f"{name:<30} {region:<8} {zone:<8} {p.get('age', '?'):<5} {p.get('profession', '?'):<30} {p.get('mbti', '?'):<5}")

        # Verifica coerenza
        if not region:
            errors.append(f"{name}: manca nuts2_region")
        elif region not in calibration:
            errors.append(f"{name}: regione {region} non trovata nei dati di calibrazione")

        if p.get('country') != 'Italia':
            errors.append(f"{name}: country dovrebbe essere 'Italia', trovato '{p.get('country')}'")

        if not p.get('persona'):
            errors.append(f"{name}: manca persona")
        elif len(p['persona']) < 200:
            errors.append(f"{name}: persona troppo corta ({len(p['persona'])} car)")

        if p.get('gender') == 'other' and p.get('age') != 30:
            errors.append(f"{name}: account istituzionale (gender=other) dovrebbe avere age=30")

    # Verifica distribuzione regionale
    print("\n--- Distribuzione regionale ---")
    region_counts = {}
    zone_counts = {}
    for p in profiles:
        r = p.get('nuts2_region', '?')
        z = calibration.get(r, {}).get('cultural_zone', '?')
        region_counts[r] = region_counts.get(r, 0) + 1
        zone_counts[z] = zone_counts.get(z, 0) + 1

    for r, c in sorted(region_counts.items()):
        cal = calibration.get(r, {})
        print(f"  {r} ({cal.get('name', '?'):<20}): {c} agenti")

    print(f"\n  Nord: {zone_counts.get('north', 0)} | Centro: {zone_counts.get('center', 0)} | Sud: {zone_counts.get('south', 0)}")

    # Confronto economico Nord vs Sud
    print("\n--- Confronto calibrazione economica ---")
    north_agents = [p for p in profiles if calibration.get(p.get('nuts2_region'), {}).get('cultural_zone') == 'north']
    south_agents = [p for p in profiles if calibration.get(p.get('nuts2_region'), {}).get('cultural_zone') == 'south']

    if north_agents and south_agents:
        n_region = north_agents[0]['nuts2_region']
        s_region = south_agents[0]['nuts2_region']
        n_cal = calibration[n_region]['layers']['economic'].get('ibf', {})
        s_cal = calibration[s_region]['layers']['economic'].get('ibf', {})

        print(f"  {'Indicatore':<30} {'Nord (' + n_region + ')':<15} {'Sud (' + s_region + ')':<15} {'Delta':>10}")
        print("  " + "-" * 72)
        for key in ['net_income_mean', 'net_wealth_mean', 'saving_rate_pct', 'home_ownership_pct']:
            n_val = n_cal.get(key, 0)
            s_val = s_cal.get(key, 0)
            delta = n_val - s_val
            print(f"  {key:<30} {n_val:>13,} {s_val:>13,} {delta:>+10,}")

    # Verifica Hofstede
    print("\n--- Confronto Hofstede regionale ---")
    print(f"  {'Dimensione':<6} {'Nord':<8} {'Centro':<8} {'Sud':<8} {'Differenza N-S':>15}")
    print("  " + "-" * 50)
    for dim in ['PDI', 'IDV', 'MAS', 'UAI', 'LTO', 'IVR']:
        n_val = calibration.get('ITC4', {}).get('layers', {}).get('cultural', {}).get('hofstede_6d', {}).get(dim, {}).get('regional_estimate', 0)
        c_val = calibration.get('ITI4', {}).get('layers', {}).get('cultural', {}).get('hofstede_6d', {}).get(dim, {}).get('regional_estimate', 0)
        s_val = calibration.get('ITF3', {}).get('layers', {}).get('cultural', {}).get('hofstede_6d', {}).get(dim, {}).get('regional_estimate', 0)
        print(f"  {dim:<6} {n_val:<8} {c_val:<8} {s_val:<8} {n_val - s_val:>+15}")

    # Risultato
    print(f"\n{'=' * 70}")
    if errors:
        print(f"  ATTENZIONE: {len(errors)} problemi trovati:")
        for e in errors:
            print(f"    - {e}")
    else:
        print("  VALIDAZIONE OK — tutti i profili sono coerenti con la calibrazione ICF")
    print(f"{'=' * 70}")

    return len(errors) == 0


if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)
