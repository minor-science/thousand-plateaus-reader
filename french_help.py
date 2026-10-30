"""French help for readers with no French: find French words and phrases in the annotated column and attach
a short English translation every time they occur.

Translations come, in order, from:
  1. the lexicon (Jo's glosses in both variorums): the English head of the gloss, before its first dash;
  2. reader_glosses.json: short translations added for the reader; drafted automatically and not yet reviewed.
French is detected as runs of words found in the Minuit text of plateaus 12-13 that are not English words
(or carry French accents), with French function words (de, la, que...) joining neighbours into one phrase.

    python3 french_help.py missing   -> list the French runs that have no translation yet, with counts
"""
import glob
import html
import json
import os
import re
import unicodedata
import zipfile
from pathlib import Path

HERE = Path(__file__).parent
SUPP = HERE / "reader_glosses.json"
FUNC = {"de", "la", "le", "les", "du", "des", "et", "à", "en", "un", "une", "que", "qui", "ne", "pas", "se", "sur",
        "par", "au", "aux", "d", "l", "qu", "s", "n", "c", "j", "m", "il", "elle", "on", "y", "ce", "sa", "son", "ses",
        "leur", "leurs", "est", "sont", "ou", "dans", "pour", "avec", "plus", "tout", "tous", "même", "comme", "si"}
ENGLISH = set(w.strip().lower() for w in open("/usr/share/dict/words"))
ENGLISH |= {"etc", "cf", "ie"}


def key(t):
    t = unicodedata.normalize("NFD", t.lower())
    return re.sub(r"[^a-z0-9' ]", "", "".join(c for c in t if unicodedata.category(c) != "Mn")).replace("'", " ").strip()


def _french_vocab():
    E = glob.glob(os.path.expanduser("~/Downloads/Mille plateaux_*.epub"))[0]
    z = zipfile.ZipFile(E)
    v = set()
    for f in ("OEBPS/chap012.html", "OEBPS/chap013.html"):
        t = html.unescape(re.sub(r"<[^>]+>", " ", z.read(f).decode("utf-8"))).replace("’", "'")
        v |= {w.lower() for w in re.findall(r"[^\W\d_]+", t)}
    return v


FRV = _french_vocab()
FRV |= {"".join(c for c in unicodedata.normalize("NFD", w) if unicodedata.category(c) != "Mn") for w in FRV}
ACC = set("éèêëàâäçôöûüîïœæÉÈÊÀÂÇÔÛÎŒ")


def strip_acc(s):
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def is_french(w):
    lw = w.lower()
    if lw not in FRV:
        return False
    if w[0].isupper() and strip_acc(lw) not in ("etat", "etats"):
        return False                       # names (Marx, Dumézil) and sentence-initial English
    if len(lw) < 3:
        return False
    if any(c in ACC for c in w):
        return True
    eng = lw in ENGLISH or lw.rstrip("s") in ENGLISH or lw[:-2] in ENGLISH and lw.endswith("es")
    return not eng


TOKEN = re.compile(r"[^\W\d_]+(?:['’][^\W\d_]+)*")


def runs(text):
    """French runs in a plain-text string: [(start, end, phrase)]."""
    out, cur = [], []
    toks = list(TOKEN.finditer(text))
    for i, m in enumerate(toks):
        w = m.group(0).replace("’", "'")
        parts = w.split("'")
        core = parts[-1]
        fr = is_french(core) or (len(parts) > 1 and parts[0].lower() in ("l", "d", "qu", "n", "s", "c", "j", "m") and core.lower() in FRV)
        gap_ok = not cur or text[toks[i - 1].end():m.start()].strip(" ,'’-") == ""
        if fr and gap_ok:
            cur.append(m)
        elif w.lower() in FUNC and cur and gap_ok:
            cur.append(m)
        else:
            if cur:
                out.append(cur)
            cur = [m] if fr else []
    if cur:
        out.append(cur)
    res = []
    for r in out:
        while r and r[-1].group(0).lower() in FUNC:
            r = r[:-1]
        while r and r[0].group(0).lower() in FUNC and not is_french(r[0].group(0)):
            r = r[1:]
        if r and any(is_french(m.group(0).split("'")[-1]) for m in r):
            res.append((r[0].start(), r[-1].end(), text[r[0].start():r[-1].end()]))
    return res


META = re.compile(r"¶|verbatim|pun cashed|fronted|scare-quoted|\bmachinery\b|\bpanel\b")


def short_gloss(g):
    """The English head of one of Jo's glosses: the text before its first dash. A head that is commentary rather
    than a translation (« the ¶6 verdict verbatim… ») gives '' so that nothing is shown; a head that is too long is
    cut at its last comma or colon instead of mid-clause."""
    g = re.sub(r"<[^>]+>", "", g)
    g = re.sub(r"\s*\([^)]*¶[^)]*\)", "", g)             # a bare cross-reference to a paragraph
    head = re.split(r"\s[–—-]\s|;", g, maxsplit=1)[0].strip(" .:")
    head = re.sub(r"^(Latin|Greek|German|Arabic|Italian|Old French):\s*", r"\1 ", head)
    if META.search(head):
        return ""
    if len(head) <= 70:
        return head if head else ""
    cut = max(head.rfind(",", 0, 70), head.rfind(":", 0, 70))
    return head[:cut].strip(" ,:") if cut > 15 else head[:70].rsplit(" ", 1)[0] + "…"


