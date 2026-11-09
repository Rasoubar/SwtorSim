"""Discrete simulation event classes resolved by the priority queue."""

from typing import TYPE_CHECKING #yellow warnings annoy me

from src.swtorsim.combat_math import calculate_hit


if TYPE_CHECKING:
    from src.swtorsim.entities import Player, Dummy, Entity
    from src.swtorsim.effects import ActiveDot, ActiveEffect


class Event:
    """Purpose is mostly for tiebreaking in case of similar occurrence time."""
    def __init__(self, name="EventName"):
        self.name = name


    def __lt__(self,other):
        """Tiebreaker for 2 events at the same time"""
        return False

class AbilityCast(Event):
    """Represents a queued ability cast event resolved on the simulation timeline."""
    def __init__(self,source,target,ability):
        super().__init__(f"Ability Cast {ability.name}")
        self.source = source
        self.target = target
        self.ability = ability

    def resolve(self, sim):
        from src.swtorsim.abilities import Ability
        Ability.cast(self.ability, self.source, self.target,sim)

class ApplyDamageLand(Event):
    """Applies pre-calculated damage to the target. Needed because of impact_delay, when damage is calculated earlier
    than it is applied."""
    def __init__(self, source, target, final_damage, is_crit, ability_name, attack_type=None, damage_type=None, math_audit=None):
        super().__init__()
        self.source = source
        self.target = target
        self.final_damage = final_damage
        self.is_crit = is_crit
        self.ability_name = ability_name
        self.attack_type = attack_type
        self.damage_type = damage_type
        self.math_audit = math_audit

    def resolve(self, sim):
        """Applies pre-calculated damage to the target, logs it into metrics."""
        crit_string = " (CRITICAL!)" if self.is_crit else ""
        try:
            sim.tracker.log_damage(
                self.ability_name,
                self.final_damage,
                self.is_crit,
                self.target,
                sim.current_time,
                attack_type=self.attack_type,
                damage_type=self.damage_type,
            )
        except TypeError:
            sim.tracker.log_damage(
                self.ability_name,
                self.final_damage,
                self.is_crit,
                self.target,
                sim.current_time,
            )
        self.target.hp -= self.final_damage
        if self.target.hp <= 0 and not getattr(self.target, "is_dead", False):
            self.target.is_dead = True
            if sim is not None and hasattr(sim, "triggers"):
                death_ctx = {
                    "caster": self.source,
                    "target": self.target,
                    "enemy_target": self.target,
                    "tags": getattr(self, "tags", ()),
                }
                sim.triggers.dispatch("on_pre_death", sim, death_ctx)
                sim.triggers.dispatch("on_death", sim, death_ctx)
                sim.triggers.dispatch("on_kill", sim, death_ctx)
        if getattr(sim, "verbose", True):
            print(f"[{sim.current_time:.2f}s] {self.ability_name} deals {self.final_damage}{crit_string} damage to {self.target.name} (HP: {self.target.hp})")
        if getattr(sim, "tracer", None) is not None:
            from src.swtorsim.metrics import ATTACK_TYPE_NAMES, DAMAGE_TYPE_NAMES
            at_name = ATTACK_TYPE_NAMES.get(self.attack_type, str(self.attack_type)) if self.attack_type else ""
            dt_name = DAMAGE_TYPE_NAMES.get(self.damage_type, str(self.damage_type)) if self.damage_type else ""
            sim.tracer.record_damage_hit(
                timestamp=sim.current_time,
                ability_name=self.ability_name,
                damage=self.final_damage,
                is_crit=self.is_crit,
                target_name=self.target.name,
                target_hp_after=self.target.hp,
                attack_type=at_name,
                damage_type=dt_name,
                math_audit=getattr(self, "math_audit", None),
            )

