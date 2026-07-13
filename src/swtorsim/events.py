from typing import TYPE_CHECKING #yellow warnings annoy me


from src.swtorsim.combat_math import calculate_hit, EFFECTS, accuracy_roll
import random
from src.swtorsim.requirements import validate_all


if TYPE_CHECKING:
    from src.swtorsim.entities import Player, Target, ActiveDot, ActiveBuff
    from abilities import Ability


class Event:
    """Purpose is mostly for tiebreaking in case of similar occurrence time."""
    def __init__(self, name="EventName"):
        self.name = name


    def __lt__(self,other):
        """Tiebreaker for 2 events at the same time"""
        return False

class ApplyDamageLand(Event):
    """Applies pre-calculated damage to the target. Needed because of impact_delay, when damage is calculated earlier
    than it is applied."""
    def __init__(self, source, target, final_damage, is_crit, ability_name):
        super().__init__()
        self.source = source
        self.target = target
        self.final_damage = final_damage
        self.is_crit = is_crit
        self.ability_name = ability_name

    def resolve(self, sim):
        """Applies pre-calculated damage to the target, logs it into metrics."""
        crit_string = " (CRITICAL!)" if self.is_crit else ""
        sim.tracker.log_damage(self.ability_name, self.final_damage, self.is_crit, self.target, sim.current_time)
        self.target.hp -= self.final_damage
        print(f"[{sim.current_time:.2f}s] {self.ability_name} deals {self.final_damage}{crit_string} damage to {self.target.name} (HP: {self.target.hp})")

class DamageHit(Event):
    """ Represents a hit execution. Holds the snapshot data needed to calculate accuracy, damage, and trigger procs."""
    def __init__(self, source: "Player", target: "Target", action_data: dict, ability_name: str):
        super().__init__(f"{ability_name} Hit")
        self.source = source
        self.target = target
        self.action_data = action_data
        self.ability_name = ability_name

    def resolve(self, sim):
        """Evaluates accuracy, calls damage calculation, determines when to apply damage, calls for damage to land,
        calls for proc evaluation."""
        if not accuracy_roll(self.source, self.action_data.get("hand", "main")):
            return
        final_damage, is_crit = calculate_hit(self.source, self.target, self.action_data)

        impact_delay = self.action_data.get("impact_delay", 0.0)
        if impact_delay > 0.0:
            sim.schedule_relative(impact_delay, ApplyDamageLand(
                self.source, self.target, final_damage, is_crit, self.ability_name
            ))
        else: #no scheduling as it lands immediately, don't want another even scheduled for the same time to skip ahead
            instant_land = ApplyDamageLand(self.source, self.target, final_damage, is_crit, self.ability_name)
            instant_land.resolve(sim)

        tags = self.action_data.get("tags", [])
        self.evaluate_on_hit_procs(sim, is_crit, tags)

    def evaluate_on_hit_procs(self, sim, is_crit: bool, tags):
        """Evaluates and triggers all eligible procs for the source based on the current hit."""
        for proc in self.source.procs.values():
            if not self.hit_proc_can_trigger(proc, sim, is_crit, tags):
                continue
            print(f'[{sim.current_time}] Proc {proc.name} triggered')
            self._trigger_proc_effects(proc, sim)

    def hit_proc_can_trigger(self, proc, sim, is_crit: bool, tags) -> bool:
        """Validates if a specific proc can fire"""
        if proc.trigger in ("cast", "periodic"):
            return False
        if sim.current_time < proc.next_possible_proc:
            return False
        if proc.trigger == "crit" and not is_crit:
            return False
        if proc.required_tags and not any(tag in tags for tag in proc.required_tags):
            return False
        if not validate_all(proc.conditions, self.source, self.target):
            return False
        if random.random() > proc.chance:
            return False
        return True

    def _trigger_proc_effects(self, proc, sim):
        """Applies the proc's internal cooldown and executes its actions"""
        current_icd = self.source.scale_time_modifier(proc.icd) if proc.affected_by_cdr else proc.icd
        proc.next_possible_proc = sim.current_time + current_icd
        from src.swtorsim.abilities import execute_single_action
        for action in proc.actions:
            execute_single_action(sim, self.source, self.target, action, proc.name)


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
    def __init__(self, player: "Player", target: "Target"):
        super().__init__("Player Ready")
        self.player = player
        self.target = target

    def resolve(self, sim):
        """Evaluates the rotation. If successful, evaluate again on next possible gcd (can be same one). If not,
         tries again 0.1seconds later."""
        acted = self.player.rotation.evaluate(self.player, self.target, sim)
        if acted:
            sim.schedule_absolute(self.player.next_gcd, self)
        else:
            sim.schedule_relative(0.1, self)

