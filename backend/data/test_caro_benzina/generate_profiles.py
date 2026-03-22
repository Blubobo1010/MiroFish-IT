"""
Generatore profili test Caro-Benzina — 3 condizioni sperimentali.

Prende i 60 template agenti e genera 3 set di profili:
  - Condizione A (Baseline): profilo generico senza dati reali
  - Condizione B (Country-level): dati nazionali aggregati
  - Condizione C (NUTS-2 Full): profilo calibrato con 4 strati di dati reali

Output: profiles/condition_a_baseline.json, condition_b_country.json, condition_c_nuts2.json
"""

import json
import os
import random
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROCESSED_DIR = os.path.join(SCRIPT_DIR, '..', 'processed')
PROFILES_DIR = os.path.join(SCRIPT_DIR, 'profiles')


def load_json(path):
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_json(data, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"  Salvato: {path} ({len(data)} profili)")


# ---------- Generazione username ----------

def make_username(name):
    """Genera username stile Reddit dal nome."""
    parts = name.lower().replace("'", "").split()
    base = "_".join(parts)
    suffix = random.randint(100, 999)
    return f"{base}_{suffix}"


# ---------- Mappa zona generica ----------

ZONE_LABELS = {
    "north": "una grande citta del nord Italia",
    "south": "una citta del sud Italia",
}

ZONE_LABELS_GENERIC = {
    "ITC4": "una grande citta del nord Italia",
    "ITF3": "una citta del sud Italia",
    "ITG1": "un'area del sud Italia",
}


# ---------- Condizione A — Baseline ----------

def build_persona_baseline(agent, scenario_cal):
    """Profilo generico. Nessun dato reale. Il modello inventa tutto."""
    a = agent
    zone_desc = ZONE_LABELS_GENERIC.get(a.get('_region', ''), 'Italia')

    # Genere
    if a['gender'] == 'male':
        art = 'un consumatore italiano'
    else:
        art = 'una consumatrice italiana'

    persona = (
        f"Sei {art}, {a['age']} anni, vivi in {zone_desc} "
        f"con la tua famiglia. "
        f"Lavori come {a['profession'].lower()}. "
        f"La benzina e il gasolio sono aumentati molto nelle ultime settimane."
    )
    return persona


# ---------- Condizione B — Country-level ----------

def build_persona_country(agent, scenario_cal):
    """Dati nazionali aggregati. Nessuna differenziazione regionale."""
    a = agent
    nat = scenario_cal['national']

    if a['gender'] == 'male':
        art = 'un consumatore italiano'
    else:
        art = 'una consumatrice italiana'

    persona = (
        f"Sei {art}, {a['age']} anni. "
        f"Il reddito medio familiare netto in Italia e circa {nat['reddito_medio_familiare_netto_eur']:,} EUR/anno. "
        f"L'Italia ha un alto indice di avversione all'incertezza (Hofstede UAI={nat['hofstede']['UAI']}) "
        f"e un basso indice di indulgenza (IVR={nat['hofstede']['IVR']}). "
        f"La benzina in Italia costa mediamente {nat['benzina_self_media_eur_l']:.3f} EUR/litro, "
        f"in aumento del {nat['variazione_2_settimane_pct']:.0f}% in 2 settimane. "
        f"Il gasolio ha superato {nat['gasolio_self_media_eur_l']:.3f} EUR/litro. "
        f"In Italia ci sono circa {nat['auto_per_1000_abitanti']} auto ogni 1.000 abitanti. "
        f"Il {nat['uso_tpl_pct']}% della popolazione usa il trasporto pubblico locale. "
        f"Il {nat['acquisti_online_pct']}% fa acquisti online."
    )
    return persona


# ---------- Condizione C — NUTS-2 Full ----------

