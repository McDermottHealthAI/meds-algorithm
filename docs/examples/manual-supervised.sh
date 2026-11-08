#!/usr/bin/env bash
# --8<-- [start:setup]
# A complete local tutorial. Prerequisites: Bash, Git, uv, and network access for dependencies.
set -euo pipefail
command -v git >/dev/null
command -v uv >/dev/null

# Use a NEW directory. Nothing is deleted or overwritten outside this tutorial.
WORKSPACE="${1:-$PWD/manual-meds-example}"
if [[ -e "$WORKSPACE" ]]; then
  echo "Choose a new directory: $WORKSPACE already exists" >&2
  exit 1
fi
mkdir -p "$WORKSPACE"
cd "$WORKSPACE"
WORKSPACE="$PWD"

# 1. Render a named, single-profile repository from a reproducible template revision.
cat > answers.yaml <<'YAML'
algorithm_name: Manual baseline
algorithm_slug: manual_baseline
algorithm_class: ManualBaseline
algorithm_description: Synthetic tutorial estimating training-label prevalence.
profiles: [supervised]
uses_predicates: true
implementation_source: This tutorial; not a reproduction of a published clinical algorithm.
YAML
uvx --from 'copier==9.17.1' copier copy --defaults --trust \
  --vcs-ref=55ddd290d20a39dd19954321580c616cc11a74ae \
  --data-file answers.yaml \
  https://github.com/McDermottHealthAI/MEDS_algorithm_template.git manual-baseline
cd manual-baseline
# --8<-- [end:setup]

# --8<-- [start:environment]
# 2. Create the Python environment and install the generated package and test dependencies.
uv python install 3.11
uv sync --python 3.11 --extra test
uv run manual-baseline profiles
uv run manual-baseline commands --profile supervised
uv run meds-algorithm-spec > installed-contract.txt
# --8<-- [end:environment]

# 3. Implement the generated stubs manually. No agent or MEDS-DEV runner is involved.
# --8<-- [start:configuration]
cat > src/manual_baseline/config.py <<'PY'
from dataclasses import dataclass
from meds_algorithm import AlgorithmConfig


@dataclass(frozen=True)
class ManualBaselineConfig(AlgorithmConfig):
    smoothing: float = 1.0

    def validate(self):
        if self.smoothing <= 0:
            raise ValueError("smoothing must be positive")
PY
# --8<-- [end:configuration]

# --8<-- [start:algorithm]
cat > src/manual_baseline/manual_baseline.py <<'PY'
import json
from pathlib import Path

import polars as pl
import yaml

from meds_algorithm import AlgorithmRepository, PayloadMetadata, SupervisedAlgorithm
from meds_algorithm.requests import (
    PreprocessDataRequest, TrainSupervisedRequest, PredictSupervisedRequest,
)
from .config import ManualBaselineConfig


class ManualBaseline(SupervisedAlgorithm):
    name = "manual_baseline"
    config_type = ManualBaselineConfig

    def preprocess_data(self, request: PreprocessDataRequest) -> PayloadMetadata:
        events = pl.read_parquet(str(request.meds_dir / "data" / "*.parquet"))
        events.write_parquet(request.output.directory / "events.parquet")
        # Core supplies the composed feature predicates; keep its reserved file unchanged.
        predicates = yaml.safe_load(request.predicates_file.read_text())["predicates"]
        (request.output.directory / "summary.json").write_text(json.dumps({
            "events": events.height, "predicate_names": sorted(predicates),
        }))
        return PayloadMetadata("tutorial-events")

    def train_supervised(self, request: TrainSupervisedRequest) -> PayloadMetadata:
        outcomes = request.labels.read("train")["boolean_value"]
        if len(outcomes) == 0:
            raise ValueError("Training labels must not be empty")
        alpha = self.config.smoothing
        probability = (outcomes.sum() + alpha) / (len(outcomes) + 2 * alpha)
        (request.output.directory / "probability.json").write_text(json.dumps(probability))
        return PayloadMetadata("tutorial-prevalence")

    def predict_supervised(self, request: PredictSupervisedRequest) -> PayloadMetadata:
        probability = json.loads((request.fitted_algorithm.directory / "probability.json").read_text())
        request.index.read().with_columns(
            pl.lit(probability).alias("predicted_boolean_probability")
        ).write_parquet(request.output.directory / "predictions.parquet")
        return PayloadMetadata("tutorial-predictions")


IMPLEMENTATIONS = {"supervised": ManualBaseline}
PROFILES = tuple(IMPLEMENTATIONS)
# Keep the completion gate: this tutorial does not implement the full conformance adapters/report.
STUB_PROFILES = set(PROFILES)


