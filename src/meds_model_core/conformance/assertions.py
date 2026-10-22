from pathlib import Path

from ..data.index import read_index


def assert_prediction_keys(predictions_dir: Path, labels_dir: Path, splits) -> None:
    """Compare actual prediction keys with requested keys, independent of row order."""
    import polars as pl

    key_columns = ["subject_id", "prediction_time"]

    # MEDS-DEV evaluates every `{predictions_dir}/**/*.parquet` (configs/_evaluate_predictions.yaml), so
    # every parquet under the predictions artifact must be a predictions file. Publish supporting tables
    # (e.g. a zero-shot query bundle) in another format, such as Arrow IPC.
    for path in sorted(Path(predictions_dir).rglob("*.parquet")):
        schema = pl.read_parquet_schema(path)
        if "predicted_boolean_probability" not in schema and "predicted_boolean_value" not in schema:
            raise AssertionError(
                f"{path} is not a predictions file; MEDS-DEV evaluates every parquet under the predictions "
                "directory; store supporting tables in another format (e.g. Arrow IPC)"
            )
    try:
        predictions = read_index(Path(predictions_dir))
        expected = read_index(Path(labels_dir), splits)
    except ValueError as error:
        raise AssertionError(str(error)) from error
    prediction_unique = predictions.unique()
    expected_unique = expected.unique()
    assert prediction_unique.height == predictions.height, "predictions contain duplicate evaluation keys"
    assert expected_unique.height == expected.height, "requested evaluation index contains duplicate keys"
    missing = expected_unique.join(prediction_unique, on=key_columns, how="anti")
    extra = prediction_unique.join(expected_unique, on=key_columns, how="anti")
    assert missing.is_empty() and extra.is_empty(), (
        f"prediction key mismatch: {missing.height} missing and {extra.height} extra keys"
    )


def assert_prediction_schema(predictions) -> None:
    """Validate predictions exactly as MEDS-DEV's pinned meds-evaluation (0.0.3) will."""
    from meds_evaluation.schema import validate_binary_classification_schema

    validate_binary_classification_schema(predictions)
