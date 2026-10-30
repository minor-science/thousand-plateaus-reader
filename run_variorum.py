#!/usr/bin/env python3
"""
Variorum runner for "Apparatus of Capture" — zero-prep edition.

Drop this file into the folder containing:

    fr app cap.txt                    (French, Minuit — OCR ok)
    apparatus of capture.txt          (English, Massumi/Minnesota — OCR ok)
    apparatus_of_capture_prompt.md    (the system prompt)

then:

    source ~/variorum-env/bin/activate
    export ANTHROPIC_API_KEY=sk-ant-...      # or put the key in api_key.txt
    python3 run_variorum.py --dry-run        # inspect chunking, no API calls
    python3 run_variorum.py                  # the real run

No chunks.md needed. The script:
  1. splits the French text into paragraph-sized chunks automatically
     (written out as chunks_auto.md so you can inspect/correct them;
     if chunks_auto.md exists, it is used instead of re-splitting);
  2. for each chunk, hands the model the French plus a sliding WINDOW of
     the English text and instructs it to locate and extract the matching
     Minnesota passage itself (correcting obvious OCR artifacts);
  3. validates each returned table row, appends it to the master file,
     logs QUOTE FLAGs / MOTIF CANDIDATEs / warnings, and checkpoints.

Resumable: re-running skips completed chunks. Delete .variorum_state.json
to start over.

Outputs:
    variorum_apparatus_of_capture.md
    flags.log
    glossary.md          (created empty on first run; edit between runs)

Options:
    --start N     re-run from chunk N onward
    --only N      re-run a single chunk (row appended; swap in manually)
    --dry-run     chunk + report only, zero API calls
"""

import argparse
import json
import re
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
MODEL = "claude-fable-5"
MAX_TOKENS = 8000
MAX_RETRIES = 4
TARGET_CHUNK_CHARS = 1800          # rough size of a French chunk
WINDOW_SLACK = 2500                # extra English chars beyond the expected match

HEADER = (
    "| Meta | French (Original) | English (Minnesota Translation) "
    "| English (Annotated Translation) |\n"
    "|---|---|---|---|\n"
)

AUTO_MODE_SUPPLEMENT = """

## AUTO-ALIGNMENT MODE (overrides the input-format section above)

In this run the user supplies, instead of a pre-aligned Minnesota passage,
a WINDOW of the OCR'd Minnesota text under the prefix `MinnesotaWindow:`.
The window begins at (or slightly before) the passage corresponding to the
French and extends past its end.

For Column 3 (English (Minnesota Translation)):
- Locate within the window the passage that corresponds to the French chunk.
- Reproduce that passage and ONLY that passage — do not include surrounding
  window text, running headers, or page numbers.
- Correct obvious OCR artifacts silently (split words like "bef ore" ->
  "before", "oj" -> "of", stray page-header fragments, broken quotation
  marks). Do not otherwise alter Massumi's wording.
- If the window appears NOT to contain the full corresponding passage
  (it starts too late or ends too early), do not guess: output the row with
  Column 3 reading only `[ALIGNMENT GAP]` and add a line before the table:
  `ALIGN FLAG: <one-line description of the mismatch>`.

The French chunk is also OCR text and carries two known defects:
- Page-bottom footnote material may be interleaved mid-chunk (a chunk may
  open with, or contain, a stray note like "150 : « ... »" or a
  bibliographic tail like "Dumézil, Mitra-Varuna, pp. 200-204"). Where you
  can identify such material as footnote content, do not translate it as
  body prose: move its translation to the bottom of the Column 4 cell per
  Rule 8, and add a line before the table:
  `NOTE FLAG: <one-line description of the displaced footnote material>`.
  If you cannot tell whether a fragment is body or footnote, flag it the
  same way and translate it in place.
- OCR artifacts occur in the French too (split words like
  "ins t i t utions", "qut'" for "que"). In Column 2, reproduce the French
  with obvious OCR spacing/character artifacts silently repaired — no
  wording changes, restoration only. Translate from the repaired reading.

The Meta cell contains only a paragraph number (pagination unknown at this
stage); reproduce it as given. All other rules stand unchanged.
"""


# ---------------------------------------------------------------- file finding

def find_file(patterns, exclude=None):
    for pat in patterns:
        for p in sorted(HERE.glob(pat)):
            if exclude and exclude in p.name:
                continue
            return p
    return None


