# SWTOR game-data extractor

Python script that reads raw SWTOR `.tor` (MYP) archives, extracts GOM bucket and string-table files, parses combat-relevant nodes starting from discipline entry points (`dis.*`), follows references into ability packages (`apc.*`), abilities (`abl.*`), and talents (`tal.*`), and writes a faithful intermediate JSON dump under `data/extracted/`.

Based on [extracTOR](https://github.com/SWTOR-Slicers/extracTOR) and [Jedipedia](https://swtor.jedipedia.net/).

## Usage

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

python src/extractor/main.py --assets /path/to/SWTOR/Assets
```

On first run, Jedipedia's hash list, `gom.js` name maps, and `fnv1a64.js`
stable-ID dictionary are downloaded into `data/` and refreshed when the remote
copies are newer.

Options:

- `--force-hash-update` — re-download Jedipedia hash/name data
- `--pts` — use PTS archives
- `--keep-work` — retain intermediate files in `data/extract_work/`

## Extraction graph

Traversal is a BFS seeded from all `dis.*` nodes (discipline entry points). Each discipline node references the relevant `apc.*` ability-package trees, which in turn reference `abl.*` abilities and `tal.*` talents. Only nodes whose FQN starts with `apc.`, `abl.`, `tal.`, or `dis.` are followed during the walk.

Two additional seed sources are always included:

- **Item ability trees** — not reliably reachable from player ability-package references:
  - `abl.itm.legendary`
  - `abl.itm.tactical.sow`
- **`ablAbilityReplacement`** (node ID `16141053964861013368`) — always extracted and written as a flat file at `data/extracted/ablAbilityReplacement.json`.

## Data layout

| Path | Purpose |
|------|---------|
| `data/hashes.bin` | Cached Jedipedia file hash list |
| `data/gom.js` | Cached Jedipedia GOM class/field/enum names |
| `data/fnv1a64.js` | Cached Jedipedia stable-ID names used for tag resolution |
| `data/extract_work/` | Ephemeral MYP extraction (deleted after run unless `--keep-work`) |
| `data/extracted/` | JSON dump of nodes |
| `data/extracted/index.json` | Root FQNs, node index, and cross-reference edges |
| `data/extracted/ablAbilityReplacement.json` | Global ability-replacement table (flat root file) |

Node JSON files are written under subdirectories derived from their FQN (e.g. `dis/agent/operative/concealment.json`, `abl/agent/recuperate.json`). Each file contains the node FQN, numeric ID, base class, and resolved field values.

## ID resolution

Field values of DOM type `ID` are replaced with the referenced node's FQN when that node exists in the bucket index. This applies to standalone ID fields, ID elements inside lists (e.g. `ablEffectIDs`), and ID keys/values inside lookup lists (e.g. `ablPackageAbilitiesList`). Unresolved IDs remain as their original numeric strings. Integer and other numeric field types are never resolved this way.

`NodeRef` fields are resolved to `{ref_id, fqn, base_class}` objects.

## Tag-name resolution

Ability tag values are stable IDs: unsigned 64-bit FNV-1a hashes of uppercase
names, rather than GOM node references. For example,
`tag.abl.smuggler.healing_ability` hashes to `711562958929859131`.
The extractor inverts the known `tag.*` strings published in Jedipedia's
`fnv1a64.js`. Matching hashes are written as tag names; hashes missing from
Jedipedia's dictionary remain unchanged as decimal IDs.
