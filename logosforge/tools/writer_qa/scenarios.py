"""Writer QA scenario matrix — section × writing mode × action × target ×
provider-response, each with the EXPECTED system behavior (output kind,
validator status, apply allowance). A scenario "fails" (produces a bug) only
when the system's actual behavior diverges from the expected safe behavior.
"""

from __future__ import annotations

from dataclasses import dataclass

from logosforge.assistant_contract import (
    ANALYSIS, ANSWER, CLARIFICATION, CODEX, DIRECT_CONTENT, NOTES, STRUCTURE,
    SUGGESTIONS, TIMELINE, TRANSCRIPT,
)

_VALID_BY_MODE = {
    "novel": "valid_novel_prose",
    "screenplay": "valid_screenplay_dialogue",
    "graphic_novel": "valid_graphic_novel_panel",
    "stage_script": "valid_stage_script_dialogue",
    "series": "valid_series_scene",
}


@dataclass(frozen=True)
class Scenario:
    name: str
    area: str
    section: str
    writing_mode: str
    action: str
    target: str
    instruction: str
    provider_profile: str
    expected_output_kind: str
    expected_status: str          # "valid" | "invalid"
    expected_apply: bool
    expect_clarification: bool = False
    entry_point: str = "assistant_panel"
    severity: str = "HIGH"        # severity if this scenario fails


def _direct(mode, action, instruction, persona="Writer"):
    """Valid direct-content scenario for a writing mode + action."""
    return Scenario(
        name=f"{mode}.manuscript.{action}.valid",
        area="Assistant", section="Manuscript", writing_mode=mode,
        action=action, target="current_scene", instruction=instruction,
        provider_profile=_VALID_BY_MODE[mode],
        expected_output_kind=DIRECT_CONTENT, expected_status="valid",
        expected_apply=True, severity="HIGH")


def _bad(mode, profile, name, severity="BLOCKER"):
    """A bad provider output that MUST be blocked (invalid, not applyable)."""
    return Scenario(
        name=f"{mode}.manuscript.dialogue.{name}",
        area="Validator", section="Manuscript", writing_mode=mode,
        action="Dialogue", target="current_scene",
        instruction="continue the dialogue", provider_profile=profile,
        expected_output_kind=DIRECT_CONTENT, expected_status="invalid",
        expected_apply=False, severity=severity)


