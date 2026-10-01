"""Typed, project-scoped plans for the HTTP PSYKE Console.

Planning is deliberately read-only.  Execution accepts only an opaque plan id,
never a caller-supplied action payload, so the previewed operation is the one
that runs.  Plans are short-lived, tied to one ``Database`` instance and one
project, and consumed at most once.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from secrets import token_urlsafe
from threading import Lock
from time import monotonic
from typing import Literal
from weakref import ref

from logosforge.db import Database
from logosforge.psyke_command_registry import CommandRegistry
from logosforge.psyke_commands import CommandType, parse
from logosforge.psyke_system_commands import SystemCommandHandlers

ConsoleAction = Literal[
    "create_psyke_entry",
    "open_scene",
    "open_psyke_entry",
]
ConsoleTarget = Literal["scene", "psyke_entry"]

PLAN_TTL_SECONDS = 120.0
MAX_PENDING_PLANS = 256
_ENTRY_TYPES = frozenset({"character", "place", "object", "lore", "theme", "other"})


class CommandPlanInputError(ValueError):
    """The requested command cannot be represented by this safe planner."""


class CommandPlanNotFoundError(LookupError):
    """The opaque plan id is absent, expired, or belongs to another project."""


class CommandPlanConflictError(RuntimeError):
    """The frozen target changed after planning and must be planned again."""


class CommandPlanAmbiguousError(CommandPlanConflictError):
    """An exact name or alias identifies more than one in-project entry."""


class CommandPlanConfirmationError(PermissionError):
    """A mutating plan was executed without explicit confirmation."""


@dataclass(frozen=True)
class ConsoleCommandPlan:
    plan_id: str
    command: str
    normalized_command: str
    action: ConsoleAction
    summary: str
    effects: tuple[str, ...]
    requires_confirmation: bool
    mutates: bool
    target_type: ConsoleTarget
    target_id: int | None
    expires_at: datetime


@dataclass(frozen=True)
class ConsoleCommandExecution:
    ok: bool
    action: ConsoleAction
    message: str
    mutated: bool
    target_type: ConsoleTarget
    target_id: int


@dataclass(frozen=True)
class _StoredPlan:
    public: ConsoleCommandPlan
    payload: dict[str, object]
    expires_monotonic: float


class PsykeCommandPlanService:
    """Create and execute deterministic plans for one database instance."""

    def __init__(
        self,
        db: Database,
        *,
        ttl_seconds: float = PLAN_TTL_SECONDS,
        clock: Callable[[], float] = monotonic,
        utcnow: Callable[[], datetime] | None = None,
    ) -> None:
        self._db_ref = ref(db)
        self._ttl_seconds = max(float(ttl_seconds), 0.001)
        self._clock = clock
        self._utcnow = utcnow or (lambda: datetime.now(timezone.utc))
        self._plans: dict[str, _StoredPlan] = {}
        self._lock = Lock()

    def _db(self) -> Database:
        database = self._db_ref()
        if database is None:
            raise CommandPlanNotFoundError("Command plan is no longer available. Preview it again.")
        return database

    def create_plan(
        self,
        project_id: int,
        raw_command: str,
        *,
        active_scene_id: int | None = None,
    ) -> ConsoleCommandPlan:
        db = self._db()
        raw = raw_command.strip()
        if not raw:
            raise CommandPlanInputError("Type a slash command to preview it.")
        if len(raw) > 500:
            raise CommandPlanInputError("Command is too long (maximum 500 characters).")

        registry = CommandRegistry()
        SystemCommandHandlers(db, project_id).register_all(registry)
        parsed = parse(raw, registry)
        if parsed.kind is CommandType.SEARCH:
            raise CommandPlanInputError("Only slash commands can be planned. Start with '/'.")
        if parsed.kind is not CommandType.SYSTEM:
            raise CommandPlanInputError(
                "Entity actions are not executable yet. Use /open psyke <name>."
            )

        registered = registry.resolve(parsed.command)
        command = registered.name if registered is not None else parsed.command
        if command == "create":
            plan, payload = self._plan_create(project_id, parsed.args)
        elif command == "open":
            plan, payload = self._plan_open(project_id, parsed.args)
        elif command == "go":
            plan, payload = self._plan_go(project_id, parsed.args, active_scene_id)
        else:
            raise CommandPlanInputError(
                f"/{command} is not available in the safe command pipeline yet."
            )

        project = db.get_project_by_id(project_id)
        if project is None:
            raise CommandPlanInputError("The command project is no longer available.")
        payload["project_created_at"] = project.created_at.isoformat()

        now = self._clock()
        expires_at = self._utcnow() + timedelta(seconds=self._ttl_seconds)
        public = ConsoleCommandPlan(
            plan_id=f"lfcp_{token_urlsafe(24)}",
            command=command,
            normalized_command=plan["normalized_command"],
            action=plan["action"],
            summary=plan["summary"],
            effects=tuple(plan["effects"]),
            requires_confirmation=bool(plan["requires_confirmation"]),
            mutates=bool(plan["mutates"]),
            target_type=plan["target_type"],
            target_id=plan["target_id"],
            expires_at=expires_at,
        )
        with self._lock:
            self._prune_locked(now)
            while len(self._plans) >= MAX_PENDING_PLANS:
                self._plans.pop(next(iter(self._plans)))
            self._plans[public.plan_id] = _StoredPlan(
                public=public,
                payload=payload,
                expires_monotonic=now + self._ttl_seconds,
            )
        return public

    def execute_plan(
        self,
        project_id: int,
        plan_id: str,
        *,
        confirmed: bool,
    ) -> ConsoleCommandExecution:
        """Consume and execute a frozen plan at most once.

        The lock covers consumption and the short database operation.  That
        makes two concurrent execute requests unable to run the same plan.
        """
        now = self._clock()
        with self._lock:
            self._prune_locked(now)
            stored = self._plans.get(plan_id)
            if stored is None or stored.payload.get("project_id") != project_id:
                raise CommandPlanNotFoundError(
                    "Command plan was not found or has expired. Preview it again."
                )
            if stored.public.requires_confirmation and not confirmed:
                raise CommandPlanConfirmationError(
                    "Explicit confirmation is required before this command can change the project."
                )
            # Consume before touching the database.  A transport retry can never
            # replay a successfully committed operation with the same plan id.
            self._plans.pop(plan_id, None)
            return self._execute_locked(stored)

    def _plan_create(self, project_id: int, args: list[str]):
        if len(args) < 2:
            raise CommandPlanInputError("Usage: /create <type> <name>")
        entry_type = args[0].lower()
        if entry_type not in _ENTRY_TYPES:
            choices = ", ".join(sorted(_ENTRY_TYPES))
            raise CommandPlanInputError(
                f"Unknown PSYKE type '{args[0]}'. Use one of: {choices}."
            )
        name = " ".join(args[1:]).strip()
        if not name:
            raise CommandPlanInputError("A name is required. Usage: /create <type> <name>")
        if len(name) > 200:
            raise CommandPlanInputError("PSYKE entry name is too long (maximum 200 characters).")

        existing = self._find_exact_entry(project_id, name, entry_type)
        if existing is not None:
            normalized = f"/create {entry_type} {existing.name}"
            return {
                "normalized_command": normalized,
                "action": "open_psyke_entry",
                "summary": f"Open existing {entry_type} '{existing.name}'",
                "effects": (
                    "No duplicate will be created.",
                    f"Open PSYKE entry #{existing.id} in this project.",
                ),
                "requires_confirmation": False,
                "mutates": False,
                "target_type": "psyke_entry",
                "target_id": existing.id,
            }, {
                "project_id": project_id,
                "entry_id": existing.id,
                "entry_name": existing.name,
                "entry_type": existing.entry_type,
            }

        normalized = f"/create {entry_type} {name}"
        return {
            "normalized_command": normalized,
            "action": "create_psyke_entry",
            "summary": f"Create {entry_type} '{name}'",
            "effects": (
                f"Add one {entry_type} entry named '{name}' to this project's PSYKE Bible.",
                "Open the resulting entry after creation.",
            ),
            "requires_confirmation": True,
            "mutates": True,
            "target_type": "psyke_entry",
            "target_id": None,
        }, {
            "project_id": project_id,
            "entry_type": entry_type,
            "name": name,
        }

    def _plan_open(self, project_id: int, args: list[str]):
        if len(args) < 2:
            raise CommandPlanInputError("Usage: /open scene <id> | /open psyke <name>")
        target = args[0].lower()
        if target == "scene":
            if len(args) != 2:
                raise CommandPlanInputError("Usage: /open scene <id>")
            scene_id = self._positive_int(args[1], "scene id")
            return self._scene_navigation_plan(project_id, scene_id, command="open")
        if target == "psyke":
            query = " ".join(args[1:]).strip()
            entry = self._resolve_exact_entry(project_id, query)
            if entry is None:
                raise CommandPlanInputError(f"No PSYKE entry matches '{query}'.")
            normalized = f"/open psyke {entry.name}"
            return {
                "normalized_command": normalized,
                "action": "open_psyke_entry",
                "summary": f"Open PSYKE entry '{entry.name}'",
                "effects": (f"Open {entry.entry_type} entry #{entry.id}; project data will not change.",),
                "requires_confirmation": False,
                "mutates": False,
                "target_type": "psyke_entry",
                "target_id": entry.id,
            }, {
                "project_id": project_id,
                "entry_id": entry.id,
                "entry_name": entry.name,
                "entry_type": entry.entry_type,
            }
        raise CommandPlanInputError("Unknown open target. Use 'scene' or 'psyke'.")

    def _plan_go(
        self,
        project_id: int,
        args: list[str],
        active_scene_id: int | None,
    ):
        if len(args) != 2 or args[0].lower() != "scene":
            raise CommandPlanInputError("Usage: /go scene next|previous|<id>")
        direction = args[1].lower()
        if direction not in {"next", "previous", "prev"}:
            scene_id = self._positive_int(args[1], "scene id")
            return self._scene_navigation_plan(project_id, scene_id, command="go")
        if active_scene_id is None:
            raise CommandPlanInputError("Select a scene before using relative scene navigation.")

        scenes = self._db().get_all_scenes(project_id)
        ids = [scene.id for scene in scenes]
        try:
            index = ids.index(active_scene_id)
        except ValueError as exc:
            raise CommandPlanInputError(
                "The active scene does not belong to this project. Select a scene and try again."
            ) from exc
        next_index = (
            min(index + 1, len(scenes) - 1)
            if direction == "next"
            else max(index - 1, 0)
        )
        target = scenes[next_index]
        normalized_direction = "previous" if direction == "prev" else direction
        boundary = next_index == index
        if boundary:
            boundary_name = "last" if direction == "next" else "first"
            raise CommandPlanInputError(
                f"Scene #{target.id} is already the {boundary_name} scene in this project."
            )
        summary = f"Open {normalized_direction} scene #{target.id} '{target.title}'"
        return {
            "normalized_command": f"/go scene {normalized_direction}",
            "action": "open_scene",
            "summary": summary,
            "effects": (f"Open scene #{target.id}; project data will not change.",),
            "requires_confirmation": False,
            "mutates": False,
            "target_type": "scene",
            "target_id": target.id,
        }, {
            "project_id": project_id,
            "scene_id": target.id,
            "source_scene_id": active_scene_id,
            "scene_order": tuple(ids),
        }

    def _scene_navigation_plan(self, project_id: int, scene_id: int, *, command: str):
        scene = self._db().get_scene_by_id(scene_id)
        if scene is None or scene.project_id != project_id:
            raise CommandPlanInputError(f"Scene {scene_id} was not found in this project.")
        return {
            "normalized_command": f"/{command} scene {scene_id}",
            "action": "open_scene",
            "summary": f"Open scene #{scene.id} '{scene.title}'",
            "effects": (f"Open scene #{scene.id}; project data will not change.",),
            "requires_confirmation": False,
            "mutates": False,
            "target_type": "scene",
            "target_id": scene.id,
        }, {
            "project_id": project_id,
            "scene_id": scene.id,
        }

    def _execute_locked(self, stored: _StoredPlan) -> ConsoleCommandExecution:
        db = self._db()
        plan = stored.public
        project_id = int(stored.payload["project_id"])
        project = db.get_project_by_id(project_id)
        if project is None or project.created_at.isoformat() != stored.payload.get("project_created_at"):
            raise CommandPlanConflictError(
                "The planned project is no longer available. Preview the command again."
            )
        if plan.action == "create_psyke_entry":
            name = str(stored.payload["name"])
            entry_type = str(stored.payload["entry_type"])
            existing = self._find_exact_entry(project_id, name, entry_type)
            entry = existing or db.create_psyke_entry(
                project_id,
                name=name,
                entry_type=entry_type,
            )
            created = existing is None
            message = (
                f"Created {entry_type} '{entry.name}' and opened it in PSYKE."
                if created
                else f"'{entry.name}' already existed; opened the existing PSYKE entry."
            )
            return ConsoleCommandExecution(
                ok=True,
                action=plan.action,
                message=message,
                mutated=created,
                target_type="psyke_entry",
                target_id=entry.id,
            )

        if plan.action == "open_scene":
            scene_id = int(stored.payload["scene_id"])
            expected_order = stored.payload.get("scene_order")
            if expected_order is not None:
                actual_order = tuple(
                    scene.id for scene in db.get_all_scenes(project_id)
                )
                if actual_order != expected_order:
                    raise CommandPlanConflictError(
                        "Scene order changed after this relative navigation was previewed. "
                        "Preview the command again."
                    )
            scene = db.get_scene_by_id(scene_id)
            if scene is None or scene.project_id != project_id:
                raise CommandPlanConflictError(
                    "The planned scene is no longer available. Preview the command again."
                )
            return ConsoleCommandExecution(
                ok=True,
                action=plan.action,
                message=f"Opened scene #{scene.id} '{scene.title}'.",
                mutated=False,
                target_type="scene",
                target_id=scene.id,
            )

        entry_id = int(stored.payload["entry_id"])
        entry = db.get_psyke_entry_by_id(entry_id)
        if (
            entry is None
            or entry.project_id != project_id
            or entry.name != stored.payload.get("entry_name")
            or entry.entry_type != stored.payload.get("entry_type")
        ):
            raise CommandPlanConflictError(
                "The planned PSYKE entry changed or is no longer available. "
                "Preview the command again."
            )
        return ConsoleCommandExecution(
            ok=True,
            action=plan.action,
            message=f"Opened PSYKE entry '{entry.name}'.",
            mutated=False,
            target_type="psyke_entry",
            target_id=entry.id,
        )

    def _find_exact_entry(self, project_id: int, name: str, entry_type: str):
        folded_name = name.casefold()
        folded_type = entry_type.casefold()
        return next(
            (
                entry
                for entry in self._db().get_all_psyke_entries(project_id)
                if entry.name.casefold() == folded_name
                and entry.entry_type.casefold() == folded_type
            ),
            None,
        )

    def _resolve_exact_entry(self, project_id: int, query: str):
        folded = query.strip().casefold()
        matches = []
        for entry in self._db().get_all_psyke_entries(project_id):
            candidates = [entry.name]
            candidates.extend(entry.aliases.split(",") if entry.aliases else [])
            if any(candidate.strip().casefold() == folded for candidate in candidates):
                matches.append(entry)
        if len(matches) > 1:
            names = ", ".join(sorted(entry.name for entry in matches))
            raise CommandPlanAmbiguousError(
                f"'{query}' matches more than one PSYKE entry: {names}. Use a unique exact name."
            )
        return matches[0] if matches else None

    @staticmethod
    def _positive_int(raw: str, label: str) -> int:
        try:
            value = int(raw)
        except ValueError as exc:
            raise CommandPlanInputError(f"Invalid {label} '{raw}'. Use a positive number.") from exc
        if value < 1:
            raise CommandPlanInputError(f"Invalid {label} '{raw}'. Use a positive number.")
        return value

    def _prune_locked(self, now: float) -> None:
        expired = [
            plan_id
            for plan_id, stored in self._plans.items()
            if stored.expires_monotonic <= now
        ]
        for plan_id in expired:
            self._plans.pop(plan_id, None)
