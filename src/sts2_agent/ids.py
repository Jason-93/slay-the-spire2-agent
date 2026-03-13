from __future__ import annotations

import hashlib
import json
import re
import uuid
from typing import Any

PROTOCOL_VERSION = "0.1.0"
IDENTIFIER_RE = re.compile(r"^[a-z]+-[a-z0-9][a-z0-9_-]{2,127}$")


class IdentifierError(ValueError):
    pass


def _normalize_component(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9_-]+", "-", value.strip().lower())
    normalized = re.sub(r"-+", "-", normalized).strip("-")
    if not normalized:
        raise IdentifierError("identifier component cannot be empty")
    return normalized


def validate_identifier(value: str, prefix: str) -> str:
    normalized_prefix = _normalize_component(prefix)
    if not value.startswith(f"{normalized_prefix}-"):
        raise IdentifierError(f"identifier must start with '{normalized_prefix}-'")
    if not IDENTIFIER_RE.match(value):
        raise IdentifierError(f"invalid identifier format: {value}")
    return value


def create_session_id(seed: str | None = None) -> str:
    base = _normalize_component(seed) if seed else "session"
    digest = hashlib.sha256(f"{base}:{uuid.uuid4().hex}".encode("utf-8")).hexdigest()[:8]
    return validate_identifier(f"sess-{digest}", "sess")


def create_decision_id(session_id: str, state_version: int, phase: str) -> str:
    validate_identifier(session_id, "sess")
    component = _normalize_component(f"{session_id}-{phase}-{state_version}")
    digest = hashlib.sha256(component.encode("utf-8")).hexdigest()[:10]
    return validate_identifier(f"dec-{digest}", "dec")


def create_action_id(decision_id: str, action_type: str, payload: dict[str, Any] | None = None) -> str:
    validate_identifier(decision_id, "dec")
    normalized_type = _normalize_component(action_type)
    canonical = json.dumps(payload or {}, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(f"{decision_id}:{normalized_type}:{canonical}".encode("utf-8")).hexdigest()[:12]
    return validate_identifier(f"act-{digest}", "act")


def ensure_state_version(value: int) -> int:
    if value < 0:
        raise IdentifierError("state_version must be >= 0")
    return value
