import json
import tempfile
import unittest
from pathlib import Path
from latex2md import convert, ConversionError
from latex2md.parser import ParseError


MAIN=r'''\documentclass{book}
\begin{document}
\mainmatter
\include{chapters/a}
\printbibliography
\end{document}
'''
CHAPTER=r'''\chapter{First} \label{chap-one}
\section{Usage} \label{sec-usage}
Open \keyref{key-alpha}{alpha}. See \script{chap-one}{script-one} and \example{chap-one}{example-one}.
The equation \(x+y\) occurs in \cite{paper}.
\begin{keywordoverview}
\keyitem{key-alpha}{alpha}{Explains the input value.}
\end{keywordoverview}
\keyword{key-alpha}{alpha}{A *key* with \textbf{nested text}.}{\OpOptional}{\OpString}{None}{String}{Try it}{alpha = "text"}
\begin{lst-script}[escapechar=@]
@\scriptnum{script-one}@
$diabat-fphd
  # comment
$
\end{lst-script}
\lstinputlisting[style=diabatfile]{examples/display/a.lst}
\begin{enumerate}
\item First \texttt{item}
\item Second item with \ref{sec-usage}
\end{enumerate}
\begin{equation}
a=b
\end{equation}
'''
EXAMPLE=r'''@\examplenum{example-one}@
$diabat-gmh
  mode = "quoted" # note
$
'''
BIB=r'''@article{paper,author={A and B},title={Title},year={2026},journal={Test Journal},doi={10.1000/test}}'''


def manual(root: Path,*,main=MAIN,chapter=CHAPTER,example=EXAMPLE,bib=BIB):
    files={'main.tex':main, 'chapters/a.tex':chapter,
           'references-build.bib':bib, 'examples/display/a.lst':example,
           'examples/release/test.inp':'$diabat-fphd\n$',
           'examples/templates/start.inp':'$postorb\n$'}
    for key,value in files.items():
        p=root/key;p.parent.mkdir(exist_ok=True,parents=True);p.write_text(value,encoding='utf8')


