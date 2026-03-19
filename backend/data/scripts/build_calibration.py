"""
Build unified calibration profiles per NUTS-2 region.
Combines all data sources into a single JSON structure ready for agent profiling.

Output: backend/data/processed/calibration_profiles.json

Each region profile includes:
1. Economic grounding (Eurostat + IBF)
2. Cultural values (Hofstede 6D + Schwartz/ESS)
3. Demographic & lifestyle indicators (ISTAT)
4. Trust & wellbeing (ESS)
"""

import json
import os

SCRIPT_DIR = os.path.dirname(__file__)
RAW_DIR = os.path.join(SCRIPT_DIR, '..', 'raw')
PROCESSED_DIR = os.path.join(SCRIPT_DIR, '..', 'processed')

# NUTS-2 regions
NUTS2_REGIONS = {
    "ITC1": "Piemonte",
    "ITC2": "Valle d'Aosta",
    "ITC3": "Liguria",
    "ITC4": "Lombardia",
    "ITH1": "P.A. Bolzano",
    "ITH2": "P.A. Trento",
    "ITH3": "Veneto",
    "ITH4": "Friuli-Venezia Giulia",
    "ITH5": "Emilia-Romagna",
    "ITI1": "Toscana",
    "ITI2": "Umbria",
    "ITI3": "Marche",
    "ITI4": "Lazio",
    "ITF1": "Abruzzo",
    "ITF2": "Molise",
    "ITF3": "Campania",
    "ITF4": "Puglia",
    "ITF5": "Basilicata",
    "ITF6": "Calabria",
    "ITG1": "Sicilia",
    "ITG2": "Sardegna",
}

# Regional cultural zone mapping (for Hofstede regional modulation)
CULTURAL_ZONES = {
    "north": ["ITC1", "ITC2", "ITC3", "ITC4", "ITH1", "ITH2", "ITH3", "ITH4", "ITH5"],
    "center": ["ITI1", "ITI2", "ITI3", "ITI4"],
    "south": ["ITF1", "ITF2", "ITF3", "ITF4", "ITF5", "ITF6", "ITG1", "ITG2"],
}

# Hofstede regional modulation factors (applied to national scores)
# Based on documented North-South cultural gradient in Italy
HOFSTEDE_REGIONAL_MODULATION = {
    "north": {"PDI": -5, "IDV": +5, "MAS": +2, "UAI": -3, "LTO": +5, "IVR": +2},
    "center": {"PDI": 0, "IDV": 0, "MAS": -3, "UAI": +2, "LTO": 0, "IVR": +1},
    "south": {"PDI": +5, "IDV": -8, "MAS": -2, "UAI": +5, "LTO": -5, "IVR": -3},
}


