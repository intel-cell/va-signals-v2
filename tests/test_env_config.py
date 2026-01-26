import subprocess

from src.secrets import get_env_or_keychain


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