def build_persona_nuts2(agent, scenario_cal, calibration):
    """Profilo calibrato con 4 strati di dati reali regionali."""
    a = agent
    region_code = a['_region']
    reg = scenario_cal[region_code]
    cal = calibration.get(region_code, {})

    # Layer economico da calibrazione ICF
    ibf = cal.get('layers', {}).get('economic', {}).get('ibf', {})
    demo = cal.get('layers', {}).get('demographic', {})
    cultural = cal.get('layers', {}).get('cultural', {}).get('hofstede_6d', {})
    social = cal.get('layers', {}).get('social', {})

    # Hofstede regionale
    uai = cultural.get('UAI', {}).get('regional_estimate', 75)
    ivr = cultural.get('IVR', {}).get('regional_estimate', 30)
    idv = cultural.get('IDV', {}).get('regional_estimate', 76)
    pdi = cultural.get('PDI', {}).get('regional_estimate', 50)

    # Fiducia
    trust_people = social.get('trust_people', 5.0)
    trust_institutions = social.get('trust_legal_system', 4.5)

    # Costruzione persona narrativa
    lines = []

    # Identita
    lines.append(
        f"Sei {a['name']}, {a['age']} anni, {a['comune_name']}."
    )

    # Istruzione e lavoro
    lines.append(
        f"{a['education']}, {a['profession'].lower()}."
    )

    # Famiglia e reddito
    lines.append(
        f"Reddito familiare netto ~{a['income_net_eur']:,} EUR/anno. {a['family']}."
    )

    # Mobilita
    auto_line = f"{a['auto_desc'].capitalize()}."
    if a['uso_tpl']:
        auto_line += f" Usi anche il trasporto pubblico."
    else:
        if reg.get('copertura_tpl', '').startswith('Scarsa') or 'inesistente' in reg.get('copertura_tpl', ''):
            auto_line += f" Nella tua zona il trasporto pubblico e quasi inesistente."
        elif 'Molto scarsa' in reg.get('copertura_tpl', ''):
            auto_line += f" Nella tua zona il trasporto pubblico e molto scarso."

    lines.append(auto_line)

    # Shock carburante
    if a['km_anno'] > 0:
        fuel_type = "gasolio" if a['km_anno'] > 15000 else "benzina"
        fuel_price = reg['gasolio_self_eur_l'] if fuel_type == "gasolio" else reg['benzina_self_eur_l']
        lines.append(
            f"Il {fuel_type} nella tua zona costa {fuel_price:.2f} EUR/l, "
            f"+{reg['variazione_2_settimane_pct']:.1f}% in 2 settimane."
        )

    # Incidenza su budget
    if a['income_net_eur'] > 0:
        fuel_cost_month = (a['km_anno'] / 12) * (reg['gasolio_self_eur_l'] / 14)  # ~14 km/l media
        fuel_pct = (fuel_cost_month * 12) / a['income_net_eur'] * 100
        lines.append(
            f"Il carburante pesa circa il {fuel_pct:.1f}% del vostro budget mensile."
        )
    elif a['km_anno'] == 0 and a['n_auto'] == 0:
        lines.append("Non hai un'auto e non spendi direttamente in carburante.")

    # Canale acquisti
    if a['acquisti_online']:
        lines.append(f"Fai acquisti online regolarmente.")
    else:
        if reg['acquisti_online_pct'] < 35:
            lines.append(f"Non fai acquisti online. Compri tutto in negozi locali e al mercato.")
        else:
            lines.append(f"Fai quasi tutti gli acquisti in negozi fisici.")

    # Contesto culturale regionale (sintetico)
    if uai > 78:
        lines.append(
            f"Nella tua zona c'e una forte avversione all'incertezza (UAI={uai}): "
            f"i cambiamenti improvvisi creano ansia."
        )
    if idv < 72:
        lines.append(
            f"La tua comunita e relativamente collettivista (IDV={idv}): "
            f"le decisioni di spesa si discutono in famiglia e con i vicini."
        )
    if trust_people < 5.0:
        lines.append(
            f"La fiducia interpersonale nella tua zona e bassa ({trust_people}/10): "
            f"c'e diffidenza verso le istituzioni e sospetto di speculazione."
        )

    persona = " ".join(lines)
    return persona


# ---------- Costruzione profilo completo formato Reddit ----------

