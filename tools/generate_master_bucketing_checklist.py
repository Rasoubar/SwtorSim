"""Generates docs/modifier_bucketing_master_checklist.md by scanning all parsed blueprints across all classes."""

import glob
import json
import os
from collections import defaultdict

STAT_REGISTRY = {
    # 1. Caster Damage Done (Direct / General)
    "79": {
        "name": "STAT_cbt_damage_done_modifier_percentage",
        "category": "Caster General Damage Done",
        "status": "[x] Verified in BUCKET_1",
        "bucket": "BUCKET_1",
        "proven_by": "Test 1, Test 2, Test 6",
        "notes": "Tag-scoped and ability-scoped instances add together in BUCKET_1.",
    },
    "78": {
        "name": "STAT_cbt_damage_done_modifier_fixed",
        "category": "Caster Flat Damage Added",
        "status": "[ ] Untested",
        "bucket": "Unassigned",
        "proven_by": "-",
        "notes": "Flat bonus damage added to hits.",
    },
    # 2. Target Channel Vulnerabilities (+5%)
    "386": {
        "name": "stat_cbt_damage_taken_scale_channel_force_modifier_percentage",
        "category": "Target Channel Vulnerability",
        "status": "[x] Verified in BUCKET_1",
        "bucket": "BUCKET_1",
        "proven_by": "Test 2",
        "notes": "Force Vulnerability (+5%) is additive inside BUCKET_1.",
    },
    "384": {
        "name": "stat_cbt_damage_taken_scale_channel_melee_modifier_percentage",
        "category": "Target Channel Vulnerability",
        "status": "[x] Verified in BUCKET_1",
        "bucket": "BUCKET_1",
        "proven_by": "Test 6",
        "notes": "Beat Down (+5%) is additive inside BUCKET_1.",
    },
    "382": {
        "name": "stat_cbt_damage_taken_scale_channel_ranged_modifier_percentage",
        "category": "Target Channel Vulnerability",
        "status": "[x] Verified BUCKET_1",
        "bucket": "BUCKET_1",
        "proven_by": "Test 9",
        "notes": "Marked (+5% Ranged). Additive in BUCKET_1. Proven in Test 9 (Arsenal Mercenary Priming Shot).",
    },
    "388": {
        "name": "stat_cbt_damage_taken_scale_channel_tech_modifier_percentage",
        "category": "Target Channel Vulnerability",
        "status": "[x] Verified BUCKET_1",
        "bucket": "BUCKET_1",
        "proven_by": "Test 8",
        "notes": "Susceptible (+5% Tech). Additive in BUCKET_1. Proven in Test 8 (IO Mercenary Incendiary Missile).",
    },
    # 3. Target Damage Type Vulnerabilities (+7%)
    "376": {
        "name": "stat_cbt_damage_taken_scale_type_internal_modifier_percentage",
        "category": "Target Type Vulnerability",
        "status": "[x] Verified in BUCKET_1",
        "bucket": "BUCKET_1",
        "proven_by": "Test 2",
        "notes": "Assailable Internal (+7%) is additive inside BUCKET_1.",
    },
    "370": {
        "name": "stat_cbt_damage_taken_scale_type_elemental_modifier_percentage",
        "category": "Target Type Vulnerability",
        "status": "[x] Verified BUCKET_1",
        "bucket": "BUCKET_1",
        "proven_by": "Test 8",
        "notes": "Assailable Elemental (+7%). Additive in BUCKET_1. Proven in Test 8 (IO Mercenary Incendiary Missile).",
    },
    "372": {
        "name": "stat_cbt_damage_taken_scale_type_energy_modifier_percentage",
        "category": "Target Type Vulnerability",
        "status": "[-] Unused in Blueprints",
        "bucket": "Unassigned",
        "proven_by": "-",
        "notes": "Energy vulnerability scaling (0 occurrences in client blueprints).",
    },
    "374": {
        "name": "stat_cbt_damage_taken_scale_type_kinetic_modifier_percentage",
        "category": "Target Type Vulnerability",
        "status": "[-] Unused in Blueprints",
        "bucket": "Unassigned",
        "proven_by": "-",
        "notes": "Kinetic vulnerability scaling (0 occurrences in client blueprints).",
    },
    # 4. Target AoE / Tag Vulnerabilities
    "46": {
        "name": "STAT_cbt_damage_received_modifier_percentage",
        "category": "Target AoE / Damage Received",
        "status": "[x] Verified in BUCKET_2 (AoE)",
        "bucket": "BUCKET_2",
        "proven_by": "Test 3, Test 5",
        "notes": "Overwhelmed (+10% AoE) is an independent multiplicative layer.",
    },
    "465": {
        "name": "stat_cbt_damage_taken_scale_tag_aoe_modifier",
        "category": "Target Tag Vulnerability",
        "status": "[-] Unused in Blueprints",
        "bucket": "Unassigned",
        "proven_by": "-",
        "notes": "Explicit AoE tag vulnerability (0 occurrences in client blueprints).",
    },
    "467": {
        "name": "stat_cbt_damage_taken_scale_tag_dot_modifier",
        "category": "Target Tag Vulnerability",
        "status": "[-] Unused in Blueprints",
        "bucket": "Unassigned",
        "proven_by": "-",
        "notes": "DoT tag vulnerability (0 occurrences in client blueprints).",
    },
    # 5. Target State Conditionals (Execute / Debuffs)
    "220": {
        "name": "STAT_cbt_damage_done_if_target_health_low_modifier_percentage",
        "category": "Target Low-Health Execute",
        "status": "[x] Verified in BUCKET_3",
        "bucket": "BUCKET_3",
        "proven_by": "Test 4, Test 5",
        "notes": "Execute sub-30% HP (+25% / +20%) is an independent multiplicative layer.",
    },
    "221": {
        "name": "STAT_cbt_damage_done_if_target_bleeding_modifier_percentage",
        "category": "Target State: Bleeding",
        "status": "[x] Verified in BUCKET_5",
        "bucket": "BUCKET_5",
        "proven_by": "Test 12, Test 14",
        "notes": "Bonus damage while target is bleeding. Proven independent multiplicative layer (BUCKET_5) via Test 12 (Bloodbath) and Test 14 (Blood Tracker).",
    },
    "222": {
        "name": "STAT_cbt_damage_done_if_target_stunned_modifier_percentage",
        "category": "Target State: Stunned (Damage Done)",
        "status": "[-] Unused in Blueprints",
        "bucket": "Unassigned",
        "proven_by": "-",
        "notes": "Damage done bonus against stunned targets (0 occurrences in player abilities and passives).",
    },
    "223": {
        "name": "STAT_cbt_damage_received_if_target_stunned_modifier_percentage",
        "category": "Target State: Stunned / Incapacitated",
        "status": "[x] Defensive Stun DR",
        "bucket": "Defensive DR",
        "proven_by": "-",
        "notes": "Defensive damage reduction utility (-30% incoming damage while stunned/incapacitated). Not an offensive multiplier.",
    },
    "250": {
        "name": "STAT_cbt_damage_done_if_target_on_fire_modifier_percentage",
        "category": "Target State: On Fire / Burn",
        "status": "[x] Verified in BUCKET_6",
        "bucket": "BUCKET_6",
        "proven_by": "Test 16",
        "notes": "Bonus damage while target is burning. Proven independent multiplicative layer (BUCKET_6) via Test 16 (Burning Storm on Vigilance Guardian Cyclone Slash).",
    },
    "389": {
        "name": "STAT_cbt_damage_done_if_target_accuracy_reduced_modifier_percentage",
        "category": "Target State: Accuracy Reduced",
        "status": "[x] Verified in BUCKET_4",
        "bucket": "BUCKET_4",
        "proven_by": "Test 7",
        "notes": "Target-state accuracy reduced conditional (+15% Torment) is an independent multiplicative bucket.",
    },
    "127": {
        "name": "STAT_cbt_dual_wield_damage_done_modifier_percentage",
        "category": "Dual Wield Conditional",
        "status": "[x] Verified Offhand Scalar",
        "bucket": "Offhand Scalar (0.25 + val)",
        "proven_by": "Test 10",
        "notes": "Dual-wield bonus damage. Proven in Test 10 on Carnage Marauder (Assault OH hit).",
    },
    # 6. Caster Dealt Scale Types / Tags
    "393": {
        "name": "stat_cbt_damage_dealt_scale_type_elemental_modifier_percentage",
        "category": "Caster Elemental Dealt Scale",
        "status": "[-] Unused in Blueprints",
        "bucket": "Unassigned",
        "proven_by": "-",
        "notes": "Caster bonus to elemental damage dealt (0 occurrences in client blueprints).",
    },
    "395": {
        "name": "stat_cbt_damage_dealt_scale_type_energy_modifier_percentage",
        "category": "Caster Energy Dealt Scale",
        "status": "[x] Verified in BUCKET_1",
        "bucket": "BUCKET_1",
        "proven_by": "Test 13",
        "notes": "Caster bonus to energy damage dealt. Proven additive in BUCKET_1 via Test 13 (High Energy Gas Cylinder).",
    },
    "397": {
        "name": "stat_cbt_damage_dealt_scale_type_kinetic_modifier_percentage",
        "category": "Caster Kinetic Dealt Scale",
        "status": "[x] Verified in BUCKET_1",
        "bucket": "BUCKET_1",
        "proven_by": "Test 13",
        "notes": "Caster bonus to kinetic damage dealt. Co-granted with 395 in High Energy Gas Cylinder / Cell. Proven additive in BUCKET_1 via Test 13.",
    },
    "399": {
        "name": "stat_cbt_damage_dealt_scale_type_internal_modifier_percentage",
        "category": "Caster Internal Dealt Scale",
        "status": "[-] Unused in Blueprints",
        "bucket": "Unassigned",
        "proven_by": "-",
        "notes": "Caster bonus to internal damage dealt (0 occurrences in client blueprints).",
    },
    "454": {
        "name": "stat_cbt_aoe_damage_dealt_modifier",
        "category": "Caster AoE Dealt Scale",
        "status": "[-] Unused in Blueprints",
        "bucket": "Unassigned",
        "proven_by": "-",
        "notes": "Caster bonus to AoE damage dealt (0 occurrences in client blueprints).",
    },
    "464": {
        "name": "stat_cbt_damage_dealt_scale_tag_aoe_modifier",
        "category": "Caster AoE Dealt Scale",
        "status": "[-] Unused in Blueprints",
        "bucket": "Unassigned",
        "proven_by": "-",
        "notes": "Caster bonus to AoE tag damage dealt (0 occurrences in client blueprints).",
    },
    "466": {
        "name": "stat_cbt_damage_dealt_scale_tag_dot_modifier",
        "category": "Caster DoT Dealt Scale",
        "status": "[-] Unused in Blueprints",
        "bucket": "Unassigned",
        "proven_by": "-",
        "notes": "Caster bonus to DoT tag damage dealt (0 occurrences in client blueprints).",
    },
}

