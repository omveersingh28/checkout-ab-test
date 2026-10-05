"""PHASE 4 - A/B test analysis: does the new billing page (/billing-2) lift orders?

HYPOTHESES AND DECISION RULES  (written down BEFORE looking at the results)
---------------------------------------------------------------------------
Unit of analysis : a session that reached a billing page during the test window.
Variants         : control = /billing (old page), treatment = /billing-2 (new page).
Primary metric   : billing-to-order conversion rate = orders / billing sessions.

  H0: conversion(/billing-2) = conversion(/billing)
  H1: the two conversion rates differ
  Test: two-proportion z-test, two-sided, alpha = 0.05.

Guardrails (things the new page must not damage):
  (1) net revenue per billing session = (revenue - refunds) / sessions   must NOT fall
  (2) refund rate per order = refunded orders / orders                   must not be significantly worse
  (3) gross margin per session = (revenue - cogs) / sessions             reported; should not fall

SHIP /billing-2 IF all of these are true:
  - the validity checks pass (traffic split, balance, contamination), AND
  - the lift is statistically significant (p < 0.05) with the 95% CI lower bound above 0, AND
  - guardrails (1) and (2) are OK.
Otherwise: do not ship.

Segments, the weekly view and the repeat-purchase follow-up are EXPLORATORY. They are
there to understand the result, not to make the decision.
"""
import json

import numpy as np
import pandas as pd
from matplotlib.ticker import FuncFormatter, PercentFormatter
from scipy.stats import chi2_contingency

from config import (ALPHA, CHARTS_DIR, COLOR_CONTROL, COLOR_NEUTRAL, COLOR_TREATMENT, CONTROL,
                    N_BOOT, POWER, RESULTS_DIR, SEED, TREATMENT, apply_chart_style, connect,
                    load_queries)
from stats_utils import (bootstrap_diff_ci, diff_ci, mde_two_prop, prop_ci, srm_pvalue,
                         two_prop_ztest)

plt = apply_chart_style()

VARIANTS = [CONTROL, TREATMENT]
COLORS = {CONTROL: COLOR_CONTROL, TREATMENT: COLOR_TREATMENT}
LABELS = {CONTROL: "Old page (/billing)", TREATMENT: "New page (/billing-2)"}
SRM_ALPHA = 0.001       # SRM fails only on very strong evidence, as is usual for this check
BALANCE_COLUMNS = ["device_type", "channel", "is_repeat_session", "landing_page"]

# Tolerances for the answer-key checks at the end of the script.
TOL_COUNT, TOL_PP, TOL_MONEY, TOL_P, TOL_Z = 2, 0.2, 0.10, 0.02, 0.1
# Bootstrap CI bounds are random numbers. With 2,000 resamples each bound moves by about
# +/- $0.04 (one standard deviation) from one random stream to the next, so two correct
# implementations can differ by more than $0.10. Only the bounds get this wider tolerance;
# every point estimate keeps +/- $0.10.
TOL_BOOT = 0.20

failed_checks = []


def check(name, actual, expected, tol):
    """Compare a computed number with the verified answer key. Never edits a number."""
    ok = abs(actual - expected) <= tol
    print(f"  {'PASS' if ok else 'FAIL'}  {name}: got {actual:,.4g}, expected {expected:,} (+/- {tol})")
    if not ok:
        failed_checks.append(name)


def fmt_p(p):
    return "< 0.001" if p < 0.001 else f"{p:.2f}"


def summarise(df):
    """Sessions, orders and conversion rate per variant, as plain Python numbers."""
    out = {}
    for v in VARIANTS:
        g = df[df["variant"] == v]
        out[v] = {"n": int(len(g)), "x": int(g["ordered"].sum())}
        out[v]["rate"] = out[v]["x"] / out[v]["n"]
    return out


