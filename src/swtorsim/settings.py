"""Global simulation settings and engine feature toggles."""

ENABLE_STEM_MATCHING: bool = False
ENABLE_PROJECTILE_FLIGHT_TIME: bool = False
DEFAULT_COMBAT_DISTANCE: float = 30.0
IN_FLASHPOINT_OPERATION: bool = True


def set_stem_matching(enabled: bool) -> None:
    """Configures whether ability stem matching (e.g. matching 'assassinate' to 'assassinate_plus') is active."""
    global ENABLE_STEM_MATCHING
    ENABLE_STEM_MATCHING = bool(enabled)


def is_stem_matching_enabled() -> bool:
    """Returns True if stem matching is currently enabled."""
    return ENABLE_STEM_MATCHING


def set_projectile_flight_time(enabled: bool) -> None:
    """Configures whether projectile travel flight time delay is enabled."""
    global ENABLE_PROJECTILE_FLIGHT_TIME
    ENABLE_PROJECTILE_FLIGHT_TIME = bool(enabled)


def is_projectile_flight_time_enabled() -> bool:
    """Returns True if projectile travel flight time delay is enabled."""
    return ENABLE_PROJECTILE_FLIGHT_TIME


def set_default_combat_distance(distance: float) -> None:
    """Sets default combat distance in meters between caster and target."""
    global DEFAULT_COMBAT_DISTANCE
    DEFAULT_COMBAT_DISTANCE = float(distance)


def get_default_combat_distance() -> float:
    """Returns default combat distance in meters."""
    return DEFAULT_COMBAT_DISTANCE


def set_in_flashpoint_operation(enabled: bool) -> None:
    """Configures whether the simulation environment is an Operation/Flashpoint encounter."""
    global IN_FLASHPOINT_OPERATION
    IN_FLASHPOINT_OPERATION = bool(enabled)


def is_in_flashpoint_operation() -> bool:
    """Returns True if the current simulation environment is an Operation/Flashpoint encounter."""
    return IN_FLASHPOINT_OPERATION
