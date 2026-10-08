# Analyse d’avis clients — analyse multilingue des avis clients

**Projet portfolio · Python · NLP local · Visualisation · Qualité des données**

Transformer des fichiers d’avis en une vue exploitable : sentiments, thèmes, cas à relire et exports. Analyse d’avis clients prolonge [l’étude Olist](../README.md) avec un outil interactif réutilisable sur d’autres données.

**Statut : application locale fonctionnelle ; pas de démonstration publique hébergée.** GitHub présente le code et la documentation. L’adresse ci-dessous fonctionne seulement après démarrage sur votre ordinateur.

[Essayer avec un CSV fictif](examples/avis_exemple.csv) · [Contrôles du modèle](MODEL_CHECK.json)


Ouvrir http://127.0.0.1:8765 lorsque le serveur est lancé. Charger Olist ou un fichier, vérifier les colonnes, choisir **Modèle multilingue local**, puis lancer. Un aperçu de 500 ou 2 000 avis permet un essai rapide ; les résultats partiels sont explicitement signalés.

## Installation et démarrage

Depuis la racine du dépôt, créer un environnement **Python 3.12 séparé** de celui de l’étude statistique (Python 3.10). Sous Linux/WSL :

```sh
python -m pip install -r requirements.txt
python download_model.py
python server.py
```

Sous Windows, créer l’environnement avec `py -3.12 -m venv .venv`, puis l’activer avec `.venv\Scripts\Activate.ps1` avant les commandes d’installation. Ctrl+C arrête le serveur. Le modèle (~297 Mo) est téléchargé une fois dans `models/sentiment/`, exclu de Git.

Importer `examples/avis_exemple.csv` pour essayer les fonctions : ces avis sont fictifs et ne proviennent pas d’Olist. Pour les données réelles, télécharger le [dataset Olist sur Kaggle](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce), puis importer `olist_order_reviews_dataset.csv` depuis l’interface. Le bouton « Charger les avis Olist » cherche ce fichier dans le dossier parent de `avis-tri/` ; l’import manuel fonctionne quel que soit son emplacement.

## Améliorations

| Ancienne version | Version 2 |
|---|---|
| Sentiment par quelques mots-clés | Modèle multilingue contextuel local, avec moteur léger en option |
| Texte non latin confondu avec texte vide | Unicode conservé |
| Analyse des avis longs | Tous les segments de 256 tokens sont analysés, aucune troncature silencieuse |
| Résultat sans indication de doute | Scores, abstention et filtre de relecture |
| Aucune correction | Correction manuelle, sentiment initial conservé dans les exports |
| Thèmes figés | Noms, mots et expressions personnalisables |
| Première feuille Excel uniquement | Choix de feuille XLS/XLSX/XLSM, dates en ISO |
| Import CSV automatique uniquement | Choix du séparateur, encodage et présence d’en-têtes |
| TXT délimité uniquement | Un avis par ligne ou paragraphe, ou tableau |
| JSON plat | JSON et JSONL/NDJSON, enveloppes reviews/avis/data/records ; objets imbriqués conservés en JSON |
| Pas de documents | DOCX et PDF texte, segmentation à vérifier |
| 30 Mo / 100 000 lignes | 100 Mo / 500 000 lignes / 500 colonnes, selon la mémoire disponible |
| Requête unique volumineuse | Lots de 64 avis, progression et arrêt après le lot courant |
| Note et texte séparés | Filtre de contradictions après choix explicite de l’échelle 1–5 ou 0–10 |

Les doublons sont repérés sur tous les avis analysés, y compris entre lots (normalisation de casse, accents et espaces). Aucun avis n’est supprimé automatiquement.

Les deux graphiques utilisent une échelle fixe de 0 à 100 % des avis sélectionnés, y compris les avis sans texte. Chaque barre affiche son effectif et sa part dans cette base. Les catégories de sentiment totalisent 100 % avant arrondi. Les thèmes peuvent se chevaucher et certains avis n’ont aucun thème détecté : leurs pourcentages ne totalisent donc pas nécessairement 100 %.

