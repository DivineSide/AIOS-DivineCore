"""Build an advertising poster PNG in the institute's brand style.

Template modeled on the client's standard poster (resources/poster_ex_1.jpeg):
yellow canvas + black frame, black TARGET ACADEMY wordmark, black headline pill
with dart-target, red ONLY pill, dark-green video strip, cream panel holding a
white 2-column courses card and a 3-icon feature row, dark-green footer with
phone mockup + official store badges.

Quality stack: Baloo 2 (Devanagari display font) + Mukta (body) from Google
Fonts, official Play/App Store badge SVGs, inline Material-style SVG icons —
all local in templates/poster_assets/. Rendered via headless Edge at 2x and
cropped to exactly 2160x2700 with PIL (Edge clips the viewport bottom, so we
render tall and crop).

Usage: python build_poster.py [poster.json] [out.png]
"""

import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from string import Template

from PIL import Image

BASE = Path(__file__).resolve().parents[1]
# templates/ is client-specific — see build_answer_key.py's CLIENT_DIR comment.
CLIENT_DIR = BASE.parent / "clients" / "target-academy"
ASSETS = CLIENT_DIR / "templates" / "poster_assets"

EDGE_CANDIDATES = [
    Path("C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe"),
    Path("C:/Program Files/Microsoft/Edge/Application/msedge.exe"),
]

ICON_DOC = """<svg viewBox="0 0 24 24" width="52" height="52" fill="#fff"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8l-6-6zm-1 7V3.5L18.5 9H13zm-5 4h8v2H8v-2zm0 4h8v2H8v-2z"/></svg>"""
ICON_CHART = """<svg viewBox="0 0 24 24" width="52" height="52" fill="#fff"><path d="M3 17l6-6 4 4 7-8v4h2V3h-8v2h4.6L13 11.4l-4-4L1.4 15 3 17zM3 19h18v2H3z"/></svg>"""
ICON_CAM = """<svg viewBox="0 0 24 24" width="44" height="44" fill="#fff" style="vertical-align:-8px;margin-right:14px"><path d="M17 10.5V7a1 1 0 0 0-1-1H4a1 1 0 0 0-1 1v10a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1v-3.5l4 4v-11l-4 4z"/></svg>"""

