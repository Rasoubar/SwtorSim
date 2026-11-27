"""Dispatcher for the debugger's actions in the browser build (called from ``pyodide_bridge.dispatch``).

Single-run actions go to one worker; the measuring actions come in pairs (a slice that runs on every worker, and an
aggregation on one), see ``debug_slices``. Kept apart from ``pyodide_bridge`` so that file only needs one branch.
"""

from __future__ import annotations

from typing import Any, Callable

from src.swtorsim.debug import debug_api, debug_slices

ACTIONS: dict[str, Callable[..., Any]] = {
    "DEBUG_CONFIGS": lambda **_: debug_api.list_configs(),
    "DEBUG_TRACE": debug_api.run_trace,
    "DEBUG_STATE": debug_api.state,
    "DEBUG_CHANGE": debug_api.change,
    "DEBUG_TRIALS": debug_slices.trials_slice,
    "DEBUG_MEASURE_AGG": debug_slices.measure_aggregate,
    "DEBUG_SWEEP_PLAN": debug_slices.sweep_plan,
    "DEBUG_FORCED": debug_slices.forced_slice,
    "DEBUG_SWEEP_AGG": debug_slices.sweep_aggregate,
    "DEBUG_DAMAGE_TRIALS": debug_slices.damage_slice,
    "DEBUG_DAMAGE_AGG": debug_slices.damage_aggregate,
}


def dispatch(action: str, data: dict | None = None) -> Any:
    """Runs one ``DEBUG_*`` action and returns its JSON-ready result; ``KeyError`` for an unknown name."""
    if action not in ACTIONS:
        raise ValueError(f"Unknown debugger action: {action}")
    return ACTIONS[action](**(data or {}))
