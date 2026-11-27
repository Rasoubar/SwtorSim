# Plan 09: Rotation Tuner

Status: proposed. Size: L (three sessions: mutations, search, UI). Risk: low (no engine change; it only edits rotations in memory). Depends on plan 00 (experiments, `rotation_inline`); plan 08 recommended.

## 1. Summary (for humans)

Writing a priority rotation is the hardest part of using the simulator, and small details matter: is Assassinate better above or below Thrash in this block? Should Recklessness wait until the target is above 30% HP or 25%? Is "energy below 70" the right threshold?

The **Rotation Tuner** tries those small edits automatically. Starting from your rotation it:

1. builds every **single small change** ("neighbor"): swap two neighbouring entries in a priority block, nudge a numeric rule threshold up or down, drop an optional step or weave entry;
2. tests all neighbors briefly on the same seeds as the current rotation;
3. re-tests the most promising few for longer;
4. accepts the best one only if it is **significantly** better, and repeats from there;
5. finally re-tests the original and the tuned rotation on **fresh seeds** it never used during the search, so you get an honest estimate (not one fitted to lucky seeds).

You get the tuned rotation, a plain-language list of what changed, the validated DPS gain, and a **Save** button that stores it as a new custom rotation. Your original file is never modified.

### What the user sees

- Simulator page, next to the Rotation File select: a **Tune...** button.
- A modal: Effort (Quick / Normal / Thorough), checkboxes for change families (Reorder priorities, Tune thresholds, Drop optional steps, Tune lead times), "Never touch the opener" (default on), an estimate, Run.
- Progress: "Generation 3 / 8: testing 34 neighbors".
- Result panel (new results tab **Rotation Tuner**): validated gain ("+1.8% +/- 0.4%, 1,000 fresh fights"), the change list, a per-generation history table, and buttons **Save as custom rotation**, **Discard**, **Open in Rotation Builder** (after saving).

## 2. Scope and non-goals

In scope: mutation operators, neighbor generation, search driver (experiment kind `"rotation_tune"`), overfitting guard, save flow, UI, CLI, tests.

Not in scope:
- Adding abilities that are not in the rotation, or inventing new rule types (search space stays "small edits of what you wrote").
- Editing `pre_combat`, `pull_conditions`, or the position of `loop_anchor`.
- Editing the opener when "Never touch the opener" is on (steps before `loop_anchor`).

## 3. Rules that apply

- Rule 11: the user's rotation file is never written. The tuned rotation is saved as a **new** custom file only when the user clicks Save.
- Rule 1: no math involved.

## 4. Current state (facts)

- Rotation format and step types: README section 7.3. Rule keys: `requirements.py :: CONDITION_REGISTRY`.
- Rule value shapes (from the validators in `src/swtorsim/requirements.py`):
  - `target_hp_below_pct`: number (0-1) or `{"pct": number, "bypass_if_buff_active": [...]}`.
  - `target_hp_above_pct`: number.
  - `caster_energy_above` / `caster_energy_below`: number (resource units).
  - `ability_cooldown_under` / `ability_cooldown_above`: `{"name": ability, "value": seconds}`.
  - `proc_cooldown_above`: `{"name": proc, "value": seconds}`.
  - `caster_buff_stacks` (and aliases), `target_debuff_stacks` (and alias): dict with one of `stacks` / `count` / `value` / `charges`, or a list `[name, stacks, comparison]`.
  - Buff/debuff presence rules: strings or lists (no numbers; not tuned).
- `lead_time` (seconds) may be set on steps and pool entries (`rotation.py`); `DEFAULT_OFF_GCD_LEAD_TIME = 0.1`, overridable per rotation by the top-level `default_lead_time`.
- `data/rotation_builder.py :: normalize_rotation_steps` (around line 714) validates/normalizes step lists and returns warnings; `build_rotation_file_data` (around line 864) writes the bare-list or wrapper form.
- Plan 00 provides `rotation_inline` (run a payload with an in-memory rotation) and experiment kinds with multi-round driving.
- Saving: `POST /api/custom_file/import` with `category: "rotations"`, `class_folder`, `spec_folder`, `filename`, `content` (native writes CRLF JSON under `data/rotations/custom/<class>/<spec>/`; WASM stores it in browser storage).
- Max resource for clamping energy thresholds: `computed_player_stats.max_resource` (from `preview_character_stats`).