class BuffExpire(Event):
    """Handles the expiration of player buffs."""
    def __init__(self, player: "Player", buff_name: str, instance_ref: "ActiveBuff"):
        super().__init__(f"{buff_name} Expired")
        self.player = player
        self.buff_name = buff_name
        self.instance_ref = instance_ref

    def resolve(self, sim):
        """Removes the buff if it's instance is the one for the scheduled event (wasn't refreshed/removed already)."""
        active_buff = self.player.effects.get(self.buff_name)

        if active_buff is not self.instance_ref:
            return

        self.player.cleanup_expired_effects([self.buff_name])

        print(f"[{sim.current_time:.2f}s] Buff expired and cleared: {self.buff_name}")

class DebuffExpire(Event):
    """Handles the expiration of target debuffs."""
    def __init__(self, target: "Target", debuff_name: str, instance_ref: "ActiveBuff"):
        super().__init__(f"{debuff_name} Expired")
        self.target = target
        self.debuff_name = debuff_name
        self.instance_ref = instance_ref

    def resolve(self, sim):
        """Removes the buff if it's instance is the one for the scheduled event (wasn't refreshed/removed already)."""
        active_debuff = self.target.debuffs.get(self.debuff_name)
        if active_debuff is not self.instance_ref:
            return
        self.target.debuffs.pop(self.debuff_name, None)
        print(f"[{sim.current_time:.2f}s] Debuff expired and cleared: {self.debuff_name} on {self.target.name}")


class DotTick(Event):
    "Represents a Dot Tick. Handles action execution, tick's value decrease and following tick scheduling."
    def __init__(self, source: "Player", target: "Target", instance_ref: "ActiveDot"):
        super().__init__(f"DoT Tick: {instance_ref.name}")
        self.source = source
        self.target = target
        self.instance_ref = instance_ref

    def resolve(self, sim):
        """If it's instance's DoT has not been overlapped:
        Executes the tick according to DoT data, decreases ticks remaining and schedules next one if still ticks
        remaining. If not, deletes dot from target. """

        dot_name = self.instance_ref.name

        if self.target.dots.get(dot_name) is not self.instance_ref:
            return

        actions = self.instance_ref.action_data.get('actions')
        from src.swtorsim.abilities import execute_single_action
        for action in actions:
            execute_single_action(sim, self.source, self.target, action, dot_name)
        self.instance_ref.ticks_remaining -= 1
        if self.instance_ref.ticks_remaining > 0:
            next_tick_time = sim.current_time + self.instance_ref.interval
            sim.schedule_absolute(next_tick_time, self)
        else:
            del self.target.dots[dot_name]
            print(f"[{sim.current_time:.2f}s] DoT expired and cleared: {dot_name}")


class ChannelTickEvent(Event):
    """ Represents a single tick of a channeled ability.
        Validates resources, executes the action, and schedules the next tick/ cleans up.
        """
    def __init__(self, player, target, channel_instance):
        super().__init__(f"Channel Tick: {channel_instance.name}")
        self.source = player
        self.target = target
        self.channel = channel_instance

    def resolve(self, sim):
        """Executes tick actions, consumes resources, and schedules the next tick or ends the channel."""
        if self.source.active_channel is not self.channel: #safeguard for clipping
            return

        acted = False
        from src.swtorsim.abilities import execute_single_action

        if self.source.resource.current_value >= self.channel.tick_cost:
            acted = True
            actions =  self.channel.action_data.get('actions')
            for action in actions:
                execute_single_action(sim, self.source, self.target, action, self.channel.name)
            self.source.resource.spend(self.channel.tick_cost)
        self.channel.remaining_ticks -= 1

        if self.channel.remaining_ticks > 0 and acted == True: #channel next if channel still going
            next_tick_time = sim.current_time + self.channel.tick_interval
            sim.schedule_absolute(next_tick_time, ChannelTickEvent(self.source, self.target, self.channel))
        else: #if for any reason didn't act/channel is over, end channel and player is ready to act now
            self.source.active_channel = None
            self.source.is_channeling = False
            print(f"[{sim.current_time:.3f}] {self.channel.name} channel over.")
            sim.schedule_absolute(sim.current_time, PlayerReady(self.source, self.target))
            #if gcd not ready yet, gcd abilities won't happen from PlayerReady, no worries there

class ResourceTick(Event):
    """Represents the passive energy regen events"""
    def __init__(self, player: "Player", interval: float = 1.0): #keeping interval because i dont know how shit is, dont wanna assume it's every second
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
        print(f'[{sim.current_time:.2f}s] omg i gained {self.amount}')
        self.player.resource.generate(self.amount)
