"""Massumi's endnotes (Minnesota edition) for plateaus 12 and 13, attached to the chunk where the note call falls.

Used by build_reader.py. Note text: the Athlone 1987 OCR (sources_text/core/atp_athlone_1987.txt), chapter 12 notes
and chapter 13 notes, kept as OCR'd (the OCR drops the accents on French names). Where a call falls:
  - plateau 12: the superscript calls in the Minnesota column of the variorum (APPROX12 for the six the OCR lost);
  - plateau 13: the call is found in the OCR body (a digit glued to the end of a word, in numerical order) and its
    lead-in words are located in the chunk's rebuilt Minnesota column (APPROX13 for the ones the scan cannot place).
Each attached note: {n, t, after (the words the call follows, plateau 13), approx (placed by judgment)}.
"""
import html
import re
import unicodedata
from pathlib import Path

SRC = Path.home() / "Downloads/protevi-response/sources_text/core/atp_athlone_1987.txt"
SUP = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹", "0123456789")
APPROX12 = {10: 9, 14: 16, 40: 55, 41: 56, 42: 59, 89: 131}     # calls the OCR lost; chunk chosen from the note's subject
APPROX13 = {1: 1}
RUNNING = r"(?:7000 B\.C\.: APPARATUS OF CAPTURE|THE SMOOTH AND THE STRIATED|1227: TREATISE ON NOMADOLOGY—THE WAR MACHINE)"


def _lines():
    return SRC.read_text().split("\n")


def _find(L, rx, after=0):
    return next(i for i, l in enumerate(L) if i > after and re.match(rx, l.strip()))


def parse(lines):
    notes, cur, exp = {}, None, 1
    for ln in lines:
        s = ln.strip()
        if not s or re.match(r"^(\d+\s*[□D0O]\s*)?NOTES TO PP", s):
            continue
        m = re.match(r"^(\d(?: ?\d){0,2})\s?\.\s*(\S.*)", s)
        num = int(m.group(1).replace(" ", "")) if m else None
        if m and num in (exp, exp + 1, exp + 2) and (m.group(2)[0].isupper() or m.group(2)[0] in "[(\"“"):
            cur = num
            notes[cur] = m.group(2)
            exp = num + 1
        elif cur:
            notes[cur] += " " + s
    return {k: re.sub(r"\s+", " ", v).strip() for k, v in notes.items()}


def endnote_text():
    L = _lines()
    a12 = _find(L, r"^12\.\s*1227: Treatise on Nomadology", 21000)
    a13 = _find(L, r"^13\.\s*7000 B\.C\.: Apparatus of Capture", a12)
    a14 = _find(L, r"^14\.\s*1440", a13)
    return parse(L[a12 + 1:a13]), parse(L[a13 + 1:a14])


def _norm(t):
    t = unicodedata.normalize("NFD", t.lower())
    return re.sub(r"[^a-z0-9]", "", "".join(c for c in t if unicodedata.category(c) != "Mn"))


def _plain(h):
    h = re.sub(r'<span class="g">.*?</span>', "", h, flags=re.S)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", h))).strip()


def p13_calls(total):
    """{k: the words before call k} from the OCR body of chapter 13, calls in numerical order."""
    L = _lines()
    a = _find(L, r"^13\.\s*7000 B\.C\.: Apparatus of Capture", 1000)
    b = _find(L, r"^1440: THE SMOOTH AND THE STRIATED", a)
    body = "\n".join(L[a:b])
    body = re.sub(r"\n(?:\d+\s*[□D0]\s*)?" + RUNNING + r"(?:\s*[□D0]?\s*\d+)?\n", "\n", body)
    pos, out = 0, {}
    for k in range(1, total + 1):
        rx = re.compile(r'(?<=[A-Za-z.,;:!?"”’)\]])' + r"\s?".join(str(k)) + r'(?![0-9])(?=[\s.,;:)"”]|$)')
        m = rx.search(body, pos)
        out[k] = None
        if m:
            out[k] = body[max(0, m.start() - 70):m.start()].replace("\n", " ")
            pos = m.end()
    return out


def attach(data):
    n12, n13 = endnote_text()
    for P in data["plateaus"]:
        notes = n12 if P["id"] == "12" else n13
        where, approx, after = {}, set(), {}
        txt = {c["n"]: _norm(_plain(" ".join(r[1] for r in c["rows"]))) for c in P["chunks"]}
        if P["id"] == "12":
            for c in P["chunks"]:
                for r in c["rows"]:
                    for x in re.findall(r"[⁰¹²³⁴⁵⁶⁷⁸⁹]+", _plain(r[1])):
                        where.setdefault(int(x.translate(SUP)), c["n"])
            for k, n in APPROX12.items():
                if k not in where:
                    where[k], _ = n, approx.add(k)
        else:
            cat, off = "", {}
            for n in sorted(txt):
                off[n] = len(cat)
                cat += txt[n]
            prev = 0
            for k, ctx in p13_calls(len(notes)).items():
                n = None
                if ctx:
                    for L_ in (40, 30, 22, 15):
                        key = _norm(ctx)[-L_:]
                        hits = [m.start() + len(key) - 1 for m in re.finditer(re.escape(key), cat)]
                        chs = [max(x for x in off if off[x] <= h) for h in hits]
                        chs = [x for x in chs if x >= prev]
                        if len(set(chs)) == 1:
                            n = chs[0]
                            break
                    if n is None and chs:
                        n = chs[0]
                if n is None:
                    n = APPROX13.get(k, prev)
                    approx.add(k)
                where[k] = n
                after[k] = re.sub(r"^\S*\s", "", ctx[-48:]).strip() if ctx else ""
                prev = n
        for c in P["chunks"]:
            c["mnotes"] = [dict(n=k, t=html.escape(notes[k], quote=False), after=html.escape(after.get(k, ""), quote=False),
                                approx=k in approx) for k in sorted(notes) if where.get(k) == c["n"]]
        missing = [k for k in notes if k not in where]
        assert not missing, (P["id"], missing)
    return data
