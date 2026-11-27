# Combat Modifier Bucketing Verification Log

This document logs the empirical in-game testing used to construct the damage modifier buckets in [`src/swtorsim/combat_math_unbucketed.py`](../src/swtorsim/combat_math_unbucketed.py) from scratch, with zero pre-assumed bucket relationships.

---

## 0. Testing & Logging Protocol

1. **Step 1 — Test Declaration (Pre-Cast)**:

   * Specify any build/gear deltas from Section 1, the ability being cast, and the active caster/target state (dummy debuffs, buffs/DoTs, target HP >30% or <30%).

2. **Step 2 — Pre-Test Prediction Table**:

   * Calculate exact Base and Post-Mitigation damage.

   * List active modifiers already assigned to verified buckets (`BUCKET_1`, etc.) and the candidate modifier(s) under test (source name, GOM Stat Name & ID, target scope, `%` value).

   * Output the Options Table showing expected **Non-Crit** and **Crit** damage for placing the candidate modifier into each existing bucket vs a **New Bucket**.

3. **Step 3 — In-Game Observation**:

   * Cast the ability in-game and record observed **Non-Crit** and **Crit** values.

4. **Step 4 — Permanent Record & Code Lock**:

   * Append the full `Test #` record to Section 3 below (setup, base math, active modifiers, options table, observed numbers, conclusion).

   * Update the **Verified Buckets Registry** in Section 2 referencing `Test #`.

   * Update [`src/swtorsim/combat_math_unbucketed.py`](../src/swtorsim/combat_math_unbucketed.py) to assign the verified modifier from `None` to its proven `BUCKET_X` constant.

---

## 1. Baseline Test Build & Character Sheet

* **Class / Discipline**: Level 80 Hatred Assassin ([`data/extractor/disciplines/assassin/hatred.json`](../data/extractor/disciplines/assassin/hatred.json))

* **Choices**: [`data/choices/assassin/hatred/mali.json`](../data/choices/assassin/hatred/mali.json) (`23: 2` Fulguration, `27: 1`Languishing Lashes, `39: 3`, `43: 1`, `51: 1`, `64: 1` Pervasive Death, `68: 3` Befall, `73: 1` Maliciousness)

* **Equipped Legendary Package**: `Force Training` (`+3%` Melee & Force Bonus Damage, `STAT_cbt_melee_damage_bonus` / `STAT_cbt_force_damage_bonus`); `Berserker's` unequipped

* **Class & Companion Buffs**: All 4 Class Buffs (`Mark of Power`, `Unnatural Might`, `Coordination`, `Hunter's Boon`) + All Companion Bonuses (`+1%` Accuracy, `+1%` Crit Chance, `+1%` Crit Multiplier/Surge)

* **Base Stats** ([`data/builds/L80_14gcd_yellow.json`](../data/builds/L80_14gcd_yellow.json) with `-1,104` Power and `-324` Critical Rating):

  * **Mastery**: `16,570` base $\to$ **`17,398.5`** (with `+5%` Mark of Power)

  * **Power**: `14,394 - 1,104` = **`13,290`**

  * **Force Power**: **`9,332`**

  * **Critical Rating**: `4,029 - 324` = **`3,705`**

  * **Standard Health (`L80`)**: **`19,335`**

* **Derived Combat Stats**:

  * **Force Bonus Damage (`F_Bonus_Damage`)**:

    $$\left(0.20 \times 17398.5 + 0.23 \times (13290 + 9332)\right) \times (1 + 0.05_{\text{Unnatural Might}} + 0.03_{\text{Force Training}}) = 8682.76 \times 1.08 = \mathbf{9377.3808}$$

  * **Critical Multiplier (Surge)**:

    $$0.50_{\text{base}} + 0.01_{\text{companion}} + \text{DR}_{\text{crit\_dmg}}(3705) = 0.51 + 0.143618 = \mathbf{65.3618\%}\; (\mathbf{1.653618\times})$$

---

### Active Build & Gear Profile (Mercenary - Innovative Ordnance)

* **Class & Discipline**: Bounty Hunter / Mercenary / Innovative Ordnance & Arsenal (Level 80)

* **Equipped Items**:

  * Concentrated Fire & Overcharged Cells legendary implants

  * SC-4 Treatment Scanner tactical (irrelevant to damage)

  * Dual Blaster Pistols (Main Hand & Off Hand: `1,832 – 3,403`)

* **Character Sheet Stats**:

  * **Mastery**: `16,570` base $\to$ **`17,398.50`** (with `+5%` Consular/Inquisitor class buff)

  * **Power**: **`13,099.0`**

  * **Tech Power**: **`9,332.0`**

  * **Critical Rating**: **`3,555.0`**

  * **Standard Health (`L80`)**: **`19,335.0`**

* **Derived Combat Stats**:

  * **Base Bonus Damage**: $(0.20 \times 17398.50) + (0.23 \times 13099.0) = \mathbf{6,492.4700}$

  * **Ranged Bonus Damage**: $6492.4700 \times 1.05 = \mathbf{6,817.0935}$

  * **Tech Bonus Damage**: $(6492.4700 + 0.23 \times 9332.0) \times 1.05 = \mathbf{9,070.7715}$

  * **Critical Multiplier (Surge)**:

    $$0.50_{\text{base}} + 0.01_{\text{companion}} + \text{DR}_{\text{crit\_dmg}}(3555) = 0.51 + 0.139438 = \mathbf{64.9438\%}\; (\mathbf{1.649438\times})$$

---

## 2. Verified Buckets Registry

| Bucket Constant | Key | Verified Modifiers / GOM Stat IDs | Proven Multiplicative Against | Proven Additive Inside | Pending Cross-Bucket Tests / Notes | Proven By |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `BUCKET_1` | `"bucket_1"` | `STAT_cbt_damage_done_modifier_percentage` (`79`) — tag-targeted (`periodic_damage`), ability-targeted (`creeping_terror`, `leeching_strike`, `thrash`, `lacerate`, `priming_shot`), & general (`Supercharge`);<br>Target channel vulnerabilities: Force (`386` *Vulnerable*), Melee (`384` *Beat Down*), Tech (`388` *Susceptible*), Ranged (`382` *Marked*);<br>Target damage-type vulnerabilities: Internal (`376` *Assailable*), Elemental (`370` *Assailable*);<br>Caster channel dealt scale: Melee (`407` *Ravager*), Force (`409` *Shii-Cho Mastery*);<br>Caster damage-type dealt scale: Energy (`395` *High Energy Gas Cylinder*), Kinetic (`397` *High Energy Gas Cylinder*) | `BUCKET_2`, `BUCKET_3`, `BUCKET_4`, `BUCKET_5` | All member stats in `BUCKET_1` sum additively | Baseline damage pool (Attacker Damage Done + Target Channel/Type Vulnerabilities + Caster Channel/Type Dealt Scales) | **Test 1**, **Test 2**, **Test 6**, **Test 8**, **Test 9**, **Test 11**, **Test 13**, **Test 15** |
| `BUCKET_2` | `"bucket_2"` | Target AoE damage vulnerability: `STAT_cbt_damage_received_modifier_percentage` (`46`) targeting `tag.abl.utility.is_aoe` (*Overwhelmed*) | `BUCKET_1`, `BUCKET_3`, `BUCKET_4` | None yet | Independent multiplicative AoE layer | **Test 3**, **Test 5** |
| `BUCKET_3` | `"bucket_3"` | Low-health execute: `STAT_cbt_damage_done_if_target_health_low_modifier_percentage` (`220`) (*Inevitable Demise*, *Languishing Lashes*) | `BUCKET_1`, `BUCKET_2` | None yet | Multiplies against `BUCKET_1` and `BUCKET_2` independently | **Test 4**, **Test 5** |
| `BUCKET_4` | `"bucket_4"` | Target-state accuracy reduced conditional: `STAT_cbt_damage_done_if_target_accuracy_reduced_modifier_percentage` (`389`) (*Torment*) | `BUCKET_1`, `BUCKET_2` | None yet | Multiplies against `BUCKET_1` and `BUCKET_2` independently | **Test 7** |
| `BUCKET_5` | `"bucket_5"` | Target state bleeding conditional: `STAT_cbt_damage_done_if_target_bleeding_modifier_percentage` (`221`) (*Bloodbath*, *Blood Tracker*, *Triumph*) | `BUCKET_1`, `BUCKET_2` | None yet | Multiplies against `BUCKET_1` (Damage Done/Vulns) and `BUCKET_2` (AoE) independently | **Test 12**, **Test 14** |
| `BUCKET_6` | `"bucket_6"` | Target state on fire / burning conditional: `STAT_cbt_damage_done_if_target_on_fire_modifier_percentage` (`250`) (*Burning Storm*) | `BUCKET_1`, `BUCKET_2` | None yet | Multiplies against `BUCKET_1` (General/Vulns) and `BUCKET_2` (AoE) independently | **Test 16** |

---

## 3. Empirical Test Log

### Test 1 — `STAT_cbt_damage_done_modifier_percentage` (`79`): Tag-Targeted vs Ability-Targeted

* **Ability**: `Creeping Terror` (`abl.sith_inquisitor.skill.madness.creeping_terror`)

* **Target State**: Operations Training Dummy with **no debuffs**

* **Damage Type / Channel**: Internal (`4`) / Force (`3`) — bypasses armor mitigation (`Armor DR = 0%`), zero damage variance (`shp_min = shp_max = 0.03465`, `coeff = 0.35`)

* **Unmodified Base Damage**:

  $$\text{Base} = (0.35 \times 9377.3808) + (0.03465 \times 19335) = 3282.0833 + 669.9578 = \mathbf{3952.0410}$$

* **Active Hit Modifiers**:

  * **`M1` — Force Dread** (Discipline Passive): **`+15%`** (`STAT_cbt_damage_done_modifier_percentage`, `79`, targets `tag.abl.sith_inquisitor.periodic_damage`)

  * **`M2` — Fulguration** (Level 23 Choice): **`+10%`** (`STAT_cbt_damage_done_modifier_percentage`, `79`, targets `abl.sith_inquisitor.skill.madness.creeping_terror`)

#### Options Tested

| Option | Bucket Grouping | Multiplier | Expected Non-Crit | Expected Crit (`1.653618x`) |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Option 1 (Same Bucket / Additive)** | `[M1(+15%) + M2(+10%)]` | `1.25000` | **4,940** (`4940.05`) | **8,169** (`8168.96`) |
| **Option 2 (Different Buckets / Multiplicative)** | `[M1(+15%)] * [M2(+10%)]` | `1.26500` | **4,999** (`4999.33`) | **8,267** (`8266.98`) |

#### In-Game Observation & Result

* **Observed Non-Crit**: **`4,940`**

* **Observed Crit**: **`8,169`** (every crit tick)

* **Conclusion**: **Option 1 (`[M1 + M2]` Additive)** matches both non-crit and crit to the exact integer.

  * Establishes **`BUCKET_1`** containing `STAT_cbt_damage_done_modifier_percentage` (`79`). Both tag-scoped (`Force Dread`) and ability-scoped (`Fulguration`) instances of `STAT_cbt_damage_done_modifier_percentage` sum additively inside `BUCKET_1`.

---

### Test 2 — Target Vulnerabilities (Force Vulnerability + Internal Vulnerability) vs `BUCKET_1`

* **Ability**: `Creeping Terror` (`abl.sith_inquisitor.skill.madness.creeping_terror`)

* **Target State**: Operations Training Dummy with **all debuffs module active**

