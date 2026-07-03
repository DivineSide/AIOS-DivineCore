"""Kruti Dev 010 <-> Unicode Devanagari converter.

Port of the reference JS implementation (`_reference_krutidevtounicode.js`,
github.com/TGNYC/Kriti-Dev-to-Unicode) — same mapping tables, same rule order,
same positional fix-ups. Kruti Dev is a legacy font that maps Devanagari glyphs
onto ASCII codepoints, so conversion is rule-ordered string replacement plus two
positional corrections: the chhoti-i matra (rendered BEFORE its consonant in
Kruti, AFTER it in Unicode) and the reph (र् rendered as a trailing "Z" glyph).

Public API:
    krutidev_to_unicode(text)  — ingest direction (read his .pptx/.doc files)
    unicode_to_krutidev(text)  — output direction (write his decks/papers)
    unicode_to_krutidev_runs(text) — like above, but returns [(text, is_latin)]
        runs so deck-building code can give Latin words a Latin font (Latin text
        rendered in the Kruti Dev font shows as garbage Devanagari glyphs).

Mapping-table order is load-bearing (conjuncts before their substrings); do not
sort or dedupe. Duplicated/odd-looking entries are faithful to the reference.
"""

import re

# --- Kruti Dev -> Unicode ----------------------------------------------------
# Order preserved from the reference array_one/array_two pair.

