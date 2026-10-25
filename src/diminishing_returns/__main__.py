"""Command line entry for the diminishing-returns run."""

import argparse

from src.diminishing_returns.config import load_dr_config

DEFAULT_CONFIG = "data/run_config/dr_config.json"


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(
        description="Sweep stats through the SWTOR sim and plot diminishing returns."
    )
    parser.add_argument(
        "dr_config",
        nargs="?",
        default=DEFAULT_CONFIG,
        help=f"Path to dr_config.json (default: {DEFAULT_CONFIG}).",
    )
    parser.add_argument(
        "--samples",
        type=int,
        default=None,
        help="Override samples_per_variant for this run.",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Save each spec's fight inputs and DPS to figures/dr/raw_<spec>.npz.",
    )
    parser.add_argument(
        "--refit",
        metavar="RAW",
        help="Refit the plots from a raw .npz saved with --debug, without simulating.",
    )
    args = parser.parse_args(argv)
    if args.samples is not None and args.samples <= 0:
        parser.error("--samples must be a positive integer.")

    dr = load_dr_config(args.dr_config)
    if args.samples is not None:
        dr.samples_per_variant = args.samples

    if args.refit:
        from src.diminishing_returns.runner import refit_raw

        results = [refit_raw(args.refit, dr)]
    else:
        from src.diminishing_returns.runner import run_specs

        results = run_specs(dr, debug=args.debug)

    from src.diminishing_returns.plots import write_plots

    for result in results:
        for path in write_plots(result):
            print(f"Saved {path}")


if __name__ == "__main__":
    main()