def create_repository():
    return AlgorithmRepository(IMPLEMENTATIONS, repo=Path(__file__).resolve().parents[2])
PY
# --8<-- [end:algorithm]

# --8<-- [start:inputs]
# 4. Create tiny synthetic MEDS events and an upstream label/index bundle.
# Real work should reuse a reviewed task bundle, not derive labels inside the algorithm.
mkdir -p inputs/meds/data inputs/labels dataset_configs predicates
uv run python - <<'PY'
from datetime import datetime
import polars as pl

pl.DataFrame({
    "subject_id": [1, 2, 3, 4, 5],
    "time": [datetime(2020, 1, 1)] * 5,
    "code": ["DEMO//encounter"] * 5,
    "numeric_value": [None] * 5,
}, schema_overrides={"numeric_value": pl.Float64}).write_parquet("inputs/meds/data/events.parquet")
for split, ids, outcomes in (
    ("train", [1, 2, 3], [True, True, False]),
    ("held_out", [4, 5], [True, False]),
):
    pl.DataFrame({
        "subject_id": ids,
        "prediction_time": [datetime(2020, 1, 2)] * len(ids),
        "boolean_value": outcomes,
    }).write_parquet(f"inputs/labels/{split}.parquet")
PY
cat > predicates/base.yaml <<'YAML'
predicates:
  encounter:
    code: DEMO//encounter
YAML
cat > predicates/demo_additional.yaml <<'YAML'
predicates:
  demo_measurement:
    code: DEMO//measurement
YAML
cat > dataset_configs/demo.yaml <<'YAML'
smoothing: 1.0
additional_predicates_file: ../predicates/demo_additional.yaml
YAML
# --8<-- [end:inputs]

# --8<-- [start:paths]
# 5. Run the complete supervised lifecycle, one independent process per step.
CONFIG="$PWD/dataset_configs/demo.yaml"
MEDS="$PWD/inputs/meds"
LABELS="$PWD/inputs/labels"
BASE_PREDICATES="$PWD/predicates/base.yaml"
ARTIFACTS="$PWD/runs/manual/supervised/artifacts"
# --8<-- [end:paths]

# --8<-- [start:preprocess]
uv run manual-baseline preprocess_data --profile supervised \
  "config_file=$CONFIG" "external_meds_dir=$MEDS" \
  "external_predicates_file=$BASE_PREDICATES" "output_data_dir=$ARTIFACTS/data"
# --8<-- [end:preprocess]

# --8<-- [start:train]
uv run manual-baseline train_supervised --profile supervised \
  "config_file=$CONFIG" "input_data_dir=$ARTIFACTS/data" \
  "external_labels_dir=$LABELS" "output_supervised_algorithm_dir=$ARTIFACTS/algorithm"
# --8<-- [end:train]

# --8<-- [start:predict]
uv run manual-baseline predict_supervised --profile supervised \
  "config_file=$CONFIG" "input_data_dir=$ARTIFACTS/data" \
  "input_supervised_algorithm_dir=$ARTIFACTS/algorithm" "external_index_dir=$LABELS" \
  'splits=[held_out]' "output_predictions_dir=$ARTIFACTS/predictions" \
  "external_evaluation_labels_dir=$LABELS"
# --8<-- [end:predict]

# --8<-- [start:verify]
# 6. Inspect and verify the outputs. Only the runner attaches the held-out truth after scoring.
uv run python - <<'PY'
from pathlib import Path
import polars as pl
import yaml
from meds_algorithm import read_manifest
from meds_algorithm.conformance.assertions import assert_prediction_schema
from manual_baseline import ManualBaseline, ManualBaselineConfig

root = Path("runs/manual/supervised/artifacts")
predictions = pl.read_parquet(root / "predictions/predictions.parquet")
assert predictions["subject_id"].to_list() == [4, 5]
assert predictions["predicted_boolean_probability"].to_list() == [0.6, 0.6]
assert predictions["boolean_value"].to_list() == [True, False]
assert_prediction_schema(predictions)
print(predictions)
for stage in ("data", "algorithm", "predictions"):
    manifest = read_manifest(root / stage)
    assert (root / stage / "config.json").is_file()
    assert (root / stage / "request.json").is_file()
    print(stage, manifest["command"]["name"], manifest["resources"]["wall_seconds"])
resolved = yaml.safe_load((root / "data/resolved_feature_predicates.yaml").read_text())
assert set(resolved["predicates"]) == {"encounter", "demo_measurement"}
config = ManualBaselineConfig.load(root / "algorithm/config.json")
assert ManualBaseline(config).name == "manual_baseline"
PY
uv run pytest -q tests/test_contract.py tests/test_operations.py
printf 'Tutorial completed in %s\n' "$PWD"
# --8<-- [end:verify]