_K2U = (
    ("ñ", "॰"), ("Q+Z", "QZ+"), ("sas", "sa"), ("aa", "a"), (")Z", "र्द्ध"),
    ("ZZ", "Z"), ("‘", '"'), ("’", '"'), ("“", "'"), ("”", "'"),

    ("å", "०"), ("ƒ", "१"), ("„", "२"), ("…", "३"), ("†", "४"),
    ("‡", "५"), ("ˆ", "६"), ("‰", "७"), ("Š", "८"), ("‹", "९"),

    ("¶+", "फ़्"), ("d+", "क़"), ("[+k", "ख़"), ("[+", "ख़्"), ("x+", "ग़"),
    ("T+", "ज़्"), ("t+", "ज़"), ("M+", "ड़"), ("<+", "ढ़"), ("Q+", "फ़"),
    (";+", "य़"), ("j+", "ऱ"), ("u+", "ऩ"),
    ("Ùk", "त्त"), ("Ù", "त्त्"), ("ä", "क्त"), ("–", "दृ"), ("—", "कृ"),
    ("é", "न्न"), ("™", "न्न्"), ("=kk", "=k"), ("f=k", "f="),

    ("à", "ह्न"), ("á", "ह्य"), ("â", "हृ"), ("ã", "ह्म"), ("ºz", "ह्र"),
    ("º", "ह्"), ("í", "द्द"), ("{k", "क्ष"), ("{", "क्ष्"), ("=", "त्र"),
    ("«", "त्र्"),
    ("Nî", "छ्य"), ("Vî", "ट्य"), ("Bî", "ठ्य"), ("Mî", "ड्य"), ("<î", "ढ्य"),
    ("|", "द्य"), ("K", "ज्ञ"), ("}", "द्व"),
    ("J", "श्र"), ("Vª", "ट्र"), ("Mª", "ड्र"), ("<ªª", "ढ्र"), ("Nª", "छ्र"),
    ("Ø", "क्र"), ("Ý", "फ्र"), ("nzZ", "र्द्र"), ("æ", "द्र"), ("ç", "प्र"),
    ("Á", "प्र"), ("xz", "ग्र"), ("#", "रु"), (":", "रू"),

    ("v‚", "ऑ"), ("vks", "ओ"), ("vkS", "औ"), ("vk", "आ"), ("v", "अ"),
    ("b±", "ईं"), ("Ã", "ई"), ("bZ", "ई"), ("b", "इ"), ("m", "उ"),
    ("Å", "ऊ"), (",s", "ऐ"), (",", "ए"), ("_", "ऋ"),

    ("ô", "क्क"), ("d", "क"), ("Dk", "क"), ("D", "क्"), ("[k", "ख"),
    ("[", "ख्"), ("x", "ग"), ("Xk", "ग"), ("X", "ग्"), ("Ä", "घ"),
    ("?k", "घ"), ("?", "घ्"), ("³", "ङ"),
    ("pkS", "चै"), ("p", "च"), ("Pk", "च"), ("P", "च्"), ("N", "छ"),
    ("t", "ज"), ("Tk", "ज"), ("T", "ज्"), (">", "झ"), ("÷", "झ्"),
    ("¥", "ञ"),

    ("ê", "ट्ट"), ("ë", "ट्ठ"), ("V", "ट"), ("B", "ठ"), ("ì", "ड्ड"),
    ("ï", "ड्ढ"), ("M+", "ड़"), ("<+", "ढ़"), ("M", "ड"), ("<", "ढ"),
    (".k", "ण"), (".", "ण्"),
    ("r", "त"), ("Rk", "त"), ("R", "त्"), ("Fk", "थ"), ("F", "थ्"),
    (")", "द्ध"), ("n", "द"), ("/k", "ध"), ("èk", "ध"), ("/", "ध्"),
    ("Ë", "ध्"), ("è", "ध्"), ("u", "न"), ("Uk", "न"), ("U", "न्"),

    ("i", "प"), ("Ik", "प"), ("I", "प्"), ("Q", "फ"), ("¶", "फ्"),
    ("c", "ब"), ("Ck", "ब"), ("C", "ब्"), ("Hk", "भ"), ("H", "भ्"),
    ("e", "म"), ("Ek", "म"), ("E", "म्"),
    (";", "य"), ("¸", "य्"), ("j", "र"), ("y", "ल"), ("Yk", "ल"),
    ("Y", "ल्"), ("G", "ळ"), ("o", "व"), ("Ok", "व"), ("O", "व्"),
    ("'k", "श"), ("'", "श्"), ('"k', "ष"), ('"', "ष्"), ("l", "स"),
    ("Lk", "स"), ("L", "स्"), ("g", "ह"),

    ("È", "ीं"), ("z", "्र"),
    ("Ì", "द्द"), ("Í", "ट्ट"), ("Î", "ट्ठ"), ("Ï", "ड्ड"), ("Ñ", "कृ"),
    ("Ò", "भ"), ("Ó", "्य"), ("Ô", "ड्ढ"), ("Ö", "झ्"), ("Ø", "क्र"),
    ("Ù", "त्त्"), ("Ük", "श"), ("Ü", "श्"),

    ("‚", "ॉ"), ("ks", "ो"), ("kS", "ौ"), ("k", "ा"), ("h", "ी"),
    ("q", "ु"), ("w", "ू"), ("`", "ृ"), ("s", "े"), ("S", "ै"),
    ("a", "ं"), ("¡", "ँ"), ("%", "ः"), ("W", "ॅ"), ("•", "ऽ"),
    ("·", "ऽ"), ("∙", "ऽ"), ("·", "ऽ"), ("~j", "्र"), ("~", "्"),
    ("\\", "?"), ("+", "़"), (" ः", ":"),
    ("^", "‘"), ("*", "’"), ("Þ", "“"), ("ß", "”"), ("(", ";"),
    ("¼", "("), ("½", ")"), ("¿", "{"), ("À", "}"), ("¾", "="),
    ("A", "।"), ("-", "."), ("&", "-"), ("&", "-"), ("Œ", "॰"),
    ("]", ","), ("~ ", "् "), ("@", "/"),
)

# Matras the K2U reph-fix walks left across (reference includes the spaces).
_K2U_MATRAS = "अ आ इ ई उ ऊ ए ऐ ओ औ ा ि ी ु ू ृ े ै ो ौ ं : ँ ॅ"


