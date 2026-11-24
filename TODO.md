# Active Task Queue & Current Roadmap

## 1. Active Roadmap & Backlog
- [ ] **Stack Modification Target Resolution Optimization**: Investigate whether effect target type (`Target Type: Self` per Jedipedia / GOM ability/effect root targeting rules) can be extracted directly into blueprints to bypass participant fallback iteration (`caster`/`target`) in `handle_modify_stack_charge`.
- [ ] **Multiplayer: `from_actor` values other than `caster`** (`src/swtorsim/requirements.py :: _condition_source`): `from_actor: caster` now limits has_effect / not_has_effect / has_effect_at_stack_charge_count to effects the caster applied. `actor_1` (2,837 conditions) and `target` (16) are still unrestricted; their meaning is not established from data. Revisit once a second effect source exists.
- [ ] **`ground` / `any` target rules still use the tag/damage heuristic** (`Ability.targets_enemy`, CHANGELOG 97): 46 live abilities. Once heals and healer specs are tested, decide whether those rules can be mapped directly, then drop the heuristic fallback and the `trigger_caster` retaliation clause in `Effect.execute` (CHANGELOG 96, #9).
- [ ] **Out-of-combat resource behavior in pre-combat**: pools are treated as in combat during the pre-pull phase (e.g. Rage decay / OOC regen not modeled). Decide whether to model it.

## 2. Current Architectural State
- **Dual-Mode Engine**: Standalone zero-install WebAssembly release (`dist/`) running via Pyodide 0.27.2 and multi-threaded Web Worker pool, alongside full-speed native desktop CPython 3.13 (`python run_sim.py`, `python -m swtorsim.web_gui`).
- **Parallelism**: In-browser dynamic hardware concurrency with interactive core selector (`1` to `32` cores, `localStorage` persistence) and batch warm-up gating (`ensureAllWorkersReady`).
- **Performance**: High-speed batch simulation with combat string formatting and `/dev/null` I/O bypass (`verbose=False`).
- **Environments**: Full Live (Level 80, 7.9) and PTS (Level 85, 8.0) dual-environment scaling across extractor, curves, engine, CLI, and Web GUI.
- **Verification**: 456/456 unittest tests passing (2026-11-23 snapshot).
