# SwtorSim Engine Rules & Architectural Constraints

This document serves as the authoritative specification of core simulation invariants, development rules, codepage standards, and operational protocols for the SWTOR Combat Simulation Engine (`SwtorSim`).

---

### 1. CRITICAL FORMULA RULE
- **NEVER touch or alter the critical damage multiplier formula** in `combat_math.py`.
- The critical damage multiplier formula is calibrated strictly against SWTOR live combat logs and theoretical foundations.

### 2. NO HEURISTIC GUESSING
- **Strictly honor `mod.is_percent` and the parsed blueprint structure.**
- **NEVER** use magnitude heuristics like:
  ```python
  # FORBIDDEN:
  val / 100.0 if abs(val) > 1.0 else val
  ```
- Percentages in parsed blueprints are already canonical decimal fractions (e.g., `0.05` for 5%). Any value passed with `is_percent=True` represents a decimal fraction.

### 3. AUTHORITATIVE IDS
- **Always cross-reference against `Stat_IDs.xlsx` and `src/extractor/mod_stats.py`.**
- **NEVER** invent, guess, or assign unverified stat IDs.
- Ensure all stat modifications map to their true GOM global IDs and semantic channels.

### 4. PYTHON RUNNER
- **Always execute tests and scripts via `.\tools\pyclean.exe` from the `SwtorSim/` directory.**
- `pyclean.exe` is a CPython 3.13 transparent runner that enforces UTF-8 console I/O (`PYTHONUTF8=1`, `PYTHONIOENCODING=utf-8`) and prevents Windows AppContainer C runtime stderr warnings (`Failed to find real location of C:\Python 3.13.9\python.exe`).

### 5. TERMINAL / CODEPAGE SAFETY
- **Use ASCII indicators (`[OK]`, `[WARN]`, `[FAIL]`) instead of Unicode emojis** (e.g., do not use `✅` or `⚠️`).
- This prevents Windows console `cp1252` encoding crashes and ensures clean terminal logging across all environments.

### 6. LINE ENDINGS (CRLF)
- **Workspace files use Windows CRLF (`\r\n`).**
- Be vigilant when writing or patching files to preserve CRLF line endings and avoid mixed/mismatched line endings across git repositories.

### 7. STEM MATCHING
- **Respect `is_stem_matching_enabled()` in `src/swtorsim/settings.py` for ability stems** (e.g. `_plus` suffixes such as `assassinate` matching `assassinate_plus`).
- Stem matching behavior must never bypass the global setting toggle.

### 8. STATE, CHANGELOG, & CATALOG INTEGRITY
- **Catalog:** Always update `tools/catalog_game_data.py` whenever actions, conditions, or stats are modeled, and re-run it via `pyclean.exe` to regenerate `data/catalog_summary.md`.
- **State Separation (Token Efficiency):**
  - **`TODO.md` (Active Queue Only):** Strictly reserved for uncompleted tasks, failing test assertions, active roadmaps, and current architectural state. Once a task is completed, REMOVE its detailed implementation log from `TODO.md`.
  - **`CHANGELOG.md` (Archive Only):** Append detailed completion logs, historical bug fixes, and verification benchmarks here. Do not read `CHANGELOG.md` into context unless specifically investigating historical regressions.

### 9. PROTOCOL
- **Cycle**: Implement -> Test via `pyclean.exe` -> Update `CHANGELOG.md` & prune `TODO.md` -> Show exact code diffs and justify them.
- Ensure 100% test pass rates across the full regression suite before finalizing any task.

### 10. ARCHITECTURAL ROUTING
- **ARCHITECTURAL ROUTING:** Before scanning or grepping across multiple source files to locate a mechanic, read `ARCHITECTURE.md` to identify the exact target file and function.
