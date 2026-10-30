# A Thousand Plateaus reader

A reading interface and annotated variorum for two plateaus of Deleuze and Guattari's *A Thousand Plateaus*: "1227: Treatise on Nomadology — The War Machine" (plateau 12) and "7000 B.C.: Apparatus of Capture" (plateau 13).

`reader.html` is the finished page: one chunk at a time, three columns (Minuit French, Massumi's Minnesota English, an annotated translation) lined up sentence by sentence, with a paragraph view, Massumi's endnotes, French help, a Differences highlight, a lexicon of terms, flags, background sources, search and page jump. Open it in any browser.

## What is here

- Plateau 12 rows are in `nomadology/variorum_nomadology.md`; plateau 13 is `variorum_from_rtf.md`. Every row has the French chunk, Massumi's passage and the annotated translation.
- `corrections_*.md` and `nomadology/swap_corrections.py`: corrected rows are never edited in the masters by hand; they go into a corrections file and are swapped in by script, with a backup, checks and a log entry in `flags.log`.
- `lexicon_12_13.md`, `glossary.md`, `reader_glosses.json`: the term lexicon and the short English glosses shown after French words.
- `PROCESS.md`: the working rules for drafting, flags, corrections, and how the reader is built.
- The build scripts: `build_lexicon.py`, then `build_reader.py` (with `align_sentences.py`, `chunk_fit.py`, `p12_sources.py`, `p13_sources.py`, `endnotes.py`, `french_help.py`, `compare.py`).

## Rebuilding

`python3 build_lexicon.py && python3 build_reader.py`

The build reads two kinds of source that are not in this repository: your own copy of the Minuit 2013 epub of *Mille plateaux* (looked up as `~/Downloads/Mille plateaux_*.epub`) and OCR text of the Minnesota edition (`atp_athlone_1987.txt` and `deleuze_guattari_atp.txt`, expected in `~/Downloads/protevi-response/sources_text/core`; change `KIT` in `p13_sources.py` and `SRC` in `endnotes.py` to move them).

## Status

The annotated translation, the glosses and the lexicon were drafted automatically under the method in `apparatus_of_capture_prompt.md` and have not all been reviewed. Quotation flags marked open in `flags.log` and `nomadology/flags_p12.log` still need verified source texts.

## Text and rights

`reader.html` and the variorum files quote *A Thousand Plateaus* (Minuit, 1980; Minnesota, 1987, trans. Brian Massumi) at length for study and comparison. The rights in that text belong to their holders.