HTML = Template(r"""<!doctype html>
<html><head><meta charset="utf-8"><style>
  @font-face { font-family:'Baloo 2'; src:url('$f_baloo') format('truetype'); }
  @font-face { font-family:'Mukta'; font-weight:700; src:url('$f_mukta_b') format('truetype'); }
  @font-face { font-family:'Mukta'; font-weight:800; src:url('$f_mukta_xb') format('truetype'); }
  * { margin:0; padding:0; box-sizing:border-box; }
  body { width:1080px; height:1350px; background:#FFD400; overflow:hidden;
         font-family:'Mukta','Nirmala UI',sans-serif; position:relative; }
  .frame { position:absolute; inset:14px; border:5px solid #111;
           border-radius:6px; pointer-events:none; z-index:50; }

  .brand { text-align:center; padding-top:22px; }
  .brand .top { font-family:'Baloo 2'; font-size:88px; font-weight:800;
                color:#0B0B0B; letter-spacing:1px; line-height:1; }
  .brand .sub { display:inline-block; font-family:'Baloo 2'; font-size:32px;
                font-weight:700; color:#0B0B0B; margin-top:2px;
                padding-bottom:2px; border-bottom:4px solid #0B0B0B; }

  .pillwrap { position:relative; width:880px; margin:24px auto 0 auto; }
  .blackpill { background:#0E0E0E; border-radius:36px; padding:20px 40px 52px 40px;
               text-align:center; box-shadow:0 14px 26px #00000044; }
  .blackpill .h { color:#FFFFFF; font-family:'Baloo 2'; font-size:96px;
                  font-weight:800; line-height:1.05; }
  .target { position:absolute; right:-30px; top:-26px; width:150px; height:150px;
            border-radius:50%; z-index:5;
            background:radial-gradient(circle, #fff 0 12%, #E32227 12% 26%,
              #fff 26% 40%, #E32227 40% 54%, #fff 54% 68%, #E32227 68% 100%);
            border:6px solid #fff; box-shadow:0 10px 20px #00000066; }
  .target::after { content:""; position:absolute; left:16px; top:62px;
                   width:100px; height:11px; background:#FFD400;
                   border:2px solid #8B6A00; transform:rotate(-18deg);
                   border-radius:5px; }
  .book { position:absolute; left:-18px; bottom:-20px; font-size:92px;
          filter:drop-shadow(0 8px 10px #00000044); z-index:5; }

  .redpill { width:600px; margin:-52px auto 0 auto; position:relative; z-index:6;
             background:linear-gradient(180deg,#FF4046,#C40000);
             border:5px solid #fff; border-radius:999px; text-align:center;
             padding:12px 10px; box-shadow:0 10px 20px #00000055; }
  .redpill .t { color:#fff; font-family:'Mukta'; font-weight:800; font-size:44px; }

  .greenstrip { margin-top:20px; background:linear-gradient(180deg,#1E6B2A,#14501D);
                padding:16px 0; text-align:center; border-top:5px solid #0B3A12;
                border-bottom:5px solid #0B3A12; }
  .greenstrip .t { color:#fff; font-family:'Mukta'; font-weight:800; font-size:42px; }

  .panel { background:#F4EFD8; padding:14px 44px 0 44px; height:600px; }

  .courseshead { width:430px; margin:0 auto; background:#0E0E0E; color:#FFD400;
                 border-radius:999px; text-align:center; font-family:'Baloo 2';
                 font-size:40px; font-weight:800; padding:6px 0;
                 position:relative; z-index:3; }
  .card { background:#fff; border-radius:26px; margin-top:-28px;
          padding:40px 36px 10px 36px; box-shadow:0 10px 22px #00000022;
          display:grid; grid-template-columns:1fr 1fr; column-gap:56px;
          position:relative; }
  .card::before { content:""; position:absolute; top:56px; bottom:26px;
                  left:50%; width:3px; background:#E2E2E2; }
  .citem { display:flex; align-items:center; gap:16px; padding:7px 0;
           border-bottom:2px solid #F0F0F0; }
  .citem:nth-last-child(-n+2) { border-bottom:none; }
  .citem .chk { width:48px; height:48px; border-radius:50%; flex-shrink:0;
                background:radial-gradient(circle at 35% 30%, #37A84D, #186228);
                color:#fff; font-size:30px; font-weight:900; display:flex;
                align-items:center; justify-content:center;
                box-shadow:inset 0 -3px 6px #00000033; }
  .citem .t { font-family:'Mukta'; font-size:40px; font-weight:800; color:#111; }

  .features { display:flex; margin-top:14px; padding-left:260px; }
  .feat { flex:1; text-align:center; padding:0 20px; }
  .feat + .feat { border-left:3px dashed #8A8A6A; }
  .feat .ic { width:96px; height:96px; border-radius:50%; margin:0 auto;
              display:flex; align-items:center; justify-content:center;
              box-shadow:0 8px 16px #00000033; }
  .feat .ic.sq { border-radius:20px; color:#fff; font-family:'Baloo 2';
                 font-size:34px; font-weight:800; }
  .feat .t { font-family:'Mukta'; font-size:25px; font-weight:800; color:#111;
             margin-top:12px; line-height:1.3; }

  .footer { position:absolute; left:0; right:0; bottom:0; height:222px;
            background:linear-gradient(180deg,#17591F,#0B3A12);
            border-top-left-radius:70px 45px; border-top-right-radius:70px 45px;
            display:flex; flex-direction:column; align-items:center;
            justify-content:center; gap:18px; padding-left:240px; }
  .footer .cta { color:#FFD400; font-family:'Baloo 2'; font-size:60px;
                 font-weight:800; text-shadow:0 4px 0 #00000066; line-height:1; }
  .badges { display:flex; gap:26px; align-items:center; }
  .badges img { height:64px; }

  .phone { position:absolute; left:44px; bottom:26px; width:200px; height:300px;
           background:#0B0B0B; border-radius:32px; padding:13px;
           transform:rotate(-7deg); box-shadow:0 16px 30px #00000077; z-index:8;
           border:3px solid #333; }
  .phone .screen { background:#FFD400; width:100%; height:100%;
                   border-radius:20px; display:flex; flex-direction:column;
                   align-items:center; justify-content:center; gap:6px; }
  .phone .cap { font-size:56px; }
  .phone .pb { font-family:'Baloo 2'; font-size:24px; font-weight:800;
               color:#0B0B0B; text-align:center; line-height:1.05; }
  .phone .ps { font-family:'Baloo 2'; font-size:17px; font-weight:700; color:#0B0B0B; }
</style></head>
<body>
  <div class="frame"></div>
  <div class="brand">
    <div class="top">$brand_top</div>
    <div class="sub">$brand_sub</div>
  </div>
  <div class="pillwrap">
    <div class="blackpill"><div class="h">$headline</div></div>
    <div class="target"></div>
    <div class="book">📖</div>
  </div>
  <div class="redpill"><div class="t">$pill_line</div></div>
  <div class="greenstrip"><div class="t">$icon_cam$strip_line</div></div>
  <div class="panel">
    <div class="courseshead">$courses_head</div>
    <div class="card">
      $courses
    </div>
    <div class="features">
      $features
    </div>
  </div>
  <div class="footer">
    <div class="cta">$cta</div>
    <div class="badges">
      <img src="$badge_play"><img src="$badge_app">
    </div>
  </div>
  <div class="phone"><div class="screen">
    <div class="cap">🎓</div>
    <div class="pb">$brand_top</div>
    <div class="ps">$brand_sub</div>
  </div></div>
</body></html>
""")


