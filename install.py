#!/usr/bin/env python3
"""
arinanoLabs Installer
Usage: curl -sL https://raw.githubusercontent.com/arinadi/arinanoLabs/main/install.py | python
"""

import sys
import os

# Ensure we can import installer package
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from rich.console import Console
except ImportError:
    print("Installing required packages...")
    os.system(f"{sys.executable} -m pip install rich requests --quiet")
    from rich.console import Console

from installer.menu import main

if __name__ == "__main__":
    main()
