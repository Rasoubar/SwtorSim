from src.swtorsim.engine import Simulation
from src.swtorsim.entities import Player, Target
from src.swtorsim.events import ResourceTick, PlayerReady
from src.swtorsim.config_load import load_abilities_from_json, load_passives_from_json, load_permanent_buffs_from_json
from src.swtorsim.rotation import FixedRotation
from src.swtorsim.requirements import validate_all

def run_test():

    sim = Simulation()
    player = Player("Assassin")
    target = Target("Target Dummy", hp=2000000)

    p_stats = player.base_stats
    p_stats["Mastery"] = 16834
    p_stats["Power"] = 14503
    p_stats["Force Power"] = 9332
    p_stats["Critical Rating"] = 3758
    p_stats["Alacrity Rating"] = 2218
    p_stats["Main_hand_min"] = 2513
    p_stats["Main_hand_max"] = 3769
    p_stats["Standard_health"] = 19335
    player.recalculate_stats()

    player.abilities_db = load_abilities_from_json("data/Assassin/Hatred/Abilities/Abilities.json")
    player.procs = load_passives_from_json("data/Assassin/Hatred/Procs/BaseAssassinProcs+MasteryPowerRelics.json")
    player.effects = load_permanent_buffs_from_json("data/Assassin/Hatred/Buffs/PermanentBuffs.json")

    player.recalculate_stats()
    abilities = {
        key.lower().replace(" ", "_"): val
        for key, val in player.abilities_db.items()
    }
    for effect_id, effect in player.effects.items(): #make better later
        if effect.id == 64:
            if effect.required_tags is not None:
                for ability in abilities.values():
                    if not any(tag in ability.tags for tag in effect.required_tags):
                        continue
                    ability.cooldown -= effect.value

    rotation = [abilities['eradicate'],abilities['creeping_terror'],abilities['discharge'],abilities['leeching_strike'],abilities['eradicate'],abilities['recklessness'],abilities['death_field'],
            abilities['leeching_strike'],abilities['assassinate'],abilities['eradicate'],abilities['thrash'],abilities['thrash'],abilities['saber_strike'],abilities['eradicate'],abilities['creeping_terror'],abilities['discharge'],abilities['leeching_strike'],abilities['eradicate'],abilities['recklessness'],abilities['death_field'],
            abilities['leeching_strike'],abilities['assassinate'],abilities['eradicate'],abilities['thrash'],abilities['saber_strike'],abilities['saber_strike']]
    player.rotation = FixedRotation(rotation)

    sim.schedule_absolute(0.0, PlayerReady(player, target))
    sim.schedule_absolute(1.0, ResourceTick(player))
    sim.run_timed(duration=90.0)


if __name__ == "__main__":
    run_test()