-- 00_views.sql
-- Purpose: give every session ONE marketing channel, so later queries can simply join to it.
--
-- How the rules work (checked top to bottom, the first match wins):
--   no utm_source and no referer   -> the visitor typed the URL            = direct
--   no utm_source but a referer    -> came from a search engine, unpaid    = organic_search
--   utm_campaign = 'brand'         -> paid ad on our own brand name        = paid_brand
--   utm_source = 'socialbook'      -> paid ad on the social network        = paid_social
--   everything else                -> paid search on generic keywords      = paid_nonbrand
-- Blank utm fields are normal in this data (they mean the traffic was not paid).

DROP VIEW IF EXISTS session_channel;

CREATE VIEW session_channel AS
SELECT website_session_id,
       CASE
         WHEN utm_source IS NULL AND http_referer IS NULL THEN 'direct'
         WHEN utm_source IS NULL                           THEN 'organic_search'
         WHEN utm_campaign = 'brand'                       THEN 'paid_brand'
         WHEN utm_source = 'socialbook'                    THEN 'paid_social'
         ELSE 'paid_nonbrand'
       END AS channel
FROM website_sessions;

-- Quick check: sessions per channel (must add up to 472,871).
SELECT channel, COUNT(*) AS sessions
FROM session_channel
GROUP BY channel
ORDER BY channel;
