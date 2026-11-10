"""Simulation entity initialization, passive blueprint hydration, and opening event scheduling."""

import copy
import random
import re
from typing import Any
from src.swtorsim.engine import Simulation
from src.swtorsim.abilities import Ability
from src.swtorsim.entities import Player, Dummy
from src.swtorsim.events import ResourceTick, PlayerReady, PeriodicProcTick, PreCombatEvent
from src.swtorsim.combat_curves import player_standard_health
from src.swtorsim.rotation import Rotation
from src.swtorsim.class_buffs import apply_class_buffs
from src.swtorsim.resources import resource_type_for_class
from src.swtorsim.run_config import normalize_pre_combat


def _strip_effect_number_suffix(effect_name: str, parent_name: str) -> str:
    """Normalizes internal effect names like 'Bloodletting_3' back to 'Bloodletting' when appropriate."""
    if not effect_name:
        return parent_name
    m = re.match(r"^(.+)_\d+$", effect_name)
    if m:
        prefix = m.group(1)
        if not parent_name or prefix.lower() == parent_name.lower():
            return parent_name or prefix
        return prefix
    return effect_name


def build_proc_registry(loadout_blueprints: dict) -> dict[str, dict[str, Any]]:
    """Builds an authoritative registry mapping canonical proc names to their lockout/ICD implementation."""
    procs_map: dict[str, dict[str, Any]] = {}
    for fqn, bp in (loadout_blueprints or {}).items():
        if str(fqn).startswith("tal."):
            continue
        parent_name = str(getattr(bp, "name", None) or fqn).strip()
        ability_type = getattr(bp, "type", "passive") or "passive"
        effects = getattr(bp, "effects", {}) or {}
        eff_iter = effects.values() if isinstance(effects, dict) else effects

        for eff in eff_iter:
            raw_eff_name = str(getattr(eff, "name", None) or parent_name).strip()
            eff_tags = [str(t) for t in (getattr(eff, "tags", None) or [])]
            initializers = getattr(eff, "initializers", None) or []
            init_types = {
                init.get("initializer_type")
                for init in initializers
                if isinstance(init, dict)
            }
            is_proc_init = "eff_initializer__set_effect_procs" in init_types
            duration = float(getattr(eff, "duration", 0.0) or 0.0)

            # 1. Explicit ICD lockout effects (e.g. Bloodletting_3, Raze_4, Mastery Surge_3)
            if any("lockout" in t.lower() for t in eff_tags):
                proc_label = _strip_effect_number_suffix(raw_eff_name, parent_name)
                procs_map[proc_label] = {
                    "name": proc_label,
                    "effect_name": raw_eff_name,
                    "source_name": parent_name,
                    "source_fqn": fqn,
                    "icd": duration,
                    "kind": "lockout_effect",
                }
                continue

            # 2. Branch trigger ICDs (interval_61) on passive/proc abilities
            if ability_type == "passive":
                for branch in getattr(eff, "branches", None) or []:
                    for trig in getattr(branch, "triggers", None) or []:
                        intervals = trig.get("intervals") or {}
                        icd_val = float(intervals.get("interval_61") or 0.0)
                        if icd_val > 0.0:
                            proc_label = _strip_effect_number_suffix(raw_eff_name, parent_name)
                            procs_map[proc_label] = {
                                "name": proc_label,
                                "source_name": parent_name,
                                "source_fqn": fqn,
                                "icd": icd_val,
                                "kind": "trigger_icd",
                            }

            # 3. Proc buff effects
            if is_proc_init and duration > 0.0:
                clean_name = _strip_effect_number_suffix(raw_eff_name, parent_name)
                if clean_name not in procs_map:
                    procs_map[clean_name] = {
                        "name": clean_name,
                        "effect_name": raw_eff_name,
                        "source_name": parent_name,
                        "source_fqn": fqn,
                        "icd": duration,
                        "kind": "proc_buff",
                    }

    return procs_map


def schedule_periodic(player, target, sim):
    """Schedules the randomized initial tick for periodic proc effects."""
    for proc in player.procs.values():
        if getattr(proc, 'trigger', None) == "periodic":
            is_affected = getattr(proc, 'affected_by_cdr', False)
            interval = player.scale_time_modifier(proc.icd) if is_affected else proc.icd
            first_tick = random.uniform(0.0, interval)
            sim.schedule_absolute(first_tick, PeriodicProcTick(player, target, proc))

def prepare_simulation(
    rotation_config,
    stats_config,
    loadout_blueprints,
    dummy_hp,
    debuff_module,
    verbose: bool = True,
    seed: int | None = None,
    tracer=None,
    config=None,
    precast: str | dict | None = None,
    pre_combat: list | None = None,
):
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
    player.proc_registry = build_proc_registry(loadout_blueprints)

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
    from src.swtorsim.effects import EffectCollection
    target.effects = EffectCollection(copy.deepcopy(debuff_module))
    target.recalculate_stats()

    if seed is not None:
        random.seed(seed)
    sim = Simulation(verbose=verbose, seed=seed, tracer=tracer)
    player.current_target = target

    for eff_key, eff in target.effects.items():
        sim.tracker.log_effect_applied(
            target.name,
            eff_key,
            0.0,
            stacks=getattr(eff, "stacks", 1),
            is_passive=getattr(eff, "is_passive", False),
        )

    # Pass 1: Register all passive blueprints in `player.passive_db` and apply flat `stat_changes`
    # before executing any `entry_effect_ids` so cross-passive `has_ability` checks (e.g. Blood Tracker)
    # are independent of dictionary iteration order. After Pass 1 completes, Pass 2 runs `entry_effect_ids`.
    from src.swtorsim.effects import ActiveEffect
    instantiated_passives = []
    for fqn, bp in passive_blueprints.items():
        passive_abl = Ability(bp)
        player.passive_db[fqn] = passive_abl
        if passive_abl.name:
            player.passive_db[passive_abl.name.lower().replace(" ", "_")] = passive_abl
        instantiated_passives.append(passive_abl)
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

    for passive_abl in instantiated_passives:
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

    # Resolve pre-combat / pre-cast steps from config, rotation, or explicit arguments
    cfg_precast = getattr(config, "precast", None) if config else None
    cfg_pre_combat = getattr(config, "pre_combat", None) if config else None
    rot_precast = rotation_config.get("precast") if isinstance(rotation_config, dict) else None
    rot_pre_combat = rotation_config.get("pre_combat") if isinstance(rotation_config, dict) else None

    resolved_precast = precast or cfg_precast or rot_precast
    resolved_pre_combat = pre_combat or cfg_pre_combat or rot_pre_combat
    pre_combat_steps = normalize_pre_combat(resolved_precast, resolved_pre_combat)

    # Schedule initial lifecycle events
    if pre_combat_steps:
        sim.schedule_absolute(0.0, PreCombatEvent(player, target, pre_combat_steps, index=0))
    else:
        sim.schedule_absolute(0.0, PlayerReady(player, target))
    first_regen_tick = random.uniform(0.0, 1.0)
    sim.schedule_absolute(first_regen_tick, ResourceTick(player))

    if tracer is not None:
        tracer.record_initial_state(
            player=player,
            target=target,
            config=config,
            loadout_blueprints=loadout_blueprints,
            rotation_config=rotation_config,
        )

    return sim, player, target
