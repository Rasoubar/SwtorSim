"""Pyodide WebAssembly Bridge for SwtorSim.

Provides a single dispatch interface for JavaScript Web Workers to interact
with SwtorSim's simulation engine, rotation builder, and web API functions without an HTTP server.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Callable

# Ensure SwtorSim root is in sys.path
SWTORSIM_ROOT = Path(__file__).resolve().parents[2]
if str(SWTORSIM_ROOT) not in sys.path:
    sys.path.insert(0, str(SWTORSIM_ROOT))

from src.swtorsim.config_load import load_json_file
from src.swtorsim.web_gui import (
    aggregate_batch_slices,
    execute_simulation_from_payload,
    execute_simulation_slice,
    get_class_gear_options,
    get_simulation_progress,
    get_simulator_catalog,
    load_run_config_bundle,
    preview_character_stats,
    set_simulation_progress_callback,
)
from data.rotation_builder import (
    _resolve_workspace_path,
    build_rotation_file_data,
    discover_loadout_catalog,
    get_workspace_catalog,
    normalize_pre_combat_steps,
    normalize_pull_gate,
    normalize_weave_steps,
    normalize_rotation_steps,
    run_dry_run_preview,
)


def register_js_progress_callback(callback_fn: Callable[..., Any]) -> None:
    """Binds a JavaScript callback function to simulation progress events."""
    def _adapter(running: bool, mode: str, completed: int, total: int, pct: float) -> None:
        try:
            callback_fn(bool(running), str(mode), int(completed), int(total), float(pct))
        except Exception:
            pass

    set_simulation_progress_callback(_adapter)


def dispatch(action: str, payload_json: str = "{}") -> str:
    """Dispatches a worker action and returns a JSON-serialized result."""
    try:
        data = json.loads(payload_json) if payload_json else {}
        result: Any = None

        if action == "GET_CATALOG":
            env = data.get("env", "live")
            result = get_simulator_catalog(env=env)

        elif action == "GET_BUILDER_CATALOG":
            env = data.get("env", "live")
            result = get_workspace_catalog(env=env)

        elif action == "GET_CLASS_GEAR":
            spec_path = data.get("spec_path", "")
            env = data.get("env", "live")
            result = get_class_gear_options(spec_path, env=env)

        elif action == "GET_BUILD_STATS":
            rel_path = data.get("path", "")
            target_file = _resolve_workspace_path(rel_path)
            if not target_file.is_file():
                return json.dumps({"error": f"Build file not found: {rel_path}"}, ensure_ascii=False)
            stats_doc = load_json_file(str(target_file))
            stats_data = stats_doc.get("stats") or stats_doc
            result = {
                "path": rel_path,
                "stats": stats_data,
            }

        elif action == "LOAD_RUN_CONFIG":
            rel_path = data.get("path", "")
            env = data.get("env", "live")
            result = load_run_config_bundle(rel_path, env=env)

        elif action == "LOAD_BUILDER_RUN_CONFIG":
            rel_path = data.get("path", "")
            target_file = _resolve_workspace_path(rel_path)
            if not target_file.is_file():
                return json.dumps({"error": f"Run config not found: {rel_path}"}, ensure_ascii=False)
            rc_data = load_json_file(str(target_file))
            choices_data = {}
            if rc_data.get("choices_path"):
                c_file = _resolve_workspace_path(rc_data["choices_path"])
                if c_file.is_file():
                    choices_data = load_json_file(str(c_file))
            choices_override = rc_data.get("choices_override") or rc_data.get("choices")
            if isinstance(choices_override, dict) and choices_override:
                choices_data.update({str(k): v for k, v in choices_override.items()})
            result = {
                "run_config": rc_data,
                "choices": choices_data,
            }

        elif action == "LOAD_ROTATION":
            rel_path = data.get("path", "")
            if not rel_path:
                return json.dumps({"error": "Missing 'path' parameter."}, ensure_ascii=False)
            target_file = _resolve_workspace_path(rel_path)
            if not target_file.is_file():
                return json.dumps({"error": f"Rotation file not found: {rel_path}"}, ensure_ascii=False)
            raw_data = load_json_file(str(target_file))
            steps, warnings = normalize_rotation_steps(raw_data)
            result = {
                "path": rel_path,
                "filename": target_file.name,
                "steps": steps,
                "pre_combat": normalize_pre_combat_steps(raw_data),
                "weave": normalize_weave_steps(raw_data),
                **normalize_pull_gate(raw_data),
                "warnings": warnings,
            }

        elif action == "DISCOVER_LOADOUT":
            spec_path = data.get("spec_path", "")
            choices = data.get("choices") or data.get("choices_path") or {}
            tactical_fqn = data.get("tactical_fqn", "")
            legendary_fqns = data.get("legendary_fqns", [])
            relic_fqns = data.get("relic_fqns", [])
            env = data.get("env", "live")
            if not spec_path:
                return json.dumps({"error": "spec_path is required."}, ensure_ascii=False)
            result = discover_loadout_catalog(
                spec_path=spec_path,
                choices=choices,
                tactical_fqn=tactical_fqn,
                legendary_fqns=legendary_fqns,
                relic_fqns=relic_fqns,
                env=env,
            )

        elif action == "RUN_ROTATION_PREVIEW":
            result = run_dry_run_preview(data)

        elif action == "SAVE_ROTATION":
            class_folder = str(data.get("class_folder") or "assassin").strip().lower()
            spec_folder = str(data.get("spec_folder") or "hatred").strip().lower()
            filename = str(data.get("filename") or "StandardRotation.json").strip()
            steps = data.get("steps")
            if not isinstance(steps, list):
                return json.dumps({"error": "steps must be a list."}, ensure_ascii=False)
            if not filename.endswith(".json"):
                filename += ".json"
            filename = Path(filename).name
            target_dir = SWTORSIM_ROOT / "data" / "rotations" / class_folder / spec_folder
            target_dir.mkdir(parents=True, exist_ok=True)
            full_path = target_dir / filename
            file_data = build_rotation_file_data(
                steps, data.get("pre_combat"), data.get("pull_conditions"), data.get("pull_max_wait"),
                weave=data.get("weave"),
            )
            formatted = json.dumps(file_data, indent=4, ensure_ascii=False)
            formatted_crlf = formatted.replace("\r\n", "\n").replace("\n", "\r\n") + "\r\n"
            full_path.write_bytes(formatted_crlf.encode("utf-8"))
            rel_saved = full_path.relative_to(SWTORSIM_ROOT).as_posix()
            result = {"ok": True, "path": rel_saved, "filename": filename}

        elif action == "PREVIEW_STATS":
            result = preview_character_stats(data)

        elif action == "SIMULATE":
            result = execute_simulation_from_payload(data)

        elif action == "SIMULATE_SLICE":
            result = execute_simulation_slice(data)

        elif action == "AGGREGATE_BATCH":
            result = aggregate_batch_slices(data)

        elif action == "GET_PROGRESS":
            result = get_simulation_progress()

        else:
            return json.dumps({"error": f"Unknown action: {action}"}, ensure_ascii=False)

        return json.dumps(result, ensure_ascii=False)

    except Exception as exc:
        import traceback
        traceback.print_exc()
        return json.dumps({"error": str(exc), "traceback": traceback.format_exc()}, ensure_ascii=False)
