"""Utility functions and classes for disk scanner formatting and colors."""

import sys

UNITS = ["B", "KB", "MB", "GB", "TB", "PB"]


def human_size(num_bytes: float) -> str:
    """Format bytes into a human-readable string (e.g., KiB, MiB)."""
    if num_bytes < 0:
        num_bytes = 0
    size = float(num_bytes)
    for unit in UNITS:
        if size < 1024.0 or unit == UNITS[-1]:
            return f"{int(size)} {unit}" if unit == "B" else f"{size:.2f} {unit}"
        size /= 1024.0
    return f"{size:.2f} PB"


def parse_size(text: str) -> int:
    """Parse a size string (e.g., '10MB', '1GB') into bytes."""
    text = text.strip().upper()
    multipliers = {"B": 1, "KB": 1024, "MB": 1024**2, "GB": 1024**3, "TB": 1024**4}
    for suffix, mult in sorted(multipliers.items(), key=lambda x: -len(x[0])):
        if text.endswith(suffix):
            num_part = text[: -len(suffix)].strip()
            try:
                return int(float(num_part) * mult)
            except ValueError:
                pass
    try:
        return int(text)
    except ValueError:
        return 0


def make_bar(percent: float, width: int = 20) -> str:
    """Create a text progress bar representing a percentage."""
    filled = max(0, min(width, int(round(width * percent / 100.0))))
    return "█" * filled + "░" * (width - filled)


class Color:
    """ANSI color codes for console highlighting."""

    ENABLED = sys.stdout.isatty()
    RESET = "\033[0m" if ENABLED else ""
    BOLD = "\033[1m" if ENABLED else ""
    DIM = "\033[2m" if ENABLED else ""
    RED = "\033[31m" if ENABLED else ""
    GREEN = "\033[32m" if ENABLED else ""
    YELLOW = "\033[33m" if ENABLED else ""
    BLUE = "\033[34m" if ENABLED else ""
    MAGENTA = "\033[35m" if ENABLED else ""
    CYAN = "\033[36m" if ENABLED else ""

    @staticmethod
    def wrap(text: str, color: str) -> str:
        """Wrap text with terminal colors if color is enabled."""
        return f"{color}{text}{Color.RESET}" if Color.ENABLED else text


def size_color(num_bytes: int) -> str:
    """Return matching color based on the size category."""
    if num_bytes >= 1024**3:
        return Color.RED
    elif num_bytes >= 100 * 1024**2:
        return Color.YELLOW
    elif num_bytes >= 10 * 1024**2:
        return Color.CYAN
    return Color.GREEN
