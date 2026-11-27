"""Comprehensive combat trace collector for interactive visual debugging."""

from typing import Any, Dict, List, Optional
import copy


class CombatTracer:
    """Collects fine-grained simulation telemetry: initial loadouts, event timelines,

    rotation decisions, hit math formulas, buff lifecycles, and resource curves.
    """

    def __init__(self):
        self.initial_state: Dict[str, Any] = {}
        self.events: List[Dict[str, Any]] = []
        self.rotation_decisions: List[Dict[str, Any]] = []
        self.hit_math_records: List[Dict[str, Any]] = []
        self.proc_records: List[Dict[str, Any]] = []
        self.resource_samples: List[Dict[str, Any]] = []
        self.target_hp_samples: List[Dict[str, Any]] = []
        self.active_buff_windows: List[Dict[str, Any]] = []
        self._open_buffs: Dict[tuple, Dict[str, Any]] = {}
        self.summary: Dict[str, Any] = {}
        self._last_resource: Optional[float] = None
        self.time_offset: float = 0.0  # raw sim time of T0 (first damage); reported times are relative to it
        # Cause links (see debug/causes.py): every event gets an id and the id of the event that caused it.
        self._next_id: int = 1
        self._frames: List[Dict[str, Any]] = []  # causes currently being processed, innermost last
        self._aliases: Dict[int, Optional[int]] = {}  # a proc frame that fired nothing -> the cause it stood in for
        self._last_apply: Dict[str, int] = {}  # effect name -> id of the event that last applied or restacked it
        self._pending_decision: Optional[tuple] = None  # (event id, time) of the last rotation choice
        self._last_cast: Optional[Dict[str, Any]] = None
        self._last_hit: Optional[Dict[str, Any]] = None
        self._last_t: Optional[float] = None
        self._hit_by_context: Dict[int, tuple] = {}  # id(dispatch context) -> (context, id of the hit it belongs to)

    # -------------------------------------------------------------------------
    # Cause links
    # -------------------------------------------------------------------------

    def current_cause_id(self) -> Optional[int]:
        """The id of the event whose consequences are being processed now, or None."""
        for frame in reversed(self._frames):
            if frame["id"] is not None:
                return frame["id"]
        return None

    def note_parked_hit(self, context: Dict[str, Any]) -> None:
        """A hit just landed and its damage-dealt dispatch is held until its branch ends: remember which hit it is."""
        if self._last_hit is not None:
            self._hit_by_context[id(context)] = (context, self._last_hit["id"])  # keeping context alive keeps its id unique

    def begin_cause(self, inherited_id: Optional[int] = None, reserve: bool = False, trigger: Optional[str] = None,
                    context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Opens a cause frame. ``inherited_id``: an event scheduled by that cause resolves. ``reserve``: a proc about to
        run; its event is recorded afterwards with the reserved id. Neither: a cast, bound by ``record_cast_start``."""
        parent = self.current_cause_id()
        held = self._hit_by_context.get(id(context)) if context is not None else None
        if trigger in ("on_damage_dealt", "on_damage_taken") and held is not None:
            parent = held[1]  # a held dispatch, released when its branch ended: it belongs to that hit
        elif trigger == "on_damage_dealt" and self._last_hit is not None and self._last_hit["t"] == self._last_t:
            parent = self._last_hit["id"]  # dispatched at once: heard right after that hit landed
        frame = {"id": inherited_id, "parent": parent, "used": inherited_id is not None}
        if reserve:
            frame["id"] = self._next_id
            self._next_id += 1
        self._frames.append(frame)
        return frame

    def end_cause(self, frame: Dict[str, Any]) -> None:
        """Closes a frame (and any left open inside it). A reserved id nobody recorded stands for its parent."""
        while self._frames:
            top = self._frames.pop()
            if top is frame:
                break
        if frame["id"] is not None and not frame["used"]:
            self._aliases[frame["id"]] = frame["parent"]

    def _emit(self, event: Dict[str, Any], frame: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Appends an event with its id and cause. With ``frame`` (a proc), the event takes the frame's reserved id and the
        frame's parent as its cause."""
        if frame is not None:
            event["id"] = frame["id"]
            event["cause"] = frame["parent"]
            frame["used"] = True
        else:
            event["id"] = self._next_id
            self._next_id += 1
            event["cause"] = self.current_cause_id()
        self.events.append(event)
        self._last_t = event["t"]
        if event["type"] == "damage_hit":
            self._last_hit = event
        return event

    def record_initial_state(
        self,
        player,
        target,
        config=None,
        loadout_blueprints: Optional[Dict[str, Any]] = None,
        rotation_config: Optional[List[Dict[str, Any]]] = None,
    ):
        """Captures complete character state and everything loaded at start."""
        blueprints = loadout_blueprints or {}
        p_stats = getattr(player, "stats", {})
        p_base = getattr(player, "base_stats", {})

        # 1. Base & Derived Attributes
        stat_entries = []
        for k in sorted(set(list(p_stats.keys()) + list(p_base.keys()))):
            base_val = p_base.get(k)
            eff_val = p_stats.get(k, base_val)
            stat_entries.append({
                "stat": k,
                "base": base_val,
                "effective": eff_val,
            })

        gcd_val = player.calculate_gcd(1.5) if hasattr(player, "calculate_gcd") else 1.5

        crit_mod_raw = float(p_stats.get("Critical Modifier", 0.5))
        crit_mult_pct = round((1.0 + crit_mod_raw) * 100.0, 2)
        main_acc_raw = float(p_stats.get("Main Accuracy", p_stats.get("Accuracy", 1.0)))
        main_acc_pct = round(main_acc_raw * 100.0, 2)
        alac_raw = float(p_stats.get("Alacrity", 0.0))
        alac_pct = round(alac_raw * 100.0, 2)
        crit_chance_raw = float(p_stats.get("Critical Chance", 0.0))
        crit_chance_pct = round(crit_chance_raw * 100.0, 2)

        # Check permanent class buff crit bonuses (Coordination / Lucky Shots: +5% crit chance)
        coord_bonus = 0.0
        if hasattr(player, "effects"):
            for eff_name, eff in getattr(player, "effects", {}).items():
                if eff_name in ("Coordination", "Lucky Shots") and not getattr(eff, "is_expired", False):
                    coord_bonus += 0.05
                    break
        eff_crit_pct = round((crit_chance_raw + coord_bonus) * 100.0, 2)

        mastery_eff = float(p_stats.get("Mastery", p_base.get("Mastery", 0.0)))
        mastery_base = float(p_base.get("Mastery", 0.0))
        power_eff = float(p_stats.get("Power", p_base.get("Power", 0.0)))
        force_power = float(p_stats.get("Force Power", p_base.get("Force Power", 0.0)))
        tech_power = float(p_stats.get("Tech Power", p_base.get("Tech Power", 0.0)))
        crit_rtg = float(p_stats.get("Critical Rating", p_base.get("Critical Rating", 0.0)))
        alac_rtg = float(p_stats.get("Alacrity Rating", p_base.get("Alacrity Rating", 0.0)))
        acc_rtg = float(p_stats.get("Accuracy Rating", p_base.get("Accuracy Rating", 0.0)))
        armor_rtg = float(p_stats.get("STAT_rtg_armor", p_stats.get("Armor Rating", p_base.get("Armor Rating", 0.0))))

        derived = {
            "level": getattr(player, "level", 80),
            "gcd": round(gcd_val, 2),
            "mastery": round(mastery_eff, 1),
            "base_mastery": round(mastery_base, 1),
            "power": round(power_eff, 1),
            "force_power": round(force_power, 1),
            "tech_power": round(tech_power, 1),
            "crit_rating": round(crit_rtg, 1),
            "crit_chance": eff_crit_pct,
            "base_crit_chance": crit_chance_pct,
            "coord_bonus_pct": round(coord_bonus * 100.0, 2),
            "crit_multiplier": crit_mult_pct,
            "alacrity_rating": round(alac_rtg, 1),
            "alacrity_pct": alac_pct,
            "accuracy_rating": round(acc_rtg, 1),
            "accuracy_pct": main_acc_pct,
            "armor_rating": round(armor_rtg, 1),
            "damage_reduction": round(float(p_stats.get("stat_cbt_armor_damage_reduction_factor", 0.0)) * 100.0, 2),
            "bonus_damage_force": round(float(p_stats.get("F_Bonus_Damage", 0.0)), 1),
            "bonus_damage_melee": round(float(p_stats.get("M_Bonus_Damage", 0.0)), 1),
            "bonus_damage_tech": round(float(p_stats.get("T_Bonus_Damage", 0.0)), 1),
            "bonus_damage_ranged": round(float(p_stats.get("R_Bonus_Damage", 0.0)), 1),
            "weapon_range": f"{int(p_stats.get('Main_hand_min', p_base.get('Main_hand_min', 0)))} - {int(p_stats.get('Main_hand_max', p_base.get('Main_hand_max', 0)))}",
            "standard_health": int(p_stats.get("Standard_health", p_base.get("Standard_health", 19335))),
            "max_health": int(p_stats.get("stat_cbt_max_health", 0)),
        }

        # 2. Categorize all loaded blueprints (passives, gear, abilities)
        passives_list = []
        active_list = []

        tactical_fqn = getattr(config, "tactical_fqn", "") if config else ""
        legendary_fqns = set(getattr(config, "legendary_fqns", []) or []) if config else set()
        relic_fqns = set(getattr(config, "relic_fqns", []) or []) if config else set()

        for fqn, bp in sorted(blueprints.items(), key=lambda kv: str(kv[1].name or kv[0])):
            bp_name = str(getattr(bp, "name", None) or fqn).strip()
            bp_type = getattr(bp, "type", "passive")
            tags = list(getattr(bp, "tags", []) or [])

            # Determine source category
            if fqn == tactical_fqn or "itm.tactical" in fqn:
                origin = "Tactical"
            elif fqn in legendary_fqns or "itm.legendary" in fqn:
                origin = "Legendary Implant"
            elif fqn in relic_fqns or "itm.relic" in fqn:
                origin = "Relic"
            elif fqn.startswith("tal."):
                origin = "Talent / Skill Tree"
            elif bp_name in ("Mark of Power", "Unnatural Might", "Coordination", "Hunter's Boon"):
                origin = "Class Buff"
            else:
                origin = "Discipline Baseline"

            if bp_type == "active" and not fqn.startswith("tal."):
                act = getattr(bp, "activation", None) or {}
                act_type = act.get("type") if isinstance(act, dict) else None
                act_dur = float(act.get("duration", 0.0)) if isinstance(act, dict) else 0.0
                active_list.append({
                    "name": bp_name,
                    "fqn": fqn,
                    "origin": origin,
                    "cooldown": getattr(bp, "cooldown", 0.0),
                    "energy_cost": getattr(bp, "energy_cost", 0.0),
                    "cast_time": act_dur if act_type == "cast" else 0.0,
                    "channel_duration": act_dur if act_type == "channel" else 0.0,
                    "energy_type": getattr(bp, "energy_type", "Kinetic"),
                    "tags": tags,
                })
            else:
                # Passive details
                stat_changes = getattr(bp, "stat_changes", []) or []
                clean_changes = []
                for sc in stat_changes:
                    if isinstance(sc, dict):
                        clean_changes.append({
                            "stat": sc.get("stat"),
                            "value": sc.get("value"),
                            "is_percent": sc.get("is_percent", False),
                            "requires_tag": sc.get("requires_tag"),
                        })

                effects_info = []
                eff_dict = getattr(bp, "effects", {}) or {}
                eff_iter = eff_dict.values() if isinstance(eff_dict, dict) else eff_dict
                for eff in eff_iter:
                    eff_name = getattr(eff, "name", "")
                    eff_tags = list(getattr(eff, "tags", []) or [])
                    eff_branches = getattr(eff, "branches", []) or []
                    branch_count = len(eff_branches)
                    trigger_names = []
                    for b in eff_branches:
                        for tr in getattr(b, "triggers", []) or []:
                            tr_name = tr.get("trigger")
                            if tr_name:
                                trigger_names.append(tr_name)
                    effects_info.append({
                        "name": eff_name,
                        "tags": eff_tags,
                        "branch_count": branch_count,
                        "triggers": trigger_names,
                    })

                passives_list.append({
                    "name": bp_name,
                    "fqn": fqn,
                    "origin": origin,
                    "tags": tags,
                    "stat_changes": clean_changes,
                    "effects": effects_info,
                })

        # 3. Authoritative Proc Registry
        procs_list = []
        for proc_key, proc_meta in sorted(getattr(player, "proc_registry", {}).items()):
            procs_list.append({
                "name": proc_meta.get("name", proc_key),
                "source_name": proc_meta.get("source_name", ""),
                "source_fqn": proc_meta.get("source_fqn", ""),
                "icd": round(float(proc_meta.get("icd", 0.0)), 2),
                "kind": proc_meta.get("kind", ""),
            })

        # 3b. Tactical, Implants & Relics Extraction
        tactical_info = None
        if tactical_fqn:
            t_bp = blueprints.get(tactical_fqn)
            tactical_info = {
                "name": str(getattr(t_bp, "name", None) or tactical_fqn.split(".")[-1].replace("_", " ").title()),
                "fqn": tactical_fqn,
                "tags": list(getattr(t_bp, "tags", []) or []),
            }

        legendaries_info = []
        for leg_fqn in sorted(legendary_fqns):
            leg_bp = blueprints.get(leg_fqn)
            legendaries_info.append({
                "name": str(getattr(leg_bp, "name", None) or leg_fqn.split(".")[-1].replace("_", " ").title()),
                "fqn": leg_fqn,
                "tags": list(getattr(leg_bp, "tags", []) or []),
            })

        relics_info = []
        for rel_fqn in sorted(relic_fqns):
            rel_bp = blueprints.get(rel_fqn)
            relics_info.append({
                "name": str(getattr(rel_bp, "name", None) or rel_fqn.split(".")[-1].replace("_", " ").title()),
                "fqn": rel_fqn,
                "tags": list(getattr(rel_bp, "tags", []) or []),
            })

        # 3c. Skill Tree (Choices by Level)
        skill_tree_levels = []
        if config and hasattr(config, "spec_path") and config.spec_path:
            try:
                from src.swtorsim.config_load import load_json_file
                spec_data = load_json_file(config.spec_path)
                tree = spec_data.get("skill_tree", {})
                choices = {str(k): int(v) for k, v in (getattr(config, "choices", None) or {}).items()}
                for lvl in sorted(tree.keys(), key=lambda x: int(x)):
                    sel_idx = choices.get(str(lvl))
                    opt_list = []
                    for opt_idx, fqns in sorted(tree[lvl].items(), key=lambda kv: int(kv[0])):
                        first_fqn = fqns[0] if fqns else ""
                        bp = blueprints.get(first_fqn)
                        bp_name = getattr(bp, "name", None)
                        if not bp_name and first_fqn:
                            try:
                                from src.swtorsim.abilities import AbilityBlueprint
                                parts = first_fqn.split(".")
                                p = Path("data/extractor/live/parsed") / Path(*parts).with_suffix(".json")
                                if p.is_file():
                                    bp_name = AbilityBlueprint.from_file(p).name
                            except Exception:
                                pass
                        opt_list.append({
                            "idx": int(opt_idx),
                            "name": bp_name or first_fqn.split(".")[-1].replace("_", " ").title(),
                            "fqn": first_fqn,
                            "is_selected": (int(opt_idx) == sel_idx),
                        })
                    skill_tree_levels.append({
                        "level": lvl,
                        "selected_idx": sel_idx,
                        "options": opt_list,
                    })
            except Exception:
                pass

        # 3d. Rotation Steps Sequence
        rotation_sequence = []
        rotation_steps = (
            (rotation_config.get("sequence") or rotation_config.get("steps") or [])
            if isinstance(rotation_config, dict)
            else (rotation_config or [])
        )
        runner = getattr(player, "pre_combat", None)
        pre_combat_steps = [dict(s) for s in (getattr(runner, "steps", None) or [])]
        for i, step in enumerate(rotation_steps):
            st_type = step.get("type", "unknown")
            st_name = step.get("name", f"Step {i+1}")
            lead = step.get("lead_time") if "lead_time" in step else step.get("pre_cast_offset")
            pool = step.get("pool", [])
            cand_list = []
            if pool:
                for opt in pool:
                    a_id = opt.get("ability_id", "")
                    a_bp = blueprints.get(a_id)
                    n = getattr(a_bp, "name", None) or a_id.replace("_", " ").title()
                    cand_list.append({"name": n, "id": a_id, "rules": opt.get("rules", {})})
            elif "ability_id" in step:
                a_id = step.get("ability_id", "")
                a_bp = blueprints.get(a_id)
                n = getattr(a_bp, "name", None) or a_id.replace("_", " ").title()
                cand_list.append({"name": n, "id": a_id, "rules": step.get("rules", {})})

            rotation_sequence.append({
                "step_num": i + 1,
                "type": st_type,
                "name": st_name,
                "lead_time": lead,
                "candidates": cand_list,
            })

        # 4. Target Starting Debuffs
        target_debuffs = []
        for debuff_key, debuff in getattr(target, "effects", {}).items():
            mods_info = []
            for m in getattr(debuff, "modifiers", []):
                mods_info.append({
                    "stat": getattr(m, "stat", ""),
                    "value": getattr(m, "value", 0.0),
                    "is_percent": getattr(m, "is_percent", False),
                })
            target_debuffs.append({
                "name": debuff_key,
                "tags": list(getattr(debuff, "tags", []) or []),
                "modifiers": mods_info,
            })

        self.initial_state = {
            "character": {
                "name": getattr(player, "name", "Character"),
                "class_name": getattr(config, "class_name", "Unknown") if config else getattr(player, "name", "Unknown"),
                "spec": getattr(config, "spec", "") if config else "",
                "level": getattr(player, "level", 80),
                "environment": getattr(config, "environment", "live").upper() if config else "LIVE",
                "resource_type": type(getattr(player, "resource", None)).__name__ if getattr(player, "resource", None) else "ResourcePool",
                "max_resource": getattr(player.resource, "max_value", 100.0) if getattr(player, "resource", None) else 100.0,
            },
            "target": {
                "name": getattr(target, "name", "Target Dummy"),
                "max_hp": getattr(target, "max_hp", getattr(target, "hp", 0)),
                "starting_hp": getattr(target, "hp", 0),
                "initial_debuffs": target_debuffs,
            },
            "derived": derived,
            "stat_entries": stat_entries,
            "passives": passives_list,
            "active_abilities": active_list,
            "procs": procs_list,
            "tactical": tactical_info,
            "legendaries": legendaries_info,
            "relics": relics_info,
            "skill_tree": skill_tree_levels,
            "rotation": rotation_sequence,
            "pre_combat": pre_combat_steps,
            "rotation_steps": rotation_config or [],
        }

        # Initialize first resource sample
        if getattr(player, "resource", None) is not None:
            self.resource_samples.append({
                "t": 0.0,
                "v": round(float(player.resource.current), 1),
            })
            self._last_resource = float(player.resource.current)

        # Initialize target HP sample
        if getattr(target, "hp", None) is not None:
            self.target_hp_samples.append({
                "t": 0.0,
                "hp": int(target.hp),
                "pct": 100.0,
            })

    # -------------------------------------------------------------------------
    # Core Event Logging Hooks
    # -------------------------------------------------------------------------

    def record_cast_start(
        self,
        timestamp: float,
        caster_name: str,
        ability_name: str,
        ability_fqn: str,
        duration: float,
        is_channel: bool = False,
        target_name: str = "",
    ):
        """Records an ability activation (instant, cast bar start, or channel start)."""
        event_dict = {
            "t": round(timestamp, 4),
            "type": "cast_start",
            "caster": caster_name,
            "ability": ability_name,
            "fqn": ability_fqn,
            "duration": round(duration, 3),
            "is_channel": is_channel,
            "target": target_name,
        }
        event = self._emit(event_dict)
        frame = self._frames[-1] if self._frames else None
        if frame is not None and frame["id"] is None:
            frame["id"] = event["id"]  # this cast is now the cause of what it does
            frame["used"] = True
        if event["cause"] is None and self._pending_decision and self._pending_decision[1] == round(timestamp, 4) and self._pending_decision[2] == ability_name:
            event["cause"] = self._pending_decision[0]  # a rotation choice made this cast
        self._last_cast = event

    def record_cast_finish(self, timestamp: float, caster_name: str, ability_name: str):
        """Records the completion of an activation cast bar."""
        self._emit({
            "t": round(timestamp, 4),
            "type": "cast_finish",
            "caster": caster_name,
            "ability": ability_name,
        })

    def record_channel_tick(self, timestamp: float, caster_name: str, ability_name: str, tick: int):
        """Records a channel pulse tick."""
        self._emit({
            "t": round(timestamp, 4),
            "type": "channel_tick",
            "caster": caster_name,
            "ability": ability_name,
            "tick": tick,
        })

    def record_damage_hit(
        self,
        timestamp: float,
        ability_name: str,
        damage: int,
        is_crit: bool,
        target_name: str,
        target_hp_after: int,
        attack_type: str = "",
        damage_type: str = "",
        math_audit: Optional[Dict[str, Any]] = None,
    ):
        """Records a damage hit event and its detailed combat math audit."""
        hit_id = len(self.hit_math_records) + 1
        audit = math_audit or {}

        event_dict = {
            "t": round(timestamp, 4),
            "type": "damage_hit",
            "hit_id": hit_id,
            "ability": ability_name,
            "damage": int(damage),
            "is_crit": bool(is_crit),
            "target": target_name,
            "target_hp": int(target_hp_after),
            "attack_type": attack_type,
            "damage_type": damage_type,
            "math": audit,
        }
        self._emit(event_dict)
        # Buffs and debuffs that shaped this hit (from its audit): link each to the event that last applied it.
        shaped_by, seen = [], set()
        for src in audit.get("sources") or []:
            name = src.get("effect")
            applied = self._last_apply.get(name)
            if applied is not None and name not in seen:
                seen.add(name)
                shaped_by.append({"id": applied, "effect": name})
        event_dict["shaped_by"] = shaped_by
        self.hit_math_records.append(event_dict)

        # Update target HP time-series
        max_hp = self.initial_state.get("target", {}).get("max_hp", 1) or 1
        pct = max(0.0, round((target_hp_after / max_hp) * 100.0, 2))
        self.target_hp_samples.append({
            "t": round(timestamp, 4),
            "hp": int(target_hp_after),
            "pct": pct,
        })

    def record_miss(self, timestamp: float, ability_name: str, hand: str = "main", attack_type: Any = "", target_name: str = ""):
        """Records a hit that missed (the accuracy roll failed); see ``src/swtorsim/miss_log.py``."""
        self._emit({
            "t": round(timestamp, 4),
            "type": "miss",
            "ability": ability_name,
            "hand": hand,
            "attack_type": attack_type,
            "target": target_name,
        })

    def record_buff_applied(
        self,
        timestamp: float,
        entity_name: str,
        effect_name: str,
        stacks: int = 1,
        duration: float = 0.0,
        is_passive: bool = False,
    ):
        """Records buff/debuff application and begins a timeline window."""
        event = self._emit({
            "t": round(timestamp, 4),
            "type": "buff_apply",
            "entity": entity_name,
            "effect": effect_name,
            "stacks": stacks,
            "duration": round(duration, 3),
            "is_passive": is_passive,
        })
        self._last_apply[effect_name] = event["id"]

        key = (entity_name, effect_name)
        window = {
            "entity": entity_name,
            "name": effect_name,
            "start": round(timestamp, 4),
            "end": None,
            "max_stacks": stacks,
            "is_passive": is_passive,
            "id": event["id"],
            "cause": event["cause"],
        }
        self._open_buffs[key] = window
        self.active_buff_windows.append(window)

    def record_buff_refreshed(
        self,
        timestamp: float,
        entity_name: str,
        effect_name: str,
        stacks: int = 1,
        duration: float = 0.0,
    ):
        """Records buff refresh."""
        self._emit({
            "t": round(timestamp, 4),
            "type": "buff_refresh",
            "entity": entity_name,
            "effect": effect_name,
            "stacks": stacks,
            "duration": round(duration, 3),
        })
        key = (entity_name, effect_name)
        if key in self._open_buffs:
            self._open_buffs[key]["max_stacks"] = max(self._open_buffs[key]["max_stacks"], stacks)

    def record_buff_stacks_changed(
        self,
        timestamp: float,
        entity_name: str,
        effect_name: str,
        old_stacks: int,
        new_stacks: int,
    ):
        """Records buff stack modification."""
        self._emit({
            "t": round(timestamp, 4),
            "type": "buff_stack",
            "entity": entity_name,
            "effect": effect_name,
            "old_stacks": old_stacks,
            "new_stacks": new_stacks,
        })
        key = (entity_name, effect_name)
        if key in self._open_buffs:
            self._open_buffs[key]["max_stacks"] = max(self._open_buffs[key]["max_stacks"], new_stacks)

    def record_buff_expired(self, timestamp: float, entity_name: str, effect_name: str):
        """Records buff expiration and closes the timeline window."""
        event = self._emit({
            "t": round(timestamp, 4),
            "type": "buff_expire",
            "entity": entity_name,
            "effect": effect_name,
        })
        key = (entity_name, effect_name)
        if key in self._open_buffs:
            self._open_buffs[key]["end"] = round(timestamp, 4)
            self._open_buffs[key]["end_id"] = event["id"]  # what ended it (a proc that consumed it, or the clock running out)
            self._open_buffs[key]["end_cause"] = event["cause"]
            del self._open_buffs[key]

    def record_resource_change(
        self,
        timestamp: float,
        entity_name: str,
        resource_type: str,
        current: float,
        delta: float,
        reason: str,
    ):
        """Records a resource spend, gain, or passive regeneration tick."""
        t_round = round(timestamp, 4)
        c_round = round(current, 1)
        d_round = round(delta, 1)

        self._emit({
            "t": t_round,
            "type": "resource",
            "entity": entity_name,
            "resource": resource_type,
            "current": c_round,
            "delta": d_round,
            "reason": reason,
        })

        if self._last_resource != c_round:
            self.resource_samples.append({
                "t": t_round,
                "v": c_round,
            })
            self._last_resource = c_round

    def record_rotation_evaluation(
        self,
        timestamp: float,
        step_index: int,
        step_type: str,
        step_name: str,
        candidates: List[Dict[str, Any]],
        chosen_ability: Optional[str] = None,
        is_stall: bool = False,
    ):
        """Records complete priority evaluation tree for why abilities were accepted or rejected."""
        decision_id = len(self.rotation_decisions) + 1
        rec = {
            "id": decision_id,
            "t": round(timestamp, 4),
            "step_index": step_index,
            "step_type": step_type,
            "step_name": step_name,
            "candidates": candidates,
            "chosen": chosen_ability,
            "is_stall": is_stall,
        }
        self.rotation_decisions.append(rec)
        event = self._emit({
            "t": round(timestamp, 4),
            "type": "rotation_eval",
            "decision_id": decision_id,
            "step_name": step_name,
            "chosen": chosen_ability,
            "is_stall": is_stall,
            "candidates_count": len(candidates),
        })
        rec["node"] = event["id"]
        if chosen_ability:
            self._pending_decision = (event["id"], round(timestamp, 4), chosen_ability)
            # A priority block records its choice after the cast it started; an optional step before it.
            cast = self._last_cast
            if cast is not None and cast["t"] == round(timestamp, 4) and cast["cause"] is None and cast["ability"] == chosen_ability:
                cast["cause"] = event["id"]

    def record_proc_dispatch(
        self,
        timestamp: float,
        trigger_name: str,
        source_name: str,
        effect_name: str,
        passed: bool,
        reason: str,
        cause_frame: Optional[Dict[str, Any]] = None,
    ):
        """Records reactive trigger dispatch attempts and lockout states. ``cause_frame`` (passed by the generated
        trigger manager) is the frame the proc's branch ran under: the proc event takes its reserved id."""
        rec = {
            "t": round(timestamp, 4),
            "trigger": trigger_name,
            "source": source_name,
            "effect": effect_name,
            "passed": passed,
            "reason": reason,
        }
        self.proc_records.append(rec)
        if passed:
            self._emit({
                "t": round(timestamp, 4),
                "type": "proc_fire",
                "trigger": trigger_name,
                "source": source_name,
                "effect": effect_name,
            }, frame=cause_frame)
        if cause_frame is not None:
            self.end_cause(cause_frame)  # what the proc did is already recorded under its reserved id

    def record_stall(self, timestamp: float, duration: float, step_info: str):
        """Records an idle deadlock / stall window."""
        self._emit({
            "t": round(timestamp, 4),
            "type": "stall",
            "duration": round(duration, 3),
            "step_info": step_info,
        })

    def record_tactical_swap(self, timestamp: float, entity_name: str, from_fqn: str, to_fqn: str, new_name: str = ""):
        """Records an out-of-combat tactical swap performed by the pre-combat sequence."""
        self._emit({
            "t": round(timestamp, 4),
            "type": "tactical_swap",
            "caster": entity_name,
            "from": from_fqn,
            "to": to_fqn,
            "ability": f"Swap Tactical: {new_name or to_fqn}",
        })

    def finalize(self, current_time: float, metrics=None, pre_combat_end: float | None = None):
        """Closes any remaining open buff windows and compiles overall summary metrics."""
        end_time = round(current_time, 4)

        # Close any buffs still active at fight finish
        for window in self._open_buffs.values():
            if window.get("end") is None:
                window["end"] = end_time
        self._open_buffs.clear()

        # Build summary
        total_damage = getattr(metrics, "total_damage", 0.0) if metrics else sum(e.get("damage", 0) for e in self.hit_math_records)
        combat_start = getattr(metrics, "combat_start_time", None) if metrics else None
        if combat_start is not None:
            self.time_offset = float(combat_start)
        elif pre_combat_end is not None:
            self.time_offset = float(pre_combat_end)
        else:
            self.time_offset = 0.0
        duration = max(0.001, end_time - self.time_offset)
        dps = round(total_damage / duration, 1)

        crits = sum(1 for e in self.hit_math_records if e.get("is_crit"))
        total_hits = len(self.hit_math_records)
        crit_pct = round((crits / total_hits * 100.0), 1) if total_hits > 0 else 0.0

        misses = sum(1 for e in self.events if e.get("type") == "miss")
        casts_count = sum(1 for e in self.events if e.get("type") == "cast_start")
        apm = round((casts_count / duration) * 60.0, 1)

        total_stalled = getattr(metrics, "total_stalled_time", 0.0) if metrics else 0.0

        self.summary = {
            "duration": round(duration, 2),
            "total_damage": int(total_damage),
            "dps": dps,
            "total_hits": total_hits,
            "crits": crits,
            "crit_pct": crit_pct,
            "misses": misses,
            "miss_pct": round(misses / (misses + total_hits) * 100.0, 2) if (misses + total_hits) > 0 else 0.0,
            "casts_count": casts_count,
            "apm": apm,
            "total_stalled_time": round(total_stalled, 3),
            "stalls_count": len([e for e in self.events if e.get("type") == "stall"]),
            "combat_start_raw": round(self.time_offset, 4),
            "t_start": round(min([0.0] + [e["t"] - self.time_offset for e in self.events if "t" in e]), 4),
            "pre_combat_end": (
                round(pre_combat_end - self.time_offset, 4) if pre_combat_end is not None else None
            ),
            "tactical_swaps": [
                {"t": round(e["t"] - self.time_offset, 4), "from": e["from"], "to": e["to"]}
                for e in self.events if e.get("type") == "tactical_swap"
            ],
        }

    def _shifted(self, records: List[Dict[str, Any]], keys=("t",)) -> List[Dict[str, Any]]:
        """Copies records with time keys made relative to T0 (pre-combat times become negative)."""
        off = self.time_offset
        if not off:
            return records
        out = []
        for rec in records:
            r = dict(rec)
            for k in keys:
                if isinstance(r.get(k), (int, float)):
                    r[k] = round(r[k] - off, 4)
            out.append(r)
        return out

    def _resolved_events(self) -> List[Dict[str, Any]]:
        """The events with causes that point at an unrecorded proc frame moved to what that frame stood in for."""
        if not self._aliases:
            return self.events
        out = []
        for ev in self.events:
            cause = ev.get("cause")
            if cause in self._aliases:
                ev = dict(ev)
                while cause in self._aliases:
                    cause = self._aliases[cause]
                ev["cause"] = cause
            out.append(ev)
        return out

    def to_dict(self) -> Dict[str, Any]:
        """Serializes the complete trace; all times are relative to T0 (first damage)."""
        return {
            "initial_state": self.initial_state,
            "summary": self.summary,
            "events": self._shifted(self._resolved_events()),
            "rotation_decisions": self._shifted(self.rotation_decisions),
            "hit_math_records": self._shifted(self.hit_math_records),
            "proc_records": self._shifted(self.proc_records),
            "resource_samples": self._shifted(self.resource_samples),
            "target_hp_samples": self._shifted(self.target_hp_samples),
            "active_buff_windows": self._shifted(self.active_buff_windows, keys=("start", "end")),
        }
