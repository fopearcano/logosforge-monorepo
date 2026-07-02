"""Conservative name reconciliation, shared by the extractor and the dashboard.

Reconciles a free-text character/entity name to an existing entity by normalized
name OR alias OR a bare-surname expansion — honorifics + screenplay parentheticals
stripped — *without* false-merging distinct same-surname people. This is the one
matching heuristic the codebase trusts to bridge the manuscript ``Character`` table
and the PSYKE ``character`` bible entries (which carry no stored link).

Dependency-free (stdlib ``re`` only) so it can be imported from any layer — the
extractor (which also pulls in the LLM provider stack) and the read-time analyzers
(narrative dashboard) — with no risk of a circular import.
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher

# Similarity at/above which two names are flagged as a possible (advisory) duplicate.
# Tuned high so a real typo ('Delacorix' vs 'Delacroix') trips it but distinct names
# do not. EXACT-equal forms are excluded (those are _match_id's job, or — for shared
# surnames like 'Sarah Park'/'Jonah Park' — deliberately NOT a merge).
_NEAR_DUPE_THRESHOLD = 0.82

# Leading titles to strip before reconciling ("Lt. Jonah Park" -> "jonah park").
# Deliberately EXCLUDES words that commonly double as given names / code-names
# ("Major", "General", "Sir", "Lady", "Captain", "Doctor", "Private") so a real
# name like "Major Tom" or "Doctor Strange" is never mangled into its second word.
_HONORIFICS = {
    "lt", "lt.", "cmdr", "cmdr.", "capt", "capt.", "cpt", "cpt.", "dr", "dr.",
    "sgt", "sgt.", "mr", "mr.", "mrs", "mrs.", "ms", "ms.", "col", "col.",
    "maj", "maj.", "gen", "gen.", "det", "det.", "pvt", "pvt.", "prof", "prof.",
    "rev", "rev.", "fr", "fr.", "cpl", "cpl.", "ens", "ens.", "adm", "adm.",
    "lieutenant", "commander", "sergeant", "colonel", "detective", "professor",
}
# Trailing screenplay parenthetical to strip ("DELACROIX (V.O.)" -> "delacroix").
_PAREN_TAIL_RE = re.compile(r"\s*\([^)]*\)\s*$")


def _csv_split(s: str) -> list[str]:
    """Comma-split a CSV aliases string (matches Database.csv_split semantics) —
    inlined to keep this module dependency-free."""
    return [p.strip() for p in (s or "").split(",") if p.strip()]


def _norm(s: str) -> str:
    s = (s or "").strip().lower()
    s = _PAREN_TAIL_RE.sub("", s).strip()            # drop a trailing (V.O.)/(beat)/...
    if s.startswith("the "):
        s = s[4:]
    toks = s.split()
    while len(toks) > 1 and toks[0] in _HONORIFICS:  # strip leading honorific(s)
        toks = toks[1:]
    return " ".join(toks)


def _forms(name: str, aliases: str) -> set[str]:
    """Every normalized comparison form for an entry: its name + each CSV alias."""
    out = {_norm(name)}
    for a in _csv_split(aliases):
        out.add(_norm(a))
    return {f for f in out if f}


def _bare_token_match(q: str, cand: str) -> bool:
    """True when a BARE single-token cue ``q`` ('park') equals the first or last
    token of a candidate form ('jonah park'). Used only to expand a bare cue to a
    full name — never to match two multi-token names to each other."""
    ct = cand.split()
    return bool(ct) and (q == ct[0] or q == ct[-1])


def _match_id(name: str, items: list[tuple[int, str, str]]) -> int | None:
    """Reconcile a free-text name to an existing entity, honorifics + parentheticals
    stripped. ``items`` are ``(id, name, aliases_csv)`` — pass ``""`` for entities
    without an aliases column (manuscript Characters).

    Two conservative passes, tuned to avoid *false merges* of distinct people:

      1. exact equality of the normalized cue against the entry's full name or any
         alias — the safe case that fixes the reported duplication bug
         ('DELACROIX (V.O.)' -> alias 'DELACROIX'; 'Lt. Jonah Park' -> 'jonah park').
      2. a *bare single-token* cue ('Park', 'Jonah') expands to a full name by
         first/last token, but ONLY on a UNIQUE hit. A multi-token cue ('Sarah
         Park') never fuzzy-matches, so two same-surname characters stay distinct;
         an ambiguous bare cue (two 'Park's) creates a new entry rather than
         guessing.
    """
    n = _norm(name)
    if not n:
        return None
    # pass 1: exact full-form match (name or any alias) — safe for everyone.
    for cid, cn, al in items:
        if n in _forms(cn, al):
            return cid
    # pass 2: a bare single-token cue -> full name, only when UNAMBIGUOUS.
    if len(n.split()) == 1 and len(n) >= 2:
        hits = {
            cid for cid, cn, al in items
            if any(_bare_token_match(n, f) for f in _forms(cn, al))
        }
        if len(hits) == 1:
            return next(iter(hits))
    return None


def _near_dupes(
    name: str, items: list[tuple[int, str, str]],
    threshold: float = _NEAR_DUPE_THRESHOLD, limit: int = 1,
) -> list[tuple[int, str, float]]:
    """ADVISORY-ONLY near-duplicate detector (never merges): which existing entities
    are suspiciously similar to ``name`` without being an exact ``_match_id`` match —
    i.e. likely an LLM TYPO ('Delacorix' for 'Cmdr. Rhea Delacroix'). ``items`` are
    ``(id, name, aliases_csv)`` (same shape as :func:`_match_id`).

    Returns up to ``limit`` ``(id, name, score)`` candidates, best first. Compares
    the normalized cue against each candidate FORM and, token-wise, against each of
    its tokens (so a bare surname typo trips it). EXACT-equal forms/tokens (score
    1.0) are skipped on purpose: those are either handled by ``_match_id`` or are
    shared surnames of distinct people, which must NEVER be flagged as a merge.
    Intended to be called only when ``_match_id`` already returned ``None``.
    """
    q = _norm(name)
    if len(q) < 3:
        return []
    q_tokens = [t for t in q.split() if len(t) >= 3]
    out: list[tuple[int, str, float]] = []
    for cid, cn, al in items:
        best = 0.0
        for f in _forms(cn, al):
            r = SequenceMatcher(None, q, f).ratio()
            if r < 1.0:
                best = max(best, r)
            for ft in f.split():
                if len(ft) < 3:
                    continue
                for qt in q_tokens:
                    rt = SequenceMatcher(None, qt, ft).ratio()
                    if rt < 1.0:  # exclude an exact shared token (e.g. same surname)
                        best = max(best, rt)
        if best >= threshold:
            out.append((cid, cn, round(best, 3)))
    out.sort(key=lambda x: (x[2], x[1]), reverse=True)  # highest SCORE first (name as stable tiebreak)
    return out[:limit]
