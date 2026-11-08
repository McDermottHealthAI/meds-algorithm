"""Render canonical core documents and immutable template-owned guides in one site."""

import hashlib
import json
import re
from pathlib import Path
from urllib.request import urlopen

from jinja2 import Environment, StrictUndefined


class _TemplateGuides:
    """Read hash-verified guide sources from a pinned public template commit."""

    def __init__(self, root: Path):
        self.root = root
        self.manifest = json.loads((root / "docs/template-source.json").read_text(encoding="utf-8"))
        if not re.fullmatch(r"[0-9a-f]{40}", self.manifest["revision"]):
            raise ValueError("Template documentation source must pin a full commit SHA")

    def read(self, name: str) -> str:
        digest = self.manifest["files"][name]
        revision = self.manifest["revision"]
        cache = self.root / ".cache/template-docs" / revision / name
        if not cache.resolve().is_relative_to((self.root / ".cache/template-docs").resolve()):
            raise ValueError("Guide source must stay inside the documentation cache")
        if cache.is_file():
            content = cache.read_bytes()
        else:
            url = f"https://raw.githubusercontent.com/McDermottHealthAI/MEDS_algorithm_template/{revision}/{name}"
            with urlopen(url, timeout=30) as response:
                content = response.read()
        if hashlib.sha256(content).hexdigest() != digest:
            raise ValueError(f"Template guide checksum mismatch: {name}")
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_bytes(content)
        return content.decode("utf-8")

    def provenance(self) -> str:
        revision = self.manifest["revision"]
        return (
            '!!! note "Template source version"\n'
            f"    Template-owned guides below come from [revision `{revision[:12]}`]"
            f"(https://github.com/McDermottHealthAI/MEDS_algorithm_template/tree/{revision}). "
            "Use your generated repository's guides for its exact version.\n\n"
        )


def on_page_markdown(markdown, page, **kwargs):
    root = Path(__file__).resolve().parents[1]
    source = page.file.src_uri
    if source in {"publishing-algorithms.md", "releasing.md", "testing.md"}:
        guides = _TemplateGuides(root)
        if source == "publishing-algorithms.md":
            guide = (
                Environment(undefined=StrictUndefined)
                .from_string(guides.read("template/RELEASING.md.jinja"))
                .render(
                    algorithm_name="My Algorithm", algorithm_slug="my_algorithm", package_name="my-algorithm"
                )
            )
            return markdown.replace("<!-- algorithm-release-guide -->", guides.provenance() + guide)
        if source == "releasing.md":
            return markdown.replace(
                "<!-- template-release-guide -->", guides.provenance() + guides.read("RELEASING.md")
            )
        return markdown.replace(
            "<!-- template-test-guide -->", guides.provenance() + guides.read("TESTING.md")
        ).replace("<!-- algorithm-test-guide -->", guides.read("template/docs/TESTING.md"))
    if source == "running.md":
        return markdown.replace(
            "<!-- orchestration-guide -->",
            (root / "src/meds_algorithm/ORCHESTRATION.md").read_text(encoding="utf-8"),
        )
    if source == "reference/spec.md":
        return markdown + "\n\n" + (root / "src/meds_algorithm/CONTRACT.md").read_text(encoding="utf-8")
    if source == "reference/architecture.md":
        return (
            (root / "ARCHITECTURE.md")
            .read_text(encoding="utf-8")
            .replace("(src/meds_algorithm/CONTRACT.md)", "(spec.md)")
        )
    if source == "reference/tests.md":
        return (root / "src/meds_algorithm/TESTING.md").read_text(encoding="utf-8")
    if source == "prompt-builder.md":
        document = (root / "docs/implementation-prompt.md").read_text(encoding="utf-8")
        prompt = re.search(r"```text\n(.*?)\n```", document, re.DOTALL).group(1)
        # JSON lives inside an HTML script element: source text must not close it.
        payload = json.dumps(prompt).replace("<", "\\u003c")
        return markdown.replace(
            "<!-- prompt-template -->",
            f'<script type="application/json" data-prompt-template>{payload}</script>',
        )
    return markdown
