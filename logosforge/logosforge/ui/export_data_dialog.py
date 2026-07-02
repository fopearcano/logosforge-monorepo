"""Dialog for exporting structured story / project data.

Lets the user pick which sections to include, the output format (JSON /
Markdown / CSV) and field-level options, then hands an
:class:`~logosforge.data_export.ExportOptions` back to the caller.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
)

from logosforge.data_export import (
    ExportOptions,
    psyke_data_options,
    story_elements_options,
)

_FORMAT_LABELS = [("JSON", "json"), ("Markdown", "markdown"), ("CSV", "csv")]

# (attribute on ExportOptions, label) for each section checkbox.
_SECTIONS = [
    ("include_project_metadata", "Project metadata"),
    ("include_outline", "Outline"),
    ("include_plot", "Plot"),
    ("include_timeline", "Timeline"),
    ("include_scenes", "Manuscript / Scenes"),
    ("include_psyke_entries", "PSYKE entries"),
    ("include_psyke_relations", "PSYKE relations"),
    ("include_psyke_progressions", "PSYKE progressions"),
    ("include_notes", "Notes"),
]

_OPTIONS = [
    ("include_ids", "Include IDs"),
    ("include_internal_metadata", "Include internal metadata"),
    ("summaries_only", "Summaries only (omit full text)"),
]


class ExportDataDialog(QDialog):
    """Collect export sections / format / options from the user.

    *mode* is one of ``"story_elements"``, ``"psyke_data"`` or
    ``"full_project"`` and seeds the initial section selection.  In
    ``full_project`` mode the section checkboxes are locked on (a full export
    includes everything).
    """

    def __init__(self, mode: str = "story_elements", parent=None) -> None:
        super().__init__(parent)
        self._mode = mode
        self._section_checks: dict[str, QCheckBox] = {}
        self._option_checks: dict[str, QCheckBox] = {}

        titles = {
            "story_elements": "Export Story Elements",
            "psyke_data": "Export PSYKE Data",
            "full_project": "Export Full Project Data",
        }
        self.setWindowTitle(titles.get(mode, "Export Data"))
        self.setMinimumWidth(440)
        self._build_ui(self._initial_options())

    def _initial_options(self) -> ExportOptions:
        if self._mode == "psyke_data":
            return psyke_data_options()
        if self._mode == "full_project":
            opts = ExportOptions(
                include_scenes=True,
                include_ids=True,
                include_internal_metadata=True,
                export_type="full_project",
            )
            return opts
        return story_elements_options()

    def _build_ui(self, opts: ExportOptions) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(10)

        header = QLabel(self.windowTitle())
        header.setStyleSheet("font-size: 14px; font-weight: bold;")
        layout.addWidget(header)

        full = self._mode == "full_project"
        hint = QLabel(
            "Full project export includes everything and round-trips back "
            "through Import." if full else
            "Choose which sections and fields to include in the export."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #94a3b8; font-size: 11px;")
        layout.addWidget(hint)

        # -- Sections ------------------------------------------------------
        layout.addWidget(self._section_label("Sections"))
        grid = QGridLayout()
        grid.setHorizontalSpacing(18)
        grid.setVerticalSpacing(4)
        for i, (attr, label) in enumerate(_SECTIONS):
            cb = QCheckBox(label)
            cb.setChecked(getattr(opts, attr))
            if full:
                cb.setChecked(True)
                cb.setEnabled(False)
            self._section_checks[attr] = cb
            grid.addWidget(cb, i // 2, i % 2)
        layout.addLayout(grid)

        # -- Format --------------------------------------------------------
        layout.addWidget(self._section_label("Format"))
        fmt_row = QHBoxLayout()
        self._format_combo = QComboBox()
        for label, value in _FORMAT_LABELS:
            self._format_combo.addItem(label, userData=value)
        fmt_row.addWidget(self._format_combo)
        fmt_row.addStretch()
        layout.addLayout(fmt_row)

        # -- Options -------------------------------------------------------
        layout.addWidget(self._section_label("Options"))
        for attr, label in _OPTIONS:
            cb = QCheckBox(label)
            cb.setChecked(getattr(opts, attr))
            self._option_checks[attr] = cb
            layout.addWidget(cb)

        # -- Buttons -------------------------------------------------------
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Export")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @staticmethod
    def _section_label(text: str) -> QLabel:
        label = QLabel(text)
        label.setStyleSheet(
            "color: #cbd5e1; font-size: 11px; font-weight: bold; padding-top: 4px;"
        )
        return label

    # -- Public API --------------------------------------------------------

    def selected_format(self) -> str:
        return self._format_combo.currentData()

    def get_options(self) -> ExportOptions:
        opts = self._initial_options()
        for attr, cb in self._section_checks.items():
            setattr(opts, attr, cb.isChecked())
        for attr, cb in self._option_checks.items():
            setattr(opts, attr, cb.isChecked())
        opts.fmt = self.selected_format()
        opts.export_type = (
            "full_project" if self._mode == "full_project"
            else "psyke_data" if self._mode == "psyke_data"
            else "story_elements"
        )
        return opts
