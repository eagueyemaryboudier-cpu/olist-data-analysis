"""Construit un projet Power BI natif PBIP/PBIR et son modele semantique.

Les schemas officiels sont caches par fetch_powerbi_schemas.py.
Ouvrir Olist.pbip dans Power BI Desktop, actualiser, puis enregistrer en PBIX.
"""
from pathlib import Path
import json
import re
import uuid
import warnings
import pandas as pd
import numpy as np
from jsonschema import Draft7Validator, RefResolver

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / 'powerbi/Olist'
REPORT = PROJECT / 'Olist.Report'
MODEL = PROJECT / 'Olist.SemanticModel'
DATA = PROJECT / 'Data'
BASE = 'https://developer.microsoft.com/json-schemas/fabric/item/report/'
SC = {
    'visual': BASE+'definition/visualContainer/2.7.0/schema.json',
    'page': BASE+'definition/page/2.0.0/schema.json',
    'report': BASE+'definition/report/3.0.0/schema.json',
    'pages': BASE+'definition/pagesMetadata/1.0.0/schema.json',
    'version': BASE+'definition/versionMetadata/1.0.0/schema.json',
    'pbir': BASE+'definitionProperties/2.0.0/schema.json',
    'pbip': 'https://developer.microsoft.com/json-schemas/fabric/pbip/pbipProperties/1.0.0/schema.json',
    'pbism': 'https://developer.microsoft.com/json-schemas/fabric/item/semanticModel/definitionProperties/1.0.0/schema.json',
}
SCHEMAS = json.loads((ROOT/'powerbi/.schemas/schemas.json').read_text(encoding='utf-8'))
VALIDATED = []


