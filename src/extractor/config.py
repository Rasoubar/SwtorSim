from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

JEDIHASH_URL = "http://swtor.jedipedia.net/ajax/getFileNames.php?env=all&format=easymyp"
GOM_JS_URL = "https://swtor.jedipedia.net/static/js/reader/gom.js"
FNV1A64_JS_URL = (
    "https://swtor.jedipedia.net/static/js/reader/lib/fnv1a64.js"
)

DATA_DIR = Path("data")
WORK_DIR = Path("data/extract_work")
OUTPUT_DIR = Path("data/extracted")

# FQN prefixes whose nodes are followed during combat graph traversal.
COMBAT_FQN_PREFIXES = (
    "apc.",
    "abl.",
    "tal.",
    "dis.",
)

ABILITY_REPLACEMENT_NODE_ID = "16141053964861013368"

ORIGIN_STORIES = (
    "agent",
    "bounty_hunter",
    "jedi_consular",
    "jedi_knight",
    "sith_inquisitor",
    "sith_warrior",
    "smuggler",
    "trooper",
)

# Combat-relevant item ability trees that are not reachable from player APC nodes.
ITEM_ABILITY_FQN_PREFIXES = (
    "abl.itm.legendary",
    "abl.itm.tactical.sow",
)

# Item nodes for tactical and legendary implants (name lookup via itm.stb).
ITEM_FQN_PREFIXES = (
    "itm.legendary",
    "itm.tactical.sow",
)

# Ability effect ID list on abl nodes.
ABL_EFFECT_IDS_FIELD = "4611686061870631192"

APC_LIST_FIELD_IDS = frozenset(
    {
        "4611686061183631195",  # ablPackageAbilitiesList
        "4611686313312184003",  # ablPackageActiveAbilitiesList
        "4611690220002920194",  # ablPackageConditionalAbilitiesList
        "4611686296953210012",  # ablPackageTalentsList
        "4611686093816269991",  # ablPackageSpecList
    }
)

COMBAT_REF_FIELD_IDS = APC_LIST_FIELD_IDS | {ABL_EFFECT_IDS_FIELD}

# Loc retriever inner field IDs.
LOC_STR_ID_FIELD = "4611686093000569992"
LOC_STR_BUCKET_FIELD = "4611686093000569993"
# English language key in loc retriever lookup lists.
LOC_ENGLISH_KEY = "15685385242400905286"

# Integer fields on disDisciplineInfo that store STB string IDs.
SKILL_TREES_STB_BUCKET = "gui.abl.player.skill_trees"

STB_STRING_FIELD_BUCKETS: dict[str, str] = {
    "4611686359990757004": SKILL_TREES_STB_BUCKET,  # disDisciplinePackageName
    "4611686359990757005": SKILL_TREES_STB_BUCKET,  # disDisciplineTabName
}


@dataclass
class ExtractorConfig:
    assets_path: Path
    force_hash_update: bool = False
    pts: bool = False
    keep_work_files: bool = False

    @property
    def data_dir(self) -> Path:
        return DATA_DIR

    @property
    def work_dir(self) -> Path:
        return WORK_DIR

    @property
    def output_dir(self) -> Path:
        return OUTPUT_DIR
