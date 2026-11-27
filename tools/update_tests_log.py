"""Updates Test 7, Test 12, and Test 16 in docs/modifier_bucketing_log.md
to explicitly include the hypothesis of additive pooling in BUCKET_2 (with Overwhelmed)
and mathematically document how the observed hits disprove it.
"""

from pathlib import Path

LOG_PATH = Path("docs/modifier_bucketing_log.md")
CHECKLIST_PATH = Path("docs/modifier_bucketing_master_checklist.md")


def update_log():
    with open(LOG_PATH, "r", encoding="utf-8") as f:
        text = f.read()

    text = text.replace("\r\n", "\n")

    # 1. Update Test 7
    t7_start = text.find("### Test 7 —")
    t7_opt_start = text.find("#### Options Tested", t7_start)
    t7_end = text.find("\n---\n\n### Test 8", t7_opt_start)
    if t7_opt_start == -1 or t7_end == -1:
        raise ValueError("Could not find Test 7 bounds")

    new_test_7 = """#### Options Tested

| Option | Hypothesis Description | Multiplier | Expected Non-Crit Range | Expected Crit Range (`1.653618x`) |
| :--- | :--- | :--- | :--- | :--- |
| **Option A (Additive in `BUCKET_1`)** | $[1.0 + 0.25_{\\text{B1}} + 0.15_{\\text{Torment}}] \\times [1.10_{\\text{Overwhelmed}}] = 1.400 \\times 1.10$ | `1.54000` | **`8,268 – 8,917`** (`8268.24 – 8917.20`) | **`13,673 – 14,746`** (`13672.52 – 14745.62`) |
| **Option B (Additive in `BUCKET_2` with *Overwhelmed*)** | $[1.25_{\\text{B1}}] \\times [1.0 + 0.10_{\\text{Overwhelmed}} + 0.15_{\\text{Torment}}] = 1.25 \\times 1.25$ | `1.56250` | **`8,389 – 9,047`** (`8389.05 – 9047.48`) | **`13,872 – 14,961`** (`13872.29 – 14961.07`) |
| **Option C (New Multiplicative Bucket `BUCKET_4`)** | $[1.25_{\\text{B1}}] \\times [1.10_{\\text{Overwhelmed}}] \\times [1.15_{\\text{Torment}}]$ | `1.58125` | **`8,490 – 9,156`** (`8489.72 – 9156.05`) | **`14,039 – 15,140`** (`14038.75 – 15140.61`) |

#### In-Game Observation & Result

* **Observed Non-Crit Hits**: **`9,151`**, **`9,145`**, **`9,073`**, **`9,006`**, **`8,992`**, **`8,941`**

* **Observed Crit Hit**: **`14,834`**

* **Conclusion**: **Option C (New Multiplicative Bucket `BUCKET_4`)** is definitively proven.

  * **Rules Out `BUCKET_1` (Option A)**: The maximum theoretical ceiling for Option A is strictly **`8,917.20`** ($\mathbf{8,917}$) for non-crits and **`14,745.62`** ($\mathbf{14,746}$) for crits. All 6 recorded non-crit hits (`8,941` through `9,151`) and the recorded crit (`14,834`) strictly exceed Option A's mathematical ceiling (by up to $+234$ points).

  * **Rules Out `BUCKET_2` (Option B)**: If *Torment* pooled additively with *Overwhelmed* in `BUCKET_2` ($1.25 \\times 1.25 = 1.5625\\times$), the maximum theoretical ceiling for non-crits is strictly **`9,047.48`** ($\mathbf{9,047}$). Three recorded hits (**`9,073`**, **`9,145`**, and **`9,151`**) strictly breach this ceiling by up to $+104$ points, proving it cannot reside in `BUCKET_2`.

  * All recorded values sit squarely inside Option C's predicted exclusive window, with top rolls reaching within $5$ points of Option C's absolute theoretical ceiling (`9,156.05`).

  * Establishes **`BUCKET_4`** containing target-state accuracy reduced conditional damage (`STAT_cbt_damage_done_if_target_accuracy_reduced_modifier_percentage` / GOM `389` / *Torment*), proving that target-state conditional damage is an independent multiplicative layer from both `BUCKET_1` (Attacker Done + Channel/Type Vulns) and `BUCKET_2` (AoE Vuln)."""

    text = text[:t7_opt_start] + new_test_7 + text[t7_end:]

    # 2. Update Test 12
    t12_start = text.find("### Test 12 —")
    t12_opt_start = text.find("#### Options Tested", t12_start)
    t12_end = text.find("\n---\n\n### Test 13", t12_opt_start)
    if t12_opt_start == -1 or t12_end == -1:
        raise ValueError("Could not find Test 12 bounds")

    new_test_12 = """#### Options Tested (Target Bleeding Active via `Bleeding (Shatter)`)

| Option | Hypothesis Description | Multiplier Formula | Expected Non-Crit Range | Expected Crit Range (`1.653618x`) |
| :--- | :--- | :--- | :--- | :--- |
| **Option A (Additive in `BUCKET_1`)** | $[B_1(1.16) + 0.25_{\\text{Bloodbath}}] \\times B_2(1.10) = 1.41 \\times 1.10$ | `1.55100` | **`9,968 – 10,704`** | **`16,484 – 17,700`** |
| **Option B (Additive in `BUCKET_2` with *Overwhelmed*)** | $[B_1(1.16)] \\times [1.0 + 0.10_{\\text{Overwhelmed}} + 0.25_{\\text{Bloodbath}}] = 1.16 \\times 1.35$ | `1.56600` | **`10,065 – 10,808`** | **`16,643 – 17,871`** |
| **Option C (Separate Multiplicative Bucket `BUCKET_5`)** | $[B_1(1.16) \\times B_2(1.10)] \\times \\mathbf{1.25_{\\text{Bloodbath}}}$ | `1.59500` | **`10,251 – 11,008`** | **`16,952 – 18,202`** |

#### In-Game Observation & Result

* **Observed Non-Crit Hits**: **`10,892`**

* **Observed Crit Hits**: **`17,757`**, **`18,102`**

* **Conclusion**: **Option C (Separate Multiplicative Layer `BUCKET_5`)** is definitively proven.

  * **Rules Out `BUCKET_1` (Option A)**: The maximum mathematical ceiling for Option A is strictly **`10,704`** non-crit and **`17,700`** crit. The observed non-crit hit of **`10,892`** breaches Option A's ceiling by **188 points**, and both observed crits breach it by up to **402 points**.

  * **Rules Out `BUCKET_2` (Option B)**: If *Bloodbath* pooled additively with *Overwhelmed* in `BUCKET_2` ($1.16 \\times 1.35 = 1.5660\\times$), the maximum theoretical ceiling is strictly **`10,808`** for non-crits and **`17,871`** for crits. The observed non-crit hit of **`10,892`** breaches Option B's ceiling by **84 points**, and the observed crit hit of **`18,102`** breaches it by **231 points**, mathematically ruling out `BUCKET_2`.

  * All observed hits sit comfortably within Option C's predicted range (`10,251 – 11,008` non-crit, `16,952 – 18,202` crit).

  * Establishes that **Target State: Bleeding (`STAT_cbt_damage_done_if_target_bleeding_modifier_percentage` / GOM `221`)** does NOT pool additively into either `BUCKET_1` or `BUCKET_2`. It operates as an independent multiplicative layer, designated **`BUCKET_5`**, which multiplies against `BUCKET_1` (Damage Done/Vulnerabilities) and `BUCKET_2` (AoE Vulnerability)."""

    text = text[:t12_opt_start] + new_test_12 + text[t12_end:]

    # 3. Update Test 16
    t16_start = text.find("### Test 16 —")
    t16_opt_start = text.find("#### Options Tested", t16_start)
    t16_end = text.find("\n---\n\n### Test 17", t16_opt_start)
    if t16_opt_start == -1 or t16_end == -1:
        raise ValueError("Could not find Test 16 bounds")

    new_test_16 = """#### Options Tested

| Option | Hypothesis Description | Multiplier Formula | Expected Non-Crit Range | Expected Crit Range (`~65.36%` surge) |
| :--- | :--- | :---: | :---: | :---: |
| **Option A (Additive in `BUCKET_1`)** | $[1.0 + 0.05 + 0.06 + 0.05 + 0.25] \\times 1.10_{\\text{AoE}}$ | **`1.551000x`** | **`9,968` — `10,704`** | **`16,484` — `17,700`** |
| **Option B (Additive in `BUCKET_2` with *Overwhelmed*)** | $[1.0 + 0.05 + 0.06 + 0.05] \\times [1.0 + 0.10_{\\text{AoE}} + 0.25_{\\text{On Fire}}]$ | **`1.566000x`** | **`10,065` — `10,808`** | **`16,643` — `17,871`** |
| **Option C (Independent Multiplicative Layer `BUCKET_6`)** | $[1.0 + 0.05 + 0.06 + 0.05] \\times 1.10_{\\text{AoE}} \\times 1.25_{\\text{On Fire}}$ | **`1.595000x`** | **`10,251` — `11,008`** | **`16,952` — `18,202`** |

#### In-Game Observation & Result (Combat Log / StarParse)

* **Observed Non-Crit Hits**:
  * Minimum observed: **`10,262`** (strictly aligns with Option C minimum `10,251`; under Option A hits would drop to `9,968`, and under Option B to `10,065`)
  * Mid-to-high hits: **`10,784`**, **`10,908`**
* **Conclusion**: **Option C (Independent Multiplicative Layer `BUCKET_6`)** is definitively confirmed!
  * **Rules Out `BUCKET_1` (Option A)**: Option A established an absolute mathematical ceiling of **`10,704`**. The observed hits of `10,784` and `10,908` exceed the Option A maximum by up to $+204$ damage, which is mathematically impossible under Option A.
  * **Rules Out `BUCKET_2` (Option B)**: If *Burning Storm* pooled additively with *Overwhelmed* in `BUCKET_2` ($1.16 \\times 1.35 = 1.5660\\times$), the absolute maximum mathematical ceiling is strictly **`10,808`** ($6,901.36 \\times 1.566 = 10,807.53$). The observed hit of **`10,908`** exceeds this ceiling by **100 points**, proving it cannot reside in `BUCKET_2`.
  * All observed values fall strictly inside Option C's predicted $[10,251 \\dots 11,008]$ window.
  * Definitively proves that **Target State: On Fire / Burning (`250`)** forms an independent multiplicative layer (**`BUCKET_6`**), precisely mirroring the behavior of Target State: Bleeding (`221` / `BUCKET_5`) and Accuracy Reduced (`389` / `BUCKET_4`)."""

    text = text[:t16_opt_start] + new_test_16 + text[t16_end:]

    # Convert to CRLF
    text = text.replace("\n", "\r\n")
    with open(LOG_PATH, "wb") as f:
        f.write(text.encode("utf-8"))
    print("[OK] Successfully updated docs/modifier_bucketing_log.md (Test 7, 12, 16)")


