# Olist — Analyse e-commerce

**Python · SQL · Power BI | Portfolio Data Analyst**

Comment accompagner la croissance d'une marketplace tout en améliorant les livraisons et l'expérience client ? Cette étude explore **26 hypothèses** à partir de neuf tables Olist et transforme les résultats en recommandations mesurables.

![Ventes livrées par mois et GMV](figures/01_ventes.png)

## Résultats essentiels

| Indicateur | Résultat et périmètre |
|---|---|
| Commandes livrées | **96 211**, achats de janvier 2017 à août 2018 |
| GMV articles | **13,18 M BRL**, commandes livrées, hors frais de port |
| Croissance du volume | **+139,9 %**, janvier–août 2018 contre les mêmes mois de 2017 |
| Concentration vendeurs | **82,2 % du GMV** réalisés par les 20 % de vendeurs les plus importants |
| Retard de livraison | **6,79 %** parmi les commandes livrées aux dates valides |
| Réachat à 90 jours | **2,01 %**, soit 1 514 clients sur 75 387 avec suivi complet |

**Un résultat méthodologique important :** les avis rédigés avant réception modifient fortement la lecture du lien entre retard et satisfaction. L'étude compare plusieurs populations et distingue association et causalité.

## Explorer le projet

- **[Étude de cas complète](ETUDE_DE_CAS.md)** — contexte métier, hypothèses, résultats, limites et recommandations.
- **[Notebook exécuté avec huit graphiques intégrés](notebooks/01_etude_olist.ipynb)** — code Python et SQL, contrôles et interprétations.
- **[15 analyses SQL](sql/02_analyses.sql)** et **[modèle SQL](sql/01_modele.sql)** — CTE, jointures, agrégations et fonctions de fenêtre.
- **[Projet Power BI natif](powerbi/Olist/Olist.pbip)** — quatre pages, graphiques, indicateurs et filtres ; [instructions d'ouverture](powerbi/OUVRIR_POWER_BI.md).
- **[Registre des 26 hypothèses](data/hypotheses.csv)** et **[dictionnaire des données](DICTIONNAIRE.md)**.
- **[Rapport HTML](ETUDE_DE_CAS.html)** — télécharger le dépôt et ouvrir ce fichier dans un navigateur pour une lecture illustrée.

## Méthode et compétences

1. **Contrôler les sources** : clés uniques, références, valeurs manquantes, chronologies et rapprochement des paiements.
2. **Modéliser au bon grain** : agréger séparément les articles, paiements et avis avant de joindre les commandes.
3. **Analyser** : ventes à période comparable, concentration produits/vendeurs, géographie, livraison, satisfaction et cohortes à 90 jours.
4. **Tester les hypothèses** : Welch, Spearman, Kruskal–Wallis, intervalles et correction Benjamini–Hochberg des tests multiples.
5. **Restituer** : graphiques, modèle Power BI et actions proposées avec indicateurs de suivi.

![Satisfaction selon le retard](figures/02_retards_avis.png)

## État des livrables

| Livrable | Validation |
|---|---|
| Analyse Python et SQL | Exécutée ; rapprochements commande par commande vérifiés |
| Notebook | 14 cellules de code exécutées, huit graphiques embarqués |
| Rapport | Résultats et limites documentés, six graphiques |
| Power BI | Projet PBIP/PBIR construit, sept tables, 27 mesures ; structure validée |

**Power BI :** l'actualisation, l'évaluation DAX et le rendu dans Desktop restent à vérifier avant enregistrement en PBIX. Le dépôt ne prétend pas contenir un PBIX validé.

## Reproduire l'analyse

Prérequis : **Python 3.10**. Depuis la racine du dépôt, sous Linux/WSL :

```bash
python3.10 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Télécharger les [données Olist sur Kaggle](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce) et placer les **neuf CSV** dans `data/raw/`, avec leurs noms d'origine. Les données brutes et les tables détaillées ne sont pas versionnées.

```bash
python scripts/run_analysis.py
python scripts/build_deliverables.py
```

Si les CSV sont déjà ailleurs, définir `OLIST_RAW_DIR` avec le chemin de ce dossier. Le premier script reconstruit les résultats et SQLite. Le second exécute les requêtes et le notebook et génère les rapports. Les sorties générées sont remplacées lors d'un recalcul.

Pour reconstruire les CSV et le projet Power BI :

```bash
python scripts/fetch_powerbi_schemas.py
python scripts/build_powerbi.py
```

Ouvrir ensuite le PBIP dans **Power BI Desktop sous Windows**, vérifier le paramètre `DataFolder`, puis actualiser. Sur une autre machine, adapter ce chemin au dossier `powerbi/Olist/Data/`. Les définitions Power BI sont contrôlées contre les schémas publics Microsoft ; cela ne remplace pas une validation dans Desktop.

Le notebook peut être lu sur GitHub sans installer Jupyter. Pour l'exécuter interactivement, utiliser un environnement Jupyter relié au même Python.

## Structure

```text
notebooks/       Notebook exécuté avec visualisations
scripts/         Pipeline Python et génération des livrables
sql/             Modèle et requêtes SQLite
figures/         Graphiques de l'étude
data/            Résultats agrégés et contrôles ; sources dans raw/ (exclues)
powerbi/         Projet PBIP/PBIR, modèle sémantique et documentation
ETUDE_DE_CAS.md   Restitution métier
```

## Limites

- Extrait historique : il ne décrit pas la performance actuelle ni toute l'activité d'Olist.
- Le GMV n'est ni le revenu net ni la marge. Coûts, acquisition, sessions et retours détaillés sont absents.
- Les tests sont exploratoires ; les variables de confusion et les biais de sélection restent discutés.
- Le réachat est observé dans cet extrait seulement ; il ne mesure pas le churn global.
- Les recommandations sont proposées comme des expérimentations. Aucun gain causal n'est revendiqué.

## Source

[Brazilian E-Commerce Public Dataset by Olist — Kaggle](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce). Attribution à Olist et aux contributeurs du dataset. Les conditions de réutilisation des données sont celles de la source. Les empreintes SHA-256 et effectifs des fichiers analysés sont dans [source_manifest.csv](data/source_manifest.csv).
