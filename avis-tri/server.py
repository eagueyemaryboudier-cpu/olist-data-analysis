"""Application locale de tri d'avis, Python 3.10+, sans dépendances."""
import csv
import sys
import uuid
import io
import json
import re
import unicodedata
import zipfile
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / '.runtime'))
from importers import read_file
import local_model
LIMIT = 100 * 1024 * 1024
MAX_ROWS = 500_000


def normalize(value):
    return ''.join(c for c in unicodedata.normalize('NFKD', str(value).lower()) if not unicodedata.combining(c))


def records_from_rows(rows):
    rows = iter(rows)
    header = next(rows, [])
    names, seen = [], set()
    for i, value in enumerate(header):
        base = str(value).strip() or f'colonne_{i+1}'
        name, n = base, 2
        while name in seen:
            name = f'{base}_{n}'
            n += 1
        names.append(name)
        seen.add(name)
    if len(names) > 200:
        raise ValueError('Maximum : 200 colonnes.')
    result = []
    for row in rows:
        if not any(str(v).strip() for v in row):
            continue
        if len(row) > len(names):
            raise ValueError('Une ligne contient plus de valeurs que l’en-tête. Vérifie le séparateur et le fichier.')
        result.append(dict(zip(names, list(row) + [''] * (len(names) - len(row)))))
        if len(result) > MAX_ROWS:
            raise ValueError('Maximum : 100 000 lignes. Scinde le fichier.')
    return names, result


