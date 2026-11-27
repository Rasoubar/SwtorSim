# Plan 06: Encounter Scripting (Movement, Out of Range, Untargetable, Raid Burst, Fight Length)

Status: proposed. Size: M-L (three phases). Risk: medium (adds gates in the casting and damage path; no formula changes). Phase C depends on plan 00; drawing windows uses plan 02.

## 1. Summary (for humans)

A training dummy never moves, never runs away and never becomes immune, so dummy parses overstate real-fight DPS, and they overstate it differently for different disciplines (a spec built on long cast bars loses more to movement than one built on instants). This plan lets a run config describe simple boss mechanics:

- **Moving** windows: you must move, so you cannot *start* cast-time or channeled abilities; instants still work.
- **Out of range** windows: the boss is away (knockback, phase), so no attacks at all; self-buffs still work; your DoTs keep ticking.
- **Untargetable** windows: like out of range, and the boss also takes no damage (DoT ticks do nothing).
- **Ranged only** windows (phase B): you are N meters away, so abilities with a shorter range are blocked. Needs one extractor field.

Windows can start at a fixed fight time, repeat every N seconds, or trigger when the boss drops below an HP %.

Two related additions:

- **Raid burst buffs**: apply Bloodthirst / Inspiration-style buffs at pull and every 5 minutes, using the real extracted ability effect.
- **Fit HP to fight length** (phase C): "make this fight last about 300 s" by running a short pilot batch and setting the dummy HP from the measured DPS. Execute-phase share depends on fight length, so this matters for fair comparisons.

### What the user sees

- New sidebar section **"5. Encounter & Raid Buffs"**:
  - A table of windows: Kind (dropdown), Start (s) or "At HP %", Duration (s), Repeat every (s), Repeat count (0 = forever), and for "Ranged only" a Distance (m). Add / remove row buttons.
  - Presets: "None", "Light movement (2 s every 20 s)", "Heavy movement (4 s every 15 s)", "Phase at 50% (10 s untargetable)".
  - Checkbox "Raid burst at pull, every 300 s" with a dropdown (Bloodthirst / Inspiration).
  - "Fit HP to [ 300 ] s" button (phase C) that fills the Dummy HP field.
- Results: KPI sub-line "Encounter downtime: X s"; windows drawn as colored bands on the Fight Timeline charts (plan 02); combat log rows `ENCOUNTER` when a window starts/ends.

## 2. Scope and non-goals

In scope: encounter schema + validation, engine gates, events, raid buff application, metrics, UI, phase B extractor field, phase C fit-HP experiment, tests.

Not in scope:
- Interrupting a cast that is already in progress when movement starts (v1 only blocks *starting* casts; see open question 1).
- "Can be used while moving" talents (some disciplines get instant versions of cast abilities via talents; those show up as different activation data or are not modeled; see open question 2).
- Damage-taken phases ("boss takes +X% damage"): that would add a target modifier and touch stat routing (rule 1); only on explicit user request.
- Smart pre-planning (not starting a 2 s cast 1 s before known movement).

## 3. Rules that apply

- Rule 1: no change to formulas. The gates sit before `can_cast` returns and before `calculate_hit` is called; they never change computed values.
- Rule 2 / pre-existing issue 4 (README section 6): verify the raid buff's damage modifier is honored as +10% before offering it; if not, stop and report.
- Rule 9: same-seed identity with no encounter (default) on the four reference configs; report DPS with a sample encounter.
- Rule 11: phase B needs a new extractor field -> change the extractor, ask the user to re-extract.

## 4. Current state (facts)

