"""Assistant context builder — Phase 5 local retrieval + composition.

Mirrors `docs/architecture/ASSISTANT_ORCHESTRATION_LAYER.md`. Implements the
**retrieve / structure** half of the LogosForge principle ("the model
generates; LogosForge remembers, retrieves, structures, updates, and syncs")
as a **local-only, provider-agnostic** context composer:

- retrieves **scoped** memory from a local `MemoryStore` (project / user /
  workspace / assistant), kept in **separate** bundle sections — never a single
  generic blob;
- deterministic keyword ranking + selection (no embeddings, no vector DB);
- a character-budget placeholder with safe truncation;
- optional provider **capabilities** (size/tool strategy hints) — capabilities
  are *not* memory and are never stored;
- prompt-section serialization that labels every scope and strips secrets /
  raw-audio paths.

**No model/provider is ever called here. No memory is ever written here.**
Nothing in this module is wired into the running Alpha; importing it touches no
DB, provider, or UI. Model backends (LM Studio, Ollama, vLLM, OpenAI,
Anthropic, OpenRouter) are generation backends only — they are not memory.
"""

from __future__ import annotations

import re
import time
import uuid
from dataclasses import dataclass, field

from logosforge.assistant_arch.model_gateway import ProviderCapability
from logosforge.memory_arch.policy import MemoryWriterPolicy
from logosforge.memory_arch.retrieval import MemoryRetriever
from logosforge.memory_arch.schema import (
    MemoryObject,
    MemoryScope,
    MemoryStatus,
    MemoryType,
)
from logosforge.memory_arch.store import MemoryStore

# ---- status groupings -------------------------------------------------------
# Non-active "needs a human / not yet trusted" statuses — excluded from normal
# context; surfaced only in review/diagnostic mode.
_CANDIDATE_STATUSES = (MemoryStatus.PROPOSED, MemoryStatus.SPECULATIVE,
                       MemoryStatus.REVIEW_REQUIRED)
_ARCHIVED_STATUSES = (MemoryStatus.DEPRECATED, MemoryStatus.SUPERSEDED,
                      MemoryStatus.CONTRADICTED, MemoryStatus.REJECTED)

# ---- expected types per scope (ranking signals, not hard filters) -----------
_PROJECT_TYPES = {
    MemoryType.PROJECT_DECISION, MemoryType.CHARACTER_FACT,
    MemoryType.CONTINUITY_FACT, MemoryType.SESSION_SUMMARY,
    MemoryType.LIMITATION, MemoryType.DEFERRED_FEATURE,
    MemoryType.RELEASE_BLOCKER_RULE, MemoryType.ARCHITECTURE_DECISION,
}
_USER_TYPES = {
    MemoryType.PREFERENCE, MemoryType.MODEL_PREFERENCE,
    MemoryType.WORKFLOW_RULE, MemoryType.PROCEDURAL_RULE,
}
_ASSISTANT_TYPES = {
    MemoryType.ASSISTANT_RULE, MemoryType.WORKFLOW_RULE,
    MemoryType.MISTAKE_CORRECTION, MemoryType.ARCHITECTURE_DECISION,
    MemoryType.REPO_DECISION, MemoryType.PROCEDURAL_RULE,
    MemoryType.RELEASE_BLOCKER_RULE, MemoryType.DEFERRED_FEATURE,
    MemoryType.LIMITATION, MemoryType.SESSION_SUMMARY,
}
_WORKSPACE_TYPES = {
    MemoryType.PROJECT_DECISION, MemoryType.ARCHITECTURE_DECISION,
    MemoryType.REPO_DECISION, MemoryType.WORKFLOW_RULE,
    MemoryType.PROCEDURAL_RULE,
}
# The focused "assistant rules" sub-view (externalized self-model references).
_ASSISTANT_RULE_TYPES = {
    MemoryType.ASSISTANT_RULE, MemoryType.PROCEDURAL_RULE,
    MemoryType.WORKFLOW_RULE,
}

_DEFAULT_CHAR_BUDGET = 6000
_PER_ITEM_CHAR_CAP = 1000
_CHARS_PER_TOKEN = 4            # crude placeholder; no tokenizer dependency
_EXCERPT_CAP = 800


def _policy() -> MemoryWriterPolicy:
    return MemoryWriterPolicy()


