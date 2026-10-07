# Tableau de bord Olist

Le projet natif est désormais construit : ouvrir **[Olist/Olist.pbip](Olist/Olist.pbip)** en suivant **[OUVRIR_POWER_BI.md](OUVRIR_POWER_BI.md)**. Il contient quatre pages de visuels et le modèle. L'actualisation et le rendu dans Power BI Desktop restent à vérifier. Les sections suivantes sont le guide pédagogique initial de construction manuelle ; le projet livré utilise ses propres 27 mesures dans `Olist/Olist.SemanticModel/model.bim`.

## 1. Importer et typer

Importer `fact_orders.csv`, `fact_items.csv`, `dim_products.csv`, `dim_sellers.csv` et `customer_cohorts.csv` depuis `portfolio/data`. Nommer les tables **FactOrders**, **FactItems**, **DimProducts**, **DimSellers**, **Cohorts**. Le fichier `import_csv.m` fournit une fonction d'import reutilisable.

Desactiver la detection automatique des relations et verifier les types avant le chargement. Les CSV utilisent une virgule comme separateur, un point decimal et UTF-8. Dans Power Query, convertir les nombres avec les parametres regionaux **Anglais (Etats-Unis)**. Conserver les valeurs vides en null, jamais en zero.

| Champs | Type |
|---|---|
| Tous les identifiants, prefixes postaux, Etats, categories | Texte |
| `item_value`, `freight_value`, `gross_value`, `payment_total`, `price` | Nombre decimal fixe pour les montants |
| `delivery_days`, `delay_days`, `distance_km`, `freight_share` | Nombre decimal |
| `item_count`, `seller_count`, `review_score`, `is_late`, `bad_review`, `analysis_period`, `eligible_90`, `repeat_90` | Nombre entier, valeurs nulles conservees |
| `purchase_date` | Date (supprimer l'heure si necessaire) |
| Colonnes temporelles de commandes/avis, `first_purchase` | Date/heure |
| `purchase_month`, `cohort_month` | Texte AAAA-MM, tri chronologique naturel |

Pour FactItems et DimProducts, typer aussi les poids, dimensions et nombres de photos en nombres ; pour FactOrders typer `max_installments` en entier.

## 2. Relations et calendrier

Relations actives, filtre **a sens unique**, de la table du cote 1 vers le cote plusieurs :

```text
DimDate[Date]           1 -> N FactOrders[purchase_date]
FactOrders[order_id]    1 -> N FactItems[order_id]
DimProducts[product_id] 1 -> N FactItems[product_id]
DimSellers[seller_id]   1 -> N FactItems[seller_id]
```

FactOrders a exactement une ligne par commande. FactItems a une ligne par couple commande/article. Ne pas ajouter de relation directe DimDate -> FactItems : la date filtre deja les articles via FactOrders. Ne pas activer de filtre bidirectionnel pour faire remonter les produits vers les commandes.

Creer cette table calculee, puis la marquer comme table de dates sur `[Date]` :

```dax
DimDate =
ADDCOLUMNS(
    CALENDAR(DATE(2016, 9, 1), DATE(2018, 10, 31)),
    "Annee", YEAR([Date]),
    "Mois", FORMAT([Date], "yyyy-MM"),
    "MoisNumero", YEAR([Date]) * 100 + MONTH([Date])
)
```

Trier `Mois` par `MoisNumero`. Cohorts reste deconnectee : utiliser son propre `cohort_month` sur la page fidelisation. Une selection de date d'achat ne doit pas tronquer arbitrairement le suivi de 90 jours.

## 3. Mesures

Creer les mesures de `mesures.dax` une par une (le fichier est un catalogue, pas une expression unique). Selon les parametres regionaux DAX, remplacer les virgules separatrices d'arguments par des points-virgules si demande par l'editeur.

Pour les pages produits/vendeurs, utiliser les mesures fondees sur **FactItems**. Un filtre de DimProducts ne remonte pas vers FactOrders : une carte `[GMV articles livres]` sur cette page ignorerait donc la selection de produit. Utiliser `[GMV articles par produit]`.

## 4. Quatre pages a construire

### Page 1 — Performance commerciale

Filtre fixe : `FactOrders[analysis_period]=1`. Segments : mois d'achat et Etat client. Cartes : commandes livrees, GMV, panier moyen articles et taux d'annulation. Courbes : commandes et GMV par mois, dans deux graphiques pour eviter un double axe. Barres : GMV par Etat. Tableau des statuts avec toutes les commandes de la periode, sans filtre global delivered.

### Page 2 — Livraison et satisfaction

Meme periode. Cartes : taux de retard, delai median, note moyenne, nombre d'avis. Barres : taux de retard par Etat, avec effectifs et seuil de 500 commandes livrees. Afficher la definition du retard : **date de reception posterieure au jour promis**. Pour le visuel retard/avis du rapport, importer aussi `review_delay.csv` comme table de synthese deconnectee : il porte sur une population specifique (avis apres reception, un avis par client). Ce visuel reste fixe ; ne pas faire croire que les segments de FactOrders le filtrent.

### Page 3 — Produits et vendeurs

Segments : DimProducts[category], DimSellers[seller_state]. Cartes et barres uniquement avec les mesures FactItems. Top 10 categories par GMV, vendeurs par GMV, nombre de commandes distinctes par categorie. Les nombres de commandes ne s'additionnent pas entre categories. Pour les notes vendeurs, importer `sellers.csv` comme synthese deconnectee et signaler qu'une note concerne une commande entiere, potentiellement multi-vendeurs.

### Page 4 — Fidelisation

Utiliser exclusivement Cohorts. Segments : `cohort_month`, `customer_state`. Cartes : clients eligibles, clients avec reachat, taux de reachat a 90 jours. Histogramme par cohorte. Filtre `eligible_90=1` : premieres commandes observees avant juin 2018, suivi complet. Ne pas appeler ce taux « churn » ni « retention globale d'Olist ».

## 5. Recette

1. Sans segment, avec periode principale, comparer les cartes a `data/run_metadata.json` et au rapport.
2. GMV = somme des prix des articles de commandes livrees, hors port. Le meme total doit apparaitre sur les pages commandes et articles sans filtre produit.
3. Filtrer une categorie : les mesures articles doivent varier. Retirer la selection et verifier le retour au total.
4. Verifier que les huit livraisons sans date de reception sur l'extrait ne sont pas classees a l'heure.
5. Recalculer les taux par division des totaux ; ne pas moyenner les taux des Etats ou des mois.
6. Verifier les interactions des tables de synthese deconnectees, les unites BRL et jours, puis enregistrer le PBIX.

## Presentation

Format 16:9, fond #FAFBFC, texte #17324D, accent principal #147D92, accent retard #D77748. Quatre cartes maximum en haut de chaque page, titres qui indiquent l'indicateur et sa population. Eviter les jauges, effets 3D et cartes geographiques lorsque les barres comparent mieux les Etats.
