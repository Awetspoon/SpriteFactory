"""Shared dataclass serialization helpers for model persistence."""

from __future__ import annotations

from dataclasses import fields, is_dataclass
from datetime import datetime
from enum import Enum
import types
from typing import Any, TypeVar, Union, get_args, get_origin, get_type_hints


T = TypeVar("T", bound="SerializableDataclass")
NONE_TYPE = type(None)
UNION_ORIGINS = {Union}
if hasattr(types, "UnionType"):
    UNION_ORIGINS.add(types.UnionType)


def _serialize_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    if is_dataclass(value):
        return {field.name: _serialize_value(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, tuple):
        return [_serialize_value(item) for item in value]
    if isinstance(value, list):
        return [_serialize_value(item) for item in value]
    if isinstance(value, set):
        return sorted((_serialize_value(item) for item in value), key=repr)
    if isinstance(value, dict):
        return {_serialize_value(key): _serialize_value(item) for key, item in value.items()}
    return value


def _deserialize_value(expected_type: Any, raw_value: Any) -> Any:
    if raw_value is None:
        return None

    if expected_type is Any or expected_type is object:
        return raw_value

    origin = get_origin(expected_type)
    args = get_args(expected_type)

    if origin in UNION_ORIGINS:
        if raw_value is None and NONE_TYPE in args:
            return None
        for candidate in (arg for arg in args if arg is not NONE_TYPE):
            try:
                return _deserialize_value(candidate, raw_value)
            except (TypeError, ValueError, KeyError):
                continue
        return raw_value

    if origin is list:
        item_type = args[0] if args else Any
        return [_deserialize_value(item_type, item) for item in raw_value]

    if origin is set:
        item_type = args[0] if args else Any
        return {_deserialize_value(item_type, item) for item in raw_value}

    if origin is tuple:
        if len(args) == 2 and args[1] is Ellipsis:
            return tuple(_deserialize_value(args[0], item) for item in raw_value)
        if args:
            return tuple(
                _deserialize_value(arg, item)
                for arg, item in zip(args, raw_value, strict=False)
            )
        return tuple(raw_value)

    if origin is dict:
        key_type = args[0] if len(args) > 0 else Any
        value_type = args[1] if len(args) > 1 else Any
        return {
            _deserialize_value(key_type, key): _deserialize_value(value_type, item)
            for key, item in raw_value.items()
        }

    if isinstance(expected_type, type) and issubclass(expected_type, Enum):
        return expected_type(raw_value)

    if expected_type is datetime:
        return datetime.fromisoformat(raw_value)

    if isinstance(expected_type, type) and is_dataclass(expected_type):
        return _deserialize_dataclass(expected_type, raw_value)

    return raw_value


def _deserialize_dataclass(cls: type[T], payload: dict[str, Any]) -> T:
    if not isinstance(payload, dict):
        raise TypeError(f"Expected dict payload for {cls.__name__}, got {type(payload).__name__}")

    hints = get_type_hints(cls)
    kwargs: dict[str, Any] = {}
    for field in fields(cls):
        if field.name not in payload:
            continue
        field_type = hints.get(field.name, field.type)
        kwargs[field.name] = _deserialize_value(field_type, payload[field.name])
    return cls(**kwargs)


class SerializableDataclass:
    """Mixin that provides JSON-friendly dict serialization for dataclasses."""

    def to_dict(self) -> dict[str, Any]:
        if not is_dataclass(self):
            raise TypeError(f"{type(self).__name__} is not a dataclass instance")
        return _serialize_value(self)

    @classmethod
    def from_dict(cls: type[T], payload: dict[str, Any]) -> T:
        return _deserialize_dataclass(cls, payload)

