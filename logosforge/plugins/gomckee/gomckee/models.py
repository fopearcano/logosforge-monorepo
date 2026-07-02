from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set


DomainName = str


@dataclass(frozen=True)
class Method:
    id: str
    name: str
    goal: str
    rules: List[str]
    applies_to: Any
    priority: int


@dataclass(frozen=True)
class Trigger:
    id: str
    condition: str
    apply_methods: List[str]


@dataclass(frozen=True)
class Check:
    id: str
    applies_to: Any
    questions: List[str]


@dataclass(frozen=True)
class Conflict:
    method_a: str
    method_b: str
    resolution: str


@dataclass(frozen=True)
class DomainSystem:
    domain: str
    principles: List[Any]
    methods: Dict[str, Method]
    triggers: List[Trigger]
    checks: List[Check]
    conflicts: List[Conflict]
    meta: Dict[str, Any]


@dataclass
class RequestState:
    text: str
    normalized_text: str
    command: Optional[str]
    enabled: bool
    active_domains: List[str]
    forced_domains: Optional[List[str]]
    mode: str
    target_forms: Set[str]
    run_checks: bool
    explain: bool
    psyche: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DomainActivation:
    domain: str
    matched_triggers: List[str]
    activated_methods: List[str]
    methods: List[Method]
    checks: List[Check]


@dataclass
class CheckResult:
    domain: str
    check_id: str
    applies_to: Any
    status: str
    rationale: str
    questions: List[str]


@dataclass
class EngineResult:
    enabled: bool
    command_effect: Optional[str]
    active_domains: List[str]
    activations: List[DomainActivation]
    resolved_methods: Dict[str, List[Method]]
    checks: List[CheckResult]
    constraints: List[str]
    explanation: Optional[str]
    state_snapshot: Dict[str, Any]
