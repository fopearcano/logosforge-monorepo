"""Global assistant side panel — compact AI writing assistant."""

from collections.abc import Callable

from PySide6.QtCore import QThread, QTimer, Signal, Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from logosforge.assistant import (
    PRESET_ACTIONS,
    build_messages,
    chat_completion,
    get_configured_timeout,
)
from logosforge.counterpart import (
    DIALOGIC_MODES,
    build_counterpart_messages,
)
from logosforge.adaptive_mode import (
    AIMode,
    HealthState,
    ModeResult,
    StoryStage,
    _MODE_DESCRIPTIONS,
    compute_mode,
    mode_context_block,
)
from logosforge.context_builder import (
    gather_graph_context,
    gather_notes_context,
    gather_outline_context,
    gather_psyke_context,
    gather_scene_context,
    gather_story_memory,
)
from logosforge.irrational import build_irrational_context, reroll_seed
from logosforge.structural_intelligence import gather_structural_context
from logosforge.db import Database
from logosforge.memory_context import gather_memory_context
from logosforge.narrative_suggestions import (
    build_suggestion_messages,
    format_suggestion_debug,
)
from logosforge.orchestration import (
    format_orchestration_debug,
    orchestrate_psyke_context,
    resolve_mode,
)
from logosforge.providers import ProviderConfig
from logosforge.quantum_outliner import (
    STRUCTURE_MODES,
    OutlineMode,
    collapse_branch as quantum_collapse_branch,
    detect_weak_scenes as quantum_detect_weak_scenes,
    generate_branches as quantum_generate_branches,
    generate_outline as quantum_generate_outline,
    get_state as quantum_get_state,
    list_active_wavefunctions as quantum_list_active,
    load_state as quantum_load_state,
    reframe as quantum_reframe,
    save_state as quantum_save_state,
)
from logosforge.settings import get_manager as get_settings
from logosforge.ui import theme
from logosforge.ui.mode_strip import ModeStrip
from logosforge.ui.provider_settings import ProviderSettingsWidget
from logosforge.ui.quantum_timeline import QuantumTimelineWidget


SECTION_SYSTEM_PROMPTS: dict[str, str] = {
    "Manuscript": (
        "You are helping the user write their manuscript. Generate or edit the "
        "actual manuscript content in the project's writing-mode format "
        "(prose for Novel, screenplay format for Screenplay, panel script for "
        "Graphic Novel, stage-script format for Stage Script). Write directly in "
        "the voice of the story. NEVER output outlines, bullet points, headers, "
        "scene breakdowns, or structural analysis unless the user explicitly "
        "asks. Just write the content."
    ),
    "Outline": (
        "You are a story planning assistant. "
        "The user is building the story outline. Generate a structured outline: "
        "numbered scenes or chapters with brief descriptions of key events, "
        "turning points, and character arcs."
    ),
    "Scenes": (
        "You are a fiction writing assistant. "
        "Help the user develop individual scenes. When asked to write "
        "a scene, generate prose — narrative text with action, "
        "dialogue, and description. When asked to plan a scene, "
        "describe setting, characters, beats, and conflict."
    ),
    "Characters": (
        "You are a character development assistant. "
        "Help the user flesh out characters: personality traits, backstory, "
        "motivations, relationships, speech patterns, and arc."
    ),
    "Plot": (
        "You are a plot development assistant. "
        "Help the user structure the plot. Focus on cause and effect, "
        "escalation, stakes, subplots, and story beats."
    ),
    "Acts": (
        "You are a story structure assistant. "
        "Help the user organize the story into acts. Analyze structure, "
        "identify act breaks, midpoints, climax placement, and pacing."
    ),
    "Beats": (
        "You are a narrative beat analyst. "
        "Help the user plan and refine story beats: emotional shifts, "
        "revelations, reversals, and micro-tensions within scenes."
    ),
    "Dialogue": (
        "You are a dialogue specialist. "
        "Help the user write natural, character-appropriate dialogue "
        "with subtext, rhythm, and distinct voices."
    ),
    "Notes": (
        "You are a creative writing assistant. "
        "The user is taking notes. Help organize ideas, brainstorm, "
        "and develop raw concepts into structured story material."
    ),
    "Places": (
        "You are a worldbuilding assistant. "
        "Help the user develop locations: atmosphere, sensory details, "
        "history, significance to the plot, and mood."
    ),
    "Pacing": (
        "You are a pacing analyst. "
        "Analyze and suggest improvements to narrative pacing: rhythm, "
        "scene length, tension curves, and breathing room."
    ),
    "PSYKE": (
        "You are a story bible assistant. "
        "Help the user develop and organize their story bible: rules, "
        "lore, character facts, world details, and continuity notes."
    ),
}

SECTION_PLACEHOLDERS: dict[str, str] = {
    "Manuscript": "Describe what to write: a scene, continuation, dialogue...",
    "Outline": "Describe your story idea or ask to structure the plot...",
    "Scenes": "Describe the scene you want to develop...",
    "Characters": "Describe a character to develop or ask for suggestions...",
    "Plot": "Ask about plot structure, stakes, subplots...",
    "Acts": "Ask about act structure, turning points...",
    "Beats": "Ask about beats, emotional shifts, revelations...",
    "Notes": "Brainstorm, develop ideas, or ask questions...",
    "Places": "Describe a location to develop or ask for details...",
    "Pacing": "Ask about pacing, rhythm, scene lengths...",
    "PSYKE": "Ask about story rules, lore, continuity...",
}

_ACTION_ALIASES: dict[str, str] = {k.lower(): k for k in PRESET_ACTIONS}


def _normalize_action(key: str) -> str | None:
    """Map a user-typed action name to the canonical PRESET_ACTIONS key."""
    return _ACTION_ALIASES.get(key.lower())


class _AssistantWorker(QThread):
    completed = Signal(str, bool)
    failed = Signal(str)

    def __init__(
        self, messages: list[dict], provider: ProviderConfig,
        timeout: int = 0,
    ) -> None:
        super().__init__()
        self._messages = messages
        self._provider = provider
        self._timeout = timeout

    def run(self) -> None:
        try:
            result, from_cache = chat_completion(
                self._messages, provider=self._provider,
                timeout=self._timeout,
            )
            self.completed.emit(result, from_cache)
        except Exception as e:
            self.failed.emit(str(e))


class _QuantumWorker(QThread):
    completed = Signal(object)
    failed = Signal(str)

    def __init__(self, fn, *args, **kwargs) -> None:
        super().__init__()
        self._fn = fn
        self._args = args
        self._kwargs = kwargs

    def run(self) -> None:
        try:
            result = self._fn(*self._args, **self._kwargs)
            self.completed.emit(result)
        except Exception as e:
            self.failed.emit(str(e))


