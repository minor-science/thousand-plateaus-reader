"""Build the variorum reader for plateaus 12-13: one self-contained HTML file.

    python3 build_reader.py      -> reader.html (open it in a browser; no server needed)

Reads, and never changes:
  nomadology/variorum_nomadology.md, nomadology/flags_p12.log, nomadology/context_p12.md   (plateau 12)
  variorum_from_rtf.md, flags.log, context_p13.md                                         (plateau 13)
Rebuild after any new row, swap, or context rebuild. The page holds the text of A Thousand Plateaus:
keep it a local file, never publish it.
"""
import html
import os
import json
import re
import unicodedata
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import align_sentences

HERE = Path(__file__).parent
PLATEAUS = [
    dict(id="12", title="12. Treatise on Nomadology", master=HERE / "nomadology/variorum_nomadology.md",
         row=r"^\| 12¶(\d+) (.*?)\|", flags=HERE / "nomadology/flags_p12.log", context=HERE / "nomadology/context_p12.md",
         ctx_head=r"^## 12¶(\d+)"),
    dict(id="13", title="13. Apparatus of Capture", master=HERE / "variorum_from_rtf.md",
         row=r"^\| ¶(\d+) (.*?)\|", flags=HERE / "flags.log", context=HERE / "context_p13.md",
         ctx_head=r"^## ¶(\d+)"),
]
GLOSS = re.compile(r'\*\*\*([^*]+)\*\*\*(\s*)<span style="color:green">\[(.*?)\]</span>')


def key(t):
    t = unicodedata.normalize("NFD", t.lower())
    return re.sub(r"[^a-z0-9 ]", "", "".join(c for c in t if unicodedata.category(c) != "Mn")).strip()


def md_inline(s):
    """Cell markdown to HTML. Cells already contain trusted HTML (span, u, i, br) written by the project."""
    s = s.replace("\\|", "|")
    s = GLOSS.sub(lambda m: f'<b class="t" data-k="{html.escape(key(m.group(1)))}">{m.group(1)}</b>{m.group(2)}'
                            f'<span class="g">[{m.group(3)}]</span>', s)
    s = s.replace('<span style="color:green">', '<span class="g">')   # glosses without a bold term in front
    s = re.sub(r"\*\*\*([^*]+)\*\*\*", r"<b><i>\1</i></b>", s)
    s = re.sub(r"(?<![\w*])\*([^*\n]+?)\*(?![\w*])", r"<i>\1</i>", s)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    return s


def pages(meta):
    fr = re.search(r"fr\.(\d+)", meta)
    um = re.search(r"umn\.(\d+)(?:-(\d+))?", meta)
    a = int(um.group(1)) if um else None
    b = um.group(2)
    if a and b:
        b = int(str(a)[: len(str(a)) - len(b)] + b)
    return (int(fr.group(1)) if fr else None, a, b or a)


SUP = "⁰¹²³⁴⁵⁶⁷⁸⁹"


def _fix_boundaries(chunks):
    """A sentence split by a chunk boundary goes with the chunk whose annotation translates it. The variorum does
    both (13¶59 finishes its sentence; 13¶54 opens by finishing 13¶53's), so the reader decides chunk by chunk,
    comparing Massumi's sentence with the end of one annotation and the start of the next."""
    import unicodedata
    import align_sentences as A

    def stems(h):
        t = html.unescape(re.sub(r"<[^>]+>", " ", re.sub(r'<span class="g">.*?</span>', " ", h))).lower()
        t = "".join(c for c in unicodedata.normalize("NFD", t) if unicodedata.category(c) != "Mn")
        return {w[:5] for w in re.findall(r"[a-z]{4,}", t)}

    def cover(sent, text):
        a = stems(sent)
        return len(a & stems(text)) / max(1, len(a))

    for prev, nxt in zip(chunks, chunks[1:]):
        pa, na = prev["_src"][2], nxt["_src"][2]
        if not pa or not na:
            continue
        tail_a, head_b = " ".join(A.split(pa)[-3:]), " ".join(A.split(na)[:3])
        for col in (0, 1):                                  # French, then Massumi, each on its own evidence
            S = A.split(nxt["_src"][col])
            if len(S) < 2:
                continue
            ca, cb = cover(S[0], tail_a), cover(S[0], head_b)
            if ca >= 0.45 and ca > cb + 0.2:
                p_ = list(prev["_src"]); n_ = list(nxt["_src"])
                p_[col] = p_[col] + " " + S[0]
                n_[col] = " ".join(S[1:])
                prev["_src"], nxt["_src"] = tuple(p_), tuple(n_)


