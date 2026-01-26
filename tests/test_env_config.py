import subprocess

import pytest

from src.secrets import get_env_or_keychain, get_secret_env, require_env


def test_get_env_or_keychain_prefers_env(monkeypatch):
    monkeypatch.setenv("TEST_SECRET", "env-value")

    def fail_check_output(*_args, **_kwargs):
        raise AssertionError("Keychain lookup should not be called when env var is set")

    monkeypatch.setattr(subprocess, "check_output", fail_check_output)

    assert get_env_or_keychain("TEST_SECRET", "test-service") == "env-value"


def test_get_env_or_keychain_falls_back_to_keychain(monkeypatch):
    monkeypatch.delenv("TEST_SECRET", raising=False)
    monkeypatch.setenv("USER", "tester")

    captured = {}

    def fake_check_output(cmd, text=True):
        captured["cmd"] = cmd
        return "keychain-value\n"

    monkeypatch.setattr(subprocess, "check_output", fake_check_output)

    assert get_env_or_keychain("TEST_SECRET", "test-service") == "keychain-value"
    assert captured["cmd"] == [
        "security",
        "find-generic-password",
        "-s",
        "test-service",
        "-a",
        "tester",
        "-w",
    ]


def test_get_secret_env_aliases_get_env_or_keychain(monkeypatch):
    captured = {}

    def fake_get_env_or_keychain(env_var, keychain_service, user_env="USER", allow_missing=False):
        captured["args"] = (env_var, keychain_service, user_env, allow_missing)
        return "alias-value"

    monkeypatch.setattr(
        "src.secrets.get_env_or_keychain",
        fake_get_env_or_keychain,
    )

    assert get_secret_env(
        "TEST_SECRET",
        "test-service",
        user_env="CUSTOM_USER",
        allow_missing=True,
    ) == "alias-value"
    assert captured["args"] == ("TEST_SECRET", "test-service", "CUSTOM_USER", True)


def test_require_env_returns_value(monkeypatch):
    monkeypatch.setenv("REQUIRED_VALUE", "present")
    assert require_env("REQUIRED_VALUE") == "present"


def test_require_env_raises_when_missing(monkeypatch):
    monkeypatch.delenv("REQUIRED_MISSING", raising=False)
    with pytest.raises(RuntimeError, match="REQUIRED_MISSING"):
        require_env("REQUIRED_MISSING")