def _safe_content(text: str, policy: MemoryWriterPolicy | None = None) -> str:
    """Defense-in-depth: stored memory is already policy-clean, but never let a
    secret / raw-audio path reach a prompt section even if one slipped in."""
    policy = policy or _policy()
    return "[redacted]" if policy.check_forbidden_content_text(text or "") \
        else (text or "")


# ============================================================ document context
@dataclass
class DocumentContext:
    """Generic, provider-agnostic snapshot of the current editor/document state.

    This is an **adapter input**, not a live hook into the running app. Future
    integration (see `chat_context.py` / `assistant_context_policy.py`) would
    populate this from the active project/editor without changing this module.
    """
    project_id: str | None = None
    current_mode: str | None = None        # novel | screenplay | graphic_novel | stage_script | series
    active_section: str | None = None      # Manuscript | Outline | Notes | PSYKE | Timeline | Dexter
    document_text: str = ""
    selected_excerpt: str = ""
    selected_block_id: str | None = None
    selected_unit_id: str | None = None    # scene / chapter / page / panel
    active_entities: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


def _coerce_document(document) -> DocumentContext | None:
    if document is None:
        return None
    if isinstance(document, DocumentContext):
        return document
    if isinstance(document, dict):
        allowed = {f for f in DocumentContext.__dataclass_fields__}
        return DocumentContext(**{k: v for k, v in document.items()
                                  if k in allowed})
    # Duck-typed adapter: anything exposing get_document_context().
    getter = getattr(document, "get_document_context", None)
    if callable(getter):
        return _coerce_document(getter())
    return None


