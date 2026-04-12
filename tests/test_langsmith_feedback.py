"""Tests for LangSmith feedback logging on draft approve/reject."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from backend.utils.langsmith_feedback import log_draft_feedback, store_approved_draft_as_example


class TestLogDraftFeedback:
    def test_approval_logs_positive_feedback(self) -> None:
        """Approving a draft logs score=1.0 with key='draft-quality'."""
        mock_client = MagicMock()
        with (
            patch.dict("os.environ", {"LANGCHAIN_TRACING_V2": "true"}),
            patch("langsmith.Client", return_value=mock_client),
        ):
            log_draft_feedback(run_id="run-123", approved=True)

        mock_client.create_feedback.assert_called_once_with(
            run_id="run-123",
            key="draft-quality",
            score=1.0,
            comment=None,
        )

    def test_rejection_logs_negative_feedback(self) -> None:
        """Rejecting (regenerating) a draft logs score=0.0."""
        mock_client = MagicMock()
        with (
            patch.dict("os.environ", {"LANGCHAIN_TRACING_V2": "true"}),
            patch("langsmith.Client", return_value=mock_client),
        ):
            log_draft_feedback(run_id="run-456", approved=False, comment="Tone was off")

        mock_client.create_feedback.assert_called_once_with(
            run_id="run-456",
            key="draft-quality",
            score=0.0,
            comment="Tone was off",
        )

    def test_noop_when_tracing_disabled(self) -> None:
        """No feedback logged when LANGCHAIN_TRACING_V2 is not 'true'."""
        mock_client = MagicMock()
        with (
            patch.dict("os.environ", {"LANGCHAIN_TRACING_V2": "false"}),
            patch("langsmith.Client", return_value=mock_client),
        ):
            log_draft_feedback(run_id="run-789", approved=True)

        mock_client.create_feedback.assert_not_called()

    def test_noop_when_tracing_env_missing(self) -> None:
        """No feedback logged when LANGCHAIN_TRACING_V2 is unset."""
        mock_client = MagicMock()
        with (
            patch.dict("os.environ", {}, clear=True),
            patch("langsmith.Client", return_value=mock_client),
        ):
            log_draft_feedback(run_id="run-000", approved=True)

        mock_client.create_feedback.assert_not_called()

    def test_noop_when_run_id_is_none(self) -> None:
        """No feedback logged when run_id is None."""
        mock_client = MagicMock()
        with (
            patch.dict("os.environ", {"LANGCHAIN_TRACING_V2": "true"}),
            patch("langsmith.Client", return_value=mock_client),
        ):
            log_draft_feedback(run_id=None, approved=True)

        mock_client.create_feedback.assert_not_called()

    def test_noop_when_langsmith_not_installed(self) -> None:
        """Graceful no-op when langsmith package is not installed."""
        with (
            patch.dict("os.environ", {"LANGCHAIN_TRACING_V2": "true"}),
            patch.dict("sys.modules", {"langsmith": None}),
        ):
            # Should not raise
            log_draft_feedback(run_id="run-abc", approved=True)

    def test_handles_client_exception_gracefully(self) -> None:
        """Feedback failure is logged as warning, not raised."""
        mock_client = MagicMock()
        mock_client.create_feedback.side_effect = RuntimeError("API error")
        with (
            patch.dict("os.environ", {"LANGCHAIN_TRACING_V2": "true"}),
            patch("langsmith.Client", return_value=mock_client),
        ):
            # Should not raise
            log_draft_feedback(run_id="run-err", approved=True)

        mock_client.create_feedback.assert_called_once()


# --- Helper for store_approved_draft_as_example tests ---

_EXAMPLE_KWARGS = dict(
    signal_summary="ML hiring spike",
    signal_category="hiring",
    persona_title="VP Engineering",
    persona_role_type="technical_buyer",
    technical_context="Scaling ML infra",
    subject_line="Re: ML platform growth",
    body="Hi, noticed your ML hiring...",
    confidence_score=0.85,
)


class TestStoreApprovedDraftAsExample:
    def test_creates_example_in_dataset(self) -> None:
        """Approved draft is stored as a LangSmith dataset example."""
        mock_client = MagicMock()
        with (
            patch.dict("os.environ", {"LANGCHAIN_TRACING_V2": "true"}),
            patch("langsmith.Client", return_value=mock_client),
        ):
            store_approved_draft_as_example(**_EXAMPLE_KWARGS)

        mock_client.create_example.assert_called_once_with(
            inputs={
                "signal_summary": "ML hiring spike",
                "persona_title": "VP Engineering",
                "persona_role_type": "technical_buyer",
                "technical_context": "Scaling ML infra",
            },
            outputs={
                "subject_line": "Re: ML platform growth",
                "body": "Hi, noticed your ML hiring...",
            },
            metadata={
                "signal_category": "hiring",
                "persona_role_type": "technical_buyer",
                "confidence_score": 0.85,
            },
            dataset_name="signalforge-approved-drafts",
        )

    def test_creates_dataset_if_missing(self) -> None:
        """Dataset is created when read_dataset raises."""
        mock_client = MagicMock()
        mock_client.read_dataset.side_effect = Exception("Not found")
        with (
            patch.dict("os.environ", {"LANGCHAIN_TRACING_V2": "true"}),
            patch("langsmith.Client", return_value=mock_client),
        ):
            store_approved_draft_as_example(**_EXAMPLE_KWARGS)

        mock_client.create_dataset.assert_called_once_with(
            "signalforge-approved-drafts",
            description="Approved drafts for SignalForge evaluation",
        )
        mock_client.create_example.assert_called_once()

    def test_noop_when_tracing_disabled(self) -> None:
        """No dataset example stored when tracing is disabled."""
        mock_client = MagicMock()
        with (
            patch.dict("os.environ", {"LANGCHAIN_TRACING_V2": "false"}),
            patch("langsmith.Client", return_value=mock_client),
        ):
            store_approved_draft_as_example(**_EXAMPLE_KWARGS)

        mock_client.create_example.assert_not_called()

    def test_noop_when_langsmith_not_installed(self) -> None:
        """Graceful no-op when langsmith is not installed."""
        with (
            patch.dict("os.environ", {"LANGCHAIN_TRACING_V2": "true"}),
            patch.dict("sys.modules", {"langsmith": None}),
        ):
            store_approved_draft_as_example(**_EXAMPLE_KWARGS)

    def test_handles_exception_gracefully(self) -> None:
        """Client errors are logged as warnings, not raised."""
        mock_client = MagicMock()
        mock_client.create_example.side_effect = RuntimeError("API error")
        with (
            patch.dict("os.environ", {"LANGCHAIN_TRACING_V2": "true"}),
            patch("langsmith.Client", return_value=mock_client),
        ):
            store_approved_draft_as_example(**_EXAMPLE_KWARGS)

        mock_client.create_example.assert_called_once()