FLAGGY = re.compile(r"(?i:flag|verified|restoration|Minnesota|scaffold|back-translat|endnote|Miller|supplied|truncat|segmentation)|Request|\bOCR\b|German original|ITALIAN|quoted via|internal find|unattributed|¶")
EDITORIAL = re.compile(r"QUOTATION FLAG|SEGMENTATION|Opening completes|tail, delivered|This row is footnote|French cell opens|Massumi likely|\bfn\.\s*\d+|Do not enter flags")


def _trim_an_heads(chunks):
    """Plateau 13 annotated cells sometimes open with the editor's own text (a QUOTATION FLAG, a bracketed remark,
    the tail of a footnote) before the annotation of the chunk begins, which pushes every annotated row out of line
    with the French and Massumi. The opening block is moved to the chunk's Flags ("Cell note") and the annotation
    starts where it begins to match Massumi's first sentences."""
    import unicodedata
    import align_sentences as A

    def stems(h):
        t = html.unescape(re.sub(r"<[^>]+>", " ", re.sub(r'<span class="g">.*?</span>', " ", h))).lower()
        t = "".join(c for c in unicodedata.normalize("NFD", t) if unicodedata.category(c) != "Mn")
        return {w[:5] for w in re.findall(r"[a-z]{4,}", t)}

    def dice(a, b):
        return 2 * len(a & b) / (len(a) + len(b)) if a and b else 0.0
    plainS = lambda s: html.unescape(re.sub(r"<[^>]+>", " ", re.sub(r'<span class="g">.*?</span>', " ", s)))
    for ci, c in enumerate(chunks):
        an, en = c["_src"][2], c["_src"][1]
        S, E = A.split(an), A.split(en)
        S = [x for s in S for x in re.split(r"(?<=\s\.)\s(?=[A-ZÀ-Ý])", s)]       # « the supplied French . En revanche »
        if len(S) < 3 or not E or re.match(r"\s*…", plainS(S[0])):
            continue                                # a continuation of the previous chunk's sentence: left as the variorum has it
        plain0 = html.unescape(re.sub(r"<[^>]+>", " ", S[0]))
        if re.match(r"\s*(?:\u26a0|\(|\[)", plain0) and EDITORIAL.search(" ".join(html.unescape(re.sub(r"<[^>]+>", " ", s)) for s in S[:3])):
            # an editor's note: runs through the sentences that still talk about the flag itself
            k = 0
            while k < len(S) - 1 and k < 14 and (k == 0 or FLAGGY.search(plainS(S[k])) or re.match(r"\s*(?:\d|\))", plainS(S[k]))):
                k += 1
        else:
            target = stems(" ".join(E[:2]))
            scores = [dice(target, stems(" ".join(S[k:k + 2]))) for k in range(min(len(S) - 1, 40))]
            k = max(range(len(scores)), key=lambda i: scores[i])
            if k == 0 or scores[k] < 0.25 or scores[0] > 0.6 * scores[k]:
                continue
            first = stems(E[0])
            while k + 1 < len(S) and dice(first, stems(S[k])) == 0 and dice(first, stems(S[k + 1])) > 0:
                k += 1                              # the window began on the last sentence of the editor's text
        # the last sentence of the editor's text may run straight into the annotation (« ... the supplied French. En revanche (...) »)
        if k >= 1:
            m_ = re.search(r"\.\s+(?=[A-ZÉ])", plainS(S[k - 1])) if False else None
        while k < len(S) - 1 and re.fullmatch(r"\s*[(\[]?\s*(?:…|\.\.\.)\s*[)\]]?\s*", plainS(S[k])):
            k += 1                                  # a lone « (…) » elision mark
        head = S[:k]
        plain = html.unescape(re.sub(r"<[^>]+>", " ", " ".join(head)))
        if k == 0 or not (EDITORIAL.search(plain) or re.match(r"\s*(?:\u26a0|\(|\[|[\u00b9\u00b2\u00b3\u2070-\u2079]|\u1d9c)", plain)):
            continue
        c["_src"] = c["_src"][:2] + (" ".join(S[k:]),) + c["_src"][3:]
        if re.match(r"\s*…", plainS(head[0])) and ci > 0:
            # not an editor's note: the tail of the previous chunk's last annotated sentence
            pv = chunks[ci - 1]
            pv["_src"] = pv["_src"][:2] + (pv["_src"][2] + " " + " ".join(head),) + pv["_src"][3:]
        else:
            c["flags"].append(dict(k="Cell note", t=re.sub(r"\s+", " ", " ".join(head)).strip()))