def parse_file(data, filename):
    ext = Path(filename).suffix.lower()
    if ext == '.xlsx':
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            if sum(f.file_size for f in z.infolist()) > 100 * 1024 * 1024:
                raise ValueError('Classeur décompressé trop volumineux (100 Mo maximum).')
            ns = {'m': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
            def xml(path):
                raw = z.read(path)
                if b'<!DOCTYPE' in raw or b'<!ENTITY' in raw:
                    raise ValueError('XML avec entités non pris en charge.')
                return ET.fromstring(raw)
            shared = []
            if 'xl/sharedStrings.xml' in z.namelist():
                shared = [''.join(si.itertext()) for si in xml('xl/sharedStrings.xml').findall('m:si', ns)]
            sheets = xml('xl/workbook.xml').findall('m:sheets/m:sheet', ns)
            rels = {r.attrib['Id']: r.attrib['Target'] for r in xml('xl/_rels/workbook.xml.rels')}
            if not sheets:
                raise ValueError('Classeur sans feuille.')
            sheet = sheets[0]
            rel = sheet.attrib['{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id']
            target = rels[rel]
            path = target.lstrip('/') if target.startswith('/') else 'xl/' + target
            rows = []
            for row in xml(path).findall('m:sheetData/m:row', ns):
                cells = {}
                for cell in row.findall('m:c', ns):
                    letters = re.match(r'[A-Z]+', cell.attrib.get('r', 'A1')).group()
                    index = 0
                    for letter in letters:
                        index = index * 26 + ord(letter) - 64
                    if index > 200:
                        raise ValueError('Maximum : 200 colonnes.')
                    value = cell.findtext('m:v', '', ns)
                    if cell.attrib.get('t') == 's':
                        value = shared[int(value)]
                    elif cell.attrib.get('t') == 'inlineStr':
                        value = ''.join(cell.find('m:is', ns).itertext())
                    cells[index-1] = value
                rows.append([cells.get(i, '') for i in range(max(cells, default=-1)+1)])
                if len(rows) > MAX_ROWS + 1:
                    raise ValueError('Maximum : 100 000 lignes.')
            columns, records = records_from_rows(rows)
            return columns, records, f'Première feuille : {sheet.attrib["name"]}. Formules : valeurs enregistrées uniquement ; dates Excel conservées telles quelles.'
    try:
        text = data.decode('utf-8-sig')
    except UnicodeDecodeError:
        text = data.decode('utf-16') if data[:2] in (b'\xff\xfe', b'\xfe\xff') else data.decode('cp1252')
    if ext == '.json':
        records = json.loads(text)
        if not isinstance(records, list) or not all(isinstance(row, dict) for row in records):
            raise ValueError('JSON attendu : une liste d’objets, un objet par avis.')
        if len(records) > MAX_ROWS:
            raise ValueError('Maximum : 100 000 lignes.')
        columns = list(dict.fromkeys(k for row in records for k in row))
        if len(columns) > 200:
            raise ValueError('Maximum : 200 colonnes.')
        records = [{k: '' if row.get(k) is None else str(row.get(k, '')) for k in columns} for row in records]
    elif ext in ('.csv', '.tsv', '.txt'):
        try:
            dialect = csv.Sniffer().sniff(text[:20000], delimiters=',;\t|')
        except csv.Error:
            dialect = csv.excel_tab if ext == '.tsv' else csv.excel
        columns, records = records_from_rows(csv.reader(io.StringIO(text, newline=''), dialect, doublequote=True))
    else:
        raise ValueError('Formats acceptés : CSV, TSV, TXT délimité, XLSX et JSON. Convertis les fichiers XLS, PDF ou Word avant import.')
    return columns, records, 'En-têtes lus sur la première ligne ; séparateur détecté automatiquement.'


POSITIVE = 'excellent parfait parfaite super satisfait satisfaite recommande rapide genial impeccable adore amazing great perfect love satisfied recommend bom boa otimo otima excelente perfeito perfeita recomendo satisfeito satisfeita gostei rapido rapida'.split()
NEGATIVE = 'mauvais mauvaise horrible nul nulle casse cassee defectueux defectueuse decevant decu decue retard lent lente arnaque bad broken terrible disappointed awful defective late ruim pessimo pessima quebrado quebrada defeito defeituoso decepcionado atrasado atrasada atraso lento lenta'.split()
THEMES = {
    'Livraison': 'livraison livre livraison livreur transport colis retard delivery shipping delivered package late entrega entregue frete transportadora atraso atrasado correios',
    'Produit / qualité': 'produit qualite casse defectueux taille couleur product quality broken size color produto qualidade quebrado defeito tamanho cor',
    'Prix / paiement': 'prix cher chere tarif paiement remboursement price expensive payment refund preco caro cara pagamento reembolso valor',
    'Service client': 'sav assistance service support vendeur seller atendimento vendedor contato resposta',
    'Emballage': 'emballage emballe packaging packed embalagem embalado caixa',
}


def classify(text):
    tokens = re.findall(r'[a-z]+|[.!?,;:]', normalize(text))
    if not str(text).strip():
        return 'Sans texte', [], [], 'Aucun texte exploitable'
    pos, neg, evidence = 0, 0, []
    for i, token in enumerate(tokens):
        if token not in POSITIVE and token not in NEGATIVE:
            continue
        polarity = 1 if token in POSITIVE else -1
        preceding = []
        for t in reversed(tokens[max(0, i-3):i]):
            if t in {'.', '!', '?', ',', ';', ':', 'mais', 'but', 'mas'}:
                break
            preceding.append(t)
        if any(t in {'pas', 'non', 'not', 'no', 'never', 'nao', 'jamais'} for t in preceding):
            polarity *= -1
        pos += polarity > 0
        neg += polarity < 0
        evidence.append(token)
    sentiment = 'Mixte' if pos and neg else 'Positif' if pos else 'Négatif' if neg else 'Indéterminé'
    themes = [name for name, words in THEMES.items() if set(tokens) & set(words.split())]
    return sentiment, themes, list(dict.fromkeys(evidence)), 'Règles lexicales FR / PT / EN ; à vérifier'


def analyze(records, mapping):
    text_col, title_col, rating_col = (mapping.get(k, '') for k in ('text', 'title', 'rating'))
    if not text_col:
        raise ValueError('Sélectionne une colonne de commentaire.')
    result = []
    counts = {}
    for row in records:
        text = ' '.join(str(row.get(c, '')).strip() for c in dict.fromkeys([title_col, text_col]) if c).strip()
        key = normalize(text).strip()
        counts[key] = counts.get(key, 0) + 1 if key else 0
        sentiment, themes, evidence, method = classify(text)
        try:
            rating = float(str(row.get(rating_col, '')).replace(',', '.')) if rating_col else None
            if rating is not None and (rating != rating or abs(rating) == float('inf')):
                rating = None
        except (ValueError, TypeError):
            rating = None
        if mapping.get('themes'):
            themes = [name for name, terms in mapping['themes'].items() if any(re.search(r'(?<!\w)' + re.escape(normalize(term).strip()) + r'(?!\w)', normalize(text)) for term in terms if term.strip())]
        result.append({'source': row, 'text': text, 'sentiment': sentiment, 'themes': themes, 'evidence': evidence, 'rating': rating, 'method': method, 'key': key, 'confidence': None, 'uncertain': sentiment == 'Indéterminé', 'corrected': False})
    if mapping.get('engine') == 'local':
        nonempty = [r for r in result if r['text'].strip()]
        if nonempty:
            predictions = local_model.predict([r['text'] for r in nonempty])
            for row, prediction in zip(nonempty, predictions):
                row.update(prediction)
                row['evidence'] = []
                row['method'] = 'XLM-T multilingue ONNX local ; thèmes par règles configurables'
    for row in result:
        row['duplicate'] = bool(row['key'] and counts[row['key']] > 1)
        del row['key']
    return result


class Handler(BaseHTTPRequestHandler):
    def send_json(self, body, status=200):
        data = json.dumps(body, ensure_ascii=False, allow_nan=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path.startswith('/exports/'):
            name = unquote(self.path.removeprefix('/exports/'))
            if not re.fullmatch(r'[a-f0-9]{32}_[a-zA-Z0-9_-]+\.(csv|json)', name):
                self.send_error(404)
                return
            path = ROOT / 'exports' / name
            if not path.is_file():
                self.send_error(404)
                return
            data = path.read_bytes()
            self.send_response(200)
            self.send_header('Content-Type', 'text/csv; charset=utf-8' if name.endswith('.csv') else 'application/json; charset=utf-8')
            self.send_header('Content-Disposition', f'attachment; filename="{name[33:]}"')
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(data)
            return
        if self.path == '/api/config':
            self.send_json({'local_model': local_model.available(), 'max_bytes': LIMIT, 'max_rows': MAX_ROWS})
            return
        if self.path not in {'/', '/app.js'}:
            self.send_error(404)
            return
        data = (ROOT / ('app.js' if self.path == '/app.js' else 'index.html')).read_bytes()
        self.send_response(200)
        self.send_header('Content-Type', 'text/javascript; charset=utf-8' if self.path == '/app.js' else 'text/html; charset=utf-8')
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        # Refuse les appels issus d'un autre site et le DNS rebinding.
        host = self.headers.get('Host', '')
        if host not in {'127.0.0.1:8765', 'localhost:8765'} or self.headers.get('Origin', 'http://' + host) != 'http://' + host:
            self.send_json({'error': 'Origine non autorisée.'}, 403)
            return
        try:
            length = int(self.headers.get('Content-Length', 0))
            if length > LIMIT or length < 0:
                raise ValueError('Maximum : 100 Mo par requête.')
            data = self.rfile.read(length)
            if self.path == '/api/import':
                options = json.loads(unquote(self.headers.get('X-Options', '%7B%7D')))
                self.send_json(read_file(data, unquote(self.headers.get('X-Filename', 'avis.csv')), options))
            elif self.path == '/api/demo':
                path = ROOT.parent / 'olist_order_reviews_dataset.csv'
                if not path.exists():
                    raise ValueError('Fichier Olist absent. Importe le fichier de ton choix.')
                self.send_json(read_file(path.read_bytes(), path.name))
            elif self.path == '/api/export':
                body = json.loads(data)
                ext = body.get('format')
                if ext not in {'csv', 'json'} or not isinstance(body.get('content'), str):
                    raise ValueError('Export invalide.')
                base = re.sub(r'[^a-zA-Z0-9_-]', '_', Path(str(body.get('name', 'avis'))).stem)[:80] or 'avis'
                name = uuid.uuid4().hex + '_' + base + '_avis_filtres.' + ext
                folder = ROOT / 'exports'
                folder.mkdir(exist_ok=True)
                (folder / name).write_bytes(body['content'].encode('utf-8'))
                self.send_json({'url': '/exports/' + name, 'filename': name[33:]})
            elif self.path == '/api/analyze':
                body = json.loads(data)
                if len(body['records']) > MAX_ROWS:
                    raise ValueError('Maximum : 500 000 lignes.')
                self.send_json({'rows': analyze(body['records'], body['mapping'])})
            else:
                self.send_json({'error': 'Adresse inconnue.'}, 404)
        except Exception as exc:
            self.send_json({'error': str(exc) or 'Fichier illisible.'}, 400)


if __name__ == '__main__':
    print('Tri des avis : http://127.0.0.1:8765 — Ctrl+C pour arrêter', flush=True)
    ThreadingHTTPServer(('127.0.0.1', 8765), Handler).serve_forever()
