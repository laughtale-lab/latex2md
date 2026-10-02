import json
from pathlib import Path
import tempfile
import unittest
from latex2md.html_audit import audit


class RenderedAnchorAuditTests(unittest.TestCase):
    def test_html_id_provenance_and_duplicate_detection(self):
        with tempfile.TemporaryDirectory() as d:
            book = Path(d)
            (book/'book').mkdir()
            (book/'conversion-report.json').write_text(json.dumps({
                'labels': {'sec-stdout': {'page': 'installation.md'},
                           'key-test': {'page': 'installation.md'}},
                'citations': ['work']
            }))
            page = book/'book/installation.html'
            page.write_text('<h3 id="sec-stdout">stdout</h3><div id="key-test"></div>')
            ref = book/'book/references.html'
            ref.write_text('<div id="cite-work"></div>')
            self.assertEqual(audit(book), (2, 1))
            page.write_text('<h3 id="other">stdout</h3><div id="key-test"></div>')
            with self.assertRaisesRegex(ValueError, 'sec-stdout.*found 0'):
                audit(book)
            page.write_text('<h3 id="sec-stdout">stdout</h3><span id="sec-stdout"></span>'
                            '<div id="key-test"></div>')
            with self.assertRaisesRegex(ValueError, 'sec-stdout.*found 2'):
                audit(book)
            page.write_text('<h3 id="sec-stdout">stdout</h3><div id="key-test"></div>')
            ref.write_text('<p>No bibliography anchor</p>')
            with self.assertRaisesRegex(ValueError, 'cite-work.*found 0'):
                audit(book)

    def test_rejects_missing_and_escaping_report_page(self):
        with tempfile.TemporaryDirectory() as d:
            book = Path(d)
            (book/'book').mkdir()
            report=book/'conversion-report.json'
            report.write_text(json.dumps({'labels': {'key': {'page': '../outside.md'}}, 'citations': []}))
            with self.assertRaisesRegex(ValueError, 'Unsafe reported page'):
                audit(book)
            report.write_text(json.dumps({'labels': {'key': {'page': 'missing.md'}}, 'citations': []}))
            with self.assertRaisesRegex(ValueError, 'Rendered page missing'):
                audit(book)


if __name__ == '__main__':
    unittest.main()
