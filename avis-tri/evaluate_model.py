"""Tests de régression construits pour l'outil, pas un benchmark indépendant."""
import json
import time
from pathlib import Path
from local_model import predict

EXAMPLES = [
 ('fr', 'Je ne suis pas satisfait de cet achat.', 'Négatif'),
 ('fr', 'Je n’ai jamais reçu ma commande.', 'Négatif'),
 ('fr', 'Le produit ne fonctionne plus après deux jours.', 'Négatif'),
 ('fr', 'Service déplorable, personne ne répond à mes messages.', 'Négatif'),
 ('fr', 'Très bon produit, je suis ravi de mon achat.', 'Positif'),
 ('fr', 'La livraison a été rapide et tout est parfait.', 'Positif'),
 ('fr', 'Merci beaucoup, je recommande cette boutique.', 'Positif'),
 ('fr', 'Le colis contient deux articles de couleur bleue.', 'Neutre'),
 ('pt', 'Não gostei, o produto não funciona.', 'Négatif'),
 ('pt', 'Nunca recebi meu pedido, quero meu dinheiro de volta.', 'Négatif'),
 ('pt', 'Péssimo atendimento, não recomendo.', 'Négatif'),
 ('pt', 'Chegou quebrado e ninguém resolveu o problema.', 'Négatif'),
 ('pt', 'Produto excelente, chegou antes do prazo!', 'Positif'),
 ('pt', 'Muito bom, estou muito satisfeita com a compra.', 'Positif'),
 ('pt', 'Adorei! Recomendo a todos.', 'Positif'),
 ('pt', 'O pacote contém dois itens azuis.', 'Neutre'),
 ('en', 'I never received my order.', 'Négatif'),
 ('en', 'The product stopped working after two days.', 'Négatif'),
 ('en', 'Terrible support, nobody answered my messages.', 'Négatif'),
 ('en', 'I am not happy with this purchase.', 'Négatif'),
 ('en', 'Excellent product, I am delighted!', 'Positif'),
 ('en', 'Arrived early and works perfectly.', 'Positif'),
 ('en', 'Thank you, I highly recommend this seller.', 'Positif'),
 ('en', 'The package contains two blue items.', 'Neutre'),
]

if __name__ == '__main__':
    start = time.time()
    result = predict([x[1] for x in EXAMPLES])
    detail = [{'language': lang, 'text': text, 'expected': expected, **output} for (lang,text,expected),output in zip(EXAMPLES,result)]
    report = {'kind': '24 exemples construits, non indépendants ; aucune précision généralisable',
              'total':len(detail), 'correct':sum(r['sentiment']==r['expected'] for r in detail),
              'abstentions':sum(r['sentiment']=='Indéterminé' for r in detail),
              'seconds':round(time.time()-start,2), 'examples':detail}
    Path('MODEL_CHECK.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k!='examples'},ensure_ascii=True))
