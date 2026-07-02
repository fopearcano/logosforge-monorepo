"""Graphic Novel — AI / ComfyUI image-prompt export hooks.

Prepares structured visual-generation packets from Page/Panel data + PSYKE
visual memory + a project style profile. This module ONLY builds and
serializes prompt packages; it does NOT generate images. The
``send_to_comfyui`` boundary is a disabled stub until a real connector
exists.

Pure core/app logic: no UI, no Tauri, no filesystem, no network.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any

from logosforge.psyke_visual import _entry_names


# ---------------------------------------------------------------------------
# Style profile (§7) — stored in project settings under "gn_style".
# ---------------------------------------------------------------------------

_DEFAULT_STYLE: dict[str, str] = {
    "art_style": "",
    "linework": "",
    "color_palette": "",
    "rendering_style": "",
    "aspect_ratio": "",
    "panel_consistency_notes": "",
    "negative_prompt_defaults": "",
}


def get_gn_style_profile(db: Any, project_id: int) -> dict:
    """Project's Graphic Novel style profile (defaults merged in)."""
    settings = {}
    try:
        settings = db.get_project_settings(project_id) or {}
    except Exception:
        settings = {}
    stored = settings.get("gn_style")
    profile = dict(_DEFAULT_STYLE)
    if isinstance(stored, dict):
        for k in _DEFAULT_STYLE:
            if stored.get(k):
                profile[k] = stored[k]
    return profile


def set_gn_style_profile(db: Any, project_id: int, profile: dict) -> None:
    """Persist the GN style profile into project settings (merges keys)."""
    settings = {}
    try:
        settings = db.get_project_settings(project_id) or {}
    except Exception:
        settings = {}
    current = settings.get("gn_style")
    current = dict(current) if isinstance(current, dict) else {}
    for k, v in (profile or {}).items():
        if k in _DEFAULT_STYLE:
            current[k] = v
    settings["gn_style"] = current
    db.save_project_settings(project_id, settings)


# ---------------------------------------------------------------------------
# Prompt package model (§2)
# ---------------------------------------------------------------------------

@dataclass
class GraphicNovelPromptPackage:
    """A structured, serializable image-generation packet for one panel."""

    project_id: int
    page_id: int
    panel_id: int
    issue_id: int | None = None
    prompt: str = ""
    negative_prompt: str = ""
    characters: list[dict] = field(default_factory=list)
    locations: list[dict] = field(default_factory=list)
    objects: list[dict] = field(default_factory=list)
    visual_motifs: list[str] = field(default_factory=list)
    style_notes: str = ""
    continuity_notes: str = ""
    camera_angle: str = ""
    shot_type: str = ""
    emotional_tone: str = ""
    output_preset: str = ""
    warnings: list[str] = field(default_factory=list)
    metadata_json: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# PSYKE matching (name/alias, no hard FKs — reuses psyke_visual)
# ---------------------------------------------------------------------------

def _psyke_index(db: Any, project_id: int) -> dict:
    """lowercased name/alias -> (entry, visual_memory_dict)."""
    index: dict = {}
    for entry in db.get_all_psyke_entries(project_id):
        try:
            visual = db.get_psyke_visual_memory(entry.id) or {}
        except Exception:
            visual = {}
        for name in _entry_names(db, entry):
            index.setdefault(name, (entry, visual))
    return index


def _visual_descriptor(visual: dict, keys: tuple[str, ...]) -> str:
    bits = [str(visual[k]) for k in keys if visual.get(k)]
    return ", ".join(bits)


# ---------------------------------------------------------------------------
# Panel prompt builder (§3)
# ---------------------------------------------------------------------------

# How many characters in a single panel reads as crowded.
_CROWDED_PANEL = 4


