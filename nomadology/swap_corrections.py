"""Swap corrected rows from corrections_p12.md into the plateau 12 master.

    python3 swap_corrections.py          # dry run: show what would change
    python3 swap_corrections.py --apply  # back up, swap, check, log
    python3 swap_corrections.py --plateau 13 [--apply]   # plateau 13: corrections_p13.md -> variorum_from_rtf.md

Each corrected row replaces the master row with the same chunk number.
If a chunk has several corrections, the last one wins. The master is backed
up to backups/ first, and nothing is written unless every check passes.
"""
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).parent
P13 = "--plateau" in sys.argv and sys.argv[sys.argv.index("--plateau") + 1] == "13"
if P13:                                 # plateau 13 (added Oct 29, 2026): same procedure, its own files
    MASTER = HERE.parent / "variorum_from_rtf.md"
    CORR = HERE.parent / "corrections_p13.md"
    APPLIED = HERE.parent / "corrections_applied_p13.md"
    FLAGS = HERE.parent / "flags.log"
    ROW = re.compile(r"^\| ¶(\d+) ")
    TAG = "13¶"
else:
    MASTER = HERE / "variorum_nomadology.md"
    CORR = HERE / "corrections_p12.md"
    APPLIED = HERE / "corrections_applied_p12.md"
    FLAGS = HERE / "flags_p12.log"
    ROW = re.compile(r"^\| 12¶(\d+) ")
    TAG = "12¶"


def cells(row):
    return re.split(r"(?<!\\)\|", row[2:-2])


def check(lines):
    nums = [int(ROW.match(l).group(1)) for l in lines if ROW.match(l)]
    expected = list(range(1, max(nums) + 1))
    problems = []
    if nums != expected:
        problems.append("chunk numbers are not 1..n once each, in order")
    for l in lines:
        if ROW.match(l):
            c = cells(l)
            if len(c) != 4:
                problems.append(f"{l[:12]}: {len(c)} columns")
            elif c[3].count('<span style="color:green">') != c[3].count("</span>"):
                problems.append(f"{l[:12]}: unbalanced <span>")
    return problems


def main():
    apply = "--apply" in sys.argv
    if not CORR.exists():
        sys.exit("no corrections file")
    fixes = {}
    for l in CORR.read_text().splitlines():
        m = ROW.match(l)
        if m:
            fixes[int(m.group(1))] = l
    if not fixes:
        sys.exit("no corrected rows to swap")
    lines = MASTER.read_text().splitlines()
    index = {int(ROW.match(l).group(1)): i for i, l in enumerate(lines) if ROW.match(l)}
    missing = [n for n in fixes if n not in index]
    if missing:
        sys.exit(f"corrections for chunks not in the master: {missing}")
    new = list(lines)
    changed = []
    for n, row in sorted(fixes.items()):
        if new[index[n]] != row:
            new[index[n]] = row
            changed.append(n)
    problems = check(new)
    if problems:
        sys.exit("refused, the swapped master would fail checks:\n  " + "\n  ".join(problems))
    print(f"rows to swap: {', '.join(f'{TAG}{n}' for n in changed) or 'none (already identical)'}")
    if not apply:
        print("dry run; rerun with --apply")
        return
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    (HERE / "backups").mkdir(exist_ok=True)
    backup = HERE / "backups" / f"{MASTER.stem}.{stamp}.md"
    shutil.copy2(MASTER, backup)
    MASTER.write_text("\n".join(new) + "\n")
    with APPLIED.open("a") as f:
        f.write(f"\n## Applied {stamp} (backup: nomadology/backups/{backup.name})\n\n")
        for n in sorted(fixes):
            f.write(fixes[n] + "\n")
    header = [l for l in CORR.read_text().splitlines() if not ROW.match(l) and l.strip()]
    CORR.write_text("\n".join(header) + "\n\n")
    with FLAGS.open("a") as f:
        for n in changed:
            f.write(f"[{TAG}{n}] SWAPPED {stamp}: corrected row from {CORR.name} now in the master (backup {backup.name}).\n")
    print(f"swapped {len(changed)} rows; backup at backups/{backup.name}; master passes checks")
    import subprocess
    for script in ("build_lexicon.py", "build_reader.py"):
        subprocess.run([sys.executable, str(HERE.parent / script)], check=False)


if __name__ == "__main__":
    main()
