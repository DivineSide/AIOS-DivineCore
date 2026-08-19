"""One-off: which client file has page borders, front-page graphics, watermark headers?"""

import sys
from pathlib import Path

from docx import Document

# resources/ is client-specific — see build_answer_key.py's CLIENT_DIR comment.
RES = Path(__file__).resolve().parents[2] / "clients" / "target-academy" / "resources"

sys.stdout.reconfigure(encoding="utf-8")
for f in sorted(RES.glob("*.docx")):
    doc = Document(str(f))
    xml = doc.element.body.xml
    front = xml.split("</w:sectPr>")[0]  # content up to end of section 0 marker
    hdr_imgs = 0
    for s in doc.sections:
        for h in (s.header, s.first_page_header, s.even_page_header):
            hdr_imgs += h.part.element.xml.count("blip")
    print(
        f"{f.name}: pgBorders={xml.count('pgBorders')}, "
        f"body-drawings={xml.count('<w:drawing>')}, "
        f"front-region-drawings={front.count('<w:drawing>')}, "
        f"header-blips={hdr_imgs}, sections={len(doc.sections)}"
    )