class DamageHit(Event):
    """ Represents a hit execution. Holds the data needed to calculate damage, and trigger procs."""
    def __init__(self, source: "Player", target: "Dummy", action_data: dict, ability_name: str, tags=None, from_proc: bool = False, ability_fqn: str = None):
        super().__init__(f"{ability_name} Hit")
        self.source = source
        self.target = target
        self.action_data = action_data
        self.ability_name = ability_name
        self.tags = frozenset(tags if tags is not None else action_data.get("tags", []))
        self.from_proc = from_proc
        self.ability_fqn = ability_fqn
        self.is_crit = False

    def resolve(self, sim):
        """Calls damage calculation, determines when to apply damage, calls for damage to land,
        calls for proc evaluation."""
        action_with_ctx = dict(self.action_data)
        action_with_ctx["tags"] = self.tags
        action_with_ctx["ability_fqn"] = self.ability_fqn
        action_with_ctx["ability_name"] = self.ability_name
        if getattr(sim, "tracer", None) is not None:
            action_with_ctx["record_audit"] = True

        final_damage, is_crit = calculate_hit(self.source, self.target, action_with_ctx)
        self.is_crit = is_crit
        resolved_at = action_with_ctx.get("resolved_attack_type", self.action_data.get("attack_type", 1))
        resolved_dt = action_with_ctx.get("resolved_damage_type", self.action_data.get("damage_type", 1))

        attack_type = self.action_data.get("attack_type", 1)
        spell_type = self.action_data.get("spell_type")
        if spell_type is None:
            if attack_type == 4:
                spell_type = 2  # Tech
            elif attack_type == 3:
                spell_type = 3  # Force
            else:
                spell_type = 1  # Weapon (Melee/Ranged)
        tags_set = set(self.tags or [])
        is_periodic = bool(
            self.action_data.get("is_periodic")
            or any(
                t.endswith(".periodic_damage") or t == "tag.abl.debuff.damage_over_time"
                for t in tags_set
            )
        )
        is_weapon_attack = attack_type in (1, 2) and not is_periodic
        if is_weapon_attack:
            weapon_mode = 3 if attack_type == 2 else 2  # 3 = Ranged, 2 = Melee
        else:
            weapon_mode = 0  # Non-weapon / periodic DoT
        ctx = {
            "caster": self.source,
            "target": self.target,
            "enemy_target": self.target,
            "tags": self.tags,
            "is_crit": is_crit,
            "damage_type": self.action_data.get("damage_type", 1),
            "attack_type": attack_type,
            "spell_type": spell_type,
            "is_weapon_attack": is_weapon_attack,
            "is_periodic": is_periodic,
            "weapon_mode": weapon_mode,
            "final_damage": final_damage,
        }

        if sim is not None and hasattr(sim, "triggers"):
            sim.triggers.dispatch("on_pre_damage_dealt", sim, ctx)
            sim.triggers.dispatch("on_pre_damage_taken", sim, ctx)

        instant_land = ApplyDamageLand(
            self.source,
            self.target,
            final_damage,
            is_crit,
            self.ability_name,
            attack_type=resolved_at,
            damage_type=resolved_dt,
            math_audit=action_with_ctx.get("_audit"),
        )
        instant_land.resolve(sim)

        if not is_periodic and hasattr(self.source, "break_stealth"):
            self.source.break_stealth(sim)

        if sim is not None and hasattr(sim, "triggers"):
            sim.triggers.dispatch("on_damage_dealt", sim, ctx)
            sim.triggers.dispatch("on_damage_taken", sim, ctx)

class PeriodicProcTick(Event):
    """Represents tics that are pre-scheduled and always happening."""
    def __init__(self, player, target, proc):
        super().__init__(f"{proc.name} Tick")
        self.player = player
        self.target = target
        self.proc = proc

    def resolve(self, sim):
        """Executes tic and schedules next one, all according to tic's action data"""
        from src.swtorsim.abilities import execute_single_action
        for action in getattr(self.proc, 'actions', []):
            if getattr(sim, "verbose", True):
                print(f'[{sim.current_time}] Temporary Proc test')
            execute_single_action(sim, self.player, self.target, action, self.proc.name)
        is_affected = getattr(self.proc, 'affected_by_cdr', False)
        interval = self.player.scale_time_modifier(self.proc.icd) if is_affected else self.proc.icd
        sim.schedule_relative(interval, PeriodicProcTick(self.player, self.target, self.proc))

