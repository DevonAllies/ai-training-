"""Entry point for the packaged (PyInstaller) DataLab Trainer app."""
import sys

from datalab.__main__ import main

if __name__ == "__main__":
    sys.exit(main())
