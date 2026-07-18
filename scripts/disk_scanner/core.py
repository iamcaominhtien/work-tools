"""Core scanning logic (Cython integration and pure Python fallback)."""

import hashlib
import os
import sys
import tempfile
from tqdm import tqdm

from .models import FileNode, ScanStats
from .utils import human_size

# Global progress bar reference
_pbar = None

# Cython source code embedded
_PYX_SOURCE = r"""
# cython: language_level=3
# cython: boundscheck=False, wraparound=False, cdivision=True
from libc.stdint cimport int64_t
from posix.types cimport off_t, mode_t
import os

cdef extern from "dirent.h" nogil:
    ctypedef struct DIR:
        pass
    struct dirent:
        char d_name[256]
        unsigned char d_type
    DIR *opendir(const char *name)
    dirent *readdir(DIR *dirp)
    int closedir(DIR *dirp)

cdef extern from "sys/stat.h" nogil:
    struct stat:
        off_t st_size
        mode_t st_mode
        unsigned long long st_dev
        unsigned long long st_ino
        int64_t st_blocks
    int lstat(const char *path, stat *buf)
    int S_ISDIR(mode_t mode)
    int S_ISLNK(mode_t mode)


cdef class ScanResult:
    cdef public str name
    cdef public str path
    cdef public int64_t size
    cdef public bint is_dir
    cdef public list children
    cdef public int64_t file_count
    cdef public int64_t dir_count
    cdef public str error

    def __cinit__(self, str name, str path, bint is_dir):
        self.name = name
        self.path = path
        self.size = 0
        self.is_dir = is_dir
        self.children = []
        self.file_count = 0
        self.dir_count = 0
        self.error = None


cdef class ScanStats:
    cdef public int64_t total_files
    cdef public int64_t total_dirs
    cdef public int64_t total_size
    cdef public int64_t errors
    cdef public int64_t scanned_items

    def __cinit__(self):
        self.total_files = 0
        self.total_dirs = 0
        self.total_size = 0
        self.errors = 0
        self.scanned_items = 0


cdef inline bint _is_dotdir(const char *name) nogil:
    if name[0] == b'.':
        if name[1] == 0:
            return True
        if name[1] == b'.' and name[2] == 0:
            return True
    return False


cdef ScanResult _scan_dir_c(bytes path_b, str path_str, str name,
                            ScanStats stats, int64_t min_size,
                            bint follow_symlinks, object progress_cb,
                            set visited_dirs):
    cdef DIR *dirp
    cdef dirent *ent
    cdef stat st
    cdef ScanResult node = ScanResult.__new__(ScanResult, name, path_str, True)
    cdef bytes child_path_b
    cdef str child_name, child_path_str
    cdef int64_t fsize
    cdef bint isdir, islink

    dirp = opendir(path_b)
    if dirp == NULL:
        node.error = "Khong the mo thu muc (khong co quyen hoac khong ton tai)"
        stats.errors += 1
        return node

    try:
        while True:
            ent = readdir(dirp)
            if ent == NULL:
                break
            if _is_dotdir(ent.d_name):
                continue

            child_name = ent.d_name.decode('utf-8', 'surrogateescape')
            child_path_b = path_b + b'/' + ent.d_name
            child_path_str = path_str + '/' + child_name

            if lstat(child_path_b, &st) != 0:
                stats.errors += 1
                continue

            islink = S_ISLNK(st.st_mode)
            isdir = S_ISDIR(st.st_mode)

            if islink and not follow_symlinks:
                continue

            if isdir:
                dir_key = (st.st_dev, st.st_ino)
                if dir_key in visited_dirs:
                    continue
                visited_dirs.add(dir_key)

                child = _scan_dir_c(child_path_b, child_path_str, child_name,
                                     stats, min_size, follow_symlinks, progress_cb,
                                     visited_dirs)
                node.size += child.size
                node.file_count += child.file_count
                node.dir_count += child.dir_count + 1
                node.children.append(child)
            else:
                fsize = <int64_t>st.st_blocks * 512
                node.size += fsize
                node.file_count += 1
                stats.total_files += 1
                stats.total_size += fsize
                if fsize >= min_size:
                    fchild = ScanResult.__new__(ScanResult, child_name, child_path_str, False)
                    fchild.size = fsize
                    node.children.append(fchild)

            stats.scanned_items += 1
            if progress_cb is not None and stats.scanned_items % 500 == 0:
                progress_cb(stats.scanned_items, stats.total_size)
    finally:
        closedir(dirp)

    stats.total_dirs += 1
    return node


def scan_directory_fast(str root_path, int64_t min_size=0,
                         bint follow_symlinks=False, object progress_cb=None,
                         set visited_dirs=None):
    root_path = os.path.abspath(root_path)
    cdef bytes path_b = root_path.encode('utf-8', 'surrogateescape')
    cdef str name = os.path.basename(root_path.rstrip('/')) or root_path
    cdef ScanStats stats = ScanStats.__new__(ScanStats)
    cdef stat root_st
    if visited_dirs is None:
        visited_dirs = set()
    if lstat(path_b, &root_st) == 0:
        visited_dirs.add((root_st.st_dev, root_st.st_ino))
    root = _scan_dir_c(path_b, root_path, name, stats, min_size, follow_symlinks, progress_cb, visited_dirs)
    return root, stats
"""

