class Metrics:
    def __init__(self):
        self.total_damage= 0.0
        self.breakdown = {}

    def log_damage(self, ability_name: str, dmg_value: float, is_crit: bool):
        self.total_damage += dmg_value

        if ability_name not in self.breakdown:
            self.breakdown[ability_name] = {
                "total_damage": 0.0,
                "hit_count": 0,
                "crit_count": 0
            }
        self.breakdown[ability_name]["total_damage"] += dmg_value
        self.breakdown[ability_name]["hit_count"] += 1
        if is_crit:
            self.breakdown[ability_name]["crit_count"] += 1

    def print_metrics(self, duration):

        total_dps = self.total_damage / duration
        print("Run Damage Stats")
        print(f'Total Damage: {self.total_damage}')
        print(f"DPS: {total_dps:,.1f}")
        print("=" * 45)
        print(f"{'Ability Name':<25} | {'Damage':<10} | {'Hits':<5} | {'Crit %':<6}")
        print("-" * 45)

        sorted_abilities = sorted(self.breakdown.items(), key=lambda item:item[1]["total_damage"], reverse=True)

        for name, data in sorted_abilities:
            crit_pct = (data["crit_count"] / data["hit_count"] * 100) if data["hit_count"] > 0 else 0
            print(f"{name:<25} | {data['total_damage']:<10,.0f} | {data['hit_count']:<5} | {crit_pct:>4.1f}%")
        print("=" * 45 + "\n")