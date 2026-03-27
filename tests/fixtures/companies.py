"""Canonical company fixtures for integration and E2E tests.

Each fixture captures the expected behavior for a known company, used to verify
pipeline outputs deterministically (with mock LLM/API clients).

Fixture design principles:
- expected_tier: the cost tier used for signal ingestion ("tier_1" / "tier_2")
- expected_qualified: whether the company passes signal qualification
- expected_signal_type: primary signal type (None if not qualified)
- expected_solution_areas: capability areas mapped from signals (empty when not qualified)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class CompanyFixture:
    company_name: str
    expected_slug: str
    expected_tier: str  # "tier_1", "tier_2", or "tier_3"
    expected_qualified: bool
    expected_signal_type: Optional[str]  # None if not qualified
    expected_solution_areas: list[str] = field(default_factory=list)


COMPANY_FIXTURES: list[CompanyFixture] = [
    # ── Tier 1 qualified ────────────────────────────────────────────────────
    CompanyFixture(
        company_name="LangChain",
        expected_slug="langchain",
        expected_tier="tier_1",
        expected_qualified=True,
        expected_signal_type="hiring_engineering",
        expected_solution_areas=["ml_platform", "data_pipeline"],
    ),
    CompanyFixture(
        company_name="Anthropic",
        expected_slug="anthropic",
        expected_tier="tier_1",
        expected_qualified=True,
        expected_signal_type="ml_infra",
        expected_solution_areas=["ml_platform", "cloud_infra"],
    ),
    CompanyFixture(
        company_name="Databricks",
        expected_slug="databricks",
        expected_tier="tier_1",
        expected_qualified=True,
        expected_signal_type="data_platform",
        expected_solution_areas=["data_pipeline", "ml_platform"],
    ),
    CompanyFixture(
        company_name="Snowflake",
        expected_slug="snowflake",
        expected_tier="tier_1",
        expected_qualified=True,
        expected_signal_type="data_platform",
        expected_solution_areas=["data_pipeline", "cloud_infra"],
    ),
    CompanyFixture(
        company_name="Cloudflare",
        expected_slug="cloudflare",
        expected_tier="tier_1",
        expected_qualified=True,
        expected_signal_type="infra_scaling",
        expected_solution_areas=["cloud_infra", "security"],
    ),
    CompanyFixture(
        company_name="Stripe",
        expected_slug="stripe",
        expected_tier="tier_1",
        expected_qualified=True,
        expected_signal_type="hiring_engineering",
        expected_solution_areas=["cloud_infra", "data_pipeline"],
    ),
    # ── Slug normalisation edge cases ────────────────────────────────────────
    CompanyFixture(
        company_name="Stripe, Inc.",
        expected_slug="stripe",
        expected_tier="tier_1",
        expected_qualified=True,
        expected_signal_type="hiring_engineering",
        expected_solution_areas=["cloud_infra", "data_pipeline"],
    ),
    # ── Tier 2 escalation (qualified) ───────────────────────────────────────
    CompanyFixture(
        company_name="Upbound Group",
        expected_slug="upbound",
        expected_tier="tier_2",
        expected_qualified=True,
        expected_signal_type="infra_scaling",
        expected_solution_areas=["cloud_infra"],
    ),
    # ── Tier 2 (not qualified — signal score below threshold) ───────────────
    CompanyFixture(
        company_name="Staples",
        expected_slug="staples",
        expected_tier="tier_2",
        expected_qualified=False,
        expected_signal_type=None,
        expected_solution_areas=[],
    ),
    # ── Tier 1 (not qualified — no matching signals) ─────────────────────────
    CompanyFixture(
        company_name="Acme Corp LLC",
        expected_slug="acme-corp",
        expected_tier="tier_1",
        expected_qualified=False,
        expected_signal_type=None,
        expected_solution_areas=[],
    ),
]
