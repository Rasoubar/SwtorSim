"""SwtorSim Web Release Builder.

Packages SwtorSim into a fully standalone client-side web application in dist/
powered by Pyodide (Python WebAssembly).

Usage:
    python tools/build_web_release.py
"""

from __future__ import annotations

import shutil
import sys
import time
from pathlib import Path

SWTORSIM_ROOT = Path(__file__).resolve().parents[1]
DIST_DIR = SWTORSIM_ROOT / "dist"
WEB_TOOLS_DIR = SWTORSIM_ROOT / "tools" / "web"
SIM_UI_PATH = SWTORSIM_ROOT / "tools" / "simulator_ui.html"
ROT_UI_PATH = SWTORSIM_ROOT / "tools" / "rotation_builder_ui.html"
TIMELINE_UI_PATH = SWTORSIM_ROOT / "tools" / "rotation_timeline_ui.html"

# Import bundle builder
sys.path.insert(0, str(SWTORSIM_ROOT))
from tools.bundle_pyodide_assets import build_asset_bundle


def inject_pyodide_client(html_content: str, version: int | None = None) -> str:
    """Injects the pyodide_client.js script tag with cache-busting version before </head>."""
    v_str = f"?v={version}" if version else ""
    tag = f'  <script src="pyodide_client.js{v_str}"></script>\n</head>'
    if '</head>' in html_content:
        return html_content.replace('</head>', tag, 1)
    return html_content + f'\n<script src="pyodide_client.js{v_str}"></script>'


def build_web_release() -> None:
    build_version = int(time.time())
    print(f"[INFO] Starting SwtorSim Web Release Build (v{build_version})...")
    DIST_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Build runtime assets archive
    print("\n--- Step 1: Packaging Runtime Assets Archive ---")
    assets_zip = DIST_DIR / "swtorsim_assets.zip"
    build_asset_bundle(assets_zip)

    # 2. Copy Web Worker and Client Bridge scripts
    print("\n--- Step 2: Copying Web Worker & API Bridge ---")
    worker_src = WEB_TOOLS_DIR / "sim_worker.js"
    client_src = WEB_TOOLS_DIR / "pyodide_client.js"

    shutil.copy2(worker_src, DIST_DIR / "sim_worker.js")
    # Inject cache-busting asset URL into pyodide_client.js
    client_content = client_src.read_text(encoding="utf-8")
    client_content = client_content.replace('"swtorsim_assets.zip"', f'"swtorsim_assets.zip?v={build_version}"')
    (DIST_DIR / "pyodide_client.js").write_text(client_content, encoding="utf-8")
    headers_src = WEB_TOOLS_DIR / "_headers"
    if headers_src.is_file():
        shutil.copy2(headers_src, DIST_DIR / "_headers")
        print(f"[OK] Copied {headers_src.name} -> dist/ (Cloudflare Pages headers)")
    print(f"[OK] Copied {worker_src.name} -> dist/")
    print(f"[OK] Copied {client_src.name} -> dist/")

    # Copy icons to dist/icons
    icons_src = WEB_TOOLS_DIR / "icons"
    if not icons_src.is_dir():
        icons_src = SWTORSIM_ROOT / "data" / "extractor" / "live" / "icons"
    if icons_src.is_dir():
        dist_icons = DIST_DIR / "icons"
        dist_icons.mkdir(parents=True, exist_ok=True)
        copied_icons = 0
        for icon_file in icons_src.glob("*.png"):
            shutil.copy2(icon_file, dist_icons / icon_file.name)
            # Ensure lowercased copy exists for case-sensitive web environments
            lower_name = icon_file.name.lower()
            if lower_name != icon_file.name:
                shutil.copy2(icon_file, dist_icons / lower_name)
            copied_icons += 1
        print(f"[OK] Copied {copied_icons} icons -> dist/icons/")

    # 3. Process & copy simulator UI as index.html
    print("\n--- Step 3: Preparing HTML Entrypoints ---")
    if SIM_UI_PATH.is_file():
        sim_html = SIM_UI_PATH.read_text(encoding="utf-8")
        injected_sim = inject_pyodide_client(sim_html, version=build_version)
        (DIST_DIR / "index.html").write_text(injected_sim, encoding="utf-8")
        print("[OK] Generated dist/index.html (Combat Simulator Dashboard)")
    else:
        print(f"[FAIL] simulator_ui.html not found at {SIM_UI_PATH}")

    # 4. Process & copy rotation builder UI
    if ROT_UI_PATH.is_file():
        rot_html = ROT_UI_PATH.read_text(encoding="utf-8")
        injected_rot = inject_pyodide_client(rot_html, version=build_version)
        (DIST_DIR / "rotation_builder.html").write_text(injected_rot, encoding="utf-8")
        print("[OK] Generated dist/rotation_builder.html (Rotation Builder)")

    # 5. Copy the Cast Timeline pop-out (static page; talks to the builder over BroadcastChannel)
    if TIMELINE_UI_PATH.is_file():
        shutil.copy2(TIMELINE_UI_PATH, DIST_DIR / "timeline.html")
        print("[OK] Copied dist/timeline.html (Cast Timeline window)")
    else:
        print(f"[FAIL] rotation_timeline_ui.html not found at {TIMELINE_UI_PATH}")

    print("\n" + "=" * 65)
    print("  [OK] WEB RELEASE BUILD COMPLETE!")
    print("=" * 65)
    print(f"Distribution output directory: {DIST_DIR}")
    print("\nTo test locally in your browser:")
    print("    python -m http.server 8080 -d dist")
    print("    Open: http://localhost:8080")
    print("\nTo deploy:")
    print("    Publish the contents of dist/ directly to GitHub Pages,")
    print("    Cloudflare Pages, Vercel, Netlify, or any static host.")
    print("=" * 65 + "\n")


if __name__ == "__main__":
    build_web_release()
