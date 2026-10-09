# Démonstration publique — Analyse d’avis clients

Site statique publié avec GitHub Pages depuis `main` → `/docs`. Aucun service d’inférence n’est appelé par le navigateur.

Les 36 commentaires sont **fictifs**, rédigés pour présenter les fonctions. Le sentiment a été calculé une fois avec le modèle ONNX local ; `data.json` indique le modèle, sa révision et la date de génération. Les thèmes reposent sur les règles de l’application Python. Ces données ne constituent ni des avis Olist ni un benchmark du modèle.

Fonctions : filtres langue, sentiment, thème, note et recherche ; tri ; pagination ; graphiques de 0 à 100 % de la sélection ; exports CSV/JSON dans le navigateur. Aucune saisie libre pour lancer une nouvelle inférence, aucun téléversement de fichier et aucune persistance des visiteurs.

Les personnes souhaitant analyser leurs propres fichiers peuvent installer [la version Python](../avis-tri/README.md).

Prévisualiser depuis la racine : `python -m http.server 8766 --directory docs`, puis ouvrir http://localhost:8766.

Régénérer les exemples, avec la version Python et son modèle lancés sur le port 8765 : `python avis-tri/build_web_demo.py`.

Tests : depuis `avis-tri`, exécuter `node test_web_demo.cjs`.
