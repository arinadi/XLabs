"""Main TUI menu for arinanoLabs — delegates to npyscreen_app."""

import sys

from .npyscreen_app import run_npyscreen


def main():
    """Main entry point for TUI."""
    try:
        run_npyscreen()
    except KeyboardInterrupt:
        print("\n\n[dim]Exiting...[/dim]\n")
        sys.exit(0)


if __name__ == "__main__":
    main()
