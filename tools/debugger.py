r"""Launches the SwtorSim web debugger (traced run timeline, proc lanes, Measure proc).

Usage:
    .\tools\pyclean.exe tools\debugger.py
    .\tools\pyclean.exe tools\debugger.py --port 8770 --no-browser
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from src.swtorsim.debug.web_debugger import launch_debugger


def main() -> int:
    parser = argparse.ArgumentParser(description="SwtorSim web debugger.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8770)
    parser.add_argument("--no-browser", action="store_true", help="Do not open the browser.")
    args = parser.parse_args()
    launch_debugger(args.host, args.port, open_browser=not args.no_browser)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
