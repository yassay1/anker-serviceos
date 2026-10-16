"""Chunking strategies for the knowledge pipeline.

Concept-ported from the reference project (SplitType registry, parent/child
markdown chunks, row-never-split tables) onto dependency-free Python. Parents
carry ``skip_embedding`` and exist only to expand child hits at retrieval time.
"""

from dataclasses import dataclass, field
import re

MARKDOWN_CHUNK_CHARS = 1200
MARKDOWN_OVERLAP_CHARS = 120
_HEADER = re.compile(r"^(#{1,4})\s+(.*)$")


@dataclass(frozen=True)
class Chunk:
    title: str
    content: str
    parent: bool = False
    attrs: dict = field(default_factory=dict)
    image: bool = False


def _paragraphs(text: str) -> list[str]:
    return [" ".join(part.split()) for part in re.split(r"\n\s*\n", text) if part.strip()]


def _window_paragraphs(paragraphs: list[str], limit: int, overlap: int) -> list[str]:
    windows: list[str] = []
    current: list[str] = []
    size = 0
    for paragraph in paragraphs:
        if len(paragraph) > limit:
            if current:
                windows.append("\n".join(current))
                current, size = [], 0
            for start in range(0, len(paragraph), max(limit - overlap, 1)):
                windows.append(paragraph[start:start + limit])
            continue
        if size + len(paragraph) > limit and current:
            windows.append("\n".join(current))
            carried = []
            carried_size = 0
            for tail in reversed(current):
                if carried_size + len(tail) > overlap:
                    break
                carried.insert(0, tail)
                carried_size += len(tail)
            current, size = carried, carried_size
        current.append(paragraph)
        size += len(paragraph)
    if current:
        windows.append("\n".join(current))
    return windows


def split_markdown_header(text: str, base_title: str) -> list[Chunk]:
    """Sections become parents (only when they need children); children are embedded."""
    sections: list[tuple[str, list[str]]] = []
    current_title, current_lines = base_title, []
    for line in text.splitlines():
        match = _HEADER.match(line.strip())
        if match:
            if current_lines or current_title != base_title:
                sections.append((current_title, current_lines))
            current_title, current_lines = match.group(2).strip(), []
        else:
            current_lines.append(line)
    sections.append((current_title, current_lines))
    chunks: list[Chunk] = []
    for title, lines in sections:
        body = "\n".join(lines).strip()
        if not body:
            continue
        if len(body) <= MARKDOWN_CHUNK_CHARS:
            chunks.append(Chunk(title=title or base_title, content=" ".join(body.split())))
            continue
        parent = Chunk(title=title or base_title, content=" ".join(body.split()), parent=True)
        chunks.append(parent)
        for window in _window_paragraphs(_paragraphs(body), MARKDOWN_CHUNK_CHARS, MARKDOWN_OVERLAP_CHARS):
            chunks.append(Chunk(title=title or base_title, content=window))
    return chunks


def split_length(text: str, base_title: str) -> list[Chunk]:
    return [Chunk(title=base_title, content=window)
            for window in _window_paragraphs(_paragraphs(text), MARKDOWN_CHUNK_CHARS, MARKDOWN_OVERLAP_CHARS)]


def split_rows(rows: list[tuple[str, str]]) -> list[Chunk]:
    """Row-mode chunks: one self-contained segment per source row; rows never split."""
    return [Chunk(title=title, content=content) for title, content in rows if content.strip()]
