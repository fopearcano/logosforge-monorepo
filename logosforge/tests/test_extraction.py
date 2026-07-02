"""Extractor reconciliation regression tests.

A Tier-2 relation that names an existing PSYKE bible entry by a bare cue
("Park"), an honorific form ("Lt. Jonah Park") or a screenplay parenthetical
("DELACROIX (V.O.)") must reconcile to that entry — never spawn a duplicate.
See the writer-QA finding in memory ``logosforge-pro-writer-qa``.
"""

from logosforge import extraction
from logosforge.db import Database
from logosforge.extraction import _match_id, _norm


def test_norm_strips_honorifics_and_parentheticals():
    assert _norm("Lt. Jonah Park") == "jonah park"
    assert _norm("DELACROIX (V.O.)") == "delacroix"
    assert _norm("The Last Archive") == "last archive"
    assert _norm("Capt. Ada Reyes") == "ada reyes"
    assert _norm("ORACLE") == "oracle"


def test_match_id_reconciles_cue_to_bible_entry():
    items = [
        (1, "Lt. Jonah Park", "Park,Jonah"),
        (2, "Cmdr. Rhea Delacroix", "DELACROIX,Rhea"),
        (3, "Mara Voss", "MARA,Mara"),
    ]
    assert _match_id("Park", items) == 1            # bare surname cue
    assert _match_id("DELACROIX (V.O.)", items) == 2  # honorific-free + parenthetical
    assert _match_id("Jonah", items) == 1            # first-name / alias
    assert _match_id("MARA", items) == 3             # all-caps alias
    assert _match_id("Eli", items) is None           # genuinely absent => no false match


def test_match_id_does_not_false_merge_distinct_names():
    """The fuzzy expansion must never collapse two DISTINCT people. Reconciliation
    only expands a *bare* cue, and only when unambiguous."""
    # A bare surname expands to the single matching full name (entry has no alias).
    assert _match_id("Park", [(1, "Jonah Park", "")]) == 1
    # A full multi-token cue with a DIFFERENT first name is a different person.
    assert _match_id("Sarah Park", [(1, "Jonah Park", "")]) is None
    assert _match_id("John Doe", [(1, "John Smith", "")]) is None
    # An ambiguous bare cue (two same-surname people) refuses to guess.
    assert _match_id("Park", [(1, "Jonah Park", ""), (2, "Sarah Park", "")]) is None
    # No prefix over-match: a longer/related short name is not absorbed.
    assert _match_id("Eddie", [(1, "Ed", "")]) is None
    assert _match_id("Samantha", [(1, "Sam", "")]) is None
    # Ambiguous title words ('Major','Doctor') are NOT stripped, so the name stays distinct.
    assert _match_id("Major Tom", [(1, "Tom", "")]) is None
    assert _match_id("Doctor Strange", [(1, "Strange Visitor", "")]) is None


def test_apply_does_not_duplicate_existing_bible():
    db = Database()
    proj = db.create_project("Dedup Test")
    db.create_psyke_entry(proj.id, "Lt. Jonah Park", entry_type="character", aliases="Park,Jonah")
    db.create_psyke_entry(proj.id, "Cmdr. Rhea Delacroix", entry_type="character", aliases="DELACROIX,Rhea")
    before = len(db.get_all_psyke_entries(proj.id))

    ext = extraction.ProjectExtraction(
        project_id=proj.id, used_llm=False, scenes=[],
        setup_payoffs=[
            extraction.RelationProposal("Park", "DELACROIX (V.O.)", "subtext_opposition", "why", 0.6),
        ],
    )
    receipt = extraction.apply_extraction(db, proj.id, ext)

    assert len(db.get_all_psyke_entries(proj.id)) == before  # no duplicate entries
    assert receipt.psyke_ids == []                           # nothing newly created
    assert len(receipt.relations) == 1                       # linked the two EXISTING entries

    # And revert stays a clean no-op on entries (only the one relation removed).
    removed = extraction.revert_extraction(db, receipt)
    assert len(db.get_all_psyke_entries(proj.id)) == before
    assert len(removed.relations) == 1


def test_annotate_near_dupes_flags_typos_not_distinct_names():
    """Propose-time advisory: a relation entity that would CREATE a new entry is
    tagged 'new' and, when it closely resembles an existing entry (a likely LLM
    typo), carries a near-dup hint — while an exact existing name is 'existing' with
    no hint, and a distinct same-surname name is 'new' with NO hint (never a merge).
    apply stays untouched: this is display-only."""
    db = Database()
    proj = db.create_project("Hint Test")
    delacroix = db.create_psyke_entry(proj.id, "Cmdr. Rhea Delacroix", entry_type="character", aliases="DELACROIX,Rhea")
    db.create_psyke_entry(proj.id, "Lt. Jonah Park", entry_type="character", aliases="Park,Jonah")

    ext = extraction.ProjectExtraction(
        project_id=proj.id, used_llm=True,
        scenes=[extraction.SceneExtraction(scene_id=1, title="S", relations=[
            # source: LLM typo of an existing entry; target: exact existing alias
            extraction.RelationProposal("Delacorix", "Park", "subtext_opposition", "why", 0.6),
            # a distinct same-surname person must be 'new' with NO hint (no false merge)
            extraction.RelationProposal("Sarah Park", "Rhea", "subtext_opposition", "why", 0.6),
        ])],
    )
    extraction._annotate_near_dupes(db, proj.id, ext)
    r1, r2 = ext.scenes[0].relations

    # typo source -> new + hint pointing at the real entry
    assert r1.source_status == "new"
    assert r1.source_hint is not None and r1.source_hint.existing_id == delacroix.id
    assert r1.source_hint.existing_name == "Cmdr. Rhea Delacroix"
    # exact existing target -> existing, no hint
    assert r1.target_status == "existing" and r1.target_hint is None
    # distinct same-surname -> new, but NO hint (the conservative no-false-merge case)
    assert r2.source_status == "new" and r2.source_hint is None
    # exact existing alias 'Rhea' -> existing
    assert r2.target_status == "existing" and r2.target_hint is None


def test_near_dupes_returns_closest_match_first():
    """When several existing entries clear the similarity threshold for one typo,
    the BEST (highest-score) candidate must be returned first — not the one whose
    name sorts last alphabetically. Regression for a sort-by-name bug."""
    from logosforge.name_reconcile import _near_dupes

    items = [(1, "Delacroix", ""), (2, "Welacroiy", "")]  # both near 'Delacroi'
    best = _near_dupes("Delacroi", items, limit=2)
    assert best[0][1] == "Delacroix"          # closest, despite 'Welacroiy' sorting later
    assert best[0][2] >= best[1][2]           # sorted by score, descending
