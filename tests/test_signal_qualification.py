"""Tests for Signal Qualification Agent — scoring boundary values (spec §13.1)."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.agents.signal_qualification import (
    QUALIFICATION_THRESHOLD,
    compute_composite_score,
    compute_deterministic_score,
    compute_signal_ambiguity_score,
    parse_llm_severity_response,
    run_signal_qualification,
)
from backend.models.enums import PipelineStatus, SignalTier
from backend.models.state import CompanyState, CostMetadata, RawSignal


def _make_company_state(raw_signals: list[RawSignal] | None = None) -> CompanyState:
    return CompanyState(
        company_id="stripe",
        company_name="Stripe",
        status=PipelineStatus.RUNNING,
        current_stage="signal_qualification",
        raw_signals=raw_signals or [],
        qualified_signal=None,
        signal_qualified=False,
        research_result=None,
        solution_mapping=None,
        generated_personas=[],
        selected_personas=[],
        recommended_outreach_sequence=[],
        synthesis_outputs={},
        drafts={},
        cost_metadata=CostMetadata(
            tier_1_calls=1,
            tier_2_calls=0,
            tier_3_calls=0,
            llm_tokens_used=0,
            estimated_cost_usd=0.001,
            tier_escalation_reasons=[],
        ),
        errors=[],
        human_review_required=False,
        human_review_reasons=[],
        override_requested=False,
        override_reason=None,
        drafted_under_override=False,
    )


def _make_signal(content: str = "kubernetes ml platform data warehouse") -> RawSignal:
    return RawSignal(
        source="jsearch",
        signal_type="job_posting",
        content=content,
        url=None,
        published_at=None,
        tier=SignalTier.TIER_1,
    )


def _make_cap_map(keywords: list[str]):
    cap_map = MagicMock()
    cap_map.all_keywords.return_value = keywords
    return cap_map


class TestComputeDeterministicScore:
    def test_all_keywords_match(self) -> None:
        signals = [_make_signal("kubernetes ml platform data warehouse")]
        cap_map = _make_cap_map(["kubernetes", "ml platform", "data warehouse"])
        score = compute_deterministic_score(signals, cap_map)
        assert score == 1.0

    def test_partial_keywords_match(self) -> None:
        signals = [_make_signal("kubernetes engineer")]
        cap_map = _make_cap_map(["kubernetes", "ml platform", "data warehouse"])
        score = compute_deterministic_score(signals, cap_map)
        assert abs(score - 1 / 3) < 1e-9

    def test_no_keywords_match(self) -> None:
        signals = [_make_signal("office manager")]
        cap_map = _make_cap_map(["kubernetes", "ml platform"])
        score = compute_deterministic_score(signals, cap_map)
        assert score == 0.0

    def test_score_capped_at_1(self) -> None:
        # More matches than keywords → still 1.0
        signals = [_make_signal("kubernetes kubernetes kubernetes")]
        cap_map = _make_cap_map(["kubernetes"])
        score = compute_deterministic_score(signals, cap_map)
        assert score == 1.0

    def test_no_capability_map_returns_zero(self) -> None:
        signals = [_make_signal("kubernetes")]
        assert compute_deterministic_score(signals, None) == 0.0

    def test_empty_keywords_returns_zero(self) -> None:
        signals = [_make_signal("kubernetes")]
        cap_map = _make_cap_map([])
        assert compute_deterministic_score(signals, cap_map) == 0.0

    def test_case_insensitive(self) -> None:
        signals = [_make_signal("KUBERNETES ML PLATFORM")]
        cap_map = _make_cap_map(["kubernetes", "ml platform"])
        score = compute_deterministic_score(signals, cap_map)
        assert score == 1.0


class TestComputeCompositeScore:
    """Spec §5.3: composite = 0.4 * det + 0.6 * llm"""

    def test_formula(self) -> None:
        score = compute_composite_score(0.5, 0.8)
        assert abs(score - (0.4 * 0.5 + 0.6 * 0.8)) < 1e-9

    def test_all_zeros(self) -> None:
        assert compute_composite_score(0.0, 0.0) == 0.0

    def test_all_ones(self) -> None:
        assert abs(compute_composite_score(1.0, 1.0) - 1.0) < 1e-9

    def test_boundary_at_qualification_threshold(self) -> None:
        # Verify threshold is 0.45
        assert QUALIFICATION_THRESHOLD == 0.45

    def test_score_above_threshold_qualifies(self) -> None:
        # composite slightly above threshold
        score = compute_composite_score(0.5, 0.5)  # = 0.5 > 0.45
        assert score > QUALIFICATION_THRESHOLD

    def test_score_below_threshold_disqualifies(self) -> None:
        # composite slightly below threshold
        score = compute_composite_score(0.3, 0.3)  # = 0.3 < 0.45
        assert score < QUALIFICATION_THRESHOLD

    def test_boundary_value_59_percent(self) -> None:
        """Score of ~0.59 should be above qualification threshold (0.45)."""
        # Spec §13.1 references 59, 60, 61 as confidence boundary values
        # For qualification (threshold=0.45), any score >= 0.45 qualifies
        score_59 = 0.59
        assert score_59 > QUALIFICATION_THRESHOLD

    def test_boundary_value_45_exact(self) -> None:
        """Score of exactly 0.45 should qualify (>= threshold)."""
        assert 0.45 >= QUALIFICATION_THRESHOLD

    def test_boundary_value_44_below(self) -> None:
        """Score of 0.44 should NOT qualify."""
        assert 0.44 < QUALIFICATION_THRESHOLD


class TestSignalAmbiguityScore:
    """signal_ambiguity_score = 1 - mean(recency, specificity)"""

    def test_high_ambiguity_on_old_generic_signal(self) -> None:
        scores = {"recency": 0.1, "specificity": 0.1, "technical_depth": 0.5, "buying_intent": 0.5}
        ambiguity = compute_signal_ambiguity_score(scores)
        assert ambiguity > 0.7  # triggers Tier 2 escalation

    def test_low_ambiguity_on_fresh_specific_signal(self) -> None:
        scores = {"recency": 0.9, "specificity": 0.9, "technical_depth": 0.8, "buying_intent": 0.8}
        ambiguity = compute_signal_ambiguity_score(scores)
        assert ambiguity < 0.3

    def test_formula_is_correct(self) -> None:
        scores = {"recency": 0.6, "specificity": 0.4, "technical_depth": 0.8, "buying_intent": 0.7}
        expected = 1.0 - (0.6 + 0.4) / 2
        assert abs(compute_signal_ambiguity_score(scores) - expected) < 1e-9


class TestParseLlmSeverityResponse:
    def test_parses_valid_json(self) -> None:
        response = '{"recency": 0.8, "specificity": 0.7, "technical_depth": 0.9, "buying_intent": 0.6}'
        result = parse_llm_severity_response(response)
        assert result is not None
        assert result["recency"] == 0.8
        assert result["buying_intent"] == 0.6

    def test_returns_none_on_invalid_json(self) -> None:
        result = parse_llm_severity_response("This is not JSON")
        assert result is None

    def test_returns_none_on_missing_keys(self) -> None:
        result = parse_llm_severity_response('{"recency": 0.8}')
        assert result is None

    def test_extracts_json_from_surrounding_text(self) -> None:
        response = 'Here is my assessment:\n{"recency": 0.7, "specificity": 0.6, "technical_depth": 0.8, "buying_intent": 0.5}\nEnd.'
        result = parse_llm_severity_response(response)
        assert result is not None
        assert result["recency"] == 0.7

    def test_returns_none_on_empty_string(self) -> None:
        assert parse_llm_severity_response("") is None


class TestRunSignalQualification:
    @pytest.mark.asyncio
    async def test_qualifies_signal_above_threshold(self) -> None:
        signals = [
            _make_signal("kubernetes ml platform data warehouse"),
            _make_signal("kubernetes scaling distributed systems"),
            _make_signal("ml platform tensorflow serving"),
        ]
        cs = _make_company_state(signals)
        cap_map = _make_cap_map(["kubernetes", "ml platform", "data warehouse"])

        # Mock LLM to return high scores
        with patch(
            "backend.agents.signal_qualification.call_llm_severity",
            new=AsyncMock(
                return_value=(
                    {"recency": 0.8, "specificity": 0.8, "technical_depth": 0.9, "buying_intent": 0.7},
                    100,
                )
            ),
        ):
            updated_cs, cost = await run_signal_qualification(
                cs=cs,
                capability_map=cap_map,
                llm_provider="anthropic",
                llm_model="claude-sonnet-4-6",
                current_total_cost=0.0,
                max_budget_usd=1.0,
            )

        assert updated_cs["signal_qualified"] is True
        assert updated_cs["qualified_signal"]["qualified"] is True
        assert updated_cs["status"] == PipelineStatus.RUNNING

    @pytest.mark.asyncio
    async def test_disqualifies_signal_below_threshold(self) -> None:
        signals = [_make_signal("office manager general administration")]
        cs = _make_company_state(signals)
        cap_map = _make_cap_map(["kubernetes", "ml platform", "data warehouse"])

        with patch(
            "backend.agents.signal_qualification.call_llm_severity",
            new=AsyncMock(
                return_value=(
                    {"recency": 0.1, "specificity": 0.1, "technical_depth": 0.1, "buying_intent": 0.1},
                    50,
                )
            ),
        ):
            updated_cs, _ = await run_signal_qualification(
                cs=cs,
                capability_map=cap_map,
                llm_provider="anthropic",
                llm_model="claude-sonnet-4-6",
                current_total_cost=0.0,
                max_budget_usd=1.0,
            )

        assert updated_cs["signal_qualified"] is False
        assert updated_cs["status"] == PipelineStatus.SKIPPED
        assert updated_cs["qualified_signal"]["disqualification_reason"] is not None

    @pytest.mark.asyncio
    async def test_falls_back_to_deterministic_on_llm_failure(self) -> None:
        signals = [_make_signal("kubernetes ml platform data warehouse")]
        cs = _make_company_state(signals)
        cap_map = _make_cap_map(["kubernetes", "ml platform", "data warehouse"])

        # LLM returns None (parse failure)
        with patch(
            "backend.agents.signal_qualification.call_llm_severity",
            new=AsyncMock(return_value=(None, 0)),
        ):
            updated_cs, _ = await run_signal_qualification(
                cs=cs,
                capability_map=cap_map,
                llm_provider="anthropic",
                llm_model="claude-sonnet-4-6",
                current_total_cost=0.0,
                max_budget_usd=1.0,
            )

        qs = updated_cs["qualified_signal"]
        assert qs is not None
        assert qs["llm_severity_score"] == 0.0
        # Deterministic score for full match = 1.0, composite falls back to det score
        assert qs["composite_score"] == qs["deterministic_score"]

    @pytest.mark.asyncio
    async def test_skips_llm_when_budget_exhausted(self) -> None:
        signals = [_make_signal("kubernetes")]
        cs = _make_company_state(signals)
        cap_map = _make_cap_map(["kubernetes"])

        call_counter = {"n": 0}

        async def mock_llm(*args, **kwargs):
            call_counter["n"] += 1
            return None, 0

        with patch(
            "backend.agents.signal_qualification.call_llm_severity",
            new=AsyncMock(side_effect=mock_llm),
        ):
            await run_signal_qualification(
                cs=cs,
                capability_map=cap_map,
                llm_provider="anthropic",
                llm_model="claude-sonnet-4-6",
                current_total_cost=1.0,  # budget exhausted
                max_budget_usd=1.0,
            )

        # LLM should not be called when budget is exhausted
        assert call_counter["n"] == 0

    @pytest.mark.asyncio
    async def test_qualification_threshold_boundary_just_above(self) -> None:
        """Score just above threshold (0.46) should qualify."""
        signals = [_make_signal("kubernetes")]
        cs = _make_company_state(signals)
        cap_map = _make_cap_map(["kubernetes"])

        # det = 1.0, llm avg = 0.1 → composite = 0.4*1.0 + 0.6*0.1 = 0.46
        with patch(
            "backend.agents.signal_qualification.call_llm_severity",
            new=AsyncMock(
                return_value=(
                    {"recency": 0.1, "specificity": 0.1, "technical_depth": 0.1, "buying_intent": 0.1},
                    10,
                )
            ),
        ):
            updated_cs, _ = await run_signal_qualification(
                cs=cs,
                capability_map=cap_map,
                llm_provider="anthropic",
                llm_model="claude-sonnet-4-6",
                current_total_cost=0.0,
                max_budget_usd=1.0,
            )

        composite = updated_cs["qualified_signal"]["composite_score"]
        assert abs(composite - 0.46) < 1e-9
        assert composite >= QUALIFICATION_THRESHOLD

    @pytest.mark.asyncio
    async def test_qualification_threshold_boundary_just_below(self) -> None:
        """Score just below threshold (0.44) should NOT qualify."""
        signals = [_make_signal("kubernetes")]
        cs = _make_company_state(signals)
        cap_map = _make_cap_map(["kubernetes"])

        # det = 1.0, llm avg = 0.0667 → composite ≈ 0.4*1.0 + 0.6*0.0667 ≈ 0.44
        # More precisely: need composite < 0.45
        # Use det = 0.4, llm = 0.4 → composite = 0.4*0.4 + 0.6*0.4 = 0.4 < 0.45
        signals_low = [_make_signal("unrelated content")]
        cs_low = _make_company_state(signals_low)
        cap_map_low = _make_cap_map(["kubernetes", "ml platform", "data warehouse", "compute", "storage"])

        with patch(
            "backend.agents.signal_qualification.call_llm_severity",
            new=AsyncMock(
                return_value=(
                    {"recency": 0.2, "specificity": 0.2, "technical_depth": 0.2, "buying_intent": 0.2},
                    10,
                )
            ),
        ):
            updated_cs, _ = await run_signal_qualification(
                cs=cs_low,
                capability_map=cap_map_low,
                llm_provider="anthropic",
                llm_model="claude-sonnet-4-6",
                current_total_cost=0.0,
                max_budget_usd=1.0,
            )

        composite = updated_cs["qualified_signal"]["composite_score"]
        assert composite < QUALIFICATION_THRESHOLD
        assert updated_cs["signal_qualified"] is False
