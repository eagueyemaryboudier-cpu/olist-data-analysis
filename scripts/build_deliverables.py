"""Construit le rapport et le notebook, execute et verifie les requetes SQL."""
from pathlib import Path
import base64
import contextlib
import html
import io
import json
import re
import sqlite3
import sys

import numpy as np
import pandas as pd

OUT = Path(__file__).resolve().parents[1]
DATA = OUT / "data"


def read(name):
    return pd.read_csv(DATA / f"{name}.csv")


def fmt(x, decimals=1):
    return f"{x:,.{decimals}f}".replace(",", " ").replace(".", ",")


def pct(x):
    return fmt(x*100) + " %"


def md_table(df):
    def clean(v):
        if isinstance(v, float):
            return fmt(v,3) if np.isfinite(v) else "—"
        return str(v).replace("|", "/").replace("\n", " ")
    rows=["| " + " | ".join(df.columns) + " |", "| " + " | ".join(["---"]*len(df.columns)) + " |"]
    rows += ["| " + " | ".join(clean(v) for v in row) + " |" for row in df.itertuples(index=False,name=None)]
    return "\n".join(rows)


def check_sql():
    conn=sqlite3.connect(OUT/"olist_portfolio.sqlite")
    conn.executescript((OUT/"sql/01_modele.sql").read_text(encoding="utf-8"))
    sql=(OUT/"sql/02_analyses.sql").read_text(encoding="utf-8")
    blocks=re.split(r"(?=-- Q\d{2} :)",sql)[1:]
    checks=[]
    for block in blocks:
        name=re.match(r"-- (Q\d+)",block).group(1)
        query="\n".join(line for line in block.splitlines() if not line.lstrip().startswith("--"))
        result=pd.read_sql_query(query,conn)
        result.to_csv(DATA/f"sql_{name}.csv",index=False,encoding="utf-8-sig")
        checks.append({"query":name,"result_rows":len(result),"execution":"OK"})
    py=pd.read_sql_query("SELECT order_id,item_value,payment_total,review_score FROM fact_orders ORDER BY order_id",conn)
    sqlmodel=pd.read_sql_query("SELECT order_id,item_value,payment_total,review_score FROM v_order_summary ORDER BY order_id",conn)
    assert py.order_id.equals(sqlmodel.order_id)
    for field in ["item_value","payment_total","review_score"]:
        assert np.allclose(py[field],sqlmodel[field],equal_nan=True),field
    conn.close()
    pd.DataFrame(checks).to_csv(DATA/"sql_validation.csv",index=False)
    return len(checks)