def find_edge() -> Path:
    for p in EDGE_CANDIDATES:
        if p.exists():
            return p
    raise SystemExit("msedge.exe not found")


def feature_icon(f) -> str:
    if f.get("square"):
        return f'<div class="ic sq" style="background:{f["color"]}">{f["icon"]}</div>'
    svg = {"doc": ICON_DOC, "chart": ICON_CHART}.get(f["icon"], f["icon"])
    return f'<div class="ic" style="background:{f["color"]}">{svg}</div>'


def build(data_path: Path, out_path: Path):
    data = json.loads(data_path.read_text(encoding="utf-8"))
    courses = data["courses"]
    half = (len(courses) + 1) // 2
    ordered = []
    for i in range(half):
        ordered.append(courses[i])
        if i + half < len(courses):
            ordered.append(courses[i + half])
    courses_html = "\n".join(
        f'<div class="citem"><div class="chk">✔</div><div class="t">{c}</div></div>'
        for c in ordered
    )
    feats_html = "\n".join(
        f'<div class="feat">{feature_icon(f)}<div class="t">{f["text"]}</div></div>'
        for f in data["features"]
    )
    html = HTML.substitute(
        f_baloo=(ASSETS / "Baloo2.ttf").as_uri(),
        f_mukta_b=(ASSETS / "Mukta-Bold.ttf").as_uri(),
        f_mukta_xb=(ASSETS / "Mukta-ExtraBold.ttf").as_uri(),
        badge_play=(ASSETS / "google_play_badge.svg").as_uri(),
        badge_app=(ASSETS / "app_store_badge.svg").as_uri(),
        icon_cam=ICON_CAM,
        brand_top=data["brand_top"],
        brand_sub=data["brand_sub"],
        headline=data["headline"],
        pill_line=data["pill_line"],
        strip_line=data["strip_line"],
        courses_head=data["courses_head"],
        courses=courses_html,
        features=feats_html,
        cta=data["cta"],
    )
    tmp = Path(tempfile.gettempdir()) / "target_poster.html"
    tmp.write_text(html, encoding="utf-8")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    # render taller than the canvas, then crop to exactly 2160x2700 —
    # headless Edge clips the bottom of the viewport otherwise
    subprocess.run(
        [str(find_edge()), "--headless=new", "--disable-gpu", "--hide-scrollbars",
         f"--screenshot={out_path}", "--window-size=1080,1500",
         "--force-device-scale-factor=2", tmp.as_uri()],
        capture_output=True, timeout=60,
    )
    time.sleep(1)
    if not out_path.exists():
        raise SystemExit("render failed — no PNG produced")
    img = Image.open(out_path)
    img.crop((0, 0, 2160, 2700)).save(out_path, "PNG")
    print(f"OK: {out_path} ({out_path.stat().st_size:,} bytes, {Image.open(out_path).size})")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    data = Path(sys.argv[1]) if len(sys.argv) > 1 else CLIENT_DIR / "review" / "poster-demo.json"
    content = json.loads(data.read_text(encoding="utf-8"))
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else CLIENT_DIR / "review" / content.get(
        "filename", "Poster - Target Academy.png")
    build(data, out)
