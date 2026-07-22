class ActiveDot:
    __slots__ = ['name', 'interval', 'ticks_remaining', 'action_data']

    def __init__(self, name, interval, ticks_remaining, action_data: dict):
        self.name = name
        self.interval = interval
        self.ticks_remaining = ticks_remaining
        self.action_data = action_data


class ActiveChannel:
    def __init__(self, name, action_data, total_ticks, tick_interval, tick_cost):
        self.name = name
        self.action_data = action_data
        self.remaining_ticks = total_ticks
        self.tick_interval = tick_interval
        self.tick_cost = tick_cost


class ActiveEffect:
    __slots__ = [
        'id', 'effect_name', 'stat_name', 'value', 'expires_at', 'source_ability', 'required_tags', 'charges', 'consumable_charges',
        'max_charges', 'proc_data', 'last_proc_at','target_hp_threshold',"stack_values"]

    def __init__(self, id_num, effect_name, stat_name, value, expires_at, source_ability,
                 required_tags=None, charges=None, consumable_charges=None, max_charges = None, target_hp_threshold = None,
                 stack_values = None):
        self.id = id_num
        self.effect_name = effect_name
        self.stat_name = stat_name
        self.value = value
        self.expires_at = expires_at
        self.source_ability = source_ability
        self.required_tags = required_tags
        self.charges = charges
        self.consumable_charges = consumable_charges
        self.max_charges = max_charges
        self.target_hp_threshold = target_hp_threshold
        self.stack_values = stack_values

    def consume_charge(self, count: int = 1) -> bool:
        """ Consumes N charges/consumable charges from the effect. Returns bool on if it has reached 0 charges."""
        if self.consumable_charges is None:
            return False
        self.consumable_charges = max(0, self.consumable_charges - count)
        return self.consumable_charges == 0

    @classmethod
    def from_action(cls, action: dict, stat_name: str, effect_key: str,
                    charges: int, expires_at: float, source_name: str):
        """Constructs an Effect from an action."""

        return cls(
            id_num=action.get("id"),
            effect_name=effect_key,
            stat_name=stat_name,
            value=action["value"],
            expires_at=expires_at,
            source_ability=source_name,
            required_tags=cls._parse_tags(action.get("required_tags")),
            charges=charges,
            consumable_charges=action.get("consumable_charges"),
            max_charges=action.get("max_charges"),
            target_hp_threshold=action.get("target_hp_threshold"),
            stack_values=action.get("stack_values")
        )

    @staticmethod
    def _parse_tags(raw_tags) -> frozenset | None:
        if not raw_tags:
            return None
        return frozenset(raw_tags if isinstance(raw_tags, (list, tuple, set)) else [raw_tags])


class ProcData:
    __slots__ = ['name','actions','chance','icd','next_possible_proc','trigger','required_tags','affected_by_cdr',
                 'conditions']

    def __init__(self, name: str, trigger: str, actions: list,
                 required_tags: list , chance: float = 1.0, icd: float = 0.0, affected_by_cdr = False, conditions: dict = None):
        self.name = name
        self.trigger = trigger
        self.required_tags = frozenset(required_tags) if required_tags else frozenset()
        self.chance = chance
        self.icd = icd
        self.actions = actions
        self.next_possible_proc = 0.0
        self.affected_by_cdr = affected_by_cdr
        self.conditions = conditions if conditions is not None else {} #I went with this to not make conditions mandatory in the JSON file. No idea what it implies for performance