* **Damage Type / Channel**: Internal (`4`) / Force (`3`) — bypasses armor mitigation (`Armor DR = 0%`), zero damage variance (`shp_min = shp_max = 0.03465`, `coeff = 0.35`)

* **Unmodified Base Damage**: `3952.0410` (int `3952`)

* **Active Verified Modifiers (`BUCKET_1`)**:

  * `M1` — Force Dread: `+15%` (`STAT_cbt_damage_done_modifier_percentage`, `79`)

  * `M2` — Fulguration: `+10%` (`STAT_cbt_damage_done_modifier_percentage`, `79`)

  * Total `BUCKET_1` = `+25%` (`1.25x`)

* **Candidate Modifiers Under Test (from Target Debuff Module)**:

  * `M_vuln` — Vulnerable (Force): `+5%` (`stat_cbt_damage_taken_scale_channel_force_modifier_percentage`, GOM `386`)

  * `M_assail` — Assailable (Mental): `+7%` (`stat_cbt_damage_taken_scale_type_internal_modifier_percentage`, GOM `376`)

#### Options Tested

| Option | Hypothesis Description | Multiplier | Expected Non-Crit | Expected Crit (`1.653618x`) |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Option A (All Additive with `BUCKET_1`)** | `[B1(+25%) + Vuln(+5%) + Assail(+7%)]` | `1.37000` | **5,414** (`5414.30`) | **8,953** (`8953.18`) |
| **Option B (Assail in `B1`, Vuln Separate)** | `[B1(+25%) + Assail(+7%)] * [Vuln(+5%)]` | `1.38600` | **5,477 – 5,478** (`5477.53`) | **9,058** (`9057.74`) |
| **Option C (Vuln in `B1`, Assail Separate)** | `[B1(+25%) + Vuln(+5%)] * [Assail(+7%)]` | `1.39100` | **5,497** (`5497.29`) | **9,090** (`9090.42`) |
| **Option D (Debuffs together in `BUCKET_2`)** | `[B1(+25%)] * [Vuln(+5%) + Assail(+7%)]` | `1.40000` | **5,533** (`5532.86`) | **9,149** (`9149.23`) |
| **Option E (All 3 Separate Buckets)** | `[B1(+25%)] * [Vuln(+5%)] * [Assail(+7%)]` | `1.40438` | **5,550** (`5550.15`) | **9,178** (`9177.82`) |

#### In-Game Observation & Result

* **Observed Non-Crit**: **`5,414`**

* **Observed Crit**: **`8,953`**

* **Conclusion**: **Option A (All Additive in `BUCKET_1`)** matches both non-crit and crit to the exact integer.

  * Proves that target channel vulnerability (`Vulnerable (Force)` `+5%`, GOM `386`) and target damage-type vulnerability (`Assailable` `+7%`, GOM `376`) are **ADDITIVE** with caster damage done in **`BUCKET_1`**.

---

### Test 3 — Target AoE Vulnerability (*Overwhelmed*) vs `BUCKET_1`

* **Ability**: `Death Field` (`abl.sith_inquisitor.skill.madness.death_field`)

* **Target State**: Operations Training Dummy with **all debuffs module active**

* **Damage Type / Channel**: Internal (`4`) / Force (`3`) / AoE (`tag.abl.sith_inquisitor.aoe_ability`) — bypasses armor mitigation (`Armor DR = 0%`)

* **Base Damage Formula**: `coeff = 1.6900`, `shp_min = 0.1490`, `shp_max = 0.1890`

  * $\text{Base Min} = (1.6900 \times 9377.3808) + (0.1490 \times 19335) = \mathbf{18,728.69}$ (int `18,728`)

  * $\text{Base Max} = (1.6900 \times 9377.3808) + (0.1890 \times 19335) = \mathbf{19,502.09}$ (int `19,502`)

* **Active Verified Modifiers in `BUCKET_1`**:

  * Pervasive Death: `+15%` (`STAT_cbt_damage_done_modifier_percentage`, `79`, targets `death_field`)

  * Vulnerable (Force): `+5%` (proven in Test 2)

  * Assailable (Internal): `+7%` (proven in Test 2)

  * Total `BUCKET_1` = `+27%` (`1.27x`)

* **Candidate Modifier Under Test**:

  * `M_aoe` — Overwhelmed (Mental): `+10%` AoE damage taken (`STAT_cbt_damage_received_modifier_percentage`, GOM `46`, targets `is_aoe`)

#### Options Tested

| Option | Hypothesis Description | Multiplier | Expected Non-Crit Range | Expected Crit Range (`1.653618x`) |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Option A (Additive in `BUCKET_1`)** | `[B1(+27%) + Overwhelmed(+10%)]` | `1.37000` | **`25,657 – 26,717`** (`25658.3 – 26717.9`) | **`42,427 – 44,180`** |
| **Option B (New Multiplicative Bucket `BUCKET_2`)** | `[B1(+27%)] * [Overwhelmed(+10%)]` | `1.39700` | **`26,163 – 27,244`** (`26164.0 – 27244.4`) | **`43,263 – 45,051`** |

#### In-Game Observation & Result

* **Observed Non-Crit Hits**: **`26,928`**, **`27,016`**, **`27,008`**, **`26,776`**

* **Conclusion**: **Option B (New Multiplicative Bucket `BUCKET_2`)** is definitively proven.

  * Three of the observed hits (`26,928`, `27,016`, `27,008`) strictly exceed the maximum theoretical ceiling of Option A (`26,717.9`), falling squarely in Option B's range.

  * Establishes **`BUCKET_2`** containing target AoE damage vulnerability (`Overwhelmed`, `STAT_cbt_damage_received_modifier_percentage` / GOM `46` targeting AoE), which **multiplies** against `BUCKET_1`.

#### Appendix: Test 3 Verification (Clean Dummy with No Module Debuffs)

* **Setup**: Fresh operations dummy without the debuff module (0 initial debuffs).

* **Hit 1 (Fresh Dummy)**: No debuffs active. Only `BUCKET_1` (Pervasive Death `+15%`, `1.150x`) active $\to$ Expected Non-Crit: `21,537 – 22,427`. *Death Field applies Overwhelmed to target.*

* **Hit 2 (Subsequent Cast)**: Target now has `Overwhelmed` (`+10%` AoE) active with no other debuffs.

  * *Additive in `BUCKET_1` Hypothesis*: `[1.0 + 0.15 + 0.10] = 1.250x` $\to$ Non-Crit Range: `23,410 – 24,377` (Ceiling: `24,377.6`).

  * *Multiplicative in `BUCKET_2` Hypothesis*: `[1.15] * [1.10] = 1.265x` $\to$ Non-Crit Range: `23,690 – 24,670`.

* **Observed Non-Crit Hit**: **`24,618`**

* **Result**: `24,618` is strictly above the additive maximum (`24,377.6`) and near the top of the multiplicative range (`23,690 – 24,670`), providing 100% independent re-verification of **`BUCKET_2`**.

---

### Test 4 — Low-Health Execute (*Inevitable Demise*) vs `BUCKET_1`

* **Ability**: `Creeping Terror` periodic DoT tick (`abl.sith_inquisitor.skill.madness.creeping_terror`)

* **Target State**: Operations Training Dummy below 30% HP (sub-30% execute window active)

* **Damage Type / Channel**: Internal (`4`) / Force (`3`) — bypasses armor mitigation (`Armor DR = 0%`), zero damage variance (`shp_min = shp_max = 0.03465`, `coeff = 0.35`)

* **Unmodified Base Damage**: `3952.0410` (int `3952`)

* **Candidate Modifier Under Test**:

  * `M_exec` — Inevitable Demise: `+25%` (`STAT_cbt_damage_done_if_target_health_low_modifier_percentage`, GOM `220`, targets `periodic_damage`)

#### Options Tested

##### Scenario A: Dummy Debuff Module Active (`BUCKET_1` = `+37%`)

* Active in `BUCKET_1`: Force Dread (`+15%`) + Fulguration (`+10%`) + Force Vuln (`+5%`) + Internal Vuln (`+7%`) = `+37%` (`1.37x`).

| Option | Hypothesis Description | Multiplier | Expected Non-Crit | Expected Crit (`1.653618x`) |
| :--- | :--- | :--- | :--- | :--- |
| **Option A1 (Additive in `BUCKET_1`)** | `[B1(+37%) + Inevitable Demise(+25%)]` | `1.62000` | **`6,402`** (`6402.31`) | **`10,587`** (`10586.97`) |
| **Option A2 (Multiplicative / New Bucket)** | `[B1(+37%)] * [Inevitable Demise(+25%)]` | `1.71250` | **`6,768`** (`6767.87`) | **`11,191`** (`11191.47`) |

##### Scenario B: Dummy with No Module Debuffs (`BUCKET_1` = `+25%`)

* Active in `BUCKET_1`: Force Dread (`+15%`) + Fulguration (`+10%`) = `+25%` (`1.25x`).

| Option | Hypothesis Description | Multiplier | Expected Non-Crit | Expected Crit (`1.653618x`) |
| :--- | :--- | :--- | :--- | :--- |
| **Option B1 (Additive in `BUCKET_1`)** | `[B1(+25%) + Inevitable Demise(+25%)]` | `1.50000` | **`5,928`** (`5928.06`) | **`9,803`** (`9802.75`) |
| **Option B2 (Multiplicative / New Bucket)** | `[B1(+25%)] * [Inevitable Demise(+25%)]` | `1.56250` | **`6,175`** (`6175.06`) | **`10,211`** (`10211.20`) |

#### In-Game Observation & Result

* **Observed Scenario A**: **Option A2 confirmed** (`6,768` non-crit / `11,191` crit)

* **Observed Scenario B**: **Option B2 confirmed** (`6,175` non-crit / `10,211` crit)

* **Conclusion**: **Option A2 and Option B2 (New Multiplicative Bucket `BUCKET_3`)** are definitively proven.

  * In both scenarios, the execute modifier multiplies against `BUCKET_1` (`1.7125x` and `1.5625x`).

  * Establishes **`BUCKET_3`** containing low-health execute (`STAT_cbt_damage_done_if_target_health_low_modifier_percentage` / GOM `220`).

  * *Note on BUCKET_2 relationship*: Resolved in **Test 5** below (proven to be separate multiplicative buckets).

---

### Test 5 — Cross-Bucket Verification: `BUCKET_2` (AoE Vulnerability) vs `BUCKET_3` (Low-Health Execute)

* **Ability**: `Death Field` (`abl.sith_inquisitor.skill.madness.death_field`)

* **Target State**: Operations Training Dummy below 30% HP (execute active) with **all debuffs module active**

* **Damage Type / Channel**: Internal (`4`) / Force (`3`) / AoE (`tag.abl.sith_inquisitor.aoe_ability`) — bypasses armor mitigation (`Armor DR = 0%`)

* **Base Damage Formula**: `coeff = 1.6900`, `shp_min = 0.1490`, `shp_max = 0.1890`

  * $\text{Base Min} = (1.6900 \times 9377.3808) + (0.1490 \times 19335) = \mathbf{18,728.69}$ (int `18,728`)

  * $\text{Base Max} = (1.6900 \times 9377.3808) + (0.1890 \times 19335) = \mathbf{19,502.09}$ (int `19,502`)

