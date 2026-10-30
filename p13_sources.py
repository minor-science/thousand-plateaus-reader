"""Rebuild plateau 13's French and Minnesota text, chunk by chunk, for the reader only.

Jo's plateau 13 variorum (variorum_from_rtf.md) has Minnesota cells that are often incomplete and French cells
with OCR'd note text inside the body, so sentence alignment fails there. This module rebuilds the two columns:
  - French: the Minuit 2013 epub (~/Downloads, chap013.html), body and notes kept apart, matched to the
    variorum's own French chunk by chunk (same language, word overlap);
  - English: Massumi's text from two OCRs (sources_text/core/deleuze_guattari_atp.txt and atp_athlone_1987.txt),
    taking each page from whichever reads better, matched to chunks through Jo's annotated translation
    (shared vocabulary plus length).
The variorum itself is never changed. Output exists only inside reader.html, which stays a local file.
"""
import glob
import html
import os
import re
import unicodedata
import zipfile
from pathlib import Path

HERE = Path(__file__).parent
KIT = Path.home() / "Downloads/protevi-response/sources_text/core"
WORDS = set(w.strip().lower() for w in open("/usr/share/dict/words"))
STOP = set("""the and for that with this from which they their there than then into only also more what when where
this these those have been were will would could should being other such through upon over under about after before
while whose itself themselves between because therefore however each every some most many much very even just
dans pour avec sont mais nous elle elles leur leurs plus comme tout tous toute toutes cette ces qui que quoi dont
être etre avoir fait sans sous entre aussi encore même meme autre autres deux""".split())


