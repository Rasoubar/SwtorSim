# Plan 04: Top Gear (Loadout Comparison Matrix)

Status: proposed. Size: M (two sessions: engine + CLI, then UI). Risk: low. Depends on plan 00. Plan 01 (adrenals) adds an optional axis.

## 1. Summary (for humans)

"Which tactical is best for my build? Which pair of legendary implants? Which relics? Is talent A or B better at level 39?" Today you answer that by changing one dropdown, running a batch, pinning it, changing the next dropdown, running again, and comparing numbers that each carry their own random noise.

**Top Gear** does it in one click. You tick the candidates you want compared; the sim builds every variant, runs them all on the **same seeds** (so luck cancels out), drops clearly worse ones early to save time, and gives you a ranked table: mean DPS, difference from your current setup, a 95% confidence interval, and a flag when two options are too close to call. One button applies the winner to your form.

### What the user sees

- Sidebar "2. Loadout, Gear & Rotation": a **Top Gear** button.
- A modal with checkbox lists:
  - Tacticals (class-filtered list, current one pre-ticked),
  - Legendary implants (tick a pool; the sim tests every pair from the pool; optionally "keep implant 1 fixed"),
  - Relics (tick a pool; pairs from the pool, plus "no relic" options if wanted),
  - Adrenals (after plan 01),
  - Skill tree levels to vary (tick levels; every option at those levels is tested),
  - Mode: "One change at a time" (vary each axis from your current setup) or "All combinations" (cartesian product, capped),
  - Effort: Quick / Normal / Thorough (sets the iteration schedule),
  - An estimate: variants, maximum fights, rough time.
- Results in a new results tab **Top Gear**: ranked table with columns Rank, Variant (what differs from current), Mean DPS, Delta vs current (+/- CI), Fights run, Status (finalist / eliminated in round N / invalid / rotation incompatible), and an **Apply** button per row.

## 2. Scope and non-goals

In scope: experiment kind `"top_gear"`, variant builder, rotation compatibility check, successive halving, UI, CLI, tests.

Not in scope:
- Stats changes (that is plan 03).
- Rotation changes per variant (a talent that removes an ability the rotation needs is flagged, not auto-fixed; plan 09 is the tool for rotation edits).
- Saving variants as run configs automatically (the Apply button loads one into the form; the user saves it if they want).

## 3. Rules that apply

- Rule 1: nothing in the math changes; variants only change loadout FQNs and choices.
- Rule 11: never write to user run config / rotation files from this feature.

## 4. Current state (facts)

- Candidate lists:
  - `web_gui.py :: get_class_gear_options(spec_path, env)` (around line 335) returns class-filtered `tacticals` and `legendaries` (`[{name, fqn}]`) and `skill_tree` (`{level: {slot: [{fqn, name, type, icon}]}}`) plus `skill_tree_levels`.
  - `get_simulator_catalog(env)` (around line 213) returns `relics` (`[{label, name, short_label, type, fqn}]`) and, after plan 01, `adrenals`.
- Validation of a loadout happens inside `_resolve_simulation_inputs_from_payload` via `validate_run_config` (legendaries: exactly 2 distinct and class-allowed; relics: 0-2 distinct and known; tactical: known and class-allowed; choices: every skill tree level present with value 1-3).
- Rotation ability ids are looked up in `player.ability_db` (indexed by FQN, by `fqn.lower().replace(" ", "_")` and by `name.lower().replace(" ", "_")`; `entities.py :: Player.build_ability_db`, around line 423). A missing id behaves like this (`src/swtorsim/rotation.py`):
  - `fixed` step: never casts -> the rotation blocks forever (deadlock).
  - `optional` step / weave entry: skipped.
  - priority pool entry: skipped (`ability` is None).
- The skill tree can *replace* abilities (for example `Assassinate+` replacing `Assassinate`, per `docs/user_guide.md` section 2.3), so changing a talent can remove an ability id the rotation uses.

## 5. Design

### 5.1 Request

```json
{
  "kind": "top_gear",
  "payload": { "...current simulate payload (this is the 'current' variant)..." },
  "options": {
    "mode": "one_axis",
    "max_variants": 200,
    "axes": {
      "tacticals": ["abl.itm.tactical....", "..."],
      "legendary_pool": ["abl.itm.legendary....", "..."],
      "legendary_fixed": null,
      "relic_pool": ["abl.itm.relic....", "..."],
      "relic_allow_empty": false,
      "adrenals": ["", "abl.itm.potion...."],
      "skill_levels": ["39", "64"]
    },
    "schedule": {"initial": 40, "max": 640, "keep_fraction": 0.5, "min_survivors": 3},
    "skip_incompatible": true
  }
}
```

Effort presets for the UI:

