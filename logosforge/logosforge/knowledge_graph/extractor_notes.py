"""Notes → Knowledge Graph extraction (Phase 10P).

Note nodes, note→PSYKE mention edges (likely, by name/alias), note→scene
mention edges, and detection of *undefined terms* (capitalized terms a note
references that are not in PSYKE) — surfaced as suggestions only. Never
auto-creates PSYKE entries. Capped.
"""

from __future__ import annotations

import re

from logosforge.knowledge_graph import provenance as P
from logosforge.knowledge_graph.models import KGEdge, KGNode, node_key

_MAX_NOTE_EDGES = 300
_WIKILINK = re.compile(r"\[\[(.+?)\]\]")
_CAP_TERM = re.compile(r"\b([A-Z][a-zA-Z]{2,}(?:\s+[A-Z][a-zA-Z]{2,}){0,2})\b")
# Common sentence-initial words we don't treat as proper-noun candidates.
_STOP = {"The", "This", "That", "These", "Those", "When", "Where", "What",
         "While", "Then", "They", "There", "Here", "With", "From", "Into",
         "Also", "But", "And", "For", "Not", "His", "Her", "Their", "She",
         "He", "It", "We", "You", "I"}


def extract_notes(db, project_id: int, graph) -> list[str]:
    """Returns the list of detected undefined terms (for radar/queries)."""
    try:
        notes = db.get_all_notes(project_id)
    except Exception:
        graph.unavailable.append("notes")
        return []
    try:
        entries = db.get_all_psyke_entries(project_id)
        from logosforge.revision_intelligence.psyke_impact import _mentioned, _names
    except Exception:
        entries, _mentioned, _names = [], None, None

    psyke_keys = {}
    known_terms: set[str] = set()
    for e in entries:
        from logosforge.knowledge_graph.extractor_psyke import psyke_node_key
        psyke_keys[e.id] = psyke_node_key(e)
        if _names:
            known_terms.update(n.lower() for n in _names(e))

    scene_titles = {}
    try:
        for s in db.get_all_scenes(project_id):
            t = (getattr(s, "title", "") or "").strip()
            if t:
                scene_titles[t.lower()] = s.id
    except Exception:
        pass

    edge_count = 0
    undefined: set[str] = set()
    for note in notes:
        nkey = node_key(P.NT_NOTE, "note", note.id)
        graph.add_node(KGNode(
            key=nkey, node_type=P.NT_NOTE, source_type="note",
            source_id=str(note.id), label=getattr(note, "title", "") or "",
            summary=(getattr(note, "content", "") or "")[:160],
            metadata={"tags": getattr(note, "tags", "") or ""}))
        graph.add_edge(KGEdge(
            source=node_key(P.NT_PROJECT, "project", project_id), target=nkey,
            edge_type=P.ET_CONTAINS, confidence=P.CONF_CONFIRMED,
            provenance=P.PROV_NOTE_REFERENCE, source_system=P.SS_NOTES,
            explanation="Project note."))

        content = getattr(note, "content", "") or ""
        text_low = (getattr(note, "title", "") + " " + content).lower()

        # Note → PSYKE mentions (likely; explicit wikilinks are confirmed).
        wikilinked = {m.group(1).strip().lower() for m in _WIKILINK.finditer(content)}
        for e in entries:
            if edge_count >= _MAX_NOTE_EDGES:
                graph.warnings.append("Note edge scan capped.")
                break
            if _mentioned is None:
                break
            try:
                hit = _mentioned(e, text_low)
            except Exception:
                hit = False
            if hit:
                name_low = (getattr(e, "name", "") or "").lower()
                conf = P.CONF_CONFIRMED if name_low in wikilinked else P.CONF_LIKELY
                graph.add_edge(KGEdge(
                    source=nkey, target=psyke_keys[e.id], edge_type=P.ET_MENTIONS,
                    confidence=conf, provenance=(P.PROV_NOTE_WIKILINK
                    if conf == P.CONF_CONFIRMED else P.PROV_NOTE_REFERENCE),
                    source_system=P.SS_NOTES,
                    explanation="Note references this PSYKE entry."))
                edge_count += 1

        # Note → scene mentions (by exact title in wikilinks).
        for ref in wikilinked:
            sid = scene_titles.get(ref)
            if sid and edge_count < _MAX_NOTE_EDGES:
                graph.add_edge(KGEdge(
                    source=nkey, target=node_key(P.NT_SCENE, "scene", sid),
                    edge_type=P.ET_MENTIONS, confidence=P.CONF_CONFIRMED,
                    provenance=P.PROV_NOTE_WIKILINK, source_system=P.SS_NOTES,
                    explanation="Note wikilinks this scene."))
                edge_count += 1

        # Undefined terms: capitalized proper-noun candidates not in PSYKE.
        for m in _CAP_TERM.finditer(content):
            words = m.group(1).strip().split()
            # Drop a leading sentence-initial stop word ("The Crimson Order").
            while words and words[0] in _STOP:
                words = words[1:]
            if not words:
                continue
            term = " ".join(words)
            if term.lower() in known_terms or term.lower() in scene_titles:
                continue
            undefined.add(term)

    undefined_list = sorted(undefined)[:25]
    if undefined_list:
        graph.warnings.append(
            f"{len(undefined_list)} note term(s) not defined in PSYKE.")
    return undefined_list