class Translator:
    def __init__(self, lex):
        self.t = {}
        for k, e in lex.items():
            sg = short_gloss(e["gloss"])
            if sg:
                self.t[k] = sg
        for g in (HERE / "nomadology/glossary_p12.md", HERE / "glossary.md"):
            for line in g.read_text().splitlines():
                m = re.match(r"\*([^*]+)\*\s+—\s+(.+)$", line)
                if m and "glossed at" not in m.group(2) and not m.group(2).startswith("*"):
                    sg = short_gloss(m.group(2))
                    if sg:
                        self.t.setdefault(key(m.group(1)), sg)
        self.supp, self.over = {}, {}
        if SUPP.exists():
            raw = json.loads(SUPP.read_text())
            for k, v in raw.items():
                if not k.startswith("_"):
                    self.supp[key(k)] = v
            for k, v in raw.get("_override", {}).items():
                self.over[key(k)] = v

    def lookup(self, phrase):
        k = key(phrase)
        if k in self.over:
            return (self.over[k] or None), ("added" if self.over[k] else None)
        if len(k) <= 2:
            return None, None
        if k in self.t:
            return self.t[k], "jo"
        if k in self.supp:
            return self.supp[k], "added"
        return None, None


def annotate(h, tr, seen, missing=None):
    """Add translations after French in an annotated HTML fragment. seen: keys already translated in this row."""
    parts = re.split(r'(<span class="g">.*?</span>|<b class="t"[^>]*>.*?</b>|<[^>]+>)', h, flags=re.S)
    out = []
    in_i = False
    in_u = False

    def gloss_follows(pi, tail):
        """True if, after this point, the next real content is one of Jo's gloss brackets."""
        if re.search(r"[^\W\d_]", tail):
            return False
        for q in parts[pi + 1:]:
            if not q:
                continue
            if q.startswith('<span class="g">'):
                return True
            if q.startswith("<"):
                continue
            if re.search(r"[^\W\d_]", q):
                return False
        return False
    for pi, p in enumerate(parts):
        if not p:
            continue
        if p.startswith("<"):
            out.append(p)
            if re.match(r"<i[\s>]", p):
                in_i = True
            elif p.startswith("</i"):
                in_i = False
            elif p.startswith("<u"):
                in_u = True
            elif p.startswith("</u"):
                in_u = False
            continue
        if in_u:
            out.append(p)
            continue
        text = html.unescape(p)
        pos, buf = 0, []
        found = runs(text)
        if in_i:
            g, src = tr.lookup(text)
            if g is not None or any(is_french(m.group(0).split("'")[-1]) for m in TOKEN.finditer(text)):
                found = [(0, len(text), text.strip())] if text.strip() else []
        ext = []
        toks_all = list(TOKEN.finditer(text))
        for a, b, phrase in found:
            before = [m for m in toks_all if m.end() <= a][-3:]
            for k in range(len(before)):
                cand = text[before[k].start():b]
                if tr.lookup(cand)[0] and (not ext or before[k].start() >= ext[-1][1]):
                    a, phrase = before[k].start(), cand
                    break
            ext.append((a, b, phrase))
        found = ext
        for a, b, phrase in found:
            g, src = tr.lookup(phrase)
            sub = []
            if g is None and " " in phrase.strip():
                # try the longest known sub-phrases
                ws = list(TOKEN.finditer(phrase))
                i = 0
                while i < len(ws):
                    for j in range(len(ws), i, -1):
                        sp = phrase[ws[i].start():ws[j - 1].end()]
                        gg, ss = tr.lookup(sp)
                        if gg:
                            sub.append((a + ws[i].start(), a + ws[j - 1].end(), sp, gg, ss))
                            i = j
                            break
                    else:
                        i += 1
            elif g is not None:
                sub = [(a, b, phrase, g, src)]
            if g is None and not sub and missing is not None:
                missing[key(phrase)] = missing.get(key(phrase), 0) + 1
            for s0, s1, sp, gg, ss in sub:
                k = key(sp)
                buf.append(html.escape(text[pos:s0], quote=False))
                buf.append(f'<span class="fx" data-k="{html.escape(k)}">{html.escape(text[s0:s1], quote=False)}</span>')
                if k not in seen and not gloss_follows(pi, text[s1:]):
                    seen.add(k)
                    buf.append(f'<span class="tr{" add" if ss == "added" else ""}"> ({html.escape(gg, quote=False)})</span>')
                pos = s1
        buf.append(html.escape(text[pos:], quote=False))
        out.append("".join(buf))
    return "".join(out)


if __name__ == "__main__":
    import sys
    s = (HERE / "reader.html").read_text()
    d = json.loads(s[s.index('id="data">') + 10:s.index("</script>", s.index('id="data">'))].replace("<\\/", "</"))
    tr = Translator(d["lex"])
    missing = {}
    for p in d["plateaus"]:
        for c in p["chunks"]:
            for r in c["rows"]:
                annotate(re.sub(r'<span class="(?:tr|fx)[^"]*"[^>]*>.*?</span>', "", r[2]), tr, set(), missing)
    if sys.argv[1:] == ["missing"]:
        for k, n in sorted(missing.items(), key=lambda x: (-x[1], x[0])):
            print(f"{n}\t{k}")
        print(f"# {len(missing)} distinct French runs without a translation", file=sys.stderr)