def locate_inputs():
    fr = find_file(["fr app cap.txt", "fr_app_cap.txt", "*fr*app*cap*.txt",
                    "*fr*capture*.txt"])
    en = find_file(["apparatus of capture.txt", "apparatus_of_capture.txt",
                    "*apparatus*capture*.txt"], exclude="prompt")
    prompt = find_file(["apparatus_of_capture_prompt.md", "*prompt*.md"])
    missing = [n for n, p in
               [("French text", fr), ("English text", en), ("system prompt", prompt)]
               if p is None]
    if missing:
        sys.exit("Cannot find in this folder: " + ", ".join(missing) +
                 "\nPut this script in the same folder as the three files.")
    return fr, en, prompt


# ------------------------------------------------------------- text normalizing

def normalize(text):
    text = text.replace("\r\n", "\n").replace("\ufeff", "")
    # rejoin hyphenation at line ends: "cap-\nture" -> "capture"
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)
    return text


def strip_english_furniture(text):
    """Remove running headers, bare page numbers, and the endnotes section."""
    out = []
    for line in text.splitlines():
        s = line.strip()
        if re.match(r"^\d{1,4}\s*[DO0]?\s*$", s):                 # page numbers
            continue
        if re.search(r"APPARA\s*T?US\s+OF\s+CAPTURE", s, re.I):   # running header
            continue
        if re.match(r"^7000\s*B\.?\s*c\.?", s, re.I):
            continue
        if re.match(r"^NOTES\s+TO\s+PP", s, re.I):                # endnotes begin
            break
        out.append(line)
    return "\n".join(out)


def strip_french_furniture(text):
    """Remove Minuit running headers and page numbers, both on their own
    lines and interleaved inline by the OCR."""
    out = []
    for line in text.splitlines():
        s = line.strip()
        if re.match(r"^\d{1,4}\s*$", s):
            continue
        if re.match(r"^(APPAREIL DE CAPTURE|MILLE PLATEAUX)\s*$", s):
            continue
        out.append(line)
    text = "\n".join(out)
    # inline: "... 532 APPAREIL DE CAPTURE ..." / "... 553 MILLE PLATEAUX ..."
    text = re.sub(r"\s*\b\d{1,4}\s+(APPAREIL DE CAPTURE|MILLE PLATEAUX)\b\s*",
                  " ", text)
    text = re.sub(r"\s*\b(APPAREIL DE CAPTURE|MILLE PLATEAUX)\s+\d{1,4}\b\s*",
                  " ", text)
    return text


def repair_paragraphs(paras):
    """OCR inserts blank lines at page breaks, splitting sentences. Merge any
    paragraph that begins mid-sentence (lowercase letter, punctuation, or a
    closing quote/paren) back into the previous one."""
    merged = []
    for p in paras:
        first = p.lstrip()[:1]
        if merged and (first.islower() or first in ";:,)»…·'-"):
            merged[-1] = merged[-1].rstrip() + " " + p.lstrip()
        else:
            merged.append(p)
    return merged


def flatten(text):
    """Collapse hard-wrapped lines into flowing paragraphs.
    A blank line = paragraph break; otherwise lines are joined with spaces."""
    paras, buf = [], []
    for line in text.splitlines():
        if line.strip():
            buf.append(line.strip())
        elif buf:
            paras.append(" ".join(buf))
            buf = []
    if buf:
        paras.append(" ".join(buf))
    return paras


def chunk_french(paras):
    """Group paragraphs into chunks near TARGET_CHUNK_CHARS. If the OCR gave us
    no blank lines (one giant paragraph), fall back to sentence packing."""
    if len(paras) <= 3 and sum(len(p) for p in paras) > 8000:
        text = " ".join(paras)
        sentences = re.split(r"(?<=[.!?»])\s+", text)
        packed, buf = [], ""
        for s in sentences:
            if len(buf) + len(s) > TARGET_CHUNK_CHARS and buf:
                packed.append(buf.strip())
                buf = s
            else:
                buf += " " + s
        if buf.strip():
            packed.append(buf.strip())
        return packed
    chunks, buf = [], ""
    for p in paras:
        if buf and len(buf) + len(p) > TARGET_CHUNK_CHARS:
            chunks.append(buf.strip())
            buf = p
        else:
            buf = (buf + "\n\n" + p) if buf else p
    if buf.strip():
        chunks.append(buf.strip())
    return chunks


