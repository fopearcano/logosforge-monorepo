"""Manuscript -> structured story-data extractor.

Turns authored scene text into the structured data the format-intelligence
layer consumes (scene<->character links, ``who_knows_what``, typed PSYKE
relations) but that nothing else populates today. See the audit in
``format-intelligence-data-gap`` memory.

Two-tier by design (don't pay the LLM for what a parser extracts exactly):

  - **Tier 1 (deterministic, free, offline):** reuse the existing block parsers
    (``screenplay_blocks.character_cues``) to read character cues straight from
    formatted scene text. Runs with no provider.
  - **Tier 2 (LLM inference):** the un-parseable, comprehension-level signal —
    ``who_knows_what`` and typed PSYKE relations (setup/payoff, subtext,
    visual-motif). Uses the existing ``assistant.chat_completion`` provider
    plumbing; degrades to Tier-1-only when no provider is reachable.

The orchestrator returns *proposals* (read-only); ``apply_extraction`` is a
separate step that writes them through the real DB writers, so a UI can keep a
human in the loop (propose -> review -> apply) before touching the canon.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field

from logosforge import assistant, providers
from logosforge.db import Database
from logosforge.models.models import SceneCharacterLink, Scene
from logosforge.screenplay_blocks import character_cues, parse_screenplay_text
from sqlmodel import Session

# The four relation types the screenplay enricher maps to typed edges.
VALID_REL_TYPES = {
    "supports_setup", "payoff", "subtext_opposition", "visual_motif",
    # stage-script pressure / subtext relation types (enrich_stage_script_graph reads
    # these via get_typed_related_psyke_entries) — so the extractor no longer rejects
    # a theatre pressure relation when it apply-writes one.
    "pressures", "confronts", "dominates", "deceives", "interrupts", "avoids",
}


@dataclass
class NearDupHint:
    """Advisory: an existing entity a proposed name closely resembles (likely an LLM
    typo). Display-only — NEVER used to auto-merge."""
    existing_id: int
    existing_name: str
    score: float


@dataclass
class RelationProposal:
    source: str
    target: str
    rel_type: str
    why: str = ""
    confidence: float = 0.6
    # Advisory, display-only (computed at PROPOSE time, IGNORED by apply): whether
    # each entity will reuse an existing PSYKE entry ("existing") or create a new one
    # ("new"); and — only when "new" — an optional near-duplicate hint flagging a
    # likely typo of an existing entry so the writer can fix/reject it rather than
    # mint a stray row. apply_extraction stays fully conservative (never auto-merges).
    source_status: str = ""
    target_status: str = ""
    source_hint: "NearDupHint | None" = None
    target_hint: "NearDupHint | None" = None


@dataclass
class SceneExtraction:
    scene_id: int
    title: str
    characters: list[str] = field(default_factory=list)        # Tier 1, deterministic
    who_knows_what: str = ""                                    # Tier 2
    relations: list[RelationProposal] = field(default_factory=list)  # Tier 2 (within-scene)


@dataclass
class ProjectExtraction:
    project_id: int
    scenes: list[SceneExtraction] = field(default_factory=list)
    setup_payoffs: list[RelationProposal] = field(default_factory=list)  # Tier 2 (cross-scene)
    used_llm: bool = False


@dataclass
class ApplyReceipt:
    """Exactly what apply_extraction wrote — the provenance record that revert undoes."""
    character_ids: list[int] = field(default_factory=list)        # Character rows created
    links: list[tuple[int, int]] = field(default_factory=list)    # (scene_id, character_id) added
    wkw_scene_ids: list[int] = field(default_factory=list)        # scenes whose who_knows_what we set
    psyke_ids: list[int] = field(default_factory=list)            # PsykeEntry rows created
    relations: list[tuple[int, int, str]] = field(default_factory=list)  # (a, b, type) added


# --------------------------------------------------------------------------- #
# JSON helper (the local provider returns plain text; parse defensively)
# --------------------------------------------------------------------------- #
def _parse_json(text: str):
    text = re.sub(r"```(?:json)?|```", "", text or "").strip()
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


# --------------------------------------------------------------------------- #
# Tier 1 — deterministic (format-aware)
# --------------------------------------------------------------------------- #
# Graphic-novel dialogue cue: an ALLCAPS speaker before a colon inside a panel's
# Dialogue field, e.g. "MARA: Forty years." or "DR. ELIAS (off): ...".
_GN_CUE_RE = re.compile(r"^\s*([A-Z][A-Z0-9 .'’\-]{0,30})\s*(?:\([^)]*\))?\s*:")


def _gn_character_cues(script) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for page in script.pages:
        for panel in page.panels:
            for line in (panel.dialogue or "").splitlines():
                m = _GN_CUE_RE.match(line)
                if not m:
                    continue
                name = re.sub(r"\s+", " ", m.group(1)).strip()
                if not name or any(ch.islower() for ch in name):  # require an ALLCAPS cue
                    continue
                key = name.lower()
                if key not in seen:
                    seen.add(key)
                    out.append(name)
    return out


# Structural labels a format parser may mistake for a cue (scene/act/page headers,
# screenplay INT./EXT. fed to a stage parser, markdown ** headers). Never a character.
_NON_CHAR_RE = re.compile(r"^(INT|EXT|INT\.?/EXT|I/E|EST|ACT|SCENE|PAGE|PANEL|FADE|CUT|THE END)\b", re.IGNORECASE)


def extract_characters(scene_text: str, engine: str = "screenplay") -> list[str]:
    """Speaker cues present in the scene (free, exact, no LLM) — per narrative format."""
    text = scene_text or ""
    e = (engine or "").lower()
    if e == "graphic_novel":
        from logosforge import graphic_novel_blocks as gnb
        cues = _gn_character_cues(gnb.parse_graphic_novel_text(text))
    elif e == "stage_script":
        from logosforge import stage_script_blocks as ssb
        cues = ssb.character_cues(ssb.parse_stage_script_text(text))
    elif e == "series":
        from logosforge import series_blocks as srb
        cues = srb.character_cues(srb.parse_series_text(text))
    else:  # screenplay / novel / default
        cues = character_cues(parse_screenplay_text(text))
    # strip markdown markers, drop structural labels, dedupe (case-insensitive)
    out: list[str] = []
    seen: set[str] = set()
    for c in cues:
        s = re.sub(r"[*#`]+", "", c).strip()
        if not s or _NON_CHAR_RE.match(s):
            continue
        key = s.lower()
        if key not in seen:
            seen.add(key)
            out.append(s)
    return out


# --------------------------------------------------------------------------- #
# Tier 2 — LLM inference
# --------------------------------------------------------------------------- #
def _conf(v, default: float = 0.6) -> float:
    """Clamp a model-supplied confidence to [0, 1]; fall back to the default when the
    model omits it or returns something non-numeric."""
    try:
        return max(0.0, min(1.0, float(v)))
    except (TypeError, ValueError):
        return default


_SCENE_SYSTEM = (
    "You are a precise screenplay structure extractor. You read ONE scene and return ONLY a "
    "single JSON object — no prose, no markdown fences.\n"
    "GROUNDING: state only what THIS scene's text explicitly shows. Never infer off-screen "
    "facts, backstory, or events from other scenes. When unsure, leave it out."
)
_SCENE_SCHEMA = (
    'Return JSON shaped exactly: {"who_knows_what": "...", "relations": '
    '[{"from": "ENTITY", "to": "ENTITY", "type": "TYPE", "why": "...", "confidence": 0.0}]}.\n'
    'who_knows_what: ONE sentence naming who in this scene knows something the others do '
    'NOT, grounded in the text. If no knowledge asymmetry is explicit, return "" (empty). '
    "Never invent a secret.\n"
    "relations: only edges THIS scene clearly supports. Pick the MOST SPECIFIC type; if none "
    "truly fits, OMIT the edge — do not default to one. Types:\n"
    "  subtext_opposition = two CHARACTERS in masked/unspoken conflict (polite words, opposed wills).\n"
    "  visual_motif = a recurring IMAGE/OBJECT/SYMBOL tied to a theme (e.g. a watch, a sound).\n"
    "  supports_setup = an element planted in this scene meant to pay off later.\n"
    "from/to are entity names (prefer the KNOWN ENTITIES). "
    'why = 3-10 words of concrete evidence from the scene (never the bare word "long"). '
    "confidence = 0.0-1.0 for how clearly the scene supports the edge."
)


def extract_scene_inferences(scene_text: str, provider, *, entities: list[str] | None = None, timeout: int = 60) -> tuple[str, list[RelationProposal]]:
    # Degrade gracefully: a slow/missing provider must not hang the whole pass —
    # the deterministic Tier-1 result already stands without this.
    ent = ("\nKNOWN STORY ENTITIES (use these EXACT names when you mean them): " + ", ".join(entities[:40]) + ".") if entities else ""
    try:
        reply, _ = assistant.chat_completion(
            [{"role": "system", "content": _SCENE_SYSTEM},
             {"role": "user", "content": f"{_SCENE_SCHEMA}{ent}\n\nSCENE:\n{scene_text}"}],
            provider=provider, use_cache=False, timeout=timeout,
        )
    except Exception:
        return "", []
    data = _parse_json(reply) or {}
    wkw = (data.get("who_knows_what") or "").strip()
    if wkw.lower() in ("none", "n/a", "null", "nothing", "-"):  # models sometimes fill "None"
        wkw = ""
    rels = []
    for r in data.get("relations", []) or []:
        t = (r.get("type") or "").strip()
        if t in VALID_REL_TYPES and r.get("from") and r.get("to"):
            rels.append(RelationProposal(
                r["from"].strip(), r["to"].strip(), t,
                (r.get("why") or "").strip(), _conf(r.get("confidence")),
            ))
    return wkw, rels


_SETUP_SYSTEM = (
    "You are a screenplay setup/payoff analyst. Across the numbered scene briefs, find an "
    "element (object, line, secret, threat, promise) PLANTED in an earlier scene that PAYS "
    "OFF in a later scene, and express each as a relation between two NAMED story entities. "
    "Only report arcs you can point to in the briefs; if there are none, return an empty list. "
    "Return ONLY one JSON object."
)


def extract_setup_payoffs(briefs: list[tuple[int, str, str]], provider, *, entities: list[str] | None = None, timeout: int = 60) -> list[RelationProposal]:
    """briefs: list of (scene_number, title, text)."""
    joined = "\n\n".join(f"SCENE {n} — {title}:\n{text}" for n, title, text in briefs)
    ent = ("\nKNOWN STORY ENTITIES (prefer these EXACT names): " + ", ".join(entities[:40]) + ".") if entities else ""
    schema = (
        'Return JSON: {"relations": [{"from": "ENTITY", "to": "ENTITY", "type": "supports_setup", '
        '"why": "...", "confidence": 0.0}]}. '
        "from/to MUST be SHORT entity names (at most 4 words) — prefer the KNOWN ENTITIES; NEVER a sentence. "
        "type: supports_setup (FROM planted early, pays off later via TO) or payoff. "
        'why: name the planted element AND how it pays off, in at most 12 words '
        '(e.g. "the four-note ping returns as the saving bearing"); never the bare word "long". '
        "Only genuine cross-scene arcs; from and to must differ."
    )
    try:
        reply, _ = assistant.chat_completion(
            [{"role": "system", "content": _SETUP_SYSTEM},
             {"role": "user", "content": f"{schema}{ent}\n\n{joined}"}],
            provider=provider, use_cache=False, timeout=timeout,
        )
    except Exception:
        return []
    data = _parse_json(reply) or {}
    out = []
    for r in data.get("relations", []) or []:
        t = (r.get("type") or "").strip() or "supports_setup"
        src, tgt = (r.get("from") or "").strip(), (r.get("to") or "").strip()
        # reject verbose/sentence-shaped targets that leaked through the prompt
        if src and tgt and src.lower() != tgt.lower() and len(src.split()) <= 5 and len(tgt.split()) <= 5 and t in ("supports_setup", "payoff"):
            out.append(RelationProposal(src, tgt, t, (r.get("why") or "").strip(), _conf(r.get("confidence"))))
    return out


def _known_entities(db: Database, project_id: int) -> list[str]:
    """Canonical entity names (characters + PSYKE entries) to anchor LLM extraction."""
    names = [c.name for c in db.get_all_characters(project_id)]
    names += [e.name for e in db.get_all_psyke_entries(project_id)]
    seen: set[str] = set()
    out: list[str] = []
    for n in names:
        k = (n or "").strip().lower()
        if k and k not in seen:
            seen.add(k)
            out.append(n.strip())
    return out


# --------------------------------------------------------------------------- #
# Orchestrator (read-only proposals)
# --------------------------------------------------------------------------- #
def extract_project(
    db: Database, project_id: int, provider=None, *,
    use_llm: bool = True, timeout: int = 60,
    on_progress: Callable[[int, int, str], None] | None = None,
) -> ProjectExtraction:
    """Build the proposal set. ``on_progress(done, total, label)`` is invoked after
    each scene (and before the cross-scene pass) so a job runner can stream progress."""
    if provider is None and use_llm:
        provider = providers.build_active_provider()
    entities = _known_entities(db, project_id) if use_llm else []
    proj = db.get_project_by_id(project_id)
    engine = (getattr(proj, "narrative_engine", "") or "screenplay").lower()
    scenes = sorted(db.get_all_scenes(project_id), key=lambda s: s.sort_order)
    total = len(scenes)
    out = ProjectExtraction(project_id=project_id, used_llm=bool(use_llm))
    briefs = []
    for i, s in enumerate(scenes):
        text = s.content or ""
        ex = SceneExtraction(scene_id=s.id, title=s.title, characters=extract_characters(text, engine))
        if use_llm and text.strip():
            ex.who_knows_what, ex.relations = extract_scene_inferences(text, provider, entities=entities, timeout=timeout)
            briefs.append((s.sort_order + 1, s.title, text))
        out.scenes.append(ex)
        if on_progress is not None:
            on_progress(i + 1, total, s.title or f"Scene {s.id}")
    if use_llm and len(briefs) >= 2:
        if on_progress is not None:
            on_progress(total, total, "cross-scene setup / payoff")
        out.setup_payoffs = extract_setup_payoffs(briefs, provider, entities=entities, timeout=timeout)
    # Advisory near-duplicate / new-vs-existing hints for the review UI (no merging).
    # Fully best-effort: a hinting failure must never break the extraction itself.
    try:
        _annotate_near_dupes(db, project_id, out)
    except Exception:
        pass
    return out


# --------------------------------------------------------------------------- #
# Apply — write proposals through the real writers (idempotent)
# --------------------------------------------------------------------------- #
# Conservative name reconciliation now lives in the dependency-free
# logosforge.name_reconcile so the read-time analyzers (narrative dashboard) can
# reuse the SAME matcher without dragging in the LLM provider stack. Re-exported
# here for back-compat (existing callers/tests import these from extraction).
from logosforge.name_reconcile import (  # noqa: E402,F401
    _HONORIFICS,
    _PAREN_TAIL_RE,
    _bare_token_match,
    _forms,
    _match_id,
    _near_dupes,
    _norm,
)


def _annotate_near_dupes(db: Database, project_id: int, ext: ProjectExtraction) -> None:
    """Tag every relation entity (per-scene + cross-scene) with its reconciliation
    status against the project's EXISTING PSYKE entries — the same set apply uses —
    and, for names that would create a NEW entry, attach a near-duplicate hint
    flagging a likely typo. Pure read + in-place annotation; advisory only, so apply
    behavior is unchanged. Best-effort: any failure leaves proposals un-annotated."""
    rels = [r for s in ext.scenes for r in s.relations] + list(ext.setup_payoffs)
    if not rels:
        return
    try:
        items = [(e.id, e.name, e.aliases) for e in db.get_all_psyke_entries(project_id)]
    except Exception:
        return

    def _status_hint(name: str):
        if not (name or "").strip():
            return "", None
        if _match_id(name, items) is not None:
            return "existing", None
        near = _near_dupes(name, items)
        hint = NearDupHint(near[0][0], near[0][1], near[0][2]) if near else None
        return "new", hint

    for r in rels:
        r.source_status, r.source_hint = _status_hint(r.source)
        r.target_status, r.target_hint = _status_hint(r.target)


def _reconcile_character(db: Database, project_id: int, name: str, cache: dict, receipt: ApplyReceipt) -> int:
    key = name.strip().lower()
    if key in cache:
        return cache[key]
    cid = _match_id(name, [(c.id, c.name, "") for c in db.get_all_characters(project_id)])
    if cid is None:
        cid = db.create_character(project_id, name.strip(), "extracted").id
        receipt.character_ids.append(cid)
    cache[key] = cid
    return cid


def _reconcile_psyke(db: Database, project_id: int, name: str, entry_type: str, cache: dict, receipt: ApplyReceipt) -> int:
    key = name.strip().lower()
    if key in cache:
        return cache[key]
    eid = _match_id(name, [(e.id, e.name, e.aliases) for e in db.get_all_psyke_entries(project_id)])
    if eid is None:
        eid = db.create_psyke_entry(project_id, name.strip(), entry_type=entry_type, notes="extracted").id
        receipt.psyke_ids.append(eid)
    cache[key] = eid
    return eid


def apply_extraction(db: Database, project_id: int, ext: ProjectExtraction) -> ApplyReceipt:
    # Phased to avoid nested Sessions (db.* writers open their own session — two
    # concurrent SQLite writers => "database is locked"). Records EXACTLY what it
    # writes into the receipt so revert_extraction can undo it precisely.
    receipt = ApplyReceipt()
    char_cache: dict[str, int] = {}
    psyke_cache: dict[str, int] = {}
    cue_names = {c.strip().lower() for s in ext.scenes for c in s.characters}

    # Phase 1: ensure every cued character exists.
    for s in ext.scenes:
        for name in s.characters:
            _reconcile_character(db, project_id, name, char_cache, receipt)

    # Phase 2: snapshot existing links before the write session.
    existing_links = {s.scene_id: set(db.get_scene_character_ids(s.scene_id)) for s in ext.scenes}

    # Phase 3: one write session for the raw link inserts + who_knows_what.
    with Session(db._engine) as session:
        for s in ext.scenes:
            have = existing_links[s.scene_id]
            for name in s.characters:
                cid = char_cache[name.strip().lower()]
                if cid not in have:
                    session.add(SceneCharacterLink(scene_id=s.scene_id, character_id=cid))
                    receipt.links.append((s.scene_id, cid))
                    have.add(cid)
            if s.who_knows_what:
                scene = session.get(Scene, s.scene_id)
                if scene is not None and not (scene.who_knows_what or "").strip():
                    scene.who_knows_what = s.who_knows_what
                    receipt.wkw_scene_ids.append(s.scene_id)
        session.commit()

    # Phase 4: typed PSYKE relations (entries created if missing).
    def _ptype(name: str) -> str:
        return "character" if name.strip().lower() in cue_names else "object"

    seen_rel: set[tuple[int, int, str]] = set()
    for rel in [r for s in ext.scenes for r in s.relations] + ext.setup_payoffs:
        if rel.rel_type not in VALID_REL_TYPES:
            continue
        a = _reconcile_psyke(db, project_id, rel.source, _ptype(rel.source), psyke_cache, receipt)
        b = _reconcile_psyke(db, project_id, rel.target, _ptype(rel.target), psyke_cache, receipt)
        if a == b or (a, b, rel.rel_type) in seen_rel:
            continue
        existing = {(e.id, t) for e, t in db.get_typed_related_psyke_entries(a)}
        if (b, rel.rel_type) not in existing:
            db.add_psyke_relation(a, b, rel.rel_type)
            receipt.relations.append((a, b, rel.rel_type))
            seen_rel.add((a, b, rel.rel_type))

    # Bind the cued manuscript Characters to their PSYKE 'character' bible entries
    # by name (idempotent; only fills unlinked rows) so the cast and the bible
    # share a stable id link, not just a runtime name match.
    db.backfill_character_psyke_links(project_id)
    return receipt


def revert_extraction(db: Database, receipt: ApplyReceipt) -> ApplyReceipt:
    """Undo a prior apply: delete the links/relations/entities it created and clear the
    who_knows_what it set. Returns what was actually removed (idempotent — missing rows skipped)."""
    from sqlmodel import select

    from logosforge.models.models import Character, PsykeEntry, PsykeRelation

    removed = ApplyReceipt()
    with Session(db._engine) as session:
        # 1. typed relations (delete both directions of the bidirectional pair)
        for a, b, t in receipt.relations:
            hit = False
            for x, y in ((a, b), (b, a)):
                for row in session.exec(select(PsykeRelation).where(PsykeRelation.entry_id == x, PsykeRelation.related_entry_id == y)).all():
                    session.delete(row)
                    hit = True
            if hit:
                removed.relations.append((a, b, t))
        # 2. scene-character links
        for scene_id, cid in receipt.links:
            rows = session.exec(select(SceneCharacterLink).where(SceneCharacterLink.scene_id == scene_id, SceneCharacterLink.character_id == cid)).all()
            for row in rows:
                session.delete(row)
            if rows:
                removed.links.append((scene_id, cid))
        # 3. who_knows_what -> restore empty (apply only set previously-empty scenes)
        for sid in receipt.wkw_scene_ids:
            sc = session.get(Scene, sid)
            if sc is not None:
                sc.who_knows_what = ""
                removed.wkw_scene_ids.append(sid)
        # 4. PSYKE entries created (+ any relation touching them)
        for eid in receipt.psyke_ids:
            for row in session.exec(select(PsykeRelation).where((PsykeRelation.entry_id == eid) | (PsykeRelation.related_entry_id == eid))).all():
                session.delete(row)
            e = session.get(PsykeEntry, eid)
            if e is not None:
                session.delete(e)
                removed.psyke_ids.append(eid)
        # 5. Character rows created (+ their links)
        for cid in receipt.character_ids:
            for row in session.exec(select(SceneCharacterLink).where(SceneCharacterLink.character_id == cid)).all():
                session.delete(row)
            c = session.get(Character, cid)
            if c is not None:
                session.delete(c)
                removed.character_ids.append(cid)
        session.commit()
    return removed
