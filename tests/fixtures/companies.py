"""Canonical company fixtures for integration and E2E tests.

Each fixture captures the expected behavior for a known company, used to verify
pipeline outputs deterministically (with mock LLM/API clients).

Populated fully in Phase 8; stubs provided here as placeholders.
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


# Stubs — expected values to be filled in Phase 8 after agent implementation
COMPANY_FIXTURES: list[CompanyFixture] = [
    CompanyFixture(
        company_name="LangChain",
        expected_slug="langchain",
        expected_tier="tier_1",
        expected_qualified=True,
        expected_signal_type="hiring_engineering",
        expected_solution_areas=[],  # Populated in Phase 8
    ),
    CompanyFixture(
        company_name="Anthropic",
        expected_slug="anthropic",
        expected_tier="tier_1",
        expected_qualified=True,
        expected_signal_type="ml_infra",
        expected_solution_areas=[],
    ),
    CompanyFixture(
        company_name="Databricks",
        expected_slug="databricks",
        expected_tier="tier_1",
        expected_qualified=True,
        expected_signal_type="data_platform",
        expected_solution_areas=[],
    ),
    CompanyFixture(
        company_name="Snowflake",
        expected_slug="snowflake",
        expected_tier="tier_1",
        expected_qualified=True,
        expected_signal_type="data_platform",
        expected_solution_areas=[],
    ),
    CompanyFixture(
        company_name="Cloudflare",
        expected_slug="cloudflare",
        expected_tier="tier_1",
        expected_qualified=True,
        expected_signal_type="infra_scaling",
        expected_solution_areas=[],
    ),
    CompanyFixture(
        company_name="Stripe",
        expected_slug="stripe",
        expected_tier="tier_1",
        expected_qualified=True,
        expected_signal_type="hiring_engineering",
        expected_solution_areas=[],
    ),
    CompanyFixture(
        company_name="Stripe, Inc.",
        expected_slug="stripe",
        expected_tier="tier_1",
        expected_qualified=True,
        expected_signal_type="hiring_engineering",
        expected_solution_areas=[],
    ),
    CompanyFixture(
        company_name="Upbound Group",
        expected_slug="upbound",
        expected_tier="tier_2",
        expected_qualified=True,
        expected_signal_type="infra_scaling",
        expected_solution_areas=[],
    ),
    CompanyFixture(
        company_name="Staples",
        expected_slug="staples",
        expected_tier="tier_2",
        expected_qualified=False,
        expected_signal_type=None,
        expected_solution_areas=[],
    ),
    CompanyFixture(
        company_name="Acme Corp LLC",
        expected_slug="acme-corp",
        expected_tier="tier_1",
        expected_qualified=False,
        expected_signal_type=None,
        expected_solution_areas=[],
    ),
]
