import sys
import os
import math
import copy
import time
import random
from multiprocessing import Pool, cpu_count
from src.swtorsim.engine import Simulation
from src.swtorsim.entities import Player, Target
from src.swtorsim.events import ResourceTick, PlayerReady, PeriodicProcTick
from src.swtorsim.rotation import Rotation


def execute_single_worker_task(args):
    run_id, duration, dummy_hp, rotation_config, stats_config, abilities_db, procs_db, buffs_db = args
    old_stdout = sys.stdout
    sys.stdout = open(os.devnull, 'w')

    try:
        abilities_copy = copy.deepcopy(abilities_db)
        sim = Simulation(abilities_copy)
        player = Player(stats_config.get("class_name", "Unknown"))
        target = Target("Target Dummy", hp=dummy_hp)
        p_stats = player.base_stats
        for stat_key, stat_value in stats_config.get("stats", {}).items():
            p_stats[stat_key] = stat_value
        player.procs = copy.deepcopy(procs_db)
        player.effects = copy.deepcopy(buffs_db)
        player.recalculate_stats()
        for effect_id, effect in player.effects.items():
            if effect.id == 64 and effect.required_tags is not None:
                for ability in sim.ability_db.values():
                    if hasattr(ability, "tags") and any(tag in ability.tags for tag in effect.required_tags):
                        ability.cooldown -= effect.value
            if effect.id == 422 and effect.required_tags is not None:
                for ability in sim.ability_db.values():
                    if hasattr(ability, "tags") and any(tag in ability.tags for tag in effect.required_tags):
                        ability.max_charges += effect.value
                        ability.charges += effect.value
        player.rotation = Rotation(name="Custom Profile Loop", steps_config=rotation_config, loop=True)
        sim.schedule_absolute(0.0, PlayerReady(player, target))
        first_regen_tick = random.uniform(0.0,1.0)
        sim.schedule_absolute(first_regen_tick, ResourceTick(player))
        for proc in player.procs.values():
            if getattr(proc, 'trigger', None) == "periodic":
                is_affected = getattr(proc, 'affected_by_cdr', False)
                interval = player.scale_time_modifier(proc.icd) if is_affected else proc.icd
                first_tick = random.uniform(0.0, interval)
                sim.schedule_absolute(first_tick, PeriodicProcTick(player, target, proc))
        sim.run_timed(duration=duration, target=target)

        elapsed_time = sim.current_time if sim.current_time > 0 else 1.0
        calculated_dps = sim.tracker.total_damage / elapsed_time

        ability_data_summary = {
            name: {
                "total_damage": data["total_damage"],
                "hit_count": data["hit_count"]
            }
            for name, data in sim.tracker.breakdown.items()
        }

        return {
            "dps": calculated_dps,
            "elapsed": elapsed_time,
            "abilities": ability_data_summary
        }
    finally:
        sys.stdout.close()
        sys.stdout = old_stdout


class ParallelBatchRunner:
    def __init__(self, rotation_config, stats_config, abilities_db, procs_db, buffs_db):
        self.rotation_config = rotation_config
        self.stats_config = stats_config
        self.abilities_db = abilities_db
        self.procs_db = procs_db
        self.buffs_db = buffs_db

    def run_monte_carlo(self, iterations=1000, duration=1000.0, dummy_hp=10000000):
        cores_available = cpu_count()
        print(f"Using {cores_available} CPU Cores")

        start_time = time.perf_counter()

        task_payloads = [
            (i, duration, dummy_hp, self.rotation_config, self.stats_config,
             self.abilities_db, self.procs_db, self.buffs_db)
            for i in range(iterations)
        ]

        chunk_packet_size = max(1, iterations // (cores_available * 4))

        with Pool(processes=cores_available) as pool:
            harvested_results = pool.map(execute_single_worker_task, task_payloads, chunksize=chunk_packet_size)

        print(f"Runs completed in {time.perf_counter() - start_time:.3f} seconds!")


        all_dps = [r["dps"] for r in harvested_results]
        total_combat_time_accumulated = sum(r["elapsed"] for r in harvested_results)
        macro_ability_breakdown = {}
        for result in harvested_results:
            for name, data in result["abilities"].items():
                if name not in macro_ability_breakdown:
                    macro_ability_breakdown[name] = {"total_damage": 0.0, "hit_count": 0}

                macro_ability_breakdown[name]["total_damage"] += data["total_damage"]
                macro_ability_breakdown[name]["hit_count"] += data["hit_count"]

        avg_dps = sum(all_dps) / len(all_dps)
        min_dps = min(all_dps)
        max_dps = max(all_dps)
        std_dev = math.sqrt(sum((x - avg_dps) ** 2 for x in all_dps) / len(all_dps))

        print("\n" + "=" * 65)
        print(f"  MONTE CARLO REPORT ({iterations} Fights)")
        print("=" * 65)
        print(f"Average Performance : {avg_dps:,.1f} DPS")
        print(f"Worst Performance   : {min_dps:,.1f} DPS")
        print(f"Best Performance    : {max_dps:,.1f} DPS")
        print(f"Standard Deviation  : ±{std_dev:,.1f} DPS")
        print("=" * 65)

        print(f"{'Ability Name':<25} | {'Avg Run DPS':<12} | {'Share %':<8} | {'Avg Hits':<8}")
        print("-" * 65)

        for name, global_data in sorted(macro_ability_breakdown.items(), key=lambda item: item[1]["total_damage"],
                                        reverse=True):
            avg_ability_dps = global_data["total_damage"] / total_combat_time_accumulated
            share_pct = (avg_ability_dps / avg_dps) * 100 if avg_dps > 0 else 0.0

            avg_hits = global_data["hit_count"] / iterations

            print(f"{name:<25} | {avg_ability_dps:<12,.1f} | {share_pct:>6.1f}% | {avg_hits:>8.1f}")
        print("=" * 65 + "\n")