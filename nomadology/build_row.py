#!/usr/bin/env python3
"""Per-chunk tooling for the plateau 12 variorum ("Traité de nomadologie"), following ../PROCESS.md and
../apparatus_of_capture_prompt.md. The translation is drafted by a language model: it drafts Column 4 and supplies the
first and last words of the matching Minnesota passage. This script does the mechanical parts:

  python3 build_row.py show [n]        print chunk n (default: next) and the English to search
  python3 build_row.py add row.json    assemble, validate, and append one row, then advance .progress_p12

row.json: {"n": 1, "en_start": "first words", "en_end": "last words", "annot": "Column 4 HTML/markdown",
           "fr_repairs": [["bad", "good"]], "flags": ["QUOTE FLAG: ..."], "motifs": ["MOTIF CANDIDATE: ..."],
           "glossed": ["*term* — rendering / glossed at 12¶n ..."]}
          a notes-only chunk takes "en_none": "[Column 3 text]" in place of en_start/en_end; the cursor stays put

Files: variorum_nomadology.md (master, append-only), flags_p12.log, glossary_p12.md, .progress_p12, .en_cursor_p12
"""
import json, re, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
MASTER = HERE / "variorum_nomadology.md"
HEADER = "| Meta | French (Original) | English (Minnesota Translation) | English (Annotated Translation) |\n|---|---|---|---|\n"
WORDS = set(w.strip().lower() for w in open("/usr/share/dict/words")) | {"deleuze", "guattari", "clastres", "dumezil"}


def chunks():
    raw = (HERE / "chunks_p12.md").read_text()
    out = {}
    for block in raw.split("=== CHUNK ===")[1:]:
        head, _, body = block.strip().partition("\n")
        m = re.match(r"12¶(\d+) fr\.(\d+)", head)
        out[int(m.group(1))] = (int(m.group(2)), body.strip())
    return out


def english():
    """English text with page markers, plus a per-character page map."""
    t = (HERE / "en_nomadology.txt").read_text()
    text, pages, cur = [], [], None
    for part in re.split(r"(\[\[\d+\]\])", t):
        m = re.match(r"\[\[(\d+)\]\]", part)
        if m:
            cur = int(m.group(1))
            continue
        part = clean_en_page(part)
        text.append(part + " ")
        pages.extend([cur] * (len(part) + 1))
    return "".join(text), pages


def clean_en_page(s):
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"^\s*[\d ]{1,9}[0DO]?\s*1\s*2\s*2\s*7\s*:\s*TREATISE ON NOMA\s*DOLOGY\s*-?\s*THE WAR MACHINE\s*", "", s)
    s = re.sub(r"^\s*1\s*2\s*2\s*7\s*:\s*TREATISE ON NOMA\s*DOLOGY\s*-?\s*THE WAR MACHINE\s*[0DO]?\s*[\d ]{1,9}\s", "", s)
    s = re.sub(r"\s\d{3}\s*$", "", s)          # trailing page number
    return s.strip()


def squash(s):
    chars, idx = [], []
    for i, ch in enumerate(s):
        if ch.isalnum():
            chars.append(ch.lower())
            idx.append(i)
    return "".join(chars), idx


def known(w):
    w = w.lower()
    if w in WORDS:
        return True
    for suf, rep in (("ies", "y"), ("ied", "y"), ("ing", ""), ("ing", "e"), ("ed", ""), ("ed", "e"), ("es", ""), ("s", ""), ("ly", ""), ("er", ""), ("ers", ""), ("ity", "e"), ("ion", "e"), ("ions", "e")):
        if w.endswith(suf) and (w[: -len(suf)] + rep) in WORDS:
            return True
    return False


def fix_en(s):
    s = re.sub(r" 0 ?3 ?\d ?\d (?=[a-z])", " ", s)   # stray mid-page marker, e.g. '0 38 1' for p. 381
    """Silently repair OCR joins and splits in the Minnesota text, checked against the system dictionary."""
    def split_join(m):
        w = m.group(0)
        lw = w.lower()
        if known(lw) or len(lw) < 5:
            return w
        for pre in ("of", "to", "the", "and"):
            if lw.startswith(pre) and known(lw[len(pre):]) and len(lw) - len(pre) > 1:
                return w[:len(pre)] + " " + w[len(pre):]
        return w
    s = re.sub(r"[A-Za-z]+", split_join, s)
    toks = s.split(" ")
    out = []
    i = 0
    while i < len(toks):
        if i + 1 < len(toks):
            a, b = toks[i], toks[i + 1]
            core = re.sub(r"\W", "", a + b).lower()
            if a.isalpha() and re.match(r"^[a-z]+\W*$", b) and known(core) and (not known(a) or not known(re.sub(r"\W", "", b))):
                out.append(a + b)
                i += 2
                continue
        out.append(toks[i])
        i += 1
    s = " ".join(out)
    s = s.replace("B.c.", "B.C.").replace("·", "").replace(" ,", ",").replace(" .", ".").replace("( ", "(").replace(" )", ")")
    return s.replace("|", "\\|")


