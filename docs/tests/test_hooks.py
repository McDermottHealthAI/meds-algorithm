"""Documentation sources remain canonical, pinned and inert in browser HTML."""

import hashlib
import importlib.util
import io
import json
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]


def load_hooks():
    spec = importlib.util.spec_from_file_location("docs_hooks", ROOT / "docs/hooks.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def page(name):
    return SimpleNamespace(file=SimpleNamespace(src_uri=name))


def test_prompt_builder_embeds_the_canonical_prompt():
    hooks = load_hooks()
    result = hooks.on_page_markdown((ROOT / "docs/prompt-builder.md").read_text(), page("prompt-builder.md"))
    payload = re.search(r"data-prompt-template>(.*?)</script>", result, re.DOTALL).group(1)
    document = (ROOT / "docs/implementation-prompt.md").read_text()
    expected = re.search(r"```text\n(.*?)\n```", document, re.DOTALL).group(1)
    assert json.loads(payload) == expected
    assert "<!-- prompt-template -->" not in result


def test_algorithm_release_guide_renders_template_source(monkeypatch):
    hooks = load_hooks()
    monkeypatch.setattr(hooks._TemplateGuides, "read", lambda self, name: "Release {{ package_name }}")
    result = hooks.on_page_markdown("<!-- algorithm-release-guide -->", page("publishing-algorithms.md"))
    assert "Release my-algorithm" in result
    assert "Template source version" in result
    assert "{{" not in result


def test_prompt_source_cannot_close_its_json_script_element(tmp_path, monkeypatch):
    hooks = load_hooks()
    monkeypatch.setattr(hooks, "__file__", str(tmp_path / "docs/hooks.py"))
    prompt = '</script><script>alert("source text")</script>'
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs/implementation-prompt.md").write_text("```text\n" + prompt + "\n```\n")
    result = hooks.on_page_markdown("<!-- prompt-template -->", page("prompt-builder.md"))
    assert result.count("</script>") == 1
    assert json.loads(result.split("data-prompt-template>", 1)[1].split("</script>", 1)[0]) == prompt


@pytest.mark.parametrize(
    ("name", "source"),
    [
        ("reference/spec.md", "src/meds_algorithm/CONTRACT.md"),
        ("reference/architecture.md", "ARCHITECTURE.md"),
        ("reference/tests.md", "src/meds_algorithm/TESTING.md"),
        ("running.md", "src/meds_algorithm/ORCHESTRATION.md"),
    ],
)
def test_core_references_use_this_checkout(name, source):
    hooks = load_hooks()
    expected = (
        (ROOT / source).read_text(encoding="utf-8").replace("(src/meds_algorithm/CONTRACT.md)", "(spec.md)")
    )
    result = hooks.on_page_markdown("<!-- orchestration-guide -->", page(name))
    assert expected in result


def source_manifest(root, content=b"guide", revision="a" * 40):
    (root / "docs").mkdir()
    (root / "docs/template-source.json").write_text(
        json.dumps(
            {
                "revision": revision,
                "files": {"TESTING.md": hashlib.sha256(content).hexdigest()},
            }
        )
    )


def test_template_guides_fetch_immutable_source_and_reuse_verified_cache(tmp_path, monkeypatch):
    hooks = load_hooks()
    source_manifest(tmp_path)
    requests = []

    def fetch(url, timeout):
        requests.append((url, timeout))
        return io.BytesIO(b"guide")

    monkeypatch.setattr(hooks, "urlopen", fetch)
    guides = hooks._TemplateGuides(tmp_path)
    assert guides.read("TESTING.md") == "guide"
    assert guides.read("TESTING.md") == "guide"
    assert len(requests) == 1
    assert "/" + "a" * 40 + "/TESTING.md" in requests[0][0]
    assert requests[0][1] == 30


@pytest.mark.parametrize("cached", [False, True])
def test_template_guide_corruption_fails_closed(tmp_path, monkeypatch, cached):
    hooks = load_hooks()
    source_manifest(tmp_path)
    if cached:
        cache = tmp_path / ".cache/template-docs" / ("a" * 40) / "TESTING.md"
        cache.parent.mkdir(parents=True)
        cache.write_bytes(b"changed")
    monkeypatch.setattr(hooks, "urlopen", lambda *args, **kwargs: io.BytesIO(b"changed"))
    with pytest.raises(ValueError, match="checksum mismatch"):
        hooks._TemplateGuides(tmp_path).read("TESTING.md")


def test_template_source_requires_immutable_revision(tmp_path):
    source_manifest(tmp_path, revision="main")
    with pytest.raises(ValueError, match="full commit SHA"):
        load_hooks()._TemplateGuides(tmp_path)


def test_template_download_failure_does_not_silently_change_source(tmp_path, monkeypatch):
    hooks = load_hooks()
    source_manifest(tmp_path)

    def unavailable(*args, **kwargs):
        raise OSError("Source unavailable")

    monkeypatch.setattr(hooks, "urlopen", unavailable)
    with pytest.raises(OSError, match="Source unavailable"):
        hooks._TemplateGuides(tmp_path).read("TESTING.md")
