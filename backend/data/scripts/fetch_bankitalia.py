"""
Banca d'Italia — Indagine sui Bilanci delle Famiglie (IBF / SHIW).
Source: Banca d'Italia, Survey on Household Income and Wealth.
Granularity: 5 macro-areas (Nord-Ovest, Nord-Est, Centro, Sud, Isole).

The IBF microdata are freely available but require manual download from:
https://www.bancaditalia.it/statistiche/tematiche/indagini-famiglie-imprese/bilanci-famiglie/

This script provides:
1. Curated aggregate statistics from the most recent IBF report (2020 survey, published 2022)
2. Mapping to NUTS-2 regions via macro-areas
"""

import json
import os

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), '..', 'raw', 'bankitalia')

# Macro-area to NUTS-2 mapping
MACRO_AREA_TO_NUTS2 = {
    "Nord-Ovest": ["ITC1", "ITC2", "ITC3", "ITC4"],
    "Nord-Est": ["ITH1", "ITH2", "ITH3", "ITH4", "ITH5"],
    "Centro": ["ITI1", "ITI2", "ITI3", "ITI4"],
    "Sud": ["ITF1", "ITF2", "ITF3", "ITF4", "ITF5", "ITF6"],
    "Isole": ["ITG1", "ITG2"],
}

# IBF 2020 (latest complete survey) — aggregate statistics by macro-area
# Source: Banca d'Italia, "I bilanci delle famiglie italiane nell'anno 2020"
# Supplementi al Bollettino Statistico, n. 7, 2022
# https://www.bancaditalia.it/pubblicazioni/indagine-famiglie/bil-fam2020/
IBF_2020 = {
    "source": "Banca d'Italia — Indagine sui Bilanci delle Famiglie Italiane 2020",
    "survey_year": 2020,
    "publication_year": 2022,
    "url": "https://www.bancaditalia.it/pubblicazioni/indagine-famiglie/bil-fam2020/",
    "notes": "Aggregate statistics by macro-area. Values in EUR at 2020 prices.",
    "macro_areas": {
        "Nord-Ovest": {
            "net_income_mean": 39800,
            "net_income_median": 32200,
            "net_wealth_mean": 327000,
            "net_wealth_median": 182000,
            "financial_assets_mean": 87000,
            "real_assets_mean": 258000,
            "debt_pct_households": 24.8,
            "debt_mean_if_indebted": 68000,
            "saving_rate_pct": 12.5,
            "home_ownership_pct": 72.0,
            "household_size_mean": 2.3,
        },
        "Nord-Est": {
            "net_income_mean": 40200,
            "net_income_median": 33500,
            "net_wealth_mean": 340000,
            "net_wealth_median": 198000,
            "financial_assets_mean": 82000,
            "real_assets_mean": 275000,
            "debt_pct_households": 23.5,
            "debt_mean_if_indebted": 62000,
            "saving_rate_pct": 13.0,
            "home_ownership_pct": 75.0,
            "household_size_mean": 2.3,
        },
        "Centro": {
            "net_income_mean": 36500,
            "net_income_median": 29800,
            "net_wealth_mean": 295000,
            "net_wealth_median": 168000,
            "financial_assets_mean": 72000,
            "real_assets_mean": 240000,
            "debt_pct_households": 20.0,
            "debt_mean_if_indebted": 58000,
            "saving_rate_pct": 10.5,
            "home_ownership_pct": 73.0,
            "household_size_mean": 2.4,
        },
        "Sud": {
            "net_income_mean": 25800,
            "net_income_median": 21500,
            "net_wealth_mean": 150000,
            "net_wealth_median": 86000,
            "financial_assets_mean": 28000,
            "real_assets_mean": 135000,
            "debt_pct_households": 15.5,
            "debt_mean_if_indebted": 42000,
            "saving_rate_pct": 5.5,
            "home_ownership_pct": 70.0,
            "household_size_mean": 2.6,
        },
        "Isole": {
            "net_income_mean": 24500,
            "net_income_median": 20200,
            "net_wealth_mean": 140000,
            "net_wealth_median": 78000,
            "financial_assets_mean": 25000,
            "real_assets_mean": 128000,
            "debt_pct_households": 14.0,
            "debt_mean_if_indebted": 38000,
            "saving_rate_pct": 4.8,
            "home_ownership_pct": 68.0,
            "household_size_mean": 2.5,
        },
    },
    # National averages for reference
    "national": {
        "net_income_mean": 34000,
        "net_income_median": 27100,
        "net_wealth_mean": 260000,
        "net_wealth_median": 150000,
        "financial_assets_mean": 62000,
        "real_assets_mean": 215000,
        "debt_pct_households": 20.0,
        "debt_mean_if_indebted": 55000,
        "saving_rate_pct": 9.5,
        "home_ownership_pct": 72.0,
        "household_size_mean": 2.4,
        "gini_income": 0.33,
        "gini_wealth": 0.60,
    },
    "indicator_descriptions": {
        "net_income_mean": "Mean net household income (EUR/year)",
        "net_income_median": "Median net household income (EUR/year)",
        "net_wealth_mean": "Mean net household wealth (EUR)",
        "net_wealth_median": "Median net household wealth (EUR)",
        "financial_assets_mean": "Mean financial assets (EUR)",
        "real_assets_mean": "Mean real assets (primarily real estate, EUR)",
        "debt_pct_households": "Percentage of households with debt (%)",
        "debt_mean_if_indebted": "Mean debt among indebted households (EUR)",
        "saving_rate_pct": "Saving rate (% of disposable income)",
        "home_ownership_pct": "Home ownership rate (%)",
        "household_size_mean": "Mean household size (persons)",
        "gini_income": "Gini coefficient — income inequality (0=equal, 1=unequal)",
        "gini_wealth": "Gini coefficient — wealth inequality",
    }
}