def write(path, value, schema=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    if schema:
        value = {'$schema': SC[schema], **value}
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            resolver = RefResolver(base_uri=SC[schema], referrer=SCHEMAS[SC[schema]], store=SCHEMAS)
            errors = list(Draft7Validator(SCHEMAS[SC[schema]], resolver=resolver).iter_errors(value))
        if errors:
            raise ValueError(str(path)+': '+ '\n'.join(str(e)[:1200] for e in errors[:3]))
        VALIDATED.append(str(path.relative_to(PROJECT)))
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def lit(value):
    if isinstance(value, bool):
        v = 'true' if value else 'false'
    elif isinstance(value, (float,int)):
        v = str(value)+'D'
    else:
        v = "'"+str(value).replace("'","''")+"'"
    return {'expr': {'Literal': {'Value': v}}}


def color(value):
    return {'solid': {'color': lit(value)}}


def obj(**properties):
    return [{'properties': properties}]


def field(table, name, measure=False):
    return {('Measure' if measure else 'Column'): {'Expression': {'SourceRef': {'Entity': table}}, 'Property': name}}


def projection(table, name, measure=False, label=None):
    return {'field': field(table,name,measure), 'queryRef': f'{table}.{name}',
            'nativeQueryRef': name, 'displayName': label or name}


def col(table, name, label=None):
    return projection(table,name,False,label)


def meas(name):
    return projection('FactOrders',name,True)


tables = []
frames = {}
measure_names = set()


def load(name):
    return pd.read_csv(ROOT/'data'/f'{name}.csv', dtype=str)


def add_table(name, frame, dates=(), numbers=(), integers=(), hidden=()):
    DATA.mkdir(parents=True,exist_ok=True)
    frame.to_csv(DATA/f'{name}.csv',index=False,encoding='utf-8-sig')
    frames[name] = frame
    cols=[]
    conversions=[]
    for c in frame.columns:
        dtype='dateTime' if c in dates else 'int64' if c in integers else 'double' if c in numbers else 'string'
        mtype={'dateTime':'type datetime','int64':'Int64.Type','double':'type number','string':'type text'}[dtype]
        column={'name':c,'dataType':dtype,'sourceColumn':c,'summarizeBy':'none'}
        if c in hidden or c.endswith('_id'):
            column['isHidden']=True
        if dtype=='dateTime':
            column['formatString']='dd/MM/yyyy'
        cols.append(column)
        conversions.append('{"'+c+'", '+mtype+'}')
    expression = [
        'let',
        f'    Source = Csv.Document(File.Contents(DataFolder & "{name}.csv"), [Delimiter=",", Encoding=65001, QuoteStyle=QuoteStyle.Csv]),',
        '    Headers = Table.PromoteHeaders(Source, [PromoteAllScalars=true]),',
        '    Blanks = Table.ReplaceValue(Headers, "", null, Replacer.ReplaceValue, Table.ColumnNames(Headers)),',
        '    Typed = Table.TransformColumnTypes(Blanks, {'+', '.join(conversions)+'}, "en-US")',
        'in', '    Typed'
    ]
    table={'name':name,'columns':cols,'partitions':[{'name':name,'mode':'import','source':{'type':'m','expression':expression}}]}
    tables.append(table)
    return table


def add_measure(name, expression, fmt='#,0', folder='01 Performance'):
    tables[0].setdefault('measures',[]).append({'name':name,'expression':expression,'formatString':fmt,'displayFolder':folder})
    measure_names.add(name)


def build_model():
    f=load('fact_orders')
    f['purchase_date']=pd.to_datetime(f.purchase_date).dt.strftime('%Y-%m-%d')
    f['livraison_statut']=np.where(f.is_late.isna(),'Non évaluable',np.where(pd.to_numeric(f.is_late).eq(1),'En retard',"À l'heure"))
    f['commande_type']=np.where(pd.to_numeric(f.seller_count).gt(1),'Plusieurs vendeurs','Un vendeur')
    f.loc[f.seller_count.isna(),'commande_type']='Sans articles'
    selected=['order_id','customer_unique_id','order_status','purchase_date','purchase_month','customer_state',
              'item_value','freight_value','gross_value','payment_total','item_count','seller_count','review_score',
              'bad_review','delivery_days','is_late','analysis_period','payment_type','max_installments','livraison_statut','commande_type']
    add_table('FactOrders',f[selected],dates=['purchase_date'],
        numbers=['item_value','freight_value','gross_value','payment_total','delivery_days'],
        integers=['item_count','seller_count','review_score','bad_review','is_late','analysis_period','max_installments'])
    it=load('fact_items')
    add_table('FactItems',it[['order_id','order_item_id','product_id','seller_id','price','freight_value']],
              numbers=['price','freight_value'],integers=['order_item_id'])
    products=load('dim_products')
    add_table('DimProducts',products[['product_id','category']])
    sellers=load('dim_sellers')
    seller_labels={s:i+1 for i,s in enumerate(sorted(sellers.seller_id))}
    sellers['Vendeur']=sellers.seller_id.map(lambda s: f'Vendeur {seller_labels[s]:04d}')
    add_table('DimSellers',sellers[['seller_id','Vendeur','seller_state']])
    date=pd.date_range('2016-09-01','2018-10-31')
    dt=pd.DataFrame({'Date':date.strftime('%Y-%m-%d'),'Mois':date.strftime('%Y-%m'),'Annee':date.year,'MoisNumero':date.year*100+date.month})
    date_table=add_table('DimDate',dt,dates=['Date'],integers=['Annee','MoisNumero'])
    date_table['dataCategory']='Time'
    next(c for c in date_table['columns'] if c['name']=='Date')['isKey']=True
    next(c for c in date_table['columns'] if c['name']=='Mois')['sortByColumn']='MoisNumero'
    cohorts=load('customer_cohorts')
    cohorts['Reachat']=np.where(pd.to_numeric(cohorts.repeat_90).eq(1),'Avec réachat','Sans réachat')
    add_table('Cohorts',cohorts[['customer_unique_id','cohort_month','customer_state','eligible_90','repeat_90','item_value','Reachat']],
              numbers=['item_value'],integers=['eligible_90','repeat_90'])
    r=f[(f.analysis_period=='1') & (f.order_status=='delivered') & f.is_late.notna() & f.review_score.notna()].copy()
    original=load('fact_orders')
    chronology=pd.to_datetime(original.review_answer_timestamp)>=pd.to_datetime(original.order_delivered_customer_date)
    eligible=original[chronology & original.order_id.isin(r.order_id)].copy()
    eligible=eligible.sort_values(['order_purchase_timestamp','order_id']).drop_duplicates('customer_unique_id')
    delay=pd.to_numeric(eligible.delay_days)
    eligible['Retard']=pd.cut(delay,[-np.inf,0,3,7,14,np.inf],labels=["À l'heure",'1–3 jours','4–7 jours','8–14 jours','15 jours et plus']).astype(str)
    eligible['OrdreRetard']=pd.cut(delay,[-np.inf,0,3,7,14,np.inf],labels=[0,1,2,3,4]).astype(int)
    rat=add_table('ReviewAnalysis',eligible[['order_id','review_score','bad_review','Retard','OrdreRetard']],integers=['review_score','bad_review','OrdreRetard'])
    next(c for c in rat['columns'] if c['name']=='Retard')['sortByColumn']='OrdreRetard'
    add_measure('Commandes','CALCULATE(COUNTROWS(FactOrders), FactOrders[analysis_period] = 1)')
    add_measure('Commandes livrées','CALCULATE([Commandes], FactOrders[order_status] = "delivered")')
    add_measure('GMV articles','CALCULATE(SUM(FactOrders[item_value]), FactOrders[analysis_period] = 1, FactOrders[order_status] = "delivered")','#,0.00 "BRL"')
    add_measure('Panier moyen','DIVIDE([GMV articles], [Commandes livrées])','#,0.00 "BRL"')
    add_measure('Taux annulation','DIVIDE(CALCULATE([Commandes], FactOrders[order_status] = "canceled"), [Commandes])','0.0%')
    logistics='FactOrders[analysis_period] = 1, FactOrders[order_status] = "delivered"'
    add_measure('Livraisons évaluables',f'CALCULATE(COUNT(FactOrders[is_late]), {logistics})',folder='02 Livraison')
    add_measure('Retards',f'CALCULATE(SUM(FactOrders[is_late]), {logistics})',folder='02 Livraison')
    add_measure('Taux de retard','DIVIDE([Retards], [Livraisons évaluables])','0.0%','02 Livraison')
    add_measure('Délai médian',f'CALCULATE(MEDIAN(FactOrders[delivery_days]), {logistics})','0.0 "j"','02 Livraison')
    add_measure('Note moyenne',f'CALCULATE(AVERAGE(FactOrders[review_score]), {logistics})','0.00','02 Livraison')
    add_measure('Avis disponibles',f'CALCULATE(COUNT(FactOrders[review_score]), {logistics})',folder='02 Livraison')
    add_measure('Avis négatifs',f'CALCULATE(SUM(FactOrders[bad_review]), {logistics})',folder='02 Livraison')
    add_measure('Taux avis négatifs','DIVIDE([Avis négatifs], [Avis disponibles])','0.0%','02 Livraison')
    add_measure('Retard États 500+', 'IF([Commandes livrées] >= 500, [Taux de retard])','0.0%','02 Livraison')
    add_measure('Note après réception','AVERAGE(ReviewAnalysis[review_score])','0.00','02 Livraison')
    add_measure('Avis après réception','COUNTROWS(ReviewAnalysis)',folder='02 Livraison')
    add_measure('GMV produits',f'CALCULATE(SUM(FactItems[price]), {logistics})','#,0.00 "BRL"','03 Offre')
    add_measure('Articles livrés',f'CALCULATE(COUNTROWS(FactItems), {logistics})',folder='03 Offre')
    add_measure('Commandes produits',f'CALCULATE(DISTINCTCOUNT(FactItems[order_id]), {logistics})',folder='03 Offre')
    add_measure('Vendeurs actifs',f'CALCULATE(DISTINCTCOUNT(FactItems[seller_id]), {logistics})',folder='03 Offre')
    add_measure('GMV top catégories','VAR Rang = RANKX(ALLSELECTED(DimProducts[category]), [GMV produits], , DESC, DENSE) RETURN IF(Rang <= 10, [GMV produits])','#,0.00 "BRL"','03 Offre')
    add_measure('GMV top vendeurs','VAR Rang = RANKX(ALLSELECTED(DimSellers[Vendeur]), [GMV produits], , DESC, DENSE) RETURN IF(Rang <= 10, [GMV produits])','#,0.00 "BRL"','03 Offre')
    add_measure('Clients éligibles','CALCULATE(COUNTROWS(Cohorts), Cohorts[eligible_90] = 1)',folder='04 Fidélisation')
    add_measure('Clients avec réachat','CALCULATE(SUM(Cohorts[repeat_90]), Cohorts[eligible_90] = 1)',folder='04 Fidélisation')
    add_measure('Réachat à 90 jours','DIVIDE([Clients avec réachat], [Clients éligibles])','0.00%','04 Fidélisation')
    add_measure('Panier initial','CALCULATE(AVERAGE(Cohorts[item_value]), Cohorts[eligible_90] = 1)','#,0.00 "BRL"','04 Fidélisation')
    add_measure('Réachat États 200+','IF([Clients éligibles] >= 200, [Réachat à 90 jours])','0.00%','04 Fidélisation')
    relationships=[]
    for child,ck,parent,pk in [('FactOrders','purchase_date','DimDate','Date'),('FactItems','order_id','FactOrders','order_id'),
                             ('FactItems','product_id','DimProducts','product_id'),('FactItems','seller_id','DimSellers','seller_id'),
                             ('ReviewAnalysis','order_id','FactOrders','order_id')]:
        assert frames[parent][pk].is_unique
        assert frames[child][ck].isin(frames[parent][pk]).all(), (child,parent)
        relationships.append({'name':str(uuid.uuid5(uuid.NAMESPACE_DNS,child+ck+parent)),
            'fromTable':child,'fromColumn':ck,'fromCardinality':'many','toTable':parent,'toColumn':pk,
            'toCardinality':'one','crossFilteringBehavior':'oneDirection','isActive':True})
    folder=str(DATA.resolve()).replace('\\','/')+'/'
    if folder.startswith('/mnt/c/'):
        folder='C:/'+folder[7:]
    model={'name':'Olist','compatibilityLevel':1567,'model':{'culture':'fr-FR','sourceQueryCulture':'en-US',
        'defaultPowerBIDataSourceVersion':'powerBI_V3','tables':tables,'relationships':relationships,
        'expressions':[{'name':'DataFolder','kind':'m','expression':'"'+folder+'" meta [IsParameterQuery=true, Type="Text", IsParameterQueryRequired=true]'}],
        'annotations':[{'name':'PBI_QueryOrder','value':json.dumps(['DataFolder']+[t['name'] for t in tables])}]}}
    write(MODEL/'model.bim',model)
    write(MODEL/'definition.pbism',{'version':'1.0','settings':{}},'pbism')
    return model


visual_manifest=[]


def visual(page, name, typ, title, x,y,w,h, roles=None, sort=None, accent='#147D92', objects=None):
    v={'visualType':typ,'drillFilterOtherVisuals':True,
       'visualContainerObjects':{'title':obj(show=lit(True),text=lit(title),fontSize=lit(12),fontColor=color('#17324D'),titleWrap=lit(True)),
           'background':obj(show=lit(True),color=color('#FFFFFF'),transparency=lit(0)),
           'border':obj(show=lit(True),color=color('#DEE6ED'),radius=lit(8))}}
    if roles:
        v['query']={'queryState':{role:{'projections':projections} for role,projections in roles.items()}}
        if sort:
            v['query']['sortDefinition']={'sort':[{'field':sort[0]['field'],'direction':sort[1]}],'isDefaultSort':False}
    v['objects']=objects or {}
    if typ not in ['textbox','slicer','tableEx','card']:
        v['objects'].update({'dataPoint':obj(defaultColor=color(accent)),
            'categoryAxis':obj(fontSize=lit(10)), 'valueAxis':obj(fontSize=lit(10))})
    data={'name':name,'position':{'x':x,'y':y,'z':len(visual_manifest),'width':w,'height':h,'tabOrder':len(visual_manifest)},'visual':v}
    write(REPORT/f'definition/pages/{page}/visuals/{name}/visual.json',data,'visual')
    visual_manifest.append({'page':page,'name':name,'type':typ,'title':title,'x':x,'y':y,'width':w,'height':h})


def textbox(page,name,text,x,y,w,h,size=22,bg='#17324D',fg='#FFFFFF'):
    props={'general':[{'properties':{'paragraphs':[{'textRuns':[{'value':text,'textStyle':{'fontFamily':'Segoe UI','fontSize':f'{size}pt','color':fg}}]}]}}]}
    visual(page,name,'textbox','',x,y,w,h,objects=props)
    path=REPORT/f'definition/pages/{page}/visuals/{name}/visual.json'
    v=json.loads(path.read_text())
    v['visual']['visualContainerObjects']={'title':obj(show=lit(False)), 'background':obj(show=lit(True),color=color(bg),transparency=lit(0)), 'border':obj(show=lit(False))}
    write(path,{k:x for k,x in v.items() if k!='$schema'},'visual')


def page(name,title,subtitle,slicers,cards):
    write(REPORT/f'definition/pages/{name}/page.json',{'name':name,'displayName':title,'displayOption':'FitToPage','width':1440,'height':900,
        'objects':{'background':obj(color=color('#F3F6FA'),transparency=lit(0))}},'page')
    textbox(name,'header_'+name,'OLIST  /  '+title,0,0,1440,76)
    textbox(name,'subtitle_'+name,subtitle,24,80,920,34,10,'#F3F6FA','#526477')
    for idx,(tbl,c,caption) in enumerate(slicers):
        visual(name,f'filter_{name}_{idx}','slicer',caption,24+idx*468,116,452,76,{'Values':[col(tbl,c,caption)]},
            objects={'data':obj(mode=lit('Dropdown'))})
    for idx,(measure,title) in enumerate(cards):
        visual(name,f'card_{name}_{idx}','card',title,24+idx*352,208,336,102,{'Values':[meas(measure)]},
               objects={'labels':obj(fontSize=lit(28),color=color('#17324D')),'categoryLabels':obj(show=lit(False))})


def chart(p,name,typ,title,category,value,slot,descending=False,accent='#147D92'):
    x,y,w,h=[(24,328,688,246),(728,328,688,246),(24,590,688,260),(728,590,688,260)][slot]
    visual(p,name,typ,title,x,y,w,h,{'Category':[category],'Y':[meas(value)]},
           sort=(meas(value),'Descending') if descending else (category,'Ascending'),accent=accent)


def build_report():
    pages=['p01_performance','p02_livraison','p03_offre','p04_fidelisation']
    p=pages[0]
    page(p,'01 Performance','Achats janvier 2017–août 2018 • GMV articles livrés, hors port • BRL',
         [('DimDate','Mois','Mois d’achat'),('FactOrders','customer_state','État client')],
         [('Commandes livrées','Commandes livrées'),('GMV articles','Volume d’affaires articles'),('Panier moyen','Panier moyen hors port'),('Taux annulation','Taux d’annulation')])
    chart(p,'ventes_mois','lineChart','Commandes livrées par mois',col('DimDate','Mois'), 'Commandes livrées',0)
    chart(p,'gmv_mois','clusteredColumnChart','GMV par mois (BRL)',col('DimDate','Mois'),'GMV articles',1)
    chart(p,'gmv_etat','clusteredBarChart','GMV par État client',col('FactOrders','customer_state','État'),'GMV articles',2,True)
    chart(p,'statuts','donutChart','Répartition des statuts de commande',col('FactOrders','order_status','Statut'),'Commandes',3,True)
    p=pages[1]
    page(p,'02 Livraison et avis','Retard en jours calendaires • Les avis avant réception restent dans les KPI globaux',
         [('DimDate','Mois','Mois d’achat'),('FactOrders','customer_state','État client')],
         [('Taux de retard','Livraisons en retard'),('Délai médian','Délai médian'),('Note moyenne','Note moyenne / 5'),('Taux avis négatifs','Avis négatifs (1–2)')])
    chart(p,'retard_mois','lineChart','Taux de retard par mois',col('DimDate','Mois'),'Taux de retard',0,accent='#D77748')
    chart(p,'note_retard','clusteredColumnChart','Note après réception · première commande admissible/client',col('ReviewAnalysis','Retard'),'Note après réception',1)
    chart(p,'retard_etats','clusteredBarChart','Retard par État · au moins 500 commandes livrées sélectionnées',col('FactOrders','customer_state','État'),'Retard États 500+',2,True,'#D77748')
    chart(p,'notes','clusteredColumnChart','Distribution des notes · dernier avis par commande',col('FactOrders','review_score','Note'),'Avis disponibles',3)
    p=pages[2]
    page(p,'03 Produits et vendeurs','Les montants sont additionnés au grain article ; les commandes distinctes ne sont pas additives',
         [('DimProducts','category','Catégorie produit'),('DimSellers','seller_state','État vendeur'),('DimDate','Mois','Mois d’achat')],
         [('GMV produits','GMV de la sélection'),('Articles livrés','Articles livrés'),('Commandes produits','Commandes distinctes'),('Vendeurs actifs','Vendeurs actifs')])
    chart(p,'top_categories','clusteredBarChart','Dix catégories au plus fort GMV dans la sélection',col('DimProducts','category','Catégorie'),'GMV top catégories',0,True)
    chart(p,'top_vendeurs','clusteredBarChart','Dix vendeurs au plus fort GMV dans la sélection',col('DimSellers','Vendeur'),'GMV top vendeurs',1,True)
    chart(p,'gmv_offre_mois','lineChart','Évolution du GMV de la sélection',col('DimDate','Mois'),'GMV produits',2)
    visual(p,'table_categories','tableEx','Détail des catégories · décompte non additif des commandes',728,590,688,260,
           {'Values':[col('DimProducts','category','Catégorie'),meas('GMV produits'),meas('Commandes produits'),meas('Articles livrés')]},sort=(meas('GMV produits'),'Descending'))
    p=pages[3]
    page(p,'04 Fidélisation','Premiers achats observés avant juin 2018 • 90 jours de suivi • Réachat dans cet extrait uniquement',
         [('Cohorts','cohort_month','Cohorte du premier achat'),('Cohorts','customer_state','État client')],
         [('Clients éligibles','Clients éligibles'),('Clients avec réachat','Clients avec réachat'),('Réachat à 90 jours','Réachat à 90 jours'),('Panier initial','Panier articles initial')])
    chart(p,'cohort_rate','lineChart','Taux de réachat à 90 jours par cohorte',col('Cohorts','cohort_month','Cohorte'),'Réachat à 90 jours',0)
    chart(p,'cohort_volume','clusteredColumnChart','Taille des cohortes éligibles',col('Cohorts','cohort_month','Cohorte'),'Clients éligibles',1)
    chart(p,'cohort_etat','clusteredBarChart','Réachat par État · au moins 200 clients éligibles',col('Cohorts','customer_state','État'),'Réachat États 200+',2,True)
    visual(p,'table_cohort','tableEx','Cohortes · taux recalculé sur les totaux',728,590,688,260,
           {'Values':[col('Cohorts','cohort_month','Cohorte'),meas('Clients éligibles'),meas('Clients avec réachat'),meas('Réachat à 90 jours')]},
           sort=(col('Cohorts','cohort_month'),'Ascending'))
    for p in pages:
        textbox(p,'footer_'+p,'Source : Olist / Kaggle • Analyse exploratoire historique • Corrélation ≠ causalité',24,862,1392,26,9,'#F3F6FA','#526477')
    write(REPORT/'definition/pages/pages.json',{'pageOrder':pages,'activePageName':pages[0]},'pages')
    write(REPORT/'definition/version.json',{'version':'2.0.0'},'version')
    write(REPORT/'definition/report.json',{'themeCollection':{'baseTheme':{'name':'CY24SU06','type':'SharedResources',
        'reportVersionAtImport':{'visual':'2.7.0','page':'2.0.0','report':'3.0.0'}}}},'report')
    write(REPORT/'definition.pbir',{'version':'4.0','datasetReference':{'byPath':{'path':'../Olist.SemanticModel'}}},'pbir')
    write(PROJECT/'Olist.pbip',{'version':'1.0','artifacts':[{'report':{'path':'Olist.Report'}}],'settings':{'enableAutoRecovery':True}},'pbip')


def validate_references():
    columns={t['name']:{c['name'] for c in t['columns']} for t in tables}
    def visit(value):
        if isinstance(value,dict):
            for kind in ['Column','Measure']:
                if kind in value and 'Property' in value[kind]:
                    q=value[kind]
                    table=q['Expression']['SourceRef'].get('Entity')
                    if table:
                        assert q['Property'] in (measure_names if kind=='Measure' else columns[table]),q
            for child in value.values(): visit(child)
        elif isinstance(value,list):
            for child in value: visit(child)
    for path in REPORT.glob('definition/pages/*/visuals/*/visual.json'):
        visit(json.loads(path.read_text(encoding='utf-8')))
    # Verifier toutes les references explicites Table[colonne] des mesures DAX.
    for m in tables[0]['measures']:
        for table,colname in re.findall(r'\b(\w+)\[([^\]]+)\]',m['expression']):
            assert colname in columns[table], (m['name'],table,colname)
    for table,frame in frames.items():
        assert len(frame)>0
    summary={'pages':4,'visuals':len(visual_manifest),'data_tables':len(tables),'measures':len(measure_names),
             'schema_validated_files':len(set(VALIDATED)), 'field_references':'passed',
             'relationships':'passed','power_bi_desktop_refresh':'not_yet_validated'}
    write(ROOT/'powerbi/validation_powerbi.json',summary)
    pd.DataFrame(visual_manifest).to_csv(ROOT/'powerbi/visual_manifest.csv',index=False,encoding='utf-8-sig')
    print(json.dumps(summary,indent=2))


if __name__=='__main__':
    build_model()
    build_report()
    validate_references()