class PlayerReady(Event):
    """Represents a player's actions/decisions to act"""
    def __init__(self, player: "Player", target: "Dummy"):
        super().__init__("Player Ready")
        self.player = player
        self.target = target

    def _get_step_diagnostic(self) -> str:
        """Extracts human-readable identifier of the rotation step currently being evaluated."""
        rot = getattr(self.player, "rotation", None)
        if rot is None:
            return "No rotation"
        seq = getattr(rot, "sequence", [])
        curr = getattr(rot, "current_step", 0)
        if curr >= len(seq):
            return f"End of sequence ({curr}/{len(seq)})"
        step = seq[curr]
        step_cls = step.__class__.__name__
        if hasattr(step, "ability_id"):
            abl = getattr(self.player, "ability_db", {}).get(step.ability_id)
            abl_name = getattr(abl, "name", step.ability_id)
            return f"{step_cls}:{abl_name}"
        if hasattr(step, "name"):
            return f"{step_cls}:{step.name}"
        return f"{step_cls}"

    def resolve(self, sim):
        """Evaluates the rotation. If successful, evaluate again on next possible gcd (can be same one). If not,
         tries again 0.1seconds later."""
        if getattr(self.player, "rotation", None) is None:
            return
        acted = self.player.rotation.evaluate(self.player, self.target, sim)
        if acted:
            if getattr(self.player, "_is_stalled", False):
                if hasattr(sim, "tracker"):
                    sim.tracker.log_rotation_stall_end(sim.current_time)
                self.player._is_stalled = False

            target_time = (
                self.player.get_next_action_time(sim.current_time)
                if hasattr(self.player, "get_next_action_time")
                else max(sim.current_time, self.player.next_gcd)
            )
            sim.schedule_absolute(target_time, PlayerReady(self.player, self.target))
        else:
            if sim.current_time < self.player.next_gcd:
                target_time = max(sim.current_time, self.player.next_gcd)
                sim.schedule_absolute(target_time, PlayerReady(self.player, self.target))
            else:
                is_busy_action = (
                    getattr(self.player, "active_channel", None) is not None
                    or getattr(self.player, "active_cast", None) is not None
                )
                if not is_busy_action and not getattr(self.player, "_is_stalled", False):
                    self.player._is_stalled = True
                    if hasattr(sim, "tracker"):
                        resource_val = getattr(getattr(self.player, "resource", None), "current", None)
                        sim.tracker.log_rotation_stall_start(
                            timestamp=sim.current_time,
                            seed=getattr(sim, "seed", None),
                            step_index=getattr(self.player.rotation, "current_step", 0),
                            step_info=self._get_step_diagnostic(),
                            resource_current=resource_val,
                        )
                sim.schedule_relative(0.1, PlayerReady(self.player, self.target))

class EffectExpire(Event):
    """Handles the expiration of player buffs."""
    def __init__(self, entity: "Entity", effect_name: str, instance_ref: "ActiveEffect"):
        super().__init__(f"{effect_name} Expired")
        self.entity = entity
        self.effect_name = effect_name
        self.instance_ref = instance_ref

    def resolve(self, sim):
        """Removes the buff if it's instance is the one for the scheduled event (wasn't refreshed/removed already)."""
        active_buff = self.entity.effects.get(self.effect_name)

        if active_buff is not self.instance_ref:
            return

        if getattr(self.instance_ref, "expires_at", None) is not None:
            if sim.current_time < self.instance_ref.expires_at - 1e-6:
                return

        blueprint = getattr(self.instance_ref, "effect_blueprint", None)
        ability = getattr(self.instance_ref, "ability_ref", None)
        caster = getattr(self.instance_ref, "caster_ref", self.entity)
        if blueprint and hasattr(blueprint, "execute_triggered_branches"):
            expire_ctx = {
                "stack_multiplier": getattr(self.instance_ref, "stacks", 1),
                "current_stacks": getattr(self.instance_ref, "stacks", 1),
                "active_effect": self.instance_ref,
                "owner_entity": self.entity,
            }
            blueprint.execute_triggered_branches(
                "on_pre_remove",
                sim,
                caster,
                self.entity,
                context=expire_ctx,
                ability=ability,
            )

        self.entity.cleanup_expired_effects([self.effect_name])

        if getattr(sim, "verbose", True):
            print(f"[{sim.current_time:.2f}s] Buff expired and cleared: {self.effect_name}")

