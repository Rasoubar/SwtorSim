# Plan 05: Combat Log Import and Parity Report

Status: proposed. Size: M-L (four phases, one session each). Risk: low (reads logs, never changes math). Independent of other plans.

## 1. Summary (for humans)

The simulator's combat math was validated against real game combat logs, but the tools that did it (`tools/parse_combat_log.py`, `tools/validate_modifiers_vs_log.py`) were never committed (see `TODO.md`, "Restore Missing Tools"). This plan rebuilds them properly and makes log comparison a first-class feature:

1. **Parser** (in `src/swtorsim/`, so it also runs in the browser build): reads a SWTOR combat log (`combat_*.txt`), splits it into fights, and computes per-ability statistics: casts, hits, crit rate, average normal hit, average crit hit, damage share, DoT tick spacing, plus buff uptimes.
2. **Parity report**: picks a fight from the log, runs the simulator with the same fight length and target HP, and shows Log vs Sim side by side with the differences highlighted, but only where the sample is large enough to mean something.
3. **Modifier ratio validator** (CLI): the method the original tool used, rebuilt from its recovered design. It compares how much a buff/debuff raises one ability's hits in the log with what the sim's modifier model predicts.
4. **Optional ID mapping**: if log ability IDs turn out to match the extractor's node IDs, match abilities by ID instead of by English name.

### What the user sees

- A new results tab **Log Parity** with a file picker ("Load combat log..."). After loading: a list of fights (start time, duration, main target, total damage, DPS); select one and click **Compare with current setup**.
- A table per ability: Log value | Sim value | Difference, for Damage share, Crit %, Avg normal hit, Avg crit hit, Crit multiplier, Casts per minute, Avg DoT tick interval. Cells are green/amber/red by how far apart they are, grey when the sample is too small.
- A buff uptime table (Log vs Sim).
- CLI: `.\tools\pyclean.exe tools/parse_combat_log.py <log.txt>` prints a quick per-ability summary; `.\tools\pyclean.exe tools/validate_modifiers_vs_log.py <log.txt> <config.json>` runs the ratio test.

## 2. Scope and non-goals

In scope: parser, analysis, sim comparison, UI tab, two CLI tools, optional ID mapping, tests with synthetic log lines.

Not in scope:
- Uploading logs anywhere. Everything stays on the user's machine.
- Changing any formula because a comparison differs. Differences are **reported as evidence** to the user (AGENTS.md rule 1: "Suspect a formula? Assume bad inputs first; otherwise report evidence to the user and stop").
- Healing / tanking analysis.

## 3. Rules that apply

- Rule 1 (frozen math): the validator *calls* `combat_math.handle_modifiers` to compute a predicted multiplier; it must not modify it.
- Rule 3: the validator's config uses stat IDs; they must come from `src/extractor/mod_stats.py` (or the user's `Stat_IDs.xlsx`, which is not in the repo).
- Rule 11: if ID mapping needs extractor output, change the extractor and ask the user to re-extract; do not edit `data/extractor/`.
- Privacy: logs contain character names. Never put a real log in the repo (tests use synthetic lines), never send it to an external service.

## 4. Current state (facts)

### 4.1 What the original tools looked like (recovered)

The compiled files `tools/__pycache__/parse_combat_log.cpython-313.pyc` and `tools/__pycache__/validate_modifiers_vs_log.cpython-313.pyc` still exist. Their constants were read without executing them. Recovered facts:

`parse_combat_log.py` docstring:

```
Minimal SWTOR combat log parser (live logs: combat_*.txt).

Line shape:
  [ts] [source] [target] [ability {id}] [EventType {id}: EventName {id}] (value ...) <threat>
Crits are flagged by a '*' right after the damage number, e.g. (1234* energy {id}).
```

Regexes:

