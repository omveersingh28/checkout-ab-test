"""PHASE 1 - Load the raw CSV files into one SQLite database (data/maven.db).

Why SQLite: it is a single file, needs no server, and lets the analysis be written in SQL.
The script also checks the row counts, so a wrong or incomplete download is caught here
and not three steps later.
"""
import pandas as pd

from config import DB_PATH, RAW_DIR, SQL_DIR, connect

# Expected rows per table (table name = CSV file name without ".csv").
EXPECTED_ROWS = {
    "website_sessions": 472_871,
    "website_pageviews": 1_188_124,
    "orders": 32_313,
    "order_items": 40_025,
    "order_item_refunds": 1_731,
    "products": 4,
}

# Expected sessions per marketing channel (from the session_channel view).
EXPECTED_CHANNELS = {
    "direct": 39_917,
    "organic_search": 43_411,
    "paid_brand": 41_243,
    "paid_nonbrand": 337_615,
    "paid_social": 10_685,
}

# Indexes on the columns we join on. Without them the joins scan 1.2 million pageviews.
INDEXES = [
    ("idx_pageviews_session", "website_pageviews(website_session_id)"),
    ("idx_orders_session", "orders(website_session_id)"),
    ("idx_orders_user", "orders(user_id)"),
    ("idx_order_items_order", "order_items(order_id)"),
    ("idx_refunds_order", "order_item_refunds(order_id)"),
]


def main():
    print("PHASE 1 - build database")
    missing = [t for t in EXPECTED_ROWS if not (RAW_DIR / f"{t}.csv").exists()]
    if missing:
        raise SystemExit(f"Missing CSV files in data/raw/: {missing}. See data/raw/README.txt")

    con = connect()

    # 1) CSV -> table. created_at stays as text 'YYYY-MM-DD HH:MM:SS': SQLite has no date
    #    type, and text in this format sorts and compares correctly.
    #    Blank cells (for example utm_source of organic traffic) become NULL.
    for table in EXPECTED_ROWS:
        df = pd.read_csv(RAW_DIR / f"{table}.csv")
        df.to_sql(table, con, if_exists="replace", index=False)
        print(f"  loaded {table:<20} {len(df):>9,} rows")

    # 2) Indexes.
    for name, target in INDEXES:
        con.execute(f"CREATE INDEX IF NOT EXISTS {name} ON {target}")

    # 3) The session_channel view.
    con.executescript((SQL_DIR / "00_views.sql").read_text())
    con.commit()

    # 4) Checks. These stop the pipeline if the data is not what we expect.
    for table, expected in EXPECTED_ROWS.items():
        actual = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        assert actual == expected, f"{table}: expected {expected:,} rows, got {actual:,}"
    print("  PASS row counts of all 6 tables")

    channels = dict(con.execute(
        "SELECT channel, COUNT(*) FROM session_channel GROUP BY channel").fetchall())
    assert channels == EXPECTED_CHANNELS, f"channel counts differ: {channels}"
    assert sum(channels.values()) == EXPECTED_ROWS["website_sessions"]
    print("  PASS channel counts (5 channels, total 472,871)")

    first, last = con.execute(
        "SELECT MIN(created_at), MAX(created_at) FROM website_sessions").fetchone()
    assert first.startswith("2012-03-19") and last.startswith("2015-03-19"), (first, last)
    print(f"  PASS session date range {first} to {last}")

    con.close()
    print(f"  database written to {DB_PATH.relative_to(DB_PATH.parent.parent)}")


if __name__ == "__main__":
    main()
