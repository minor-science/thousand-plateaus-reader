#!/usr/bin/env python3
"""Prepare plateau 12 ("Traité de nomadologie : la machine de guerre") for the variorum, using the
cleaning and chunking functions of ../run_variorum.py (plateau 13's pipeline) unchanged.

Writes, in this folder:
  fr_nomadologie.txt      French, Minuit 1980, pp. 434-527, OCR text with [[p]] page markers
  en_nomadology.txt       English, Minnesota 1987, pp. 351-423, one page per [[p]] marker
  chunks_p12.md           French chunks, '=== CHUNK ===' blocks headed '12¶n fr.<first page>'
  windows_p12.md          for each chunk, the estimated English pages to search
"""
import re, subprocess, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import run_variorum as rv  # noqa: E402

PDF = Path.home() / "Downloads/Mille plateaux (Minuit 1980).pdf"     # your own copy of the Minuit text
ATP_EN = Path.home() / "Downloads/protevi-response/sources_text/core/deleuze_guattari_atp.txt"
PDF_OFFSET = 3            # printed page = pdf page + 3
FR_FIRST, FR_LAST = 434, 527
EN_FIRST, EN_LAST = 351, 423


def french_pages():
    pages = {}
    for printed in range(FR_FIRST, FR_LAST + 1):
        out = subprocess.run(["pdftotext", "-f", str(printed - PDF_OFFSET), "-l", str(printed - PDF_OFFSET), str(PDF), "-"],
                             capture_output=True, text=True).stdout
        pages[printed] = out
    return pages


def clean_fr_page(t):
    t = rv.normalize(t)
    lines = []
    for ln in t.splitlines():
        s = ln.strip()
        if re.match(r"^\d[\d ]{0,5}$", s):                      # page number, OCR-spaced ("43 4")
            continue
        if re.match(r"^(MILLE PLATEAUX|TRAIT.{0,6}DE NOMADOLOGIE.*|T\s*H\s*A\s*I\s*T.*MACH\s*INE.*)$", s):
            continue
        lines.append(ln)
    return "\n".join(lines)


def main():
    fr = french_pages()
    with open(HERE / "fr_nomadologie.txt", "w") as f:
        for p, t in fr.items():
            f.write(f"\n[[{p}]]\n{t}")
    # paragraphs with the page each starts on
    paras = []  # (page, text)
    for p, t in fr.items():
        for para in rv.flatten(clean_fr_page(t)):
            paras.append([p, para])
    # merge mid-sentence continuations (rv.repair_paragraphs logic, keeping the first page)
    merged = []
    for p, para in paras:
        first = para.lstrip()[:1]
        prev_open = merged and not re.search(r"[.!?»:)]\s*(\d{1,3})?\s*$", merged[-1][1].rstrip())
        if merged and (first.islower() or first in ";:,)»…·'-" or prev_open):
            merged[-1][1] = merged[-1][1].rstrip() + " " + para.lstrip()
        else:
            merged.append([p, para])
    # split long paragraphs at sentence ends into pieces near the target size
    pieces = []
    for p, para in merged:
        if len(para) <= rv.TARGET_CHUNK_CHARS * 1.4:
            pieces.append([p, para])
            continue
        sents = re.split(r"(?<=[.!?»])\s+(?=[A-ZÀ-ÖØ-Þ«(])", para)
        buf = ""
        for s in sents:
            if buf and len(buf) + len(s) > rv.TARGET_CHUNK_CHARS:
                pieces.append([p, buf.strip()])
                buf = s
            else:
                buf = (buf + " " + s) if buf else s
        if buf.strip():
            pieces.append([p, buf.strip()])
    merged = pieces
    # chunk near rv.TARGET_CHUNK_CHARS, keeping each chunk's first page
    chunks, buf, bufp = [], "", None
    for p, para in merged:
        if buf and len(buf) + len(para) > rv.TARGET_CHUNK_CHARS:
            chunks.append((bufp, buf.strip()))
            buf, bufp = para, p
        else:
            buf = (buf + "\n\n" + para) if buf else para
            bufp = bufp or p
    if buf.strip():
        chunks.append((bufp, buf.strip()))
    with open(HERE / "chunks_p12.md", "w") as f:
        for i, (p, c) in enumerate(chunks, 1):
            f.write(f"=== CHUNK ===\n12¶{i} fr.{p}\n{c}\n\n")
    # English, one page per marker
    en_pages = open(ATP_EN, errors="ignore").read().split("\f")
    with open(HERE / "en_nomadology.txt", "w") as f:
        for p in range(EN_FIRST, EN_LAST + 1):
            t = re.sub(r"[ \t]+", " ", en_pages[p + 20])
            f.write(f"\n[[{p}]]\n{t.strip()}\n")
    # proportional window estimate per chunk
    total = sum(len(c) for _, c in chunks)
    acc = 0
    with open(HERE / "windows_p12.md", "w") as f:
        for i, (p, c) in enumerate(chunks, 1):
            lo = EN_FIRST + (EN_LAST - EN_FIRST + 1) * acc / total
            acc += len(c)
            hi = EN_FIRST + (EN_LAST - EN_FIRST + 1) * acc / total
            f.write(f"12¶{i}\tfr.{p}\ten.{int(lo)}-{int(hi) + 1}\t{len(c)} chars\n")
    print(f"{len(chunks)} chunks, {total} French chars, pages {FR_FIRST}-{FR_LAST}")


if __name__ == "__main__":
    main()
