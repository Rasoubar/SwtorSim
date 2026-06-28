from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from extractor.config import DATA_DIR, WORK_DIR
from extractor.gom.client_gom import load_client_gom

EFF_TRIGGER_ENUM_ID = "4611686039404270025"

# effTriggerEnum members from client.gom (index -> snake_case label).
# Triggers whose firing time is derived from the hosting effect's effDuration.
EFFECT_DURATION_TRIGGERS: frozenset[str] = frozenset(
    {
        "on_pre_remove",
        "on_timer_expired",
        "on_remove",
    }
)

EMBEDDED_TRIGGER_LABELS: dict[str, str] = {
    "1": "invalid",
    "2": "on_tick",
    "3": "on_travel_complete",
    "4": "on_damage_taken",
    "5": "on_pre_remove",
    "6": "on_timer_expired",
    "7": "on_apply",
    "8": "on_effect_received",
    "9": "on_channeling_ended",
    "10": "on_damage_dealt",
    "11": "on_weapon_mode_changed",
    "12": "on_pre_damage_taken",
    "13": "on_death",
    "14": "on_charges_increased",
    "15": "on_conversation_entered",
    "16": "on_charges_decreased",
    "17": "on_effect_applied",
    "18": "on_effect_dispelled",
    "19": "on_projectile_hit",
    "20": "unused_on_aura_entered",
    "21": "unused_on_aura_exited",
    "22": "on_conversation_exited",
    "23": "on_move",
    "24": "unused_on_avoid",
    "25": "on_kill",
    "26": "on_pre_damage_dealt",
    "27": "unused_on_flurry_begin",
    "28": "on_move_stop",
    "29": "on_remove",
    "30": "on_refresh",
    "31": "on_pre_death",
    "32": "on_healing_dealt",
    "33": "on_healing_taken",
    "34": "on_pre_healing_dealt",
    "35": "on_pre_healing_taken",
    "36": "on_stunned",
    "37": "on_stun_removed",
    "38": "on_replay_looping_epp",
    "39": "on_ability_activate",
    "40": "on_ability_post_activate",
    "41": "on_enter_combat",
    "42": "on_exit_combat",
    "43": "on_spawn_entry_epp",
    "44": "on_revive",
    "45": "on_power_channel_depleted",
    "46": "on_power_channel_filled",
    "47": "on_modal_user_deactivated",
    "48": "on_boost_started",
    "49": "on_minimum_health_reached",
    "50": "on_level_changed",
    "51": "on_command_rank_changed",
    "52": "on_area_effect_expired",
    "53": "on_area_effect_ticked",
    "54": "on_ability_charges_modified",
    "55": "on_amplifiers_changed",
    "56": "on_discipline_utilities_changed",
    "57": "on_item_unequipped",
    "58": "on_item_equipped",
    "59": "on_pre_effect_dispelled",
    "60": "on_mount",
    "61": "on_dismount",
}


def _trigger_label_from_member(member: str) -> str:
    name = member
    if name.startswith("effTrigger_"):
        name = name[len("effTrigger_") :]
    if name.startswith("_UNUSED_"):
        name = name[len("_UNUSED_") :]
    s1 = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", name)
    s2 = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s1)
    return s2.lower()


def _labels_from_client_gom(path: Path) -> dict[str, str] | None:
    try:
        client_gom = load_client_gom(path)
    except (OSError, ValueError):
        return None
    members = client_gom.enum_members.get(EFF_TRIGGER_ENUM_ID)
    if not members:
        return None
    return {
        str(index): _trigger_label_from_member(member)
        for index, member in enumerate(members, 1)
    }


def load_trigger_labels() -> dict[str, str]:
    candidate_paths = [
        WORK_DIR / "resources" / "systemgenerated" / "client.gom",
        DATA_DIR / "client.gom",
    ]
    for path in candidate_paths:
        labels = _labels_from_client_gom(path)
        if labels:
            return labels
    return dict(EMBEDDED_TRIGGER_LABELS)


def decode_trigger_name(raw: Any, labels: dict[str, str]) -> tuple[str, int | None]:
    key = str(raw)
    if key.isdigit():
        index = int(key)
        return labels.get(key, f"trigger_{key}"), index
    if key.startswith("effTrigger_"):
        return _trigger_label_from_member(key), None
    return key, None