## 5. Design

### 5.1 Normalized working form

Convert any rotation to a dict for editing and back on save:

```python
def to_working_form(rotation) -> dict:
    """{"sequence": [...], "weave": [...], "pre_combat": [...], "pull_conditions": {...}, "pull_max_wait": x} (deep copy)."""

def from_working_form(work: dict):
    """Inverse; uses data.rotation_builder.build_rotation_file_data so saved files match the Builder's format."""
```

### 5.2 Mutation model (`src/swtorsim/rotation_mutations.py`, new, pure)

A mutation is a small JSON object so it can be stored in experiment state and shown to users:

```json
{"op": "swap_pool", "step": 7, "i": 2}
{"op": "set_rule_value", "path": ["sequence", 7, "pool", 3, "rules", "caster_energy_below"], "from": 70, "to": 60}
{"op": "drop_step", "step": 12}
{"op": "drop_weave", "index": 0}
{"op": "set_lead_time", "path": ["sequence", 5, "lead_time"], "from": 0.4, "to": 0.2}
```

Functions:

```python
def apply_mutation(work: dict, m: dict) -> dict:
    """Returns a new working form with m applied (input unchanged); raises ValueError if m no longer applies."""

def describe_mutation(work: dict, m: dict, names: dict[str, str]) -> str:
    """Plain-language text, e.g. "Block 'Main Priority': Assassinate now above Thrash"."""

def neighbors(work: dict, options: dict, max_resource: float) -> list[dict]:
    """Every single mutation allowed by options, in a deterministic order."""
```

Neighbor generation rules (`options` toggles each family):

- **swap_pool** (Reorder priorities): for every `priority_block` step `s` in the editable range and every `i` in `0 .. len(pool) - 2`, swap entries `i` and `i + 1`. Skip swaps of two entries with the same `ability_id` and identical rules (no-op).
- **set_rule_value** (Tune thresholds): for every numeric rule value in editable steps, pool entries and weave entries:
  - `caster_energy_above` / `caster_energy_below`: candidates `v - 20, v - 10, v + 10, v + 20`, clamped to `[0, max_resource]`, rounded to integers.
  - `target_hp_below_pct` / `target_hp_above_pct` (number or `pct` inside the dict form): `v - 0.10, v - 0.05, v + 0.05, v + 0.10`, clamped to `[0.01, 0.99]`, rounded to 2 decimals.
  - `ability_cooldown_*`, `proc_cooldown_above` (`value`): `v - 1.0, v - 0.5, v + 0.5, v + 1.0`, clamped to `>= 0`, 1 decimal.
  - stack rules (`stacks` / `count` / `value` / `charges`, or list index 1): `v - 1, v + 1`, clamped to `>= 0`, integers.
  - Drop candidates equal to the current value or duplicates after clamping.
- **drop_step** (Drop optional steps): every `optional` step in the editable range; never `fixed`, `priority_block` or `loop_anchor`.
- **drop_weave**: every weave entry.
- **set_lead_time** (off by default): steps and pool entries that already have `lead_time`: `v - 0.2, v - 0.1, v + 0.1, v + 0.2`, clamped to `[0, 1.5]`.

Editable range: steps from the `loop_anchor` index to the end when "Never touch the opener" is on; all steps otherwise.

Validation of every neighbor: `normalize_rotation_steps(from_working_form(new)["sequence"] or the list)` must return no new warnings; otherwise discard it (log in `kind_state.discarded`).

### 5.3 Search (experiment kind `"rotation_tune"`, `src/swtorsim/rotation_tuner.py`)

Request:

```json
{
  "kind": "rotation_tune",
  "payload": { "...current simulate payload (rotation_path = the rotation to tune)..." },
  "options": {
    "effort": "normal",
    "families": {"swap_pool": true, "set_rule_value": true, "drop_step": true, "drop_weave": true, "set_lead_time": false},
    "protect_opener": true,
    "max_neighbors": 40,
    "rng_seed": 7
  }
}
```

Effort presets (`n_screen` fights per neighbor in the screening round, `top_k` re-tested, `n_confirm` extra fights for them, `generations` max, `n_validate` fresh fights at the end):

