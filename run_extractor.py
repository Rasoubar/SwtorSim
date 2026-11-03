"""SwtorSim Unified Game Data Extractor.

Launch by double-clicking, or run from terminal:
    py run_extractor.py
    py run_extractor.py --live
    py run_extractor.py --pts
    py run_extractor.py --both
"""

from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys

DEFAULT_LIVE_ASSETS = Path(
    r"C:\Program Files (x86)\Steam\steamapps\common\Star Wars - The Old Republic\Assets"
)
DEFAULT_PTS_ASSETS = Path(
    r"C:\Program Files (x86)\Steam\steamapps\common\Star Wars - The Old Republic - PTS\Assets"
)

PROJECT_ROOT = Path(__file__).resolve().parent
EXTRACTOR_MAIN = PROJECT_ROOT / "src" / "extractor" / "main.py"
PYCLEAN_EXE = PROJECT_ROOT / "tools" / "pyclean.exe"


def get_runner() -> list[str]:
    """Returns the preferred runner executable."""
    if PYCLEAN_EXE.exists():
        return [str(PYCLEAN_EXE)]
    return [sys.executable]


def run_extractor(assets_path: Path, is_pts: bool = False, parsed_only: bool = True) -> bool:
    """Executes the extractor subprocess for the given assets."""
    label = "PTS" if is_pts else "LIVE"
    mode_str = " (Parsed Only - Fast)" if parsed_only else " (Full with Raw Dumps)"
    target_dir = "data/extractor/pts" if is_pts else "data/extractor"

    print("\n" + "=" * 56)
    print(f" [INFO] Starting {label} Data Extraction{mode_str}")
    print(f" [INFO] Assets:     {assets_path}")
    print(f" [INFO] Output Dir: {target_dir}")
    print("=" * 56 + "\n")

    if not assets_path.exists():
        print(f"[FAIL] Assets directory not found:\n       {assets_path}")
        print("       Please check your game installation path.")
        return False

    cmd = get_runner() + [str(EXTRACTOR_MAIN), "--assets", str(assets_path)]
    if is_pts:
        cmd.append("--pts")
    if parsed_only:
        cmd.append("--parsed-only")

    try:
        res = subprocess.run(cmd, cwd=str(PROJECT_ROOT))
        if res.returncode == 0:
            print(f"\n[OK] {label} extraction finished successfully.")
            return True
        else:
            print(f"\n[FAIL] {label} extraction failed with return code {res.returncode}.")
            return False
    except Exception as exc:
        print(f"\n[FAIL] Failed to execute extractor: {exc}")
        return False


def interactive_menu() -> None:
    """Displays a simple interactive numbered menu."""
    while True:
        print("\n" + "=" * 56)
        print("        SwtorSim Game Data Extractor Menu")
        print("=" * 56)
        print("  [1] Extract LIVE Data (Parsed Only - Fast & ~12MB)")
        print("  [2] Extract PTS Data  (Parsed Only - Fast & ~12MB)")
        print("  [3] Extract BOTH      (Live & PTS - Parsed Only)")
        print()
        print("  [4] Extract LIVE (Full Raw Dump - includes extracted/)")
        print("  [5] Extract PTS  (Full Raw Dump - includes extracted/)")
        print()
        print("  [6] Exit")
        print("=" * 56)

        choice = input("Select an option (1-6): ").strip()

        if choice == "1":
            run_extractor(DEFAULT_LIVE_ASSETS, is_pts=False, parsed_only=True)
            input("\nPress Enter to return to menu...")
        elif choice == "2":
            run_extractor(DEFAULT_PTS_ASSETS, is_pts=True, parsed_only=True)
            input("\nPress Enter to return to menu...")
        elif choice == "3":
            ok_live = run_extractor(DEFAULT_LIVE_ASSETS, is_pts=False, parsed_only=True)
            if ok_live:
                run_extractor(DEFAULT_PTS_ASSETS, is_pts=True, parsed_only=True)
            input("\nPress Enter to return to menu...")
        elif choice == "4":
            run_extractor(DEFAULT_LIVE_ASSETS, is_pts=False, parsed_only=False)
            input("\nPress Enter to return to menu...")
        elif choice == "5":
            run_extractor(DEFAULT_PTS_ASSETS, is_pts=True, parsed_only=False)
            input("\nPress Enter to return to menu...")
        elif choice in ("6", "q", "exit", ""):
            print("Exiting.")
            break
        else:
            print(f"[WARN] Invalid option '{choice}'. Please enter 1 to 6.")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="SwtorSim Game Data Extractor Launcher."
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--live", action="store_true", help="Extract Live assets")
    group.add_argument("--pts", action="store_true", help="Extract PTS assets")
    group.add_argument("--both", action="store_true", help="Extract both Live and PTS")
    parser.add_argument(
        "--full",
        action="store_true",
        help="Include full raw GOM node dumps in extracted/ (default: parsed-only)",
    )
    parser.add_argument(
        "--live-assets",
        type=Path,
        default=DEFAULT_LIVE_ASSETS,
        help="Custom path to Live assets",
    )
    parser.add_argument(
        "--pts-assets",
        type=Path,
        default=DEFAULT_PTS_ASSETS,
        help="Custom path to PTS assets",
    )

    args = parser.parse_args()
    parsed_only = not args.full

    if args.live:
        return 0 if run_extractor(args.live_assets, is_pts=False, parsed_only=parsed_only) else 1
    elif args.pts:
        return 0 if run_extractor(args.pts_assets, is_pts=True, parsed_only=parsed_only) else 1
    elif args.both:
        live_ok = run_extractor(args.live_assets, is_pts=False, parsed_only=parsed_only)
        pts_ok = run_extractor(args.pts_assets, is_pts=True, parsed_only=parsed_only) if live_ok else False
        return 0 if (live_ok and pts_ok) else 1
    else:
        interactive_menu()
        return 0


if __name__ == "__main__":
    sys.exit(main())
