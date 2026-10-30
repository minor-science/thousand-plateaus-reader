"""Sentence alignment for the variorum reader: split each column into sentences and line them up.

Used by build_reader.py. Lengths are compared with glosses removed; beads may be 1-1, 1-2, 2-1, 2-2, 1-0, 0-1.
"""
import html as _html
import re
import unicodedata

ABBR = {"p", "pp", "cf", "etc", "ch", "t", "n", "nn", "vol", "ed", "eds", "éd", "M", "MM", "av", "apr", "sq", "St", "Mr",
        "Mrs", "Dr", "op", "cit", "ibid", "fig", "no", "nos", "col", "trans", "vs", "Vol", "Fr", "Minn", "C", "J", "vols",
        "chap", "sqq", "id", "Id", "art", "liv", "ill", "sect", "Ste", "Mme", "Mlle", "Ier", "env", "ca", "c", "i.e", "e.g",
        "U.F", "P.U", "N.R", "C.N.R", "fol"}
GLOSS_RX = re.compile(r'<span class="g">.*?</span>', re.S)
TAG_RX = re.compile(r"<[^>]+>")
END_RX = re.compile(r'([.!?…]|\.\.\.)((?:\s?»|[”"’)\]])*)([⁰¹²³⁴⁵⁶⁷⁸⁹]*)(\s+)(?=[«“"(\[A-ZÀÂÉÈÊÎÔÛÇŒ0-9])')
BAL = ["i", "b", "u", "em", "strong", "code"]


def _protect(s):
    keep = []
    def sub(m):
        keep.append(m.group(0))
        return f"\x01{len(keep)-1}\x02"
    s = GLOSS_RX.sub(sub, s)
    s = re.sub(r"<[^>]+>", sub, s)          # tags never split
    return s, keep


def _restore(s, keep):
    return re.sub(r"\x01(\d+)\x02", lambda m: keep[int(m.group(1))], s)


def split(h):
    """HTML fragment -> list of sentence fragments (HTML). Line breaks (<br>) also end a sentence."""
    if not h.strip():
        return []
    parts = [x for x in re.split(r"(?:\s*<br\s*/?>\s*)+", h) if x.strip()]
    if len(parts) > 1:
        return [f for x in parts for f in split(x)]
    s, keep = _protect(h)
    out, last = [], 0
    for m in END_RX.finditer(s):
        end = m.end(3)
        before = s[last:m.start(1)]
        word = re.search(r"([\w.\-]+)$", _restore(before, keep).replace("\x01", ""))
        w = word.group(1) if word else ""
        if m.group(1) == "." and (w.rstrip(".") in ABBR or w.rstrip(".").lower() in ABBR or re.fullmatch(r"[A-ZÀ-Ý]", w) or re.fullmatch(r"(?:[A-Z]\.)+[A-Z]?", w + ".")):
            continue
        out.append(s[last:end])
        last = m.end(4)
    out.append(s[last:])
    frags = [_restore(x, keep).strip() for x in out if x.strip()]
    # section numbers: « …des minorités. 7 Propositions » breaks before the number; a lone « 7. » joins what follows
    res = []
    for f in frags:
        res += [x for x in re.split(r"(?<=[.!?»)\]] )(?=\d{1,2}\.? [A-ZÀ-Ý])", f) if x.strip()]
    frags = []
    for f in res:
        if frags and re.fullmatch(r"\d{1,2}\.?", _html.unescape(TAG_RX.sub("", frags[-1])).strip()):
            frags[-1] = frags[-1] + " " + f
        else:
            frags.append(f.strip())
    return _balance(frags)


def _balance(frags):
    carry = []
    res = []
    for f in frags:
        f = "".join(f"<{t}>" for t in carry) + f
        carry = []
        for t in BAL:
            opens = len(re.findall(rf"<{t}(?:\s[^>]*)?>", f))
            closes = f.count(f"</{t}>")
            if opens > closes:
                f += f"</{t}>" * (opens - closes)
                carry += [t] * (opens - closes)
        res.append(f)
    return res


def plain_len(h):
    return len(_html.unescape(TAG_RX.sub("", GLOSS_RX.sub("", h))).strip()) + 1


# French run-ons often become several English sentences (Massumi splits them): 1-n is cheaper than n-1.
BEADS = [(1, 1, 0.0), (1, 2, 1.0), (2, 1, 1.6), (2, 2, 3.2), (1, 0, 3.5), (0, 1, 3.5), (1, 3, 2.2), (3, 1, 3.6), (1, 4, 3.6), (4, 1, 5.5)]