| Effort | n_screen | top_k | n_confirm | generations | n_validate |
|---|---|---|---|---|---|
| Quick | 30 | 3 | 120 | 4 | 300 |
| Normal | 60 | 5 | 240 | 8 | 1000 |
| Thorough | 100 | 8 | 400 | 12 | 2000 |

State (`kind_state`):

```text
{
  "work_current": <working form>, "work_original": <working form>,
  "applied": [mutation, ...],              # accepted so far, in order
  "generation": 0, "phase": "screen" | "confirm" | "validate" | "done",
  "current_vid": "<variant id of current best>",
  "candidates": {"<vid>": {"mutation": {...}, "work": {...}}},
  "history": [{"generation", "neighbors", "best_gain", "accepted": mutation | null}],
  "seed_offset_validate": 1000000
}
```

Variants: every rotation version is a variant whose payload = base payload + `rotation_inline = from_working_form(work)`. Variant id = `payload_fingerprint` of that payload (plan 00), so the same rotation reached twice is evaluated once.

Rounds (`next_jobs`):

1. **Generation start (screen)**: if the current variant has fewer than `n_screen` fights, extend it. Build `neighbors(work_current)`; if more than `max_neighbors`, take a deterministic sample with `random.Random(rng_seed + generation).sample(...)`. Each neighbor gets `(0, n_screen)` (same seeds as current).
2. **Confirm**: rank neighbors by paired mean difference vs current; take the best `top_k` with a positive difference. If none, go to validate. Extend those and the current variant to `n_screen + n_confirm` fights (`start = n_current`).
3. **Accept**: among confirmed neighbors, choose the largest paired difference with `significant == True` **and** no more deadlocked runs than current. If found: append its mutation to `applied`, set `work_current`, `current_vid`, `generation += 1`, record history; go to 1 (until `generations` reached). If not found: go to validate.
4. **Validate**: two variants, original and final, each `(seed_offset_validate, n_validate)` (run ids starting at 1,000,000, so seeds were never used in the search). Plan 00's `append_runs` stores them in the same columns; mark them by seed range in `finalize`.
5. Done -> `[]`.

`finalize`:

```json
{
  "kind": "rotation_tune",
  "validated": {"original_mean": 31000.1, "tuned_mean": 31560.4, "diff": 560.3, "ci95": 120.2, "diff_pct": 1.81, "significant": true, "n": 1000},
  "changes": ["Block 'Reck+DF+MPRIO1 Window 1': Assassinate now above Death Field", "Step 6 optional 'Recklessness': target_hp_above_pct 0.3 -> 0.25"],
  "applied": [ {...mutations...} ],
  "history": [ {...} ],
  "tuned_rotation": [ "...rotation JSON in file form..." ],
  "warnings": ["2 neighbors discarded as invalid"]
}
```

If the validated difference is not significant, say so plainly in the UI ("No reliable improvement found; the search gain did not hold on fresh seeds") and do not offer Save by default (offer "Save anyway").

Budget estimate (for the modal): `fights <= generations * (max_neighbors * n_screen + top_k * n_confirm) + 2 * n_validate`.

### 5.4 Save flow

- Filename suggestion: `<original stem>_tuned.json`; if it exists, `_tuned_2`, ...
- `POST /api/custom_file/import` with `category: "rotations"`, `class_folder` / `spec_folder` from the current spec (same folder logic the Rotation Builder uses: `rotation_folder_defaults(spec_path)` in `data/rotation_builder.py`), `content: tuned_rotation`.
- Reload the catalog and select the new rotation.
- "Open in Rotation Builder" uses the existing launcher (`/api/launch_rotation_builder`) and passes the path if the builder supports it (check its query parameters; otherwise just open it).

### 5.5 CLI

```
.\tools\pyclean.exe main.py hatred_14gcd --tune-rotation [--effort quick|normal|thorough] [--save-as <filename>]
```

Prints progress per generation and the final report in ASCII. `--save-as` writes under `data/rotations/custom/<class>/<spec>/` only when given (the user asked for it by passing the flag).

## 6. Step-by-step implementation

