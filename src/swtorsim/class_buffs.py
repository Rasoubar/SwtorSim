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
from typing import Dict, List, Tuple

from src.swtorsim.effects import ActiveEffect

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PARSED_DIR = PROJECT_ROOT / "data" / "extractor" / "parsed"

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


def _blueprint_path(fqn: str) -> Path:
    return PARSED_DIR.joinpath(*fqn.split(".")).with_suffix(".json")


def load_class_buff_effects() -> List[ActiveEffect]:
    """Builds one permanent ActiveEffect per class buff from the extracted blueprints."""
    effects: List[ActiveEffect] = []
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
        effect = ActiveEffect.from_effect_node(data.get("fqn") or fqn, buff_name, node)
        effect.name = buff_name
        effect.is_passive = True
        effect.expires_at = None
        effects.append(effect)
    return effects


def apply_class_buffs(player, sim=None) -> List[str]:
    """Grants every class buff to the player and installs the hidden permanent bonus.

    Buffs already present (e.g. the player's own class buff applied from the loadout)
    are left untouched to avoid double-counting. Returns the names of newly added buffs.
    """
    added: List[str] = []
    for effect in load_class_buff_effects():
        if effect.name in player.effects:
            continue
        player.effects[effect.name] = effect
        added.append(effect.name)
        if sim is not None and getattr(sim, "tracker", None) is not None:
            sim.tracker.log_effect_applied(
                player.name,
                effect.name,
                0.0,
                stacks=getattr(effect, "stacks", 1),
                is_passive=True,
            )
    player.permanent_bonuses = dict(HIDDEN_BONUSES)
    return added