def _toks(h, minlen=4):
    t = unicodedata.normalize("NFD", _html.unescape(TAG_RX.sub(" ", GLOSS_RX.sub(" ", h))).lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return {w[:6] for w in re.findall(r"[a-z]{%d,}" % minlen, t)}


def _anchors(h):
    """Names and numbers: capitalized words (first 4 letters, accents stripped) and digits."""
    t = _html.unescape(TAG_RX.sub(" ", GLOSS_RX.sub(" ", h)))
    t = "".join(c for c in unicodedata.normalize("NFD", t) if unicodedata.category(c) != "Mn")
    caps = {w[:4].lower() for w in re.findall(r"(?<![.!?]\s)(?<!^)\b[A-Z][a-z]{3,}", t)}
    nums = set(re.findall(r"\b\d{2,4}\b", t))
    return caps | nums


def _dice(a, b):
    return 2 * len(a & b) / (len(a) + len(b)) if a and b else 0.0


def align(a, b, sa=None, sb=None, w_sim=0.0, ratio=1.0):
    """Monotone alignment of two sentence lists. a, b: plain lengths; ratio: expected len(a)/len(b) for
    sentences that match. Cost of a bead = shape penalty + length mismatch (absolute, so a column that stops
    early does not shift the rest) - w_sim * word overlap (sa, sb: token sets). Returns beads [(i0, i1, j0, j1)]."""
    import math
    if not a or not b:
        return [(0, len(a), 0, len(b))]
    INF = 1e18
    n, m = len(a), len(b)
    cost = [[INF] * (m + 1) for _ in range(n + 1)]
    back = [[None] * (m + 1) for _ in range(n + 1)]
    cost[0][0] = 0.0
    for i in range(n + 1):
        for j in range(m + 1):
            if cost[i][j] >= INF:
                continue
            for di, dj, pen in BEADS:
                ii, jj = i + di, j + dj
                if ii > n or jj > m:
                    continue
                if di and dj:
                    x, y = sum(a[i:ii]), sum(b[j:jj])
                    c = pen + 2.0 * abs(math.log((x + 30) / (ratio * y + 30)))
                    if w_sim:
                        c -= w_sim * _dice(set().union(*sa[i:ii]), set().union(*sb[j:jj]))
                else:
                    # a sentence with no counterpart: cheaper at the end, where one column may simply stop
                    c = pen * (0.6 if (ii == n or jj == m) else 1.0)
                c += cost[i][j]
                if c < cost[ii][jj]:
                    cost[ii][jj] = c
                    back[ii][jj] = (i, j)
    beads, i, j = [], n, m
    while (i, j) != (0, 0):
        pi, pj = back[i][j]
        beads.append((pi, i, pj, j))
        i, j = pi, pj
    return beads[::-1]


def _stems(h):
    t = unicodedata.normalize("NFD", _html.unescape(TAG_RX.sub(" ", GLOSS_RX.sub(" ", h))).lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return {w[:5] for w in re.findall(r"[a-z]{5,}", t)}


W_FE, W_FN = 2.0, 4.0     # weights of shared names (French-Minnesota) and shared words (French-annotated)


def rows(fr_h, en_h, an_h):
    """Three columns -> rows [[fr, en, an]].
    French-annotated is aligned by length and shared vocabulary (the annotated keeps many French words);
    French-Minnesota by length and shared names and numbers. A row boundary falls only on a French sentence
    boundary that both alignments agree on, so the three columns cannot drift apart."""
    F, E, N = split(fr_h), split(en_h), split(an_h)
    if not F:
        return [[fr_h, en_h, an_h]]
    LF = [plain_len(x) for x in F]
    fe = align(LF, [plain_len(x) for x in E], [_anchors(x) | _stems(x) for x in F], [_anchors(x) | _stems(x) for x in E], w_sim=W_FE, ratio=1.1) if E else [(0, len(F), 0, 0)]
    fn = align(LF, [plain_len(x) for x in N], [_stems(x) for x in F], [_stems(x) for x in N], w_sim=W_FN, ratio=1.0) if N else [(0, len(F), 0, 0)]

    def starts(beads):
        st = set()
        for i0, i1, _, _ in beads:
            if i1 > i0:
                st.add(i0)
        return st
    cut = sorted(starts(fe) & starts(fn) | {0})
    seg_of = {}
    for k, c0 in enumerate(cut):
        c1 = cut[k + 1] if k + 1 < len(cut) else len(F)
        for i in range(c0, c1):
            seg_of[i] = k
    rows_out = [[[], [], []] for _ in cut]
    for i in range(len(F)):
        rows_out[seg_of[i]][0].append(F[i])

    def place(beads, col, items):
        last = 0
        for i0, i1, j0, j1 in beads:
            k = seg_of[i0] if i1 > i0 else last
            rows_out[k][col].extend(items[j0:j1])
            if i1 > i0:
                last = seg_of[i1 - 1]
    if E:
        place(fe, 1, E)
    if N:
        place(fn, 2, N)
    _refine_en(rows_out)
    return [[" ".join(r[0]), " ".join(r[1]), " ".join(r[2])] for r in rows_out]


def _refine_en(rows_out):
    """Where Massumi restores an original English quotation his sentences do not follow the French. Jo's annotation is
    English too, so a Massumi sentence at the edge of a row moves to the neighbouring row when the two rows' annotated
    text then fits Massumi's better (shared words), by a clear margin."""
    def fit(en, an):
        a, b = _stems(" ".join(an)), _stems(" ".join(en))
        return _dice(a, b)
    for _ in range(3):
        moved = False
        for k in range(len(rows_out) - 1):
            r0, r1 = rows_out[k], rows_out[k + 1]
            if not r0[2] or not r1[2]:
                continue
            base = fit(r0[1], r0[2]) + fit(r1[1], r1[2])
            if len(r1[1]) >= 1 and r1[1]:
                up = fit(r0[1] + r1[1][:1], r0[2]) + fit(r1[1][1:], r1[2])
                if up > base + 0.12:
                    r0[1].append(r1[1].pop(0))
                    moved = True
                    continue
            if r0[1]:
                down = fit(r0[1][:-1], r0[2]) + fit([r0[1][-1]] + r1[1], r1[2])
                if down > base + 0.12:
                    r1[1].insert(0, r0[1].pop())
                    moved = True
        if not moved:
            break

