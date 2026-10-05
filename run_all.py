"""Run the whole project from raw CSVs to results, charts and checks.

    python run_all.py

Each script stops with an error if one of its checks fails, so reaching the last line
means every check passed.
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SCRIPTS = ["01_build_database.py", "02_business_overview.py", "03_build_ab_table.py", "04_ab_test.py"]


def check_documents_match_results():
    """The README and the memo are written by hand, so make sure their headline numbers
    are still the ones the scripts produced (results/ab_results.json)."""
    r = json.loads((ROOT / "results" / "ab_results.json").read_text())
    g = r["guardrails"]
    must_appear = [
        f"{r['sessions']['total']:,}",                          # 3,320 sessions
        f"{r['conv_rates']['/billing']:.1%}",                   # 45.1%
        f"{r['conv_rates']['/billing-2']:.1%}",                 # 62.1%
        f"{r['lift_pp']:+.1f} pp",                              # +17.0 pp
        f"{r['ci']['low_pp']:.1f}",                             # 13.7
        f"{r['ci']['high_pp']:.1f}",                            # 20.3
        f"${g['revenue_per_session']['diff']:.2f}",             # $8.50
        f"${g['net_revenue_per_session']['diff']:.2f}",         # $7.56
        f"{g['refund_rate_per_order']['p_value']:.2f}",         # 0.28
        r["decision"]["text"],                                  # SHIP /billing-2
    ]
    for doc in ["README.md", "reports/decision_memo.md"]:
        text = (ROOT / doc).read_text()
        missing = [number for number in must_appear if number not in text]
        if missing:
            raise SystemExit(f"{doc} does not match results/ab_results.json, missing: {missing}")
        print(f"  PASS {doc} matches results/ab_results.json")


def main():
    for script in SCRIPTS:
        print("=" * 90)
        # sys.executable = the Python that runs this file, so the virtual environment is reused.
        done = subprocess.run([sys.executable, str(ROOT / "src" / script)])
        if done.returncode != 0:
            raise SystemExit(f"STOPPED: {script} failed (see the message above)")
    print("=" * 90)
    print("Documents vs results")
    check_documents_match_results()
    print("\nALL CHECKS PASSED")


if __name__ == "__main__":
    main()