def notebook():
    cells=[]
    def md(s):
        cells.append({"cell_type":"markdown","metadata":{},"source":s.splitlines(keepends=True)})
    def code(s):
        cells.append({"cell_type":"code","metadata":{},"source":s.splitlines(keepends=True),"execution_count":None,"outputs":[]})
    md("# Olist — ventes, livraison et satisfaction\n\nEtude exploratoire reproductible pour un portfolio Data Analyst. Les résultats sont calculés sur les fichiers locaux.\n\nExécuter d'abord `python scripts/run_analysis.py` depuis `portfolio`, puis ouvrir ce notebook. Il présente la lecture des sources, les contrôles, SQL, Python et l'interprétation. Les 26 hypothèses détaillées figurent dans le rapport et `data/hypotheses.csv`.\n\nSource : [Olist sur Kaggle](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce). Les résultats décrivent cet extrait historique, sans causalité démontrée.")
    code("from pathlib import Path\nimport sqlite3\nimport pandas as pd\nimport numpy as np\nfrom scipy import stats\n\n# Trouver le projet depuis le dossier portfolio ou notebooks.\nBASE = next(p for p in [Path.cwd(), *Path.cwd().parents] if (p / 'data/run_metadata.json').exists())\nimport os\nROOT = Path(os.environ.get('OLIST_RAW_DIR', str(BASE / 'data/raw')))\nconn = sqlite3.connect(BASE / 'olist_portfolio.sqlite')\norders = pd.read_csv(ROOT / 'olist_orders_dataset.csv', dtype=str)\nitems = pd.read_csv(ROOT / 'olist_order_items_dataset.csv')\nprint('Commandes :', len(orders), '| Articles :', len(items))\nprint(orders[['order_id', 'order_status']].head().to_string(index=False))")
    md("## 1. Le grain des données\n\nUne commande peut avoir plusieurs articles, paiements et avis. Joindre les trois tables enfants directement multiplie les lignes. On agrège séparément avant la jointure. `customer_unique_id` est utilisé pour suivre un client entre commandes.")
    code("assert orders.order_id.is_unique\nassert not items.duplicated(['order_id', 'order_item_id']).any()\nprint('Clés des commandes et des articles : valides')\nquality = pd.read_csv(BASE / 'data/quality_checks.csv')\nprint(quality[quality.valeur > 0].to_string(index=False))")
    md("## 2. Une première analyse en SQL\n\nGMV = somme des prix des articles de commandes livrées, hors port. Ce n'est ni le revenu net d'Olist ni une marge. Période d'achat principale : janvier 2017 à août 2018. Les dates et statuts finaux proviennent de l'extrait disponible.")
    code('query = """\nSELECT purchase_month, COUNT(*) AS orders,\n       ROUND(SUM(item_value),2) AS gmv_brl,\n       ROUND(AVG(item_value),2) AS basket_brl\nFROM fact_orders\nWHERE analysis_period=1 AND order_status=\'delivered\'\nGROUP BY purchase_month ORDER BY purchase_month;\n"""\nmonthly = pd.read_sql_query(query, conn)\nprint(monthly.to_string(index=False))')
    md("![Evolution mensuelle](../figures/01_ventes.png)\n\nComparer janvier–août d'une année à janvier–août de l'autre évite de comparer huit mois à douze mois. Une seule année complète ne suffit pas à établir une saisonnalité stable.")
    md("## 3. Jointures contrôlées\n\nLa vue SQL est reconstruite depuis les sources avec des CTE et `ROW_NUMBER`. Le dernier avis est choisi selon la date de réponse, puis création, identifiant et ordre source en cas d'égalité.")
    code("conn.executescript((BASE / 'sql/01_modele.sql').read_text(encoding='utf-8'))\nrecon = pd.read_sql_query('SELECT COUNT(*) AS rows, COUNT(DISTINCT order_id) AS unique_orders, SUM(item_value) AS gmv FROM v_order_summary', conn)\nassert recon.loc[0, 'rows'] == recon.loc[0, 'unique_orders'] == len(orders)\nassert np.isclose(recon.loc[0, 'gmv'], items.price.sum())\nprint(recon.to_string(index=False))")
    md("## 4. Tester l'association retard–satisfaction\n\nRetard = réception un jour calendaire après la date promise ou plus. Un avis rédigé avant la réception ne peut pas évaluer une livraison terminée. Le test principal utilise les avis postérieurs à la réception et la première commande admissible par client. Cette sélection crée aussi un biais : la sensibilité à ce choix est présentée ensuite.")
    code("f = pd.read_csv(BASE / 'data/fact_orders.csv', parse_dates=['order_purchase_timestamp', 'order_delivered_customer_date', 'review_answer_timestamp'])\nrated = f[(f.analysis_period == 1) & (f.order_status == 'delivered') & f.is_late.notna() & f.review_score.notna() & (f.review_answer_timestamp >= f.order_delivered_customer_date)]\nrated = rated.sort_values(['order_purchase_timestamp', 'order_id']).drop_duplicates('customer_unique_id')\nlate = rated.loc[rated.is_late == 1, 'review_score']\non_time = rated.loc[rated.is_late == 0, 'review_score']\ntest = stats.ttest_ind(late, on_time, equal_var=False)\nprint(f'Retard : {late.mean():.3f}, n={len(late)}')\nprint(f'A l heure : {on_time.mean():.3f}, n={len(on_time)}')\nprint(f'Ecart : {late.mean() - on_time.mean():.3f} point')\nprint(f'p brute Welch (bilatéral) : {test.pvalue:.3g}')\nprint('Lire la q-value corrigée et l’IC dans hypotheses.csv.')")
    code("sensitivity = pd.read_csv(BASE / 'data/review_sensitivity.csv')\nprint(sensitivity.to_string(index=False))")
    md("![Retards et avis](../figures/02_retards_avis.png)\n\nLa différence reste une association. Les produits, vendeurs, territoires et profils de clients ne sont pas assignés au hasard. Les tests exploratoires n'établissent pas un effet causal.")
    md("## 5. Concentration du GMV\n\nLes prix sont additifs au niveau article. Les nombres de commandes distinctes par catégorie ne le sont pas : une commande peut contenir plusieurs catégories.")
    code("category_sql = \"SELECT category, SUM(price) AS gmv FROM fact_items WHERE analysis_period=1 AND order_status='delivered' GROUP BY category ORDER BY gmv DESC\"\ncategory = pd.read_sql_query(category_sql, conn)\nprint(category.head(10).to_string(index=False))\nprint(f'Part du top 10 : {category.head(10).gmv.sum() / category.gmv.sum():.2%}')")
    md("![Categories](../figures/03_categories.png)")
    md("## 6. Réachat avec 90 jours de suivi\n\nUtiliser les premiers achats observés avant juin 2018 donne des cohortes mensuelles avec suivi complet au 31 août 2018. Un nouvel achat est une autre commande, passée après l'achat initial et au plus 90 jours plus tard, finalement livrée dans l'extrait. On ne mesure ni le churn ni la fidélité globale à Olist.")
    code("cohorts = pd.read_csv(BASE / 'data/cohorts_90.csv')\nrate = cohorts.repeat_90.sum() / cohorts.customers.sum()\nprint(cohorts.to_string(index=False))\nprint(f'Reachat 90 jours pondéré par les clients : {rate:.2%}')")
    md("![Reachat](../figures/06_reachat.png)")
    md("## 7. Résultats des hypothèses et limites\n\nLes p-values des tests inférentiels sont corrigées ensemble avec Benjamini–Hochberg. Les IC à 95 % de différences de moyennes ne sont pas des intervalles simultanés. Les seuils descriptifs sont exploratoires et explicités ; ils ne reçoivent pas de p-value.")
    code("hyp = pd.read_csv(BASE / 'data/hypotheses.csv')\nprint(hyp[['id', 'hypothese', 'conclusion', 'effect', 'q_bh']].to_string(index=False))\nassert len(hyp) == 26\nconn.close()")
    md("## 8. Passage à Power BI\n\nLe projet natif `../powerbi/Olist/Olist.pbip` contient quatre pages et leurs visuels, sept tables et 27 mesures DAX. Les instructions sont dans `../powerbi/OUVRIR_POWER_BI.md`. Sa structure est validée ; l'actualisation, l'évaluation DAX et le rendu dans Power BI Desktop restent à vérifier avant d'enregistrer un PBIX.\n\n## Recommandations\n\nPrioriser l'audit des commandes multi-vendeurs et des promesses de livraison, segmenter les performances logistiques par territoire et distance, puis tester une action de réachat sur un groupe témoin. Aucun gain financier causal n'est estimé à partir de ces associations.")
    # Generer les graphiques DANS le notebook et conserver les images dans les sorties.
    plots = {
        "01_ventes.png": """fig, axes = plt.subplots(2, 1, figsize=(11, 7), sharex=True)
x = np.arange(len(monthly))
axes[0].plot(x, monthly.orders, marker='o', color='#147D92')
axes[0].set_ylabel('Commandes livrées')
axes[1].bar(x, monthly.gmv_brl / 1e6, color='#147D92')
axes[1].set_ylabel('GMV articles (M BRL)')
axes[1].set_xticks(x[::2])
axes[1].set_xticklabels(monthly.purchase_month.iloc[::2], rotation=40, ha='right')
fig.suptitle('Ventes livrées par mois d’achat — janvier 2017 à août 2018')
plt.tight_layout()
plt.show()""",
        "02_retards_avis.png": """labels = ["À l'heure", '1–3 jours', '4–7 jours', '8–14 jours', '15 jours et plus']
delay_groups = pd.cut(rated.delay_days, [-np.inf, 0, 3, 7, 14, np.inf], labels=labels)
scores = rated.groupby(delay_groups, observed=True).review_score.agg(['mean', 'count'])
fig, ax = plt.subplots(figsize=(10, 5))
ax.bar(scores.index.astype(str), scores['mean'], color=['#147D92'] + ['#D77748'] * 4)
for pos, row in enumerate(scores.itertuples()):
    ax.text(pos, row.mean + .1, f'{row.mean:.2f}\\nn={row.count}', ha='center')
ax.set_ylim(0, 5.5)
ax.set_ylabel('Note moyenne / 5')
ax.set_title('Avis après réception : satisfaction selon le retard')
fig.text(.08, .01, 'Une commande admissible par client ; groupes de 8 jours et plus peu nombreux. Association, pas causalité.', fontsize=9)
plt.tight_layout(rect=[0, .05, 1, 1])
plt.show()""",
        "03_categories.png": """top = category.head(10).sort_values('gmv')
fig, ax = plt.subplots(figsize=(11, 6))
ax.barh(top.category, top.gmv / 1e6, color='#147D92')
ax.set_xlabel('GMV articles livrés (M BRL)')
ax.set_title('Les dix catégories au plus fort GMV')
plt.tight_layout()
plt.show()""",
        "06_reachat.png": """eligible_cohorts = cohorts[cohorts.customers >= 100]
fig, ax = plt.subplots(figsize=(11, 5))
ax.bar(eligible_cohorts.cohort_month, eligible_cohorts.repeat_rate_90 * 100, color='#147D92')
ax.tick_params(axis='x', rotation=45)
ax.set_ylabel('Clients avec réachat à 90 jours (%)')
ax.set_title('Réachat par cohorte — suivi de 90 jours complet')
plt.tight_layout()
plt.show()"""
    }
    extra = """# Géographie : comparaison parmi les commandes livrées de la période.
delivered = f[(f.analysis_period == 1) & (f.order_status == 'delivered')]
states = delivered.groupby('customer_state').agg(orders=('order_id', 'size'), late_rate=('is_late', 'mean'))
states = states[states.orders >= 500].sort_values('late_rate')
fig, ax = plt.subplots(figsize=(10, 6))
ax.barh(states.index, states.late_rate * 100, color='#D77748')
ax.set_xlabel('Retard calendaire (%) ; dates valides')
ax.set_title('Retard par État client — au moins 500 commandes livrées')
plt.tight_layout()
plt.show()

# Concentration : prix agrégés par vendeur au grain article.
sellers = pd.read_sql_query("SELECT seller_id, SUM(price) AS gmv FROM fact_items WHERE analysis_period=1 AND order_status='delivered' GROUP BY seller_id ORDER BY gmv DESC", conn)
fig, ax = plt.subplots(figsize=(9, 5))
ax.plot(np.arange(1, len(sellers)+1)/len(sellers)*100, sellers.gmv.cumsum()/sellers.gmv.sum()*100, color='#147D92', linewidth=2.5)
ax.axvline(20, color='gray', linestyle='--')
ax.axhline(80, color='gray', linestyle='--')
ax.set(xlabel='Vendeurs par GMV décroissant (%)', ylabel='GMV cumulé (%)', title='Concentration du GMV par vendeur', xlim=(0, 100), ylim=(0, 100))
plt.tight_layout()
plt.show()

# Répartition des notes : toutes les notes des commandes livrées de la période.
scores_all = delivered.review_score.value_counts().sort_index()
fig, ax = plt.subplots(figsize=(8, 4))
ax.bar(scores_all.index.astype(int), scores_all.values, color=['#D77748', '#D77748', '#9AAABC', '#147D92', '#147D92'])
ax.set(xlabel='Note / 5', ylabel='Commandes notées', title='Répartition des notes — dernier avis par commande')
ax.set_xticks(range(1, 6))
plt.tight_layout()
plt.show()

# Distribution du délai par zone ; zoom 0–60 jours, valeurs extrêmes masquées.
geo = delivered[delivered.seller_count.eq(1) & delivered.same_state.notna()]
fig, ax = plt.subplots(figsize=(8, 5))
ax.boxplot([geo.loc[geo.same_state.eq(1), 'delivery_days'].dropna(), geo.loc[geo.same_state.eq(0), 'delivery_days'].dropna()], labels=['Même État', 'États différents'], showfliers=False)
ax.set(ylim=(0, 60), ylabel='Délai en jours', title='Délai de livraison des commandes mono-vendeur')
plt.tight_layout()
plt.show()"""
    expanded=[]
    inserted=False
    for cell in cells:
        source_text=''.join(cell['source'])
        if cell['cell_type']=='code' and not inserted:
            cell['source'] = (source_text + "\nimport matplotlib.pyplot as plt\nplt.rcParams.update({'figure.dpi': 120, 'axes.spines.top': False, 'axes.spines.right': False})\n").splitlines(keepends=True)
            inserted=True
        if cell['cell_type']=='markdown':
            for filename, plot_code in plots.items():
                if filename in source_text:
                    expanded.append({'cell_type':'code','metadata':{},'source':plot_code.splitlines(keepends=True),'execution_count':None,'outputs':[]})
                    cell['source']=re.sub(r'!\[[^\]]*\]\([^)]*\)\s*', '', source_text).splitlines(keepends=True)
            if source_text.startswith('## 6.'):
                expanded.append({'cell_type':'markdown','metadata':{},'source':['### Géographie, vendeurs et distributions\n']})
                expanded.append({'cell_type':'code','metadata':{},'source':extra.splitlines(keepends=True),'execution_count':None,'outputs':[]})
        if cell['source']:
            expanded.append(cell)
    cells=expanded
    # Les cellules sont reellement executees, sorties texte et PNG embarquees.
    import os
    previous=os.getcwd()
    os.chdir(OUT)
    env={"__name__":"__main__"}
    count=0
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    original_show=plt.show
    image_outputs=[]
    def capture_show(*args, **kwargs):
        for number in plt.get_fignums():
            fig=plt.figure(number)
            buffer=io.BytesIO()
            fig.savefig(buffer,format='png',dpi=120,bbox_inches='tight')
            image_outputs.append({'output_type':'display_data','data':{'image/png':base64.b64encode(buffer.getvalue()).decode('ascii')},'metadata':{}})
            plt.close(fig)
    plt.show=capture_show
    try:
        for cell in cells:
            if cell["cell_type"] != "code":
                continue
            count += 1
            capture=io.StringIO()
            image_outputs=[]
            with contextlib.redirect_stdout(capture):
                exec(compile("".join(cell["source"]),f"notebook_cell_{count}","exec"),env)
            cell["execution_count"]=count
            output=capture.getvalue()
            cell["outputs"]=[{"output_type":"stream","name":"stdout","text":output.splitlines(keepends=True)}] if output else []
            cell['outputs'].extend(image_outputs)
    finally:
        plt.show=original_show
        os.chdir(previous)
    nb={"cells":cells,"metadata":{"kernelspec":{"display_name":"Python 3 (lewagon)","language":"python","name":"python3"},
        "language_info":{"name":"python","version":"3.10.6"}},"nbformat":4,"nbformat_minor":4}
    (OUT/"notebooks/01_etude_olist.ipynb").write_text(json.dumps(nb,ensure_ascii=False,indent=1),encoding="utf-8")
    return count