def _replace_all(text: str, pairs) -> str:
    for old, new in pairs:
        while old in text:
            text = text.replace(old, new)
    return text


def krutidev_to_unicode(text: str) -> str:
    """Kruti Dev 010 legacy-encoded text -> Unicode Devanagari."""
    if not text:
        return text
    s = _replace_all(text, _K2U)

    s = s.replace("±", "Zं")    # reph+anusvar ligature
    s = s.replace("Æ", "र्f")   # reph + chhoti-i ligature (e.g. धार्मिक)

    # chhoti-i: Kruti renders ि BEFORE the consonant; move it after.
    pos = s.find("f")
    while pos != -1:
        nxt = s[pos + 1] if pos + 1 < len(s) else ""
        s = s.replace("f" + nxt, nxt + "ि", 1)
        pos = s.find("f", pos + 1)

    s = s.replace("Ç", "fa")     # ि + anusvar ligature (e.g. किंकर)
    s = s.replace("É", "र्fa")   # reph + ि + anusvar (e.g. शर्मिंदा)
    pos = s.find("fa")
    while pos != -1:
        nxt = s[pos + 2] if pos + 2 < len(s) else ""
        s = s.replace("fa" + nxt, nxt + "िं", 1)
        pos = s.find("fa", pos + 2)

    s = s.replace("Ê", "ीZ")     # ी + reph ligature

    # ि wrongly attached to a half-letter: push it past the conjunct.
    pos = s.find("ि्")
    while pos != -1:
        nxt = s[pos + 2] if pos + 2 < len(s) else ""
        s = s.replace("ि्" + nxt, "्" + nxt + "ि", 1)
        pos = s.find("ि्", pos + 2)

    # reph: trailing "Z" glyph becomes र् placed before the syllable.
    pos = s.find("Z")
    while pos > 0:
        start = pos - 1
        while start >= 0 and s[start] in _K2U_MATRAS:
            start -= 1
        start = max(start, 0)
        seg = s[start:pos]
        s = s.replace(seg + "Z", "र्" + seg, 1)
        pos = s.find("Z")

    return s


# --- Unicode -> Kruti Dev ----------------------------------------------------

