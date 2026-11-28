# How SwtorSim Assumes SWTOR Combat Works

This document describes the game mechanics the engine assumes, in the order the engine applies them. It is written from the code as it stands (2026-11-21), the CHANGELOG, `TODO.md` and earlier sessions. It describes behavior; it does not change it.

Where to find the code for each part: `ARCHITECTURE.md`. The damage formulas are frozen (`AGENTS.md` rule 1); this document only describes them.

**Evidence labels.** Many rules carry a label saying where they come from:

- **[log]** checked against a combat log (Parsely, raw game log) or tested in game by the user.
- **[data]** follows directly from the extracted game data (the GOM blueprints).
- **[choice]** an engine decision with no recorded game evidence. These are the first places to look when the sim and the game disagree.

Rules without a label are plain engine mechanics (how the clock or the event queue works).

---

## Contents

1. [Scope: what is simulated](#1-scope-what-is-simulated)
2. [The clock and the event queue](#2-the-clock-and-the-event-queue)
3. [How game data becomes abilities, effects and branches](#3-how-game-data-becomes-abilities-effects-and-branches)
4. [Setup: the order the character is built](#4-setup-the-order-the-character-is-built)
5. [The decision loop and the rotation](#5-the-decision-loop-and-the-rotation)
6. [Casting an ability](#6-casting-an-ability)
7. [Effects: application, refresh, ticks, expiry](#7-effects-application-refresh-ticks-expiry)
8. [Branches: how they are selected and run](#8-branches-how-they-are-selected-and-run)
9. [Actions](#9-actions)
10. [Damage: from action to landed hit](#10-damage-from-action-to-landed-hit)
11. [Procs: triggers on the event bus](#11-procs-triggers-on-the-event-bus)
12. [Conditions](#12-conditions)
13. [Resources](#13-resources)
14. [Stats, Alacrity and time scaling](#14-stats-alacrity-and-time-scaling)
15. [Combat state, stealth, immunity, death](#15-combat-state-stealth-immunity-death)
16. [Pre-combat (pre-pull)](#16-pre-combat-pre-pull)
17. [Simplifications and toggles](#17-simplifications-and-toggles)
18. [Open questions and points that look inconsistent](#18-open-questions-and-points-that-look-inconsistent)
19. [Where older docs disagree with the code](#19-where-older-docs-disagree-with-the-code)

---

## 1. Scope: what is simulated

- **One player against one training dummy.** The dummy never acts, never moves and never deals damage. There are no other players, companions or adds.
- **Damage only.** Heals, absorbs, threat, movement, knockbacks, stuns and similar actions are read from the data but do nothing (see section 9).
- **Position is fixed.** The player is always behind the target (`if_caster_positioning` is always true) at a fixed distance (default 30 m).
- **The fight is an Operation/Flashpoint encounter** by default (`in_flashpoint_operation = true`), which matters for abilities gated by `cnd.global.is_in_flashpoint_operation`.
- **The dummy** has 10% defense against every attack, base armor 17,225, toughness 5, creature type 1, resolve immunity, and is always in combat. With `training_dummy_armor_debuff` on it carries the 7 raid debuffs for the whole fight (Sundered -20% armor, Beat Down +5% melee, Marked +5% ranged, Vulnerable +5% Force, Susceptible +5% Tech, Assailable +7% elemental/internal, Overwhelmed +10% AoE), built from the game's own training-dummy debuff blueprint **[data]**.
- **Level** comes from the build: 80 on Live, 85 on PTS, each with its own curves (`combat_curves.json`).

---

## 2. The clock and the event queue

The engine is a discrete-event simulation. Nothing happens between events; time jumps from one event to the next.

**Ordering.** Events sit in a min-heap keyed by `(time, sequence number)`. Two events at the same time resolve in the order they were scheduled (first scheduled, first resolved). Several mechanics depend on this order; for example a DoT's last tick and an `EffectExpire` at the same timestamp would resolve expiry-first if the expiry was scheduled first (section 7.6).

**Nested resolution.** Much of the work does not go through the queue at all. An instant ability executes its effects inside the cast call. An undelayed hit is calculated, lands and fires its procs inside the action that created it, and those procs can deal damage and fire further procs, all at the same timestamp, depth first. Only things with a real delay (cast bars, channel ticks, DoT ticks, expiries, projectiles, delayed actions, charge recharges, resource ticks, the next decision) are queued.

**Time precision.** Timers that the player reads (`next_gcd`, cooldown end times, recharge end times) are rounded to 4 decimals. Decision times are rounded first and then clamped to "not earlier than now", so the clock never moves backwards.

**T0 is the first damage.** The fight clock starts when the first hit lands on the dummy (`combat_start_time`). Every log line and report time is relative to it; pre-combat times are negative. This matches how combat logs and StarParse count a fight **[log]**.

**End of the fight.** The run stops at the first of:
- `duration` seconds after T0 (events later than that are not resolved);
- the dummy reaching 0 HP (the event that kills it finishes resolving, then the run stops).

Before T0 the end is open while pre-combat is running (with a hard cap of 600 s + duration as a deadlock guard).

**DPS** is total damage divided by the time from T0 to the end. The **execute phase** is every hit landed while the dummy is at or below 30% HP.

**Randomness.** One seeded random stream drives everything: accuracy rolls, the damage roll, crit rolls, proc chances, `random_chance` conditions, action `chance` fields, the GCD stall model, and the phases of the first resource tick and of periodic procs. The same seed and the same inputs reproduce the same fight.

---

## 3. How game data becomes abilities, effects and branches

The extractor turns the game's GOM nodes into JSON blueprints. The engine assumes the following structure and meanings.

### 3.1 The hierarchy

```
Ability (abl.*)                cost, GCD, cooldown, charges, activation, target rule, conditions
  Effect 1..N (numbered)       duration, tick interval, tags, stack charge, conditions, target overrides
    Branch (sub-effect 2..M)   triggers, conditions, target overrides, actions, "else" gate
      Action                   damage, apply effect, resource, cooldown, stack change, ...
```

- **Ability.** Missing `type` means passive. An active ability without data uses a 1.5 s base GCD and triggers the GCD; a passive uses neither.
- **Effect.** Each GOM effect node is one numbered effect. Effect 0 is skipped.
  - **Entry vs called.** An effect is an *entry* effect (runs when the ability activates) unless one of its sub-effects carries `IfCalledByEffect`; called effects run only when another action names them (`call_effect`, `apply_effect`) **[data]**.
  - **Persistent vs instant.** An effect with a duration above 0, or flagged passive by its `SetPassive` initializer, lives on an actor. Anything else is instant: its branches run once and nothing is stored.
  - **Alacrity flag.** `effIgnoreAlacrity` defaults to *false* for effects that tick and *true* for effects that only have a duration, when the node does not say **[data]** (extractor default).
- **Sub-effect 1 is the header.** Its conditions, target overrides and initializers become the effect's own conditions, overrides and initializers. Sub-effects 2 and up become the branches.
- **Branches with no trigger** are given `on_apply`, so they run when the effect is applied (or, for an instant effect, when it executes).

### 3.2 Conditions the extractor removes

These GOM conditions are dropped and treated as always true: `IfCalledByEffect`, `IsAlive`, `IsEnemy`, `IfWeaponType`, `IsChanneling`, `InRange`. A dropped condition inside an **AND** simply disappears; inside an **OR** it makes the whole OR true (so `InRange(10m) OR (InRange(20m) AND HasAbility)` becomes "always true", not "HasAbility"). A gate that reduces to always true is removed. (The OR rule was fixed in the extractor; the parsed data on disk still has the old logic until the next re-extract, see `TODO.md`.)

### 3.3 If / else chains

`effCondition_Else` on a sub-effect means "run only if the previous sub-effect did not run". `effCondition_IfElseBlock` means "run only if no earlier member of the same block ran". The extractor writes both as `run_if_none_ran: [indices]` on the branch **[data]**.

### 3.4 Actions removed or reshaped by the extractor

- Dropped entirely: `PlayAppearance`, `ModifyThreat`, `Immobilize`, `ModifyMovementSpeed`. An effect made only of these is dropped.
- `WeaponDamage` becomes a `damage` action with `hand` and `attack_type` read from the equipment slots: slot 5 = melee main hand, 3 = melee off hand, 2 = ranged main hand, 4 = ranged off hand **[data]**. Flurry blow counts are kept.
- `SpellDamage` becomes a `damage` action with the GOM damage type (1 kinetic, 2 energy, 3 elemental, 4 internal).
- `ModifyStat` amounts that scale with item rating (relics, adrenals) are resolved at extraction time with the standard rating of the chosen item rating (extractor defaults: Live 344, PTS 380) **[log]** (relic surge values matched the in-game tooltip and PTS parse).
- Trigger delays: `on_pre_remove` / `on_timer_expired` / `on_remove` triggers get `delay = effect duration`; `on_tick` triggers with a tick number get `delay = tick number x tick interval`.

### 3.5 Ability targeting from the data

The game's `ablTargetRule` is extracted as `target_rule` **[data]**:

| Rule | Who the cast is aimed at |
|---|---|
| `attackable` | the enemy |
| `self`, `friendly`, `friendly_dead`, `companion`, `grouped`, `ground_self`, `cover_object` | the caster |
| `ground`, `any`, missing | heuristic: the enemy if the ability is tagged aggressive or basic attack, or has any damaging branch; else the caster **[choice]** |

A self-aimed ability can still damage the enemy through its own AoE target overrides (Sweeping Slash, Force Wave). Section 6.3 explains how "aimed at" differs from "aggressive".

---

## 4. Setup: the order the character is built

`prepare_simulation` builds a fight in this order. The order matters because later steps read state the earlier ones created.

1. **Split the loadout.** Active abilities (not `tal.*`) become castable `Ability` objects. Everything else (passives, talents, tactical, legendary implants, relics) is a passive blueprint. Abilities that another loaded ability triggers by name (`execute_ability`, the programmatic `custom` hook) are loaded too; they are indexed first so the selected ability wins a name clash.
2. **Player base stats** from the build (a shared `Force-Tech Power` key fills both Force Power and Tech Power; one attack only ever reads one of them). Standard health comes from the level curve. Stats are recalculated.
3. **The dummy**, with its permanent debuffs.
4. **Seed the random stream.**
5. **Load passives in two passes** (with `sim.loading` set, see section 14):
   - Pass 1: register every passive and apply its root `stat_changes` as a permanent effect. This happens for all passives first, so a `has_ability` check in one passive sees every other passive regardless of order.
   - Pass 2: run each passive's entry effects with the player as caster and target. Persistent passive effects are applied to the player and their triggers are subscribed to the event bus.
6. **Class buffs.** Every player gets all four class buffs (Unnatural Might, Mark of Power, Coordination, Hunter's Boon), built from their extracted passive blueprints, skipping any the player already has (or its mirror from the other faction). Legacy unlocks are assumed. Plus a hidden permanent bonus: +1% accuracy, +1% crit chance, +1% crit multiplier.
7. Stats are recalculated and `sim.loading` is cleared.
8. **Charge modifiers** are applied to every active ability (bonus max charges from talents).
9. **Rotation** is built; pre-combat steps and the pull gate are read from the rotation file.
10. **First events:** either the pre-combat runner at t = 0, or the first `PlayerReady` at t = 0. The first `ResourceTick` is placed at a random time in [0, 1) s, then repeats every 1.0 s.

---

## 5. The decision loop and the rotation

### 5.1 One decision chain

The player makes decisions through `PlayerReady` events. There is exactly one live chain per player: every hand-off (`schedule_next_decision`) starts a new generation, and any older `PlayerReady` still in the queue does nothing when it fires.

A `PlayerReady`:
1. does nothing while pre-combat owns the player;
2. asks the rotation to act;
3. if something was cast, hands off to the next decision time;
4. if nothing was cast: if the GCD is still running it waits for the GCD end; otherwise it polls again 0.1 s later and, unless a cast or channel is in progress, records a **rotation stall** until something casts.

**Next decision time** = the GCD end (`next_gcd`), or earlier by the upcoming step's lead time when that step casts an **off-GCD** ability. A step without its own `lead_time` uses the rotation file's `default_lead_time` (set in the Rotation Builder toolbar), else 0.1 s. A step with an on-GCD ability, or a priority block whose first viable option is on the GCD, gets no lead (an early wake-up would only let a lower-priority off-GCD option jump ahead).

Cast and channel completions also hand off, so the decision after a 2 s cast happens at the end of the cast, not at the GCD end.

### 5.2 Rotation structure

A rotation is an ordered `sequence` of steps, an optional `loop_anchor`, and an optional `weave` list.

- Steps before the `loop_anchor` are the **opener** and run once. After the last step the pointer goes back to the anchor; the steps from the anchor on loop forever.
- The rotation evaluates **only the current step**. It never looks ahead to later steps.

| Step | Behavior |
|---|---|
| `fixed` | Blocks until its ability casts. Before the GCD ends (lead-time wake-up) it can only cast an off-GCD ability. |
| `priority_block` | Tries its options top to bottom; casts the first whose rules pass and whose cast succeeds. Blocks until one casts. Before the GCD ends only off-GCD options are considered. A missing ability is skipped (traced as "not found in loadout"). |
| `optional` | Tries once (before the GCD ends, only an off-GCD ability can cast). If the player is free (GCD over, no cast or channel running) the step resolves whether it cast or not. If the GCD is still running, or a cast/channel is in progress, it waits instead of being skipped. |
| `weave` entries | Loop only. Each entry behaves like an `optional` step placed before every loop step, in list order. They reset when the loop step resolves. |

Rotation rules (`rules`) are ANDed. They are evaluated against the enemy as target, regardless of who the ability is aimed at. An unknown rule key stops the run with an error.

### 5.3 Busy states

While a cast bar or a channel is running, no ability can be cast, on-GCD or off-GCD (`can_cast` refuses). The rotation therefore never clips its own channels or casts **[choice]**. The clipping code in `Ability.cast` exists but is only reachable with `allow_clip`, which the rotation does not use.

---

## 6. Casting an ability

### 6.1 Can it be cast? (checked in this order)

1. Refresh max charges from talents.
2. On-GCD ability and the GCD is running: no. (Exact comparison: a GCD that ends 1e-14 s from now is still running.)
3. A channel or cast bar is running: no.
4. Charge ability with 0 charges: no.
5. Cooldown has more than 0.0001 s left: no.
6. The resource cost (after cost modifiers) cannot be paid: no.
7. The ability's own conditions fail (checked against the enemy if the ability is aimed at the enemy, else against the caster): no.

### 6.2 What a cast does (in this order)

1. Re-check `can_cast`.
2. Clear any channel or cast bar (only possible with `allow_clip`; a clipped channel fires `on_channeling_ended` with `is_successful = false` on the event bus, before its channel-bound effects are cleaned up, so the channel's own effect 1 hears it).
3. Work out the activation: instant, cast bar (scaled cast time > 0), or channel.
4. **Pay the cost now** for instant abilities and channels. **Timed casts pay at the end of the cast bar** (section 6.5).
5. **Lock timers:** set the GCD (on-GCD abilities) and either start the cooldown or spend a charge. Off-GCD abilities leave the GCD untouched.
6. Dispatch **`on_ability_activate`** on the event bus.
7. Set the player's current target.
8. If the ability is **aggressive**: break stealth; enter combat if not already (dispatching `on_enter_combat`).
9. Start an **activation token** (section 11.5).
10. Route:
    - **Instant:** dispatch **`on_ability_post_activate`**, then execute every entry effect now **[data]**. What the post-activate spends or grants is settled before the cast's hits are calculated and their damage triggers fire (damage triggers still fire per branch, section 10.5). Data that only works in this order: Energize grants Energize_3 (+50% Force crit damage on Shock, 1s) at Shock's post-activate while Shock's own hit removes Energize; War Machine marks Adrenaline Rush at its post-activate and Adrenaline Rush's entry effect reads the mark; Corrosive Return / Brutal Return refund the Tactical Advantage / Upper Hand the cast spends at post-activate when the hit lands with none left (user report: a Corrosive Assault at 1 stack ends at 1). Consequences not yet checked in game: buffs granted at an instant's post-activate also apply to that cast (Shock Trooper's +10% on the granting Flaming Fist), and Tactical Advantage / Upper Hand spenders no longer get the spent stack's generic crit bonus.
    - **Cast reduced to 0s:** execute the entry effects now, then dispatch `on_ability_post_activate` (the cast-finish order; Convection's +10% on Lightning Bolt is removed at the bolt's post-activate).
    - **Channel:** start the channel (entry effects run immediately), then dispatch `on_ability_post_activate`.
    - **Timed cast:** set the cast bar and schedule the cast finish. `on_ability_post_activate` waits for the finish.
11. Count the cast (for the casts column of the breakdown).

Cooldown and GCD lengths are snapshotted at cast time: Alacrity gained later does not shorten a running cooldown.

### 6.3 Aimed at the enemy vs aggressive

Two separate questions:
- **Aimed at the enemy** (`targets_enemy`): who the ability's conditions are checked on and who the entry effects receive as their target. From `target_rule` (section 3.5).
- **Aggressive** (`is_aggressive`): whether casting it enters combat and breaks stealth. True if it is aimed at the enemy **or** the tag/damage heuristic flags it. A self-centered damaging AoE (rule `self`) is aimed at the caster but still aggressive.

### 6.4 GCD, cooldowns and charges

- **GCD** = `(base x (1 + %mods) + flat mods) / (1 + Alacrity + instant-reduction bonus)`, **rounded up to the next 0.1 s** (stat 66 for GCD mods, stat 274 for the instant-reduction bonus). `ablIgnoreAlacrity` skips the Alacrity division.
- **GCD stall (lag model).** With `gcd_stall = p`, a fraction p of GCDs is 0.1 s longer **[choice]** (calibrated to about 30% of 1.4 s GCDs on PTS). Default 0: no random draw.
- **Cooldown** = `(base x (1 + %mods) + flat mods) / (1 + Alacrity + instant-reduction bonus)`, rounded up to 0.1 s (stat 64). Cooldowns always scale with Alacrity, even for `ablIgnoreAlacrity` abilities.
- **Charges.** Spending a charge while at full charges starts a recharge. The recharge length (stat 423 mods if an effect carries one for this ability, otherwise its stat 64 mods, never both from one effect **[data]**; divided by the Alacrity stat only, rounded up to 0.1 s) is snapshotted when it starts. When a recharge finishes and the ability is still not full, the next recharge starts. A granted charge does not restart a running recharge. Recharge uses the Alacrity stat without the instant-reduction bonus **[choice]** (no log evidence either way).
- **Max charges change** (talent or tactical swap): a rising max adds the difference to the current charges; a falling max caps the current charges at the new max and never hands back a spent charge **[choice]** (the user's call, untested in game).
- A charge ability has no entry in the cooldown map; cooldown rules read its recharge end time when it has 0 charges.

### 6.5 Cast bars

- **Cast time** = `(base x (1 + %mods) + flat mods) / (1 + Alacrity + cast-speed bonus)`, rounded to 4 decimals (stat 62 for cast-time mods, stat 256 for the cast-speed bonus). The bonus is extra Alacrity, the same way the GCD adds stat 274 **[choice]** (the user's call, 2026-11-28; no log measured yet). `ablIgnoreAlacrity` skips the division, bonus included. The instant-reduction bonus (274) does not apply.
- During the bar the player can do nothing else.
- **At the end of the bar** the cost is computed again (modifiers as they are now) and paid. If it cannot be paid the cast fails: no effects, no post-activate, and the next decision is scheduled. If it can, the entry effects execute, `on_ability_post_activate` fires, and the next decision is scheduled.
- An interrupted cast (`ability_cancel`) does nothing at the end of the bar. The GCD and cooldown were already spent at cast start.

### 6.6 Channels

- **Duration** = `(base x (1 + %mods) + flat mods) / (1 + Alacrity + channel-speed bonus)` (stat 63 for channel mods, stat 257 for the channel-speed bonus), rounded to 4 decimals. The bonus is extra Alacrity, as for cast time **[choice]**.
- **Tick count** is fixed by the base data: the base tick interval is the first effect tick interval found, else the smallest `on_tick` delay, else `min(1 s, duration / 3)`; stat 45 tick mods then apply; ticks = `round(base duration / base interval)`. The scaled interval is `scaled duration / ticks`, so faster channels keep every tick, only closer together (Penetrating Blasts keeps its 5th tick under Sniper Volley **[data]**).
- **At channel start** the entry effects run immediately (the initial hit). If they cancel the channel, no ticks follow.
- **Each tick** (first one 1 interval after the start) runs the `on_tick` branches of **every** effect of the ability, with the tick number (a branch with `tick_number` n only runs on tick n; 0 means every tick). These branches are run directly: the effects' own conditions and target overrides are not re-checked at tick time.
- **Natural end** (after the last tick): the event-bus `on_channeling_ended` fires with `is_successful = true` (the ability's own channel-end branches sit on its effect 1, which is applied and subscribed for the channel, so they run once, through the bus), channel-bound effects are cleaned up, and the next decision is scheduled.
- **Channel-bound effects.** Persistent effects the channel applies with no duration of their own are removed when the channel ends (their `on_pre_remove` runs once). Effects with their own duration stay.
- Channels have no per-tick cost.

---

## 7. Effects: application, refresh, ticks, expiry

### 7.1 Executing an effect (in this order)

1. **Target.** Start from the target the caller passed (the enemy or the caster, section 6.3). The effect's own target overrides replace it (section 8.3). If the effect has no overrides but has a branch triggered by `on_damage_dealt` or `on_ability_activated`, or a retaliation branch (`on_damage_taken` answering `trigger_caster`, e.g. Cloak of Pain, Rebuke), the effect goes on the caster.
2. **Effect conditions.** If they fail, nothing happens.
3. **Immunity.** If the target is immune to any of the effect's tags, nothing happens.
4. **Pre-combat.** While pre-combat runs, effects aimed at anyone other than the caster are not applied.
5. **Persistent effect:** apply or refresh it on the target (section 7.2), then run its `on_refresh` branches (if it was already active) or `on_apply` branches (if new). If a refresh raised its stacks, run its `on_stack_charge_increased` branches and dispatch `on_stack_charge_increased` on the bus. Then schedule its `on_timer_expired` branches (section 7.7).
6. **Instant effect:** dispatch **`on_effect_applied`** and **`on_effect_received`** on the bus (target = the effect's target, tags = the effect's tags, `include_effect_refreshes` false), then run its `on_apply` (and untriggered) branches now, then schedule its `on_timer_expired` branches **[data]**. Tactical Advantage and Upper Hand gain a stack only on receiving a `ta_granter` / `uh_granter` effect, and every such effect is instant (Corrosive Return, Fatality, Lethal Strike, Backstab, Holotraverse, Tactical Stims, Brutal Return, ...); without the dispatch none of those grants lands.

### 7.2 Applying a persistent effect

1. **Duration** = base duration after stat 44 mods, then divided by Alacrity unless the effect ignores Alacrity. Which Alacrity: the **Alacrity stat only** while the character loads, **total Alacrity** (stat + instant-reduction bonus) for anything applied later **[log]** (Radiation Burns tick spacing and the Vent Heat effect in a Mercenary parse; load-time rule tested in game).
2. **Key.** The effect is stored under `"<ability fqn>:<effect number>"`. The same effect of the same ability refreshes itself; same-named effects from different abilities coexist. Lookups by display name still work (first active match).
3. **Ticks** (effect with both a duration and a tick interval): base tick after stat 45 mods; tick count = `max(1, round(base duration / base tick))`; scaled tick = scaled duration / tick count. The last tick lands exactly at the end of the duration.
4. **Passive ticking effects** (effects of passive abilities with a tick interval and no duration, e.g. Terminal Velocity): tick forever at an interval fixed when applied **[log]** (Terminal Velocity sits on a fixed 1.4345 s grid in a Mercenary parse).
5. **By-tag replacement.** If the incoming effect is `is_by_tag` with `relevant_tags` and no instance of it is active, an active effect that shares one of those tags and is also by-tag (or is one of the dummy's permanent debuffs) is replaced. With `nr_occurances = 1` the old one is dropped (its triggers unsubscribed; its `on_pre_remove` does **not** run). A dummy debuff that is replaced passes on its permanence. This stops Sundered from stacking with another -20% armor debuff **[data]**.
6. **Refresh** (the effect is already active under its key). A new instance replaces the old one:
   - **Stacks:** if the effect can stack (`max > 1` and `initial < max`) it gains **one** stack, capped at max. Otherwise (single stack, or a countdown pool with `initial = max`) it resets to `max(old stacks, initial)`, which for a countdown pool is its initial count.
   - **End time** = the later of the old end time and the new one; a refresh never shortens an effect. A permanent effect stays permanent.
   - **Immunities** the first application granted are kept (a refresh does not re-run `on_apply`).
   - **Proc ICDs** of its triggers carry over **[choice]** (taken from a bug report; not yet confirmed against a log). A new application after the effect ended starts with fresh ICDs.
   - The tick phase restarts: the next tick comes one full tick interval after the refresh.
7. **Stat modifiers are read now** from the effect's branches (section 7.3).
8. **Subscribe triggers.** Every branch trigger that is not a lifecycle trigger is registered on the event bus, owned by this effect instance.
9. Dispatch **`on_effect_applied`** and **`on_effect_received`** (on every application and refresh; `include_effect_refreshes` is true only when the same effect of the same ability was refreshed).
10. Schedule the first tick (ticking effects) or the expiry (timed effects without ticks).
11. Recalculate the owner's stats if the effect carries modifiers.

### 7.3 Stat modifiers are a snapshot

The modifiers an effect gives are collected **once, when it is applied or refreshed**: the engine walks the effect's branches in index order, skips branches whose conditions fail at that moment or whose `run_if_none_ran` gate is closed, and turns every `modify_stat`, `modify_meta_stat` and `apply_conditional_(meta_)stat_mod` action into a modifier **[choice]**. Branch triggers are not looked at for this. A condition that changes while the buff is up does not change its modifiers until the next refresh.

- `is_percent` modifiers hold decimal fractions (0.05 = 5%). There is no magnitude guessing (`AGENTS.md` rule 2).
- An effect that `scales_with_stack_charge` multiplies all its modifier values by its current stacks.
- A modifier with targets (ability FQNs or tags) applies only to matching abilities; one without targets applies to everything.
- Conditional modifiers (`apply_conditional_stat_mod`) also need their conditional tag on an active effect: on the target (actor 3), on the caster (actor 1), or on either (unspecified), optionally only effects applied by this caster.

### 7.4 Stacks

- `modify_stack_charge` adds or removes stacks, clamped to `[0, max]`. Gaining stacks runs the effect's `on_stack_charge_increased` branches and dispatches the bus event. Losing stacks runs its `on_stack_charge_decreased` branches (with the trigger's own `proc_chance_percent`, e.g. Deathmark's 50% refund) and dispatches the bus event. A stack-loss branch that refunds the last stack keeps the effect alive.
- `set_effect_stack_charge` sets an exact count (clamped to max) without firing stack events.
- An effect at 0 stacks is removed (its `on_pre_remove` runs once).
- Stack-charge conditions count by tag: `has_effect` with `count = n` adds up the stacks of **every** matching effect, so three different DoTs sharing a tag count as 3 **[log]** (Leeching Strike restores 12 Force on 31 of 31 casts).

### 7.5 DoT and buff ticks

- The first tick lands one tick interval after the application; there is no tick at application.
- Each tick runs the effect's `on_tick` branches (tick number rules as for channels), with `is_periodic` set and the owner effect's stacks as multiplier when it scales with stacks. Effect conditions are not re-checked at tick time.
- After the last tick the effect expires through that tick (section 7.6).
- If the end time was pushed out after the ticks ran out, ticking continues for the remaining time.
- **`reset_timer`** restores full duration and full ticks and **restarts the tick phase**: the next tick comes one full interval after the reset, and the pending tick is discarded **[log]** (Corrosive Dart ticks in a Marksmanship parse are always one interval after the reset). A ticking effect keeps its final tick (it expires through the tick, not a separate expiry event).
- **`modify_active_duration`** moves the end time of matching effects (by tag, or the owning effect) by the given seconds; it never moves it into the past. It does not change the tick count.

### 7.6 Expiry and removal

Every way an effect can end runs its **`on_pre_remove` branches exactly once** per instance, then removes it:

| Path | `on_pre_remove` | Evidence |
|---|---|---|
| Natural expiry (`EffectExpire`) | yes | |
| Last DoT tick | yes | Ferocity_2 consumes its stack this way **[data]** |
| `remove_effect`, `dispel`, `buff_remove` | yes | **[log]** confirmed in game for `remove_effect` / stack depletion (Thermal Detonator explosion, Shoulder Cannon 90 s cooldown); `dispel` rests on the data |
| Stacks reach 0 | yes | same |
| Channel end (channel-bound effects) | yes | |
| Stealth broken | yes | (Stealth's 6 s cooldown lives there **[data]**) |
| By-tag replacement | **no** | |
| Refresh | **no** (the effect continues) | |
| Tactical swap | **no** | |

Removing an effect unsubscribes its triggers and recalculates stats.

An `EffectExpire` that belongs to an older instance (the effect was refreshed or removed since) does nothing. A stale `DotTick` (older instance, or older tick phase) does nothing.

### 7.7 Delayed branches (`on_timer_expired`)

A branch triggered by `on_timer_expired` runs once, `delay` seconds after the effect executes (the delay is the effect's raw duration from the data). It is skipped if the caster or the target is dead by then.

---

## 8. Branches: how they are selected and run

### 8.1 Which branches run

When an effect runs the branches of a lifecycle trigger (`on_apply`, `on_refresh`, `on_tick`, `on_stack_charge_*`, `on_pre_remove`, `on_travel_complete`), it walks its branches **in index order** and for each:

1. **Trigger match.** The branch must list that trigger. Extra filters per trigger:
   - `on_tick`: `tick_number` must be 0 or the current tick.
   - `on_stack_charge_increased/decreased`: a `count` requirement needs at least that many current stacks.
   - `on_channeling_ended`: `is_successful` must match.
   - `on_stack_charge_decreased`: the trigger's `proc_chance_percent` is rolled.
2. **Else gate.** If any branch named in `run_if_none_ran` has already run in this pass, skip.
3. **Run the branch** (section 8.2). A branch counts as "ran" if its conditions passed and its proc roll succeeded, even if its attack missed.

### 8.2 Running one branch (in this order)

1. **Target overrides** pick the branch target (section 8.3).
2. **Branch conditions**, checked against the branch target. Fail: the branch did not run.
3. **Proc chance** (only for stack-loss triggers here; event-bus procs roll in the dispatcher). Rolled only after the conditions pass, so a failed branch draws nothing from the random stream.
4. **Hit group.** If the branch holds a damage action that is not its last action (2 or more damage actions, or a damage action followed by other actions), a hit group opens (section 10.5).
5. **Actions run top to bottom.** For each action:
   - **Result gates.** An action with `results` or `combat_math_only` looks at the damage actions **earlier in the same branch**:
     - only failure results (`Miss`, `Immune`, `Resisted`): runs if the attack failed;
     - `Crit` only: runs if the attack crit (a delayed hit's crit is unknown; it then counts as "hit");
     - anything else: runs if the attack hit;
     - `match_all` means all earlier attacks must qualify, otherwise any one.
     If there was no earlier damage action in the branch, the gate is ignored and the action runs **[choice]**.
   - **Action conditions and `chance`.** An action whose own conditions fail, or whose `chance` roll fails, **stops the rest of the branch** **[choice]**. A damage action that misses does not stop the branch; later actions decide through their result gates.
6. The hit group closes and releases its parked procs.

### 8.3 Target overrides

| Override | Resolves to |
|---|---|
| `caster` | the caster |
| `aoe_sphere`, `aoe_cone`, `enemies_list`, `primary_target` | the enemy (the trigger's enemy target, else the caster's current target) |
| `party_members` | the caster (no group in the sim) |
| `trigger_target` / `trigger_caster` | the target / caster of the event that fired the proc |
| anything else (`pet`, `companion`, `random_enemy`, ...) | ignored; the current target stays |

Overrides apply in list order; the last one wins. AoE abilities hit the single dummy once.

---

## 9. Actions

| Action | What the engine assumes it does |
|---|---|
| `damage` | Section 10. |
| `call_effect` | Runs another effect of the same ability by number, on the caster (`to_actor` caster/self) or on the branch target. Passes the context through. |
| `apply_effect`, `buff`, `debuff`, `dot` | Executes the referenced effect (section 7.1). |
| `execute_ability` | Runs another ability's entry effects: no cost, no GCD, no cooldown, no `on_ability_activate`. |
| `custom` with hook `6855115466292073041` | Same as `execute_ability` for the ability in `param2`, against the branch target (Force Cloak, Cloaking Screen, Disappearing Act: the caster; base Shoulder Cannon: the enemy) **[data]**. |
| `energy_recovery`, `resource_gain`, `regen_force`, `regen_energy`, `restore_action_points` | Gain `flat + percent x max`, then `x (1 + restore % mods) + restore flat mods` (stats 90/91 Rage/Focus, 92/93 Force, 94/95 Energy/Heat). For Heat it vents. With a `delay` the gain is scheduled. |
| `spend_energy`, `spend_force` | Spend `flat + % of max + % of current`. If it cannot be paid, nothing is spent. |
| `modify_cooldown`, `cooldown_mod` | Shorten (or lengthen) a running cooldown of matching abilities (FQN or tags): flat seconds, or a percentage of the **base** cooldown; `-100%` resets it. Skipped for charge abilities. |
| `modify_recharge_time` | On a charge ability, move the running recharge timer; reaching now restores the charge at once and starts the next recharge. On a normal ability, same as `modify_cooldown`. |
| `grant_charge`, `modify_ability_stack_charge` | Add or remove ability charges. |
| `cooldown` | Put an ability on cooldown: the one in `timer_spec` (else `ability_spec`, else the triggering ability) **[data]**; length from the action or the ability's base cooldown, scaled by Alacrity unless the action ignores it; never shortens a longer running cooldown. |
| `global_cooldown` | Start a GCD of the given length (default 1.5 s), scaled like the GCD; never shortens a longer one. Not affected by the GCD stall model. |
| `modify_stack_charge` | Section 7.4. Which effect: by tag (owner, caster, then target); or by `ability_spec`, only that ability's effect that declares a stack charge, and nothing if none is active **[choice]** (open, see section 18); or else the effect the branch belongs to. |
| `set_effect_stack_charge` | Section 7.4, same target search. |
| `remove_effect` | Removes **the effect the branch belongs to**. The game data gives it no parameters (all 664 live nodes are empty), so it cannot mean anything else **[data]**. With no owning effect it does nothing **[choice]**. |
| `dispel` | Removes effects matching an ability spec or tags from both caster and target, dispatching `on_effect_dispelled` first. |
| `buff_remove` | Removes a named effect from the caster. |
| `reset_timer` | Section 7.5. |
| `modify_active_duration` | Section 7.5. |
| `invoke_projectile` | Runs the effect's `on_travel_complete` branches after the flight time: a fixed time for timed projectiles (interval 41, always on, e.g. Saber Throw), `distance / (speed x 10)` for others when flight time is enabled, else at once. Skipped if caster or target died in flight. |
| `grant_immunity` | Adds immunity tags to the effect it belongs to (they go away with it), or to the actor. |
| `ability_cancel` | Ends the actor's channel (`on_channeling_ended` with `is_successful = false`, then cleans up channel-bound effects) and cancels a cast bar. |
| `take_cover`, `take_portable_cover`, `leave_cover`, `become_stealthed`, `enter_combat`, `exit_combat` | Set the actor's flag (the two combat actions also dispatch `on_enter_combat` / `on_exit_combat`). |
| `modify_stat`, `modify_meta_stat`, `apply_conditional_*` | Nothing at run time; their values become the effect's modifiers when it is applied (section 7.3). |
| Heals, absorbs, threat, movement, crowd control, revive, pets, `god_damage`, `insta_kill`, ... | Nothing (no-op list in `abilities.py`). |
| Any other action type | The run stops with an error. |

---

## 10. Damage: from action to landed hit

### 10.1 Preparing the hit

1. **Off-hand without an off-hand weapon:** the action does nothing (and counts as success).
2. **Periodic?** A hit is periodic when it comes from a tick, or the effect tags end in `.periodic_damage` / are `tag.abl.debuff.damage_over_time`.
3. **Attack type** (1 melee, 2 ranged, 3 Force, 4 Tech):
   - Weapon actions (`hand` present): from the slots; failing that, ranged if tagged ranged or the class is Agent, Smuggler, Bounty Hunter or Trooper, else melee **[choice]**.
   - Spell actions: **Tech** if tagged tech, or the class is Agent / Smuggler / Bounty Hunter / Trooper, or the player has Tech Power and no Force Power; otherwise **Force** **[choice]**.
4. **Damage type:** the action's own type; weapon attacks with no type deal **energy**, other untyped attacks **kinetic** **[choice]** (lightsabers and blasters).
5. **Stack multiplier:** the coefficient and both standard-health percentages are multiplied by the context's `stack_multiplier` (section 18 lists where that value comes from).
6. **Flurry:** a flurry of n blows splits the coefficient and standard-health percentages by n, and the amount modifier as `(1 + amp) / n - 1`. Each blow rolls accuracy separately.
7. **Tags** of the hit = action tags + ability tags + effect tags. Damage modifiers and proc filters match against these.

### 10.2 Accuracy

Per blow, before damage is computed:

- Hit chance = accuracy - defense.
- **Accuracy:** main hand / Force / Tech: `1 + accuracy from rating + flat accuracy mods (incl. hidden 1%)` plus that attack type's accuracy mods (stats 114, 120, 232, 233, 11). **Off hand:** the same with base 0.67 instead of 1, plus stat 126.
- **Defense:** the dummy's 10% plus defense mods on it (115, 121, 234, 235).
- At 110% accuracy main-hand, Force and Tech attacks always hit; an off-hand hit has 77% accuracy against 10% defense and lands 67% of the time.
- A miss creates no hit; it counts as a failed attack for result gates.

### 10.3 The damage formula (frozen; summary only)

The authoritative formulas are in `combat_math.py` (and its twin `combat_math_unbucketed.py`). In order:

1. **Base damage**, a whole number rolled uniformly between min and max:
   - Force / Tech: `coefficient x bonus damage + standard-health % x standard health`.
   - Weapon: `(1 + amp) x weapon damage + coefficient x bonus damage + standard-health % x standard health`. Weapon damage is scaled by stat 413. **Off-hand weapon damage is 0.25 x the off-hand weapon** (0.25 + stat 127 with Dual Wield Mastery) **[log]** (Battering Assault and Rapid Shots off-hand hits, 2026-11-17).
2. **Armor** (kinetic and energy only; elemental and internal ignore it): `armor x (1 - armor penetration)`, then `DR = armor / (armor + multiplier x level + additive)` with the level constants from the curves.
3. **Damage buckets:** additive inside a bucket, multiplicative between buckets **[log]** (each bucket assignment came from an empirical test, `docs/modifier_bucketing_log.md`):

   | Bucket | Members |
   |---|---|
   | 1 | caster 79 (damage done %), 395 / 397 (energy / kinetic dealt), 407 / 409 (melee / Force dealt); target 370 / 376 (elemental / internal taken), 382 / 384 / 386 / 388 (ranged / melee / Force / Tech taken), 456, 458, 459, 463 |
   | 2 | target 46 (damage received %, e.g. Overwhelmed on AoE) |
   | 3 | caster 220 (target at or below 30% HP) |
   | 4 | caster 389 (target has an `accuracy_reduced` effect) |
   | 5 | caster 221 (target has a `bleed` effect) |
   | 6 | caster 250 (target has a `burn`/`fire` effect) |

   A damage stat with **no verified bucket** that matches a hit stops the run with a fatal error instead of guessing (e.g. 222, 393, 399, 405, 411, 449-466 on the caster; 47, 223, 369-375, 381, 383, 385, 387, 457, 460 on the target). Stat 78 (flat damage done) is a verified no-op. Stats not in the tables are ignored at hit time.
4. **Crit:** chance = sheet crit + crit chance mods (116 / 122 / 133 / 135, also on the target). On a crit the damage is multiplied by `1 + (surge + surge mods) x max(1, crit chance)`: crit chance above 100% raises the multiplier.
5. The result is truncated to a whole number.

### 10.4 Landing the hit (in this order)

1. A hit created while pre-combat owns the player is dropped (also when it lands later, e.g. a projectile).
2. Calculate the damage (10.3) and the crit.
3. Dispatch **`on_pre_damage_dealt`** and **`on_pre_damage_taken`**. The damage is already fixed: these procs cannot change this hit.
4. Land it: start the fight clock if this is the first damage, log it, subtract HP. If HP reaches 0 for the first time: dispatch `on_pre_death`, `on_death`, `on_kill`.
5. A non-periodic hit breaks the attacker's stealth.
6. Dispatch **`on_damage_dealt`** and **`on_damage_taken`**, or park them in the branch's hit group.

The proc context carries: crit flag, resolved damage type, attack type, spell type (1 weapon, 2 Tech, 3 Force), weapon flag, periodic flag, weapon mode (2 melee weapon, 3 ranged weapon, 0 otherwise), tags and the final damage.

A delayed `damage` action schedules the whole sequence; the damage is calculated when it lands, from the state at that moment.

### 10.5 Hit groups: hits of one branch share one state

When one branch holds a damage action followed by more actions (main hand + off hand, Battering Assault's main / off / main, Shock's hit + `call_effect`s), every hit is still calculated and lands in order, but their `on_damage_dealt` / `on_damage_taken` procs are **held until the whole branch has finished** (including its delayed hits), then fired in hit order **[log]** (confirmed in game, 2026-11-17):

- A buff the first hit consumes still applies to the later hits of the branch (Pulverize on the Dual Saber Throw off-hand hit; Priming Bolts on the Priming Shot off-hand hit).
- An effect the first hit's procs grant does **not** apply to the later hits of the branch (Battering Assault: Beat Down / Juyo Form from hit 1 do not raise hit 3; 17 casts).
- Hits in **separate branches** of one ability resolve one after another as usual (Vicious Slash).
- Do not narrow the deferral to "removals only": the gain direction above contradicts that.
- Non-damage actions between the hits still run in place. An effect applied between two hits does hear the earlier hit's procs once they are released (Hemorrhaging Blast's debuff echoes both Blood Choke detonations set off by the main-hand hit) **[log]** (226 casts in 10 logs; a filter that blocked this was reverted).
- The same holds for a branch with **one** damage action followed by other actions: those actions run before the hit's procs fire **[data]**. PTS Shock (Lightning): branch 3 is damage, `call_effect 2`, `call_effect 6`; effect 6 needs the Lightning Torrent buff, which makes Shock crit and is removed by Shock's crit `on_damage_dealt`. Firing the proc right after the hit made effect 6 (Shock casts Crushing Darkness) unreachable. A branch whose only damage action is its last action fires its procs right after the hit.

Relic surges proc'd by a cast do not raise that cast's own hits **[log]**; in the sim this follows from procs firing after the hit is calculated.

---

## 11. Procs: triggers on the event bus

### 11.1 Two kinds of triggers

- **Lifecycle triggers** (`on_apply`, `on_refresh`, `on_tick`, `on_stack_charge_increased`, `on_stack_charge_decreased`) belong to the effect itself and run through section 8.1. They are never put on the bus.
- **Event-bus triggers** (everything else) are subscribed when their effect is applied (passives at load, buffs and debuffs when applied) and unsubscribed when it ends. Each listener remembers its caster (who applied the effect) and its owner (the entity the effect sits on).

Events the engine dispatches on the bus: `on_ability_activate`, `on_ability_post_activate`, `on_enter_combat`, `on_exit_combat`, `on_pre_damage_dealt`, `on_pre_damage_taken`, `on_damage_dealt`, `on_damage_taken`, `on_pre_death`, `on_death`, `on_kill`, `on_effect_applied`, `on_effect_received`, `on_effect_dispelled`, `on_stack_charge_increased`, `on_stack_charge_decreased`, `on_channeling_ended`. Healing events exist in the filters but nothing dispatches them.

### 11.2 Dispatch: filters in order

For each listener of the event, in subscription order (a snapshot taken when the dispatch starts):

1. **Actor.** "Dealt" events (`on_damage_dealt`, `on_pre_damage_dealt`, `on_kill`, `on_effect_applied`, `on_ability_activate`, `on_channeling_ended`, ...) need the event's caster to be the listener's caster. "Taken" events (`on_damage_taken`, `on_pre_damage_taken`, `on_death`, `on_pre_death`, `on_effect_received`) need the event's target to be the listener's owner. So a debuff on the dummy listening for `on_damage_taken` hears every hit on the dummy; a player buff listening for `on_damage_dealt` hears every hit the player deals.
2. **Excluded tags:** any match rejects.
3. **Flags:** `is_successful` must match; `include_effect_refreshes = false` rejects refreshes.
4. **Required tags:** at least one must match (OR).
5. **Crit result:** a trigger requiring `effResultCrit` needs a crit.
6. **Ability spec** must equal the event's ability (with the `_plus` stem when stem matching is on). **Damage type** (0 or 5 = any), **spell type** (1 = any) and **weapon mode** (1 = any; 2 melee weapon hits only; 3 ranged weapon hits only; periodic hits never match 2 or 3) must match **[data]**.
6b. **Else gate:** a branch with `run_if_none_ran` is skipped when one of its gate branches of the same owner effect already ran on this event (same rule as the lifecycle pass; an owner's listeners are registered in branch order). Checked before the rate limit and proc roll, so a skipped branch spends neither.
7. **Same-activation rule** (section 11.5).
8. **Rate limit (ICD):** `(interval_61 + stat 229 mods) / (1 + total Alacrity)`, unrounded, read when the proc fires **[log]** (confirmed in game; Bloodlust's 3 s limit is 2.787 s at 7.64% Alacrity). It applies to every trigger, including abilities flagged `ablIgnoreAlacrity`. Relics keep their 20 s through a separate lockout effect that ignores Alacrity **[data]**.
9. **Proc chance:** `proc_chance_percent + stat 228 mods x 100`, capped to [0, 100]; at 100 no random number is drawn.
10. **Run the branch** with the listener's caster as caster and **the owner as the default target**. The ICD is locked *before* the branch runs (so its own damage cannot re-fire it) and released again if the branch did not run (its conditions failed).

The branch context adds the owner effect: its stacks (`current_stacks`), its stack multiplier (stacks if it scales with stacks, else 1), and `owner_effect_key`, so `remove_effect`, `reset_timer` and friends act on the right effect.

### 11.3 Nesting

A proc's branch runs immediately, inside the dispatch, and can deal damage that dispatches further events before the outer dispatch continues with its next listener. The only thing that stops a listener from re-triggering itself through its own damage is its rate limit.

### 11.4 Proc lockouts the rotation can read

`proc_cooldown_above` resolves a proc name through the proc registry built at load: either a **lockout effect** (an effect tagged `...lockout`, e.g. `Bloodletting_3`) whose remaining time is read, or a **trigger ICD** (`interval_61` on a passive) whose remaining lockout is read from the bus.

### 11.5 Same-activation rule for `on_ability_post_activate`

Each activation (an instant cast, a channel start, a cast finish) carries a token. An effect (re)applied during that activation does **not** hear that activation's `on_ability_post_activate`, unless it is an **entry effect of the activating ability** **[log]**:

- A crit that grants Lightning Effusion does not spend one of its 2 charges on the same cast (PTS Lightning trace: the next two Force attacks are discounted).
- Translocate's Benign Presence and Take Cover's Hot Pursuit are not removed by the activation that granted them.
- Thundering Blast's own entry effect (25% Forked Darkness echo) still hears Thundering Blast's post-activate **[data]**.

For an instant cast the post-activate now comes before the entry effects (section 6, step 10), so effects the cast's hits apply (a crit proc, a called buff) do not exist yet when it fires; the rule still matters for effects applied by `on_ability_activate` procs, for channel starts and for cast finishes. No instant ability's entry effect listens to its own post-activate in the PTS data.

### 11.6 Periodic procs

Legacy `periodic` procs tick at their interval (scaled by total Alacrity when `affected_by_cdr`), starting at a random point in the first interval.

---

## 12. Conditions

### 12.1 Extracted conditions (from the game data)

A condition set is a list of atomic conditions plus a logic tree (`and` / `or`). A condition id missing from the results counts as true. `negated` flips the result.

**Whose state is checked** (`actor`):

| Actor | Checked on |
|---|---|
| `caster` | the caster |
| `target` | the branch's target (after target overrides, so it can be the caster) |
| `trigger_target` / `trigger_caster` | the target / caster of the event that fired the proc |
| `actor_4` | the enemy the ability acts on (event enemy, else a non-caster target, else the caster's current target) **[data]** |
| not given | the caster (`is_creature_type`: the target) |

**What each type assumes:**

| Type | Assumption |
|---|---|
| `has_effect` / `not_has_effect` | An active effect matching the tags or ability spec; `count` is the summed stacks of all matches. `from_actor` is ignored (see section 18). |
| `has_effect_at_stack_charge_count` | Highest stack count of a matching effect, compared with the comparison (default `eq`). |
| `if_stack_charge` | The stacks in the current context equal `count`. |
| `has_ability` | The player has the ability or passive (talent, gear) in the loadout. Rank is always 1. |
| `has_ability_stack_charge` | Current charges of an ability (0 for non-charge abilities). |
| `has_specified_resource_amount` | Current resource. For **Heat** the data means resource *available*, so the engine compares `100 - heat` **[data]** (Vent Heat `lte 60` is castable from 40 heat). |
| `if_health` | Actor HP %. |
| `if_toughness` | Player toughness 1, dummy 5. |
| `random_chance` | `percent_chance / 100` **[log]** (Mortal Wound otherwise doubled Vital Shot / Shrap Bomb ticks against a PTS parse). |
| `is_casting` | The actor has a cast bar or channel (optionally of the named ability). |
| `is_in_combat` / `is_not_in_combat`, `is_in_cover` / `is_not_in_cover`, `is_stealthed` / `is_not_stealthed`, `is_mounted`, `is_dead` | The actor's flag. |
| `is_dual_wielding` / `is_not_dual_wielding`, `has_melee_weapon` | From the off-hand / main-hand weapon stats. |
| `if_weapon_mode` | Event weapon mode, else 2 when dual wielding, 1 with a main hand. |
| `is_player` / `is_not_player`, `is_class`, `is_creature_type`, `if_faction` | From the actor (player: creature type 4, faction empire by default). |
| `is_party_member`, `is_friend`, `is_target_caster` | True only for the caster. |
| `immune_by_resolve` | True on the dummy. |
| `passes_conditional` | The flashpoint/operation toggle. |
| `if_caster_positioning` | Always behind the target (true). |
| `if_primary_target`, `if_spell_hit`, `is_discipline`, `is_object`, `if_not_weapon_type`, `if_result` (no context) | True. |
| `is_companion`, `has_pending_revive`, `is_area` | False. |
| any other type | True. |

### 12.2 Rotation rules (written in the rotation file)

| Rule | Passes when |
|---|---|
| `target_hp_below_pct` | dummy HP ratio <= value (optionally also when a bypass buff is up) |
| `target_hp_above_pct` | dummy HP ratio > value |
| `caster_energy_above` / `caster_energy_below` | resource >= value / < value, in raw pool units (Heat is heat built up) |
| `caster_has_buff` / `caster_does_not_have_buff` | any / none of the named buffs active (by key, or by name among non-passive, non-lockout effects) |
| `target_has_debuff` / `target_doesnt_have_debuff` | same, on the dummy |
| `caster_buff_stacks` / `target_debuff_stacks` | stack count comparison (default `>=`), case and underscore insensitive |
| `ability_cooldown_under` / `ability_cooldown_above` | remaining cooldown < / > value (a charge ability counts only at 0 charges) |
| `proc_cooldown_above` | the proc is not active and its remaining lockout > value (section 11.4) |

---

## 13. Resources

| Pool | Classes | Start | Passive rate per second |
|---|---|---|---|
| Force | Assassin / Shadow, Sorcerer / Sage | full (100 by default) | 8 |
| Energy | Operative / Scoundrel, Sniper / Gunslinger | full (100) | 5 at >= 60, 3 at 20-59, 2 below 20 |
| Heat | Mercenary / Commando, Powertech / Vanguard | 0 heat | vents 5 below 40, 3 at 40-79, 2 at 80+ |
| Rage / Focus | Marauder / Sentinel, Juggernaut / Guardian | 0 (max 12) | none |

- **Resource tick:** every 1.0 s (first at a random point in the first second): `rate x (1 + regen % mods) + regen flat mods`, then `x (1 + Alacrity stat)`. The bracket is read from the value at the tick.
- **Heat is inverted:** paying a cost adds heat (refused if it would pass the max); a gain vents heat.
- **Max resource** follows stats 9 (tech energy max) and 10 (Force max); a full pool stays full when the max grows.
- **Costs** = `base x (1 + % mods) + flat mods` (stats 68 Force, 69 Energy, 70 Rage/Focus), never below 0. Cost buffs that are used up (e.g. Lightning Effusion charges) are consumed by their own triggers, not by the cost calculation.
- Pools behave as in combat during pre-combat: no out-of-combat regen or Rage decay **[choice]** (open, `TODO.md`).

---

## 14. Stats, Alacrity and time scaling

### 14.1 Sheet stats (`recalculate_stats`, frozen)

Recalculated whenever an effect with modifiers is applied or removed. Only modifiers **without** ability targets are used here; targeted ones are read at hit time.

- **Mastery** = `(base + flat) x (1 + %)`. **Power** = base + flat.
- **Bonus damage:** `0.20 x Mastery + 0.23 x Power`, times `(1 + generic bonus + type bonus)` for melee and ranged; Force and Tech add `0.23 x Force/Tech Power` before the multiplier.
- **Crit chance** = 5% + crit rating curve + Mastery curve + hidden 1%. **Surge** = 50% + crit rating curve + hidden 1%.
- **Alacrity** = Alacrity rating curve. **Accuracy** = 100% + accuracy rating curve + flat accuracy (incl. hidden 1%); off hand starts at 67%.
- Rating curves: `cap x (1 - (1 - 0.01 / cap) ^ (rating / level / divisor))`, cap and divisor from `combat_curves.json`.
- **Dummy armor** = 17,225 x (1 + armor mods on it).

### 14.2 Which Alacrity each timer uses

"Total Alacrity" = Alacrity stat + the unconditional instant-reduction bonuses (stat 274: High Velocity Gas Cylinder, Supercharged Velocity, Improved Vents).

| Timer | Alacrity used | Rounding |
|---|---|---|
| GCD | total (+ matching 274) | up to 0.1 s |
| Ability cooldown | total (+ matching 274) | up to 0.1 s |
| Charge recharge | stat only | up to 0.1 s |
| Cast time | stat only (cast-reduction stats apply separately) | 4 decimals |
| Channel duration | stat only (channel-reduction stats apply separately) | 4 decimals |
| Effect duration and its ticks | total; **stat only for effects applied while loading** **[log]** | none |
| Passive ticking effects | fixed at application, same load rule **[log]** | none |
| Proc rate limits (ICD) | total, read when the proc fires **[log]** | none |
| Resource regen | stat only (`x (1 + Alacrity)`) | none |
| Projectile flight, delayed branches | none | none |

---

## 15. Combat state, stealth, immunity, death

- **Entering combat:** the first aggressive cast (or an `enter_combat` action) sets the player in combat and dispatches `on_enter_combat`. The dummy is always in combat.
- **Stealth** breaks on an aggressive cast and on every non-periodic hit the player lands. Breaking it removes stealth-tagged effects (except combat-stealth windows such as Force Camouflage / Cloaking Screen) through the normal removal path, so their `on_pre_remove` runs (Stealth's 6 s cooldown, scaled by Alacrity) **[data]**.
- **Immunity:** an entity is immune to an effect when any of the effect's tags is in its immunities (from active effects' granted immunities plus permanent ones). Immune effects are not applied at all.
- **Death:** at 0 HP the dummy is marked dead once and `on_pre_death`, `on_death`, `on_kill` fire; the run then ends. Delayed branches and projectiles aimed at a dead target do nothing.

---

## 16. Pre-combat (pre-pull)

An optional opener phase from the rotation file, run on the simulation clock before the rotation starts.

- **Steps run strictly in order:** `ability`, `swap_tactical`, `wait` (seconds), `wait_until` (rotation-style rules, polled every 0.1 s, skipped with a warning after `max_wait`, default 60 s).
- An ability step waits for the GCD; casts and channels always run to their end (completion resumes the runner); with `wait_for_cooldown` it waits for a cooldown, charge or resource up to `max_wait`. A step that cannot be cast is skipped with a warning.
- **Pre-combat casts never touch the dummy:** their hits are dropped and effects aimed at the enemy are not applied. They still pay costs, start cooldowns and GCDs, and apply self-buffs. So the fight clock starts with the first rotation hit **[choice]**.
- **Tactical swaps** are instant, free and off-GCD, and only allowed out of combat (an aggressive pre-combat cast puts the player in combat, after which swaps are refused). The old tactical's registration, permanent effects, triggers and proc entries are removed without `on_pre_remove`; timed effects it already produced stay.
- **Pull gate** (`pull_conditions`): after the last step the runner holds until the rules pass, polling every 0.1 s; after `pull_max_wait` the run fails with `PullConditionsNotMetError`.
- The whole phase is capped at 300 s; then the rotation takes over at the next GCD.

---

## 17. Simplifications and toggles

| Toggle (run config) | Default | Effect |
|---|---|---|
| `enable_projectile_flight_time` | off | distance-based projectiles land after `distance / (speed x 10)` |
| `default_combat_distance` | 30 m | distance for the above |
| `in_flashpoint_operation` | on | value of `passes_conditional` |
| `enable_stem_matching` | off | `assassinate` also matches `assassinate_plus` in specs, modifiers and triggers (planned for removal) |
| `training_dummy_armor_debuff` | config | the 7 raid debuffs on the dummy |
| `gcd_stall` | 0 | fraction of GCDs lengthened by 0.1 s |
| `environment` | live | Live (level 80) or PTS (level 85) data and curves |

Other fixed assumptions: no movement or range checks (all range conditions are dropped as true), no cover except through actions, the player is never stunned or interrupted, the dummy never dodges beyond its flat 10%, and console "MISSED" lines are printed for misses.

---

## 18. Open questions and points that look inconsistent

From `TODO.md`, the CHANGELOG and this read-through. None of these were changed.

**Unconfirmed engine choices (from the record):**
- A refresh keeps the effect's running trigger ICDs (from a bug report; no log yet).
- `modify_stack_charge` with an `ability_spec` acts only on that ability's stack-charge effect (Convection / Lightning Strike, Cull, Wounding Shot); check with a Lightning Sorcerer / Virulence log.
- `remove_effect` with no owning effect does nothing (Volatile Substance and Blood Boiler explosions).
- A falling max-charge count caps current charges (untested in game).
- `from_actor` on conditions is ignored; only correct while the player is the only source of effects on the dummy.
- Out-of-combat resource behavior during pre-combat is not modeled.
- `ground` / `any` target rules still use the tag/damage heuristic.
- Charge recharge uses the Alacrity stat only (no log evidence).
- Off-hand weapon hits under the sim floor on some weapon-based abilities (Hemorrhaging Blast, Dirty Blast) and 1/3-coefficient hits about 0.08% low on PTS Dirty Fighting (frozen math; evidence only).
- Marksmanship rotation deadlock after a 0.37 s Penetrating Blasts (cause not investigated).

**Code observations, checked against the parsed data (2026-11-21).** Scanned all live and PTS parsed files; runtime counts from the shipped run configs (`data/run_config/*.json` at their own seeds and durations; `dirty_fighting_13gcd` skipped, its rotation file is missing). Nothing was changed.

1. **Channel-end branches run twice (real, damage-affecting; fixed 2026-11-21: the direct run at natural end was removed, and both interrupt paths now dispatch before `cleanup_channel_effects`; `tests/test_channel_end_once.py`).** An ability's own `on_channeling_ended` branches run directly at natural channel end, and the same branch is also subscribed on the event bus (the channel's effect 1 is applied, so its triggers are subscribed), so it hears the bus `on_channeling_ended` dispatched right after. All 27 channel-end branches in the data have this shape (effect 1 of a channel ability). Runtime: Madness Force Lightning, 5 completed channels, effect 6 (the end-of-channel hit) executed 10 times, 5 from each path. Doubled damage: **Madness Force Lightning and Balance Telekinetic Throw** (live and PTS). Doubled non-damage: the PTS `execute_ability` channels (Recuperate, Recharge and Reload, Meditation, Seethe, Channel Hatred, Introspection) and a harmless double refresh of the 8 s Lightning / Telekinetics buffs. No shipped config casts any of them. The opposite problem on interruption: Kolto Waves' branch requires `is_successful: false`, so it never runs at natural end, and on an interrupted channel (clip in `Ability.cast`, `ability_cancel`) `cleanup_channel_effects` removes and unsubscribes effect 1 before `on_channeling_ended` is dispatched, so that branch never runs at all (code read, not run).
2. **Else gates are ignored on the event bus (new, found by the scan; fixed 2026-11-21: `TriggerManager.dispatch` now applies the gate per owner and event, see section 11 step 6b; `tests/test_bus_else_gate.py`).** `run_if_none_ran` is honored when an effect runs its lifecycle branches, but `TriggerManager.dispatch` runs each bus branch on its own and never checks it. 5 bus branches carry an else gate: Combustible Gas Cylinder and Plasma Cell branch 4 (live and PTS) and PTS Integrated Toxins branch 3. With the Superheated Shot / Scorching Bolts talent, a Mag Shot / Rail Shot hit runs branch 3 and the gated branch 4 can also run (25%), applying the burn a second time at the same moment (a refresh). Integrated Toxins' two branches listen to different abilities, so the gate never matters there. No shipped loadout has these.
3. **`stack_multiplier` differs by path (not reached by current data).** On application, refresh and `on_pre_remove` the context multiplier is the effect's stacks even when it does not scale with stacks; on ticks and bus procs it is the stacks only for scaling effects. No stacking, non-scaling persistent effect has a damage action (or calls an instant damaging effect) in an `on_apply` / `on_refresh` / `on_pre_remove` branch, so the damage side never applies. `if_stack_charge` reads the multiplier first: the only bus/tick branches that use it on a non-scaling stacking effect are Force Cloak's Renewing Darkness / Restorative Shade (`on_effect_received`, counts 1-5), which heal and remove themselves; no DPS impact, but their stack-count branches always see 1.
4. **Listeners whose effect is gone still run in the same dispatch (reached, harmless so far).** The static scan finds 290 effects where an earlier branch of the same event removes or consumes the effect before a later one. Runtime over the shipped configs: only `hatred_14gcd` reaches it, 13 of 172 runs of Deathmark:2 branch 6 (Down Fall: Creeping Terror ticks take a second stack) run after branch 2 took the last stack; branch 6 only removes a stack from its own (gone) effect, so it does nothing. 0 cases in the other 5 configs. A later branch that deals damage or applies something would still act; no such case was seen at runtime.
5. **Percentage cooldown reductions use the base cooldown (reached by Carnage data, not by the shipped config).** 360 of the 370 percentage `modify_cooldown` actions are -100% resets, where base vs scaled makes no difference. The other 10: Berserk / Zen Ataru Frenzy buff (-80% Devastating Blast / its mirror, Carnage / Combat, live and PTS), Assassinate+ / Spinning Strike+ proc (-33% Reaping Strike / its mirror, Deception / Infiltration), and the Rest and Recharge legacy perk (-50%, -20%). The shipped `carnage_14gcd` loadout does not contain the Frenzy buff. Which value the game uses is unknown.
6. **`on_timer_expired` delays ignore Alacrity (reached by Carnage).** 106 such triggers; all but 5 sit on effects that ignore Alacrity, so the raw delay is exact for them. The 5 that scale: **Ataru Form_2** (Carnage and Combat, 0.6 s, the Ataru swing damage; in the shipped `carnage_14gcd`), Force Flagellation_2 and Force Lash_2 (1.0 s, Fury / Concentration and Rage / Focus), Renewal (heal). In the sim the Ataru swing lands 0.6 s after the proc although the effect itself ends at 0.6 / (1 + Alacrity); whether the game delays it by the scaled time is unknown (at 7% Alacrity the difference is about 0.04 s).
7. **An action whose own conditions fail stops the rest of the branch (not reached).** No extracted action carries `conditions` or `chance`, so this path is never taken.

---

## 19. Where older docs disagree with the code

`docs/architecture.md` and `docs/combat_math.md` predate several changes. Where they differ from this document, the code (and this document) is current:

| Older text | Current behavior |
|---|---|
| Off-hand ratio 0.30 (`combat_math.md`) | 0.25 (+ stat 127) since 2026-11-17 |
| GCD snapped **down** to 0.1 s (`combat_math.md`) | rounded **up** to 0.1 s |
| Six named buckets (`normal_percentage`, `channel_scaling`, ...) | six empirically verified buckets 1-6 (section 10.3) |
| Class buffs and companion bonus list, incl. +1% Alacrity and Endurance (`combat_math.md`) | four class buffs from blueprints; hidden +1% accuracy / crit chance / surge only |
| Refresh adds `initial_stacks` (`architecture.md`) | refresh adds one stack, or resets countdown pools (section 7.2) |
| First `ResourceTick` at t = 1.0 s (`architecture.md`) | random in [0, 1) s, then every 1.0 s |
| Next decision at `max(now, next_gcd)` (`architecture.md`) | also earlier by an off-GCD lead time; cast and channel ends hand off too |
| Effect keys by name (`architecture.md`) | keys are `ability fqn:effect number` |
| Channel clipping by a new cast (`architecture.md`) | the rotation never clips; casting is refused while busy |