## Modèle et interprétation

Source : [Cardiff NLP — XLM-T](https://huggingface.co/cardiffnlp/twitter-xlm-roberta-base-sentiment), adapté au sentiment dans huit langues dont français, portugais et anglais, à partir de tweets. Un décalage avec les avis marchands est possible. Poids locaux : [conversion ONNX Community](https://huggingface.co/onnx-community/twitter-xlm-roberta-base-sentiment-ONNX), quantification int8. Aucun code du dépôt du modèle n’est exécuté. La révision téléchargée et les empreintes SHA-256 sont dans `models/sentiment/manifest.json`.

Classes du modèle : positif, négatif, neutre. Résultat **Indéterminé** si le meilleur score est inférieur à 0,60 ou si son écart avec le deuxième est inférieur à 0,15. Seuils choisis pour la prudence, non calibrés sur Olist ; les scores ne garantissent pas la justesse.

Les segments longs sont agrégés en pondérant leurs scores par le nombre de tokens. Des segments positifs et négatifs suffisamment nets (score ≥ 0,60 et marge ≥ 0,15) donnent **Mixte**, à vérifier. Tous les sentiments mixtes dans une phrase courte ne sont pas détectés. La note ne détermine jamais le sentiment.

Les thèmes restent des règles par mots et expressions, désormais modifiables ; ils ne sont pas produits par un modèle sémantique. Adapter les mots au domaine et aux langues du fichier.

## Limites restantes

- Ironie, fautes, langues moins couvertes et ambiguïtés peuvent encore produire des erreurs. La relecture reste utile.
- PDF scannés : OCR préalable nécessaire, pages sans texte signalées. PDF complexes et DOCX : vérifier qu’un paragraphe correspond bien à un avis. Pas d’import d’un format arbitraire, de DOC binaire ou d’images.
- Formules Excel : uniquement les résultats enregistrés dans le classeur, sans calcul ni macro. Une formule sans résultat en cache donne une cellule vide ; recalculer et enregistrer dans Excel si nécessaire.
- Le modèle peut prendre plusieurs minutes ou davantage pour des dizaines de milliers de commentaires sur CPU. Les aperçus sont les premières lignes, pas un échantillon représentatif.
- Commentaire de plus de 100 000 caractères : refus explicite, segmenter le document en avis. Archives décompressées limitées à 300 Mo.
- Corrections en mémoire : exporter avant de fermer, réimporter ou relancer. Une correction ne réentraîne pas le modèle.
- Contradiction note/sentiment : signal de relecture, pas preuve d’une erreur du client.

## Exports et confidentialité

CSV UTF-8 BOM avec point-virgule, ou JSON. Colonnes sources conservées, avec sentiment initial/corrigé, score, relecture, thèmes, méthode et nombres d’avis importés/analysés. Les cellules CSV pouvant être interprétées comme des formules sont neutralisées ; le JSON conserve le texte exact. Chaque export demandé est enregistré dans le dossier local `exports/` puis proposé au téléchargement par un lien HTTP. La copie reste disponible même si le navigateur intégré ne déclenche pas le téléchargement ; elle n’est pas supprimée automatiquement. Ce dossier est exclu de Git.

Traitement en mémoire, aucune requête d’analyse vers un service extérieur. Cache limité à 50 000 textes pour éviter des calculs répétés, effacé à l’arrêt du serveur. Le serveur écoute uniquement sur l’interface locale ; ne pas l’exposer sur Internet.

## Vérification

```sh
python -m unittest -v test_app.py test_importers.py
node test_ui.cjs
python evaluate_model.py
# Avec le serveur lancé :
python -m unittest -v test_http.py
```

`MODEL_CHECK.json` : 24 exemples construits (8 français, 8 portugais, 8 anglais), 23 classements attendus et une abstention lors de la vérification initiale. Ce contrôle n’est pas un benchmark indépendant et ne permet pas de revendiquer une précision en production.
