class Metrics:
    def __init__(self):
        self.total_damage = 0.0
        self.breakdown = {}

        # 🟢 NEW: Separate buckets for execute phase (<30%)
        self.total_execute_damage = 0.0
        self.execute_breakdown = {}
        self.execute_start_time = None

    def log_damage(self, ability_name: str, dmg_value: float, is_crit: bool, target, current_time: float):
        # 1. Standard Logging
        self.total_damage += dmg_value

        if ability_name not in self.breakdown:
            self.breakdown[ability_name] = {"total_damage": 0.0, "hit_count": 0, "crit_count": 0}
        self.breakdown[ability_name]["total_damage"] += dmg_value
        self.breakdown[ability_name]["hit_count"] += 1
        if is_crit:
            self.breakdown[ability_name]["crit_count"] += 1

        # 2. Execute Phase Logging (<30% HP)
        if target and target.hp_ratio <= 0.30:
            # 🟢 Record the timestamp of the very first sub-30 hit
            if self.execute_start_time is None:
                self.execute_start_time = current_time

            self.total_execute_damage += dmg_value

            if ability_name not in self.execute_breakdown:
                self.execute_breakdown[ability_name] = {"total_damage": 0.0, "hit_count": 0, "crit_count": 0}
            self.execute_breakdown[ability_name]["total_damage"] += dmg_value
            self.execute_breakdown[ability_name]["hit_count"] += 1
            if is_crit:
                self.execute_breakdown[ability_name]["crit_count"] += 1

    def print_metrics(self, duration):
        total_dps = self.total_damage / duration
        print("Run Damage Stats")
        print(f'Total Damage: {self.total_damage:,.0f}')
        print(f"DPS: {total_dps:,.1f}")
        print("=" * 60)
        print(f"{'Ability Name':<25} | {'Damage':<10} | {'Hits':<5} | {'Crit %':<6}")
        print("-" * 60)

        sorted_abilities = sorted(self.breakdown.items(), key=lambda item: item[1]["total_damage"], reverse=True)

        for name, stats in sorted_abilities:
            crit_pct = (stats["crit_count"] / stats["hit_count"]) * 100 if stats["hit_count"] > 0 else 0
            print(f"{name:<25} | {stats['total_damage']:<10,.0f} | {stats['hit_count']:<5} | {crit_pct:<6.1f}%")

        # 🟢 NEW: Print Execute Phase specific metrics at the bottom
        if self.total_execute_damage > 0:
            execute_pct = (self.total_execute_damage / self.total_damage) * 100
            print("\n" + "=" * 60)
            print(f"EXECUTE PHASE (<30% HP) - Total: {self.total_execute_damage:,.0f} ({execute_pct:.1f}% of total)")
            print("-" * 60)

            sorted_exec = sorted(self.execute_breakdown.items(), key=lambda item: item[1]["total_damage"], reverse=True)
            for name, stats in sorted_exec:
                crit_pct = (stats["crit_count"] / stats["hit_count"]) * 100 if stats["hit_count"] > 0 else 0
                print(f"{name:<25} | {stats['total_damage']:<10,.0f} | {stats['hit_count']:<5} | {crit_pct:<6.1f}%")

        print("=" * 60)