_U2K = (
    ("‘", "^"), ("’", "*"), ("“", "Þ"), ("”", "ß"), ("(", "¼"), (")", "½"),
    ("{", "¿"), ("}", "À"), ("=", "¾"), ("।", "A"), ("?", "\\"), ("-", "&"),
    ("µ", "&"), ("॰", "Œ"), (",", "]"), (".", "-"), ("् ", "~ "),
    # A literal Unicode "/" must become the Kruti byte "@" (the reverse of the
    # K2U ("@","/") rule): in Kruti Dev 010 the "/" byte is the glyph ध् (half-dha),
    # so leaving "/" as-is corrupted the ubiquitous "कौन सा/से ... है/हैं" phrasing
    # into a stray ध्. Placed AFTER "." so it doesn't disturb the ध्->/ direction.
    ("/", "@"),

    ("०", "å"), ("१", "ƒ"), ("२", "„"), ("३", "…"), ("४", "†"),
    ("५", "‡"), ("६", "ˆ"), ("७", "‰"), ("८", "Š"), ("९", "‹"), ("x", "Û"),

    ("फ़्", "¶"), ("क़", "d"), ("ख़", "[k"), ("ग़", "x"), ("ज़्", "T"),
    ("ज़", "t"), ("ड़", "M+"), ("ढ़", "<+"), ("फ़", "Q"), ("य़", ";"),
    ("ऱ", "j"), ("ऩ", "u"),
    ("त्त्", "Ù"), ("त्त", "Ùk"), ("क्त", "ä"), ("दृ", "–"), ("कृ", "—"),

    ("ह्न", "à"), ("ह्य", "á"), ("हृ", "â"), ("ह्म", "ã"), ("ह्र", "ºz"),
    ("ह्", "º"), ("द्द", "í"), ("क्ष्", "{"), ("क्ष", "{k"), ("त्र्", "«"),
    ("त्र", "="), ("ज्ञ", "K"),
    ("छ्य", "Nî"), ("ट्य", "Vî"), ("ठ्य", "Bî"), ("ड्य", "Mî"), ("ढ्य", "<î"),
    ("द्य", "|"), ("द्व", "}"),
    ("श्र", "J"), ("ट्र", "Vª"), ("ड्र", "Mª"), ("ढ्र", "<ªª"), ("छ्र", "Nª"),
    ("क्र", "Ø"), ("फ्र", "Ý"), ("द्र", "æ"), ("प्र", "ç"), ("ग्र", "xz"),
    ("रु", "#"), ("रू", ":"),
    ("्र", "z"),

    ("ओ", "vks"), ("औ", "vkS"), ("आ", "vk"), ("अ", "v"), ("ई", "bZ"),
    ("इ", "b"), ("उ", "m"), ("ऊ", "Å"), ("ऐ", ",s"), ("ए", ","), ("ऋ", "_"),

    ("क्", "D"), ("क", "d"), ("क्क", "ô"), ("ख्", "["), ("ख", "[k"),
    ("ग्", "X"), ("ग", "x"), ("घ्", "?"), ("घ", "?k"), ("ङ", "³"),
    ("चै", "pkS"), ("च्", "P"), ("च", "p"), ("छ", "N"), ("ज्", "T"),
    ("ज", "t"), ("झ्", "÷"), ("झ", ">"), ("ञ", "¥"),

    ("ट्ट", "ê"), ("ट्ठ", "ë"), ("ट", "V"), ("ठ", "B"), ("ड्ड", "ì"),
    ("ड्ढ", "ï"), ("ड", "M"), ("ढ", "<"), ("ण्", "."), ("ण", ".k"),
    ("त्", "R"), ("त", "r"), ("थ्", "F"), ("थ", "Fk"), ("द्ध", ")"),
    ("द", "n"), ("ध्", "/"), ("ध", "/k"), ("न्", "U"), ("न", "u"),

    ("प्", "I"), ("प", "i"), ("फ्", "¶"), ("फ", "Q"), ("ब्", "C"),
    ("ब", "c"), ("भ्", "H"), ("भ", "Hk"), ("म्", "E"), ("म", "e"),
    ("य्", "¸"), ("य", ";"), ("र", "j"), ("ल्", "Y"), ("ल", "y"),
    ("ळ", "G"), ("व्", "O"), ("व", "o"),
    ("श्", "'"), ("श", "'k"), ("ष्", '"'), ("ष", '"k'), ("स्", "L"),
    ("स", "l"), ("ह", "g"),

    ("ऑ", "v‚"), ("ॉ", "‚"), ("ो", "ks"), ("ौ", "kS"), ("ा", "k"),
    ("ी", "h"), ("ु", "q"), ("ू", "w"), ("ृ", "`"), ("े", "s"), ("ै", "S"),
    ("ं", "a"), ("ँ", "¡"), ("ः", "%"), ("ॅ", "W"), ("ऽ", "·"),
    ("् ", "~ "), ("्", "~"),
)

# Matras the U2K reph-fix walks right across (no spaces in this set).
_U2K_MATRAS = "ािीुूृेैोौं:ँॅ"

# Composed nukta sequences -> precomposed codepoints (reference does this first).
_NUKTA = {
    "क़": "क़", "ख़": "ख़", "ग़": "ग़", "ज़": "ज़",
    "ड़": "ड़", "ढ़": "ढ़", "ऩ": "ऩ", "फ़": "फ़",
    "य़": "य़", "ऱ": "ऱ",
}


