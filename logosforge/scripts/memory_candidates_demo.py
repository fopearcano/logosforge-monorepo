#!/usr/bin/env python3
"""Dev demo: the LogosForge memory candidate workflow (Phase 4).

Run this **manually** to see extract → classify → propose → review end to end.
It is never imported or started by the app. It touches **no** database file
(uses an in-process ``:memory:`` store), **no** model, **no** network, and
**no** provider — pure local heuristics.

    python3 scripts/memory_candidates_demo.py

What it shows:
* only *marked* spans become candidates (raw chat is ignored);
* policy auto-saves safe, high-confidence, durable memory as **active**, and
  flags uncertain/sensitive/conflicting/speculative memory for review;
* Project Memory and Assistant Meta-Memory stay separate by scope;
* approve / reject / supersede are explicit and non-destructive;
* a deterministic local session summary;
* a heuristic contradiction surface (no LLM, no embeddings).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from logosforge.assistant_arch.tools import AssistantTools           # noqa: E402
from logosforge.memory_arch.local_store import LocalSQLiteMemoryStore  # noqa: E402
from logosforge.memory_arch.schema import MemoryScope                 # noqa: E402


def banner(title: str) -> None:
    print("\n" + "=" * 68)
    print(title)
    print("=" * 68)


def main() -> int:
    # In-process DB only — nothing is written to disk.
    tools = AssistantTools(store=LocalSQLiteMemoryStore(":memory:"))
    project_id, user_id, session_id = "demo-project", "demo-user", "demo-sess"

    banner("1) Process an event — policy auto-saves safe memory, flags the rest")
    ev = tools.log_event(
        "chat", session_id=session_id, project_id=project_id, user_id=user_id,
        content=(
            "Let's keep writing the chapter. "                # unmarked → ignored
            "I prefer em dashes over semicolons. "            # preference / user
            "For this project, the protagonist is Ada North. "  # decision / project
            "Correction: the deadline is Friday, not Monday. "  # correction / assistant
            "Maybe the rival could secretly be her mentor. "  # speculative
            "Defer the vector index to a later phase. "       # deferred / assistant
            "From now on store api_key: sk-shouldnotbestored1234."  # marked but forbidden → dropped
        ))
    result = tools.process_event_for_memory_candidates(ev)
    for mem in result.written:
        print(f"  + [{mem.scope.value:9}] {mem.type.value:20} "
              f"({mem.status.value}) {mem.content!r}")
    for skip in result.skipped:
        print(f"  - skipped: {skip['reason']}  ::  {skip['content'][:48]!r}")
    for warn in result.warnings:
        print(f"  ! {warn}")

    banner("2) Review queue (proposed + speculative only)")
    for mem in tools.list_memory_candidates():
        print(f"  ? {mem.id[:8]} [{mem.scope.value}] {mem.content!r}")

    banner("3) Approve one, reject one (both non-destructive)")
    proj = tools.list_memory_candidates(scope=MemoryScope.PROJECT,
                                        project_id=project_id)[0]
    approved = tools.approve_memory_candidate(proj.id)
    print(f"  approved → {approved.status.value}: {approved.content!r}")
    user_prefs = tools.list_memory_candidates(scope=MemoryScope.USER)
    rejected = tools.reject_memory_candidate(
        user_prefs[0].id, reason="duplicate of an existing preference")
    print(f"  rejected → {rejected.status.value} (kept, not deleted): "
          f"{tools.store.get(rejected.id) is not None}")

    banner("4) Deterministic session summary (no model)")
    summary = tools.summarize_session(session_id)
    print(f"  status={summary['status']} candidate={summary['candidate_id'][:8]}")
    print(f"  {summary['summary']!r}")

    banner("5) Heuristic contradiction surface")
    tools.write_memory_candidate("The gate is locked at night.",
                                 type=tools.store.get(approved.id).type,
                                 scope=MemoryScope.PROJECT,
                                 project_id=project_id)
    tools.write_memory_candidate("The gate is not locked at night.",
                                 type=tools.store.get(approved.id).type,
                                 scope=MemoryScope.PROJECT,
                                 project_id=project_id)
    for hit in tools.find_contradictions("gate", project_id=project_id):
        ids = ", ".join(m.id[:8] for m in hit["memories"])
        print(f"  ⚠ {hit['kind']}: {hit['reason']}  [{ids}]")

    print("\nDone. No DB file, no network, no provider, no model were used.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