def build_gn_panel_prompt_package(
    db: Any, project_id: int, panel_id: int,
) -> GraphicNovelPromptPackage | None:
    """Combine Panel + Page + PSYKE visual memory + style into a package."""
    panel = db.get_gn_panel_by_id(panel_id)
    if panel is None:
        return None
    page = db.get_gn_page_by_id(panel.page_id)
    style = get_gn_style_profile(db, project_id)
    index = _psyke_index(db, project_id)

    pkg = GraphicNovelPromptPackage(
        project_id=project_id, page_id=panel.page_id, panel_id=panel_id,
        issue_id=getattr(page, "issue_id", None) if page else None,
        camera_angle=panel.camera_angle or "",
        shot_type=panel.shot_type or "",
        emotional_tone=panel.emotional_tone or "",
        visual_motifs=db.csv_split(panel.visual_motifs),
    )

    warnings: list[str] = []

    # Characters — match PSYKE for visual identity / costume.
    char_names = db.csv_split(panel.characters_present)
    if len(char_names) > _CROWDED_PANEL:
        warnings.append(
            f"{len(char_names)} characters in one panel — consider splitting."
        )
    for name in char_names:
        match = index.get(name.strip().lower())
        if match and (match[0].entry_type or "").lower() == "character":
            visual = match[1]
            pkg.characters.append({
                "name": name,
                "visual_identity": _visual_descriptor(visual, (
                    "silhouette", "shape_language", "color_identity",
                    "visual_symbolism",
                )),
                "costume_state": visual.get("costume_state", ""),
            })
            if not visual:
                warnings.append(
                    f"Character '{name}' has no PSYKE visual identity."
                )
        else:
            pkg.characters.append({"name": name, "visual_identity": "",
                                   "costume_state": ""})
            warnings.append(f"Character '{name}' is not defined in PSYKE.")

    # Locations — any matched place entries referenced via motifs/characters
    # are out of scope; we surface explicit location entries that match a
    # motif token, plus warn when no location design exists at all.
    for motif in pkg.visual_motifs:
        match = index.get(motif.strip().lower())
        if not match:
            warnings.append(f"Motif '{motif}' is not defined in PSYKE.")
            continue
        entry, visual = match
        etype = (entry.entry_type or "").lower()
        if etype == "place":
            pkg.locations.append({
                "name": entry.name,
                "design": _visual_descriptor(visual, (
                    "architecture", "lighting_mood", "color_palette",
                    "environmental_motifs",
                )),
            })
        elif etype == "object":
            pkg.objects.append({
                "name": entry.name,
                "appearance": visual.get("appearance", ""),
                "continuity_state": visual.get("continuity_state", ""),
                "symbolic_meaning": visual.get("symbolic_meaning", ""),
            })

    # Page-level context.
    if page is not None:
        if (page.emotional_beat or "").strip():
            pkg.metadata_json["page_emotional_beat"] = page.emotional_beat
        if (page.density_level or "").strip():
            pkg.metadata_json["page_density"] = page.density_level
        if (page.reveal_type or "").strip():
            pkg.metadata_json["page_reveal"] = page.reveal_type
        pkg.metadata_json["page_number"] = page.page_number
    pkg.metadata_json["panel_number"] = panel.panel_number

    # Style + continuity.
    style_bits = [v for k, v in style.items()
                  if k != "negative_prompt_defaults" and v]
    pkg.style_notes = "; ".join(style_bits)
    pkg.output_preset = style.get("aspect_ratio", "")
    pkg.negative_prompt = style.get("negative_prompt_defaults", "")
    if style.get("panel_consistency_notes"):
        pkg.continuity_notes = style["panel_consistency_notes"]

    # Compose the positive prompt text from the structured parts.
    pkg.prompt = _compose_prompt(panel, page, pkg)

    # Guardrails (§8) — warnings only, never block.
    if not (panel.description or "").strip() and not (panel.action or "").strip():
        warnings.append("Panel has no description or action.")
    if not (panel.shot_type or "").strip():
        warnings.append("Panel has no shot type.")
    if not (panel.camera_angle or "").strip():
        warnings.append("Panel has no camera angle.")
    if not pkg.locations:
        warnings.append("No location visual design referenced for this panel.")

    pkg.warnings = warnings
    pkg.metadata_json["warning_count"] = len(warnings)
    return pkg


def _compose_prompt(panel: Any, page: Any, pkg: GraphicNovelPromptPackage) -> str:
    parts: list[str] = []
    desc = (panel.description or "").strip()
    action = (panel.action or "").strip()
    if desc:
        parts.append(desc)
    if action:
        parts.append(action)
    if pkg.shot_type:
        parts.append(f"{pkg.shot_type} shot")
    if pkg.camera_angle:
        parts.append(f"{pkg.camera_angle} angle")
    for c in pkg.characters:
        if c["visual_identity"]:
            parts.append(f"{c['name']} ({c['visual_identity']})")
        else:
            parts.append(c["name"])
    for loc in pkg.locations:
        if loc["design"]:
            parts.append(f"setting: {loc['design']}")
    if pkg.emotional_tone:
        parts.append(f"tone: {pkg.emotional_tone}")
    if pkg.visual_motifs:
        parts.append("motifs: " + ", ".join(pkg.visual_motifs))
    if pkg.style_notes:
        parts.append(pkg.style_notes)
    return ", ".join(p for p in parts if p)


