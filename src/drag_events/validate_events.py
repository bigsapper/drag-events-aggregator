"""Validate dist/events.json against dist/events.schema.json."""

from __future__ import annotations

import json
import re
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from .paths import EVENTS_FILE as DEFAULT_EVENTS_FILE
from .paths import EVENTS_SCHEMA_FILE as DEFAULT_SCHEMA_FILE


@dataclass(frozen=True)
class ValidationError:
    path: str
    message: str

    def __str__(self) -> str:
        return f"{self.path}: {self.message}"


class SchemaValidationError(ValueError):
    """Raised when events output does not satisfy the JSON schema."""

    def __init__(self, errors: list[ValidationError]):
        self.errors = errors
        message = "\n".join(str(error) for error in errors)
        super().__init__(message)


def load_json(path: Path) -> object:
    return json.loads(path.read_text())


def _is_date(value: str) -> bool:
    try:
        datetime.strptime(value, "%Y-%m-%d")
        return True
    except ValueError:
        return False


def _is_date_time(value: str) -> bool:
    try:
        if value.endswith("Z"):
            datetime.fromisoformat(value[:-1] + "+00:00")
        else:
            datetime.fromisoformat(value)
        return True
    except ValueError:
        return False


def _is_uuid(value: str) -> bool:
    try:
        uuid.UUID(value)
        return True
    except (ValueError, AttributeError, TypeError):
        return False


def _is_uri(value: str) -> bool:
    parsed = urlparse(value)
    return bool(parsed.scheme and parsed.netloc)


def _is_email(value: str) -> bool:
    return re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value) is not None


def _matches_type(instance: object, expected_type: str) -> bool:
    if expected_type == "array":
        return isinstance(instance, list)
    if expected_type == "object":
        return isinstance(instance, dict)
    if expected_type == "string":
        return isinstance(instance, str)
    if expected_type == "number":
        return isinstance(instance, (int, float)) and not isinstance(instance, bool)
    if expected_type == "null":
        return instance is None
    if expected_type == "boolean":
        return isinstance(instance, bool)
    if expected_type == "integer":
        return isinstance(instance, int) and not isinstance(instance, bool)
    return False


def _validate_format(instance: object, expected_format: str) -> bool:
    if not isinstance(instance, str):
        return False
    if expected_format == "date":
        return _is_date(instance)
    if expected_format == "date-time":
        return _is_date_time(instance)
    if expected_format == "uuid":
        return _is_uuid(instance)
    if expected_format == "uri":
        return _is_uri(instance)
    if expected_format == "email":
        return _is_email(instance)
    return True


def _validate_instance(
    instance: object,
    schema: dict,
    root_schema: dict,
    path: str,
    errors: list[ValidationError],
) -> None:
    ref = schema.get("$ref")
    if ref:
        if not ref.startswith("#/"):
            errors.append(ValidationError(path, f"unsupported ref {ref!r}"))
            return
        target: object = root_schema
        for segment in ref[2:].split("/"):
            if not isinstance(target, dict) or segment not in target:
                errors.append(ValidationError(path, f"unresolved ref {ref!r}"))
                return
            target = target[segment]
        _validate_instance(instance, target, root_schema, path, errors)
        return

    expected_type = schema.get("type")
    if expected_type is not None:
        allowed_types = expected_type if isinstance(expected_type, list) else [expected_type]
        if not any(_matches_type(instance, kind) for kind in allowed_types):
            expected = " or ".join(allowed_types)
            errors.append(ValidationError(path, f"expected {expected}, got {type(instance).__name__}"))
            return

    if "enum" in schema and instance not in schema["enum"]:
        errors.append(ValidationError(path, f"expected one of {schema['enum']}, got {instance!r}"))

    if instance is None:
        return

    if isinstance(instance, (int, float)) and not isinstance(instance, bool):
        minimum = schema.get("minimum")
        maximum = schema.get("maximum")
        if minimum is not None and instance < minimum:
            errors.append(ValidationError(path, f"must be >= {minimum}"))
        if maximum is not None and instance > maximum:
            errors.append(ValidationError(path, f"must be <= {maximum}"))

    if isinstance(instance, str):
        expected_format = schema.get("format")
        if expected_format and not _validate_format(instance, expected_format):
            errors.append(ValidationError(path, f"expected {expected_format} string"))
        pattern = schema.get("pattern")
        if pattern and re.fullmatch(pattern, instance) is None:
            errors.append(ValidationError(path, f"must match pattern {pattern!r}"))

    if isinstance(instance, list):
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for index, value in enumerate(instance):
                _validate_instance(value, item_schema, root_schema, f"{path}[{index}]", errors)
        return

    if isinstance(instance, dict):
        properties = schema.get("properties", {})
        required = schema.get("required", [])
        for key in required:
            if key not in instance:
                errors.append(ValidationError(path, f"missing required property {key!r}"))
        if schema.get("additionalProperties") is False:
            extras = sorted(set(instance) - set(properties))
            for key in extras:
                errors.append(ValidationError(path, f"unexpected property {key!r}"))
        for key, value in instance.items():
            property_schema = properties.get(key)
            if isinstance(property_schema, dict):
                _validate_instance(value, property_schema, root_schema, f"{path}.{key}", errors)


def collect_validation_errors(events: object, schema: dict | None = None) -> list[ValidationError]:
    root_schema = schema or load_json(DEFAULT_SCHEMA_FILE)
    errors: list[ValidationError] = []
    _validate_instance(events, root_schema, root_schema, "$", errors)
    return errors


def validate_payload_against_schema(payload: object, schema: dict) -> None:
    errors = collect_validation_errors(payload, schema=schema)
    if errors:
        raise SchemaValidationError(errors)


def validate_events_payload(events: object, schema: dict | None = None) -> None:
    validate_payload_against_schema(events, schema or load_json(DEFAULT_SCHEMA_FILE))


def validate_events_file(
    events_path: Path = DEFAULT_EVENTS_FILE,
    schema_path: Path = DEFAULT_SCHEMA_FILE,
) -> None:
    schema = load_json(schema_path)
    events = load_json(events_path)
    validate_events_payload(events, schema=schema)


def main() -> None:
    events_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_EVENTS_FILE
    schema_path = Path(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_SCHEMA_FILE
    try:
        validate_events_file(events_path=events_path, schema_path=schema_path)
    except SchemaValidationError as exc:
        print(f"Schema validation failed for {events_path}:")
        for error in exc.errors:
            print(f"  - {error}")
        raise SystemExit(1) from exc
    print(f"Schema validation passed for {events_path}")


if __name__ == "__main__":
    main()
