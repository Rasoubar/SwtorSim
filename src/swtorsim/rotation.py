class Rotation:
    def __init__(self, name, steps_config, loop: bool = True):
        self.name = name
        self.sequence = []
        self.current_step = 0
        self.loop = loop

        self.build_steps(steps_config)

    def build_steps(self, steps_config):
        for step_data in steps_config:
            if step_data["type"] == "fixed":
                self.sequence.append(FixedAbilityStep(step_data["ability_id"]))
            elif step_data["type"] == "priority_block":
                self.sequence.append(PriorityBlockStep(step_data["name"], step_data["pool"]))

    def evaluate(self, player, target, sim) -> bool:
        if self.current_step >= len(self.sequence):
            return False
        step = self.sequence[self.current_step]
        if step.evaluate(player, target, sim):
            self.current_step += 1
            if self.loop and self.current_step >= len(self.sequence):
                self.current_step = 0
            return True

        return False


class FixedAbilityStep:
    def __init__(self, ability_id):
        self.ability_id = ability_id

    def evaluate(self, player, target, sim) -> bool:
        ability = sim.ability_db.get(self.ability_id)
        return ability.cast(player, target, sim)

class PriorityBlockStep:
    def __init__(self, name, pool):
        self.name = name
        self.pool = pool    #all abilities + rules, in order of prioww

    def evaluate(self, player, target, sim) -> bool:
        for item in self.pool:
            ability_id = item["ability_id"]
            ability = sim.ability_db.get(ability_id)
            if ability is None:
                continue
            rules_passed = True
            for rule in item.get("rules", []):
                if not self.evaluate_rule(rule, player, target, sim):
                    rules_passed = False
                    break
            if not rules_passed:
                continue
            if not ability.can_cast(player, target, sim):
                continue
            return ability.cast(player, target, sim)

        return False

    def evaluate_rule(self, rule, player, target, sim) -> bool:
        rule_type = rule["type"]
        if rule_type == "dot_absent":
            return rule["name"] not in target.dots
        if rule_type == "buff_stacks":
            buff = player.buffs.get(rule["name"], 0) #to add when needed
        if rule_type == "energy_level":
            current_energy = player.resource.current_value
            operator = rule["operator"]
            threshold = rule["value"]

            return self.compare(current_energy, operator, threshold)


        return False

    def compare(self, val1, operator, val2) -> bool:
        if operator == "==": return val1 == val2
        if operator == ">=": return val1 >= val2
        if operator == "<=": return val1 <= val2
        if operator == ">":  return val1 > val2
        if operator == "<":  return val1 < val2
        return False