- Casting gate: `src/swtorsim/abilities.py :: Ability.can_cast` (around line 1443) and its diagnostic twin `check_cast_eligibility` (around line 1483). Both compute `is_aggressive` with the same expression (tags `tag.abl.utility.aggressive_action` / `tag.abl.utility.is_basic_attack`, or untagged with an attack branch). Activation type is `ability.activation["type"]` (`"instant"`, `"cast"`, `"channel"`).
- Fight start: `src/swtorsim/events.py :: ApplyDamageLand.resolve` (around line 50) sets `sim.combat_start_time` on the first damage, then deducts HP (`self.target.hp -= self.final_damage`).
- Damage pipeline: `DamageHit.resolve` (around line 108) calls `calculate_hit`, dispatches `on_pre_damage_*`, resolves `ApplyDamageLand`, dispatches `on_damage_*`.
- Rotation loop: `PlayerReady.resolve` (around line 493). When the rotation cannot act and the player is not busy after the GCD, it starts a "stall" (`_is_stalled`, `sim.tracker.log_rotation_stall_start`) and retries every 0.1 s.
- Casts abort cleanly if `caster.active_cast` is no longer the ability (`CastFinishEvent.resolve`, around line 798).
- Setup: `src/swtorsim/setup.py :: prepare_simulation` (around line 281) builds the player, the single `Dummy`, the `Simulation`, and schedules the first `PlayerReady`.
- Raid buff data: `data/extractor/live/parsed/abl/sith_warrior/bloodthirst.json`:
  - effect 1: `dispel` + a `raid_members` branch calling effects 2 and 3,
  - effect 2 "Bloodthirst": duration 10 s, `on_apply`/`on_refresh` branch calls effect 4; `on_apply` branch `modify_stat STAT_cbt_healing_done_modifier_percentage amount_min 0.1` and `modify_stat STAT_cbt_damage_done_modifier_percentage amount_min 0.1` (`amount_percent 0.0`),
  - effect 4 "Satiated": 300 s lockout (`tag.abl.sith_warrior.bloodthirst_lockout`).
  - `data/extractor/live/parsed/abl/jedi_knight/inspiration.json` exists too (inspect its effect numbers before use).
  - `raid_members` is not handled by `_resolve_target_overrides` (README issue 5), so executing the whole ability would hit the dummy. Applying **effect 2 directly** with `Effect.execute(sim, caster=player, target=player, ability=ability)` avoids that: effect 2 has no target overrides and is persistent, so `Effect.execute` routes it to `player.apply_effect` and runs its `on_apply` branches (including the Satiated call).
