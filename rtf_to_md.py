#!/usr/bin/env python3
"""
rtf_to_md.py — Convert chunks_auto.rtf to a clean Markdown variorum.

Handles the specific formatting conventions used in this RTF:
  f3/f6   = body text (Times Roman / Times New Roman)
  f4      = bold-italic French key term  ->  ***term***
  cf3     = green annotation text        ->  <span style="color:green">text</span>
  ul      = underlined title             ->  *title*
  \'xx    = cp1252 character escape      ->  unicode
  uc0 uN  = unicode codepoint escape     ->  unicode

Output: variorum_from_rtf.md  (safe to review before replacing the master)
"""

import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

# ── Character decoding ──────────────────────────────────────────────────────

def decode_rtf_chars(s: str) -> str:
    """Decode \'xx (cp1252) and \\uc0\\uN (unicode) escapes in RTF text."""
    # Unicode escapes — must go first, before stripping control words
    s = re.sub(r'\\uc0\\u(\d+)\s?', lambda m: chr(int(m.group(1))), s)
    # cp1252 byte escapes
    def cp1252(m):
        try:
            return bytes([int(m.group(1), 16)]).decode('cp1252')
        except Exception:
            return '?'
    s = re.sub(r"\\'([0-9a-fA-F]{2})", cp1252, s)
    return s


# ── Page-header / OCR furniture stripping for column 3 (Minnesota) ──────────

# Matches embedded running headers and page numbers from the OCR'd Minnesota text.
# Covers variants like "426 D 7000 s.c.: APPARA TUS OF CAPTURE" and
# "572 0 NOTES TO PP. 472-481" etc.
HEADER_RE = re.compile(
    r'\b\d{1,4}\s*[DO0]?\s*'                          # page number + optional D/O artifact
    r'(?:'
    r'7000\s*[A-Za-z]\.?\s*[A-Za-z]\.?'               # "7000 B.C." or "7000 s.c."
    r'|APPARA\s*T?US\s+OF\s+CAPTURE'                  # running header (possibly split)
    r'|APPARATUS\s+OF\s+CAPTURE'
    r')',
    re.IGNORECASE,
)
# Also strip the bare running header (without a page number prefix)
BARE_HEADER_RE = re.compile(r'APPARA\s*T?US\s+OF\s+CAPTURE[^\n]*', re.IGNORECASE)
BARE_PAGENUM_RE = re.compile(r'^\s*\d{1,4}\s*$', re.MULTILINE)
NOTES_RE = re.compile(r'\bNOTES\s+TO\s+PP\b.*', re.IGNORECASE | re.DOTALL)


def clean_minnesota_text(s: str) -> str:
    """Remove running headers, bare page numbers, and NOTES section from col 3."""
    s = NOTES_RE.sub('', s)
    s = HEADER_RE.sub('', s)
    s = BARE_HEADER_RE.sub('', s)
    s = BARE_PAGENUM_RE.sub('', s)
    return s


# ── RTF control word stripping ───────────────────────────────────────────────

# Matches any RTF control word (\\word[-N][ ]) or control symbol (\\x)
# Does NOT match \' (handled separately above) or \<newline>
_CTRL_RE = re.compile(r'\\(?:[a-zA-Z]+\*?-?\d*\s?|[^a-zA-Z\'\n{} ])')


def strip_controls(s: str) -> str:
    return _CTRL_RE.sub('', s)


# ── Tokeniser for column 4 (annotated translation) ──────────────────────────

# We tokenise on RTF control words so we can run a state machine.
# Tokens are either a control-word string (starting with \) or plain text.
_TOK_RE = re.compile(
    r"(\\uc0\\u\d+\s?"           # unicode escape (consume before general ctrl)
    r"|\\\'[0-9a-fA-F]{2}"       # cp1252 escape
    r"|\\\n"                      # soft line break (backslash + newline)
    r"|\\[a-zA-Z]+\*?-?\d*\s?"   # control word
    r"|[{}]"                      # brace (group delimiter)
    r")"
)


def _tokenise(s: str):
    """Yield (is_control, text) pairs."""
    pos = 0
    for m in _TOK_RE.finditer(s):
        if m.start() > pos:
            yield False, s[pos:m.start()]
        yield True, m.group(0)
        pos = m.end()
    if pos < len(s):
        yield False, s[pos:]


