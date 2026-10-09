"""Prépare des avis fictifs préanalysés pour la démo statique (serveur local requis)."""
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent
records = list(csv.DictReader((ROOT/'examples/avis_exemple.csv').open(encoding='utf-8'), delimiter=';'))
extra = [
 ('fr','Le service client a résolu mon problème en une heure.',5),
 ('fr','Le colis est arrivé en retard et le produit est cassé.',1),
 ('fr','Le prix est trop élevé pour cette qualité.',2),
 ('fr','Emballage soigné et livraison rapide, je recommande.',5),
 ('fr','La couleur est différente de celle de la photo.',2),
 ('fr','Je ne suis pas satisfait du remboursement proposé.',1),
 ('fr','La boîte contient trois pièces et une notice.',3),
 ('pt','O atendimento resolveu meu problema rapidamente.',5),
 ('pt','A entrega atrasou e o produto chegou quebrado.',1),
 ('pt','O preço é muito alto para esta qualidade.',2),
 ('pt','Embalagem perfeita e entrega rápida. Recomendo!',5),
 ('pt','A cor é diferente da foto.',2),
 ('pt','Não estou satisfeito com o reembolso.',1),
 ('pt','A caixa contém três peças e um manual.',3),
 ('en','Customer support solved my problem in one hour.',5),
 ('en','Delivery was late and the product arrived broken.',1),
 ('en','The price is too high for this quality.',2),
 ('en','Great packaging and fast delivery. Highly recommended!',5),
 ('en','The color is different from the photo.',2),
 ('en','I am not satisfied with the refund.',1),
 ('en','The box contains three parts and a manual.',3),
]
records += [{'texte':text,'note':str(note),'langue':language} for language,text,note in extra]
request = Request('http://127.0.0.1:8765/api/analyze', json.dumps({'records':records,'mapping':{'text':'texte','rating':'note','engine':'local'}}).encode(), {'Content-Type':'application/json'})
with urlopen(request, timeout=120) as response:
    rows = json.load(response)['rows']
payload = {'description':'Avis fictifs rédigés pour démontrer les fonctions. Aucun résultat métier sur Olist ne peut en être déduit.',
           'generated_at':datetime.now(timezone.utc).isoformat(),
           'model':'onnx-community/twitter-xlm-roberta-base-sentiment-ONNX',
           'model_revision':'3112e85dea04f0019bf01282916588e3c9dd9bc8',
           'rows':[{'id':i+1,'text':r['text'],'rating':r['rating'],'language':r['source']['langue'],
                    'sentiment':r['sentiment'],'themes':r['themes'],'score':r['confidence'],
                    'uncertain':r['uncertain']} for i,r in enumerate(rows)]}
dest=ROOT.parent/'docs'/'data.json'
dest.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
print(f'{len(rows)} avis fictifs analysés et exportés.')