def main():
    print("PHASE 4 - A/B test analysis")
    RESULTS_DIR.mkdir(exist_ok=True)
    CHARTS_DIR.mkdir(parents=True, exist_ok=True)

    con = connect()
    checks_sql = load_queries("05_ab_checks.sql")
    df = pd.read_sql_query("SELECT * FROM ab_sessions", con)
    start_ts, end_ts = con.execute(checks_sql["test_window"]).fetchone()
    both_users = pd.read_sql_query(checks_sql["users_in_both_variants"], con)
    repeat = pd.read_sql_query(checks_sql["repeat_purchase_90d"], con).set_index("variant")
    before_after = pd.read_sql_query(checks_sql["before_and_after_test"], con).set_index("period")
    con.close()

    control = df[df["variant"] == CONTROL]
    treat = df[df["variant"] == TREATMENT]
    s = summarise(df)
    n_c, x_c, n_t, x_t = s[CONTROL]["n"], s[CONTROL]["x"], s[TREATMENT]["n"], s[TREATMENT]["x"]

    # =====================================================================================
    # A. VALIDITY CHECKS  (before looking at the lift: is the experiment itself sound?)
    # =====================================================================================
    print("\nA. Validity checks")

    # A1. Sample ratio mismatch: a 50/50 test should give two groups of about the same size.
    srm_p = srm_pvalue(n_c, n_t)
    srm_ok = srm_p >= SRM_ALPHA
    print(f"  {'PASS' if srm_ok else 'FAIL'}  SRM: {n_c:,} vs {n_t:,} sessions, p = {srm_p:.3f}")

    # A2. Balance: the two groups should be made of the same kind of sessions. If one page
    #     got more desktop users, a difference in orders could be the device and not the page.
    #     Uses scipy's default settings: on a 2x2 table (device, repeat session, landing page)
    #     that includes Yates' continuity correction, which gives slightly more cautious p-values.
    balance_p = {}
    for col in BALANCE_COLUMNS:
        table = pd.crosstab(df["variant"], df[col])
        balance_p[col] = float(chi2_contingency(table)[1])
        print(f"  {'PASS' if balance_p[col] > ALPHA else 'WARN'}  balance on {col}: p = {balance_p[col]:.3f}")
    balance_ok = all(p > ALPHA for p in balance_p.values())

    # A3. Contamination: the split was per session, so a returning user could see both pages.
    n_both_users = int(len(both_users))
    n_both_sessions = int(both_users["sessions"].sum())
    clean = df[~df["user_id"].isin(both_users["user_id"])]
    sc = summarise(clean)
    z_clean, p_clean = two_prop_ztest(sc[CONTROL]["x"], sc[CONTROL]["n"], sc[TREATMENT]["x"], sc[TREATMENT]["n"])
    print(f"  INFO  {n_both_users} users saw both pages ({n_both_sessions} sessions)")

    # =====================================================================================
    # B. PRIMARY RESULT
    # =====================================================================================
    print("\nB. Primary result: billing-to-order conversion")
    p_c, p_t = s[CONTROL]["rate"], s[TREATMENT]["rate"]
    z, p_value = two_prop_ztest(x_c, n_c, x_t, n_t)
    lift, ci_low, ci_high = diff_ci(x_c, n_c, x_t, n_t)
    lift_rel = lift / p_c
    _, boot_low, boot_high = bootstrap_diff_ci(control["ordered"], treat["ordered"], N_BOOT, SEED)

    # Cross-check: a chi-square test on the 2x2 table is the same test as the z-test
    # (chi-square = z squared), so the two p-values must agree. correction=False switches
    # off the continuity correction, because the z-test does not have one either.
    chi2_p = float(chi2_contingency([[x_c, n_c - x_c], [x_t, n_t - x_t]], correction=False)[1])
    assert np.isclose(p_value, chi2_p, rtol=1e-6), (p_value, chi2_p)

    for v in VARIANTS:
        print(f"  {v:<11} {s[v]['x']:>5,} orders / {s[v]['n']:,} sessions = {s[v]['rate']:.2%}")
    print(f"  lift {lift * 100:+.2f} pp (relative {lift_rel:+.1%}), 95% CI [{ci_low * 100:.2f}, {ci_high * 100:.2f}] pp")
    print(f"  bootstrap 95% CI [{boot_low * 100:.2f}, {boot_high * 100:.2f}] pp")
    print(f"  z = {z:.2f}, p {fmt_p(p_value)} (z-test p = {p_value:.2e}, chi-square p = {chi2_p:.2e})")

    # Sensitivity: same test without the users who saw both pages.
    clean_lift = sc[TREATMENT]["rate"] - sc[CONTROL]["rate"]
    same_conclusion = (p_clean < ALPHA) == (p_value < ALPHA) and np.sign(clean_lift) == np.sign(lift)
    print(f"  sensitivity without those users: {sc[CONTROL]['n']:,} vs {sc[TREATMENT]['n']:,} sessions, "
          f"{sc[CONTROL]['rate']:.2%} vs {sc[TREATMENT]['rate']:.2%}, z = {z_clean:.2f} "
          f"-> {'same conclusion' if same_conclusion else 'DIFFERENT conclusion'}")

    # =====================================================================================
    # C. POWER: what is the smallest lift this test could reliably detect?
    # =====================================================================================
    mde = mde_two_prop(p_c, min(n_c, n_t), ALPHA, POWER)
    print(f"\nC. Minimum detectable effect: {mde * 100:.2f} pp (observed lift {lift * 100:.1f} pp)")

    # =====================================================================================
    # D. GUARDRAILS
    # =====================================================================================
    print("\nD. Guardrails")
    money = {
        "revenue_per_session": lambda g: g["revenue"],
        "net_revenue_per_session": lambda g: g["revenue"] - g["refund_usd"],  # after refunds
        "gross_margin_per_session": lambda g: g["revenue"] - g["cogs"],       # after product cost
    }
    guardrails = {}
    for name, value in money.items():
        a, b = value(control), value(treat)
        # Bootstrap CI: per-session money is mostly zeros plus a few $49.99, so not bell-shaped.
        d, low, high = bootstrap_diff_ci(a, b, N_BOOT, SEED)
        guardrails[name] = {CONTROL: float(a.mean()), TREATMENT: float(b.mean()),
                            "diff": d, "ci_low": low, "ci_high": high}
        print(f"  {name:<25} ${a.mean():.2f} vs ${b.mean():.2f}  diff {d:+.2f}  95% CI [{low:.2f}, {high:.2f}]")

    # Refund rate per ORDER (a session without an order cannot be refunded).
    r_c = int((control["refund_usd"] > 0).sum())
    r_t = int((treat["refund_usd"] > 0).sum())
    z_ref, p_ref = two_prop_ztest(r_c, x_c, r_t, x_t)
    d_ref, ref_low, ref_high = diff_ci(r_c, x_c, r_t, x_t)
    guardrails["refund_rate_per_order"] = {
        CONTROL: r_c / x_c, TREATMENT: r_t / x_t, "refunded_orders": {CONTROL: r_c, TREATMENT: r_t},
        "diff": d_ref, "ci_low": ref_low, "ci_high": ref_high, "z": z_ref, "p_value": p_ref}
    print(f"  refund rate per order     {r_c} of {x_c} ({r_c / x_c:.1%}) vs {r_t} of {x_t} ({r_t / x_t:.1%})  "
          f"diff {d_ref * 100:+.2f} pp  95% CI [{ref_low * 100:.2f}, {ref_high * 100:.2f}] pp  p = {p_ref:.2f}")

    # Average order value: reported only. One product existed, so it cannot differ.
    aov = {v: float(df[(df["variant"] == v) & (df["ordered"] == 1)]["revenue"].mean()) for v in VARIANTS}
    print(f"  average order value       ${aov[CONTROL]:.2f} vs ${aov[TREATMENT]:.2f} (single product -> not informative)")

    net_ok = guardrails["net_revenue_per_session"]["diff"] >= 0            # guardrail (1)
    refund_ok = not (p_ref < ALPHA and d_ref > 0)                           # guardrail (2)
    margin_ok = guardrails["gross_margin_per_session"]["diff"] >= 0        # guardrail (3), reported
    print(f"  {'PASS' if net_ok else 'FAIL'}  (1) net revenue per session did not fall")
    print(f"  {'PASS' if refund_ok else 'FAIL'}  (2) refund rate is not significantly worse (but note the wide CI)")
    print(f"  {'PASS' if margin_ok else 'FAIL'}  (3) gross margin per session did not fall")

    # =====================================================================================
    # E. SEGMENTS  (exploratory, not for decisions)
    # =====================================================================================
    print("\nE. Segments by device (exploratory)")
    segments = {}
    for device, g in df.groupby("device_type"):
        sg = summarise(g)
        d, low, high = diff_ci(sg[CONTROL]["x"], sg[CONTROL]["n"], sg[TREATMENT]["x"], sg[TREATMENT]["n"])
        segments[device] = {"sessions": {v: sg[v]["n"] for v in VARIANTS},
                            "orders": {v: sg[v]["x"] for v in VARIANTS},
                            "conv_rates": {v: sg[v]["rate"] for v in VARIANTS},
                            "lift_pp": d * 100, "ci_low_pp": low * 100, "ci_high_pp": high * 100}
        print(f"  {device:<8} {sg[CONTROL]['rate']:.1%} (n={sg[CONTROL]['n']:,}) -> {sg[TREATMENT]['rate']:.1%} "
              f"(n={sg[TREATMENT]['n']:,})  lift {d * 100:+.1f} pp  95% CI [{low * 100:.1f}, {high * 100:.1f}]")

    # =====================================================================================
    # F. STABILITY: is the lift there every week, or only at the start (novelty effect)?
    # =====================================================================================
    print("\nF. Stability")
    ts = pd.to_datetime(df["billing_ts"])
    first_day = ts.min().normalize()
    df["week"] = (ts - first_day).dt.days // 7           # week 0 = first 7 days of the test
    weekly = (df.groupby(["week", "variant"])["ordered"].agg(sessions="count", orders="sum").reset_index())
    weekly["conv_rate"] = weekly["orders"] / weekly["sessions"]
    weekly["week_start"] = (first_day + pd.to_timedelta(weekly["week"] * 7, unit="D")).dt.strftime("%Y-%m-%d")
    wide = weekly.pivot(index="week_start", columns="variant", values="conv_rate")
    n_weeks = int(len(wide))
    weeks_ahead = int((wide[TREATMENT] > wide[CONTROL]).sum())
    print(f"  new page ahead in {weeks_ahead} of {n_weeks} weeks "
          f"(smallest weekly group: {weekly['sessions'].min()} sessions)")
    weekly[["week", "week_start", "variant", "sessions", "orders", "conv_rate"]].round(4).to_csv(
        RESULTS_DIR / "ab_weekly_conversion.csv", index=False)

    # .astype(int): the counts come back as whole numbers, keep them that way for printing.
    pre = before_after.loc["before_test_billing", ["sessions", "orders"]].astype(int)
    post = before_after.loc["after_rollout_billing2", ["sessions", "orders"]].astype(int)
    print(f"  before the test, /billing:       {pre['orders']:,} / {pre['sessions']:,} = {pre['orders'] / pre['sessions']:.1%}")
    print(f"  56 days after test, /billing-2:  {post['orders']:,} / {post['sessions']:,} = {post['orders'] / post['sessions']:.1%}")

    # =====================================================================================
    # G. REPEAT PURCHASE within 90 days  (exploratory)
    # =====================================================================================
    rep = {v: int(repeat.loc[v, "repeat_within_90d"]) for v in VARIANTS}
    print(f"\nG. Repeat purchase within 90 days: {rep[CONTROL]} of {x_c} vs {rep[TREATMENT]} of {x_t} "
          "-> inconclusive, repeat purchases are rare in this data")

    # =====================================================================================
    # H. BUSINESS IMPACT  (only what the data shows; no annual extrapolation)
    # =====================================================================================
    extra_orders = lift * 1000
    print(f"\nH. Impact: about {extra_orders:.0f} extra orders per 1,000 billing sessions "
          f"(95% CI {ci_low * 1000:.0f} to {ci_high * 1000:.0f}); revenue per billing session "
          f"{guardrails['revenue_per_session']['diff']:+.2f} USD")

    # =====================================================================================
    # DECISION  (apply the rules from the top of this file, nothing else)
    # =====================================================================================
    validity_ok = srm_ok and balance_ok and same_conclusion
    significant = p_value < ALPHA and ci_low > 0
    ship = validity_ok and significant and net_ok and refund_ok
    decision = "SHIP /billing-2" if ship else "DO NOT SHIP /billing-2"
    print(f"\nDECISION: {decision}")
    print(f"  validity checks pass: {validity_ok} | significant lift with CI above 0: {significant} | "
          f"net revenue OK: {net_ok} | refund rate OK: {refund_ok}")

    # =====================================================================================
    # I. SAVE every number (README and memo are written from this file)
    # =====================================================================================
    results = {
        "test_window": {"start": start_ts, "end": end_ts, "calendar_weeks": n_weeks},
        "sessions": {CONTROL: n_c, TREATMENT: n_t, "total": n_c + n_t},
        "orders": {CONTROL: x_c, TREATMENT: x_t},
        "conv_rates": {CONTROL: p_c, TREATMENT: p_t},
        "lift_pp": lift * 100,
        "lift_rel": lift_rel,
        "ci": {"level": 0.95, "low_pp": ci_low * 100, "high_pp": ci_high * 100,
               "bootstrap_low_pp": boot_low * 100, "bootstrap_high_pp": boot_high * 100},
        "p_values": {"z": z, "primary_ztest": p_value, "primary_chi2": chi2_p, "refund_rate": p_ref},
        "srm_p": srm_p,
        "balance_p": balance_p,
        "contamination": {
            "users_in_both_variants": n_both_users, "their_sessions": n_both_sessions,
            "sensitivity_sessions": {v: sc[v]["n"] for v in VARIANTS},
            "sensitivity_conv_rates": {v: sc[v]["rate"] for v in VARIANTS},
            "sensitivity_z": z_clean, "sensitivity_p": p_clean, "same_conclusion": bool(same_conclusion)},
        "guardrails": {**guardrails, "average_order_value": aov,
                       "ok": {"net_revenue": bool(net_ok), "refund_rate": bool(refund_ok), "gross_margin": bool(margin_ok)}},
        "segments": segments,
        "stability": {
            "weeks": n_weeks, "weeks_new_page_ahead": weeks_ahead,
            "before_test_billing": {"sessions": int(pre["sessions"]), "orders": int(pre["orders"]),
                                    "conv_rate": float(pre["orders"] / pre["sessions"])},
            "after_rollout_billing2_56d": {"sessions": int(post["sessions"]), "orders": int(post["orders"]),
                                           "conv_rate": float(post["orders"] / post["sessions"])}},
        "repeat90": {"ordering_sessions": {CONTROL: x_c, TREATMENT: x_t}, "repeat_within_90d": rep,
                     "rates": {CONTROL: rep[CONTROL] / x_c, TREATMENT: rep[TREATMENT] / x_t}},
        "mde_pp": mde * 100,
        "impact": {"extra_orders_per_1000_billing_sessions": extra_orders,
                   "extra_orders_ci_low": ci_low * 1000, "extra_orders_ci_high": ci_high * 1000,
                   "revenue_per_billing_session_diff": guardrails["revenue_per_session"]["diff"]},
        "decision": {"ship": bool(ship), "text": decision, "validity_ok": bool(validity_ok),
                     "significant": bool(significant)},
    }
    with open(RESULTS_DIR / "ab_results.json", "w") as f:
        json.dump(results, f, indent=2)
    print("\nI. saved results/ab_results.json")

    # =====================================================================================
    # CHARTS 06-10  (blue = old page, orange = new page, in every chart)
    # =====================================================================================
    pct_axis = PercentFormatter(1.0, decimals=0)

    # ---- 06: conversion with 95% CI ------------------------------------------------------
    fig, ax = plt.subplots(figsize=(7, 5))
    for i, v in enumerate(VARIANTS):
        p, low, high = prop_ci(s[v]["x"], s[v]["n"])
        ax.bar(i, p, width=0.5, color=COLORS[v])
        ax.errorbar(i, p, yerr=[[p - low], [high - p]], color="#0b0b0b", capsize=6, linewidth=1.5)
        ax.text(i, high + 0.015, f"{p:.1%}", ha="center", va="bottom", fontsize=13, fontweight="bold")
    ax.set_xticks([0, 1], [f"{LABELS[v]}\n{s[v]['x']:,} orders / {s[v]['n']:,} sessions" for v in VARIANTS])
    ax.set_xlim(-0.6, 1.6)
    ax.set_ylim(0, 0.8)
    ax.yaxis.set_major_formatter(pct_axis)
    ax.set_ylabel("Billing sessions that placed an order")
    ax.set_title(f"Billing-to-order conversion: {lift * 100:+.1f} pp with the new page")
    ax.set_xlabel(f"Difference {lift * 100:+.1f} pp, 95% CI [{ci_low * 100:.1f}, {ci_high * 100:.1f}] pp, "
                  f"p {fmt_p(p_value)}. Whiskers = 95% CI of each rate.", fontsize=9, labelpad=10)
    ax.grid(axis="x", visible=False)
    fig.tight_layout()
    fig.savefig(CHARTS_DIR / "06_ab_conversion_with_ci.png")
    plt.close(fig)

    # ---- 07: guardrails ------------------------------------------------------------------
    panels = [("revenue_per_session", "Revenue per session", "money"),
              ("net_revenue_per_session", "Net revenue per session\n(after refunds) - guardrail 1", "money"),
              ("gross_margin_per_session", "Gross margin per session\n(after product cost) - guardrail 3", "money"),
              ("refund_rate_per_order", "Refund rate per order\n(lower is better) - guardrail 2", "rate")]
    fig, axes = plt.subplots(1, 4, figsize=(14, 4.6))
    for ax, (key, title, kind) in zip(axes, panels):
        g = guardrails[key]
        values = [g[v] for v in VARIANTS]
        bars = ax.bar([0, 1], values, width=0.55, color=[COLORS[v] for v in VARIANTS])
        if kind == "money":
            ax.bar_label(bars, labels=[f"${v:.2f}" for v in values], padding=3, fontweight="bold")
            ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"${v:.0f}"))
            note = f"diff {g['diff']:+.2f} USD\n95% CI [{g['ci_low']:.2f}, {g['ci_high']:.2f}]"
        else:
            ax.bar_label(bars, labels=[f"{v:.1%}" for v in values], padding=3, fontweight="bold")
            ax.yaxis.set_major_formatter(PercentFormatter(1.0, decimals=0))
            note = (f"diff {g['diff'] * 100:+.1f} pp, p = {g['p_value']:.2f} (not significant)\n"
                    f"95% CI [{g['ci_low'] * 100:.1f}, {g['ci_high'] * 100:.1f}] pp - wide")
        ax.set_xticks([0, 1], ["Old page\n/billing", "New page\n/billing-2"])
        ax.set_xlim(-0.6, 1.6)
        ax.set_ylim(0, max(values) * 1.2)
        ax.set_title(title, fontsize=10)
        ax.set_xlabel(note, fontsize=9, labelpad=8)
        ax.grid(axis="x", visible=False)
    fig.suptitle("Guardrail metrics by billing page (diff = new page minus old page)",
                 x=0.01, ha="left", fontsize=12, fontweight="bold")
    fig.tight_layout()
    fig.savefig(CHARTS_DIR / "07_ab_guardrails.png")
    plt.close(fig)

    # ---- 08: weekly conversion -----------------------------------------------------------
    fig, ax = plt.subplots(figsize=(10, 5))
    week_dates = pd.to_datetime(wide.index)
    for v in VARIANTS:
        ax.plot(week_dates, wide[v], color=COLORS[v], marker="o", markersize=5, label=LABELS[v])
    ax.set_ylim(0, 0.9)
    ax.yaxis.set_major_formatter(pct_axis)
    ax.set_ylabel("Billing-to-order conversion")
    ax.set_xlabel("Week of the test (starting date; the last week has 6 days)")
    ax.set_title(f"Weekly conversion: the new page is ahead in {weeks_ahead} of {n_weeks} weeks")
    ax.set_xticks(week_dates[::2], [d.strftime("%d %b") for d in week_dates[::2]])
    ax.legend(loc="lower right")
    fig.tight_layout()
    fig.savefig(CHARTS_DIR / "08_ab_weekly_conversion.png")
    plt.close(fig)

    # ---- 09: by device -------------------------------------------------------------------
    devices = sorted(segments)  # desktop, mobile
    fig, ax = plt.subplots(figsize=(8, 5))
    width = 0.36
    for j, v in enumerate(VARIANTS):
        for i, device in enumerate(devices):
            seg = segments[device]
            p, low, high = prop_ci(seg["orders"][v], seg["sessions"][v])
            x = i + (j - 0.5) * (width + 0.02)   # small gap between the two bars of a device
            ax.bar(x, p, width=width, color=COLORS[v], label=LABELS[v] if i == 0 else None)
            ax.errorbar(x, p, yerr=[[p - low], [high - p]], color="#0b0b0b", capsize=5, linewidth=1.2)
            ax.text(x, high + 0.015, f"{p:.1%}\nn={seg['sessions'][v]:,}", ha="center", va="bottom", fontsize=9)
    ax.set_xticks(range(len(devices)), [f"{d}\nlift {segments[d]['lift_pp']:+.1f} pp" for d in devices])
    ax.set_ylim(0, 0.9)
    ax.yaxis.set_major_formatter(pct_axis)
    ax.set_ylabel("Billing-to-order conversion")
    ax.set_xlabel("Device type (whiskers = 95% CI; mobile groups are small)")
    ax.set_title("Conversion by device (exploratory, not for decisions)")
    ax.legend(loc="upper right")
    ax.grid(axis="x", visible=False)
    fig.tight_layout()
    fig.savefig(CHARTS_DIR / "09_ab_by_device.png")
    plt.close(fig)

    # ---- 10: validity checks as a table --------------------------------------------------
    rows = [["Sample ratio (50/50 split)", f"{n_c:,} vs {n_t:,} sessions", f"{srm_p:.2f}", "PASS" if srm_ok else "FAIL"]]
    for col in BALANCE_COLUMNS:
        rows.append([f"Balance: {col}", "same mix in both groups?", f"{balance_p[col]:.2f}",
                     "PASS" if balance_p[col] > ALPHA else "WARN"])
    rows.append(["Users who saw both pages", f"{n_both_users} users, {n_both_sessions} sessions", "-",
                 "see next row"])
    rows.append(["Result without those users", f"{sc[CONTROL]['rate']:.1%} vs {sc[TREATMENT]['rate']:.1%}, z = {z_clean:.1f}",
                 fmt_p(p_clean), "same conclusion" if same_conclusion else "differs"])
    fig, ax = plt.subplots(figsize=(9.5, 3.2))
    ax.axis("off")
    table = ax.table(cellText=rows, colLabels=["Check", "What we saw", "p-value", "Status"],
                     cellLoc="left", colLoc="left", loc="center", colWidths=[0.30, 0.36, 0.12, 0.22])
    table.auto_set_font_size(False)
    table.set_fontsize(9.5)
    table.scale(1, 1.5)
    for (r, _), cell in table.get_celld().items():
        cell.set_edgecolor("#e1e0d9")
        if r == 0:
            cell.set_text_props(fontweight="bold")
            cell.set_facecolor("#f0efec")
    ax.set_title("Experiment validity checks (SRM fails only if p < 0.001; balance is fine if p > 0.05)", pad=12)
    fig.tight_layout()
    fig.savefig(CHARTS_DIR / "10_ab_validity_checks.png")
    plt.close(fig)
    print("   saved charts 06-10")

    # =====================================================================================
    # ANSWER-KEY CHECKS: the verified numbers for this dataset. A FAIL means a bug to fix.
    # =====================================================================================
    print("\nAnswer-key checks")
    g = guardrails
    check("sessions /billing", n_c, 1663, TOL_COUNT)
    check("sessions /billing-2", n_t, 1657, TOL_COUNT)
    check("orders /billing", x_c, 750, TOL_COUNT)
    check("orders /billing-2", x_t, 1029, TOL_COUNT)
    check("conversion /billing (%)", p_c * 100, 45.10, TOL_PP)
    check("conversion /billing-2 (%)", p_t * 100, 62.10, TOL_PP)
    check("lift (pp)", lift * 100, 17.0, TOL_PP)
    check("relative lift (%)", lift_rel * 100, 37.7, TOL_PP)
    check("CI low (pp)", ci_low * 100, 13.7, TOL_PP)
    check("CI high (pp)", ci_high * 100, 20.3, TOL_PP)
    check("z", z, 9.8, TOL_Z)
    check("p-value below 0.001", float(p_value < 0.001), 1, 0)
    check("SRM p", srm_p, 0.92, TOL_P)
    check("balance p device", balance_p["device_type"], 0.23, TOL_P)
    check("balance p repeat session", balance_p["is_repeat_session"], 0.76, TOL_P)
    check("balance p channel", balance_p["channel"], 0.70, TOL_P)
    check("balance p landing page", balance_p["landing_page"], 0.72, TOL_P)
    check("revenue/session /billing", g["revenue_per_session"][CONTROL], 22.55, TOL_MONEY)
    check("revenue/session /billing-2", g["revenue_per_session"][TREATMENT], 31.04, TOL_MONEY)
    check("revenue/session diff", g["revenue_per_session"]["diff"], 8.50, TOL_MONEY)
    check("revenue/session CI low", g["revenue_per_session"]["ci_low"], 6.8, TOL_BOOT)
    check("revenue/session CI high", g["revenue_per_session"]["ci_high"], 10.2, TOL_BOOT)
    check("net revenue/session /billing", g["net_revenue_per_session"][CONTROL], 21.13, TOL_MONEY)
    check("net revenue/session /billing-2", g["net_revenue_per_session"][TREATMENT], 28.69, TOL_MONEY)
    check("net revenue/session diff", g["net_revenue_per_session"]["diff"], 7.56, TOL_MONEY)
    check("net revenue/session CI low", g["net_revenue_per_session"]["ci_low"], 5.9, TOL_BOOT)
    check("net revenue/session CI high", g["net_revenue_per_session"]["ci_high"], 9.3, TOL_BOOT)
    check("margin/session /billing", g["gross_margin_per_session"][CONTROL], 13.76, TOL_MONEY)
    check("margin/session /billing-2", g["gross_margin_per_session"][TREATMENT], 18.94, TOL_MONEY)
    check("margin/session diff", g["gross_margin_per_session"]["diff"], 5.19, TOL_MONEY)
    check("margin/session CI low", g["gross_margin_per_session"]["ci_low"], 4.1, TOL_BOOT)
    check("margin/session CI high", g["gross_margin_per_session"]["ci_high"], 6.2, TOL_BOOT)
    check("refunded orders /billing", r_c, 47, TOL_COUNT)
    check("refunded orders /billing-2", r_t, 78, TOL_COUNT)
    check("refund rate diff (pp)", d_ref * 100, 1.3, TOL_PP)
    check("refund rate p", p_ref, 0.28, TOL_P)
    check("refund rate CI low (pp)", ref_low * 100, -1.1, TOL_PP)
    check("refund rate CI high (pp)", ref_high * 100, 3.7, TOL_PP)
    check("average order value /billing", aov[CONTROL], 49.99, TOL_MONEY)
    check("average order value /billing-2", aov[TREATMENT], 49.99, TOL_MONEY)
    check("users in both variants", n_both_users, 18, TOL_COUNT)
    check("sessions of those users", n_both_sessions, 38, TOL_COUNT)
    check("sensitivity sessions /billing", sc[CONTROL]["n"], 1644, TOL_COUNT)
    check("sensitivity sessions /billing-2", sc[TREATMENT]["n"], 1638, TOL_COUNT)
    check("sensitivity conversion /billing (%)", sc[CONTROL]["rate"] * 100, 44.95, TOL_PP)
    check("sensitivity conversion /billing-2 (%)", sc[TREATMENT]["rate"] * 100, 62.09, TOL_PP)
    check("sensitivity z", z_clean, 9.8, TOL_Z)
    check("repeat purchase /billing", rep[CONTROL], 7, TOL_COUNT)
    check("repeat purchase /billing-2", rep[TREATMENT], 10, TOL_COUNT)
    check("MDE (pp)", mde * 100, 4.8, TOL_PP)
    check("test length (weeks)", n_weeks, 17, 0)
    check("weeks with new page ahead", weeks_ahead, 17, 0)
    check("desktop conversion /billing (%)", segments["desktop"]["conv_rates"][CONTROL] * 100, 46.3, TOL_PP)
    check("desktop conversion /billing-2 (%)", segments["desktop"]["conv_rates"][TREATMENT] * 100, 63.8, TOL_PP)
    check("mobile conversion /billing (%)", segments["mobile"]["conv_rates"][CONTROL] * 100, 34.3, TOL_PP)
    check("mobile conversion /billing-2 (%)", segments["mobile"]["conv_rates"][TREATMENT] * 100, 49.5, TOL_PP)
    check("before-test /billing conversion (%)", pre["orders"] / pre["sessions"] * 100, 44.5, TOL_PP)
    check("after-rollout /billing-2 conversion (%)", post["orders"] / post["sessions"] * 100, 63.3, TOL_PP)
    check("extra orders per 1,000 sessions", extra_orders, 170, 2)
    check("decision is SHIP", float(ship), 1, 0)

    if failed_checks:
        raise SystemExit(f"\n{len(failed_checks)} answer-key check(s) FAILED: {failed_checks}")
    print("\n  all answer-key checks passed")


if __name__ == "__main__":
    main()
