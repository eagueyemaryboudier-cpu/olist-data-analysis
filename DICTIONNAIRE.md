# Dictionnaire et contrat des données

Les CSV source conservent leurs noms et colonnes d'origine, y compris les suffixes historiques `lenght`. Le profil exhaustif de chaque colonne source (effectif, manquants, valeurs distinctes) se trouve dans `data/quality_columns.csv`.

## Tables

| Table | Grain | Clé / jointure |
|---|---|---|
| orders | Une commande | order_id |
| order_items | Une ligne d'article commandée | (order_id, order_item_id) |
| order_payments | Une séquence de paiement d'une commande | (order_id, payment_sequential) |
| order_reviews | Un enregistrement d'avis | Ni order_id ni review_id ne sont uniques seuls |
| customers | Un identifiant client rattaché à une commande | customer_id ; customer_unique_id relie les achats d'un client |
| products | Un produit | product_id |
| sellers | Un vendeur | seller_id |
| geolocation | Une observation géographique par préfixe postal | Préfixe non unique ; médiane avant jointure |
| product_category_name_translation | Une traduction de catégorie | product_category_name |
| fact_orders | Une commande enrichie | order_id unique |
| fact_items | Une ligne d'article enrichie | (order_id, order_item_id) |
| customer_cohorts | Un client ayant une commande livrée dans l'horizon | customer_unique_id unique |

## Principaux champs de fact_orders

| Champ | Définition / unité |
|---|---|
| order_id | Identifiant texte de la commande |
| customer_id | Identifiant client dans la table customers pour cette commande |
| customer_unique_id | Identifiant texte persistant utilisé pour le réachat |
| order_status | Statut final observé dans l'extrait |
| order_purchase_timestamp | Date et heure de l'achat |
| order_approved_at | Date et heure d'approbation |
| order_delivered_carrier_date | Date et heure de remise au transporteur |
| order_delivered_customer_date | Date et heure de réception client |
| order_estimated_delivery_date | Date de livraison promise |
| purchase_date / purchase_month | Jour normalisé / mois AAAA-MM de l'achat |
| analysis_period | 1 pour un achat entre le 01/01/2017 et le 31/08/2018 inclus, 0 sinon |
| customer_state / customer_city | État / ville du client |
| customer_zip_code_prefix | Préfixe postal client, texte conservant les zéros initiaux |
| item_count | Nombre de lignes dans order_items ; manquant si aucun article |
| seller_count | Nombre de vendeurs distincts dans la commande |
| item_value | Somme de price, en BRL, hors port |
| freight_value | Somme des frais de port des lignes, en BRL |
| gross_value | item_value + freight_value, en BRL |
| freight_share | freight_value / gross_value ; nul/missing si dénominateur non positif |
| payment_total | Somme des payment_value, en BRL |
| payment_gap | payment_total - gross_value, en BRL |
| payment_rows / payment_types | Nombre de lignes de paiement / modes distincts |
| payment_type | Mode unique, sinon mixed ; manquant si aucun paiement |
| max_installments | Maximum d'échéances parmi les lignes de paiement ; ce n'est pas leur somme |
| review_score | Note du dernier avis sélectionné, 1 à 5 ; manquante si aucun |
| review_answer_timestamp | Horodatage de réponse de l'avis sélectionné |
| has_comment | 1 si le message de l'avis sélectionné n'est pas vide, 0 sinon ; manquant sans avis |
| bad_review | 1 pour notes 1–2, 0 pour notes 3–5 ; manquant sans avis |
| delivery_days | (Réception - achat) en jours fractionnaires, livrées et durée non négative |
| delay_days | Jour réception - jour promis, positif si retard, négatif si avance ; livrées et dates valides |
| is_late | 1 si delay_days > 0, 0 sinon ; manquant si non évaluable |
| is_late_timestamp | Sensibilité : comparaison des horodatages bruts plutôt que des jours |
| promise_days | Date promise moins jour d'achat, en jours |
| handoff_days | Remise transporteur - approbation, jours fractionnaires, livrées et durée non négative |
| transit_days | Réception - remise transporteur, jours fractionnaires, livrées et durée non négative |
| same_state | Vendeur et client dans le même État ; uniquement commandes mono-vendeur |
| distance_km | Distance à vol d'oiseau entre médianes de préfixes postaux ; mono-vendeur |

## Champs propres aux articles et produits

`price` et `freight_value` désignent le montant de la **ligne**, contrairement aux agrégats de fact_orders. `category` est la catégorie traduite si disponible, sinon la catégorie portugaise, sinon `unknown`. Les poids sont en grammes et les dimensions en centimètres selon les noms des colonnes. `product_photos_qty` compte les photos observées dans le fichier produit.

Les champs de commande répétés dans fact_items servent au filtrage. **Ne pas sommer des montants de commande répétés**, ni moyenner les notes d'articles pour prétendre obtenir une moyenne par commande. Dédupliquer au grain voulu ou utiliser fact_orders.

## Cohortes

- `first_purchase` : date du premier achat finalement livré observé pour ce client jusqu'au 31/08/2018 ; ne prouve pas qu'il s'agit de sa première commande réelle.
- `first_order_id` : identifiant correspondant ; tri par date puis order_id en cas d'égalité.
- `eligible_90` : premier achat avant juin 2018, pour garder des cohortes mensuelles entières avec au moins 90 jours de suivi.
- `repeat_90` : autre achat finalement livré, strictement après le premier achat et dans les 90 jours suivants.
- `eligible_postdelivery_90` : réception initiale suffisamment ancienne pour observer 90 jours complets après cette réception.
- `repeat_after_delivery_90` : autre achat finalement livré passé strictement après la réception initiale et au plus 90 jours après ; utilisé pour H24.
- `cohort_month` : mois du premier achat observé.

## Statistiques

Dans hypotheses.csv, `effect` vaut une différence de moyennes (premier groupe moins second), un rho de Spearman, ou la statistique H pour Kruskal–Wallis. L'unité est indiquée par `population` et `methode`. Pour H24, il s'agit d'une différence de proportions ; multiplier par 100 pour des points de pourcentage. `ci_low` et `ci_high` sont les IC marginaux à 95 % des différences de moyennes. `p_value` est brute ; `q_bh` est corrigée sur les 16 tests inférentiels. Les cellules non applicables restent vides.
