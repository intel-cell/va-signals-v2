"""Tests for SSL context usage in fetchers."""

import types
from unittest.mock import MagicMock, patch

from src import fetch_bills, fetch_hearings, fetch_transcripts


class DummyResponse:
    def __init__(self, payload: bytes = b"{}"):
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self) -> bytes:
        return self._payload


def _assert_fetch_uses_certifi_context(module, fetch_fn, url: str, api_key: str | None = None):
    dummy_certifi = types.SimpleNamespace(where=lambda: "/tmp/ca.pem")
    context = object()
    create_context = MagicMock(return_value=context)
    dummy_ssl = types.SimpleNamespace(create_default_context=create_context)

    with patch.object(module, "certifi", dummy_certifi, create=True):
        with patch.object(module, "ssl", dummy_ssl, create=True):
            with patch.object(
                module.urllib.request, "urlopen", return_value=DummyResponse()
            ) as urlopen:
                if api_key is None:
                    fetch_fn(url)
                else:
                    fetch_fn(url, api_key)

    create_context.assert_called_once_with(cafile="/tmp/ca.pem")
    assert urlopen.call_args.kwargs.get("context") is context


def test_fetch_bills_fetch_json_uses_certifi_context():
    _assert_fetch_uses_certifi_context(
        fetch_bills, fetch_bills._fetch_json, "https://example.com", "key"
    )


def test_fetch_hearings_fetch_json_uses_certifi_context():
    _assert_fetch_uses_certifi_context(
        fetch_hearings, fetch_hearings._fetch_json, "https://example.com", "key"
    )


def test_fetch_transcripts_fetch_json_uses_certifi_context():
    _assert_fetch_uses_certifi_context(
        fetch_transcripts, fetch_transcripts.fetch_json, "https://example.com", "key"
    )


def test_fetch_transcripts_fetch_text_uses_certifi_context():
    dummy_certifi = types.SimpleNamespace(where=lambda: "/tmp/ca.pem")
    context = object()
    create_context = MagicMock(return_value=context)
    dummy_ssl = types.SimpleNamespace(create_default_context=create_context)

    with patch.object(fetch_transcripts, "certifi", dummy_certifi, create=True):
        with patch.object(fetch_transcripts, "ssl", dummy_ssl, create=True):
            with patch.object(
                fetch_transcripts.urllib.request,
                "urlopen",
                return_value=DummyResponse(payload=b"hello"),
            ) as urlopen:
                result = fetch_transcripts.fetch_text("https://example.com")

    assert result == "hello"
    create_context.assert_called_once_with(cafile="/tmp/ca.pem")
    assert urlopen.call_args.kwargs.get("context") is context