def col4_to_md(raw: str) -> str:
    """
    Convert a column-4 RTF cell to Markdown, preserving:
      - bold-italic  (\\f4\\i\\b ... \\fN\\i0\\b0)  →  ***term***
      - green        (\\cf3 ... \\cf0 or \\cf2)     →  <span style="color:green">…</span>
      - underline    (\\ul ... \\ulnone)             →  *title*
      - soft breaks  (\\ + newline)                  →  newline
    """
    # Decode character escapes first so the state machine sees plain text
    raw = decode_rtf_chars(raw)

    result = []
    bold_italic = False
    green       = False
    underline   = False

    for is_ctrl, tok in _tokenise(raw):
        if not is_ctrl:
            result.append(tok)
            continue

        t = tok.strip()   # control word without trailing space

        # ── font ────────────────────────────────────────────────────────────
        if t == r'\f4' or t == r'\f4\i\b' or t == r'\f4\i' or t == r'\f4\b':
            if not bold_italic:
                result.append('***')
                bold_italic = True

        elif re.match(r'\\f[0-9]+$', t) and bold_italic:
            # Any other font switch closes bold-italic
            result.append('***')
            bold_italic = False

        elif t in (r'\i0', r'\b0', r'\i0\b0', r'\b0\i0'):
            if bold_italic:
                result.append('***')
                bold_italic = False

        # ── colour ──────────────────────────────────────────────────────────
        elif t == r'\cf3':
            if not green:
                result.append('<span style="color:green">')
                green = True

        elif t in (r'\cf0', r'\cf2'):
            if green:
                result.append('</span>')
                green = False

        # ── underline ───────────────────────────────────────────────────────
        elif t == r'\ul':
            if not underline:
                result.append('*')
                underline = True

        elif t == r'\ulnone':
            if underline:
                result.append('*')
                underline = False

        # ── line / paragraph breaks ─────────────────────────────────────────
        elif tok == '\\\n':          # soft line break: \<newline>
            result.append('\n')

        elif t == r'\par':
            result.append('\n')

        # ── braces / everything else: silently discard ───────────────────────
        # (this covers all layout/format control words we don't need)

    # Close any dangling spans
    if bold_italic:
        result.append('***')
    if green:
        result.append('</span>')
    if underline:
        result.append('*')

    out = ''.join(result)

    # ── Post-process ────────────────────────────────────────────────────────
    # Strip tab characters (RTF literal tabs become stray \t in output)
    out = out.replace('\t', ' ')
    # Collapse whitespace within ***…*** spans so the term doesn't straddle a line
    # e.g. ***term\n*** → ***term***
    out = re.sub(r'\*\*\*(.*?)\*\*\*',
                 lambda m: '***' + m.group(1).strip() + '***',
                 out, flags=re.DOTALL)
    # Same for green spans that got extra whitespace at start/end
    out = re.sub(r'<span style="color:green">\s*(.*?)\s*</span>',
                 lambda m: '<span style="color:green">' + m.group(1) + '</span>',
                 out, flags=re.DOTALL)
    # Collapse multiple spaces (not newlines)
    out = re.sub(r'[ ]{2,}', ' ', out)
    # Trim leading/trailing whitespace per line
    out = '\n'.join(line.strip() for line in out.splitlines())
    # Remove blank lines at start/end
    out = out.strip()
    # Collapse 3+ newlines to 2
    out = re.sub(r'\n{3,}', '\n\n', out)

    # Convert newlines to <br> for Markdown table cell
    out = out.replace('\n\n', '<br><br>').replace('\n', '<br>')

    return out


def col123_to_md(raw: str, clean_mn: bool = False) -> str:
    """Convert a plain-text column (1, 2, or 3) RTF cell to clean text."""
    s = decode_rtf_chars(raw)
    # Soft line breaks → newline
    s = re.sub(r'\\\n', '\n', s)
    # Hard paragraph break
    s = re.sub(r'\\par\b\s*', '\n', s)
    # Strip all RTF controls
    s = strip_controls(s)
    # Strip braces
    s = re.sub(r'[{}]', '', s)
    # Normalise whitespace
    s = re.sub(r'[ \t]{2,}', ' ', s)
    s = '\n'.join(line.strip() for line in s.splitlines())
    if clean_mn:
        s = clean_minnesota_text(s)
    s = s.strip()
    s = re.sub(r'\n{3,}', '\n\n', s)
    # Convert newlines to <br>
    s = s.replace('\n\n', '<br><br>').replace('\n', '<br>')
    return s


# ── Fix known OCR artifacts in French column ─────────────────────────────────

FRENCH_OCR_FIXES = [
    # RTF has these after cp1252 decoding and control stripping
    (r'\btEtat\b',                   "l'État"),
    (r'l\}axiomatique',              "l'axiomatique"),
    (r'd\}un\b',                     "d'un"),
    (r'de l\}axiomatique',           "de l'axiomatique"),
    (r'l\}automation',               "l'automation"),
    # OCR splits
    (r'\bprhée\b',                   'privée'),
    (r'\brOl\b',                     'roi'),        # e.g. "rOl Juriste"
    (r'\bgu\'',                      "qu'"),        # qut' → qu'
]

def fix_french_ocr(s: str) -> str:
    for pat, rep in FRENCH_OCR_FIXES:
        s = re.sub(pat, rep, s)
    return s


