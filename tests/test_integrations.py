from types import SimpleNamespace

import pytest

from meds_algorithm.conformance import meds_dev
from meds_algorithm.integrations.meds_dev import register


@pytest.mark.parametrize(
    "expression", ["", "not real_data", "not meds_dev", "slow", "meds_dev or not meds_dev"]
)
def test_directory_does_not_opt_in_to_provisioning(tmp_path, monkeypatch, expression):
    monkeypatch.setenv("MEDS_DEV_DIR", str(tmp_path))
    monkeypatch.setattr(meds_dev, "run", lambda *args, **kwargs: pytest.fail("must not provision"))
    request = SimpleNamespace(config=SimpleNamespace(getoption=lambda *args, **kwargs: expression))
    with pytest.raises(pytest.skip.Exception, match="explicitly select"):
        meds_dev.provision_meds_dev(request, None)


def test_registration_is_per_profile_and_rejects_escape(tmp_path):
    algorithm = tmp_path / "algorithm"
    (algorithm / "algorithms/probe").mkdir(parents=True)
    (algorithm / "algorithms/probe/model.yaml").write_text("commands: {}")
    (algorithm / "requirements.txt").write_text("-e .\n")
    dev = tmp_path / "dev"
    (dev / "src/MEDS_DEV/models").mkdir(parents=True)
    with pytest.raises(ValueError):
        register(algorithm, dev, "../escape", "probe")
    target = register(algorithm, dev, "family", "probe")
    assert target.name == "family__probe"
    assert str(algorithm) in (target / "requirements.txt").read_text()


def test_registration_writes_an_unquoted_editable_file_url(tmp_path):
    # uv treats quotes in a requirements file literally; a percent-encoded file URL survives spaces.
    algorithm = tmp_path / "my algorithm"
    (algorithm / "algorithms/supervised").mkdir(parents=True)
    (algorithm / "algorithms/supervised/model.yaml").write_text("commands: {}")
    (algorithm / "requirements.txt").write_text("numpy\n-e .\n")
    dev = tmp_path / "dev"
    (dev / "src/MEDS_DEV/models").mkdir(parents=True)
    target = register(algorithm, dev, "family", "supervised")
    lines = (target / "requirements.txt").read_text().splitlines()
    assert lines == ["numpy", f"-e {algorithm.resolve().as_uri()}"]
    assert "%20" in lines[1] and '"' not in lines[1]
