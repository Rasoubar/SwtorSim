# Plan 10: Multi-Target (Cleave and AoE) Simulations

Status: proposed. Size: L (three phases, one or more sessions each). Risk: **high** (changes the core branch execution path, though no formulas). Do this last, and only after the user gives an explicit go-ahead for each phase.

## 1. Summary (for humans)

Every simulation today has exactly one target. Area abilities (the extracted data has 377 area target overrides: 341 spheres, 22 cones, 2 cylinders, plus "enemies list" types) all resolve to that single dummy, so cleave and AoE damage is invisible. This plan adds **N targets** (for example 2, 3, 4 or 8 dummies standing together). Area abilities then hit every target they can reach up to their extracted `max_targets`, DoTs spread where the game data spreads them, and the result shows total DPS plus a per-target split.

### What the user sees

- "1. Execution Mode & Target": a new **Targets** input (1-8, default 1) and "Fight ends when: primary target dies / all targets die".
- Results: total DPS (all targets), a "Primary target DPS" sub-line, and in the ability breakdown a column "Avg targets hit" for area abilities. Combat log rows name the target ("Target Dummy 2").

## 2. Scope and non-goals

In scope:
- Phase A: plumbing for N targets with **identical results when N = 1** (proven by same-seed checks).
- Phase B: fan-out of area branches/effects to multiple targets.
- Phase C: metrics per target, UI, docs.

Not in scope:
- Target switching in the rotation (rules always evaluate the primary target).
- Positioning beyond "all stacked together" (every target within every radius). A real geometry model is a later step.
- Changing damage formulas, AoE damage modifiers or the "Overwhelmed" AoE vulnerability debuff (already in the dummy debuffs; unchanged).

## 3. Rules that apply

- Rule 1: no formula changes. Fan-out calls the same handlers once per target.
- Rule 9: N = 1 must be bit-for-bit identical on the four reference configs, seeds 42/43/44 (every damage event, event count, and RNG state after the run, like recent CHANGELOG entries).
- Rule 0: ask before starting each phase; this is a large change to central code.

## 4. Current state (facts)

- One target: `src/swtorsim/setup.py :: prepare_simulation` (around line 327) creates `Dummy("Target Dummy", hp=dummy_hp)`, gives it `EffectCollection(copy.deepcopy(debuff_module))`, and sets `player.current_target = target`. It returns `(sim, player, target)`; every caller unpacks three values.
- Fight end: `Simulation.run_timed(duration, target)` (`src/swtorsim/engine.py`) stops when `target.hp <= 0`.
- Target resolution: `src/swtorsim/abilities.py :: _resolve_target_overrides(overrides, current_target, caster, context)` (around line 19) returns **one** entity. `aoe_sphere`, `aoe_cone`, `enemies_list`, `primary_target` all resolve to `enemy_target` (context `enemy_target`, else `caster.current_target`, else the current target).
- Branch execution: `Branch.execute` (around line 80) resolves `actual_target` once, checks branch conditions against it, then runs each action with it; damage actions build `combat_outcomes` used to gate later actions (`results` / `combat_math_only`).
- Effect execution: `Effect.execute` (around line 284) resolves an effect-level target the same way, then applies a persistent effect to it (`apply_effect`) or runs instant branches.
- Area override data shape (from extracted data): `{"type": "aoe_sphere", "aoe_include_phase_players": false, "max_targets": 8, "sort_type": "closest", "radius": 2.0}`; cones add `direction`, `distance`, `angle`. Fields present on 363 of 377 overrides; check the other 14 during phase B.
- Metrics: `Metrics.log_damage(..., target, ...)` uses the hit target's `hp_ratio` for the execute (below 30%) split.
- Damage events carry their target: `DamageHit(source, target, ...)`, `ApplyDamageLand(source, target, ...)`.

## 5. Design

### 5.1 Config

```json
"targets": {"count": 1, "end_when": "primary"}
```

- `count`: 1-8. `end_when`: `"primary"` (default) or `"all"`.
- Every target has `dummy_hp` HP, the same armor, the same raid debuffs, the same `combat_distance`.
- `RunConfig.targets: dict`; payload `targets`; settings dict passes it to workers.

### 5.2 Phase A: plumbing (no behavior change)

1. `prepare_simulation(..., target_count: int = 1)`:
   - Primary: exactly as today (same name "Target Dummy", same order of operations, same RNG calls).
   - Extra targets `Target Dummy 2 .. N` are created **after** everything the single-target path does that touches RNG, so N = 1 draws exactly the same random numbers. Each gets its own deep copy of `debuff_module` and the same `sim.tracker.log_effect_applied` calls.
   - `sim.enemies = [primary, *extras]`; return value unchanged (`(sim, player, primary)`).
2. `Simulation.run_timed(duration, target=None, stop_when=None)`: when `stop_when` is given, stop when it returns True; otherwise the current `target.hp <= 0` rule. For `end_when = "all"`, callers pass `stop_when=lambda: all(e.hp <= 0 for e in sim.enemies)`.
3. Dead targets: `ApplyDamageLand` already sets `is_dead`; nothing else changes in phase A.
4. Same-seed identity check (rule 9). Phase A ends here.

### 5.3 Phase B: fan-out

```python
AREA_OVERRIDE_TYPES = frozenset({"aoe_sphere", "aoe_cone", "aoe_cylinder", "enemies_list"})


def _area_override(overrides) -> dict | None:
    """The first area override of a branch/effect, or None."""


def _area_targets(override: dict, primary, sim) -> list:
    """Alive enemies an area override reaches: primary first, then others by index, capped at max_targets.

    'Stacked' model: every enemy is within every radius/cone. Without sim.enemies (tests,
    old callers) returns [primary].
    """
```

