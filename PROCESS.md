# Process notes — Apparatus of Capture and Treatise on Nomadology variorums

This folder produces a bilingual annotated variorum of the "Apparatus of
Capture" plateau (A Thousand Plateaus). Rows are drafted by a language
model under the method in `apparatus_of_capture_prompt.md`, which sets the
rules, especially:

- the bold-italic **iff** bracket rule and bracket discipline
- QUOTE FLAG: never reconstruct a quoted source's wording from memory
- pipe escaping (`\|`) and closed HTML tags inside table cells

## Files

- `chunks_auto.md` — French chunks, `=== CHUNK ===` blocks numbered ¶1, ¶2…
  (If missing, regenerate with: `python3 run_variorum.py --dry-run`)
- `apparatus of capture.txt` — Massumi/Minnesota English, OCR'd (page
  headers, page numbers, and endnotes are still present; skip them)
- `apparatus_of_capture_prompt.md` — the system prompt / method
- `glossary.md` — standing glossary; consult before every chunk, and after
  each chunk append any MOTIF CANDIDATE lines to the bottom of this file
  under a `## Candidates (unreviewed)` heading rather than deciding
- `variorum_apparatus_of_capture.md` — the master table (append-only)
- `flags.log` — one line per QUOTE FLAG / NOTE FLAG / ALIGN FLAG / warning,
  prefixed `[¶n]`
- `.progress` — plain text, the number of the last completed chunk

## Per-chunk procedure

1. Read `.progress`; the next chunk is that number + 1 (start at 1 if the
   file doesn't exist).
2. Read that chunk's French from `chunks_auto.md`.
3. Find the corresponding passage in `apparatus of capture.txt`.
   Reproduce only that passage in Column 3, silently correcting obvious OCR
   artifacts (split words, "oj"→"of", stray header fragments). If the passage
   cannot confidently locate the passage, put `[ALIGNMENT GAP]` in Column 3
   and log an ALIGN FLAG — do not guess.
4. The French chunk may contain interleaved page-bottom footnote material
   from the OCR. Route identifiable footnotes to the bottom of Column 4 per
   the prompt's Rule 8 and log a NOTE FLAG.
5. Produce the 4-column table row per the prompt. Meta cell is `¶n` only.
6. Append the row to `variorum_apparatus_of_capture.md` (create it with the
   table header if absent). Append any flags to `flags.log`. Update
   `.progress`.
7. Report a one-line status: chunk number, flags raised, done.

## Batch runs

When asked to "continue" or "do the next N", process chunks one at a time
through the full procedure — never draft several chunks in one pass, and
never rewrite existing rows except by the swap procedure below. If asked
to redo chunk n, or if an error turns up in a row already written, write the
corrected row to the corrections file (`corrections_p12.md` for plateau 12)
and log a SWAP line in the flags log.

## Swapping corrections

Corrected rows are swapped into the master by script rather than by hand. Use `nomadology/swap_corrections.py` (run from
`nomadology/`): it backs up the master to `backups/` with a timestamp,
replaces each corrected row by its chunk number, checks that the master
still has every chunk once and in order with four columns per row, moves
the applied rows to `corrections_applied_p12.md`, and logs a SWAPPED line
per row. Run it after a batch, and report which rows
were swapped. For plateau 13 (added Oct 29, 2026) the same script takes
`--plateau 13`: corrected rows go in `corrections_p13.md` (ATP folder) and are
swapped into `variorum_from_rtf.md`. Never hand-edit a row in the master; always go through the
corrections file and the script.

## Fixing flags

Fixes the flags call for are made automatically, through the same
corrections-file-and-swap route:
- ALIGN / REPAIR flags that say "check the Minuit page": check the French
  against the Minuit 2013 epub with `nomadology/audit_fr_epub.py N`
  (it reads the epub in ~/Downloads in place and prints only differing
  words; never copy the epub's text into project files or chat). Where the
  epub settles it, write the corrected row, swap, and log RESOLVED or SWAP.
  Keep printed oddities as printed, marked [sic], and unbracket supplied
  words the epub confirms.
- ADDENDUM lines: fold them into the row's gloss via a corrected row.
- NOTE FLAGs: mark RESOLVED once the note's text is placed in a row.
- QUOTE FLAGs: resolve only against a verified source text on hand (never
  from memory); otherwise leave them open and say so.
- SENSE NOTEs and SPLIT NOTEs are observations, not fixes; leave them.

## Reader and lexicon (Oct 29, 2026)

`reader.html` is the reading interface for both variorums (one chunk at a time, three columns lined up sentence by sentence by `align_sentences.py`, with a paragraph view, glosses, notes, flags, background sources, lexicon lookup, search, page jump). `lexicon_12_13.md` is the French-term lexicon. Both are generated: rebuild with `python3 build_lexicon.py && python3 build_reader.py` after any new row or context rebuild (`swap_corrections.py --apply` does this itself). For plateau 13 the reader rebuilds the French (Minuit 2013 epub) and Minnesota (two OCRs, `sources_text/core/deleuze_guattari_atp.txt` and `atp_athlone_1987.txt`) columns chunk by chunk with `p13_sources.py`, because the variorum's own cells are incomplete there; the variorum is not changed. Never hand-edit them. The reader embeds the text of A Thousand Plateaus: keep it a local file, never publish it.

## Hard rules

- Never edit `apparatus_of_capture_prompt.md` or the source `.txt` files.
  Existing rows in the master table change only through the swap procedure
  above (backup, script, checks), never by hand.
- Never fabricate a quotation. When a QUOTE FLAG fires, the row still gets
  written (with the French translated literally), but the flag must be
  logged so verified source text can be supplied later.
- If anything in the texts is ambiguous (chunk boundaries look wrong,
  alignment is unclear across a large span), stop and ask rather than
  pushing through.

## Reader alignment (Oct 29, 2026, second pass)

- Plateau 12's French is now rebuilt whole from the Minuit epub by `p12_sources.py` (the variorum's French cells are cut at every « [...] » page break, which used to drop the rest of the body). Then `build_reader.py` runs `_fix_fragments` (a Minnesota or annotated cell that opens on the tail of the previous chunk's sentence goes back to that chunk) and `_refit` (`chunk_fit.py`: French and Massumi sentences are re-cut plateau-wide to the annotated column's chunks). Plateau 13 is unchanged.
- `endnotes.py` attaches Massumi's endnotes (Athlone OCR, chapters 12 and 13: 111 and 68 notes) to the chunk where each call falls; six plateau-12 calls the OCR lost are placed by judgment (APPROX12) and marked in the reader.
- `reader_glosses.json` fixes (compars, precipitation, ennemi quelconque, informatique, encastement, nationalitaires, s'asservit, monter, une pointe de la science); `french_help.short_gloss` now drops glosses that are commentary, not translation.
- Plateau 13 annotated cells that open with the editor's own text (⚠ QUOTATION FLAG / SEGMENTATION blocks, bracketed remarks, footnote tails) are trimmed in the reader by `_trim_an_heads`: the block goes to the chunk's Flags as "Cell note" and the annotation starts where it matches Massumi. The variorum cells are unchanged.
- Known and left alone: cells that open with « … » continuing the previous chunk's sentence (13¶54); where Massumi restores an original English quotation with different sentences (12¶95); the Minnesota OCR's own errors.
