"""Etude exploratoire Olist. Executer depuis n'importe quel repertoire.

Les CSV source restent intacts. Les sorties generees de portfolio/ sont remplacees.
Compatible Python 3.10, pandas 1.4, scipy 1.8.
"""
from pathlib import Path
import hashlib
import json
import sqlite3
import sys
import os
import platform
import html
import math
import textwrap

import numpy as np
import pandas as pd
from scipy import stats
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

OUT = Path(__file__).resolve().parents[1]
ROOT = Path(os.environ.get("OLIST_RAW_DIR", str(OUT / "data/raw"))).resolve()
DATA = OUT / "data"
FIG = OUT / "figures"
for directory in [DATA, FIG, OUT / "sql", OUT / "powerbi", OUT / "notebooks"]:
    directory.mkdir(parents=True, exist_ok=True)
PERIOD_START = pd.Timestamp("2017-01-01")
PERIOD_END = pd.Timestamp("2018-09-01")  # borne exclusive
OBS_END = pd.Timestamp("2018-08-31 23:59:59")


def save(df, name):
    df.to_csv(DATA / f"{name}.csv", index=False, encoding="utf-8-sig")


def fmt(value, decimals=1):
    return f"{value:,.{decimals}f}".replace(",", " ").replace(".", ",")


def pct(value):
    return fmt(100 * value) + " %"


def table_md(df):
    frame = df.copy().fillna("—")
    def clean(x):
        return str(x).replace("|", "/").replace("\n", " ")
    lines = ["| " + " | ".join(map(clean, frame.columns)) + " |",
             "| " + " | ".join(["---"] * len(frame.columns)) + " |"]
    lines += ["| " + " | ".join(map(clean, row)) + " |" for row in frame.itertuples(index=False, name=None)]
    return "\n".join(lines)


