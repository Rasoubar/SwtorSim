# Rewrite notes

The simulator is moving from handwritten JSON onto the files produced by `src/extractor`. The extractor pipeline is documented in [src/extractor/README.md](../src/extractor/README.md). This file is the simulator-side checklist. The runtime described in [architecture.md](architecture.md) does not currently complete a fight.

## In place

- The extractor writes discipline manifests, parsed abilities and talents, a gear lookup, and a relic list.
- A run config (file or interactive CLI) names a discipline, stats, rotation, skill-tree choices, tactical, implants, and relics.
- `config_load.load_from_run_config` turns that config into a rotation, stats, and `AbilityBlueprint` objects.
- Parsed abilities load into `AbilityBlueprint`, `Effect`, and `Branch`, including triggers, conditions, and actions.
- `TriggerManager` can subscribe a branch to an event name and filter on tags, excluded tags, integer flags, and proc chance.
- Combat rating curves are read from extracted constants (`combat_curves.py`).

## Still the previous runtime

- `Tester`, the event classes, damage math, metrics, and `Entity.apply_effect` still expect the old action dicts and the `ActiveEffect` in `effects.py`.
- `setup.pre_sim_effects` matches cooldown and charge effects by hardcoded ids, and `prepare_simulation` does not call it.
- `execute_single_action` covers only part of the extracted action set. `modify_stack_charge` does nothing. DoTs, channels, buffs, and debuffs are not applied from this dispatcher.
- Procs are still the old `ProcData` / `PeriodicProcTick` path. `triggers.py` is not what a hit or a crit consults.
- `effects.py` and `effects_temp.py` are two effect models in the same package.

`engine.py`, `rotation.py`, and `resources.py` are expected to stay. Further extracted-schema changes still have to land in the loader before a full loadout can drive a fight.

## Next

**Ability execution.** Run extracted branches for the action types a spec actually uses: damage is started; DoTs, channels, buffs, debuffs, and stack changes are not. Drop the old `instant_tick` DoT flag. An effect that scales with Alacrity should carry `tick_interval` (game field `effInterval`).

**Trigger listener.** Subscribe cast, hit, crit, and periodic branches through `TriggerManager` at setup, and retire the separate proc database. Split listeners by event when they are registered. Keep on-hit and on-crit in an order that matches the game; splitting those two changes which one runs first.

**Pre-sim setup.** Apply passive effects, cooldown changes, and max-charge changes from the extracted nodes while the player is built. Remove the hardcoded effect ids in `pre_sim_effects`. Schedule periodic triggers from those nodes, including the randomized first tick.

**Heals.** After the damage path is executing extracted effects.

**Effect kinds.** Separate combat modifiers from cooldown and charge modifiers, and move stack consumption out of `combat_math`. Stack and charge rules should follow the extracted node (refresh, max stacks, drain on trigger).

**Resources and channels.** Finish passive decay on builder pools (Rage / Focus). Channel clipping and partial ticks need a clear interaction with `PlayerReady`: clipping a channel, spending the tick cost, and queueing the next ready event.

## Open design notes

- Actions are dicts. They can become a class or dataclass once the action set is stable.
- Proc filters should take a list of tags, so a later schema change does not require another pass over the listener.
- Conditions need "caster has this buff at N stacks" (Marauder and Mercenary both use it). `requirements.py` checks buff presence, not stack count.
- Bonus damage is not one bucket. Other classes need the kinds of bonus damage distinguished before their specs can be modeled.
- Proc evaluation should get cheaper once listeners are split by event at setup. Matching every proc on every hit is the current cost.
