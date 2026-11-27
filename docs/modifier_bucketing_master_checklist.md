# SWTOR Combat Modifier Master Bucketing Checklist

This document tracks all combat damage modifier stats across SWTOR, their current empirical bucketing status, and which classes/disciplines have access to them for testing.

> [!NOTE]
> All blueprint audit counts and references in this document are strictly based on audited player abilities and passives (`abl.*` and `tal.*` files).

---

## 1. Verified Buckets Summary

$$
\text{Damage} = \text{Base} \times \underbrace{\big[1.0 + \sum \text{Bucket 1}\big]}_{\text{Attacker Done} + \text{Vulnerabilities} + \text{Energy/Kinetic/Melee/Force Dealt}} \times \underbrace{\big[1.0 + \text{Bucket 2}\big]}_{\text{AoE Vuln (Overwhelmed)}} \times \underbrace{\big[1.0 + \text{Bucket 3}\big]}_{\text{Sub-30\% Execute}} \times \underbrace{\big[1.0 + \text{Bucket 4}\big]}_{\text{Accuracy Reduced (Torment)}} \times \underbrace{\big[1.0 + \text{Bucket 5}\big]}_{\text{Target Bleeding (Bloodbath)}} \times \underbrace{\big[1.0 + \text{Bucket 6}\big]}_{\text{Target On Fire (Burning Storm)}}
$$

| Bucket | Role | Verified Member Stat IDs | Proven Multiplicative Against |
| :--- | :--- | :--- | :--- |
| **`BUCKET_1`** | Baseline Additive Damage Pool | `79` (Attacker Done), `386` (Force Vuln), `384` (Melee Vuln), `382` (Ranged Vuln), `388` (Tech Vuln), `376` (Internal Vuln), `370` (Elemental Vuln), `395` (Energy Dealt Scale), `397` (Kinetic Dealt Scale), `407` (Melee Dealt Scale), `409` (Force Dealt Scale) | `BUCKET_2`, `BUCKET_3`, `BUCKET_4`, `BUCKET_5` |
| **`BUCKET_2`** | Independent Target AoE Layer | `46` (Overwhelmed AoE damage taken) | `BUCKET_1`, `BUCKET_3`, `BUCKET_4`, `BUCKET_5` |
| **`BUCKET_3`** | Independent Low-Health Execute Layer | `220` (Inevitable Demise, Languishing Lashes) | `BUCKET_1`, `BUCKET_2` |
| **`BUCKET_4`** | Independent Target-State Conditional Layer | `389` (Torment / Accuracy Reduced) | `BUCKET_1`, `BUCKET_2` |
| **`BUCKET_5`** | Independent Target-State Bleeding Layer | `221` (Bloodbath, Blood Tracker, Triumph) | `BUCKET_1`, `BUCKET_2` |
| **`BUCKET_6`** | Independent Target-State Burning Layer | `250` (Burning Storm) | `BUCKET_1`, `BUCKET_2` |

### 1.1 Cross-Bucket Coexistence & Mutual Exclusivity Analysis (Buckets 3 to 6)

A comprehensive architectural audit of all live discipline blueprints was conducted to determine whether stat IDs in Buckets 3 through 6 ever coexist within the same specialization, and whether they can be tested against each other for mutual multiplicativity:

* **Bucket 3 (ID `220` - Low-Health Execute < 30% HP)**:
  * Present in DPS trees: Lethality/Virulence, Pyrotech/Plasmatech, Balance/Madness, Infiltration/Deception, Serenity/Hatred, Dirty Fighting/Ruffian, and IO Mercenary / Assault Specialist Commando.
* **Bucket 4 (ID `389` - Target Accuracy Reduced)**:
  * Present strictly in Tank trees: Darkness Assassin (*Torment* -> `Lacerate`) and Kinetic Combat Shadow (*Psychokinesis* -> `Whirling Blow`). Neither tank discipline has access to execute (ID `220`), bleed (ID `221`), or fire (ID `250`) modifiers.
* **Bucket 5 (ID `221` - Target State: Bleeding)**:
  * Present in Vengeance Juggernaut (*Bloodbath*), AP Powertech (*Blood Tracker*), Tactics Vanguard (*Triumph*), and IO Mercenary / Assault Specialist Commando (*Relentless Ordnance* / *Relentless Assault*).
* **Bucket 6 (ID `250` - Target State: On Fire / Burning)**:
  * Present strictly in Vigilance Guardian (*Burning Storm* -> `Cyclone Slash`). Vigilance has no execute, bleed, or accuracy-reduced modifiers.

#### Coexistence Audit Matrix

| Bucket Pair | Coexists in Same Spec? | Notes & Live Feasibility |
| :--- | :---: | :--- |
| **Bucket 3 (`220`) vs Bucket 4 (`389`)** | **No** | `389` is exclusive to tank specs (Darkness / Kinetic Combat); `220` in those classes is exclusive to DPS specs (Hatred/Serenity, Deception/Infiltration, Madness/Balance). |
| **Bucket 3 (`220`) vs Bucket 6 (`250`)** | **No** | `250` is exclusive to Vigilance Guardian, which has no execute modifier. |
| **Bucket 4 (`389`) vs Bucket 5 (`221`)** | **No** | `389` is Inquisitor/Consular tank only; `221` is Warrior, BH, and Trooper only. |
| **Bucket 4 (`389`) vs Bucket 6 (`250`)** | **No** | `389` is Inquisitor/Consular tank only; `250` is Knight only. |
| **Bucket 5 (`221`) vs Bucket 6 (`250`)** | **No** | `221` is Warrior, BH, Trooper; `250` is Knight. (Vengeance *Bloodbath* [Bleed `221`] and Vigilance *Burning Storm* [Burn `250`] are faction mirrors). |
| **Bucket 3 (`220`) vs Bucket 5 (`221`)** | **Yes (IO / AS only)**, but **Completely Separate Ability Tags (No Overlap)** | Coexists only in Innovative Ordnance Mercenary (`abl.bounty_hunter.skill.innovative_ordnance.relentless_ordnance`) and Assault Specialist Commando (`abl.trooper.skill.assault_specialist.relentless_assault`). However, Stat `221` (+5%) applies strictly to direct flame attacks (`tag.abl.bounty_hunter.flamethrower_ability` / `tag.abl.trooper.elemental_attack`), whereas Stat `220` (+30%) applies strictly to periodic DoT ticks (`tag.abl.debuff.damage_over_time`). No ability or damage event carries both tags. |

