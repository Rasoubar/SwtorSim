"""Simulation entity initialization, passive blueprint hydration, and opening event scheduling."""

import copy
import random
import re
from pathlib import Path
from typing import Any
from src.swtorsim.engine import Simulation, sim_log
from src.swtorsim.abilities import Ability
from src.swtorsim.entities import Player, Dummy
from src.swtorsim.events import ResourceTick, PlayerReady, PeriodicProcTick, PreCombatRunner, DEFAULT_PRE_COMBAT_MAX_WAIT
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

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_TACTICAL_BP_CACHE: dict[tuple[str, str], Any] = {}


def _register_passive_blueprint(player, bp, sim):
    """Pass 1 for one passive: registers it in ``passive_db`` and applies flat ``stat_changes``."""
    from src.swtorsim.effects import ActiveEffect
    passive_abl = Ability(bp)
    player.passive_db[bp.fqn] = passive_abl
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
            sim.current_time,
            stacks=getattr(eff, "stacks", 1),
            is_passive=True,
        )
    return passive_abl


def _load_tactical_blueprint(fqn: str):
    """Loads (and caches) a tactical blueprint from the active environment's parsed data."""
    from src.swtorsim.abilities import AbilityBlueprint
    from src.swtorsim.config_load import fqn_to_relative_path
    from src.swtorsim.settings import get_extractor_data_dir

    parsed_dir = get_extractor_data_dir() / "parsed"
    if not parsed_dir.is_absolute():
        parsed_dir = _PROJECT_ROOT / parsed_dir
    key = (str(parsed_dir), fqn)
    if key not in _TACTICAL_BP_CACHE:
        path = parsed_dir / fqn_to_relative_path(fqn)
        if not path.is_file():
            raise ValueError(f"Tactical blueprint not found for '{fqn}': {path}")
        _TACTICAL_BP_CACHE[key] = AbilityBlueprint.from_file(path)
    return _TACTICAL_BP_CACHE[key]


def validate_tactical_for_class(fqn: str, class_name: str | None) -> None:
    """Raises ValueError unless ``fqn`` is a tactical usable by ``class_name`` (or generic)."""
    from src.swtorsim.run_config import CLASS_FQN_KEYWORDS, TACTICAL_PREFIX

    if not isinstance(fqn, str) or not fqn.startswith(TACTICAL_PREFIX):
        raise ValueError(f"swap_tactical target '{fqn}' is not a tactical ({TACTICAL_PREFIX}*).")
    keywords = CLASS_FQN_KEYWORDS.get(str(class_name or "").lower())
    if keywords is not None and "generic" not in fqn and not any(k in fqn for k in keywords):
        raise ValueError(f"Tactical '{fqn}' is not available to class '{class_name}'.")


def validate_pre_combat_rules(steps: list[dict], pull_conditions: dict | None) -> None:
    """Raises ValueError for unknown rule keys in ``wait_until`` steps or pull conditions."""
    from src.swtorsim.requirements import CONDITION_REGISTRY

    def _check(rules, label):
        if not rules:
            return
        if not isinstance(rules, dict):
            raise ValueError(f"{label} must be a rules object, got {type(rules).__name__}.")
        if "list" in rules and "logic" in rules:
            return  # extracted AST condition format
        unknown = [k for k in rules if k not in CONDITION_REGISTRY]
        if unknown:
            raise ValueError(f"{label} uses unknown condition(s): {', '.join(unknown)}.")

    for idx, step in enumerate(steps or []):
        if isinstance(step, dict) and "wait_until" in step:
            _check(step.get("wait_until"), f"Pre-combat step {idx + 1} wait_until")
    _check(pull_conditions, "pull_conditions")


def prepare_tactical_swaps(player, steps: list[dict], class_name: str | None) -> None:
    """Validates every ``swap_tactical`` step and preloads its blueprint into ``player.gear_library``."""
    for step in steps:
        fqn = step.get("swap_tactical") if isinstance(step, dict) else None
        if not fqn:
            continue
        validate_tactical_for_class(fqn, class_name)
        if fqn not in player.gear_library:
            player.gear_library[fqn] = _load_tactical_blueprint(fqn)