class AssistantPanel(QWidget):
    """Compact AI writing assistant — docks as a right-side panel."""

    panel_closed = Signal()
    collapse_requested = Signal()
    pin_toggled = Signal(bool)

    def __init__(
        self,
        db: Database,
        project_id: int,
        on_data_changed: Callable[[], None] | None = None,
        on_open_scene: Callable[[int], None] | None = None,
        get_active_scene_id: Callable[[], int | None] | None = None,
        get_selected_text: Callable[[], str] | None = None,
        get_active_editor: Callable[[], object | None] | None = None,
    ) -> None:
        super().__init__()
        self._db = db
        self._project_id = project_id
        self._on_data_changed = on_data_changed
        self._on_open_scene = on_open_scene
        self._get_active_scene_id = get_active_scene_id
        self._get_selected_text = get_selected_text
        self._get_active_editor = get_active_editor
        self._active_section: str = "Dashboard"
        self._worker: _AssistantWorker | None = None
        self._quantum_worker: _QuantumWorker | None = None
        self._pending_messages: list[dict] | None = None

        quantum_load_state(db, project_id)

        self._debounce_timer = QTimer()
        self._debounce_timer.setSingleShot(True)
        self._debounce_timer.setInterval(120)
        self._debounce_timer.timeout.connect(self._fire_request)

        self._overlay_mode = False
        self._typing_dimmed = False
        # Widgets whose inline stylesheet depends on the theme. Registered via
        # _t() at build time and re-applied by apply_theme() so the Assistant
        # follows an Appearance change live (no recreation / restart).
        self._themed_widgets: list = []

        self.setMinimumWidth(220)
        self.setMaximumWidth(360)
        self.setObjectName("assistantPanel")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        outer.addWidget(scroll)

        container = QWidget()
        self._layout = QVBoxLayout(container)
        self._layout.setContentsMargins(8, 6, 8, 8)
        self._layout.setSpacing(6)
        scroll.setWidget(container)

        self._build_ui()

    # -- Layout ----------------------------------------------------------------

    def _build_ui(self) -> None:
        # Header
        header = QHBoxLayout()
        header.setSpacing(4)
        title = QLabel("Assistant")
        title_font = QFont()
        title_font.setBold(True)
        title_font.setPointSize(title_font.pointSize() + 1)
        title.setFont(title_font)
        self._t(title, lambda: f"color: {theme.TEXT_PRIMARY};")
        header.addWidget(title)
        header.addStretch()

        # Pin: when pinned the dock keeps the panel docked even when space is
        # tight (content scrolls); unpinned lets it auto-hide to protect the
        # working area.
        self._pin_btn = QPushButton("\U0001F4CC")
        self._pin_btn.setCheckable(True)
        self._pin_btn.setFixedSize(24, 24)
        self._pin_btn.setFlat(True)
        self._pin_btn.setToolTip("Pin the assistant (keep docked when space is tight)")
        self._t(self._pin_btn, lambda: (
            f"QPushButton {{ color: {theme.TEXT_MUTED}; border: none; }}"
            f"QPushButton:hover {{ color: {theme.TEXT_PRIMARY}; }}"
            f"QPushButton:checked {{ color: {theme.ACCENT}; }}"
        ))
        self._pin_btn.toggled.connect(self.pin_toggled.emit)
        header.addWidget(self._pin_btn)

        # Collapse to a thin strip (keeps the assistant reachable without
        # taking working width).
        self._collapse_btn = QPushButton("\u2013")
        self._collapse_btn.setFixedSize(24, 24)
        self._collapse_btn.setFlat(True)
        self._collapse_btn.setToolTip("Collapse the assistant panel")
        self._t(self._collapse_btn, lambda: (
            f"QPushButton {{ color: {theme.TEXT_MUTED}; border: none; }}"
            f"QPushButton:hover {{ color: {theme.TEXT_PRIMARY}; }}"
        ))
        self._collapse_btn.clicked.connect(self.collapse_requested.emit)
        header.addWidget(self._collapse_btn)

        self._overlay_btn = QPushButton("\u29c9")
        self._overlay_btn.setFixedSize(24, 24)
        self._overlay_btn.setFlat(True)
        self._overlay_btn.setToolTip(
            "Undock / dock the assistant (floating overlay panel)",
        )
        self._t(self._overlay_btn, lambda: (
            f"QPushButton {{ color: {theme.TEXT_MUTED}; border: none; }}"
            f"QPushButton:hover {{ color: {theme.TEXT_PRIMARY}; }}"
        ))
        self._overlay_btn.clicked.connect(self._toggle_overlay)
        header.addWidget(self._overlay_btn)

        close_btn = QPushButton("\u2715")
        close_btn.setFixedSize(24, 24)
        close_btn.setFlat(True)
        self._t(close_btn, lambda: (
            f"QPushButton {{ color: {theme.TEXT_MUTED}; border: none; }}"
            f"QPushButton:hover {{ color: {theme.TEXT_PRIMARY}; }}"
        ))
        close_btn.clicked.connect(self.panel_closed.emit)
        header.addWidget(close_btn)
        self._layout.addLayout(header)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        self._t(sep, lambda: f"color: {theme.BORDER};")
        self._layout.addWidget(sep)

        # Panel mode selector: Assistant | Counterpart | Quantum
        self._panel_mode = "assistant"
        panel_mode_row = QHBoxLayout()
        panel_mode_row.setSpacing(4)
        self._assistant_mode_btn = QPushButton("Assistant")
        self._counterpart_mode_btn = QPushButton("Counterpart")
        self._quantum_mode_btn = QPushButton("Quantum")
        for btn, mode in (
            (self._assistant_mode_btn, "assistant"),
            (self._counterpart_mode_btn, "counterpart"),
            (self._quantum_mode_btn, "quantum"),
        ):
            btn.setCheckable(True)
            btn.clicked.connect(lambda _, m=mode: self._set_panel_mode(m))
        self._assistant_mode_btn.setChecked(True)
        self._assistant_mode_btn.setStyleSheet(self._seg_btn_style(active=True))
        self._counterpart_mode_btn.setStyleSheet(self._seg_btn_style(active=False))
        self._quantum_mode_btn.setStyleSheet(self._seg_btn_style(active=False))
        panel_mode_row.addWidget(self._assistant_mode_btn)
        panel_mode_row.addWidget(self._counterpart_mode_btn)
        panel_mode_row.addWidget(self._quantum_mode_btn)
        panel_mode_row.addStretch()
        self._layout.addLayout(panel_mode_row)

        # Mode strip
        self._mode_strip = ModeStrip(
            self._db, self._project_id,
            on_mode_changed=self._on_mode_override,
        )
        self._layout.addWidget(self._mode_strip)

        # Context source selector + Generate
        ctx_row = QHBoxLayout()
        ctx_row.setSpacing(4)
        self._ctx_source_combo = QComboBox()
        self._ctx_source_combo.addItem("Selection", userData="selection")
        self._ctx_source_combo.addItem("Current scene", userData="scene")
        self._ctx_source_combo.addItem("Outline", userData="outline")
        self._ctx_source_combo.addItem("Acts", userData="acts")
        self._ctx_source_combo.addItem("Whole project", userData="project")
        self._ctx_source_combo.setCurrentIndex(1)
        ctx_row.addWidget(self._ctx_source_combo, stretch=1)
        self._send_btn = QPushButton("Generate")
        self._t(self._send_btn, lambda: theme.primary_btn())
        self._send_btn.clicked.connect(self._send_custom)
        ctx_row.addWidget(self._send_btn)
        self._layout.addLayout(ctx_row)

        # Core actions (grid for wrapping on narrow panels)
        action_grid = QGridLayout()
        action_grid.setSpacing(4)
        action_grid.setContentsMargins(0, 0, 0, 0)
        self._preset_buttons: list[QPushButton] = []
        for col, action in enumerate(("Rewrite", "Expand", "Dialogue")):
            btn = QPushButton(action)
            btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            btn.clicked.connect(
                lambda _, a=action: self._send_preset(a)
            )
            action_grid.addWidget(btn, 0, col)
            self._preset_buttons.append(btn)

        self._suggest_btn = QPushButton("Suggest")
        self._suggest_btn.setToolTip(
            "Structured narrative direction suggestions"
        )
        self._suggest_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._suggest_btn.clicked.connect(self._on_suggest_beats)
        action_grid.addWidget(self._suggest_btn, 1, 0, 1, 2)
        self._preset_buttons.append(self._suggest_btn)

        self._more_btn = QPushButton("More \u25be")
        more_menu = QMenu(self)
        for action in (
            "Summarize", "Tension", "Pacing", "Next Beat", "Alternatives",
        ):
            more_menu.addAction(
                action, lambda a=action: self._send_preset(a)
            )
        self._more_btn.setMenu(more_menu)
        self._more_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        action_grid.addWidget(self._more_btn, 1, 2)
        self._preset_buttons.append(self._more_btn)
        self._layout.addLayout(action_grid)

        # Counterpart actions (hidden by default)
        self._counterpart_row = QWidget()
        cp_grid = QGridLayout(self._counterpart_row)
        cp_grid.setContentsMargins(0, 0, 0, 0)
        cp_grid.setSpacing(4)
        self._counterpart_buttons: list[QPushButton] = []
        for col, mode_name in enumerate(("Feedback", "Critique", "Interpret")):
            btn = QPushButton(mode_name)
            btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            btn.clicked.connect(
                lambda _, m=mode_name: self._send_counterpart(m)
            )
            cp_grid.addWidget(btn, 0, col)
            self._counterpart_buttons.append(btn)
        cp_more_btn = QPushButton("More ▾")
        cp_more_menu = QMenu(self)
        for mode_name in ("Ask Back", "Compare"):
            cp_more_menu.addAction(
                mode_name, lambda m=mode_name: self._send_counterpart(m)
            )
        cp_more_btn.setMenu(cp_more_menu)
        cp_more_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        cp_grid.addWidget(cp_more_btn, 1, 0, 1, 3)
        self._counterpart_buttons.append(cp_more_btn)
        self._counterpart_row.setVisible(False)
        self._layout.addWidget(self._counterpart_row)

        # Quantum actions (hidden by default)
        self._quantum_row = QWidget()
        q_grid = QGridLayout(self._quantum_row)
        q_grid.setContentsMargins(0, 0, 0, 0)
        q_grid.setSpacing(4)
        self._quantum_buttons: list[QPushButton] = []

        outline_btn = QPushButton("Outline")
        outline_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        outline_btn.setToolTip("Generate opening branches from a premise")
        outline_btn.clicked.connect(self._on_quantum_outline)
        q_grid.addWidget(outline_btn, 0, 0)
        self._quantum_buttons.append(outline_btn)

        possibilities_btn = QPushButton("Possibilities")
        possibilities_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        possibilities_btn.setToolTip("Generate next-move branches for the prompt")
        possibilities_btn.clicked.connect(self._on_quantum_possibilities)
        q_grid.addWidget(possibilities_btn, 0, 1)
        self._quantum_buttons.append(possibilities_btn)

        reframe_btn = QPushButton("Reframe")
        reframe_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        reframe_btn.setToolTip("Reread the active scene from a different POV")
        reframe_btn.clicked.connect(self._on_quantum_reframe)
        q_grid.addWidget(reframe_btn, 1, 0)
        self._quantum_buttons.append(reframe_btn)

        weak_btn = QPushButton("Uncertainty")
        weak_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        weak_btn.setToolTip("Find weak/predictable scenes")
        weak_btn.clicked.connect(self._on_quantum_uncertainty)
        q_grid.addWidget(weak_btn, 1, 1)
        self._quantum_buttons.append(weak_btn)

        collapse_btn = QPushButton("Collapse ▾")
        collapse_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        collapse_btn.setToolTip("Commit a branch — updates PSYKE")
        self._collapse_menu = QMenu(self)
        collapse_btn.setMenu(self._collapse_menu)
        self._collapse_menu.aboutToShow.connect(self._refresh_collapse_menu)
        q_grid.addWidget(collapse_btn, 2, 0, 1, 2)
        self._quantum_buttons.append(collapse_btn)

        self._quantum_row.setVisible(False)
        self._layout.addWidget(self._quantum_row)

        # Quantum structure mode selector
        self._structure_mode_row = QWidget()
        sm_layout = QHBoxLayout(self._structure_mode_row)
        sm_layout.setContentsMargins(0, 2, 0, 2)
        sm_layout.setSpacing(2)
        sm_label = QLabel("Structure:")
        self._t(sm_label, lambda: (
            f"color: {theme.TEXT_MUTED}; font-size: 10px; background: transparent;"
        ))
        sm_layout.addWidget(sm_label)
        self._structure_mode_buttons: list[QPushButton] = []
        for mode_name in STRUCTURE_MODES:
            btn = QPushButton(mode_name.capitalize())
            btn.setCheckable(True)
            btn.setFixedHeight(20)
            btn.clicked.connect(
                lambda _, m=mode_name: self._on_structure_mode(m)
            )
            sm_layout.addWidget(btn)
            self._structure_mode_buttons.append(btn)
        sm_layout.addStretch()
        self._structure_mode_row.setVisible(False)
        self._layout.addWidget(self._structure_mode_row)
        self._sync_structure_mode_buttons()

        # Lambda Mode toggle
        self._lambda_row = QWidget()
        lm_layout = QHBoxLayout(self._lambda_row)
        lm_layout.setContentsMargins(0, 1, 0, 1)
        lm_layout.setSpacing(6)
        self._lambda_toggle = QPushButton("Lambda Mode")
        self._lambda_toggle.setCheckable(True)
        self._lambda_toggle.setFixedHeight(20)
        self._lambda_toggle.clicked.connect(self._on_lambda_toggle)
        lm_layout.addWidget(self._lambda_toggle)
        self._lambda_indicator = QLabel("Mode: Classical")
        self._lambda_indicator.setStyleSheet(
            f"color: {theme.TEXT_MUTED}; font-size: 9px; background: transparent;"
        )
        lm_layout.addWidget(self._lambda_indicator)
        lm_layout.addStretch()
        self._lambda_row.setVisible(False)
        self._layout.addWidget(self._lambda_row)
        self._sync_lambda_toggle()

        # Quantum timeline superposition
        self._quantum_timeline = QuantumTimelineWidget(self._db, self._project_id)
        self._quantum_timeline.branch_selected.connect(self._on_timeline_branch_selected)
        self._quantum_timeline.collapse_requested.connect(self._on_quantum_collapse)
        self._quantum_timeline.archive_requested.connect(self._on_timeline_archive)
        self._quantum_timeline.setVisible(False)
        self._layout.addWidget(self._quantum_timeline)

        # Outline-only: template selector (from the PSYKE Outline Templates
        # plugin catalog). Shown only in Outline Mode; affects generation.
        self._outline_template_row = QWidget()
        _tpl_row = QHBoxLayout(self._outline_template_row)
        _tpl_row.setContentsMargins(0, 0, 0, 0)
        _tpl_row.setSpacing(4)
        _tpl_row.addWidget(QLabel("Template:"))
        self._outline_template_combo = QComboBox()
        self._reload_outline_templates()
        _tpl_row.addWidget(self._outline_template_combo, stretch=1)
        self._outline_template_row.setVisible(False)
        self._layout.addWidget(self._outline_template_row)

        # Custom prompt
        self._prompt_input = QPlainTextEdit()
        self._prompt_input.setPlaceholderText(
            "Instructions or questions about the scene..."
        )
        self._prompt_input.setMinimumHeight(60)
        self._prompt_input.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        # Prompt and response share the panel's flexible height 1 : 2 — a
        # roomier prompt for longer instructions, the response still ~2/3.
        self._layout.addWidget(self._prompt_input, stretch=1)

        # Collapsible settings
        self._settings_btn = QPushButton("\u25b6 Settings")
        self._settings_btn.setFlat(True)
        self._t(self._settings_btn, lambda: (
            f"QPushButton {{ color: {theme.TEXT_SECONDARY}; border: none;"
            f" text-align: left; padding: 2px 0; font-size: 11px; }}"
            f"QPushButton:hover {{ color: {theme.TEXT_PRIMARY}; }}"
        ))
        self._settings_btn.clicked.connect(self._toggle_settings)
        self._layout.addWidget(self._settings_btn)

        self._settings_container = QWidget()
        settings_layout = QVBoxLayout(self._settings_container)
        settings_layout.setContentsMargins(0, 0, 0, 0)
        settings_layout.setSpacing(4)
        self._outline_check = QCheckBox("Include story outline")
        self._story_memory_check = QCheckBox("Include story memory")
        self._psyke_check = QCheckBox("PSYKE")
        self._notes_check = QCheckBox("Include Notes")
        self._notes_check.setToolTip(
            "Include relevant project Notes in the Assistant context "
            "(scene-linked, PSYKE-linked, tag/name matches, and pinned "
            "notes — not every note)."
        )
        settings_layout.addWidget(self._outline_check)
        settings_layout.addWidget(self._story_memory_check)
        settings_layout.addWidget(self._psyke_check)
        settings_layout.addWidget(self._notes_check)

        self._idea_check = QCheckBox("Idea di Controllo")
        self._idea_check.setToolTip(
            "Inject the project's Controlling Idea (McKee) as a guiding "
            "constraint for the Assistant."
        )
        settings_layout.addWidget(self._idea_check)

        self._irrational_check = QCheckBox("Go Irrational")
        self._irrational_check.setToolTip(
            "Disrupt PSYKE rules: temporal displacement, entity blending, surreal prompts"
        )
        self._t(self._irrational_check, lambda: (
            f"QCheckBox {{ color: {theme.TEXT_SECONDARY}; }}"
            f"QCheckBox::indicator:checked {{ background: #a855f7; border: 1px solid #7c3aed; }}"
        ))
        settings_layout.addWidget(self._irrational_check)
        self._irrational_iteration = 0

        self._ctx_toggle = QCheckBox("Show context sent to model")
        self._ctx_toggle.toggled.connect(self._on_ctx_toggle)
        settings_layout.addWidget(self._ctx_toggle)

        self._ctx_viewer = QPlainTextEdit()
        self._ctx_viewer.setReadOnly(True)
        self._ctx_viewer.setMaximumHeight(140)
        self._ctx_viewer.setPlaceholderText(
            "Context will appear here after a request..."
        )
        self._t(self._ctx_viewer, lambda: (
            f"QPlainTextEdit {{"
            f"  background-color: {theme.BG_PANEL};"
            f"  color: {theme.TEXT_SECONDARY};"
            f"  border: 1px solid {theme.BORDER};"
            f"  font-size: 10px; padding: 4px;"
            f"}}"
        ))
        self._ctx_viewer.setVisible(False)
        settings_layout.addWidget(self._ctx_viewer)

        self._provider_widget = ProviderSettingsWidget(compact=True)
        self._restore_provider_settings()
        settings_layout.addWidget(self._provider_widget)

        timeout_row = QHBoxLayout()
        timeout_row.setSpacing(4)
        timeout_label = QLabel("API timeout:")
        self._t(timeout_label, lambda: f"color: {theme.TEXT_SECONDARY}; font-size: 11px;")
        timeout_row.addWidget(timeout_label)
        self._timeout_spin = QSpinBox()
        self._timeout_spin.setRange(0, 600)
        self._timeout_spin.setSuffix("s")
        self._timeout_spin.setSpecialValueText("Auto")
        self._timeout_spin.setToolTip(
            "Seconds before a request times out.\n"
            "Auto = 120s for cloud providers, 300s for local."
        )
        self._timeout_spin.setFixedWidth(80)
        timeout_row.addWidget(self._timeout_spin)
        timeout_row.addStretch()
        settings_layout.addLayout(timeout_row)

        self._settings_container.setVisible(False)
        self._layout.addWidget(self._settings_container)

        # Response area
        resp_header = QHBoxLayout()
        resp_header.setSpacing(4)
        resp_label = QLabel("Response")
        self._t(resp_label, lambda: (
            f"color: {theme.TEXT_SECONDARY}; font-size: 11px;"
        ))
        resp_header.addWidget(resp_label)
        self._cache_label = QLabel("cached")
        self._t(self._cache_label, lambda: (
            f"color: {theme.ACCENT}; font-size: 10px; font-style: italic;"
        ))
        self._cache_label.setVisible(False)
        resp_header.addWidget(self._cache_label)
        resp_header.addStretch()
        self._layout.addLayout(resp_header)

        # QTextEdit (not QPlainTextEdit) so read-only answers/analysis render
        # their Markdown (bold, lists, headings) for reading instead of showing
        # raw "**", "#", "-". Applyable prose/structure is still shown verbatim.
        self._response_output = QTextEdit()
        self._response_output.setReadOnly(True)
        self._response_output.setPlaceholderText(
            "AI response will appear here..."
        )
        self._response_output.setMinimumHeight(80)
        self._response_output.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        self._t(self._response_output, lambda: (
            f"QTextEdit {{"
            f"  background-color: {theme.BG_PANEL};"
            f"  color: {theme.TEXT_PRIMARY};"
            f"  border: 1px solid {theme.BORDER};"
            f"  border-radius: 4px; padding: 6px;"
            f"}}"
        ))
        self._layout.addWidget(self._response_output, stretch=2)

        # Apply actions: Copy | Replace | Insert | Append
        apply_row = QHBoxLayout()
        apply_row.setSpacing(4)

        self._copy_btn = QPushButton("Copy")
        self._copy_btn.clicked.connect(self._copy_response)
        apply_row.addWidget(self._copy_btn)

        self._replace_content_btn = QPushButton("Replace")
        self._replace_content_btn.clicked.connect(self._apply_replace)
        apply_row.addWidget(self._replace_content_btn)

        self._insert_cursor_btn = QPushButton("Insert")
        self._insert_cursor_btn.clicked.connect(self._apply_insert)
        apply_row.addWidget(self._insert_cursor_btn)

        self._append_btn = QPushButton("Append")
        self._append_btn.clicked.connect(self._apply_append)
        apply_row.addWidget(self._append_btn)

        # Outline-only: turn a generated outline into structured nodes.
        self._apply_outline_btn = QPushButton("Apply to Outline")
        self._apply_outline_btn.setToolTip(
            "Parse the generated outline into acts/chapters/scenes/beats and "
            "add them to the Outline (additive — nothing is overwritten)."
        )
        self._apply_outline_btn.clicked.connect(self._apply_to_outline)
        self._apply_outline_btn.setVisible(False)
        apply_row.addWidget(self._apply_outline_btn)

        self._apply_buttons = [
            self._copy_btn,
            self._replace_content_btn,
            self._insert_cursor_btn,
            self._append_btn,
            self._apply_outline_btn,
        ]
        self._layout.addLayout(apply_row)

        self._mode_strip.refresh()
        self._restore_panel_settings()
        # Persist provider/server settings immediately on change. Wired
        # AFTER restore so restoring saved values never re-triggers a save.
        self._provider_widget.settings_changed.connect(
            self._persist_provider_settings
        )
        self._timeout_spin.valueChanged.connect(
            lambda *_: self._persist_provider_settings()
        )
        # Persist the Include Notes preference immediately on toggle.
        self._notes_check.toggled.connect(
            lambda checked: get_settings().set(
                "assistant_include_notes", bool(checked)
            )
        )

    # -- Mode override ---------------------------------------------------------

    def _on_mode_override(self, mode: AIMode | None) -> None:
        pass  # Mode is read from strip at context-build time

    # -- Panel mode (Assistant / Counterpart) ----------------------------------

    def _seg_btn_style(self, active: bool) -> str:
        if active:
            return (
                f"QPushButton {{ background-color: {theme.ACCENT};"
                f" color: #ffffff; border: none; border-radius: 4px;"
                f" padding: 3px 10px; font-size: 11px; font-weight: bold; }}"
            )
        return (
            f"QPushButton {{ background-color: transparent;"
            f" color: {theme.TEXT_MUTED}; border: 1px solid {theme.BORDER};"
            f" border-radius: 4px; padding: 3px 10px; font-size: 11px; }}"
            f"QPushButton:hover {{ color: {theme.TEXT_PRIMARY}; }}"
        )

    def _set_panel_mode(self, mode: str) -> None:
        if mode not in ("assistant", "counterpart", "quantum"):
            mode = "assistant"
        self._panel_mode = mode
        is_assistant = mode == "assistant"
        is_counterpart = mode == "counterpart"
        is_quantum = mode == "quantum"

        self._assistant_mode_btn.setChecked(is_assistant)
        self._counterpart_mode_btn.setChecked(is_counterpart)
        self._quantum_mode_btn.setChecked(is_quantum)
        self._assistant_mode_btn.setStyleSheet(self._seg_btn_style(is_assistant))
        self._counterpart_mode_btn.setStyleSheet(self._seg_btn_style(is_counterpart))
        self._quantum_mode_btn.setStyleSheet(self._seg_btn_style(is_quantum))

        # Toggle action rows
        for btn in self._preset_buttons:
            btn.setVisible(is_assistant)
        self._counterpart_row.setVisible(is_counterpart)
        self._quantum_row.setVisible(is_quantum)
        self._structure_mode_row.setVisible(is_quantum)
        self._lambda_row.setVisible(is_quantum)
        self._quantum_timeline.setVisible(is_quantum)
        if is_quantum:
            self._sync_structure_mode_buttons()
            self._sync_lambda_toggle()
            self._quantum_timeline.refresh()

        # Apply buttons mutate scene content — only Assistant uses them
        self._replace_content_btn.setVisible(is_assistant)
        self._insert_cursor_btn.setVisible(is_assistant)
        self._append_btn.setVisible(is_assistant)

        # Mode strip only relevant for assistant
        self._mode_strip.setVisible(is_assistant)

        if is_assistant:
            placeholder = SECTION_PLACEHOLDERS.get(
                self._active_section,
                "Instructions or questions about your story...",
            )
            self._prompt_input.setPlaceholderText(placeholder)
        elif is_counterpart:
            self._prompt_input.setPlaceholderText(
                "Ask about your scene, request feedback, or reflect..."
            )
        else:
            self._prompt_input.setPlaceholderText(
                "Premise, situation, or POV name (used by Quantum actions)..."
            )

    # -- Settings toggle -------------------------------------------------------

    def _restore_provider_settings(self) -> None:
        mgr = get_settings()
        pw = self._provider_widget
        saved_provider = str(mgr.get("ai_provider") or "")

        # Seed the widget's per-provider memory from saved settings, folding in
        # the last-saved flat keys for the active provider (covers first run /
        # upgrades where no per-provider memory exists yet).
        raw_memory = mgr.get("ai_provider_memory")
        memory = dict(raw_memory) if isinstance(raw_memory, dict) else {}
        if saved_provider:
            entry = dict(memory.get(saved_provider) or {})
            entry.setdefault("model", str(mgr.get("ai_model") or ""))
            entry.setdefault("base_url", str(mgr.get("ai_base_url") or ""))
            entry.setdefault("api_key", str(mgr.get("ai_api_key") or ""))
            memory[saved_provider] = entry
        pw.set_provider_memory(memory)

        idx = pw._provider_combo.findText(saved_provider)
        if idx >= 0:
            pw._provider_combo.setCurrentIndex(idx)
        # Re-apply the active provider's remembered values even if the combo
        # index did not change (setCurrentIndex is a no-op then, so it would
        # not reload the fields on its own).
        pw.reload_current_provider()

    def _restore_panel_settings(self) -> None:
        mgr = get_settings()
        mode = str(mgr.get("assistant_panel_mode") or "assistant")
        if mode in ("assistant", "counterpart", "quantum"):
            self._set_panel_mode(mode)
        self._outline_check.setChecked(bool(mgr.get("assistant_include_outline")))
        self._story_memory_check.setChecked(bool(mgr.get("assistant_include_memory")))
        self._psyke_check.setChecked(bool(mgr.get("assistant_include_bible")))
        # Default ON (preserves prior always-included behavior) when unset.
        notes_pref = mgr.get("assistant_include_notes")
        self._notes_check.setChecked(True if notes_pref is None else bool(notes_pref))
        idea_default = bool(mgr.get("assistant_include_controlling_idea"))
        if mgr.get("assistant_include_controlling_idea") is None:
            idea_default = self._is_idea_plugin_enabled()
        self._idea_check.setChecked(idea_default)
        self._irrational_check.setChecked(bool(mgr.get("assistant_irrational")))
        timeout_val = mgr.get("assistant_api_timeout")
        self._timeout_spin.setValue(int(timeout_val) if timeout_val else 0)

    def _persist_provider_settings(self) -> None:
        """Save provider / server settings to global settings immediately.

        Provider config is global (app-wide), stored in
        ~/.logosforge/settings.json — it is not project-specific, so it
        survives project switches and app restarts. Covers provider, base
        URL, model, API key, and the API timeout. Local-server setups
        (LM Studio / Ollama / OpenAI-compatible) persist via the same
        provider + base_url + model keys.
        """
        mgr = get_settings()
        pw = self._provider_widget
        mgr.set("ai_provider", pw._provider_combo.currentText())
        mgr.set("ai_model", pw._model_combo.currentText())
        mgr.set("ai_api_key", pw._key_input.text())
        mgr.set("ai_base_url", pw._url_input.text())
        mgr.set("ai_provider_memory", pw.provider_memory())
        mgr.set("assistant_api_timeout", self._timeout_spin.value())

    def save_settings(self) -> None:
        mgr = get_settings()
        pw = self._provider_widget
        mgr.set("ai_provider", pw._provider_combo.currentText())
        mgr.set("ai_model", pw._model_combo.currentText())
        mgr.set("ai_api_key", pw._key_input.text())
        mgr.set("ai_base_url", pw._url_input.text())
        mgr.set("ai_provider_memory", pw.provider_memory())
        mgr.set("assistant_panel_mode", self._panel_mode)
        mgr.set("assistant_include_outline", self._outline_check.isChecked())
        mgr.set("assistant_include_memory", self._story_memory_check.isChecked())
        mgr.set("assistant_include_bible", self._psyke_check.isChecked())
        mgr.set("assistant_include_notes", self._notes_check.isChecked())
        mgr.set(
            "assistant_include_controlling_idea",
            self._idea_check.isChecked(),
        )
        mgr.set("assistant_irrational", self._irrational_check.isChecked())
        mgr.set("assistant_api_timeout", self._timeout_spin.value())

    def _is_idea_plugin_enabled(self) -> bool:
        try:
            from logosforge.plugin_manager import get_plugin_manager
            mgr = get_plugin_manager()
            for p in mgr.plugins:
                if p.id == "idea_di_controllo" and p.enabled:
                    return True
        except Exception:
            return False
        return False

    def _toggle_settings(self) -> None:
        visible = not self._settings_container.isVisible()
        self._settings_container.setVisible(visible)
        self._settings_btn.setText(
            "\u25bc Settings" if visible else "\u25b6 Settings"
        )

    def _on_ctx_toggle(self, checked: bool) -> None:
        self._ctx_viewer.setVisible(checked)

    # -- Context source --------------------------------------------------------

    def _get_context_source(self) -> str:
        return self._ctx_source_combo.currentData() or "scene"

    def _get_auto_scene_id(self) -> int | None:
        if self._get_active_scene_id:
            sid = self._get_active_scene_id()
            if sid is not None:
                return sid
        scenes = self._db.get_all_scenes(self._project_id)
        if len(scenes) == 1:
            return scenes[0].id
        return None

    def _get_selected_text_content(self) -> str:
        if self._get_selected_text:
            text = self._get_selected_text()
            if text:
                return text
        return ""

    def set_project(self, project_id: int) -> None:
        # Drop anything the previous project queued up — the next prompt
        # must be evaluated against the new project's context.
        self._pending_messages = None
        self._project_id = project_id
        # Clear the previous project's visible AI context so nothing from the
        # old project lingers in the always-on dock (and so the next answer is
        # never built on the prior project's prompt/response/context).
        self._reset_ai_context()
        quantum_load_state(self._db, project_id)
        self._quantum_timeline._project_id = project_id
        self._quantum_timeline.refresh()
        # Re-point the mode strip at the new project (was only refreshed against
        # the previous project_id, leaving a stale mode + manual override).
        self._mode_strip.set_project(project_id)

    def _reset_ai_context(self) -> None:
        """Clear project-bound visible state so no previous-project AI context
        (prompt, response, gathered context preview) survives a project switch."""
        if hasattr(self, "_prompt_input"):
            self._prompt_input.clear()
        if hasattr(self, "_response_output"):
            self._response_output.clear()
        if hasattr(self, "_ctx_viewer"):
            self._ctx_viewer.clear()

    def set_active_scene(self, scene_id: int) -> None:
        pass

    def refresh_scenes(self) -> None:
        self._mode_strip.refresh()

    def set_active_section_name(self, name: str) -> None:
        self._active_section = name
        placeholder = SECTION_PLACEHOLDERS.get(
            name, "Instructions or questions about your story..."
        )
        if self._panel_mode == "assistant":
            self._prompt_input.setPlaceholderText(placeholder)
        self._update_outline_action_visibility()
        self.refresh_scenes()

    def _is_outline_mode(self) -> bool:
        """Outline Mode = the Assistant is targeting the Outline section."""
        return self._active_section in ("Outline", "Plan")

    def _update_outline_action_visibility(self) -> None:
        outline = self._is_outline_mode()
        if hasattr(self, "_apply_outline_btn"):
            self._apply_outline_btn.setVisible(outline)
        # In Outline Mode the generated text is planning structure, NOT
        # manuscript prose. Hide the prose-targeting actions so a generated
        # outline can never be written into a scene's manuscript body; only
        # "Apply to Outline" (and Copy) remain. (A hard guard in each handler
        # backs this up even if a button is triggered programmatically.)
        for attr in ("_replace_content_btn", "_insert_cursor_btn", "_append_btn"):
            btn = getattr(self, attr, None)
            if btn is not None:
                btn.setVisible(not outline)
        if hasattr(self, "_outline_template_row"):
            self._reload_outline_templates()
            self._outline_template_row.setVisible(outline)

    def _reload_outline_templates(self) -> None:
        """Populate the Outline template selector from the plugin catalog."""
        from logosforge.outline_templates import list_templates
        combo = self._outline_template_combo
        current = combo.currentData() if combo.count() else ""
        combo.blockSignals(True)
        combo.clear()
        combo.addItem("No template", userData="")
        for key, name, desc in list_templates():
            combo.addItem(name, userData=key)
            combo.setItemData(combo.count() - 1, desc, Qt.ItemDataRole.ToolTipRole)
        idx = combo.findData(current)
        combo.setCurrentIndex(idx if idx >= 0 else 0)
        combo.blockSignals(False)

    def selected_outline_template(self) -> str:
        """Key of the currently selected Outline template ('' = none)."""
        if hasattr(self, "_outline_template_combo"):
            return self._outline_template_combo.currentData() or ""
        return ""

    def _outline_template_prompt(self, base_prompt: str) -> str:
        """Prepend template + engine guidance to the user prompt in Outline
        Mode so the generated outline follows the selected template."""
        if not self._is_outline_mode():
            return base_prompt
        key = self.selected_outline_template()
        if not key:
            return base_prompt
        from logosforge.outline_actions import build_outline_generation_prompt
        from logosforge.outline_templates import get_template
        from logosforge.project_compat import get_project_narrative_engine
        tmpl = get_template(key)
        if tmpl is None:
            return base_prompt
        engine = get_project_narrative_engine(
            self._db.get_project_by_id(self._project_id)
        )
        guidance = build_outline_generation_prompt(
            "full", engine=engine, template_name=tmpl.name,
            template_beats=[b.title for b in tmpl.beats],
            instructions=base_prompt,
        )
        return guidance

    def run_action(self, action_key: str, selected_text: str = "") -> bool:
        """Trigger a preset AI action programmatically. Returns False if busy."""
        if self._worker is not None:
            return False
        canonical = _normalize_action(action_key)
        if canonical is None:
            return False

        scene_ctx = ""
        if selected_text:
            scene_ctx = f"[Selected Text]\n{selected_text}"
        else:
            scene_id = self._get_auto_scene_id()
            if scene_id is not None:
                scene_ctx = gather_scene_context(
                    self._db, self._project_id, scene_id,
                )

        if not scene_ctx:
            self._response_output.setPlainText("No text selected and no active scene.")
            return False

        action_prompt = PRESET_ACTIONS[canonical]
        messages = build_messages(
            action_prompt, scene_ctx,
            structural_context=gather_structural_context(self._db, self._project_id),
            system_prompt=self._get_section_system_prompt(canonical),
        )

        if not self.isVisible():
            self.setVisible(True)
        self._response_output.setPlainText("")
        self._start_request(messages)
        return True

    def _get_section_system_prompt(self, action: str = "") -> str:
        from logosforge.assistant_contract import (
            is_direct_manuscript_writing, output_contract, route,
        )
        base = SECTION_SYSTEM_PROMPTS.get(self._active_section, "")
        mode = "novel"
        overlay = ""
        try:
            from logosforge.narrative_engines import engine_for_project
            project = self._db.get_project_by_id(self._project_id)
            engine = engine_for_project(project)
            mode = getattr(engine, "name", "novel") or "novel"
            overlay = engine.system_prompt_overlay or ""
        except Exception:
            pass
        # Remember the (mode, section, action) for response validation.
        self._last_contract = (mode, self._active_section, action)
        # Full routing contract drives validation / apply / cache enforcement.
        try:
            instr = self._prompt_input.toPlainText().strip()
        except Exception:
            instr = ""
        self._task_contract = route(
            entry_point="assistant_panel", section=self._active_section,
            writing_mode=mode, action=action, user_instruction=instr,
            has_target=True)
        # Direct manuscript-writing actions get a strict, mode-correct OUTPUT
        # contract — NOT the section base + the engine's critique/"key questions"
        # overlay, which makes the model emit analysis/structure instead of text.
        if is_direct_manuscript_writing(self._active_section, action):
            return output_contract(writing_mode=mode,
                                   section=self._active_section, action=action)
        if overlay:
            return base + "\n\n" + overlay if base else overlay
        return base

    def _current_writing_mode(self) -> str:
        """The project's narrative-engine name (writing mode), e.g. 'novel' or
        'screenplay'. Falls back to 'novel' if the engine can't be resolved."""
        try:
            from logosforge.narrative_engines import engine_for_project
            project = self._db.get_project_by_id(self._project_id)
            engine = engine_for_project(project)
            return getattr(engine, "name", "novel") or "novel"
        except Exception:
            return "novel"

    def _set_analysis_contract(self, *, entry_point: str, action: str) -> None:
        """Route a non-direct ANALYSIS contract and store it as the active task
        contract for a Counterpart/Quantum send.

        Counterpart (editorial critique) and Quantum (possibilities) output is
        inherently analysis, never manuscript prose — so it must carry its OWN
        contract instead of inheriting whatever stale Assistant '*_direct'
        contract a prior request left in ``self._task_contract``. The
        analysis_answer profile skips the manuscript markdown/list/forbidden-
        prose checks (which misfire on legitimate critique) while keeping the
        profile-independent secret / raw-audio / hidden-context guards, and
        apply_allowed=False keeps the output out of the manuscript.
        """
        from logosforge.assistant_contract import route
        self._task_contract = route(
            entry_point=entry_point, section="manuscript",
            writing_mode=self._current_writing_mode(), action=action,
            has_target=True)

    # -- Sending requests ------------------------------------------------------

    def _build_context(
        self, action_key: str = "",
    ) -> tuple[str, str, str, str, str, str, str, str, str, str]:
        source = self._get_context_source()
        scene_id = self._get_auto_scene_id()

        scene_ctx = ""
        if source == "selection":
            selected = self._get_selected_text_content()
            if selected:
                scene_ctx = f"[Selected Text]\n{selected}"
            elif scene_id is not None:
                scene_ctx = gather_scene_context(
                    self._db, self._project_id, scene_id,
                )
        elif source == "scene" and scene_id is not None:
            scene_ctx = gather_scene_context(
                self._db, self._project_id, scene_id,
            )

        outline_ctx = ""
        if source in ("outline", "project", "acts") or self._outline_check.isChecked():
            outline_ctx = gather_outline_context(self._db, self._project_id)

        story_memory_ctx = ""
        if self._story_memory_check.isChecked():
            global_mem = gather_story_memory(self._db, self._project_id)
            scene_mem = ""
            if scene_id is not None:
                scene_mem = gather_memory_context(
                    self._db, self._project_id, scene_id=scene_id,
                )
            story_memory_ctx = "\n\n".join(
                part for part in [global_mem, scene_mem] if part
            )

        psyke_ctx = ""
        orchestration_debug = ""
        if self._psyke_check.isChecked():
            prompt_query = self._prompt_input.toPlainText().strip()
            selected_text = self._get_selected_text_content()
            query_text = "\n".join(t for t in (prompt_query, selected_text) if t)
            if scene_id is not None:
                # Custom "Generate" (no preset action_key) also routes through
                # the mode-aware orchestration — resolve_mode("") defaults to
                # MODE_REWRITE — so it gets the same entry caps + relation
                # filtering instead of dumping a less-filtered bible.
                mode = resolve_mode(action_key)
                result = orchestrate_psyke_context(
                    self._db, self._project_id, scene_id, mode,
                    selected_text=query_text,
                )
                psyke_ctx = result.psyke_context
                orchestration_debug = format_orchestration_debug(result)
            else:
                psyke_ctx = gather_psyke_context(
                    self._db, self._project_id, scene_id,
                    query_text=query_text,
                )

        # Notes are relevance-filtered (scene/PSYKE links, tags, names,
        # pinned) inside gather_notes_context — never a blind dump. Built
        # fresh from the DB each request, so it always reflects the latest
        # notes (no stale cache to invalidate).
        notes_ctx = ""
        if self._notes_check.isChecked():
            prompt_query = self._prompt_input.toPlainText().strip()
            notes_ctx = gather_notes_context(
                self._db, self._project_id, scene_id,
                query_text=prompt_query,
            )

        graph_ctx = ""
        if scene_id is not None and source in ("scene", "selection"):
            graph_ctx = gather_graph_context(self._db, self._project_id, scene_id)

        structural_ctx = gather_structural_context(self._db, self._project_id)

        irrational_ctx = ""
        if self._irrational_check.isChecked() and scene_id is not None:
            seed = reroll_seed(scene_id, self._irrational_iteration)
            irrational_ctx = build_irrational_context(
                self._db, self._project_id, scene_id, seed=seed,
            )

        controlling_idea_ctx = ""
        if self._idea_check.isChecked():
            from logosforge.controlling_idea import gather_controlling_idea_context
            controlling_idea_ctx = gather_controlling_idea_context(
                self._db, self._project_id, scene_id,
            )

        self._mode_strip.refresh()
        mode_result = self._mode_strip.get_mode_result()
        if self._mode_strip.is_overridden():
            effective = self._mode_strip.get_effective_mode()
            mode_result = ModeResult(
                mode=effective,
                stage=mode_result.stage if mode_result else StoryStage.EARLY,
                health=mode_result.health if mode_result else HealthState.FRAGMENTED,
                description=_MODE_DESCRIPTIONS[effective],
            )
        mode_ctx = mode_context_block(mode_result) if mode_result else ""

        # Narrative-engine context — resolved via engine_for_project (reads
        # project.narrative_engine, with legacy format_mode fallback).
        # Prepended to structural_ctx so the Assistant has the engine's
        # priorities + structural terminology + review checks when it reasons.
        try:
            from logosforge.assistant_contract import (
                is_direct_manuscript_writing,
            )
            from logosforge.narrative_engines import engine_for_project
            project = self._db.get_project_by_id(self._project_id)
            engine = engine_for_project(project)
            # For direct manuscript writing, use the MINIMAL writing block (units
            # + terminology only). The full block carries the engine's critique
            # "key questions" / review checks, which make a direct-writing action
            # (e.g. Dialogue) emit analysis/structure instead of manuscript text.
            if is_direct_manuscript_writing(self._active_section, action_key):
                engine_block = engine.format_writing_block()
            else:
                engine_block = engine.format_context_block()
            if engine_block:
                structural_ctx = (
                    engine_block + "\n\n" + structural_ctx
                    if structural_ctx else engine_block
                )
        except Exception:
            pass

        # Go McKee — operational writing-intelligence layer. When the
        # plugin is enabled it injects PSYKE-aware craft constraints and
        # diagnostic checks; when disabled it contributes nothing, so
        # toggling Go McKee genuinely changes Assistant behavior. Folded
        # into structural_ctx (always threaded to build_messages) and
        # placed first so its craft pressure leads.
        try:
            from logosforge.gomckee_bridge import gather_gomckee_context
            gomckee_ctx = gather_gomckee_context(
                self._db, self._project_id, scene_id,
                query_text=self._prompt_input.toPlainText().strip(),
            )
            if gomckee_ctx:
                structural_ctx = (
                    gomckee_ctx + "\n\n" + structural_ctx
                    if structural_ctx else gomckee_ctx
                )
        except Exception:
            pass

        # Phase 8B — controlled Strategy / Narrative Health / Diagnostics
        # injection. Gated by settings with conservative defaults and hard
        # caps so the prompt never receives a bloated dump. Read-only,
        # deterministic, no LLM/DB writes. Reads the current project / section /
        # scene each build so a project switch can't leak old context.
        try:
            from logosforge.assistant_context_policy import (
                gather_injected_context,
            )
            injected = gather_injected_context(
                self._db, self._project_id,
                section_name=self._active_section, scene_id=scene_id,
            )
            if injected:
                structural_ctx = (
                    injected + "\n\n" + structural_ctx
                    if structural_ctx else injected
                )
        except Exception:
            pass

        # Graphic Novel — when the project's engine is graphic_novel,
        # surface page rhythm / motifs / density / continuity and PSYKE
        # visual identity so the Assistant reasons visually.
        try:
            from logosforge.narrative_engines import engine_for_project
            project = self._db.get_project_by_id(self._project_id)
            if engine_for_project(project).name == "graphic_novel":
                gn_blocks: list[str] = []
                from logosforge.graphic_novel_plot import (
                    build_graphic_novel_context,
                )
                gn_ctx = build_graphic_novel_context(self._db, self._project_id)
                if gn_ctx:
                    gn_blocks.append(gn_ctx)
                from logosforge.psyke_visual import build_visual_memory_context
                visual_ctx = build_visual_memory_context(self._db, self._project_id)
                if visual_ctx:
                    gn_blocks.append(visual_ctx)
                if gn_blocks:
                    block = "\n\n".join(gn_blocks)
                    structural_ctx = (
                        block + "\n\n" + structural_ctx
                        if structural_ctx else block
                    )
        except Exception:
            pass

        # Stage Script — when the engine is stage_script, surface compact
        # theatrical PSYKE (objectives, pressures, knowledge, entrances/
        # exits, props, staging concerns) so the Assistant reasons for the
        # stage.
        try:
            from logosforge.narrative_engines import engine_for_project
            project = self._db.get_project_by_id(self._project_id)
            if engine_for_project(project).name == "stage_script":
                stage_blocks: list[str] = []
                from logosforge.stage_script_plot import (
                    build_stage_script_context,
                )
                stage_ctx = build_stage_script_context(
                    self._db, self._project_id, scene_id,
                )
                if stage_ctx:
                    stage_blocks.append(stage_ctx)
                from logosforge.psyke_theatre import build_theatre_memory_context
                theatre_ctx = build_theatre_memory_context(
                    self._db, self._project_id,
                )
                if theatre_ctx:
                    stage_blocks.append(theatre_ctx)
                if stage_blocks:
                    block = "\n\n".join(stage_blocks)
                    structural_ctx = (
                        block + "\n\n" + structural_ctx
                        if structural_ctx else block
                    )
        except Exception:
            pass

        # Series — when the engine is series, surface compact long-form
        # memory (current season/episode, active arcs, unresolved threads,
        # continuity risks, character state history).
        try:
            from logosforge.narrative_engines import engine_for_project
            project = self._db.get_project_by_id(self._project_id)
            if engine_for_project(project).name == "series":
                from logosforge.psyke_series import build_series_memory_context
                series_ctx = build_series_memory_context(
                    self._db, self._project_id,
                )
                if series_ctx:
                    structural_ctx = (
                        series_ctx + "\n\n" + structural_ctx
                        if structural_ctx else series_ctx
                    )
        except Exception:
            pass

        return scene_ctx, outline_ctx, story_memory_ctx, psyke_ctx, orchestration_debug, notes_ctx, graph_ctx, mode_ctx, structural_ctx, irrational_ctx, controlling_idea_ctx

    def _send_preset(self, action_key: str) -> None:
        if self._worker is not None:
            return

        scene_ctx, outline_ctx, story_memory_ctx, psyke_ctx, orch_debug, notes_ctx, graph_ctx, mode_ctx, struct_ctx, irr_ctx, idea_ctx = (
            self._build_context(action_key=action_key)
        )
        if not scene_ctx and not outline_ctx and not struct_ctx:
            self._response_output.setPlainText("No context available. Add scenes or project data first.")
            return

        user_note = self._prompt_input.toPlainText().strip()
        action_prompt = PRESET_ACTIONS[action_key]

        messages = build_messages(
            action_prompt, scene_ctx,
            outline_context=outline_ctx,
            story_memory_context=story_memory_ctx,
            psyke_context=psyke_ctx,
            notes_context=notes_ctx,
            graph_context=graph_ctx,
            mode_context=mode_ctx,
            user_note=user_note,
            structural_context=struct_ctx,
            irrational_context=irr_ctx,
            controlling_idea_context=idea_ctx,
            system_prompt=self._get_section_system_prompt(action_key),
        )
        self._update_ctx_viewer(
            scene_ctx, outline_ctx, story_memory_ctx, psyke_ctx, action_prompt,
            orch_debug, graph_ctx, mode_ctx,
        )
        self._start_request(messages)

    def _send_custom(self) -> None:
        if self._panel_mode == "counterpart":
            return self._send_counterpart_custom()
        if self._worker is not None:
            return
        prompt = self._prompt_input.toPlainText().strip()
        if not prompt:
            self._response_output.setPlainText("Enter a prompt first.")
            return

        scene_ctx, outline_ctx, story_memory_ctx, psyke_ctx, orch_debug, notes_ctx, graph_ctx, mode_ctx, struct_ctx, irr_ctx, idea_ctx = (
            self._build_context()
        )

        # Outline Mode: fold in the selected template + engine structure so the
        # generated outline follows it.
        prompt = self._outline_template_prompt(prompt)

        messages = build_messages(
            prompt, scene_ctx,
            outline_context=outline_ctx,
            story_memory_context=story_memory_ctx,
            psyke_context=psyke_ctx,
            notes_context=notes_ctx,
            graph_context=graph_ctx,
            mode_context=mode_ctx,
            structural_context=struct_ctx,
            irrational_context=irr_ctx,
            controlling_idea_context=idea_ctx,
            system_prompt=self._get_section_system_prompt("generate"),
        )
        self._update_ctx_viewer(
            scene_ctx, outline_ctx, story_memory_ctx, psyke_ctx, prompt,
            orch_debug, graph_ctx, mode_ctx,
        )
        self._start_request(messages)

    def _send_counterpart(self, mode_key: str) -> None:
        if self._worker is not None:
            return
        # Counterpart output is analysis — route a proper non-direct contract
        # now so the response is never validated against (or applied as) a
        # stale Assistant manuscript '*_direct' contract from a prior request.
        self._set_analysis_contract(
            entry_point="counterpart_panel", action=mode_key)

        scene_ctx, outline_ctx, story_memory_ctx, psyke_ctx, orch_debug, _notes_ctx, graph_ctx, _mode_ctx, _struct_ctx, _irr_ctx, _idea_ctx = (
            self._build_context()
        )
        if not scene_ctx and not outline_ctx:
            self._response_output.setPlainText("No context available. Add scenes or project data first.")
            return

        mode_prompt = DIALOGIC_MODES[mode_key]
        user_note = self._prompt_input.toPlainText().strip()

        messages = build_counterpart_messages(
            mode_prompt, scene_ctx,
            outline_context=outline_ctx,
            story_memory_context=story_memory_ctx,
            psyke_context=psyke_ctx,
            graph_context=graph_ctx,
            user_note=user_note,
        )
        self._update_ctx_viewer(
            scene_ctx, outline_ctx, story_memory_ctx, psyke_ctx,
            f"[COUNTERPART: {mode_key}] {mode_prompt}",
            orch_debug, graph_ctx,
        )
        self._start_request(messages)

    def _send_counterpart_custom(self) -> None:
        if self._worker is not None:
            return
        # Same analysis routing as the preset counterpart modes (see
        # _send_counterpart): never inherit a stale '*_direct' contract.
        self._set_analysis_contract(
            entry_point="counterpart_panel", action="custom")
        prompt = self._prompt_input.toPlainText().strip()
        if not prompt:
            self._response_output.setPlainText("Enter a prompt first.")
            return

        scene_ctx, outline_ctx, story_memory_ctx, psyke_ctx, orch_debug, _notes_ctx, graph_ctx, _mode_ctx, _struct_ctx, _irr_ctx, _idea_ctx = (
            self._build_context()
        )

        messages = build_counterpart_messages(
            prompt, scene_ctx,
            outline_context=outline_ctx,
            story_memory_context=story_memory_ctx,
            psyke_context=psyke_ctx,
            graph_context=graph_ctx,
        )
        self._update_ctx_viewer(
            scene_ctx, outline_ctx, story_memory_ctx, psyke_ctx,
            f"[COUNTERPART: Custom] {prompt}",
            orch_debug, graph_ctx,
        )
        self._start_request(messages)

    # -- Quantum Outliner handlers ---------------------------------------------

    def _quantum_prompt(self) -> str:
        return self._prompt_input.toPlainText().strip()

    def _on_structure_mode(self, mode: str) -> None:
        state = quantum_get_state(self._project_id)
        state.structure_mode = mode
        self._sync_structure_mode_buttons()
        quantum_save_state(self._db, self._project_id)
        if self._on_data_changed:
            self._on_data_changed()

    def _sync_structure_mode_buttons(self) -> None:
        state = quantum_get_state(self._project_id)
        current = state.structure_mode
        for btn in self._structure_mode_buttons:
            is_active = btn.text().lower() == current
            btn.setChecked(is_active)
            btn.setStyleSheet(self._structure_mode_btn_style(is_active))

    @staticmethod
    def _structure_mode_btn_style(active: bool) -> str:
        if active:
            return (
                f"QPushButton {{ background: {theme.SELECTION_BG};"
                f" color: {theme.ACCENT}; border: 1px solid {theme.ACCENT_DIM};"
                f" border-radius: 3px; padding: 1px 6px;"
                f" font-size: 10px; font-weight: bold; }}"
            )
        return (
            f"QPushButton {{ background: transparent;"
            f" color: {theme.TEXT_MUTED}; border: 1px solid {theme.BORDER};"
            f" border-radius: 3px; padding: 1px 6px; font-size: 10px; }}"
            f"QPushButton:hover {{ color: {theme.TEXT_PRIMARY}; }}"
        )

    def _on_lambda_toggle(self) -> None:
        state = quantum_get_state(self._project_id)
        if self._lambda_toggle.isChecked():
            state.outline_mode = OutlineMode.LAMBDA
        else:
            state.outline_mode = OutlineMode.CLASSICAL
        self._sync_lambda_toggle()
        quantum_save_state(self._db, self._project_id)
        self._quantum_timeline.refresh()
        if self._on_data_changed:
            self._on_data_changed()

    def _sync_lambda_toggle(self) -> None:
        state = quantum_get_state(self._project_id)
        is_lambda = state.outline_mode is OutlineMode.LAMBDA
        self._lambda_toggle.setChecked(is_lambda)
        self._lambda_toggle.setStyleSheet(self._lambda_btn_style(is_lambda))
        if is_lambda:
            self._lambda_indicator.setText("Mode: Lambda")
            self._lambda_indicator.setStyleSheet(
                f"color: {theme.ACCENT_DIM}; font-size: 9px;"
                f" font-weight: bold; background: transparent;"
            )
        else:
            self._lambda_indicator.setText("Mode: Classical")
            self._lambda_indicator.setStyleSheet(
                f"color: {theme.TEXT_MUTED}; font-size: 9px; background: transparent;"
            )

    @staticmethod
    def _lambda_btn_style(active: bool) -> str:
        if active:
            return (
                f"QPushButton {{ background: {theme.SELECTION_BG};"
                f" color: {theme.ACCENT}; border: 1px solid {theme.ACCENT_DIM};"
                f" border-radius: 3px; padding: 1px 8px;"
                f" font-size: 10px; font-weight: bold; }}"
            )
        return (
            f"QPushButton {{ background: transparent;"
            f" color: {theme.TEXT_MUTED}; border: 1px solid {theme.BORDER};"
            f" border-radius: 3px; padding: 1px 8px; font-size: 10px; }}"
            f"QPushButton:hover {{ color: {theme.TEXT_PRIMARY}; }}"
        )

    def _show_quantum_result(self, result) -> None:
        self._response_output.setMarkdown(
            self._quantum_markdown(result.title, result.body or "")
        )

    @staticmethod
    def _quantum_markdown(title: str, body: str) -> str:
        # The quantum report is structured monospace text (section banners,
        # weighted option blocks, weakness bars, and an aligned factor-
        # comparison matrix). Render it through the shared Markdown view: bold
        # the section/option headers and keep EVERY line break (two trailing
        # spaces = a Markdown hard break) so the option detail lines (Stakes /
        # Consequence / …) don't collapse into one paragraph. A blank-line block
        # that holds a solid horizontal rule is an aligned table — keep it in a
        # code fence so its columns stay monospace and lined up.
        def _is_rule(s: str) -> bool:
            t = s.strip()
            return len(t) >= 4 and set(t) <= set("─—-=━┄")

        out = [f"### ⟨ QUANTUM · {title} ⟩", ""]

        def _flush(block: list[str]) -> None:
            if not block:
                return
            if any(_is_rule(b) for b in block):
                out.append("```")                     # aligned table → monospace
                out.extend(b.rstrip() for b in block)
                out.append("```")
            else:
                for raw in block:
                    line = raw.rstrip()
                    s = line.strip()
                    if s.startswith("═══") and s.endswith("═══"):
                        out.append(f"**{s.strip('═ ').strip()}**  ")
                    elif s and s[0] in "▸●✓✗→•":
                        out.append(f"**{line}**  ")
                    else:
                        out.append(f"{line}  ")
            out.append("")

        block: list[str] = []
        for raw in body.split("\n"):
            if raw.strip() == "":
                _flush(block)
                block = []
            else:
                block.append(raw)
        _flush(block)
        return "\n".join(out)

    def _start_quantum(self, fn, *args, loading_msg: str = "Working…", **kwargs) -> bool:
        if self._quantum_worker is not None:
            return False
        self._set_quantum_busy(True)
        self._response_output.setPlainText(loading_msg)
        self._quantum_worker = _QuantumWorker(fn, *args, **kwargs)
        self._quantum_worker.completed.connect(self._on_quantum_done)
        self._quantum_worker.failed.connect(self._on_quantum_error)
        self._quantum_worker.start()
        return True

    def _on_quantum_done(self, result) -> None:
        self._show_quantum_result(result)
        self._set_quantum_busy(False)
        if result.kind in ("possibilities", "collapse"):
            quantum_save_state(self._db, self._project_id)
            if self._on_data_changed:
                self._on_data_changed()
        self._quantum_worker = None
        self._quantum_timeline.refresh()

    def _on_quantum_error(self, error: str) -> None:
        self._response_output.setPlainText(f"Error:\n\n{error}")
        self._set_quantum_busy(False)
        self._quantum_worker = None

    def _set_quantum_busy(self, busy: bool) -> None:
        for btn in self._quantum_buttons:
            btn.setEnabled(not busy)

    def _on_quantum_outline(self) -> None:
        premise = self._quantum_prompt()
        if not premise:
            self._response_output.setPlainText(
                "Type a story premise above, then click Outline."
            )
            return
        scene_id = self._get_auto_scene_id()
        self._start_quantum(
            quantum_generate_outline, self._db, self._project_id, premise,
            source_scene_id=scene_id,
            loading_msg="Generating wavefunction…",
        )

    def _on_quantum_possibilities(self) -> None:
        situation = self._quantum_prompt()
        scene_id = self._get_auto_scene_id()
        if not situation:
            if scene_id is not None:
                situation = f"Continue from active scene #{scene_id}"
            else:
                self._response_output.setPlainText(
                    "Type a situation (e.g. 'Hero meets enemy') and click Possibilities."
                )
                return
        self._start_quantum(
            quantum_generate_branches, self._db, self._project_id, situation,
            source_scene_id=scene_id,
            loading_msg="Generating possibilities…",
        )

    def _on_quantum_reframe(self) -> None:
        pov = self._quantum_prompt() or "neutral"
        scene_text = self._get_selected_text_content()
        if not scene_text:
            scene_id = self._get_auto_scene_id()
            if scene_id is not None:
                scene = self._db.get_scene_by_id(scene_id)
                if scene:
                    scene_text = scene.content or ""
        if not scene_text:
            self._response_output.setPlainText(
                "Select text or open a scene to reframe."
            )
            return
        self._start_quantum(
            quantum_reframe, scene_text, pov, self._db, self._project_id,
            loading_msg=f"Reframing from {pov}…",
        )

    def _on_quantum_uncertainty(self) -> None:
        result = quantum_detect_weak_scenes(self._db, self._project_id)
        self._show_quantum_result(result)

    def _refresh_collapse_menu(self) -> None:
        self._collapse_menu.clear()
        active = quantum_list_active(self._project_id)
        if not active:
            action = self._collapse_menu.addAction("(no active wavefunctions)")
            action.setEnabled(False)
            return
        for wf in active:
            sub = self._collapse_menu.addMenu(f"{wf['anchor'][:40]}")
            for branch in wf["branches"]:
                label = f"{branch['title']} [{branch['id']}]"
                sub.addAction(
                    label,
                    lambda wf_id=wf["wavefunction_id"], b_id=branch["id"]:
                        self._on_quantum_collapse(wf_id, b_id),
                )

    def _on_quantum_collapse(self, wf_id: str, branch_id: str) -> None:
        self._start_quantum(
            quantum_collapse_branch, self._db, self._project_id, wf_id, branch_id,
            loading_msg="Collapsing branch…",
        )

    def _on_timeline_branch_selected(self, wf_id: str, branch_id: str) -> None:
        from logosforge.quantum_outliner.state import get_state
        state = get_state(self._project_id)
        wf = state.get(wf_id)
        if wf is None:
            return
        branch = wf.get_branch(branch_id)
        if branch is None:
            return
        lines = [
            f"[QUANTUM · Branch Selected]",
            "",
            f"Wavefunction: {wf.anchor}",
            f"Branch: {branch.title}  [{branch.id}]",
            f"  {branch.description}",
        ]
        if branch.stakes:
            lines.append(f"  Stakes: {branch.stakes}")
        if branch.consequence:
            lines.append(f"  Consequence: {branch.consequence}")
        self._response_output.setPlainText("\n".join(lines))

    def _on_timeline_archive(self, wf_id: str) -> None:
        from logosforge.quantum_outliner.state import get_state
        state = get_state(self._project_id)
        removed = state.remove(wf_id)
        if removed:
            quantum_save_state(self._db, self._project_id)
            self._quantum_timeline.refresh()
            self._response_output.setPlainText("Wavefunction archived.")
            if self._on_data_changed:
                self._on_data_changed()

    def _on_suggest_beats(self) -> None:
        if self._worker is not None:
            return
        scene_id = self._get_auto_scene_id()
        if scene_id is None:
            self._response_output.setPlainText("Select a scene to get beat suggestions.")
            return

        messages, ctx = build_suggestion_messages(
            self._db, self._project_id, scene_id,
        )
        if not messages:
            self._response_output.setPlainText(
                "Could not build suggestion context."
            )
            return

        if ctx:
            self._update_ctx_viewer(
                "", "", "", ctx.psyke_context,
                "Narrative Beat Suggestions",
                format_suggestion_debug(ctx),
            )

        self._start_request(messages)

    def _update_ctx_viewer(
        self, scene_ctx: str, outline_ctx: str,
        story_memory_ctx: str, psyke_ctx: str, action: str,
        orchestration_debug: str = "", graph_ctx: str = "",
        mode_ctx: str = "",
    ) -> None:
        parts = []
        if mode_ctx:
            parts.append(f"--- AI Mode ---\n{mode_ctx}")
        parts.append(f"--- Scene Context ---\n{scene_ctx}")
        if outline_ctx:
            parts.append(f"--- Outline ---\n{outline_ctx}")
        if story_memory_ctx:
            parts.append(f"--- Story Memory ---\n{story_memory_ctx}")
        if psyke_ctx:
            parts.append(f"--- Story Bible ---\n{psyke_ctx}")
        if graph_ctx:
            parts.append(f"--- Graph Context ---\n{graph_ctx}")
        if orchestration_debug:
            parts.append(orchestration_debug)
        parts.append(f"--- Action ---\n{action}")
        self._ctx_viewer.setPlainText("\n\n".join(parts))

    def _start_request(self, messages: list[dict]) -> None:
        error = self._provider_widget.validate()
        if error:
            self._response_output.setPlainText(error)
            return
        self._pending_messages = messages
        self._debounce_timer.start()

    def _fire_request(self) -> None:
        if self._pending_messages is None:
            return
        messages = self._pending_messages
        self._pending_messages = None
        self._set_busy(True)
        self._cache_label.setVisible(False)
        self._response_output.setPlainText("Thinking...")

        provider = self._provider_widget.get_provider_config()
        timeout = get_configured_timeout(provider.name)
        self._worker = _AssistantWorker(messages, provider, timeout=timeout)
        self._worker.completed.connect(self._on_response)
        self._worker.failed.connect(self._on_error)
        self._worker.start()

    # -- Response handling -----------------------------------------------------

    def _show_response_text(self, text: str, contract) -> None:
        # Read-only answers/analysis/suggestions are Markdown — render them so
        # the reader sees bold/lists/headings, not raw "**"/"#"/"-". Applyable
        # or parsed output (manuscript prose, outline structure, codex, notes)
        # is shown verbatim: it has meaningful line breaks Markdown would
        # collapse, and Apply/parse must read the exact source via toPlainText().
        from logosforge.assistant_contract import (
            ANALYSIS, ANSWER, CLARIFICATION, SUGGESTIONS,
        )
        kind = getattr(contract, "output_kind", "")
        if kind in (ANALYSIS, ANSWER, SUGGESTIONS, CLARIFICATION):
            self._response_output.setMarkdown(text)
        else:
            self._response_output.setPlainText(text)

    def _on_response(self, text: str, from_cache: bool) -> None:
        # Validate against the routed task contract BEFORE the response is
        # treated as usable. Invalid direct output is shown as an error (or
        # withheld if it leaks secrets), and Apply is disabled — for cached
        # responses too, so an invalid result is never replayed as valid.
        self._set_busy(False)
        self._worker = None
        self._cache_label.setVisible(from_cache)
        self._response_valid = True
        self._copy_allowed = True
        try:
            from logosforge.assistant_contract import validate
            # Counterpart/Quantum route their own non-direct analysis contract
            # at send time (see _set_analysis_contract), so validation here
            # always runs against the truthful contract for this request — no
            # panel-mode special-casing needed.
            contract = getattr(self, "_task_contract", None)
            res = validate(text, contract) if contract is not None else None
        except Exception:
            res = None

        if res is None or res.status == "valid":
            self._show_response_text(text, contract)
            self._response_valid = True
            # Manuscript Apply only for direct content; Outline mode applies
            # valid structure through its own outline pipeline — but ONLY when
            # the Assistant panel generated it. Counterpart/Quantum produce
            # non-applyable analysis (apply_allowed=False), so they must stay
            # apply-disabled even when the Outline section happens to be active.
            self._apply_ok = (
                True if res is None
                else bool(res.apply_allowed)
                or (self._is_outline_mode()
                    and getattr(self, "_panel_mode", "assistant") == "assistant"
                    and getattr(contract, "entry_point", "") == "assistant_panel"))
            self._copy_allowed = True
        elif res.diagnostic_only:
            self._response_output.setPlainText(
                "⚠ Response withheld: it contained sensitive content "
                "(a secret or raw-audio path). Nothing was applied.")
            self._response_valid = False
            self._apply_ok = False
            self._copy_allowed = False
        else:
            reasons = "; ".join(res.reasons[:3])
            label = getattr(contract, "writing_mode", "manuscript").replace(
                "_", " ")
            self._response_output.setPlainText(
                f"⚠ Invalid output — this is planning/structure/meta, not "
                f"usable {label} content, so Apply is disabled "
                f"({reasons}). Refine your request or run the action again.\n\n"
                f"— raw model output (not applied) —\n{text}")
            self._response_valid = False
            self._apply_ok = False
            self._copy_allowed = False
        # Counterpart/Quantum stay apply-disabled because their routed analysis
        # contract has apply_allowed=False — the valid branch above already left
        # _apply_ok False (the only special-case left is scoping the Outline
        # override to the Assistant panel), so no blanket hardening is needed.
        self._apply_response_gating()

        # Local Writer QA mode (OFF by default): record a redacted structured
        # event so an external writer/QA agent can audit routing / validation /
        # apply without exposing secrets, raw audio, local paths, or full
        # manuscripts. Fully env-gated and fail-safe; disabled → no-op.
        try:
            from logosforge import qa_mode
            if qa_mode.is_qa_mode():
                c = getattr(self, "_task_contract", None)
                qa_mode.log_event(
                    "assistant_response",
                    entry_point=getattr(c, "entry_point", "assistant_panel"),
                    section=getattr(c, "section", self._active_section),
                    writing_mode=getattr(c, "writing_mode", ""),
                    action=getattr(c, "action", ""),
                    target=getattr(c, "target", ""),
                    output_kind=getattr(c, "output_kind", ""),
                    validator_profile=getattr(c, "validator_profile", ""),
                    validation_status=(res.status if res is not None else "none"),
                    validation_reasons=(list(res.reasons)
                                        if res is not None else []),
                    response_valid=bool(getattr(self, "_response_valid", False)),
                    apply_allowed=bool(getattr(self, "_apply_ok", False)),
                    copy_allowed=bool(getattr(self, "_copy_allowed", False)),
                    withheld=bool(res is not None and res.diagnostic_only),
                    from_cache=bool(from_cache),
                    profile=qa_mode.fake_provider_profile(),
                    response_excerpt=text,
                )
        except Exception:
            pass

    def _apply_response_gating(self) -> None:
        """Enable manuscript Apply (Replace/Insert/Append) only for valid,
        apply-eligible output; Copy only when allowed. Invalid output (planning
        leak / secret) can never be applied — for cached responses too."""
        apply_ok = getattr(self, "_apply_ok", True)
        copy_ok = getattr(self, "_copy_allowed", True)
        for btn in getattr(self, "_apply_buttons", []):
            if btn is getattr(self, "_copy_btn", None):
                btn.setEnabled(copy_ok)
            else:
                btn.setEnabled(apply_ok)

    def _on_error(self, error: str) -> None:
        self._response_output.setPlainText(f"Error:\n\n{error}")
        self._set_busy(False)
        self._worker = None

    def _set_busy(self, busy: bool) -> None:
        self._send_btn.setEnabled(not busy)
        self._ctx_source_combo.setEnabled(not busy)
        for btn in self._preset_buttons:
            btn.setEnabled(not busy)
        for btn in self._apply_buttons:
            btn.setEnabled(not busy)

    def _copy_response(self) -> None:
        if not getattr(self, "_copy_allowed", True):
            return
        text = self._response_output.toPlainText()
        if text:
            QApplication.clipboard().setText(text)

    # -- Apply to editor / scene -----------------------------------------------

    def _get_response_text(self) -> str | None:
        # Hard guard: never apply output the validator rejected (planning leak,
        # secret, hidden-context dump) — covers Replace/Insert/Append + outline.
        if not getattr(self, "_response_valid", True):
            return None
        text = self._response_output.toPlainText().strip()
        if not text or text == "Thinking..." or text.startswith("Error:"):
            return None
        return text

    def _notify_data_changed(self) -> None:
        # Primary path: emit through the project event bus. MainWindow
        # subscribes to project_data_changed and routes it through its
        # own _on_data_changed handler.
        from logosforge.project_events import emit_project_data_changed
        emit_project_data_changed()
        # Back-compat: also invoke the legacy callback so headless tests
        # and non-MainWindow hosts that pass a callback continue to work.
        if self._on_data_changed:
            self._on_data_changed()

    def _active_editor(self) -> object | None:
        if self._get_active_editor:
            return self._get_active_editor()
        return None

    def _apply_replace(self) -> None:
        text = self._get_response_text()
        if text is None:
            return

        # Outline Mode: the response is planning structure — route it through
        # the outline pipeline (parse/validate/apply as acts/chapters/scenes),
        # never into manuscript prose.
        if self._is_outline_mode():
            self._apply_to_outline()
            return

        editor = self._active_editor()
        if editor and hasattr(editor, "textCursor"):
            cursor = editor.textCursor()
            has_selection = cursor.hasSelection()
            what = "the selected text" if has_selection else "all text in the editor"
            answer = QMessageBox.question(
                self, "Replace",
                f"Replace {what} with the AI response?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
            if not has_selection:
                cursor.select(cursor.SelectionType.Document)
            cursor.insertText(text)
            editor.setTextCursor(cursor)
            self._notify_data_changed()
            return

        scene_id = self._get_auto_scene_id()
        if scene_id is not None:
            answer = QMessageBox.question(
                self, "Replace Scene Content",
                "Replace the entire scene content?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
            self._db.update_scene_content(scene_id, text)
            self._notify_data_changed()
            return

        QApplication.clipboard().setText(text)

    def _apply_insert(self) -> None:
        text = self._get_response_text()
        if text is None:
            return

        if self._is_outline_mode():
            self._apply_to_outline()
            return

        editor = self._active_editor()
        if editor and hasattr(editor, "textCursor"):
            answer = QMessageBox.question(
                self, "Insert Text",
                "Insert the AI response at the cursor position?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
            cursor = editor.textCursor()
            # Inserting at the caret can wedge the text against an adjacent
            # character (e.g. "patient.The dim glow"). Add a single separating
            # space only when a neighbour is non-whitespace — never at the start
            # of a block and never when whitespace already separates. (Block
            # boundaries / end-of-document return the U+2029 paragraph
            # separator, which str.isspace() treats as whitespace.)
            doc = editor.document()
            start = min(cursor.position(), cursor.anchor())
            end = max(cursor.position(), cursor.anchor())
            before_ch = doc.characterAt(start - 1) if start > 0 else ""
            after_ch = doc.characterAt(end)
            ins = text
            if before_ch and not before_ch.isspace() and not ins[:1].isspace():
                ins = " " + ins
            if after_ch and not after_ch.isspace() and not ins[-1:].isspace():
                ins = ins + " "
            cursor.insertText(ins)
            editor.setTextCursor(cursor)
            self._notify_data_changed()
            return

        QApplication.clipboard().setText(text)

    def _apply_append(self) -> None:
        text = self._get_response_text()
        if text is None:
            return

        if self._is_outline_mode():
            self._apply_to_outline()
            return

        editor = self._active_editor()
        if editor and hasattr(editor, "textCursor"):
            cursor = editor.textCursor()
            if cursor.hasSelection():
                end = max(cursor.position(), cursor.anchor())
                cursor.setPosition(end)
            else:
                cursor.movePosition(cursor.MoveOperation.End)
            cursor.insertText("\n\n" + text)
            editor.setTextCursor(cursor)
            self._notify_data_changed()
            return

        scene_id = self._get_auto_scene_id()
        if scene_id is not None:
            scene = self._db.get_scene_by_id(scene_id)
            if scene is not None:
                existing = scene.content or ""
                new_content = (existing + "\n\n" + text) if existing else text
                self._db.update_scene_content(scene_id, new_content)
                self._notify_data_changed()
                return

        QApplication.clipboard().setText(text)

    # -- Apply generated outline as structured nodes ---------------------------

    def propose_outline_ops(self):
        """Parse the current response into proposed outline operations.

        Returns (ops, count) or (None, 0) if there is no usable response.
        Pure — does not write anything.
        """
        text = self._get_response_text()
        if text is None:
            return None, 0
        from logosforge.outline_actions import (
            count_ops,
            parse_outline_response,
        )
        ops = parse_outline_response(text)
        return (ops, count_ops(ops)) if ops else (None, 0)

    def apply_outline_ops(self, ops, parent_id: int | None = None) -> list[int]:
        """Apply parsed ops to the Outline as Scenes (act/chapter/scene/beat).

        The visible Outline / Plot / Timeline are all scene-derived, so the
        structure is written as scenes through the normal scene service — not
        the orphaned OutlineNode table — then the section is refreshed.
        """
        from logosforge.outline_actions import apply_outline_as_scenes
        created = apply_outline_as_scenes(self._db, self._project_id, ops)
        if created:
            from logosforge.project_events import get_event_bus
            bus = get_event_bus()
            bus.scenes_changed.emit()
            bus.outline_changed.emit()
            bus.plot_changed.emit()
            bus.project_data_changed.emit()
            if self._on_data_changed:
                self._on_data_changed()
        return created

    def _apply_to_outline(self, *, confirm: bool = True) -> list[int]:
        """Outline Mode: propose the structure, validate/repair, confirm, apply."""
        ops, _n = self.propose_outline_ops()
        if not ops:
            return []
        from logosforge.outline_actions import (
            count_ops,
            format_outline_preview,
            repair_outline_ops,
            validate_outline_ops,
        )
        # Fill empty descriptions / trim prose, then reject unusable output so
        # nothing broken or prose-like is silently applied.
        ops, gen_warnings = repair_outline_ops(ops)
        ok, errors = validate_outline_ops(ops)
        if not ok:
            QMessageBox.warning(
                self, "Apply to Outline",
                "The generated outline can't be applied safely:\n\n• "
                + "\n• ".join(errors),
            )
            return []
        if confirm:
            from logosforge.ui.outline_confirm_dialog import OutlineConfirmDialog
            if not OutlineConfirmDialog.confirm(
                format_outline_preview(ops), count_ops(ops),
                title="Apply to Outline", warnings=gen_warnings, parent=self,
            ):
                return []
        return self.apply_outline_ops(ops)

    # -- Overlay mode ----------------------------------------------------------

    overlay_toggled = Signal(bool)

    def _toggle_overlay(self) -> None:
        self._overlay_mode = not self._overlay_mode
        self.overlay_toggled.emit(self._overlay_mode)
        self.refresh_style()

    def is_overlay(self) -> bool:
        return self._overlay_mode

    def closeEvent(self, event) -> None:
        # While undocked into its own top-level window, the OS close button
        # should re-dock the panel (the host re-parents it on overlay_toggled)
        # rather than destroy it.
        if self._overlay_mode:
            event.ignore()
            self._toggle_overlay()
            return
        super().closeEvent(event)

    def set_pinned_state(self, pinned: bool) -> None:
        """Reflect the dock's pin state on the header button (no re-emit)."""
        if self._pin_btn.isChecked() != pinned:
            self._pin_btn.blockSignals(True)
            self._pin_btn.setChecked(pinned)
            self._pin_btn.blockSignals(False)

    # -- Contextual dimming ----------------------------------------------------

    def dim_for_typing(self) -> None:
        if not self._typing_dimmed:
            self._typing_dimmed = True
            self.setWindowOpacity(0.7) if self._overlay_mode else None
            self.setStyleSheet(self._build_style(dimmed=True))

    def undim(self) -> None:
        if self._typing_dimmed:
            self._typing_dimmed = False
            self.setWindowOpacity(1.0) if self._overlay_mode else None
            self.setStyleSheet(self._build_style(dimmed=False))

    def refresh_style(self) -> None:
        self.setStyleSheet(self._build_style(dimmed=self._typing_dimmed))

    def _t(self, widget, style_fn):
        """Register a widget whose inline stylesheet depends on the theme and
        apply it now. apply_theme() re-runs every registered style_fn so the
        panel follows an Appearance change live (no recreation)."""
        self._themed_widgets.append((widget, style_fn))
        widget.setStyleSheet(style_fn())
        return widget

    def apply_theme(self) -> None:
        """Re-apply the current app theme to the panel and all of its themed
        child widgets (header, mode tabs, buttons, inputs, settings, response).
        Called on Appearance change so the Assistant updates without a restart.
        Safe to call repeatedly; never recreates the panel."""
        # 1. Panel container (background / border / scrollbars).
        self.refresh_style()
        # 2. Inline-styled children registered via _t (theme colours are read
        #    live, so re-running each style_fn picks up the new palette).
        for widget, style_fn in list(self._themed_widgets):
            try:
                widget.setStyleSheet(style_fn())
            except Exception:
                pass
        # 3. State-dependent button groups (their refreshers read the theme too).
        try:
            self._set_panel_mode(self._panel_mode)
            self._sync_structure_mode_buttons()
            self._sync_lambda_toggle()
        except Exception:
            pass
        # 4. Repolish so children styled purely by the global app stylesheet
        #    (combos, checkboxes, spin boxes, preset buttons) refresh too.
        for child in self.findChildren(QWidget):
            child.style().unpolish(child)
            child.style().polish(child)
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()

    def _build_style(self, dimmed: bool = False) -> str:
        opacity_rule = "opacity: 0.65;" if dimmed and not self._overlay_mode else ""
        if self._overlay_mode:
            return (
                f"#assistantPanel {{"
                f"  border-left: none;"
                f"  border: 1px solid {theme.BORDER};"
                f"  border-radius: 10px;"
                f"  background-color: {theme.BG_PANEL};"
                f"  {opacity_rule}"
                f"}}"
            )
        return (
            f"#assistantPanel {{"
            f"  border-left: 1px solid {theme.BORDER};"
            f"  background-color: {theme.BG_PANEL};"
            f"  {opacity_rule}"
            f"}}"
        )
