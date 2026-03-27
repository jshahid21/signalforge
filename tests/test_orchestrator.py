"""Tests for orchestrator: slug normalization and input validation (spec §5.1, §13.1)."""
from __future__ import annotations

import pytest

from backend.agents.orchestrator import normalize_company_name, validate_companies


class TestNormalizeCompanyName:
    """Spec §5.1 normalization rules."""

    def test_stripe_inc(self) -> None:
        assert normalize_company_name("Stripe, Inc.") == "stripe"

    def test_upbound_group(self) -> None:
        assert normalize_company_name("Upbound Group") == "upbound"

    def test_stripe_dot_com(self) -> None:
        assert normalize_company_name("stripe.com") == "stripe-com"

    def test_langchain_no_suffix(self) -> None:
        assert normalize_company_name("LangChain") == "langchain"

    def test_anthropic_no_suffix(self) -> None:
        assert normalize_company_name("Anthropic") == "anthropic"

    def test_llc_suffix(self) -> None:
        assert normalize_company_name("Acme LLC") == "acme"

    def test_ltd_suffix(self) -> None:
        assert normalize_company_name("Foo Ltd") == "foo"

    def test_corp_suffix(self) -> None:
        assert normalize_company_name("BigCo Corp") == "bigco"

    def test_corporation_suffix(self) -> None:
        assert normalize_company_name("OldBank Corporation") == "oldbank"

    def test_incorporated_suffix(self) -> None:
        assert normalize_company_name("TechCo Incorporated") == "techco"

    def test_special_chars_replaced(self) -> None:
        assert normalize_company_name("Foo & Bar") == "foo-bar"

    def test_consecutive_dashes_collapsed(self) -> None:
        # "Foo  &  Bar" → after replacement → "foo--bar" → "foo-bar"
        assert normalize_company_name("Foo  &  Bar") == "foo-bar"

    def test_leading_trailing_dashes_trimmed(self) -> None:
        # a name that starts with special chars
        result = normalize_company_name("-- TechCo --")
        assert not result.startswith("-")
        assert not result.endswith("-")

    def test_snowflake(self) -> None:
        assert normalize_company_name("Snowflake") == "snowflake"

    def test_databricks(self) -> None:
        assert normalize_company_name("Databricks") == "databricks"

    def test_cloudflare(self) -> None:
        assert normalize_company_name("Cloudflare") == "cloudflare"

    def test_upbound_group_rent_a_center(self) -> None:
        # Only "Group" is stripped, "Upbound" remains
        assert normalize_company_name("Upbound Group") == "upbound"

    def test_case_insensitive_suffix(self) -> None:
        # Suffix stripping is case-insensitive
        assert normalize_company_name("Acme INC") == "acme"
        assert normalize_company_name("Acme inc") == "acme"

    def test_whitespace_only_after_strip(self) -> None:
        # Handles edge case of name that is just a suffix
        result = normalize_company_name("Group")
        # "Group" alone may strip to empty; confirm no crash and strip behavior
        # "Group" → strip suffix → "" → trim → ""
        # But spec only shows examples with actual company names
        # This is defensive: ensure no exception raised
        assert isinstance(result, str)

    def test_numbers_preserved(self) -> None:
        assert normalize_company_name("Web3 Labs") == "web3-labs"


class TestValidateCompanies:
    def test_accepts_single_company(self) -> None:
        validate_companies(["Stripe"])  # Should not raise

    def test_accepts_max_5_companies(self) -> None:
        validate_companies(["A", "B", "C", "D", "E"])  # Should not raise

    def test_raises_on_empty_list(self) -> None:
        with pytest.raises(ValueError, match="At least one"):
            validate_companies([])

    def test_raises_on_more_than_5(self) -> None:
        with pytest.raises(ValueError, match="Maximum is 5"):
            validate_companies(["A", "B", "C", "D", "E", "F"])

    def test_raises_on_duplicate_after_normalization(self) -> None:
        with pytest.raises(ValueError, match="Duplicate company"):
            validate_companies(["Stripe", "Stripe, Inc."])

    def test_raises_with_both_names_in_error(self) -> None:
        with pytest.raises(ValueError, match="stripe"):
            validate_companies(["Stripe", "Stripe, Inc."])

    def test_accepts_different_companies(self) -> None:
        # These should not normalize to same slug
        validate_companies(["Stripe", "LangChain", "Anthropic"])

    def test_raises_on_upbound_collision(self) -> None:
        # "Upbound Group" and "Upbound" both → "upbound"
        with pytest.raises(ValueError, match="Duplicate company"):
            validate_companies(["Upbound Group", "Upbound"])
