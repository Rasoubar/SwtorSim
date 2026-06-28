# SWTOR game-data extractor

Python package that reads raw SWTOR `.tor` (MYP) archives, extracts GOM bucket and string-table files, parses combat-relevant nodes, and writes JSON under `data/`.

Based on [extracTOR](https://github.com/SWTOR-Slicers/extracTOR) and [Jedipedia](https://swtor.jedipedia.net/).

## Usage

Run from the repository root:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

python src/extractor/main.py --assets /path/to/SWTOR/Assets
```

On first run, Jedipedia's hash list, `gom.js` name maps, and `fnv1a64.js` stable-ID dictionary are downloaded into `data/` and refreshed when the remote copies are newer (checked via HTTP `Last-Modified`).

Options:

- `--force-hash-update` — re-download Jedipedia hash/name data
- `--pts` — use PTS (`_test_`) archives instead of live
- `--keep-work` — retain intermediate files in `data/extract_work/`

## Pipeline

1. **Archive extraction** (`extract.py`, `myp_archive.py`, `hashlist.py`) — resolve Jedipedia file hashes, read `.tor` archives, and write only combat-relevant paths into `data/extract_work/resources/`:
   - `systemgenerated/buckets.info` and `systemgenerated/buckets/*.bkt`
   - `resources/systemgenerated/client.gom`
   - `en-us/str/**/*.stb` and `resources/gamedata/str/stb.manifest`
2. **Index build** (`graph.py`, `bkt.py`, `gom/`) — parse bucket files into a node index (FQN, ID, base class, payload location).
3. **Combat graph traversal** (`graph.py`) — BFS from discipline and supplemental seeds; parse and resolve each node's fields.
4. **Raw dump** (`dump.py`) — write full resolved node JSON to `data/extracted/` plus `index.json`.
5. **Derived outputs** — build trimmed JSON consumed downstream:
   - `disciplines.py` → `data/disciplines/`
   - `talents.py`, `abilities.py` → `data/parsed/tal/`, `data/parsed/abl/`
   - `gear.py` → `data/gear_abilities_talents.json`
   - `relics.py` → `data/relics.json`

## Extraction graph

Traversal is a BFS seeded from all `dis.*` nodes (discipline entry points). Each discipline node references the relevant `apc.*` ability-package trees, which in turn reference `abl.*` abilities and `tal.*` talents. Only nodes whose FQN starts with `apc.`, `abl.`, `tal.`, or `dis.` are followed during the walk.

Reference edges are collected from:

- APC list fields (`ablPackageAbilitiesList`, `ablPackageActiveAbilitiesList`, `ablPackageConditionalAbilitiesList`, `ablPackageTalentsList`, `ablPackageSpecList`)
- `ablEffectIDs` on ability nodes
- Any node reference found anywhere on a node whose FQN is already under a combat prefix

Three additional seed sources are always included:

- **Base APC nodes** — class and combat-style bases for each origin story: `apc.<origin>.base` and `apc.<origin>.<style>.base` (eight origin stories: agent, bounty_hunter, jedi_consular, jedi_knight, sith_inquisitor, sith_warrior, smuggler, trooper)
- **Item ability trees** — not reliably reachable from player ability-package references:
  - `abl.itm.legendary`
  - `abl.itm.tactical.sow`
  - `abl.itm.relic.*.scales_with_item_rating` (rating-scaled relics only; other `abl.itm.relic.*` nodes are skipped)
- **`ablAbilityReplacementInfo`** (node ID `16141053964861013368`) — always extracted and written as a flat file at `data/extracted/ablAbilityReplacementInfo.json`

## Data layout

| Path | Purpose |
|------|---------|
| `data/hashes.bin` | Cached Jedipedia file hash list (binary; built from a transient `.txt` download) |
| `data/gom.js` | Cached Jedipedia GOM class/field/enum names |
| `data/fnv1a64.js` | Cached Jedipedia stable-ID names used for tag resolution |
| `data/extract_work/` | Ephemeral MYP extraction (deleted after run unless `--keep-work`) |
| `data/extracted/` | Full resolved node JSON dump |
| `data/extracted/index.json` | Root FQNs, node index, and cross-reference edges |
| `data/extracted/ablAbilityReplacementInfo.json` | Global ability-replacement table (flat root file) |
| `data/disciplines/<class>/<discipline>.json` | Trimmed discipline manifests (see below) |
| `data/parsed/abl/...` | Trimmed root-ability JSON (`ablAbility` nodes only) |
| `data/parsed/tal/...` | Trimmed talent JSON (`talTalent` nodes only) |
| `data/gear_abilities_talents.json` | Item display name → implant ability/talent FQN lookup |
| `data/relics.json` | Sorted list of root `abl.itm.relic.*.scales_with_item_rating` ability FQNs |

Node JSON files under `data/extracted/` are written to subdirectories derived from their FQN (e.g. `dis/agent/operative/concealment.json`, `abl/agent/recuperate.json`). Each file contains the node FQN, numeric ID, base class, and resolved field values.

Non-scaled relic abilities under `abl/itm/relic/` are excluded from the dump even if referenced during traversal.

## Derived outputs

### Disciplines (`data/disciplines/`)

One file per `dis.*` node, path derived from the FQN with the `dis.` prefix removed (e.g. `dis.specialist.tactics` → `specialist/tactics.json`).

Each file contains:

- `tab_name`, `package_name` — resolved discipline display names
- `active_abilities` — union of abilities from the class base APC, style base APC, and discipline APC (including talents from `ablPackageTalentsList`), with ability-replacement rules applied
- `skill_tree` — level → choice → ability FQN mapping from `disLevelToAbilities`

### Abilities (`data/parsed/abl/`)

One file per root `abl.*` node with base class `ablAbility`:

```json
{"fqn": "abl.agent.adrenaline_probe", "name": "Adrenaline Probe", "cooldown": 120.0}
```

### Talents (`data/parsed/tal/`)

One file per root `tal.*` node with base class `talTalent`:

```json
{
  "fqn": "tal.sith_inquisitor.skill.darkness.torment",
  "name": "Torment",
  "tags": [],
  "stat_changes": [
    {
      "name": "STAT_cbt_damage_done_if_target_accuracy_reduced_modifier_percentage",
      "value": 0.15,
      "stackable": true,
      "impact": {"type": "abl", "fqn": "abl.sith_inquisitor.lacerate"}
    }
  ]
}
```

### Gear lookup (`data/gear_abilities_talents.json`)

Flat sorted map of implant display name → ability or talent FQN, built by scanning `itm.legendary.*` and `itm.tactical.sow.*` item nodes (not part of the combat graph walk). Uses `itmEquipAbility` when present, otherwise derives the ability FQN from the item FQN (stripping `ilvl_*` segments).

### Relics (`data/relics.json`)

Sorted JSON array of root `ablAbility` FQNs matching `abl.itm.relic.*.scales_with_item_rating`.

## ID resolution

Field values of DOM type `ID` are replaced with the referenced node's FQN when that node exists in the bucket index. This applies to standalone ID fields, ID elements inside lists (e.g. `ablEffectIDs`), and ID keys/values inside lookup lists (e.g. `ablPackageAbilitiesList`). Unresolved IDs remain as their original numeric strings.

`NodeRef` fields are resolved to `{ref_id, fqn, base_class}` objects.

Enum fields are resolved to their GOM member names via `client.gom` and `gom.js`.

## STB string resolution

Some integer fields store string-table IDs rather than numeric values. These are looked up in `.stb` files under `en-us/str/`:

| Field | STB bucket |
|-------|------------|
| `disDisciplineTabName` | `gui/abl/player/skill_trees.stb` |
| `disDisciplinePackageName` | `gui/abl/player/skill_trees.stb` |

For example, `disDisciplineTabName` value `2031339142381639` on `dis.specialist.plasmatech` resolves to `"Vanguard"`. Unresolved string IDs remain as their original numeric strings.

Loc retriever fields on abilities and talents (`locTextRetrieverMap`) are resolved separately via the English language entry in their embedded lookup list. Bucket names in the retriever are aliased to on-disk STB files: `str.abl` → `abl.stb`, `str.tal` → `tal.stb`, `str.itm` → `itm.stb`. For example, `strLocalizedTextRetrieverStringID` `814776770887680` on `abl.agent.adrenaline_probe` resolves to `"Adrenaline Probe"`. Resolved fields are written as `{"loc_retriever": …, "resolved_text": "…"}`.

## Tag-name resolution

Ability tag values are stable IDs: unsigned 64-bit FNV-1a hashes of uppercase names, rather than GOM node references. For example, `tag.abl.smuggler.healing_ability` hashes to `711562958929859131`.

The extractor inverts the known `tag.*` strings published in Jedipedia's `fnv1a64.js`. Matching hashes anywhere in resolved field values are written as tag names; hashes missing from Jedipedia's dictionary remain unchanged as decimal IDs.

## Module layout

| Module | Role |
|--------|------|
| `main.py` / `cli.py` | CLI entry point and orchestration |
| `config.py` | Paths, URLs, field IDs, FQN prefix constants |
| `extract.py` | Filtered `.tor` extraction |
| `myp_archive.py` | MYP archive reader (zlib/zstd decompression) |
| `hashlist.py` | Jedipedia hash list download and binary cache |
| `gom_cache.py` / `stable_ids.py` | Jedipedia `gom.js` and `fnv1a64.js` caches |
| `gom/` | GOM name lookup and `client.gom` enum parsing |
| `bkt.py` | Bucket file parsing |
| `node.py` | GOM node field parser |
| `varint.py` / `ids.py` | SWTOR varint and 64-bit ID helpers |
| `stb.py` / `strings.py` | String-table parsing and resolution |
| `graph.py` | Bucket index, combat graph traversal, field resolution |
| `dump.py` | Raw JSON dump and index writer |
| `disciplines.py` | Discipline manifest builder |
| `talents.py` / `abilities.py` | Trimmed talent and ability writers |
| `gear.py` / `relics.py` | Gear lookup and relic list builders |
| `tools/validate_workdir.py` | Validate an existing work dir without re-reading archives |

## Validation tool

After a run with `--keep-work`, you can re-index and traverse the extracted resources without touching `.tor` archives:

```bash
python src/extractor/tools/validate_workdir.py
python src/extractor/tools/validate_workdir.py --sample-fqn abl.agent.recuperate
```