class DotTick(Event):
    """Represents a Dot Tick. Handles action execution, tick's value decrease and following tick scheduling."""
    def __init__(self, source: "Player", target: "Dummy", instance_ref, effect_key: str = None):
        super().__init__(f"DoT Tick: {instance_ref.name}")
        self.source = source
        self.target = target
        self.instance_ref = instance_ref
        self.effect_key = effect_key or instance_ref.name

    def resolve(self, sim):
        """If it's instance's DoT has not been overlapped:
        Executes the tick according to DoT data, decreases ticks remaining and schedules next one if still ticks
        remaining. If not, deletes dot from target. """

        dot_name = self.effect_key
        effect_blueprint = getattr(self.instance_ref, "effect_blueprint", None)

        if effect_blueprint is not None:
            if self.target.effects.get(dot_name) is not self.instance_ref:
                return
            if getattr(self.instance_ref, "is_expired", False):
                return

            total_ticks = getattr(self.instance_ref, "total_ticks", 0)
            current_tick = (total_ticks - self.instance_ref.ticks_remaining + 1) if total_ticks > 0 else 1
            eff_tags = set(getattr(self.instance_ref, "tags", frozenset()))
            stack_mult = (
                self.instance_ref.stacks
                if getattr(self.instance_ref, "scales_with_stacks", False)
                else 1
            )
            context = {
                "is_periodic": True,
                "effect_tags": frozenset(eff_tags),
                "stack_multiplier": stack_mult,
                "owner_effect_key": dot_name,
                "owner_entity": self.target,
            }
            effect_blueprint.execute_triggered_branches(
                "on_tick",
                sim,
                self.source,
                self.target,
                ability=getattr(self.instance_ref, "ability_ref", None),
                include_untriggered=False,
                tick_number=current_tick,
                context=context,
            )
            self.instance_ref.ticks_remaining -= 1
            if self.instance_ref.ticks_remaining > 0 and self.instance_ref.tick_interval:
                next_tick_time = sim.current_time + self.instance_ref.tick_interval
                sim.schedule_absolute(next_tick_time, self)
            elif (
                getattr(self.instance_ref, "expires_at", None) is not None
                and sim.current_time < self.instance_ref.expires_at - 1e-6
                and self.instance_ref.tick_interval
                and self.instance_ref.tick_interval > 0
            ):
                rem_time = self.instance_ref.expires_at - sim.current_time
                self.instance_ref.ticks_remaining = max(1, int(round(rem_time / self.instance_ref.tick_interval)))
                next_tick_time = sim.current_time + self.instance_ref.tick_interval
                sim.schedule_absolute(next_tick_time, self)
            else:
                if effect_blueprint and hasattr(effect_blueprint, "execute_triggered_branches"):
                    expire_ctx = {
                        "stack_multiplier": getattr(self.instance_ref, "stacks", 1),
                        "current_stacks": getattr(self.instance_ref, "stacks", 1),
                        "active_effect": self.instance_ref,
                        "owner_entity": self.target,
                    }
                    effect_blueprint.execute_triggered_branches(
                        "on_pre_remove",
                        sim,
                        self.source,
                        self.target,
                        context=expire_ctx,
                        ability=getattr(self.instance_ref, "ability_ref", None),
                    )
                self.target.cleanup_expired_effects([dot_name])
                is_dot = (
                    "tag.abl.debuff.damage_over_time" in getattr(self.instance_ref, "tags", ())
                    or any(
                        t.get("trigger") == "on_tick"
                        for b in getattr(effect_blueprint, "branches", ())
                        for t in getattr(b, "triggers", ())
                    )
                )
                label = "DoT" if is_dot else "Buff"
                if getattr(sim, "verbose", True):
                    print(f"[{sim.current_time:.2f}s] {label} expired and cleared: {dot_name}")
            return

        # Legacy fallback without blueprint
        if getattr(self.target, "effects", {}).get(dot_name) is not self.instance_ref:
            return

        actions = self.instance_ref.action_data.get('actions') or []
        from src.swtorsim.abilities import execute_single_action
        for action in actions:
            execute_single_action(sim, self.source, self.target, action, dot_name)
        self.instance_ref.ticks_remaining -= 1
        if self.instance_ref.ticks_remaining > 0:
            next_tick_time = sim.current_time + getattr(self.instance_ref, "interval", 1.0)
            sim.schedule_absolute(next_tick_time, self)
        else:
            self.target.cleanup_expired_effects([dot_name])
            if getattr(sim, "verbose", True):
                print(f"[{sim.current_time:.2f}s] DoT expired and cleared: {dot_name}")

