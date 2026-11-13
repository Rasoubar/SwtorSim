# Active Task Queue & Current Roadmap

## 1. Active Roadmap & Backlog
- [ ] **Additional Class Disciplines Verification**: Continue verifying and testing combat parses across additional classes and disciplines (e.g. Deception Assassin, Sorcerer, Operative).
- [ ] **Stack Modification Target Resolution Optimization**: Investigate whether effect target type (`Target Type: Self` per Jedipedia / GOM ability/effect root targeting rules) can be extracted directly into blueprints to bypass participant fallback iteration (`caster`/`target`) in `handle_modify_stack_charge`.
- [ ] **Restore Missing Tools**: `tools/catalog_game_data.py` (+ `data/catalog_summary.md`), `tools/parse_combat_log.py`, `tools/validate_modifiers_vs_log.py`, and `tests/test_modifier_multipliers.py` / `tests/test_validate_modifiers_vs_log.py` are referenced by the docs but were never committed. Only a stale `tools/__pycache__/parse_combat_log.cpython-313.pyc` remains locally.
- [ ] **Marksmanship rotation deadlock** (`marksmanshipv2_sub30_crouch_test.json`, seed 42): after a Penetrating Blasts cast at ~148s ends after 0.37s (cause not yet investigated; energy was ~100), the `Sub 30: Takedown / Followthrough` priority block waits indefinitely for the Followthrough buff, Corrosive Dart expires and the sim stalls for the rest of the run. Exposed by the `reset_timer` tick-phase change (CHANGELOG 73); decide whether the engine should skip/time out a blocked priority step or the rotation should be edited.
- [ ] **Out-of-combat resource behavior in pre-combat**: pools are treated as in combat during the pre-pull phase (e.g. Rage decay / OOC regen not modeled). Decide whether to model it.
- [ ] **Action handler leftovers**: `handle_cooldown_action` reads `ints.ability_spec`, but extracted `cooldown` actions carry `ints.timer_spec` (cooldown lands on the wrong ability for Rising Phoenix -> Jet Charge and Impact Charge -> Storm); `_resolve_target_overrides` tests `o_type in ("party_members")`, a string instead of a tuple (no current override type trips it).

## 2. Current Architectural State
- **Dual-Mode Engine**: Standalone zero-install WebAssembly release (`dist/`) running via Pyodide 0.27.2 and multi-threaded Web Worker pool, alongside full-speed native desktop CPython 3.13 (`python run_sim.py`, `python -m swtorsim.web_gui`).
- **Parallelism**: In-browser dynamic hardware concurrency with interactive core selector (`1` to `32` cores, `localStorage` persistence) and batch warm-up gating (`ensureAllWorkersReady`).
- **Performance**: High-speed batch simulation with combat string formatting and `/dev/null` I/O bypass (`verbose=False`).
- **Environments**: Full Live (Level 80, 7.9) and PTS (Level 85, 8.0) dual-environment scaling across extractor, curves, engine, CLI, and Web GUI.
- **Verification**: 80/80 unit, rotational lead-time, rotation stall, blueprint round-trip, cast resource timing, icon integration, pre-cast, and simulation integration tests passing (100% pass rate).
