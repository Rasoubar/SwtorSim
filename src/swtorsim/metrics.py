"""Combat telemetry tracker for damage breakdowns, execute-phase splits, and buff/debuff uptime."""

import re

ATTACK_TYPE_NAMES = {
    1: "Melee",
    2: "Ranged",
    3: "Force",
    4: "Tech",
}

DAMAGE_TYPE_NAMES = {
    1: "Kinetic",
    2: "Energy",
    3: "Elemental",
    4: "Internal",
}


def format_type_descriptor(attack_types, damage_types) -> str:
    """Formats attack and damage types into a human-readable string like 'Melee / Energy'."""
    at_str = "/".join(ATTACK_TYPE_NAMES.get(a, str(a)) for a in sorted(attack_types)) if attack_types else "Unknown"
    dt_str = "/".join(DAMAGE_TYPE_NAMES.get(d, str(d)) for d in sorted(damage_types)) if damage_types else "Unknown"
    return f"{at_str} / {dt_str}"


_UNNAMED_EFFECT_SUFFIX_RE = re.compile(r"_\d+$")


def has_proper_effect_name(name: str) -> bool:
    """Returns True if the effect has a proper display name (does not end with _x or use a raw FQN fallback)."""
    if not name or not isinstance(name, str):
        return False
    stripped = name.strip()
    if not stripped:
        return False
    if _UNNAMED_EFFECT_SUFFIX_RE.search(stripped):
        return False
    if stripped.startswith(("abl.", "tal.")):
        return False
    return True


