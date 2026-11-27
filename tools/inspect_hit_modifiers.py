#!/usr/bin/env python3
"""
Inspect Hit Modifiers & Combat Math Tool
---------------------------------------
A general-purpose diagnostic tool to simulate a single hit of ANY ability for ANY class/discipline,
printing full telemetry on:
  1. Active player passives & buffs
  2. Active target debuffs
  3. Detailed handle_modifiers trace (buckets, flags, scalars)
  4. Exact mathematical step-by-step breakdown:
     - Base weapon scaling
     - Raw base damage range
     - Post-mitigation base damage range (armor DR factor)
     - Total multiplier and theoretical min/max non-crit & crit bands
  5. The actual simulated hit roll and damage value

Usage Examples:
  # Vengeance Juggernaut Vicious Slash
  .\\tools\\pyclean.exe tools/inspect_hit_modifiers.py --discipline juggernaut/vengeance --ability abl.sith_warrior.vicious_slash

  # Advanced Prototype Powertech Magnetic Blast
  .\\tools\\pyclean.exe tools/inspect_hit_modifiers.py --discipline powertech/advanced_prototype --ability abl.bounty_hunter.skill.advanced_prototype.magnetic_blast --mastery 16570 --power 13126 --tech-power 9332 --crit 3577 --weapon-min 1832 --weapon-max 3403

  # Using an existing run_config file:
  .\\tools\\pyclean.exe tools/inspect_hit_modifiers.py --config data/run_config/Carnage.json --ability abl.sith_warrior.skill.carnage.massacre
"""

import argparse
import copy
import json
import os
import sys
from pathlib import Path

# Ensure SwtorSim root is on sys.path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.swtorsim.abilities import AbilityBlueprint
from src.swtorsim.config_load import load_training_dummy_armor_debuffs, load_from_run_config
from src.swtorsim.run_config import load_run_config
from src.swtorsim.setup import prepare_simulation
from src.swtorsim import combat_math
from src.swtorsim import combat_math_unbucketed


def find_discipline_file(disc_query: str) -> Path:
    """Finds discipline json file in data/extractor/live/disciplines."""
    disc_dir = ROOT / "data" / "extractor" / "live" / "disciplines"
    clean_query = disc_query.lower().replace("\\", "/").strip()
    
    # Direct match if path-like
    if "/" in clean_query:
        parts = clean_query.split("/")
        candidate = disc_dir / parts[0] / f"{parts[1]}.json"
        if candidate.is_file():
            return candidate

    # Search recursively
    for p in disc_dir.rglob("*.json"):
        if clean_query in p.stem.lower() or clean_query in str(p.relative_to(disc_dir)).lower():
            return p

    raise FileNotFoundError(f"Could not find discipline matching '{disc_query}' in {disc_dir}")


def load_blueprint_by_fqn(fqn: str) -> AbilityBlueprint:
    """Loads AbilityBlueprint from parsed JSON directory."""
    parsed_dir = ROOT / "data" / "extractor" / "live" / "parsed"
    # Try exact path
    candidate = parsed_dir / Path(*fqn.split(".")).with_suffix(".json")
    if candidate.is_file():
        return AbilityBlueprint.from_file(candidate)

    # Search by stem
    stem = fqn.split(".")[-1]
    for p in parsed_dir.rglob(f"{stem}.json"):
        return AbilityBlueprint.from_file(p)

    raise FileNotFoundError(f"Could not find parsed ability blueprint for '{fqn}'")


