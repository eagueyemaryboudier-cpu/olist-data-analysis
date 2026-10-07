-- SQLite 3.25+. Executer sur portfolio/olist_portfolio.sqlite.
-- Vue pedagogique : chaque table enfant est agregee AVANT les jointures.
-- ROW_NUMBER evite de multiplier les commandes ayant plusieurs avis.
DROP VIEW IF EXISTS v_order_summary;
CREATE VIEW v_order_summary AS
WITH items AS (
    SELECT order_id, COUNT(*) AS item_count,
           COUNT(DISTINCT seller_id) AS seller_count,
           SUM(price) AS item_value, SUM(freight_value) AS freight_value
    FROM order_items GROUP BY order_id
), payments AS (
    SELECT order_id, SUM(payment_value) AS payment_total
    FROM order_payments GROUP BY order_id
), ranked_reviews AS (
    SELECT order_id, review_score,
           ROW_NUMBER() OVER (
               PARTITION BY order_id
               ORDER BY review_answer_timestamp DESC, review_creation_date DESC,
                        review_id DESC, rowid DESC
           ) AS rn
    FROM order_reviews
)
SELECT o.order_id, o.order_status, o.order_purchase_timestamp,
       c.customer_unique_id, c.customer_state,
       i.item_count, i.seller_count, i.item_value, i.freight_value,
       p.payment_total, r.review_score
FROM orders o
LEFT JOIN customers c ON c.customer_id=o.customer_id
LEFT JOIN items i ON i.order_id=o.order_id
LEFT JOIN payments p ON p.order_id=o.order_id
LEFT JOIN ranked_reviews r ON r.order_id=o.order_id AND r.rn=1;
