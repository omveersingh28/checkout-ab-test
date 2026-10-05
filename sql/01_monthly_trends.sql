-- 01_monthly_trends.sql
-- Business questions (a), (b) and (d): how did traffic, orders, conversion and revenue
-- change month by month?

-- name: monthly_trends
-- One row per month. LEFT JOIN keeps the sessions that did NOT order, which is what makes
-- COUNT(*) = all sessions and COUNT(o.order_id) = only the sessions with an order.
-- Note: the first month (2012-03) and the last month (2015-03) are partial months.
SELECT strftime('%Y-%m', s.created_at)                                   AS month,
       COUNT(*)                                                          AS sessions,
       COUNT(o.order_id)                                                 AS orders,
       ROUND(1.0 * COUNT(o.order_id) / COUNT(*), 4)                      AS conv_rate,
       ROUND(COALESCE(SUM(o.price_usd), 0), 2)                           AS revenue,
       ROUND(1.0 * SUM(o.price_usd) / COUNT(o.order_id), 2)              AS revenue_per_order,
       ROUND(1.0 * COALESCE(SUM(o.price_usd), 0) / COUNT(*), 4)          AS revenue_per_session
FROM website_sessions s
LEFT JOIN orders o ON o.website_session_id = s.website_session_id
GROUP BY 1
ORDER BY 1;

-- name: page_change_dates
-- When was each landing page and each billing page first and last seen?
-- These dates are drawn as vertical lines on the conversion chart, because a change in
-- conversion often lines up with a page change.
SELECT pageview_url,
       MIN(created_at) AS first_seen,
       MAX(created_at) AS last_seen,
       COUNT(*)        AS pageviews
FROM website_pageviews
WHERE pageview_url LIKE '/lander-%'
   OR pageview_url IN ('/billing', '/billing-2')
GROUP BY pageview_url
ORDER BY first_seen;

-- name: product_launches
-- Launch date of each product. New products change revenue per order (different prices,
-- and customers can buy more than one item), so they are marked on the revenue chart.
SELECT product_id, product_name, created_at AS launched_at
FROM products
ORDER BY product_id;
