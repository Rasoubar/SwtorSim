"""SwtorSim Unified Game Data Extractor.

Launch by double-clicking, or run from terminal:
    py run_extractor.py
    py run_extractor.py --live
    py run_extractor.py --pts
    py run_extractor.py --both
    py run_extractor.py --source launcher --live
    py run_extractor.py --live-assets "D:\\Games\\SWTOR\\Assets" --live
"""

from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys

STEAM_LIVE_ASSETS = Path(
    r"C:\Program Files (x86)\Steam\steamapps\common\Star Wars - The Old Republic\Assets"
)
STEAM_PTS_ASSETS = Path(
    r"C:\Program Files (x86)\Steam\steamapps\common\Star Wars - The Old Republic - PTS\Assets"
)

LAUNCHER_LIVE_ASSETS = Path(
    r"C:\Program Files (x86)\Electronic Arts\BioWare\Star Wars - The Old Republic\Assets"
)
LAUNCHER_PTS_ASSETS = Path(
    r"C:\Program Files (x86)\Electronic Arts\BioWare\Star Wars - The Old Republic - PTS\Assets"
)

DEFAULT_LIVE_ASSETS = STEAM_LIVE_ASSETS
DEFAULT_PTS_ASSETS = STEAM_PTS_ASSETS

PROJECT_ROOT = Path(__file__).resolve().parent
EXTRACTOR_MAIN = PROJECT_ROOT / "src" / "extractor" / "main.py"
PYCLEAN_EXE = PROJECT_ROOT / "tools" / "pyclean.exe"


def get_runner() -> list[str]:
    """Returns the preferred runner executable."""
    if PYCLEAN_EXE.exists():
        return [str(PYCLEAN_EXE)]
    return [sys.executable]


def normalize_assets_path(raw: str | Path) -> Path:
    """Normalizes a user-supplied path, stripping quotes and appending 'Assets' if needed."""
    cleaned = str(raw).strip().strip('"').strip("'")
    path = Path(cleaned)
    if path.name.lower() != "assets" and (path / "Assets").is_dir():
        return path / "Assets"
    return path


def prompt_custom_path(label: str, current_default: Path) -> Path:
    """Prompts the user for a custom Assets path."""
    while True:
        raw = input(
            f"Enter custom {label} Assets path\n"
            f"  [Default: {current_default}]: "
        ).strip()
        if not raw:
            return current_default
        candidate = normalize_assets_path(raw)
        if candidate.exists():
            return candidate
        print(f"[WARN] Path does not exist: {candidate}")
        use_anyway = input("Use this path anyway? (y/n): ").strip().lower()
        if use_anyway in ("y", "yes"):
            return candidate


def select_asset_source(
    current_source: str = "Steam",
    current_live: Path = STEAM_LIVE_ASSETS,
    current_pts: Path = STEAM_PTS_ASSETS,
) -> tuple[str, Path, Path]:
    """Interactive prompt to choose between Steam, Launcher, or Custom asset paths."""
    while True:
        print("\n" + "=" * 64)
        print("           Select SWTOR Installation Asset Source")
        print("=" * 64)
        print("  [1] Steam")
        print(f"      Live: {STEAM_LIVE_ASSETS}")
        print(f"      PTS:  {STEAM_PTS_ASSETS}")
        print()
        print("  [2] Launcher (Electronic Arts / BioWare)")
        print(f"      Live: {LAUNCHER_LIVE_ASSETS}")
        print(f"      PTS:  {LAUNCHER_PTS_ASSETS}")
        print()
        print("  [3] Custom Path (Enter your own Live / PTS Assets folder)")
        print("=" * 64)

        choice = input("Select source (1-3) [default: 1]: ").strip()
        if choice in ("1", ""):
            return "Steam", STEAM_LIVE_ASSETS, STEAM_PTS_ASSETS
        elif choice == "2":
            return "Launcher", LAUNCHER_LIVE_ASSETS, LAUNCHER_PTS_ASSETS
        elif choice == "3":
            print("\n--- Custom Asset Paths (leave blank to keep current path) ---")
            live_path = prompt_custom_path("LIVE", current_live)
            pts_path = prompt_custom_path("PTS", current_pts)
            return "Custom", live_path, pts_path
        else:
            print(f"[WARN] Invalid selection '{choice}'. Please enter 1, 2, or 3.")


