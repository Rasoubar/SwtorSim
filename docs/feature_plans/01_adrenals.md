# Plan 01: Adrenals

Status: proposed. Size: S-M (one session). Risk: low.

## 1. Summary (for humans)

In SWTOR every serious parse uses an **adrenal**: a consumable that gives a big stat bonus for 15 seconds on a 3-minute cooldown. The extractor already pulls adrenals out of the game files, but the simulator never loads them, so every simulated fight runs without one. This plan lets you pick an adrenal in the simulator and the Rotation Builder, then use it from the rotation like any other off-GCD ability.

### What the user sees

- Simulator page, "2. Loadout, Gear & Rotation": a new **Adrenal** dropdown under the relics ("-- None --" by default).
- Rotation Builder: the same dropdown in the gear panel; when an adrenal is chosen it appears in the castable abilities list (off-GCD), so it can be placed as an optional step, a priority entry, a weave entry, or a pre-combat step.
- Run configs gain an optional `"adrenal_fqn"` field; saving/exporting a config includes it.

## 2. Scope and non-goals

In scope: config field, validation, loadout wiring (simulator, batch, WASM, Rotation Builder, CLI wizard), UI dropdowns, docs, tests.

Not in scope:
- Auto-using the adrenal without a rotation step (users add a step; plan 09's tuner can later learn where to put it).
- Medpacs / stims (not extracted).
- Any change to how the stat bonus is computed (rule 1).

## 3. Rules that apply

- Rule 1: the adrenal's stats go through the existing, frozen `Player.recalculate_stats`. Do not touch it.
- Rule 3: the stat IDs involved are already routed (see section 4); do not add routing.
- Rule 9: DPS before/after on a config that uses the adrenal (using a scratchpad copy of the rotation).
- Rule 11: do not edit `data/extractor/...` or user rotation files. Put modified rotations for tests/checks in the scratchpad.

## 4. Current state (facts)

- Catalogs exist for both environments and are already bundled into the web release (`tools/bundle_pyodide_assets.py`, `INCLUDE_FILES`, lines 48 and 52):
  - `data/extractor/live/adrenals.json` and `data/extractor/pts/adrenals.json`, both:
    ```json
    ["abl.itm.potion.biochem.adrenal.alacrity.artifact.grade11",
     "abl.itm.potion.biochem.adrenal.atk.artifact.grade11",
     "abl.itm.potion.biochem.adrenal.critical.prototype.grade11",
     "abl.itm.potion.biochem.adrenal.heal.artifact.grade11"]
    ```
- Parsed blueprints exist in both environments under `parsed/abl/itm/potion/biochem/adrenal/<kind>/<grade>/grade11.json`.
- `atk/artifact/grade11.json` ("Advanced Polybiotic Attack Adrenal"): `type: active`, `cooldown: 180.0`, `triggers_gcd: false`, `ablIgnoreAlacrity: true`, ability tag `tag.abl.itm.adrenal_cooldown`, one condition (`has_effect`, negated, tag `tag.abl.pvp.doing_pvp`), one effect (15 s, `effIgnoreAlacrity: true`, tags `tag.abl.itm.adrenals` + `tag.abl.itm.adrenal_cooldown`, `stack_charge` by tag `tag.abl.itm.adrenals`) whose `on_apply` branch has `modify_stat STAT_rtg_attack_power amount_min 1005` and `modify_stat STAT_cbt_healing_done_modifier_percentage amount_min -0.2`.
- `alacrity/artifact` ("Advanced Kyrprax Efficacy Adrenal"): `STAT_rtg_spell_haste` +1005. `critical/prototype` ("Prototype Kyrprax Critical Adrenal"): `STAT_rtg_critical_chance` +960.
- Those three stats are already routed:
  - `src/swtorsim/entities.py :: Player.recalculate_stats`, around lines 747-751: `"STAT_rtg_attack_power"` -> Power, `"STAT_rtg_critical_chance"` -> Critical Rating, `"STAT_rtg_spell_haste"` -> Alacrity Rating.
  - `src/swtorsim/combat_math.py`, around lines 414-417, lists the same keys in the base-stat skip list.
- Because the adrenal is an `active` blueprint, adding its FQN to the loadout makes `prepare_simulation` instantiate it as an `Ability` (`src/swtorsim/setup.py`, around line 302), exactly like an on-use relic. `Player.build_ability_db` then indexes it by FQN and by `name.lower().replace(" ", "_")`, e.g. `advanced_polybiotic_attack_adrenal`.
- Today the loadout FQN list is assembled in four places, none of which include adrenals:
  1. `src/swtorsim/config_load.py :: selected_fqns_from_config` (around line 146) for the CLI.
  2. `src/swtorsim/web_gui.py :: _resolve_simulation_inputs_from_payload` (around lines 595-603) for the web simulator and WASM.
  3. `src/swtorsim/rotation_builder.py :: loadout_fqns` for the Rotation Builder catalog and dry-run.
  4. `src/diminishing_returns/config.py` (its own run configs; leave it alone unless the user asks).
- Validation lives in `src/swtorsim/run_config.py :: validate_run_config` (around line 281). Relics are validated by `_validate_relics` against the relic catalog. There is no adrenal catalog path helper yet.

## 5. Design

### 5.1 Config field

`RunConfig` gets `adrenal_fqn: str = ""`. Empty string means "no adrenal". It is optional in run config JSON:

```json
{ "adrenal_fqn": "abl.itm.potion.biochem.adrenal.atk.artifact.grade11" }
```

Validation rules:
- Empty or missing: fine, nothing loaded.
- Non-empty: must be a string listed in the environment's `adrenals.json`. Error message: `adrenal_fqn '<fqn>' is not a known adrenal.`
- The adrenal catalog file must exist only when `adrenal_fqn` is set (old installs without the file keep working).

### 5.2 Loadout order

Append the adrenal FQN **last**, after relics, in every FQN list. Appending last keeps `_BLUEPRINT_LOADOUT_CACHE` keys and dictionary iteration order unchanged for configs without an adrenal, so those configs stay identical.

### 5.3 Rotation usage

Users reference the adrenal like any ability. Recommended `ability_id` is the slug the Rotation Builder shows (for example `advanced_polybiotic_attack_adrenal`). Typical placements:

```json
{ "type": "optional", "ability_id": "advanced_polybiotic_attack_adrenal", "rules": {"caster_has_buff": "Recklessness"} }
```

or as a pre-combat step `{"ability": "advanced_polybiotic_attack_adrenal"}`.

Document in `docs/user_guide.md` that the effect lasts 15 s, the cooldown is 180 s, and it is off the GCD.

## 6. Step-by-step implementation

1. **Baseline.** Run the test suite and record the count. Run `.\tools\pyclean.exe main.py hatred_14gcd --mode BATCH --iterations 50` and save `Average Performance` (config without adrenal; must stay identical).

2. **Verify the blueprint works before wiring UI** (scratchpad script, not in the repo):
   - Resolve the `hatred_14gcd` payload, append the attack adrenal FQN to the selected FQN list, call `load_complete_loadout` and `prepare_simulation`.
   - `abl = player.ability_db["abl.itm.potion.biochem.adrenal.atk.artifact.grade11"]`; record `player.stats["Power"]`; call `abl.cast(player, target, sim)` with `sim.current_time = 0.0`; check it returned True, that an effect named "Advanced Polybiotic Attack Adrenal" is on the player, and that `player.stats["Power"]` went up.
   - Run `sim.run_until(16.0)`; the effect must be gone and Power back to the original value.
   - Check `can_cast` is False until 180 s later.
   - If any of this fails, **stop and report** (do not patch formulas; inspect inputs first per rule 1).

3. **`src/swtorsim/run_config.py`:**
   - Add constants and a path helper next to `get_relics_path`:
     ```python
     ADRENAL_PREFIX = "abl.itm.potion."

     def get_adrenals_path(env: str | None = None) -> str:
         """Returns the adrenals catalog path for the active or specified environment."""
         return str(get_extractor_data_dir(env) / "adrenals.json")
     ```
   - Add `adrenal_fqn: str = ""` to `RunConfig` (after `relic_fqns`; dataclass fields with defaults can go anywhere after the non-default ones).
   - In `load_run_config` add `adrenal_fqn=_optional_adrenal(raw)` where
     ```python
     def _optional_adrenal(raw: dict) -> str:
         """'' when missing or null; otherwise the stripped string (type-checked)."""
         value = raw.get("adrenal_fqn")
         if value is None:
             return ""
         if not isinstance(value, str):
             raise ValueError("'adrenal_fqn' must be a string.")
         return value.strip()
     ```
     (Do not use `_optional_config_str`: it rejects empty strings, but an empty value must mean "none".)
   - In `validate_run_config`, after the relic check:
     ```python
     adrenal = getattr(config, "adrenal_fqn", "") or ""
     if adrenal:
         adrenals_path = get_adrenals_path(env)
         if not _is_file(adrenals_path):
             errors.append(f"adrenal catalog file not found: {adrenals_path}")
         else:
             catalog = _load_json(adrenals_path)
             known = {f for f in catalog if isinstance(f, str)} if isinstance(catalog, list) else set()
             if adrenal not in known:
                 errors.append(f"adrenal_fqn '{adrenal}' is not a known adrenal.")
     ```

4. **`src/swtorsim/config_load.py :: selected_fqns_from_config`:** append `*([config.adrenal_fqn] if getattr(config, "adrenal_fqn", "") else [])` after relics.

5. **`src/swtorsim/web_gui.py`:**
   - `_resolve_simulation_inputs_from_payload`: read `adrenal_fqn = str(payload.get("adrenal_fqn") or "").strip()`, pass `adrenal_fqn=adrenal_fqn` to `RunConfig(...)`, and append it to `selected_fqns` after relics when non-empty.
   - `get_simulator_catalog`: add an `"adrenals"` list, built like `relics_list`:
     ```python
     {"fqn": fqn, "name": bp_doc["name"], "label": f"{name} ({kind})", "icon": bp_doc.get("icon", ""), "kind": kind}
     ```
     where `kind` is the FQN segment after `adrenal.` (`atk`, `alacrity`, `critical`, `heal`). Read the catalog with `get_adrenals_path(active_env)`; return `[]` if the file is missing.
   - `load_run_config_bundle`: nothing special (it returns the raw run config, which now may contain `adrenal_fqn`).
   - Import `get_adrenals_path` from `run_config`.

6. **`tools/simulator_ui.html`:**
   - Markup: after the relic `form-grid-2` (around line 1190) add
     ```html
     <div class="form-row">
       <label class="form-label">Adrenal</label>
       <select id="adrenalSelect"></select>
     </div>
     ```
   - `loadCatalog` (around line 1724, next to the relic population): fill `adrenalSelect` with `-- None --` plus `data.adrenals`; preserve the previous value when `preserveSelections` is true (same pattern as `prevRel1`).
   - `buildPayloadFromForm`: add `adrenal_fqn: document.getElementById("adrenalSelect").value || ""`.
   - `applyPresetRunConfig`: `document.getElementById("adrenalSelect").value = rc.adrenal_fqn || "";` (after the relics).
   - `buildExportRunConfigObject`: add `adrenal_fqn: p.adrenal_fqn` (omit the key when empty to keep exported files clean: `...(p.adrenal_fqn ? {adrenal_fqn: p.adrenal_fqn} : {})`).
   - Call `refreshComputedStats()` on change? Not needed (the adrenal only matters while active).

7. **Rotation Builder (`src/swtorsim/rotation_builder.py`):**
   - `loadout_fqns(..., adrenal_fqn: str = "")`: append to `extra` after relics.
   - `build_castable_catalog(..., adrenal_fqn: str = "")` and `discover_loadout_catalog(..., adrenal_fqn: str = "")`: pass it through to `loadout_fqns`.
   - `RotationBuilderRequestHandler.do_POST` `/api/loadout` (around line 1278): read `payload.get("adrenal_fqn") or ""` and pass it.
   - `run_dry_run_preview` (around line 1061): pass `adrenal_fqn=payload.get("adrenal_fqn") or ""` to `loadout_fqns`.
   - `get_workspace_catalog` (around line 1009): add `"adrenals"` (same shape as in the simulator catalog). Factor a shared helper if convenient, for example `adrenal_catalog_entries(env)` in `web_gui.py` or a new tiny function in `run_config.py` that both call (keep it free of HTTP code).
   - CLI builder (`cli_main`, around line 1481): optional; if it prompts for relics, add an adrenal prompt the same way.

8. **Rotation Builder UI (`tools/rotation_builder_ui.html`):**
   - Markup next to the relic selects (around line 1314): `<select id="adrenalSelect" onchange="onGearOrRelicChange('adrenal', 1)">`.
   - Populate it where the relic selects are filled (around line 1635) from `workspaceCatalog.adrenals`.
   - `refreshLoadoutCatalog` (around line 1894): add `adrenal_fqn` to the payload, honoring `gearOverrides.adrenal_fqn` like the other gear fields.
   - Run-config load (around line 2024): set `adrenalSelect` from `rc.adrenal_fqn`.
   - Dry-run preview payload (around line 4696): add `adrenal_fqn`.
   - `onGearOrRelicChange('adrenal')`: just refresh the catalog.

9. **WASM bridge (`src/swtorsim/pyodide_bridge.py`):** in `DISCOVER_LOADOUT` pass `adrenal_fqn=data.get("adrenal_fqn", "")`. `RUN_ROTATION_PREVIEW`, `SIMULATE`, `SIMULATE_SLICE`, `AGGREGATE_BATCH`, `GET_CATALOG` pick it up automatically through the functions above.

10. **CLI wizard (`src/swtorsim/cli.py`):** add `select_adrenal(adrenals_path)` modeled on `select_relics` (menu with "None" first) and set `adrenal_fqn` on the `RunConfig` built by `collect_run_config_interactive`. If the wizard saves configs, include the field only when set.

11. **Tests** (section 7), docs (section 9), CHANGELOG.

## 7. Tests

New file `tests/test_adrenals.py`:

- `test_load_run_config_accepts_known_adrenal`: write a temp copy of `data/run_config/hatred_14gcd.json` (in a `tempfile.TemporaryDirectory`) with `adrenal_fqn` set to the attack adrenal; `load_run_config` succeeds and `config.adrenal_fqn` matches.
- `test_load_run_config_rejects_unknown_adrenal`: same with `"abl.itm.potion.biochem.adrenal.fake"` -> `ValueError` mentioning `adrenal_fqn`.
- `test_missing_or_null_adrenal_means_none`: no key, and `null`, both give `""`.
- `test_selected_fqns_append_adrenal_last`: `selected_fqns_from_config(config)[-1]` is the adrenal; without it, the list equals the pre-change list (compare to a list built without the field).
- `test_adrenal_raises_power_immediately`: prepare a sim with the adrenal in the loadout and **no relics** (so no other Power procs), dummy HP 1,000,000. Before running any event, record `player.stats["Power"]`, cast the adrenal with `sim.current_time = 0.0`, and assert Power increased (do not assert an exact +1005: class buffs may scale Power).
- `test_adrenal_buff_expires_after_15_seconds`: same setup, cast, then `sim.run_until(15.5, target)`; assert no non-expired effect named "Advanced Polybiotic Attack Adrenal" remains on the player. (Do not compare Power after running events: the rotation and passives can legitimately change it.)
- `test_adrenal_cooldown_is_180_seconds`: after a cast, read `end = player.cooldowns[abl.name]`; assert `abs(end - 180.0) < 0.01` (the blueprint has `ablIgnoreAlacrity: true`); `can_cast` is False at `sim.current_time = end - 0.01` and True at `end + 0.01` (GCD is not involved because `triggers_gcd` is False).
- `test_catalog_lists_adrenals`: `get_simulator_catalog("live")["adrenals"]` has 4 entries with names; same for `"pts"`.
- `test_rotation_builder_catalog_includes_adrenal_when_selected`: `build_castable_catalog(spec, choices, adrenal_fqn=...)` contains an ability whose `fqn` is the adrenal and `triggers_gcd` is False.

Run the whole suite.

## 8. Verification

1. Full suite passes.
2. Same-seed identity for configs **without** an adrenal: the `Average Performance` from step 1 is unchanged.
3. DPS effect (rule 9): copy `data/rotations/assassin/hatred/BasicMaliPS.json` and `data/run_config/hatred_14gcd.json` into the scratchpad. In the copied rotation add, right after the first `recklessness` optional step:
   ```json
   {"type": "optional", "ability_id": "advanced_polybiotic_attack_adrenal", "rules": {}}
   ```
   In the copied run config set `rotation_path` to the copied rotation (absolute path) and `adrenal_fqn` to the attack adrenal. Run `.\tools\pyclean.exe main.py <copied config path> --mode BATCH --iterations 50` and report mean DPS without vs with the adrenal. Expect a small increase (roughly 1-3%). A decrease or no change means the adrenal is not firing; investigate with a TEST run (look for "Casts Advanced Polybiotic Attack Adrenal" in the combat log).
4. Browser checks (native `main.py --web`): the dropdown lists 4 adrenals for Live and PTS; a TEST run with the adrenal and the copied rotation shows the cast in the Combat Event Log and the buff in "Buffs & Debuffs" with about 15 s windows; saving a config writes `adrenal_fqn`; loading it restores the dropdown.
5. Rotation Builder: choose the adrenal, confirm it appears as an off-GCD castable, drag it into a step, run the preview.
6. WASM build: rebuild `dist/`, repeat check 4.

## 9. Docs

- `docs/user_guide.md`: add `adrenal_fqn` to the run config field table (type string, default `""`, "FQN from `data/extractor/<env>/adrenals.json`; empty for none") and a short "Using an adrenal" paragraph (section 5.3).
- `ARCHITECTURE.md`: mention `adrenal_fqn` in the `run_config.py` row and `get_adrenals_path`.
- `CHANGELOG.md`: entry "Loadout: Adrenals".

## 10. Done when

- [ ] An adrenal can be chosen in the simulator, Rotation Builder and CLI wizard, saved and reloaded.
- [ ] It casts from a rotation step and buffs the right stat for 15 s with a 180 s cooldown.
- [ ] Configs without an adrenal are bit-for-bit unchanged.
- [ ] Works in WASM.
- [ ] Tests, docs, CHANGELOG done.

## 11. Open questions for the user

1. Should the healing adrenal (`heal/artifact`) be hidden from the DPS simulator dropdown? (Suggested: show it, labeled "(heal)", since filtering by name is guesswork.)
2. Is grade 11 the only grade you care about? The extractor currently outputs only grade 11; other grades would need an extractor change and a re-extract.
