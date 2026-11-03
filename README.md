# SWTOR Combat Simulator

A combat simulator for *Star Wars: The Old Republic*. It is meant to run a rotation against a dummy — abilities, procs, mitigation, and resource pools — using data taken from the game client, then report damage from a single fight or a Monte Carlo batch.

The repository has two parts:

- **Extractor** (`src/extractor`) — reads SWTOR `.tor` archives and writes parts fo them in JSON (disciplines, abilities, talents, gear, relics).
- **Simulator** (`src/swtorsim`) — an event-driven fight loop simulating the combat.

## Layout

| Path | What it is |
| --- | --- |
| `src/extractor/` | Archive reader and combat-data parser |
| `src/swtorsim/` | Simulator runtime (mid-rewrite) |
| `main.py` | Intended simulator entry point |
| `data/` | Extracted JSON, builds, and rotations. `data/extractor/` is gitignored |
| `docs/` | Architecture and rewrite notes |

## License and affiliation

This is an unofficial fan project. It is not affiliated with Broadsword, BioWare, or Electronic Arts. *Star Wars: The Old Republic* and related marks belong to their owners.
