"""SwtorSim Web GUI Server & Simulation API.

Provides a local HTTP server and JSON REST API for configuring loadouts,
editing character stats and engine settings, running single-run (TEST) and
Monte Carlo (BATCH) combat simulations, and visualizing telemetry in the browser.
"""

import atexit
import copy
import io
import json
import math
import os
import random
import socket
import statistics
import sys
import threading
import time
import webbrowser
from contextlib import redirect_stdout
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from multiprocessing import Pool, cpu_count
from pathlib import Path
from typing import Any
import urllib.request
from urllib.parse import parse_qs, urlparse

SWTORSIM_ROOT = Path(__file__).resolve().parents[2]
if str(SWTORSIM_ROOT) not in sys.path:
    sys.path.insert(0, str(SWTORSIM_ROOT))

from src.swtorsim.cast_timeline import CastTimelineRecorder, rotation_steps_of
from src.swtorsim.cli import index_disciplines
from src.swtorsim.config_load import (
    expand_force_tech_power,
    fqn_to_relative_path,
    load_character_stats_from_json,
    load_complete_loadout,
    load_json_file,
    load_rotation_from_json,
    load_training_dummy_armor_debuffs,
)
from src.swtorsim.metrics import (
    ATTACK_TYPE_NAMES,
    DAMAGE_TYPE_NAMES,
    format_type_descriptor,
    has_proper_effect_name,
)
from src.swtorsim.run_config import (
    BUILDS_DIR,
    DISCIPLINES_DIR,
    GEAR_PATH,
    LEGENDARY_PREFIX,
    RELICS_PATH,
    ROTATIONS_DIR,
    TACTICAL_PREFIX,
    TRAINING_DUMMY_ARMOR_DEBUFF_LABEL,
    RunConfig,
    apply_weapon_ranges,
    discipline_names,
    filter_gear_for_class,
    get_disciplines_dir,
    get_gear_path,
    get_relics_path,
    parse_hand_range,
    relic_menu_label,
    resolve_env_extractor_path,
    resolve_skill_tree_fqns,
    validate_run_config,
)
from src.swtorsim.settings import (
    get_extractor_data_dir,
    set_default_combat_distance,
    set_in_flashpoint_operation,
    set_projectile_flight_time,
    set_stem_matching,
)
from src.swtorsim.setup import prepare_simulation

PARSED_DIR = SWTORSIM_ROOT / "data" / "extractor" / "live" / "parsed"
SIM_UI_HTML_PATH = SWTORSIM_ROOT / "tools" / "simulator_ui.html"
TIMELINE_UI_HTML_PATH = SWTORSIM_ROOT / "tools" / "rotation_timeline_ui.html"
RUN_CONFIG_DIR = SWTORSIM_ROOT / "data" / "run_config"

COMMON_HP_PRESETS = [
    {"label": "1.0M - Quick Parse", "value": 1_000_000},
    {"label": "2.5M - Small Dummy", "value": 2_500_000},
    {"label": "6.0M - Standard Dummy", "value": 6_000_000},
    {"label": "6.5M - Operation Dummy", "value": 6_500_000},
    {"label": "10.0M - Extended Dummy", "value": 10_000_000},
]

DEFAULT_STAT_KEYS = (
    "Mastery",
    "Power",
    "Force-Tech Power",
    "Critical Rating",
    "Alacrity Rating",
    "Accuracy Rating",
    "Main_hand_min",
    "Main_hand_max",
    "Off_hand_min",
    "Off_hand_max",
)

_ROTATION_BUILDER_LOCK = threading.Lock()
_ROTATION_BUILDER_PORT: int | None = None
_BLUEPRINT_LOADOUT_CACHE: dict[tuple[str, ...], dict[str, Any]] = {}

_SIM_PROGRESS_LOCK = threading.Lock()
_SIM_PROGRESS: dict[str, Any] = {
    "running": False,
    "mode": "TEST",
    "completed": 0,
    "total": 1,
    "pct": 0.0,
}


_SIM_PROGRESS_CALLBACK: Any = None

_SIM_CANCEL = threading.Event()


class SimulationCancelled(Exception):
    """Raised when the user cancels an in-flight batch simulation."""


def request_simulation_cancel() -> None:
    """Asks the active batch simulation to stop at the next opportunity."""
    _SIM_CANCEL.set()


def set_simulation_progress_callback(callback: Any) -> None:
    """Registers an optional callback for simulation progress events (e.g. Pyodide Web Workers)."""
    global _SIM_PROGRESS_CALLBACK
    _SIM_PROGRESS_CALLBACK = callback


def _update_simulation_progress(running: bool, mode: str, completed: int, total: int) -> None:
    """Thread-safe update of the active simulation progress counter."""
    safe_total = max(1, int(total))
    safe_completed = max(0, min(int(completed), safe_total))
    pct = round((safe_completed / safe_total) * 100.0, 1)
    with _SIM_PROGRESS_LOCK:
        _SIM_PROGRESS["running"] = bool(running)
        _SIM_PROGRESS["mode"] = str(mode)
        _SIM_PROGRESS["completed"] = safe_completed
        _SIM_PROGRESS["total"] = safe_total
        _SIM_PROGRESS["pct"] = pct
    if _SIM_PROGRESS_CALLBACK is not None:
        try:
            _SIM_PROGRESS_CALLBACK(bool(running), str(mode), safe_completed, safe_total, pct)
        except Exception:
            pass


def get_simulation_progress() -> dict[str, Any]:
    """Returns a snapshot of the current simulation progress."""
    with _SIM_PROGRESS_LOCK:
        return dict(_SIM_PROGRESS)


def _resolve_workspace_path(rel_or_abs: str | Path) -> Path:
    """Resolves a path relative to SWTORSIM_ROOT if it is not already absolute/existing."""
    if not rel_or_abs or not str(rel_or_abs).strip():
        return Path("")
    p = Path(rel_or_abs)
    if p.exists() and p != Path("."):
        return p.resolve()
    candidate = SWTORSIM_ROOT / p
    if candidate.exists() and candidate != SWTORSIM_ROOT:
        return candidate.resolve()
    # Case-insensitive resolution fallback for Linux/WASM virtual filesystems
    parts = p.parts
    curr = SWTORSIM_ROOT
    matched = True
    for part in parts:
        found = False
        try:
            for child in curr.iterdir():
                if child.name.lower() == part.lower():
                    curr = child
                    found = True
                    break
        except Exception:
            pass
        if not found:
            matched = False
            break
    if matched and curr.exists():
        return curr.resolve()
    return candidate


def _to_workspace_rel(path: str | Path) -> str:
    """Converts a path to a POSIX path relative to SWTORSIM_ROOT when possible."""
    p = _resolve_workspace_path(path)
    try:
        return p.relative_to(SWTORSIM_ROOT).as_posix()
    except ValueError:
        return p.as_posix()


def _write_json_crlf(target_path: Path, data: Any) -> None:
    """Writes JSON to disk with canonical Windows CRLF line endings (Rule #6)."""
    target_path.parent.mkdir(parents=True, exist_ok=True)
    formatted = json.dumps(data, indent=2, ensure_ascii=False)
    formatted_crlf = formatted.replace("\r\n", "\n").replace("\n", "\r\n") + "\r\n"
    target_path.write_bytes(formatted_crlf.encode("utf-8"))


def get_simulator_catalog(env: str = "live") -> dict[str, Any]:
    """Discovers all run configs, disciplines, builds, choices, rotations, and relics."""
    active_env = str(env).lower().strip()
    disc_dir = _resolve_workspace_path(get_disciplines_dir(active_env))
    disciplines_raw = index_disciplines(str(disc_dir))
    disciplines: dict[str, dict[str, str]] = {}
    for cls_name, specs in disciplines_raw.items():
        disciplines[cls_name] = {}
        for sp_name, sp_path in specs.items():
            disciplines[cls_name][sp_name] = _to_workspace_rel(sp_path)

    def _scan_dir(dir_rel: str) -> list[dict[str, Any]]:
        base = _resolve_workspace_path(dir_rel)
        items: list[dict[str, Any]] = []
        if not base.is_dir():
            return items
        for path in sorted(base.rglob("*.json")):
            if not path.is_file():
                continue
            rel = path.relative_to(base)
            is_custom = any(p.lower() == "custom" for p in rel.parts)
            label = rel.with_suffix("").as_posix()
            items.append(
                {
                    "label": label,
                    "name": path.name,
                    "path": _to_workspace_rel(path),
                    "is_custom": is_custom,
                }
            )
        return items

    def _scan_rotations(dir_rel: str) -> list[dict[str, Any]]:
        base = _resolve_workspace_path(dir_rel)
        items: list[dict[str, Any]] = []
        if not base.is_dir():
            return items
        for path in sorted(base.rglob("*.json")):
            if not path.is_file():
                continue
            rel = path.relative_to(base)
            parts = rel.parts
            cls = parts[0].lower() if len(parts) >= 2 else ""
            sp = parts[1].lower() if len(parts) >= 3 else ""
            items.append(
                {
                    "label": rel.with_suffix("").as_posix(),
                    "name": path.name,
                    "path": _to_workspace_rel(path),
                    "class": cls,
                    "spec": sp,
                    "is_custom": False,
                }
            )
        return items

    run_configs = _scan_dir("data/run_config")
    builds_raw = _scan_dir(BUILDS_DIR)
    builds: list[dict[str, Any]] = []
    for b in builds_raw:
        b_file = _resolve_workspace_path(b["path"])
        stats_dict = {}
        if b_file.is_file():
            try:
                stats_dict = load_json_file(str(b_file))
            except Exception:
                stats_dict = {}
            if isinstance(stats_dict, dict):
                expand_force_tech_power(stats_dict)
        builds.append({**b, "stats": stats_dict})

    rotations_files = _scan_rotations(ROTATIONS_DIR)

    relics_path = _resolve_workspace_path(get_relics_path(active_env))
    relics_raw = load_json_file(str(relics_path)) if relics_path.is_file() else []
    relics_list: list[dict[str, str]] = []
    parsed_dir = SWTORSIM_ROOT / get_extractor_data_dir(active_env) / "parsed"
    for fqn in relics_raw:
        if not isinstance(fqn, str) or not fqn.strip():
            continue
        short_lbl = relic_menu_label(fqn)
        r_name = short_lbl
        r_type = "active" if ".onuse." in fqn else "passive"
        bp_file = parsed_dir / fqn_to_relative_path(fqn)
        if bp_file.is_file():
            try:
                bp_doc = load_json_file(str(bp_file))
                r_name = bp_doc.get("name") or short_lbl
                r_type = bp_doc.get("type") or r_type
            except Exception:
                pass
        tag_lbl = "On-Use" if r_type == "active" else "Proc"
        relics_list.append(
            {
                "label": f"{r_name} [{tag_lbl}] ({short_lbl})",
                "name": r_name,
                "short_label": short_lbl,
                "type": r_type,
                "fqn": fqn,
            }
        )

    return {
        "environment": active_env,
        "run_configs": run_configs,
        "disciplines": disciplines,
        "builds": builds,
        "choices_files": [],
        "rotations": rotations_files,
        "relics": relics_list,
        "hp_presets": COMMON_HP_PRESETS,
        "stat_keys": list(DEFAULT_STAT_KEYS),
    }


