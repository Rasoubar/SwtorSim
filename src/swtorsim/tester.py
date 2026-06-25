import copy
import random
from src.swtorsim.engine import Simulation
from src.swtorsim.entities import Player, Target
from src.swtorsim.events import ResourceTick, PlayerReady, PeriodicProcTick
from src.swtorsim.rotation import Rotation


class SingleTester:
    def __init__(self, rotation_config, stats_config, abilities_db, procs_db, buffs_db):
        self.rotation_config = rotation_config
        self.stats_config = stats_config
        self.abilities_db = abilities_db
        self.procs_db = procs_db
        self.buffs_db = buffs_db

    def run_test(self, duration=300.0, dummy_hp=10000000):
        print(f"--- Starting Single Test Run ({duration}s) ---")

        # Deepcopy to prevent polluting your main databases
        abilities_copy = copy.deepcopy(self.abilities_db)
        sim = Simulation(abilities_copy)

        player = Player(self.stats_config.get("class_name", "Unknown"))
        target = Target("Target Dummy", hp=dummy_hp)
        # Load Stats
        p_stats = player.base_stats
        for stat_key, stat_value in self.stats_config.get("stats", {}).items():
            p_stats[stat_key] = stat_value

        player.procs = copy.deepcopy(self.procs_db)
        player.effects = copy.deepcopy(self.buffs_db)
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

        player.rotation = Rotation(name="Custom Profile Loop", steps_config=self.rotation_config, loop=True)
        print(player.stats)
        print(player.effects)
        print(player.procs)
        sim.schedule_absolute(0.0, PlayerReady(player, target))
        first_regen_tick = random.uniform(0.0, 1.0)
        sim.schedule_absolute(first_regen_tick, ResourceTick(player))

        for proc in player.procs.values():
            if getattr(proc, 'trigger', None) == "periodic":
                is_affected = getattr(proc, 'affected_by_cdr', False)
                interval = player.scale_time_modifier(proc.icd) if is_affected else proc.icd
                first_tick = random.uniform(0.0,interval)
                sim.schedule_absolute(first_tick, PeriodicProcTick(player, target, proc))

            # Execute run (all engine debug prints will output normally here)
        sim.run_timed(duration=duration, target=target)

        # Calculate and display results
        elapsed_time = sim.current_time if sim.current_time > 0 else 1.0
        calculated_dps = sim.tracker.total_damage / elapsed_time

        print("\n" + "=" * 55)
        print(f"  SINGLE TEST REPORT")
        print("=" * 55)
        print(f"Elapsed Time : {elapsed_time:.1f}s")
        print(f"Total Damage : {sim.tracker.total_damage:,.0f}")
        print(f"Final DPS    : {calculated_dps:,.1f}")
        print("=" * 55)
        print(f"{'Ability Name':<25} | {'Damage':<12} | {'DPS':<8}")
        print("-" * 55)

        for name, data in sorted(sim.tracker.breakdown.items(), key=lambda item: item[1]["total_damage"], reverse=True):
            dmg = data["total_damage"]
            dps = dmg / elapsed_time
            print(f"{name:<25} | {dmg:<12,.0f} | {dps:<8,.1f}")

            # 🟢 NEW: Calculate and print True Phase DPS
        if getattr(sim.tracker, 'total_execute_damage', 0) > 0 and getattr(sim.tracker, 'execute_start_time',
                                                                               None) is not None:
            # Calculate how many seconds the execute phase lasted
            execute_duration = elapsed_time - sim.tracker.execute_start_time
            execute_duration = max(execute_duration, 1.0)  # Prevent division by zero

            phase_dps = sim.tracker.total_execute_damage / execute_duration

            print("\n" + "=" * 55)
            print(f"  EXECUTE PHASE (<30% HP)")
            print(f"  Phase Duration : {execute_duration:.1f}s")
            print(f"  Phase DPS      : {phase_dps:,.1f}")
            print("-" * 55)

            for name, data in sorted(sim.tracker.execute_breakdown.items(),
                                         key=lambda item: item[1]["total_damage"], reverse=True):
                dmg = data["total_damage"]
                dps = dmg / execute_duration  # 🟢 DPS is now relative to the phase duration
                print(f"{name:<25} | {dmg:<12,.0f} | {dps:<8,.1f}")

        print("=" * 55 + "\n")
        print("=" * 55 + "\n")

        return calculated_dps