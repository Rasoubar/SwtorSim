"""JSON-in / JSON-out functions behind the web debugger (no HTTP here, so any transport can call them).

``run_trace`` runs one traced fight and returns the whole trace for the UI; ``measure`` replays a proc many times.
Both drive the real engine through the generated traced code (see ``traced_run``) and never edit it.

Every call names its fight either by ``config`` (a saved run config, see ``list_configs``) or by ``setup`` (the request
payload of the Combat Simulator page, so the debugger can open exactly what the simulator has on screen).
"""

from __future__ import annotations

import json
import re
import sys
import threading
from pathlib import Path
from typing import Any

from src.swtorsim.debug import inspect_state
from src.swtorsim.debug.damage_check import ParallelDamageTrials, measure_damage, reference_stats
from src.swtorsim.debug.proc_measure import (
    ParallelTrials,
    make_sim_builder,
    measure_proc,
    proc_key,
    summarize_proc_log,
    sweep_proc,
)

ROOT = Path(__file__).resolve().parents[3]


def current_code_version() -> str:
    """Fingerprint of the code a debugger process runs (every ``src/swtorsim`` module and the page: path, size, mtime).

    A debugger process reports the value it had when it started; a process that was started before the code changed
    reports an older one, which tells the simulator not to reuse it.
    """
    import hashlib

    digest = hashlib.sha1()
    files = sorted((ROOT / "src" / "swtorsim").rglob("*.py")) + [ROOT / "tools" / "debugger_ui.html"]
    for path in files:
        try:
            stat = path.stat()
        except OSError:
            continue
        digest.update(f"{path.relative_to(ROOT).as_posix()}|{stat.st_size}|{stat.st_mtime_ns}\n".encode())
    return digest.hexdigest()[:16]
RUN_CONFIG_DIR = ROOT / "data" / "run_config"

# Stable order: the trace refers to outcomes by index (smaller payload).
OUTCOMES = [
    "fired",
    "roll_failed",
    "blocked_icd",
    "blocked_condition",
    "branch_did_not_run",
    "skipped_else_gate",
    "skipped_same_activation",
]

# One traced run or measurement at a time: the traced engine is swapped in process-wide while a simulation is built.
_LOCK = threading.RLock()


def list_configs() -> dict[str, Any]:
    """Saved run configs the debugger can load (the shipped ones, and custom ones as ``custom/<name>``)."""
    names = sorted(p.stem for p in RUN_CONFIG_DIR.glob("*.json"))
    custom = RUN_CONFIG_DIR / "custom"
    if custom.is_dir():
        names += sorted(f"custom/{p.stem}" for p in custom.glob("*.json"))
    return {"configs": names}


def resolve_config(name: str) -> str:
    """Maps a config name from ``list_configs`` to its path; anything else is rejected (no path traversal)."""
    if name not in list_configs()["configs"]:
        raise ValueError(f"Unknown run config: {name!r}")
    return str(RUN_CONFIG_DIR / f"{name}.json")


ICON_DIRS = (
    ROOT / "tools" / "web" / "icons",
    ROOT / "data" / "extractor" / "live" / "icons",
    ROOT / "data" / "extractor" / "pts" / "icons",
)
# The tracer rounds the event times it reports to 4 decimals; replays anchored on them start this much earlier.
EVENT_TIME_TOLERANCE = 1e-4
_ICON_NAME = re.compile(r"^[\w\-.]+\.png$", re.IGNORECASE)


def find_icon(name: str) -> Path | None:
    """Path of an icon PNG by bare file name (no folders allowed), or None."""
    if not _ICON_NAME.match(name or ""):
        return None
    for folder in ICON_DIRS:
        for candidate in (folder / name, folder / name.lower()):
            if candidate.is_file():
                return candidate
    return None


def icon_map(blueprints) -> dict[str, str]:
    """Display name -> icon file for every ability and effect that has an icon; read-only.

    Where the icon files are on this machine, only icons that exist are listed. Where they are not (the browser build
    keeps them as static files next to the page, outside Python's file system), every plain icon name is listed and
    the page hides the ones that fail to load.
    """
    if any(folder.is_dir() for folder in ICON_DIRS):
        usable = lambda file: find_icon(file) is not None
    else:
        usable = lambda file: bool(_ICON_NAME.match(file or ""))
    icons: dict[str, str] = {}
    for bp in blueprints.values():
        own = getattr(bp, "icon", None)
        name = getattr(bp, "name", None)
        if name and own and str(name) not in icons and usable(own):
            icons[str(name)] = own
        effects = getattr(bp, "effects", None) or {}
        for eff in (effects.values() if isinstance(effects, dict) else effects):
            effect_name = getattr(eff, "name", None)
            effect_icon = getattr(eff, "icon", None) or own
            if effect_name and effect_icon and str(effect_name) not in icons and usable(effect_icon):
                icons[str(effect_name)] = effect_icon
    return icons