```python
_LINE_RE = re.compile(r'^\[(?P<ts>[\d:.]+)\] \[(?P<src>[^\]]*)\] \[(?P<tgt>[^\]]*)\] \[(?P<abl>[^\]]*)\] \[(?P<evt>[^\]]*)\](?: \((?P<val>[^)]*)\))?')
_ID_RE = re.compile(r'\s*\{\d+\}')
_VAL_RE = re.compile(r'^(?P<num>\d+)(?P<crit>\*)?')
```

Structure: `LogEvent` dataclass with fields `source, target, ability, event_type, event_name, value, is_crit`; functions `_entity_name(raw)`, `parse_line(line)`, `iter_events(lines)`, `parse_log_file(path)` (opened with `encoding="utf-8", errors="replace"`), `analyze_fight(events)` ("Per-(source, ability) damage totals; quick sanity view of a log", counting `hits`, `crits`, `total` for `ApplyEffect` / `Damage` events).

`validate_modifiers_vs_log.py` docstring (verbatim):

```
Validate sim modifier multipliers against a live SWTOR combat log.

Method (ratio test):
  1. Replay ApplyEffect/RemoveEffect events to know which tracked buffs (on the player)
     and debuffs (on the hit target) are active at every damage hit of one ability.
  2. Group NON-crit hits by active tracked-effect set; compute each group's mean hit.
  3. live_ratio = mean(group) / mean(reference group).
     sim_ratio  = total_multiplier(group) / total_multiplier(reference), computed by
     combat_math.handle_modifiers with the modifiers declared in the config.
  4. PASS when |live_ratio / sim_ratio - 1| <= tolerance + 2 * relative standard error.
Weapon damage, stats and armor cancel out of the ratio (armor pen changes excepted).

Config JSON:
{
  "player": "Name",                      # optional, else most frequent damage source
  "ability": "Force Lightning",          # log ability name
  "attack_type": 3, "damage_type": 2,    # 1 melee 2 ranged 3 force 4 tech / 1 kin 2 en 3 elem 4 int
  "tags": [], "ability_fqn": "x.y.z",    # optional
  "tolerance": 0.03, "min_samples": 10,
  "reference": [],                       # optional effect-name set used as baseline
  "effects": {
    "Recklessness": {"on": "caster", "modifiers": [{"stat": "79", "value": 0.10}]},
    "Sundered":     {"on": "target", "modifiers": [{"stat": "79", "value": 0.05}]}
  }
}
Stat ids must come from Stat_IDs.xlsx / mod_stats.py; values are decimal fractions.

Usage: pyclean.exe tools/validate_modifiers_vs_log.py <log.txt> <config.json>
```

Functions: `_entity(effects, names, hp_ratio)` ("Stub entity carrying one buff per active tracked effect name", building `Modifier` objects and a `SimpleNamespace`), `sim_multiplier(cfg, caster_names, target_names)` (calls `handle_modifiers` and reads `total_multiplier`), `collect_groups(events, cfg)` (returns `{(frozenset caster_effects, frozenset target_effects): [non-crit hit values]}`), `compare(groups, cfg)` (uses `statistics.fmean`, a `rel_se(vals)` helper with `statistics.stdev / sqrt(n) / fmean`, `math.hypot`, statuses `SKIP` / `FAIL`), `_fmt(key)` (`caster{...} target{...}`), `report(ref_key, ref_n, rows)` (prints `[OK]` / `[WARN] ... too few samples` / `[FAIL]` with `live=`, `sim=`, `err=` as `+.2%`, `(allowed +/-...)`), `main(argv)` (prints `[FAIL] need at least two distinct buff states for this ability in the log` when only one group exists).

### 4.2 Relevant simulator facts