def _fix_fragments(chunks):
    """The variorum cuts chunks at page breaks, sometimes mid-sentence: a chunk's Minnesota or annotated cell then
    opens on the tail of the sentence the previous chunk began. The tail goes back to the chunk where its sentence
    starts, as the French (rebuilt whole from the epub) already does."""
    import align_sentences as A
    for k, nxt in enumerate(chunks):
        prev = next((c for c in reversed(chunks[:k]) if not c["_src"][2].lstrip().startswith("[Notes only")), None)
        if prev is None:
            continue
        for col in (1, 2):
            t = nxt["_src"][col]
            if t.lstrip().startswith("[Notes only"):
                continue
            plain = html.unescape(re.sub(r"<[^>]+>", "", t)).lstrip(" ,;:.…»)]\u201d\"[")
            if not plain or not plain[0].islower() or not prev["_src"][col].strip():
                continue
            S = A.split(t)
            if len(S) < 1:
                continue
            p_, n_ = list(prev["_src"]), list(nxt["_src"])
            p_[col] = p_[col] + " " + S[0]
            n_[col] = " ".join(S[1:])
            prev["_src"], nxt["_src"] = tuple(p_), tuple(n_)


def _refit(chunks, cols=(1, 0)):
    """Plateau-wide: re-cut French and Massumi sentences to the annotated column's chunks (chunk_fit.py)."""
    import align_sentences as A
    import chunk_fit
    real = [c for c in chunks if c["_src"][2].strip() and not c["_src"][2].lstrip().startswith("[Notes only")]
    stub = re.compile(r"\[\s*[–-]\s*(?:the sentence )?continues? (?:at|in|into) 1[23]¶\d+\s*\]")
    # a stub that only announces "continues at 12¶36" has its sentence in full at the head of the next chunk
    a_sents = [[s for s in A.split(c["_src"][2]) if not stub.search(html.unescape(re.sub(r"<[^>]+>", "", s)))] for c in real]
    for col in cols:
        x_sents = [A.split(c["_src"][col]) for c in real]
        # sentences of a notes-only chunk belong to its neighbours
        fixed = chunk_fit.refit(x_sents, a_sents)
        for c, ss in zip(real, fixed):
            t = list(c["_src"])
            t[col] = " ".join(ss)
            c["_src"] = tuple(t)


