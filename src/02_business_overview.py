"""PHASE 2 - Short business overview (context for the A/B test).

Answers four questions with SQL (sql/01-03), one chart each, and a short findings file:
  (a) What is the trend in website sessions and order volume?
  (b) What is the session-to-order conversion rate, and how has it trended?
  (c) Which marketing channels have been most successful?
  (d) How have revenue per order and revenue per session evolved?
Plus a funnel chart that shows where the billing page (the A/B test) sits.
"""
import matplotlib.dates as mdates
import pandas as pd
from matplotlib.ticker import FuncFormatter, PercentFormatter

from config import (CHARTS_DIR, COLOR_MARKER, COLOR_NEUTRAL, RESULTS_DIR, apply_chart_style,
                    connect, load_queries)

plt = apply_chart_style()

# Verified funnel reach counts. If these change, the data or the SQL changed.
EXPECTED_FUNNEL = {"products": 261_231, "cart": 94_953, "shipping": 64_484,
                   "billing": 52_058, "order": 32_313}

# Page changes drawn on the conversion chart: (page, which date to use, label, label side).
PAGE_EVENTS = [
    ("/lander-1", "first_seen", "lander-1 starts", "left"),
    ("/billing-2", "first_seen", "billing-2 test starts", "left"),
    ("/billing", "last_seen", "billing-2 for everyone", "right"),
    ("/lander-2", "first_seen", "lander-2 starts", "left"),
    ("/lander-3", "first_seen", "lander-3 starts", "left"),
    ("/lander-4", "first_seen", "lander-4 starts", "left"),
    ("/lander-5", "first_seen", "lander-5 starts", "left"),
]

FUNNEL_LABELS = {
    "sessions": "All sessions (landing page)", "products": "/products",
    "product_page": "A product page", "cart": "/cart", "shipping": "/shipping",
    "billing": "Billing page  <- A/B test", "order": "Order placed",
}


def add_event_lines(ax, events):
    """Draw thin labelled vertical lines. events = list of (date, label, side)."""
    for date, label, side in events:
        ax.axvline(date, color=COLOR_MARKER, linewidth=0.8, zorder=1)
        # 'side' says on which side of the line the text sits, so near-by events do not overlap.
        offset = pd.Timedelta(days=6 if side == "left" else -6)
        ax.text(date + offset, 0.98, label, rotation=90, fontsize=8, color=COLOR_NEUTRAL,
                va="top", ha="left" if side == "left" else "right",
                transform=ax.get_xaxis_transform())


def format_month_axis(ax):
    ax.xaxis.set_major_locator(mdates.MonthLocator(bymonth=[1, 7]))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))