def build_reddit_profile(agent, persona, condition, region_code):
    """Costruisce un profilo nel formato Reddit di MiroFish/OASIS."""
    return {
        "user_id": agent['id'] + (0 if condition == 'A' else 60 if condition == 'B' else 120),
        "username": make_username(agent['name']),
        "name": agent['name'],
        "bio": f"{agent['profession']}, {agent['age']} anni, {agent['comune_name']}",
        "persona": persona,
        "karma": random.randint(500, 5000),
        "age": agent['age'],
        "gender": agent['gender'],
        "mbti": agent['mbti'],
        "country": "Italia",
        "profession": agent['profession'],
        "interested_topics": agent['topics'],
        "nuts2_region": region_code if condition == 'C' else None,
        "condition": condition,
        "comune_type": agent['comune_type'],
        "comune_name": agent['comune_name'],
        "created_at": "2026-03-18"
    }


# ---------- Main ----------

def main():
    print("=" * 70)
    print("  MiroFish-IT — Generatore Profili Test Caro-Benzina")
    print("  60 agenti x 3 condizioni = 180 profili")
    print("=" * 70)

    # Carica dati (usa pilot se disponibile, altrimenti template completi)
    pilot_path = os.path.join(SCRIPT_DIR, 'agent_templates_pilot.json')
    full_path = os.path.join(SCRIPT_DIR, 'agent_templates.json')
    templates_path = pilot_path if os.path.exists(pilot_path) else full_path
    templates = load_json(templates_path)
    print(f"  Template: {os.path.basename(templates_path)}")
    scenario_cal = load_json(os.path.join(SCRIPT_DIR, 'scenario_calibration.json'))
    calibration = load_json(os.path.join(PROCESSED_DIR, 'calibration_profiles.json'))

    regions = ['ITC4', 'ITF3', 'ITG1']
    condition_a = []
    condition_b = []
    condition_c = []

    for region_code in regions:
        agents = templates[region_code]
        print(f"\n  Regione {region_code} ({scenario_cal[region_code]['region_name']}): {len(agents)} agenti")

        for agent in agents:
            agent['_region'] = region_code

            # Condizione A — Baseline
            persona_a = build_persona_baseline(agent, scenario_cal)
            profile_a = build_reddit_profile(agent, persona_a, 'A', region_code)
            condition_a.append(profile_a)

            # Condizione B — Country-level
            persona_b = build_persona_country(agent, scenario_cal)
            profile_b = build_reddit_profile(agent, persona_b, 'B', region_code)
            condition_b.append(profile_b)

            # Condizione C — NUTS-2 Full
            persona_c = build_persona_nuts2(agent, scenario_cal, calibration)
            profile_c = build_reddit_profile(agent, persona_c, 'C', region_code)
            condition_c.append(profile_c)

    # Salva
    print(f"\n  Salvataggio profili...")
    save_json(condition_a, os.path.join(PROFILES_DIR, 'condition_a_baseline.json'))
    save_json(condition_b, os.path.join(PROFILES_DIR, 'condition_b_country.json'))
    save_json(condition_c, os.path.join(PROFILES_DIR, 'condition_c_nuts2.json'))

    # Report
    print(f"\n{'=' * 70}")
    print(f"  Generati {len(condition_a) + len(condition_b) + len(condition_c)} profili totali")
    print(f"  Condizione A (Baseline):     {len(condition_a)} profili")
    print(f"  Condizione B (Country):      {len(condition_b)} profili")
    print(f"  Condizione C (NUTS-2 Full):  {len(condition_c)} profili")
    print(f"{'=' * 70}")

    # Esempio confronto per verifica
    print(f"\n--- Esempio confronto: agente #{templates['ITG1'][0]['id']} ({templates['ITG1'][0]['name']}) ---")
    print(f"\n  [A] Baseline:")
    print(f"  {condition_a[40]['persona'][:200]}...")
    print(f"\n  [B] Country:")
    print(f"  {condition_b[40]['persona'][:200]}...")
    print(f"\n  [C] NUTS-2 Full:")
    print(f"  {condition_c[40]['persona'][:300]}...")

    return True


if __name__ == '__main__':
    random.seed(42)  # Riproducibilita
    success = main()
    sys.exit(0 if success else 1)
