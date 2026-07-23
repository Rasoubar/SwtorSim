
class Metrics:
    def __init__(self):
        self.total_damage = 0.0
        self.breakdown = {}
        self.total_execute_damage = 0.0
        self.execute_breakdown = {}
        self.execute_start_time = None

    def log_damage(self, ability_name: str, dmg_value: float, is_crit: bool, target, current_time: float):
        """Called on every hit, logs the damage and what caused it"""
        self.total_damage += dmg_value
        self._record_hit(self.breakdown, ability_name, dmg_value, is_crit)

        # Sub 30% phase
        if target and getattr(target, 'hp_ratio', 1.0) <= 0.30:
            if self.execute_start_time is None:
                self.execute_start_time = current_time

            self.total_execute_damage += dmg_value
            self._record_hit(self.execute_breakdown, ability_name, dmg_value, is_crit)

    @staticmethod
    def _record_hit(target_dict: dict, ability_name: str, dmg_value: float, is_crit: bool):
        """Helper to update damage metrics for a breakdown dictionary"""
        if ability_name not in target_dict:
            target_dict[ability_name] = {"total_damage": 0.0, "hit_count": 0, "crit_count": 0}

        target_dict[ability_name]["total_damage"] += dmg_value
        target_dict[ability_name]["hit_count"] += 1
        if is_crit:
            target_dict[ability_name]["crit_count"] += 1

    def print_metrics(self, duration):
        """Prints the metrics logged data"""
        total_dps = self.total_damage / duration
        print("Run Damage Stats")
        print(f"Duration: {duration:,.1f}s")
        print(f'Total Damage: {self.total_damage:,.0f}')
        print(f"DPS: {total_dps:,.1f}")
        print("=" * 60)

        sorted_abilities = sorted(self.breakdown.items(), key=lambda item: item[1]["total_damage"], reverse=True)
        print_ability_breakdown(duration, sorted_abilities)

        if self.total_execute_damage > 0:
            execute_duration = duration-self.execute_start_time
            print("\n" + "=" * 60)
            print(f"EXECUTE PHASE (<30% HP) - DPS: {self.total_execute_damage/execute_duration:,.0f}, Duration: {execute_duration:,.1f}s")
            sorted_exec = sorted(self.execute_breakdown.items(), key=lambda item: item[1]["total_damage"], reverse=True)
            print_ability_breakdown(execute_duration, sorted_exec)

        print("=" * 60)


def print_ability_breakdown(duration, sorted_abilities):
    """Prints the breakdown of damage/crit per ability"""
    print(f"{'Ability Name':<25} | {'DPS':<10} | {'Hits':<5} | {'Crit %':<6}")
    print("-" * 60)

    for name, stats in sorted_abilities:
        crit_pct = (stats["crit_count"] / stats["hit_count"]) * 100 if stats["hit_count"] > 0 else 0
        print(
            f"{name:<25} | {stats['total_damage'] / duration:<10,.0f} | {stats['hit_count']:<5} | {crit_pct:<6.1f}%")