def inspect_hit(
    discipline_path: Path = None,
    run_config_path: Path = None,
    ability_fqn: str = None,
    mastery: float = 16570.0,
    power: float = 13290.0,
    tech_power: float = 0.0,
    force_power: float = 9332.0,
    crit_rating: float = 3705.0,
    surge_arg: float = None,
    weapon_min: float = 2094.0,
    weapon_max: float = 3141.0,
    offhand_min: float = 0.0,
    offhand_max: float = 0.0,
    debuff_module: bool = True,
    dummy_hp: int = 6500000,
    burning: bool = False,
    bleeding: bool = False,
    poisoned: bool = False,
):
    print("=" * 80)
    print("SWTOR COMBAT ENGINE: SINGLE-HIT MODIFIER & FORMULA INSPECTOR")
    print("=" * 80)

    blueprints = {}
    class_name = "Unknown"
    discipline_name = "Unknown"
    debuffs = load_training_dummy_armor_debuffs() if debuff_module else {}

    if run_config_path and run_config_path.is_file():
        print(f"[CONFIG] Loading from run_config: {run_config_path.name}")
        cfg = load_run_config(str(run_config_path))
        inputs = load_from_run_config(cfg)
        blueprints = inputs.loadout_blueprints
        stats_config = inputs.stats_config
        rot_config = [{"type": "fixed", "ability_id": ability_fqn}]
        class_name = stats_config.get("class_name", "Unknown")
        discipline_name = stats_config.get("discipline", "Unknown")
    else:
        print(f"[DISCIPLINE] Loading from: {discipline_path.relative_to(ROOT)}")
        with open(discipline_path, "r", encoding="utf-8") as fp:
            disc_data = json.load(fp)

        class_name = disc_data.get("tab_name") or discipline_path.parent.name.capitalize()
        discipline_name = disc_data.get("package_name") or discipline_path.stem.capitalize()

        for fqn in disc_data.get("active_abilities", []):
            try:
                bp = load_blueprint_by_fqn(fqn)
                blueprints[fqn] = bp
            except Exception:
                pass

        # Ensure target ability is loaded
        if ability_fqn not in blueprints:
            target_bp = load_blueprint_by_fqn(ability_fqn)
            blueprints[ability_fqn] = target_bp
            ability_fqn = target_bp.fqn

        rot_config = [{"type": "fixed", "ability_id": ability_fqn}]

        stats_dict = {
            "Mastery": mastery,
            "Power": power,
            "Critical_rating": crit_rating,
            "Alacrity_rating": 0.0,
            "Accuracy_rating": 10000.0,
            "Main_hand_min": weapon_min,
            "Main_hand_max": weapon_max,
            "Off_hand_min": offhand_min,
            "Off_hand_max": offhand_max,
        }
        stats_dict["Critical Rating"] = crit_rating
        stats_dict["Alacrity Rating"] = 0.0
        stats_dict["Accuracy Rating"] = 10000.0
        if tech_power > 0:
            stats_dict["Tech Power"] = tech_power
            stats_dict["Tech_power"] = tech_power
        if force_power > 0:
            stats_dict["Force Power"] = force_power
            stats_dict["Force_power"] = force_power

        stats_config = {
            "stats": stats_dict,
            "class_name": class_name,
            "discipline": discipline_name,
            "level": 80,
        }

    print(f"[LOADOUT] Loaded {len(blueprints)} blueprints for {class_name} ({discipline_name})")
    print(f"[TARGET] Ability under test: {ability_fqn}")

    # Prepare simulation
    sim, player, target = prepare_simulation(
        rotation_config=rot_config,
        stats_config=stats_config,
        loadout_blueprints=blueprints,
        dummy_hp=dummy_hp,
        debuff_module=debuffs,
        verbose=False,
    )

    from src.swtorsim.effects import ActiveEffect
    if burning:
        target.effects["Burning"] = ActiveEffect(
            fqn="eff.test.burning",
            name="Burning",
            tags=frozenset(["tag.abl.debuff.burn", "tag.abl.debuff.fire", "burn", "fire"]),
            duration=60.0,
        )
    if bleeding:
        target.effects["Bleeding"] = ActiveEffect(
            fqn="eff.test.bleeding",
            name="Bleeding",
            tags=frozenset(["tag.abl.debuff.bleed", "bleed"]),
            duration=60.0,
        )
    if poisoned:
        target.effects["Poisoned"] = ActiveEffect(
            fqn="eff.test.poisoned",
            name="Poisoned",
            tags=frozenset(["tag.abl.debuff.poison", "poison"]),
            duration=60.0,
        )

    # Enforce 100% accuracy and 0% dummy defense to guarantee hit inspection
    player.stats["Main Accuracy"] = 2.0
    player.stats["Melee Accuracy"] = 2.0
    player.stats["Ranged Accuracy"] = 2.0
    player.stats["Force Accuracy"] = 2.0
    player.stats["Tech Accuracy"] = 2.0
    target.stats["Defense"] = 0.0
    target.stats["Resistance"] = 0.0

    # 1. Print Active Passives & Buffs
    print("\n--- ACTIVE PLAYER PASSIVES & ENTRY EFFECTS ---")
    for eff_id, eff in player.effects.items():
        mods = eff.get_effective_modifiers() if hasattr(eff, "get_effective_modifiers") else getattr(eff, "modifiers", [])
        mod_strs = [f"{m.stat}={m.value}" + (f" (targets: {list(m.targets)})" if m.targets else "") for m in mods]
        mods_preview = f" -> [{', '.join(mod_strs)}]" if mod_strs else ""
        print(f"  * {eff.name}{mods_preview}")

    # 2. Print Target Debuffs
    print("\n--- ACTIVE TARGET DEBUFFS ---")
    for eff_id, eff in target.effects.items():
        mods = eff.get_effective_modifiers() if hasattr(eff, "get_effective_modifiers") else getattr(eff, "modifiers", [])
        mod_strs = [f"{m.stat}={m.value}" + (f" (targets: {list(m.targets)})" if m.targets else "") for m in mods]
        mods_preview = f" -> [{', '.join(mod_strs)}]" if mod_strs else ""
        print(f"  * {eff.name}{mods_preview}")

    # 3. Hook handle_modifiers and calculate_base_damage
    captured_hits = []
    target_stem = ability_fqn.split(".")[-1]

    orig_handle_modifiers = combat_math.handle_modifiers

    def hooked_handle_modifiers(caster, tgt, action_data, damage_type=None):
        action_tags = frozenset(action_data.get("tags") or ())
        act_fqn = action_data.get("ability_fqn") or ""
        attack_type = action_data.get("attack_type", 1)
        hand = action_data.get("hand", "main")
        if damage_type is None:
            damage_type = action_data.get("resolved_damage_type") or action_data.get("damage_type", 1)

        # Track applied modifiers individually
        applied_mods = []

        # Trace caster buffs
        for buff in caster.effects.values():
            if getattr(buff, "is_expired", False):
                continue
            getter = getattr(buff, "get_effective_modifiers", None)
            eff_mods = getter() if getter is not None else getattr(buff, "modifiers", [])
            for m in eff_mods or ():
                test_buckets = {}
                test_mods = {'bonus_crit_chance': 0.0, 'bonus_crit_modifier': 0.0, 'bonus_armor_pen': 0.0, 'base_weapon_damage_modifier': 0.0, 'total_multiplier': 1.0}
                dummy_caster = copy.copy(caster)
                dummy_eff = copy.copy(buff)
                dummy_eff.modifiers = [m]
                dummy_eff.get_effective_modifiers = lambda m=m: [m]
                dummy_caster.effects = {"eff": dummy_eff}
                combat_math.handle_caster_buffs(dummy_caster, tgt, action_tags, act_fqn, attack_type, damage_type, test_buckets, test_mods, hand=hand)
                if test_buckets or any(test_mods[k] != 0.0 for k in ('bonus_crit_chance', 'bonus_crit_modifier', 'bonus_armor_pen', 'base_weapon_damage_modifier')):
                    applied_mods.append({
                        'source': f"Caster: {buff.name}",
                        'stat': str(m.stat),
                        'value': float(m.value),
                        'targets': list(getattr(m, 'targets', ())),
                        'buckets': test_buckets,
                        'mods': {k: v for k, v in test_mods.items() if v != 0.0 and k != 'total_multiplier'}
                    })

        # Trace target debuffs
        for debuff in tgt.effects.values():
            if getattr(debuff, "is_expired", False):
                continue
            getter = getattr(debuff, "get_effective_modifiers", None)
            eff_mods = getter() if getter is not None else getattr(debuff, "modifiers", [])
            for m in eff_mods or ():
                test_buckets = {}
                test_mods = {'bonus_crit_chance': 0.0, 'bonus_crit_modifier': 0.0, 'bonus_armor_pen': 0.0, 'base_weapon_damage_modifier': 0.0, 'total_multiplier': 1.0}
                dummy_tgt = copy.copy(tgt)
                dummy_eff = copy.copy(debuff)
                dummy_eff.modifiers = [m]
                dummy_eff.get_effective_modifiers = lambda m=m: [m]
                dummy_tgt.effects = {"eff": dummy_eff}
                combat_math.handle_target_debuffs(dummy_tgt, action_tags, act_fqn, attack_type, damage_type, test_buckets, test_mods, caster=caster)
                if test_buckets or any(test_mods[k] != 0.0 for k in ('bonus_crit_chance', 'bonus_crit_modifier', 'bonus_armor_pen', 'base_weapon_damage_modifier')):
                    applied_mods.append({
                        'source': f"Target: {debuff.name}",
                        'stat': str(m.stat),
                        'value': float(m.value),
                        'targets': list(getattr(m, 'targets', ())),
                        'buckets': test_buckets,
                        'mods': {k: v for k, v in test_mods.items() if v != 0.0 and k != 'total_multiplier'}
                    })

        res = orig_handle_modifiers(caster, tgt, action_data, damage_type)
        if target_stem in act_fqn:
            captured_hits.append({
                "action_data": copy.deepcopy(action_data),
                "modifiers": copy.deepcopy(res),
                "applied_mods": applied_mods,
                "resolved_damage_type": damage_type
            })
        return res

    combat_math.handle_modifiers = hooked_handle_modifiers

    # Execute 1 hit
    sim.run_timed(1.5)

    combat_math.handle_modifiers = orig_handle_modifiers

    if not captured_hits:
        captured_hits = [{
            "action_data": {},
            "modifiers": {},
            "applied_mods": [],
            "resolved_damage_type": 1
        }]

    # 4. Print Telemetry & Mathematical Breakdown
    print("\n" + "=" * 80)
    print("PLAYER RUNTIME STATS (DURING HIT)")
    print("=" * 80)
    base_m = player.base_stats.get("Mastery", mastery)
    eff_m = player.stats.get("Mastery", base_m)
    print(f"  Base Mastery           : {base_m:.1f}")
    print(f"  Effective Mastery      : {eff_m:.1f} (after passives & class buffs)")
    print(f"  Power                  : {player.stats.get('Power', power):.1f}")
    if player.stats.get('Tech_power', 0.0) > 0:
        print(f"  Tech Power             : {player.stats.get('Tech_power'):.1f}")
    crit_val = player.stats.get('Critical Rating') or player.stats.get('Critical_rating') or crit_rating
    print(f"  Critical Rating        : {crit_val:.1f}")
    print(f"  Melee Bonus Damage     : {player.stats.get('M_Bonus_Damage', 0.0):.3f}")
    print(f"  Ranged Bonus Damage    : {player.stats.get('R_Bonus_Damage', 0.0):.3f}")
    print(f"  Force Bonus Damage     : {player.stats.get('F_Bonus_Damage', 0.0):.3f}")
    print(f"  Tech Bonus Damage      : {player.stats.get('T_Bonus_Damage', 0.0):.3f}")
    print(f"  Base Armor Penetration : {player.stats.get('Armor Penetration', 0.0)*100.0:.2f}%")
    print(f"  Mainhand Weapon Damage : [{player.stats.get('Main_hand_min', 0.0):.1f} -- {player.stats.get('Main_hand_max', 0.0):.1f}]")
    if player.stats.get('Off_hand_max', 0.0) > 0:
        print(f"  Offhand Weapon Damage  : [{player.stats.get('Off_hand_min', 0.0):.1f} -- {player.stats.get('Off_hand_max', 0.0):.1f}]")
    print(f"  Standard Health        : {player.stats.get('Standard_health', 19335.0):.1f}")

    for idx, hit in enumerate(captured_hits, 1):
        act_data = hit.get("action_data", {})
        mods = hit.get("modifiers", {})
        applied_list = hit.get("applied_mods", [])
        damage_type = hit.get("resolved_damage_type", 1)

        print("\n" + "=" * 80)
        print(f"HIT #{idx} TELEMETRY: COMBAT MATH & MODIFIER TRACE")
        print("=" * 80)
        print(f"Action: {act_data.get('ability_fqn')}")
        print(f"Attack Type: {act_data.get('resolved_attack_type')} (1=Melee, 2=Ranged, 3=Force, 4=Tech)")
        print(f"Damage Type: {damage_type} (1=Kinetic, 2=Energy, 3=Internal, 4=Elemental)")
        print(f"Action Tags: {list(act_data.get('tags') or [])}")

        print("\n--- APPLIED MODIFIERS TO THIS HIT ---")
        if not applied_list:
            print("  (None matched)")
        for item in applied_list:
            details = []
            if item['buckets']:
                for bname, bval in item['buckets'].items():
                    details.append(f"Bucket '{bname}': +{bval*100:.1f}% ({bval})")
            if item['mods']:
                for mname, mval in item['mods'].items():
                    details.append(f"{mname}: {mval}")
            tgt_str = f" [targets: {item['targets']}]" if item['targets'] else ""
            print(f"  * {item['source']} -> {item['stat']} = {item['value']}{tgt_str} ==> {', '.join(details)}")

        print("\n[MODIFIERS DICT]")
        for k, v in mods.items():
            print(f"  {k}: {v}")

        # Step-by-step formula breakdown
        coeff = act_data.get("coeff", 0.0)
        amp = act_data.get("amp", 0.0)
        shp_min = act_data.get("shp_min", 0.0)
        shp_max = act_data.get("shp_max", 0.0)
        standard_health = player.stats.get("Standard_health", 19335.0)
        attack_type = act_data.get("resolved_attack_type", 1)

        if attack_type == 1:
            bonus_dmg = player.stats.get("M_Bonus_Damage", 0.0)
        elif attack_type == 2:
            bonus_dmg = player.stats.get("R_Bonus_Damage", 0.0)
        elif attack_type == 3:
            bonus_dmg = player.stats.get("F_Bonus_Damage", 0.0)
        else:
            bonus_dmg = player.stats.get("T_Bonus_Damage", 0.0)

        weapon_mod = mods.get("base_weapon_damage_modifier", 0.0)
        weapon_mult = max(0.0, 1.0 + weapon_mod)
        w_min = player.stats.get("Main_hand_min", 0.0) * weapon_mult
        w_max = player.stats.get("Main_hand_max", 0.0) * weapon_mult

        print("\n[FORMULA BREAKDOWN]")
        print(f"  Bonus Damage ({'Melee' if attack_type==1 else 'Force/Tech/Ranged'}): {bonus_dmg:.3f}")
        print(f"  Standard Health: {standard_health:.1f}")
        if attack_type in (1, 2):
            print(f"  Weapon Scaled Range (mult={weapon_mult:.2f}x): [{w_min:.2f} -- {w_max:.2f}]")
            raw_min = ((amp + 1.0) * w_min) + (coeff * bonus_dmg) + (shp_min * standard_health)
            raw_max = ((amp + 1.0) * w_max) + (coeff * bonus_dmg) + (shp_max * standard_health)
        else:
            raw_min = (coeff * bonus_dmg) + (shp_min * standard_health)
            raw_max = (coeff * bonus_dmg) + (shp_max * standard_health)

        print(f"  Raw Base Damage: [{raw_min:.2f} -- {raw_max:.2f}]")

        post_mit_min = combat_math.handle_mitigation(player, target, raw_min, damage_type, mods)
        post_mit_max = combat_math.handle_mitigation(player, target, raw_max, damage_type, mods)
        armor_factor = post_mit_min / raw_min if raw_min > 0 else 1.0

        print(f"  Post-Mitigation Base (factor={armor_factor:.6f}): [{post_mit_min:.2f} -- {post_mit_max:.2f}]")
        unbucketed_mods = combat_math_unbucketed.handle_modifiers(player, target, act_data, damage_type=damage_type)
        unbucketed_mult = unbucketed_mods.get("total_multiplier", 1.0)
        legacy_mult = mods.get("total_multiplier", 1.0)

        print(f"  Legacy Multiplier      : {legacy_mult:.6f}x")
        print(f"  Verified Multiplier    : {unbucketed_mult:.6f}x (from combat_math_unbucketed)")

        if surge_arg is not None:
            actual_surge = surge_arg
        else:
            total_crit_mod = player.stats.get("Critical Modifier", 0.5) + mods.get("bonus_crit_modifier", 0.0)
            actual_surge = 1.0 + total_crit_mod

        # Expected Non-Crit & Crit
        unbucketed_nc_min = post_mit_min * unbucketed_mult
        unbucketed_nc_max = post_mit_max * unbucketed_mult
        unbucketed_c_min = unbucketed_nc_min * actual_surge
        unbucketed_c_max = unbucketed_nc_max * actual_surge

        legacy_nc_min = post_mit_min * legacy_mult
        legacy_nc_max = post_mit_max * legacy_mult
        legacy_c_min = legacy_nc_min * actual_surge
        legacy_c_max = legacy_nc_max * actual_surge

        print("\n" + "=" * 80)
        print(f"EXPECTED HIT RANGES (HIT #{idx})")
        print("=" * 80)
        print(f"--- [A] VERIFIED EMPIRICAL MODEL (combat_math_unbucketed) ---")
        print(f"  NON-CRIT RANGE : [{unbucketed_nc_min:.2f} -- {unbucketed_nc_max:.2f}]  ==>  INTEGER: {int(unbucketed_nc_min)} -- {int(unbucketed_nc_max)}")
        print(f"  CRIT RANGE     : [{unbucketed_c_min:.2f} -- {unbucketed_c_max:.2f}]  ==>  INTEGER: {int(unbucketed_c_min)} -- {int(unbucketed_c_max)}  (Surge: {actual_surge:.6f}x)")

        if abs(unbucketed_mult - legacy_mult) > 1e-6:
            print(f"\n--- [B] LEGACY / ALTERNATIVE MODEL (combat_math) ---")
            print(f"  NON-CRIT RANGE : [{legacy_nc_min:.2f} -- {legacy_nc_max:.2f}]  ==>  INTEGER: {int(legacy_nc_min)} -- {int(legacy_nc_max)}")
            print(f"  CRIT RANGE     : [{legacy_c_min:.2f} -- {legacy_c_max:.2f}]  ==>  INTEGER: {int(legacy_c_min)} -- {int(legacy_c_max)}  (Surge: {actual_surge:.6f}x)")
        print("=" * 80)