def _unequip_passive(player, fqn: str, sim) -> None:
    """Removes a passive's registration, permanent effects and procs; timed effects it already produced are kept."""
    old_abl = player.passive_db.pop(fqn, None)
    if old_abl is not None and getattr(old_abl, "name", None):
        alias = old_abl.name.lower().replace(" ", "_")
        if player.passive_db.get(alias) is old_abl:
            player.passive_db.pop(alias, None)
    old_name = getattr(old_abl, "name", None) if old_abl is not None else None

    for entity in (player, getattr(player, "current_target", None)):
        if entity is None:
            continue
        entity._sim_ref = sim
        doomed = []
        for key, eff in list(entity.effects.items()):
            from_source = (
                str(key).startswith(f"{fqn}:")
                or getattr(eff, "fqn", None) == fqn
                or (entity is player and old_name and key == old_name and getattr(eff, "is_passive", False))
            )
            if not from_source:
                continue
            is_timed = getattr(eff, "expires_at", None) is not None
            if is_timed:
                continue
            doomed.append(key)
        entity.cleanup_expired_effects(doomed)

    player.proc_registry = {
        name: info for name, info in (player.proc_registry or {}).items() if info.get("source_fqn") != fqn
    }


def _equip_passive(player, bp, sim) -> None:
    """Pass 1 + Pass 2 for a single newly equipped passive, then refreshes its proc registry."""
    passive_abl = _register_passive_blueprint(player, bp, sim)
    for entry_id in passive_abl.entry_effect_ids:
        passive_abl.execute_effect(entry_id, player, player, sim)
    player.proc_registry.update(build_proc_registry({bp.fqn: bp}))


def swap_tactical(player, new_fqn: str, sim) -> bool:
    """Instant, off-GCD, zero-cost tactical swap. Returns False when ``new_fqn`` is already equipped.

    Unequips the current tactical (registration, permanent effects, triggers, proc registry;
    timed effects it already produced are always kept), equips the new one exactly like loadout
    setup does, and recalculates stats.
    """
    new_fqn = str(new_fqn or "").strip()
    old_fqn = getattr(player, "tactical_fqn", "") or ""
    if not new_fqn or new_fqn == old_fqn:
        return False
    bp = player.gear_library.get(new_fqn)
    if bp is None:
        bp = _load_tactical_blueprint(new_fqn)
        player.gear_library[new_fqn] = bp

    player._sim_ref = sim
    if old_fqn:
        _unequip_passive(player, old_fqn, sim)
    _equip_passive(player, bp, sim)
    player.tactical_fqn = new_fqn
    player.recalculate_stats()
    for abl in player.ability_db.values():
        if hasattr(abl, "apply_charge_modifiers"):
            abl.apply_charge_modifiers(player)

    if getattr(sim, "verbose", True):
        sim_log(sim, f"{player.name} swapped tactical {old_fqn or '<none>'} -> {new_fqn}")
    tracer = getattr(sim, "tracer", None)
    if tracer is not None and hasattr(tracer, "record_tactical_swap"):
        tracer.record_tactical_swap(
            sim.current_time, player.name, old_fqn, new_fqn,
            new_name=str(getattr(bp, "name", None) or new_fqn),
        )
    return True


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
    pull_conditions: dict | None = None,
    pull_max_wait: float | None = None,
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
    instantiated_passives = [
        _register_passive_blueprint(player, bp, sim) for bp in passive_blueprints.values()
    ]

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

    # Track the equipped tactical so pre-combat swaps can unequip it, and validate/preload swap targets
    from src.swtorsim.run_config import TACTICAL_PREFIX
    cfg_tactical = getattr(config, "tactical_fqn", "") if config else ""
    player.tactical_fqn = cfg_tactical or next(
        (f for f in passive_blueprints if str(f).startswith(TACTICAL_PREFIX)), ""
    )
    player.starting_tactical_fqn = player.tactical_fqn
    if player.tactical_fqn and player.tactical_fqn in passive_blueprints:
        player.gear_library[player.tactical_fqn] = passive_blueprints[player.tactical_fqn]
    prepare_tactical_swaps(player, pre_combat_steps, stats_config.get("class_name"))

    # Fight-start (pull) gate: rotation-style rules that must hold before the rotation starts
    rot_pull = rotation_config.get("pull_conditions") if isinstance(rotation_config, dict) else None
    rot_pull_wait = rotation_config.get("pull_max_wait") if isinstance(rotation_config, dict) else None
    resolved_pull = pull_conditions if pull_conditions is not None else (rot_pull or {})
    resolved_pull_wait = pull_max_wait if pull_max_wait is not None else rot_pull_wait
    validate_pre_combat_rules(pre_combat_steps, resolved_pull)

    # Schedule initial lifecycle events
    if pre_combat_steps or resolved_pull:
        runner = PreCombatRunner(
            player,
            target,
            pre_combat_steps,
            pull_conditions=resolved_pull,
            pull_max_wait=float(resolved_pull_wait) if resolved_pull_wait is not None else DEFAULT_PRE_COMBAT_MAX_WAIT,
        )
        player.pre_combat = runner
        sim.pre_combat_runner = runner
        runner.request(sim, 0.0)
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
