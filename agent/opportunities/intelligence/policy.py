from __future__ import annotations

import json
from collections.abc import Mapping
from functools import lru_cache
from hashlib import sha256
from pathlib import Path
from typing import Any

POLICY_ROOT = Path(__file__).with_name("policies")
INTELLIGENCE_POLICY_VERSION = "1.0.0"
COMMERCIALIZATION_POLICY_VERSION = "1.0.0"


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_json(value: Any) -> str:
    return sha256(canonical_json(value).encode("utf-8")).hexdigest()


@lru_cache(maxsize=2)
def load_intelligence_policy() -> Mapping[str, Any]:
    policy = _load("intelligence-policy-v1.json")
    if policy.get("version") != INTELLIGENCE_POLICY_VERSION:
        raise ValueError("unsupported Cybercore intelligence policy version")
    weights = policy.get("weights", {})
    if abs(sum(float(value) for value in weights.values()) - 1.0) > 0.000001:
        raise ValueError("Cybercore intelligence policy weights must sum to 1")
    return policy


@lru_cache(maxsize=2)
def load_commercialization_policy() -> Mapping[str, Any]:
    policy = _load("commercialization-policy-v1.json")
    if policy.get("version") != COMMERCIALIZATION_POLICY_VERSION:
        raise ValueError("unsupported Cybercore commercialization policy version")
    precedence = policy.get("path_precedence")
    if not isinstance(precedence, list) or not precedence:
        raise ValueError("Cybercore commercialization path precedence is required")
    return policy


def _load(name: str) -> Mapping[str, Any]:
    path = POLICY_ROOT / name
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError(f"Cybercore policy must be a JSON object: {name}")
    return payload