def run_extractor(assets_path: Path, is_pts: bool = False, parsed_only: bool = True) -> bool:
    """Executes the extractor subprocess for the given assets."""
    assets_path = normalize_assets_path(assets_path)
    label = "PTS" if is_pts else "LIVE"
    mode_str = " (Parsed Only - Fast)" if parsed_only else " (Full with Raw Dumps)"
    target_dir = "data/extractor/pts" if is_pts else "data/extractor/live"

    print("\n" + "=" * 64)
    print(f" [INFO] Starting {label} Data Extraction{mode_str}")
    print(f" [INFO] Assets:     {assets_path}")
    print(f" [INFO] Output Dir: {target_dir}")
    print("=" * 64 + "\n")

    if not assets_path.exists():
        print(f"[FAIL] Assets directory not found:\n       {assets_path}")
        print("       Please check your game installation path or change the asset source.")
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
    """Displays the interactive source selection and extraction menu."""
    source_name, live_assets, pts_assets = select_asset_source()

    while True:
        print("\n" + "=" * 64)
        print("            SwtorSim Game Data Extractor Menu")
        print("=" * 64)
        print(f"  Active Source: [{source_name}]")
        print(f"  LIVE Assets:   {live_assets}")
        print(f"  PTS Assets:    {pts_assets}")
        print("-" * 64)
        print("  [1] Extract LIVE Data (Parsed Only - Fast & ~12MB)")
        print("  [2] Extract PTS Data  (Parsed Only - Fast & ~12MB)")
        print("  [3] Extract BOTH      (Live & PTS - Parsed Only)")
        print()
        print("  [4] Extract LIVE (Full Raw Dump - includes extracted/)")
        print("  [5] Extract PTS  (Full Raw Dump - includes extracted/)")
        print()
        print("  [6] Change Asset Source (Steam / Launcher / Custom)")
        print("  [7] Exit")
        print("=" * 64)

        choice = input("Select an option (1-7): ").strip()

        if choice == "1":
            run_extractor(live_assets, is_pts=False, parsed_only=True)
            input("\nPress Enter to return to menu...")
        elif choice == "2":
            run_extractor(pts_assets, is_pts=True, parsed_only=True)
            input("\nPress Enter to return to menu...")
        elif choice == "3":
            ok_live = run_extractor(live_assets, is_pts=False, parsed_only=True)
            if ok_live:
                run_extractor(pts_assets, is_pts=True, parsed_only=True)
            input("\nPress Enter to return to menu...")
        elif choice == "4":
            run_extractor(live_assets, is_pts=False, parsed_only=False)
            input("\nPress Enter to return to menu...")
        elif choice == "5":
            run_extractor(pts_assets, is_pts=True, parsed_only=False)
            input("\nPress Enter to return to menu...")
        elif choice == "6":
            source_name, live_assets, pts_assets = select_asset_source(
                source_name, live_assets, pts_assets
            )
        elif choice in ("7", "q", "exit", ""):
            print("Exiting.")
            break
        else:
            print(f"[WARN] Invalid option '{choice}'. Please enter 1 to 7.")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="SwtorSim Game Data Extractor Launcher."
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--live", action="store_true", help="Extract Live assets")
    group.add_argument("--pts", action="store_true", help="Extract PTS assets")
    group.add_argument("--both", action="store_true", help="Extract both Live and PTS")
    parser.add_argument(
        "--source",
        choices=("steam", "launcher", "custom"),
        default="steam",
        help="Preset installation source ('steam', 'launcher', or 'custom'; default: steam)",
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="Include full raw GOM node dumps in extracted/ (default: parsed-only)",
    )
    parser.add_argument(
        "--live-assets",
        type=Path,
        default=None,
        help="Custom path to Live Assets directory (overrides --source)",
    )
    parser.add_argument(
        "--pts-assets",
        type=Path,
        default=None,
        help="Custom path to PTS Assets directory (overrides --source)",
    )

    args = parser.parse_args()
    parsed_only = not args.full

    if args.source == "launcher":
        default_live = LAUNCHER_LIVE_ASSETS
        default_pts = LAUNCHER_PTS_ASSETS
    else:
        default_live = STEAM_LIVE_ASSETS
        default_pts = STEAM_PTS_ASSETS

    live_assets = normalize_assets_path(args.live_assets) if args.live_assets else default_live
    pts_assets = normalize_assets_path(args.pts_assets) if args.pts_assets else default_pts

    if args.live:
        if args.source == "custom" and args.live_assets is None:
            live_assets = prompt_custom_path("LIVE", default_live)
        return 0 if run_extractor(live_assets, is_pts=False, parsed_only=parsed_only) else 1
    elif args.pts:
        if args.source == "custom" and args.pts_assets is None:
            pts_assets = prompt_custom_path("PTS", default_pts)
        return 0 if run_extractor(pts_assets, is_pts=True, parsed_only=parsed_only) else 1
    elif args.both:
        if args.source == "custom":
            if args.live_assets is None:
                live_assets = prompt_custom_path("LIVE", default_live)
            if args.pts_assets is None:
                pts_assets = prompt_custom_path("PTS", default_pts)
        live_ok = run_extractor(live_assets, is_pts=False, parsed_only=parsed_only)
        pts_ok = run_extractor(pts_assets, is_pts=True, parsed_only=parsed_only) if live_ok else False
        return 0 if (live_ok and pts_ok) else 1
    else:
        interactive_menu()
        return 0


if __name__ == "__main__":
    sys.exit(main())