# ================================================================ context bundle
@dataclass
class ContextBundle:
    """Structured, provider-agnostic assistant context. Memory sections are kept
    strictly separate — they are never merged into one generic blob."""

    request_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    user_request: str = ""
    project_id: str | None = None
    user_id: str | None = None
    workspace_id: str | None = None
    current_mode: str | None = None
    current_document_context: str = ""
    selected_document_excerpt: str = ""

    # Separate memory sections (never combined).
    project_memory: list[MemoryObject] = field(default_factory=list)
    user_memory: list[MemoryObject] = field(default_factory=list)
    workspace_memory: list[MemoryObject] = field(default_factory=list)
    assistant_meta_memory: list[MemoryObject] = field(default_factory=list)
    assistant_rules: list[MemoryObject] = field(default_factory=list)

    provider_capabilities: ProviderCapability | None = None

    retrieval_warnings: list[str] = field(default_factory=list)
    excluded_memory: list[dict] = field(default_factory=list)

    # Budget accounting (character placeholder; no tokenizer dependency).
    token_budget: int = 0
    character_budget: int = _DEFAULT_CHAR_BUDGET
    estimated_chars: int = 0
    estimated_tokens: int = 0
    included_count: int = 0
    excluded_count: int = 0

    created_at: float = field(default_factory=time.time)
    metadata: dict = field(default_factory=dict)

    # -- back-compat aliases (older callers/tests used these names) ------
    @property
    def warnings(self) -> list[str]:
        return self.retrieval_warnings

    @property
    def retrieved_at(self) -> float:
        return self.created_at

    # -- serialization ---------------------------------------------------
    def to_prompt_sections(self, diagnostic: bool = False,
                           policy: MemoryWriterPolicy | None = None
                           ) -> list[dict]:
        """Ordered, clearly-labeled prompt sections. Strips secrets / raw-audio
        paths; omits archived statuses unless ``diagnostic``; never includes raw
        source events or provider keys. **Context preparation only — not sent to
        any provider.**"""
        policy = policy or _policy()

        def fmt(mem: MemoryObject) -> str:
            content = _safe_content(mem.content, policy)
            if len(content) > _PER_ITEM_CHAR_CAP:
                content = content[:_PER_ITEM_CHAR_CAP].rstrip() + " […]"
            return (f"- [{mem.type.value}] {content} "
                    f"(status: {mem.status.value}, "
                    f"confidence: {mem.confidence:.2f})")

        def block(items: list[MemoryObject]) -> str:
            shown = [m for m in items
                     if diagnostic or m.status not in _ARCHIVED_STATUSES]
            return "\n".join(fmt(m) for m in shown) if shown else "(none)"

        sections = [
            {"title": "Current Task",
             "body": _safe_content(self.user_request, policy) or "(none)"},
            {"title": "Current Document Context",
             "body": self.current_document_context or "(none)"},
            {"title": "Project Memory", "body": block(self.project_memory)},
            {"title": "User Memory", "body": block(self.user_memory)},
            {"title": "Workspace Memory", "body": block(self.workspace_memory)},
            {"title": "Assistant Meta-Memory",
             "body": block(self.assistant_meta_memory)},
            {"title": "Assistant Rules", "body": block(self.assistant_rules)},
            {"title": "Provider Capabilities",
             "body": _format_capabilities(self.provider_capabilities)},
            {"title": "Warnings / Exclusions",
             "body": _format_warnings(self.retrieval_warnings,
                                      self.excluded_memory)},
        ]
        return sections

    def to_prompt_text(self, diagnostic: bool = False) -> str:
        parts = []
        for sec in self.to_prompt_sections(diagnostic=diagnostic):
            parts.append(f"## {sec['title']}\n{sec['body']}")
        return "\n\n".join(parts)

    def to_dict(self, policy: MemoryWriterPolicy | None = None) -> dict:
        policy = policy or _policy()

        def mem(m: MemoryObject) -> dict:
            return {"id": m.id, "scope": m.scope.value, "type": m.type.value,
                    "status": m.status.value,
                    "content": _safe_content(m.content, policy),
                    "confidence": m.confidence, "tags": list(m.tags),
                    "entities": list(m.entities), "project_id": m.project_id}

        return {
            "request_id": self.request_id, "user_request": self.user_request,
            "project_id": self.project_id, "user_id": self.user_id,
            "workspace_id": self.workspace_id, "current_mode": self.current_mode,
            "current_document_context": self.current_document_context,
            "selected_document_excerpt": self.selected_document_excerpt,
            "project_memory": [mem(m) for m in self.project_memory],
            "user_memory": [mem(m) for m in self.user_memory],
            "workspace_memory": [mem(m) for m in self.workspace_memory],
            "assistant_meta_memory": [mem(m) for m in self.assistant_meta_memory],
            "assistant_rules": [mem(m) for m in self.assistant_rules],
            "provider_capabilities": _capabilities_dict(self.provider_capabilities),
            "retrieval_warnings": list(self.retrieval_warnings),
            "excluded_memory": list(self.excluded_memory),
            "token_budget": self.token_budget,
            "character_budget": self.character_budget,
            "estimated_chars": self.estimated_chars,
            "estimated_tokens": self.estimated_tokens,
            "included_count": self.included_count,
            "excluded_count": self.excluded_count,
            "created_at": self.created_at, "metadata": dict(self.metadata),
        }


# Capability fields exposed to the assistant (size/tool strategy hints only —
# never base_url / auth_mode, which are not context).
_CAPABILITY_FIELDS = (
    "provider_id", "provider_type", "context_window", "supports_tools",
    "supports_json_schema", "supports_streaming", "supports_embeddings",
    "supports_vision", "supports_audio", "privacy_mode", "offline_capable",
)


def _capabilities_dict(cap: ProviderCapability | None) -> dict:
    if cap is None:
        return {}
    out = {}
    for f in _CAPABILITY_FIELDS:
        v = getattr(cap, f, None)
        out[f] = v.value if hasattr(v, "value") else v
    return out


def _format_capabilities(cap: ProviderCapability | None) -> str:
    if cap is None:
        return "(no provider selected)"
    d = _capabilities_dict(cap)
    return "\n".join(f"- {k}: {v}" for k, v in d.items())


def _format_warnings(warnings: list[str], excluded: list[dict]) -> str:
    lines = [f"- warning: {w}" for w in warnings]
    for e in excluded:
        lines.append(f"- excluded ({e['reason']}): "
                     f"[{e['scope']}/{e['type']}] {e.get('preview', '')}")
    return "\n".join(lines) if lines else "(none)"