* **Active Verified Modifiers**:

  * In `BUCKET_1`: Pervasive Death (`+15%`) + Force Vuln (`+5%`) + Internal Vuln (`+7%`) = `+27%` (`1.27x`)

  * In `BUCKET_2` Candidate: Overwhelmed (`+10%` AoE vuln)

  * In `BUCKET_3` Candidate: Inevitable Demise (`+25%` execute sub-30% HP)

#### Options Tested

| Option | Hypothesis Description | Multiplier | Expected Non-Crit Range | Expected Crit Range (`1.653618x`) |
| :--- | :--- | :--- | :--- | :--- |
| **Option A (`B2 + B3` Shared Bucket)** | `[B1(+27%)] * [Overwhelmed(+10%) + Inevitable Demise(+25%)]` = `1.27 * 1.35` | `1.71450` | **`32,109 – 33,436`** (`32109.3 – 33436.3`) | **`53,096 – 55,290`** (`53096.6 – 55290.8`) |
| **Option B (`B2` and `B3` Independent)** | `[B1(+27%)] * [Overwhelmed(+10%)] * [Inevitable Demise(+25%)]` = `1.27 * 1.10 * 1.25` | `1.74625` | **`32,703 – 34,055`** (`32704.0 – 34055.5`) | **`54,079 – 56,314`** (`54079.8 – 56314.9`) |

#### In-Game Observation & Result

* **Observed Crit Hits**: **`55,834`**, **`55,714`**

* **Conclusion**: **Option B (`BUCKET_2` and `BUCKET_3` are completely separate multiplicative layers)** is definitively proven.

  * The maximum theoretical crit ceiling for Option A (shared additive bucket) is strictly **`55,290`**.

  * Both observed hits (`55,834` and `55,714`) far exceed Option A's ceiling and sit right in the upper middle of Option B's expected crit band (`54,079 – 56,314`).

  * Establishes that **`BUCKET_2`** (AoE vulnerability) and **`BUCKET_3`** (Execute) multiply against each other as well as against `BUCKET_1`.

---

### Test 6 — Target Melee Vulnerability (*Beat Down* / `384`), Kinetic Armor DR, & Melee Surge (*Claws of Decay* / `117`)

* **Abilities**: `Thrash` (`abl.sith_inquisitor.thrash`) & `Leeching Strike` (`abl.sith_inquisitor.skill.hatred.leeching_strike`)

* **Target State**: Operations Training Dummy with **all debuffs module active** (*Sundered* $-20\%$ armor, *Beat Down* $+5\%$ melee vulnerability)

* **Damage Type / Channel**: Kinetic (`1`) / Melee (`1`) — mitigated by armor

* **Kinetic Armor DR Verification**:

  * Level 80 denominator constant: $389.98999 \times 80 + 800 = \mathbf{31,999.20}$

  * Target armor after *Sundered* ($-20\%$): $17,225 \times 0.8 = \mathbf{13,780}$

  * $\text{Armor DR} = \frac{13780}{13780 + 31999.20} = \mathbf{30.1010\%} \implies \text{Mitigation Factor} = \mathbf{0.698990}$

* **Base Damage Formula (Thrash per hit)**: `coeff = 0.72`, `amp = -0.52`, `shp = 0.072`

  * $\text{Base Min} = (0.48 \times 2513) + (0.72 \times 7059.3120) + (0.072 \times 19335) = 1206.24 + 5082.70 + 1392.12 = \mathbf{7,681.06}$

  * $\text{Base Max} = (0.48 \times 3769) + (0.72 \times 7059.3120) + (0.072 \times 19335) = 1809.12 + 5082.70 + 1392.12 = \mathbf{8,283.94}$

  * $\text{Post-Mitigation Min} = 7681.06 \times 0.698990 = \mathbf{5,368.99}$

  * $\text{Post-Mitigation Max} = 8283.94 \times 0.698990 = \mathbf{5,790.39}$

* **Melee Surge with Claws of Decay (`117`)**:

  $$\text{Crit Multiplier} = 1.0 + 0.653618_{\text{sheet}} + 0.12_{\text{Claws}} = \mathbf{1.773618\times}$$

* **Candidate Modifiers Under Test**:

  * *Thrashing Blades*: `+5%` (`STAT_cbt_damage_done_modifier_percentage` / `79`, proven in `BUCKET_1`)

  * *Beat Down*: `+5%` Melee vulnerability (`stat_cbt_damage_taken_scale_channel_melee_modifier_percentage` / `384`)

#### Options Tested

| Option | Hypothesis Description | Multiplier | Expected Non-Crit Range per Hit | Expected Crit Range per Hit (`1.773618x`) |
| :--- | :--- | :--- | :--- | :--- |
| **Option A (Additive in `BUCKET_1`)** | `1.0 + 0.05(Thrash) + 0.05(BeatDown)` | `1.10000` | **`5,906 – 6,369`** (`5905.89 – 6369.43`) | **`10,475 – 11,298`** (`10474.76 – 11296.95`) |
| **Option B (Separate Multiplicative Bucket)** | `[1.05(Thrash)] * [1.05(BeatDown)]` | `1.10250` | **`5,919 – 6,384`** (`5919.31 – 6383.91`) | **`10,498 – 11,322`** (`10498.58 – 11322.67`) |

#### In-Game Observation & Result

* **Observed Non-Crit Hits**: **`5,911`**, **`5,912`**, **`5,914`** (repeated multiple times; all top rolls strictly within additive boundary $\le 6,369$)

* **Observed Crit Hits**: **`10,478`**, **`10,481`** (repeated multiple times)

* **Conclusion**: **Option A (Additive in `BUCKET_1`)** is definitively proven.

  * The mathematical absolute minimum floor for Option B (separate multiplicative bucket) is strictly **`5,919.31`** ($\mathbf{5,919}$) for non-crits, and **`10,498.58`** ($\mathbf{10,498}$) for crits.

  * The observed hits `5,911`, `5,912`, `5,914` (non-crit) and `10,478`, `10,481` (crit) sit strictly **below the minimum possible floor of Option B**. Under Option B, hits that low are mathematically impossible.

  * Establishes that **Target Melee Channel Vulnerability (*Beat Down* / GOM `384`)** is **ADDITIVE in `BUCKET_1`** alongside Force Vulnerability (`386`), Internal Vulnerability (`376`), and Attacker Damage Done (`79`).

  * Also confirms target kinetic armor mitigation with *Sundered* ($-20\%$) and the Melee Critical Damage addition from *Claws of Decay* (`117`).

---

### Test 7 — Target-State Conditional: Accuracy Reduced (*Torment* / `389`) vs `BUCKET_1` & `BUCKET_2`

* **Ability**: `Lacerate` (`abl.sith_inquisitor.lacerate`)

* **Discipline**: Darkness Assassin (`sith_inquisitor.skill.darkness`)

* **Target State**: Operations Training Dummy with **all debuffs module active** (*Sundered* $-20\%$ armor, *Beat Down* $+5\%$ melee vulnerability, *Overwhelmed* $+10\%$ AoE vulnerability) and **Accuracy Reduced debuff applied** (via Darkness *Discharge* / *Severing Slash*)

* **Damage Type / Channel**: Kinetic (`1`) / Melee (`1`) / AoE (`tag.abl.utility.is_aoe`) — mitigated by armor

* **Base Damage Formula (Lacerate)**: `coeff = 0.72`, `amp = -0.52` ($0.48\times$ weapon), `shp = 0.072`

  * $\text{Base Min} = (0.48 \times 2513) + (0.72 \times 7059.3120) + (0.072 \times 19335) = 1206.24 + 5082.70 + 1392.12 = \mathbf{7,681.06}$

  * $\text{Base Max} = (0.48 \times 3769) + (0.72 \times 7059.3120) + (0.072 \times 19335) = 1809.12 + 5082.70 + 1392.12 = \mathbf{8,283.94}$

  * $\text{Post-Mitigation (Sundered 30.101% DR, factor 0.698990)}$: $\mathbf{5,368.99 – 5,790.39}$

* **Critical Surge (Darkness base sheet surge)**: $\mathbf{65.3618\%} \implies \mathbf{1.653618\times}$

* **Active Verified Modifiers**:

  * In `BUCKET_1`: Dark Charge ($-10\%$) + Thrashing Blades ($+5\%$) + Lambaste ($+25\%$) + Beat Down ($+5\%$) = $\mathbf{+25.0\%}\; (\mathbf{1.250\times})$

  * In `BUCKET_2`: Overwhelmed ($+10\%$ AoE vulnerability) = $\mathbf{1.100\times}$

* **Candidate Modifier Under Test**:

  * *Torment* (Discipline Passive): `+15%` damage to Lacerate when target has accuracy reduced (`STAT_cbt_damage_done_if_target_accuracy_reduced_modifier_percentage` / GOM `389`)

#### Options Tested

| Option | Hypothesis Description | Multiplier | Expected Non-Crit Range | Expected Crit Range (`1.653618x`) |
| :--- | :--- | :--- | :--- | :--- |
| **Option A (Additive in `BUCKET_1`)** | $[1.0 + 0.25_{\text{B1}} + 0.15_{\text{Torment}}] \times [1.10_{\text{Overwhelmed}}] = 1.400 \times 1.10$ | `1.54000` | **`8,268 – 8,917`** (`8268.24 – 8917.20`) | **`13,673 – 14,746`** (`13672.52 – 14745.62`) |
| **Option B (Additive in `BUCKET_2` with *Overwhelmed*)** | $[1.25_{\text{B1}}] \times [1.0 + 0.10_{\text{Overwhelmed}} + 0.15_{\text{Torment}}] = 1.25 \times 1.25$ | `1.56250` | **`8,389 – 9,047`** (`8389.05 – 9047.48`) | **`13,872 – 14,961`** (`13872.29 – 14961.07`) |
| **Option C (New Multiplicative Bucket `BUCKET_4`)** | $[1.25_{\text{B1}}] \times [1.10_{\text{Overwhelmed}}] \times [1.15_{\text{Torment}}]$ | `1.58125` | **`8,490 – 9,156`** (`8489.72 – 9156.05`) | **`14,039 – 15,140`** (`14038.75 – 15140.61`) |

#### In-Game Observation & Result

* **Observed Non-Crit Hits**: **`9,151`**, **`9,145`**, **`9,073`**, **`9,006`**, **`8,992`**, **`8,941`**

* **Observed Crit Hit**: **`14,834`**

* **Conclusion**: **Option C (New Multiplicative Bucket `BUCKET_4`)** is definitively proven.

  * **Rules Out `BUCKET_1` (Option A)**: The maximum theoretical ceiling for Option A is strictly **`8,917.20`** ($\mathbf{8,917}$) for non-crits and **`14,745.62`** ($\mathbf{14,746}$) for crits. All 6 recorded non-crit hits (`8,941` through `9,151`) and the recorded crit (`14,834`) strictly exceed Option A's mathematical ceiling (by up to $+234$ points).

  * **Rules Out `BUCKET_2` (Option B)**: If *Torment* pooled additively with *Overwhelmed* in `BUCKET_2` ($1.25 \times 1.25 = 1.5625\times$), the maximum theoretical ceiling for non-crits is strictly **`9,047.48`** ($\mathbf{9,047}$). Three recorded hits (**`9,073`**, **`9,145`**, and **`9,151`**) strictly breach this ceiling by up to $+104$ points, proving it cannot reside in `BUCKET_2`.

  * All recorded values sit squarely inside Option C's predicted exclusive window, with top rolls reaching within $5$ points of Option C's absolute theoretical ceiling (`9,156.05`).

  * Establishes **`BUCKET_4`** containing target-state accuracy reduced conditional damage (`STAT_cbt_damage_done_if_target_accuracy_reduced_modifier_percentage` / GOM `389` / *Torment*), proving that target-state conditional damage is an independent multiplicative layer from both `BUCKET_1` (Attacker Done + Channel/Type Vulns) and `BUCKET_2` (AoE Vuln).