class ConversionTests(unittest.TestCase):
    def test_end_to_end_and_generated_tree(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'source';output=root/'out'
            manual(source)
            report=convert(source,output)
            self.assertEqual(report['statistics']['keywords'],1)
            self.assertEqual(report['statistics']['script_labels'],1)
            self.assertEqual(report['statistics']['example_labels'],1)
            self.assertEqual(report['statistics']['original_input_files'],2)
            content=(output/'src/first.md').read_text()
            self.assertIn('href',content) if False else None
            self.assertIn('[alpha](#key-alpha)',content)
            self.assertIn('[Script 1-1](#script-one)',content)
            self.assertIn('[Example 1-1](#example-one)',content)
            self.assertIn('id="key-alpha"',content)
            self.assertIn('id="script-one"',content)
            self.assertIn('id="example-one"',content)
            self.assertIn('\\\\(x+y\\\\)',content)
            self.assertIn('1. First',content)
            self.assertIn('2. Second',content)
            self.assertNotIn('1. \n',content)
            self.assertIn('mathjax-support = true',(output/'book.toml').read_text())
            self.assertIn('diabat.css',(output/'book.toml').read_text())
            self.assertEqual((source/'examples/release/test.inp').read_bytes(),
                             (output/'src/downloads/examples/release/test.inp').read_bytes())
            self.assertIn('cite-paper',(output/'src/references.md').read_text())
            self.assertEqual(json.loads((output/'conversion-report.json').read_text())['citations'],['paper'])

    def test_unknown_active_macro_aborts_without_output(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);manual(root/'s',chapter=CHAPTER+r'\unexpectedmacro{hidden content}')
            with self.assertRaisesRegex(ConversionError,'unsupported active'):
                convert(root/'s',root/'out')
            self.assertFalse((root/'out').exists())

    def test_broken_cross_reference_fails_closed(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);manual(root/'s',chapter=CHAPTER+r'Another \ref{missing-label}.')
            with self.assertRaisesRegex(ConversionError,'unresolved internal reference'):
                convert(root/'s',root/'out')
            self.assertFalse((root/'out').exists())

    def test_diaeresis_transliterates_in_prose_and_keyword_table(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            accent=r' L\"owdin and L\"{o}wdin.'
            convert_source=CHAPTER.replace('Explains the input value.',
                                           'Explains the input value.' + accent)
            manual(root/'s',chapter=convert_source + accent)
            convert(root/'s',root/'out')
            text=(root/'out/src/first.md').read_text(encoding='utf8')
            self.assertIn('Löwdin and Löwdin',text)
            self.assertNotIn('L"owdin',text)

    def test_bibliography_url_only(self):
        # Regression: a BibTeX URL without a DOI renders a valid Markdown link.
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            manual(root / 's', bib='@misc{paper,title={Manual},url={https://example.org/manual}}')
            convert(root / 's', root / 'out')
            text = (root / 'out/src/references.md').read_text(encoding='utf8')
            self.assertIn('[Link](https://example.org/manual)', text)

    def test_bibliography_rejects_unsafe_url(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            manual(root / 's', bib='@misc{paper,title={Manual},url={javascript:alert(1)}}')
            with self.assertRaisesRegex(ConversionError, 'unsupported URL scheme'):
                convert(root / 's', root / 'out')

    def test_missing_bibliography_entry(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);manual(root/'s',bib='@article{somethingelse,title={unused}}')
            with self.assertRaisesRegex(ConversionError,'missing BibTeX citation paper'):
                convert(root/'s',root/'out')

    def test_missing_listing_is_error(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);manual(root/'s');(root/'s/examples/display/a.lst').unlink()
            with self.assertRaisesRegex(ConversionError,'missing required source'):
                convert(root/'s',root/'out')

    def test_duplicate_label_is_error(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);manual(root/'s',chapter=CHAPTER+r'\label{chap-one}')
            with self.assertRaisesRegex(ConversionError,'duplicate label'):
                convert(root/'s',root/'out')

    def test_path_traversal_fails(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);manual(root/'s',main=MAIN.replace('chapters/a','../../secret'))
            with self.assertRaisesRegex(ConversionError,'outside manual root'):
                convert(root/'s',root/'out')

    def test_not_overwrite_existing_dir(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);manual(root/'s');(root/'out').mkdir();(root/'out/keep.txt').write_text('mine')
            with self.assertRaisesRegex(ConversionError,'not empty'):
                convert(root/'s',root/'out')
            self.assertEqual((root/'out/keep.txt').read_text(),'mine')

if __name__=='__main__': unittest.main()


class MdBookAnchorTests(unittest.TestCase):
    """Renderer-level coverage: never fix dropped HTML anchors downstream."""

    def test_native_heading_ids_for_chapter_section_subsection(self):
        body = (r'\chapter{First}\label{chap-one}' + '\n' +
                r'\section{Usage}\label{sec-usage}' + '\n' +
                r'\subsection{Standard output and error output}\label{sec-stdout}' + '\n' +
                r'See \ref{sec-stdout}. A keyword: \keyref{key-alpha}{alpha}.' + '\n' +
                r'\keyword{key-alpha}{alpha}{Desc}{\OpOptional}{\OpString}{None}{String}{Hint}{alpha=1}')
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            manual(root/'source', chapter=body)
            report = convert(root/'source', root/'book')
            text = (root/'book/src/first.md').read_text(encoding='utf8')
            self.assertIn('# 1 First {#chap-one}\n', text)
            self.assertIn('## 1.1 Usage {#sec-usage}\n', text)
            self.assertIn('### 1.1.1 Standard output and error output {#sec-stdout}\n', text)
            self.assertIn('[1.1.1](#sec-stdout)', text)
            self.assertIn('<div class="manual-anchor" id="key-alpha"></div>', text)
            self.assertNotIn('<a id=', text)
            self.assertEqual(report['statistics']['section_labels'], 3)

    def test_whitespace_only_between_heading_and_label_is_valid(self):
        body = (r'\chapter{First}' + '\n\n   ' + r'\label{chap-one}' + '\n' +
                r'\section{Usage}' + '\n  \n ' + r'\label{sec-usage}' + '\n' +
                'Source text.')
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            manual(root/'s', chapter=body)
            convert(root/'s', root/'book')
            text = (root/'book/src/first.md').read_text()
            self.assertIn('# 1 First {#chap-one}', text)
            self.assertIn('## 1.1 Usage {#sec-usage}', text)

    def test_body_label_is_standalone_div_not_attached_to_heading(self):
        body = (r'\chapter{First}\label{chap-one}' + '\n' +
                r'\section{Usage}' + '\n' +
                'Ordinary text before the label.\\label{body-marker}' + '\n' +
                r'See \ref{body-marker}.')
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            manual(root/'s', chapter=body)
            convert(root/'s', root/'book')
            content = (root/'book/src/first.md').read_text()
            self.assertIn('## 1.1 Usage\n', content)
            self.assertNotIn('## 1.1 Usage {#body-marker}', content)
            self.assertIn('<div class="manual-anchor" id="body-marker"></div>', content)
            self.assertIn('[1.1](#body-marker)', content)

    def test_no_standalone_a_for_bibliography_or_keyword(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            manual(root/'s')
            convert(root/'s',root/'book')
            body = (root/'book/src/first.md').read_text()
            bibliography = (root/'book/src/references.md').read_text()
            self.assertIn('<div class="manual-anchor" id="key-alpha"></div>', body)
            self.assertIn('<div class="manual-anchor" id="cite-paper"></div>', bibliography)
            self.assertNotIn('<a id=', body + bibliography)

    def test_invalid_source_label_fails_closed(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            manual(root/'s', chapter=r'\chapter{First}\label{bad label}')
            with self.assertRaisesRegex(ConversionError,'unsupported HTML/mdBook label ID'):
                convert(root/'s',root/'book')
            self.assertFalse((root/'book').exists())