# ============================================================== builder
class AssistantContextBuilder:
    """Read-only, local-only context assembly. Optional store/gateway/policy;
    degrades safely (valid empty bundle) when a store is absent. Never mutates
    memory; never calls a model/provider."""

    def __init__(self, store: MemoryStore | None = None, gateway=None,
                 policy: MemoryWriterPolicy | None = None) -> None:
        self._store = store
        self._gateway = gateway
        self._policy = policy or _policy()
        self._retriever = MemoryRetriever(store)   # back-compat helper

    # --------------------------------------------------------------- main
    def build_context(self, user_request: str, project_id: str | None = None,
                      user_id: str | None = None,
                      workspace_id: str | None = None,
                      provider_id: str | None = None, *,
                      request_id: str | None = None,
                      task_type: str | None = None,
                      current_mode: str | None = None,
                      active_entities: list[str] | None = None,
                      document=None, filters: dict | None = None,
                      include_proposed: bool = False, review_mode: bool = False,
                      diagnostic: bool = False,
                      character_budget: int | None = None,
                      token_budget: int | None = None) -> ContextBundle:
        """Compose a scoped, provider-agnostic `ContextBundle`. Read-only.

        Status policy: **active by default**; `include_proposed`/`review_mode`
        also surface proposed/speculative; `diagnostic` additionally surfaces
        deprecated/superseded/contradicted/rejected **with labels**. Archived
        statuses are otherwise reported under `excluded_memory`.
        """
        doc = _coerce_document(document)
        # Document fields can supply defaults the caller did not pass.
        if doc is not None:
            project_id = project_id or doc.project_id
            current_mode = current_mode or doc.current_mode
        merged_entities = list(active_entities or [])
        if doc is not None:
            merged_entities += [e for e in doc.active_entities
                                if e not in merged_entities]

        # Budget: explicit char budget wins, else derive from tokens, else default.
        if character_budget is not None:
            char_budget = character_budget
        elif token_budget is not None:
            char_budget = max(token_budget, 0) * _CHARS_PER_TOKEN
        else:
            char_budget = _DEFAULT_CHAR_BUDGET

        bundle = ContextBundle(
            request_id=request_id or uuid.uuid4().hex,
            user_request=user_request or "", project_id=project_id,
            user_id=user_id, workspace_id=workspace_id,
            current_mode=current_mode, token_budget=token_budget or 0,
            character_budget=char_budget)

        if doc is not None:
            bundle.current_document_context = _summarize_document(doc, self._policy)
            bundle.selected_document_excerpt = _safe_content(
                doc.selected_excerpt or doc.document_text, self._policy)[:_EXCERPT_CAP]

        include_candidates = include_proposed or review_mode or diagnostic
        include_archived = diagnostic
        excluded: list[dict] = []

        if self._store is None:
            bundle.retrieval_warnings.append(
                "no memory store configured (empty memory).")
            return bundle

        # ---- compose each scope independently (kept separate) ----------
        if project_id:
            project_ranked = self._compose(
                MemoryScope.PROJECT, user_request, project_id, user_id,
                workspace_id, current_mode, merged_entities, task_type,
                _PROJECT_TYPES, include_candidates, include_archived,
                filters, excluded)
        else:
            project_ranked = []
            bundle.retrieval_warnings.append(
                "no project_id; Project Memory omitted.")

        user_ranked = self._compose(
            MemoryScope.USER, user_request, project_id, user_id, workspace_id,
            current_mode, merged_entities, task_type, _USER_TYPES,
            include_candidates, include_archived, filters, excluded)

        if workspace_id:
            workspace_ranked = self._compose(
                MemoryScope.WORKSPACE, user_request, project_id, user_id,
                workspace_id, current_mode, merged_entities, task_type,
                _WORKSPACE_TYPES, include_candidates, include_archived,
                filters, excluded)
        else:
            workspace_ranked = []

        assistant_ranked = self._compose(
            MemoryScope.ASSISTANT, user_request, project_id, user_id,
            workspace_id, current_mode, merged_entities, task_type,
            _ASSISTANT_TYPES, include_candidates, include_archived,
            filters, excluded)

        # Assistant rules = focused rule-typed sub-view of assistant scope.
        rule_items = [m for m in assistant_ranked
                      if m.type in _ASSISTANT_RULE_TYPES]
        non_rule_assistant = [m for m in assistant_ranked
                              if m.type not in _ASSISTANT_RULE_TYPES]

        # ---- budget: assistant rules + project decisions first ---------
        priority = [
            ("assistant_rules", rule_items),
            ("project_memory", project_ranked),
            ("user_memory", user_ranked),
            ("workspace_memory", workspace_ranked),
            ("assistant_other", non_rule_assistant),
        ]
        kept, over_budget, used_chars = _apply_budget(priority, char_budget)
        excluded.extend(over_budget)

        bundle.assistant_rules = kept["assistant_rules"]
        bundle.project_memory = kept["project_memory"]
        bundle.user_memory = kept["user_memory"]
        bundle.workspace_memory = kept["workspace_memory"]
        # Meta-memory is the full assistant view (rules + the rest), rank-ordered.
        bundle.assistant_meta_memory = _merge_keep_order(
            assistant_ranked, kept["assistant_rules"] + kept["assistant_other"])

        bundle.excluded_memory = excluded
        bundle.estimated_chars = used_chars
        bundle.estimated_tokens = used_chars // _CHARS_PER_TOKEN
        bundle.included_count = (len(bundle.project_memory)
                                 + len(bundle.user_memory)
                                 + len(bundle.workspace_memory)
                                 + len(bundle.assistant_meta_memory))
        bundle.excluded_count = len(excluded)

        # ---- provider capabilities (hints only; never memory) ----------
        bundle.provider_capabilities = self._provider_capabilities(
            provider_id, bundle.retrieval_warnings)
        return bundle

    # ----------------------------------------------------------- internals
    def _compose(self, scope, query, project_id, user_id, workspace_id,
                 current_mode, active_entities, task_type, expected_types,
                 include_candidates, include_archived, filters, excluded):
        """Retrieve one scope, apply id/status gates, then rank. Appends
        rejected items to ``excluded`` with reasons."""
        raw = self._store.search("", scope=scope)
        type_filter = (filters or {}).get("type")
        included = []
        for mem in raw:
            # Scope-id integrity → never mis-file or leak across owners.
            if scope is MemoryScope.PROJECT and project_id \
                    and mem.project_id != project_id:
                excluded.append(_excl(mem, "wrong project", self._policy)); continue
            if scope is MemoryScope.USER and user_id \
                    and mem.user_id != user_id:
                excluded.append(_excl(mem, "wrong user", self._policy)); continue
            if scope is MemoryScope.WORKSPACE and workspace_id \
                    and mem.workspace_id != workspace_id:
                excluded.append(_excl(mem, "wrong workspace", self._policy)); continue
            if type_filter is not None and mem.type is not MemoryType(type_filter):
                continue
            # Status gate.
            if mem.status in _ARCHIVED_STATUSES:
                if include_archived:
                    included.append(mem)
                else:
                    excluded.append(_excl(mem, mem.status.value, self._policy))
                continue
            if mem.status in _CANDIDATE_STATUSES:
                if include_candidates:
                    included.append(mem)
                else:
                    excluded.append(_excl(
                        mem, f"not active ({mem.status.value})", self._policy))
                continue
            included.append(mem)        # active
        return _rank(included, query, project_id, current_mode,
                     active_entities, task_type, expected_types)

    def _provider_capabilities(self, provider_id, warnings):
        if self._gateway is None or not provider_id:
            warnings.append("no provider selected; capabilities unavailable.")
            return None
        for cap in self._gateway.list_providers():
            if cap.provider_id == provider_id:
                return cap
        warnings.append(f"provider '{provider_id}' not registered.")
        return None

    # ----------------------------------------------- back-compat surface
    def retrieve_project_context(self, project_id: str) -> dict:
        """Placeholder snapshot. Real editor/project state arrives via a
        `DocumentContext` adapter; this never reaches into the UI."""
        return {"project_id": project_id, "document_context": "",
                "structure": []}

    def retrieve_relevant_memory(self, query: str,
                                 scopes: list[MemoryScope],
                                 project_id: str | None = None,
                                 user_id: str | None = None,
                                 workspace_id: str | None = None
                                 ) -> list[MemoryObject]:
        return self._retriever.retrieve(query, scopes, project_id, user_id,
                                        workspace_id)

    def select_context(self, memory_items: list[MemoryObject],
                       token_budget: int) -> list[MemoryObject]:
        kept, _over, _used = _apply_budget(
            [("only", list(memory_items))],
            max(token_budget, 0) * _CHARS_PER_TOKEN or _DEFAULT_CHAR_BUDGET)
        return kept["only"]


