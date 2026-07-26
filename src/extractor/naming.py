from __future__ import annotations

import re

# The game uses "stack" and "charge" interchangeably for the same mechanic, so
# every already snake_cased name is folded onto a single "stack_charge" token.
_STACK_CHARGE_TOKENS: frozenset[str] = frozenset({"charge", "charges", "stack", "stacks"})

# effStackLimit / effParam_MaxStackCount describe how many occurrences count, not
# a maximum stack/charge size, so it gets its own dedicated name (matches the
# jedipedia page).
_MAX_STACK_COUNT = "max_stack_count"
_NR_OCCURANCES = "nr_occurances"

_DUPLICATE_STACK_CHARGE = re.compile(r"stack_charge(?:_stack_charge)+")


def normalize_stack_charge(name: str) -> str:
    """Fold "stack"/"charge" tokens in a snake_cased name onto "stack_charge".

    Whole tokens are replaced so composites like "recharge" (a single token) are
    left untouched. ``max_stack_count`` is special-cased to ``nr_occurances``.
    """
    if name == _MAX_STACK_COUNT:
        return _NR_OCCURANCES

    tokens = name.split("_")
    replaced = [
        "stack_charge" if token in _STACK_CHARGE_TOKENS else token for token in tokens
    ]
    result = "_".join(replaced)
    return _DUPLICATE_STACK_CHARGE.sub("stack_charge", result)
