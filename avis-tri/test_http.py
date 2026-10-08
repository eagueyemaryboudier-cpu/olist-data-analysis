"""Tests d'intégration contre le serveur local déjà démarré."""
import json
import unittest
from urllib.request import Request, urlopen
from urllib.error import HTTPError

BASE = 'http://127.0.0.1:8765'


def post(path, obj):
    request = Request(BASE+path, json.dumps(obj).encode(), {'Content-Type':'application/json'})
    with urlopen(request, timeout=120) as response:
        return json.load(response)


class HTTPTests(unittest.TestCase):
    def test_model_and_long_review(self):
        text = 'I love this product. ' * 100 + 'This is a terrible product. ' * 100
        result = post('/api/analyze', {'records':[{'text':text}], 'mapping':{'text':'text','engine':'local'}})
        self.assertEqual(result['rows'][0]['chunks'], 5)
        self.assertEqual(result['rows'][0]['sentiment'], 'Mixte')
        self.assertEqual(result['rows'][0]['text'], text.strip())

    def test_export_saved_and_downloadable(self):
        content = '\ufeff"texte";"sentiment"\r\n"Très bien";"Positif"'
        result = post('/api/export', {'content':content,'format':'csv','name':'verification'})
        with urlopen(BASE+result['url']) as response:
            self.assertIn('attachment', response.headers['Content-Disposition'])
            self.assertEqual(response.read().decode('utf-8'), content)

    def test_import_api(self):
        req = Request(BASE+'/api/import', 'texte;note\nTrès bien;5'.encode(), {'X-Filename':'test.csv','X-Options':'%7B%22delimiter%22%3A%22%3B%22%7D'})
        with urlopen(req) as response:
            data = json.load(response)
        self.assertEqual(data['records'][0]['texte'], 'Très bien')

    def test_cross_origin_rejected(self):
        req = Request(BASE+'/api/analyze', b'{}', {'Origin':'https://example.org'})
        with self.assertRaises(HTTPError) as error:
            urlopen(req)
        self.assertEqual(error.exception.code,403)


if __name__ == '__main__':
    unittest.main()
