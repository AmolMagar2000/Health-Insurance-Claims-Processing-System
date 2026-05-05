"""
utils/policy_loader.py
======================
Loads policy_terms.json once and provides typed accessor helpers.
All adjudication logic pulls rules from here — nothing is hardcoded.
"""

from __future__ import annotations

import json
import os
from functools import lru_cache
from typing import Any, Dict, List, Optional


POLICY_FILE = os.path.join(os.path.dirname(__file__), "..", "policy_terms.json")


@lru_cache(maxsize=1)
def load_policy() -> Dict[str, Any]:
    """Load the policy JSON file exactly once, then cache it in memory."""
    path = os.path.abspath(POLICY_FILE)
    with open(path, "r") as f:
        return json.load(f)


# ── Handy helpers ─────────────────────────────────────────────────────────────

def get_member(member_id: str) -> Optional[Dict[str, Any]]:
    """Return the member record or None if not found."""
    policy = load_policy()
    for m in policy.get("members", []):
        if m["member_id"] == member_id:
            return m
    return None


def get_category_rules(category: str) -> Optional[Dict[str, Any]]:
    """Return the opd_categories entry for a given category key (e.g. 'CONSULTATION')."""
    policy = load_policy()
    return policy.get("opd_categories", {}).get(category.lower())


def get_required_documents(category: str) -> Dict[str, List[str]]:
    """Return {required: [...], optional: [...]} document types for a category."""
    policy = load_policy()
    return policy.get("document_requirements", {}).get(category.upper(), {"required": [], "optional": []})


def get_waiting_periods() -> Dict[str, Any]:
    return load_policy().get("waiting_periods", {})


def get_exclusions() -> Dict[str, Any]:
    return load_policy().get("exclusions", {})


def get_network_hospitals() -> List[str]:
    return load_policy().get("network_hospitals", [])


def get_fraud_thresholds() -> Dict[str, Any]:
    return load_policy().get("fraud_thresholds", {})


def get_coverage() -> Dict[str, Any]:
    return load_policy().get("coverage", {})


def is_network_hospital(hospital_name: Optional[str]) -> bool:
    """Case-insensitive check whether a hospital name is in the network."""
    if not hospital_name:
        return False
    network = [h.lower() for h in get_network_hospitals()]
    return hospital_name.lower() in network


def get_pre_auth_requirements() -> Dict[str, Any]:
    return load_policy().get("pre_authorization", {})