---

### Test 8 — Target Elemental Vulnerability (*Assailable* / `370`) & Tech Vulnerability (*Susceptible* / `388`) vs `BUCKET_1`

* **Ability**: `Incendiary Missile` (`abl.bounty_hunter.skill.firebug.incendiary_missile`), specifically the periodic `Burning` DoT tick

* **Discipline**: Innovative Ordnance Mercenary (`bounty_hunter.skill.innovative_ordnance`)

* **Target State**: Operations Training Dummy with **all debuffs module active** (*Sundered* $-20\%$ armor, *Susceptible* $+5\%$ tech vulnerability, *Assailable* $+7\%$ elemental/internal vulnerability)

* **Damage Type / Channel**: Elemental (`3`) / Tech (`3`) — completely bypasses armor (`Armor DR = 0%`), zero weapon damage variance (`coeff = 0.31`, `amp = 0.0`, `shp_min = shp_max = 0.031`)

* **Unmodified Base Damage Formula**:

  $$\text{Base Tick} = (0.31 \times 9070.7715) + (0.031 \times 19335) = 2811.9392 + 599.3850 = \mathbf{3,411.3242}$$

* **Critical Surge (Mercenary base sheet surge)**: $\mathbf{64.9438\%} \implies \mathbf{1.649438\times}$

* **Candidate Modifiers Under Test**:

  * *Assailable (Elemental)*: `+7%` (`stat_cbt_damage_taken_scale_type_elemental_modifier_percentage` / GOM `370`)

  * *Susceptible (Tech)*: `+5%` (`stat_cbt_damage_taken_scale_channel_tech_modifier_percentage` / GOM `388`)

#### Options Tested

| Option | Hypothesis Description | Multiplier | Expected Non-Crit Tick | Expected Crit Tick (`1.649438x`) |
| :--- | :--- | :--- | :--- | :--- |
| **Option A (Both Additive in `BUCKET_1`)** | $[1.0 + 0.07_{\text{Assailable}} + 0.05_{\text{Susceptible}}]$ | `1.12000` | **`3,821`** (`3820.68`) | **`6,302`** (`6301.98`) |
| **Option B (Separate Multiplicative Buckets)** | $[1.07_{\text{Assailable}}] \times [1.05_{\text{Susceptible}}]$ | `1.12350` | **`3,833`** (`3832.62`) | **`6,322`** (`6321.67`) |

#### In-Game Observation & Result

* **Observed Non-Crit Tick**: **`3,821`**

* **Conclusion**: **Option A (Additive in `BUCKET_1`)** matches the in-game observation to the exact integer.

  * The mathematical prediction for Option A is strictly **`3,820.68`** (which rounds to **`3,821`**).

  * Option B produces **`3,832.62`** (which rounds to **`3,833`**), a 12-point deviation.

  * Establishes that **Target Elemental Type Vulnerability (*Assailable Elemental* / GOM `370`)** and **Target Tech Channel Vulnerability (*Susceptible* / GOM `388`)** are **ADDITIVE in `BUCKET_1`**, summing linearly alongside Attacker Damage Done (`79`), Force Vulnerability (`386`), Melee Vulnerability (`384`), and Internal Vulnerability (`376`).

---

### Test 9 — Target Ranged Channel Vulnerability (*Marked* / `382`) vs `BUCKET_1`

* **Ability**: `Priming Shot` (`abl.bounty_hunter.skill.arsenal.priming_shot`) — Mainhand Hit

* **Discipline**: Arsenal Mercenary (`bounty_hunter.skill.arsenal`)

* **Target State**: Operations Training Dummy with **all debuffs module active** (*Sundered* $-20\%$ armor, *Marked* $+5\%$ ranged vulnerability)

* **Damage Type / Channel**: Energy (`2`) / Ranged (`2`) — mitigated by armor

* **Energy Armor DR & Armor Penetration Verification**:

  * Level 80 denominator constant: $389.98999 	imes 80 + 800 = \mathbf{31,999.20}$

  * Target armor after *Sundered* ($-20\%$): $17,225 	imes 0.8 = \mathbf{13,780}$

  * *High Velocity Gas Cylinder* (`STAT_cbt_armor_penetration` / `166`): $\mathbf{35\%}$ armor penetration

  * Effective Armor: $13,780 	imes (1.0 - 0.35) = \mathbf{8,957.0}$

  * $	ext{Armor DR} =

rac{8957.0}{8957.0 + 31999.20} = \mathbf{21.8697\%} \implies 	ext{Mitigation Factor} = \mathbf{0.781303}$

* **Base Damage Formula (`Priming Shot` Mainhand)**: `coeff = 2.02`, `amp = 0.34` ($1.34	imes$ weapon), `shp = 0.202`

  * $	ext{Base Min} = (1.34 	imes 1832) + (2.02 	imes 6817.0935) + (0.202 	imes 19335) = 2454.88 + 13770.53 + 3905.67 = \mathbf{20,131.08}$

  * $	ext{Base Max} = (1.34 	imes 3403) + (2.02 	imes 6817.0935) + (0.202 	imes 19335) = 4560.02 + 13770.53 + 3905.67 = \mathbf{22,236.22}$

  * $	ext{Post-Mitigation Min} = 20131 	imes 0.781303 = \mathbf{15,728.42}$

  * $	ext{Post-Mitigation Max} = 22236 	imes 0.781303 = \mathbf{17,373.05}$

* **Ranged Critical Surge**:

  * With *Target Tracking* (`STAT_cbt_ranged_critical_damage` $+35\%$):

    $$	ext{Crit Multiplier (No Adv. Targeting)} = 1.0 + 0.649438_{	ext{sheet}} + 0.35_{	ext{Target Tracking}} = \mathbf{1.999438	imes}$$

  * With *Target Tracking* ($+35\%$) + *Advanced Targeting* proc ($+10\%$ for 6s after any crit):

    $$	ext{Crit Multiplier (With Adv. Targeting)} = 1.999438 + 0.10 = \mathbf{2.099438	imes}$$

* **Active Modifiers Under Test (with 10 stacks of *Supercharge*)**:

  * *Ironsights* (Discipline Passive): `+10%` (`STAT_cbt_damage_done_modifier_percentage` / `79`, proven in `BUCKET_1`)

  * *Supercharge* (10 stacks): `+1.0%` (`STAT_cbt_damage_done_modifier_percentage` / `79`, proven in `BUCKET_1`)

  * *Marked (Physical)*: `+5%` Ranged vulnerability (`stat_cbt_damage_taken_scale_channel_ranged_modifier_percentage` / GOM `382`)

#### Options Tested (at 10 `Supercharge` Stacks)

| Option | Hypothesis Description | Multiplier | Expected Non-Crit Range | Expected Crit Range (No `Adv. Targeting`, `1.999438x`) |
| :--- | :--- | :--- | :--- | :--- |
| **Option A (Additive in `BUCKET_1`)** | $1.0 + 0.10_{	ext{Ironsights}} + 0.01_{	ext{Supercharge}} + 0.05_{	ext{Marked}}$ | `1.16000` | **`18,245 – 20,153`** (`18244.96 – 20152.74`) | **`36,480 – 40,294`** (`36479.66 – 40294.16`) |
| **Option B (Separate Multiplicative Bucket)** | $[1.0 + 0.10_{	ext{Ironsights}} + 0.01_{	ext{Supercharge}}] 	imes [1.05_{	ext{Marked}}]$ | `1.16550` | **`18,331 – 20,248`** (`18331.46 – 20248.29`) | **`36,653 – 40,485`** (`36652.62 – 40485.21`) |

#### In-Game Observation & Result

* **Observed Non-Crit Hits**: **`18,261`** (at 10 `Supercharge` stacks); earlier casts during ramp: `19.01k`, `20,080`

* **Observed Crit Hits**: **`36,604`** (at 10 `Supercharge` stacks, no `Advanced Targeting`); earlier crit with `Advanced Targeting` (`+10%` surge proc active): **`41,281`** (within `38,304 – 42,309`)

* **Conclusion**: **Option A (Additive in `BUCKET_1`)** is definitively proven.

  * The mathematical absolute minimum floor for Option B (separate multiplicative bucket) at 10 `Supercharge` stacks is strictly **`18,331.46`** ($\mathbf{18,331}$) for non-crits, and **`36,652.62`** ($\mathbf{36,653}$) for crits.

  * Both observed hits — **`18,261`** (non-crit) and **`36,604`** (crit) — sit strictly **below the minimum possible mathematical floor of Option B** (`18,261 < 18,331` by 70 points; `36,604 < 36,653` by 49 points) and right near the bottom floor of Option A (`18,245` and `36,480`). Under Option B, hits that low are mathematically impossible.

  * Establishes that **Target Ranged Channel Vulnerability (*Marked* / GOM `382`)** is **ADDITIVE in `BUCKET_1`**, completing the empirical verification that **all 4 target channel vulnerabilities** — Force (`386`), Melee (`384`), Tech (`388`), and Ranged (`382`) — reside in `BUCKET_1`.

---

### Test 10 — Dual Wield Damage Done (`STAT_cbt_dual_wield_damage_done_modifier_percentage` / GOM `127`) vs Offhand Weapon Scalar

* **Ability**: `Assault` (`abl.flurry.sith_warrior.assault_optimize`)

* **Discipline**: Carnage Marauder (`sith_warrior.skill.carnage`) — Dual Wielding (Main Hand & Off Hand: `2,094 – 3,141`)

* **Target State**: Operations Training Dummy with **all debuffs module active** (*Sundered* $-20\%$ armor, *Beat Down* $+5\%$ melee vulnerability)

* **Damage Type / Channel**: Kinetic (`1`) / Melee (`1`) — mitigated by armor

* **Kinetic Armor DR & Beat Down Mitigation Factor**:

  * Target armor after *Sundered* ($-20\%$): $10,450 	imes 0.8 = \mathbf{8,360}$

  * Operations dummy mitigation factor with Beat Down ($+5\%$): $(1.0 -

rac{8360}{8360 + 19485}) 	imes 1.05 = \mathbf{0.734755}$

* **Character Stats**:

  * Mastery: `16,570` base $	o$ `17,398.50` (with $+5\%$ *Mark of Power*)

  * Power: `13,290.0`

  * Melee Bonus Damage: $(13290 	imes 0.23 + 17398.50 	imes 0.20) 	imes 1.05_{	ext{Unnatural Might}} = \mathbf{6,863.22}$

  * Critical Rating: `3,705` $\implies$ Surge Multiplier = $\mathbf{1.653618	imes}$

* **Ability Mechanics (4 Hits from 1 Cast)**:

  * Effect 2 (Dual Wield) executes:

    1. Strike 1 (MH): `coeff = 0.33`, `amp = -0.67`, `flurry = 1`

    2. Strike 2 (OH): `coeff = 0.0`, `amp = 0.0`, `flurry = 1`, `hand = off`

    3. Strike 3 (MH): `coeff = 0.67`, `amp = -0.33`, `flurry = 2` $\implies$ splits into **two flurry blows**, each with `coeff = 0.335`, `1 + amp = 0.335`

* **Active Modifier Under Test**:

  * *Dual Wield Mastery* (Passive Talent): `+25%` (`STAT_cbt_dual_wield_damage_done_modifier_percentage` / GOM `127`)

