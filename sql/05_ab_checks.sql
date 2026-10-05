-- 05_ab_checks.sql
-- Small summary queries for the A/B test. They read the ab_sessions table (04_ab_sessions.sql).

-- name: test_window
-- The test window, read straight from the pageviews (same rule as in 04_ab_sessions.sql).
SELECT (SELECT MIN(created_at) FROM website_pageviews WHERE pageview_url = '/billing-2') AS start_ts,
       (SELECT MAX(created_at) FROM website_pageviews WHERE pageview_url = '/billing')   AS end_ts;

-- name: variant_summary
-- The headline table: sessions, orders, conversion and money per variant.
SELECT variant, COUNT(*) AS sessions, SUM(ordered) AS orders,
       ROUND(1.0 * SUM(ordered) / COUNT(*), 4) AS conv_rate,
       ROUND(SUM(revenue), 2) AS revenue, ROUND(SUM(cogs), 2) AS cogs, ROUND(SUM(refund_usd), 2) AS refunds
FROM ab_sessions GROUP BY variant;

-- name: sessions_with_both_pages
-- A session must belong to exactly one variant. This must return 0.
SELECT COUNT(*) AS sessions_with_both_pages
FROM (SELECT website_session_id
      FROM ab_sessions
      GROUP BY website_session_id
      HAVING COUNT(DISTINCT variant) > 1);

-- name: users_in_both_variants
-- Contamination check: the split was made per session, so a user who came back could see
-- the other page. Lists those users and how many test sessions they had.
SELECT user_id, COUNT(*) AS sessions
FROM ab_sessions
GROUP BY user_id
HAVING COUNT(DISTINCT variant) = 2
ORDER BY user_id;

-- name: repeat_purchase_90d
-- Of the sessions that ordered: did the same user place ANOTHER order within 90 days?
-- EXISTS returns 1 or 0 for each row, so SUM(EXISTS ...) counts the rows where it is true.
SELECT a.variant,
       COUNT(*) AS ordering_sessions,
       SUM(EXISTS (SELECT 1 FROM orders o2
                   WHERE o2.user_id = a.user_id
                     AND o2.created_at > a.order_ts
                     AND o2.created_at <= datetime(a.order_ts, '+90 days'))) AS repeat_within_90d
FROM ab_sessions a
WHERE a.ordered = 1
GROUP BY a.variant;

-- name: before_and_after_test
-- Observational check OUTSIDE the experiment (not a second A/B test):
--   before_test_billing    = all /billing sessions before the test started
--   after_rollout_billing2 = /billing-2 sessions in the 56 days after the test ended
-- If the new page is really better, the after-rollout rate should look like the test result.
WITH bounds AS (
  SELECT (SELECT MIN(created_at) FROM website_pageviews WHERE pageview_url = '/billing-2') AS start_ts,
         (SELECT MAX(created_at) FROM website_pageviews WHERE pageview_url = '/billing')   AS end_ts
),
billing_views AS (
  SELECT website_session_id, pageview_url AS variant, MIN(created_at) AS billing_ts
  FROM website_pageviews
  WHERE pageview_url IN ('/billing', '/billing-2')
  GROUP BY website_session_id, pageview_url
)
SELECT CASE WHEN bv.billing_ts < b.start_ts THEN 'before_test_billing'
            ELSE 'after_rollout_billing2' END                    AS period,
       COUNT(*)                                                  AS sessions,
       COUNT(o.order_id)                                         AS orders,
       ROUND(1.0 * COUNT(o.order_id) / COUNT(*), 4)              AS conv_rate
FROM billing_views bv
CROSS JOIN bounds b
LEFT JOIN orders o ON o.website_session_id = bv.website_session_id
WHERE (bv.variant = '/billing'   AND bv.billing_ts < b.start_ts)
   OR (bv.variant = '/billing-2' AND bv.billing_ts > b.end_ts
                                 AND bv.billing_ts <= datetime(b.end_ts, '+56 days'))
GROUP BY 1
ORDER BY 1 DESC;