CLASS_NAME_MAP = {
    "sith_inquisitor": "Sith Inquisitor (Assassin / Sorcerer)",
    "jedi_consular": "Jedi Consular (Shadow / Sage)",
    "agent": "Imperial Agent (Operative / Sniper)",
    "smuggler": "Smuggler (Scoundrel / Gunslinger)",
    "bounty_hunter": "Bounty Hunter (Mercenary / Powertech)",
    "trooper": "Trooper (Commando / Vanguard)",
    "sith_warrior": "Sith Warrior (Juggernaut / Marauder)",
    "jedi_knight": "Jedi Knight (Guardian / Sentinel)",
}


def scan_definitions():
    """Scans all parsed abilities and talents to discover all occurrences of each stat."""
    stat_occurrences = defaultdict(lambda: defaultdict(list))

    paths = glob.glob("data/extractor/pts/parsed/**/*.json", recursive=True) + glob.glob(
        "data/extractor/live/parsed/**/*.json", recursive=True
    )
    seen_files = set()

    for p in paths:
        norm_p = os.path.normpath(p)
        if norm_p in seen_files:
            continue
        seen_files.add(norm_p)

        try:
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            continue

        fqn = data.get("fqn", "")
        name = data.get("name", "")

        # Identify class from path/FQN
        class_key = "General / Other"
        for ck in CLASS_NAME_MAP:
            if ck in fqn or f"/parsed/abl/{ck}" in norm_p.replace("\\", "/") or f"/parsed/tal/{ck}" in norm_p.replace("\\", "/"):
                class_key = CLASS_NAME_MAP[ck]
                break

        # Check talent stat_changes
        for sc in data.get("stat_changes", []):
            st_name = str(sc.get("name", ""))
            val = sc.get("value", 0.0)
            imp = sc.get("impact", {})
            imp_fqn = imp.get("fqn", "") if imp else ""

            # Check matches against our STAT_REGISTRY
            for stat_id, info in STAT_REGISTRY.items():
                if st_name == stat_id or st_name == info["name"]:
                    stat_occurrences[stat_id][class_key].append(
                        {"name": name, "fqn": fqn, "val": val, "impact": imp_fqn}
                    )

        # Check ability actions / modifiers
        for e in data.get("effects", []):
            for b in e.get("branches", []):
                for a in b.get("actions", []):
                    st = str(a.get("stat", ""))
                    val = a.get("amount", a.get("amount_min", a.get("value", 0.0)))
                    for stat_id, info in STAT_REGISTRY.items():
                        if st == stat_id or st == info["name"]:
                            stat_occurrences[stat_id][class_key].append(
                                {"name": name, "fqn": fqn, "val": val, "impact": ""}
                            )

    return stat_occurrences


