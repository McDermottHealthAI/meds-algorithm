"""Read the one normative specification shipped with the installed core version."""

import argparse
from importlib.resources import files


def specification() -> str:
    return files("meds_model_core").joinpath("CONTRACT.md").read_text(encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    print(specification())


if __name__ == "__main__":
    main()
