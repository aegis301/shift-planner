
from app.schemas import ShiftConstraint
from app.services.constraints import ResolvedConstraint
from app.services.unavailable_overlap import (
    ResolvedUnavailableOverlapPolicy,
    resolve_unavailable_overlap_policy,
)


def test_resolve_unavailable_overlap_policy_default_block():
    policy = resolve_unavailable_overlap_policy([])
    assert policy == ResolvedUnavailableOverlapPolicy(mode="block", severity="error")


def test_resolve_unavailable_overlap_policy_explicit_allow():
    resolved = [
        ResolvedConstraint(
            source="variant",
            rule=ShiftConstraint.model_validate(
                {"type": "unavailable_overlap_policy", "unavailable_overlap_mode": "allow"}
            ),
        )
    ]
    policy = resolve_unavailable_overlap_policy(resolved)
    assert policy.mode == "allow"


def test_resolve_unavailable_overlap_policy_legacy_warn():
    resolved = [
        ResolvedConstraint(
            source="variant",
            rule=ShiftConstraint.model_validate(
                {"type": "no_cross_day_into_unavailable_day", "severity": "warning"}
            ),
        )
    ]
    policy = resolve_unavailable_overlap_policy(resolved)
    assert policy.mode == "warn"
    assert policy.severity == "warning"


def test_new_policy_overrides_legacy():
    resolved = [
        ResolvedConstraint(
            source="variant",
            rule=ShiftConstraint.model_validate(
                {"type": "no_cross_day_into_unavailable_day", "severity": "error"}
            ),
        ),
        ResolvedConstraint(
            source="template",
            rule=ShiftConstraint.model_validate(
                {"type": "unavailable_overlap_policy", "unavailable_overlap_mode": "allow"}
            ),
        ),
    ]
    policy = resolve_unavailable_overlap_policy(resolved)
    assert policy.mode == "allow"