def _stat_label(raw) -> str:
    """Readable stat name from the repo's own stat table (numeric ids only; names pass through)."""
    src = str(ROOT / "src")
    if src not in sys.path:
        sys.path.append(src)  # the extractor modules import each other as top-level names; appended so nothing is shadowed
    try:
        from extractor.mod_stats import decode_stat_name
        return decode_stat_name(raw)
    except Exception:
        return str(raw)


def _round(value, digits=4):
    return None if value is None else round(float(value), digits)


# --- which fight: a saved config or the simulator's setup -------------------------------------------------------------

def fight_source(config: str | None, setup: dict | None):
    """Returns ``(what make_sim_builder takes, label, "config" | "setup")`` for a request."""
    if setup:
        label = " ".join(str(setup.get(k) or "") for k in ("class", "spec")).strip() or "Simulator setup"
        return dict(setup), label, "setup"
    if not config:
        raise ValueError("Name a run config or give the simulator setup.")
    return resolve_config(config), config, "config"


def _stamp(path: Any) -> int | None:
    """Modification time of a file the fight is built from (so an edited file is not served from the cache)."""
    try:
        candidate = Path(str(path))
        return (candidate if candidate.is_absolute() else ROOT / candidate).stat().st_mtime_ns
    except (OSError, ValueError):
        return None


# The last built fight is kept: trace, state, change and measuring all work on the same one, and loading it (blueprints,
# stats) is most of the cost of a call. Only one is kept because resolving a fight also sets engine-wide settings (stem
# matching, data environment, ...) that the next fight would overwrite.
_BUILDER_CACHE: dict[str, tuple] = {}


def get_builder(source, environment: str = "live", seed: int | None = None, with_tracer: bool = False,
                dummy_hp: int | None = None, duration: float | None = None):
    """``make_sim_builder`` with the last result reused; returns ``(build_sim, seed, duration)``."""
    if isinstance(source, dict):
        files = [_stamp(source.get(k)) for k in ("spec_path", "stats_path", "rotation_path") if source.get(k)]
    else:
        files = [_stamp(source)]
    key = json.dumps([source, environment, seed, with_tracer, dummy_hp, duration, files], sort_keys=True, default=str)
    cached = _BUILDER_CACHE.get(key)
    if cached is None:
        _BUILDER_CACHE.clear()
        cached = _BUILDER_CACHE[key] = make_sim_builder(
            source, environment, seed, with_tracer=with_tracer, dummy_hp=dummy_hp, duration=duration
        )
    return cached


def compress_proc_log(proc_log: list[dict], time_offset: float) -> dict[str, Any]:
    """Columnar form of ``proc_log``: one row per trigger rule plus one compact row per evaluation.

    Each evaluation row is ``[t, raw_t, rule_id, outcome_index, base_chance, chance, draw, remaining, interval]``
    with ``t`` relative to the first damage (pre-combat negative) and ``raw_t`` on the simulation clock, unrounded (what
    ``measure`` takes as its anchor). The last two entries are the id of the event being processed when the rule was
    evaluated and, for a rule that fired, the id of the proc's own event (``None`` otherwise).
    """
    summary = {tuple(row["key"]): row for row in summarize_proc_log(proc_log)}
    rule_ids: dict[tuple, int] = {}
    rules: list[dict] = []
    evals: list[list] = []
    for rec in proc_log:
        key = proc_key(rec)
        rule_id = rule_ids.get(key)
        if rule_id is None:
            rule_id = rule_ids[key] = len(rules)
            row = summary[key]
            rules.append({
                "id": rule_id,
                "key": list(key),
                "source": rec.get("source"),
                "kind": rec.get("kind"),
                "event": rec.get("event"),
                "outcomes": row["outcomes"],
                "mean_chance": _round(row["mean_chance"], 3),
                "first_roll_raw": row["first_roll"],
            })
        outcome = rec["outcome"]
        evals.append([
            _round(rec["t"] - time_offset), rec["t"], rule_id, OUTCOMES.index(outcome),
            _round(rec.get("base_chance"), 3), _round(rec.get("chance"), 3), _round(rec.get("draw"), 3),
            _round(rec.get("remaining")), _round(rec.get("interval")),
            rec.get("cause"), rec.get("node"),
        ])
    return {"outcomes": OUTCOMES, "rules": rules, "evals": evals, "time_offset": _round(time_offset)}


