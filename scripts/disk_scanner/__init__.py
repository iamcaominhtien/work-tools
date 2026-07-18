"""Disk Scanner: A high-performance recursive disk usage scanner."""

from .core import scan_directory
from .main import main

__all__ = ["scan_directory", "main"]
