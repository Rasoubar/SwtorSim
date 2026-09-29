import argparse
import random

from src.swtorsim.cli import collect_run_config_interactive
from src.swtorsim.config_load import load_from_run_config
from src.swtorsim.run_config import load_run_config
from src.swtorsim.tester import Tester


def run(config):
    random.seed(config.seed)
    inputs = load_from_run_config(config)

    tester = Tester(
        rotation_config=inputs.rotation_config,
        stats_config=inputs.stats_config,
        loadout_blueprints=inputs.loadout_blueprints,
        duration=config.duration,
        dummy_hp=config.dummy_hp,
        debuff_module=inputs.debuff_module,
    )

    if config.mode == "TEST":
        tester.run_test()
    elif config.mode == "BATCH":
        tester.run_monte_carlo(iterations=config.iterations)


def main():
    parser = argparse.ArgumentParser(
        description="SWTOR combat simulator. Omit the config path to use the interactive CLI."
    )
    parser.add_argument(
        "run_config",
        nargs="?",
        help="Path to a run_config.json with the loadout already selected.",
    )
    args = parser.parse_args()
    config = (
        load_run_config(args.run_config)
        if args.run_config
        else collect_run_config_interactive()
    )
    run(config)


if __name__ == "__main__":
    main()