#### Practical Takeaway
Because these four stats belong strictly to the attacker (not debuffs on the boss), other players cannot give them to you. In live gameplay, **no single hit ever has more than one of these conditional buffs (Buckets 3 to 6) active at the same time**. 

Each bucket is individually proven to multiply baseline damage (`BUCKET_1`) and AoE vulnerability (`BUCKET_2`). Testing whether they multiply each other is not possible in-game because the game never lets them trigger on the same damage event.

---

## 2. Master Stat Checklist & Matrix

| Stat ID | GOM Stat Name | Category | Status | Verified Bucket | Primary Test Class / Source | Notes & Testing Target |
| :---: | :--- | :--- | :---: | :---: | :--- | :--- |
| **`79`** | `STAT_cbt_damage_done_modifier_percentage` | Caster General Damage Done | **[x] Verified in BUCKET_1** | `BUCKET_1` | Imperial Agent, Bounty Hunter (+7 more) | Tag-scoped and ability-scoped instances add together in BUCKET_1. |
| **`78`** | `STAT_cbt_damage_done_modifier_fixed` | Caster Flat Damage Added | **[x] Verified No-Op (Flat)** | `No-Op (0.20 Flat)` | Trooper (Vanguard `Harpoon` / *Pull and Pummel*) | Flat modifier (`_fixed`); passing `0.20` in *Pull and Pummel* (`harpoon.json`) adds `+0` integer damage in live combat (Test 17). |
| **`386`** | `stat_cbt_damage_taken_scale_channel_force_modifier_percentage` | Target Channel Vulnerability | **[x] Verified in BUCKET_1** | `BUCKET_1` | Target Debuff Module / Raid Debuffs | Force Vulnerability (+5%) is additive inside BUCKET_1. |
| **`384`** | `stat_cbt_damage_taken_scale_channel_melee_modifier_percentage` | Target Channel Vulnerability | **[x] Verified in BUCKET_1** | `BUCKET_1` | Target Debuff Module / Raid Debuffs | Beat Down (+5%) is additive inside BUCKET_1. |
| **`382`** | `stat_cbt_damage_taken_scale_channel_ranged_modifier_percentage` | Target Channel Vulnerability | **[x] Verified BUCKET_1** | `BUCKET_1` | Target Debuff Module / Raid Debuffs | Marked (+5% Ranged). Additive in BUCKET_1. Proven in Test 9 (Arsenal Mercenary Priming Shot). |
| **`388`** | `stat_cbt_damage_taken_scale_channel_tech_modifier_percentage` | Target Channel Vulnerability | **[x] Verified BUCKET_1** | `BUCKET_1` | Target Debuff Module / Raid Debuffs | Susceptible (+5% Tech). Additive in BUCKET_1. Proven in Test 8 (IO Mercenary Incendiary Missile). |
| **`376`** | `stat_cbt_damage_taken_scale_type_internal_modifier_percentage` | Target Type Vulnerability | **[x] Verified in BUCKET_1** | `BUCKET_1` | Target Debuff Module / Raid Debuffs | Assailable Internal (+7%) is additive inside BUCKET_1. |
| **`370`** | `stat_cbt_damage_taken_scale_type_elemental_modifier_percentage` | Target Type Vulnerability | **[x] Verified BUCKET_1** | `BUCKET_1` | Target Debuff Module / Raid Debuffs | Assailable Elemental (+7%). Additive in BUCKET_1. Proven in Test 8 (IO Mercenary Incendiary Missile). |
| **`372`** | `stat_cbt_damage_taken_scale_type_energy_modifier_percentage` | Target Type Vulnerability | **[-] Unused in Blueprints** | `Unassigned` | None (Unused GOM Stat) | Energy vulnerability scaling (0 occurrences in client blueprints). |
| **`374`** | `stat_cbt_damage_taken_scale_type_kinetic_modifier_percentage` | Target Type Vulnerability | **[-] Unused in Blueprints** | `Unassigned` | None (Unused GOM Stat) | Kinetic vulnerability scaling (0 occurrences in client blueprints). |
| **`46`** | `STAT_cbt_damage_received_modifier_percentage` | Target AoE / Damage Received | **[x] Verified in BUCKET_2 (AoE)** | `BUCKET_2` | Target Debuff Module / Raid Debuffs | Overwhelmed (+10% AoE) is an independent multiplicative layer. |
| **`465`** | `stat_cbt_damage_taken_scale_tag_aoe_modifier` | Target Tag Vulnerability | **[-] Unused in Blueprints** | `Unassigned` | None (Unused GOM Stat) | Explicit AoE tag vulnerability (0 occurrences in client blueprints). |
| **`467`** | `stat_cbt_damage_taken_scale_tag_dot_modifier` | Target Tag Vulnerability | **[-] Unused in Blueprints** | `Unassigned` | None (Unused GOM Stat) | DoT tag vulnerability (0 occurrences in client blueprints). |
| **`220`** | `STAT_cbt_damage_done_if_target_health_low_modifier_percentage` | Target Low-Health Execute | **[x] Verified in BUCKET_3** | `BUCKET_3` | Imperial Agent, Bounty Hunter (+4 more) | Execute sub-30% HP (+25% / +20%) is an independent multiplicative layer. |
| **`221`** | `STAT_cbt_damage_done_if_target_bleeding_modifier_percentage` | Target State: Bleeding | **[x] Verified in BUCKET_5** | `BUCKET_5` | Bounty Hunter, Sith Warrior (+1 more) | Bonus damage while target is bleeding. Proven independent multiplicative layer (BUCKET_5) via Test 12 (Bloodbath) and Test 14 (Blood Tracker). |
| **`222`** | `STAT_cbt_damage_done_if_target_stunned_modifier_percentage` | Target State: Stunned (Damage Done) | **[-] Unused in Blueprints** | `Unassigned` | None (Unused GOM Stat) | Damage done bonus against stunned targets (0 occurrences in player abilities and passives). |
| **`223`** | `STAT_cbt_damage_received_if_target_stunned_modifier_percentage` | Target State: Stunned / Incapacitated | **[x] Defensive Stun DR** | `Defensive DR` | Bounty Hunter, Jedi Consular (+4 more) | Defensive damage reduction utility (-30% incoming damage while stunned/incapacitated). Not an offensive multiplier. |
| **`250`** | `STAT_cbt_damage_done_if_target_on_fire_modifier_percentage` | Target State: On Fire / Burn | **[x] Verified in BUCKET_6** | `BUCKET_6` | Jedi Knight | Bonus damage while target is burning. Proven independent multiplicative layer (BUCKET_6) via Test 16 (Burning Storm on Vigilance Guardian Cyclone Slash). |
| **`389`** | `STAT_cbt_damage_done_if_target_accuracy_reduced_modifier_percentage` | Target State: Accuracy Reduced | **[x] Verified in BUCKET_4** | `BUCKET_4` | Jedi Consular, Sith Inquisitor | Target-state accuracy reduced conditional (+15% Torment) is an independent multiplicative bucket. |
| **`127`** | `STAT_cbt_dual_wield_damage_done_modifier_percentage` | Dual Wield Conditional | **[x] Verified Offhand Scalar** | `Offhand Scalar (0.25 + val)` | Jedi Knight, Sith Warrior | Dual-wield bonus damage. Proven in Test 10 on Carnage Marauder (Assault OH hit). |
| **`393`** | `stat_cbt_damage_dealt_scale_type_elemental_modifier_percentage` | Caster Elemental Dealt Scale | **[-] Unused in Blueprints** | `Unassigned` | None (Unused GOM Stat) | Caster bonus to elemental damage dealt (0 occurrences in client blueprints). |
| **`395`** | `stat_cbt_damage_dealt_scale_type_energy_modifier_percentage` | Caster Energy Dealt Scale | **[x] Verified in BUCKET_1** | `BUCKET_1` | Bounty Hunter, Trooper | Caster bonus to energy damage dealt. Proven additive in BUCKET_1 via Test 13 (High Energy Gas Cylinder). |
| **`397`** | `stat_cbt_damage_dealt_scale_type_kinetic_modifier_percentage` | Caster Kinetic Dealt Scale | **[x] Verified in BUCKET_1** | `BUCKET_1` | Bounty Hunter, Trooper | Caster bonus to kinetic damage dealt. Co-granted with 395 in High Energy Gas Cylinder / Cell. Proven additive in BUCKET_1 via Test 13 (High Energy Gas Cylinder). |
| **`405`** | `stat_cbt_damage_dealt_scale_channel_ranged_modifier_percentage` | Caster Channel Dealt Scale | **[x] Target Output Debuff** | `Target Debuff` | Sith Warrior, Jedi Knight (+4 more) | Enemy output debuff (-5% / -15% outgoing ranged damage e.g. Combust, Slow Time, Awe, Wither). |
| **`407`** | `stat_cbt_damage_dealt_scale_channel_melee_modifier_percentage` | Caster Channel Dealt Scale | **[x] Verified in BUCKET_1** | `BUCKET_1` | Jedi Knight, Sith Warrior | Melee damage dealt bonus. Proven additive in BUCKET_1 via Test 11 (Vicious Slash / Ravager). |
| **`409`** | `stat_cbt_damage_dealt_scale_channel_force_modifier_percentage` | Caster Channel Dealt Scale | **[x] Verified in BUCKET_1** | `BUCKET_1` | Jedi Knight, Sith Warrior | Force damage dealt bonus. Proven additive in BUCKET_1 via Test 15 (Shii-Cho Mastery on Rage Juggernaut Force Choke). |
| **`411`** | `stat_cbt_damage_dealt_scale_channel_tech_modifier_percentage` | Caster Channel Dealt Scale | **[x] Target Output Debuff** | `Target Debuff` | Bounty Hunter, Trooper, Consular (+3 more) | Enemy output debuff (-5% / -15% outgoing tech damage e.g. Firestorm, Guardian Slash, Crushing Blow, Ion Storm). |
| **`413`** | `STAT_cbt_base_weapon_damage_modifier_percentage` | Caster Base Weapon Damage Multiplier | **[x] Base Weapon Dice Multiplier** | `Base Weapon Pipeline` | Imperial Agent, Smuggler, Warrior, Knight | Multiplies base weapon min/max damage roll in calculate_base_damage() (+20% in Skirmisher, Single Saber Mastery, Blasters Blazing). |
| **`399`** | `stat_cbt_damage_dealt_scale_type_internal_modifier_percentage` | Caster Internal Dealt Scale | **[-] Unused in Blueprints** | `Unassigned` | None (Unused GOM Stat) | Caster bonus to internal damage dealt (0 occurrences in client blueprints). |
| **`454`** | `stat_cbt_aoe_damage_dealt_modifier` | Caster AoE Dealt Scale | **[-] Unused in Blueprints** | `Unassigned` | None (Unused GOM Stat) | Caster bonus to AoE damage dealt (0 occurrences in client blueprints). |
| **`464`** | `stat_cbt_damage_dealt_scale_tag_aoe_modifier` | Caster AoE Dealt Scale | **[-] Unused in Blueprints** | `Unassigned` | None (Unused GOM Stat) | Caster bonus to AoE tag damage dealt (0 occurrences in client blueprints). |
| **`466`** | `stat_cbt_damage_dealt_scale_tag_dot_modifier` | Caster DoT Dealt Scale | **[-] Unused in Blueprints** | `Unassigned` | None (Unused GOM Stat) | Caster bonus to DoT tag damage dealt (0 occurrences in client blueprints). |

