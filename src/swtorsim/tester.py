import sys
import os
import math
import time
import statistics
import matplotlib.pyplot as plt
from multiprocessing import Pool, cpu_count
from src.swtorsim.setup import prepare_simulation


def execute_single_worker_task(args):
    """Worker task that runs an isolated simulation run inside a parallel thread process."""
    run_id, duration, dummy_hp, rotation_config, stats_config, abilities_db, procs_db, buffs_db = args
    old_stdout = sys.stdout
    sys.stdout = open(os.devnull, 'w')

    try:
        sim, player, target = prepare_simulation(rotation_config, stats_config, abilities_db, procs_db, buffs_db, dummy_hp)
        sim.run_timed(duration, target)

        elapsed_time = sim.current_time if sim.current_time > 0 else 1.0
        calculated_dps = sim.tracker.total_damage / elapsed_time
        # 1. Standard Ability Breakdown Packaging
        ability_data_summary = {
            name: {
                "total_damage": data["total_damage"],
                "hit_count": data["hit_count"]
            }
            for name, data in sim.tracker.breakdown.items()
        }

        # 2. 🟢 Isolated Execute Phase Breakdown Packaging
        execute_data_summary = {
            name: {
                "total_damage": data["total_damage"],
                "hit_count": data["hit_count"]
            }
            for name, data in getattr(sim.tracker, 'execute_breakdown', {}).items()
        }

        # 🟢 Calculate isolated phase duration for this specific run
        execute_start = getattr(sim.tracker, 'execute_start_time', None)
        execute_dur = (elapsed_time - execute_start) if execute_start is not None else 0.0

        return {
            "dps": calculated_dps,
            "elapsed": elapsed_time,
            "abilities": ability_data_summary,
            "total_execute_damage": getattr(sim.tracker, 'total_execute_damage', 0.0),
            "execute_duration": execute_dur,
            "execute_abilities": execute_data_summary
        }
    finally:
        sys.stdout.close()
        sys.stdout = old_stdout