class Metrics:
    """Accumulates per-ability damage, critical hit counts, execute phase stats, and effect uptimes."""

    def __init__(self):
        self.total_damage = 0.0
        self.breakdown = {}
        self.total_execute_damage = 0.0
        self.execute_breakdown = {}
        self.execute_start_time = None
        self.active_effects = {}
        self.effect_history = {}
        self.seed = None
        self.stall_events = []
        self._active_stall = None
        self.total_stalled_time = 0.0
        self.permanent_stall = False

    def log_rotation_stall_start(
        self,
        timestamp: float,
        seed: int | None,
        step_index: int,
        step_info: str,
        resource_current: float | None = None,
    ):
        """Records the beginning of an idle rotation stall (player ready to act off-GCD, but rotation cannot cast)."""
        if self._active_stall is None:
            self._active_stall = {
                "start": timestamp,
                "seed": seed,
                "step_index": step_index,
                "step_info": step_info,
                "resource": resource_current,
            }

    def log_rotation_stall_end(self, timestamp: float):
        """Records the resolution of a rotation stall once an action is cast."""
        if self._active_stall is not None:
            duration = max(0.0, timestamp - self._active_stall["start"])
            self.total_stalled_time += duration
            self.stall_events.append({
                **self._active_stall,
                "end": timestamp,
                "duration": duration,
                "recovered": True,
            })
            self._active_stall = None

    def finalize_stalls(self, current_time: float):
        """Closes any open stall window at fight completion, marking permanent deadlocks if unrecovered."""
        if self._active_stall is not None:
            end_time = round(current_time, 4)
            duration = round(max(0.0, end_time - self._active_stall["start"]), 4)
            self.total_stalled_time = round(self.total_stalled_time + duration, 4)
            self.permanent_stall = True
            self.stall_events.append({
                **self._active_stall,
                "end": end_time,
                "duration": duration,
                "recovered": False,
            })
            self._active_stall = None

    def log_damage(
        self,
        ability_name: str,
        dmg_value: float,
        is_crit: bool,
        target,
        current_time: float,
        attack_type: int = None,
        damage_type: int = None,
    ):
        """Called on every hit, logs the damage and what caused it"""
        self.total_damage += dmg_value
        self._record_hit(self.breakdown, ability_name, dmg_value, is_crit, attack_type, damage_type)

        # Sub 30% phase
        if target and getattr(target, 'hp_ratio', 1.0) <= 0.30:
            if self.execute_start_time is None:
                self.execute_start_time = current_time

            self.total_execute_damage += dmg_value
            self._record_hit(self.execute_breakdown, ability_name, dmg_value, is_crit, attack_type, damage_type)

    @staticmethod
    def _record_hit(
        target_dict: dict,
        ability_name: str,
        dmg_value: float,
        is_crit: bool,
        attack_type: int = None,
        damage_type: int = None,
    ):
        """Helper to update damage metrics for a breakdown dictionary"""
        if ability_name not in target_dict:
            target_dict[ability_name] = {
                "total_damage": 0.0,
                "hit_count": 0,
                "crit_count": 0,
                "attack_types": set(),
                "damage_types": set(),
            }

        target_dict[ability_name]["total_damage"] += dmg_value
        target_dict[ability_name]["hit_count"] += 1
        if is_crit:
            target_dict[ability_name]["crit_count"] += 1
        if attack_type is not None:
            target_dict[ability_name]["attack_types"].add(attack_type)
        if damage_type is not None:
            target_dict[ability_name]["damage_types"].add(damage_type)

    def log_effect_applied(
        self,
        entity_name: str,
        effect_key: str,
        current_time: float,
        stacks: int = 1,
        is_passive: bool = False,
    ):
        """Records the application or refresh/stack update of an effect."""
        if not has_proper_effect_name(effect_key):
            return
        key = (entity_name, effect_key)
        if key not in self.active_effects:
            self.active_effects[key] = {
                "start": current_time,
                "current_stacks": stacks,
                "max_stacks": stacks,
            }
        else:
            self.active_effects[key]["current_stacks"] = stacks
            self.active_effects[key]["max_stacks"] = max(
                self.active_effects[key]["max_stacks"], stacks
            )

    def log_effect_removed(self, entity_name: str, effect_key: str, current_time: float):
        """Records the removal or expiration of an active effect."""
        key = (entity_name, effect_key)
        if key in self.active_effects:
            entry = self.active_effects.pop(key)
            if key not in self.effect_history:
                self.effect_history[key] = []
            dur = max(0.0, current_time - entry["start"])
            self.effect_history[key].append({
                "start": entry["start"],
                "end": current_time,
                "duration": dur,
                "max_stacks": entry["max_stacks"],
            })

    def finalize_effects(self, current_time: float):
        """Closes any active effect windows at fight conclusion."""
        for key, entry in list(self.active_effects.items()):
            if key not in self.effect_history:
                self.effect_history[key] = []
            dur = max(0.0, current_time - entry["start"])
            self.effect_history[key].append({
                "start": entry["start"],
                "end": current_time,
                "duration": dur,
                "max_stacks": entry["max_stacks"],
            })
        self.active_effects.clear()

    def print_buff_breakdown(self, duration: float):
        """Prints a structured report of when each buff and debuff was active throughout the fight."""
        self.finalize_effects(duration)
        if not self.effect_history:
            return

        print("\n" + "=" * 90)
        print("BUFF & EFFECT ACTIVE WINDOWS")
        print("=" * 90)
        print(f"{'Effect Name':<28} | {'Entity':<14} | {'Uptime':<8} | {'Uptime %':<8} | {'Active Intervals'}")
        print("-" * 90)

        filtered = []
        for (entity, name), windows in self.effect_history.items():
            if not has_proper_effect_name(name):
                continue
            total_active = sum(w["duration"] for w in windows)
            pct = (total_active / duration) * 100 if duration > 0 else 0
            filtered.append(((entity, name), windows, total_active, pct))

        filtered.sort(key=lambda x: x[2], reverse=True)

        for (entity, name), windows, total_active, pct in filtered:
            intervals_str = ", ".join(
                f"[{w['start']:.2f}s-{w['end']:.2f}s" + (f" x{w['max_stacks']}" if w['max_stacks'] > 1 else "") + "]"
                for w in windows
            )
            print(f"{name:<28} | {entity:<14} | {total_active:6.1f}s | {pct:6.1f}%  | {intervals_str}")
        print("=" * 90)

    def print_metrics(self, duration, show_buffs: bool = False):
        """Prints the metrics logged data"""
        total_dps = self.total_damage / duration
        print("Run Damage Stats")
        print(f"Duration: {duration:,.1f}s")
        print(f'Total Damage: {self.total_damage:,.0f}')
        print(f"DPS: {total_dps:,.1f}")
        print("=" * 75)

        sorted_abilities = sorted(self.breakdown.items(), key=lambda item: item[1]["total_damage"], reverse=True)
        print_ability_breakdown(duration, sorted_abilities)

        if self.total_execute_damage > 0 and duration > self.execute_start_time:
            execute_duration = duration - self.execute_start_time
            print("\n" + "=" * 75)
            print(f"EXECUTE PHASE (<30% HP) - DPS: {self.total_execute_damage/execute_duration:,.0f}, Duration: {execute_duration:,.1f}s")
            sorted_exec = sorted(self.execute_breakdown.items(), key=lambda item: item[1]["total_damage"], reverse=True)
            print_ability_breakdown(execute_duration, sorted_exec)

        print("=" * 75)

        if show_buffs:
            self.print_buff_breakdown(duration)

        if self.stall_events:
            print("\n" + "=" * 75)
            status_tag = "[FAIL] ROTATION PERMANENT DEADLOCK" if self.permanent_stall else "[WARN] ROTATION STALLS DETECTED"
            print(f"{status_tag}")
            pct = (self.total_stalled_time / duration * 100.0) if duration > 0 else 0.0
            print(f"Total Stalled Time: {self.total_stalled_time:,.2f}s ({pct:.1f}% of fight)")
            print(f"Stall Count: {len(self.stall_events)}")
            if self.seed is not None:
                print(f"RNG Seed: {self.seed}")
            longest = max(self.stall_events, key=lambda s: s["duration"])
            print(f"Longest Stall: {longest['duration']:.2f}s (from {longest['start']:.2f}s to {longest['end']:.2f}s) on step #{longest['step_index']}: {longest['step_info']}")
            if self.permanent_stall:
                last_stall = self.stall_events[-1]
                print(f"Deadlock Detail: Stopped at {last_stall['start']:.2f}s on step #{last_stall['step_index']}: {last_stall['step_info']} (Resource: {last_stall['resource']})")
            print("=" * 75)


def print_ability_breakdown(duration, sorted_abilities):
    """Prints the breakdown of damage/crit per ability including attack and damage type"""
    print(f"{'Ability Name':<25} | {'Type':<18} | {'DPS':<10} | {'Hits':<5} | {'Crit %':<6}")
    print("-" * 75)

    for name, stats in sorted_abilities:
        crit_pct = (stats["crit_count"] / stats["hit_count"]) * 100 if stats["hit_count"] > 0 else 0
        type_desc = format_type_descriptor(stats.get("attack_types", ()), stats.get("damage_types", ()))
        print(
            f"{name:<25} | {type_desc:<18} | {stats['total_damage'] / duration:<10,.0f} | {stats['hit_count']:<5} | {crit_pct:<6.1f}%"
        )
