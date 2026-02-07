"""Helpers for reading secrets from env or macOS Keychain."""

from __future__ import annotations

import os
import subprocess


def get_env_or_keychain(
    env_var: str,
    keychain_service: str,
    user_env: str = "USER",
    allow_missing: bool = False,
) -> str | None:
    """Return env var if set, else fallback to Keychain lookup."""
    value = os.environ.get(env_var)
    if value:
        return value

    cmd = ["security", "find-generic-password", "-s", keychain_service]
    user = os.environ.get(user_env, "")
    if user:
        cmd += ["-a", user]
    cmd.append("-w")

    try:
        # Add timeout to prevent hanging on Keychain prompts
        output = subprocess.check_output(cmd, text=True, timeout=5).strip()
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        output = ""

    if output:
        return output
    if allow_missing:
        return None

    raise RuntimeError(
        f"No {env_var} found. Set env var or add to Keychain: "
        f"security add-generic-password -s '{keychain_service}' -a \"$USER\" -w '<KEY>'"
    )


def get_secret_env(
    env_var: str,
    keychain_service: str,
    user_env: str = "USER",
    allow_missing: bool = False,
) -> str | None:
    """Alias for get_env_or_keychain to match spec wording."""
    return get_env_or_keychain(
        env_var,
        keychain_service,
        user_env=user_env,
        allow_missing=allow_missing,
    )


def require_env(env_var: str) -> str:
    """Return required env var or raise a clear error."""
    value = os.environ.get(env_var)
    if value:
        return value
    raise RuntimeError(f"{env_var} environment variable not set")