def report(sql_count,cell_count):
    meta=json.loads((DATA/"run_metadata.json").read_text())
    h=read("hypotheses")
    checks=read("quality_checks")
    source=read("source_manifest")
    sens=read("review_sensitivity")
    monthly=read("monthly")
    first=read("customer_cohorts")
    facts=read("fact_orders")
    d=facts[(facts.analysis_period == 1) & (facts.order_status == "delivered")]
    e=first[first.eligible_90.eq(1)]
    h10=h[h.id.eq("H10")].iloc[0]
    h16=h[h.id.eq("H16")].iloc[0]
    h24=h[h.id.eq("H24")].iloc[0]
    topmonth=monthly.loc[monthly.late_rate.idxmax()]
    late_all=sens[(sens.population=="Tous avis disponibles") & sens.is_late.eq(1)].iloc[0]
    late_after=sens[(sens.population=="Avis apres reception, tous clients") & sens.is_late.eq(1)].iloc[0]
    keep=late_after.n/late_all.n
    cards=[("Commandes livrées",fmt(meta["delivered_orders"],0)),("GMV articles",fmt(meta["gmv"]/1e6,2)+" M BRL"),
           ("Retard calendaire",pct(meta["late_rate"])),("Réachat à 90 jours",pct(e.repeat_90.mean()))]
    sections=[]
    def add(title, paragraphs=None, frame=None, image=None):
        sections.append({"title":title,"paragraphs":paragraphs or [],"frame":frame,"image":image})
    add("1. La question métier",[
        "Comment accompagner la croissance des ventes tout en améliorant la fiabilité des livraisons et l'expérience client ? Cette étude simule une mission de Data Analyst auprès d'une marketplace. Elle vise à identifier des priorités d'investigation, puis à proposer des actions mesurables.",
        "Le travail couvre 26 hypothèses sur les ventes, les produits, les vendeurs, les paiements, la géographie, la satisfaction et le réachat. Ce n'est pas une mission réellement commanditée par Olist : les décisions et expérimentations proposées sont celles d'un cas portfolio."])
    add("2. Résumé des résultats",[
        "Sur janvier–août, les commandes finalement livrées passent de 21 998 en 2017 à 52 783 en 2018 (+139,9 %). Le panier articles moyen passe de 136,1 à 136,8 BRL (+0,5 %). La croissance observée vient donc principalement du volume, et non d'une forte hausse du panier.",
        "Les dix premières catégories concentrent 62,5 % du GMV. Les 20 % de vendeurs les plus importants en réalisent 82,2 %. Cette concentration justifie un suivi opérationnel prioritaire des vendeurs clés, sans présumer de leur marge ni de leur risque de départ.",
        f"Dans la population d'avis postérieurs à la réception, les retards sont associés à une note inférieure de {fmt(-h10.effect,2)} point (IC 95 % de l'écart retard moins ponctuel : [{fmt(h10.ci_low,2)} ; {fmt(h10.ci_high,2)}]). Les commandes multi-vendeurs présentent un écart de {fmt(h16.effect,2)} point par rapport aux mono-vendeur. Les groupes diffèrent aussi par d'autres caractéristiques : ces écarts ne sont pas des effets causaux.",
        f"Le réachat livré à 90 jours est de {pct(e.repeat_90.mean())}, soit {fmt(e.repeat_90.sum(),0)} clients sur {fmt(len(e),0)} éligibles. Il s'agit d'un comportement observé dans cet extrait et non du taux de fidélité global d'Olist.",
        "Toutes les intuitions ne sont pas confirmées : São Paulo représente 38,4 % du GMV, sous le seuil exploratoire de 40 %. Le nombre de photos n'a pas d'association nette avec la note. La durée supplémentaire de retard parmi les seuls avis post-réception en retard n'est pas concluante après correction des tests."])
    add("3. Sources, périmètre et définitions",[
        f"Neuf CSV fournis localement. Dates d'achat de l'extrait : {meta['source_min_purchase']} à {meta['source_max_purchase']}. La période principale retient janvier 2017 à août 2018 : 2016 est fragmentaire et les derniers mois de 2018 présentent très peu de commandes. Cela ne prouve pas que les mois retenus couvrent toute l'activité d'Olist.",
        "L'analyse est rétrospective, par date d'achat, avec le statut final et les événements disponibles dans les fichiers. Ce n'est pas une photographie de ce qui était connu au 31 août 2018. Les commandes des cohortes de réachat sont datées par leur achat et doivent être finalement livrées dans l'extrait.",
        "GMV articles = somme de price pour les commandes livrées. Panier articles = GMV / nombre de commandes livrées. Les montants sont en BRL, sans correction d'inflation. Le port est traité séparément ; gross_value désigne articles + port. Les paiements ne sont pas additionnés au GMV.",
        "Retard = jour de réception strictement postérieur au jour promis. Les dates manquantes ne sont pas assimilées à des livraisons ponctuelles. La note est celle du dernier avis de commande, de 1 à 5. Un avis négatif correspond à 1 ou 2. Une note de commande n'est pas une note propre à chacun de ses produits ou vendeurs.",
        "Une commande peut contenir plusieurs lignes d'articles, paiements et avis. Le modèle agrège chaque table enfant avant les jointures avec les commandes. Il utilise customer_unique_id pour identifier un client entre achats. Les préfixes postaux restent du texte."],
        source[["file","rows","columns"]].rename(columns={"file":"Fichier","rows":"Lignes","columns":"Colonnes"}))
    add("4. Qualité des données et décisions",[
        "Les identifiants de commandes, clients, produits, vendeurs et les clés composées testées sont uniques. Toutes les références étrangères vérifiées existent. Les totaux articles, port et paiements avant et après agrégation concordent.",
        "Les 547 commandes avec plusieurs avis sont ramenées à un avis selon une règle déterministe : dernière réponse, puis création, review_id et position source. Les textes d'avis ne sont pas copiés dans le rapport. Les valeurs absentes restent manquantes.",
        "Les chronologies incohérentes sont signalées. Une durée négative de préparation ou de transit est exclue de l'indicateur correspondant sans supprimer arbitrairement toute la commande. Les avis avant réception sont conservés dans les descriptifs, puis exclus du test principal de satisfaction post-réception.",
        "Les coordonnées sont filtrées sur un rectangle large du Brésil puis agrégées par médiane du préfixe postal. Ce filtre simple n'est pas une validation par frontière nationale. La distance obtenue est une approximation à vol d'oiseau.",
        "Les rapprochements paiements / articles + port gardent une tolérance de 0,01 BRL. Les anomalies restent visibles et ne sont pas forcées à zéro."],
        checks[checks.valeur.gt(0)].rename(columns={"controle":"Contrôle","valeur":"Nombre","traitement":"Traitement"}))
    add("5. Ventes : séparer croissance, panier et calendrier",[
        "La comparaison annuelle porte sur les huit mêmes mois. Novembre est le mois le plus actif de 2017 avec 7 289 commandes livrées. Le dataset seul ne permet pas d'attribuer le pic à une promotion ou à Black Friday.",
        "Le week-end compte en moyenne 127,9 commandes livrées achetées par jour, contre 170,3 en semaine. Le calcul tient compte du nombre de jours et inclut les jours sans vente. Une analyse ajustée du calendrier resterait nécessaire avant de modifier les effectifs ou les budgets.",
        "Recommandation : suivre séparément volume, panier moyen et GMV, puis dimensionner la capacité logistique lors des pics. Vérifier ces schémas sur une période plus longue avant de les considérer comme une saisonnalité stable."], image="01_ventes.png")
    add("6. Livraison et satisfaction : un résultat sensible au choix des avis",[
        f"Le taux de retard principal est de {pct(meta['late_rate'])}. Comparer les timestamps bruts donnerait {pct(meta['late_timestamp_rate'])} : les promesses datées à minuit peuvent classer en retard une réception le même jour. La convention calendaire retenue doit accompagner le KPI.",
        f"Le délai médian observé est de {fmt(meta['delivery_median'],1)} jours. Le mois d'achat au taux de retard le plus élevé est {topmonth.purchase_month}, à {pct(topmonth.late_rate)}. Il mérite un audit des transporteurs, vendeurs et territoires ; le dataset n'identifie pas la cause.",
        f"Seuls {pct(keep)} des avis de commandes en retard sont postérieurs à la réception ({fmt(late_after.n,0)} sur {fmt(late_all.n,0)}). Exclure les avis antérieurs retire donc une grande part de l'insatisfaction exprimée pendant l'attente. Le test H10 répond à la question de la satisfaction après réception, tandis que la première ligne de population décrit l'ensemble des avis disponibles.",
        "La direction de l'association doit être lue avec son ampleur et cette sélection. La régression, les contrôles par vendeur/catégorie/mois et des données de transport seraient des approfondissements utiles ; ils ne sont pas prétendus réalisés ici."],
        sens.rename(columns={"population":"Population","is_late":"Retard (1=oui)","n":"Commandes notées","review_score":"Note moyenne","bad_review_rate":"Part notes 1–2"}),"02_retards_avis.png")
    add("7. Produits, vendeurs et géographie",[
        "Les catégories et vendeurs se classent par GMV d'articles livrés. Les commandes distinctes d'une catégorie ne s'additionnent pas aux autres catégories. Pour les notes vendeurs, chaque couple vendeur–commande ne compte qu'une fois, mais une commande multi-vendeurs reste partagée entre plusieurs vendeurs.",
        "Les commandes inter-États mono-vendeur mettent en moyenne 15,2 jours à arriver, contre 7,9 dans le même État. La distance approximative est positivement associée au délai (rho de Spearman ≈ 0,545). Les comparaisons restent confondues avec les produits, vendeurs et conditions de transport.",
        "Les notes plus faibles des commandes multi-vendeurs sont un signal prioritaire à investiguer : livraisons séparées, complétude et communication des statuts sont des pistes de diagnostic, pas des causes établies par les données.",
        "Recommandation : auditer les vendeurs à volume suffisant (au moins 100 commandes avec dates valides), comparer des commandes similaires, et tester une promesse de livraison adaptée aux flux géographiques."],image="03_categories.png")
    add("8. Variations territoriales",[
        "Le graphique conserve les États comptant au moins 500 commandes livrées pour éviter de mettre en avant des taux instables sur quelques commandes. Le taux a pour dénominateur les commandes livrées avec dates valides. Une comparaison de taux bruts n'est pas un classement équitable des transporteurs."],image="04_etats.png")
    add("9. Dépendance aux vendeurs",[
        "Le repère 20/80 est une hypothèse exploratoire explicite, pas une loi supposée. Le groupe top 20 % est arrondi au vendeur supérieur et calculé parmi les vendeurs ayant au moins une vente livrée sur la période.",
        "Recommandation : mettre en place un suivi des vendeurs clés et un plan de continuité, tout en développant des vendeurs complémentaires. La concentration du GMV ne suffit pas à choisir quels vendeurs sont rentables."],image="05_vendeurs.png")
    add("10. Paiement et réachat",[
        "Les commandes carte en plusieurs échéances ont un panier avec port moyen plus élevé que celles en une échéance (197,8 contre 100,5 BRL). Cela ne signifie pas que proposer le paiement fractionné crée cet écart : les acheteurs de paniers élevés peuvent choisir davantage cette option.",
        f"La récurrence brute sur l'historique est proche de 3 %, mais la comparaison des cohortes utilise un horizon constant : {fmt(len(e),0)} premiers acheteurs observés avant juin 2018, suivis sur 90 jours à partir de leur achat. Les achats hors Olist Store ou hors extrait ne sont pas visibles.",
        f"H24 utilise une autre fenêtre, de 90 jours après réception, afin d'accorder la même durée de réachat aux groupes. Résultat : {h24.resultat}. L'écart de proportions vaut {fmt(h24.effect*100,2)} point de pourcentage. Sa portée est limitée par la sélection des clients et l'absence de variables marketing.",
        "Recommandation : lancer un test de relance post-livraison auprès de clients éligibles, avec groupe témoin randomisé. Mesurer le réachat incrémental, le coût et les désabonnements. Le dataset ne permet pas de chiffrer aujourd'hui le ROI de cette action."],image="06_reachat.png")
    add("11. Méthodes statistiques et règles d'interprétation",[
        "Les hypothèses et seuils sont exploratoires, définis pour structurer cette étude, et non préenregistrés dans une étude confirmatoire. Les descriptions H01–H09 et H25 sont évaluées contre des critères explicites. Un résultat « observé » décrit uniquement l'extrait.",
        "Les comparaisons de moyennes utilisent Welch bilatéral avec IC de différence à 95 %. Les corrélations utilisent Spearman. Le test de catégories est un Kruskal–Wallis global : il ne démontre pas quelles paires diffèrent ni un simple écart de moyennes.",
        "Les 16 p-values inférentielles sont corrigées ensemble avec Benjamini–Hochberg ; le seuil exploratoire q < 0,05 est utilisé pour les conclusions. Les IC restent marginaux, non corrigés pour comparaisons multiples. Les p-values numériquement nulles reflètent la précision machine et ne sont pas des probabilités exactement nulles.",
        "Pour réduire la répétition de clients, les tests sur les commandes conservent la première observation admissible par client. Les observations peuvent néanmoins être dépendantes via les vendeurs, les produits ou les périodes. La correction BH ne résout ni cette dépendance, ni les variables de confusion, ni le biais de sélection.",
        "Les notes sont ordinales : une moyenne est un résumé pratique, à lire avec les distributions. Une association de -0,051 point pour un port supérieur à 20 % du panier peut être statistiquement détectable sans être importante commercialement. Aucune conclusion n'est formulée comme une preuve de causalité."])
    small=h[["id","theme","hypothese","resultat","conclusion"]].rename(columns={"id":"ID","theme":"Thème","hypothese":"Hypothèse","resultat":"Résultat","conclusion":"Conclusion"})
    add("12. Registre des 26 hypothèses",["Les effectifs, effets, intervalles, p-values, q-values et limites individuelles sont fournis dans data/hypotheses.csv. Les unités de chaque effet sont celles de la variable testée ; pour H24, multiplier l'écart par 100 pour obtenir des points de pourcentage."],small)
    next_actions=pd.DataFrame([
        ["1", "Auditer commandes multi-vendeurs et mois de retard élevé", "Responsables opérations / support", "Complétude, retard calendaire, notes 1–2", "Analyse de commandes comparables puis pilote contrôlé"],
        ["2", "Adapter les promesses aux flux géographiques", "Logistique", "Ponctualité + délai promis + conversion", "Tester par zone, ne pas améliorer le taux en allongeant seulement la promesse"],
        ["3", "Sécuriser les vendeurs clés", "Équipe marketplace", "GMV exposé, incidents, diversité offre", "Évaluer coûts et capacité avant arbitrage"],
        ["4", "Tester une relance après réception", "CRM", "Réachat incrémental à 90j et coût", "Randomisation, groupe témoin, suivi complet"],
        ["5", "Qualifier les écarts de paiement", "Finance / data", "Nombre et somme absolue des écarts", "Relier remboursements et écritures comptables manquantes"],
    ],columns=["Priorité","Action proposée","Équipe","Indicateur","Validation nécessaire"])
    add("13. Plan d'action proposé",["Les priorités ci-dessous sont des propositions issues de l'analyse. Aucune action n'a été déployée et aucun gain n'est revendiqué."],next_actions)
    untestable=pd.DataFrame([
        ["Marge et rentabilité", "Coût d'achat, commissions, coûts réels de transport, retours"],
        ["Conversion et abandon panier", "Sessions, visites, paniers et événements de navigation"],
        ["ROI marketing / CAC", "Dépenses, canaux d'acquisition et attribution"],
        ["Élasticité prix / effet promotion", "Historique des prix, expositions, contrôle ou variation exogène"],
        ["Churn et vraie valeur vie client", "Historique plus long, couverture client complète, marge"],
        ["Effet du transporteur", "Identifiant transporteur, trajet et incidents détaillés"],
        ["Taux de retours / remboursements", "Tables dédiées de retours et remboursements"],
        ["Profil démographique", "Âge, revenu ou autres caractéristiques directement observées"],
        ["Satisfaction causée par la livraison", "Expérience contrôlée ou stratégie causale crédible"],
        ["Performance actuelle d'Olist", "Données actuelles et périmètre d'activité comparable"],
    ],columns=["Question non tranchée","Données nécessaires"])
    add("14. Ce que cette étude ne permet pas de conclure",["Ces questions sont pertinentes pour un projet commercial, mais inventer des réponses affaiblirait le portfolio. Elles constituent un plan de collecte ou d'approfondissement."],untestable)
    add("15. Reproductibilité et livrables",[
        f"Le pipeline Python a été exécuté dans Ubuntu WSL, environnement lewagon (Python {meta['python']}, pandas {meta['pandas']}, NumPy {meta['numpy']}, SciPy {meta['scipy']}, Matplotlib {meta['matplotlib']}). Les neuf fichiers sont identifiés par empreinte SHA-256 dans source_manifest.csv.",
        f"Les {sql_count} requêtes SQL ont été exécutées. La vue SQL reconstruite depuis les données sources concorde commande par commande avec le modèle Python pour les montants et les notes. Les {cell_count} cellules de code du notebook ont été exécutées et leurs sorties sont enregistrées.",
        "Le projet natif powerbi/Olist/Olist.pbip contient quatre pages, 14 graphiques, 16 cartes d'indicateurs, neuf filtres et deux tableaux. Il relie sept tables et 27 mesures DAX. Les définitions passent les schémas officiels Microsoft. L'actualisation, l'évaluation DAX et le rendu dans Power BI Desktop restent à vérifier avant l'enregistrement en PBIX.",
        "Source du jeu de données : https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce. Avant publication, conserver l'attribution et vérifier les conditions de redistribution sur la page source. Les fichiers sources sont à télécharger séparément depuis Kaggle."])
    # Markdown portable pour GitHub.
    markdown=["# Olist — Croissance, livraison et satisfaction client", "\nÉtude de cas Data Analyst · Python, SQL et préparation Power BI\n",
              " | ".join(f"**{label} : {value}**" for label,value in cards),
              "\nPériode principale : achats de janvier 2017 à août 2018. Cohortes de réachat : historique avec suivi complet.\n"]
    content=[]
    nav=[]
    for ix, sec in enumerate(sections,1):
        markdown.append("\n## "+sec["title"]+"\n")
        markdown.extend(p+"\n" for p in sec["paragraphs"])
        section_html=[f'<section id="s{ix}"><h2>{html.escape(sec["title"])}</h2>']
        section_html.extend(f'<p>{html.escape(p)}</p>' for p in sec["paragraphs"])
        if sec["frame"] is not None:
            markdown.append(md_table(sec["frame"])+"\n")
            table=sec["frame"].to_html(index=False,border=0,escape=True,float_format=lambda x:fmt(x,3))
            section_html.append('<div class="table-scroll">'+table+'</div>')
        if sec["image"]:
            markdown.append(f'![{sec["title"]}](figures/{sec["image"]})\n')
            section_html.append(f'<figure><img src="figures/{sec["image"]}" alt="{html.escape(sec["title"])}"></figure>')
        section_html.append("</section>")
        content.append("\n".join(section_html))
        nav.append(f'<a href="#s{ix}">{html.escape(sec["title"])}</a>')
    (OUT/"ETUDE_DE_CAS.md").write_text("\n".join(markdown),encoding="utf-8")
    css="""
    :root{--ink:#17324d;--accent:#147d92;--bg:#fafbfc}*{box-sizing:border-box}html{scroll-behavior:smooth}
    body{margin:0;background:var(--bg);color:#24394d;font:16px/1.75 'Segoe UI',Arial,sans-serif}
    header{background:var(--ink);color:white;padding:64px max(5vw,calc((100vw - 1160px)/2));}
    .eyebrow{color:#a5dce2;font-size:13px;letter-spacing:2px;text-transform:uppercase;font-weight:600}
    h1{font-size:clamp(32px,4vw,54px);line-height:1.15;max-width:900px;margin:16px 0 24px}
    header p{max-width:850px;color:#dae5ee}.cards{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin:30px 0 0}
    .card{border-top:3px solid #61b4bf;background:#23415c;padding:18px}.card strong{display:block;font-size:28px;line-height:1.4}.card span{font-size:13px;color:#dce6ef}
    main{max-width:1160px;margin:auto;padding:32px 28px 80px}nav{padding:22px;background:#eef3f6;display:flex;gap:8px 22px;flex-wrap:wrap}
    nav a{font-size:13px;color:var(--accent);text-decoration:none}section{padding:34px 0;border-bottom:1px solid #dce4ea}
    h2{font-size:26px;line-height:1.3;color:var(--ink);margin:0 0 20px}p{max-width:1000px;margin:0 0 16px}
    .table-scroll{overflow:auto;margin:24px 0;border:1px solid #dce4ea;border-radius:4px}
    table{border-collapse:collapse;width:100%;font-size:13px;line-height:1.5}th{background:var(--ink);color:white;text-align:left;padding:12px;vertical-align:top;min-width:90px}
    td{padding:12px;vertical-align:top;border-bottom:1px solid #dce4ea;min-width:90px}tr:nth-child(even){background:#eef3f6}
    #s12 td:nth-child(3){min-width:230px}#s12 td:nth-child(4){min-width:260px}figure{margin:28px 0}img{display:block;width:100%;height:auto}
    footer{background:#eef3f6;padding:25px;text-align:center;font-size:13px}a{color:var(--accent)}
    @media(max-width:720px){.cards{grid-template-columns:repeat(2,1fr)}header{padding:32px 20px}main{padding:20px}h2{font-size:23px}.card strong{font-size:23px}}
    @media print{header{background:white;color:var(--ink);padding:10px}header p{color:#24394d}.cards{display:none}nav{display:none}main{padding:0}section{break-inside:avoid}body{font-size:11px}.table-scroll{overflow:visible}th{background:#ddd;color:black}img{max-height:500px;object-fit:contain}}
    """
    card_html="".join(f'<div class="card"><span>{html.escape(label)}</span><strong>{html.escape(value)}</strong></div>' for label,value in cards)
    page='<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Olist — Étude de cas Data Analyst</title><style>'+css+'</style></head><body>'
    page+='<header><div class="eyebrow">Portfolio · Data Analyst</div><h1>Olist : comprendre la croissance et les frictions de livraison</h1><p>26 hypothèses confrontées aux données. Une étude reproductible qui relie performance commerciale, expérience client et décisions opérationnelles.</p><p>Achats de janvier 2017 à août 2018 · Python & SQL · Préparation Power BI</p><div class="cards">'+card_html+'</div></header>'
    page+='<main><nav aria-label="Sommaire">'+"".join(nav)+'</nav>'+"".join(content)+'</main><footer>Source : <a href="https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce">Brazilian E-Commerce Public Dataset by Olist</a> · Étude exploratoire historique · Aucun gain causal revendiqué</footer></body></html>'
    (OUT/"ETUDE_DE_CAS.html").write_text(page,encoding="utf-8")
    print("Rapports HTML et Markdown generes.")


def main():
    sql_count=check_sql()
    cells=notebook()
    report(sql_count,cells)
    summary={"sql_queries_executed":sql_count,"sql_python_rowwise_reconciliation":"passed",
             "notebook_code_cells_executed":cells,"hypotheses":len(read("hypotheses"))}
    (DATA/"validation.json").write_text(json.dumps(summary,indent=2),encoding="utf-8")
    print(json.dumps(summary,indent=2))


if __name__=="__main__":
    main()
