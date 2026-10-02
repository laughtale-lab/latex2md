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