def get_class_gear_options(spec_path: str, env: str = "live") -> dict[str, Any]:
    """Returns class-filtered tacticals, legendaries, and discipline skill-tree metadata."""
    active_env = str(env).lower().strip()
    cand_spec = resolve_env_extractor_path(spec_path, active_env)
    if _resolve_workspace_path(cand_spec).is_file():
        spec_path = cand_spec
    resolved_spec = _resolve_workspace_path(spec_path)
    if not resolved_spec.is_file():
        raise FileNotFoundError(f"Discipline file not found: {spec_path}")

    spec_data = load_json_file(str(resolved_spec))
    class_name, spec_name = discipline_names(spec_data, str(resolved_spec))

    gear_file = _resolve_workspace_path(get_gear_path(active_env))
    gear_data = load_json_file(str(gear_file)) if gear_file.is_file() else {}

    tacticals_map = filter_gear_for_class(gear_data, TACTICAL_PREFIX, class_name)
    legendaries_map = filter_gear_for_class(gear_data, LEGENDARY_PREFIX, class_name)

    tacticals = [
        {"name": name, "fqn": fqn}
        for name, fqn in sorted(tacticals_map.items(), key=lambda x: x[0].lower())
    ]
    legendaries = [
        {"name": name, "fqn": fqn}
        for name, fqn in sorted(legendaries_map.items(), key=lambda x: x[0].lower())
    ]

    parsed_dir = SWTORSIM_ROOT / get_extractor_data_dir(active_env) / "parsed"
    skill_tree_raw = spec_data.get("skill_tree", {})
    skill_tree_info: dict[str, dict[str, list[dict[str, str]]]] = {}
    for lvl, slots in sorted(skill_tree_raw.items(), key=lambda item: int(item[0]) if str(item[0]).isdigit() else 999):
        lvl_str = str(lvl)
        skill_tree_info[lvl_str] = {}
        if isinstance(slots, dict):
            for slot_key, fqns in slots.items():
                entries = []
                for fqn in fqns or []:
                    bp_path = parsed_dir / fqn_to_relative_path(fqn)
                    bp_name = fqn.split(".")[-1].replace("_", " ").title()
                    bp_type = "ability"
                    bp_icon = ""
                    if bp_path.is_file():
                        try:
                            bp_data = load_json_file(str(bp_path))
                            bp_name = bp_data.get("name") or bp_name
                            bp_type = bp_data.get("type") or bp_type
                            bp_icon = bp_data.get("icon") or ""
                        except Exception:
                            pass
                    entry = {"fqn": fqn, "name": bp_name, "type": bp_type}
                    if bp_icon:
                        entry["icon"] = bp_icon
                    entries.append(entry)
                skill_tree_info[lvl_str][str(slot_key)] = entries

    return {
        "class_name": class_name,
        "spec": spec_name,
        "spec_path": _to_workspace_rel(resolved_spec),
        "tacticals": tacticals,
        "legendaries": legendaries,
        "skill_tree": skill_tree_info,
        "skill_tree_levels": sorted(
            (str(k) for k in (spec_data.get("skill_tree") or {}).keys()),
            key=lambda x: int(x) if x.isdigit() else 999,
        ),
    }


def load_run_config_bundle(rel_path: str, env: str = "live") -> dict[str, Any]:
    """Loads a run_config JSON along with its referenced stats and choices dictionaries."""
    active_env = str(env).lower().strip()
    target = _resolve_workspace_path(rel_path)
    if not target.is_file():
        raise FileNotFoundError(f"Run config not found: {rel_path}")

    raw_rc = dict(load_json_file(str(target)))
    spec_path = str(raw_rc.get("spec_path", "")).replace("\\", "/")
    if spec_path:
        cand_spec = resolve_env_extractor_path(spec_path, active_env)
        if _resolve_workspace_path(cand_spec).is_file():
            spec_path = cand_spec
            raw_rc["spec_path"] = cand_spec
    class_name = str(raw_rc.get("class_name") or raw_rc.get("class") or "").strip()
    spec_name = str(raw_rc.get("spec") or raw_rc.get("spec_name") or "").strip()
    gear_opts = {"tacticals": [], "legendaries": [], "skill_tree_levels": []}
    if spec_path:
        try:
            gear_opts = get_class_gear_options(spec_path, env=active_env)
            if gear_opts.get("class_name"):
                class_name = gear_opts["class_name"]
            if gear_opts.get("spec"):
                spec_name = gear_opts["spec"]
        except Exception:
            pass

    if class_name:
        raw_rc.setdefault("class", class_name)
        raw_rc.setdefault("class_name", class_name)
    if spec_name:
        raw_rc.setdefault("spec", spec_name)
        raw_rc.setdefault("spec_name", spec_name)

    stats_data = {}
    if raw_rc.get("stats_path"):
        s_file = _resolve_workspace_path(raw_rc["stats_path"])
        if s_file.is_file():
            stats_data = load_json_file(str(s_file))

    stats_override = raw_rc.get("stats_override")
    if isinstance(stats_override, dict) and stats_override:
        if isinstance(stats_data, dict):
            stats_data.update(stats_override)
    if isinstance(stats_data, dict):
        expand_force_tech_power(stats_data)

    choices_data = {}
    if raw_rc.get("choices_path"):
        c_file = _resolve_workspace_path(raw_rc["choices_path"])
        if c_file.is_file():
            choices_data = load_json_file(str(c_file))

    choices_override = raw_rc.get("choices_override") or raw_rc.get("choices")
    if isinstance(choices_override, dict) and choices_override:
        choices_data.update({str(k): v for k, v in choices_override.items()})

    return {
        "path": _to_workspace_rel(target),
        "name": target.name,
        "class_name": class_name,
        "spec": spec_name,
        "run_config": raw_rc,
        "stats": stats_data,
        "stats_override": stats_override or {},
        "choices": choices_data,
        "gear_options": gear_opts,
    }


def _extract_computed_player_stats(player: Any) -> dict[str, Any]:
    """Extracts human-readable computed player sheet stats after passive initialization."""
    st = getattr(player, "stats", {}) or {}
    gcd_val = player.calculate_gcd(1.5) if hasattr(player, "calculate_gcd") else 1.5
    return {
        "level": int(getattr(player, "level", 85)),
        "resource_type": getattr(getattr(player, "resource", None), "pool_type", "Force"),
        "max_resource": float(getattr(getattr(player, "resource", None), "max_value", 100.0)),
        "mastery": round(float(st.get("Mastery", 0.0)), 1),
        "power": round(float(st.get("Power", 0.0)), 1),
        "force_power": round(float(st.get("Force Power", 0.0)), 1),
        "tech_power": round(float(st.get("Tech Power", 0.0)), 1),
        "crit_rating": round(float(st.get("Critical Rating", 0.0)), 1),
        "alacrity_rating": round(float(st.get("Alacrity Rating", 0.0)), 1),
        "accuracy_rating": round(float(st.get("Accuracy Rating", 0.0)), 1),
        "melee_bonus_dmg": round(float(st.get("M_Bonus_Damage", 0.0)), 1),
        "ranged_bonus_dmg": round(float(st.get("R_Bonus_Damage", 0.0)), 1),
        "force_bonus_dmg": round(float(st.get("F_Bonus_Damage", 0.0)), 1),
        "tech_bonus_dmg": round(float(st.get("T_Bonus_Damage", 0.0)), 1),
        "crit_chance_pct": round(float(st.get("Critical Chance", 0.0)) * 100.0, 2),
        "crit_multiplier_pct": round(float(st.get("Critical Modifier", 0.0)) * 100.0, 2),
        "alacrity_pct": round(float(st.get("Alacrity", 0.0)) * 100.0, 2),
        "accuracy_pct": round(float(st.get("Main Accuracy", 1.0)) * 100.0, 2),
        "gcd_seconds": round(float(gcd_val), 2),
        "main_hand_min": round(float(st.get("Main_hand_min", 0.0)), 1),
        "main_hand_max": round(float(st.get("Main_hand_max", 0.0)), 1),
        "off_hand_min": round(float(st.get("Off_hand_min", 0.0)), 1),
        "off_hand_max": round(float(st.get("Off_hand_max", 0.0)), 1),
        "has_offhand_weapon": float(st.get("Off_hand_max", 0.0)) > 0.0,
    }


