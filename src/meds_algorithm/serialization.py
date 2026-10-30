"""Strict, explicit-class serialization for immutable configuration and requests."""

from __future__ import annotations

import json
import math
import types
from dataclasses import fields, is_dataclass
from enum import Enum
from pathlib import Path
from typing import ClassVar, Union, get_args, get_origin, get_type_hints


def encode(value):
    """JSON values only; never turn unsupported Python objects into arbitrary strings."""
    if is_dataclass(value) and not isinstance(value, type):
        if not value.__dataclass_params__.frozen:
            raise TypeError("Serializable dataclasses must be frozen")
        return {field.name: encode(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, tuple):
        return [encode(item) for item in value]
    if value is None or type(value) in (str, bool, int):
        return value
    if type(value) is float and math.isfinite(value):
        return value
    raise TypeError(f"Unsupported serialization value: {type(value).__name__}")


def decode(annotation, value, *, base: Path):
    origin = get_origin(annotation)
    args = get_args(annotation)
    if origin in (Union, types.UnionType):
        for option in args:
            try:
                return decode(option, value, base=base)
            except (TypeError, ValueError):
                pass
        raise TypeError(f"Value does not match {annotation}")
    if annotation is type(None) and value is None:
        return None
    if annotation is Path:
        if not isinstance(value, (str, Path)) or not str(value).strip():
            raise TypeError("Expected a nonempty path")
        path = Path(value)
        return (base / path).resolve() if not path.is_absolute() else path.resolve()
    if origin is tuple:
        if not isinstance(value, (tuple, list)):
            raise TypeError("Expected an array")
        if len(args) == 2 and args[1] is Ellipsis:
            return tuple(decode(args[0], item, base=base) for item in value)
        if len(args) != len(value):
            raise TypeError("Wrong tuple length")
        return tuple(decode(kind, item, base=base) for kind, item in zip(args, value, strict=True))
    if isinstance(annotation, type) and issubclass(annotation, Enum):
        return annotation(value)
    if is_dataclass(annotation):
        if isinstance(value, annotation):
            value = encode(value)
        if not isinstance(value, dict):
            raise TypeError(f"Expected an object for {annotation.__name__}")
        names = {field.name for field in fields(annotation)}
        if unknown := value.keys() - names:
            raise ValueError(f"Unknown fields for {annotation.__name__}: {sorted(unknown)}")
        hints = get_type_hints(annotation)
        return annotation(**{key: decode(hints[key], item, base=base) for key, item in value.items()})
    if annotation is float and type(value) in (int, float) and math.isfinite(value):
        return float(value)
    if annotation in (str, int, bool) and type(value) is annotation:
        return value
    raise TypeError(f"Expected {annotation}, got {type(value).__name__}")


class Serializable:
    """Subclass with a frozen dataclass. Loading never imports a class named by a file."""

    schema_version: ClassVar[int] = 1

    def __post_init__(self):
        hints = get_type_hints(type(self))
        for field in fields(self):
            object.__setattr__(
                self, field.name, decode(hints[field.name], getattr(self, field.name), base=Path.cwd())
            )
        encode(self)
        self.validate()

    def validate(self) -> None:
        """Override to enforce algorithm-specific value constraints."""

    def to_dict(self) -> dict:
        return encode(self)

    @classmethod
    def from_dict(cls, values: dict, *, base: Path | None = None):
        return decode(cls, values, base=Path.cwd() if base is None else Path(base).resolve())

    def save(self, path: Path | str) -> Path:
        path = Path(path)
        envelope = {
            "schema_version": self.schema_version,
            "type": f"{type(self).__module__}.{type(self).__qualname__}",
            "values": self.to_dict(),
        }
        path.write_text(json.dumps(envelope, sort_keys=True, indent=2, allow_nan=False), encoding="utf-8")
        return path

    @classmethod
    def load(cls, path: Path | str):
        path = Path(path).resolve()
        envelope = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(envelope, dict) or set(envelope) != {"schema_version", "type", "values"}:
            raise ValueError("Invalid serialized envelope")
        if (
            envelope["schema_version"] != cls.schema_version
            or envelope["type"] != f"{cls.__module__}.{cls.__qualname__}"
        ):
            raise ValueError("Serialized type or schema version mismatch")
        return cls.from_dict(envelope["values"], base=path.parent)