def run_trace(*, config: str | None = None, setup: dict | None = None, environment: str = "live",
              seed: int | None = None, duration: float | None = None, dummy_hp: int | None = None) -> dict[str, Any]:
    """Runs one traced fight and returns what the UI draws: summary, events, buff windows, hit math, procs."""
    source, label, kind = fight_source(config, setup)
    with _LOCK:
        build_sim, run_seed, run_duration = get_builder(
            source, environment, seed, with_tracer=True, dummy_hp=dummy_hp, duration=duration
        )
        sim = build_sim()
        target = sim.incoming_attack_attacker
        import contextlib
        import io

        with contextlib.redirect_stdout(io.StringIO()):
            sim.run_timed(duration=run_duration, target=target)
        tracer = sim.tracer
        trace = tracer.to_dict()
        offset = tracer.time_offset
        proc = compress_proc_log(sim.triggers.proc_log, offset)
        icons = icon_map(build_sim.inputs.loadout_blueprints)
        fight_environment = getattr(build_sim.config, "environment", None) or environment

    keep = ("damage_hit", "cast_start", "stall", "tactical_swap", "miss", "proc_fire", "rotation_eval")
    initial = trace["initial_state"]
    # Exact simulation-clock time of each event (the trace's own times are relative to the first damage); the
    # state / damage-check replays take their anchors on the simulation clock.
    raw_times = [e["t"] for e in tracer.events]
    events = [dict(e, raw=raw) for e, raw in zip(trace["events"], raw_times) if e.get("type") in keep]
    for event in events:
        for hit_source in (event.get("math") or {}).get("sources", []):
            hit_source["label"] = _stat_label(hit_source["stat"])
    return {
        "config": {"name": label, "environment": fight_environment, "seed": run_seed, "duration": run_duration,
                   "source": kind},
        "summary": trace["summary"],
        "character": initial.get("character"),
        "derived": initial.get("derived"),
        "gear": {"tactical": initial.get("tactical"), "legendaries": initial.get("legendaries") or [],
                 "relics": initial.get("relics") or []},
        "events": events,
        "rotation": trace["rotation_decisions"],
        "icons": icons,
        "buff_windows": trace["active_buff_windows"],
        "proc": proc,
    }


def measure_result_dict(result) -> dict[str, Any]:
    """The JSON form of a ``ProcMeasurement`` (shared by the API and the browser's worker-pool path)."""
    low, high = result.interval
    return {
        "source": result.source,
        "anchor": result.anchor,
        "window": result.window,
        "trials": result.trials,
        "rolls": result.rolls,
        "roll_passes": result.roll_passes,
        "fires": result.fires,
        "observed": result.observed,
        "expected": result.expected,
        "interval": [low, high],
        "z_score": result.z_score,
        "verdict": result.verdict,
        "stopped_because": result.stopped_because,
        "seconds": result.seconds,
        "rolls_per_trial": (result.rolls / result.trials) if result.trials else 0.0,
        "fires_per_trial": (result.fires / result.trials) if result.trials else 0.0,
    }


def sweep_result_dict(result, step: float) -> dict[str, Any]:
    """The JSON form of a ``SweepResult``."""
    return {
        "source": result.source,
        "anchor": result.anchor,
        "chance": result.chance,
        "step": step,
        "tested": len(result.values),
        "passed": result.observed_count,
        "expected": result.expected_count,
        "boundary_at_chance_passes": result.boundary_at_chance_passes,
        "boundary_above_chance_fails": result.boundary_above_chance_fails,
        "problems": result.problems,
        "verdict": result.verdict,
        "seconds": result.seconds,
    }


def measure(*, key: list, anchor: float, config: str | None = None, setup: dict | None = None,
            environment: str = "live", seed: int | None = None, window: float = 0.0, trials: int = 500,
            workers: int = 1, dummy_hp: int | None = None, duration: float | None = None,
            source: str = "") -> dict[str, Any]:
    """Replays the fight to ``anchor`` (raw sim time) and measures the proc rule ``key``; see ``proc_measure``."""
    what, _label, _kind = fight_source(config, setup)
    key_t = tuple(key)
    trials = max(1, min(int(trials), 5000))
    workers = max(1, min(int(workers), 16))
    window = max(0.0, float(window))
    anchor = float(anchor) - window
    with _LOCK:
        if workers > 1:
            with ParallelTrials(what, environment, seed, key_t, anchor, window, workers) as pool:
                result = measure_proc(None, key_t, anchor, window=window, max_trials=trials, source=source,
                                      run_batch=pool.run_batch, batch_size=pool.batch_size)
        else:
            build_sim, _seed, _duration = get_builder(what, environment, seed, dummy_hp=dummy_hp, duration=duration)
            result = measure_proc(build_sim, key_t, anchor, window=window, max_trials=trials, source=source)
    return measure_result_dict(result)