def _resolve_simulation_inputs_from_payload(payload: dict[str, Any]) -> tuple[RunConfig, dict[str, Any]]:
    """Validates and resolves a simulation request payload into RunConfig and prepared inputs."""
    env = (payload.get("environment") or payload.get("env") or ("pts" if payload.get("pts") else "live")).lower().strip()
    raw_spec = str(payload.get("spec_path") or "").replace("\\", "/")
    cand_spec = resolve_env_extractor_path(raw_spec, env)
    if _resolve_workspace_path(cand_spec).is_file():
        raw_spec = cand_spec
    spec_path = str(_resolve_workspace_path(raw_spec))
    stats_path = str(_resolve_workspace_path(payload.get("stats_path") or ""))
    rotation_path = str(_resolve_workspace_path(payload.get("rotation_path") or ""))
    raw_choices_path = str(payload.get("choices_path") or "").strip()
    choices_path = str(_resolve_workspace_path(raw_choices_path)) if raw_choices_path else ""

    spec_data = load_json_file(spec_path)
    class_name, spec_name = discipline_names(spec_data, spec_path)

    tactical_fqn = str(payload.get("tactical_fqn") or "").strip()
    legendary_fqns = [
        str(x).strip() for x in (payload.get("legendary_fqns") or []) if str(x).strip()
    ]
    relic_fqns = [
        str(x).strip() for x in (payload.get("relic_fqns") or []) if str(x).strip()
    ]

    mode = str(payload.get("mode") or "TEST").upper()
    if mode not in ("TEST", "BATCH"):
        mode = "TEST"

    iterations = max(1, min(10_000, int(payload.get("iterations") or 50)))
    duration = max(1, int(float(payload.get("duration") or 1000)))
    dummy_hp = max(1_000, int(float(payload.get("dummy_hp") or 6_000_000)))
    level = max(1, min(100, int(payload.get("level") or 85)))

    raw_seed = payload.get("seed")
    seed = int(raw_seed) if (raw_seed is not None and str(raw_seed).strip() != "") else 42
    main_hand_min, main_hand_max = parse_hand_range(payload.get("main_hand"), "main_hand")
    off_hand_min, off_hand_max = parse_hand_range(payload.get("off_hand"), "off_hand")

    training_dummy_armor_debuff = bool(payload.get("training_dummy_armor_debuff", True))
    enable_stem_matching = bool(payload.get("enable_stem_matching", True))
    enable_projectile_flight_time = bool(payload.get("enable_projectile_flight_time", False))
    in_flashpoint_operation = bool(payload.get("in_flashpoint_operation", True))
    combat_distance = max(0.0, float(payload.get("combat_distance", 30.0)))

    # Resolve choices
    choices_data = {}
    if choices_path and Path(choices_path).is_file():
        choices_data = load_json_file(choices_path)
    if isinstance(payload.get("choices_override"), dict) and payload["choices_override"]:
        choices_data = {str(k): int(v) for k, v in payload["choices_override"].items()}
    elif isinstance(payload.get("choices"), dict) and payload["choices"]:
        choices_data = {str(k): int(v) for k, v in payload["choices"].items()}

    config = RunConfig(
        spec_path=_to_workspace_rel(spec_path),
        class_name=class_name,
        spec=spec_name,
        stats_path=_to_workspace_rel(stats_path),
        rotation_path=_to_workspace_rel(rotation_path),
        choices=choices_data,
        choices_path=_to_workspace_rel(choices_path) if choices_path else "",
        main_hand_min=main_hand_min,
        main_hand_max=main_hand_max,
        off_hand_min=off_hand_min,
        off_hand_max=off_hand_max,
        tactical_fqn=tactical_fqn,
        legendary_fqns=legendary_fqns,
        relic_fqns=relic_fqns,
        mode=mode,
        iterations=iterations,
        duration=duration,
        dummy_hp=dummy_hp,
        training_dummy_armor_debuff=training_dummy_armor_debuff,
        enable_stem_matching=enable_stem_matching,
        enable_projectile_flight_time=enable_projectile_flight_time,
        in_flashpoint_operation=in_flashpoint_operation,
        combat_distance=combat_distance,
        level=level,
        seed=seed,
        environment=env,
        precast=str(payload.get("precast") or "").strip(),
        pre_combat=list(payload.get("pre_combat") or []) if isinstance(payload.get("pre_combat"), list) else [],
    )
    from src.swtorsim.settings import set_data_environment
    set_data_environment(env)

    # Apply global simulation toggles
    set_stem_matching(config.enable_stem_matching)
    set_projectile_flight_time(config.enable_projectile_flight_time)
    set_default_combat_distance(config.combat_distance)
    set_in_flashpoint_operation(config.in_flashpoint_operation)

    # Ensure CWD is SWTORSIM_ROOT for validate_run_config relative path checks
    os.chdir(SWTORSIM_ROOT)
    validate_run_config(config)

    baseline = spec_data.get("active_abilities", [])
    tree_fqns = resolve_skill_tree_fqns(spec_data.get("skill_tree", {}), choices_data)
    selected_fqns = [
        *[f for f in baseline if f and f.strip()],
        *[f for f in tree_fqns if f and f.strip()],
        *[f for f in [config.tactical_fqn] if f and f.strip()],
        *[f for f in config.legendary_fqns if f and f.strip()],
        *[f for f in config.relic_fqns if f and f.strip()],
    ]

    with redirect_stdout(io.StringIO()):
        active_parsed_dir = SWTORSIM_ROOT / get_extractor_data_dir(env) / "parsed"
        loadout_key = (env, tuple(selected_fqns))
        if loadout_key not in _BLUEPRINT_LOADOUT_CACHE:
            _BLUEPRINT_LOADOUT_CACHE[loadout_key] = load_complete_loadout(
                selected_fqns, parsed_dir=str(active_parsed_dir)
            )
        loadout_blueprints = _BLUEPRINT_LOADOUT_CACHE[loadout_key]

    stats_config = load_character_stats_from_json(
        config.class_name, stats_path, config.level
    )
    stats_override = payload.get("stats_override")
    if isinstance(stats_override, dict):
        for k, v in stats_override.items():
            if k in ("Main_hand_min", "Main_hand_max", "Off_hand_min", "Off_hand_max"):
                continue
            if v is None or str(v).strip() == "":
                continue
            try:
                stats_config["stats"][str(k)] = float(v)
            except (ValueError, TypeError):
                pass
    expand_force_tech_power(stats_config["stats"])
    apply_weapon_ranges(stats_config["stats"], config)

    rotation_config = load_rotation_from_json(rotation_path)
    debuff_module: dict[str, Any] = {}
    if config.training_dummy_armor_debuff:
        debuff_module.update(load_training_dummy_armor_debuffs())

    return config, {
        "rotation_config": rotation_config,
        "stats_config": stats_config,
        "loadout_blueprints": loadout_blueprints,
        "debuff_module": debuff_module,
        "selected_fqns": selected_fqns,
    }


def preview_character_stats(payload: dict[str, Any]) -> dict[str, Any]:
    """Computes character sheet stats for the current loadout & stat overrides without running a fight."""
    config, sim_inputs = _resolve_simulation_inputs_from_payload(payload)
    with redirect_stdout(io.StringIO()):
        _sim, player, target = prepare_simulation(
            sim_inputs["rotation_config"],
            sim_inputs["stats_config"],
            sim_inputs["loadout_blueprints"],
            config.dummy_hp,
            sim_inputs["debuff_module"],
        )
    return {
        "class_name": config.class_name,
        "spec": config.spec,
        "computed_player_stats": _extract_computed_player_stats(player),
        "target_armor": round(float(target.stats.get("Armor", 0.0)), 1),
    }


def _format_ability_breakdown_rows(
    breakdown_dict: dict[str, dict[str, Any]],
    phase_duration: float,
    phase_total_damage: float,
    extra_stats: dict[str, dict[str, Any]] | None = None,
    iterations: int = 1,
    cast_counts: dict[str, int] | None = None,
) -> list[dict[str, Any]]:
    """Formats ability damage breakdown into sorted JSON-serializable rows.

    ``cast_counts`` holds summed cast counts per ability name. Damage rows with no matching cast
    (DoT ticks, procs) get ``casts``/``dmg_per_cast`` of None.
    """
    rows: list[dict[str, Any]] = []
    sorted_items = sorted(
        breakdown_dict.items(),
        key=lambda item: item[1].get("total_damage", 0.0),
        reverse=True,
    )
    for name, data in sorted_items:
        total_dmg = float(data.get("total_damage", 0.0))
        hits = int(data.get("hit_count", 0))
        crits = int(data.get("crit_count", 0))
        attack_types = sorted(data.get("attack_types", ()))
        damage_types = sorted(data.get("damage_types", ()))
        type_desc = format_type_descriptor(attack_types, damage_types)

        dps = total_dmg / phase_duration if phase_duration > 0 else 0.0
        share_pct = (total_dmg / phase_total_damage * 100.0) if phase_total_damage > 0 else 0.0
        crit_pct = (crits / hits * 100.0) if hits > 0 else 0.0
        avg_hit = (total_dmg / hits) if hits > 0 else 0.0

        row: dict[str, Any] = {
            "name": name,
            "type_desc": type_desc,
            "attack_types": [ATTACK_TYPE_NAMES.get(a, str(a)) for a in attack_types],
            "damage_types": [DAMAGE_TYPE_NAMES.get(d, str(d)) for d in damage_types],
            "total_damage": round(total_dmg / iterations, 1),
            "dps": round(dps, 1),
            "share_pct": round(share_pct, 2),
            "hits": round(hits / iterations, 1) if iterations > 1 else hits,
            "crits": round(crits / iterations, 1) if iterations > 1 else crits,
            "crit_pct": round(crit_pct, 1),
            "avg_hit": round(avg_hit, 0),
        }
        casts = int((cast_counts or {}).get(name, 0))
        row["casts"] = (round(casts / iterations, 1) if iterations > 1 else casts) if casts > 0 else None
        row["dmg_per_cast"] = round(total_dmg / casts, 0) if casts > 0 else None
        if extra_stats and name in extra_stats:
            ex = extra_stats[name]
            row["min_hit"] = round(float(ex.get("min_hit", 0.0)), 0)
            row["max_hit"] = round(float(ex.get("max_hit", 0.0)), 0)
        rows.append(row)
    return rows


