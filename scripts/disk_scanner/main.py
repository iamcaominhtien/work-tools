"""CLI Entry point for the disk scanner module."""

import argparse
import os
import sys
import time
from loguru import logger

from .core import _load_fast_core, scan_directory
from .display import print_summary, print_top_table, print_tree
from .utils import Color, parse_size


def main() -> None:
    """Parse CLI arguments, execute directory scanning, and print report."""
    parser = argparse.ArgumentParser(
        description="Quét và phân tích dung lượng ổ đĩa đệ quy.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Ví dụ:
  uv run scripts/disk_scanner .
  uv run scripts/disk_scanner "C:\\Users\\Ten" --top 20 --depth 4
  uv run scripts/disk_scanner /var/log --min-size 1MB --files-only
  uv run scripts/disk_scanner . --no-cython
""",
    )
    parser.add_argument(
        "path", nargs="?", default=".", help="Đường dẫn thư mục cần quét"
    )
    parser.add_argument(
        "--top", type=int, default=10, help="Số mục hiển thị mỗi cấp trong cây"
    )
    parser.add_argument(
        "--depth", type=int, default=3, help="Độ sâu tối đa hiển thị cây"
    )
    parser.add_argument(
        "--min-size",
        type=str,
        default="0",
        help="Bỏ qua file nhỏ hơn kích thước này, vd: 10MB",
    )
    parser.add_argument(
        "--top-table", type=int, default=15, help="Số dòng trong bảng top nặng nhất"
    )
    parser.add_argument(
        "--files-only", action="store_true", help="Bảng top chỉ tính file"
    )
    parser.add_argument("--no-color", action="store_true", help="Tắt màu console")
    parser.add_argument(
        "--follow-symlinks", action="store_true", help="Đi theo symlink"
    )
    parser.add_argument(
        "--no-progress", action="store_true", help="Không hiện tiến trình quét"
    )
    parser.add_argument(
        "--no-cython",
        action="store_true",
        help="Ép dùng lõi Python thuần, không build/dùng Cython",
    )
    parser.add_argument(
        "--gui",
        action="store_true",
        help="Hiển thị kết quả quét dưới dạng giao diện đồ họa (GUI)",
    )
    args = parser.parse_args()

    if args.no_color:
        Color.ENABLED = False
        for attr in [
            "RESET",
            "BOLD",
            "DIM",
            "RED",
            "GREEN",
            "YELLOW",
            "BLUE",
            "MAGENTA",
            "CYAN",
        ]:
            setattr(Color, attr, "")

    root_path = os.path.abspath(args.path)
    if not os.path.exists(root_path):
        logger.error(f"❌ Đường dẫn không tồn tại: {root_path}")
        sys.exit(1)
    if not os.path.isdir(root_path):
        logger.error(f"❌ Không phải thư mục: {root_path}")
        sys.exit(1)

    if not args.no_cython:
        _load_fast_core()

    from .core import USING_FAST_CORE  # Import actual status after loading

    min_size = parse_size(args.min_size)
    engine_note = "⚡ lõi Cython/C" if USING_FAST_CORE else "🐍 lõi Python thuần"
    logger.info(f"🚀 Bắt đầu quét ({engine_note}): {root_path}")
    logger.info("-" * 60)

    t0 = time.time()
    try:
        root, stats = scan_directory(
            root_path,
            min_size=min_size,
            follow_symlinks=args.follow_symlinks,
            progress=not args.no_progress,
        )
    except KeyboardInterrupt:
        logger.error("\n⛔ Đã dừng quét theo yêu cầu người dùng.")
        sys.exit(130)
    elapsed = time.time() - t0

    logger.info("")
    logger.info("── CẤU TRÚC THƯ MỤC (theo dung lượng giảm dần) ──")
    print_tree(root, root.size or 1, max_depth=args.depth, top_n=args.top)
    print_top_table(root, top_n=args.top_table, only_files=args.files_only)
    print_summary(root_path, root, stats, elapsed)

    if args.gui:
        logger.info("🎨 Đang khởi chạy giao diện GUI...")
        from .gui import run_gui

        run_gui(root, stats, elapsed)


if __name__ == "__main__":
    main()
