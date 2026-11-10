"""Single-run and multiprocessing Monte Carlo simulation runner and report generator."""

import sys
import os
import math
import time
import statistics
from multiprocessing import Pool, cpu_count
from src.swtorsim.setup import prepare_simulation
from src.swtorsim.metrics import format_type_descriptor


class Tester:
    """Orchestrates single-fight verbose runs and multi-core Monte Carlo batch simulations."""

    def __init__(self, rotation_config, stats_config, loadout_blueprints, duration, dummy_hp, debuff_module, enable_stem_matching: bool = False, seed: int = 42):
        self.rotation_config = rotation_config
        self.stats_config = stats_config
        self.loadout_blueprints = loadout_blueprints
        self.duration = duration
        self.dummy_hp = dummy_hp
        self.debuff_module = debuff_module
        self.enable_stem_matching = enable_stem_matching
        self.seed = seed

    def run_test(self, show_buffs: bool = True, tracer=None, config=None):
        """Orchestrates a single simulation."""
        print(f"--- Starting Single Test Run ({self.duration}s) ---")
        sim, player, target = prepare_simulation(
            self.rotation_config,
            self.stats_config,
            self.loadout_blueprints,
            self.dummy_hp,
            self.debuff_module,
            seed=self.seed,
            tracer=tracer,
            config=config,
        )
        sim.run_timed(duration=self.duration, target=target)
        sim.tracker.print_metrics(sim.current_time, show_buffs=show_buffs)
        return sim, player, target

    def run_monte_carlo(self, iterations=1000):
        """Orchestrates monte carlo workflow."""
        harvested_results = self._run_parallel_tests(iterations)
        summary = self._aggregate_results(harvested_results)
        self.produce_monte_carlo_report(summary, iterations)

    def _run_parallel_tests(self, iterations):
        """Runs individual simulations in parallel."""
        cores_available = cpu_count()
        print(f"Using {cores_available} CPU Cores")
        start_time = time.perf_counter()

        task_payloads = [
            (i, self.duration, self.dummy_hp, self.rotation_config, self.stats_config,
             self.loadout_blueprints, self.debuff_module, self.enable_stem_matching, self.seed + i)
            for i in range(iterations)
        ]

        chunk_packet_size = max(1, iterations // (cores_available * 4))

        with Pool(processes=cores_available) as pool:
            harvested_results = pool.map(self.execute_single_worker_task, task_payloads, chunksize=chunk_packet_size)

        print(f"Runs completed in {time.perf_counter() - start_time:.3f} seconds!")
        return harvested_results

    @staticmethod
    def execute_single_worker_task(args):
        """Single simulation worker for monte carlo."""
        if len(args) == 9:
            run_id, duration, dummy_hp, rotation_config, stats_config, loadout_blueprints, debuff_module, enable_stem_matching, worker_seed = args
        else:
            run_id, duration, dummy_hp, rotation_config, stats_config, loadout_blueprints, debuff_module, enable_stem_matching = args
            worker_seed = 42 + run_id
        from src.swtorsim.settings import set_stem_matching
        set_stem_matching(enable_stem_matching)

        old_stdout = sys.stdout
        sys.stdout = open(os.devnull, 'w')

        try:
            sim, player, target = prepare_simulation(
                rotation_config, stats_config, loadout_blueprints, dummy_hp, debuff_module, verbose=False, seed=worker_seed
            )
            sim.run_timed(duration, target)

            combat_start = getattr(sim, "combat_start_time", None) or 0.0
            elapsed_time = max(0.0, sim.current_time - combat_start)
            calculated_dps = sim.tracker.total_damage / elapsed_time if elapsed_time > 0 else 0.0

            ability_data_summary = {
                name: {
                    "total_damage": data["total_damage"],
                    "hit_count": data["hit_count"],
                    "crit_count": data.get("crit_count", 0),
                    "attack_types": list(data.get("attack_types", ())),
                    "damage_types": list(data.get("damage_types", ())),
                }
                for name, data in sim.tracker.breakdown.items()
            }

            execute_data_summary = {
                name: {
                    "total_damage": data["total_damage"],
                    "hit_count": data["hit_count"],
                    "crit_count": data.get("crit_count", 0),
                    "attack_types": list(data.get("attack_types", ())),
                    "damage_types": list(data.get("damage_types", ())),
                }
                for name, data in getattr(sim.tracker, 'execute_breakdown', {}).items()
            }

            execute_start = getattr(sim.tracker, 'execute_start_time', None)
            execute_dur = (elapsed_time - execute_start) if execute_start is not None else 0.0

            return {
                "dps": calculated_dps,
                "elapsed": elapsed_time,
                "abilities": ability_data_summary,
                "total_execute_damage": getattr(sim.tracker, 'total_execute_damage', 0.0),
                "execute_duration": execute_dur,
                "execute_abilities": execute_data_summary,
                "stall_count": len(getattr(sim.tracker, 'stall_events', [])),
                "total_stalled_time": getattr(sim.tracker, 'total_stalled_time', 0.0),
                "permanent_stall": getattr(sim.tracker, 'permanent_stall', False),
                "seed": worker_seed,
                "stall_events": getattr(sim.tracker, 'stall_events', []),
            }
        finally:
            sys.stdout.close()
            sys.stdout = old_stdout

    @staticmethod
    def _aggregate_results(harvested_results):
        """Aggregates per-worker simulation results into macro DPS statistics and ability breakdowns."""
        all_dps = [r["dps"] for r in harvested_results]
        total_time = sum(r["elapsed"] for r in harvested_results)

        macro_breakdown = {}
        macro_exec_breakdown = {}
        total_exec_damage = 0.0
        total_exec_duration = 0.0

        for result in harvested_results:
            total_exec_damage += result.get("total_execute_damage", 0.0)
            total_exec_duration += result.get("execute_duration", 0.0)

            for name, data in result["abilities"].items():
                if name not in macro_breakdown:
                    macro_breakdown[name] = {
                        "total_damage": 0.0,
                        "hit_count": 0,
                        "crit_count": 0,
                        "attack_types": set(),
                        "damage_types": set(),
                    }
                macro_breakdown[name]["total_damage"] += data["total_damage"]
                macro_breakdown[name]["hit_count"] += data["hit_count"]
                macro_breakdown[name]["crit_count"] += data.get("crit_count", 0)
                macro_breakdown[name]["attack_types"].update(data.get("attack_types", ()))
                macro_breakdown[name]["damage_types"].update(data.get("damage_types", ()))

            for name, data in result.get("execute_abilities", {}).items():
                if name not in macro_exec_breakdown:
                    macro_exec_breakdown[name] = {
                        "total_damage": 0.0,
                        "hit_count": 0,
                        "crit_count": 0,
                        "attack_types": set(),
                        "damage_types": set(),
                    }
                macro_exec_breakdown[name]["total_damage"] += data["total_damage"]
                macro_exec_breakdown[name]["hit_count"] += data["hit_count"]
                macro_exec_breakdown[name]["crit_count"] += data.get("crit_count", 0)
                macro_exec_breakdown[name]["attack_types"].update(data.get("attack_types", ()))
                macro_exec_breakdown[name]["damage_types"].update(data.get("damage_types", ()))

        avg_dps = sum(all_dps) / len(all_dps)
        stalled_runs = [r for r in harvested_results if r.get("stall_count", 0) > 0]
        deadlocked_runs = [r for r in harvested_results if r.get("permanent_stall", False)]
        stalled_seeds = [r["seed"] for r in stalled_runs if r.get("seed") is not None]
        deadlocked_seeds = [r["seed"] for r in deadlocked_runs if r.get("seed") is not None]
        total_stalled_time_all = sum(float(r.get("total_stalled_time", 0.0)) for r in harvested_results)

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
            "macro_exec_breakdown": macro_exec_breakdown,
            "stalled_runs_count": len(stalled_runs),
            "deadlocked_runs_count": len(deadlocked_runs),
            "stalled_seeds": stalled_seeds,
            "deadlocked_seeds": deadlocked_seeds,
            "avg_stalled_time": total_stalled_time_all / len(harvested_results) if harvested_results else 0.0,
        }
        return summary

    @staticmethod
    def produce_monte_carlo_report(summary, iterations):
        """Prints the formatted Monte Carlo DPS summary, ability tables, and saves the DPS histogram."""
        avg_dps = summary["avg_dps"]
        total_combat_time_accumulated = summary["total_time"]

        print("\n" + "=" * 65)
        print(f"  MONTE CARLO REPORT ({iterations} Fights)")
        print("=" * 65)
        print(f"Average Performance : {avg_dps:,.1f} DPS")
        print(f"Median Performance  : {summary['median_dps']:,.1f} DPS")
        print(f"Worst Performance   : {summary['min_dps']:,.1f} DPS")
        print(f"Best Performance    : {summary['max_dps']:,.1f} DPS")
        print(f"Standard Deviation  : +/-{summary['std_dev']:,.1f} DPS")
        print("=" * 65)

        Tester.print_macro_phase_table(
            summary["macro_breakdown"],
            total_combat_time_accumulated,
            avg_dps,
            iterations
        )

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

        if summary.get("stalled_runs_count", 0) > 0:
            print("=" * 65)
            status_tag = (
                "[FAIL] ROTATION PERMANENT DEADLOCKS DETECTED"
                if summary.get("deadlocked_runs_count", 0) > 0
                else "[WARN] ROTATION STALLS DETECTED"
            )
            print(f"  {status_tag}")
            print("=" * 65)
            print(f"Stalled Runs        : {summary['stalled_runs_count']} / {iterations} ({summary['stalled_runs_count'] / iterations * 100:.1f}%)")
            print(f"Avg Stalled Time    : {summary['avg_stalled_time']:.2f}s per run")
            if summary.get("deadlocked_runs_count", 0) > 0:
                print(f"Deadlocked Runs     : {summary['deadlocked_runs_count']} / {iterations} ({summary['deadlocked_runs_count'] / iterations * 100:.1f}%)")
                print(f"Deadlocked Seeds    : {summary['deadlocked_seeds'][:10]}" + ("..." if len(summary['deadlocked_seeds']) > 10 else ""))
            print("=" * 65)

    @staticmethod
    def _plot_dps_histogram(all_dps, avg_dps, std_dev, iterations):
        """Renders and saves a matplotlib histogram of Monte Carlo DPS outcomes to ``figures/``."""
        try:
            import matplotlib.pyplot as plt
        except ImportError:
            print("[WARN] matplotlib is not installed. Skipping histogram image generation.")
            return

        plt.figure(figsize=(10.0, 6.0))
        plt.hist(
            all_dps,
            bins='auto',
            color='#2ca02c',
            alpha=0.75,
            edgecolor='black',
            linewidth=0.6,
            label='DPS Distribution'
        )
        plt.axvline(avg_dps, color='red', linestyle='dashed', linewidth=1.5,
                    label=f'Avg DPS: {avg_dps:,.1f}')
        plt.axvspan(avg_dps - std_dev, avg_dps + std_dev, color='gray', alpha=0.15,
                    label=f'+/-1 Std Dev ({std_dev:,.1f} DPS)')

        plt.title(f'SWTOR Sim: Monte Carlo DPS Distribution ({iterations} Fights)', fontsize=14, fontweight='bold', pad=15)
        plt.xlabel('Damage Per Second (DPS)', fontsize=12)
        plt.ylabel('Frequency (Frequency of Runs)', fontsize=12)
        plt.grid(axis='y', linestyle='--', alpha=0.5)
        plt.legend(loc='upper right')
        plt.tight_layout()

        os.makedirs("figures", exist_ok=True)
        output_filename = os.path.join("figures", "dps_distribution_histogram.png")
        plt.savefig(output_filename, dpi=300)
        print(f"Histogram successfully generated and saved to: {output_filename}")
        plt.close()

    @staticmethod
    def print_macro_phase_table(breakdown_data, total_duration, total_dps, iterations):
        """Prints a formatted per-ability DPS, damage share, hit count, and crit rate table."""
        print(f"{'Ability Name':<25} | {'Type':<18} | {'Phase DPS':<12} | {'Phase %':<8} | {'Avg Hits':<9} | {'Crit %':<7}")
        print("-" * 95)
        sorted_abilities = sorted(breakdown_data.items(), key=lambda item: item[1]["total_damage"], reverse=True)
        for name, global_data in sorted_abilities:
            avg_ability_dps = global_data["total_damage"] / total_duration
            share_pct = (avg_ability_dps / total_dps) * 100 if total_dps > 0 else 0.0
            avg_hits = global_data["hit_count"] / iterations
            crit_pct = (global_data.get("crit_count", 0) / global_data["hit_count"] * 100) if global_data["hit_count"] > 0 else 0.0
            type_desc = format_type_descriptor(global_data.get("attack_types", ()), global_data.get("damage_types", ()))
            print(f"{name:<25} | {type_desc:<18} | {avg_ability_dps:<12,.1f} | {share_pct:>6.1f}% | {avg_hits:>9.1f} | {crit_pct:>6.1f}%")
        print("=" * 95 + "\n")
