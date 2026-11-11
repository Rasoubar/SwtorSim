"""Records per-cast timeline rows (step, resource, buffs, cast/channel timing) for the Cast Timeline view.

Display-only instrumentation shared by the Rotation Builder dry-run (`data/rotation_builder.py`) and the
Combat Simulator single run (`web_gui._run_single_test_detailed`). It wraps `Ability.cast` on the player's
abilities and only reads engine state (scaled cast time, `ActiveChannel`, `next_gcd`); it never changes
the simulation.
"""

from __future__ import annotations

from typing import Any


def ability_name_to_slug(name: str, fqn: str = "") -> str:
    """Converts an ability display name (e.g. 'Assassinate+') into its canonical rotation slug ('assassinate+')."""
    raw = (name or "").strip()
    if not raw:
        raw = fqn.split(".")[-1] if fqn else "unknown"
    return raw.lower().replace(" ", "_")


def rotation_steps_of(rotation_config: Any) -> list[dict]:
    """Returns the step list of a rotation config (plain list, or dict with 'sequence' / 'steps')."""
    if isinstance(rotation_config, dict):
        return list(rotation_config.get("sequence") or rotation_config.get("steps") or [])
    return list(rotation_config or [])


class CastTimelineRecorder:
    """Wraps the player's abilities and records one row per successful cast.

    Row fields: time, ability, slug, triggers_gcd, resource, step_index, step_label, phase, buffs,
    activation ('instant' | 'cast' | 'channel'), gcd, busy, end_time, clipped, and for channels
    ticks / ticks_total / tick_interval. `finalize(time_origin)` adds combat_time / combat_end_time.
    """

    def __init__(self, player: Any, max_buffs: int = 6):
        self.player = player
        self.max_buffs = max_buffs
        self.rows: list[dict[str, Any]] = []
        self._pending: dict[str, Any] | None = None

    # -- activation bookkeeping -------------------------------------------------------------
    def _close_pending(self, now: float | None) -> None:
        """Finalizes the in-flight activation; now=None means it ran to its natural end."""
        info = self._pending
        self._pending = None
        if not info:
            return
        row = info["row"]
        planned_end = info["start"] + row["busy"]
        if now is not None and now < planned_end - 1e-6:
            row["end_time"] = round(now, 3)
            row["clipped"] = True
        else:
            row["end_time"] = round(planned_end, 3)
        channel = info.get("channel")
        if channel is not None:
            done = int(getattr(channel, "current_tick", 0) or 0)
            row["ticks"] = min(done, row["ticks_total"]) if row.get("clipped") else max(done, row["ticks_total"])
            interval = row.get("tick_interval") or 0.0
            # Channel cancelled by its own effects (not by a later cast): end after the last tick.
            if (
                not row.get("clipped")
                and getattr(channel, "is_finished", False)
                and done < row["ticks_total"]
                and interval > 0
            ):
                row["ticks"] = done
                row["end_time"] = round(info["start"] + done * interval, 3)
                row["clipped"] = True

    def _activation_still_running(self, caster: Any, now: float) -> bool:
        info = self._pending
        if not info:
            return False
        if info["kind"] == "channel":
            ch = info.get("channel")
            return ch is not None and caster.active_channel is ch and not getattr(ch, "is_finished", False)
        return caster.active_cast is not None and now < info["start"] + info["row"]["busy"] - 1e-6

    def _step_info(self, caster: Any) -> tuple[int, str, bool]:
        runner = getattr(caster, "pre_combat", None)
        if runner is not None and runner.active:
            return max(0, runner.index - 1), "Pre-Combat", True
        rotation = getattr(caster, "rotation", None)
        step_idx = getattr(rotation, "current_step", 0)
        seq = getattr(rotation, "sequence", None) or []
        step_obj = seq[step_idx] if 0 <= step_idx < len(seq) else None
        return step_idx, (getattr(step_obj, "name", None) or type(step_obj).__name__), False

    # -- installation -------------------------------------------------------------------------
    def install(self) -> "CastTimelineRecorder":
        """Wraps every ability in player.ability_db (wrap order: call after any other cast wrappers)."""
        for abl in set(self.player.ability_db.values()):
            abl.cast = self._make_wrapper(abl, abl.cast)
        return self

    def _make_wrapper(self, a: Any, fn: Any):
        def _wrapped(caster, tgt, s, *args, **kwargs):
            step_idx, step_label, in_pre_combat = self._step_info(caster)
            act = a.activation or getattr(a.blueprint, "activation", None) or {}
            act_type = act.get("type") if isinstance(act, dict) else None
            act_dur = float(act.get("duration", 0.0)) if isinstance(act, dict) else 0.0
            # Same call Ability.cast makes before resolving the cast (read-only).
            scaled_cast = (
                caster.calculate_cast_time(act_dur, ability=a)
                if act_type == "cast" and act_dur > 0.0 and hasattr(caster, "calculate_cast_time")
                else 0.0
            )
            was_busy = self._activation_still_running(caster, s.current_time)
            ok = fn(caster, tgt, s, *args, **kwargs)
            if ok:
                # A successful cast interrupts whatever was still casting/channeling.
                self._close_pending(s.current_time if was_busy else None)
                channel = caster.active_channel if getattr(caster.active_channel, "ability", None) is a else None
                if channel is not None:
                    kind, busy = "channel", float(channel.duration or 0.0)
                elif act_type == "cast" and scaled_cast > 0.0:
                    kind, busy = "cast", float(scaled_cast)
                else:
                    kind, busy = "instant", 0.0
                gcd = max(0.0, float(getattr(caster, "next_gcd", 0.0)) - s.current_time) if a.triggers_gcd else 0.0
                active_buffs = [
                    eff.name
                    for eff in caster.effects.values()
                    if not getattr(eff, "is_expired", False)
                    and not getattr(eff, "is_passive", False)
                    and not any("lockout" in t for t in getattr(eff, "tags", ()))
                ]
                row = {
                    "time": round(s.current_time, 2),
                    "ability": a.name,
                    "slug": ability_name_to_slug(a.name, a.fqn),
                    "triggers_gcd": a.triggers_gcd,
                    "resource": round(caster.resource.current_value, 1),
                    "step_index": step_idx + 1,
                    "step_label": step_label,
                    "phase": "pre_combat" if in_pre_combat else "rotation",
                    "buffs": active_buffs[: self.max_buffs],
                    "activation": kind,
                    "gcd": round(gcd, 3),
                    "busy": round(busy, 3),
                    "end_time": round(s.current_time + busy, 3),
                    "clipped": False,
                }
                if kind == "channel":
                    row["ticks_total"] = int(channel.total_ticks or 0)
                    row["tick_interval"] = round(float(channel.tick_interval or 0.0), 3)
                    row["ticks"] = row["ticks_total"]
                self.rows.append(row)
                if kind != "instant":
                    self._pending = {"row": row, "kind": kind, "channel": channel, "start": s.current_time}
            return ok

        return _wrapped

    # -- results ------------------------------------------------------------------------------
    def finalize(self, time_origin: float) -> list[dict[str, Any]]:
        """Closes the last activation and adds fight-relative times (0.00 = first damage)."""
        self._close_pending(None)
        for row in self.rows:
            row["combat_time"] = round(row["time"] - time_origin, 2)
            row["combat_end_time"] = round(row["end_time"] - time_origin, 3)
        return self.rows

    def ability_maps(self, rotation_steps: list[dict]) -> dict[str, dict[str, str]]:
        """icons / names keyed by slug, slugs keyed by rotation ability_id, for the timeline page."""
        db = getattr(self.player, "ability_db", {}) or {}
        by_fqn = {getattr(a, "fqn", None): a for a in db.values()}

        def lookup(aid: str):
            if not aid:
                return None
            return db.get(aid) or db.get(str(aid).lower().replace(" ", "_")) or by_fqn.get(aid)

        icons: dict[str, str] = {}
        names: dict[str, str] = {}
        slugs: dict[str, str] = {}

        def remember(aid: str, abl: Any) -> None:
            slug = ability_name_to_slug(abl.name, abl.fqn) if abl is not None else str(aid)
            slugs[aid] = slug
            name = abl.name if abl is not None else str(aid)
            names[aid] = name
            names[slug] = name
            icon = getattr(getattr(abl, "blueprint", None), "icon", None) if abl is not None else None
            if icon:
                icons[slug] = icon

        for step in rotation_steps or []:
            for p in step.get("pool") or [step]:
                aid = p.get("ability_id")
                if aid and aid not in slugs:
                    remember(aid, lookup(aid))
        for row in self.rows:
            if row["slug"] not in slugs:
                remember(row["slug"], lookup(row["slug"]))
        return {"icons": icons, "names": names, "slugs": slugs}
