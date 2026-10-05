# Decision memo: new billing page (/billing-2)

**To:** Checkout team  |  **Test:** 2012-09-10 to 2013-01-05 (17 weeks), 3,320 billing sessions  |  **Data:** synthetic (Maven Fuzzy Factory)

## Decision
**SHIP /billing-2** - keep it live for all visitors (it has been the only billing page since 2013-01-06).

## Why
- **More visitors who reach billing place an order:** 45.1% with the old page (750 of 1,663) vs 62.1% with the new page (1,029 of 1,657). That is +17.0 pp, a relative lift of +37.7%.
- **The lift is not chance:** 95% CI for the difference is 13.7 to 20.3 pp and p < 0.001 (z = 9.82). The test could detect lifts of about 4.8 pp, and this one is more than three times that.
- **The experiment was sound and the lift was steady:** the traffic split was even (SRM p = 0.92), both groups had the same mix of device, channel, new/returning sessions and landing page (all p > 0.05), and the new page was ahead in 17 of 17 weeks.

In business terms: about 170 extra orders for every 1,000 sessions that reach the billing page, and $8.50 more revenue per billing session (95% CI 6.75 to 10.15).

## Guardrails
| Guardrail | Old page | New page | Difference | Verdict |
|---|---|---|---|---|
| Net revenue per session (after refunds) | $21.13 | $28.69 | +$7.56 (95% CI 5.78 to 9.16) | OK - it rose |
| Refund rate per order | 6.3% (47 of 750) | 7.6% (78 of 1,029) | +1.3 pp (95% CI -1.1 to +3.7), p = 0.28 | OK - not significant, but see risks |
| Gross margin per session | $13.76 | $18.94 | +$5.19 (95% CI 4.12 to 6.19) | OK - it rose |

## Risks and what the test cannot tell us
- **Refunds are not settled.** The refund rate was a little higher with the new page. The difference is not statistically significant, but the interval is wide: the true effect could be anywhere from 1.1 pp lower to 3.7 pp higher. Even so, net revenue per session (which already subtracts refunds) rose clearly.
- **Only the billing step was tested** (billing -> order). The test says nothing about earlier steps of the funnel.
- **Repeat purchases are inconclusive.** Only 7 of 750 and 10 of 1,029 buyers ordered again within 90 days - too few to compare.
- **Mobile detail is rough.** Only 366 mobile billing sessions were in the test. Mobile improved (34.3% -> 49.5%) but its interval is wide (5.2 to 25.2 pp).
- **18 users saw both pages** (38 sessions), because the split was per session. Removing them changes nothing (45.0% vs 62.1%, z = 9.84).
- **The rollout check is not a second experiment.** In the 56 days after the test, /billing-2 converted at 63.3% (834 of 1,318) vs 44.5% for /billing before the test (870 of 1,954). This agrees with the test, but a second product and a new landing page launched in the same weeks.
- **The data is synthetic**, built by Maven Analytics for teaching. Real experiments are usually messier, and a lift this large would be unusual.

## Recommended next step
1. Keep /billing-2 at 100% of traffic.
2. Track refund rate per order monthly until there are enough orders to narrow the interval.
3. Test an earlier funnel step next. The largest drop is at the product page: only 45.2% of sessions that view a product add it to the cart (94,953 of 210,214).

*All numbers come from `results/ab_results.json` and `results/funnel.csv`, produced by `python run_all.py`.*