def unicode_to_krutidev(text: str) -> str:
    """Unicode Devanagari -> Kruti Dev 010 legacy encoding.

    NOTE: Latin letters in the input get remapped (Kruti reuses ASCII
    codepoints). For mixed Hindi/English text use unicode_to_krutidev_runs().
    """
    if not text:
        return text
    s = text
    for composed, precomposed in _NUKTA.items():
        s = s.replace(composed, precomposed)

    # chhoti-i: move ि before its consonant (and before its full conjunct).
    pos = s.find("ि")
    while pos != -1:
        left = s[pos - 1] if pos > 0 else ""
        s = s.replace(left + "ि", "f" + left, 1)
        pos -= 1
        while pos - 1 >= 1 and s[pos - 1] == "्":
            cluster = s[pos - 2] + "्"
            s = s.replace(cluster + "f", "f" + cluster, 1)
            pos -= 2
        pos = s.find("ि", pos + 1)

    # reph: र् becomes a "Z" glyph after the syllable (incl. its matras).
    s += "  "  # pad so lookahead never falls off the end (reference does this)
    pos = s.find("र्")
    while pos > 0:
        z_at = pos + 2
        while s[z_at + 1] in _U2K_MATRAS:
            z_at += 1
        seg = s[pos + 2 : z_at + 1]
        s = s.replace("र्" + seg, seg + "Z", 1)
        pos = s.find("र्")
    s = s[:-2]

    return _replace_all(s, _U2K)


# Latin words, plus ASCII punctuation Kruti Dev repurposes for Devanagari glyphs
# with no reverse mapping (":" renders as रू, ";" as "(", "|" as द्य, ...). Those
# must stay in a Latin-font run to display correctly.
_LATIN_RUN = re.compile(
    r"[A-Za-z][A-Za-z0-9'’.-]*(?: +[A-Za-z][A-Za-z0-9'’.-]*)*|[:;%!@#&*+~^_<>|\\'\"–—]+"
)


def unicode_to_krutidev_runs(text: str):
    """Split mixed Hindi/English text into [(text, is_latin)] runs.

    Hindi runs come back Kruti-encoded (render with font "Kruti Dev 010");
    Latin runs come back untouched (render with a Latin font, e.g. Calibri) —
    his papers have English headlines, so deck/paper builders need this.
    """
    runs = []
    last = 0
    for m in _LATIN_RUN.finditer(text):
        if m.start() > last:
            runs.append((unicode_to_krutidev(text[last : m.start()]), False))
        runs.append((m.group(), True))
        last = m.end()
    if last < len(text):
        runs.append((unicode_to_krutidev(text[last:]), False))
    return runs


# A plain Latin-word splitter for Unicode mode. We do NOT need to pull out the
# Kruti-repurposed punctuation here (`:`, `;`, `|`, …) — in Unicode mode those
# characters render correctly in any font, so only true Latin words get split
# out so they can use a Latin font for nicer Western glyphs.
_LATIN_WORD = re.compile(r"[A-Za-z][A-Za-z0-9'’.\-/]*(?: +[A-Za-z][A-Za-z0-9'’.\-/]*)*")


def unicode_runs(text: str):
    """Split text into [(text, is_latin)] runs, keeping Devanagari as Unicode.

    The Unicode-mode counterpart of unicode_to_krutidev_runs(): Hindi runs are
    returned UNCHANGED (render with a Unicode Devanagari font like Nirmala UI),
    Latin runs are split out so they can use a Latin font. Nothing is converted.
    """
    runs = []
    last = 0
    for m in _LATIN_WORD.finditer(text):
        if m.start() > last:
            runs.append((text[last : m.start()], False))
        runs.append((m.group(), True))
        last = m.end()
    if last < len(text):
        runs.append((text[last:], False))
    return runs


# The font registry the frontend chooses from. Each entry names the Devanagari
# font and the run-splitter used to render it. To add a font, add a row here —
# the builders read this, they don't hardcode font names.
FONTS = {
    "krutidev": {
        "devanagari": "Kruti Dev 010",
        "splitter": unicode_to_krutidev_runs,
    },
    "unicode": {
        "devanagari": "Nirmala UI",
        "splitter": unicode_runs,
    },
}

