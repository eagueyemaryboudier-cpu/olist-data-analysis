"""Telecharge uniquement les schemas JSON publics de Microsoft pour validation."""
from pathlib import Path
import json
import urllib.request
from urllib.parse import urljoin, urldefrag

OUT = Path(__file__).resolve().parents[1] / 'powerbi/.schemas'
OUT.mkdir(parents=True, exist_ok=True)
BASE = 'https://developer.microsoft.com/json-schemas/fabric/item/report/'
START = [BASE + path for path in [
    'definition/visualContainer/2.7.0/schema.json',
    'definition/page/2.0.0/schema.json',
    'definition/report/3.0.0/schema.json',
    'definition/pagesMetadata/1.0.0/schema.json',
    'definition/versionMetadata/1.0.0/schema.json',
    'definitionProperties/2.0.0/schema.json',
]] + [
    'https://developer.microsoft.com/json-schemas/fabric/pbip/pbipProperties/1.0.0/schema.json',
    'https://developer.microsoft.com/json-schemas/fabric/item/semanticModel/definitionProperties/1.0.0/schema.json',
]
store = {}


def visit(url):
    url = urldefrag(url)[0]
    if url in store:
        return
    if not url.startswith('https://developer.microsoft.com/json-schemas/'):
        raise ValueError(url)
    print(url, flush=True)
    with urllib.request.urlopen(url, timeout=45) as response:
        value = json.load(response)
    store[url] = value
    def walk(obj):
        if isinstance(obj, dict):
            if '$ref' in obj and not obj['$ref'].startswith('#'):
                visit(urljoin(url, obj['$ref']))
            for child in obj.values():
                walk(child)
        elif isinstance(obj, list):
            for child in obj:
                walk(child)
    walk(value)


if __name__ == '__main__':
    for address in START:
        visit(address)
    (OUT / 'schemas.json').write_text(json.dumps(store, indent=2), encoding='utf-8')
    print(f'{len(store)} schemas enregistres')
