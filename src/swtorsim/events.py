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
    """Represents a single ability cast event
        TEMPORARY PLACEHOLDER"""
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
    def __init__(self, source, target, final_damage, is_crit, ability_name, attack_type=None, damage_type=None):
        super().__init__()
        self.source = source
        self.target = target
        self.final_damage = final_damage
        self.is_crit = is_crit
        self.ability_name = ability_name
        self.attack_type = attack_type
        self.damage_type = damage_type

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
        print(f"[{sim.current_time:.2f}s] {self.ability_name} deals {self.final_damage}{crit_string} damage to {self.target.name} (HP: {self.target.hp})")

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

    def resolve(self, sim):
        """Calls damage calculation, determines when to apply damage, calls for damage to land,
        calls for proc evaluation."""
        action_with_ctx = dict(self.action_data)
        action_with_ctx["tags"] = self.tags
        action_with_ctx["ability_fqn"] = self.ability_fqn
        action_with_ctx["ability_name"] = self.ability_name

        final_damage, is_crit = calculate_hit(self.source, self.target, action_with_ctx)
        resolved_at = action_with_ctx.get("resolved_attack_type", self.action_data.get("attack_type", 1))
        resolved_dt = action_with_ctx.get("resolved_damage_type", self.action_data.get("damage_type", 1))

        instant_land = ApplyDamageLand(
            self.source,
            self.target,
            final_damage,
            is_crit,
            self.ability_name,
            attack_type=resolved_at,
            damage_type=resolved_dt,
        )
        instant_land.resolve(sim)

        if sim is not None and hasattr(sim, "triggers"):
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
            weapon_mode = 2 if is_weapon_attack else 0
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
            }
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

    def resolve(self, sim):
        """Evaluates the rotation. If successful, evaluate again on next possible gcd (can be same one). If not,
         tries again 0.1seconds later."""
        if getattr(self.player, "rotation", None) is None:
            return
        acted = self.player.rotation.evaluate(self.player, self.target, sim)
        if acted:
            target_time = max(sim.current_time, self.player.next_gcd) #to prevent any accidental past scheduling
            sim.schedule_absolute(target_time, PlayerReady(self.player, self.target))
        else:
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

        blueprint = getattr(self.instance_ref, "effect_blueprint", None)
        ability = getattr(self.instance_ref, "ability_ref", None)
        caster = getattr(self.instance_ref, "caster_ref", self.entity)
        if blueprint and hasattr(blueprint, "execute_triggered_branches"):
            blueprint.execute_triggered_branches(
                "on_pre_remove",
                sim,
                caster,
                self.entity,
                ability=ability,
            )

        self.entity.cleanup_expired_effects([self.effect_name])

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
            else:
                self.target.cleanup_expired_effects([dot_name])
                print(f"[{sim.current_time:.2f}s] DoT expired and cleared: {dot_name}")
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

        if getattr(self.channel, "tick_cost", 0.0) > 0.0:
            if not self.source.resource.can_afford(self.channel.tick_cost):
                self.source.active_channel = None
                self.source.is_channeling = False
                target_time = max(sim.current_time, getattr(self.source, "next_gcd", sim.current_time))
                sim.schedule_absolute(target_time, PlayerReady(self.source, self.target))
                return
            self.source.resource.spend(self.channel.tick_cost)

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

        if self.channel.remaining_ticks > 0:
            next_tick_time = sim.current_time + self.channel.tick_interval
            sim.schedule_absolute(next_tick_time, ChannelTickEvent(self.channel))
        else:
            self.channel.is_finished = True
            self.source.active_channel = None
            self.source.is_channeling = False
            print(f"[{sim.current_time:.3f}] {self.channel.name} channel over.")
            target_time = max(sim.current_time, getattr(self.source, "next_gcd", sim.current_time))
            sim.schedule_absolute(target_time, PlayerReady(self.source, self.target))

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
        self.player.resource.tick_passive_regen(self.interval, alacrity_mod) #generate
        sim.schedule_relative(self.interval, self) #schedule next

class ResourceGainEvent(Event):
    """Represents one-time resource gain events."""
    def __init__(self, player, amount):
        super().__init__("Resource Gain")
        self.player = player
        self.amount = amount

    def resolve(self, sim):
        """Adds the resource value to the resource pool."""
        self.player.resource.generate(self.amount)

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
        if getattr(self.target, "is_dead", False) or getattr(self.caster, "is_dead", False):
            return
        self.branch.execute(
            sim,
            self.caster,
            self.target,
            context=self.context,
            ability=self.ability,
        )

