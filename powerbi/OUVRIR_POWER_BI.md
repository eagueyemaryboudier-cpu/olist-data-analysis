# Ouvrir le rapport Olist

Le rapport est construit au format natif **Power BI Project (PBIP/PBIR)** :

**[Olist/Olist.pbip](Olist/Olist.pbip)**

Il contient **4 pages, 14 graphiques, 16 cartes d'indicateurs, 9 segments de filtre et 2 tableaux**, ainsi que les titres et notes méthodologiques. Les visuels sont reliés à un modèle de 7 tables et 27 mesures DAX.

## Après avoir cloné le dépôt

Les CSV détaillés ne sont pas versionnés. Exécuter les scripts de reproduction du README, y compris `build_powerbi.py`, pour les reconstruire. Le paramètre `DataFolder` du modèle versionné contient volontairement `CHANGE_ME` : le générateur le remplace par le chemin local.

1. Installer ou ouvrir une version récente de **Power BI Desktop**.
2. Ouvrir `Olist.pbip`. Si le sélecteur ne propose pas les projets, ouvrir `Olist.Report/definition.pbir`.
3. Cliquer **Actualiser** : après reconstruction, le projet contient les définitions et les CSV, mais pas de cache de données Power BI préchargé.
4. Vérifier les quatre pages et les interactions de filtres.
5. Choisir **Fichier > Enregistrer sous > Power BI (.pbix)** pour obtenir un fichier PBIX contenant les données.

Le projet est local. Il n'a pas besoin d'être publié dans Power BI Service pour être utilisé dans Desktop.

## Les pages

| Page | Contenu |
|---|---|
| Performance | Commandes livrées, GMV, panier moyen, annulations, tendances mensuelles, États et statuts |
| Livraison et avis | Retards, délai médian, note moyenne, avis négatifs, notes après réception, distribution des notes |
| Produits et vendeurs | GMV, articles, commandes distinctes, vendeurs actifs, top catégories, top vendeurs, tableau détaillé |
| Fidélisation | Clients éligibles, réachat à 90 jours, panier initial, tendances par cohorte et par État |

Les filtres sont propres à chaque page. La page fidélisation utilise les cohortes avec un suivi complet ; elle n'est pas tronquée par un filtre sur les dates des commandes. Les mesures commerciales appliquent la période janvier 2017–août 2018. Le visuel des notes après réception utilise une population plus restreinte, explicitée dans son titre et dans l'étude.

## Si le dossier est déplacé

Dans **Transformer les données > Gérer les paramètres**, modifier **DataFolder** pour qu'il pointe vers le dossier `Olist/Data/` du projet, avec un séparateur final `/`. Exemple : `D:/Portfolio/Olist/Data/`.

Le paramètre est aussi visible dans `Olist.SemanticModel/model.bim`. Conserver ensemble le fichier PBIP et les dossiers Report, SemanticModel et Data.

## Contrôles attendus après actualisation

Sans sélection de filtre :

- Commandes livrées : **96 211**.
- GMV articles : **13 181 027,13 BRL**.
- Taux de retard : **6,79 %** (arrondi visuel possible à 6,8 %).
- Clients éligibles au réachat : **75 387**.
- Clients avec réachat à 90 jours : **1 514** ; taux **2,01 %**.

Sélectionner ensuite une catégorie sur la page Produits : ses cartes, courbe et classements doivent varier ensemble. Sur Fidélisation, sélectionner une cohorte et vérifier que le taux est le quotient des deux effectifs affichés.

## État de validation

Les 63 fichiers de définition concernés ont passé les schémas JSON officiels Microsoft. Les références des graphiques et les clés des relations ont été contrôlées. Les données sont issues du pipeline Python/SQL vérifié.

**L'ouverture, l'actualisation des données, l'évaluation DAX et le rendu dans Power BI Desktop restent à vérifier.** Aucun fichier PBIX ni aperçu prétendument issu de Power BI Desktop n'est fourni tant que cette vérification n'a pas été réalisée. Voir `validation_powerbi.json`.

## Références du format

- [Projet de rapport Power BI et format PBIR — Microsoft](https://learn.microsoft.com/en-us/power-bi/developer/projects/projects-report)
- [Modèle sémantique Power BI — Microsoft](https://learn.microsoft.com/en-us/power-bi/developer/projects/projects-dataset)

Les mesures exactes du projet sont dans `Olist/Olist.SemanticModel/model.bim`. Le guide historique `GUIDE_POWER_BI.md` explique les principes du modèle, mais la reconstruction manuelle des pages n'est plus nécessaire.
