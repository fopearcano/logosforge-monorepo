"""PSYKE detail field schemas per entry type."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FieldSpec:
    key: str
    label: str
    widget: str  # "line" | "multiline" | "combo"
    max_chars: int = 300
    options: tuple[str, ...] = ()
    section: str = ""


_SCHEMAS: dict[str, list[FieldSpec]] = {
    "character": [
        # Identity
        FieldSpec("full_name", "Full Name", "line", 200, section="Identity"),
        FieldSpec("aliases_detail", "Nicknames / Titles", "line", 200, section="Identity"),
        FieldSpec("age", "Age", "line", 50, section="Identity"),
        FieldSpec("gender", "Gender", "line", 80, section="Identity"),
        FieldSpec("role", "Role", "combo", options=(
            "", "Protagonist", "Antagonist", "Deuteragonist", "Mentor",
            "Sidekick", "Love Interest", "Foil", "Confidant",
            "Herald", "Trickster", "Guardian", "Shadow", "Minor",
        ), section="Identity"),
        FieldSpec("archetype", "Archetype", "line", 150, section="Identity"),
        # Appearance
        FieldSpec("appearance", "Physical Appearance", "multiline", 500, section="Appearance"),
        FieldSpec("distinguishing", "Distinguishing Features", "multiline", 300, section="Appearance"),
        FieldSpec("style", "Clothing / Style", "multiline", 300, section="Appearance"),
        # Psychology
        FieldSpec("personality", "Personality", "multiline", 500, section="Psychology"),
        FieldSpec("strengths", "Strengths", "multiline", 300, section="Psychology"),
        FieldSpec("flaws", "Flaws / Weaknesses", "multiline", 300, section="Psychology"),
        FieldSpec("fears", "Fears", "multiline", 300, section="Psychology"),
        FieldSpec("desires", "Desires / Wants", "multiline", 300, section="Psychology"),
        FieldSpec("needs", "Needs (internal)", "multiline", 300, section="Psychology"),
        FieldSpec("misbelief", "Lie / Misbelief", "multiline", 300, section="Psychology"),
        # Background
        FieldSpec("background", "Backstory", "multiline", 800, section="Background"),
        FieldSpec("occupation", "Occupation", "line", 150, section="Background"),
        FieldSpec("skills", "Skills / Abilities", "multiline", 300, section="Background"),
        FieldSpec("relationships", "Key Relationships", "multiline", 500, section="Background"),
        # Voice & Arc
        FieldSpec("voice", "Speech Pattern / Voice", "multiline", 400, section="Voice & Arc"),
        FieldSpec("mannerisms", "Mannerisms / Habits", "multiline", 300, section="Voice & Arc"),
        FieldSpec("arc", "Character Arc", "multiline", 500, section="Voice & Arc"),
        FieldSpec("goals", "Story Goals", "multiline", 400, section="Voice & Arc"),
        # Screenplay — cinematic and performative data
        FieldSpec("spoken_voice", "Spoken Voice", "multiline", 400, section="Screenplay"),
        FieldSpec("gesture_vocabulary", "Gesture Vocabulary", "multiline", 400, section="Screenplay"),
        FieldSpec("silence_pattern", "Silence Pattern", "multiline", 300, section="Screenplay"),
        FieldSpec("performance_mask", "Performance Mask", "multiline", 400, section="Screenplay"),
        FieldSpec("subtext_strategy", "Subtext Strategy", "multiline", 400, section="Screenplay"),
        FieldSpec("physical_behavior", "Physical Behavior", "multiline", 400, section="Screenplay"),
    ],
    "place": [
        # Geography
        FieldSpec("type", "Type", "combo", options=(
            "", "City", "Town", "Village", "Building", "Room", "Landscape",
            "Region", "Country", "Continent", "Planet", "Realm",
            "Wilderness", "Underground", "Underwater", "Airborne", "Virtual",
        ), section="Geography"),
        FieldSpec("location", "Location / Region", "line", 200, section="Geography"),
        FieldSpec("climate", "Climate / Weather", "line", 200, section="Geography"),
        FieldSpec("terrain", "Terrain / Geography", "multiline", 300, section="Geography"),
        FieldSpec("size", "Scale / Size", "line", 100, section="Geography"),
        # Sensory
        FieldSpec("appearance", "Visual Description", "multiline", 500, section="Sensory"),
        FieldSpec("sounds", "Sounds", "multiline", 200, section="Sensory"),
        FieldSpec("smells", "Smells", "multiline", 200, section="Sensory"),
        FieldSpec("atmosphere", "Atmosphere / Mood", "multiline", 400, section="Sensory"),
        # Society
        FieldSpec("population", "Population / Inhabitants", "multiline", 300, section="Society"),
        FieldSpec("culture", "Culture / Customs", "multiline", 400, section="Society"),
        FieldSpec("politics", "Government / Politics", "multiline", 400, section="Society"),
        FieldSpec("economy", "Economy / Resources", "multiline", 300, section="Society"),
        FieldSpec("religion", "Religion / Beliefs", "multiline", 300, section="Society"),
        # History & Narrative
        FieldSpec("history", "History", "multiline", 500, section="History & Narrative"),
        FieldSpec("landmarks", "Landmarks / Key Features", "multiline", 400, section="History & Narrative"),
        FieldSpec("secrets", "Secrets / Hidden Aspects", "multiline", 400, section="History & Narrative"),
        FieldSpec("significance", "Story Significance", "multiline", 300, section="History & Narrative"),
        FieldSpec("conflicts", "Conflicts / Tensions", "multiline", 300, section="History & Narrative"),
    ],
    "object": [
        # Physical
        FieldSpec("type", "Type", "combo", options=(
            "", "Weapon", "Armor", "Tool", "Artifact", "Document",
            "Vehicle", "Technology", "Jewelry", "Clothing", "Container",
            "Key / Lock", "Currency", "Food / Drink", "Medicine", "Other",
        ), section="Physical"),
        FieldSpec("appearance", "Appearance", "multiline", 400, section="Physical"),
        FieldSpec("material", "Material / Composition", "line", 200, section="Physical"),
        FieldSpec("size_weight", "Size / Weight", "line", 150, section="Physical"),
        FieldSpec("condition", "Condition", "line", 150, section="Physical"),
        # Properties
        FieldSpec("function", "Function / Purpose", "multiline", 400, section="Properties"),
        FieldSpec("powers", "Powers / Special Properties", "multiline", 400, section="Properties"),
        FieldSpec("limitations", "Limitations / Costs", "multiline", 300, section="Properties"),
        FieldSpec("activation", "How It Works / Activation", "multiline", 300, section="Properties"),
        # Provenance
        FieldSpec("origin", "Origin / Creator", "multiline", 300, section="Provenance"),
        FieldSpec("history", "History / Previous Owners", "multiline", 500, section="Provenance"),
        FieldSpec("current_owner", "Current Owner / Location", "line", 200, section="Provenance"),
        FieldSpec("significance", "Story Significance", "multiline", 300, section="Provenance"),
        FieldSpec("symbolism", "Symbolic Meaning", "multiline", 300, section="Provenance"),
    ],
    "lore": [
        # Core
        FieldSpec("category", "Category", "combo", options=(
            "", "Magic System", "Technology", "Religion", "Mythology",
            "History", "Language", "Law", "Science", "Prophecy",
            "Custom / Ritual", "Organization", "Species / Race",
            "Calendar / Time", "Cosmology", "Economy", "Other",
        ), section="Core"),
        FieldSpec("summary", "Summary", "multiline", 600, section="Core"),
        FieldSpec("scope", "Scope / Reach", "line", 200, section="Core"),
        # Rules & Structure
        FieldSpec("rules", "Rules / Laws", "multiline", 600, section="Rules & Structure"),
        FieldSpec("costs", "Costs / Limitations", "multiline", 400, section="Rules & Structure"),
        FieldSpec("hierarchy", "Hierarchy / Structure", "multiline", 400, section="Rules & Structure"),
        FieldSpec("exceptions", "Exceptions / Edge Cases", "multiline", 400, section="Rules & Structure"),
        # Context
        FieldSpec("history", "Historical Origin", "multiline", 500, section="Context"),
        FieldSpec("public_knowledge", "Common Knowledge", "multiline", 400, section="Context"),
        FieldSpec("secrets", "Hidden Truths", "multiline", 400, section="Context"),
        FieldSpec("impact", "Impact on Society", "multiline", 400, section="Context"),
        FieldSpec("conflicts", "Conflicts / Contradictions", "multiline", 300, section="Context"),
        FieldSpec("foreshadowing", "Foreshadowing Opportunities", "multiline", 300, section="Context"),
    ],
    "theme": [
        # Thesis
        FieldSpec("statement", "Thematic Statement", "multiline", 300, section="Thesis"),
        FieldSpec("question", "Central Question", "multiline", 300, section="Thesis"),
        FieldSpec("argument", "Argument / Position", "combo", options=(
            "", "Affirmed", "Denied", "Ambiguous", "Explored",
        ), section="Thesis"),
        # Exploration
        FieldSpec("positive", "Positive Manifestation", "multiline", 400, section="Exploration"),
        FieldSpec("negative", "Negative Manifestation", "multiline", 400, section="Exploration"),
        FieldSpec("contrary", "Contrary / Gray Area", "multiline", 400, section="Exploration"),
        FieldSpec("symbols", "Symbols / Motifs", "multiline", 400, section="Exploration"),
        FieldSpec("dialogue_hooks", "Dialogue Hooks", "multiline", 400, section="Exploration"),
        # Characters & Plot
        FieldSpec("protagonist_relation", "Protagonist's Relationship", "multiline", 400, section="Characters & Plot"),
        FieldSpec("antagonist_relation", "Antagonist's Relationship", "multiline", 400, section="Characters & Plot"),
        FieldSpec("subplots", "Subplot Connections", "multiline", 400, section="Characters & Plot"),
        FieldSpec("arc_integration", "How Theme Evolves in Story", "multiline", 500, section="Characters & Plot"),
    ],
    "other": [
        FieldSpec("category", "Category", "line", 150, section=""),
        FieldSpec("summary", "Summary", "multiline", 600, section=""),
        FieldSpec("details", "Details", "multiline", 800, section=""),
        FieldSpec("references", "References / Connections", "multiline", 400, section=""),
    ],
}


def get_detail_schema(entry_type: str) -> list[FieldSpec]:
    return _SCHEMAS.get(entry_type, [])


# Graphic Novel visual-memory fields, shown as a "Visual Memory" group when
# the project's narrative engine is graphic_novel. These are persisted in the
# nested details_json["visual"] section (NOT as flat detail keys), so they are
# read/written via db.get/set_psyke_visual_memory — keeping them distinct from
# the standard flat detail fields above.
_VISUAL_LABELS: dict[str, str] = {
    # character
    "silhouette": "Silhouette",
    "shape_language": "Shape Language",
    "color_identity": "Color Identity",
    "costume_state": "Costume State",
    "pose_language": "Pose Language",
    "gesture_vocabulary": "Gesture Vocabulary",
    "facial_expression_range": "Facial Expression Range",
    "visual_symbolism": "Visual Symbolism",
    # place
    "architecture": "Architecture",
    "lighting_mood": "Lighting / Mood",
    "color_palette": "Color Palette",
    "environmental_motifs": "Environmental Motifs",
    "recurring_camera_angles": "Recurring Camera Angles",
    "spatial_continuity_notes": "Spatial Continuity Notes",
    "recurring_objects": "Recurring Objects",
    # object
    "appearance": "Appearance",
    "scale": "Scale",
    "owner": "Owner",
    "continuity_state": "Continuity State",
    "symbolic_meaning": "Symbolic Meaning",
    "first_appearance": "First Appearance",
    "recurring_use": "Recurring Use",
    # theme
    "visual_manifestations": "Visual Manifestations",
    "symbolic_colors": "Symbolic Colors",
    "recurring_shapes": "Recurring Shapes",
    "motif_family": "Motif Family",
    # lore
    "visual_rules": "Visual Rules",
    "design_constraints": "Design Constraints",
    "world_style_notes": "World Style Notes",
}


def get_visual_schema(entry_type: str) -> list[FieldSpec]:
    """Visual Memory FieldSpecs for *entry_type* (empty when none apply).

    Keys mirror logosforge.psyke_visual.visual_fields_for_type and are
    stored under details_json["visual"].
    """
    from logosforge.psyke_visual import visual_fields_for_type
    return [
        FieldSpec(
            key, _VISUAL_LABELS.get(key, key.replace("_", " ").title()),
            "multiline", 300, section="Visual Memory",
        )
        for key in visual_fields_for_type(entry_type)
    ]