def load_sources():
    sources = {}
    manifest = []
    for path in sorted(ROOT.glob("*.csv")):
        name = path.stem.replace("olist_", "").replace("_dataset", "")
        frame = pd.read_csv(path, dtype=str)
        sources[name] = frame
        manifest.append({"file": path.name, "rows": len(frame), "columns": len(frame.columns),
                         "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    assert len(sources) == 9, "Neuf sources attendues"
    save(pd.DataFrame(manifest), "source_manifest")
    profile = []
    for name, frame in sources.items():
        for col in frame:
            profile.append({"table": name, "column": col, "rows": len(frame),
                            "missing": int(frame[col].isna().sum()),
                            "missing_rate": float(frame[col].isna().mean()),
                            "unique_non_null": int(frame[col].nunique())})
    save(pd.DataFrame(profile), "quality_columns")
    return sources, manifest


def build_model(raw):
    checks = []
    def check(name, value, rule):
        checks.append({"controle": name, "valeur": int(value), "traitement": rule})
    for table, key in [("orders", ["order_id"]), ("customers", ["customer_id"]),
                       ("products", ["product_id"]), ("sellers", ["seller_id"]),
                       ("order_items", ["order_id", "order_item_id"]),
                       ("order_payments", ["order_id", "payment_sequential"])]:
        duplicates = raw[table].duplicated(key).sum()
        check(f"Doublons de cle : {table}", duplicates, "Arret si non nul")
        assert duplicates == 0 and raw[table][key].notna().all().all()
    o, c, p, s, i, pay, r = [raw[k].copy() for k in
        ["orders", "customers", "products", "sellers", "order_items", "order_payments", "order_reviews"]]
    for frame, cols in [(i, ["order_item_id", "price", "freight_value"]),
                        (pay, ["payment_sequential", "payment_installments", "payment_value"]),
                        (r, ["review_score"]),
                        (p, [x for x in p if x not in ["product_id", "product_category_name"]])]:
        for col in cols:
            frame[col] = pd.to_numeric(frame[col], errors="raise")
    for col in o:
        if col.endswith("timestamp") or col.endswith("date") or col == "order_approved_at":
            o[col] = pd.to_datetime(o[col], errors="raise")
    for col in ["review_creation_date", "review_answer_timestamp"]:
        r[col] = pd.to_datetime(r[col], errors="raise")
    i["shipping_limit_date"] = pd.to_datetime(i["shipping_limit_date"])
    for child, col, parent, pk in [(i, "order_id", o, "order_id"), (pay, "order_id", o, "order_id"),
            (r, "order_id", o, "order_id"), (o, "customer_id", c, "customer_id"),
            (i, "product_id", p, "product_id"), (i, "seller_id", s, "seller_id")]:
        missing = (~child[col].isin(parent[pk])).sum()
        check(f"References absentes {col}, table {len(child)} lignes", missing, "Arret si non nul")
        assert missing == 0
    check("Commandes avec plusieurs avis", (r.groupby("order_id").size() > 1).sum(),
          "Dernier avis par date de reponse, puis creation, puis review_id, puis ordre source")
    check("Doublons review_id", r.duplicated("review_id").sum(), "review_id non utilise seul comme cle")
    r["_source_row"] = np.arange(len(r))
    latest = r.sort_values(["review_answer_timestamp", "review_creation_date", "review_id", "_source_row"],
                           kind="mergesort", na_position="first").drop_duplicates("order_id", keep="last").copy()
    latest["has_comment"] = latest.review_comment_message.fillna("").str.strip().ne("").astype(int)
    latest = latest[["order_id", "review_score", "has_comment", "review_answer_timestamp"]]
    item_totals = i.groupby("order_id").agg(item_count=("order_item_id", "size"),
        seller_count=("seller_id", "nunique"), item_value=("price", "sum"), freight_value=("freight_value", "sum"))
    pay_totals = pay.groupby("order_id").agg(payment_total=("payment_value", "sum"),
        payment_rows=("payment_sequential", "size"), payment_types=("payment_type", "nunique"),
        max_installments=("payment_installments", "max"))
    pay_type = pay.groupby("order_id").payment_type.agg(lambda x: x.iloc[0] if x.nunique() == 1 else "mixed")
    pay_totals["payment_type"] = pay_type
    f = o.merge(c, on="customer_id", how="left", validate="one_to_one")
    f = f.merge(item_totals, on="order_id", how="left", validate="one_to_one")
    f = f.merge(pay_totals, on="order_id", how="left", validate="one_to_one")
    f = f.merge(latest, on="order_id", how="left", validate="one_to_one")
    assert len(f) == len(o) and f.order_id.is_unique
    f["purchase_date"] = f.order_purchase_timestamp.dt.normalize()
    f["purchase_month"] = f.order_purchase_timestamp.dt.strftime("%Y-%m")
    f["gross_value"] = f.item_value + f.freight_value
    f["freight_share"] = f.freight_value / f.gross_value.where(f.gross_value > 0)
    f["payment_gap"] = f.payment_total - f.gross_value
    delivered = f.order_status.eq("delivered")
    duration = (f.order_delivered_customer_date - f.order_purchase_timestamp).dt.total_seconds() / 86400
    valid_delivery = delivered & duration.ge(0) & f.order_estimated_delivery_date.notna()
    f["delivery_days"] = duration.where(delivered & duration.ge(0))
    f["delay_days"] = (f.order_delivered_customer_date.dt.normalize() - f.order_estimated_delivery_date.dt.normalize()).dt.days.where(valid_delivery)
    f["is_late"] = f.delay_days.gt(0).astype(float).where(valid_delivery)
    f["is_late_timestamp"] = (f.order_delivered_customer_date > f.order_estimated_delivery_date).astype(float).where(valid_delivery)
    f["promise_days"] = (f.order_estimated_delivery_date - f.purchase_date).dt.total_seconds() / 86400
    handoff = (f.order_delivered_carrier_date - f.order_approved_at).dt.total_seconds() / 86400
    f["handoff_days"] = handoff.where(delivered & handoff.ge(0))
    transit = (f.order_delivered_customer_date - f.order_delivered_carrier_date).dt.total_seconds() / 86400
    f["transit_days"] = transit.where(delivered & transit.ge(0))
    f["bad_review"] = f.review_score.le(2).astype(float).where(f.review_score.notna())
    f["analysis_period"] = ((f.order_purchase_timestamp >= PERIOD_START) & (f.order_purchase_timestamp < PERIOD_END)).astype(int)
    check("Commandes sans articles", f.item_count.isna().sum(), "Montants laisses manquants")
    check("Commandes sans paiement", f.payment_total.isna().sum(), "Montants laisses manquants")
    check("Commandes sans avis", f.review_score.isna().sum(), "Exclues des moyennes de notes")
    check("Livrees sans date de reception", (delivered & f.order_delivered_customer_date.isna()).sum(), "Exclues des delais")
    check("Reception avant achat", duration.lt(0).sum(), "Duree exclue des indicateurs logistiques")
    check("Remise transporteur avant approbation", handoff.lt(0).sum(), "Duree de preparation exclue")
    check("Reception avant remise transporteur", transit.lt(0).sum(), "Duree de transit exclue")
    check("Avis repondu avant reception", (f.review_answer_timestamp < f.order_delivered_customer_date).sum(),
          "Conserves pour descriptif, exclus du test principal retard-note")
    check("Ecart paiement vs articles+port > 0,01 BRL", f.payment_gap.abs().gt(.010001).sum(),
          "Signale, aucune correction arbitraire")
    assert np.isclose(f.item_value.sum(), i.price.sum())
    assert np.isclose(f.freight_value.sum(), i.freight_value.sum())
    assert np.isclose(f.payment_total.sum(), pay.payment_value.sum())
    # Un seul point median par prefixe postal, jamais de jointure sur les lignes geographiques brutes.
    geo = raw["geolocation"].copy()
    for col in ["geolocation_lat", "geolocation_lng"]:
        geo[col] = pd.to_numeric(geo[col], errors="raise")
    plausible = geo.geolocation_lat.between(-34, 6) & geo.geolocation_lng.between(-74, -34)
    check("Coordonnees hors rectangle large du Bresil", (~plausible).sum(), "Exclues avant mediane par prefixe")
    gp = geo.loc[plausible].groupby("geolocation_zip_code_prefix", as_index=False)[["geolocation_lat", "geolocation_lng"]].median()
    pp = p.merge(raw["product_category_name_translation"], on="product_category_name", how="left", validate="many_to_one")
    pp["category"] = pp.product_category_name_english.fillna(pp.product_category_name).fillna("unknown")
    detail = i.merge(pp, on="product_id", how="left", validate="many_to_one")
    detail = detail.merge(s, on="seller_id", how="left", validate="many_to_one")
    detail = detail.merge(f[["order_id", "customer_state", "customer_zip_code_prefix", "order_status", "purchase_date", "purchase_month", "analysis_period", "delivery_days", "is_late", "review_score", "item_count", "seller_count"]], on="order_id", validate="many_to_one")
    detail["same_state"] = detail.seller_state.eq(detail.customer_state).astype(int)
    for prefix, key in [("customer", "customer_zip_code_prefix"), ("seller", "seller_zip_code_prefix")]:
        detail = detail.merge(gp.rename(columns={"geolocation_zip_code_prefix": key,
            "geolocation_lat": f"{prefix}_lat", "geolocation_lng": f"{prefix}_lng"}), on=key, how="left", validate="many_to_one")
    lat1, lat2 = np.radians(detail.customer_lat), np.radians(detail.seller_lat)
    dlat, dlon = lat2-lat1, np.radians(detail.seller_lng-detail.customer_lng)
    a = np.sin(dlat/2)**2 + np.cos(lat1)*np.cos(lat2)*np.sin(dlon/2)**2
    detail["distance_km"] = 6371 * 2 * np.arcsin(np.sqrt(a.clip(0, 1)))
    single = detail[detail.seller_count.eq(1)].drop_duplicates("order_id")[["order_id", "same_state", "distance_km"]]
    f = f.merge(single, on="order_id", how="left", validate="one_to_one")
    save(pd.DataFrame(checks), "quality_checks")
    save(f, "fact_orders")
    save(detail, "fact_items")
    save(pp, "dim_products")
    save(s, "dim_sellers")
    save(gp, "geo_prefix")
    return f, detail, pd.DataFrame(checks), latest, gp


def cohort_analysis(f):
    # Fenetre historique egale pour tous : premier achat livre enregistre jusqu'au 31/08/2018.
    d = f[f.order_status.eq("delivered") & f.order_purchase_timestamp.le(OBS_END)].copy()
    d = d.sort_values(["order_purchase_timestamp", "order_id"])
    first = d.drop_duplicates("customer_unique_id").copy()
    first = first.rename(columns={"order_id": "first_order_id", "order_purchase_timestamp": "first_purchase"})
    x = d[["customer_unique_id", "order_id", "order_purchase_timestamp"]].merge(
        first[["customer_unique_id", "first_order_id", "first_purchase", "order_delivered_customer_date"]], on="customer_unique_id", validate="many_to_one")
    delta = (x.order_purchase_timestamp-x.first_purchase).dt.total_seconds()/86400
    is_new_order = x.order_id.ne(x.first_order_id)
    within = is_new_order & delta.gt(0) & delta.le(90)
    rep = x.loc[within].groupby("customer_unique_id").size()
    days_after_delivery = (x.order_purchase_timestamp-x.order_delivered_customer_date).dt.total_seconds()/86400
    after_delivery = is_new_order & days_after_delivery.gt(0) & days_after_delivery.le(90)
    rep_after = x.loc[after_delivery].groupby("customer_unique_id").size()
    first["repeat_90"] = first.customer_unique_id.isin(rep.index).astype(int)
    first["repeat_after_delivery_90"] = first.customer_unique_id.isin(rep_after.index).astype(int)
    complete_cohort_cutoff = (OBS_END-pd.Timedelta(days=90)).to_period("M").start_time
    first["eligible_90"] = first.first_purchase.lt(complete_cohort_cutoff).astype(int)
    first["eligible_postdelivery_90"] = first.order_delivered_customer_date.le(OBS_END-pd.Timedelta(days=90)).astype(int)
    first["cohort_month"] = first.first_purchase.dt.strftime("%Y-%m")
    eligible = first[first.eligible_90.eq(1)]
    cohorts = eligible.groupby("cohort_month", as_index=False).agg(customers=("customer_unique_id", "size"),
        repeat_90=("repeat_90", "sum"), repeat_rate_90=("repeat_90", "mean"))
    save(cohorts, "cohorts_90")
    save(first, "customer_cohorts")
    return first, cohorts, d


def hypothesis_analysis(f, detail, first, delivered_all):
    results = []
    a = f[f.analysis_period.eq(1)].copy()
    d = a[a.order_status.eq("delivered")].copy()
    # Hypotheses descriptives : criteres explicites, pas de test de causalite.
    def desc(hid, theme, hypothesis, observed, supported, population, limit):
        results.append(dict(id=hid, theme=theme, hypothese=hypothesis, resultat=observed,
            conclusion="Observee" if supported else "Non observee", population=population,
            n_a=np.nan, n_b=np.nan, effect=np.nan, ci_low=np.nan, ci_high=np.nan,
            p_value=np.nan, methode="Descriptif", limite=limit))
    windows = {}
    for year in [2017, 2018]:
        q = d[(d.order_purchase_timestamp.dt.year == year) & (d.order_purchase_timestamp.dt.month <= 8)]
        windows[year] = {"orders": len(q), "gmv": q.item_value.sum(), "aov": q.item_value.mean()}
    growth = windows[2018]["orders"]/windows[2017]["orders"]-1
    desc("H01", "Ventes", "Le volume livre augmente entre janvier-aout 2017 et janvier-aout 2018",
         f"{windows[2017]['orders']} -> {windows[2018]['orders']} commandes ; {pct(growth)}", growth > 0,
         "Commandes livrees, mois d'achat comparables", "Croissance de cet extrait, pas de toute Olist ni causalite marketing")
    av = windows[2018]["aov"]/windows[2017]["aov"]-1
    desc("H02", "Ventes", "Le panier articles moyen augmente sur les memes mois",
         f"{fmt(windows[2017]['aov'])} -> {fmt(windows[2018]['aov'])} BRL ; {pct(av)}", av > 0,
         "Commandes livrees janvier-aout, hors port", "Composition des produits et clients non constante")
    m17 = d[d.order_purchase_timestamp.dt.year.eq(2017)].groupby("purchase_month").size()
    desc("H03", "Ventes", "Novembre est le mois au plus fort volume livre en 2017",
         f"Maximum : {m17.idxmax()} ({m17.max()} commandes)", m17.idxmax() == "2017-11",
         "Commandes livrees achetees en 2017", "Un pic ne prouve pas un effet Black Friday ; une seule annee complete")
    cal = pd.date_range(PERIOD_START, PERIOD_END-pd.Timedelta(days=1))
    weekend = d.order_purchase_timestamp.dt.dayofweek.ge(5)
    wavg = weekend.sum()/sum(cal.dayofweek >= 5)
    bavg = (~weekend).sum()/sum(cal.dayofweek < 5)
    desc("H04", "Ventes", "Le volume quotidien moyen est plus faible le week-end",
         f"Week-end {fmt(wavg)} vs semaine {fmt(bavg)} commandes/jour", wavg < bavg,
         "Commandes livrees janvier 2017-aout 2018 ; jours sans vente inclus", "Effets calendaires et tendance non ajustes")
    di = detail[detail.analysis_period.eq(1) & detail.order_status.eq("delivered")].copy()
    cat = di.groupby("category").price.sum().sort_values(ascending=False)
    cshare = cat.head(10).sum()/cat.sum()
    desc("H05", "Produits", "Dix categories concentrent plus de la moitie du GMV livre",
         f"Top 10 : {pct(cshare)} du GMV", cshare > .5, "Articles livres janvier 2017-aout 2018",
         "GMV articles, pas marge ; categories manquantes conservees sous unknown")
    sellers = di.groupby("seller_id").price.sum().sort_values(ascending=False)
    k = math.ceil(len(sellers)*.2)
    sshare = sellers.head(k).sum()/sellers.sum()
    desc("H06", "Vendeurs", "Les 20 % de vendeurs les plus importants realisent au moins 80 % du GMV",
         f"{k}/{len(sellers)} vendeurs : {pct(sshare)} du GMV", sshare >= .8,
         "Vendeurs ayant au moins un article livre, periode principale", "Seuil Pareto exploratoire ; aucun lien avec la rentabilite")
    sp = d.loc[d.customer_state.eq("SP"), "item_value"].sum()/d.item_value.sum()
    desc("H07", "Geographie", "Les clients de SP representent plus de 40 % du GMV livre",
         f"SP : {pct(sp)} du GMV", sp > .4, "Commandes livrees, periode principale", "Localisation client, pas localisation vendeur")
    customer_counts = delivered_all.groupby("customer_unique_id").size()
    rep = customer_counts.gt(1).mean()
    desc("H08", "Fidelisation", "Moins de 10 % des clients livres ont plusieurs commandes observees",
         f"{pct(rep)} ; {int(customer_counts.gt(1).sum())}/{len(customer_counts)} clients", rep < .1,
         "Tous achats livres jusqu'au 31/08/2018 ; customer_unique_id", "Fenetre inegale, achats hors extrait invisibles ; pas un taux de churn")
    eligible = first[first.eligible_90.eq(1)]
    rep90 = eligible.repeat_90.mean()
    desc("H09", "Fidelisation", "Le reachat livre a 90 jours est inferieur a 5 %",
         f"{pct(rep90)} ; {int(eligible.repeat_90.sum())}/{len(eligible)} clients eligibles", rep90 < .05,
         "Premier achat livre observe avant juin 2018, cohortes mensuelles avec 90 jours complets", "Premier achat observe, pas acquisition certaine ; commandes de l'extrait seulement")
    def compare(hid, theme, hyp, frame, mask, metric, labels, direction, limit):
        valid = frame[metric].notna() & mask.notna()
        g = mask[valid].astype(bool)
        x = frame.loc[valid, metric][g].astype(float).to_numpy()
        y = frame.loc[valid, metric][~g].astype(float).to_numpy()
        assert len(x) >= 2 and len(y) >= 2, hid
        effect = x.mean()-y.mean()
        vx, vy = x.var(ddof=1)/len(x), y.var(ddof=1)/len(y)
        se = np.sqrt(vx+vy)
        df = (vx+vy)**2/(vx**2/(len(x)-1)+vy**2/(len(y)-1))
        margin = stats.t.ppf(.975, df)*se
        _, pval = stats.ttest_ind(x, y, equal_var=False)
        results.append(dict(id=hid, theme=theme, hypothese=hyp,
            resultat=f"{labels[0]} : {fmt(x.mean(),3)} (n={len(x)}) ; {labels[1]} : {fmt(y.mean(),3)} (n={len(y)}) ; ecart {fmt(effect,3)}",
            conclusion="A calculer", population=f"{labels[0]} vs {labels[1]} ; variable {metric}", n_a=len(x), n_b=len(y),
            effect=effect, ci_low=effect-margin, ci_high=effect+margin, p_value=pval, methode="Welch, bilateral", direction=direction,
            limite=limit))
    def corr(hid, theme, hyp, frame, x, y, direction, limit):
        xy = frame[[x,y]].dropna()
        rho, pval = stats.spearmanr(xy[x], xy[y])
        results.append(dict(id=hid, theme=theme, hypothese=hyp,
            resultat=f"rho={fmt(rho,3)} ; n={len(xy)}", conclusion="A calculer", population=f"{x} vs {y}",
            n_a=len(xy), n_b=np.nan, effect=rho, ci_low=np.nan, ci_high=np.nan, p_value=pval,
            methode="Spearman, bilateral", direction=direction, limite=limit))
    rated = d[d.review_score.notna() & d.is_late.notna() & (d.review_answer_timestamp >= d.order_delivered_customer_date)].copy()
    # Une commande par client pour reduire la dependance dans les tests de satisfaction.
    rated = rated.sort_values(["order_purchase_timestamp", "order_id"]).drop_duplicates("customer_unique_id")
    base_limit = "Association exploratoire, sans causalite ; avis apres reception ; premiere commande admissible par client"
    compare("H10", "Satisfaction", "Les commandes en retard ont une note plus faible", rated, rated.is_late.eq(1),
            "review_score", ["Retard", "A l'heure"], -1, base_limit)
    corr("H11", "Satisfaction", "Parmi les retards, un retard plus long est associe a une note plus faible",
         rated[rated.is_late.eq(1)], "delay_days", "review_score", -1, base_limit)
    compare("H12", "Livraison", "Les livraisons de plus de 15 jours ont une note plus faible", rated,
            rated.delivery_days.gt(15), "review_score", [">15 jours", "<=15 jours"], -1,
            base_limit + " ; seuil exploratoire de 15 jours")
    single = d[d.seller_count.eq(1) & d.same_state.notna()].copy()
    single = single.sort_values(["order_purchase_timestamp", "order_id"]).drop_duplicates("customer_unique_id")
    compare("H13", "Geographie", "Les commandes entre Etats differents mettent plus longtemps a arriver", single,
            single.same_state.eq(0), "delivery_days", ["Inter-Etats", "Meme Etat"], 1,
            "Commandes mono-vendeur, premiere par client ; distances, produits et vendeurs confondus")
    corr("H14", "Geographie", "Une distance vendeur-client plus grande est associee a un delai plus long", single,
         "distance_km", "delivery_days", 1, "Distance a vol d'oiseau entre medianes de prefixes, pas itineraire reel")
    freight_rated = rated[rated.freight_share.notna()]
    compare("H15", "Prix", "Un port superieur a 20 % du panier total est associe a une note plus faible", freight_rated,
            freight_rated.freight_share.gt(.2), "review_score", ["Port >20 %", "Port <=20 %"], -1,
            base_limit + " ; prix et geographie non ajustes")
    rr = rated[rated.seller_count.notna()]
    compare("H16", "Vendeurs", "Les commandes multi-vendeurs ont une note plus faible", rr, rr.seller_count.gt(1),
            "review_score", ["Multi-vendeurs", "Mono-vendeur"], -1, base_limit)
    rr = rated[rated.item_count.notna()]
    compare("H17", "Produits", "Les commandes multi-articles ont une note plus faible", rr, rr.item_count.gt(1),
            "review_score", ["Multi-articles", "Un article"], -1, base_limit)
    payd = d.sort_values(["order_purchase_timestamp", "order_id"]).drop_duplicates("customer_unique_id")
    credit = payd[payd.payment_type.eq("credit_card") & payd.max_installments.ge(1)]
    compare("H18", "Paiement", "Le paiement par carte en plusieurs fois accompagne un panier plus eleve", credit,
            credit.max_installments.gt(1), "gross_value", ["Plusieurs echeances", "Une echeance"], 1,
            "Carte seule ; premiere commande livree par client ; choix de paiement endogene, pas un effet causal")
    cp = payd[payd.payment_type.isin(["credit_card", "boleto"])]
    compare("H19", "Paiement", "Le panier carte est plus eleve que le panier boleto", cp, cp.payment_type.eq("credit_card"),
            "gross_value", ["Carte", "Boleto"], 1, "Modes exclusifs ; premiere commande livree par client ; panier avec port")
    sr = di[di.item_count.eq(1)].merge(rated[["order_id"]], on="order_id", validate="one_to_one")
    top_categories = sr.category.value_counts().head(10).index
    kr_groups = [sr.loc[sr.category.eq(cat), "review_score"].dropna() for cat in top_categories]
    hstat, kp = stats.kruskal(*kr_groups)
    catmeans = sr[sr.category.isin(top_categories)].groupby("category").review_score.mean()
    results.append(dict(id="H20", theme="Produits", hypothese="Les distributions des notes different entre les dix categories les plus frequentes",
        resultat=f"Notes moyennes de {fmt(catmeans.min(),2)} a {fmt(catmeans.max(),2)} ; H={fmt(hstat,2)}",
        conclusion="A calculer", population="Commandes mono-article, avis apres reception, premiere admissible par client",
        n_a=sum(map(len, kr_groups)), n_b=np.nan, effect=hstat, ci_low=np.nan, ci_high=np.nan,
        p_value=kp, methode="Kruskal-Wallis, omnibus", direction=1,
        limite="Test global des distributions ; ne designe pas les paires differentes ; categories selectionnees par volume"))
    one = di[di.item_count.eq(1)].merge(payd[["order_id"]], on="order_id", validate="one_to_one")
    corr("H21", "Logistique", "Les articles plus lourds ont des frais de port plus eleves", one,
         "product_weight_g", "freight_value", 1, "Commandes mono-article ; poids, taille, categorie et distance non ajustes")
    corr("H22", "Produits", "Davantage de photos produit est associe a une meilleure note", sr,
         "product_photos_qty", "review_score", 1, "Avis de commande, pas note produit ; mono-article, photos observees sans historique")
    compare("H23", "Satisfaction", "Les avis avec commentaire ecrit ont une note plus faible", rated,
            rated.has_comment.eq(1), "review_score", ["Commentaire", "Sans commentaire"], -1,
            base_limit + " ; biais de participation, aucune analyse semantique du texte")
    e = first[first.eligible_postdelivery_90.eq(1) & first.is_late.notna()].copy()
    compare("H24", "Fidelisation", "Un premier achat livre en retard est associe a moins de reachat apres reception a 90 jours", e,
            e.is_late.eq(1), "repeat_after_delivery_90", ["Retard initial", "A l'heure initial"], -1,
            "Fenetre egale de 90 jours apres reception initiale ; clients avec suivi complet ; achats hors extrait invisibles ; association seulement")
    recon = d[d.payment_gap.notna()]
    mismatch = recon.payment_gap.abs().gt(.010001).sum()
    desc("H25", "Qualite", "Les paiements concordent avec articles+port a 0,01 BRL pres pour au moins 99 % des commandes livrees",
         f"{mismatch} ecarts sur {len(recon)} ; concordance {pct(1-mismatch/len(recon))}", 1-mismatch/len(recon) >= .99,
         "Commandes livrees avec montants disponibles, periode principale", "Ne prouve pas une comptabilite nette : remboursements et frais absents")
    corr("H26", "Logistique", "Une preparation plus longue est associee a davantage de retard", single,
         "handoff_days", "delay_days", 1, "Preparation = approbation vers transporteur ; valeurs negatives exclues ; delai promis variable")
    result = pd.DataFrame(results).sort_values("id").reset_index(drop=True)
    # Benjamini-Hochberg sur l'ensemble des tests inferentiels, sans selection selon les p-values.
    tested = result.p_value.notna()
    pv = result.loc[tested, "p_value"].to_numpy()
    order = np.argsort(pv)
    ranked = pv[order]*len(pv)/np.arange(1,len(pv)+1)
    adjusted = np.minimum.accumulate(ranked[::-1])[::-1].clip(0,1)
    q = np.empty_like(adjusted)
    q[order] = adjusted
    result.loc[tested, "q_bh"] = q
    for ix in result.index[tested]:
        row = result.loc[ix]
        if row.q_bh >= .05:
            conclusion = "Non concluante"
        elif row.effect * row.direction > 0:
            conclusion = "Association dans le sens attendu"
        else:
            conclusion = "Association dans le sens oppose"
        result.loc[ix, "conclusion"] = conclusion
    save(result, "hypotheses")
    return result, windows, rated


def aggregates(f, detail, rated):
    a = f[f.analysis_period.eq(1)]
    d = a[a.order_status.eq("delivered")]
    di = detail[detail.analysis_period.eq(1) & detail.order_status.eq("delivered")]
    monthly = d.groupby("purchase_month", as_index=False).agg(orders=("order_id", "size"),
        gmv=("item_value", "sum"), aov=("item_value", "mean"), late_rate=("is_late", "mean"), review_score=("review_score", "mean"))
    states = d.groupby("customer_state", as_index=False).agg(orders=("order_id", "size"), gmv=("item_value", "sum"),
        delivery_days=("delivery_days", "mean"), late_rate=("is_late", "mean"), review_score=("review_score", "mean"))
    categories = di.groupby("category", as_index=False).agg(items=("order_item_id", "size"), orders=("order_id", "nunique"), gmv=("price", "sum"))
    seller_order = di[["seller_id", "order_id", "is_late", "review_score"]].drop_duplicates(["seller_id", "order_id"])
    sellers = di.groupby("seller_id", as_index=False).agg(items=("order_item_id", "size"), gmv=("price", "sum"))
    sellers = sellers.merge(seller_order.groupby("seller_id", as_index=False).agg(orders=("order_id", "size"),
        late_n=("is_late", "count"), late_rate=("is_late", "mean"), review_n=("review_score", "count"), review_score=("review_score", "mean")), on="seller_id", validate="one_to_one")
    buckets = pd.cut(rated.delay_days, [-np.inf,0,3,7,14,np.inf], labels=["A l'heure", "1-3 jours", "4-7 jours", "8-14 jours", "15 jours et plus"])
    review_delay = rated.assign(delay_bucket=buckets).groupby("delay_bucket", observed=True).agg(orders=("order_id", "size"),
        review_score=("review_score", "mean"), bad_review_rate=("bad_review", "mean")).reset_index()
    sensitivity = []
    for label, frame in [("Tous avis disponibles",d), ("Avis apres reception, tous clients",d[d.review_answer_timestamp>=d.order_delivered_customer_date]),
                         ("Avis apres reception, un par client (H10)",rated)]:
        for late, group in frame[frame.is_late.notna() & frame.review_score.notna()].groupby("is_late"):
            sensitivity.append({"population":label,"is_late":late,"n":len(group),"review_score":group.review_score.mean(),
                                "bad_review_rate":group.bad_review.mean()})
    save(pd.DataFrame(sensitivity),"review_sensitivity")
    for name, frame in [("monthly", monthly), ("states", states), ("categories", categories), ("sellers", sellers), ("review_delay", review_delay)]:
        save(frame, name)
    return monthly, states, categories, sellers, review_delay


def database(raw, f, detail, latest, gp, first):
    # Construire en memoire puis sauvegarder limite les E/S sur /mnt/c sous WSL.
    mem = sqlite3.connect(":memory:")
    for name, frame in raw.items():
        if name == "geolocation":
            continue
        typed = frame.copy()
        for col in ["price", "freight_value", "payment_value", "order_item_id", "payment_sequential", "payment_installments", "review_score"]:
            if col in typed:
                typed[col] = pd.to_numeric(typed[col])
        typed.to_sql(name, mem, index=False, if_exists="replace")
    for name, frame in [("fact_orders", f), ("fact_items", detail), ("review_latest", latest), ("geo_prefix", gp), ("customer_cohorts", first)]:
        frame.to_sql(name, mem, index=False, if_exists="replace")
    for table, columns in [("orders", "order_id"), ("customers", "customer_id"), ("products", "product_id"),
                           ("sellers", "seller_id"), ("order_items", "order_id,order_item_id"),
                           ("fact_orders", "order_id"), ("review_latest", "order_id"), ("customer_cohorts", "customer_unique_id")]:
        mem.execute(f"CREATE UNIQUE INDEX idx_{table} ON {table} ({columns})")
    mem.commit()
    assert mem.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    with sqlite3.connect(OUT / "olist_portfolio.sqlite") as target:
        mem.backup(target)
    return mem


def figures(monthly, states, categories, sellers, review_delay, cohorts):
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 11, "axes.spines.top": False,
                         "axes.spines.right": False, "figure.facecolor": "#fafbfc", "axes.facecolor": "#fafbfc"})
    def finish(name, title, subtitle):
        plt.gcf().suptitle(title, x=.08, ha="left", fontsize=17, fontweight="bold", color="#17324d")
        plt.gcf().text(.08,.02,subtitle,fontsize=9,color="#526477")
        plt.tight_layout(rect=[.02,.07,.98,.91])
        plt.savefig(FIG/f"{name}.png",dpi=160,bbox_inches="tight")
        plt.close()
    fig, axes = plt.subplots(2,1,figsize=(11,7),sharex=True)
    x = np.arange(len(monthly))
    axes[0].plot(x,monthly.orders,color="#147d92",linewidth=2.5,marker="o",markersize=4)
    axes[0].set_ylabel("Commandes livrees")
    axes[1].bar(x,monthly.gmv/1e6,color="#147d92")
    axes[1].set_ylabel("GMV articles (M BRL)")
    axes[1].set_xticks(x[::2]); axes[1].set_xticklabels(monthly.purchase_month.iloc[::2],rotation=35,ha="right")
    finish("01_ventes", "Ventes livrees : volume et valeur", "Mois d'achat, janvier 2017-aout 2018. GMV hors port ; aucune inference de saisonnalite multiannuelle.")
    fig, ax = plt.subplots(figsize=(10,5))
    ax.bar(review_delay.delay_bucket.astype(str),review_delay.review_score,color=["#147d92"]+["#d77748"]*4)
    ax.set_ylim(0,5.4); ax.set_ylabel("Note moyenne / 5")
    for ix,row in review_delay.iterrows():
        ax.text(ix,row.review_score+.1,f"{row.review_score:.2f}\nn={row.orders:,}",ha="center",fontsize=9)
    finish("02_retards_avis", "Satisfaction selon le retard", "Jours calendaires ; avis apres reception, premiere commande admissible par client. Association, pas causalite.")
    top = categories.nlargest(10,"gmv").sort_values("gmv")
    fig, ax = plt.subplots(figsize=(11,6))
    ax.barh(top.category,top.gmv/1e6,color="#147d92"); ax.set_xlabel("GMV articles livres (M BRL)")
    finish("03_categories", "Les dix categories au plus fort GMV", "Janvier 2017-aout 2018. Les montants d'articles sont additifs ; les nombres de commandes par categorie ne le sont pas.")
    st=states[states.orders>=500].sort_values("late_rate")
    fig, ax = plt.subplots(figsize=(10,6))
    ax.barh(st.customer_state,100*st.late_rate,color="#d77748"); ax.set_xlabel("Commandes en retard (%)")
    finish("04_etats", "Le respect de la promesse varie selon l'Etat client", "Etats avec au moins 500 commandes livrees ; taux parmi les dates valides. Comparaison non ajustee.")
    ranked=sellers.sort_values("gmv",ascending=False)
    fig, ax=plt.subplots(figsize=(9,5))
    ax.plot(np.arange(1,len(ranked)+1)/len(ranked)*100,ranked.gmv.cumsum()/ranked.gmv.sum()*100,color="#147d92",linewidth=2.5)
    ax.axvline(20,color="#8697a8",linestyle="--"); ax.axhline(80,color="#8697a8",linestyle="--")
    ax.set_xlabel("Vendeurs classes par GMV decroissant (%)"); ax.set_ylabel("GMV cumule (%)"); ax.set_xlim(0,100); ax.set_ylim(0,100)
    finish("05_vendeurs", "Concentration du GMV par vendeur", "Vendeurs ayant des articles livres dans la periode principale. Reperes 20 % / 80 % a titre exploratoire.")
    co=cohorts[cohorts.customers>=100]
    fig, ax=plt.subplots(figsize=(11,5))
    ax.bar(co.cohort_month,100*co.repeat_rate_90,color="#147d92"); ax.tick_params(axis="x",rotation=45)
    ax.set_ylabel("Clients avec reachat livre a 90 jours (%)")
    finish("06_reachat", "Reachat avec une fenetre de suivi constante", "Cohortes d'au moins 100 clients, 90 jours complets au 31/08/2018. Premier achat observe ; hors extrait invisible.")