def main():
    print("PHASE 2 - business overview")
    RESULTS_DIR.mkdir(exist_ok=True)
    CHARTS_DIR.mkdir(parents=True, exist_ok=True)
    con = connect()

    # ---- Run the SQL ---------------------------------------------------------------------
    q1 = load_queries("01_monthly_trends.sql")
    monthly = pd.read_sql_query(q1["monthly_trends"], con)
    pages = pd.read_sql_query(q1["page_change_dates"], con)
    products = pd.read_sql_query(q1["product_launches"], con)
    channels = pd.read_sql_query(load_queries("02_channel_performance.sql")["channel_performance"], con)
    funnel = pd.read_sql_query(load_queries("03_funnel.sql")["funnel"], con)
    con.close()

    # The first and last month are only partly covered by the data (it starts and ends on
    # the 19th), so they would look like a fake drop. Flag them and keep them off the charts.
    monthly["is_partial_month"] = monthly["month"].isin([monthly["month"].min(), monthly["month"].max()])
    full = monthly[~monthly["is_partial_month"]].copy()
    full["date"] = pd.to_datetime(full["month"] + "-01")

    funnel["share_of_sessions"] = (funnel["sessions"] / funnel["sessions"].iloc[0]).round(4)
    # How many sessions carry on from the step before (shows where the biggest drop is).
    funnel["share_of_previous_step"] = (funnel["sessions"] / funnel["sessions"].shift(1)).round(4)
    total_sessions = channels["sessions"].sum()
    total_revenue = channels["revenue"].sum()
    channels["share_of_sessions"] = (channels["sessions"] / total_sessions).round(4)
    channels["share_of_revenue"] = (channels["revenue"] / total_revenue).round(4)

    # ---- Checks --------------------------------------------------------------------------
    reach = dict(zip(funnel["step"], funnel["sessions"]))
    for step, expected in EXPECTED_FUNNEL.items():
        assert reach[step] == expected, f"funnel step {step}: expected {expected}, got {reach[step]}"
    assert monthly["sessions"].sum() == 472_871 and monthly["orders"].sum() == 32_313
    print("  PASS funnel reach counts and monthly totals")

    # ---- Save result tables --------------------------------------------------------------
    monthly.to_csv(RESULTS_DIR / "monthly_trends.csv", index=False)
    pages.to_csv(RESULTS_DIR / "page_change_dates.csv", index=False)
    channels.to_csv(RESULTS_DIR / "channel_performance.csv", index=False)
    funnel.to_csv(RESULTS_DIR / "funnel.csv", index=False)

    # ---- Chart 01: sessions and orders ---------------------------------------------------
    # Two panels instead of two y-axes on one plot: sessions are ~15x larger than orders,
    # and a double axis would let the reader compare heights that mean nothing.
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 6), sharex=True)
    ax1.plot(full["date"], full["sessions"], color=COLOR_NEUTRAL)
    ax1.set_title("Website sessions per month")
    ax1.set_ylabel("Sessions")
    ax2.plot(full["date"], full["orders"], color=COLOR_NEUTRAL)
    ax2.set_title("Orders per month")
    ax2.set_ylabel("Orders")
    ax2.set_xlabel("Month (full months only: Apr 2012 - Feb 2015)")
    for ax in (ax1, ax2):
        ax.set_ylim(bottom=0)
        ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:,.0f}"))
    format_month_axis(ax2)
    fig.tight_layout()
    fig.savefig(CHARTS_DIR / "01_monthly_sessions_orders.png")
    plt.close(fig)

    # ---- Chart 02: conversion rate -------------------------------------------------------
    page_dates = pages.set_index("pageview_url")
    events = [(pd.to_datetime(page_dates.loc[url, col]), label, side)
              for url, col, label, side in PAGE_EVENTS]
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(full["date"], full["conv_rate"], color=COLOR_NEUTRAL, marker="o", markersize=3)
    add_event_lines(ax, events)
    ax.set_title("Session-to-order conversion rate per month, with page changes")
    ax.set_ylabel("Orders / sessions")
    ax.set_xlabel("Month (full months only: Apr 2012 - Feb 2015)")
    ax.set_ylim(0, 0.125)  # head-room so the vertical labels do not sit on the line
    ax.yaxis.set_major_formatter(PercentFormatter(1.0, decimals=0))
    format_month_axis(ax)
    fig.tight_layout()
    fig.savefig(CHARTS_DIR / "02_conversion_rate_trend.png")
    plt.close(fig)

    # ---- Chart 03: channels --------------------------------------------------------------
    ch = channels.sort_values("revenue")  # biggest revenue ends up at the top of the chart
    panels = [("sessions", "Sessions (volume)", lambda v: f"{v:,.0f}"),
              ("conv_rate", "Conversion rate", lambda v: f"{v:.1%}"),
              ("revenue_per_session", "Revenue per session", lambda v: f"${v:.2f}")]
    fig, axes = plt.subplots(1, 3, figsize=(12, 3.8), sharey=True)
    for ax, (col, title, fmt) in zip(axes, panels):
        bars = ax.barh(ch["channel"], ch[col], color=COLOR_NEUTRAL, height=0.6)
        ax.bar_label(bars, labels=[fmt(v) for v in ch[col]], padding=3, fontsize=9)
        ax.set_title(title)
        ax.set_xlim(0, ch[col].max() * 1.25)  # room for the value labels
        ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _, f=fmt: f(v)))
        ax.xaxis.set_major_locator(plt.MaxNLocator(4))
        ax.grid(axis="y", visible=False)
    axes[0].set_ylabel("Marketing channel")
    fig.suptitle("Channel performance, Mar 2012 - Mar 2015 (sorted by revenue)",
                 x=0.01, ha="left", fontsize=12, fontweight="bold")
    fig.tight_layout()
    fig.savefig(CHARTS_DIR / "03_channel_performance.png")
    plt.close(fig)

    # ---- Chart 04: revenue per order and per session -------------------------------------
    launches = [(pd.to_datetime(r.launched_at), f"#{r.product_id} {r.product_name}", "left")
                for r in products.itertuples() if r.product_id > 1]  # product 1 was there from day one
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 7), sharex=True)
    ax1.plot(full["date"], full["revenue_per_order"], color=COLOR_NEUTRAL)
    ax1.set_title("Revenue per order, with product launches")
    ax1.set_ylabel("Revenue / orders")
    ax1.set_ylim(0, full["revenue_per_order"].max() * 1.15)
    ax1.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"${v:.0f}"))
    ax2.plot(full["date"], full["revenue_per_session"], color=COLOR_NEUTRAL)
    ax2.set_title("Revenue per session")
    ax2.set_ylabel("Revenue / sessions")
    ax2.set_xlabel("Month (full months only: Apr 2012 - Feb 2015)")
    ax2.set_ylim(0, full["revenue_per_session"].max() * 1.15)
    ax2.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"${v:.2f}"))
    for ax in (ax1, ax2):
        for date, _, _ in launches:
            ax.axvline(date, color=COLOR_MARKER, linewidth=0.8, zorder=1)
    # Labels only on the top panel, placed low because the line there is near the top.
    for date, label, _ in launches:
        ax1.text(date + pd.Timedelta(days=6), 0.04, label, rotation=90, fontsize=8,
                 color=COLOR_NEUTRAL, va="bottom", ha="left", transform=ax1.get_xaxis_transform())
    format_month_axis(ax2)
    fig.tight_layout()
    fig.savefig(CHARTS_DIR / "04_revenue_per_order_and_session.png")
    plt.close(fig)

    # ---- Chart 05: funnel ----------------------------------------------------------------
    fn = funnel.iloc[::-1]  # reverse so the first step is drawn at the top
    fig, ax = plt.subplots(figsize=(9, 4.2))
    bars = ax.barh([FUNNEL_LABELS[s] for s in fn["step"]], fn["share_of_sessions"],
                   color=COLOR_NEUTRAL, height=0.6)
    ax.bar_label(bars, padding=4, fontsize=9,
                 labels=[f"{share:.1%}  ({n:,})" for share, n in zip(fn["share_of_sessions"], fn["sessions"])])
    ax.set_title("Share of all sessions that reach each funnel step")
    ax.set_xlabel("Share of all sessions (number of sessions in brackets)")
    ax.set_ylabel("Funnel step")
    ax.set_xlim(0, 1.25)
    ax.xaxis.set_major_formatter(PercentFormatter(1.0, decimals=0))
    ax.set_xticks([0, 0.25, 0.5, 0.75, 1.0])
    ax.grid(axis="y", visible=False)
    fig.tight_layout()
    fig.savefig(CHARTS_DIR / "05_funnel.png")
    plt.close(fig)
    print("  saved charts 01-05")

    # ---- Findings (every number below is read from the tables above) ----------------------
    first, last = full.iloc[0], full.iloc[-1]
    peak = full.loc[full["sessions"].idxmax()]
    by_channel = channels.set_index("channel")
    biggest = channels.iloc[0]  # SQL sorted by revenue, so row 0 is the biggest channel
    best = channels.loc[channels["revenue_per_session"].idxmax()]
    worst = channels.loc[channels["revenue_per_session"].idxmin()]
    organic = by_channel.loc["organic_search"]
    month = full.set_index("month")
    billing_to_order = reach["order"] / reach["billing"]
    share = dict(zip(funnel["step"], funnel["share_of_sessions"]))
    rollout = page_dates.loc["/billing", "last_seen"][:10]
    lander2 = page_dates.loc["/lander-2", "first_seen"][:10]
    product2 = products.set_index("product_id").loc[2, "launched_at"][:10]

    findings = f"""# Business overview - findings

Generated by `src/02_business_overview.py` from `sql/01-03`. Monthly numbers use full months
only ({first['month']} to {last['month']}); the first and last month in the data are partial.
The data is synthetic (Maven Fuzzy Factory, built by Maven Analytics for teaching).

## (a) Trend in sessions and orders  - chart 01
- Monthly sessions grew from {first['sessions']:,} ({first['month']}) to {last['sessions']:,} ({last['month']}), about {last['sessions'] / first['sessions']:.1f}x.
- Monthly orders grew faster: from {first['orders']:,} to {last['orders']:,}, about {last['orders'] / first['orders']:.0f}x. Orders outgrew traffic because conversion also improved (see b).
- Traffic is seasonal: it spikes every November-December. The busiest month was {peak['month']} with {peak['sessions']:,} sessions and {peak['orders']:,} orders.

## (b) Session-to-order conversion rate  - chart 02
- Conversion rose from {first['conv_rate']:.2%} ({first['month']}) to {last['conv_rate']:.2%} ({last['month']}).
- The clearest step up is around January 2013: {month.loc['2012-12', 'conv_rate']:.2%} in 2012-12, {month.loc['2013-01', 'conv_rate']:.2%} in 2013-01 and {month.loc['2013-02', 'conv_rate']:.2%} in 2013-02.
- Three things changed in that same fortnight: /billing-2 went to all visitors (after {rollout}), a second product launched ({product2}) and /lander-2 started ({lander2}). A trend line cannot separate these causes. That is exactly why the billing page needs a proper A/B test.

## (c) Most successful channels  - chart 03
- By size: {biggest['channel']} dominates with {biggest['share_of_sessions']:.1%} of sessions and {biggest['share_of_revenue']:.1%} of revenue (${biggest['revenue']:,.0f}).
- By quality: {best['channel']} converts best ({best['conv_rate']:.2%}, ${best['revenue_per_session']:.2f} revenue per session), followed by organic_search ({organic['conv_rate']:.2%}, ${organic['revenue_per_session']:.2f}). These are visitors who already know the brand or found the site themselves.
- {worst['channel']} is the weakest channel: {worst['conv_rate']:.2%} conversion and ${worst['revenue_per_session']:.2f} per session, about half of any other channel.

## (d) Revenue per order and per session  - chart 04
- Revenue per order was exactly ${month.loc['2012-12', 'revenue_per_order']:.2f} until the end of 2012, because the store sold a single product at one price.
- It rose to ${month.loc['2013-11', 'revenue_per_order']:.2f} by 2013-11 after product #2 launched, and to about ${month.loc['2014-02', 'revenue_per_order']:.2f} from 2014-02 once products #3 and #4 were on sale. It ended at ${last['revenue_per_order']:.2f} ({last['month']}).
- Revenue per session grew from ${first['revenue_per_session']:.2f} to ${last['revenue_per_session']:.2f}, about {last['revenue_per_session'] / first['revenue_per_session']:.1f}x. It is conversion rate x revenue per order, so both improvements feed into it.

## Funnel and where the A/B test sits  - chart 05
- Of all sessions, {share['products']:.1%} reach /products, {share['cart']:.1%} reach the cart, {share['shipping']:.1%} reach shipping, {share['billing']:.1%} reach a billing page and {share['order']:.1%} place an order.
- The billing page is the last step before an order. Over the whole period {billing_to_order:.1%} of sessions that reached a billing page ordered ({reach['order']:,} of {reach['billing']:,}), so more than a third of visitors who got as far as entering payment details still left.
- The A/B test in this project sits on exactly this step (billing -> order). Visitors there are the closest to buying, so a better billing page turns into orders directly.
"""
    (RESULTS_DIR / "business_findings.md").write_text(findings)
    print("  saved results/business_findings.md and 4 result CSVs")


if __name__ == "__main__":
    main()
