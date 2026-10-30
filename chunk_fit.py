"""Re-cut a column's chunks to fit the annotated column, for the reader only.

The variorum cuts French, Massumi and Jo's annotation at different places (page breaks, sometimes mid-sentence).
Jo's annotation follows the French sentence by sentence, so it is the pivot: all of one column's sentences, in
reading order across the whole plateau, are aligned with the annotated sentences (banded dynamic programming, length
plus shared vocabulary, like align_sentences.rows), and each sentence goes to the chunk of the annotated sentence it
aligns with. A sentence with no counterpart stays with the chunk it was already in.
"""
import math
import re

import align_sentences as A

BEADS = [(1, 1, 0.0), (1, 2, 1.0), (2, 1, 1.6), (2, 2, 3.2), (1, 0, 3.5), (0, 1, 3.5), (1, 3, 2.2), (3, 1, 3.6)]


def _tok(h):
    return A._anchors(h) | A._stems(h)


def refit(x_chunks, a_chunks, band=2, w_sim=3.0, ratio=1.0, move_pen=1.5):
    """x_chunks, a_chunks: lists (same order) of sentence lists (HTML) per chunk. Returns new x_chunks."""
    X = [(s, k) for k, ss in enumerate(x_chunks) for s in ss]
    Aa = [(s, k) for k, ss in enumerate(a_chunks) for s in ss]
    if not X or not Aa:
        return x_chunks
    lx = [A.plain_len(s) for s, _ in X]
    la = [A.plain_len(s) for s, _ in Aa]
    tx = [_tok(s) for s, _ in X]
    ta = [_tok(s) for s, _ in Aa]
    n, m = len(X), len(Aa)
    # for each X sentence, the window of annotated sentence indices within `band` chunks of its own chunk
    first, last = {}, {}
    for j, (_, k) in enumerate(Aa):
        first.setdefault(k, j)
        last[k] = j
    ks = sorted(first)

    def window(i):
        k = X[i][1]
        lo = next((first[q] for q in range(k - band, k + band + 1) if q in first), None)
        hi = next((last[q] for q in range(k + band, k - band - 1, -1) if q in last), None)
        if lo is None or hi is None:
            return 0, m
        return max(0, lo - 1), min(m, hi + 1)
    win = [window(i) for i in range(n)]
    INF = 1e18
    cost = {(0, 0): 0.0}
    back = {}
    for i in range(n + 1):
        jlo, jhi = (win[i][0], win[i][1]) if i < n else (win[n - 1][0], win[n - 1][1])
        for j in range(max(0, jlo - 6), min(m, jhi + 6) + 1):
            c0 = cost.get((i, j))
            if c0 is None:
                continue
            for di, dj, pen in BEADS:
                ii, jj = i + di, j + dj
                if ii > n or jj > m:
                    continue
                if di and dj:
                    xs, ys = sum(lx[i:ii]), sum(la[j:jj])
                    c = pen + 2.0 * abs(math.log((xs + 30) / (ratio * ys + 30)))
                    c -= w_sim * A._dice(set().union(*tx[i:ii]), set().union(*ta[j:jj]))
                    if Aa[j][1] != X[i][1]:
                        c += move_pen           # a sentence leaves its chunk only on clear evidence
                else:
                    c = pen
                c += c0
                if c < cost.get((ii, jj), INF):
                    cost[(ii, jj)] = c
                    back[(ii, jj)] = (i, j)
    if (n, m) not in cost:
        return x_chunks
    label = [None] * n
    i, j = n, m
    while (i, j) != (0, 0):
        pi, pj = back[(i, j)]
        if i > pi and j > pj:
            for q in range(pi, i):
                label[q] = Aa[pj][1]
        i, j = pi, pj
    # unmatched sentences take the previous label (monotone); never go backwards
    cur = 0
    for q in range(n):
        if label[q] is None:
            label[q] = max(cur, X[q][1]) if cur > X[q][1] else X[q][1]
        label[q] = max(label[q], cur)
        cur = label[q]
    out = [[] for _ in x_chunks]
    for q in range(n):
        out[label[q]].append(X[q][0])
    return out