def sweep(*, key: list, anchor: float, config: str | None = None, setup: dict | None = None,
          environment: str = "live", seed: int | None = None, step: float = 1.0, workers: int = 1,
          dummy_hp: int | None = None, duration: float | None = None, source: str = "") -> dict[str, Any]:
    """Exact check of one roll: forces every draw 1..100 at ``anchor`` (raw sim time); see ``sweep_proc``."""
    what, _label, _kind = fight_source(config, setup)
    key_t = tuple(key)
    step = min(10.0, max(0.1, float(step)))
    workers = max(1, min(int(workers), 16))
    with _LOCK:
        if workers > 1:
            with ParallelTrials(what, environment, seed, key_t, float(anchor), 0.0, workers) as pool:
                result = sweep_proc(None, key_t, float(anchor), step, source, run_forced=pool.run_forced)
        else:
            build_sim, _seed, _duration = get_builder(what, environment, seed, dummy_hp=dummy_hp, duration=duration)
            result = sweep_proc(build_sim, key_t, float(anchor), step, source)
    return sweep_result_dict(result, step)


def state(*, at: float, config: str | None = None, setup: dict | None = None, environment: str = "live",
          seed: int | None = None, dummy_hp: int | None = None, duration: float | None = None) -> dict[str, Any]:
    """Replays the fight to just before ``at`` (raw sim time) and reads the state there; see ``inspect_state``."""
    what, _label, _kind = fight_source(config, setup)
    with _LOCK:
        build_sim, _seed, _duration = get_builder(what, environment, seed, dummy_hp=dummy_hp, duration=duration)
        sim = build_sim()
        sim.run_until(float(at) - EVENT_TIME_TOLERANCE)
        return inspect_state.snapshot(sim, float(at))


def change(*, at: float, config: str | None = None, setup: dict | None = None, window: float = 0.0,
           environment: str = "live", seed: int | None = None, dummy_hp: int | None = None,
           duration: float | None = None) -> dict[str, Any]:
    """What changed from just before ``at`` (raw sim time) to the end of ``at + window``; see ``diff_snapshots``.

    One replay: the state is read just before the moment and again once ``window`` seconds of events have run.
    """
    what, _label, _kind = fight_source(config, setup)
    at, window = float(at), max(0.0, float(window))
    with _LOCK:
        build_sim, _seed, _duration = get_builder(what, environment, seed, dummy_hp=dummy_hp, duration=duration)
        sim = build_sim()
        sim.run_until(at - EVENT_TIME_TOLERANCE)
        before = inspect_state.snapshot(sim, at)
        sim.run_until(at + window + EVENT_TIME_TOLERANCE)
        after = inspect_state.snapshot(sim, at + window)
    return {"at": at, "window": window, "diff": inspect_state.diff_snapshots(before, after, elapsed=window)}


def damage(*, ability: str, anchor: float, config: str | None = None, setup: dict | None = None,
           environment: str = "live", seed: int | None = None, window: float = 0.0, trials: int = 300,
           workers: int = 1, dummy_hp: int | None = None, duration: float | None = None) -> dict[str, Any]:
    """Replays one ability's hit many times (``anchor`` = the hit's raw sim time); see ``damage_check``."""
    what, _label, _kind = fight_source(config, setup)
    trials = max(1, min(int(trials), 3000))
    workers = max(1, min(int(workers), 16))
    window = max(0.0, float(window))
    start = float(anchor) - window
    with _LOCK:
        build_sim, _seed, _duration = get_builder(
            what, environment, seed, with_tracer=True, dummy_hp=dummy_hp, duration=duration
        )
        reference = reference_stats(build_sim, start)
        if workers > 1:
            with ParallelDamageTrials(what, environment, seed, ability, start, window, workers) as pool:
                result = measure_damage(None, ability, start, window, trials, run_batch=pool.run_batch,
                                        batch_size=pool.batch_size, reference=reference)
        else:
            result = measure_damage(build_sim, ability, start, window, trials, reference=reference)
    return result.to_dict()


ACTIONS = {
    "configs": lambda payload: list_configs(),
    "trace": lambda payload: run_trace(**payload),
    "measure": lambda payload: measure(**payload),
    "sweep": lambda payload: sweep(**payload),
    "state": lambda payload: state(**payload),
    "change": lambda payload: change(**payload),
    "damage": lambda payload: damage(**payload),
}


def handle(action: str, payload: dict | None = None) -> dict[str, Any]:
    """Transport-neutral entry point: ``handle("trace", {...})``. Raises ``KeyError`` for an unknown action."""
    return ACTIONS[action](payload or {})
