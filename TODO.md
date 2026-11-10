# Active Task Queue & Current Roadmap

## 1. Active Roadmap & Backlog
- [ ] **Additional Class Disciplines Verification**: Continue verifying and testing combat parses across additional classes and disciplines (e.g. Deception Assassin, Sorcerer, Operative).
- [ ] **Stack Modification Target Resolution Optimization**: Investigate whether effect target type (`Target Type: Self` per Jedipedia / GOM ability/effect root targeting rules) can be extracted directly into blueprints to bypass participant fallback iteration (`caster`/`target`) in `handle_modify_stack_charge`.

## 2. Current Architectural State
- **Dual-Mode Engine**: Standalone zero-install WebAssembly release (`dist/`) running via Pyodide 0.27.2 and multi-threaded Web Worker pool, alongside full-speed native desktop CPython 3.13 (`python run_sim.py`, `python -m swtorsim.web_gui`).
- **Parallelism**: In-browser dynamic hardware concurrency with interactive core selector (`1` to `32` cores, `localStorage` persistence) and batch warm-up gating (`ensureAllWorkersReady`).
- **Performance**: High-speed batch simulation with combat string formatting and `/dev/null` I/O bypass (`verbose=False`).
- **Environments**: Full Live (Level 80, 7.9) and PTS (Level 85, 8.0) dual-environment scaling across extractor, curves, engine, CLI, and Web GUI.
- **Verification**: 80/80 unit, rotational lead-time, rotation stall, blueprint round-trip, cast resource timing, icon integration, pre-cast, and simulation integration tests passing (100% pass rate).