def _run_single_test_detailed(
    config: RunConfig,
    sim_inputs: dict[str, Any],
) -> dict[str, Any]:
    """Executes a single TEST run and captures detailed breakdown, buff windows, and combat log."""
    random.seed(config.seed)
    t0 = time.perf_counter()

    stdout_buf = io.StringIO()
    combat_events: list[dict[str, Any]] = []
    ability_extra: dict[str, dict[str, Any]] = {}

    with redirect_stdout(stdout_buf):
        sim, player, target = prepare_simulation(
            sim_inputs["rotation_config"],
            sim_inputs["stats_config"],
            sim_inputs["loadout_blueprints"],
            config.dummy_hp,
            sim_inputs["debuff_module"],
            seed=config.seed,
            config=config,
        )
        player.combat_distance = config.combat_distance
        target.combat_distance = config.combat_distance


        computed_stats = _extract_computed_player_stats(player)

        # Wrap ability casts to record cast events & cast counts
        for abl in set(player.ability_db.values()):
            orig_cast = abl.cast

            def _make_cast_wrapper(ability_obj, fn):
                def _wrapped_cast(caster, tgt, s):
                    # Instant abilities resolve their damage inside fn(), which logs
                    # damage events before fn() returns. Remember where this cast
                    # belongs so it can be inserted ahead of those same-tick hits.
                    insert_idx = len(combat_events)
                    ok = fn(caster, tgt, s)
                    if ok:
                        a_name = ability_obj.name or ability_obj.fqn
                        res_val = round(float(getattr(caster.resource, "current_value", 0.0)), 1)
                        hp_pct = round(float(tgt.hp_ratio) * 100.0, 1)
                        combat_events.insert(
                            insert_idx,
                            {
                                "time": round(float(s.current_time), 4),
                                "category": "cast",
                                "ability": a_name,
                                "triggers_gcd": bool(ability_obj.triggers_gcd),
                                "damage": 0.0,
                                "is_crit": False,
                                "target_hp": round(float(tgt.hp), 0),
                                "target_hp_pct": hp_pct,
                                "resource": res_val,
                                "text": f"Casts {a_name}" + ("" if ability_obj.triggers_gcd else " (off-GCD)"),
                            }
                        )
                    return ok

                return _wrapped_cast

            abl.cast = _make_cast_wrapper(abl, orig_cast)

        # Per-cast rows (step, buffs, cast/channel timing) for the Cast Timeline window (display only)
        cast_recorder = CastTimelineRecorder(player).install()

        # Wrap tracker.log_damage to record min/max hits and structured damage events
        orig_log_damage = sim.tracker.log_damage

        def _wrapped_log_damage(
            ability_name: str,
            dmg_value: float,
            is_crit: bool,
            tgt: Any,
            current_time: float,
            attack_type: int = None,
            damage_type: int = None,
        ):
            orig_log_damage(
                ability_name,
                dmg_value,
                is_crit,
                tgt,
                current_time,
                attack_type=attack_type,
                damage_type=damage_type,
            )
            ex = ability_extra.setdefault(
                ability_name,
                {"min_hit": float("inf"), "max_hit": 0.0},
            )
            if dmg_value < ex["min_hit"]:
                ex["min_hit"] = dmg_value
            if dmg_value > ex["max_hit"]:
                ex["max_hit"] = dmg_value

            new_hp = max(0.0, float(tgt.hp) - float(dmg_value))
            hp_pct = round((new_hp / float(tgt.max_hp)) * 100.0, 1) if tgt.max_hp > 0 else 0.0
            res_val = round(float(getattr(player.resource, "current_value", 0.0)), 1)
            dt_name = DAMAGE_TYPE_NAMES.get(damage_type, "")
            combat_events.append(
                {
                    "time": round(float(current_time), 4),
                    "category": "damage",
                    "ability": ability_name,
                    "damage": round(float(dmg_value), 0),
                    "is_crit": bool(is_crit),
                    "damage_type": dt_name,
                    "target_hp": round(new_hp, 0),
                    "target_hp_pct": hp_pct,
                    "resource": res_val,
                    "text": f"{ability_name} hits for {dmg_value:,.0f}"
                    + (" (CRIT!)" if is_crit else "")
                    + (f" [{dt_name}]" if dt_name else ""),
                }
            )

        sim.tracker.log_damage = _wrapped_log_damage

        # Wrap stall logging to record structured stall & deadlock events in the combat log
        orig_stall_end = sim.tracker.log_rotation_stall_end
        def _wrapped_stall_end(timestamp: float):
            active = sim.tracker._active_stall
            if active:
                dur = round(max(0.0, timestamp - active["start"]), 2)
                res_val = round(float(getattr(player.resource, "current_value", 0.0)), 1)
                hp_pct = round(float(target.hp_ratio) * 100.0, 1)
                combat_events.append({
                    "time": round(float(timestamp), 4),
                    "_stall_start": float(active["start"]),
                    "category": "stall",
                    "ability": active.get("step_info", "Rotation Stall"),
                    "damage": 0.0,
                    "is_crit": False,
                    "damage_type": "",
                    "target_hp": round(float(target.hp), 0),
                    "target_hp_pct": hp_pct,
                    "resource": res_val,
                    "text": f"Rotation stalled for {dur:.2f}s (from {{start}}s) on step #{active['step_index']}: {active['step_info']}",
                })
            orig_stall_end(timestamp)
        sim.tracker.log_rotation_stall_end = _wrapped_stall_end

        orig_finalize_stalls = sim.tracker.finalize_stalls
        def _wrapped_finalize_stalls(current_time: float):
            active = sim.tracker._active_stall
            if active:
                dur = round(max(0.0, current_time - active["start"]), 2)
                res_val = round(float(getattr(player.resource, "current_value", 0.0)), 1)
                hp_pct = round(float(target.hp_ratio) * 100.0, 1)
                combat_events.append({
                    "time": round(float(current_time), 4),
                    "_stall_start": float(active["start"]),
                    "category": "deadlock",
                    "ability": active.get("step_info", "Rotation Deadlock"),
                    "damage": 0.0,
                    "is_crit": False,
                    "damage_type": "",
                    "target_hp": round(float(target.hp), 0),
                    "target_hp_pct": hp_pct,
                    "resource": res_val,
                    "text": f"Rotation permanently deadlocked at {{start}}s (stalled for {dur:.2f}s) on step #{active['step_index']}: {active['step_info']}",
                })
            orig_finalize_stalls(current_time)
        sim.tracker.finalize_stalls = _wrapped_finalize_stalls

        sim.run_timed(duration=config.duration, target=target)
        sim.tracker.finalize_effects(sim.current_time)
        combat_events.sort(key=lambda ev: ev["time"])
        time_origin = sim.time_origin()
        for ev in combat_events:
            ev["time"] = round(ev["time"] - time_origin, 2)
            if "_stall_start" in ev:
                ev["text"] = ev["text"].replace("{start}", f"{ev.pop('_stall_start') - time_origin:.2f}")

    wall_ms = round((time.perf_counter() - t0) * 1000.0, 1)
    combat_start = sim.combat_start_time if getattr(sim, "combat_start_time", None) is not None else 0.0
    fight_duration = max(0.0, float(sim.current_time) - combat_start)
    total_damage = float(sim.tracker.total_damage)
    dps = total_damage / fight_duration if fight_duration > 0 else 0.0

    for ex in ability_extra.values():
        if ex["min_hit"] == float("inf"):
            ex["min_hit"] = 0.0

    breakdown_rows = _format_ability_breakdown_rows(
        sim.tracker.breakdown,
        fight_duration,
        total_damage,
        extra_stats=ability_extra,
        iterations=1,
        cast_counts=sim.tracker.cast_counts,
    )

    exec_start_raw = getattr(sim.tracker, "execute_start_time", None)
    exec_start = (float(exec_start_raw) - time_origin) if exec_start_raw is not None else None
    exec_total_dmg = float(getattr(sim.tracker, "total_execute_damage", 0.0))
    if exec_start is not None and fight_duration > exec_start and exec_total_dmg > 0:
        exec_dur = fight_duration - exec_start
        exec_dps = exec_total_dmg / exec_dur if exec_dur > 0 else 0.0
        exec_rows = _format_ability_breakdown_rows(
            sim.tracker.execute_breakdown,
            exec_dur,
            exec_total_dmg,
            iterations=1,
            cast_counts=sim.tracker.execute_cast_counts,
        )
        execute_phase = {
            "active": True,
            "start_time": round(float(exec_start), 2),
            "duration": round(exec_dur, 2),
            "total_damage": round(exec_total_dmg, 0),
            "dps": round(exec_dps, 1),
        }
    else:
        exec_rows = []
        execute_phase = {
            "active": False,
            "start_time": None,
            "duration": 0.0,
            "total_damage": 0.0,
            "dps": 0.0,
        }

    # Format buff and debuff active windows
    buff_rows: list[dict[str, Any]] = []
    for (entity_name, eff_name), windows in sim.tracker.effect_history.items():
        if not has_proper_effect_name(eff_name):
            continue
        merged_windows: list[dict[str, Any]] = []
        total_active = 0.0
        for w in windows:
            s_t = round(float(w["start"]) - time_origin, 2)
            e_t = round(float(w["end"]) - time_origin, 2)
            dur = round(max(0.0, float(w["duration"])), 2)
            if dur <= 0.0:
                continue
            # Uptime counts only the in-fight part of each window (pre-pull time excluded)
            total_active += max(0.0, min(e_t, fight_duration) - max(s_t, 0.0))
            merged_windows.append(
                {
                    "start": s_t,
                    "end": e_t,
                    "duration": dur,
                    "max_stacks": int(w.get("max_stacks", 1)),
                }
            )
        if not merged_windows:
            continue
        pct = min(100.0, (total_active / fight_duration) * 100.0) if fight_duration > 0 else 0.0
        max_stacks_overall = max((w["max_stacks"] for w in merged_windows), default=1)
        buff_rows.append(
            {
                "name": eff_name,
                "entity": entity_name,
                "is_target": entity_name == target.name,
                "count": len(merged_windows),
                "max_stacks": max_stacks_overall,
                "total_uptime": round(total_active, 2),
                "uptime_pct": round(pct, 1),
                "windows": merged_windows,
            }
        )
    buff_rows.sort(key=lambda r: (r["is_target"], -r["total_uptime"]))

    # Cast Timeline payload (tools/rotation_timeline_ui.html): casts, rotation snapshot, icon/name maps,
    # and exact player-buff windows (the 10 with the most uptime) instead of per-cast samples.
    timeline_casts = cast_recorder.finalize(time_origin)
    timeline_steps = rotation_steps_of(sim_inputs["rotation_config"])
    pre_runner = getattr(player, "pre_combat", None)
    cast_timeline = {
        "casts": timeline_casts,
        "rotation": timeline_steps,
        **cast_recorder.ability_maps(timeline_steps),
        "buff_windows": [
            {"name": b["name"], "windows": [[w["start"], w["end"]] for w in b["windows"]]}
            for b in sorted(
                (b for b in buff_rows if not b["is_target"]), key=lambda b: -b["total_uptime"]
            )[:10]
        ],
        "tactical_swaps": [
            {**sw, "combat_time": round(float(sw["t"]) - time_origin, 2)}
            for sw in (getattr(pre_runner, "swaps", None) or [])
        ],
    }

    total_hits = sum(int(d.get("hit_count", 0)) for d in sim.tracker.breakdown.values())
    total_crits = sum(int(d.get("crit_count", 0)) for d in sim.tracker.breakdown.values())
    overall_crit_pct = (total_crits / total_hits * 100.0) if total_hits > 0 else 0.0

    return {
        "mode": "TEST",
        "environment": config.environment,
        "class_name": config.class_name,
        "spec": config.spec,
        "level": config.level,
        "dummy_hp": config.dummy_hp,
        "seed": config.seed,
        "elapsed_wall_ms": wall_ms,
        "duration": round(fight_duration, 2),
        "pre_combat_duration": round(max(0.0, time_origin), 2),
        "total_damage": round(total_damage, 0),
        "dps": round(dps, 1),
        "total_hits": total_hits,
        "total_crits": total_crits,
        "overall_crit_pct": round(overall_crit_pct, 1),
        "target_remaining_hp": round(max(0.0, float(target.hp)), 0),
        "killed_target": bool(target.hp <= 0),
        "computed_player_stats": computed_stats,
        "execute_phase": execute_phase,
        "breakdown": breakdown_rows,
        "execute_breakdown": exec_rows,
        "buffs": buff_rows,
        "combat_log": combat_events,
        "cast_timeline": cast_timeline,
        "stalls": {
            "total_stalled_time": round(sim.tracker.total_stalled_time, 2),
            "stall_count": len(sim.tracker.stall_events),
            "permanent_stall": sim.tracker.permanent_stall,
            "events": [
                {
                    **ev,
                    "start": round(float(ev["start"]) - time_origin, 2),
                    **({"end": round(float(ev["end"]) - time_origin, 2)} if ev.get("end") is not None else {}),
                }
                for ev in sim.tracker.stall_events
            ],
        },
    }