def load_json(path: str) -> dict:
    """Load JSON file, return empty dict if not found."""
    full_path = os.path.join(RAW_DIR, path)
    if os.path.exists(full_path):
        with open(full_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    print(f"  Warning: {path} not found, skipping")
    return {}


def get_cultural_zone(nuts2_code: str) -> str:
    """Determine cultural zone for a NUTS-2 region."""
    for zone, codes in CULTURAL_ZONES.items():
        if nuts2_code in codes:
            return zone
    return "center"  # default


def build_profiles():
    """Build unified calibration profiles."""
    print("[Build] Loading data sources...")

    # Load all sources
    hofstede = load_json('hofstede/italy_hofstede_6d.json')
    eurostat = load_json('eurostat/italy_nuts2_summary.json')
    istat = load_json('istat/italy_regional_demographics.json')
    ibf = load_json('bankitalia/ibf_2020_nuts2_mapped.json')
    schwartz = load_json('ess/italy_schwartz_values.json')
    trust = load_json('ess/italy_trust_wellbeing.json')

    # National Hofstede scores
    hofstede_scores = hofstede.get("scores", {})

    profiles = {}

    for code, name in NUTS2_REGIONS.items():
        zone = get_cultural_zone(code)

        # --- 1. Economic Grounding Layer ---
        economic = {}

        # Eurostat data
        eurostat_region = eurostat.get(code, {}).get("indicators", {})
        if eurostat_region:
            for key in ["gdp_eur", "gdp_pps", "employment_rate", "population", "household_income_pps"]:
                indicator = eurostat_region.get(key, {})
                if indicator.get("value") is not None:
                    economic[key] = {
                        "value": indicator["value"],
                        "year": indicator.get("year"),
                        "unit": indicator.get("unit")
                    }

        # IBF data (wealth, income, savings)
        ibf_region = ibf.get(code, {})
        if ibf_region:
            economic["ibf"] = {
                "macro_area": ibf_region.get("macro_area"),
                "net_income_mean": ibf_region.get("net_income_mean"),
                "net_income_median": ibf_region.get("net_income_median"),
                "net_wealth_mean": ibf_region.get("net_wealth_mean"),
                "net_wealth_median": ibf_region.get("net_wealth_median"),
                "saving_rate_pct": ibf_region.get("saving_rate_pct"),
                "home_ownership_pct": ibf_region.get("home_ownership_pct"),
                "household_size_mean": ibf_region.get("household_size_mean"),
                "source": "Banca d'Italia IBF 2020"
            }

        # --- 2. Cultural Value Layer ---
        cultural = {}

        # Hofstede with regional modulation
        if hofstede_scores:
            modulation = HOFSTEDE_REGIONAL_MODULATION.get(zone, {})
            cultural["hofstede_6d"] = {}
            for dim, national_score in hofstede_scores.items():
                mod = modulation.get(dim, 0)
                regional_score = max(0, min(100, national_score + mod))
                cultural["hofstede_6d"][dim] = {
                    "national_score": national_score,
                    "regional_estimate": regional_score,
                    "modulation": mod,
                    "zone": zone
                }

        # Schwartz values (national — no regional variation available)
        if schwartz:
            basic_values = schwartz.get("basic_values", {})
            cultural["schwartz"] = {
                "basic_values": {k: v["score"] for k, v in basic_values.items()},
                "higher_order": {k: v["score"] for k, v in schwartz.get("higher_order_values", {}).items()},
                "dominant_values": schwartz.get("profile_interpretation", {}).get("dominant_values", []),
                "source": "ESS Round 10 (2020/2021)"
            }

        # --- 3. Demographic & Lifestyle Layer ---
        demographic = {}
        istat_region = istat.get(code, {})
        if istat_region:
            demographic = {
                "population": istat_region.get("population"),
                "median_age": istat_region.get("median_age"),
                "fertility_rate": istat_region.get("fertility_rate"),
                "university_graduates_pct": istat_region.get("university_graduates_pct"),
                "unemployment_rate": istat_region.get("unemployment_rate"),
                "internet_users_pct": istat_region.get("internet_users_pct"),
                "life_satisfaction_mean": istat_region.get("life_satisfaction_mean"),
                "sport_regular_pct": istat_region.get("sport_regular_pct"),
                "volunteer_pct": istat_region.get("volunteer_pct"),
                "source": "ISTAT Noi Italia / BES 2023"
            }

        # --- 4. Trust & Social Indicators ---
        social = {}
        if trust:
            indicators = trust.get("indicators", {})
            social = {k: v["value"] for k, v in indicators.items()}
            social["source"] = "ESS Round 10 (2020/2021)"

        # --- Build profile ---
        profiles[code] = {
            "nuts2_code": code,
            "name": name,
            "cultural_zone": zone,
            "layers": {
                "economic": economic,
                "cultural": cultural,
                "demographic": demographic,
                "social": social,
            }
        }

    return profiles


def generate_profile_text(profile: dict) -> str:
    """
    Generate a human-readable calibration text for agent persona injection.
    This text can be appended to agent persona prompts.
    """
    code = profile["nuts2_code"]
    name = profile["name"]
    zone = profile["cultural_zone"]
    layers = profile["layers"]

    lines = []
    lines.append(f"[Calibrazione Istituzionale — {name} ({code})]")
    lines.append(f"Zona culturale: {zone.capitalize()} Italia")
    lines.append("")

    # Economic
    eco = layers.get("economic", {})
    ibf = eco.get("ibf", {})
    if ibf:
        lines.append(f"Reddito familiare netto medio: €{ibf.get('net_income_mean', 'N/A'):,}/anno")
        lines.append(f"Reddito familiare netto mediano: €{ibf.get('net_income_median', 'N/A'):,}/anno")
        lines.append(f"Ricchezza netta media: €{ibf.get('net_wealth_mean', 'N/A'):,}")
        lines.append(f"Tasso di risparmio: {ibf.get('saving_rate_pct', 'N/A')}%")
        lines.append(f"Proprietà casa: {ibf.get('home_ownership_pct', 'N/A')}%")

    emp = eco.get("employment_rate", {})
    if emp:
        lines.append(f"Tasso di occupazione (20-64): {emp.get('value', 'N/A')}%")
    lines.append("")

    # Cultural
    cultural = layers.get("cultural", {})
    hof = cultural.get("hofstede_6d", {})
    if hof:
        lines.append("Dimensioni culturali Hofstede (stima regionale):")
        for dim in ["PDI", "IDV", "MAS", "UAI", "LTO", "IVR"]:
            d = hof.get(dim, {})
            lines.append(f"  {dim}: {d.get('regional_estimate', 'N/A')}/100")

    schwartz = cultural.get("schwartz", {})
    if schwartz.get("dominant_values"):
        lines.append(f"Valori dominanti (Schwartz): {', '.join(schwartz['dominant_values'])}")
    lines.append("")

    # Demographic
    demo = layers.get("demographic", {})
    if demo:
        lines.append(f"Età mediana: {demo.get('median_age', 'N/A')}")
        lines.append(f"Disoccupazione: {demo.get('unemployment_rate', 'N/A')}%")
        lines.append(f"Laureati: {demo.get('university_graduates_pct', 'N/A')}%")
        lines.append(f"Utenti internet: {demo.get('internet_users_pct', 'N/A')}%")
        lines.append(f"Soddisfazione vita: {demo.get('life_satisfaction_mean', 'N/A')}/10")
        lines.append(f"Sport regolare: {demo.get('sport_regular_pct', 'N/A')}%")
        lines.append(f"Volontariato: {demo.get('volunteer_pct', 'N/A')}%")
    lines.append("")

    # Social/Trust
    social = layers.get("social", {})
    if social:
        lines.append(f"Fiducia nelle persone: {social.get('trust_people', 'N/A')}/10")
        lines.append(f"Fiducia nel parlamento: {social.get('trust_parliament', 'N/A')}/10")
        lines.append(f"Felicità auto-riferita: {social.get('happiness', 'N/A')}/10")

    return "\n".join(lines)


def main():
    os.makedirs(PROCESSED_DIR, exist_ok=True)

    # Build unified profiles
    profiles = build_profiles()

    # Save unified profiles
    profiles_path = os.path.join(PROCESSED_DIR, 'calibration_profiles.json')
    with open(profiles_path, 'w', encoding='utf-8') as f:
        json.dump(profiles, f, ensure_ascii=False, indent=2)
    print(f"\n[Build] Unified calibration profiles -> {profiles_path}")
    print(f"[Build] {len(profiles)} NUTS-2 regions processed")

    # Generate human-readable profile texts
    profile_texts = {}
    for code, profile in profiles.items():
        profile_texts[code] = generate_profile_text(profile)

    texts_path = os.path.join(PROCESSED_DIR, 'calibration_texts.json')
    with open(texts_path, 'w', encoding='utf-8') as f:
        json.dump(profile_texts, f, ensure_ascii=False, indent=2)
    print(f"[Build] Calibration texts (for persona injection) -> {texts_path}")

    # Print sample profile
    sample_code = "ITC4"  # Lombardia
    print(f"\n{'='*60}")
    print(f"SAMPLE PROFILE: {NUTS2_REGIONS[sample_code]} ({sample_code})")
    print(f"{'='*60}")
    print(profile_texts[sample_code])

    # Print comparison: North vs South
    print(f"\n{'='*60}")
    print("NORTH vs SOUTH COMPARISON")
    print(f"{'='*60}")

    north_code = "ITC4"  # Lombardia
    south_code = "ITF3"  # Campania
    n = profiles[north_code]["layers"]
    s = profiles[south_code]["layers"]

    print(f"\n{'Indicator':<35} {'Lombardia':>12} {'Campania':>12} {'Delta':>10}")
    print("-" * 72)

    comparisons = [
        ("Reddito medio (€)", "economic.ibf.net_income_mean"),
        ("Ricchezza media (€)", "economic.ibf.net_wealth_mean"),
        ("Risparmio (%)", "economic.ibf.saving_rate_pct"),
        ("Disoccupazione (%)", "demographic.unemployment_rate"),
        ("Laureati (%)", "demographic.university_graduates_pct"),
        ("Internet (%)", "demographic.internet_users_pct"),
        ("Soddisfazione vita", "demographic.life_satisfaction_mean"),
        ("Volontariato (%)", "demographic.volunteer_pct"),
    ]

    for label, path in comparisons:
        parts = path.split(".")
        n_val = n
        s_val = s
        for p in parts:
            n_val = n_val.get(p, {}) if isinstance(n_val, dict) else None
            s_val = s_val.get(p, {}) if isinstance(s_val, dict) else None

        if n_val is not None and s_val is not None:
            if isinstance(n_val, (int, float)) and isinstance(s_val, (int, float)):
                delta = n_val - s_val
                n_str = f"{n_val:>10,.1f}" if isinstance(n_val, float) else f"{n_val:>10,}"
                s_str = f"{s_val:>10,.1f}" if isinstance(s_val, float) else f"{s_val:>10,}"
                d_str = f"{delta:>+10,.1f}" if isinstance(delta, float) else f"{delta:>+10,}"
                print(f"{label:<35} {n_str} {s_str} {d_str}")


if __name__ == '__main__':
    main()
