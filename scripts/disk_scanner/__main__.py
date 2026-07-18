"""Package entrypoint when run as a script directory or module."""

import os
import sys

# Ensure parent directory is in sys.path to allow absolute import of disk_scanner
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from disk_scanner.main import main

if __name__ == "__main__":
    main()