# ============================================================ helpers
def _excl(mem: MemoryObject, reason: str,
          policy: MemoryWriterPolicy) -> dict:
    return {"id": mem.id, "scope": mem.scope.value, "type": mem.type.value,
            "status": mem.status.value, "reason": reason,
            "preview": _safe_content(mem.content, policy)[:80]}


def _rank(items, query, project_id, current_mode, active_entities, task_type,
          expected_types):
    """Deterministic descending sort by relevance score, then recency, then id."""
    scored = [(_score(m, query, project_id, current_mode, active_entities,
                      task_type, expected_types), m) for m in items]
    scored.sort(key=lambda pair: (-pair[0], -(pair[1].updated_at or 0.0),
                                  pair[1].id))
    return [m for _s, m in scored]


def _score(mem: MemoryObject, query, project_id, current_mode, active_entities,
           task_type, expected_types) -> float:
    q = (query or "").lower().strip()
    content = mem.content.lower()
    tags = [t.lower() for t in mem.tags]
    ents = [e.lower() for e in mem.entities]
    score = 0.0
    if q:
        if q in content:
            score += 5
        if any(q in t for t in tags):
            score += 3
        if any(q in e for e in ents):
            score += 3
        words = [w for w in re.findall(r"[a-z0-9']+", q) if len(w) > 2]
        if words and any(w in content for w in words):
            score += 1
    if project_id and mem.project_id == project_id:
        score += 2
    if mem.status is MemoryStatus.ACTIVE:
        score += 2
    score += min(max(mem.confidence, 0.0), 1.0)
    if mem.type in expected_types:
        score += 1
    if task_type and (task_type.lower() in content
                      or task_type.lower() == mem.type.value):
        score += 1
    if current_mode:
        cm = current_mode.lower()
        if cm in content or any(cm in t for t in tags):
            score += 1
    for ent in (active_entities or []):
        e = ent.lower()
        if e and (e in content or any(e in x for x in ents)
                  or any(e in t for t in tags)):
            score += 2
    return score