def update_checklist():
    with open(CHECKLIST_PATH, "r", encoding="utf-8") as f:
        text = f.read()

    text = text.replace("\r\n", "\n")

    # Update links for Test 16 and Test 7 if needed
    text = text.replace(
        "[Test 16 — Target State: On Fire vs BUCKET_1](modifier_bucketing_log.md#test-16--target-state-on-fire-burning-stat_cbt_damage_done_if_target_on_fire_modifier_percentage--gom-250-vs-bucket_1)",
        "[Test 16 — Target State: On Fire vs BUCKET_1 & BUCKET_2](modifier_bucketing_log.md#test-16--target-state-on-fire--burning-stat_cbt_damage_done_if_target_on_fire_modifier_percentage--gom-250-vs-bucket_1--bucket_2)"
    )
    text = text.replace(
        "[Test 7 — Target-State Accuracy Reduced Conditional](modifier_bucketing_log.md#test-7--target-state-accuracy-reduced-conditional-stat_cbt_damage_done_if_target_accuracy_reduced_modifier_percentage--gom-389)",
        "[Test 7 — Target-State Conditional: Accuracy Reduced vs BUCKET_1 & BUCKET_2](modifier_bucketing_log.md#test-7--target-state-conditional-accuracy-reduced-torment--389-vs-bucket_1--bucket_2)"
    )

    text = text.replace("\n", "\r\n")
    with open(CHECKLIST_PATH, "wb") as f:
        f.write(text.encode("utf-8"))
    print("[OK] Successfully updated docs/modifier_bucketing_master_checklist.md")


if __name__ == "__main__":
    update_log()
    update_checklist()