---

## 3. Detailed Stat Profiles & Class Availability

### ID `79` — `STAT_cbt_damage_done_modifier_percentage`

* **Category**: Caster General Damage Done

* **Status**: **[x] Verified in BUCKET_1** (Bucket: `BUCKET_1`)

* **Verification Record**: Test 1, Test 2, Test 6

* **Testing Notes**: Tag-scoped and ability-scoped instances add together in BUCKET_1.

#### Known Abilities & Talents in Blueprints:

* **Imperial Agent (Operative / Sniper)**:

  * `Ballistic Shield` (+5.0%)

  * `Sleep Dart` (+-50.0%)

  * `Tactical Advantage` (+5.0%)

  * `Potent Brew` (+5.0% -> corrosive_dart)

  * `Skirmisher` (+15.0% -> overload_shot)

  * `Skirmisher` (+50.0% -> aoe_damage)

  * `Steady Shots` (+5.0% -> series_of_shots)

  * `Steady Shots` (+5.0% -> snipe)

* **Bounty Hunter (Mercenary / Powertech)**:

  * `Explosive Fuel` (+20.0%)

  * `Guard` (+3.0%)

  * `Guard` (+-50.0%)

  * `Supercharge` (+0.1%)

  * `Power Yield` (+2.0%)

  * `Combat Support Cylinder` (+3.0%)

  * `Thermal Yield` (+2.0%)