Session 1 (mutations, pure):
1. Baseline tests. Plan 00 present.
2. `rotation_mutations.py`: working form, `apply_mutation`, `describe_mutation`, `neighbors`, validation through `normalize_rotation_steps`.
3. Tests (section 7, first group) using `data/rotations/assassin/hatred/BasicMaliPS.json` and `data/rotations/marauder/carnage/basic_priority.json` loaded read-only.

Session 2 (search):
4. `rotation_tuner.py`: kind with the phases above, registered with plan 00.
5. Tests with a **fake evaluator**: run the driver loop (`start_experiment` / `advance_experiment`) in the test, but instead of running fights, produce job results from a function `fake_dps(work, seed)` that rewards a known mutation (for example, swapping pool entries 0 and 1 of block 3 adds +100 DPS, everything else +0 with noise from `random.Random(seed)`). The tuner must find and accept that mutation and nothing else.
6. Smoke test with real fights: Quick effort but overridden tiny numbers (`n_screen = 2`, `generations = 1`, `n_validate = 2`, `max_neighbors = 3`), `dummy_hp = 150_000`, `cores = 1`.
7. CLI.

Session 3 (UI):
8. Tune modal, progress, Rotation Tuner tab, Save flow.
9. Manual checks native and WASM; docs; CHANGELOG.

## 7. Tests

`tests/test_rotation_mutations.py`:
- `test_working_form_round_trip` (bare list and wrapper files).
- `test_swap_pool_neighbors_count` (block with 9 entries -> 8 swaps, minus no-op duplicates).
- `test_threshold_candidates_clamped_and_rounded` (energy at 10 -> no negative values; hp pct near 0.95 -> max 0.99).
- `test_dict_form_target_hp_rule_tuned_inside_pct`.
- `test_stack_rule_list_and_dict_forms`.
- `test_protect_opener_excludes_steps_before_anchor`.
- `test_apply_mutation_does_not_mutate_input`.
- `test_describe_mutation_texts`.
- `test_every_neighbor_normalizes_without_new_warnings`.

`tests/test_rotation_tuner.py`:
- `test_finds_planted_improvement_with_fake_evaluator`.
- `test_rejects_insignificant_gain` (planted gain of +5 DPS with noise SD 500 -> nothing accepted).
- `test_rejects_variant_with_more_deadlocks` (fake results where the best neighbor deadlocks).
- `test_validation_uses_fresh_seed_range` (validation run ids start at 1,000,000).
- `test_same_rotation_reached_twice_is_evaluated_once` (fingerprint dedupe).
- `test_smoke_real_fights_tiny`.

## 8. Verification

1. Full suite passes.
2. Run Normal effort on `hatred_14gcd` natively; check the reported changes make sense when read, and that the validated gain is consistent with a manual check: save the tuned rotation, run a 1,000-fight batch of each rotation with a seed not used in the search (for example 9999), and compare.
3. Confirm the original rotation file's bytes are unchanged (hash before/after).
4. Cancel mid-search; UI recovers; nothing saved.
5. WASM: Quick effort run completes (slower is fine) and matches native numbers for the same request.

## 9. Docs

- `docs/user_guide.md`: "Rotation Tuner" section (what it changes, effort presets, why the validated number can be smaller than the search number, that nothing is saved without clicking Save).
- `ARCHITECTURE.md`: rows for `swtorsim/rotation_mutations.py` and `swtorsim/rotation_tuner.py`; UI functions; CLI flag.
- `CHANGELOG.md`: one entry per session.

## 10. Done when

- [ ] Mutations cover the families above, are validated, deterministic and described in plain language.
- [ ] The tuner finds a planted improvement and rejects noise (fake evaluator tests).
- [ ] Validation on fresh seeds is reported; Save writes only a new custom file on request.
- [ ] Works natively, in WASM and from the CLI.
- [ ] Tests, docs, CHANGELOG.

## 11. Open questions for the user

1. Should the tuner also try **moving** an entry more than one position (larger search space, slower), or are adjacent swaps enough for v1?
2. Should tuned rotations be validated across several dummy HP values (for example 1M, 6M, 10M) to avoid rotations that only win on one fight length? (Adds cost; suggested as an option, off by default.)
3. Is dropping optional steps acceptable as a suggestion, or should the tuner only reorder and retune?
