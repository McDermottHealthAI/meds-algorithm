"""Compose feature predicates without overriding the dataset's definitions."""

import hashlib
from pathlib import Path

import yaml

RESOLVED_PREDICATES_FILENAME = "resolved_feature_predicates.yaml"


class _UniqueKeysLoader(yaml.SafeLoader):
    def construct_mapping(self, node, deep=False):
        self.flatten_mapping(node)
        mapping = {}
        for key_node, value_node in node.value:
            key = self.construct_object(key_node, deep=deep)
            if not isinstance(key, str) or not key.strip():
                raise ValueError("Predicate YAML keys must be nonempty strings")
            if key in mapping:
                raise ValueError(f"Duplicate YAML key: {key}")
            mapping[key] = self.construct_object(value_node, deep=deep)
        return mapping


def _digest(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _read(path: Path):
    data = path.read_bytes()
    try:
        document = yaml.load(data, Loader=_UniqueKeysLoader)
    except yaml.YAMLError as error:
        raise ValueError(f"Invalid predicates YAML in {path}: {error}") from error
    if not isinstance(document, dict) or set(document) != {"predicates"}:
        raise ValueError(f"{path} must contain only a predicates mapping, not task/cohort configuration")
    predicates = document["predicates"]
    if not isinstance(predicates, dict) or any(
        not isinstance(definition, dict) or not definition for definition in predicates.values()
    ):
        raise ValueError(f"{path} predicates must map names to nonempty definitions")
    return predicates, {"path": str(path.resolve()), "digest": _digest(data)}


def compose_feature_predicates(base: Path | None, additional: Path) -> tuple[bytes, dict]:
    """Return deterministic YAML and provenance from the same source snapshots.

    Accept predicate-only documents in MEDS-DEV's shape. Reject duplicate names even when definitions
    agree. Expression semantics and dataset compatibility remain the algorithm's responsibility.
    """
    predicates, base_source = ({}, None) if base is None else _read(Path(base))
    additions, additional_source = _read(Path(additional))
    if duplicates := predicates.keys() & additions.keys():
        raise ValueError(f"Additional predicates duplicate dataset names: {sorted(duplicates)}")
    content = yaml.safe_dump({"predicates": predicates | additions}, sort_keys=True).encode("utf-8")
    return content, {
        "base": base_source,
        "additional": additional_source,
        "resolved": {"path": RESOLVED_PREDICATES_FILENAME, "digest": _digest(content)},
    }