* **General / Other**:

  * `Active Reload` (+5.0%)

  * `Target Eliminator` (+2.0%)

  * `Shock Trooper` (+10.0%)

  * `Berserk` (+3.0%)

  * `Stationary Grit` (+3.0%)

  * `Fighting Spirit` (+3.0%)

  * `Berserker's Call` (+5.0%)

  * `Advanced Kyrprax Triage Adrenal` (+-20.0%)

* **Jedi Consular (Shadow / Sage)**:

  * `Combat Technique` (+-10.0%)

  * `Force Stun` (+-25.0%)

  * `Guard` (+3.0%)

  * `Guard` (+-50.0%)

  * `Mind Maze` (+-25.0%)

  * `Spinning Strike+` (+2.0%)

  * `Applied Force` (+5.0% -> double_strike)

  * `Applied Force` (+5.0% -> whirling_blow)

* **Jedi Knight (Guardian / Sentinel)**:

  * `Guard` (+3.0%)

  * `Guard` (+-50.0%)

  * `Inspiration` (+10.0%)

  * `Shii-Cho Form` (+3.0%)

  * `Heightened Blows` (+5.0%)

  * `Soresu Form` (+-10.0%)

  * `Heightened Power` (+5.0%)

  * `Zealous Leap` (+3.0%)

* **Sith Inquisitor (Assassin / Sorcerer)**:

  * `Dark Charge` (+-10.0%)

  * `Electrocute` (+-25.0%)

  * `Guard` (+3.0%)

  * `Guard` (+-50.0%)

  * `Mind Trap` (+-25.0%)

  * `Assassinate+` (+2.0%)

  * `Thrashing Blades` (+5.0% -> thrash)

  * `Thrashing Blades` (+5.0% -> lacerate)

* **Sith Warrior (Juggernaut / Marauder)**:

  * `Bloodthirst` (+10.0%)

  * `Guard` (+3.0%)

  * `Guard` (+-50.0%)

  * `Shii-Cho Form` (+3.0%)

  * `Juyo Form` (+1.0%)

  * `Cascading Domination` (+5.0%)

  * `Soresu Form` (+-10.0%)

  * `Cascading Power` (+5.0%)

* **Smuggler (Scoundrel / Gunslinger)**:

  * `Scrambling Field` (+5.0%)

  * `Tranquilizer` (+-50.0%)

  * `Upper Hand` (+5.0%)

  * `Blasters Blazing` (+15.0% -> quick_shot)

  * `Blasters Blazing` (+50.0% -> aoe_damage)

  * `Browbeater` (+5.0% -> vital_shot)

  * `Steady Shots` (+5.0% -> speed_shot)

  * `Steady Shots` (+5.0% -> charged_burst)

* **Trooper (Commando / Vanguard)**:

  * `Battle Focus` (+20.0%)

  * `Guard` (+3.0%)

  * `Guard` (+-50.0%)

  * `Supercharge` (+0.1%)

  * `Combat Support Cell` (+3.0%)

  * `Durasteel Armor` (+2.0%)

  * `Ion Cell` (+-10.0%)

---

### ID `78` — `STAT_cbt_damage_done_modifier_fixed`

* **Category**: Caster Flat Damage Added

* **Status**: **[x] Verified No-Op (Flat)** (Bucket: `No-Op (0.20 Flat)`)