class Tester:
    def __init__(self, rotation_config, stats_config, abilities_db, procs_db, buffs_db, duration, dummy_hp):
        self.rotation_config = rotation_config
        self.stats_config = stats_config
        self.abilities_db = abilities_db
        self.procs_db = procs_db
        self.buffs_db = buffs_db
        self.duration = duration
        self.dummy_hp = dummy_hp

    def run_test(self):
        print(f"--- Starting Single Test Run ({self.duration}s) ---")

        # Deepcopy to prevent polluting your main databases
        sim, player, target = prepare_simulation(self.rotation_config, self.stats_config, self.abilities_db, self.procs_db, self.buffs_db, self.dummy_hp)

        print(player.stats)
        print(player.effects)
        print(player.procs)

        sim.run_timed(duration=self.duration, target=target)
        sim.tracker.print_metrics(sim.current_time)

    def run_monte_carlo(self, iterations=1000):

        harvested_results = self._run_parallel_tests(iterations)

        summary = self._aggregate_results(harvested_results)

        self.produce_monte_carlo_report(summary, iterations)

    def _run_parallel_tests(self, iterations):
        cores_available = cpu_count()
        print(f"Using {cores_available} CPU Cores")

        start_time = time.perf_counter()

        task_payloads = [
            (i, self.duration, self.dummy_hp, self.rotation_config, self.stats_config,
             self.abilities_db, self.procs_db, self.buffs_db)
            for i in range(iterations)
        ]

        chunk_packet_size = max(1, iterations // (cores_available * 4))

        with Pool(processes=cores_available) as pool:
            harvested_results = pool.map(execute_single_worker_task, task_payloads, chunksize=chunk_packet_size)

        print(f"Runs completed in {time.perf_counter() - start_time:.3f} seconds!")
        return harvested_results

    @staticmethod
    def _aggregate_results( harvested_results):
        """Processes raw payloads into combined stats and ability breakdowns."""
        all_dps = [r["dps"] for r in harvested_results]
        total_time = sum(r["elapsed"] for r in harvested_results)

        macro_breakdown = {}
        macro_exec_breakdown = {}
        total_exec_damage = 0.0
        total_exec_duration = 0.0

        for result in harvested_results:
            total_exec_damage += result.get("total_execute_damage", 0.0)
            total_exec_duration += result.get("execute_duration", 0.0)

            # Standard Pool Mapping
            for name, data in result["abilities"].items():
                if name not in macro_breakdown:
                    macro_breakdown[name] = {"total_damage": 0.0, "hit_count": 0}
                macro_breakdown[name]["total_damage"] += data["total_damage"]
                macro_breakdown[name]["hit_count"] += data["hit_count"]

            # Execute Pool Mapping
            for name, data in result.get("execute_abilities", {}).items():
                if name not in macro_exec_breakdown:
                    macro_exec_breakdown[name] = {"total_damage": 0.0, "hit_count": 0}
                macro_exec_breakdown[name]["total_damage"] += data["total_damage"]
                macro_exec_breakdown[name]["hit_count"] += data["hit_count"]

        # Summary Math
        avg_dps = sum(all_dps) / len(all_dps)
        summary = {
            "all_dps": all_dps,
            "avg_dps": avg_dps,
            "median_dps": statistics.median(all_dps),
            "min_dps": min(all_dps),
            "max_dps": max(all_dps),
            "std_dev": math.sqrt(sum((x - avg_dps) ** 2 for x in all_dps) / len(all_dps)),
            "total_time": total_time,
            "total_exec_damage": total_exec_damage,
            "total_exec_duration": total_exec_duration,
            "macro_breakdown": macro_breakdown,
            "macro_exec_breakdown": macro_exec_breakdown
        }
        return summary

    @staticmethod
    def produce_monte_carlo_report(summary, iterations):
        """Prints the final averaged summary and tables for the macro run using the aggregated summary data."""
        avg_dps = summary["avg_dps"]
        total_combat_time_accumulated = summary["total_time"]

        print("\n" + "=" * 65)
        print(f"  MONTE CARLO REPORT ({iterations} Fights)")
        print("=" * 65)
        print(f"Average Performance : {avg_dps:,.1f} DPS")
        print(f"Median Performance  : {summary['median_dps']:,.1f} DPS")
        print(f"Worst Performance   : {summary['min_dps']:,.1f} DPS")
        print(f"Best Performance    : {summary['max_dps']:,.1f} DPS")
        print(f"Standard Deviation  : ±{summary['std_dev']:,.1f} DPS")
        print("=" * 65)


        Tester.print_macro_phase_table(
            summary["macro_breakdown"],
            total_combat_time_accumulated,
            avg_dps,
            iterations
        )

        # 🟢 Beautiful, Dedicated Execute Phase Report Table
        total_execute_duration_accumulated = summary["total_exec_duration"]
        if total_execute_duration_accumulated > 0:
            total_execute_damage_accumulated = summary["total_exec_damage"]
            avg_execute_dps = total_execute_damage_accumulated / total_execute_duration_accumulated
            avg_execute_duration = total_execute_duration_accumulated / iterations

            print("=" * 65)
            print(f"  EXECUTE PHASE PERFORMANCE (<30% HP)")
            print("=" * 65)
            print(f"Avg Phase Duration  : {avg_execute_duration:.1f}s")
            print(f"True Phase DPS      : {avg_execute_dps:,.1f} DPS")
            print("=" * 65)

            Tester.print_macro_phase_table(
                summary["macro_exec_breakdown"],
                total_execute_duration_accumulated,
                avg_execute_dps,
                iterations
            )

            Tester._plot_dps_histogram(summary["all_dps"], avg_dps, summary["std_dev"], iterations)

    @staticmethod
    def _plot_dps_histogram(all_dps, avg_dps, std_dev, iterations):
        """Helper to render and save the Monte Carlo DPS distribution."""
        plt.figure(figsize=(10.0, 6.0))

        # Determine a dynamic number of bins based on iteration scale
        num_bins = max(10, min(50, iterations // 20))

        # Plot the histogram
        plt.hist(
            all_dps,
            bins=num_bins,
            color='#2ca02c',
            alpha=0.75,
            edgecolor='black',
            linewidth=0.6,
            label='DPS Distribution'
        )

        # Add a vertical line indicating the average DPS
        plt.axvline(avg_dps, color='red', linestyle='dashed', linewidth=1.5,
                    label=f'Avg DPS: {avg_dps:,.1f}')

        # Add shaded regions representing Standard Deviation bounds
        plt.axvspan(avg_dps - std_dev, avg_dps + std_dev, color='gray', alpha=0.15,
                    label=f'±1 Std Dev ({std_dev:,.1f} DPS)')

        # Customizing Titles & Labels
        plt.title(f'SWTOR Sim: Monte Carlo DPS Distribution ({iterations} Fights)', fontsize=14, fontweight='bold',
                  pad=15)
        plt.xlabel('Damage Per Second (DPS)', fontsize=12)
        plt.ylabel('Frequency (Frequency of Runs)', fontsize=12)
        plt.grid(axis='y', linestyle='--', alpha=0.5)
        plt.legend(loc='upper right')

        # Apply a clean layout
        plt.tight_layout()

        # Options: Save to disk, show interactively, or both
        output_filename = "dps_distribution_histogram.png"
        plt.savefig(output_filename, dpi=300)
        print(f"Histogram successfully generated and saved to: {output_filename}")

        plt.show()
        plt.close()

    @staticmethod
    def print_macro_phase_table(breakdown_data, total_duration, total_dps, iterations):
        """Helper to print a formatted ability damage table for a specific phase."""
        print(f"{'Ability Name':<25} | {'Phase DPS':<12} | {'Phase %':<8} | {'Avg Hits':<8}")
        print("-" * 65)

        sorted_abilities = sorted(breakdown_data.items(), key=lambda item: item[1]["total_damage"], reverse=True)

        for name, global_data in sorted_abilities:
            avg_ability_dps = global_data["total_damage"] / total_duration
            share_pct = (avg_ability_dps / total_dps) * 100 if total_dps > 0 else 0.0
            avg_hits = global_data["hit_count"] / iterations

            print(f"{name:<25} | {avg_ability_dps:<12,.1f} | {share_pct:>6.1f}% | {avg_hits:>8.1f}")
        print("=" * 65 + "\n")