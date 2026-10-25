"""Global simulation settings and engine feature toggles."""

ENABLE_STEM_MATCHING: bool = False


def set_stem_matching(enabled: bool) -> None:
    """Configures whether ability stem matching (e.g. matching 'assassinate' to 'assassinate_plus') is active."""
    global ENABLE_STEM_MATCHING
    ENABLE_STEM_MATCHING = bool(enabled)


def is_stem_matching_enabled() -> bool:
    """Returns True if stem matching is currently enabled."""
    return ENABLE_STEM_MATCHING
