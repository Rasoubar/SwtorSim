# SwtorSim Combat Math Reference

This document details the exact mathematical formulas implemented across [`combat_math.py`](../src/swtorsim/combat_math.py), [`combat_curves.py`](../src/swtorsim/combat_curves.py), [`entities.py`](../src/swtorsim/entities.py), and [`class_buffs.py`](../src/swtorsim/class_buffs.py).

---

## 1. Hit Resolution Pipeline Overview

Every damaging action resolves through [`calculate_hit(caster, target, action_data)`](../src/swtorsim/combat_math.py#L8-L35):

$$\text{Base Damage} \xrightarrow{\text{Mitigation}} \text{Post-Mitigation} \xrightarrow{\times \prod_{b} (1 + B_b)} \text{Post-Modifier} \xrightarrow{\text{Crit / Supercrit}} \lfloor \text{Final Damage} \rfloor$$

1. **Accuracy Roll** ([`accuracy_roll`](../src/swtorsim/combat_math.py#L747-L760)): Evaluated in `handle_damage_action` before `DamageHit` is created.
2. **Modifier Collection** ([`handle_modifiers`](../src/swtorsim/combat_math.py#L37-L66)): Evaluates all active buffs on the caster and debuffs on the target, sorting damage modifiers into **6 multiplicative buckets** and accumulating `bonus_crit_chance`, `bonus_crit_modifier`, `bonus_armor_pen`, and `base_weapon_damage_modifier`.
3. **Base Damage** ([`calculate_base_damage`](../src/swtorsim/combat_math.py#L649-L717)): Computes raw pre-mitigation ability damage from `StandardDamage` (`20125.0` at Level 80), `Bonus Damage`, weapon damage ranges, off-hand penalties, and flurry hit splitting.
4. **Armor Mitigation** ([`handle_mitigation`](../src/swtorsim/combat_math.py#L719-L728)): Reduces Kinetic (`1`) and Energy (`2`) damage by the target's effective armor damage reduction (after Sundered and caster Armor Penetration). Elemental (`3`) and Internal (`4`) bypass armor completely.
5. **Bucket Multiplication**: Multiplies `post_mit_damage` by `modifiers['total_multiplier']`.
6. **Critical & Supercrit Resolution** ([`calculate_crit`](../src/swtorsim/combat_math.py#L730-L745)): Rolls against effective critical chance, applies critical multiplier (including supercrit overflow when `crit_chance > 1.0`), and truncates to `int`.

---

## 2. Character Stat Recalculation & Diminishing Returns

### 2.1 Class Buffs & Companion Bonuses (`src/swtorsim/class_buffs.py`)

When a `Player` entity is initialized, [`build_permanent_buffs_for_player()`](../src/swtorsim/class_buffs.py#L140-L152) attaches two permanent baseline effects before any talent or gear passives are evaluated:

1. **Class Buffs**:
   - **Mark of Power** (Inquisitor / Consular): `+5%` Mastery (`STAT_att_mastery`, `is_percent=True`)
   - **Force Valor** (Warrior / Knight): `+5%` Melee, Ranged, Force, and Tech Bonus Damage (`STAT_cbt_melee_damage_bonus`, `STAT_cbt_ranged_damage_bonus`, `STAT_cbt_force_damage_bonus`, `STAT_cbt_tech_damage_bonus`, `is_percent=True`)
   - **Coordination** (Agent / Smuggler): `+5%` Critical Chance across all channels
   - **Unnatural Might** (Bounty Hunter / Trooper): `+5%` Endurance (`STAT_att_endurance`, `is_percent=True`)
2. **Hidden Companion Bonuses** (+1% each):
   - `+1%` Accuracy (`STAT_cbtAccuracy`)
   - `+1%` Critical Chance (`STAT_cbt_melee_crit`, `ranged_crit`, `force_crit`, `tech_crit`)
   - `+1%` Critical Multiplier / Surge (`STAT_cbt_melee_crit_damage_bonus`, `ranged`, `force`, `tech`)
   - `+1%` Alacrity (`STAT_rtg_alacrity`, `is_percent=True`)
   - `+1%` Endurance (`STAT_att_endurance`, `is_percent=True`)

### 2.2 Diminishing Returns Equation (`src/swtorsim/combat_curves.py`)

SWTOR converts combat ratings (`Critical Rating`, `Alacrity Rating`, `Accuracy Rating`) into decimal percentage bonuses using an exponential diminishing returns formula ([`calc_dr`](../src/swtorsim/combat_curves.py#L38-L44)):

$$f(R) = C \cdot \left(1 - \left(1 - \frac{1}{100 \cdot C}\right)^{\frac{R}{L \cdot D}}\right)$$

where:
- $R$ is the raw rating (`rating`),
- $L$ is the character level (`80` on Live, `85` on PTS),
- $C$ (`Cap`) and $D$ (`Divisor`) are extracted directly from `modDerivedStatMappingList` and `dcvCombatSystemsPerLevelPrototype` in [`combat_curves.json`](../data/extractor/combat_curves.json).

#### Derived Rating Curves (`combat_curves.py`)

| Derived Stat | Function | Cap ($C$) | Level 80 Effective Divisor ($80 \cdot D$) | Base Ungeared Offset |
| :--- | :--- | :--- | :--- | :--- |
| **Mastery -> Crit Chance** | [`mastery_crit_chance`](../src/swtorsim/combat_curves.py#L47-L50) | `0.20` (20%) | `43459.40` | `+0.05` (5% base crit) |
| **Crit Rating -> Crit Chance** | [`crit_rating_chance`](../src/swtorsim/combat_curves.py#L53-L56) | `0.30` (30%) | `19290.24` | `0.00` |
| **Crit Rating -> Crit Multiplier** | [`crit_rating_multiplier`](../src/swtorsim/combat_curves.py#L59-L62) | `0.30` (30%) | `19290.24` | `+0.50` (50% base surge) |
| **Alacrity Rating -> Alacrity %** | [`alacrity_pct`](../src/swtorsim/combat_curves.py#L65-L68) | `0.30` (30%) | `25720.32` | `0.00` |
| **Accuracy Rating -> Accuracy %** | [`accuracy_pct`](../src/swtorsim/combat_curves.py#L71-L74) | `0.30` (30%) | `25720.32` | `+1.00` (100% base accuracy) |

### 2.3 Bonus Damage Derivation (`Player.recalculate_stats`)

In [`Player.recalculate_stats()`](../src/swtorsim/entities.py#L220-L335):

1. **Effective Mastery & Power**:
   $$\text{Mastery} = (\text{RawMastery} + \Delta\text{Mastery}_{\text{flat}}) \times (1 + \Delta\text{Mastery}_{\%})$$
   $$\text{Power} = (\text{RawPower} + \Delta\text{Power}_{\text{flat}}) \times (1 + \Delta\text{Power}_{\%})$$

2. **Melee / Ranged Bonus Damage**:
   $$\text{BonusDamage}_{\text{M/R}} = \left(0.20 \cdot \text{Mastery} + 0.23 \cdot \text{Power} + \Delta\text{Bonus}_{\text{M/R, flat}}\right) \times \left(1 + \Delta\text{Bonus}_{\text{M/R, }\%}\right)$$

3. **Force / Tech Bonus Damage**:
   $$\text{BonusDamage}_{\text{F/T}} = \left(0.20 \cdot \text{Mastery} + 0.23 \cdot (\text{Power} + \text{FT}_{\text{MH}} + \text{FT}_{\text{OH}}) + \Delta\text{Bonus}_{\text{F/T, flat}}\right) \times \left(1 + \Delta\text{Bonus}_{\text{F/T, }\%}\right)$$
   where $\text{FT}_{\text{MH}}$ (`Force/Tech Bonus`) and $\text{FT}_{\text{OH}}$ (`Offhand Force/Tech Bonus`) are the Force/Tech power ratings on the equipped main-hand and off-hand items.

---

## 3. Alacrity, Time Scaling, and GCD Rounding

[`Player.scale_time_modifier(base_duration)`](../src/swtorsim/entities.py#L337-L340) scales durations inversely with total Alacrity:

$$T_{\text{scaled}} = \frac{T_{\text{base}}}{1 + \text{Alacrity}}$$

- **Global Cooldown (GCD)** ([`round_gcd_time`](../src/swtorsim/entities.py#L343-L348)):
  SWTOR snaps the scaled GCD down to the nearest tenth of a second (`0.1s` step) with a floating-point epsilon of `1e-9`:
  $$\text{GCD} = \frac{\lfloor (T_{\text{scaled}} + 10^{-9}) \times 10 \rfloor}{10}$$
  For a standard `1.5s` base GCD:
  - `7.1429%` Alacrity reaches the **`1.4s` GCD** tier (`1.5 / 1.071429 = 1.400s`).
  - `15.3846%` Alacrity reaches the **`1.3s` GCD** tier (`1.5 / 1.153846 = 1.300s`).
- **Ability Cooldowns, Cast Times, Channel Durations, and DoT Intervals**:
  - Scaled continuously by `1 / (1 + Alacrity)` (unless `abl_ignore_alacrity` or `eff_ignore_alacrity` is `True`), after applying any ability-specific flat or percentage modifiers (`STAT_cbt_cooldown`, `STAT_cbt_activation_time`, `STAT_cbt_channel_duration`, `STAT_cbt_effect_duration`, `STAT_cbt_effect_tick`).

---

## 4. Accuracy & Defense Roll

Before a `"damage"` action creates a `DamageHit` event, [`accuracy_roll(caster, target, attack_type, is_offhand)`](../src/swtorsim/combat_math.py#L747-L760) determines whether the strike lands:

$$\text{HitChance} = \text{Accuracy}_{\text{caster}} - \text{Defense}_{\text{target}} - \begin{cases} 0.33 & \text{if } \texttt{is\_offhand} \\ 0.00 & \text{otherwise} \end{cases}$$

- Operations Training Dummies have `defense_chance = 0.10` (`10%`).
- Therefore, **`1.10` (`110%`) Accuracy** guarantees `100%` hit rate on main-hand and Force/Tech attacks (`1.10 - 0.10 = 1.00`).
- Dual-wield off-hand weapon attacks incur a `-33%` (`0.33`) accuracy penalty (`0.77` hit chance at `110%` sheet accuracy).

---

## 5. Base Damage Calculation (`calculate_base_damage`)

[`calculate_base_damage(caster, action_data, attack_type, modifiers)`](../src/swtorsim/combat_math.py#L649-L717) computes pre-mitigation damage using the level-indexed `StandardHealth` / `StandardDamage` constant (`20,125.0` at Level 80; `36,245.0` at Level 85):

### 5.1 Force (`3`) & Tech (`4`) Attacks

$$\text{MinBase} = \text{SHP}_{\min} \times \text{StandardDamage} + \text{Coefficient} \times \text{BonusDamage}_{\text{F/T}}$$
$$\text{MaxBase} = \text{SHP}_{\max} \times \text{StandardDamage} + \text{Coefficient} \times \text{BonusDamage}_{\text{F/T}}$$

A uniform random value is rolled in $[\text{MinBase}, \text{MaxBase}]$, then multiplied by $(1 + \text{amount\_modifier\_percent})$.

### 5.2 Melee (`1`) & Ranged (`2`) Weapon Attacks

Weapon damage rolls uniformly between `Weapon Damage Min` and `Weapon Damage Max` (scaled by `1 + base_weapon_damage_modifier`, GOM Stat `413`):

$$\text{WeaponRoll}_{\text{MH}} = \mathcal{U}(\text{WepMin}_{\text{MH}}, \text{WepMax}_{\text{MH}}) \times (1 + \Delta\text{WepDmg}_{\%})$$

$$\text{Base}_{\text{MH}} = \text{WeaponRoll}_{\text{MH}} \times (1 + \text{AMP}) + \text{SHP} \times \text{StandardDamage} + \text{Coefficient} \times \text{BonusDamage}_{\text{M/R}}$$

- **Dual-Wield Off-Hand Hit (`use_offhand = True`)**:
  In SWTOR, off-hand weapon hits deal `30%` (`OFFHAND_DAMAGE_PENALTY = 0.30`) of the combined weapon + bonus damage scaling:
  $$\text{Base}_{\text{OH}} = \left(\text{WeaponRoll}_{\text{OH}} \times (1 + \text{AMP}) + \text{SHP}_{\text{OH}} \times \text{StandardDamage} + \text{Coeff}_{\text{OH}} \times \text{BonusDamage}_{\text{M/R}}\right) \times 0.30$$
- **Flurry / Multi-Strike Splitting (`hit_split`)**:
  When a single GOM damage action represents a multi-hit flurry (`flurry_M` tag) or a dual-wield strike split across main-hand and off-hand (`handle_damage_action`), `hit_split` divides the per-strike damage proportionally (and `scales_with_stack_charge` multiplies by `stack_multiplier`).

---

## 6. Armor Mitigation (`handle_mitigation`)

[`handle_mitigation(caster, target, base_damage, damage_type, modifiers)`](../src/swtorsim/combat_math.py#L719-L728) applies armor reduction:

- **Elemental (`3`) and Internal (`4`)**: Ignore armor completely ($\text{Mitigation} = 0$).
- **Kinetic (`1`) and Energy (`2`)**:
  1. Target effective armor rating (`Dummy.get_effective_armor()`):
     $$\text{Armor}_{\text{target}} = \text{BaseArmor} \times (1 + \Delta\text{Armor}_{\text{debuffs}})$$
     With *Sundered* (`-20%`), a Level 80 boss's `11,049` base armor drops to `11049 * 0.80 = 8839.2`.
  2. Caster armor penetration (`bonus_armor_pen`, GOM Stat `166`) reduces the target's effective armor further:
     $$\text{Armor}_{\text{final}} = \max\left(0,\; \text{Armor}_{\text{target}} \times (1 - \text{ArmorPen}_{\text{caster}})\right)$$
  3. Damage Reduction (`DR`) from [`armor_constants(level)`](../src/swtorsim/combat_curves.py#L31-L35) (`multiplier = 199.9` and `additive = 8000.0` at Level 80):
     $$\text{DR} = \frac{\text{Armor}_{\text{final}}}{\text{Armor}_{\text{final}} + L \cdot 199.9 + 8000.0}$$
  4. Post-mitigation damage:
     $$\text{PostMitDamage} = \text{BaseDamage} \times (1 - \text{DR})$$

---

## 7. The 6 Multiplicative Damage Buckets (`handle_modifiers`)

SWTOR groups damage-increasing buffs and target vulnerability debuffs into **6 distinct buckets** ([`combat_math.py`](../src/swtorsim/combat_math.py#L66-L73)). Modifiers **within** the same bucket sum additively, and the resulting bucket totals multiply together:

$$\text{TotalMultiplier} = \prod_{k \in \text{Buckets}} \left(1 + \sum_{i \in k} m_i\right)$$

| # | Bucket Constant | Key Name | Additive Members (Caster Buffs & Target Debuffs) |
| :--- | :--- | :--- | :--- |
| **1** | `BUCKET_NORMAL` | `"normal_percentage"` | General damage dealt (`STAT_cbt_damage_done_modifier_percentage`, `79`, `78`), target general/AoE damage taken (`46`, `STAT_cbt_damage_received_modifier_percentage`, *Overwhelmed*), and target channel vulnerabilities (`386` *Vulnerable*, `388` *Susceptible*, `384` *Beat Down*, `382` *Marked*, `463`, `456`, `458`, `459`). |
| **2** | `BUCKET_EXECUTE` | `"sub_30"` | Low-health execute modifiers (`STAT_cbt_damage_done_if_target_health_low_modifier_percentage`, `220`) active when `target.hp_ratio <= 0.30`. |
| **3** | `BUCKET_CHANNEL` | `"channel_scaling"` | Caster attack-channel scaling (`stat_cbt_damage_dealt_scale_channel_melee` / `ranged` / `force` / `tech`, `408`, `409`, `410`, `411`, `369`, `371`, `373`, `375`) and caster periodic damage dealt (`stat_cbt_damage_dealt_scale_periodic_modifier_percentage`, `412`) when `mod.targets` is empty. |
| **4** | `BUCKET_DAMAGE_TYPE` | `"damage_type_scaling"` | Caster damage-type scaling (`stat_cbt_damage_dealt_scale_type_kinetic` / `energy` / `elemental` / `internal`, `404`–`407`, `377`–`380`) and target damage-type vulnerabilities (`390`–`396`, `455`, `457`, *Assailable* `+7%` Elemental/Internal). |
| **5** | `BUCKET_TAG` | `"tag_scaling"` | Ability-specific and tag-targeted damage modifiers (`stat_cbt_damage_dealt_scale_tag_modifier_percentage`, `381`, `389`, `397`, `399`, `403`, and `412` when scoped to specific `mod.targets`). |
| **6** | `BUCKET_TARGET_STATE` | `"target_state"` | Conditional target-state damage amplifiers (`368` bleeding, `372` burning, `374` poisoned, `383` shocked, `385` vulnerable, `387` stunned/incapacitated). |

---

## 8. Critical Hit & Supercrit Resolution (`calculate_crit`)

> [!IMPORTANT]
> Per `AGENTS.md` Rule 1, the critical damage multiplier formula in [`calculate_crit()`](../src/swtorsim/combat_math.py#L730-L745) is calibrated strictly against live SWTOR combat logs and must **never** be altered.

1. **Effective Critical Chance**:
   $$\text{CritChance} = \text{BaseCrit}_{\text{caster}} + \Delta\text{CritChance}_{\text{modifiers}}$$

2. **Effective Critical Bonus (Surge)**:
   $$\text{Surge} = \text{BaseSurge}_{\text{caster}} + \Delta\text{Surge}_{\text{modifiers}}$$

3. **Supercrit Overflow (`Autocrit`)**:
   In SWTOR, when an ability's effective critical chance exceeds `1.0` (`100%`, e.g. via an autocrit buff), the excess critical chance above `1.0` converts into additional critical damage scaled by the player's Surge:
   $$\text{AutocritBonus} = \begin{cases} (\text{CritChance} - 1.0) \times \text{Surge} & \text{if } \text{CritChance} \ge 1.0 \\ 0.0 & \text{otherwise} \end{cases}$$

4. **Final Critical Damage**:
   If the roll $\mathcal{U}(0, 1) \le \text{CritChance}$:
   $$\text{FinalDamage} = \lfloor \text{PostModDamage} \times \left(1.0 + \text{Surge} + \text{AutocritBonus}\right) \rfloor$$
   Otherwise (non-crit):
   $$\text{FinalDamage} = \lfloor \text{PostModDamage} \rfloor$$
