"""
Textile Security & Capability Tier Policy Matrix.
Defines security gating (2FA TOTP), sandbox isolation, and workspace permissions per capability tier.
"""

from dataclasses import dataclass
from typing import Any

from needle import CapabilityTier, parse_capability_tier


@dataclass(frozen=True, slots=True)
class TierPolicy:
    """Security and execution policy for a capability tier."""

    tier: CapabilityTier
    requires_2fa: bool
    requires_sandbox: bool
    workspace_writable: bool
    default_timeout: float


TIER_POLICIES: dict[CapabilityTier, TierPolicy] = {
    CapabilityTier.OBSERVE: TierPolicy(
        tier=CapabilityTier.OBSERVE,
        requires_2fa=False,
        requires_sandbox=True,
        workspace_writable=False,
        default_timeout=10.0,
    ),
    CapabilityTier.INTERACT: TierPolicy(
        tier=CapabilityTier.INTERACT,
        requires_2fa=False,
        requires_sandbox=True,
        workspace_writable=False,
        default_timeout=15.0,
    ),
    CapabilityTier.MUTATE: TierPolicy(
        tier=CapabilityTier.MUTATE,
        requires_2fa=True,
        requires_sandbox=True,
        workspace_writable=True,
        default_timeout=60.0,
    ),
    CapabilityTier.PRIVILEGED: TierPolicy(
        tier=CapabilityTier.PRIVILEGED,
        requires_2fa=True,
        requires_sandbox=False,
        workspace_writable=True,
        default_timeout=300.0,
    ),
    CapabilityTier.SYSTEM_EXEC: TierPolicy(
        tier=CapabilityTier.SYSTEM_EXEC,
        requires_2fa=True,
        requires_sandbox=True,
        workspace_writable=False,
        default_timeout=120.0,
    ),
}


def get_tier_policy(tier: Any) -> TierPolicy:
    """Retrieve the TierPolicy for a given capability tier, failing closed on invalid tiers."""
    validated = parse_capability_tier(tier)
    if validated in TIER_POLICIES:
        return TIER_POLICIES[validated]
    raise ValueError(f"No TierPolicy configured for capability tier '{tier}'.")


__all__ = ["TIER_POLICIES", "TierPolicy", "get_tier_policy"]