# ------------------------------------------------------- alignment bookkeeping

def squash(s):
    """Lowercase alphanumerics only, plus an index map back to the original."""
    chars, idx = [], []
    for i, ch in enumerate(s):
        if ch.isalnum():
            chars.append(ch.lower())
            idx.append(i)
    return "".join(chars), idx


def advance_cursor(english, cursor, extracted_tail):
    """Find the end of the extracted Minnesota passage in the English source,
    tolerant of OCR spacing/punctuation noise. Returns new cursor or None."""
    window = english[cursor:cursor + 20000]
    win_sq, win_idx = squash(window)
    tail_sq, _ = squash(extracted_tail)
    if len(tail_sq) < 20:
        return None
    probe = tail_sq[-60:]
    pos = win_sq.find(probe)
    if pos == -1 and len(probe) > 30:          # retry with a shorter probe
        pos = win_sq.find(probe[-30:])
    if pos == -1:
        return None
    end_sq = pos + len(probe) - 1
    if end_sq >= len(win_idx):
        return None
    return cursor + win_idx[end_sq] + 1


# ------------------------------------------------------------------ validation

UNESCAPED_PIPE = re.compile(r"(?<!\\)\|")


def validate_row(text):
    warnings = []
    lines = [ln for ln in text.splitlines() if ln.strip()]
    table_lines = [ln for ln in lines if ln.lstrip().startswith("|")]
    flag_lines = [ln for ln in lines
                  if ln.startswith(("QUOTE FLAG:", "MOTIF CANDIDATE:",
                                    "ALIGN FLAG:", "NOTE FLAG:"))]
    stray = [ln for ln in lines
             if ln not in table_lines and ln not in flag_lines
             and not set(ln.strip()) <= {"-", "|", " "}]
    if stray:
        warnings.append(f"non-table text in response: {stray[:2]}")
    if not table_lines:
        warnings.append("no table row found in response")
    body = "\n".join(table_lines)
    if body.count('<span style="color:green">') != body.count("</span>"):
        warnings.append("unbalanced <span> tags")
    if body.count("<u>") != body.count("</u>"):
        warnings.append("unbalanced <u> tags")
    minnesota_cell = ""
    for ln in table_lines:
        if set(ln.strip()) <= {"-", "|", " "}:
            continue
        cells = UNESCAPED_PIPE.split(ln)
        if len(cells) != 6:
            warnings.append(f"row has {len(cells) - 1} unescaped pipes "
                            f"(expected 5): {ln[:60]}...")
        elif not minnesota_cell:
            minnesota_cell = cells[3].strip()
    table_lines = [ln for ln in table_lines
                   if not ln.replace(" ", "").startswith(("|Meta|", "|---"))]
    return table_lines, flag_lines, warnings, minnesota_cell


# ------------------------------------------------------------------------ main

