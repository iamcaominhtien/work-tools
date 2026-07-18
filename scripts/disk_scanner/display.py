"""Display utilities for tree printing, summary reporting, and tables."""

import os
from loguru import logger

from . import core
from .models import FileNode, ScanStats
from .utils import human_size, make_bar


def print_tree(
    node: FileNode,
    root_size: int,
    prefix: str = "",
    depth: int = 0,
    max_depth: int = 2,
    top_n: int = 10,
    is_last: bool = True,
    is_root: bool = True,
) -> None:
    """Print the directory structure recursively as a console tree."""
    icon = "📁" if node.is_dir else "📄"
    percent = (node.size / root_size * 100) if root_size > 0 else 0
    size_str = f"{human_size(node.size):>10}"
    pct_str = f"{percent:5.1f}%"
    label = node.name

    if is_root:
        print(f"{icon} {label}  {size_str}  ({pct_str})")
    else:
        connector = "└── " if is_last else "├── "
        line = f"{prefix}{connector}{icon} {label}  {size_str}  ({pct_str})"
        if node.error:
            line += f"  ⚠ {node.error}"
        print(line)

    if node.error:
        return
    if depth >= max_depth:
        if node.is_dir and (node.dir_count + node.file_count) > 0:
            child_prefix = prefix + ("    " if is_last else "│   ")
            print(
                f"{child_prefix}└── ... (ẩn {len(node.children)} mục con, đạt giới hạn độ sâu)"
            )
        return

    children = node.sorted_children()
    shown = children[:top_n]
    hidden = children[top_n:]
    child_prefix = prefix + ("    " if is_last else "│   ") if not is_root else ""

    for i, child in enumerate(shown):
        last = (i == len(shown) - 1) and not hidden
        print_tree(
            child,
            root_size,
            child_prefix,
            depth + 1,
            max_depth,
            top_n,
            last,
            is_root=False,
        )

    if hidden:
        hidden_size = sum(c.size for c in hidden)
        print(
            f"{child_prefix}└── ... và {len(hidden)} mục khác ({human_size(hidden_size)})"
        )


def collect_all(node: FileNode, acc: list[FileNode]) -> None:
    """Collect all children nodes recursively into a list."""
    acc.append(node)
    for c in node.children:
        collect_all(c, acc)


def print_top_table(root: FileNode, top_n: int = 15, only_files: bool = False) -> None:
    """Print a table of the top largest files/directories."""
    acc: list[FileNode] = []
    collect_all(root, acc)
    acc = (
        [n for n in acc if not n.is_dir]
        if only_files
        else [n for n in acc if n.path != root.path]
    )
    acc.sort(key=lambda n: n.size, reverse=True)
    top = acc[:top_n]

    title = "TOP FILE NẶNG NHẤT" if only_files else "TOP THƯ MỤC / FILE NẶNG NHẤT"
    logger.info("")
    logger.info(f"── {title} ──")
    header = f"{'#':>3}  {'Loại':<6} {'Dung lượng':>12}  {'Tỉ lệ':>7}  {'Đường dẫn'}"
    logger.info(header)
    logger.info("-" * min(100, max(60, len(header))))

    root_size = root.size or 1
    for i, n in enumerate(top, 1):
        percent = n.size / root_size * 100
        kind = "📁 DIR" if n.is_dir else "📄 FILE"
        size_str = f"{human_size(n.size):>12}"
        bar = make_bar(percent, 12)
        logger.info(f"{i:>3}  {kind:<6} {size_str}  {percent:6.2f}%  {bar}  {n.path}")


def print_summary(
    root_path: str, root: FileNode, stats: ScanStats, elapsed: float
) -> None:
    """Print execution summary statistics and disk partition usage."""
    logger.info("")
    logger.info("═" * 60)
    engine = (
        "Cython/C (đã biên dịch, tăng tốc)"
        if core.USING_FAST_CORE
        else "Pure Python (fallback)"
    )
    logger.info(f"  TÓM TẮT QUÉT DUNG LƯỢNG  —  Lõi quét: {engine}")
    logger.info("═" * 60)
    logger.info(f"  📂 Đường dẫn gốc     : {os.path.abspath(root_path)}")
    logger.info(f"  💾 Tổng dung lượng    : {human_size(root.size)}")
    logger.info(f"  📄 Tổng số file       : {stats.total_files:,}")
    logger.info(f"  📁 Tổng số thư mục    : {stats.total_dirs:,}")
    if stats.errors:
        logger.error(f"  ⚠️  Số lỗi truy cập    : {stats.errors}")
    speed = f"  (~{stats.scanned_items / elapsed:,.0f} mục/giây)" if elapsed > 0 else ""
    logger.info(f"  ⏱️  Thời gian quét     : {elapsed:.3f} giây{speed}")

    try:
        usage = os.statvfs(root_path) if hasattr(os, "statvfs") else None
        if usage:
            disk_total = usage.f_frsize * usage.f_blocks
            disk_free = usage.f_frsize * usage.f_bavail
            disk_used = disk_total - disk_free
            pct = disk_used / disk_total * 100 if disk_total else 0
            logger.info("─" * 60)
            logger.info("  🖴  Ổ đĩa chứa đường dẫn:")
            logger.info(f"      Tổng   : {human_size(disk_total)}")
            logger.info(f"      Đã dùng: {human_size(disk_used)}  ({pct:.1f}%)")
            logger.info(f"      Trống  : {human_size(disk_free)}")
            logger.info(f"      {make_bar(pct, 40)}")
    except (OSError, AttributeError):
        pass
    logger.info("═" * 60)
