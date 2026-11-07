"""SwtorSim Unified Simulation Runner (alias to main.py).

Provides backward-compatible entry points for running simulations.
Directs all executions to main.py.
"""

from main import (
    COMMON_HP_PRESETS,
    CONFIG_DIR,
    discover_configs,
    main,
    parse_hp_value,
    prompt_config_interactive,
    prompt_hp_interactive,
    prompt_mode_interactive,
    resolve_config_path,
    run,
)

if __name__ == "__main__":
    main()
