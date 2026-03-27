"""Tests for capability map generator and web crawler."""
from __future__ import annotations

import os
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.capability_map_generator import (
    CapabilityMapGeneratorInput,
    _parse_generation_response,
    generate_capability_map,
)
from backend.tools.web_crawler import _strip_html_tags


class TestStripHtmlTags:
    def test_removes_basic_tags(self) -> None:
        result = _strip_html_tags("<p>Hello <b>world</b></p>")
        assert "<" not in result
        assert "Hello" in result
        assert "world" in result

    def test_removes_script_tags(self) -> None:
        result = _strip_html_tags("<script>alert('xss')</script><p>Content</p>")
        assert "alert" not in result
        assert "Content" in result

    def test_removes_style_tags(self) -> None:
        result = _strip_html_tags("<style>.foo { color: red }</style><p>Text</p>")
        assert "color" not in result
        assert "Text" in result

    def test_collapses_whitespace(self) -> None:
        result = _strip_html_tags("<p>Hello   World</p>")
        assert "Hello World" in result

    def test_handles_empty_string(self) -> None:
        assert _strip_html_tags("") == ""


class TestParseGenerationResponse:
    def test_parses_valid_response(self) -> None:
        response = """{
          "capabilities": [
            {
              "id": "data_platform",
              "label": "Data Platform",
              "problem_signals": ["data warehouse", "etl pipeline"],
              "solution_areas": ["Columnar storage", "Query optimization"]
            }
          ]
        }"""
        result = _parse_generation_response(response)
        assert len(result) == 1
        assert result[0]["id"] == "data_platform"
        assert result[0]["label"] == "Data Platform"
        assert "data warehouse" in result[0]["problem_signals"]

    def test_returns_empty_on_invalid_json(self) -> None:
        assert _parse_generation_response("not json") == []

    def test_returns_empty_on_missing_capabilities(self) -> None:
        assert _parse_generation_response('{"version": "1.0"}') == []

    def test_skips_entries_missing_required_fields(self) -> None:
        response = '{"capabilities": [{"problem_signals": ["test"]}]}'
        result = _parse_generation_response(response)
        assert result == []

    def test_extracts_json_from_prose(self) -> None:
        response = 'Here is the map: {"capabilities": [{"id": "ml", "label": "ML Infra", "problem_signals": [], "solution_areas": []}]}'
        result = _parse_generation_response(response)
        assert len(result) == 1


class TestGenerateCapabilityMap:
    @pytest.mark.asyncio
    async def test_returns_none_without_llm_model(self) -> None:
        inputs = CapabilityMapGeneratorInput(product_list="Product A\nProduct B")
        result = await generate_capability_map(inputs, llm_model="")
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_with_no_inputs(self) -> None:
        inputs = CapabilityMapGeneratorInput()
        result = await generate_capability_map(inputs, llm_model="claude-sonnet-4-6")
        assert result is None

    @pytest.mark.asyncio
    async def test_generates_capability_map_from_product_list(self) -> None:
        """Mocked LLM response generates a capability map and saves it."""
        llm_response = """{
          "capabilities": [
            {
              "id": "data_platform",
              "label": "Data Platform",
              "problem_signals": ["data warehouse", "query performance", "etl pipeline"],
              "solution_areas": ["Columnar storage optimization", "Distributed query execution"]
            },
            {
              "id": "ml_infra",
              "label": "ML Infrastructure",
              "problem_signals": ["ml platform", "model training", "gpu cluster"],
              "solution_areas": ["ML pipeline automation", "Distributed training orchestration"]
            }
          ]
        }"""

        with tempfile.TemporaryDirectory() as tmpdir:
            map_path = os.path.join(tmpdir, "capability_map.yaml")
            os.environ["SIGNALFORGE_CAPABILITY_MAP_PATH"] = map_path

            try:
                with patch(
                    "backend.capability_map_generator.ChatAnthropic"
                ) as MockLLM:
                    mock_response = MagicMock()
                    mock_response.content = llm_response
                    MockLLM.return_value.ainvoke = AsyncMock(return_value=mock_response)

                    inputs = CapabilityMapGeneratorInput(
                        product_list="DataWarehouse Pro\nML Platform\nQuery Engine"
                    )
                    result = await generate_capability_map(
                        inputs, llm_model="claude-sonnet-4-6"
                    )
            finally:
                os.environ.pop("SIGNALFORGE_CAPABILITY_MAP_PATH", None)

        assert result is not None
        assert len(result.entries) == 2
        assert result.entries[0].id == "data_platform"
        assert "data warehouse" in result.entries[0].problem_signals

    @pytest.mark.asyncio
    async def test_combines_multiple_inputs(self) -> None:
        """Product list + territory both contribute to the LLM prompt."""
        called_with_prompts: list[str] = []

        async def capture_prompt(messages):
            for msg in messages:
                called_with_prompts.append(msg.content)
            mock = MagicMock()
            mock.content = '{"capabilities": [{"id": "test", "label": "Test", "problem_signals": ["p1"], "solution_areas": ["a1"]}]}'
            return mock

        with tempfile.TemporaryDirectory() as tmpdir:
            map_path = os.path.join(tmpdir, "capability_map.yaml")
            os.environ["SIGNALFORGE_CAPABILITY_MAP_PATH"] = map_path

            try:
                with patch(
                    "backend.capability_map_generator.ChatAnthropic"
                ) as MockLLM:
                    MockLLM.return_value.ainvoke = capture_prompt

                    inputs = CapabilityMapGeneratorInput(
                        product_list="Product A",
                        territory="Financial services data analytics",
                    )
                    await generate_capability_map(inputs, llm_model="claude-sonnet-4-6")
            finally:
                os.environ.pop("SIGNALFORGE_CAPABILITY_MAP_PATH", None)

        assert len(called_with_prompts) > 0
        combined = called_with_prompts[0]
        assert "Product A" in combined
        assert "Financial services" in combined