def get_api_key():
    import os
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not key or "your-key" in key:
        key_file = HERE / "api_key.txt"
        if key_file.exists():
            key = key_file.read_text().strip()
            os.environ["ANTHROPIC_API_KEY"] = key
    if not key or not key.startswith("sk-ant-"):
        sys.exit("No valid API key. Either:\n"
                 "  export ANTHROPIC_API_KEY=sk-ant-...\n"
                 "or create api_key.txt in this folder containing only the key.")
    return key


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", type=int)
    ap.add_argument("--only", type=int)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    fr_path, en_path, prompt_path = locate_inputs()
    print(f"French:  {fr_path.name}\nEnglish: {en_path.name}\n"
          f"Prompt:  {prompt_path.name}")

    system_prompt = prompt_path.read_text(encoding="utf-8") + AUTO_MODE_SUPPLEMENT
    english = " ".join(flatten(strip_english_furniture(
        normalize(en_path.read_text(encoding="utf-8", errors="replace")))))

    chunks_file = HERE / "chunks_auto.md"
    if chunks_file.exists():
        raw = chunks_file.read_text(encoding="utf-8")
        chunks = [c.strip() for c in raw.split("=== CHUNK ===") if c.strip()]
        chunks = [re.sub(r"^¶\d+\s*\n", "", c) for c in chunks]
        print(f"Using existing {chunks_file.name}: {len(chunks)} chunks.")
    else:
        fr_paras = repair_paragraphs(flatten(strip_french_furniture(normalize(
            fr_path.read_text(encoding="utf-8", errors="replace")))))
        chunks = chunk_french(fr_paras)
        with chunks_file.open("w", encoding="utf-8") as f:
            for i, c in enumerate(chunks, 1):
                f.write(f"=== CHUNK ===\n¶{i}\n{c}\n\n")
        print(f"Wrote {chunks_file.name}: {len(chunks)} chunks "
              f"(inspect/edit it; it will be reused on the next run).")

    total_fr = sum(len(c) for c in chunks)
    ratio = len(english) / max(total_fr, 1)

    if args.dry_run:
        for i, c in enumerate(chunks, 1):
            print(f"  ¶{i:3d}  {len(c):5d} ch   {c[:70]!r}")
        print(f"\nEnglish text: {len(english)} chars, ratio {ratio:.2f}. "
              f"No API calls made.")
        return

    get_api_key()
    import anthropic
    client = anthropic.Anthropic()

    out_path = HERE / "variorum_apparatus_of_capture.md"
    flags_path = HERE / "flags.log"
    state_path = HERE / ".variorum_state.json"
    glossary_path = HERE / "glossary.md"
    if not glossary_path.exists():
        glossary_path.write_text(
            "# Standing glossary — edit between runs\n"
            "# format: term — fixed rendering / status (e.g. 'glossed at ¶3, "
            "plain italics thereafter')\n", encoding="utf-8")
    if not out_path.exists():
        out_path.write_text(HEADER, encoding="utf-8")

    state = {"done": [], "cursor": 0}
    if state_path.exists():
        state = json.loads(state_path.read_text())
    done = set(state["done"])
    cursor = state["cursor"]

    todo = [args.only] if args.only else range(args.start or 1, len(chunks) + 1)

    for i in todo:
        if i in done and not (args.only or args.start):
            continue
        chunk = chunks[i - 1]
        glossary = glossary_path.read_text(encoding="utf-8")
        expected = int(len(chunk) * ratio)
        window = english[cursor:cursor + expected + WINDOW_SLACK]
        print(f"[{i}/{len(chunks)}] ¶{i} "
              f"(fr {len(chunk)} ch, window {len(window)} ch) ... ",
              end="", flush=True)

        user_msg = (f"Meta: ¶{i}\n\nFrench:\n{chunk}\n\n"
                    f"MinnesotaWindow:\n{window}\n\n"
                    f"Glossary:\n{glossary.strip() or '(none yet)'}")

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                resp = client.messages.create(
                    model=MODEL, max_tokens=MAX_TOKENS, temperature=0,
                    system=system_prompt,
                    messages=[{"role": "user", "content": user_msg}])
                break
            except anthropic.APIStatusError as e:
                if attempt == MAX_RETRIES:
                    raise
                wait = 2 ** attempt * 5
                print(f"\n  API error ({e.status_code}), retry {attempt} "
                      f"in {wait}s", end="", flush=True)
                time.sleep(wait)

        text = "".join(b.text for b in resp.content if b.type == "text")
        table_lines, flag_lines, warnings, minnesota_cell = validate_row(text)

        new_cursor = None
        if minnesota_cell and "ALIGNMENT GAP" not in minnesota_cell:
            tail = minnesota_cell.split("<br>")[-1]
            new_cursor = advance_cursor(english, cursor, tail)
        if new_cursor is None:
            new_cursor = min(cursor + expected, len(english))
            warnings.append("cursor advanced by estimate, not by match — "
                            "check alignment of the NEXT chunk")
        cursor = new_cursor

        with out_path.open("a", encoding="utf-8") as f:
            f.write("\n".join(table_lines) + "\n")
        if flag_lines or warnings:
            with flags_path.open("a", encoding="utf-8") as f:
                for ln in flag_lines:
                    f.write(f"[¶{i}] {ln}\n")
                for w in warnings:
                    f.write(f"[¶{i}] WARNING: {w}\n")

        done.add(i)
        state_path.write_text(json.dumps(
            {"done": sorted(done), "cursor": cursor}))
        status = "ok"
        if flag_lines:
            status += f", {len(flag_lines)} flag(s)"
        if warnings:
            status += f", {len(warnings)} WARNING(s)"
        print(status)

    print(f"\nDone. Table: {out_path.name}   Flags: {flags_path.name}\n"
          f"Read flags.log before trusting the output — QUOTE FLAGs mean "
          f"unverified quotations.")


if __name__ == "__main__":
    main()
