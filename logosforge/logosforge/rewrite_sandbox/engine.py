"""Adaptive Rewrite Sandbox engine (Phase 10L).

Generates, scores and (only on explicit confirmation) applies rewrite variants.
Canonical project content is NEVER changed during generation — mutation happens
only in :func:`apply_rewrite_variant` with ``confirm=True`` and a stale-source
guard. Rides the single shared Assistant backend via an injectable ``chat_fn``
(defaults to ``assistant.chat_completion`` — no new provider layer).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from logosforge.rewrite_sandbox.prompt_builder import build_rewrite_prompt
from logosforge.rewrite_sandbox.scoring import score_rewrite


def _hash(text: str) -> str:
    return hashlib.sha1((text or "").encode("utf-8")).hexdigest()[:16]


def _excerpt(text: str, n: int = 280) -> str:
    t = (text or "").strip()
    return t if len(t) <= n else t[:n] + "…"


def _default_chat_fn(messages, provider):
    from logosforge.assistant import chat_completion
    text, _cached = chat_completion(messages, provider=provider)
    return text


def _default_provider_resolver():
    from logosforge.ui.outline_ai import build_provider
    return build_provider()


@dataclass
class RewriteGenerationResult:
    ok: bool = False
    session_id: int | None = None
    variant_id: int | None = None
    variant_text: str = ""
    score: dict = field(default_factory=dict)
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"ok": self.ok, "session_id": self.session_id,
                "variant_id": self.variant_id, "variant_text": self.variant_text,
                "score": dict(self.score), "error": self.error}


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------


def _writing_mode(db, project_id: int) -> str:
    try:
        from logosforge.writing_modes import get_project_writing_mode_by_id
        return get_project_writing_mode_by_id(db, project_id)
    except Exception:
        return "novel"


def create_rewrite_session(db, project_id: int, *, source_type: str = "scene",
                           source_id: int | None = None, source_text: str = "",
                           instruction: str = "", title: str = ""):
    """Create an isolated rewrite session (no canonical mutation)."""
    return db.create_rewrite_session(
        project_id, source_type=source_type, source_id=source_id,
        writing_mode=_writing_mode(db, project_id),
        title=title or f"Rewrite: {source_type}", instruction=instruction,
        source_text_hash=_hash(source_text), source_excerpt=_excerpt(source_text),
        status="open")


# ---------------------------------------------------------------------------
# Generation (calls the shared backend; never mutates canonical content)
# ---------------------------------------------------------------------------


def generate_rewrite_variant(
    db, project_id: int, *, session_id: int, source_text: str,
    strategy_key: str = "", instruction: str = "", label: str = "",
    chat_fn: Callable[[list, object], str] | None = None,
    provider_resolver: Callable[[], object] | None = None,
    include_psyke: bool = True,
) -> RewriteGenerationResult:
    """Generate one variant via the shared backend and store it (no mutation)."""
    res = RewriteGenerationResult(session_id=session_id)
    if not (source_text or "").strip():
        res.error = "Empty source text."
        return res

    mode = _writing_mode(db, project_id)
    prompt = build_rewrite_prompt(
        db, project_id, writing_mode=mode, source_type="scene",
        source_text=source_text, user_instruction=instruction,
        strategy_key=strategy_key, include_psyke=include_psyke)

    resolver = provider_resolver or _default_provider_resolver
    chat = chat_fn or _default_chat_fn
    try:
        provider = resolver()
    except Exception:
        provider = None
    if provider is None and chat_fn is None:
        res.error = "No AI provider configured."
        return res

    provider_name = getattr(provider, "name", "") or ""
    model_name = getattr(provider, "model", "") or ""
    try:
        text = chat(prompt.messages(), provider) or ""
    except Exception as exc:
        res.error = f"Assistant request failed: {exc}"
        return res
    text = text.strip()
    if not text:
        res.error = "AI returned empty text."
        return res

    score = score_rewrite(db, project_id, source_text, text, writing_mode=mode)
    variant = db.create_rewrite_variant(
        project_id, session_id, label=label or (strategy_key or "variant"),
        strategy=strategy_key, model_provider=provider_name, model_name=model_name,
        prompt_summary=prompt.summary(), variant_text=text,
        variant_text_hash=_hash(text), score_json=json.dumps(score),
        status="candidate")
    res.ok = True
    res.variant_id = variant.id
    res.variant_text = text
    res.score = score
    return res


def generate_multiple_variants(
    db, project_id: int, *, session_id: int, source_text: str,
    strategies: list[str], instruction: str = "",
    chat_fn: Callable[[list, object], str] | None = None,
    provider_resolver: Callable[[], object] | None = None,
) -> list[RewriteGenerationResult]:
    out = []
    for i, key in enumerate(strategies):
        out.append(generate_rewrite_variant(
            db, project_id, session_id=session_id, source_text=source_text,
            strategy_key=key, instruction=instruction, label=f"V{i + 1}: {key}",
            chat_fn=chat_fn, provider_resolver=provider_resolver))
    return out


def score_rewrite_variant(db, project_id: int, variant_id: int) -> dict:
    """Re-score a stored variant against the current source (deterministic)."""
    v = db.get_rewrite_variant(variant_id)
    if v is None:
        return {}
    sess = db.get_rewrite_session(v.session_id)
    source = _current_source_text(db, sess) if sess else ""
    score = score_rewrite(db, project_id, source, v.variant_text,
                          writing_mode=(sess.writing_mode if sess else "novel"))
    db.update_rewrite_variant(variant_id, score_json=json.dumps(score))
    return score


# ---------------------------------------------------------------------------
# Apply (explicit, confirmed, stale-guarded)
# ---------------------------------------------------------------------------


def _current_source_text(db, session) -> str:
    st, sid = session.source_type, session.source_id
    try:
        if st in ("scene", "manuscript", "screenplay_block") and sid is not None:
            scene = db.get_scene_by_id(sid)
            return getattr(scene, "content", "") or ""
        if st == "outline" and sid is not None:
            node = db.get_outline_node(sid) if hasattr(db, "get_outline_node") else None
            return getattr(node, "description", "") or ""
    except Exception:
        return ""
    return ""


def is_source_stale(db, session_id: int) -> bool:
    sess = db.get_rewrite_session(session_id)
    if sess is None:
        return True
    current = _current_source_text(db, sess)
    if not current and not sess.source_excerpt:
        return False
    return _hash(current) != sess.source_text_hash


def apply_rewrite_variant(db, project_id: int, variant_id: int, *,
                          confirm: bool = False, apply_mode: str = "replace_scene",
                          force: bool = False, create_checkpoint: bool = True) -> dict:
    """Apply a variant to its source. Requires ``confirm=True``. Stale-guarded."""
    if not confirm:
        return {"ok": False, "error": "Apply requires explicit confirmation."}
    v = db.get_rewrite_variant(variant_id)
    if v is None:
        return {"ok": False, "error": "Variant not found."}
    sess = db.get_rewrite_session(v.session_id)
    if sess is None:
        return {"ok": False, "error": "Session not found."}
    if sess.source_type not in ("scene", "manuscript", "screenplay_block"):
        return {"ok": False, "error": f"Apply for '{sess.source_type}' is deferred."}
    if sess.source_id is None:
        return {"ok": False, "error": "No source id to apply to."}
    before = _current_source_text(db, sess)
    if not force and _hash(before) != sess.source_text_hash:
        return {"ok": False, "error": "Source changed since the variant was "
                "generated. Regenerate or re-apply with force=True.", "stale": True}

    # Phase 10M — route the mutation through the Controlled Apply service (diff +
    # conflict detection + checkpoint + event), preserving the 10L contract.
    from logosforge.controlled_apply.service import apply_operation
    res = apply_operation(
        db, project_id, target_type="scene", target_id=sess.source_id,
        proposed_text=v.variant_text, apply_mode="replace", confirmed=True,
        force=force, source_type="rewrite_variant", source_id=variant_id,
        create_checkpoint=create_checkpoint)
    if not res.get("ok"):
        return {"ok": False, "error": res.get("error", "Apply failed."),
                "stale": res.get("stale", False)}
    stage_id = res.get("stage_id")

    db.create_rewrite_apply_record(
        project_id, sess.id, variant_id, source_type=sess.source_type,
        source_id=sess.source_id, apply_mode=apply_mode,
        before_hash=_hash(before), after_hash=v.variant_text_hash,
        created_stage_id=stage_id)
    db.update_rewrite_variant(variant_id, status="applied")
    db.update_rewrite_session(sess.id, status="applied",
                              source_text_hash=v.variant_text_hash)
    return {"ok": True, "variant_id": variant_id, "scene_id": sess.source_id,
            "stage_id": stage_id}


def discard_session(db, session_id: int) -> None:
    db.update_rewrite_session(session_id, status="discarded")


# ---------------------------------------------------------------------------
# Status (read-only, for Assistant/Logos)
# ---------------------------------------------------------------------------


def rewrite_health_metrics(db, project_id: int) -> list:
    """Cross-mode health metrics from OPEN rewrite sessions only (capped at WATCH).

    Rejected/applied/canonical content is unaffected — open high-risk variants are
    surfaced separately. Returns [] when there is no open session.
    """
    from logosforge.logos.health import metric as M
    try:
        sess = db.get_latest_rewrite_session(project_id, status="open")
    except Exception:
        sess = None
    if sess is None:
        return []
    st = session_status(db, project_id)
    metrics = [M.NarrativeHealthMetric(
        category=M.CAT_REWRITE_CONTINUITY,
        status=(M.STATUS_WATCH if st.get("variant_count") else M.STATUS_STABLE),
        confidence=0.4,
        evidence=f"{st.get('variant_count', 0)} open rewrite variant(s) (not "
                 "applied).")]
    metrics.append(M.NarrativeHealthMetric(
        category=M.CAT_PSYKE_PRESERVATION,
        status=(M.STATUS_WATCH if st.get("psyke_terms_removed") else M.STATUS_STABLE),
        confidence=0.4,
        evidence=(f"{st['psyke_terms_removed']} PSYKE reference(s) removed across "
                  "open variants." if st.get("psyke_terms_removed")
                  else "Open variants preserve PSYKE references.")))
    metrics.append(M.NarrativeHealthMetric(
        category=M.CAT_SOURCE_STALENESS,
        status=(M.STATUS_WATCH if st.get("stale") else M.STATUS_STABLE),
        confidence=0.45,
        evidence=("Source changed since variants were generated."
                  if st.get("stale") else "Source matches the variant baseline.")))
    return metrics


def session_status(db, project_id: int) -> dict:
    sess = db.get_latest_rewrite_session(project_id, status="open")
    if sess is None:
        return {"active": False}
    variants = db.get_rewrite_variants(sess.id)
    preferred = next((v for v in variants if v.status == "preferred"), None)
    warnings = []
    if is_source_stale(db, sess.id):
        warnings.append("Source changed since variants were generated.")
    psyke_removed = 0
    for v in variants:
        try:
            psyke_removed += int(json.loads(v.score_json or "{}").get(
                "psyke_terms_removed", 0))
        except Exception:
            pass
    return {
        "active": True, "session_id": sess.id, "source_type": sess.source_type,
        "writing_mode": sess.writing_mode, "variant_count": len(variants),
        "preferred": (preferred.label if preferred else ""),
        "stale": is_source_stale(db, sess.id),
        "psyke_terms_removed": psyke_removed, "warnings": warnings,
    }