def fix_fr(s, repairs):
    s = re.sub(r"\s+", " ", s)
    for a, b in repairs:
        s = s.replace(a, b)
    s = re.sub(r"\b([lLdDnNsSjJmMtTcC]|qu|Qu|jusqu|lorsqu|puisqu) '", r"\1'", s)
    s = re.sub(r" ([.,)])", r"\1", s)
    s = s.replace("( ", "(").replace("­", "")
    for a, b in repairs:
        s = s.replace(a, b)
    return s.replace("|", "\\|")


def state(name, default):
    p = HERE / name
    return p.read_text().strip() if p.exists() else default


def show(n=None):
    cs = chunks()
    n = n or int(state(".progress_p12", "0")) + 1
    p, fr = cs[n]
    en, pages = english()
    cur = int(state(".en_cursor_p12", "0"))
    print(f"=== 12¶{n} fr.{p}  (of {len(cs)})\n{fr}\n\n=== ENGLISH from cursor {cur} (page {pages[cur] if cur < len(pages) else '?'})\n{en[cur:cur + len(fr) + 2200]}")


def add(path):
    d = json.loads(Path(path).read_text())
    n = d["n"]
    expected = int(state(".progress_p12", "0")) + 1
    if n != expected:
        sys.exit(f"next chunk is 12¶{expected}, not {n}")
    p, fr = chunks()[n]
    en, pages = english()
    cur = int(state(".en_cursor_p12", "0"))
    if d.get("en_none"):                         # notes-only chunk: no Minnesota body text to match
        return add_row(d, n, p, fr, d["en_none"], f"{pages[cur]}", cur)
    win = en[cur:cur + 30000]
    wsq, widx = squash(win)
    s_sq, e_sq = squash(d["en_start"])[0], squash(d["en_end"])[0]
    a = wsq.find(s_sq)
    if a == -1:
        sys.exit(f"en_start not found after cursor: {d['en_start']!r}")
    b = wsq.find(e_sq, a)
    if b == -1:
        sys.exit(f"en_end not found after en_start: {d['en_end']!r}")
    start, end = cur + widx[a], cur + widx[b + len(e_sq) - 1] + 1
    while end < len(en) and en[end] in "\"'”’.,;:!?)»":
        end += 1
    passage = en[start:end].strip()
    for x, y in d.get("en_repairs", []):
        passage = passage.replace(x, y)
    passage = fix_en(passage)
    pg = sorted({pages[i] for i in range(start, end) if pages[i]})
    umn = f"{pg[0]}" if len(pg) == 1 else f"{pg[0]}-{str(pg[-1])[-2:]}"
    return add_row(d, n, p, fr, passage, umn, end)


def add_row(d, n, p, fr, passage, umn, end):
    annot = d["annot"].strip()
    problems = []
    if "\n" in annot:
        problems.append("raw line break in Column 4")
    if annot.count('<span style="color:green">') != annot.count("</span>"):
        problems.append("unbalanced <span>")
    if annot.count("<u>") != annot.count("</u>"):
        problems.append("unbalanced <u>")
    if re.search(r"(?<!\\)\|", annot):
        problems.append("unescaped pipe in Column 4")
    bold = re.findall(r"\*\*\*([^*]+)\*\*\*(\s*\S*\s*<span style=\"color:green\">)?", annot)
    if any(not br for _, br in bold):
        problems.append("bold-italic term without a following bracket (iff rule)")
    if problems:
        sys.exit("refused: " + "; ".join(problems))
    row = f"| 12¶{n} fr.{p} umn.{umn} | {fix_fr(fr, d.get('fr_repairs', []))} | {passage} | {annot} |\n"
    if not MASTER.exists():
        MASTER.write_text(HEADER)
    with MASTER.open("a") as f:
        f.write(row)
    with (HERE / "flags_p12.log").open("a") as f:
        for fl in d.get("flags", []):
            f.write(f"[12¶{n}] {fl}\n")
    gl = HERE / "glossary_p12.md"
    g = gl.read_text()
    for line in d.get("glossed", []):
        g = g.replace("\n## Candidates (unreviewed)", f"\n{line}\n## Candidates (unreviewed)", 1)
    for line in d.get("motifs", []):
        g += f"{line}\n"
    gl.write_text(g)
    (HERE / ".progress_p12").write_text(str(n))
    (HERE / ".en_cursor_p12").write_text(str(end))
    print(f"12¶{n} done · umn.{umn} · {len(d.get('flags', []))} flags · {len(bold)} glossed terms")


if __name__ == "__main__":
    if sys.argv[1] == "show":
        show(int(sys.argv[2]) if len(sys.argv) > 2 else None)
    elif sys.argv[1] == "add":
        add(sys.argv[2])
