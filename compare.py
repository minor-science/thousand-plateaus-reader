"""Mark where Jo's annotated translation and Massumi's sentence differ, row by row, for the reader.

Words in a row's annotated text that have no counterpart in Massumi's sentence (and the reverse) are wrapped in
<span class="dv">. French terms, Jo's gloss brackets, and small connecting words are left out of the comparison,
so the highlight shows real divergence, not noise.
"""
import difflib
import html
import re
import unicodedata

import french_help

STOP = set("""a an the of to in on at by for with from as and or but nor so that this these those it its is are was
were be been being has have had do does did not no than then there their they them he his him she her we our you
your i me my which who whom whose what when where while if into upon also only more most such each every some any
all one two other same very just even""".split())
SKIP = re.compile(r'(<span class="g">.*?</span>|<b class="t"[^>]*>.*?</b>|<i class="lx"[^>]*>.*?</i>|<[^>]+>)', re.S)
WORD = re.compile(r"[^\W\d_]+(?:['’][^\W\d_]+)*")


def norm(w):
    w = "".join(c for c in unicodedata.normalize("NFD", w.lower()) if unicodedata.category(c) != "Mn")
    w = w.replace("’", "'")
    for suf in ("ies", "es", "s", "ed", "ing", "ly"):
        if len(w) > len(suf) + 3 and w.endswith(suf):
            return w[: -len(suf)]
    return w


def tokens(h, tr=None, annotated=False):
    """[(part_index, start, end, normalized, real)] for words outside glosses and tags. In the annotated column,
    French runs and Jo's glossed terms are not compared as French: their translation stands in for them
    (virtual tokens, never highlighted)."""
    parts = SKIP.split(h)
    toks = []
    emph = 0                                   # inside <b>/<i>: Jo's marked French
    for pi, p in enumerate(parts):
        if not p:
            continue
        if re.match(r"<(b|i|em|strong)>", p):
            emph += 1
            continue
        if re.match(r"</(b|i|em|strong)>", p):
            emph = max(0, emph - 1)
            continue
        if annotated and emph and not p.startswith("<"):
            text = html.unescape(p)
            if tr is not None and text.strip():
                g, _ = tr.lookup(text.strip())
                if g:
                    toks += [(pi, 0, 0, norm(w), False) for w in WORD.findall(g)]
                else:
                    for m in WORD.finditer(text):
                        gg, _ = tr.lookup(m.group(0))
                        toks += [(pi, m.start(), m.start(), norm(w), False) for w in WORD.findall(gg or "")]
            continue
        if p.startswith('<b class="t"'):
            if annotated:
                nxt = next((q for q in parts[pi + 1:] if q and q.strip()), "")
                if nxt.startswith('<span class="g">'):
                    head = french_help.short_gloss(re.sub(r"<[^>]+>", "", nxt).strip("[] "))
                    toks += [(pi, 0, 0, norm(w), False) for w in WORD.findall(head)]
            continue
        if p.startswith('<i class="lx"'):
            if annotated and tr is not None:
                g, _ = tr.lookup(html.unescape(re.sub(r"<[^>]+>", "", p)))
                if g:
                    toks += [(pi, 0, 0, norm(w), False) for w in WORD.findall(g)]
            continue
        if p.startswith("<"):
            continue
        text = html.unescape(p)
        excluded = []
        if annotated:
            for a, b, phrase in french_help.runs(text):
                excluded.append((a, b))
                if tr is not None:
                    g, _ = tr.lookup(phrase)
                    if g:
                        toks += [(pi, a, a, norm(w), False) for w in WORD.findall(g)]
        for m in WORD.finditer(text):
            if any(a <= m.start() < b for a, b in excluded):
                continue
            toks.append((pi, m.start(), m.end(), norm(m.group(0)), True))
    toks.sort(key=lambda t: (t[0], t[1]))
    return parts, toks


def wrap(parts, toks, marked):
    """Rebuild HTML, wrapping marked tokens (merged within a part when adjacent)."""
    by_part = {}
    for i in marked:
        pi, a, b, _, real = toks[i]
        if not real:
            continue
        by_part.setdefault(pi, []).append((a, b))
    out = []
    for pi, p in enumerate(parts):
        if pi not in by_part or not p or p.startswith("<"):
            out.append(p)
            continue
        text = html.unescape(p)
        spans = sorted(by_part[pi])
        merged = []
        for a, b in spans:
            if merged and re.fullmatch(r"[\s,'’-]*", text[merged[-1][1]:a]):
                merged[-1] = (merged[-1][0], b)
            else:
                merged.append((a, b))
        buf, pos = [], 0
        for a, b in merged:
            buf.append(html.escape(text[pos:a], quote=False))
            buf.append('<span class="dv">' + html.escape(text[a:b], quote=False) + "</span>")
            pos = b
        buf.append(html.escape(text[pos:], quote=False))
        out.append("".join(buf))
    return "".join(out)


def _translates(t, parts, bset, tr):
    """An unmarked French word (flux, ensembles) whose translation Massumi uses is not a divergence."""
    if tr is None or not t[4]:
        return False
    w = html.unescape(parts[t[0]])[t[1]:t[2]]
    g, _ = tr.lookup(w)
    return bool(g) and any(norm(x) in bset for x in WORD.findall(g))


def mark(an_h, en_h, tr=None):
    if not an_h.strip() or not en_h.strip():
        return an_h, en_h
    ap, at = tokens(an_h, tr, annotated=True)
    ep, et = tokens(en_h)
    A = [t[3] for t in at]
    B = [t[3] for t in et]
    sm = difflib.SequenceMatcher(None, A, B, autojunk=False)
    ma, mb = set(), set()
    bset, aset = set(B), set(A)
    for tag, a1, a2, b1, b2 in sm.get_opcodes():
        if tag == "equal":
            continue
        # a word reordered rather than changed is not a divergence
        ma.update(i for i in range(a1, a2) if A[i] not in STOP and len(A[i]) > 2 and A[i] not in bset
                  and not _translates(at[i], ap, bset, tr))
        mb.update(j for j in range(b1, b2) if B[j] not in STOP and len(B[j]) > 2 and B[j] not in aset)
    return wrap(ap, at, ma), wrap(ep, et, mb)
