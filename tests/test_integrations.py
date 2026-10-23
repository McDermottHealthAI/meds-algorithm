from types import SimpleNamespace

import pytest

from meds_model_core.conformance import meds_dev
from meds_model_core.integrations.meds_dev import register


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
    model = tmp_path / "model"
    (model / "models/probe").mkdir(parents=True)
    (model / "models/probe/model.yaml").write_text("commands: {}")
    (model / "requirements.txt").write_text("-e .\n")
    dev = tmp_path / "dev"
    (dev / "src/MEDS_DEV/models").mkdir(parents=True)
    with pytest.raises(ValueError):
        register(model, dev, "../escape", "probe")
    target = register(model, dev, "family", "probe")
    assert target.name == "family__probe"
    assert str(model) in (target / "requirements.txt").read_text()


def test_registration_writes_an_unquoted_editable_file_url(tmp_path):
    # uv treats quotes in a requirements file literally; a percent-encoded file URL survives spaces.
    model = tmp_path / "my model"
    (model / "models/supervised").mkdir(parents=True)
    (model / "models/supervised/model.yaml").write_text("commands: {}")
    (model / "requirements.txt").write_text("numpy\n-e .\n")
    dev = tmp_path / "dev"
    (dev / "src/MEDS_DEV/models").mkdir(parents=True)
    target = register(model, dev, "family", "supervised")
    lines = (target / "requirements.txt").read_text().splitlines()
    assert lines == ["numpy", f"-e {model.resolve().as_uri()}"]
    assert "%20" in lines[1] and '"' not in lines[1]