_SIMULATION_POOL_LOCK = threading.Lock()
_GLOBAL_SIMULATION_POOL: Any = None
_GLOBAL_SIMULATION_POOL_KEY: Any = None
_WORKER_SIM_CONTEXT: dict[str, Any] = {}


def _init_batch_worker(sim_context: dict[str, Any]) -> None:
    """Initializes worker process with the heavy simulation context (blueprints, rotation, etc.)."""
    global _WORKER_SIM_CONTEXT
    _WORKER_SIM_CONTEXT = sim_context


def _is_pycharm_plot_helper_dir(path_entry: str) -> bool:
    """True for PyCharm's `pycharm_<lib>_backend` helper directories (each ships a `sitecustomize.py`)."""
    name = os.path.basename(os.path.normpath(path_entry)).lower()
    return name.startswith("pycharm_") and name.endswith("_backend")


def _prepare_worker_environment() -> None:
    """Keeps pool workers from loading matplotlib / numpy (OpenBLAS) at interpreter start-up.

    A PyCharm run configuration puts its plot-helper directories on PYTHONPATH. Their
    `sitecustomize.py` imports matplotlib in every Python child, so each pool worker commits
    one OpenBLAS buffer per core (about 780 MB on 24 cores) before it runs any of our code.
    When Windows cannot grant that memory OpenBLAS exits the worker, and `Pool()` then blocks
    forever writing start-up data to a pipe nobody reads (BATCH stuck at 0%).

    Workers inherit `os.environ` whenever they are spawned, including later respawns by the
    pool, so the change is made in place and stays for the life of the server.
    """
    python_path = os.environ.get("PYTHONPATH")
    if python_path:
        entries = [entry for entry in python_path.split(os.pathsep) if entry]
        kept = [entry for entry in entries if not _is_pycharm_plot_helper_dir(entry)]
        if len(kept) != len(entries):
            if kept:
                os.environ["PYTHONPATH"] = os.pathsep.join(kept)
            else:
                del os.environ["PYTHONPATH"]
    # Safety net if a worker ever imports numpy anyway; an explicit user value wins.
    os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")


def get_or_create_simulation_pool(cores: int, sim_context: dict[str, Any], pool_key: Any) -> Any:
    """Returns a warm, persistent worker pool pre-loaded with static simulation context."""
    global _GLOBAL_SIMULATION_POOL, _GLOBAL_SIMULATION_POOL_KEY
    with _SIMULATION_POOL_LOCK:
        if _GLOBAL_SIMULATION_POOL is None or _GLOBAL_SIMULATION_POOL_KEY != pool_key:
            if _GLOBAL_SIMULATION_POOL is not None:
                try:
                    _GLOBAL_SIMULATION_POOL.close()
                    _GLOBAL_SIMULATION_POOL.terminate()
                    _GLOBAL_SIMULATION_POOL.join()
                except Exception:
                    pass
            _prepare_worker_environment()
            _GLOBAL_SIMULATION_POOL = Pool(
                processes=cores,
                initializer=_init_batch_worker,
                initargs=(sim_context,),
            )
            _GLOBAL_SIMULATION_POOL_KEY = pool_key
        return _GLOBAL_SIMULATION_POOL


def cleanup_simulation_pool() -> None:
    """Terminates persistent worker pool on shutdown."""
    global _GLOBAL_SIMULATION_POOL
    with _SIMULATION_POOL_LOCK:
        if _GLOBAL_SIMULATION_POOL is not None:
            try:
                _GLOBAL_SIMULATION_POOL.close()
                _GLOBAL_SIMULATION_POOL.terminate()
                _GLOBAL_SIMULATION_POOL.join()
            except Exception:
                pass
            _GLOBAL_SIMULATION_POOL = None


atexit.register(cleanup_simulation_pool)


def _run_task_chunk(task_fn: Any, chunk: list) -> list[dict[str, Any]]:
    """Runs a chunk of batch payloads in a pool worker (chunks let the parent poll for cancellation)."""
    return [task_fn(p) for p in chunk]


def _batch_worker_task(args: tuple) -> dict[str, Any]:
    """Worker function for parallel Monte Carlo simulations."""
    if len(args) == 4:
        run_id, base_seed, duration, dummy_hp = args
        ctx = _WORKER_SIM_CONTEXT
        rotation_config = ctx["rotation_config"]
        stats_config = ctx["stats_config"]
        loadout_blueprints = ctx["loadout_blueprints"]
        debuff_module = ctx["debuff_module"]
        settings_dict = ctx["settings_dict"]
    else:
        (
            run_id,
            base_seed,
            duration,
            dummy_hp,
            rotation_config,
            stats_config,
            loadout_blueprints,
            debuff_module,
            settings_dict,
        ) = args

    set_stem_matching(settings_dict["enable_stem_matching"])
    set_projectile_flight_time(settings_dict["enable_projectile_flight_time"])
    set_default_combat_distance(settings_dict["combat_distance"])
    set_in_flashpoint_operation(settings_dict["in_flashpoint_operation"])

    worker_seed = (int(base_seed) + int(run_id)) if base_seed is not None else None
    if worker_seed is not None:
        random.seed(worker_seed)

    old_stdout = sys.stdout
    sys.stdout = open(os.devnull, "w")
    try:
        precast = settings_dict.get("precast")
        pre_combat = settings_dict.get("pre_combat")
        sim, player, target = prepare_simulation(
            rotation_config,
            stats_config,
            loadout_blueprints,
            dummy_hp,
            debuff_module,
            verbose=False,
            seed=worker_seed,
            precast=precast,
            pre_combat=pre_combat,
        )
        player.combat_distance = settings_dict["combat_distance"]
        target.combat_distance = settings_dict["combat_distance"]

        sim.run_timed(duration, target)
    finally:
        sys.stdout.close()
        sys.stdout = old_stdout

    combat_start = sim.combat_start_time if getattr(sim, "combat_start_time", None) is not None else 0.0
    elapsed_time = max(0.0, float(sim.current_time) - combat_start)
    calculated_dps = float(sim.tracker.total_damage) / elapsed_time if elapsed_time > 0 else 0.0

    ability_data_summary = {
        name: {
            "total_damage": data["total_damage"],
            "hit_count": data["hit_count"],
            "crit_count": data.get("crit_count", 0),
            "attack_types": list(data.get("attack_types", ())),
            "damage_types": list(data.get("damage_types", ())),
        }
        for name, data in sim.tracker.breakdown.items()
    }

    execute_data_summary = {
        name: {
            "total_damage": data["total_damage"],
            "hit_count": data["hit_count"],
            "crit_count": data.get("crit_count", 0),
            "attack_types": list(data.get("attack_types", ())),
            "damage_types": list(data.get("damage_types", ())),
        }
        for name, data in getattr(sim.tracker, "execute_breakdown", {}).items()
    }

    execute_start = getattr(sim.tracker, "execute_start_time", None)
    execute_dur = max(0.0, float(sim.current_time) - execute_start) if execute_start is not None else 0.0

    return {
        "cast_counts": dict(sim.tracker.cast_counts),
        "execute_cast_counts": dict(sim.tracker.execute_cast_counts),
        "run_id": run_id + 1,
        "dps": calculated_dps,
        "total_damage": float(sim.tracker.total_damage),
        "elapsed": elapsed_time,
        "abilities": ability_data_summary,
        "total_execute_damage": float(getattr(sim.tracker, "total_execute_damage", 0.0)),
        "execute_duration": float(execute_dur),
        "execute_abilities": execute_data_summary,
        "stall_count": len(getattr(sim.tracker, "stall_events", [])),
        "total_stalled_time": float(getattr(sim.tracker, "total_stalled_time", 0.0)),
        "permanent_stall": bool(getattr(sim.tracker, "permanent_stall", False)),
        "seed": worker_seed,
    }