class ChannelTickEvent(Event):
    """Represents a single tick of a channeled ability.
    Executes branch actions, validates per-tick resource cost, and schedules subsequent ticks.
    """

    def __init__(self, *args, **kwargs):
        if len(args) == 1 and hasattr(args[0], "remaining_ticks"):
            self.channel = args[0]
            self.source = getattr(self.channel, "caster", None)
            self.target = getattr(self.channel, "target", None)
        elif len(args) >= 3:
            self.source = args[0]
            self.target = args[1]
            self.channel = args[2]
        else:
            self.channel = kwargs.get("channel") or kwargs.get("channel_instance")
            self.source = kwargs.get("player") or getattr(self.channel, "caster", None)
            self.target = kwargs.get("target") or getattr(self.channel, "target", None)
        super().__init__(f"Channel Tick: {getattr(self.channel, 'name', 'Channel')}")

    def resolve(self, sim):
        """Executes tick actions, consumes resources, and schedules the next tick or ends the channel."""
        if getattr(self.source, "active_channel", None) is not self.channel:  # safeguard for clipping
            return

        self.channel.current_tick = getattr(self.channel, "current_tick", 0) + 1
        self.channel.remaining_ticks -= 1

        # 1. Execute on_tick triggered branches across all ability effects
        ability = getattr(self.channel, "ability", None)
        if ability is not None:
            for eff in getattr(ability, "effects", {}).values():
                if hasattr(eff, "execute_triggered_branches"):
                    eff.execute_triggered_branches(
                        "on_tick",
                        sim,
                        self.source,
                        self.target,
                        ability=ability,
                        tick_number=self.channel.current_tick,
                    )

        # 2. Legacy action_data fallback if present
        actions = getattr(self.channel, "action_data", {}).get("actions") or []
        if actions:
            from src.swtorsim.abilities import execute_single_action
            for action in actions:
                execute_single_action(sim, self.source, self.target, action, self.channel.name)

        # Check if ability_cancel terminated the channel during tick execution
        if getattr(self.channel, "is_finished", False) or getattr(self.source, "active_channel", None) is not self.channel:
            self.channel.is_finished = True
            if getattr(self.source, "active_channel", None) is self.channel:
                self.source.active_channel = None
                self.source.is_channeling = False
            from src.swtorsim.abilities import cleanup_channel_effects
            cleanup_channel_effects(self.channel, sim)
            target_time = (
                self.source.get_next_action_time(sim.current_time)
                if hasattr(self.source, "get_next_action_time")
                else max(sim.current_time, getattr(self.source, "next_gcd", sim.current_time))
            )
            sim.schedule_absolute(target_time, PlayerReady(self.source, self.target))
            return

        if self.channel.remaining_ticks > 0:
            next_tick_time = sim.current_time + self.channel.tick_interval
            sim.schedule_absolute(next_tick_time, ChannelTickEvent(self.channel))
        else:
            self.channel.is_finished = True
            self.source.active_channel = None
            self.source.is_channeling = False
            if getattr(sim, "verbose", True):
                print(f"[{sim.current_time:.3f}] {self.channel.name} channel over.")
            ability = getattr(self.channel, "ability", None)
            if ability is not None:
                for eff in getattr(ability, "effects", {}).values():
                    if hasattr(eff, "execute_triggered_branches"):
                        eff.execute_triggered_branches(
                            "on_channeling_ended",
                            sim,
                            self.source,
                            self.target,
                            ability=ability,
                            context={"is_successful": True, "caster": self.source, "target": self.target},
                        )
            if sim is not None and hasattr(sim, "triggers"):
                sim.triggers.dispatch(
                    "on_channeling_ended",
                    sim,
                    {
                        "caster": self.source,
                        "target": self.target,
                        "enemy_target": self.target,
                        "ability_spec": getattr(ability, "fqn", None),
                        "tags": getattr(ability, "tags", ()),
                        "is_successful": True,
                    },
                )
            from src.swtorsim.abilities import cleanup_channel_effects
            cleanup_channel_effects(self.channel, sim)
            target_time = (
                self.source.get_next_action_time(sim.current_time)
                if hasattr(self.source, "get_next_action_time")
                else max(sim.current_time, getattr(self.source, "next_gcd", sim.current_time))
            )
            sim.schedule_absolute(target_time, PlayerReady(self.source, self.target))

