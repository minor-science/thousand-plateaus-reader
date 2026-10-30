"""Rebuild plateau 12's French column, chunk by chunk, for the reader only (same idea as p13_sources).

The variorum's French cells for plateau 12 carry the OCR'd footnotes inside the body, and in 30 chunks a « [...] »
marks a page break where the body is cut, the note text follows, and the rest of the body comes after it. The
reader used to keep only what came before the first « [...] ». Here the French body is taken whole from the Minuit
2013 epub (chap012.html): each chunk starts where the variorum's French starts (found by shared word runs), runs to
the next chunk's start (snapped to a sentence start), and takes the French notes whose calls fall inside it.
The variorum itself is never changed.
"""
import glob
import html
import os
import re
import zipfile

import p13_sources as S


def epub12():
    """(body text with note calls removed, [(char offset, call number)], {note number: text})."""
    E = glob.glob(os.path.expanduser("~/Downloads/Mille plateaux_*.epub"))[0]
    s = zipfile.ZipFile(E).read("OEBPS/chap012.html").decode("utf-8")
    s = re.sub(r"(?s)<head>.*?</head>", "", s)
    s = re.sub(r'<a class="renvoi"[^>]*>\s*(\d+)\s*</a>', lambda m: f"\x01{m.group(1)}\x02", s)
    s = re.sub(r"<br\s*/?>|</p>|</div>|</h\d>", "\n", s)
    s = html.unescape(re.sub(r"<[^>]+>", "", s)).replace("’", "'")
    starts = [m.start() for m in re.finditer(r"\n\s*1\.\s", s)]
    cut = starts[-1]
    body, notes_txt = s[:cut], s[cut:]
    notes = {}
    for m in re.finditer(r"\n\s*(\d{1,3})\.\s(.*?)(?=\n\s*\d{1,3}\.\s|\Z)", "\n" + notes_txt.strip(), re.S):
        if int(m.group(1)) <= 104:
            notes[int(m.group(1))] = re.sub(r"\s+", " ", m.group(2)).strip()
    calls, out, pos = [], [], 0
    for m in re.finditer(r"\x01(\d+)\x02", body):
        out.append(body[pos:m.start()])
        calls.append((sum(len(x) for x in out), int(m.group(1))))
        pos = m.end()
    out.append(body[pos:])
    text = "".join(out)
    text = re.sub(r"([^\W\d_])(\d{1,3})(?=[\s.,;:)»])", r"\1", text)     # a call left glued to a word
    return text, calls, notes


def _grams(t):
    import unicodedata
    t = "".join(c for c in unicodedata.normalize("NFD", t.lower()) if unicodedata.category(c) != "Mn")
    w = re.findall(r"[a-z]+", t)
    return {" ".join(w[i:i + 4]) for i in range(len(w) - 3)}


def find_start(text, ws, idx, after, limit, k=5, probe=60):
    """Word index where `text` begins: every k-gram of its first `probe` words votes for (position - offset);
    the start with the most votes wins (earliest on a tie), so a phrase that recurs earlier cannot win alone."""
    sw = [w for w, _ in S.word_stream(text)]
    votes = {}
    for off in range(0, min(probe, max(0, len(sw) - k + 1))):
        for pos in idx.get(tuple(sw[off:off + k]), []):
            st = pos - off
            if after - 30 <= st <= after + limit:
                votes[st] = votes.get(st, 0) + 1
    # a few words of slack for insertions or deletions: pool votes within 6 words
    best = None
    for st in sorted(votes):
        v = sum(n for s2, n in votes.items() if st - 6 <= s2 <= st + 6)
        if best is None or v > best[1]:
            best = (st, v)
    need = min(4, max(1, len(sw) - k + 1))
    return max(after, best[0]) if best and best[1] >= need else None


def find_start3(text, ws, after, limit):
    """A cell that opens on a few words after « [...] » (the tail of a sentence the page break cut): find them as a
    run of words, nearest after `after`."""
    sw = [w for w, _ in S.word_stream(text)]
    if len(sw) < 3:
        return None
    n = len(sw)
    for i in range(max(0, after - 30), min(len(ws) - n, after + limit)):
        if all(ws[i + j][0] == sw[j] for j in range(n)):
            return i
    return None


def rebuild(chunks):
    """chunks: dicts with n and fr_plain (the variorum's French, possibly cut by « [...] »).
    Returns {n: {"fr": str, "frnotes": str}}."""
    text, calls, notes = epub12()
    # keep offsets valid: the glued-call cleanup above may shorten text; recompute call offsets on word stream below
    ws = S.word_stream(text)
    idx = S.ngram_index(ws, 5)
    body_g, note_g = _grams(" ".join(w for w, _ in ws)), _grams(" ".join(notes.values()))

    def is_body(seg):
        g = _grams(seg)
        return bool(g) and len(g & body_g) >= 2 * len(g & note_g) or (0 < len(g) < 3)
    starts, after = [], 0
    for c in chunks:
        head = next((x for x in c["fr_plain"].split("[...]") if x.strip() and is_body(x)), "")
        if c.get("notes_only"):
            starts.append(None)
            continue
        p = find_start(head, ws, idx, after, 6000) if len(head.split()) >= 8 else find_start3(head, ws, after, 6000)
        starts.append(p)
        if p is not None:
            after = p + 1
    for i, c in enumerate(chunks):           # a chunk whose cells are only page-foot notes has no body of its own
        if c.get("notes_only"):
            starts[i] = None
    known = [(i, s) for i, s in enumerate(starts) if s is not None]
    for i, s in enumerate(starts):
        if s is None and chunks[i].get("notes_only"):
            starts[i] = next((starts[j] for j in range(i + 1, len(chunks)) if starts[j] is not None), len(ws) - 1)
        elif s is None:
            prev = max((k for k in known if k[0] < i), default=None)
            nxt = min((k for k in known if k[0] > i), default=None)
            starts[i] = (int(prev[1] + (nxt[1] - prev[1]) * (i - prev[0]) / (nxt[0] - prev[0])) if prev and nxt
                         else (prev[1] if prev else 0))
    sts = S.sentence_starts(text)
    # a sentence cut by a page break belongs to the chunk where it starts: take the next sentence start after the
    # chunk's first word (a start within two characters of a sentence start counts as that start)
    def ceil(x):
        return min([y for y in sts if y >= x - 2], default=len(text))
    cs = [ceil(ws[min(p, len(ws) - 1)][1]) for p in starts]
    cs[0] = 0
    for i in range(1, len(cs)):
        cs[i] = max(cs[i], cs[i - 1])
    out = {}
    for i, c in enumerate(chunks):
        end = cs[i + 1] if i + 1 < len(chunks) else len(text)
        ks = [k for off, k in calls if cs[i] <= off < end]
        out[c["n"]] = {"fr": re.sub(r"\s+", " ", text[cs[i]:end]).strip(),
                       "frnotes": " ".join(f"{k}. {notes[k]}" for k in ks if k in notes),
                       "anchored": starts[i] is not None}
    return out
