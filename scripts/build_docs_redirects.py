"""Build the retired GitHub Pages site's redirects using only the standard library."""

import json
from pathlib import Path


def main():
    root = Path(__file__).resolve().parents[1]
    output = root / "site-redirects"
    source = (root / "redirects/index.html").read_text(encoding="utf-8")
    routes = json.loads((root / "redirects/paths.json").read_text(encoding="utf-8"))
    files = ["index.html", "404.html"]
    for route in routes:
        files.extend([f"{route}/index.html", f"{route}.html"])
    for name in files:
        destination = output / name
        if not destination.resolve().is_relative_to(output.resolve()):
            raise ValueError("Redirect route must stay inside the output directory")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(source, encoding="utf-8")
    (output / ".nojekyll").touch()


if __name__ == "__main__":
    main()