def _fix_en_boundaries(chunks, cols=(1, 0)):
    """Massumi's cell and Jo's annotated cell are cut at different places in the variorum. Jo's annotation follows
    the French, so it decides: a Massumi sentence at the edge of a chunk moves across the boundary when it shares
    more words with the annotated sentence on the other side."""
    import unicodedata
    import align_sentences as A

    def stems(h):
        t = html.unescape(re.sub(r"<[^>]+>", " ", re.sub(r'<span class="g">.*?</span>', " ", h))).lower()
        t = "".join(c for c in unicodedata.normalize("NFD", t) if unicodedata.category(c) != "Mn")
        return {w[:5] for w in re.findall(r"[a-z]{4,}", t)}

    def cover(sent, text):
        a = stems(sent)
        return len(a & stems(text)) / max(1, len(a))

    for prev, nxt in zip(chunks, chunks[1:]):
        for col in cols:
            thr = 0.4 if col == 1 else 0.3          # French shares only cognates and names with the annotation
            for _ in range(4):
                pa, na = prev["_src"][2], nxt["_src"][2]
                if not pa.strip() or not na.strip():
                    break
                tail_a, head_a = A.split(pa)[-1], A.split(na)[0]
                Sn, Sp = A.split(nxt["_src"][col]), A.split(prev["_src"][col])
                p_, n_ = list(prev["_src"]), list(nxt["_src"])
                if len(Sn) >= 2 and cover(Sn[0], tail_a) >= thr and cover(Sn[0], tail_a) > cover(Sn[0], head_a) + 0.15:
                    p_[col] = p_[col] + " " + Sn[0]
                    n_[col] = " ".join(Sn[1:])
                elif len(Sp) >= 2 and cover(Sp[-1], head_a) >= thr and cover(Sp[-1], head_a) > cover(Sp[-1], tail_a) + 0.15:
                    p_[col] = " ".join(Sp[:-1])
                    n_[col] = Sp[-1] + " " + n_[col]
                else:
                    break
                prev["_src"], nxt["_src"] = tuple(p_), tuple(n_)


def p13_annotated(an):
    """Plateau 13 cells: <br> are line wraps from the RTF conversion; a superscript alone on a line is a note
    call broken off its word; the notes start at the first line that opens with a superscript and text, or
    with a superscript whose next line is a reference. Returns (body, notes, note numbers)."""
    lines = [l.strip() for l in re.split(r"<br\s*/?>", an)]
    looks_ref = re.compile(r"\bpp?\.\s?\d|\b(?:Cf|Idem|Ibid|Id)\b|\b1[5-9]\d\d\b")
    start = None
    for i, l in enumerate(lines):
        prev = next((x for x in reversed(lines[:i]) if x), "")
        if re.search(rf"[{SUP}]$", prev):          # a broken note call continues here, not a note
            continue
        m = re.match(rf"([{SUP}]+)\s+(\S)", l)
        if m and m.group(2) != "[":
            start = i
            break
        if re.fullmatch(rf"[{SUP}]+", l):
            nxt = next((x for x in lines[i + 1:] if x), "")
            if looks_ref.search(nxt[:80]) and not re.fullmatch(rf"[{SUP}]+", nxt) and not nxt.startswith("["):
                if not prev or prev.endswith((".", "»", ")", "]")) or len(nxt) < 140:
                    start = i
                    break
    body_lines = lines[:start] if start is not None else lines
    note_lines = lines[start:] if start is not None else []
    body = ""
    for l in body_lines:
        if not l:
            continue
        if re.fullmatch(rf"[{SUP}]+", l) or re.match(r"[.,;:)»]", l) or (re.match(rf"[{SUP}]", l) and re.search(rf"[{SUP}]\s*$", body)):
            body = body.rstrip() + l + " "
        else:
            body += l + " "
    notes, nums = [], []
    for l in note_lines:
        if not l:
            continue
        if re.fullmatch(rf"[{SUP}]+", l) and notes and re.fullmatch(rf"[{SUP}]+", notes[-1]):
            notes[-1] += l
        elif notes and re.fullmatch(rf"[{SUP}]+", notes[-1]):
            notes[-1] += " " + l
        else:
            notes.append(l)
    tr = str.maketrans(SUP, "0123456789")
    for nl in notes:
        m = re.match(rf"([{SUP}]+)", nl)
        if m:
            nums.append(int(m.group(1).translate(tr)))
    for m in re.finditer(rf"(?<=[^\s{SUP}])([{SUP}]+)", body):      # note calls in the body
        k = int(m.group(1).translate(tr))
        if k not in nums:
            nums.append(k)
    return body.strip(), "<br>".join(notes), sorted(nums)


