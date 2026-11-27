"""Runs the real simulation with the generated traced engine code swapped in; the engine files stay untouched.

The swap lasts only for the ``with`` block, so normal runs never see it:
  * ``engine.TriggerManager`` is rebound to the generated traced class (bus procs);
  * ``Branch.execute`` and ``Effect.execute_triggered_branches`` get the generated patched functions
    (lifecycle procs: on_apply, on_refresh, on_tick, on_stack_charge_*);
  * ``Ability.cast`` and the simulation's scheduling are wrapped to keep the tracer's cause links (``causes.py``);
  * ``events.calculate_hit`` is rebound to a copy whose hit functions also record who contributed to the multiplier
    and the crit (``combat_math_traced.py``; the formulas themselves are unchanged and parity-tested).
"""

from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path

from src.swtorsim.debug.causes import track_causes

_GENERATED = Path(__file__).resolve().parent / "generated" / "abilities_traced.py"
_GENERATED_COMBAT_MATH = Path(__file__).resolve().parent / "generated" / "combat_math_traced.py"


@lru_cache(maxsize=1)
def _load_traced_abilities_functions():
    """Compiles abilities_traced.py with the globals of the real abilities module (a snapshot copy)."""
    import src.swtorsim.abilities as abilities

    namespace = dict(abilities.__dict__)
    source = _GENERATED.read_text(encoding="utf-8")
    exec(compile(source, str(_GENERATED), "exec"), namespace)
    return namespace["branch_execute"], namespace["effect_execute_triggered_branches"]


@lru_cache(maxsize=1)
def _load_traced_calculate_hit():
    """Compiles combat_math_traced.py with a copy of the real combat_math globals; returns its calculate_hit."""
    import src.swtorsim.combat_math as combat_math

    namespace = dict(combat_math.__dict__)
    source = _GENERATED_COMBAT_MATH.read_text(encoding="utf-8")
    exec(compile(source, str(_GENERATED_COMBAT_MATH), "exec"), namespace)
    return namespace["calculate_hit"]


@contextmanager
def traced_engine():
    """Makes every ``Simulation`` built inside the block use the traced engine pieces.

    Yields the traced ``TriggerManager`` class; each simulation's evaluations (bus and lifecycle) are on
    ``sim.triggers.proc_log``.
    """
    import src.swtorsim.abilities as abilities
    import src.swtorsim.engine as engine
    import src.swtorsim.events as events
    from src.swtorsim.debug.generated.triggers_traced import TriggerManager as TracedTriggerManager

    branch_execute, effect_execute_triggered_branches = _load_traced_abilities_functions()
    original_manager = engine.TriggerManager
    original_branch_execute = abilities.Branch.execute
    original_triggered = abilities.Effect.execute_triggered_branches
    original_calculate_hit = events.calculate_hit
    traced_calculate_hit = _load_traced_calculate_hit()

    engine.TriggerManager = TracedTriggerManager
    abilities.Branch.execute = branch_execute
    abilities.Effect.execute_triggered_branches = effect_execute_triggered_branches
    events.calculate_hit = traced_calculate_hit
    try:
        with track_causes():
            yield TracedTriggerManager
    finally:
        engine.TriggerManager = original_manager
        abilities.Branch.execute = original_branch_execute
        abilities.Effect.execute_triggered_branches = original_triggered
        events.calculate_hit = original_calculate_hit
