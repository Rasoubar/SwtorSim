"""Records which event caused which, for the debugger's cause links. The engine files stay untouched.

Inside a debug run (see ``traced_run.traced_engine``) two things are wrapped, and restored afterwards:
  * ``Ability.cast``: while an ability is being cast, the tracer keeps a "cast" frame; its ``cast_start`` event is the
    cause of everything the cast does (resource spent, effects applied, hits, procs).
  * ``HitGroup.park`` (with ``DamageHit.resolve``): a branch that issues several hits holds their on_damage_dealt
    dispatches until it ends; the tracer remembers which hit each held dispatch belongs to.
  * ``Simulation.schedule_relative`` / ``schedule_absolute``: an event scheduled while a cause is active resolves later
    under that same cause (a delayed hit, a DoT tick, a cast finishing). Events that start their own chain (the next
    rotation decision, resource regeneration, pre-combat steps) are left alone.

The wrappers only keep the tracer's frame stack; they do not change what the engine does or how many random draws it
makes. Procs are handled by the generated copy of the trigger manager (``begin_cause`` / ``end_cause`` around the
branch it runs).
"""

from contextlib import contextmanager

# Events that begin their own chain instead of inheriting the cause that scheduled them.
_OWN_CHAIN = frozenset({"PlayerReady", "PreCombatEvent", "ResourceTick", "IncomingAttack", "PeriodicProcTick"})


def _inherit_cause(event, cause_id, tracer):
    """Makes ``event`` resolve under the cause that scheduled it."""
    real = type(event).resolve.__get__(event, type(event))

    def resolve(sim, _real=real, _cause=cause_id, _tracer=tracer):
        frame = _tracer.begin_cause(inherited_id=_cause)
        try:
            return _real(sim)
        finally:
            _tracer.end_cause(frame)

    event.resolve = resolve


def _wrap_schedule(original):
    def schedule(self, when, event):
        tracer = getattr(self, "tracer", None)
        if tracer is not None and type(event).__name__ not in _OWN_CHAIN:
            cause_id = tracer.current_cause_id()
            if cause_id is not None:
                _inherit_cause(event, cause_id, tracer)
        return original(self, when, event)

    return schedule


_resolving_tracer = None  # the tracer of the hit being resolved (HitGroup.park has no simulation to ask)


def _wrap_hit_resolve(original):
    def resolve(self, sim):
        global _resolving_tracer
        tracer = getattr(sim, "tracer", None)
        if tracer is None:
            return original(self, sim)
        previous, _resolving_tracer = _resolving_tracer, tracer
        try:
            return original(self, sim)
        finally:
            _resolving_tracer = previous

    return resolve


def _wrap_park(original):
    def park(self, context):
        # The branch is still running: this hit's on_damage_dealt dispatch waits until it ends (HitGroup). Remember which
        # hit it belongs to, so the procs it fires are linked to it and not to the hit recorded last.
        if _resolving_tracer is not None:
            _resolving_tracer.note_parked_hit(context)
        return original(self, context)

    return park


def _wrap_cast(original):
    def cast(self, caster, target, sim, allow_clip=False):
        tracer = getattr(sim, "tracer", None)
        if tracer is None:
            return original(self, caster, target, sim, allow_clip=allow_clip)
        frame = tracer.begin_cause()
        try:
            return original(self, caster, target, sim, allow_clip=allow_clip)
        finally:
            tracer.end_cause(frame)

    return cast


@contextmanager
def track_causes():
    """Wraps ``Ability.cast`` and the simulation's scheduling for the length of the block."""
    import src.swtorsim.abilities as abilities
    import src.swtorsim.engine as engine

    import src.swtorsim.events as events

    simulation = engine.Simulation
    original_hit_resolve = events.DamageHit.resolve
    original_park = events.HitGroup.park
    events.DamageHit.resolve = _wrap_hit_resolve(original_hit_resolve)
    events.HitGroup.park = _wrap_park(original_park)
    original_cast = abilities.Ability.cast
    original_relative = simulation.schedule_relative
    original_absolute = simulation.schedule_absolute
    abilities.Ability.cast = _wrap_cast(original_cast)
    simulation.schedule_relative = _wrap_schedule(original_relative)
    simulation.schedule_absolute = _wrap_schedule(original_absolute)
    try:
        yield
    finally:
        events.DamageHit.resolve = original_hit_resolve
        events.HitGroup.park = original_park
        abilities.Ability.cast = original_cast
        simulation.schedule_relative = original_relative
        simulation.schedule_absolute = original_absolute
