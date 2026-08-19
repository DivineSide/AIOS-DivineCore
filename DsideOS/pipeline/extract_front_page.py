"""Extract the front page from a sample paper into resources/front-page.docx.

The front page = everything in the body BEFORE the first question paragraph
(text starting "1."). Keeps original images whether anchored as modern
<w:drawing> or legacy VML <w:pict>, plus the original section structure, so
build_paper.py can use this file as the base for every generated paper.
"""

import sys
from pathlib import Path

from docx import Document
from docx.oxml.ns import qn
from docx.text.paragraph import Paragraph

sys.path.insert(0, str(Path(__file__).parent))
from ingest import paragraph_text  # noqa: E402

# resources/ is client-specific — see build_answer_key.py's CLIENT_DIR comment.
RES = Path(__file__).resolve().parents[2] / "clients" / "target-academy" / "resources"
SOURCE = RES / "TARGET SERIES 02.docx"
OUT = RES / "front-page.docx"


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    doc = Document(str(SOURCE))
    body = doc.element.body

    cut = None
    for child in body:
        if child.tag == qn("w:p"):
            text = paragraph_text(Paragraph(child, doc)).strip()
            if text.startswith("1.") or text.startswith("1 ."):
                cut = child
                break
    if cut is None:
        raise SystemExit("could not find first question paragraph")

    removing = False
    removed = 0
    for child in list(body):
        if child is cut:
            removing = True
        if removing and child.tag != qn("w:sectPr"):
            body.remove(child)
            removed += 1

    kept_xml = body.xml
    print(f"cut at first question; removed {removed} elements")
    print(f"kept: {len(body)} body elements, drawings={kept_xml.count('<w:drawing>')}, "
          f"vml-picts={kept_xml.count('<w:pict>')}, pgBorders={kept_xml.count('pgBorders')}")
    for child in body.findall(qn("w:p"))[:6]:
        t = paragraph_text(Paragraph(child, doc)).strip()
        if t:
            print(f"  text kept: {t[:70]!r}")
    doc.save(str(OUT))
    print(f"OK: {OUT}")


if __name__ == "__main__":
    main()