#### Options Tested for Offhand Strike

| Option | Hypothesis Description | Offhand Base Damage Range | Expected Post-Mitigation Non-Crit Range | Expected Crit Range (`1.653618x`) |
| :--- | :--- | :--- | :--- | :--- |
| **Option A (External Multiplier in `BUCKET_1` on 30% base)** | $	ext{Weapon} 	imes 0.30 	imes [1.0 + 0.05_{	ext{Beat Down}} + 0.25_{	ext{DW}}]$ | `[628.2 – 942.3]` | **`572 – 857`** (`571.6 – 857.4`) | **`945 – 1,418`** (`945.2 – 1417.8`) |
| **Option B (Separate Multiplicative Bucket on 30% base)** | $	ext{Weapon} 	imes (0.30 	imes 1.25) 	imes 1.05_{	ext{Beat Down}}$ | `[785.3 – 1177.9]` | **`577 – 865`** (`577.0 – 865.5`) | **`954 – 1,431`** (`954.1 – 1431.2`) |
| **Option C (Additive Weapon Scalar: `0.30 + 0.25 = 0.55`)** | $	ext{Weapon} 	imes (0.30 + 0.25) 	imes 1.05_{	ext{Beat Down}}$ | `[1151.7 – 1727.6]` | **`846 – 1,269`** (`846.2 – 1269.3`) | **`1,399 – 2,099`** (`1399.3 – 2099.0`) |

#### In-Game Observation & Result

* **Observed Hits (Single `Assault` Cast)**:

  * Hit 1 (MH Strike 1): **`2,208`** (Expected Non-Crit: `2,172 – 2,426` $\implies$ **Match**)

  * Hit 2 (OH Strike 2): **`965`**

  * Hit 3 (MH Flurry Blow 1): **`*4,033`** (Expected Crit: `3,646 – 4,072` $\implies$ **Match**)

  * Hit 4 (MH Flurry Blow 2): **`2,215`** (Expected Non-Crit: `2,205 – 2,463` $\implies$ **Match**)

* **Conclusion**: **Option C (Additive Weapon Scalar `0.30 + 0.25 = 0.55`)** is definitively proven.

  * Under Option A (additive in `BUCKET_1`) and Option B (multiplicative on base $0.30$), the absolute mathematical ceiling for an offhand non-crit hit is **`857`** and **`865`** respectively.

  * The observed in-game offhand hit of **`965`** sits substantially above both Option A and Option B ceilings (`965 > 865` by 100 points), making both Option A and Option B mathematically impossible.

  * Under Option C ($0.30_{	ext{base}} + 0.25_{	ext{Dual Wield Mastery}} = \mathbf{0.55}$ / 55% offhand weapon damage scalar), the expected range is **`846 – 1,269`**, perfectly containing the observed **`965`** at an ~28% weapon roll (matching the identical low rolls of Strike 1 and Strike 3).

  * Establishes that **`STAT_cbt_dual_wield_damage_done_modifier_percentage` (`127`)** is **an additive modifier to the base offhand weapon ratio** (`offhand_ratio = 0.30 + val`), which nearly doubles offhand weapon damage as stated in game tooltips.

  * **Update 2026-11-17:** the base off-hand ratio was later measured at `0.25`, not `0.30` (see `CHANGELOG.md`, "off-hand base ratio 0.30 -> 0.25"), and the formula is now `offhand_ratio = 0.25 + val`. The Test 10 numbers above were computed with `0.30` and are left as recorded. Scaled to a `0.25` base, the Option A and Option B ceilings become about `714` and `721`, and Option C (`0.25 + 0.25 = 0.50`) gives about `769 – 1,154`. The observed `965` is still above both ceilings and inside Option C, so the conclusion is unchanged: stat `127` is additive to the off-hand weapon scalar.

---

### Test 11 — Caster Channel Dealt Scale: Melee (`stat_cbt_damage_dealt_scale_channel_melee_modifier_percentage` / GOM `407`) vs `BUCKET_1`

* **Ability**: `Vicious Slash` (`abl.sith_warrior.vicious_slash`)
* **Discipline**: Vengeance Juggernaut (`sith_warrior.skill.vengeance`)
* **Target State**: Operations Training Dummy with **all debuffs module active** (*Sundered* $-20\%$ armor, *Beat Down* $+5\%$ melee channel vulnerability)
* **Damage Type / Channel**: Energy (`2`) / Direct Melee Attack — mitigated by kinetic/energy armor
* **Armor DR & Mitigation Factor**:
  * Base Armor: $17,225 \to 13,780$ after Sundered ($-20\%$)
  * Level 80 denominator constant: $K = 389.989990234375 \times 80 + 800.0 = \mathbf{31,999.20}$
  * $\text{Armor DR} = \frac{13,780}{13,780 + 31,999.20} = \mathbf{30.101004\%} \implies \text{Mitigation Factor} = \mathbf{0.698990}$
* **Character Stats**:
  * Base Mastery: `16,570.0` (buffed with 5% *Mark of Power* $\to \mathbf{17,398.50}$)
  * Power: `13,290.0`
  * Melee Bonus Damage: $(13,290 \times 0.23 + 17,398.50 \times 0.20) \times 1.05_{\text{Unnatural Might}} = \mathbf{6,863.22}$
  * Mainhand Weapon: Single Lightsaber $[2,094 \text{ -- } 3,141] \times 1.20_{\text{Single Saber Mastery}} = [2,512.80 \text{ -- } 3,769.20]$
  * Critical Rating: `3,705.0` $\implies$ Surge Multiplier = $\mathbf{1.653618\times}$ (Sheet Surge: `65.36%`)
  * Level 80 Standard Health: `19,335.0`
* **Raw Base Formula**:
  * Blueprint: $\text{coeff} = 1.66$, $\text{amp} = 0.08$, $\text{shp\_min} = \text{shp\_max} = 0.165668994$ (zero health variance)
  * Weapon Scaling: $(1.0 + \text{amp}) \times \text{Weapon} = 1.08 \times [2,512.80 \text{ -- } 3,769.20] = [2,713.824 \text{ -- } 4,070.736]$
  * Bonus & Health: $(1.66 \times 6,863.22) + (0.165668994 \times 19,335.0) = 11,392.945 + 3,203.208 = 14,596.153$
  * Raw Base Range: $[17,309.98 \text{ -- } 18,666.89]$
  * Post-Armor Mitigation Base ($0.698990$ factor): $[12,099.50 \text{ -- } 13,047.97]$
* **Active Baseline Modifiers**:
  * In `BUCKET_1`: Shien Form (`+6%` / `79`), Beat Down (`+5%` / `384`) = $+11\%$ (`1.110000x`)
* **Modifier Under Test**:
  * *Ravager* (Discipline Passive): `+5%` Melee damage dealt (`stat_cbt_damage_dealt_scale_channel_melee_modifier_percentage` / GOM `407`)

#### Options Tested

| Option | Hypothesis Description | Multiplier Formula | Expected Non-Crit Range | Expected Crit Range (`1.653618x`) |
| :--- | :--- | :--- | :--- | :--- |
| **Option A (Additive in `BUCKET_1`)** | $1.0 + 0.06_{\text{Shien}} + 0.05_{\text{BeatDown}} + 0.05_{\text{Ravager}}$ | **`1.160000x`** | **`14,035 – 15,135`** | **`23,209 – 25,028`** |
| **Option B (Separate Multiplicative Layer)** | $(1.0 + 0.06 + 0.05) \times 1.05_{\text{Ravager}}$ | **`1.165500x`** | **`14,102 – 15,207`** | **`23,319 – 25,147`** |

#### In-Game Observation & Result (Combat Log / StarParse)
* **Observed Non-Crit Hits**: **`14,041`**, **`14,091`**
* **Observed Crit Hits**: **`*23,249`**, **`*23,272`**, **`*23,294`**
* **Conclusion**: **Option A (Additive in `BUCKET_1`)** is definitively proven:
  * Under Option B, the absolute lowest possible non-crit roll produces a mathematical floor of **`14,102.0`**. Both observed non-crit hits — **`14,041`** and **`14,091`** — strictly breach Option B's minimum floor by up to **61 points**, making Option B mathematically impossible.
  * Under Option B, the absolute lowest possible critical hit produces a mathematical floor of **`23,319.3`**. All three observed crits — **`*23,249`**, **`*23,272`**, and **`*23,294`** — breach Option B's crit floor by up to **70 points**, while sitting perfectly within Option A's predicted band (**`23,209 – 25,028`**).
  * Establishes that **Caster Channel Dealt Scale: Melee (`stat_cbt_damage_dealt_scale_channel_melee_modifier_percentage` / GOM `407`)** pools **additively into `BUCKET_1`** alongside general damage done (`79`), vulnerabilities (`384`, `386`, etc.), and damage type scales (`395`, `397`).

---

### Test 12 — Target State: Bleeding (`STAT_cbt_damage_done_if_target_bleeding_modifier_percentage` / GOM `221`) vs `BUCKET_1` & `BUCKET_2`

* **Ability**: `Sweeping Slash` (`abl.sith_warrior.sweeping_slash`)

* **Discipline**: Vengeance Juggernaut (`sith_warrior.skill.vengeance`)

* **Target State**: Operations Training Dummy with **all debuffs module active** (*Sundered* $-20\%$ armor, *Beat Down* $+5\%$ melee channel vulnerability, *Overwhelmed* $+10\%$ AoE vulnerability)

* **Damage Type / Channel**: Kinetic (`1`) / Melee (`1`) / AoE (`tag.abl.utility.is_aoe`) — mitigated by armor

* **Kinetic Armor DR & Mitigation Factor**:

  * Base Armor: $17,225 	o 13,780$ after Sundered ($-20\%$)

  * Level 80 denominator constant: $K = 389.98999 	imes 80 + 800 = \mathbf{31,999.20}$

  * $	ext{Armor DR} =

rac{13,780}{13,780 + 31,999.20} = \mathbf{30.101004\%} \implies 	ext{Mitigation Factor} = \mathbf{0.698990}$

* **Character Stats**:

  * Mastery: `16,570` base $	o$ `17,398.50` (with $+5\%$ *Mark of Power*)

  * Power: `13,290.0`

  * Melee Bonus Damage: $(13,290 	imes 0.23 + 17,398.50 	imes 0.20) 	imes 1.05_{	ext{Unnatural Might}} = \mathbf{6,863.22}$

  * Single Saber Weapon Range: $[2,094 	ext{ -- } 3,141] 	imes 1.20_{	ext{Single Saber Mastery}} = [2,512.80 	ext{ -- } 3,769.20]$

  * Critical Rating: `3,705` $\implies$ Surge Multiplier = $\mathbf{1.653618	imes}$

  * Unbuffed Post-Mitigation Base: $[6,427.07 	ext{ -- } 6,901.30]$

* **Active Baseline Modifiers (No Bleed)**:

  * In `BUCKET_1`: Shien Form (`+6%`) + Ravager (`+5%`) + Beat Down (`+5%`) = $+16\%$ (`1.1600x`)

  * In `BUCKET_2`: Overwhelmed (`+10%` AoE vulnerability) = `1.1000x`

  * Total Baseline Multiplier: $1.16 	imes 1.10 = \mathbf{1.27600	imes}$

  * Baseline Expected Range: Non-Crit `8,201 – 8,806` (Observed in-game baseline: `8,205` $\implies$ exact match).

