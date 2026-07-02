"""Strip a leaked grounding-context preamble from a Logos model reply.

Logos injects an internal grounding block ("[PSYKE Context] ... Entries: ...")
so the model is well-grounded. Instruction-weak / uncensored models sometimes
echo that block — plus a self-invented header ("Expanded text:") — as a *leading*
preamble before the real transformed text, e.g.::

    [PSYKE Context]

    Entries:
    - Mara (character)

    Expanded text:

    She turned up the gain, and the static resolved into a single voice.

The main ``/assistant/chat`` path REJECTS such output wholesale
(:func:`logosforge.assistant_contract.validate`). Logos is an inline, advisory
layer where the useful text is worth keeping, so here we instead STRIP the leaked
*leading* preamble and keep the real content.

CRITICAL design choice: we engage **only** when the reply *leads with* an echoed
grounding block — detected by a STANDALONE bracketed head line ("[PSYKE Context]"
on its own line), never by a bare substring. So legitimate grounded advice that
naturally mentions "psyke", "memory", "ai mode", or even opens with a "[Memory]
of her mother..." aside is left completely untouched. The only withhold case is a
reply that is *nothing but* a leaked block.
"""

from __future__ import annotations

import re

# A leaked grounding block opens with a STANDALONE bracketed head on its own line:
# "[PSYKE Context]", "[Global Story Memory]", "[AI Mode: Balance]", "[Memory]".
# The WHOLE line must be the bracketed label (closing bracket at line end), so a
# legitimate aside like "[Memory] of her mother flooded back." is NOT matched.
_CONTEXT_HEAD_RX = re.compile(
    r"^\s*\[(?:psyke context|global story memory|ai mode[^\]]*|memory)\]\s*$",
    re.IGNORECASE,
)

# Whole-line section labels that make up the injected grounding block
# (context_builder / orchestration emit these "Label:" lines).
_GROUNDING_LABEL_RX = re.compile(
    r"^\s*(?:global|characters?|entries|entry|relations?|relationships?|latest|"
    r"scene|scenes|outline|notes?|setup|payoff|progressions?|memory|context|"
    r"temporal|world|places?|objects?|lore|themes?)\s*:\s*$",
    re.IGNORECASE,
)

# A model-invented throat-clearing header that introduces the real output after an
# echoed block, e.g. "Expanded text:", "Here is the rewrite:", "Output:".
# Deliberately NARROW: it does NOT match the labels actions legitimately require
# ("Expanded version:", "Compressed version:", "Option 1:"), so those survive.
_OUTPUT_HEADER_RX = re.compile(
    r"^\s*(?:"
    r"here(?:\s+is|'s)\b[\w\s,'-]*?:"
    r"|(?:expanded|rewritten|revised|improved|condensed|compressed)\s+text\s*:"
    r"|rewritten\s*:"
    r"|output\s*:|result\s*:|response\s*:"
    r")\s*$",
    re.IGNORECASE,
)


def _is_bullet(s: str) -> bool:
    return s[:2] in ("- ", "* ", "• ") or s.startswith("•")


def leads_with_context_head(reply: str) -> bool:
    """True iff the reply's first non-blank line is a standalone grounding head."""
    for line in reply.splitlines():
        if not line.strip():
            continue
        return bool(_CONTEXT_HEAD_RX.match(line))
    return False


def strip_leaked_preamble(reply: str) -> str:
    """If the reply LEADS with an echoed grounding block, drop that block and keep
    the real content after it. Returns *reply* unchanged when there is no leading
    grounding head; returns ``""`` when the reply was nothing but a leaked block."""
    lines = reply.splitlines()
    first = 0
    while first < len(lines) and not lines[first].strip():
        first += 1
    if first >= len(lines) or not _CONTEXT_HEAD_RX.match(lines[first]):
        return reply
    n = len(lines)

    # Prefer cutting at a model-invented output header — a clean boundary. Search
    # only across the grounding structure; stop at the first clearly-real line so
    # we never mistake a sentence deep in the content for a header.
    for j in range(first + 1, n):
        if _OUTPUT_HEADER_RX.match(lines[j]):
            k = j + 1
            while k < n and not lines[k].strip():
                k += 1
            return "\n".join(lines[k:]).strip()
        s = lines[j].strip()
        if s and not _GROUNDING_LABEL_RX.match(lines[j]) and not _is_bullet(s):
            break

    # No output header: consume the head + grounding-structure lines (blanks, known
    # section labels, and the bullets directly under them). A bullet or any line
    # that appears AFTER a blank gap following grounding structure is real output,
    # not grounding — so a list reply separated from the echo by a blank survives.
    idx = first + 1
    gap_after_structure = False
    while idx < n:
        s = lines[idx].strip()
        if not s:
            gap_after_structure = True
            idx += 1
            continue
        if _GROUNDING_LABEL_RX.match(lines[idx]):
            gap_after_structure = False
            idx += 1
            continue
        if _is_bullet(s) and not gap_after_structure:
            idx += 1
            continue
        break  # real content
    while idx < n and not lines[idx].strip():
        idx += 1
    return "\n".join(lines[idx:]).strip()


def sanitize_logos_reply(reply: str) -> tuple[str, bool]:
    """Sanitize a raw Logos model reply.

    Returns ``(clean_reply, withheld)``:

    * no leading grounding-block leak -> ``(reply, False)`` (unchanged — incl. any
      reply that merely *mentions* psyke/memory/etc. in ordinary prose)
    * leading leak with real text     -> ``(stripped_text, False)``
    * leading leak with nothing left  -> ``("", True)`` (caller shows a notice)
    """
    if not leads_with_context_head(reply):
        return reply, False
    cleaned = strip_leaked_preamble(reply)
    if not cleaned.strip():
        return "", True
    return cleaned, False