* **Verification Record**: [Test 17 — Caster Flat Damage Done via Pull and Pummel](modifier_bucketing_log.md#test-17--caster-flat-damage-done-stat_cbt_damage_done_modifier_fixed--gom-78-via-pull-and-pummel-abltrooperharpoon)

* **Testing Notes**: Flat bonus damage stat (`_fixed`). In `abl.trooper.harpoon` (*Pull and Pummel*), Effect 6 specifies `stat: 78` (`STAT_cbt_damage_done_modifier_fixed`), `amount: 0.20`, `is_percent: false` (unlike its Powertech mirror *Reel and Rattle* in `abl.bounty_hunter.grapple`, which uses `stat: 79` `STAT_cbt_damage_done_modifier_percentage`). Empirical testing on Tactics Vanguard (`Stockstrike`) proved that Stat `78` does not act as a percentage multiplier and deals `+0` bonus integer damage when given `0.20`.

---

### ID `386` — `stat_cbt_damage_taken_scale_channel_force_modifier_percentage`

* **Category**: Target Channel Vulnerability

* **Status**: **[x] Verified in BUCKET_1** (Bucket: `BUCKET_1`)

* **Verification Record**: Test 2

* **Testing Notes**: Force Vulnerability (+5%) is additive inside BUCKET_1.

#### Known Abilities & Talents in Blueprints:

* **Imperial Agent (Operative / Sniper)**:

  * `Evasion` (+-75.0%)

  * `Evasive Maneuvers` (+-75.0%)

* **Jedi Consular (Shadow / Sage)**:

  * `Vanquish` (+5.0%)

  * `Profundity` (+5.0%)

  * `Squelch` (+5.0%)

  * `Mental Momentum` (+5.0%)

* **Jedi Knight (Guardian / Sentinel)**:

  * `Zealous Judgment` (+-75.0%)

* **General / Other**:

  * `Shattered Armor` (+5.0%)

* **Sith Inquisitor (Assassin / Sorcerer)**:

  * `Saber Conduit` (+5.0%)

  * `Eradicate` (+5.0%)

  * `Forked Darkness` (+5.0%)

  * `Demolish` (+5.0%)

* **Sith Warrior (Juggernaut / Marauder)**:

  * `Ruthless Aggressor` (+-75.0%)

* **Smuggler (Scoundrel / Gunslinger)**:

  * `Dodge` (+-75.0%)

  * `Dodge Stance` (+-75.0%)

---

### ID `384` — `stat_cbt_damage_taken_scale_channel_melee_modifier_percentage`

* **Category**: Target Channel Vulnerability

* **Status**: **[x] Verified in BUCKET_1** (Bucket: `BUCKET_1`)

* **Verification Record**: Test 6

* **Testing Notes**: Beat Down (+5%) is additive inside BUCKET_1.

#### Known Abilities & Talents in Blueprints:

* **Jedi Knight (Guardian / Sentinel)**:

  * `Focused Slash` (+5.0%)

  * `Concentrated Slice` (+5.0%)

  * `Burning Purpose` (+5.0%)

* **General / Other**:

  * `Shattered Armor` (+5.0%)

* **Sith Warrior (Juggernaut / Marauder)**:

  * `Enraged Slash` (+5.0%)

  * `Furious Strike` (+5.0%)

  * `Eviscerate` (+5.0%)

---

### ID `382` — `stat_cbt_damage_taken_scale_channel_ranged_modifier_percentage`

* **Category**: Target Channel Vulnerability

* **Status**: **[x] Verified BUCKET_1** (Bucket: `BUCKET_1`)

* **Verification Record**: Test 9 (docs/modifier_bucketing_log.md)

* **Testing Notes**: Marked (+5% Ranged). Proven additive in BUCKET_1 with Ironsights (+10% / 79) and Supercharge (+1% / 79). Observed hits 18,261 (non-crit) and 36,604 (crit) sit strictly below the multiplicative floor (18,331 and 36,653) and inside the additive range (18,245–20,153 and 36,480–40,294).

#### Known Abilities & Talents in Blueprints:

* **Imperial Agent (Operative / Sniper)**:

  * `Corrosive Dart` (+5.0%)

* **Bounty Hunter (Mercenary / Powertech)**:

  * `Priming Shot` (+5.0%)

  * `Serrated Shot` (+5.0%)

* **General / Other**:

  * `Shattered Armor` (+5.0%)

* **Smuggler (Scoundrel / Gunslinger)**:

  * `Vital Shot` (+5.0%)

* **Trooper (Commando / Vanguard)**:

  * `Serrated Bolt` (+5.0%)

  * `Vortex Bolt` (+5.0%)

---

### ID `388` — `stat_cbt_damage_taken_scale_channel_tech_modifier_percentage`

* **Category**: Target Channel Vulnerability

* **Status**: **[x] Verified BUCKET_1** (Bucket: `BUCKET_1`)

* **Verification Record**: Test 8 (docs/modifier_bucketing_log.md)

* **Testing Notes**: Susceptible (+5% Tech). Proven additive in BUCKET_1 with Assailable Elemental (+7% / 370). Observed hit 3,821 perfectly matches additive prediction 3,820.68.

#### Known Abilities & Talents in Blueprints:

* **Imperial Agent (Operative / Sniper)**:

  * `Evasion` (+-75.0%)

  * `Shiv` (+5.0%)

  * `Calculated Frenzy` (+5.0%)

  * `Evasive Maneuvers` (+-75.0%)

* **Bounty Hunter (Mercenary / Powertech)**:

  * `Thermal Detonator` (+5.0%)

  * `Scorch` (+5.0%)

* **Jedi Knight (Guardian / Sentinel)**:

  * `Zealous Judgment` (+-75.0%)

* **General / Other**:

  * `Shattered Armor` (+5.0%)

* **Sith Warrior (Juggernaut / Marauder)**:

  * `Ruthless Aggressor` (+-75.0%)

* **Smuggler (Scoundrel / Gunslinger)**:

  * `Blaster Whip` (+5.0%)

  * `Dodge` (+-75.0%)

  * `Dodge Stance` (+-75.0%)

  * `Rolling Punches` (+5.0%)

* **Trooper (Commando / Vanguard)**:

  * `Plasmatize` (+5.0%)

  * `Assault Plastique` (+5.0%)

---

### ID `376` — `stat_cbt_damage_taken_scale_type_internal_modifier_percentage`

* **Category**: Target Type Vulnerability

* **Status**: **[x] Verified in BUCKET_1** (Bucket: `BUCKET_1`)

* **Verification Record**: Test 2

* **Testing Notes**: Assailable Internal (+7%) is additive inside BUCKET_1.

#### Known Abilities & Talents in Blueprints:

* **Imperial Agent (Operative / Sniper)**:

  * `Volatile Substance` (+7.0%)

  * `Corrosive Grenade` (+7.0%)

* **Bounty Hunter (Mercenary / Powertech)**:

  * `Incendiary Missile` (+7.0%)

  * `Mandalorian Warhead` (+7.0%)

* **Jedi Consular (Shadow / Sage)**:

  * `Shifted Balance` (+7.0%)

* **Jedi Knight (Guardian / Sentinel)**:

  * `Burning Focus` (+7.0%)

* **General / Other**:

  * `Shattered Armor` (+7.0%)

* **Sith Inquisitor (Assassin / Sorcerer)**:

  * `Death Brand` (+7.0%)

* **Sith Warrior (Juggernaut / Marauder)**:

  * `Bloodlust` (+7.0%)

* **Smuggler (Scoundrel / Gunslinger)**:

  * `Shrap Bomb` (+7.0%)

  * `Blood Boiler` (+7.0%)

* **Trooper (Commando / Vanguard)**:

  * `Incendiary Round` (+7.0%)

  * `Armor Piercing Round` (+7.0%)

---

### ID `370` — `stat_cbt_damage_taken_scale_type_elemental_modifier_percentage`

* **Category**: Target Type Vulnerability

* **Status**: **[x] Verified BUCKET_1** (Bucket: `BUCKET_1`)

* **Verification Record**: Test 8 (docs/modifier_bucketing_log.md)

* **Testing Notes**: Assailable Elemental (+7%). Proven additive in BUCKET_1 with Susceptible Tech (+5% / 388). Observed hit 3,821 perfectly matches additive prediction 3,820.68.

#### Known Abilities & Talents in Blueprints:

* **Imperial Agent (Operative / Sniper)**:

  * `Volatile Substance` (+7.0%)

  * `Corrosive Grenade` (+7.0%)

* **Bounty Hunter (Mercenary / Powertech)**:

  * `Incendiary Missile` (+7.0%)

  * `Mandalorian Warhead` (+7.0%)

* **Jedi Consular (Shadow / Sage)**:

  * `Shifted Balance` (+7.0%)

* **Jedi Knight (Guardian / Sentinel)**:

  * `Burning Focus` (+7.0%)

* **General / Other**:

  * `Shattered Armor` (+7.0%)

* **Sith Inquisitor (Assassin / Sorcerer)**:

  * `Death Brand` (+7.0%)

* **Sith Warrior (Juggernaut / Marauder)**:

  * `Bloodlust` (+7.0%)

* **Smuggler (Scoundrel / Gunslinger)**:

  * `Shrap Bomb` (+7.0%)

  * `Blood Boiler` (+7.0%)

* **Trooper (Commando / Vanguard)**:

  * `Incendiary Round` (+7.0%)

  * `Armor Piercing Round` (+7.0%)

---

### ID `372` — `stat_cbt_damage_taken_scale_type_energy_modifier_percentage`

* **Category**: Target Type Vulnerability

* **Status**: **[-] Unused in Blueprints** (Bucket: `Unassigned`)

* **Verification Record**: -

* **Testing Notes**: Energy vulnerability scaling. Theoretical GOM enum constant; 0 occurrences across all active extracted blueprints.

No direct class blueprint occurrences found; evaluated via engine hooks.

---

### ID `374` — `stat_cbt_damage_taken_scale_type_kinetic_modifier_percentage`

* **Category**: Target Type Vulnerability

* **Status**: **[-] Unused in Blueprints** (Bucket: `Unassigned`)

* **Verification Record**: -

* **Testing Notes**: Kinetic vulnerability scaling. Theoretical GOM enum constant; 0 occurrences across all active extracted blueprints.

No direct class blueprint occurrences found; evaluated via engine hooks.

---

### ID `46` — `STAT_cbt_damage_received_modifier_percentage`

* **Category**: Target AoE / Damage Received

* **Status**: **[x] Verified in BUCKET_2 (AoE)** (Bucket: `BUCKET_2`)

* **Verification Record**: Test 3, Test 5

* **Testing Notes**: Overwhelmed (+10% AoE) is an independent multiplicative layer.

#### Known Abilities & Talents in Blueprints:

* **Imperial Agent (Operative / Sniper)**:

  * `Ballistic Shield` (+-20.0%)

  * `Combat Stims` (+-20.0%)

  * `Toxic Regulators` (+-30.0% -> damage_over_time)

* **Bounty Hunter (Mercenary / Powertech)**:

  * `Guard` (+-5.0%)

  * `Flame Suit` (+-30.0% -> damage_over_time)

* **General / Other**:

  * `Berserk` (+6.0%)

  * `Final Breath 3` (+-5.0%)

  * `Suppression` (+10.0%)

  * `Take Cover` (+-5.0%)

  * `Crouch` (+-5.0%)

* **Jedi Consular (Shadow / Sage)**:

  * `Force Speed` (+-25.0%)

  * `Force Stun` (+5.0%)

  * `Guard` (+-5.0%)

  * `Rescue` (+-25.0%)

  * `Spinning Kick` (+6.0%)

  * `Stealth` (+-15.0%)

  * `Stealth` (+-20.0%)

  * `Stealth` (+5.0%)

* **Jedi Knight (Guardian / Sentinel)**:

  * `Force Camouflage` (+-50.0%)

  * `Guard` (+-5.0%)

  * `Guarded by the Force` (+-99.0%)

  * `Guardian Leap` (+-30.0%)

  * `Guardian Leap` (+-20.0%)

  * `Warding Call` (+-40.0%)

* **Sith Inquisitor (Assassin / Sorcerer)**:

  * `Electrocute` (+5.0%)

  * `Extrication` (+-25.0%)

  * `Force Speed` (+-25.0%)

  * `Guard` (+-5.0%)

  * `Spike` (+5.0%)

  * `Stealth` (+-20.0%)

  * `Stealth` (+-15.0%)

  * `Stealth` (+5.0%)

* **Sith Warrior (Juggernaut / Marauder)**:

  * `Force Camouflage` (+-50.0%)

  * `Guard` (+-5.0%)

  * `Intercede` (+-30.0%)

  * `Intercede` (+-20.0%)

  * `Undying Rage` (+-99.0%)

  * `Invincible` (+-40.0%)

* **Smuggler (Scoundrel / Gunslinger)**:

  * `Scrambling Field` (+-20.0%)

  * `Pugnacious` (+-20.0%)

  * `Pugnacious+` (+-20.0%)

  * `Concussion` (+-30.0% -> damage_over_time)

* **Trooper (Commando / Vanguard)**:

  * `Guard` (+-5.0%)

  * `Assault Frame` (+-30.0% -> damage_over_time)

---

### ID `465` — `stat_cbt_damage_taken_scale_tag_aoe_modifier`

* **Category**: Target Tag Vulnerability

* **Status**: **[-] Unused in Blueprints** (Bucket: `Unassigned`)

* **Verification Record**: -

* **Testing Notes**: Explicit AoE tag vulnerability. Theoretical GOM enum constant; 0 occurrences across all active extracted blueprints.

No direct class blueprint occurrences found; evaluated via engine hooks.

---

### ID `467` — `stat_cbt_damage_taken_scale_tag_dot_modifier`

* **Category**: Target Tag Vulnerability

* **Status**: **[-] Unused in Blueprints** (Bucket: `Unassigned`)

* **Verification Record**: -

* **Testing Notes**: DoT tag vulnerability. Theoretical GOM enum constant; 0 occurrences across all active extracted blueprints.

No direct class blueprint occurrences found; evaluated via engine hooks.

---

### ID `220` — `STAT_cbt_damage_done_if_target_health_low_modifier_percentage`

* **Category**: Target Low-Health Execute

* **Status**: **[x] Verified in BUCKET_3** (Bucket: `BUCKET_3`)

* **Verification Record**: Test 4, Test 5

* **Testing Notes**: Execute sub-30% HP (+25% / +20%) is an independent multiplicative layer.

#### Known Abilities & Talents in Blueprints:

* **Imperial Agent (Operative / Sniper)**:

  * `Devouring Microbes` (+15.0% -> poison_effect)

* **Bounty Hunter (Mercenary / Powertech)**:

  * `Burnout` (+10.0% -> flamethrower_ability)

* **Jedi Consular (Shadow / Sage)**:

  * `Mental Scarring` (+15.0% -> periodic_damage)

  * `Judgement` (+5.0%)

  * `Aching Mind` (+25.0% -> force_in_balance)

  * `Aching Mind` (+25.0% -> periodic_damage)

  * `Aching Mind` (+25.0% -> vanquish_dd)

* **Sith Inquisitor (Assassin / Sorcerer)**:

  * `Executioner` (+5.0%)

  * `Inevitable Demise` (+25.0% -> death_field)

  * `Inevitable Demise` (+25.0% -> periodic_damage)

  * `Inevitable Demise` (+25.0% -> demolish_dd)

  * `Creeping Death` (+15.0% -> periodic_damage)

* **Smuggler (Scoundrel / Gunslinger)**:

  * `Cold Blooded` (+15.0% -> bleed_ability)

* **Trooper (Commando / Vanguard)**:

  * `Burnout` (+10.0% -> elemental_attack)

---

### ID `221` — `STAT_cbt_damage_done_if_target_bleeding_modifier_percentage`

* **Category**: Target State: Bleeding

* **Status**: **[x] Verified BUCKET_5** (Independent Multiplicative Layer)

* **Verification Record**: [Test 12 — Target State: Bleeding vs BUCKET_1 & BUCKET_2](modifier_bucketing_log.md#test-12--target-state-bleeding-stat_cbt_damage_done_if_target_bleeding_modifier_percentage--gom-221-vs-bucket_1--bucket_2) & [Test 14 — Target State: Bleeding Re-Verification on Advanced Prototype](modifier_bucketing_log.md#test-14--target-state-bleeding-re-verification-on-advanced-prototype-stat_cbt_damage_done_if_target_bleeding_modifier_percentage--gom-221-via-internal-bleed-dot-retractable-blade)

* **Testing Notes**: Bonus damage while target is bleeding. Test on Marauder / Sentinel or Dirty Fighting / Virulence.

#### Known Abilities & Talents in Blueprints:

* **Bounty Hunter (Mercenary / Powertech)**:

  * `Blood Tracker` (+3.0%)

* **Sith Warrior (Juggernaut / Marauder)**:

  * `Bloodbath` (+25.0% -> sweeping_slash)

* **Trooper (Commando / Vanguard)**:

  * `Triumph` (+3.0%)

---

### ID `222` — `STAT_cbt_damage_done_if_target_stunned_modifier_percentage`

* **Category**: Target State: Stunned (Damage Done)

* **Status**: **[-] Unused in Blueprints** (Bucket: `Unassigned`)

* **Verification Record**: -

* **Testing Notes**: Damage done bonus against stunned targets. Theoretical GOM enum constant; 0 occurrences across audited player abilities and passives.

No direct class blueprint occurrences found; evaluated via engine hooks.

---

### ID `223` — `STAT_cbt_damage_received_if_target_stunned_modifier_percentage`

* **Category**: Target State: Stunned / Incapacitated

* **Status**: **[x] Defensive Stun DR** (Bucket: `Defensive DR`)

* **Verification Record**: -

* **Testing Notes**: Defensive damage reduction utility (-30% incoming damage while stunned or incapacitated). Not an offensive multiplier.

#### Known Abilities & Talents in Blueprints:

* **Bounty Hunter (Mercenary / Powertech)**:

  * `Hunter Killer Damage Reduction` (+-30.0%)

  * `Hitman` (+-30.0%)

* **Jedi Consular (Shadow / Sage)**:

  * `Intangible Spirit` (+-30.0%)

* **Jedi Knight (Guardian / Sentinel)**:

  * `Stalwart Defense` (+-30.0%)

* **Sith Inquisitor (Assassin / Sorcerer)**:

  * `Formless Phantom` (+-30.0%)

* **Sith Warrior (Juggernaut / Marauder)**:

  * `Hardened Defense` (+-30.0%)

* **Trooper (Commando / Vanguard)**:

  * `Frontline Defense` (+-30.0%)

  * `Hunter Killer Damage Reduction` (+-30.0%)

---

### ID `250` — `STAT_cbt_damage_done_if_target_on_fire_modifier_percentage`

* **Category**: Target State: On Fire / Burn

* **Status**: **[x] Verified in BUCKET_6**

* **Verification Record**: [Test 16 — Target State: On Fire vs BUCKET_1 & BUCKET_2](modifier_bucketing_log.md#test-16--target-state-on-fire--burning-stat_cbt_damage_done_if_target_on_fire_modifier_percentage--gom-250-vs-bucket_1--bucket_2)

* **Testing Notes**: Bonus damage while target is burning. Proven independent multiplicative layer (BUCKET_6) via Test 16 (Burning Storm on Vigilance Guardian Cyclone Slash).

#### Known Abilities & Talents in Blueprints:

* **Jedi Knight (Guardian / Sentinel)**:

  * `Burning Storm` (+5.0% -> cyclone_slash)

---

### ID `389` — `STAT_cbt_damage_done_if_target_accuracy_reduced_modifier_percentage`

* **Category**: Target State: Accuracy Reduced

* **Status**: **[x] Verified in BUCKET_4**

* **Verification Record**: [Test 7 — Target-State Conditional: Accuracy Reduced vs BUCKET_1 & BUCKET_2](modifier_bucketing_log.md#test-7--target-state-conditional-accuracy-reduced-torment--389-vs-bucket_1--bucket_2)

* **Testing Notes**: Target-state accuracy reduced conditional (+15% Torment) is an independent multiplicative bucket.

#### Known Abilities & Talents in Blueprints:

* **Jedi Consular (Shadow / Sage)**:

  * `Psychokinesis` (+15.0% -> whirling_blow)

* **Sith Inquisitor (Assassin / Sorcerer)**:

  * `Torment` (+15.0% -> lacerate)

---

### ID `127` — `STAT_cbt_dual_wield_damage_done_modifier_percentage`

* **Category**: Dual Wield Conditional

* **Status**: **[x] Verified Offhand Weapon Scalar** (Additive to base offhand ratio: `0.25 + val`)

* **Verification Record**: [Test 10 — Dual Wield Damage Done vs Offhand Weapon Scalar](modifier_bucketing_log.md#test-10--dual-wield-damage-done-stat_cbt_dual_wield_damage_done_modifier_percentage--gom-127-vs-offhand-weapon-scalar)

* **Testing Notes**: Dual-wield bonus damage. Test on Marauder / Sentinel or Mercenary / Gunslinger.

#### Known Abilities & Talents in Blueprints:

* **Jedi Knight (Guardian / Sentinel)**:

  * `Dual Wield Mastery` (+25.0%)

* **Sith Warrior (Juggernaut / Marauder)**:

  * `Dual Wield Mastery` (+25.0%)

---

### ID `393` — `stat_cbt_damage_dealt_scale_type_elemental_modifier_percentage`

* **Category**: Caster Elemental Dealt Scale

* **Status**: **[-] Unused in Blueprints** (Bucket: `Unassigned`)

* **Verification Record**: -

* **Testing Notes**: Caster bonus to elemental damage dealt. Theoretical GOM enum constant; 0 occurrences across all active extracted blueprints.

No direct class blueprint occurrences found; evaluated via engine hooks.

---

### ID `395` — `stat_cbt_damage_dealt_scale_type_energy_modifier_percentage`

* **Category**: Caster Energy Dealt Scale

* **Status**: **[x] Verified in BUCKET_1**

* **Verification Record**: [Test 13 — Caster Type Dealt Scale: Energy / Kinetic vs BUCKET_1](modifier_bucketing_log.md#test-13--caster-type-dealt-scale-energy--kinetic-stat_cbt_damage_dealt_scale_type_energy_modifier_percentage--gom-395-and-kinetic--gom-397-vs-bucket_1)

* **Testing Notes**: Caster bonus to energy damage dealt.

#### Known Abilities & Talents in Blueprints:

* **Bounty Hunter (Mercenary / Powertech)**:

  * `High Energy Gas Cylinder` (+7.0%)

  * `High Energy Gas Cylinder` (+5.0%)

* **Trooper (Commando / Vanguard)**:

  * `High Energy Cell` (+7.0%)

  * `High Energy Cell` (+5.0%)

---

### ID `397` — `stat_cbt_damage_dealt_scale_type_kinetic_modifier_percentage`

* **Category**: Caster Kinetic Dealt Scale

* **Status**: **[x] Verified in BUCKET_1**

* **Verification Record**: [Test 13 — Caster Type Dealt Scale: Energy / Kinetic vs BUCKET_1](modifier_bucketing_log.md#test-13--caster-type-dealt-scale-energy--kinetic-stat_cbt_damage_dealt_scale_type_energy_modifier_percentage--gom-395-and-kinetic--gom-397-vs-bucket_1)

* **Testing Notes**: Caster bonus to kinetic damage dealt. Co-granted with 395 in High Energy Gas Cylinder / Cell.

#### Known Abilities & Talents in Blueprints:

* **Bounty Hunter (Mercenary / Powertech)**:

  * `High Energy Gas Cylinder` (+7.0%)

  * `High Energy Gas Cylinder` (+5.0%)

* **Trooper (Commando / Vanguard)**:

  * `High Energy Cell` (+7.0%)

  * `High Energy Cell` (+5.0%)

---

### ID `407` — `stat_cbt_damage_dealt_scale_channel_melee_modifier_percentage`

* **Category**: Caster Channel Dealt Scale

* **Status**: **[x] Verified in BUCKET_1**

* **Verification Record**: [Test 11 — Caster Channel Dealt Scale: Melee vs BUCKET_1](modifier_bucketing_log.md#test-11--caster-channel-dealt-scale-melee-stat_cbt_damage_dealt_scale_channel_melee_modifier_percentage--gom-407-vs-bucket_1)

* **Testing Notes**: Melee channel damage dealt modifier. Proven additive in BUCKET_1 via Test 11 on Vengeance Juggernaut (Vicious Slash / Ravager).

#### Known Abilities & Talents in Blueprints:

* **Sith Warrior (Juggernaut / Marauder)**:

  * `Ravager` (+5.0%)

* **Jedi Knight (Guardian / Sentinel)**:

  * `Master Focus` (+5.0%)

---

### ID `399` — `stat_cbt_damage_dealt_scale_type_internal_modifier_percentage`

* **Category**: Caster Internal Dealt Scale

* **Status**: **[-] Unused in Blueprints** (Bucket: `Unassigned`)

* **Verification Record**: -

* **Testing Notes**: Caster bonus to internal damage dealt. Theoretical GOM enum constant; 0 occurrences across all active extracted blueprints.

No direct class blueprint occurrences found; evaluated via engine hooks.

---

### ID `454` — `stat_cbt_aoe_damage_dealt_modifier`

* **Category**: Caster AoE Dealt Scale

* **Status**: **[-] Unused in Blueprints** (Bucket: `Unassigned`)

* **Verification Record**: -

* **Testing Notes**: Caster bonus to AoE damage dealt. Theoretical GOM enum constant; 0 occurrences across all active extracted blueprints.

No direct class blueprint occurrences found; evaluated via engine hooks.

---

### ID `464` — `stat_cbt_damage_dealt_scale_tag_aoe_modifier`

* **Category**: Caster AoE Dealt Scale

* **Status**: **[-] Unused in Blueprints** (Bucket: `Unassigned`)

* **Verification Record**: -

* **Testing Notes**: Caster bonus to AoE tag damage dealt. Theoretical GOM enum constant; 0 occurrences across all active extracted blueprints.

No direct class blueprint occurrences found; evaluated via engine hooks.

---

### ID `466` — `stat_cbt_damage_dealt_scale_tag_dot_modifier`

* **Category**: Caster DoT Dealt Scale

* **Status**: **[-] Unused in Blueprints** (Bucket: `Unassigned`)

* **Verification Record**: -

* **Testing Notes**: Caster bonus to DoT tag damage dealt. Theoretical GOM enum constant; 0 occurrences across all active extracted blueprints.

No direct class blueprint occurrences found; evaluated via engine hooks.