- Range data: raw extracted abilities have `ablMaxRange` (e.g. `extracted/abl/sith_inquisitor/assassinate.json` = 0.4, `shock.json` = 1.0). Game distance units are tens of meters (the engine's projectile code uses `distance / (speed * 10.0)`), so 0.4 = 4 m (melee) and 1.0 = 10 m. Parsed blueprints do not carry it; `_build_ability_payload` (`src/extractor/abilities.py`, around line 2059) would need to write it.

## 5. Design

### 5.1 Schema

Run config / simulate payload key `"encounter"` (optional; absent or `{}` = no encounter):

```json
"encounter": {
  "windows": [
    {"kind": "moving", "start": 20.0, "duration": 2.0, "repeat_every": 20.0, "repeat_count": 0},
    {"kind": "out_of_range", "start": 90.0, "duration": 5.0},
    {"kind": "untargetable", "at_hp_pct": 0.5, "duration": 10.0, "clear_target_effects": false},
    {"kind": "ranged_only", "start": 150.0, "duration": 8.0, "distance_m": 15.0}
  ],
  "raid_buffs": [
    {"ability_fqn": "abl.sith_warrior.bloodthirst", "effect": 2, "at": 0.0, "repeat_every": 300.0}
  ]
}
```

Validation (`src/swtorsim/run_config.py :: normalize_encounter(raw) -> dict`, raising `ValueError` with a precise message, like `normalize_pre_combat`):
- `kind` in `{"moving", "out_of_range", "untargetable", "ranged_only"}` (`ranged_only` only after phase B).
- Exactly one of `start` (>= 0) or `at_hp_pct` (0 < x < 1).
- `duration` > 0. `repeat_every` > `duration` when present (no overlapping repeats of the same window). `repeat_count` int >= 0 (0 = until fight end); not allowed with `at_hp_pct`.
- `distance_m` > 0 for `ranged_only`.
- `raid_buffs[*]`: `ability_fqn` non-empty; `effect` int >= 1; `at` >= 0; `repeat_every` > 0 optional. File existence and effect presence are checked at setup (needs the environment's parsed dir).
- Times are **fight-relative** (0 = first damage), consistent with the rest of the UI.

`RunConfig` gets `encounter: dict = field(default_factory=dict)`; `load_run_config` reads `raw.get("encounter")`, normalizes it; `_resolve_simulation_inputs_from_payload` does the same for the payload; the batch `settings_dict` carries it (plan 00's `build_fight_context` is the single place to add it).

### 5.2 Engine module `src/swtorsim/encounter.py` (new)

```python
WINDOW_KINDS = ("moving", "out_of_range", "untargetable", "ranged_only")
GOM_DISTANCE_UNIT_M = 10.0  # ablMaxRange 0.4 == 4 m


@dataclass
class ActiveWindow:
    kind: str
    start: float      # raw sim time
    end: float
    distance_m: float | None = None
    clear_target_effects: bool = False


class EncounterController:
    """Schedules encounter windows and raid buffs, and answers 'is this blocked right now?'."""

    def __init__(self, spec: dict, parsed_dir: Path):
        ...

    def install(self, sim, player, target) -> None:
        """Attaches itself as sim.encounter and loads raid buff blueprints (fails fast on bad FQNs)."""

    # --- hooks called by the engine -------------------------------------------------------
    def on_combat_start(self, sim) -> None:
        """Schedules time-based windows and raid buffs relative to sim.combat_start_time."""

    def on_damage_landed(self, sim, target) -> None:
        """Opens HP-triggered windows the first time target.hp_ratio <= at_hp_pct."""

    # --- queries ---------------------------------------------------------------------------
    def active_kinds(self, now: float) -> set[str]: ...
    def is_blocking(self, now: float) -> bool: ...
    def block_reason(self, ability, caster, now: float) -> str | None:
        """'Encounter: moving' etc. when the ability may not start now, else None."""
    def is_untargetable(self, target, now: float) -> bool: ...

    # --- reporting -------------------------------------------------------------------------
    def report(self, time_origin: float) -> dict:
        """{"windows": [{"kind", "start", "end"}], "blocked_time": s} in fight-relative seconds."""
```

Events (in `encounter.py`, subclassing `events.Event`):
- `EncounterWindowStart(controller, window)`: appends to the active list, records it, for `untargetable` with `clear_target_effects` removes non-passive effects whose `caster_ref` is the player from the target (via `cleanup_expired_effects`), and logs a verbose line `Encounter: <kind> starts (<duration>s)`.
- `EncounterWindowEnd(controller, window)`: removes it; calls `events.schedule_next_decision(player, target, sim)` so the rotation reacts immediately instead of waiting for the 0.1 s retry.
- `RaidBuffEvent(controller, buff)`: `effect.execute(sim, player, player, ability=buff_ability)`, then reschedules itself after `repeat_every` if set.

Block rules (`block_reason`):
- `moving`: block when `ability.activation["type"] in ("cast", "channel")` and the activation duration is > 0.
- `out_of_range`, `untargetable`: block when the ability is aggressive (same expression as `can_cast`; move that expression into a property `Ability.is_aggressive` and use it in `can_cast`, `check_cast_eligibility` and here, so the three can never disagree).
- `ranged_only` (phase B): block when aggressive and `blueprint.max_range is not None and blueprint.max_range * GOM_DISTANCE_UNIT_M < distance_m`. Abilities with no `max_range` are not blocked (count them and expose the list in `report()` as `unknown_range_abilities` so the user can see what was assumed).

### 5.3 Engine hooks (minimal, all guarded by `enc = getattr(sim, "encounter", None)`)

1. `Ability.can_cast`: right after the charges/cooldown checks and before the cost check (order does not change results when `enc` is None):
   ```python
   enc = getattr(sim, "encounter", None)
   if enc is not None and enc.block_reason(self, caster, sim.current_time):
       return False
   ```
   `check_cast_eligibility`: same, returning `(False, reason)`.
2. `ApplyDamageLand.resolve`: after `sim.combat_start_time = sim.current_time` add `enc.on_combat_start(sim)`; after `self.target.hp -= self.final_damage` add `enc.on_damage_landed(sim, self.target)`.
3. `DamageHit.resolve`: at the very top:
   ```python
   enc = getattr(sim, "encounter", None)
   if enc is not None and enc.is_untargetable(self.target, sim.current_time):
       return
   ```
   (No damage, no damage triggers. DoT ticks call this path too, so they "tick for nothing".)
4. `PlayerReady.resolve`, in the branch that would start a stall:
   ```python
   if enc is not None and enc.is_blocking(sim.current_time):
       if getattr(self.player, "_is_stalled", False):
           sim.tracker.log_rotation_stall_end(sim.current_time)
           self.player._is_stalled = False
       sim.schedule_relative(0.1, PlayerReady(self.player, self.target, self.generation))
       return
   ```
   so encounter downtime is never reported as a rotation stall.
5. `setup.prepare_simulation`: new keyword `encounter: dict | None = None` (falls back to `config.encounter` when `config` is given); if non-empty, `EncounterController(encounter, parsed_dir).install(sim, player, target)` after the `Simulation` is created. The parsed dir is `get_extractor_data_dir() / "parsed"`.
6. Batch / experiment workers pass `settings_dict["encounter"]` to `prepare_simulation`.

### 5.4 Result payload

- TEST and BATCH results gain `encounter: {"windows": [...], "blocked_time": s}` (TEST: from `controller.report(time_origin)`; BATCH: average `blocked_time` over runs and the first run's windows for display). Absent when no encounter.
- TEST combat log: one `category: "encounter"` row at each window start/end (`text: "Moving starts (2.0s)"`), so the log filter "All Events" shows them. Add a log badge style.

### 5.5 Raid buff verification (must happen before UI exposure)

Scratchpad check:
1. Prepare a sim for `hatred_14gcd` with `raid_buffs` = Bloodthirst effect 2 at 0.0.
2. Compute one hit of a fixed ability with and without the buff active (same seed, crit disabled is not possible, so compare the *non-crit* damage of the same ability at the same stats: call `combat_math.calculate_hit` read-only twice, once before applying the effect and once after, with `random.seed` reset to the same value before each call).
3. Expect a ratio of 1.10 (+10% damage done).
4. If the ratio is not 1.10, **stop and report** to the user with the numbers. Likely cause: `Modifier.from_modify_stat` sets `is_percent=False` because `amount_percent` is 0 (README issue 4). The fix belongs in the extractor or in how `modify_stat` percent stats are flagged, and needs the user's decision. Never add a magnitude heuristic.

### 5.6 Fit HP to fight length (phase C, plan 00 kind `"fit_hp"`)

Request: `{"kind": "fit_hp", "payload": {...}, "options": {"target_seconds": 300, "pilot_iterations": 20, "tolerance_pct": 2.0, "max_rounds": 3}}`.

- Round 0: base payload with its current `dummy_hp`, `(0, pilot_iterations)`.
- After each round: `mean_dur = mean(elapsed)`; if `abs(mean_dur - target) / target * 100 <= tolerance_pct`, stop; else `hp_new = round(hp_old * target / mean_dur, -4)` (scale HP by the duration ratio; DPS is roughly constant, but the execute phase changes it slightly, so iterate), add a new variant with that HP and run it on the same seeds.
- `finalize`: `{"dummy_hp": best_hp, "mean_duration": d, "rounds": [...]}`; the UI writes `dummy_hp` into the input.
- Note that `duration` in the payload must be larger than the target (set it to `max(payload.duration, 2 * target_seconds)` for the pilot).

### 5.7 UI

- New sidebar section after "4. Engine Mechanics & Toggles" (around line 1343): "5. Encounter & Raid Buffs" with the windows table (`encounterRows` array in JS, `renderEncounterTable()`), preset select, raid buff checkbox + select, and (phase C) "Fit HP" input + button.
- `buildPayloadFromForm`: add `encounter: buildEncounterFromForm()` (omit when empty).
- `applyPresetRunConfig` and `buildExportRunConfigObject`: read/write `rc.encounter`.
- Plan 02 integration: `renderTimelineTab` already draws `res.encounter.windows` as bands (plan 02, step 9).
- KPI: under "Fight Duration & Damage", append "Encounter downtime: X s" when present.

## 6. Step-by-step implementation

Phase A (windows + raid buffs):
1. Baseline tests; same-seed reference outputs for the four configs (README section 3).
2. `normalize_encounter` + `RunConfig.encounter` + payload/settings plumbing. Tests for validation.
3. `Ability.is_aggressive` property; replace the two inline copies (pure refactor; same-seed identity check).
4. `encounter.py` controller, events, block rules for `moving` / `out_of_range` / `untargetable`.
5. Engine hooks (section 5.3). Same-seed identity with no encounter.
6. Raid buff verification (section 5.5). If it fails, finish phase A without raid buffs and report.
7. Result payload fields and combat log rows.
8. UI section, payload, load/save.
9. Tests (section 7), DPS report (section 8), docs, CHANGELOG.

Phase B (ranged_only):
10. Extractor: in `_build_ability_payload` add `payload["max_range"] = _float_field(record, "ablMaxRange")` when present (raw GOM value, not converted). Add `max_range: Optional[float] = None` to `AbilityBlueprint` and read it in `from_dict`. Ask the user to re-extract Live and PTS. Until they do, `ranged_only` stays disabled (validation error "ranged_only requires re-extracted data with max_range").
11. Block rule and `unknown_range_abilities` reporting; UI distance column; tests with a fake blueprint.

Phase C (fit HP): kind `"fit_hp"` in `encounter.py` or a small `fit_hp.py`; UI button; tests with fake results.

## 7. Tests

New file `tests/test_encounter.py`:
- Validation: `test_normalize_rejects_unknown_kind`, `test_requires_start_or_at_hp_not_both`, `test_repeat_every_must_exceed_duration`, `test_empty_encounter_is_noop`.
- `test_is_aggressive_property_matches_old_expression` (for every active ability of a real loadout).
- `test_moving_blocks_cast_and_channel_not_instant`: fake controller with an active `moving` window; a cast-time ability's `can_cast` is False, an instant's is True.
- `test_out_of_range_allows_self_buff_blocks_attack`.
- `test_untargetable_drops_damage_hit`: resolve a `DamageHit` while untargetable (stub `calculate_hit` like `tests/test_trigger_damage_type.py` does) -> target HP unchanged, no `on_damage_dealt` dispatch.
- `test_windows_scheduled_relative_to_first_damage`: run a short fight with `start = 5`, check the recorded window start equals `combat_start_time + 5`.
- `test_hp_window_fires_once`.
- `test_encounter_downtime_not_counted_as_stall`.
- `test_raid_buff_applies_effect_and_lockout` (only if section 5.5 passed): Bloodthirst effect present for 10 s, Satiated present for 300 s.
- `test_no_encounter_same_seed_identical`: same seed, `encounter={}` vs no key -> identical `total_damage`.
- Phase B: `test_ranged_only_uses_max_range_in_meters` (fake blueprint `max_range = 0.4`, distance 10 m -> blocked; `max_range = 3.0` -> allowed; `None` -> allowed and listed).
- Phase C: `test_fit_hp_converges_on_fake_results`.

## 8. Verification

1. Full suite passes.
2. Same-seed identity without an encounter on the four reference configs (seeds 42/43/44).
3. DPS report: `hatred_14gcd` and `sniper_marksmanship_config_test` (a cast-heavy spec if available), 100 iterations, with the "Light movement" preset vs none. Expect a DPS loss, larger for the cast-heavy spec. Report both numbers.
4. TEST run: the Fight Timeline shows the bands, the combat log shows ENCOUNTER rows, no casts start inside `moving` windows for cast-time abilities (check the Cast Timeline window too), the stall banner does not fire because of encounter downtime.
5. Raid buff: Bloodthirst windows visible in Buffs & Debuffs at 0 s and 300 s.
6. WASM parity.

## 9. Docs

- `docs/user_guide.md`: "Encounter scripting" section with the schema, kinds, examples, limitations (no mid-cast interrupt, no "usable while moving" talents, raid buff verification note).
- `ARCHITECTURE.md`: `swtorsim/encounter.py` row; hooks listed in the `abilities.py` / `events.py` / `setup.py` rows; extractor `max_range`.
- `CHANGELOG.md`: one entry per phase.

## 10. Done when

- [ ] Windows of every kind behave as specified, scheduled by time, repeat or HP.
- [ ] No-encounter runs are identical to before.
- [ ] Encounter downtime is reported separately from stalls.
- [ ] Raid buffs verified (or explicitly deferred with evidence reported).
- [ ] UI editing, load/save, timeline bands.
- [ ] Phase B and C done or explicitly deferred.

## 11. Open questions for the user

1. Should a `moving` window that starts during a cast bar cancel that cast (and if so, should the GCD/cooldown spent at cast start be refunded)? v1 does not cancel.
2. Which "castable while moving" effects exist in the disciplines you care about (talents, procs)? They need explicit modeling.
3. Raid burst cadence: always at pull + every 300 s, or configurable per encounter (plan supports both; which default)?
4. For `untargetable`, should player DoTs be removed (`clear_target_effects`) by default? Real fights differ.