def _apply_budget(sections_in_priority, char_budget):
    """Greedy character budget across sections in priority order. Returns
    (kept_by_section, excluded_over_budget, chars_used). Truncation for prompt
    output happens at render time; objects themselves are never mutated."""
    remaining = char_budget
    kept = {name: [] for name, _ in sections_in_priority}
    over: list[dict] = []
    policy = _policy()
    for name, items in sections_in_priority:
        for mem in items:
            cost = min(len(mem.content or ""), _PER_ITEM_CHAR_CAP)
            if cost <= remaining:
                remaining -= cost
                kept[name].append(mem)
            else:
                over.append(_excl(mem, "over budget", policy))
    return kept, over, char_budget - remaining


def _merge_keep_order(ranked, kept_subset):
    """Return ``kept_subset`` members in the order they appear in ``ranked``."""
    kept_ids = {m.id for m in kept_subset}
    return [m for m in ranked if m.id in kept_ids]


def _summarize_document(doc: DocumentContext,
                        policy: MemoryWriterPolicy) -> str:
    lines = []
    if doc.current_mode:
        lines.append(f"Mode: {doc.current_mode}")
    if doc.active_section:
        lines.append(f"Section: {doc.active_section}")
    if doc.selected_unit_id:
        lines.append(f"Unit: {doc.selected_unit_id}")
    if doc.selected_block_id:
        lines.append(f"Block: {doc.selected_block_id}")
    if doc.active_entities:
        lines.append("Entities: " + ", ".join(doc.active_entities))
    excerpt = doc.selected_excerpt or doc.document_text
    if excerpt:
        lines.append("Excerpt: "
                     + _safe_content(excerpt, policy)[:_EXCERPT_CAP])
    return "\n".join(lines)


# ============================================================ Phase-2 placeholder
class MemoryCandidateExtractor:
    """Turns a session/event into proposed memory candidates.

    Phase 2 placeholder: **returns an empty list**, calls no model, writes no
    memory. The real heuristic extractor lives in
    `logosforge.memory_arch.candidates` (Phase 4); this stub is intentionally
    left untouched so the two never collide."""

    def extract_candidates(self, session_or_event,
                           context=None) -> list[MemoryObject]:
        return []
