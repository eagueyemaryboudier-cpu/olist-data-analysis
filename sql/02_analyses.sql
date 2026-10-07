-- Chaque bloc est executable independamment sur olist_portfolio.sqlite.
-- Periode principale : achat du 01/01/2017 au 31/08/2018 inclus.

-- Q01 : repartition des statuts sur l'integralite de l'extrait.
SELECT order_status, COUNT(*) AS orders,
       ROUND(100.0*COUNT(*)/SUM(COUNT(*)) OVER (),2) AS share_pct
FROM orders GROUP BY order_status ORDER BY orders DESC;

-- Q02 : chiffres cles, une ligne par commande, GMV hors port.
SELECT COUNT(*) AS delivered_orders, ROUND(SUM(item_value),2) AS gmv_brl,
       ROUND(AVG(item_value),2) AS aov_brl,
       ROUND(AVG(review_score),3) AS mean_review,
       COUNT(is_late) AS logistics_denominator,
       ROUND(100.0*AVG(is_late),2) AS late_pct
FROM fact_orders WHERE analysis_period=1 AND order_status='delivered';

-- Q03 : evolution mensuelle avec LAG et croissance sur le mois precedent.
WITH monthly AS (
    SELECT purchase_month, COUNT(*) AS orders, SUM(item_value) AS gmv
    FROM fact_orders WHERE analysis_period=1 AND order_status='delivered'
    GROUP BY purchase_month
), previous AS (
    SELECT *, LAG(orders) OVER (ORDER BY purchase_month) AS previous_orders
    FROM monthly
)
SELECT purchase_month, orders, ROUND(gmv,2) AS gmv,
       ROUND(100.0*(orders-previous_orders)/NULLIF(previous_orders,0),2) AS mom_pct
FROM previous ORDER BY purchase_month;

-- Q04 : comparaison annuelle sur les memes huit mois.
SELECT STRFTIME('%Y',order_purchase_timestamp) AS year,
       COUNT(*) AS orders, ROUND(SUM(item_value),2) AS gmv,
       ROUND(AVG(item_value),2) AS average_basket
FROM fact_orders
WHERE analysis_period=1 AND order_status='delivered'
  AND CAST(STRFTIME('%m',order_purchase_timestamp) AS INTEGER)<=8
GROUP BY year ORDER BY year;

-- Q05 : categories. Compter les commandes DISTINCTES, sommer les prix des articles.
SELECT category, COUNT(*) AS items, COUNT(DISTINCT order_id) AS orders,
       ROUND(SUM(price),2) AS gmv
FROM fact_items WHERE analysis_period=1 AND order_status='delivered'
GROUP BY category ORDER BY gmv DESC LIMIT 15;

-- Q06 : concentration vendeurs. Arrondir le nombre de vendeurs vers le haut.
WITH seller_gmv AS (
    SELECT seller_id, SUM(price) AS gmv
    FROM fact_items WHERE analysis_period=1 AND order_status='delivered'
    GROUP BY seller_id
), ranked AS (
    SELECT *, ROW_NUMBER() OVER (ORDER BY gmv DESC,seller_id) AS rank,
           COUNT(*) OVER () AS total_sellers, SUM(gmv) OVER () AS total_gmv
    FROM seller_gmv
)
SELECT SUM(CASE WHEN rank <= CAST((total_sellers+4)/5 AS INTEGER) THEN gmv ELSE 0 END)
       / MAX(total_gmv) AS top20_seller_gmv_share
FROM ranked;

-- Q07 : retard et notes avec chronologie des avis et un client par observation.
WITH eligible AS (
    SELECT *, ROW_NUMBER() OVER (
        PARTITION BY customer_unique_id ORDER BY order_purchase_timestamp,order_id
    ) AS rn
    FROM fact_orders
    WHERE analysis_period=1 AND order_status='delivered'
      AND is_late IS NOT NULL AND review_score IS NOT NULL
      AND review_answer_timestamp>=order_delivered_customer_date
)
SELECT is_late, COUNT(*) AS orders, AVG(review_score) AS mean_review,
       AVG(bad_review) AS bad_review_rate
FROM eligible WHERE rn=1 GROUP BY is_late;

-- Q08 : geographie avec seuil de volume explicite (HAVING).
SELECT customer_state, COUNT(*) AS orders, COUNT(is_late) AS valid_dates,
       AVG(delivery_days) AS delivery_days, AVG(is_late) AS late_rate,
       SUM(item_value) AS gmv
FROM fact_orders WHERE analysis_period=1 AND order_status='delivered'
GROUP BY customer_state HAVING COUNT(*)>=500 ORDER BY late_rate DESC;

-- Q09 : vendeurs a investiguer. La note porte sur la commande complete.
WITH seller_orders AS (
    SELECT DISTINCT seller_id,order_id,is_late,review_score
    FROM fact_items WHERE analysis_period=1 AND order_status='delivered'
)
SELECT seller_id, COUNT(*) AS orders, COUNT(is_late) AS valid_dates,
       AVG(is_late) AS late_rate, AVG(review_score) AS mean_review
FROM seller_orders GROUP BY seller_id
HAVING COUNT(is_late)>=100 ORDER BY late_rate DESC LIMIT 20;

-- Q10 : fidelisation, identifiant client persistant et observation egale.
SELECT cohort_month, COUNT(*) AS customers, SUM(repeat_90) AS repeat_customers,
       AVG(repeat_90) AS repeat_rate_90
FROM customer_cohorts WHERE eligible_90=1 GROUP BY cohort_month ORDER BY cohort_month;

-- Q11 : dependance articles / commandes. Une commande multi-articles = une seule commande.
SELECT CASE WHEN item_count=1 THEN '1 article' ELSE 'Plusieurs articles' END AS segment,
       COUNT(*) AS orders, AVG(item_value) AS average_basket
FROM fact_orders WHERE analysis_period=1 AND order_status='delivered' AND item_count IS NOT NULL
GROUP BY segment;

-- Q12 : paiements. Les modes mixtes restent une categorie explicite.
SELECT payment_type, COUNT(*) AS orders, AVG(gross_value) AS basket_with_freight,
       AVG(max_installments) AS max_installments_per_order
FROM fact_orders WHERE analysis_period=1 AND order_status='delivered'
GROUP BY payment_type ORDER BY orders DESC;

-- Q13 : rapprochement financier, tolerance 0,01 BRL.
SELECT COUNT(*) AS comparable_orders,
       SUM(CASE WHEN ABS(payment_gap)>0.010001 THEN 1 ELSE 0 END) AS mismatch_orders,
       SUM(payment_gap) AS signed_gap, SUM(ABS(payment_gap)) AS absolute_gap
FROM fact_orders WHERE analysis_period=1 AND order_status='delivered' AND payment_gap IS NOT NULL;

-- Q14 : sensibilite de la definition du retard.
SELECT COUNT(is_late) AS valid_dates, AVG(is_late) AS calendar_late_rate,
       AVG(is_late_timestamp) AS timestamp_late_rate
FROM fact_orders WHERE analysis_period=1 AND order_status='delivered';

-- Q15 : verification du grain de la vue reconstruite a partir des sources.
SELECT COUNT(*) AS rows, COUNT(DISTINCT order_id) AS unique_orders,
       SUM(item_value) AS total_item_value, SUM(payment_total) AS total_payment
FROM v_order_summary;