def _compute_histogram_bins(values: list[float]) -> list[dict[str, Any]]:
    """Computes clean Sturges/Freedman-Diaconis histogram bins for the frontend chart."""
    if not values:
        return []
    lo = min(values)
    hi = max(values)
    n = len(values)
    if math.isclose(lo, hi):
        return [{"x0": round(lo - 10, 1), "x1": round(hi + 10, 1), "count": n, "pct": 100.0}]

    num_bins = max(5, min(24, int(math.ceil(math.log2(n) + 1)) + 2))
    step = (hi - lo) / num_bins
    bins: list[dict[str, Any]] = []
    for i in range(num_bins):
        b0 = lo + i * step
        b1 = lo + (i + 1) * step if i < num_bins - 1 else hi
        bins.append({"x0": round(b0, 1), "x1": round(b1, 1), "count": 0, "pct": 0.0})

    for v in values:
        idx = int((v - lo) / step)
        if idx >= num_bins:
            idx = num_bins - 1
        bins[idx]["count"] += 1

    for b in bins:
        b["pct"] = round((b["count"] / n) * 100.0, 1)
    return bins


def _run_batch_monte_carlo_detailed(
    config: RunConfig,
    sim_inputs: dict[str, Any],
) -> dict[str, Any]:
    """Executes a Monte Carlo BATCH simulation and returns aggregated stats and distribution data."""
    iterations = config.iterations

    # Compute player sheet stats once
    with redirect_stdout(io.StringIO()):
        _sim0, player0, _target0 = prepare_simulation(
            sim_inputs["rotation_config"],
            sim_inputs["stats_config"],
            sim_inputs["loadout_blueprints"],
            config.dummy_hp,
            sim_inputs["debuff_module"],
        )
        computed_stats = _extract_computed_player_stats(player0)

    settings_dict = {
        "enable_stem_matching": config.enable_stem_matching,
        "enable_projectile_flight_time": config.enable_projectile_flight_time,
        "combat_distance": config.combat_distance,
        "in_flashpoint_operation": config.in_flashpoint_operation,
        "precast": getattr(config, "precast", ""),
        "pre_combat": getattr(config, "pre_combat", []),
    }

    sim_context = {
        "rotation_config": sim_inputs["rotation_config"],
        "stats_config": sim_inputs["stats_config"],
        "loadout_blueprints": sim_inputs["loadout_blueprints"],
        "debuff_module": sim_inputs["debuff_module"],
        "settings_dict": settings_dict,
    }

    stats_tuple = tuple(sorted(sim_inputs["stats_config"].get("stats", {}).items()))
    settings_tuple = (
        settings_dict["enable_stem_matching"],
        settings_dict["enable_projectile_flight_time"],
        settings_dict["combat_distance"],
        settings_dict["in_flashpoint_operation"],
    )
    selected_fqns_tuple = tuple(sim_inputs.get("selected_fqns") or ())
    cores = max(1, min(cpu_count() or 2, iterations))
    pool_key = (
        cores,
        selected_fqns_tuple,
        config.stats_path,
        config.rotation_path,
        stats_tuple,
        settings_tuple,
        config.training_dummy_armor_debuff,
    )

    t0 = time.perf_counter()
    payloads = [
        (
            i,
            config.seed,
            config.duration,
            config.dummy_hp,
        )
        for i in range(iterations)
    ]

    _SIM_CANCEL.clear()
    _update_simulation_progress(True, "BATCH", 0, iterations)
    harvested: list[dict[str, Any]] = []
    try:
        is_emscripten = sys.platform == "emscripten" or getattr(sys, "_emscripten_info", None) is not None
        if iterations <= 1 or is_emscripten:
            global _WORKER_SIM_CONTEXT
            _WORKER_SIM_CONTEXT = sim_context
            for idx, p in enumerate(payloads, 1):
                if _SIM_CANCEL.is_set():
                    raise SimulationCancelled()
                harvested.append(_batch_worker_task(p))
                _update_simulation_progress(True, "BATCH", idx, iterations)
        else:
            from src.swtorsim.web_gui import _batch_worker_task as _parallel_worker

            chunk_size = max(1, int(round(iterations * 0.01)))
            pool = get_or_create_simulation_pool(cores, sim_context, pool_key)
            print(f"Using {cores} CPU Cores (Warm Persistent Pool, chunksize={chunk_size})")
            pending = [
                pool.apply_async(_run_task_chunk, (_parallel_worker, payloads[i : i + chunk_size]))
                for i in range(0, iterations, chunk_size)
            ]
            while pending:
                if _SIM_CANCEL.is_set():
                    # Terminating the pool drops queued runs; it is rebuilt on the next batch.
                    cleanup_simulation_pool()
                    raise SimulationCancelled()
                still_pending = []
                for async_res in pending:
                    if async_res.ready():
                        harvested.extend(async_res.get())
                    else:
                        still_pending.append(async_res)
                if len(still_pending) != len(pending):
                    _update_simulation_progress(True, "BATCH", len(harvested), iterations)
                pending = still_pending
                if pending:
                    time.sleep(0.05)
            harvested.sort(key=lambda r: r["run_id"])
            print(f"Runs completed in {time.perf_counter() - t0:.3f} seconds!")
    finally:
        _update_simulation_progress(False, "BATCH", len(harvested), iterations)

    wall_ms = round((time.perf_counter() - t0) * 1000.0, 1)
    return _aggregate_batch_results(harvested, config, wall_ms, iterations, computed_stats)


