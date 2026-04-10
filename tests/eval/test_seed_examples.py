"""Unit tests for seed_examples.py — validates structure without LLM calls."""
from __future__ import annotations

import pytest
from tests.eval.seed_examples import SEED_EXAMPLES

REQUIRED_FIELDS = {"company_name", "signal_summary", "persona_title", "role_type"}
VALID_ROLE_TYPES = {"technical_buyer", "economic_buyer", "influencer", "blocker"}


class TestSeedExamples:
    def test_has_exactly_five_examples(self) -> None:
        assert len(SEED_EXAMPLES) == 5

    def test_all_required_fields_present(self) -> None:
        for i, example in enumerate(SEED_EXAMPLES):
            missing = REQUIRED_FIELDS - set(example.keys())
            assert not missing, f"Example {i} missing fields: {missing}"

    def test_no_empty_values(self) -> None:
        for i, example in enumerate(SEED_EXAMPLES):
            for field in REQUIRED_FIELDS:
                assert example[field], f"Example {i} has empty {field!r}"

    def test_role_types_are_valid(self) -> None:
        for i, example in enumerate(SEED_EXAMPLES):
            assert example["role_type"] in VALID_ROLE_TYPES, (
                f"Example {i} has unknown role_type {example['role_type']!r}"
            )

    def test_no_draft_content_in_examples(self) -> None:
        draft_keys = {"subject_line", "body", "draft", "subject", "email_body"}
        for i, example in enumerate(SEED_EXAMPLES):
            unexpected = draft_keys & set(example.keys())
            assert not unexpected, f"Example {i} contains draft content keys: {unexpected}"

    def test_diverse_role_types(self) -> None:
        role_types = {example["role_type"] for example in SEED_EXAMPLES}
        assert len(role_types) >= 2, f"Expected diversity in role_types, got: {role_types}"

    def test_unique_company_names(self) -> None:
        names = [example["company_name"] for example in SEED_EXAMPLES]
        assert len(names) == len(set(names)), "Company names are not unique"
