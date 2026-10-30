"""Read the one normative specification shipped with the installed core version."""

import argparse
from importlib.resources import files


def specification() -> str:
    return files("meds_algorithm").joinpath("CONTRACT.md").read_text(encoding="utf-8")


def architecture() -> str:
    """Read the bundled API/UML guide maintained as ARCHITECTURE.md in the repository."""
    return files("meds_algorithm").joinpath("ARCHITECTURE.md").read_text(encoding="utf-8")


def validation_guide() -> str:
    """Read the bundled test catalogue and validation guide."""
    return files("meds_algorithm").joinpath("TESTING.md").read_text(encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    print(specification())


if __name__ == "__main__":
    main()
