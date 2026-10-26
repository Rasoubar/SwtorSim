# Simulator architecture

A fight is a priority queue of timestamped events. Time advances only when an event is popped. The player becomes ready, the rotation picks an ability, the cast spends resources and runs effects, and later events apply damage, ticks, regen, and expirations.

That loop is still the shape of the code in `engine.py`, `events.py`, `rotation.py`, and `resources.py`. Those three modules (`engine`, `rotation`, `resources`) are expected to stay through the rewrite.

What is changing is the data under a cast. The previous runtime loaded handwritten ability, proc, and permanent-effect JSON into flat action lists. The rewrite loads extracted ability and talent files. Each ability is a set of effects; each effect has branches with triggers, conditions, and actions. `AbilityBlueprint`, `Effect`, and `Branch` in `abilities.py` are the start of that model. `TriggerManager` in `triggers.py` is the start of subscribing those branches to combat events.

The two models currently sit side by side. `effects.py` is the old buff, debuff, DoT, and channel state. `effects_temp.py` and `modifiers.py` are the replacement being sketched. `setup.py` builds the player from blueprints, then still schedules the old opening events. Because of that mix, the simulator does not currently complete a fight. The rewrite checklist is in [rewrite.md](rewrite.md).

## Event loop

`Simulation.run_timed` pops events from a `heapq` ordered by timestamp and sequence id, sets `current_time`, and calls `event.resolve`. The loop ends when the queue is empty, the configured duration is reached, or the target's health is at or below zero.

`PlayerReady` asks `Rotation.evaluate` to run the current step (`FixedAbilityStep`, `PriorityBlockStep`, or `OptionalAbilityStep`). A successful cast advances the step and schedules the next `PlayerReady` at `max(current_time, player.next_gcd)`. A blocked step schedules another `PlayerReady` 0.1s later.

`Ability.cast` checks GCD, cost, cooldown, charges, and conditions, interrupts an active channel, spends resources, applies cooldown or charge use, and runs the ability's entry effects. `execute_single_action` dispatches the action dict. The handlers that exist today cover damage, resource gain, cooldown modification, charge restore, buff removal, and calling another effect. Stack modification is a no-op. DoT, channel, buff, and debuff application are still the old event classes (`DotTick`, `ChannelTickEvent`, `EffectExpire`) and are not dispatched from this path yet.

`DamageHit` runs `combat_math.calculate_hit` (modifiers, armor, crit) and either resolves immediately or schedules `ApplyDamageLand` after an impact delay. Landing the hit updates target health and `Metrics`.

Other recurring events still defined on the old loop:

| Event | Role |
| --- | --- |
| `DotTick` | Tick a DoT, then schedule the next tick or remove it |
| `ChannelTickEvent` | Tick a channel, spend the per-tick cost, then continue or queue `PlayerReady` |
| `PeriodicProcTick` | Run a periodic proc and schedule the next interval |
| `ResourceTick` | Passive regen, scaled by Alacrity |
| `EffectExpire` | Remove a buff or debuff and recalculate stats when needed |
| `ChargeRestoreEvent` | Restore a charge and chain the next timer |
| `ResourceGainEvent` | Apply a scripted resource gain |

`setup.prepare_simulation` is what currently builds a run: it splits loadout blueprints into active `Ability` objects and passives, builds `Player` and `Dummy`, attaches the rotation, and schedules the first `PlayerReady` plus a randomized first `ResourceTick`. `pre_sim_effects` and `schedule_periodic` are still in that file and are not called from `prepare_simulation`.

`Tester` runs one fight or a process-pool Monte Carlo batch. It calls `prepare_simulation` and `Simulation.run_timed`.

## Modules

| Module | Role |
| --- | --- |
| `engine.py` | Event queue (`Simulation`) |
| `events.py` | Event types listed above |
| `rotation.py` | Fixed steps, priority blocks, optional steps |
| `resources.py` | Force, Energy, Heat, and builder pools (Rage / Focus) |
| `tester.py` | Single run and Monte Carlo orchestration |
| `setup.py` | Build player, target, and the opening events |
| `cli.py` | Interactive loadout selection |
| `run_config.py` | Run-config schema and validation |
| `config_load.py` | Load discipline, choices, stats, rotation, and ability JSON into blueprints |
| `abilities.py` | Blueprint model (`AbilityBlueprint`, `Effect`, `Branch`) and action dispatch |
| `triggers.py` | Listener table for branch triggers (started, not the live proc path) |
| `requirements.py` | Condition checks (buffs, energy, target health, cooldowns) |
| `combat_math.py` | Accuracy, modifier buckets, mitigation, crits |
| `combat_curves.py` | Level curves and rating constants read from extracted data |
| `entities.py` | `Player` and `Dummy` stats and effect tracking |
| `effects.py` | Previous DoT, channel, buff, and proc records |
| `effects_temp.py` | In-progress replacement for a live effect instance |
| `modifiers.py` | Stat-modifier parsing for the new effect model |
| `metrics.py` | Damage log, per-ability breakdown, execute-phase totals |

## Loading a run

`main.py` reads a `run_config.json` or collects the same choices from the CLI: discipline, stats, rotation, skill-tree choices, tactical, implants, relics, dummy health, duration, and single-run vs batch mode.

`load_from_run_config` resolves that into:

- the rotation step list
- character stats, with standard health taken from the level curve
- ability blueprints for the discipline baseline, chosen skill-tree nodes, tactical, implants, and relics
- an optional training-dummy armor debuff

Blueprint files are addressed by FQN (`abl.sith_inquisitor.shock` maps to a JSON path under the extracted tree).
