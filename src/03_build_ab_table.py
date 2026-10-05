"""PHASE 3 - Build and validate the A/B test table (ab_sessions).

The table itself is built in SQL (sql/04_ab_sessions.sql). This script runs that SQL and
then checks that the table is what an A/B test needs: one row per session, exactly one
variant per session, and the expected test window and group sizes.
"""
import pandas as pd

from config import CONTROL, SQL_DIR, TREATMENT, connect, load_queries

# Verified values for this dataset. The window is DERIVED in SQL; here we only check it.
EXPECTED_START = "2012-09-10 00:13:05"   # first ever /billing-2 pageview
EXPECTED_END = "2013-01-05 20:53:22"     # last ever /billing pageview
EXPECTED_SESSIONS = {CONTROL: 1663, TREATMENT: 1657}
TOLERANCE_ROWS = 2


def main():
    print("PHASE 3 - build A/B table")
    con = connect()
    con.executescript((SQL_DIR / "04_ab_sessions.sql").read_text())
    con.commit()

    checks = load_queries("05_ab_checks.sql")

    # 1) Test window.
    start_ts, end_ts = con.execute(checks["test_window"]).fetchone()
    assert start_ts == EXPECTED_START, f"test start is {start_ts}"
    assert end_ts == EXPECTED_END, f"test end is {end_ts}"
    in_window = con.execute("SELECT MIN(billing_ts), MAX(billing_ts) FROM ab_sessions").fetchone()
    assert in_window == (start_ts, end_ts), f"table covers {in_window}"
    print(f"  PASS test window {start_ts} to {end_ts}")

    # 2) One row per session, and no session saw both pages.
    #    If a session had seen both pages we could not say which page caused its order.
    rows, sessions = con.execute(
        "SELECT COUNT(*), COUNT(DISTINCT website_session_id) FROM ab_sessions").fetchone()
    assert rows == sessions, f"{rows} rows but {sessions} distinct sessions"
    both = con.execute(checks["sessions_with_both_pages"]).fetchone()[0]
    assert both == 0, f"{both} sessions saw both billing pages"
    print("  PASS one row per session, no session saw both pages")

    # 3) Group sizes.
    summary = pd.read_sql_query(checks["variant_summary"], con)
    sizes = dict(zip(summary["variant"], summary["sessions"]))
    for variant, expected in EXPECTED_SESSIONS.items():
        assert abs(sizes[variant] - expected) <= TOLERANCE_ROWS, f"{variant}: {sizes[variant]} sessions"
    assert abs(rows - sum(EXPECTED_SESSIONS.values())) <= TOLERANCE_ROWS
    print(f"  PASS {rows:,} sessions = {sizes[CONTROL]:,} ({CONTROL}) + {sizes[TREATMENT]:,} ({TREATMENT})")

    # 4) An order can only come from a session that is in the table once (no double counting).
    orders, distinct_orders = con.execute(
        "SELECT COUNT(order_id), COUNT(DISTINCT order_id) FROM ab_sessions").fetchone()
    assert orders == distinct_orders
    print("  PASS no order is counted twice")

    print(summary.to_string(index=False))
    con.close()


if __name__ == "__main__":
    main()
