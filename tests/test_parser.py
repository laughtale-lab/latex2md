import unittest
from latex2md.parser import Reader, ParseError, plain
from latex2md.bib import parse_bib

class StructuralParserTests(unittest.TestCase):
    def parse(self, tex): return Reader(tex,'fixture.tex').parse()

    def test_nested_braces_and_nine_keyword_arguments(self):
        nodes=self.parse(r'\keyword{k}{name}{with {nested {description}}}{N}{T}{D}{O}{S}{x}')
        self.assertEqual(len(nodes),1)
        self.assertEqual(nodes[0].value,'keyword')
        self.assertEqual(len(nodes[0].args),9)
        self.assertEqual(plain(nodes[0].args[2]),'with {nested {description}}')

    def test_includes_are_structural(self):
        result=self.parse(r'\input{chapters/intro} \ref{sec:test}')
        self.assertEqual([n.kind for n in result],['macro','text','macro'])
        self.assertEqual(plain(result[0].args[0]),'chapters/intro')

    def test_math_and_listings_do_not_interfere(self):
        result=self.parse(r'$x^2$ \(\frac{1}{2}\) \begin{lst-script}'+ '\n'+
                          '$diabat-fphd\n# % { is literal\n\\foo\n' + r'\end{lst-script}')
        self.assertEqual(result[0].kind,'math')
        self.assertEqual(result[2].kind,'math')
        self.assertEqual(result[4].kind,'verbatim')
        self.assertIn('% { is literal',result[4].children[0].value)

    def test_comment_unmatched_braces_cannot_break_parsing(self):
        result=self.parse('a % } } ignore\n\\textbf{b}')
        self.assertEqual(result[-1].value,'textbf')

    def test_missing_environment_fails(self):
        with self.assertRaisesRegex(ParseError,'missing'):
            self.parse(r'\begin{enumerate}\item something')

    def test_unknown_nested_argument_does_not_leak(self):
        result=self.parse(r'\fancyhead[L]{\nouppercase{\leftmark}}')
        self.assertEqual(len(result),1)
        self.assertEqual(result[0].value,'fancyhead')

    def test_optional_short_chapter_title(self):
        result=self.parse(r'\chapter[Short]{Long\texttt{title}}')
        self.assertEqual(result[0].option,'Short')
        self.assertEqual(result[0].value,'chapter')

class BibTests(unittest.TestCase):
    def test_nested_bib_fields(self):
        bib='@article{a, author={First {Nested} and Second}, title={An {Important} Paper}, doi={10.1/alpha}}'
        item=parse_bib(bib,'fixture.bib')['a']
        self.assertEqual(item.fields['title'],'An {Important} Paper')
        self.assertEqual(item.fields['doi'],'10.1/alpha')
    def test_duplicate_key_fails(self):
        with self.assertRaises(ParseError):
            parse_bib('@article{x,title={a}}\n@misc{x, title={b}}','test')

if __name__=='__main__': unittest.main()