| Preset | initial | max |
|---|---|---|
| Quick | 20 | 160 |
| Normal | 40 | 640 |
| Thorough | 100 | 1600 |

### 5.2 Variant building (pure function, fully tested)

```python
def build_top_gear_variants(base: dict, axes: dict, mode: str, max_variants: int,
                            skill_tree: dict) -> list[dict]:
    """[{id, label, overrides, diff}] for every requested combination; 'current' first."""
```

Axis value sets, each including the current value so "no change" is always a member:
- `tacticals`: given list (plus current).
- Legendary pairs: if `legendary_fixed` is set, pairs `(fixed, x)` for `x` in pool minus fixed; else all unordered pairs `itertools.combinations(sorted(pool), 2)`. Plus the current pair. Represent a pair as a sorted tuple so `(A, B)` and `(B, A)` are the same variant.
- Relic pairs: unordered pairs from the pool; if `relic_allow_empty`, also singletons and the empty set. Plus current.
- Adrenals: given list (plus current); `""` means none.
- Skill levels: for each listed level, options `1, 2, 3` that exist in `skill_tree[level]`.

Modes:
- `one_axis`: start from the current setup; for each axis, one variant per non-current value of that axis (other axes at current). Total = 1 + sum(len(values) - 1).
- `cartesian`: product of all axes' value sets. If the product exceeds `max_variants`, refuse with an error that states the count and suggests `one_axis` or smaller pools (do not silently sample).

Each variant:
- `overrides` touches only `tactical_fqn`, `legendary_fqns` (list of 2), `relic_fqns`, `adrenal_fqn`, `choices` (merged by `apply_overrides`).
- `diff`: list of human-readable changes vs current, e.g. `["Tactical: Two-Time Trouble", "L39: option 2 (Force Fracture)"]`, built with names from the catalogs.
- `id`: stable short id, e.g. sha1 of the canonical overrides (first 10 hex chars), with `"current"` for the base.
- Deduplicate by canonical overrides (sorted lists).

### 5.3 Rotation compatibility check

```python
def rotation_ability_ids(rotation_config) -> dict[str, list[str]]:
    """{"fixed": [...], "optional": [...], "pool": [...], "weave": [...], "pre_combat": [...]} of ability ids used."""


def loadout_ability_keys(loadout_blueprints: dict) -> set[str]:
    """The keys Player.build_ability_db would create for the active, non-talent blueprints."""
```

`loadout_ability_keys` must mirror `Player.build_ability_db` exactly: for each blueprint with `type == "active"` and FQN not starting with `"tal."`, add `fqn`, `fqn.lower().replace(" ", "_")`, `name.lower().replace(" ", "_")`. (Do not invent stem matching here; ability ids are exact keys.)

For each valid variant, after resolving its payload once in the parent:
- `missing_fixed` = fixed ids not in keys -> status `"incompatible"` (deadlock expected). Skip when `skip_incompatible` (default), else run and let the stall metrics show it.
- `missing_other` = optional/pool/weave/pre-combat ids not in keys -> keep the variant, attach a warning "Rotation entries X, Y are not in this loadout and will be skipped".

### 5.4 Successive halving (rounds)

State in `kind_state`: `{"schedule": {...}, "target_n": initial}`.

- Round 0: every active variant gets `(0, initial)`.
- After each round (in `next_jobs`):
  1. Rank active variants by mean DPS.
  2. Survivors: the top `ceil(keep_fraction * k)` **plus** any variant whose paired difference to the leader is not significant (`not compare(...)["significant"]`), **plus** `current` (always kept so every finalist has a delta vs current; it never counts toward the survivor limit and is never eliminated).
  3. Ensure at least `min_survivors` (excluding current) when available.
  4. Mark the rest `status = "eliminated"`, `meta.eliminated_round = round`.
  5. If survivors (excluding current) `<= min_survivors` and the leader is significantly ahead of the second, or `target_n >= max`, stop (`[]`).
  6. Otherwise `target_n = min(2 * target_n, max)` and give each survivor `(n_current, target_n - n_current)` (extending the same seed sequence).
- `finalize`: every variant with its status, summary, `vs_current` (paired on shared seeds; eliminated variants still have their round-0 seeds in common with current), rank among finalists, diff text, warnings. Include for the top 3 finalists the full ability breakdown? Optional: a final small job with `lean=False` would need extra plumbing; skip in v1 and tell the user to Apply + run a batch for details.

### 5.5 UI