def core_scenarios() -> list[Scenario]:
    s: list[Scenario] = []

    # A-E. Direct manuscript writing across all five modes (valid outputs).
    for mode in ("novel", "screenplay", "graphic_novel", "stage_script",
                 "series"):
        s.append(_direct(mode, "generate", "write the next beat"))
        s.append(_direct(mode, "rewrite", "rewrite the selected passage"))
        s.append(_direct(mode, "expand", "expand this moment"))
        s.append(_direct(mode, "Dialogue", "continue the dialogue"))
        # Bad outputs that must be blocked.
        s.append(_bad(mode, "invalid_planning_markdown", "planning_blocked"))
        s.append(_bad(mode, "invalid_context_dump", "context_dump_blocked"))
        s.append(_bad(mode, "invalid_meta_reasoning", "meta_blocked"))
        # Wrong-mode + empty outputs SHOULD be blocked too (surfaces gaps).
        s.append(_bad(mode, "invalid_wrong_mode", "wrong_mode", "BLOCKER"))
        s.append(_bad(mode, "invalid_empty", "empty", "HIGH"))
        # provider error must be handled gracefully.
        s.append(Scenario(
            name=f"{mode}.manuscript.generate.provider_error",
            area="Assistant", section="Manuscript", writing_mode=mode,
            action="generate", target="current_scene",
            instruction="write the next beat", provider_profile="provider_error",
            expected_output_kind=DIRECT_CONTENT, expected_status="valid",
            expected_apply=True, severity="HIGH"))

    # Suggest (Manuscript) — valid suggestions, NOT directly applyable.
    s.append(Scenario(
        name="novel.manuscript.suggest.valid", area="Assistant",
        section="Manuscript", writing_mode="novel", action="suggest",
        target="current_scene", instruction="suggest sharper beats",
        provider_profile="valid_note_summary",
        expected_output_kind=SUGGESTIONS, expected_status="valid",
        expected_apply=False, severity="MEDIUM"))

    # F. Outline — structure allowed; direct prose not produced.
    for action in ("generate", "expand", "rewrite"):
        s.append(Scenario(
            name=f"outline.{action}.structure", area="Outline",
            section="Outline", writing_mode="novel", action=action,
            target="current_outline_node", instruction="structure the act",
            provider_profile="valid_outline_structure",
            expected_output_kind=STRUCTURE, expected_status="valid",
            expected_apply=False, severity="MEDIUM"))

    # G. Notes — note operations, not manuscript.
    for action, instr in (("summarize", "summarize these notes"),
                          ("extract", "extract tasks"),
                          ("convert", "turn notes into an outline")):
        s.append(Scenario(
            name=f"notes.{action}", area="Notes", section="Notes",
            writing_mode="novel", action=action, target="current_note",
            instruction=instr, provider_profile="valid_note_summary",
            expected_output_kind=NOTES, expected_status="valid",
            expected_apply=False, severity="MEDIUM"))

    # H. PSYKE — codex/entity content.
    for instr in ("create a character profile", "create a location",
                  "extract the relationship"):
        s.append(Scenario(
            name=f"psyke.generate.{instr.split()[1]}", area="PSYKE",
            section="PSYKE", writing_mode="novel", action="generate",
            target="current_psyke_entity", instruction=instr,
            provider_profile="valid_psyke_entity",
            expected_output_kind=CODEX, expected_status="valid",
            expected_apply=False, severity="MEDIUM"))

    # I. Timeline — timeline operations.
    for instr in ("add a timeline event", "check continuity",
                  "reorder the sequence"):
        s.append(Scenario(
            name=f"timeline.{instr.split()[0]}", area="Timeline",
            section="Timeline", writing_mode="novel", action="generate",
            target="current_timeline_item", instruction=instr,
            provider_profile="valid_note_summary",
            expected_output_kind=TIMELINE, expected_status="valid",
            expected_apply=False, severity="MEDIUM"))

    # J. Chat — project-aware intent routing.
    s.append(Scenario(
        name="chat.continue.direct", area="Chat", section="Chat",
        writing_mode="screenplay", action="ask",
        target="current_scene", instruction="continue this scene",
        provider_profile="valid_screenplay_dialogue",
        expected_output_kind=DIRECT_CONTENT, expected_status="valid",
        expected_apply=True, entry_point="chat", severity="HIGH"))
    s.append(Scenario(
        name="chat.structure", area="Chat", section="Chat",
        writing_mode="novel", action="ask", target="project",
        instruction="give me the structure of act two",
        provider_profile="valid_outline_structure",
        expected_output_kind=STRUCTURE, expected_status="valid",
        expected_apply=False, entry_point="chat", severity="MEDIUM"))
    s.append(Scenario(
        name="chat.analysis", area="Chat", section="Chat",
        writing_mode="novel", action="ask", target="current_scene",
        instruction="analyze the pacing of this scene",
        provider_profile="valid_note_summary",
        expected_output_kind=ANALYSIS, expected_status="valid",
        expected_apply=False, entry_point="chat", severity="MEDIUM"))
    s.append(Scenario(
        name="chat.no_context.clarify", area="Chat", section="Chat",
        writing_mode="novel", action="ask", target="no_target",
        instruction="continue the scene", provider_profile="valid_novel_prose",
        expected_output_kind=CLARIFICATION, expected_status="valid",
        expected_apply=False, expect_clarification=False, entry_point="chat",
        severity="MEDIUM"))

    # K. Dexter text — transcript handling (never raw audio).
    s.append(Scenario(
        name="dexter.format_transcript", area="Dexter", section="Dexter",
        writing_mode="novel", action="format", target="whole_document",
        instruction="format this transcript", provider_profile="valid_novel_prose",
        expected_output_kind=TRANSCRIPT, expected_status="valid",
        expected_apply=False, entry_point="dexter_text", severity="MEDIUM"))

    # M. Missing target for a direct-writing request → clarification.
    s.append(Scenario(
        name="screenplay.manuscript.dialogue.no_target", area="Assistant",
        section="Manuscript", writing_mode="screenplay", action="Dialogue",
        target="no_target", instruction="continue the dialogue",
        provider_profile="valid_screenplay_dialogue",
        expected_output_kind=CLARIFICATION, expected_status="valid",
        expected_apply=False, expect_clarification=True, severity="MEDIUM"))

    return s


def get_suite(name: str) -> list[Scenario]:
    name = (name or "all").lower()
    alls = core_scenarios()
    if name in ("all", "alpha"):
        return alls
    if name == "assistant":
        return [x for x in alls if x.section in ("Manuscript", "Chat")]
    if name == "manuscript":
        return [x for x in alls if x.section == "Manuscript"]
    if name in ("outline", "notes", "psyke", "timeline", "chat", "dexter"):
        return [x for x in alls if x.section.lower() == name]
    return alls