class CastFinishEvent(Event):
    """Fired when an ability with a cast time finishes casting."""

    def __init__(self, caster, target, ability, entry_effect_ids):
        super().__init__(f"Cast Finish {getattr(ability, 'name', 'Ability')}")
        self.caster = caster
        self.target = target
        self.ability = ability
        self.entry_effect_ids = entry_effect_ids

    def resolve(self, sim):
        """Completes the cast if uninterrupted, executes entry effects, and dispatches ``on_ability_post_activate``."""
        # Safeguard: if cast was interrupted or cancelled, abort
        if getattr(self.caster, "active_cast", None) is not self.ability:
            return

        self.caster.active_cast = None
        self.caster.is_casting = False

        # Timed casts pay their resource cost on completion (cost modifiers evaluated now).
        # If the pool can no longer cover the cost, the cast fails without executing effects.
        resource = getattr(self.caster, "resource", None)
        if resource is not None and hasattr(self.caster, "calculate_resource_cost"):
            final_spend = self.caster.calculate_resource_cost(
                self.ability.name, getattr(self.ability, "energy_cost", 0.0), apply=True
            )
            if final_spend > 0.0:
                if not resource.spend(final_spend):
                    if getattr(sim, "verbose", True):
                        print(f"[{sim.current_time:.3f}s] {self.caster.name} failed casting {self.ability.name} (insufficient resource)")
                    target_time = (
                        self.caster.get_next_action_time(sim.current_time)
                        if hasattr(self.caster, "get_next_action_time")
                        else max(sim.current_time, getattr(self.caster, "next_gcd", sim.current_time))
                    )
                    sim.schedule_absolute(target_time, PlayerReady(self.caster, getattr(self.caster, "current_target", self.target)))
                    return
                if getattr(sim, "tracer", None) is not None:
                    sim.tracer.record_resource_change(
                        timestamp=sim.current_time,
                        entity_name=self.caster.name,
                        resource_type=getattr(resource, "pool_type", "Resource"),
                        current=resource.current,
                        delta=-final_spend,
                        reason=f"Cast {self.ability.name}",
                    )

        if getattr(sim, "verbose", True):
            print(f"[{sim.current_time:.3f}s] {self.caster.name} finished casting {self.ability.name}")

        for entry_id in self.entry_effect_ids:
            self.ability.execute_effect(entry_id, self.caster, self.target, sim)

        if sim is not None and hasattr(sim, "triggers"):
            sim.triggers.dispatch(
                "on_ability_post_activate",
                sim,
                {
                    "caster": self.caster,
                    "target": self.target,
                    "enemy_target": self.target,
                    "ability_spec": getattr(self.ability, "fqn", None),
                    "tags": getattr(self.ability, "tags", ()),
                    "from_actor": 2,
                },
            )

        target_time = (
            self.caster.get_next_action_time(sim.current_time)
            if hasattr(self.caster, "get_next_action_time")
            else max(sim.current_time, getattr(self.caster, "next_gcd", sim.current_time))
        )
        sim.schedule_absolute(target_time, PlayerReady(self.caster, getattr(self.caster, "current_target", self.target)))

