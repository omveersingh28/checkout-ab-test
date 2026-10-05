-- 02_channel_performance.sql
-- Business question (c): which marketing channels have been most successful?
-- Needs the session_channel view from 00_views.sql.

-- name: channel_performance
-- One row per channel for the whole period. Volume (sessions, revenue) shows how BIG a
-- channel is; conversion rate and revenue per session show how GOOD its traffic is.
SELECT c.channel,
       COUNT(*)                                                          AS sessions,
       COUNT(o.order_id)                                                 AS orders,
       ROUND(1.0 * COUNT(o.order_id) / COUNT(*), 4)                      AS conv_rate,
       ROUND(COALESCE(SUM(o.price_usd), 0), 2)                           AS revenue,
       ROUND(1.0 * COALESCE(SUM(o.price_usd), 0) / COUNT(*), 4)          AS revenue_per_session
FROM website_sessions s
JOIN session_channel c ON c.website_session_id = s.website_session_id
LEFT JOIN orders o ON o.website_session_id = s.website_session_id
GROUP BY c.channel
ORDER BY revenue DESC;
