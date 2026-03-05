"""Tests for LLM reranker (mock/disabled mode)."""
import os
import pytest
from unittest.mock import patch

from app.services.reranker import (
    _is_enabled,
    rerank_match,
    rerank_matches_batch,
)


class TestRerankerDisabled:
    def test_disabled_by_default(self):
        # Ensure env var not set
        with patch.dict(os.environ, {}, clear=True):
            assert _is_enabled() is False

    def test_enabled_via_env(self):
        with patch.dict(os.environ, {'ENABLE_LLM_RERANKER': 'true'}):
            assert _is_enabled() is True

    def test_rerank_returns_base_when_disabled(self):
        with patch.dict(os.environ, {}, clear=True):
            score, explanation, was_reranked = rerank_match(
                "Python Dev",
                "Looking for Python developer",
                "5 years Python experience",
                0.75,
                "3/4 keywords matched",
            )

            assert score == 0.75
            assert explanation == "3/4 keywords matched"
            assert was_reranked is False

    def test_batch_rerank_disabled(self):
        with patch.dict(os.environ, {}, clear=True):
            matches = [
                {
                    'job_title': 'Dev 1',
                    'job_description': 'Desc 1',
                    'base_score': 0.8,
                    'base_explanation': 'Exp 1',
                },
                {
                    'job_title': 'Dev 2',
                    'job_description': 'Desc 2',
                    'base_score': 0.6,
                    'base_explanation': 'Exp 2',
                },
            ]

            results = rerank_matches_batch(matches, "Resume content")

            assert len(results) == 2
            assert all(r['llm_reranked'] is False for r in results)
            assert results[0]['base_score'] == 0.8
            assert results[1]['base_score'] == 0.6


class TestRerankerEnabled:
    def test_falls_back_without_api_key(self):
        with patch.dict(os.environ, {'ENABLE_LLM_RERANKER': 'true'}, clear=True):
            score, explanation, was_reranked = rerank_match(
                "Python Dev",
                "Looking for Python developer",
                "5 years Python experience",
                0.75,
                "3/4 keywords matched",
            )

            # Should fall back gracefully
            assert score == 0.75
            assert explanation == "3/4 keywords matched"
            assert was_reranked is False


class TestRerankerParsing:
    """Test JSON response parsing logic."""

    def test_valid_json_response(self):
        # Mock the API call to return valid JSON
        mock_response = '{"score": 0.85, "explanation": "Strong Python match"}'

        with patch.dict(os.environ, {'ENABLE_LLM_RERANKER': 'true', 'OPENAI_API_KEY': 'test'}):
            with patch('app.services.reranker._call_openai', return_value=mock_response):
                score, explanation, was_reranked = rerank_match(
                    "Python Dev",
                    "Looking for Python developer",
                    "5 years Python experience",
                    0.75,
                    "3/4 keywords matched",
                )

                assert score == 0.85
                assert "[LLM]" in explanation
                assert "Strong Python match" in explanation
                assert was_reranked is True

    def test_markdown_code_block_response(self):
        # Some LLMs wrap JSON in markdown code blocks
        mock_response = '```json\n{"score": 0.9, "explanation": "Excellent fit"}\n```'

        with patch.dict(os.environ, {'ENABLE_LLM_RERANKER': 'true', 'OPENAI_API_KEY': 'test'}):
            with patch('app.services.reranker._call_openai', return_value=mock_response):
                score, explanation, was_reranked = rerank_match(
                    "Python Dev",
                    "Looking for Python developer",
                    "5 years Python experience",
                    0.75,
                    "3/4 keywords matched",
                )

                assert score == 0.9
                assert was_reranked is True

    def test_invalid_json_falls_back(self):
        mock_response = 'Not valid JSON at all'

        with patch.dict(os.environ, {'ENABLE_LLM_RERANKER': 'true', 'OPENAI_API_KEY': 'test'}):
            with patch('app.services.reranker._call_openai', return_value=mock_response):
                score, explanation, was_reranked = rerank_match(
                    "Python Dev",
                    "Looking for Python developer",
                    "5 years Python experience",
                    0.75,
                    "3/4 keywords matched",
                )

                # Falls back to base
                assert score == 0.75
                assert was_reranked is False

    def test_score_clamped_to_valid_range(self):
        # Test score > 1.0 gets clamped
        mock_response = '{"score": 1.5, "explanation": "Over-enthusiastic"}'

        with patch.dict(os.environ, {'ENABLE_LLM_RERANKER': 'true', 'OPENAI_API_KEY': 'test'}):
            with patch('app.services.reranker._call_openai', return_value=mock_response):
                score, _, _ = rerank_match(
                    "Dev", "Desc", "Resume", 0.75, "Base"
                )
                assert score == 1.0

        # Test score < 0 gets clamped
        mock_response = '{"score": -0.5, "explanation": "Negative"}'

        with patch.dict(os.environ, {'ENABLE_LLM_RERANKER': 'true', 'OPENAI_API_KEY': 'test'}):
            with patch('app.services.reranker._call_openai', return_value=mock_response):
                score, _, _ = rerank_match(
                    "Dev", "Desc", "Resume", 0.75, "Base"
                )
                assert score == 0.0
