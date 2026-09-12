import copy
import random
from src.swtorsim.engine import Simulation
from src.swtorsim.abilities import Ability
from src.swtorsim.entities import Player, Dummy
from src.swtorsim.events import ResourceTick, PlayerReady, PeriodicProcTick
from src.swtorsim.rotation import Rotation

def pre_sim_effects(player):
    """Applies effects that alter abilities at the core and therefore need to be applied before running"""
    cooldown_effects = [e for e in player.effects.values() if e.id == 64 and e.required_tags]  #temporary fixes
    charge_effects = [e for e in player.effects.values() if e.id == 422 and e.required_tags]

    if not cooldown_effects and not charge_effects:
        return

    for ability in player.ability_db.values():
        if not hasattr(ability, "tags") or not ability.tags:
            continue
        for effect in cooldown_effects:
            if any(tag in ability.tags for tag in effect.required_tags):
                ability.cooldown -= effect.value
        for effect in charge_effects:
            if any(tag in ability.tags for tag in effect.required_tags):
                ability.max_charges += effect.value
                ability.charges += effect.value

def schedule_periodic(player, target, sim):
    """Schedules 1st even of periodic effects, like pt extra regen"""
    for proc in player.procs.values():
        if getattr(proc, 'trigger', None) == "periodic":
            is_affected = getattr(proc, 'affected_by_cdr', False)
            interval = player.scale_time_modifier(proc.icd) if is_affected else proc.icd
            first_tick = random.uniform(0.0, interval)
            sim.schedule_absolute(first_tick, PeriodicProcTick(player, target, proc))

def prepare_simulation(rotation_config, stats_config, loadout_blueprints, dummy_hp, debuff_module):
    """Prepares simulation entities from unified loadout blueprints."""
    active_abilities = {}
    passive_blueprints = {}

    # Separate active abilities from passives/gear
    for fqn, bp in loadout_blueprints.items():
        if bp.type == "active" and not fqn.startswith("tal."):
            # Instantiate runtime Ability from blueprint
            active_abilities[fqn] = Ability(bp)
        else:
            passive_blueprints[fqn] = bp

    # Initialize Player and Target
    player = Player(
        name=stats_config.get("class_name", "Unknown"),
        abilities=active_abilities,
        passives=passive_blueprints
    )

    # Set up player base stats
    for stat_key, stat_value in stats_config.get("stats", {}).items():
        player.base_stats[stat_key] = stat_value
    player.recalculate_stats()

    # Set up dummy
    target = Dummy("Target Dummy", hp=dummy_hp)
    target.effects = copy.deepcopy(debuff_module)
    target.recalculate_stats()

    sim = Simulation()

    # Assign rotation
    player.rotation = Rotation(name="Custom Profile Loop", steps_config=rotation_config, loop=True)

    # Schedule initial lifecycle events
    sim.schedule_absolute(0.0, PlayerReady(player, target))
    first_regen_tick = random.uniform(0.0, 1.0)
    sim.schedule_absolute(first_regen_tick, ResourceTick(player))

    return sim, player, target