USING_FAST_CORE = False
_scan_core = None


def _get_cache_dir() -> str:
    """Return OS-specific cache directory for compiling Cython module."""
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or tempfile.gettempdir()
    else:
        base = os.environ.get("XDG_CACHE_HOME") or os.path.join(
            os.path.expanduser("~"), ".cache"
        )
    d = os.path.join(base, "disk_scanner_cy")
    os.makedirs(d, exist_ok=True)
    return d


def _load_fast_core() -> None:
    """Compile and load the Cython core scanner if possible."""
    global USING_FAST_CORE, _scan_core
    try:
        cache_dir = _get_cache_dir()
        src_hash = hashlib.sha256(_PYX_SOURCE.encode("utf-8")).hexdigest()[:16]
        module_name = f"_scan_core_{src_hash}"
        pyx_path = os.path.join(cache_dir, module_name + ".pyx")

        if not os.path.exists(pyx_path):
            with open(pyx_path, "w", encoding="utf-8") as f:
                f.write(_PYX_SOURCE)

        if cache_dir not in sys.path:
            sys.path.insert(0, cache_dir)

        try:
            import importlib

            mod = importlib.import_module(module_name)
            _scan_core = mod
            USING_FAST_CORE = True
            return
        except ImportError:
            pass

        import pyximport

        pyximport.install(
            language_level=3,
            build_dir=os.path.join(cache_dir, "build"),
            build_in_temp=True,
            inplace=True,
        )
        import importlib

        mod = importlib.import_module(module_name)
        _scan_core = mod
        USING_FAST_CORE = True
    except Exception:
        USING_FAST_CORE = False
        _scan_core = None


def _convert_from_fast(result) -> FileNode:
    """Convert C-level Cython results back into Python FileNode objects."""
    node = FileNode(
        name=result.name,
        path=result.path,
        size=result.size,
        is_dir=result.is_dir,
        file_count=result.file_count,
        dir_count=result.dir_count,
        error=result.error,
    )
    for c in result.children:
        node.children.append(_convert_from_fast(c))
    return node


