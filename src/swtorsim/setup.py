import copy
import random
from src.swtorsim.engine import Simulation
from src.swtorsim.abilities import Ability
from src.swtorsim.entities import Player, Dummy
from src.swtorsim.events import ResourceTick, PlayerReady, PeriodicProcTick
from src.swtorsim.combat_curves import player_standard_health
from src.swtorsim.rotation import Rotation
from src.swtorsim.class_buffs import apply_class_buffs
from src.swtorsim.resources import resource_type_for_class

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
        passives=passive_blueprints,
        resource=resource_type_for_class(stats_config.get("class_name")),
    )

    # Set up player base stats. Standard health comes from the level curve.
    player.level = stats_config.get("level", player.level)
    for stat_key, stat_value in stats_config.get("stats", {}).items():
        if stat_key == "Standard_health":
            continue
        player.base_stats[stat_key] = stat_value
    player.base_stats["Standard_health"] = player_standard_health(player.level)
    player.recalculate_stats()

    # Set up dummy
    target = Dummy("Target Dummy", hp=dummy_hp)
    target.effects = copy.deepcopy(debuff_module)
    target.recalculate_stats()

    sim = Simulation()
    player.current_target = target

    for eff_key, eff in target.effects.items():
        sim.tracker.log_effect_applied(
            target.name,
            eff_key,
            0.0,
            stacks=getattr(eff, "stacks", 1),
            is_passive=getattr(eff, "is_passive", False),
        )

    # Instantiate and activate passive blueprints (skill tree passives, tacticals, legendaries, relics)
    from src.swtorsim.effects import ActiveEffect
    for fqn, bp in passive_blueprints.items():
        passive_abl = Ability(bp)
        player.passive_db[fqn] = passive_abl
        if passive_abl.name:
            player.passive_db[passive_abl.name.lower().replace(" ", "_")] = passive_abl
        if getattr(bp, "stat_changes", None):
            eff = ActiveEffect.from_stat_changes(
                {
                    "fqn": bp.fqn,
                    "name": bp.name,
                    "tags": list(bp.tags or []),
                    "stat_changes": bp.stat_changes,
                }
            )
            eff.is_passive = True
            eff_key = bp.name or bp.fqn
            player.effects[eff_key] = eff
            sim.tracker.log_effect_applied(
                player.name,
                eff_key,
                0.0,
                stacks=getattr(eff, "stacks", 1),
                is_passive=True,
            )
        for entry_id in passive_abl.entry_effect_ids:
            passive_abl.execute_effect(entry_id, player, player, sim)

    # Every player gets all class buffs plus the hidden permanent bonus
    apply_class_buffs(player, sim)
    player.recalculate_stats()

    # Apply charge modifiers to active abilities
    for abl in player.ability_db.values():
        if hasattr(abl, "apply_charge_modifiers"):
            abl.apply_charge_modifiers(player)

    # Assign rotation
    player.rotation = Rotation(name="Custom Profile Loop", steps_config=rotation_config, loop=True)

    # Schedule initial lifecycle events
    sim.schedule_absolute(0.0, PlayerReady(player, target))
    first_regen_tick = random.uniform(0.0, 1.0)
    sim.schedule_absolute(first_regen_tick, ResourceTick(player))

    return sim, player, target
