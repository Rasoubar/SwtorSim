# SWTOR game-data extractor

Python script that reads raw SWTOR `.tor` (MYP) archives, extracts GOM bucket and string-table files, parses combat-relevant nodes starting from player ability packages (`apc.<origin_story>.<class>`), and writes a faithful intermediate JSON dump under `data/extracted/`.

Based on [extracTOR](https://github.com/SWTOR-Slicers/extracTOR) and [Jedipedia](https://swtor.jedipedia.net/).

## Usage

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

python src/extractor/main.py --assets /path/to/SWTOR/Assets
```

On first run, Jedipedia hash list and `gom.js` name maps are downloaded into `data/` and refreshed when the remote copies are newer.

Options:

- `--force-hash-update` — re-download hash list and `gom.js` from Jedipedia
- `--origin-story sith_inquisitor` — limit to one origin story
- `--pts` — use PTS archives
- `--keep-work` — retain intermediate files in `data/extract_work/`

## Data layout

| Path | Purpose |
|------|---------|
| `data/hashes.bin` | Cached Jedipedia file hash list |
| `data/gom.js` | Cached Jedipedia GOM class/field/enum names |
| `data/extract_work/` | Ephemeral MYP extraction (deleted after run unless `--keep-work`) |
| `data/extracted/` | JSON dump of nodes |
