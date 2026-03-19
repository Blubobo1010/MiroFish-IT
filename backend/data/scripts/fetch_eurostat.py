"""
Fetch economic indicators from Eurostat SDMX REST API for Italian NUTS-2 regions.
Source: Eurostat (European Commission) — free, no auth required.
Granularity: NUTS-2.

Datasets:
- nama_10r_2gdp: Regional GDP (million EUR)
- nama_10r_2hhinc: Household income (PPS per inhabitant)
- lfst_r_lfe2emprt: Employment rate (% 20-64)
- demo_r_d2jan: Population by region
- tec00114: GDP per capita in PPS (for country-level reference)
"""

import json
import os
import sys
import time
import urllib.request
import urllib.error

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), '..', 'raw', 'eurostat')

# Italian NUTS-2 regions
NUTS2_REGIONS = {
    "ITC1": "Piemonte",
    "ITC2": "Valle d'Aosta/Vallée d'Aoste",
    "ITC3": "Liguria",
    "ITC4": "Lombardia",
    "ITH1": "Provincia Autonoma di Bolzano/Bozen",
    "ITH2": "Provincia Autonoma di Trento",
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

# Eurostat JSON API base URL
# Uses the JSON-stat format via the Eurostat data browser API
BASE_URL = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data"


def fetch_eurostat_json(dataset_id: str, params: dict, max_retries: int = 3) -> dict:
    """Fetch data from Eurostat JSON API with retries.

    For multi-value params (like geo), pass a list as the value.
    Each item generates a separate query parameter (geo=X&geo=Y).
    """
    query_parts = []
    for k, v in params.items():
        if isinstance(v, list):
            for item in v:
                query_parts.append(f"{k}={item}")
        else:
            query_parts.append(f"{k}={v}")
    url = f"{BASE_URL}/{dataset_id}?" + "&".join(query_parts)

    for attempt in range(max_retries):
        try:
            print(f"  Fetching {dataset_id} (attempt {attempt + 1})...")
            print(f"  URL: {url}")
            req = urllib.request.Request(url, headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read().decode('utf-8'))
                return data
        except urllib.error.HTTPError as e:
            print(f"  HTTP Error {e.code}: {e.reason}")
            if e.code == 429:
                wait = 10 * (attempt + 1)
                print(f"  Rate limited, waiting {wait}s...")
                time.sleep(wait)
            elif attempt == max_retries - 1:
                raise
        except Exception as e:
            print(f"  Error: {e}")
            if attempt == max_retries - 1:
                raise
            time.sleep(5)

    return {}


def parse_eurostat_response(data: dict, value_label: str = "value") -> dict:
    """
    Parse Eurostat JSON-stat response into a region->year->value structure.
    The Eurostat JSON API returns data in a flat indexed format with dimension metadata.
    """
    if not data or "value" not in data:
        return {}

    values = data["value"]
    dim_ids = data.get("id", [])
    dim_sizes = data.get("size", [])
    dimensions = data.get("dimension", {})

    # Find geo and time dimension indices (case-insensitive search)
    geo_idx = None
    time_idx = None
    for i, dim_id in enumerate(dim_ids):
        if dim_id.lower() == "geo":
            geo_idx = i
        elif dim_id.lower() in ("time", "time_period"):
            time_idx = i

    if geo_idx is None or time_idx is None:
        print(f"  Warning: could not find geo/time dimensions in {dim_ids}")
        return {}

    # Build reverse index (position -> code) for each dimension
    dim_pos2code = {}
    for i, dim_id in enumerate(dim_ids):
        dim_data = dimensions.get(dim_id, {})
        cats = dim_data.get("category", {}).get("index", {})
        dim_pos2code[i] = {v: k for k, v in cats.items()}

    # Build result: {region_code: {year: value}}
    result = {}

    for flat_idx_str, val in values.items():
        flat_idx = int(flat_idx_str)

        # Compute position in each dimension using row-major order
        positions = []
        remaining = flat_idx
        for size in reversed(dim_sizes):
            positions.append(remaining % size)
            remaining //= size
        positions.reverse()

        geo_code = dim_pos2code[geo_idx].get(positions[geo_idx], f"unknown_{positions[geo_idx]}")
        time_code = dim_pos2code[time_idx].get(positions[time_idx], f"unknown_{positions[time_idx]}")

        if geo_code not in result:
            result[geo_code] = {}
        result[geo_code][time_code] = val

    return result


def fetch_regional_gdp():
    """Fetch regional GDP per capita in EUR (nama_10r_2gdp)."""
    print("\n[Eurostat] Fetching Regional GDP per capita...")
    nuts2_codes = list(NUTS2_REGIONS.keys())

    data = fetch_eurostat_json("nama_10r_2gdp", {
        "geo": nuts2_codes,
        "unit": "MIO_EUR",
        "sinceTimePeriod": "2018",
        "untilTimePeriod": "2023",
    })
    return parse_eurostat_response(data)


def fetch_regional_gdp_per_capita_pps():
    """Fetch regional GDP per capita in PPS (nama_10r_2gdp)."""
    print("\n[Eurostat] Fetching Regional GDP per capita in PPS...")
    nuts2_codes = list(NUTS2_REGIONS.keys())

    data = fetch_eurostat_json("nama_10r_2gdp", {
        "geo": nuts2_codes,
        "unit": "MIO_PPS_EU27_2020",
        "sinceTimePeriod": "2018",
        "untilTimePeriod": "2023",
    })
    return parse_eurostat_response(data)


def fetch_employment_rate():
    """Fetch employment rate 20-64 by NUTS-2 (lfst_r_lfe2emprt)."""
    print("\n[Eurostat] Fetching Employment Rate (20-64)...")
    nuts2_codes = list(NUTS2_REGIONS.keys())

    data = fetch_eurostat_json("lfst_r_lfe2emprt", {
        "geo": nuts2_codes,
        "age": "Y20-64",
        "sex": "T",
        "sinceTimePeriod": "2018",
        "untilTimePeriod": "2023",
    })
    return parse_eurostat_response(data)


def fetch_population():
    """Fetch population by NUTS-2 region (demo_r_d2jan)."""
    print("\n[Eurostat] Fetching Population...")
    nuts2_codes = list(NUTS2_REGIONS.keys())

    data = fetch_eurostat_json("demo_r_d2jan", {
        "geo": nuts2_codes,
        "sex": "T",
        "age": "TOTAL",
        "sinceTimePeriod": "2018",
        "untilTimePeriod": "2023",
    })
    return parse_eurostat_response(data)


def fetch_household_income():
    """Fetch household income per capita in PPS (nama_10r_2hhinc)."""
    print("\n[Eurostat] Fetching Household Income (PPS per inhabitant)...")
    nuts2_codes = list(NUTS2_REGIONS.keys())

    data = fetch_eurostat_json("nama_10r_2hhinc", {
        "geo": nuts2_codes,
        "unit": "PPS_HAB_EU27_2020",
        "na_item": "B6N",  # Net disposable income
        "sinceTimePeriod": "2018",
        "untilTimePeriod": "2023",
    })
    return parse_eurostat_response(data)


def get_latest_value(region_data: dict) -> tuple:
    """Get the most recent year's value from a region's time series."""
    if not region_data:
        return None, None
    years = sorted(region_data.keys(), reverse=True)
    for year in years:
        val = region_data[year]
        if val is not None:
            return year, val
    return None, None


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # Fetch all datasets
    datasets = {}

    try:
        datasets["gdp_eur"] = fetch_regional_gdp()
    except Exception as e:
        print(f"  FAILED: {e}")
        datasets["gdp_eur"] = {}

    try:
        datasets["gdp_pps"] = fetch_regional_gdp_per_capita_pps()
    except Exception as e:
        print(f"  FAILED: {e}")
        datasets["gdp_pps"] = {}

    try:
        datasets["employment_rate"] = fetch_employment_rate()
    except Exception as e:
        print(f"  FAILED: {e}")
        datasets["employment_rate"] = {}

    try:
        datasets["population"] = fetch_population()
    except Exception as e:
        print(f"  FAILED: {e}")
        datasets["population"] = {}

    try:
        datasets["household_income_pps"] = fetch_household_income()
    except Exception as e:
        print(f"  FAILED: {e}")
        datasets["household_income_pps"] = {}

    # Save raw datasets
    for name, data in datasets.items():
        path = os.path.join(OUTPUT_DIR, f'{name}_raw.json')
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"[Eurostat] Saved {name} -> {path}")

    # Build consolidated per-region summary (latest available year)
    print("\n[Eurostat] Building consolidated regional summary...")
    regional_summary = {}

    for code, name in NUTS2_REGIONS.items():
        region = {
            "nuts2_code": code,
            "name": name,
            "indicators": {}
        }

        for indicator, data in datasets.items():
            region_data = data.get(code, {})
            year, value = get_latest_value(region_data)
            region["indicators"][indicator] = {
                "value": value,
                "year": year,
                "unit": {
                    "gdp_eur": "million EUR",
                    "gdp_pps": "million PPS (EU27 2020)",
                    "employment_rate": "% (age 20-64)",
                    "population": "persons",
                    "household_income_pps": "PPS per inhabitant (EU27 2020)",
                }.get(indicator, "unknown")
            }

        regional_summary[code] = region

    # Save consolidated summary
    summary_path = os.path.join(OUTPUT_DIR, 'italy_nuts2_summary.json')
    with open(summary_path, 'w', encoding='utf-8') as f:
        json.dump(regional_summary, f, ensure_ascii=False, indent=2)
    print(f"[Eurostat] Consolidated summary -> {summary_path}")

    # Print summary table
    print("\n[Eurostat] Italian NUTS-2 Regional Summary (latest available year):")
    print(f"{'Code':<6} {'Region':<40} {'GDP(M€)':<12} {'Empl%':<8} {'Pop':<12} {'HH Inc(PPS)':<12}")
    print("-" * 92)

    for code in sorted(NUTS2_REGIONS.keys()):
        r = regional_summary.get(code, {})
        ind = r.get("indicators", {})
        gdp_val = ind.get("gdp_eur", {}).get("value")
        emp_val = ind.get("employment_rate", {}).get("value")
        pop_val = ind.get("population", {}).get("value")
        hhi_val = ind.get("household_income_pps", {}).get("value")

        gdp_str = f"{gdp_val:>10,.0f}" if isinstance(gdp_val, (int, float)) else f"{'N/A':>10}"
        emp_str = f"{emp_val:>6.1f}" if isinstance(emp_val, (int, float)) else f"{'N/A':>6}"
        pop_str = f"{pop_val:>10,.0f}" if isinstance(pop_val, (int, float)) else f"{'N/A':>10}"
        hhi_str = f"{hhi_val:>10,.0f}" if isinstance(hhi_val, (int, float)) else f"{'N/A':>10}"

        print(f"{code:<6} {NUTS2_REGIONS[code]:<40} {gdp_str} {emp_str} {pop_str} {hhi_str}")


if __name__ == '__main__':
    main()
