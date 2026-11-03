# Blueprint Engine Migration Archive (`rewrite.md`)

> [!NOTE]
> **Status: Complete.** The migration from hardcoded ability scripts (`abilities_temp.py` / `effects_temp.py`) to the GOM blueprint-driven architecture described below is **100% complete**.
>
> For current technical documentation, see:
> - **[Architecture Guide](architecture.md)** — Complete walkthrough of the production blueprint-driven discrete-event engine.
> - **[Combat Math Reference](combat_math.md)** — Mathematical specification of the 6 multiplicative damage buckets, diminishing returns, and hit resolution.
> - **[Extractor & JSON Schemas](extractor_and_schemas.md)** — How `.tor` MYP / GOM data is extracted into `data/extractor/parsed/`.
> - **[Developer Guide](developer_guide.md)** — How to add new stat IDs, action handlers, conditions, triggers, and class disciplines.

---

## Summary of the Completed Migration

Originally, SwtorSim relied on hand-written Python ability definitions and a flat proc list (`Proc`). The engine was rewritten to consume structured JSON blueprints extracted directly from SWTOR's Game Object Model (GOM):

1. **Unified Blueprint Hierarchy (`src/swtorsim/abilities.py`)**:
   - Replaced `abilities_temp.py` with `AbilityBlueprint`, `Effect`, `Branch`, and runtime `Ability`.
   - Active abilities (`type == "active"`) and passive packages/talents (`type == "passive"`) now share a single hydration and execution pipeline.
2. **Unified Runtime Effect System (`src/swtorsim/effects.py`, `src/swtorsim/entities.py`)**:
   - Replaced `effects_temp.py` and separate `Entity.buffs` / `Dummy.dots` dictionaries with `ActiveEffect` and `ActiveChannel` stored in `entity.effects`.
   - Added full support for stack scaling (`scales_with_stack_charge`), stack modification actions (`modify_stack_charge`, `set_effect_stack_charge`), duration modifications (`reset_timer`, `modify_active_duration`), and effect immunities (`grant_immunity`).
3. **Reactive Event Bus (`src/swtorsim/triggers.py`)**:
   - Replaced hardcoded proc checks with `TriggerManager`, supporting 22+ GOM trigger types (`on_damage_dealt`, `on_ability_activate`, `on_ability_post_activate`, `on_channeling_ended`, `on_enter_combat`, etc.) and internal cooldown (`interval_61`) rate-limiting.
4. **36 Condition Evaluators (`src/swtorsim/requirements.py`)**:
   - Implemented full support for all extracted GOM `cbtRequirement*` and `effRequirement*` condition nodes alongside rotation builder rules.
5. **6-Bucket Multiplicative Damage Model (`src/swtorsim/combat_math.py`)**:
   - Replaced legacy string-keyed modifier checks with authoritative GOM `modStatEnum` table dispatch across the 6 multiplicative damage buckets (`normal_percentage`, `sub_30`, `channel_scaling`, `damage_type_scaling`, `tag_scaling`, `target_state`).
