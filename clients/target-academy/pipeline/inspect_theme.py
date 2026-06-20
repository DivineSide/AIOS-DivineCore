"""One-off: theme colors + color map of the client deck (what is bg1/tx1?)."""

import re
import sys
from pathlib import Path

from pptx import Presentation

RES = Path(__file__).resolve().parents[1] / "resources"

sys.stdout.reconfigure(encoding="utf-8")
prs = Presentation(str(RES / "ppt target revision series 02.pptx"))
m = prs.slide_masters[0]
print("clrMap:", m._element.find("{http://schemas.openxmlformats.org/presentationml/2006/main}clrMap").attrib)
theme = m.part.part_related_by("http://schemas.openxmlformats.org/officeDocument/2006/relationships/theme")
xml = theme.blob.decode("utf-8", "ignore")
for name in ["dk1", "lt1", "dk2", "lt2", "accent1", "accent2"]:
    mt = re.search(
        rf"<a:{name}>.*?(?:srgbClr val=\"([0-9A-Fa-f]{{6}})\"|sysClr val=\"(\w+)\" lastClr=\"([0-9A-Fa-f]{{6}})\")",
        xml,
        re.S,
    )
    print(name, mt.groups() if mt else None)
