"""Conservative, named repairs for known converter-specific DXF output."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

_GROUP_CODE = re.compile(rb"^[ \t]*([0-9]{1,4})[ \t]*$")
_MTEXT_CODES = frozenset({1, 3})
_MTEXT_CHUNK_BYTES = 250

_Tag = tuple[bytes, int, bytes, bool]
_Rule = Callable[[bytes], tuple[bytes, bool]]


@dataclass(frozen=True)
class NormalizationResult:
    """Normalized DXF content and the rules that changed it."""

    content: bytes
    applied_rules: tuple[str, ...]


class DxfNormalizer:
    """Apply conservative repairs for recognized DXF converter defects."""

    def __init__(self) -> None:
        """Initialize the ordered normalization rules."""
        self._rules: tuple[tuple[str, _Rule], ...] = (
            ("mtext_fixed_width_wrap", _repair_mtext_wrap),
        )

    def normalize(self, content: bytes) -> NormalizationResult:
        """Return normalized content without changing unrecognized input."""
        applied: list[str] = []
        for name, rule in self._rules:
            content, changed = rule(content)
            if changed:
                applied.append(name)
        return NormalizationResult(content, tuple(applied))


def _repair_mtext_wrap(content: bytes) -> tuple[bytes, bool]:
    lines = content.splitlines()
    tags: list[_Tag] = []
    index = 0
    in_mtext = False
    changed = False

    while index < len(lines):
        match = _GROUP_CODE.fullmatch(lines[index])
        if match is None or index + 1 >= len(lines):
            return content, False
        code_line = lines[index]
        code = int(match.group(1))
        value = lines[index + 1]
        index += 2

        if code == 0:
            in_mtext = value.strip().upper() == b"MTEXT"

        repaired = False
        if in_mtext and code in _MTEXT_CODES and len(value) == 255:
            continuation: list[bytes] = []
            while index < len(lines) and _GROUP_CODE.fullmatch(lines[index]) is None:
                continuation.append(lines[index])
                index += 1
            if continuation:
                value += b"".join(continuation)
                repaired = True
                changed = True
        tags.append((code_line, code, value, repaired))

    if not changed:
        return content, False

    normalized: list[tuple[bytes, bytes]] = []
    index = 0
    in_mtext = False
    while index < len(tags):
        code_line, code, value, repaired = tags[index]
        if code == 0:
            in_mtext = value.strip().upper() == b"MTEXT"

        if in_mtext and code in _MTEXT_CODES:
            end = index
            while end < len(tags) and tags[end][1] in _MTEXT_CODES:
                end += 1
            text_tags = tags[index:end]
            if any(tag[3] for tag in text_tags):
                chunks = _split_utf8_chunks(b"".join(tag[2] for tag in text_tags))
                if chunks is None:
                    return content, False
                normalized.extend(
                    (f"{tag_code:>3}".encode("ascii"), chunk)
                    for tag_code, chunk in [
                        *((3, chunk) for chunk in chunks[:-1]),
                        (1, chunks[-1]),
                    ]
                )
                index = end
                continue

        normalized.append((code_line, value))
        index += 1

    newline = b"\r\n" if b"\r\n" in content else b"\n"
    output = newline.join(line for pair in normalized for line in pair)
    if content.endswith((b"\n", b"\r")):
        output += newline
    return output, True


def _split_utf8_chunks(value: bytes) -> list[bytes] | None:
    try:
        text = value.decode("utf-8")
    except UnicodeDecodeError:
        return None

    chunks: list[bytes] = []
    current = bytearray()
    for character in text:
        encoded = character.encode("utf-8")
        if current and len(current) + len(encoded) > _MTEXT_CHUNK_BYTES:
            chunks.append(bytes(current))
            current.clear()
        current.extend(encoded)
    if current or not chunks:
        chunks.append(bytes(current))
    return chunks
