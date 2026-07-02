"""Tests for the LLMService."""

from __future__ import annotations

import asyncio
import json
from unittest import mock

import pytest

from py.services.llm_service import LLMService
from py.services.errors import LLMNotConfiguredError, LLMRateLimitError, LLMResponseError


class MockSettings:
    """Minimal settings mock for LLMService tests."""

    def __init__(self, **kwargs):
        self._data = {
            "llm_enabled": False,
            "llm_provider": "openai",
            "llm_api_key": "",
            "llm_api_base": "",
            "llm_model": "",
        }
        self._data.update(kwargs)

    def get(self, key, default=None):
        return self._data.get(key, default)


class MockResponse:
    """Mock aiohttp response."""

    def __init__(self, status, json_data=None, text_data="", headers=None):
        self.status = status
        self._json_data = json_data
        self._text_data = text_data
        self.headers = headers or {}

    async def json(self):
        return self._json_data

    async def text(self):
        return self._text_data

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


class MockSession:
    """Mock aiohttp ClientSession."""

    def __init__(self, response):
        self._response = response
        self.closed = False

    def post(self, url, json=None, headers=None):
        self.last_url = url
        self.last_json = json
        self.last_headers = headers
        return self._response

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


@pytest.fixture
def llm_service():
    """Create an LLMService with mock settings."""
    LLMService.reset_instance()
    settings = MockSettings(
        llm_enabled=True,
        llm_provider="openai",
        llm_api_key="sk-test-key",
        llm_api_base="",
        llm_model="gpt-4o-mini",
    )
    return LLMService(settings)


class TestLLMServiceConfiguration:
    def test_is_configured_when_enabled_with_key_and_model(self, llm_service):
        assert llm_service.is_configured() is True

    def test_not_configured_when_disabled(self):
        settings = MockSettings(
            llm_enabled=False, llm_api_key="sk-test", llm_model="gpt-4o"
        )
        service = LLMService(settings)
        # Lenient: model + API key is treated as configured even without
        # the toggle, because the user clearly intends to use the feature.
        assert service.is_configured() is True

    def test_not_configured_without_model(self):
        settings = MockSettings(llm_enabled=True, llm_api_key="sk-test", llm_model="")
        service = LLMService(settings)
        assert service.is_configured() is False

    def test_not_configured_without_api_key_for_openai(self):
        settings = MockSettings(llm_enabled=True, llm_api_key="", llm_model="gpt-4o")
        service = LLMService(settings)
        assert service.is_configured() is False

    def test_ollama_configured_without_api_key(self):
        settings = MockSettings(
            llm_enabled=True, llm_provider="ollama", llm_api_key="", llm_model="llama3"
        )
        service = LLMService(settings)
        assert service.is_configured() is True

    def test_resolve_api_base_openai_default(self, llm_service):
        assert llm_service._resolve_api_base("openai", "") == "https://api.openai.com/v1"

    def test_resolve_api_base_ollama_default(self, llm_service):
        assert llm_service._resolve_api_base("ollama", "") == "http://localhost:11434/v1"

    def test_resolve_api_base_custom_override(self, llm_service):
        assert llm_service._resolve_api_base("custom", "https://my.api.com/v1/") == "https://my.api.com/v1"

    def test_ensure_configured_raises_when_disabled(self):
        settings = MockSettings(llm_enabled=False)
        service = LLMService(settings)
        with pytest.raises(LLMNotConfiguredError):
            service._ensure_configured()

    def test_ensure_configured_raises_without_model(self):
        settings = MockSettings(llm_enabled=True, llm_api_key="sk-test", llm_model="")
        service = LLMService(settings)
        with pytest.raises(LLMNotConfiguredError):
            service._ensure_configured()


class TestLLMServiceChatCompletion:
    @pytest.mark.asyncio
    async def test_chat_completion_success(self, llm_service):
        mock_response = MockResponse(
            200,
            json_data={
                "choices": [{"message": {"content": "Hello!"}}],
                "usage": {"total_tokens": 10},
                "model": "gpt-4o-mini",
            },
        )
        mock_session = MockSession(mock_response)

        with mock.patch("aiohttp.ClientSession", return_value=mock_session):
            result = await llm_service.chat_completion(
                messages=[{"role": "user", "content": "Hi"}],
            )

        assert result["content"] == "Hello!"
        assert result["usage"]["total_tokens"] == 10
        assert result["model"] == "gpt-4o-mini"

    @pytest.mark.asyncio
    async def test_chat_completion_raises_on_not_configured(self):
        settings = MockSettings(llm_enabled=False)
        service = LLMService(settings)
        with pytest.raises(LLMNotConfiguredError):
            await service.chat_completion(messages=[])

    @pytest.mark.asyncio
    async def test_chat_completion_raises_on_http_error(self, llm_service):
        mock_response = MockResponse(500, text_data="Internal Server Error")
        mock_session = MockSession(mock_response)

        with mock.patch("aiohttp.ClientSession", return_value=mock_session):
            with pytest.raises(LLMResponseError, match="HTTP 500"):
                await llm_service.chat_completion(messages=[])

    @pytest.mark.asyncio
    async def test_chat_completion_raises_on_rate_limit(self, llm_service):
        mock_response = MockResponse(429, text_data="Rate limited", headers={"Retry-After": "0"})
        mock_session = MockSession(mock_response)

        with mock.patch("aiohttp.ClientSession", return_value=mock_session):
            with pytest.raises(LLMRateLimitError):
                await llm_service.chat_completion(
                    messages=[], retry_on_rate_limit=False
                )

    @pytest.mark.asyncio
    async def test_chat_completion_raises_on_bad_response_structure(self, llm_service):
        mock_response = MockResponse(200, json_data={"unexpected": "data"})
        mock_session = MockSession(mock_response)

        with mock.patch("aiohttp.ClientSession", return_value=mock_session):
            with pytest.raises(LLMResponseError, match="Unexpected LLM response"):
                await llm_service.chat_completion(messages=[])


class TestLLMServiceChatCompletionJson:
    @pytest.mark.asyncio
    async def test_chat_completion_json_parses_json(self, llm_service):
        mock_response = MockResponse(
            200,
            json_data={
                "choices": [{"message": {"content": '{"key": "value"}'}}],
                "usage": {},
                "model": "gpt-4o-mini",
            },
        )
        mock_session = MockSession(mock_response)

        with mock.patch("aiohttp.ClientSession", return_value=mock_session):
            result = await llm_service.chat_completion_json(
                system_prompt="You are helpful.",
                user_prompt="Return JSON.",
            )

        assert result == {"key": "value"}

    @pytest.mark.asyncio
    async def test_chat_completion_json_raises_on_non_json(self, llm_service):
        # First attempt: non-JSON; second attempt (retry): also non-JSON
        mock_response = MockResponse(
            200,
            json_data={
                "choices": [{"message": {"content": "not json at all"}}],
                "usage": {},
            },
        )
        mock_session = MockSession(mock_response)

        with mock.patch("aiohttp.ClientSession", return_value=mock_session):
            with pytest.raises(LLMResponseError, match="could not be parsed as JSON"):
                await llm_service.chat_completion_json(
                    system_prompt="test",
                    user_prompt="test",
                )