def split_fr_notes(fr, notes):
    """Plateau 12 rows carry the French note texts with the body: after it, and sometimes mid-cell where a page's
    notes fell. Split them off: a note starts with its number right after a sentence end, or at a « [N, suite ...] »
    marker; any sentence the Minuit epub prints among its notes and not in its body also goes to the notes."""
    nums = re.findall(r"Fr: (\d+)", notes)
    cands = [m.start() for m in re.finditer(r"\[\d+(?:, (?:suite|début)[^\]]*)?\]\s", fr) if m.start() > 0]
    for n in nums:
        cands += [m.start(1) for m in re.finditer(rf"(?<=[.»)\]] )({n}\s?\.\s)", fr)]
    cands = [c for c in cands if c > len(fr) * 0.25]
    cands += _note_tail(fr)
    k = min(cands) if cands else len(fr)
    body, tail = fr[:k].rstrip(), fr[k:].strip()
    keep, moved = _note_sents(body)
    return keep, " ".join(x for x in (moved, tail) if x)


_EPUB12 = None


def _grams(t):
    import unicodedata
    t = "".join(c for c in unicodedata.normalize("NFD", t.lower()) if unicodedata.category(c) != "Mn")
    w = re.findall(r"[a-z]+", t)
    return {" ".join(w[i:i + 4]) for i in range(len(w) - 3)}


def _note_tail(fr):
    """Where the trailing run of sentences that belong to the Minuit notes (not the body) begins, as found in the
    epub. Returns [] when the cell ends on body text."""
    global _EPUB12
    if _EPUB12 is None:
        import p13_sources
        paras, notes = p13_sources.epub_chapter("OEBPS/chap012.html")
        _EPUB12 = (_grams(" ".join(paras)), _grams(" ".join(notes.values())))
    body_g, note_g = _EPUB12
    import align_sentences
    sents = align_sentences.split(fr)
    pos, starts = 0, []
    for x in sents:
        i = fr.find(x[:40], pos)
        starts.append(i if i >= 0 else pos)
        pos = max(pos, starts[-1] + 1)
    cut = None
    for i in range(len(sents) - 1, 0, -1):
        g = _grams(re.sub(r"<[^>]+>", " ", sents[i]))
        if len(g) < 2:
            continue                        # too short to tell: keep scanning, decided by its neighbours
        if len(g & note_g) > 2 * len(g & body_g) and len(g & note_g) >= 0.4 * len(g):
            cut = starts[i]
        else:
            break
    return [cut] if cut is not None else []


def _note_sents(fr):
    """Sentences inside the body that the epub prints among its notes (a page's notes fallen mid-cell)."""
    import align_sentences
    _note_tail(fr)                                       # loads the epub
    body_g, note_g = _EPUB12
    keep, moved = [], []
    sents = align_sentences.split(fr)
    for i, x in enumerate(sents):
        g = _grams(re.sub(r"<[^>]+>", " ", x))
        notey = len(g) >= 4 and len(g & note_g) > 2 * len(g & body_g) and len(g & note_g) >= 0.5 * len(g)
        (moved if notey else keep).append(x)
    return " ".join(keep), " ".join(moved)


def flag_targets(bracket, plat):
    """'[12¶34-36]', '[12¶91 12¶102]', '[¶4]' -> chunk numbers."""
    out = []
    for a, b in re.findall(r"¶(\d+)(?:-(\d+))?", bracket):
        a = int(a)
        out += list(range(a, int(b) + 1)) if b else [a]
    return out


