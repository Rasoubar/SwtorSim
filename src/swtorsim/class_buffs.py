"""Universal class buffs and hidden permanent bonuses granted to every player.

Every simulated player receives the four class buffs (Unnatural Might, Mark of
Power, Coordination, Hunter's Boon) regardless of their own class, plus a hidden
permanent bonus of +1% accuracy, +1% critical chance and +1% critical multiplier.

The buff effects are built straight from the extracted ``*_passive`` blueprints so
their stat values stay authoritative. The ``tal.legacy.buff_unlock.*`` conditions
gating cross-class buffs are intentionally bypassed: every player is assumed to
have all of them unlocked.
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from src.swtorsim.effects import ActiveEffect
from src.swtorsim.settings import get_extractor_data_dir

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PARSED_DIR = PROJECT_ROOT / "data" / "extractor" / "live" / "parsed"

# (effect name, passive blueprint FQN carrying that effect)
CLASS_BUFF_SOURCES: Tuple[Tuple[str, str], ...] = (
    ("Unnatural Might", "abl.sith_warrior.unnatural_might_passive"),
    ("Mark of Power", "abl.sith_inquisitor.mark_of_power_passive"),
    ("Coordination", "abl.agent.coordination_passive"),
    ("Hunter's Boon", "abl.bounty_hunter.hunters_boon_passive"),
)

# Hidden permanent bonus, as canonical decimal fractions (0.01 == 1%).
HIDDEN_ACCURACY = 0.01
HIDDEN_CRIT_CHANCE = 0.01
HIDDEN_CRIT_MULTIPLIER = 0.01

HIDDEN_BONUSES: Dict[str, float] = {
    "Accuracy": HIDDEN_ACCURACY,
    "Critical Chance": HIDDEN_CRIT_CHANCE,
    "Critical Modifier": HIDDEN_CRIT_MULTIPLIER,
}

# Bidirectional mapping between Imperial and Republic mirror class buffs.
MIRROR_CLASS_BUFFS: Dict[str, Tuple[str, ...]] = {
    "Unnatural Might": ("Force Might",),
    "Force Might": ("Unnatural Might",),
    "Mark of Power": ("Force Valor",),
    "Force Valor": ("Mark of Power",),
    "Coordination": ("Lucky Shots",),
    "Lucky Shots": ("Coordination",),
    "Hunter's Boon": ("Trooper's Fortitude",),
    "Trooper's Fortitude": ("Hunter's Boon",),
}

# Cached blueprint AST nodes keyed by extractor data directory:
# {data_dir: [(fqn, buff_name, effect_node), ...]}
_BUFF_TEMPLATES_CACHE: Dict[str, List[Tuple[str, str, Dict[str, Any]]]] = {}


def _blueprint_path(fqn: str) -> Path:
    env_parsed = PROJECT_ROOT / get_extractor_data_dir() / "parsed"
    base_dir = env_parsed if env_parsed.is_dir() else PARSED_DIR
    return base_dir.joinpath(*fqn.split(".")).with_suffix(".json")


def clear_class_buff_cache() -> None:
    """Clears in-memory blueprint template cache (e.g. when switching extractor data directories)."""
    _BUFF_TEMPLATES_CACHE.clear()


def _get_class_buff_templates() -> List[Tuple[str, str, Dict[str, Any]]]:
    """Retrieves and caches the raw blueprint AST effect nodes from disk."""
    data_dir = get_extractor_data_dir()
    templates = _BUFF_TEMPLATES_CACHE.get(data_dir)
    if templates is not None:
        return templates

    loaded: List[Tuple[str, str, Dict[str, Any]]] = []
    for buff_name, fqn in CLASS_BUFF_SOURCES:
        path = _blueprint_path(fqn)
        if not path.is_file():
            print(f"[WARN] Class buff blueprint not found for '{buff_name}': {path}")
            continue
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        node = next(
            (n for n in data.get("effects") or [] if n.get("name") == buff_name),
            None,
        )
        if node is None:
            print(f"[WARN] Effect '{buff_name}' not found in blueprint '{fqn}'.")
            continue
        loaded.append((data.get("fqn") or fqn, buff_name, node))

    _BUFF_TEMPLATES_CACHE[data_dir] = loaded
    return loaded


def apply_class_buffs(player, sim=None) -> List[str]:
    """Grants every class buff to the player and installs the hidden permanent bonus.

    Buffs already present (e.g. the player's own class buff applied from the loadout)
    or mirror counterparts from the opposite faction are skipped to avoid double-counting.
    Returns the names of newly added buffs.
    """
    added: List[str] = []
    player_effects = player.effects

    for fqn, buff_name, node in _get_class_buff_templates():
        mirrors = MIRROR_CLASS_BUFFS.get(buff_name, ())
        if buff_name in player_effects or any(m in player_effects for m in mirrors):
            continue

        effect = ActiveEffect.from_effect_node(fqn, buff_name, node)
        effect.name = buff_name
        effect.is_passive = True
        effect.expires_at = None
        player_effects[buff_name] = effect
        added.append(buff_name)

        if sim is not None and getattr(sim, "tracker", None) is not None:
            sim.tracker.log_effect_applied(
                player.name,
                buff_name,
                0.0,
                stacks=getattr(effect, "stacks", 1),
                is_passive=True,
            )

    player.permanent_bonuses = dict(HIDDEN_BONUSES)
    return added
