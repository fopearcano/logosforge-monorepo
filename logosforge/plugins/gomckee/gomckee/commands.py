from __future__ import annotations

from typing import List, Optional, Tuple


VALID = {"on", "off", "story", "character", "dialogue", "all", "check", "explain"}


def parse_gomckee_command(text: str) -> Tuple[Optional[str], Optional[List[str]]]:
    text = (text or "").strip().lower()
    if not text.startswith("/gomckee"):
        return None, None
    parts = text.split()
    if len(parts) == 1:
        return "explain", None
    command = parts[1]
    if command not in VALID:
        return None, None
    if command == "story":
        return command, ["story"]
    if command == "character":
        return command, ["character"]
    if command == "dialogue":
        return command, ["dialogue"]
    if command == "all":
        return command, ["story", "character", "dialogue"]
    return command, None