* **Active Modifier Under Test (While Bleeding)**:

  * *Bloodbath* (Discipline Passive): `+25%` to `Sweeping Slash` while target is bleeding (`STAT_cbt_damage_done_if_target_bleeding_modifier_percentage` / GOM `221`)

#### Options Tested (Target Bleeding Active via `Bleeding (Shatter)`)

| Option | Hypothesis Description | Multiplier Formula | Expected Non-Crit Range | Expected Crit Range (`1.653618x`) |
| :--- | :--- | :--- | :--- | :--- |
| **Option A (Additive in `BUCKET_1`)** | $[B_1(1.16) + 0.25_{\text{Bloodbath}}] \times B_2(1.10) = 1.41 \times 1.10$ | `1.55100` | **`9,968 – 10,704`** | **`16,484 – 17,700`** |
| **Option B (Additive in `BUCKET_2` with *Overwhelmed*)** | $[B_1(1.16)] \times [1.0 + 0.10_{\text{Overwhelmed}} + 0.25_{\text{Bloodbath}}] = 1.16 \times 1.35$ | `1.56600` | **`10,065 – 10,808`** | **`16,643 – 17,871`** |
| **Option C (Separate Multiplicative Bucket `BUCKET_5`)** | $[B_1(1.16) \times B_2(1.10)] \times \mathbf{1.25_{\text{Bloodbath}}}$ | `1.59500` | **`10,251 – 11,008`** | **`16,952 – 18,202`** |

#### In-Game Observation & Result

* **Observed Non-Crit Hits**: **`10,892`**

* **Observed Crit Hits**: **`17,757`**, **`18,102`**

* **Conclusion**: **Option C (Separate Multiplicative Layer `BUCKET_5`)** is definitively proven.

  * **Rules Out `BUCKET_1` (Option A)**: The maximum mathematical ceiling for Option A is strictly **`10,704`** non-crit and **`17,700`** crit. The observed non-crit hit of **`10,892`** breaches Option A's ceiling by **188 points**, and both observed crits breach it by up to **402 points**.

  * **Rules Out `BUCKET_2` (Option B)**: If *Bloodbath* pooled additively with *Overwhelmed* in `BUCKET_2` ($1.16 \times 1.35 = 1.5660\times$), the maximum theoretical ceiling is strictly **`10,808`** for non-crits and **`17,871`** for crits. The observed non-crit hit of **`10,892`** breaches Option B's ceiling by **84 points**, and the observed crit hit of **`18,102`** breaches it by **231 points**, mathematically ruling out `BUCKET_2`.

  * All observed hits sit comfortably within Option C's predicted range (`10,251 – 11,008` non-crit, `16,952 – 18,202` crit).

  * Establishes that **Target State: Bleeding (`STAT_cbt_damage_done_if_target_bleeding_modifier_percentage` / GOM `221`)** does NOT pool additively into either `BUCKET_1` or `BUCKET_2`. It operates as an independent multiplicative layer, designated **`BUCKET_5`**, which multiplies against `BUCKET_1` (Damage Done/Vulnerabilities) and `BUCKET_2` (AoE Vulnerability).
---

### Test 13 — Caster Type Dealt Scale: Energy / Kinetic (`stat_cbt_damage_dealt_scale_type_energy_modifier_percentage` / GOM `395` and `kinetic` / GOM `397`) vs `BUCKET_1`

* **Ability**: `Magnetic Blast` (`abl.bounty_hunter.skill.advanced_prototype.magnetic_blast`)

* **Discipline**: Advanced Prototype Powertech (`powertech.skill.advanced_prototype`)

* **Target State**: Operations Training Dummy with **all debuffs module active** (*Sundered* $-20\%$ armor, *Susceptible* $+5\%$ Tech channel vulnerability)

* **Damage Type / Channel**: Energy (`2`) / Direct Tech Attack — mitigated by kinetic/energy armor

* **Armor DR & Mitigation Factor**:

  * Base Armor: $17,225 \to 13,780$ after Sundered ($-20\%$)

  * Level 80 denominator constant: $K = 389.989990234375 \times 80 + 800.0 = \mathbf{31,999.20}$

  * $\text{Armor DR} = \frac{13,780}{13,780 + 31,999.20} = \mathbf{30.101004\%} \implies \text{Mitigation Factor} = \mathbf{0.698990}$

* **Character Stats**:

  * Base Mastery: `16,570.0` (before 5% *Mark of Power* buff; buffed total = $16,570 \times 1.05 = \mathbf{17,398.50}$)

  * Power: `13,126.0`

  * Tech Power: `9,332.0`

  * Critical Rating: `3,577.0` $\implies$ Base Surge $65.0058\%$

  * In-Game Sheet Tech Bonus Damage: $(17,398.50 \times 0.20 + 13,126 \times 0.23 + 9,332 \times 0.23) \times 1.05_{\text{Force Might}} = \mathbf{9,077.292}$

  * Prototype Weapon Systems (+15% Tech Surge): Surge Multiplier = $1.0 + 0.650058 + 0.15 = \mathbf{1.800058\times}$

  * Raw Base Range: $1.50 \times 9,077.292 + (0.130 \text{ -- } 0.170) \times 19,335.0 = [16,129.49 \text{ -- } 16,902.89]$

  * Post-Armor Mitigation Base ($0.698990$ factor): $[11,274.01 \text{ -- } 11,814.33]$

* **Active Baseline Modifiers**:

  * In `BUCKET_1`: Power Bracer (`+10%`), Susceptible (`+5%`), Shock Trooper / Combat Tech's Damage Bonus (`+10%`) = $+25\%$ (`1.2500x`)

* **Modifier Under Test**:

  * *High Energy Gas Cylinder* (Discipline Passive): `+7%` to Energy and Kinetic damage dealt (`stat_cbt_damage_dealt_scale_type_energy_modifier_percentage` / GOM `395` and `kinetic` / GOM `397`)

#### Options Tested (All Module Debuffs + Shock Trooper Active)

| Option | Hypothesis Description | Multiplier Formula | Expected Non-Crit Range | Expected Crit Range (`1.800058x`) |
| :--- | :--- | :--- | :--- | :--- |
| **Option A (Additive in `BUCKET_1`)** | $1.0 + 0.10_{\text{Bracer}} + 0.10_{\text{ShockTrooper}} + 0.05_{\text{Susc}} + 0.07_{\text{Cylinder}}$ | **`1.320000x`** | **`14,882 – 15,595`** | **`26,788 – 28,072`** |
| **Option B (Separate Multiplicative Bucket)** | $(1.0 + 0.10 + 0.10 + 0.05) \times 1.07_{\text{Cylinder}}$ | **`1.337500x`** | **`15,079 – 15,802`** | **`27,143 – 28,444`** |

#### In-Game Observation & Result (Combat Log / StarParse)
* **Initial Run (Live Spec-Swap Anomaly)**:
  * *Observed Non-Crits*: `14,783`, `14,921`, `15,014`, `15,107`, `15,118`, `15,217`, `15,271`
  * *Observed Crits*: `*26,895`, `*27,096`, `*27,423`, `*27,538`
  * *Root Cause Analysis*: Swapping disciplines in-instance caused the live game engine to evaluate *High Energy Gas Cylinder* (Level 15 passive) before *Blood Tracker* (Level 23 talent) was registered in memory, defaulting the cylinder bonus to **+5%** instead of **+7%** (giving total $+30\%$ instead of $+32\%$).
* **Clean Verification Run (7% High Energy Gas Cylinder Fully Active)**:
  * *Observed Non-Crit Hits*: **`14,997`**, **`15,008`**, **`15,131`**, **`15,194`**, **`15,327`**, **`15,490`**
  * *Observed Crit Hits*: **`*27,330`**, **`*27,458`**, **`*27,757`**, **`*27,989`**
* **Conclusion**: **Option A (Additive in `BUCKET_1`)** is definitively proven:
  * Under Option B (multiplicative $1.25 \times 1.07 = 1.3375\times$), the absolute lowest possible non-crit roll produces a mathematical floor of **`15,079.0`**.
  * The observed clean non-crit hits of **`14,997`** and **`15,008`** strictly breach Option B's minimum floor by up to **82 points**, making Option B mathematically impossible.
  * All observed non-crits (`14,997 – 15,490`) sit squarely within Option A's predicted band (**`14,882 – 15,595`**), and all observed crits (`*27,330 – *27,989`) sit cleanly within Option A's predicted crit range (**`26,788 – 28,072`**).
  * Establishes that **Caster Type Dealt Scale: Energy (`395`) and Kinetic (`397`)** pool **additively into `BUCKET_1`** alongside general damage done (`79`) and vulnerabilities (`386`, `388`, etc.).
---

### Test 14 — Target State: Bleeding Re-Verification on Advanced Prototype (`STAT_cbt_damage_done_if_target_bleeding_modifier_percentage` / GOM `221`) via Internal Bleed DoT (`Retractable Blade`)

* **Ability**: `Bleeding (Retractable Blade)` (`abl.bounty_hunter.skill.advanced_prototype.retractable_blade`, Effect 2)

* **Discipline**: Advanced Prototype Powertech (`powertech.skill.advanced_prototype`)

* **Target State**: Operations Training Dummy with all debuffs module active (*Sundered* $-20\%$ armor, *Susceptible* $+5\%$ Tech channel vulnerability, *Assailable* $+7\%$ Internal/Elemental vulnerability)

* **Damage Type / Channel**: Internal (`4`) / Periodic Tech Attack — **0% Armor DR** (bypasses armor completely)

* **Character Stats**:

  * Base Mastery: `16,570.0` (buffed = `17,398.50`)

  * Power: `13,126.0`

  * Tech Power: `9,332.0`

  * In-Game Sheet Tech Bonus Damage: `9,077.292`

  * Critical Multiplier: $1.0 + 0.650058 + 0.15 = \mathbf{1.800058\times}$

  * Level 80 Standard Health: `19,335.0`

* **Raw Base Formula (Zero Variance)**:

  * Blueprint values: $\text{coeff} = 0.25$, $\text{shp\_min} = \text{shp\_max} = 0.025$

  * $\text{Base Tick} = (0.25 \times 9,077.292) + (0.025 \times 19,335.0) = 2,269.323 + 483.375 = \mathbf{2,752.698}$

  * Zero variance and zero armor mitigation $\implies$ Post-mitigation base = $\mathbf{2,752.70}$

* **Active Baseline Modifiers in `BUCKET_1` (No Shock Trooper)**:

  * Power Bracer (`+10%`), Serrated Blades (`+5%`), Assailable Internal (`+7%`), Susceptible Tech (`+5%`)

  * $\text{Sum in BUCKET\_1} = 1.0 + 0.10 + 0.05 + 0.07 + 0.05 = \mathbf{1.2700\times}$

* **Modifier Under Test**:

  * *Blood Tracker* (Discipline Passive): `+3%` damage dealt to bleeding targets (`STAT_cbt_damage_done_if_target_bleeding_modifier_percentage` / GOM `221`)

#### Options Tested

| Option | Hypothesis Description | Multiplier Formula | Expected Non-Crit Tick | Expected Crit Tick (`1.800058x`) |
| :--- | :--- | :--- | :--- | :--- |
| **Option A (Additive in `BUCKET_1`)** | $1.0 + 0.10 + 0.05 + 0.07 + 0.05 + 0.03$ | **`1.300000x`** | **`3,578`** (`3,578.5`) | **`6,441`** (`6,441.5`) |
| **Option B (Separate Multiplicative Layer `BUCKET_5`)** | $(1.0 + 0.10 + 0.05 + 0.07 + 0.05) \times 1.03$ | **`1.308100x`** | **`3,601`** (`3,600.8`) | **`6,482`** (`6,481.7`) |