# ── Row extraction ───────────────────────────────────────────────────────────

# Chunk meta cell pattern: (¶ or bare number) N  fr.XXX  umn.YYY
META_RE = re.compile(r'[¶]?\s*(\d+)\s+fr\.(\d+)\s+umn\.(\d+)', re.IGNORECASE)


def extract_rows(rtf_text: str):
    """
    Yield (meta_raw, fr_raw, mn_raw, an_raw) tuples for each content row.

    Strategy:
      Split the whole RTF on \\row (row-end marker).
      Each block is a complete table row.  Within each block, split on \\cell
      to get the 4 column segments (plus some trailing RTF after the last \\cell).
    """
    # Split on \row (handles both \row and \lastrow\row)
    row_blocks = re.split(r'\\(?:last)?row\b', rtf_text)

    for block in row_blocks:
        # Each block: trowd-spec + cell-content-1 \cell cell-content-2 \cell ...
        # Split on \cell (cell-end marker) but NOT \cellx (column-position spec in
        # the trowd definition).  Using \b ensures \cellx2160 is not split.
        cell_parts = re.split(r'\\cell\b(?!x)', block)

        # We need exactly 4 actual \cell markers → 5 parts
        # (some spacer rows give 4 parts; header/structure rows give 5 but empty)
        if len(cell_parts) < 5:
            continue

        # The column segments are parts [0..3]
        # part[0]: trowd spec + first cell content
        # part[1]: second cell content
        # part[2]: third cell content
        # part[3]: fourth cell content (annotated translation)
        meta_raw = cell_parts[0]
        fr_raw   = cell_parts[1]
        mn_raw   = cell_parts[2]
        an_raw   = cell_parts[3]

        # Decode the meta field to check if this is a real content row
        meta_decoded = decode_rtf_chars(meta_raw)
        meta_decoded = re.sub(r'\\\n', ' ', meta_decoded)
        meta_decoded = strip_controls(meta_decoded)
        meta_decoded = re.sub(r'[{}]', '', meta_decoded)
        meta_decoded = re.sub(r'\s+', ' ', meta_decoded).strip()

        m = META_RE.search(meta_decoded)
        if not m:
            continue   # header / spacer / structure row — skip

        chunk_num = int(m.group(1))
        fr_page   = m.group(2)
        mn_page   = m.group(3)

        # Build clean meta string (ensure ¶ prefix)
        meta_clean = f'¶{chunk_num} fr.{fr_page} umn.{mn_page}'

        yield chunk_num, meta_clean, fr_raw, mn_raw, an_raw


# ── Main ─────────────────────────────────────────────────────────────────────

HEADER = (
    '| Meta | French (Original) | English (Minnesota Translation) '
    '| English (Annotated Translation) |\n'
    '|---|---|---|---|\n'
)


def main():
    rtf_path = HERE / 'chunks_auto.rtf'
    out_path  = HERE / 'variorum_from_rtf.md'

    if not rtf_path.exists():
        sys.exit(f'Cannot find {rtf_path}')

    print(f'Reading {rtf_path.name} …', flush=True)
    rtf_text = rtf_path.read_text(encoding='utf-8', errors='replace')

    rows = []
    seen = set()

    for chunk_num, meta, fr_raw, mn_raw, an_raw in extract_rows(rtf_text):
        if chunk_num in seen:
            print(f'  WARNING: duplicate chunk ¶{chunk_num} — skipping duplicate')
            continue
        seen.add(chunk_num)

        fr = col123_to_md(fr_raw, clean_mn=False)
        fr = fix_french_ocr(fr)
        mn = col123_to_md(mn_raw, clean_mn=True)
        an = col4_to_md(an_raw)

        # Escape any unescaped pipes in cell content (protect table structure)
        def esc(s):
            # Don't escape pipes inside HTML tags
            parts = re.split(r'(<[^>]+>)', s)
            return ''.join(
                p if p.startswith('<') else p.replace('|', r'\|')
                for p in parts
            )

        rows.append(f'| {meta} | {esc(fr)} | {esc(mn)} | {esc(an)} |')
        print(f'  ¶{chunk_num:3d} … ok', flush=True)

    # Sort by chunk number (rows should already be in order, but just in case)
    rows.sort(key=lambda r: int(re.search(r'¶(\d+)', r).group(1)))

    print(f'\nWriting {out_path.name} ({len(rows)} rows) …')
    with out_path.open('w', encoding='utf-8') as f:
        f.write(HEADER)
        for row in rows:
            f.write(row + '\n')

    missing = [n for n in range(1, 108) if n not in seen]
    if missing:
        print(f'WARNING: missing chunks: {missing}')
    else:
        print('All 107 chunks present.')
    print('Done.')


if __name__ == '__main__':
    main()