# ---------------------------------------------------------------------------
# Page prompt pack (§4)
# ---------------------------------------------------------------------------

def build_gn_page_prompt_packages(
    db: Any, project_id: int, page_id: int,
) -> list[GraphicNovelPromptPackage]:
    """Per-panel packages for a page, in panel order (not merged)."""
    out: list[GraphicNovelPromptPackage] = []
    for panel in db.get_gn_panels_for_page(page_id):
        pkg = build_gn_panel_prompt_package(db, project_id, panel.id)
        if pkg is not None:
            out.append(pkg)
    return out


# ---------------------------------------------------------------------------
# Export formats (§5)
# ---------------------------------------------------------------------------

def package_to_json(
    package: GraphicNovelPromptPackage | list[GraphicNovelPromptPackage],
) -> str:
    """Machine-readable JSON for one package or a list of packages."""
    if isinstance(package, list):
        data = [p.to_dict() for p in package]
    else:
        data = package.to_dict()
    return json.dumps(data, indent=2, ensure_ascii=False)


def _one_markdown(pkg: GraphicNovelPromptPackage) -> list[str]:
    lines = [
        f"### Page {pkg.metadata_json.get('page_number', '?')} "
        f"Panel {pkg.metadata_json.get('panel_number', '?')}",
        "",
        f"**Prompt:** {pkg.prompt}",
    ]
    if pkg.negative_prompt:
        lines.append(f"**Negative:** {pkg.negative_prompt}")
    if pkg.shot_type or pkg.camera_angle:
        lines.append(f"**Framing:** {pkg.shot_type} / {pkg.camera_angle}".strip(" /"))
    if pkg.characters:
        names = ", ".join(c["name"] for c in pkg.characters)
        lines.append(f"**Characters:** {names}")
    if pkg.visual_motifs:
        lines.append(f"**Motifs:** {', '.join(pkg.visual_motifs)}")
    if pkg.continuity_notes:
        lines.append(f"**Continuity:** {pkg.continuity_notes}")
    if pkg.warnings:
        lines.append("**Warnings:**")
        lines.extend(f"- {w}" for w in pkg.warnings)
    lines.append("")
    return lines


def package_to_markdown(
    package: GraphicNovelPromptPackage | list[GraphicNovelPromptPackage],
) -> str:
    """Human-readable Markdown prompt sheet."""
    packages = package if isinstance(package, list) else [package]
    lines = ["# Graphic Novel Image Prompt Sheet", ""]
    for pkg in packages:
        lines.extend(_one_markdown(pkg))
    return "\n".join(lines).rstrip() + "\n"


# ---------------------------------------------------------------------------
# ComfyUI hook boundary (§9) — stub, no network.
# ---------------------------------------------------------------------------

def comfyui_available() -> bool:
    """Whether a real ComfyUI connector is wired. Always False this slice."""
    return False


def send_to_comfyui(package: GraphicNovelPromptPackage) -> None:
    """Integration boundary for a future ComfyUI connector.

    Intentionally disabled this slice — no network calls. A real connector
    would translate the package into a ComfyUI workflow and submit it.
    """
    raise NotImplementedError(
        "ComfyUI integration is not enabled. This slice only prepares and "
        "exports prompt packages; wire a connector to enable generation."
    )


# ---------------------------------------------------------------------------
# Assistant hook (§10) — reuses the builders, no duplicated logic.
# ---------------------------------------------------------------------------

def assistant_panel_prompt(db: Any, project_id: int, panel_id: int) -> str:
    """Answer 'create an image prompt for this panel' (Markdown sheet)."""
    pkg = build_gn_panel_prompt_package(db, project_id, panel_id)
    if pkg is None:
        return "No such panel."
    return package_to_markdown(pkg)


def assistant_page_prompts(db: Any, project_id: int, page_id: int) -> str:
    """Answer 'export prompts for this page' (Markdown sheet, panels in order)."""
    pkgs = build_gn_page_prompt_packages(db, project_id, page_id)
    if not pkgs:
        return "No panels on this page."
    return package_to_markdown(pkgs)


def assistant_missing_visual_data(db: Any, project_id: int, panel_id: int) -> str:
    """Answer 'what visual data is missing before generating this panel?'."""
    pkg = build_gn_panel_prompt_package(db, project_id, panel_id)
    if pkg is None:
        return "No such panel."
    if not pkg.warnings:
        return "This panel has the visual data needed to generate an image."
    return "Missing / risky before generating this panel:\n" + "\n".join(
        f"- {w}" for w in pkg.warnings
    )