#### In-Game Observation & Result (Combat Log / StarParse)

* **Observed Non-Crit Tick**: **`3,601`**

* **Observed Crit Tick**: **`6,482`**

* **Conclusion**: **Option B (Separate Multiplicative Layer `BUCKET_5`)** is definitively confirmed with 100.00% exact integer precision:

  * Option A predicted `3,578` non-crit and `6,441` crit. Both observed values strictly exceed Option A.

  * Option B predicted `3,600.8` ($\to \mathbf{3,601}$) and `6,481.7` ($\to \mathbf{6,482}$), matching the live game down to the exact single integer point.

  * Re-verifies that **Target State: Bleeding (`221`)** forms an independent multiplicative layer (**`BUCKET_5`**).


---

### Test 15 — Caster Channel Dealt Scale: Force (`stat_cbt_damage_dealt_scale_channel_force_modifier_percentage` / GOM `409`) vs `BUCKET_1`

* **Ability**: `Force Choke` (`abl.sith_warrior.force_choke`), tick 1
* **Discipline & Class**: Sith Warrior / Juggernaut / Rage (Level 80)
* **Target State**: Operations Training Dummy with standard debuffs active (*Sundered* -20% armor, *Vulnerable* +5% Force damage)
* **Damage Type / Channel**: Kinetic (`1`) / Force (`3`)
* **Character Stats**:
  * Base Mastery: `16,570.5` $\to$ Effective Mastery: `17,399.0` (with *Mark of Power* `+5%`)
  * Power: `13,290.0`
  * Force Power: `9,332.0` (from item rating 344 lightsaber hilt)
  * Force Bonus Damage: `9,117.003` (character sheet: `9,117`)
  * Standard Health: `19,335.0`
  * Armor Penetration: Base `15.0%` (*Shii-Cho Mastery*)
* **Raw Base Formula (Zero Variance)**:
  * Blueprint values: $\text{coeff} = 0.32$, $\text{shp} = 0.032$
  * $\text{Raw Base} = (0.32 \times 9,117.003) + (0.032 \times 19,335) = 2,917.441 + 618.720 = \mathbf{3,536.1610}$
* **Armor Mitigation**:
  * Target dummy standard base armor = $14,641.25$
  * After *Sundered* ($-20\%$): $11,713.0$
  * With *Shii-Cho Mastery* ($15\%$ armor pen) and $K = 31,999.20$: Effective DR = $26.7957\% \implies$ Mitigation Factor = $\mathbf{0.732043}$
  * Post-Mitigation Base = $3,536.1610 \times 0.732043 = \mathbf{2,588.622}$
* **Active Baseline Modifiers in `BUCKET_1`**:
  * Shii-Cho Form (`+3%` Damage Done, `STAT_cbt_damage_done_modifier_percentage` / `79`)
  * Target Vulnerable (`+5%` Force Vulnerability, `stat_cbt_damage_taken_scale_channel_force_modifier_percentage` / `386`)
  * Baseline Multiplier = $1.0 + 0.03 + 0.05 = \mathbf{1.0800x}$
* **Modifier Under Test**:
  * *Shii-Cho Mastery* (Discipline Passive): `+3.0%` Force damage dealt (`stat_cbt_damage_dealt_scale_channel_force_modifier_percentage` / GOM `409`)

#### Options Tested

| Option | Hypothesis Description | Multiplier Formula | Expected Non-Crit | Expected Crit (`1.803618x`) |
| :--- | :--- | :--- | :--- | :--- |
| **Option A (Additive into `BUCKET_1`)** | $1.0 + 0.03_{\text{Form}} + 0.05_{\text{Vuln}} + 0.03_{\text{Mastery}}$ | **`1.110000x`** | **`2,873`** (`2,873.37`) | **`5,182`** (`5,182.46`) |
| **Option B (Independent Multiplicative Layer)** | $(1.0 + 0.03 + 0.05) \times (1.0 + 0.03)$ | **`1.112400x`** | **`2,880`** (`2,879.58`) | **`5,194`** (`5,193.67`) |

#### In-Game Observation & Result (Combat Log / StarParse)

* **Observed Non-Crit Hit**: **`2,873`**
* **Observed Crit Hit**: **`5,182`**
* **Conclusion**: **Option A (Additive into `BUCKET_1`)** matches both non-crit and crit down to the exact single integer point.
  * Option A predicted `2,873` non-crit and `5,182` crit — matching the live game with 100.00% exact integer precision.
  * Option B predicted `2,880` non-crit and `5,194` crit, which is definitively refuted by live data.
  * Confirms that **Caster Channel Dealt Scale: Force (`409`)** pools additively into **`BUCKET_1`** alongside general damage done (`79`), vulnerabilities (`386`, `384`, etc.), and damage-type dealt scales (`395`, `397`, `407`).

---

### Test 16 — Target State: On Fire / Burning (`STAT_cbt_damage_done_if_target_on_fire_modifier_percentage` / GOM `250`) vs `BUCKET_1` & `BUCKET_2`

* **Ability**: `Cyclone Slash` (`abl.jedi_knight.cyclone_slash`)
* **Discipline & Class**: Jedi Knight / Guardian / Vigilance (Level 80)
* **Target State**: Operations Training Dummy with standard debuffs active (*Sundered* -20% armor, *Beat Down* +5% Melee, *Overwhelmed* +10% AoE) and **Burning debuff active** (applied by `Plasma Brand` / `Burning Blade`)
* **Damage Type / Channel**: Energy (`2`) / Melee (`1`)
* **Character Stats**:
  * Base Mastery: `16,570.5` $\to$ Effective Mastery: `17,399.0`
  * Power: `13,290.0`
  * Melee Bonus Damage: `6,863.325`
  * Mainhand Weapon Damage: $[2,094.0 \dots 3,141.0]$ (Item Rating 344 single lightsaber)
  * Standard Health: `19,335.0`
* **Raw Base & Post-Mitigation Formula**:
  * Weapon component scaled by *Single Saber Mastery* ($1.20\times$): $[2,512.80 \dots 3,769.20]$
  * Energy/Kinetic Armor Mitigation against dummy with *Sundered* ($-20\%$): factor $= \mathbf{0.698990}$
  * Post-Mitigation Base Range: $[\mathbf{6,427.13} \dots \mathbf{6,901.36}]$
* **Active Baseline Modifiers**:
  * `Master Focus`: `+5.0%` Melee channel dealt scale (`stat_cbt_damage_dealt_scale_channel_melee_modifier_percentage` / `407`, `BUCKET_1`)
  * `Shien Form`: `+6.0%` General damage done (`STAT_cbt_damage_done_modifier_percentage` / `79`, `BUCKET_1`)
  * `Beat Down`: `+5.0%` Melee vulnerability (`stat_cbt_damage_taken_scale_channel_melee_modifier_percentage` / `384`, `BUCKET_1`)
  * `Overwhelmed`: `+10.0%` AoE damage taken (`STAT_cbt_damage_received_modifier_percentage` / `46`, `BUCKET_2`)
* **Modifier Under Test**:
  * *Burning Storm* (Discipline Passive): `+25.0%` damage to targets on fire (`STAT_cbt_damage_done_if_target_on_fire_modifier_percentage` / GOM `250`)

#### Options Tested

| Option | Hypothesis Description | Multiplier Formula | Expected Non-Crit Range | Expected Crit Range (`~65.36%` surge) |
| :--- | :--- | :---: | :---: | :---: |
| **Option A (Additive in `BUCKET_1`)** | $[1.0 + 0.05 + 0.06 + 0.05 + 0.25] \times 1.10_{\text{AoE}}$ | **`1.551000x`** | **`9,968` — `10,704`** | **`16,484` — `17,700`** |
| **Option B (Additive in `BUCKET_2` with *Overwhelmed*)** | $[1.0 + 0.05 + 0.06 + 0.05] \times [1.0 + 0.10_{\text{AoE}} + 0.25_{\text{On Fire}}]$ | **`1.566000x`** | **`10,065` — `10,808`** | **`16,643` — `17,871`** |
| **Option C (Independent Multiplicative Layer `BUCKET_6`)** | $[1.0 + 0.05 + 0.06 + 0.05] \times 1.10_{\text{AoE}} \times 1.25_{\text{On Fire}}$ | **`1.595000x`** | **`10,251` — `11,008`** | **`16,952` — `18,202`** |

#### In-Game Observation & Result (Combat Log / StarParse)

* **Observed Non-Crit Hits**:
  * Minimum observed: **`10,262`** (strictly aligns with Option C minimum `10,251`; under Option A hits would drop to `9,968`, and under Option B to `10,065`)
  * Mid-to-high hits: **`10,784`**, **`10,908`**
* **Conclusion**: **Option C (Independent Multiplicative Layer `BUCKET_6`)** is definitively confirmed!
  * **Rules Out `BUCKET_1` (Option A)**: Option A established an absolute mathematical ceiling of **`10,704`**. The observed hits of `10,784` and `10,908` exceed the Option A maximum by up to $+204$ damage, which is mathematically impossible under Option A.
  * **Rules Out `BUCKET_2` (Option B)**: If *Burning Storm* pooled additively with *Overwhelmed* in `BUCKET_2` ($1.16 \times 1.35 = 1.5660\times$), the absolute maximum mathematical ceiling is strictly **`10,808`** ($6,901.36 \times 1.566 = 10,807.53$). The observed hit of **`10,908`** exceeds this ceiling by **100 points**, proving it cannot reside in `BUCKET_2`.
  * All observed values fall strictly inside Option C's predicted $[10,251 \dots 11,008]$ window.
  * Definitively proves that **Target State: On Fire / Burning (`250`)** forms an independent multiplicative layer (**`BUCKET_6`**), precisely mirroring the behavior of Target State: Bleeding (`221` / `BUCKET_5`) and Accuracy Reduced (`389` / `BUCKET_4`).
---

### Test 17 — Caster Flat Damage Done (`STAT_cbt_damage_done_modifier_fixed` / GOM `78`) via *Pull and Pummel* (`abl.trooper.harpoon`)

* **Ability**: `Stockstrike` (`abl.trooper.stockstrike`)
* **Discipline & Class**: Trooper / Vanguard / Tactics (Level 80, swapped in-instance from Plasmatech)
* **Target State**: Tested both on a Clean Operations Training Dummy (no debuff module) and a Debuffed Operations Training Dummy (*Sundered* $-20\%$ armor, *Susceptible* $+5\%$ Tech vulnerability)
* **Damage Type / Channel**: Kinetic (`1`) / Tech (`4`)
* **Character Stats**:
  * Base Mastery: `15,554.3` $\to$ Effective Mastery: `16,332.0` (with *Mark of Power* `+5%`)
  * Power: `12,658.0`
  * Tech Power: `8,691.0` (Item Rating 340 Blaster Rifle, $[1,794.0 \dots 2,691.0]$ weapon damage)
  * Tech Bonus Damage: `8,750.00` (character sheet: `8,750`)
  * Critical Rating: `3,901.0` (Critical Multiplier with Tactics `+5%` Surge = `1.808916x`)
  * Standard Health: `19,350.0`
  * Armor Penetration: Base `15.0%` (*Focused Impact*)