def main():
    parser = argparse.ArgumentParser(description="Inspect Hit Modifiers & Combat Math for any ability/class.")
    parser.add_argument("--discipline", type=str, help="Discipline identifier, e.g. 'juggernaut/vengeance' or 'carnage'")
    parser.add_argument("--ability", type=str, required=True, help="Ability FQN or stem, e.g. 'abl.sith_warrior.vicious_slash'")
    parser.add_argument("--config", type=str, help="Path to run_config JSON file")
    parser.add_argument("--mastery", type=float, default=16570.0, help="Base mastery (default: 16570)")
    parser.add_argument("--power", type=float, default=13290.0, help="Power (default: 13290)")
    parser.add_argument("--tech-power", type=float, default=0.0, help="Tech power (default: 0)")
    parser.add_argument("--force-power", type=float, default=9332.0, help="Force power (default: 9332)")
    parser.add_argument("--crit", type=float, default=3705.0, help="Critical rating (default: 3705)")
    parser.add_argument("--surge", type=float, default=None, help="Explicit total surge multiplier, e.g. 1.653618")
    parser.add_argument("--weapon-min", type=float, default=2094.0, help="Mainhand min weapon damage (default: 2094)")
    parser.add_argument("--weapon-max", type=float, default=3141.0, help="Mainhand max weapon damage (default: 3141)")
    parser.add_argument("--offhand-min", type=float, default=0.0, help="Offhand min weapon damage (default: 0)")
    parser.add_argument("--offhand-max", type=float, default=0.0, help="Offhand max weapon damage (default: 0)")
    parser.add_argument("--no-debuffs", action="store_true", help="Disable training dummy debuff module")
    parser.add_argument("--dummy-hp", type=int, default=6500000, help="Dummy HP (default: 6500000)")
    parser.add_argument("--burning", action="store_true", help="Apply Burning debuff to dummy")
    parser.add_argument("--bleeding", action="store_true", help="Apply Bleeding debuff to dummy")
    parser.add_argument("--poisoned", action="store_true", help="Apply Poisoned debuff to dummy")

    args = parser.parse_args()

    disc_path = None
    if args.discipline:
        disc_path = find_discipline_file(args.discipline)

    cfg_path = Path(args.config) if args.config else None

    if not disc_path and not cfg_path:
        parser.error("Either --discipline or --config must be provided.")

    inspect_hit(
        discipline_path=disc_path,
        run_config_path=cfg_path,
        ability_fqn=args.ability,
        mastery=args.mastery,
        power=args.power,
        tech_power=args.tech_power,
        force_power=args.force_power,
        crit_rating=args.crit,
        surge_arg=args.surge,
        weapon_min=args.weapon_min,
        weapon_max=args.weapon_max,
        offhand_min=args.offhand_min,
        offhand_max=args.offhand_max,
        debuff_module=not args.no_debuffs,
        dummy_hp=args.dummy_hp,
        burning=args.burning,
        bleeding=args.bleeding,
        poisoned=args.poisoned,
    )


if __name__ == "__main__":
    main()