- Sim per-ability rows (`web_gui.py :: _format_ability_breakdown_rows`, around line 660) have `total_damage`, `dps`, `share_pct`, `hits`, `crits`, `crit_pct`, `avg_hit` (normal and crit hits mixed), and in TEST mode `min_hit`, `max_hit`, `casts`. There is **no separate normal-hit mean or crit-hit mean**.
- `Metrics._record_hit` (`src/swtorsim/metrics.py`, around line 142) accumulates per ability: `total_damage`, `hit_count`, `crit_count`, types. Adding `crit_damage` there is a telemetry change (allowed; not combat math).
- Sim ability names are the blueprint display names (English), the same names the English game client writes into logs.
- Raw extracted ability JSON has a node `id` (for example `data/extractor/live/extracted/abl/sith_inquisitor/assassinate.json`: `"id": "16141010231170334810"`), but parsed blueprints (`data/extractor/live/parsed/...`) have no id field. The extractor knows it as `record.entry.node_id` (`src/extractor/abilities.py :: build_id_to_fqn`, around line 236). **It is unknown whether the combat log's `{id}` for an ability equals this node id.** Phase D checks that before using it.

## 5. Design

### 5.1 Log line grammar (to verify against a real log)

```
[HH:MM:SS.mmm] [SOURCE] [TARGET] [ABILITY] [EFFECT] (VALUE) <THREAT>
```

- `SOURCE` / `TARGET`: empty, `=` (same as source), or `NAME|(x,y,z,facing)|(hp/maxhp)` where `NAME` is
  - a player: `@Name#123456789012345`,
  - a companion: `@Owner#.../Companion Name {id}:instance`,
  - an NPC: `Operations Training Dummy {id}:instance`.
- `ABILITY`: empty or `Ability Name {id}`.
- `EFFECT`: `EventType {id}: EffectName {id}` e.g. `ApplyEffect {...}: Damage {...}`, `Event {...}: AbilityActivate {...}`, `Event {...}: EnterCombat {...}`, `Event {...}: ExitCombat {...}`, `ApplyEffect {...}: Recklessness {...}`, `RemoveEffect {...}: Recklessness {...}`, `Spend {...}: force {...}`, `DisciplineChanged {...}: Sith Assassin {...}/Hatred {...}`, `AreaEntered {...}: ...`.
- `VALUE` for damage: `amount[*][ ~effective] [dmgtype {id}][ -mitigation {id}][ (N absorbed {id})]`, e.g. `(1234* energy {id})`, `(0 -miss {id})`, `(1500 ~1200 internal {id})`.
- `THREAT`: `<1234.0>` (ignore).

Parse defensively:
- Use the recovered `_LINE_RE` for the outer shape; then parse each bracket with small helpers.
- Unknown shapes are counted in `ParseStats.unparsed_lines` and `ParseStats.unknown_value_shapes`; never raise.
- Timestamps have no date: detect midnight rollover (time going backwards by more than 12 hours) and add 24 h.
- Encoding: try UTF-8; on `UnicodeDecodeError` fall back to cp1252; always `errors="replace"`.

### 5.2 Data model (`src/swtorsim/combat_log.py`, new)

```python
@dataclass(slots=True)
class LogEntity:
    name: str            # "@Name#123" -> "Name"; NPC "Operations Training Dummy"
    raw: str
    entity_id: str = ""  # NPC {id} or player number
    instance: str = ""   # NPC :instance
    is_player: bool = False
    is_companion: bool = False
    hp: float | None = None
    max_hp: float | None = None

@dataclass(slots=True)
class LogEvent:
    t: float             # seconds since log start (rollover-corrected)
    source: LogEntity | None
    target: LogEntity | None   # resolved: "=" -> same as source
    ability: str
    ability_id: str
    event_type: str      # "ApplyEffect", "RemoveEffect", "Event", "Spend", ...
    event_name: str      # "Damage", "AbilityActivate", "EnterCombat", effect names...
    event_name_id: str
    amount: float | None
    effective: float | None
    is_crit: bool
    damage_type: str     # "kinetic" | "energy" | "internal" | "elemental" | ""
    mitigation: str      # "miss" | "dodge" | "parry" | "deflect" | "immune" | "resist" | "shield" | "glance" | ""
    absorbed: float | None

def parse_line(line: str, prev_t: float | None = None) -> LogEvent | None: ...
def parse_log_text(text: str) -> tuple[list[LogEvent], dict]:   # events, parse_stats
def split_fights(events: list[LogEvent], player_name: str | None = None) -> list[dict]: ...
def analyze_fight(events: list[LogEvent], fight: dict) -> dict: ...
```

