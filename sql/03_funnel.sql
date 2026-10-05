-- 03_funnel.sql
-- Context for the A/B test: how many sessions reach each step of the purchase funnel?
-- The billing page is the last step before an order, which is where the test sits.

-- name: funnel
-- Each line counts the sessions that viewed that page at least once (COUNT DISTINCT,
-- because a session can load the same page twice). UNION ALL stacks the steps into one table.
SELECT 'sessions'      AS step, COUNT(DISTINCT website_session_id) AS sessions FROM website_pageviews
UNION ALL SELECT 'products', COUNT(DISTINCT website_session_id) FROM website_pageviews WHERE pageview_url = '/products'
UNION ALL SELECT 'product_page', COUNT(DISTINCT website_session_id) FROM website_pageviews WHERE pageview_url LIKE '/the-%'
UNION ALL SELECT 'cart', COUNT(DISTINCT website_session_id) FROM website_pageviews WHERE pageview_url = '/cart'
UNION ALL SELECT 'shipping', COUNT(DISTINCT website_session_id) FROM website_pageviews WHERE pageview_url = '/shipping'
UNION ALL SELECT 'billing', COUNT(DISTINCT website_session_id) FROM website_pageviews WHERE pageview_url IN ('/billing', '/billing-2')
UNION ALL SELECT 'order', COUNT(*) FROM orders;
