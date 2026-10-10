import io
import json
import os
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from apps.api.llm import (
    LLMConfigurationError,
    LLMProviderError,
    LLMQuotaError,
    generate_answer,
)


class GenerateAnswerTests(unittest.TestCase):
    def test_sends_server_side_gemini_request_and_returns_answer(self):
        response = io.BytesIO(
            json.dumps(
                {
                    "candidates": [
                        {"content": {"parts": [{"text": "  A sourced answer.  "}]}}
                    ]
                }
            ).encode("utf-8")
        )
        environment = {
            "LLM_PROVIDER": "gemini",
            "LLM_API_KEY": "test-key",
            "LLM_MODEL": "gemini-test-model",
        }
        with patch.dict(os.environ, environment), patch(
            "apps.api.llm.urlopen", return_value=response
        ) as open_url:
            answer = generate_answer("What is in the file?", "[report.pdf, chunk 0]\nFacts")

        request = open_url.call_args.args[0]
        request_body = json.loads(request.data.decode("utf-8"))
        self.assertEqual(answer, "A sourced answer.")
        self.assertEqual(request.headers["X-goog-api-key"], "test-key")
        self.assertIn("/gemini-test-model:generateContent", request.full_url)
        self.assertIn("report.pdf", request_body["contents"][0]["parts"][0]["text"])
        self.assertEqual(open_url.call_args.kwargs["timeout"], 30.0)

    def test_requires_api_key_without_calling_provider(self):
        with patch.dict(os.environ, {"LLM_PROVIDER": "gemini"}, clear=True):
            with patch("apps.api.llm.urlopen") as open_url:
                with self.assertRaises(LLMConfigurationError):
                    generate_answer("question", "context")
        open_url.assert_not_called()

    def test_uses_pinned_model_when_model_is_not_configured(self):
        response = io.BytesIO(
            json.dumps(
                {"candidates": [{"content": {"parts": [{"text": "Answer"}]}}]}
            ).encode("utf-8")
        )
        with patch.dict(
            os.environ,
            {"LLM_PROVIDER": "gemini", "LLM_API_KEY": "test-key"},
            clear=True,
        ), patch("apps.api.llm.urlopen", return_value=response) as open_url:
            generate_answer("question", "context")

        request = open_url.call_args.args[0]
        self.assertIn("/gemini-3.5-flash-lite:generateContent", request.full_url)

    def test_rejects_unsupported_provider(self):
        with patch.dict(
            os.environ,
            {"LLM_PROVIDER": "other", "LLM_API_KEY": "test-key"},
            clear=True,
        ):
            with self.assertRaises(LLMConfigurationError):
                generate_answer("question", "context")

    def test_maps_free_tier_quota_response(self):
        error = HTTPError("https://example.test", 429, "quota", {}, None)
        with patch.dict(
            os.environ,
            {"LLM_PROVIDER": "gemini", "LLM_API_KEY": "test-key"},
            clear=True,
        ), patch("apps.api.llm.urlopen", side_effect=error):
            with self.assertRaises(LLMQuotaError):
                generate_answer("question", "context")

    def test_rejects_response_without_generated_text(self):
        response = io.BytesIO(b'{"candidates":[]}')
        with patch.dict(
            os.environ,
            {"LLM_PROVIDER": "gemini", "LLM_API_KEY": "test-key"},
            clear=True,
        ), patch("apps.api.llm.urlopen", return_value=response):
            with self.assertRaises(LLMProviderError):
                generate_answer("question", "context")