`Branch.execute`:
- If `_area_override(self.target_overrides)` is set **and** `len(getattr(sim, "enemies", ())) > 1`: run the current body once per target from `_area_targets` (conditions checked per target, actions executed per target, `combat_outcomes` per target), and return `(any_ran, any_success)`.
- Otherwise: the existing code path, unchanged (N = 1 and non-area branches never enter the new code).
- RNG order: targets in deterministic order (primary first). Document that multi-target fights consume more random numbers, so N > 1 results are not comparable seed-by-seed with N = 1 (they do not need to be).

`Effect.execute`: same pattern for effect-level area overrides.

Context: when fanning out, set `context["enemy_target"] = that target` for the actions of that iteration so nested `call_effect` / triggers aim at the right dummy.

Special cases to audit (list findings in the CHANGELOG):
- `primary_target`: never fans out (it means "the main target").
- `enemies_list` semantics: inspect three examples in the data; if unclear, ask the user before fanning it out.
- `max_targets` missing: treat as 8 and record the count of such overrides.
- Effects that spread DoTs (for example a talent that copies a DoT to nearby enemies) should work through `call_effect` with an area branch; verify with one concrete ability in a TEST run.

### 5.4 Phase C: metrics and UI

- `Metrics`: per-target totals `damage_by_target: {name: total}`; per ability `targets_hit` count per activation (increment in the fan-out loop; average = targets_hit / activations).
- Execute phase: keep it tied to the **primary** target's HP (document it). Today `log_damage` checks the hit target's `hp_ratio`; change that to check `sim.enemies[0]` only when `len(sim.enemies) > 1` (N = 1 unchanged).
- Results: `primary_dps`, `damage_by_target`, breakdown rows `avg_targets_hit` (only when N > 1).
- UI: Targets input and "Fight ends when" select in section 1; KPI sub-line; breakdown column shown only when present; combat log shows the target name (`ApplyDamageLand` already knows `self.target.name`; add it to the event dict in `_run_single_test_detailed`'s `log_damage` wrapper via the `tgt` argument).

## 6. Step-by-step implementation

Phase A (ask the user first):
1. Baseline tests; record same-seed reference dumps (every damage event, event count, RNG state via `random.getstate()` hashed) for the four configs and three seeds.
2. Config plumbing (`RunConfig.targets`, payload, settings dict).
3. `prepare_simulation(target_count)`, `sim.enemies`, `run_timed(stop_when)`; callers pass the setting (web TEST, batch worker / `run_fight_from_context`, Rotation Builder dry-run keeps 1).
4. Same-seed identity: must be identical. Tests. CHANGELOG.

Phase B (ask again):
5. `_area_override`, `_area_targets`; fan-out in `Branch.execute` and `Effect.execute`.
6. Audit special cases (section 5.3) on real data; write the counts into the CHANGELOG entry.
7. Same-seed identity for N = 1 again; TEST runs with N = 2 and N = 4 on an AoE-heavy rotation; check the combat log shows hits on each dummy and that single-target abilities still hit only the primary.
8. Tests. CHANGELOG.

Phase C:
9. Metrics, result fields, UI.
10. Docs, CHANGELOG.

## 7. Tests

`tests/test_multi_target.py`:
- Phase A: `test_single_target_is_identical` (same seed, `target_count=1` vs default: identical damage event list); `test_extra_targets_have_own_debuff_copies`; `test_run_timed_stop_when_all_dead`.
- Phase B: `test_area_branch_hits_all_alive_targets_up_to_max` (fake branch with an `aoe_sphere` override, `max_targets = 2`, three enemies -> two hits, primary first); `test_dead_target_is_skipped`; `test_primary_target_override_never_fans_out`; `test_non_area_branch_hits_only_primary`; `test_enemy_target_context_set_per_iteration`.
- Phase C: `test_damage_by_target_sums_to_total`; `test_execute_phase_follows_primary_when_multi_target`.

## 8. Verification

1. Full suite passes after every phase.
2. Same-seed identity for N = 1 after phases A and B (four configs, three seeds).
3. N = 2 / 4 TEST runs: area abilities show hits on several dummies; total DPS rises; single-target abilities unchanged per hit.
4. If the user has a real multi-dummy combat log, compare per-ability `avg_targets_hit` and damage share with plan 05's tools.
5. WASM parity.

## 9. Docs

- `docs/user_guide.md`: "Multiple targets" section (stacked model, what fans out, end condition, execute phase tied to the primary).
- `ARCHITECTURE.md`: `setup.py` (`target_count`, `sim.enemies`), `engine.py` (`stop_when`), `abilities.py` (`_area_override`, `_area_targets`, fan-out), `metrics.py` additions.
- `docs/architecture.md`: a short paragraph in the execution narrative.
- `CHANGELOG.md`: one entry per phase.

## 10. Done when

- [ ] N = 1 is bit-for-bit identical (proven after A and B).
- [ ] Area branches and effects hit up to `max_targets` alive targets; single-target logic untouched.
- [ ] Per-target metrics and UI.
- [ ] Special cases audited and documented.
- [ ] Tests, docs, CHANGELOG.

## 11. Open questions for the user

1. Go-ahead for phase A? For phase B? (Required; this is the riskiest plan.)
2. Is the "stacked" model (every target in every radius) good enough for v1, or do you need per-target distances?
3. How should `enemies_list` overrides behave (fan out to all, or something else)? The plan inspects examples first and asks if unclear.
4. Which disciplines/rotations matter most for AoE validation, and do you have multi-target combat logs?