### 5.3 Fight segmentation

- Player: the most frequent `source` with `is_player` among `Damage` events (or the user's choice).
- A fight starts at `EnterCombat` (source = player) and ends at the next `ExitCombat` (or at the player's death, or at the log's end).
- Fight time window for statistics: from the player's **first damage event** to the **last damage event** inside the fight (StarParse convention for dummies; avoids counting the pre-pull).
- Main target: the target that received the most damage from the player. Record its `max_hp` from the target field.
- Discard fights shorter than 10 s or with fewer than 20 damage events (configurable).
- Fight summary: `{index, start_clock, duration, player, main_target, main_target_max_hp, total_damage, dps, events: (start_idx, end_idx)}`.

### 5.4 Analysis per fight

Per ability (player as source, `Damage` events, any target; also per target for the main target only):
- `hits` = damage events that are not mitigated misses (`mitigation not in {"miss", "dodge", "parry", "deflect", "immune", "resist"}`); `misses` counted separately.
- `crits`, `crit_pct`.
- `normal_mean`, `normal_sd`, `crit_mean`, `crit_sd` (on `amount`, not `effective`; note in the UI that the log's `amount` is pre-absorb).
- `crit_multiplier` = `crit_mean / normal_mean` (when both have at least 5 samples).
- `total`, `share_pct` (of the player's total in the window), `dps`.
- `casts` = `Event: AbilityActivate` with that ability name by the player in the window; `casts_per_min`.
- DoT tick spacing: for abilities with at least 5 damage events that are not within 0.05 s of an `AbilityActivate` of the same name, compute the median gap between consecutive damage events on the same target (gaps > 6 s ignored). Label "approximate".

Buff uptime (player target): from `ApplyEffect` / `RemoveEffect` with `target` = player, union of intervals per effect name inside the window, divided by the window length.

### 5.5 Parity comparison

```python
def build_sim_payload_for_fight(base_payload: dict, fight: dict) -> dict:
    """Copies the form payload and sets duration = ceil(fight.duration) + 5 and dummy_hp = main target max HP."""
```

- Use BATCH with 100 iterations (default) for stable sim means; TEST mode cannot give normal/crit means per ability with error bars.
- Needs the sim to report per ability `normal_mean` / `crit_mean`: add `crit_damage` accumulation to `Metrics._record_hit` and carry it through `_batch_worker_task` summaries and `_aggregate_batch_results` / `_format_ability_breakdown_rows` as new optional row fields `avg_normal_hit`, `avg_crit_hit` (`(total - crit_damage) / (hits - crits)` and `crit_damage / crits`). This only adds fields; existing fields stay identical.
- Join by ability name (exact, case-insensitive). Unmatched names are listed separately on both sides (common causes: procs with different names, abilities missing from the sim).
- Difference rules (per metric):
  - Crit %: difference in percentage points; flag when `abs(diff) > 2 * sqrt(p * (1 - p) / n_log)` (binomial SE of the log sample) and n_log >= 30.
  - Avg normal hit, avg crit hit: relative difference; flag when `abs(diff) > max(0.02, 2 * sd_log / sqrt(n_log) / mean_log)` and n >= 10.
  - Crit multiplier: relative difference; same rule using the crit sample.
  - Damage share and casts/min: show the difference; no significance flag (they depend on the rotation, which may legitimately differ from what the player pressed).
  - Grey "n too small" cells below the thresholds.
- Endpoint: `POST /api/combat_log/parse` with `{"text": "<log text>"}` -> `{"fights": [...], "parse_stats": {...}, "session_id": "..."}`. Keep the parsed events in a small in-memory cache keyed by `session_id` (max 2 logs) so the compare call does not resend the text. `POST /api/combat_log/compare` with `{"session_id", "fight_index", "payload", "iterations"}` -> `{"fight": {...}, "log": {...}, "sim": {...}, "rows": [...], "buffs": [...], "unmatched": {...}}`.
- Size guard: refuse texts above 150 MB with a clear error.
- WASM: bridge actions `PARSE_COMBAT_LOG` and `COMPARE_COMBAT_LOG` (the cache lives in worker 0's Python module state; the compare action must therefore go to worker 0: use `callPrimaryWorker`). For the sim part in WASM, call the existing batch path from JS instead (`executeBatchMultiCore`) and then pass the batch result to a `COMPARE_COMBAT_LOG` variant that accepts a ready `sim_result`. Simplest uniform design: `compare` takes either `payload` (native runs the batch itself) or `sim_result` (already computed).

### 5.6 Modifier ratio validator (CLI)

Rebuild `tools/validate_modifiers_vs_log.py` per the recovered design (section 4.1), using `src.swtorsim.combat_log` for parsing instead of the old tools module. Keep the same config format and output lines so the user's old configs keep working. Notes for the rebuild:
- Effects active at a hit: replay `ApplyEffect` / `RemoveEffect` in time order, tracking only effect names listed in `cfg["effects"]`, separately on the player and on the hit target.
- `sim_multiplier`: build stub caster/target objects carrying one effect per active tracked name, each with `Modifier(stat=..., value=..., targets=frozenset(...), is_percent=...)` from the config, then call `combat_math.handle_modifiers(...)` exactly as the module expects (read its signature at implementation time) and read `total_multiplier`. Pass `is_percent` explicitly from the config; the original config format implies decimal fractions (`0.10` = 10%), so default `is_percent` to `True` **only if** the user confirms (open question 2); never infer it from the magnitude (rule 2).
- Statistics: `rel_se(vals) = stdev(vals) / sqrt(n) / fmean(vals)`; combined error for a ratio of two groups `math.hypot(rel_se_group, rel_se_ref)`; PASS when `abs(live_ratio / sim_ratio - 1) <= tolerance + 2 * combined_rel_se`; SKIP (`[WARN] ... too few samples`) when a group has fewer than `min_samples` hits.

### 5.7 Optional ID mapping (Phase D)

1. Ask the user for a real log (they keep it local; read it from wherever they put it).
2. For three abilities (for example Assassinate, Thrash, Discharge), compare the log's `{id}` with `"id"` in `data/extractor/live/extracted/abl/**/<ability>.json`.
3. If they match: change `src/extractor/abilities.py :: _build_ability_payload` (around line 2059) to also write `"node_id": record.entry.node_id`; ask the user to re-extract Live and PTS; read `node_id` in the parity join (ID first, name second).
4. If they do not match: stop, report, and keep name matching.

## 6. Step-by-step implementation

Phase A (parser + CLI):
1. Baseline tests. Ask the user for a sample log path (they may decline; synthetic tests still work).
2. `src/swtorsim/combat_log.py`: data classes, `parse_line`, `parse_log_text`, `split_fights`, `analyze_fight`.
3. `tools/parse_combat_log.py`: thin CLI over the module (prints fights and per-ability table in ASCII). Mirror the original module-level API names (`parse_line`, `iter_events`, `parse_log_file`, `analyze_fight`) as wrappers so old habits work.
4. Tests (section 7). If the user provided a log, run the CLI on it and report `parse_stats` (unparsed line count) before going further; fix the parser until unparsed lines are explained.
5. Update `TODO.md` "Restore Missing Tools": remove `tools/parse_combat_log.py` from the list (keep the others). CHANGELOG.

Phase B (parity UI):
6. `Metrics._record_hit` `crit_damage`; carry it through batch summaries and rows (`avg_normal_hit`, `avg_crit_hit`). Same-seed identity check on existing fields.
7. Endpoints and bridge actions (section 5.5); comparison function `compare_fight_to_sim(log_analysis, sim_result) -> rows`.
8. UI tab "Log Parity": file input (`accept=".txt"`), read with `File.text()`, POST, fight list, compare button, results tables, color legend.
9. CHANGELOG.

Phase C (validator):
10. `tools/validate_modifiers_vs_log.py` per section 5.6. Ask open question 2 first.
11. Tests with synthetic groups (no real log). Update `TODO.md` (remove the validator from the missing list). CHANGELOG.

Phase D (optional ID mapping): section 5.7.

## 7. Tests

New file `tests/test_combat_log.py` with synthetic lines built in the test (no real names; use `@Tester#1`):

```python
DMG = "[12:00:01.000] [@Tester#1|(0,0,0,0)|(50000/50000)] [Operations Training Dummy {111}:1|(1,1,0,0)|(4990000/5000000)] [Assassinate {222}] [ApplyEffect {333}: Damage {444}] (10000* energy {555}) <10000.0>"
```

- `test_parse_damage_line_crit_and_type`: amount 10000, crit True, damage_type "energy", source name "Tester", target max_hp 5,000,000.
- `test_parse_miss_line`: `(0 -miss {666})` -> mitigation "miss", not a hit.
- `test_parse_effective_amount`: `(1500 ~1200 internal {7})` -> amount 1500, effective 1200.
- `test_equals_target_resolves_to_source`.
- `test_unparsed_line_is_counted_not_raised`.
- `test_midnight_rollover`.
- `test_split_fights_enter_exit_and_window_from_first_damage`.
- `test_analyze_counts_casts_and_crit_rate`.
- `test_dot_tick_spacing_median`.
- `test_buff_uptime_union_of_intervals`.
- `test_compare_flags_only_with_enough_samples` (fake log analysis and fake sim rows).
- Phase B: `test_record_hit_tracks_crit_damage` and `test_rows_add_normal_and_crit_means_without_changing_existing_fields`.
- Phase C: `test_ratio_validator_passes_when_ratio_matches` with a fake `handle_modifiers` (mock) and synthetic groups; `test_ratio_validator_skips_small_groups`.

## 8. Verification

1. Full suite passes.
2. With a real log from the user (if available): `parse_stats.unparsed_lines` explained; a training-dummy fight's DPS matches what StarParse (or the user's parser) reported, within 0.5%.
3. Parity table on a matching build: crit multiplier and normal-hit means within the significance thresholds for the main abilities. Any red cell: report it to the user as evidence with the numbers; do not touch formulas.
4. Same-seed identity of all pre-existing batch fields after Phase B.
5. WASM: load the same log in the browser build; same fights and numbers.

## 9. Docs

- `docs/user_guide.md`: replace sections 4.2 and 4.3 (they describe the missing tools) with the new tab and the two CLIs, including the validator config format.
- `ARCHITECTURE.md`: replace the two "(MISSING from repo)" rows with real ones (`swtorsim/combat_log.py`, `tools/parse_combat_log.py`, `tools/validate_modifiers_vs_log.py`), endpoints, bridge actions.
- `TODO.md`: shrink "Restore Missing Tools" as each tool lands.
- `CHANGELOG.md`: one entry per phase.

## 10. Done when

- [ ] Parser handles the real log the user provides with all unparsed lines explained.
- [ ] Parity tab compares a fight with a batch of the current setup, with significance-aware highlighting.
- [ ] Validator CLI reproduces the original tool's method and output format.
- [ ] Optional ID mapping decided (implemented or ruled out with evidence).
- [ ] Tests, docs, TODO, CHANGELOG.

## 11. Open questions for the user

1. Can you provide one real combat log (kept local) with a few dummy parses of a config that exists in `data/run_config/`? It is needed to confirm the line grammar and for the ID check.
2. In the old validator config, were modifier `value`s always decimal-fraction percentages (`0.10` = 10%), so `is_percent` should default to `True`? (Must be confirmed, not guessed.)
3. Is your game client in English? Name matching assumes English ability names in the log.
4. Do you want the parity tab to compare against a TEST run of a specific seed as an option, or only against a batch?