def main():
    print("Lecture et profilage des neuf sources...", flush=True)
    raw, manifest = load_sources()
    print("Construction du modele et controles...", flush=True)
    f, detail, checks, latest, gp = build_model(raw)
    first, cohorts, delivered_all = cohort_analysis(f)
    print("Evaluation des 26 hypotheses...", flush=True)
    hypotheses, windows, rated = hypothesis_analysis(f, detail, first, delivered_all)
    aggs = aggregates(f, detail, rated)
    figures(*aggs, cohorts)
    conn = database(raw, f, detail, latest, gp, first)
    # Reconciliation independante SQL vs pandas.
    sql_n, sql_gmv = conn.execute("SELECT COUNT(*), SUM(item_value) FROM fact_orders WHERE analysis_period=1 AND order_status='delivered'").fetchone()
    d=f[f.analysis_period.eq(1) & f.order_status.eq("delivered")]
    assert sql_n == len(d) and np.isclose(sql_gmv,d.item_value.sum())
    metadata = {"python": platform.python_version(), "pandas":pd.__version__, "numpy":np.__version__,
                "scipy":__import__("scipy").__version__, "matplotlib":matplotlib.__version__,
                "source_min_purchase":str(f.order_purchase_timestamp.min()),
                "source_max_purchase":str(f.order_purchase_timestamp.max()),
                "period_start":"2017-01-01", "period_end_inclusive":"2018-08-31",
                "source_orders":len(f), "delivered_orders":len(d), "gmv":float(d.item_value.sum()),
                "late_rate":float(d.is_late.mean()), "late_timestamp_rate":float(d.is_late_timestamp.mean()),
                "avg_review":float(d.review_score.mean()), "delivery_median":float(d.delivery_days.median()),
                "sql_reconciliation":"passed", "hypothesis_count":len(hypotheses)}
    (DATA/"run_metadata.json").write_text(json.dumps(metadata,indent=2),encoding="utf-8")
    print(json.dumps(metadata,indent=2),flush=True)
    print(hypotheses[["id","resultat","conclusion"]].to_string(index=False),flush=True)
    conn.close()


if __name__ == "__main__":
    main()