def _aggregate_batch_results(
    harvested: list[dict[str, Any]],
    config: RunConfig,
    wall_ms: float,
    iterations: int,
    computed_stats: dict[str, Any],
) -> dict[str, Any]:
    """Calculates statistical distributions and ability breakdowns from harvested runs."""
    all_dps = [float(r["dps"]) for r in harvested]
    all_durations = [float(r["elapsed"]) for r in harvested]
    total_time = sum(all_durations)
    total_damage_all = sum(float(r["total_damage"]) for r in harvested)

    macro_breakdown: dict[str, dict[str, Any]] = {}
    macro_exec_breakdown: dict[str, dict[str, Any]] = {}
    macro_cast_counts: dict[str, int] = {}
    macro_exec_cast_counts: dict[str, int] = {}
    total_exec_damage = 0.0
    total_exec_duration = 0.0

    for result in harvested:
        total_exec_damage += result.get("total_execute_damage", 0.0)
        total_exec_duration += result.get("execute_duration", 0.0)
        for name, n in result.get("cast_counts", {}).items():
            macro_cast_counts[name] = macro_cast_counts.get(name, 0) + n
        for name, n in result.get("execute_cast_counts", {}).items():
            macro_exec_cast_counts[name] = macro_exec_cast_counts.get(name, 0) + n

        for name, data in result["abilities"].items():
            entry = macro_breakdown.setdefault(
                name,
                {
                    "total_damage": 0.0,
                    "hit_count": 0,
                    "crit_count": 0,
                    "attack_types": set(),
                    "damage_types": set(),
                },
            )
            entry["total_damage"] += data["total_damage"]
            entry["hit_count"] += data["hit_count"]
            entry["crit_count"] += data.get("crit_count", 0)
            entry["attack_types"].update(data.get("attack_types", ()))
            entry["damage_types"].update(data.get("damage_types", ()))

        for name, data in result.get("execute_abilities", {}).items():
            entry = macro_exec_breakdown.setdefault(
                name,
                {
                    "total_damage": 0.0,
                    "hit_count": 0,
                    "crit_count": 0,
                    "attack_types": set(),
                    "damage_types": set(),
                },
            )
            entry["total_damage"] += data["total_damage"]
            entry["hit_count"] += data["hit_count"]
            entry["crit_count"] += data.get("crit_count", 0)
            entry["attack_types"].update(data.get("attack_types", ()))
            entry["damage_types"].update(data.get("damage_types", ()))

    avg_dps = sum(all_dps) / len(all_dps)
    median_dps = statistics.median(all_dps)
    min_dps = min(all_dps)
    max_dps = max(all_dps)
    std_dev = math.sqrt(sum((x - avg_dps) ** 2 for x in all_dps) / len(all_dps))
    avg_duration = total_time / len(all_dps)
    avg_total_damage = total_damage_all / len(all_dps)

    sorted_dps = sorted(all_dps)
    def _percentile(p: float) -> float:
        idx = (len(sorted_dps) - 1) * p
        lo_i = int(math.floor(idx))
        hi_i = int(math.ceil(idx))
        if lo_i == hi_i:
            return sorted_dps[lo_i]
        return sorted_dps[lo_i] + (sorted_dps[hi_i] - sorted_dps[lo_i]) * (idx - lo_i)

    breakdown_rows = _format_ability_breakdown_rows(
        macro_breakdown,
        total_time,
        total_damage_all,
        iterations=iterations,
        cast_counts=macro_cast_counts,
    )

    if total_exec_duration > 0 and total_exec_damage > 0:
        avg_exec_dps = total_exec_damage / total_exec_duration
        avg_exec_dur = total_exec_duration / iterations
        exec_rows = _format_ability_breakdown_rows(
            macro_exec_breakdown,
            total_exec_duration,
            total_exec_damage,
            iterations=iterations,
            cast_counts=macro_exec_cast_counts,
        )
        execute_phase = {
            "active": True,
            "start_time": None,
            "duration": round(avg_exec_dur, 2),
            "total_damage": round(total_exec_damage / iterations, 0),
            "dps": round(avg_exec_dps, 1),
        }
    else:
        exec_rows = []
        execute_phase = {
            "active": False,
            "start_time": None,
            "duration": 0.0,
            "total_damage": 0.0,
            "dps": 0.0,
        }

    total_hits = sum(int(d.get("hit_count", 0)) for d in macro_breakdown.values())
    total_crits = sum(int(d.get("crit_count", 0)) for d in macro_breakdown.values())
    overall_crit_pct = (total_crits / total_hits * 100.0) if total_hits > 0 else 0.0

    stalled_runs = [r for r in harvested if r.get("stall_count", 0) > 0]
    deadlocked_runs = [r for r in harvested if r.get("permanent_stall", False)]
    stalled_seeds = [r["seed"] for r in stalled_runs if r.get("seed") is not None]
    deadlocked_seeds = [r["seed"] for r in deadlocked_runs if r.get("seed") is not None]
    total_stalled_time = sum(float(r.get("total_stalled_time", 0.0)) for r in harvested)

    return {
        "mode": "BATCH",
        "environment": config.environment,
        "iterations": iterations,
        "class_name": config.class_name,
        "spec": config.spec,
        "level": config.level,
        "dummy_hp": config.dummy_hp,
        "seed": config.seed,
        "elapsed_wall_ms": wall_ms,
        "duration": round(avg_duration, 2),
        "total_damage": round(avg_total_damage, 0),
        "dps": round(avg_dps, 1),
        "avg_dps": round(avg_dps, 1),
        "median_dps": round(median_dps, 1),
        "min_dps": round(min_dps, 1),
        "max_dps": round(max_dps, 1),
        "std_dev": round(std_dev, 1),
        "ci_95": round(1.96 * std_dev / math.sqrt(iterations), 1),
        "p10_dps": round(_percentile(0.10), 1),
        "p25_dps": round(_percentile(0.25), 1),
        "p75_dps": round(_percentile(0.75), 1),
        "p90_dps": round(_percentile(0.90), 1),
        "all_dps": [round(x, 1) for x in all_dps],
        "histogram_bins": _compute_histogram_bins(all_dps),
        "total_hits": round(total_hits / iterations, 1),
        "total_crits": round(total_crits / iterations, 1),
        "overall_crit_pct": round(overall_crit_pct, 1),
        "computed_player_stats": computed_stats,
        "execute_phase": execute_phase,
        "breakdown": breakdown_rows,
        "execute_breakdown": exec_rows,
        "buffs": [],
        "combat_log": [],
        "stalls": {
            "stalled_runs_count": len(stalled_runs),
            "deadlocked_runs_count": len(deadlocked_runs),
            "stalled_seeds": stalled_seeds[:50],
            "deadlocked_seeds": deadlocked_seeds[:50],
            "avg_stalled_time": round(total_stalled_time / len(harvested), 2) if harvested else 0.0,
        },
    }


