"""Writing Modes catalog — the five project writing modes and their display data.

Project-agnostic: the catalog is static core data (``logosforge.writing_modes``),
so this route is NOT project-scoped. Frontends use it to populate a mode picker
(label, structural vocabulary, default format, medium constraints). Every value
is sourced from the core's authoritative ``writing_modes`` module — no data is
duplicated here.
"""

from __future__ import annotations

from fastapi import APIRouter

from logosforge import writing_modes as wm
from logosforge.api import schemas

router = APIRouter(tags=["writing-modes"])


@router.get("/writing-modes", response_model=schemas.WritingModesResponseDTO)
def list_writing_modes() -> schemas.WritingModesResponseDTO:
    modes = [
        schemas.WritingModeDTO(
            id=mode,
            label=wm.mode_label(mode),
            structural_units=list(wm.structural_units(mode)),
            default_writing_format=wm.default_writing_format(mode),
            medium_constraints=wm.medium_constraints(mode),
        )
        for mode in wm.ALL_MODES
    ]
    return schemas.WritingModesResponseDTO(modes=modes, default_mode=wm.DEFAULT_MODE)