def strip_accents(s):
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def sentences(text):
    from align_sentences import split
    return [re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", x))).strip() for x in split(html.escape(text, quote=False))]


def toks(s, stem=5):
    w = re.findall(r"[a-z]{4,}", strip_accents(s.lower()))
    return {x[:stem] for x in w if x not in STOP}


# ---------- sources ----------

def epub_chapter13():
    return epub_chapter("OEBPS/chap013.html")


def epub_chapter(fname):
    E = glob.glob(os.path.expanduser("~/Downloads/Mille plateaux_*.epub"))[0]
    s = zipfile.ZipFile(E).read(fname).decode("utf-8")
    s = re.sub(r"(?s)<head>.*?</head>", "", s)
    s = re.sub(r'<a class="renvoi"[^>]*>\s*\d+\s*</a>', "", s)          # note calls, as the epub marks them
    s = re.sub(r"<br\s*/?>|</p>|</div>|</h\d>", "\n", s)
    s = html.unescape(re.sub(r"<[^>]+>", "", s)).replace("’", "'")
    # notes: the run of numbered paragraphs at the end ("1. ...", "2. ..." up to the last)
    starts = [m.start() for m in re.finditer(r"\n\s*1\.\s", s)]
    cut = starts[-1] if starts else len(s)
    body, notes_txt = s[:cut], s[cut:]
    notes = {}
    for m in re.finditer(r"\n\s*(\d{1,3})\.\s(.*?)(?=\n\s*\d{1,3}\.\s|\Z)", "\n" + notes_txt.strip(), re.S):
        notes[int(m.group(1))] = re.sub(r"\s+", " ", m.group(2)).strip()
    body = re.sub(r"([^\W\d_])(\d{1,3})(?=[\s.,;:)»])", r"\1", body)    # any note call left glued to a word « mot12 »
    body = re.sub(r"[ \t]+", " ", body)
    paras = [p.strip() for p in re.split(r"\n\s*\n|\n", body) if p.strip()]
    return paras, notes


def dict_share(t):
    ws = re.findall(r"[A-Za-z]+", t)
    return sum(1 for w in ws if w.lower() in WORDS) / max(1, len(ws))


def massumi_p13():
    core = open(KIT / "deleuze_guattari_atp.txt", errors="ignore").read().split("\f")
    ath = open(KIT / "atp_athlone_1987.txt", errors="ignore").read().split("\f")
    amap = {}
    for i, pg in enumerate(ath):
        for n in re.findall(r"^\s*(\d{3})\s*$", pg, re.M)[:1]:
            amap.setdefault(int(n), i)
    pages = []
    for p in range(424, 474):
        cands = [core[p + 20]] if p + 20 < len(core) else []
        if p in amap:
            cands.append(ath[amap[p]])
        best = max(cands, key=dict_share)
        lines = [l for l in best.splitlines()
                 if l.strip() and not re.fullmatch(r"\s*[\dDO ]{1,9}\s*", l)
                 and not re.search(r"APPARATUS OF CAPTURE|7000 B\.C\.|^\s*\d{3}\s*$", l)]
        pages.append("\n".join(lines))
    t = "\n".join(pages)
    t = t.split("14. 1440")[0]
    if not t.lstrip().startswith("13."):
        t = "13. 7000 B.C.: Apparatus of Capture\n" + t
    t = re.sub(r"(\w)-\n(\w)", r"\1\2", t)
    t = re.sub(r"PROPOSITION ([IVX])\s([IVX])\b", r"PROPOSITION \1\2", t)
    t = re.sub(r"\s*\n\s*", " ", t)
    import sys
    sys.path.insert(0, str(HERE / "nomadology"))
    from build_row import fix_en
    t = fix_en(t)
    # stray note calls left by the OCR at sentence starts ("... Orient. 1 5 Once again")
    t = re.sub(r'(?<=[.!?"”’)])\s+\d(?:\s?\d){0,2}\s+(?=[A-Z"“])', " ", t)
    return t


# ---------- alignment ----------

BEADS = [(1, 1, 0.0), (1, 2, 0.5), (2, 1, 0.5), (2, 2, 1.0), (1, 3, 1.0), (3, 1, 1.0)]


def sim(a, b):
    if not a or not b:
        return 0.0
    return 2 * len(a & b) / (len(a) + len(b))


def align_global(src, tgt, src_toks, tgt_toks, skip_src=0.9, skip_tgt=0.9, band_frac=0.06):
    """Banded DP over two sentence sequences. Returns, for each target sentence, the index of the source
    sentence it was matched with (or None)."""
    n, m = len(src), len(tgt)
    band = int(band_frac * max(n, m)) + 40
    INF = float("inf")
    cost = {(0, 0): 0.0}
    back = {}
    LS = [len(x) + 1 for x in src]
    LT = [len(x) + 1 for x in tgt]
    rs = sum(LT) / sum(LS)
    for i in range(n + 1):
        jc = int(i * m / max(1, n))
        for j in range(max(0, jc - band), min(m, jc + band) + 1):
            c = cost.get((i, j))
            if c is None:
                continue
            for di, dj, pen in BEADS + [(1, 0, skip_src), (0, 1, skip_tgt)]:
                ii, jj = i + di, j + dj
                if ii > n or jj > m:
                    continue
                if di and dj:
                    a = set().union(*src_toks[i:ii])
                    b = set().union(*tgt_toks[j:jj])
                    ls, lt = sum(LS[i:ii]) * rs, sum(LT[j:jj])
                    step = pen + 2.2 * (1 - sim(a, b)) + 0.6 * abs(ls - lt) / (ls + lt)
                else:
                    step = pen
                nc = c + step
                if nc < cost.get((ii, jj), INF):
                    cost[(ii, jj)] = nc
                    back[(ii, jj)] = (i, j, di, dj)
    match = [None] * m
    ij = (n, m)
    if ij not in back:
        return match
    while ij != (0, 0):
        i, j, di, dj = back[ij]
        if di and dj:
            for k in range(j, j + dj):
                match[k] = i
        ij = (i, j)
    return match


def assign(match, src_chunk, m):
    """Target sentence -> chunk, filling unmatched ones from their neighbours."""
    out = [src_chunk[x] if x is not None else None for x in match]
    last = None
    for k in range(m):
        if out[k] is None:
            out[k] = last
        else:
            last = out[k]
    nxt = None
    for k in range(m - 1, -1, -1):
        if out[k] is None:
            out[k] = nxt
        else:
            nxt = out[k]
    return out


def refine(tgt_toks, chunk_of, src_heads, window=8):
    """Move each chunk boundary in the target sequence to the sentence that best matches the opening of the
    next chunk on the source side. src_heads[n] = token sets of chunk n's first source sentences."""
    order = []
    for c in chunk_of:
        if c is not None and (not order or order[-1] != c):
            order.append(c)
    order = list(dict.fromkeys(order))
    starts = {}
    for k, c in enumerate(chunk_of):
        starts.setdefault(c, k)
    bounds = [starts[c] for c in order]
    for idx in range(1, len(order)):
        b, n = bounds[idx], order[idx]
        heads = src_heads.get(n) or []
        if not heads:
            continue
        lo = max(bounds[idx - 1] + 1, b - window)
        hi = min(len(tgt_toks) - 1, b + window)
        if idx + 1 < len(bounds):
            hi = min(hi, bounds[idx + 1] - 1)
        best, bestk = -1.0, b
        for k in range(lo, hi + 1):
            sc = max(sim(tgt_toks[k], h) for h in heads[:2])
            if k + 1 < len(tgt_toks):
                sc = max(sc, 0.9 * sim(tgt_toks[k] | tgt_toks[k + 1], heads[0]))
            sc -= 0.02 * abs(k - b)
            if sc > best:
                best, bestk = sc, k
        if best >= 0.35:
            bounds[idx] = bestk
    out = [None] * len(chunk_of)
    for idx, n in enumerate(order):
        end = bounds[idx + 1] if idx + 1 < len(bounds) else len(chunk_of)
        for k in range(bounds[idx], end):
            out[k] = n
    for k in range(0, bounds[0] if bounds else 0):
        out[k] = order[0]
    return out


def heads_of(sents, chunk_ids, tok, minlen=40):
    h = {}
    for s, n in zip(sents, chunk_ids):
        if len(s) >= minlen and len(h.get(n, [])) < 3:
            h.setdefault(n, []).append(tok(s))
    return h


def rebuild(chunks):
    """chunks: list of dicts with n, fr_plain (variorum French), an_plain (annotated body), note_nums.
    Returns {n: {"fr": str, "en": str, "frnotes": str}}."""
    # English
    an_sents, an_chunk = [], []
    for c in chunks:
        for s in sentences(c["an_plain"]):
            an_sents.append(s)
            an_chunk.append(c["n"])
    en_sents = sentences(massumi_p13())
    match = align_global(an_sents, en_sents, [toks(s) for s in an_sents], [toks(s) for s in en_sents])
    en_toks = [toks(s) for s in en_sents]
    en_chunk = assign(match, an_chunk, len(en_sents))
    # French
    paras, notes = epub_chapter13()
    fr_sents = [s for p in paras for s in sentences(p)]
    ocr_sents, ocr_chunk = [], []
    for c in chunks:
        for s in sentences(c["fr_plain"]):
            ocr_sents.append(s)
            ocr_chunk.append(c["n"])
    fmatch = align_global(ocr_sents, fr_sents, [toks(s, 6) for s in ocr_sents], [toks(s, 6) for s in fr_sents],
                          skip_src=0.7, skip_tgt=1.2)
    fr_chunk = assign(fmatch, ocr_chunk, len(fr_sents))
    out = {c["n"]: {"fr": [], "en": [], "frnotes": []} for c in chunks}
    for s, n in zip(en_sents, en_chunk):
        if n is not None:
            out[n]["en"].append(s)
    for s, n in zip(fr_sents, fr_chunk):
        if n is not None:
            out[n]["fr"].append(s)
    for c in chunks:
        for k in c["note_nums"]:
            if k in notes:
                out[c["n"]]["frnotes"].append(f"{k}. {notes[k]}")
    return {n: {k: " ".join(v) for k, v in d.items()} for n, d in out.items()}


# ---------- anchor method (used by the reader) ----------

def word_stream(text):
    """Normalized words with their character offsets in text."""
    out = []
    for m in re.finditer(r"[^\W\d_]+", text):
        w = strip_accents(m.group(0).lower())
        if len(w) >= 2:
            out.append((w, m.start()))
    return out


def ngram_index(ws, k):
    idx = {}
    for i in range(len(ws) - k + 1):
        idx.setdefault(tuple(w for w, _ in ws[i:i + k]), []).append(i)
    return idx


def find_start(src_text, ws, idx, k, after, limit, probe=80, need=3):
    """Word index in the stream where src_text begins. Each k-gram from the first `probe` words of src_text
    votes for (position - offset); the earliest start after `after` with at least `need` votes wins.
    Repeated phrases cannot win alone. None if no start gathers enough votes within `limit` words."""
    sw = [w for w, _ in word_stream(src_text)]
    votes = {}
    for off in range(0, min(probe, max(0, len(sw) - k + 1))):
        for pos in idx.get(tuple(sw[off:off + k]), []):
            st = pos - off
            if after - 30 <= st <= after + limit:
                # allow a few words of slack for OCR insertions or deletions
                key = st // 6
                votes[key] = votes.get(key, []) + [st]
    good = [(min(v), len(v)) for v in votes.values() if len(v) >= need]
    if not good:
        return None
    return max(after, min(good)[0])


def sentence_starts(text):
    from align_sentences import END_RX
    starts = [0]
    for m in END_RX.finditer(text):
        starts.append(m.end(4))
    # a section number (« 1. Adjonction », « PROPOSITION X I. ») belongs with its heading, never at a chunk's end
    nums = {m.end(): m.start(1) for m in re.finditer(r"[.!?»\"”]\s+((?:\d{1,2}\s?\.|PROPOSITION [IVX ]+\.)\s*)", text)}
    return sorted({nums.get(x, x) for x in starts})


def snap(char_pos, starts):
    return min(starts, key=lambda s: abs(s - char_pos))


def rebuild_anchored(chunks):
    """chunks: dicts with n, fr_plain, en_plain (the variorum's own, possibly partial, Minnesota cell),
    note_nums. Returns {n: {"fr", "en", "frnotes", "anchor_en"}}."""
    paras, notes = epub_chapter13()
    fr_text = "\n".join(paras)
    en_text = massumi_p13()
    fws, ews = word_stream(fr_text), word_stream(en_text)
    fidx, eidx = ngram_index(fws, 5), ngram_index(ews, 5)
    # French starts
    fstart, after = [], 0
    for c in chunks:
        p = find_start(c["fr_plain"], fws, fidx, 5, after, 4000)
        fstart.append(p)
        if p is not None:
            after = p + 1
    # English starts from the variorum's partial Minnesota cells
    estart, after = [], 0
    for c in chunks:
        p = find_start(c["en_plain"], ews, eidx, 5, after, 4000) if c["en_plain"] else None
        estart.append(p)
        if p is not None:
            after = p + 1
    # fill gaps by interpolation on French word positions
    def interp(starts, ref, total):
        known = [(i, s) for i, s in enumerate(starts) if s is not None]
        out = list(starts)
        for i, s in enumerate(starts):
            if s is not None:
                continue
            prev = max((k for k in known if k[0] < i), default=None)
            nxt = min((k for k in known if k[0] > i), default=None)
            if prev and nxt and ref[i] is not None and ref[prev[0]] is not None and ref[nxt[0]] is not None and ref[nxt[0]] > ref[prev[0]]:
                f = (ref[i] - ref[prev[0]]) / (ref[nxt[0]] - ref[prev[0]])
                out[i] = int(prev[1] + f * (nxt[1] - prev[1]))
            elif prev and nxt:
                out[i] = int(prev[1] + (nxt[1] - prev[1]) * (i - prev[0]) / (nxt[0] - prev[0]))
            elif prev:
                out[i] = prev[1]
            else:
                out[i] = 0
        return out
    fstart = interp(fstart, list(range(len(chunks))), len(fws))
    anchored = [s is not None for s in estart]
    estart = interp(estart, fstart, len(ews))
    # monotone, snapped to sentence starts
    fs, es = sentence_starts(fr_text), sentence_starts(en_text)
    fc = [snap(fws[min(p, len(fws) - 1)][1], fs) for p in fstart]
    ec = [snap(ews[min(p, len(ews) - 1)][1], es) for p in estart]
    for arr in (fc, ec):
        arr[0] = 0
        for i in range(1, len(arr)):
            arr[i] = max(arr[i], arr[i - 1])
    out = {}
    for i, c in enumerate(chunks):
        fend = fc[i + 1] if i + 1 < len(chunks) else len(fr_text)
        eend = ec[i + 1] if i + 1 < len(chunks) else len(en_text)
        fn = [f"{k}. {notes[k]}" for k in c["note_nums"] if k in notes]
        out[c["n"]] = {"fr": re.sub(r"\s+", " ", fr_text[fc[i]:fend]).strip(),
                       "en": re.sub(r"\s+", " ", en_text[ec[i]:eend]).strip(),
                       "frnotes": " ".join(fn), "anchor_en": anchored[i]}
    return out