- Button `Top Gear` in section 2 (next to the tactical select or at the end of the section).
- Modal `topGearModal`:
  - Lists built from data already loaded in the page. `updateClassGearOptions` (around line 2058) does not keep the tactical/legendary lists in a variable; it writes them into the selects. So read tacticals from `document.getElementById("tacticalSelect").options` and legendaries from `legendary1Select.options` (skip the empty "(None)" option), the skill tree from the global `CURRENT_SKILL_TREE` (set by the same function), relics from `CATALOG.relics`, adrenals from `CATALOG.adrenals` (`CATALOG` is set in `loadCatalog`, around line 1667).
  - Relic list is long: add a text filter box above it.
  - Live estimate: call a cheap endpoint? Not needed: compute the variant count in JS with the same rules (one_axis: 1 + sum(n_i - 1); cartesian: product), and show `max fights <= variants * schedule.max` (upper bound) and `typical ~ variants * initial * 2`.
- Results tab `tabTopGear`: table as described; row hover shows warnings; "Apply" sets the selects and `CURRENT_CHOICES`, re-renders the skill tree drawer, refreshes the computed stats. A note under the table: "Deltas are paired on shared seeds. 'Within noise' means the difference is smaller than its 95% CI."

### 5.6 CLI

```
.\tools\pyclean.exe main.py hatred_14gcd --top-gear axes.json [--effort quick|normal|thorough] [--json-out results.json]
```

`axes.json` contains the `options` object (section 5.1). Print an ASCII table; `--json-out` writes the raw result (only to the path the user gives).

## 6. Step-by-step implementation

Session 1:
1. Baseline tests. Plan 00 present.
2. New module `src/swtorsim/top_gear.py` with `build_top_gear_variants`, `rotation_ability_ids`, `loadout_ability_keys`, `TopGearKind` (registered with `experiments.register_kind`).
3. Tests for the pure functions with hand-written axes and a small fake skill tree.
4. Successive-halving logic with fake results (tests).
5. End-to-end smoke test (`cores=1`, 3 tacticals, `initial = 2`, `max = 4`, `dummy_hp = 150_000`).
6. CLI flag.
7. CHANGELOG.

Session 2:
8. UI modal, estimate, results tab, Apply.
9. Browser checks native + WASM.
10. Docs, CHANGELOG.

## 7. Tests

New file `tests/test_top_gear.py`:
- `test_one_axis_count`: 3 tacticals (incl. current), pool of 4 legendaries (6 pairs incl. current), 2 relic pairs, 1 skill level with 3 options -> `1 + 2 + 5 + 1 + 2 = 11` variants.
- `test_cartesian_refuses_over_cap`: error message contains the count.
- `test_pairs_are_unordered_and_deduped`.
- `test_legendary_fixed_pairs`.
- `test_current_variant_is_first_and_has_empty_diff`.
- `test_rotation_ability_ids_walks_all_step_kinds` (fixed, optional, priority pool, weave, pre_combat).
- `test_loadout_ability_keys_matches_build_ability_db`: for a real loadout, keys equal the keys of `Player.build_ability_db(active_abilities)` built the same way `prepare_simulation` does.
- `test_missing_fixed_marks_incompatible`.
- `test_halving_keeps_current_and_ties` (fake results where two variants are within noise of the leader -> both survive).
- `test_halving_stops_at_max`.
- `test_top_gear_smoke` (end to end, tiny).

## 8. Verification

1. Full suite passes.
2. On `hatred_14gcd`: one-axis over 3 tacticals at Normal effort. Then run a plain 640-iteration batch for the winner and for current with the same seed and confirm the delta matches the Top Gear delta within CI.
3. A deliberately incompatible case: vary a skill level whose option replaces an ability used by a fixed step in the rotation (find one with the Rotation Builder) and confirm the variant shows "rotation incompatible".
4. Cancel works mid-round; the UI recovers.
5. WASM: same request, same numbers.

## 9. Docs

- `docs/user_guide.md`: "Top Gear" section (what is compared, what "within noise" means, the rotation-compatibility caveat).
- `ARCHITECTURE.md`: `swtorsim/top_gear.py` row; UI functions; CLI flag.
- `CHANGELOG.md`.

## 10. Done when

- [ ] Variants build correctly for all axes and both modes, with caps and dedupe.
- [ ] Incompatible rotations are detected before running.
- [ ] Successive halving keeps current, ties and the leader; stops at the cap.
- [ ] UI modal, estimate, results, Apply; CLI; WASM parity.
- [ ] Tests, docs, CHANGELOG.

## 11. Open questions for the user

1. Should "All combinations" ever sample randomly when over the cap, or always refuse (plan default: refuse)?
2. Default relic pool: only relics of the current item rating family, or the whole catalog?
3. When a talent change makes a rotation incompatible, do you want an option to auto-substitute the replacement ability (for example `assassinate` -> `assassinate+`)? The plan does not do it because it would be a rotation edit; it would need its own rules.
