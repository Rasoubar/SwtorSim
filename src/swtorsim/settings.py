"""Process-local runtime flags shared by ability, modifier, and trigger matching."""

_stem_matching_enabled = False


def set_stem_matching(enabled: bool) -> None:
    """Turns PTS ``_plus`` ability matching on or off for this process."""
    global _stem_matching_enabled
    _stem_matching_enabled = bool(enabled)


def is_stem_matching_enabled() -> bool:
    """Returns whether ``_plus`` ability stems should match their base abilities."""
    return _stem_matching_enabled