* **Raw Base & Post-Mitigation Formula**:
  * Blueprint values (`abl.trooper.stockstrike`): $\text{coeff} = 1.77$, $\text{shp} = [0.158, 0.198]$
  * $\text{Raw Base Range} = 1.77 \times 8,750.00 + [0.158, 0.198] \times 19,350.0 = [\mathbf{18,542.43} \dots \mathbf{19,315.83}]$
  * **Clean Dummy Mitigation** ($9,565 \times 0.85 = 8,130.25$ eff. armor $\implies 34.993\%$ DR, factor $= \mathbf{0.6500705}$):
    * Post-Mitigation Base: $[\mathbf{12,053.89} \dots \mathbf{12,556.65}]$
  * **Debuffed Dummy Mitigation** ($9,565 \times 0.80 \times 0.85 = 6,504.20$ eff. armor $\implies 30.101\%$ DR, factor $= \mathbf{0.6989900}$):
    * Post-Mitigation Base: $[\mathbf{12,960.97} \dots \mathbf{13,501.57}]$
* **Active Baseline Modifiers in `BUCKET_1` (In-Instance Spec Swap State)**:
  * `Focused Impact`: `+10.0%` Stockstrike damage (`STAT_cbt_damage_done_modifier_percentage` / `79`, `BUCKET_1`)
  * `Riot Augs`: `+10.0%` Stockstrike damage (`STAT_cbt_damage_done_modifier_percentage` / `79`, `BUCKET_1`)
  * `High Energy Cell`: `+5.0%` Kinetic damage dealt (`stat_cbt_damage_dealt_scale_type_kinetic_modifier_percentage` / `397`, `BUCKET_1` — evaluates to `+5.0%` instead of `+7.0%` upon in-instance discipline swap prior to `Triumph` loading, identical to Test 13)
  * `Susceptible (Tech)` (Debuffed Dummy only): `+5.0%` Tech vulnerability (`stat_cbt_damage_taken_scale_channel_tech_modifier_percentage` / `388`, `BUCKET_1`)
  * **Clean Dummy Baseline Multiplier**: $1.0 + 0.10 + 0.10 + 0.05 = \mathbf{1.2500x}$
  * **Debuffed Dummy Baseline Multiplier**: $1.0 + 0.10 + 0.10 + 0.05 + 0.05 = \mathbf{1.3000x}$
* **Modifier Under Test**:
  * *Pull and Pummel* (`abl.trooper.skill.utility.pull_and_pummel` via `abl.trooper.harpoon` Effect 6): `stat: 78` (`STAT_cbt_damage_done_modifier_fixed`), `amount: 0.20`, `is_percent: false`, targeting `tag.abl.trooper.stockstrike`.
  * *(Note: Powertech mirror `Reel and Rattle` in `abl.bounty_hunter.grapple` Effect 6 uses `stat: 79` `STAT_cbt_damage_done_modifier_percentage` with `amount: 0.20`, whereas Vanguard's `harpoon.json` uses `stat: 78` `STAT_cbt_damage_done_modifier_fixed` with `amount: 0.20`.)*

#### Options Tested

| Condition & Hypothesis | Multiplier Formula | Expected Non-Crit Range | Expected Crit Range (`1.808916x`) | Observed In-Game Hits |
| :--- | :---: | :---: | :---: | :---: |
| **Clean Dummy — Unbuffed / No-Op (`+0%`)** | **`1.2500x`** | **`15,067` — `15,696`** | **`27,256` — `28,392`** | **`15,232` (Non-Crit)**, **`27,641` (Crit)** |
| **Clean Dummy — Option A (Additive `BUCKET_1` `+20%`)** | **`1.4500x`** | `17,478` — `18,207` | `31,616` — `32,935` | — |
| **Clean Dummy — Option B (Multiplicative `1.20x`)** | **`1.5000x`** | `18,081` — `18,835` | `32,707` — `34,071` | — |
| **Debuffed Dummy — Unbuffed / No-Op (`+0%`)** | **`1.3000x`** | **`16,849` — `17,552`** | **`30,479` — `31,750`** | **`31,162` (Crit)** |
| **Debuffed Dummy — Option A (Additive `BUCKET_1` `+20%`)** | **`1.5000x`** | `19,441` — `20,252` | `35,168` — `36,635` | — |
| **Debuffed Dummy — Option B (Multiplicative `1.20x`)** | **`1.5600x`** | `20,219` — `21,062` | `36,575` — `38,100` | — |

#### In-Game Observation & Result (Combat Log / StarParse)

* **Observed Clean Dummy Hits**: **`15,232` (Non-Crit)** and **`27,641` (Crit)** (sitting at `26.2%` and `33.9%` weapon roll percentiles inside `[15,067 – 15,696]` and `[27,256 – 28,392]`).
* **Observed Debuffed Dummy Hit**: **`31,162` (Crit)** (sitting dead center at `53.7%` weapon roll percentile inside `[30,479 – 31,750]`).
* **Observed Hits With *Pull and Pummel* Buff Active (After Casting `Harpoon`)**:
  * Every single `Stockstrike` hit with the *Pull and Pummel* buff active on the buff bar landed strictly inside the unbuffed baseline range (`[15,067 – 15,696]` Non-Crit / `[27,256 – 28,392]` Crit on clean dummy, and `[30,479 – 31,750]` Crit on debuffed dummy), dealing `+0` bonus damage.
* **Conclusion**: **Verified No-Op (`+0` percentage multiplier) for `STAT_cbt_damage_done_modifier_fixed` (`78`)**:
  * Because `harpoon.json` Effect 6 assigns `0.20` to `STAT_cbt_damage_done_modifier_fixed` (`78`, flat damage) instead of `STAT_cbt_damage_done_modifier_percentage` (`79`, percentage damage used by Powertech's *Reel and Rattle*), the live SWTOR combat engine does not treat Stat `78` as a percentage multiplier, and a fractional `0.20` flat modifier yields `+0` integer damage in live combat.
  * Locked Stat `78` (`STAT_cbt_damage_done_modifier_fixed`) as a verified no-op in percentage multiplier bucketing in `src/swtorsim/combat_math_unbucketed.py` and `src/swtorsim/combat_math.py`.


---

## 4. Cross-Bucket Coexistence & Mutual Exclusivity Audit (Buckets 3 to 6)

### Objective
Audit all live extracted ability and talent blueprints across all SWTOR combat disciplines to determine whether member stat IDs from independent conditional layers (**`BUCKET_3`**, **`BUCKET_4`**, **`BUCKET_5`**, and **`BUCKET_6`**) ever coexist within a single specialization or can affect the same damage event, and assess whether their mutual multiplicativity with each other is empirically testable on live servers.

### Audited Member Stat IDs
* **`BUCKET_3`** (Execute < 30% HP): `220` (`STAT_cbt_damage_done_if_target_health_low_modifier_percentage`)
* **`BUCKET_4`** (Target Accuracy Reduced): `389` (`STAT_cbt_damage_done_if_target_accuracy_reduced_modifier_percentage`)
* **`BUCKET_5`** (Target State: Bleeding): `221` (`STAT_cbt_damage_done_if_target_bleeding_modifier_percentage`)
* **`BUCKET_6`** (Target State: Burning): `250` (`STAT_cbt_damage_done_if_target_on_fire_modifier_percentage`)

### Blueprint Discipline Distribution
1. **Stat `389` (Bucket 4)** is exclusive to Tank disciplines:
   * Darkness Assassin (*Torment* -> `Lacerate`)
   * Kinetic Combat Shadow (*Psychokinesis* -> `Whirling Blow`)
   * Neither discipline possesses an execute (ID `220`), bleed (ID `221`), or fire (ID `250`) damage modifier.
2. **Stat `250` (Bucket 6)** is exclusive to Vigilance Guardian:
   * *Burning Storm* -> `Cyclone Slash`
   * Vigilance Guardian possesses no execute, bleed, or accuracy-reduced damage modifiers.
3. **Stat `221` (Bucket 5)** is present on:
   * Vengeance Juggernaut (*Bloodbath* -> `Sweeping Slash`)
   * Advanced Prototype Powertech (*Blood Tracker* -> general damage)
   * Tactics Vanguard (*Triumph* -> general damage)
   * Innovative Ordnance Mercenary / Assault Specialist Commando (*Relentless Ordnance* / *Relentless Assault*)
4. **Stat `220` (Bucket 3)** is present on DPS specs:
   * Lethality/Virulence (*Devouring Microbes*)
   * Pyrotech/Plasmatech (*Burnout*)
   * Balance/Madness (*Mental Scarring* / *Creeping Death*)
   * Infiltration/Deception (*Judgement* / *Executioner*)
   * Serenity/Hatred (*Aching Mind* / *Inevitable Demise*, *Atrophying Attacks* / *Languishing Lashes*)
   * Dirty Fighting/Ruffian (*Cold Blooded*)
   * Innovative Ordnance / Assault Specialist (*Relentless Ordnance* / *Relentless Assault*)

### Pairwise Spec Coexistence Findings
* **Buckets 3 & 4 (`220` & `389`)**: **Disjoint**. Tank specs have `389`; Inquisitor/Consular DPS specs have `220`. Mutually exclusive skill trees.
* **Buckets 3 & 6 (`220` & `250`)**: **Disjoint**. Vigilance Guardian has `250` but no execute modifier.
* **Buckets 4 & 5 (`389` & `221`)**: **Disjoint**. `389` is Inquisitor/Consular tank; `221` is Warrior/BH/Trooper.
* **Buckets 4 & 6 (`389` & `250`)**: **Disjoint**. `389` is Inquisitor/Consular tank; `250` is Knight DPS.
* **Buckets 5 & 6 (`221` & `250`)**: **Disjoint**. `221` is Warrior/BH/Trooper; `250` is Knight. (Vengeance *Bloodbath* [Bleed `221`] and Vigilance *Burning Storm* [Burn `250`] are faction mirrors).
* **Buckets 3 & 5 (`220` & `221`)**: **Sole Spec Overlap**, but **Orthogonally Scoped**:
  * Coexists in Innovative Ordnance Mercenary (`abl.bounty_hunter.skill.innovative_ordnance.relentless_ordnance`) and Assault Specialist Commando (`abl.trooper.skill.assault_specialist.relentless_assault`).
  * In `Relentless Ordnance`, Effect 1 Branch 2 grants:
    * Action 1: `stat: 221` (Bleeding), `amount: 0.05` (+5%) scoped to `tag.abl.bounty_hunter.flamethrower_ability` (AS Commando: `tag.abl.trooper.elemental_attack`).
    * Action 2: `stat: 220` (Execute), `amount: 0.30` (+30%) scoped to `tag.abl.debuff.damage_over_time`.
  * Because direct flame/elemental hits and periodic DoT ticks never share these tags on the same damage event, both multipliers never apply to the same hit.

### Architectural & Testing Verdict
1. All four stats are **attacker-side conditional modifiers** (`STAT_cbt_damage_done_if_*`), meaning other raid participants cannot supply the missing multiplier to an attacker's hit.
2. An individual damage event in live SWTOR combat **never encounters more than one of Buckets 3 through 6 simultaneously**.
3. Therefore, whether Buckets 3 through 6 would be mutually multiplicative against each other ($[1 + B_3][1 + B_5]$) or mutually additive ($[1 + B_3 + B_5]$) is **physically untestable on any damage event in the live game**.
4. Each bucket is verified strictly as an independent multiplicative layer against **`BUCKET_1`** (Additive Base Pool) and **`BUCKET_2`** (AoE Overwhelmed).