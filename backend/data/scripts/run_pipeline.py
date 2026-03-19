"""
Master pipeline runner — fetches all data sources and builds calibration profiles.
Usage: python run_pipeline.py [--skip-eurostat] [--skip-istat-api]
"""

import sys
import os
import importlib
import time

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)


def run_step(name: str, module_name: str):
    """Run a pipeline step with timing."""
    print(f"\n{'='*60}")
    print(f"  STEP: {name}")
    print(f"{'='*60}")
    start = time.time()
    try:
        mod = importlib.import_module(module_name)
        mod.main()
        elapsed = time.time() - start
        print(f"\n  [{name}] Completed in {elapsed:.1f}s")
        return True
    except Exception as e:
        elapsed = time.time() - start
        print(f"\n  [{name}] FAILED after {elapsed:.1f}s: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    skip_eurostat = "--skip-eurostat" in sys.argv
    skip_istat_api = "--skip-istat-api" in sys.argv

    print("=" * 60)
    print("  MiroFish-IT — Data Pipeline")
    print("  Institutional Calibration Framework (ICF)")
    print("=" * 60)

    results = {}
    total_start = time.time()

    # Step 1: Hofstede (static data, always works)
    results["Hofstede 6D"] = run_step("Hofstede 6D", "fetch_hofstede")

    # Step 2: Eurostat (API, may fail on network issues)
    if skip_eurostat:
        print("\n[Eurostat] Skipped (--skip-eurostat)")
        results["Eurostat NUTS-2"] = "SKIPPED"
    else:
        results["Eurostat NUTS-2"] = run_step("Eurostat NUTS-2", "fetch_eurostat")

    # Step 3: ISTAT (curated data + optional API)
    results["ISTAT Demographics"] = run_step("ISTAT Demographics", "fetch_istat")

    # Step 4: Banca d'Italia IBF (curated data)
    results["Banca d'Italia IBF"] = run_step("Banca d'Italia IBF", "fetch_bankitalia")

    # Step 5: ESS / Schwartz (curated data + optional microdata)
    results["ESS Schwartz Values"] = run_step("ESS Schwartz Values", "fetch_ess")

    # Step 6: Build unified calibration profiles
    results["Build Calibration"] = run_step("Build Calibration Profiles", "build_calibration")

    # Summary
    total_elapsed = time.time() - total_start
    print(f"\n{'='*60}")
    print(f"  PIPELINE COMPLETE — {total_elapsed:.1f}s total")
    print(f"{'='*60}")
    print(f"\n{'Step':<30} {'Status':<10}")
    print("-" * 42)
    for step, status in results.items():
        if status is True:
            print(f"{step:<30} {'OK':>8}")
        elif status is False:
            print(f"{step:<30} {'FAILED':>8}")
        else:
            print(f"{step:<30} {str(status):>8}")

    # Check output files
    processed_dir = os.path.join(SCRIPT_DIR, '..', 'processed')
    if os.path.exists(os.path.join(processed_dir, 'calibration_profiles.json')):
        size = os.path.getsize(os.path.join(processed_dir, 'calibration_profiles.json'))
        print(f"\nOutput: calibration_profiles.json ({size:,} bytes)")
    if os.path.exists(os.path.join(processed_dir, 'calibration_texts.json')):
        size = os.path.getsize(os.path.join(processed_dir, 'calibration_texts.json'))
        print(f"Output: calibration_texts.json ({size:,} bytes)")


if __name__ == '__main__':
    main()
