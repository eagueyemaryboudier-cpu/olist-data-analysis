import io
import unittest
import zipfile
from server import parse_file, classify, analyze


class AppTests(unittest.TestCase):
    def test_csv_quotes_multiline_and_encoding(self):
        cols, rows, _ = parse_file('texte;note\r\n"Très bien; reçu\nmerci";5\r\n'.encode('cp1252'), 'avis.csv')
        self.assertEqual(cols, ['texte', 'note'])
        self.assertEqual(rows[0]['texte'], 'Très bien; reçu\nmerci')

    def test_duplicate_headers_and_bad_rows(self):
        cols, _, _ = parse_file(b'text,text\na,b', 'a.csv')
        self.assertEqual(cols, ['text', 'text_2'])
        with self.assertRaises(ValueError):
            parse_file(b'a,b\nx,y,z', 'a.csv')

    def test_csv_embedded_quotes(self):
        _, rows, _ = parse_file(b'text,note\n"a ""quoted, phrase""",5', 'a.csv')
        self.assertEqual(rows[0]['text'], 'a "quoted, phrase"')

    def test_json_and_rejected_shape(self):
        _, rows, _ = parse_file(b'[{"text":"hello","note":null}]', 'a.json')
        self.assertEqual(rows[0]['note'], '')
        with self.assertRaises(ValueError):
            parse_file(b'{"text":"hello"}', 'a.json')

    def test_sentiment_negation_and_empty(self):
        self.assertEqual(classify('Não recomendo, produto ruim')[0], 'Négatif')
        self.assertEqual(classify('pas satisfait')[0], 'Négatif')
        self.assertEqual(classify('great but broken')[0], 'Mixte')
        self.assertEqual(classify('')[0], 'Sans texte')
        self.assertEqual(classify('information inconnue')[0], 'Indéterminé')
        self.assertIn('Livraison', classify('entrega rapida')[1])

    def test_rating_independent_and_duplicates(self):
        rows = analyze([{'t':'ruim','r':'5'}, {'t':'RUIM','r':'NaN'}, {'t':'','r':'1'}], {'text':'t','rating':'r'})
        self.assertEqual(rows[0]['sentiment'], 'Négatif')
        self.assertTrue(rows[0]['duplicate'])
        self.assertIsNone(rows[1]['rating'])
        self.assertEqual(rows[2]['sentiment'], 'Sans texte')
        self.assertFalse(rows[2]['duplicate'])

    def test_xlsx_sparse_cells_first_sheet(self):
        b = io.BytesIO()
        with zipfile.ZipFile(b, 'w') as z:
            z.writestr('xl/workbook.xml', '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Avis" r:id="rId1"/></sheets></workbook>')
            z.writestr('xl/_rels/workbook.xml.rels', '<Relationships><Relationship Id="rId1" Target="worksheets/sheet1.xml"/></Relationships>')
            z.writestr('xl/worksheets/sheet1.xml', '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData><row><c r="A1" t="inlineStr"><is><t>texte</t></is></c><c r="B1" t="inlineStr"><is><t>note</t></is></c></row><row><c r="B2"><v>4</v></c></row></sheetData></worksheet>')
        cols, rows, info = parse_file(b.getvalue(), 'a.xlsx')
        self.assertEqual(rows, [{'texte':'','note':'4'}])
        self.assertIn('Avis', info)


if __name__ == '__main__':
    unittest.main()