def execute_simulation_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Resolves the payload and runs either TEST or BATCH simulation."""
    config, sim_inputs = _resolve_simulation_inputs_from_payload(payload)
    if config.mode == "BATCH":
        return _run_batch_monte_carlo_detailed(config, sim_inputs)
    return _run_single_test_detailed(config, sim_inputs)

def execute_simulation_slice(payload: dict[str, Any]) -> dict[str, Any]:
    """Runs a chunk/slice of Monte Carlo runs for a Web Worker thread in parallel."""
    start_run_id = int(payload.get("start_run_id") or 0)
    slice_count = int(payload.get("slice_count") or 1)
    config, sim_inputs = _resolve_simulation_inputs_from_payload(payload)

    settings_dict = {
        "enable_stem_matching": config.enable_stem_matching,
        "enable_projectile_flight_time": config.enable_projectile_flight_time,
        "combat_distance": config.combat_distance,
        "in_flashpoint_operation": config.in_flashpoint_operation,
        "precast": getattr(config, "precast", ""),
        "pre_combat": getattr(config, "pre_combat", []),
    }
    sim_context = {
        "rotation_config": sim_inputs["rotation_config"],
        "stats_config": sim_inputs["stats_config"],
        "loadout_blueprints": sim_inputs["loadout_blueprints"],
        "debuff_module": sim_inputs["debuff_module"],
        "settings_dict": settings_dict,
    }
    global _WORKER_SIM_CONTEXT
    _WORKER_SIM_CONTEXT = sim_context

    payloads = [
        (
            start_run_id + i,
            config.seed,
            config.duration,
            config.dummy_hp,
        )
        for i in range(slice_count)
    ]

    _update_simulation_progress(True, "BATCH", 0, slice_count)
    harvested: list[dict[str, Any]] = []
    try:
        for idx, p in enumerate(payloads, 1):
            harvested.append(_batch_worker_task(p))
            _update_simulation_progress(True, "BATCH", idx, slice_count)
    finally:
        _update_simulation_progress(False, "BATCH", len(harvested), slice_count)

    return {"harvested": harvested, "slice_count": slice_count}


def aggregate_batch_slices(payload: dict[str, Any]) -> dict[str, Any]:
    """Aggregates harvested slices from parallel Web Workers into the final report."""
    base_payload = payload.get("payload", {})
    all_harvested = payload.get("all_harvested", [])
    wall_ms = float(payload.get("wall_ms", 0.0))
    total_iterations = int(payload.get("total_iterations", len(all_harvested)))

    config, sim_inputs = _resolve_simulation_inputs_from_payload(base_payload)
    with redirect_stdout(io.StringIO()):
        _sim0, player0, _target0 = prepare_simulation(
            sim_inputs["rotation_config"],
            sim_inputs["stats_config"],
            sim_inputs["loadout_blueprints"],
            config.dummy_hp,
            sim_inputs["debuff_module"],
        )
        computed_stats = _extract_computed_player_stats(player0)

    all_harvested.sort(key=lambda r: r.get("run_id", 0))
    return _aggregate_batch_results(all_harvested, config, wall_ms, total_iterations, computed_stats)



def _is_rotation_builder(host: str, port: int) -> bool:
    """Returns True if the server on host:port serves the Rotation Builder page (matched by <title>; the Simulator page also mentions the builder)."""
    try:
        with urllib.request.urlopen(f"http://{host}:{port}/", timeout=1.0) as resp:
            return b"<title>SwtorSim - Rotation Builder</title>" in resp.read(65536)
    except Exception:
        return False


def ensure_rotation_builder_running(host: str = "127.0.0.1", default_port: int = 8765) -> str:
    """Ensures the Rotation Builder HTTP server is running and returns its URL."""
    global _ROTATION_BUILDER_PORT
    with _ROTATION_BUILDER_LOCK:
        if _ROTATION_BUILDER_PORT is not None:
            return f"http://{host}:{_ROTATION_BUILDER_PORT}"

        # Reuse the default port only if it really serves the Rotation Builder (e.g. started externally);
        # any other listener is skipped and the next free port is used.
        if _is_rotation_builder(host, default_port):
            _ROTATION_BUILDER_PORT = default_port
            return f"http://{host}:{default_port}"

        from data.rotation_builder import RotationBuilderRequestHandler

        for candidate in range(default_port, default_port + 20):
            # Windows' SO_REUSEADDR lets bind() succeed on an occupied port, so probe first.
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
                probe.settimeout(0.25)
                if probe.connect_ex((host, candidate)) == 0:
                    continue
            try:
                srv = ThreadingHTTPServer((host, candidate), RotationBuilderRequestHandler)
                _ROTATION_BUILDER_PORT = candidate
                t = threading.Thread(target=srv.serve_forever, daemon=True)
                t.start()
                print(f"[OK] Started Rotation Builder server at http://{host}:{candidate}")
                return f"http://{host}:{candidate}"
            except OSError:
                continue

        raise RuntimeError("Could not start Rotation Builder server on ports 8765-8784.")


class SimulatorRequestHandler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: Any) -> None:
        pass

    def _send_json(self, data: Any, status: int = 200) -> None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _read_json_body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0") or "0")
        raw = self.rfile.read(length) if length > 0 else b"{}"
        return json.loads(raw.decode("utf-8"))

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        route = parsed.path
        qs = parse_qs(parsed.query)

        try:
            if route in ("/timeline", "/timeline.html"):
                # Cast Timeline window (shared with the Rotation Builder)
                if not TIMELINE_UI_HTML_PATH.is_file():
                    self._send_json({"error": f"UI file not found at {TIMELINE_UI_HTML_PATH}"}, status=500)
                    return
                html_bytes = TIMELINE_UI_HTML_PATH.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(html_bytes)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(html_bytes)
                return

            if route in ("/", "/index.html"):
                if not SIM_UI_HTML_PATH.is_file():
                    self._send_json(
                        {"error": f"Simulator UI HTML not found at {SIM_UI_HTML_PATH}"},
                        status=500,
                    )
                    return
                html_bytes = SIM_UI_HTML_PATH.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(html_bytes)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(html_bytes)
                return

            if route.startswith("/icons/"):
                icon_name = Path(route).name
                if not icon_name.lower().endswith(".png"):
                    icon_name = f"{icon_name}.png"
                icon_file = None
                for cand_dir in (
                    SWTORSIM_ROOT / "tools" / "web" / "icons",
                    SWTORSIM_ROOT / "data" / "extractor" / "live" / "icons",
                    SWTORSIM_ROOT / "data" / "extractor" / "pts" / "icons",
                ):
                    cand_path = cand_dir / icon_name
                    if cand_path.is_file():
                        icon_file = cand_path
                        break
                    lower_path = cand_dir / icon_name.lower()
                    if lower_path.is_file():
                        icon_file = lower_path
                        break
                if icon_file is None:
                    self.send_response(404)
                    self.end_headers()
                    return
                png_bytes = icon_file.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "image/png")
                self.send_header("Content-Length", str(len(png_bytes)))
                self.send_header("Cache-Control", "public, max-age=86400")
                self.end_headers()
                self.wfile.write(png_bytes)
                return

            env = (qs.get("env") or ["live"])[0]
            if route == "/api/catalog":
                self._send_json(get_simulator_catalog(env=env))
                return

            if route == "/api/progress":
                self._send_json(get_simulation_progress())
                return

            if route == "/api/class_gear":
                spec_path = (qs.get("spec_path") or [""])[0]
                if not spec_path:
                    self._send_json({"error": "Missing spec_path parameter."}, status=400)
                    return
                self._send_json(get_class_gear_options(spec_path, env=env))
                return

            if route == "/api/run_config":
                rel_path = (qs.get("path") or [""])[0]
                if not rel_path:
                    self._send_json({"error": "Missing path parameter."}, status=400)
                    return
                self._send_json(load_run_config_bundle(rel_path, env=env))
                return

            if route == "/api/build_stats":
                rel_path = (qs.get("path") or [""])[0]
                target = _resolve_workspace_path(rel_path)
                if not target.is_file():
                    self._send_json({"error": f"Build file not found: {rel_path}"}, status=404)
                    return
                self._send_json(
                    {
                        "path": _to_workspace_rel(target),
                        "stats": load_json_file(str(target)),
                    }
                )
                return

            self._send_json({"error": f"Not found: {route}"}, status=404)
        except Exception as exc:
            self._send_json({"error": str(exc)}, status=500)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        route = parsed.path

        try:
            payload = self._read_json_body()

            if route == "/api/simulate":
                try:
                    result = execute_simulation_from_payload(payload)
                except SimulationCancelled:
                    result = {"cancelled": True}
                self._send_json(result)
                return

            if route == "/api/simulate_cancel":
                request_simulation_cancel()
                self._send_json({"ok": True})
                return

            if route == "/api/preview_stats":
                result = preview_character_stats(payload)
                self._send_json(result)
                return

            if route == "/api/run_config/save":
                filename = str(payload.get("filename") or "custom_config.json").strip()
                if not filename.endswith(".json"):
                    filename += ".json"
                filename = Path(filename).name
                rc_obj = payload.get("run_config")
                if not isinstance(rc_obj, dict):
                    self._send_json({"error": "run_config must be a JSON object."}, status=400)
                    return

                spec_path = str(rc_obj.get("spec_path") or "")
                if spec_path and (not rc_obj.get("class_name") or not rc_obj.get("spec")):
                    try:
                        g_opts = get_class_gear_options(spec_path, env=payload.get("env") or "live")
                        if not rc_obj.get("class_name") and not rc_obj.get("class"):
                            rc_obj["class"] = g_opts.get("class_name", "")
                            rc_obj["class_name"] = g_opts.get("class_name", "")
                        if not rc_obj.get("spec") and not rc_obj.get("spec_name"):
                            rc_obj["spec"] = g_opts.get("spec", "")
                            rc_obj["spec_name"] = g_opts.get("spec", "")
                    except Exception:
                        pass

                target_file = RUN_CONFIG_DIR / filename
                _write_json_crlf(target_file, rc_obj)
                rel_saved = _to_workspace_rel(target_file)
                print(f"[OK] Saved run config to {rel_saved}")
                self._send_json({"ok": True, "path": rel_saved, "filename": filename})
                return

            if route == "/api/build_stats/save":
                filename = str(payload.get("filename") or "custom_build.json").strip()
                if not filename.endswith(".json"):
                    filename += ".json"
                filename = Path(filename).name
                stats_obj = payload.get("stats")
                if not isinstance(stats_obj, dict):
                    self._send_json({"error": "stats must be a JSON object."}, status=400)
                    return
                clean_stats = {}
                for k, v in stats_obj.items():
                    if k in ("Main_hand_min", "Main_hand_max", "Off_hand_min", "Off_hand_max"):
                        continue
                    if v is None or str(v).strip() == "":
                        continue
                    try:
                        fval = float(v)
                        clean_stats[str(k)] = int(fval) if fval.is_integer() else fval
                    except (ValueError, TypeError):
                        pass

                builds_dir = _resolve_workspace_path(BUILDS_DIR)
                target_file = builds_dir / filename
                _write_json_crlf(target_file, clean_stats)
                rel_saved = _to_workspace_rel(target_file)
                print(f"[OK] Saved build stats to {rel_saved}")
                self._send_json({"ok": True, "path": rel_saved, "filename": filename})
                return

            if route == "/api/custom_file/import":
                category = str(payload.get("category") or "rotations").strip().lower()
                filename = str(payload.get("filename") or "custom.json").strip()
                if not filename.endswith(".json"):
                    filename += ".json"
                filename = Path(filename).name
                content = payload.get("content")
                class_folder = str(payload.get("class_folder") or "").strip().lower()
                spec_folder = str(payload.get("spec_folder") or "").strip().lower()

                if category == "rotations":
                    folder = SWTORSIM_ROOT / "data" / "rotations"
                    if class_folder and spec_folder:
                        folder = folder / class_folder / spec_folder
                elif category == "choices":
                    folder = SWTORSIM_ROOT / "data" / "Choices" / "custom"
                    if class_folder and spec_folder:
                        folder = folder / class_folder / spec_folder
                elif category == "builds":
                    folder = SWTORSIM_ROOT / "data" / "builds" / "custom"
                elif category == "run_config":
                    folder = SWTORSIM_ROOT / "data" / "run_config" / "custom"
                    if isinstance(content, dict):
                        if not content.get("spec_path") and (content.get("run_config") or content.get("config")):
                            content = content.get("run_config") or content.get("config")
                        spec_path = str(content.get("spec_path") or "")
                        if spec_path and (not content.get("class_name") or not content.get("spec")):
                            try:
                                g_opts = get_class_gear_options(spec_path)
                                if not content.get("class_name") and not content.get("class"):
                                    content["class"] = g_opts.get("class_name", "")
                                    content["class_name"] = g_opts.get("class_name", "")
                                if not content.get("spec") and not content.get("spec_name"):
                                    content["spec"] = g_opts.get("spec", "")
                                    content["spec_name"] = g_opts.get("spec", "")
                            except Exception:
                                pass
                else:
                    self._send_json({"error": f"Invalid category: {category}"}, status=400)
                    return

                folder.mkdir(parents=True, exist_ok=True)
                target_file = folder / filename
                _write_json_crlf(target_file, content)
                rel_saved = _to_workspace_rel(target_file)
                print(f"[OK] Imported custom {category} to {rel_saved}")
                self._send_json({"ok": True, "path": rel_saved, "filename": filename})
                return

            if route == "/api/custom_file/delete":
                rel_path = str(payload.get("path") or "").strip()
                target_file = _resolve_workspace_path(rel_path)
                try:
                    rel_to_root = target_file.resolve().relative_to(SWTORSIM_ROOT).as_posix()
                except ValueError:
                    self._send_json({"error": "Invalid file path."}, status=400)
                    return
                rotations_root = (SWTORSIM_ROOT / "data" / "rotations").resolve()
                try:
                    target_file.resolve().relative_to(rotations_root)
                    in_rotations = True
                except ValueError:
                    in_rotations = False
                if not in_rotations and "/custom/" not in f"/{rel_to_root}":
                    self._send_json({"error": "Only rotation files, or files under a custom folder, can be deleted."}, status=400)
                    return
                if target_file.is_file():
                    try:
                        target_file.unlink()
                        print(f"[OK] Deleted custom file: {rel_path}")
                        self._send_json({"ok": True, "path": rel_path})
                        return
                    except Exception as e:
                        self._send_json({"error": str(e)}, status=500)
                        return
                self._send_json({"error": f"File not found: {rel_path}"}, status=404)
                return

            if route == "/api/launch_rotation_builder":
                url = ensure_rotation_builder_running()
                sim_port = self.server.server_address[1]
                url_with_port = f"{url}?sim_port={sim_port}"
                self._send_json({"ok": True, "url": url_with_port})
                return

            self._send_json({"error": f"Unknown endpoint: {route}"}, status=404)
        except Exception as exc:
            self._send_json({"error": str(exc)}, status=500)


def launch_web_simulator(
    host: str = "127.0.0.1",
    port: int = 8787,
    open_browser: bool = True,
) -> None:
    """Starts the local SwtorSim Web GUI server."""
    os.chdir(SWTORSIM_ROOT)
    server = None
    actual_port = port
    for candidate_port in range(port, port + 20):
        try:
            server = ThreadingHTTPServer((host, candidate_port), SimulatorRequestHandler)
            actual_port = candidate_port
            break
        except OSError:
            continue

    if server is None:
        raise RuntimeError(f"[FAIL] Could not bind local HTTP server on ports {port}-{port + 19}.")

    url = f"http://{host}:{actual_port}"
    print("=========================================")
    print("   SWTOR SIM - WEB SIMULATOR DASHBOARD   ")
    print("=========================================")
    print(f"[OK] Server running at: {url}")
    print("[OK] Press Ctrl+C in the terminal to stop the server.")

    if open_browser:
        try:
            webbrowser.open(url)
        except Exception:
            pass

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[OK] Shutting down Simulator Web GUI server.")
    finally:
        server.server_close()


if __name__ == "__main__":
    launch_web_simulator()
