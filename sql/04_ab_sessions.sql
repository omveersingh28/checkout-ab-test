-- 04_ab_sessions.sql
-- Builds the table ab_sessions: ONE ROW PER SESSION that reached a billing page during the
-- A/B test. Everything in the test analysis is computed from this one table.
--
--   Unit of analysis : a session that saw a billing page
--   Variant          : which billing page it saw ('/billing' = old, '/billing-2' = new)
--   Outcome          : did the session place an order (ordered = 1 / 0)
--
-- The test window is DERIVED from the data, not typed in by hand:
--   start = the first ever /billing-2 pageview (before that, the new page did not exist)
--   end   = the last ever /billing pageview    (after that, everyone got the new page)
-- Only inside this window were both pages live at the same time, so only there is the
-- comparison fair.

DROP TABLE IF EXISTS ab_sessions;

CREATE TABLE ab_sessions AS
WITH bounds AS (
  -- The start and end of the test window (one row, two columns).
  SELECT (SELECT MIN(created_at) FROM website_pageviews WHERE pageview_url = '/billing-2') AS start_ts,
         (SELECT MAX(created_at) FROM website_pageviews WHERE pageview_url = '/billing')   AS end_ts
),
billing_views AS (
  -- Every session that saw a billing page, which page, and when it first saw it.
  SELECT website_session_id, pageview_url AS variant, MIN(created_at) AS billing_ts
  FROM website_pageviews
  WHERE pageview_url IN ('/billing', '/billing-2')
  GROUP BY website_session_id, pageview_url
),
first_pv AS (
  -- The first pageview of each session = its landing page (used for a balance check).
  SELECT website_session_id, MIN(website_pageview_id) AS pv_id
  FROM website_pageviews
  GROUP BY website_session_id
),
refunds AS (
  -- Refunds are stored per order item, so add them up to one amount per order.
  SELECT order_id, SUM(refund_amount_usd) AS refund_usd
  FROM order_item_refunds
  GROUP BY order_id
)
SELECT bv.website_session_id,
       bv.variant,
       bv.billing_ts,
       s.user_id,
       s.is_repeat_session,
       s.device_type,
       c.channel,
       lp.pageview_url                         AS landing_page,
       o.order_id,
       o.created_at                            AS order_ts,
       CASE WHEN o.order_id IS NOT NULL THEN 1 ELSE 0 END AS ordered,
       COALESCE(o.price_usd, 0)                AS revenue,     -- 0 when the session did not order
       COALESCE(o.cogs_usd, 0)                 AS cogs,
       COALESCE(r.refund_usd, 0)               AS refund_usd
FROM billing_views bv
CROSS JOIN bounds b                                             -- attach the window to every row
JOIN website_sessions s      ON s.website_session_id = bv.website_session_id
JOIN session_channel c       ON c.website_session_id = bv.website_session_id
JOIN first_pv fp             ON fp.website_session_id = bv.website_session_id
JOIN website_pageviews lp    ON lp.website_pageview_id = fp.pv_id
LEFT JOIN orders o           ON o.website_session_id = bv.website_session_id   -- LEFT: keep non-buyers
LEFT JOIN refunds r          ON r.order_id = o.order_id
WHERE bv.billing_ts BETWEEN b.start_ts AND b.end_ts;
