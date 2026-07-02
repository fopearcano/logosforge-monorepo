from __future__ import annotations

import re
from typing import Dict, List

from .models import Conflict, Method


class ConflictResolver:
    WIN_RE = re.compile(r"\b(M\d+)\s+wins\b", re.IGNORECASE)

    def resolve(self, methods: List[Method], conflicts: List[Conflict]) -> List[Method]:
        by_id = {method.id: method for method in methods}
        removed = set()

        for conflict in conflicts:
            if conflict.method_a not in by_id or conflict.method_b not in by_id:
                continue
            explicit = self.WIN_RE.search(conflict.resolution or "")
            if explicit:
                winner = explicit.group(1).upper()
                loser = conflict.method_b if winner == conflict.method_a else conflict.method_a
                removed.add(loser)
                continue

            a = by_id[conflict.method_a]
            b = by_id[conflict.method_b]
            loser = b.id if a.priority >= b.priority else a.id
            removed.add(loser)

        resolved = [method for method in methods if method.id not in removed]
        resolved.sort(key=lambda item: item.priority, reverse=True)
        return resolved