def scan_directory_pure_python(
    path: str,
    stats: ScanStats,
    min_size: int = 0,
    follow_symlinks: bool = False,
    progress: bool = True,
    visited_dirs: set = None,
) -> FileNode:
    """Scan directory recursively using pure Python (os.scandir) fallback."""
    if visited_dirs is None:
        visited_dirs = set()
        try:
            root_stat = os.lstat(path)
            visited_dirs.add((root_stat.st_dev, root_stat.st_ino))
        except OSError:
            pass

    name = os.path.basename(os.path.normpath(path)) or path
    node = FileNode(name=name, path=path, is_dir=True)
    try:
        entries = list(os.scandir(path))
    except PermissionError:
        node.error = "Không có quyền truy cập"
        stats.errors += 1
        return node
    except FileNotFoundError:
        node.error = "Không tìm thấy"
        stats.errors += 1
        return node
    except OSError as e:
        node.error = str(e)
        stats.errors += 1
        return node

    for entry in entries:
        try:
            if entry.is_symlink() and not follow_symlinks:
                continue
            if entry.is_dir(follow_symlinks=follow_symlinks):
                try:
                    entry_stat = entry.stat(follow_symlinks=follow_symlinks)
                    dir_key = (entry_stat.st_dev, entry_stat.st_ino)
                except OSError:
                    dir_key = None

                if dir_key is not None:
                    if dir_key in visited_dirs:
                        continue
                    visited_dirs.add(dir_key)

                child = scan_directory_pure_python(
                    entry.path, stats, min_size, follow_symlinks, progress, visited_dirs
                )
                node.size += child.size
                node.file_count += child.file_count
                node.dir_count += child.dir_count + 1
                node.children.append(child)
            else:
                try:
                    stat_res = entry.stat(follow_symlinks=follow_symlinks)
                    if hasattr(stat_res, "st_blocks"):
                        fsize = stat_res.st_blocks * 512
                    else:
                        fsize = stat_res.st_size
                except OSError:
                    fsize = 0
                    stats.errors += 1
                node.size += fsize
                node.file_count += 1
                stats.total_files += 1
                stats.total_size += fsize
                if fsize >= min_size:
                    node.children.append(
                        FileNode(
                            name=entry.name, path=entry.path, size=fsize, is_dir=False
                        )
                    )
            stats.scanned_items += 1
            if progress and stats.scanned_items % 500 == 0:
                global _pbar
                if _pbar is not None:
                    _pbar.update(500)
                    _pbar.set_description_str(
                        f"🔍 Đang quét | {human_size(stats.total_size)}"
                    )
        except OSError:
            stats.errors += 1
            continue
    stats.total_dirs += 1
    return node


def scan_directory(
    path: str, min_size: int = 0, follow_symlinks: bool = False, progress: bool = True
) -> tuple[FileNode, ScanStats]:
    """Scan directory using Cython if available, otherwise pure Python."""
    global _pbar, USING_FAST_CORE, _scan_core

    if progress:
        _pbar = tqdm(
            desc="🔍 Đang quét",
            bar_format="{desc}: {n_fmt} mục",
            leave=False,
        )

    visited_dirs = set()

    if USING_FAST_CORE and _scan_core is not None:

        def cb(scanned: int, total_size: int) -> None:
            if progress and _pbar is not None:
                _pbar.update(500)
                _pbar.set_description_str(f"🔍 Đang quét | {human_size(total_size)}")

        raw_root, raw_stats = _scan_core.scan_directory_fast(
            path,
            min_size=min_size,
            follow_symlinks=follow_symlinks,
            progress_cb=cb if progress else None,
            visited_dirs=visited_dirs,
        )
        root = _convert_from_fast(raw_root)
        stats = ScanStats()
        stats.total_files = raw_stats.total_files
        stats.total_dirs = raw_stats.total_dirs
        stats.total_size = raw_stats.total_size
        stats.errors = raw_stats.errors
        stats.scanned_items = raw_stats.scanned_items
        result = (root, stats)
    else:
        stats = ScanStats()
        root = scan_directory_pure_python(
            path, stats, min_size, follow_symlinks, progress, visited_dirs
        )
        result = (root, stats)

    if progress and _pbar is not None:
        _pbar.close()

    return result
