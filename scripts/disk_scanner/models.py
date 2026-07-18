"""Data models for disk scanner."""

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class FileNode:
    """Represents a node in the file system tree (either file or directory)."""

    name: str
    path: str
    size: int = 0
    is_dir: bool = False
    children: List["FileNode"] = field(default_factory=list)
    file_count: int = 0
    dir_count: int = 0
    error: Optional[str] = None

    def sorted_children(self) -> List["FileNode"]:
        """Returns children sorted by size descending."""
        return sorted(self.children, key=lambda n: n.size, reverse=True)


class ScanStats:
    """Statistics collector for directory scanning."""

    def __init__(self) -> None:
        """Initialize scan statistics variables."""
        self.total_files = 0
        self.total_dirs = 0
        self.total_size = 0
        self.errors = 0
        self.scanned_items = 0