class ResourceTick(Event):
    """Represents the passive energy regen events"""
    def __init__(self, player: "Player", interval: float = 1.0): #keeping interval because I don't know how shit is, don't want to assume it's every second
        super().__init__(f"Resource Passive Tick")
        self.player = player
        self.interval = interval

    def resolve(self, sim):
        """Applies alacrity, generates the resource, and schedules the next tick."""
        alacrity_pct = self.player.stats.get("Alacrity", 0.0)
        alacrity_mod = 1.0 + alacrity_pct
        old_val = getattr(self.player.resource, "current", 0.0)
        self.player.resource.tick_passive_regen(self.interval, alacrity_mod, player=self.player) #generate
        if getattr(sim, "tracer", None) is not None:
            sim.tracer.record_resource_change(
                timestamp=sim.current_time,
                entity_name=self.player.name,
                resource_type=getattr(self.player.resource, "pool_type", "Resource"),
                current=self.player.resource.current,
                delta=self.player.resource.current - old_val,
                reason="Passive Regen Tick",
            )
        sim.schedule_relative(self.interval, self) #schedule next

class ResourceGainEvent(Event):
    """Represents one-time resource gain events."""

    def __init__(self, player, amount: float, source: str = "Resource Gain"):
        super().__init__("Resource Gain")
        self.player = player
        self.amount = float(amount)
        self.source = source

    def resolve(self, sim):
        """Adds the resource value to the resource pool and records trace telemetry."""
        if not hasattr(self.player, "resource") or self.player.resource is None:
            return
        old_val = getattr(self.player.resource, "current", 0.0)
        self.player.resource.generate(self.amount)
        new_val = getattr(self.player.resource, "current", 0.0)
        if getattr(sim, "tracer", None) is not None:
            sim.tracer.record_resource_change(
                timestamp=sim.current_time,
                entity_name=self.player.name,
                resource_type=getattr(self.player.resource, "pool_type", "Resource"),
                current=new_val,
                delta=self.amount,
                reason=self.source,
            )

class ChargeRestoreEvent(Event):
    """Represents a single charge restore event"""
    def __init__(self, caster: "Player", ability):
        super().__init__("Charge Restore")
        self.caster = caster
        self.ability = ability

    def resolve(self, sim):
        """Delegates charge restoration to the ability if this event is still active"""
        if self.ability.active_charge_event is not self:
            return

        self.ability.restore_charge(self.caster, sim, amount=1, from_timer=True)


class DelayedBranchEvent(Event):
    """Executes an ability branch after a delay (e.g. on_timer_expired secondary strikes)."""

    def __init__(self, branch, caster, target, ability=None, context=None):
        super().__init__(f"Delayed Branch: {getattr(ability, 'name', 'Ability')}")
        self.branch = branch
        self.caster = caster
        self.target = target
        self.ability = ability
        self.context = context or {}

    def resolve(self, sim):
        """Executes the delayed branch if neither caster nor target is dead."""
        if getattr(self.target, "is_dead", False) or getattr(self.caster, "is_dead", False):
            return
        self.branch.execute(
            sim,
            self.caster,
            self.target,
            context=self.context,
            ability=self.ability,
        )

class ProjectileImpactEvent(Event):
    """Fired when an in-flight projectile arrives at its target, triggering on_travel_complete branches."""

    def __init__(self, effect, caster, target, ability=None, context=None):
        abl_name = getattr(ability, "name", "Ability")
        super().__init__(f"Projectile Impact: {abl_name}")
        self.effect = effect
        self.caster = caster
        self.target = target
        self.ability = ability
        self.context = context or {}

    def resolve(self, sim):
        """Dispatches ``on_travel_complete`` branches on the projectile's effect."""
        if getattr(self.target, "is_dead", False) or getattr(self.caster, "is_dead", False):
            return
        if self.effect:
            self.effect.execute_triggered_branches(
                "on_travel_complete",
                sim,
                self.caster,
                self.target,
                context=self.context,
                ability=self.ability,
            )

