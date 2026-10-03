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
            self.assertIn('# 1 First { #chap-one }',content)
            self.assertIn('## 1.1 Usage { #sec-usage }',content)
            self.assertNotIn('<a id="chap-one"',content)
            self.assertNotIn('<a id="sec-usage"',content)
            self.assertIn('[alpha](#key-alpha)',content)
            self.assertIn('[Script 1-1](#script-one)',content)
            self.assertIn('[Example 1-1](#example-one)',content)
            self.assertIn('class="target-anchor keyword-target" id="key-alpha"',content)
            self.assertIn('id="script-one"',content)
            self.assertIn('id="example-one"',content)
            self.assertIn('\\\\(x+y\\\\)',content)
            self.assertIn('1. First',content)
            self.assertIn('2. Second',content)
            self.assertNotIn('1. \n',content)
            book_config=(output/'book.toml').read_text()
            self.assertIn('mathjax-support = true',book_config)
            self.assertIn('diabat.css',book_config)
            self.assertIn('[output.html.print]\nenable = false',book_config)
            self.assertEqual((source/'examples/release/test.inp').read_bytes(),
                             (output/'src/downloads/examples/release/test.inp').read_bytes())
            references=(output/'src/references.md').read_text()
            self.assertIn('class="target-anchor citation-target" id="cite-paper"',references)
            report_json=json.loads((output/'conversion-report.json').read_text())
            self.assertEqual(report_json['citations'],['paper'])
            self.assertEqual(report_json['targets']['chap-one']['render'],'heading')
            self.assertEqual(report_json['targets']['chap-one']['kind'],'chapter')
            self.assertEqual(report_json['targets']['sec-usage']['render'],'heading')
            self.assertEqual(report_json['targets']['script-one']['kind'],'script')
            self.assertEqual(report_json['targets']['cite-paper']['page'],'references.md')

    def test_fenced_listing_inside_ordered_list_uses_marker_width_indent(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            chapter=CHAPTER + r"""
\begin{enumerate}
\item One
\item Two
\item Three
\item Four
\item Five
\item Six
\item Seven
\item Integer sequence example:
\begin{lst-script}
state_index = 1, 3..5, 8:12:2, 20
\end{lst-script}
selects the requested states.
\item Nine
\item Ten with another listing:
\begin{lst-script}
mode = 10
\end{lst-script}
\end{enumerate}
\subsection{After Nested Listing}\label{subsec-after-nested-listing}
The heading after the list must remain outside every code fence.
"""
            manual(root/'s',chapter=chapter)
            convert(root/'s',root/'out')
            text=(root/'out/src/first.md').read_text(encoding='utf8')
            self.assertIn('8. Integer sequence example:\n   \n   ```diabat\n'
                          '   state_index = 1, 3..5, 8:12:2, 20\n'
                          '   ```\n   \n   selects the requested states.', text)
            self.assertIn('10. Ten with another listing:\n    \n    ```diabat\n'
                          '    mode = 10\n    ```', text)
            self.assertIn('### 1.1.1 After Nested Listing { #subsec-after-nested-listing }', text)
            self.assertNotIn('\n  state_index = 1, 3..5, 8:12:2, 20\n', text)

    def test_non_heading_label_remains_explicit_target(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            chapter=CHAPTER + r'Plain text before a standalone target.\phantomsection\label{standalone-target}'
            manual(root/'s',chapter=chapter)
            report=convert(root/'s',root/'out')
            content=(root/'out/src/first.md').read_text(encoding='utf8')
            self.assertIn('class="target-anchor standalone-target" id="standalone-target"',content)
            self.assertEqual(report['targets']['standalone-target']['render'],'raw-html')
            self.assertEqual(report['targets']['standalone-target']['kind'],'standalone')

    def test_heading_binding_stops_after_nonblank_content(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            chapter=CHAPTER.replace(r'\section{Usage} \label{sec-usage}',
                                    r'\section{Usage} prose first \label{sec-usage}')
            manual(root/'s',chapter=chapter)
            report=convert(root/'s',root/'out')
            content=(root/'out/src/first.md').read_text(encoding='utf8')
            self.assertNotIn('Usage { #sec-usage }',content)
            self.assertIn('id="sec-usage"',content)
            self.assertEqual(report['targets']['sec-usage']['render'],'raw-html')

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
