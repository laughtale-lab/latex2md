import json
import tempfile
import unittest
from pathlib import Path

from latex2md.htmlaudit import HtmlAuditError, audit_html


class HtmlAuditTests(unittest.TestCase):
    def fixture(self, root: Path):
        html=root/'html';html.mkdir()
        (html/'index.html').write_text(
            '<h1 id="chap-one">One</h1><a href="two.html#sec-two">two</a>', encoding='utf8')
        (html/'two.html').write_text(
            '<h2 id="sec-two">Two</h2><div id="key-alpha"></div>'
            '<a href="index.html#chap-one">one</a>', encoding='utf8')
        report=root/'conversion-report.json'
        report.write_text(json.dumps({'targets':{
            'chap-one': {'name':'chap-one','page':'README.md','number':'1','kind':'chapter',
                         'display':'1','render':'heading','source':'fixture:1'},
            'sec-two': {'name':'sec-two','page':'two.md','number':'1.1','kind':'section',
                        'display':'1.1','render':'heading','source':'fixture:2'},
            'key-alpha': {'name':'key-alpha','page':'two.md','number':'','kind':'keyword',
                          'display':'alpha','render':'raw-html','source':'fixture:3'},
        }}),encoding='utf8')
        return report,html

    def test_valid_site(self):
        with tempfile.TemporaryDirectory() as d:
            report,html=self.fixture(Path(d))
            result=audit_html(report,html,site_prefix='')
            self.assertEqual(result['targets'],3)

    def test_heading_target_must_be_real_heading(self):
        with tempfile.TemporaryDirectory() as d:
            report,html=self.fixture(Path(d))
            p=html/'index.html'
            p.write_text('<div id="chap-one">One</div><a href="two.html#sec-two">two</a>',encoding='utf8')
            with self.assertRaisesRegex(HtmlAuditError,'must render as h1'):
                audit_html(report,html,site_prefix='')

    def test_script_target_requires_listing_caption_semantics(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);report,html=self.fixture(root)
            data=json.loads(report.read_text())
            data['targets']['script-one']={
                'name':'script-one','page':'two.md','number':'1','kind':'script',
                'display':'2-1','render':'raw-html','source':'fixture:4'
            }
            report.write_text(json.dumps(data),encoding='utf8')
            p=html/'two.html';p.write_text(p.read_text()+'<div id="script-one">Script 2-1</div>',encoding='utf8')
            with self.assertRaisesRegex(HtmlAuditError,'listing-caption'):
                audit_html(report,html,site_prefix='')
            p.write_text(p.read_text().replace('<div id="script-one">','<div class="listing-caption" id="script-one">'),encoding='utf8')
            audit_html(report,html,site_prefix='')

    def test_missing_expected_target_fails(self):
        with tempfile.TemporaryDirectory() as d:
            report,html=self.fixture(Path(d))
            (html/'two.html').write_text('<h2>Two</h2><div id="key-alpha"></div>',encoding='utf8')
            with self.assertRaisesRegex(HtmlAuditError,'sec-two'):
                audit_html(report,html,site_prefix='')

    def test_duplicate_expected_target_fails(self):
        with tempfile.TemporaryDirectory() as d:
            report,html=self.fixture(Path(d))
            p=html/'two.html';p.write_text(p.read_text()+ '<span id="key-alpha"></span>',encoding='utf8')
            with self.assertRaisesRegex(HtmlAuditError,'exactly once'):
                audit_html(report,html,site_prefix='')

    def test_broken_fragment_fails(self):
        with tempfile.TemporaryDirectory() as d:
            report,html=self.fixture(Path(d))
            p=html/'index.html';p.write_text('<h1 id="chap-one">One</h1><a href="two.html#missing">bad</a>',encoding='utf8')
            with self.assertRaisesRegex(HtmlAuditError,'fragment'):
                audit_html(report,html,site_prefix='')

    def test_missing_resource_fails(self):
        with tempfile.TemporaryDirectory() as d:
            report,html=self.fixture(Path(d))
            p=html/'index.html';p.write_text(p.read_text()+'<img src="assets/missing.png">',encoding='utf8')
            with self.assertRaisesRegex(HtmlAuditError,'missing local'):
                audit_html(report,html,site_prefix='')

    def test_missing_css_resource_fails(self):
        with tempfile.TemporaryDirectory() as d:
            report,html=self.fixture(Path(d))
            (html/'theme.css').write_text('body { background:url("images/missing.svg"); }',encoding='utf8')
            with self.assertRaisesRegex(HtmlAuditError,'CSS resource'):
                audit_html(report,html,site_prefix='')
            (html/'images').mkdir();(html/'images/missing.svg').write_text('<svg/>',encoding='utf8')
            audit_html(report,html,site_prefix='')

    def test_explicit_deferred_resource(self):
        with tempfile.TemporaryDirectory() as d:
            report,html=self.fixture(Path(d))
            p=html/'index.html';p.write_text(p.read_text()+'<a href="diabat.pdf">PDF</a>',encoding='utf8')
            audit_html(report,html,site_prefix='',allow_missing={'diabat.pdf'})

if __name__=='__main__':
    unittest.main()