ORDER = ["QUOTE FLAG", "SENSE NOTE", "ALIGN FLAG", "REPAIR NOTE", "NOTE FLAG", "SPLIT NOTE", "CONTEXT",
         "RECEPTION NOTE", "ADDENDUM", "CORRECTION", "RESOLVED", "SWAP", "SWAPPED"]


def flag_kind(text):
    m = re.match(r"\s*([A-Z]{2,}(?: [A-Z]{2,})*)", text)
    k = m.group(1) if m else "NOTE"
    k = {"QUOTE FLAGS": "RESOLVED", "STATUS": "RESOLVED"}.get(k, k)
    rest = text[m.end():].lstrip(" :—-") if m else text
    rest = re.sub(r"^\([^)]*\)\s*[:—-]?\s*", lambda x: x.group(0) if k in ("RESOLVED", "SWAP", "ADDENDUM") else "", rest)
    return k, rest


data = {"plateaus": [], "ctx": [], "lex": {}}
ctx_index = {}
for P in PLATEAUS:
    chunks = []
    for line in P["master"].read_text().splitlines():
        m = re.match(P["row"], line)
        if not m:
            continue
        n = int(m.group(1))
        cells = re.split(r"(?<!\\)\|", line[2:-2])
        if len(cells) != 4:
            continue
        meta, fr, en, an = (c.strip() for c in cells)
        note_nums = []
        if P["id"] == "13":
            body, notes, note_nums = p13_annotated(an)
        else:
            body, _, notes = an.partition("<br>Notes:")
        frp, ua, ub = pages(meta)
        fr_body, fr_notes = (fr, "") if P["id"] == "13" else split_fr_notes(fr, notes)
        frh, enh, anh = md_inline(fr_body), md_inline(en), md_inline(body)
        chunks.append(dict(n=n, fr_page=frp, umn=[ua, ub], rows=None, _src=(frh, enh, anh, fr, en, body, note_nums),
                           notes=md_inline(notes.strip()), frnotes=md_inline(fr_notes), flags=[], ctx=[]))
        for term, _, gloss in GLOSS.findall(an):
            e = data["lex"].setdefault(key(term), {"term": term.strip(), "gloss": gloss, "where": []})
            ref = f"{P['id']}-{n}"
            if ref not in e["where"]:
                e["where"].append(ref)
    if P["id"] == "13":
        import p13_sources
        def plain(h):
            h = re.sub(r'<span style="color:green">.*?</span>', "", h)
            return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", h).replace("\\|", "|").replace("*", "")).strip()
        src = [dict(n=c["n"], fr_plain=plain(c["_src"][3]), en_plain=plain(c["_src"][4]), an_plain=plain(c["_src"][5]),
                    note_nums=c["_src"][6]) for c in chunks]
        # note numbers run upward through the plateau: drop calls far below what earlier chunks already reached
        # (a two-digit call that lost its second digit in the RTF, e.g. ⁴ for ⁴¹)
        high = 0
        for d in src:
            keep = [k for k in d["note_nums"] if k >= high - 3]
            d["note_nums"] = keep
            if keep:
                high = max(high, max(keep))
        R = p13_sources.rebuild_anchored(src)
        for c in chunks:
            r = R[c["n"]]
            c["_src"] = (html.escape(r["fr"], quote=False), html.escape(r["en"], quote=False), c["_src"][2])
            c["frnotes"] = html.escape(r["frnotes"], quote=False)
            c["rebuilt"] = True
        _trim_an_heads(chunks)
        _fix_boundaries(chunks)
    if P["id"] == "12":
        # French from the Minuit epub, whole (the variorum's cells are cut at every « [...] » page break)
        import p12_sources
        R12 = p12_sources.rebuild([dict(n=c["n"], notes_only=bool(re.match(r"\s*\[Notes only", c["_src"][4])), fr_plain=re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", c["_src"][3]).replace("\\|", "|")).strip())
                                   for c in chunks])
        for c in chunks:
            r = R12[c["n"]]
            c["_src"] = (html.escape(r["fr"], quote=False), c["_src"][1], c["_src"][2], c["_src"][3], c["_src"][4], c["_src"][5], c["_src"][6])
            c["frnotes"] = html.escape(r["frnotes"], quote=False)
            c["rebuilt"] = True
        _fix_fragments(chunks)
        _refit(chunks)
    for c in chunks:
        frh, enh, anh = c.pop("_src")[:3]
        c["rows"] = align_sentences.rows(frh, enh, anh)
    by_n = {c["n"]: c for c in chunks}
    for line in P["flags"].read_text().splitlines():
        m = re.match(r"^(\[[^\]]*\])\s*(.*)$", line)
        if not m:
            continue
        text = m.group(2)
        text = re.sub(r"^1[23]¶\d+\s*[—-]\s*", "", re.sub(r"^([A-Z ]+:)\s*1[23]¶\d+\s*[—-]\s*", r"\1 ", text))
        for n in flag_targets(m.group(1), P["id"]):
            if n in by_n:
                k, rest = flag_kind(text)
                by_n[n]["flags"].append(dict(k=k, t=md_inline(html.escape(rest, quote=False))))
    for c in chunks:
        c["flags"].sort(key=lambda f: ORDER.index(f["k"]) if f["k"] in ORDER else len(ORDER))
    cur = None
    for line in P["context"].read_text().splitlines():
        h = re.match(P["ctx_head"], line)
        if h:
            cur = by_n.get(int(h.group(1)))
            continue
        if cur is not None and line.startswith("- "):
            item = line[2:].strip()
            if item not in ctx_index:
                ctx_index[item] = len(data["ctx"])
                data["ctx"].append(md_inline(item))
            cur["ctx"].append(ctx_index[item])
    data["plateaus"].append(dict(id=P["id"], title=P["title"], chunks=chunks))

# Differences: words where the annotated translation and Massumi's sentence part ways, row by row
import compare
import french_help
_tr = french_help.Translator(data["lex"])
for P_ in data["plateaus"]:
    for c in P_["chunks"]:
        for r in c["rows"]:
            r[2], r[1] = compare.mark(r[2], r[1], _tr)
# French help: a short translation after every French word or phrase in the annotated column, once per row
for P_ in data["plateaus"]:
    for c in P_["chunks"]:
        for r in c["rows"]:
            r[2] = french_help.annotate(r[2], _tr, set())
        if c["notes"]:
            c["notes"] = french_help.annotate(c["notes"], _tr, set())
# Massumi's endnotes (Minnesota), placed at the chunk where each note call falls
import endnotes
endnotes.attach(data)
data["supp"] = {french_help.key(k): v for k, v in json.loads(french_help.SUPP.read_text()).items() if not k.startswith("_")}
data["short"] = _tr.t
# Where the annotation stops short of the French, say so instead of leaving a blank that looks like a fault
def _plain(h):
    return re.sub(r"<[^>]+>", "", h).strip()


for P_ in data["plateaus"]:
    for c in P_["chunks"]:
        for r in c["rows"]:
            if _plain(r[0]) and not _plain(r[2]):
                r[2] = '<span class="na">Not annotated in the variorum.</span>'
payload = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
page = (HERE / "reader_template.html").read_text().replace("/*DATA*/", payload)
(HERE / "reader.html").write_text(page)
n_flags = sum(len(c["flags"]) for p in data["plateaus"] for c in p["chunks"])
print(f"reader.html: {sum(len(p['chunks']) for p in data['plateaus'])} chunks, {n_flags} flags, "
      f"{len(data['ctx'])} background entries, {len(data['lex'])} lexicon terms, {len(page)//1024} KB")