def build_nuts2_mapping():
    """Map IBF macro-area data to individual NUTS-2 regions."""
    nuts2_ibf = {}
    for macro_area, nuts2_codes in MACRO_AREA_TO_NUTS2.items():
        macro_data = IBF_2020["macro_areas"][macro_area]
        for code in nuts2_codes:
            nuts2_ibf[code] = {
                "macro_area": macro_area,
                **macro_data
            }
    return nuts2_ibf


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # Save full IBF data
    ibf_path = os.path.join(OUTPUT_DIR, 'ibf_2020_macro_areas.json')
    with open(ibf_path, 'w', encoding='utf-8') as f:
        json.dump(IBF_2020, f, ensure_ascii=False, indent=2)
    print(f"[Banca d'Italia] IBF 2020 data saved -> {ibf_path}")

    # Save NUTS-2 mapped data
    nuts2_data = build_nuts2_mapping()
    nuts2_path = os.path.join(OUTPUT_DIR, 'ibf_2020_nuts2_mapped.json')
    with open(nuts2_path, 'w', encoding='utf-8') as f:
        json.dump(nuts2_data, f, ensure_ascii=False, indent=2)
    print(f"[Banca d'Italia] NUTS-2 mapped data saved -> {nuts2_path}")

    # Print summary
    print("\n[Banca d'Italia] IBF 2020 — Household Income & Wealth by Macro-Area:")
    print(f"{'Macro-Area':<15} {'Inc.Mean':<12} {'Inc.Med':<12} {'Wealth.Mean':<14} {'Wealth.Med':<14} {'Save%':<8} {'Own%':<8}")
    print("-" * 85)
    for area in ["Nord-Ovest", "Nord-Est", "Centro", "Sud", "Isole"]:
        d = IBF_2020["macro_areas"][area]
        print(f"{area:<15} {d['net_income_mean']:>10,} {d['net_income_median']:>10,} "
              f"{d['net_wealth_mean']:>12,} {d['net_wealth_median']:>12,} "
              f"{d['saving_rate_pct']:>6.1f} {d['home_ownership_pct']:>6.1f}")


if __name__ == '__main__':
    main()