DEFAULT_FONT = "krutidev"   # current shipping behavior; frontend overrides per build


def render_runs(text: str, font: str = DEFAULT_FONT):
    """THE font switch. Unicode text in -> [(run_text, is_latin)] out.

    `font` selects the rendering: "krutidev" converts Hindi to Kruti Dev legacy
    encoding (current shipping path); "unicode" keeps Hindi as Unicode for a
    Unicode Devanagari font. Builders call this and never touch the font tables
    directly — so the choice is a single parameter threaded from the frontend.

    Returns (runs, devanagari_font_name) so the caller knows which font to set
    on the non-Latin runs.
    """
    if font not in FONTS:
        raise ValueError(f"Unknown font {font!r}. Available: {list(FONTS)}")
    spec = FONTS[font]
    return spec["splitter"](str(text or "")), spec["devanagari"]


if __name__ == "__main__":
    # Known-good pairs (verified against Kruti Dev typing references).
    U2K_CASES = [
        ("भारत", "Hkkjr"),
        ("हिन्दी", "fgUnh"),
        ("स्थिति", "fLFkfr"),
        ("धर्म", "/keZ"),
        ("कार्यक्रम", "dk;ZØe"),
        ("क्षत्रिय", "{kf=;"),
        ("धार्मिक", "/kkfeZd"),
        ("भारतीय संविधान।", "Hkkjrh; lafo/kkuA"),
    ]
    failures = 0
    for uni, kru in U2K_CASES:
        got = unicode_to_krutidev(uni)
        ok = got == kru
        failures += not ok
        print(f"U2K {'PASS' if ok else 'FAIL'}: {uni!r} -> {got!r}" + ("" if ok else f" (expected {kru!r})"))
    for uni, kru in U2K_CASES:
        got = krutidev_to_unicode(kru)
        ok = got == uni
        failures += not ok
        print(f"K2U {'PASS' if ok else 'FAIL'}: {kru!r} -> {got!r}" + ("" if ok else f" (expected {uni!r})"))
    # Round-trip a longer sentence through both directions. (ASCII ":" is
    # excluded by design — Kruti repurposes it; runs-splitting handles it.)
    sentence = "अनुच्छेद 14 विधि के समक्ष समता का अधिकार।"
    rt = krutidev_to_unicode(unicode_to_krutidev(sentence))
    ok = rt == sentence
    failures += not ok
    print(f"ROUNDTRIP {'PASS' if ok else 'FAIL'}: {rt!r}")
    # Repurposed punctuation must land in Latin runs, not Kruti runs.
    runs = unicode_to_krutidev_runs("खण्ड 'अ': प्रश्न (Fundamental Rights) देखें।")
    ok = any(":" in t for t, is_latin in runs if is_latin)
    failures += not ok
    print(f"RUNS {'PASS' if ok else 'FAIL'}: {runs}")

    # render_runs("...", "krutidev") must equal unicode_to_krutidev_runs.
    kr_runs, kr_font = render_runs("भारत Test", "krutidev")
    ok = kr_runs == unicode_to_krutidev_runs("भारत Test") and kr_font == "Kruti Dev 010"
    failures += not ok
    print(f"RENDER krutidev {'PASS' if ok else 'FAIL'}: {kr_runs} font={kr_font}")

    # render_runs("...", "unicode") must keep Devanagari unchanged + split Latin.
    uni_runs, uni_font = render_runs("भारत Test", "unicode")
    hindi_kept = any("भारत" in t for t, is_latin in uni_runs if not is_latin)
    latin_split = any(t == "Test" for t, is_latin in uni_runs if is_latin)
    ok = hindi_kept and latin_split and uni_font == "Nirmala UI"
    failures += not ok
    print(f"RENDER unicode {'PASS' if ok else 'FAIL'}: {uni_runs} font={uni_font}")

    raise SystemExit(1 if failures else 0)