def generate_markdown(occurrences):
    md = []
    md.append("# SWTOR Combat Modifier Master Bucketing Checklist\n")
    md.append("This document tracks all combat damage modifier stats across SWTOR, their current empirical bucketing status, and which classes/disciplines have access to them for testing.\n")
    md.append("---\n")
    md.append("## 1. Verified Buckets Summary\n")
    md.append("$$\\text{Damage} = \\text{Base} \\times \\underbrace{\\big[1.0 + \\sum \\text{Bucket 1}\\big]}_{\\text{Attacker Done} + \\text{Force Vuln} + \\text{Melee Vuln} + \\text{Internal Vuln}} \\times \\underbrace{\\big[1.0 + \\text{Bucket 2}\\big]}_{\\text{AoE Vuln (Overwhelmed)}} \\times \\underbrace{\\big[1.0 + \\text{Bucket 3}\\big]}_{\\text{Sub-30\\% Execute}} \\times \\underbrace{\\big[1.0 + \\text{Bucket 4}\\big]}_{\\text{Accuracy Reduced Conditional (Torment)}}\n$$\n")
    md.append("| Bucket | Role | Verified Member Stat IDs | Proven Multiplicative Against |\n")
    md.append("| :--- | :--- | :--- | :--- |\n")
    md.append("| **`BUCKET_1`** | Baseline Additive Damage Pool | `79` (Attacker Done), `386` (Force Vuln), `384` (Melee Vuln), `376` (Internal Vuln) | `BUCKET_2`, `BUCKET_3`, `BUCKET_4` |\n")
    md.append("| **`BUCKET_2`** | Independent Target AoE Layer | `46` (Overwhelmed AoE damage taken) | `BUCKET_1`, `BUCKET_3`, `BUCKET_4` |\n")
    md.append("| **`BUCKET_3`** | Independent Low-Health Execute Layer | `220` (Inevitable Demise, Languishing Lashes) | `BUCKET_1`, `BUCKET_2` |\n")
    md.append("| **`BUCKET_4`** | Independent Target-State Conditional Layer | `389` (Torment / Accuracy Reduced) | `BUCKET_1`, `BUCKET_2` |\n")
    md.append("\n---\n")

    md.append("## 2. Master Stat Checklist & Matrix\n\n")
    md.append("| Stat ID | GOM Stat Name | Category | Status | Verified Bucket | Primary Test Class / Source | Notes & Testing Target |\n")
    md.append("| :---: | :--- | :--- | :---: | :---: | :--- | :--- |\n")

    for stat_id, info in STAT_REGISTRY.items():
        classes_present = list(occurrences.get(stat_id, {}).keys())
        if "386" in stat_id or "384" in stat_id or "382" in stat_id or "388" in stat_id or "376" in stat_id or "370" in stat_id or stat_id == "46":
            class_desc = "Target Debuff Module / Raid Debuffs"
        elif classes_present:
            class_desc = ", ".join([c.split(" (")[0] for c in classes_present[:2]])
            if len(classes_present) > 2:
                class_desc += f" (+{len(classes_present)-2} more)"
        else:
            class_desc = "Class-specific / General"

        md.append(
            f"| **`{stat_id}`** | `{info['name']}` | {info['category']} | **{info['status']}** | `{info['bucket']}` | {class_desc} | {info['notes']} |\n"
        )

    md.append("\n---\n")
    md.append("## 3. Detailed Stat Profiles & Class Availability\n\n")

    for stat_id, info in STAT_REGISTRY.items():
        md.append(f"### ID `{stat_id}` — `{info['name']}`\n")
        md.append(f"* **Category**: {info['category']}\n")
        md.append(f"* **Status**: **{info['status']}** (Bucket: `{info['bucket']}`)\n")
        md.append(f"* **Verification Record**: {info['proven_by']}\n")
        md.append(f"* **Testing Notes**: {info['notes']}\n\n")

        cls_data = occurrences.get(stat_id, {})
        if cls_data:
            md.append("#### Known Abilities & Talents in Blueprints:\n")
            for cls_name, abls in cls_data.items():
                md.append(f"* **{cls_name}**:\n")
                seen_abls = set()
                for a in abls[:8]:  # show up to 8 unique abilities per class
                    k = (a["name"], a["val"], a["impact"])
                    if k in seen_abls:
                        continue
                    seen_abls.add(k)
                    val_str = f"+{a['val']*100:.1f}%" if abs(a["val"]) < 1.0 and a["val"] != 0 else f"{a['val']}"
                    impact_str = f" -> {a['impact'].split('.')[-1]}" if a["impact"] else ""
                    md.append(f"  * `{a['name']}` ({val_str}{impact_str})\n")
        else:
            if stat_id in ("386", "384", "382", "388", "370", "376", "46"):
                md.append("Applied via Operations Training Dummy Debuff Module / standard raid debuffs.\n")
            else:
                md.append("No direct class blueprint occurrences found; evaluated via engine hooks.\n")

        md.append("\n---\n")

    return "".join(md)


def main():
    print("[*] Scanning blueprints for combat modifier stats across all classes...")
    occurrences = scan_definitions()
    print(f"[*] Found stat matches across {len(occurrences)} distinct stats.")

    md_content = generate_markdown(occurrences)
    output_path = "docs/modifier_bucketing_master_checklist.md"
    
    # Enforce CRLF
    crlf_content = md_content.replace("\r\n", "\n").replace("\n", "\r\n")
    with open(output_path, "wb") as f:
        f.write(crlf_content.encode("utf-8"))

    print(f"[OK] Master checklist generated at: {output_path}")


if __name__ == "__main__":
    main()