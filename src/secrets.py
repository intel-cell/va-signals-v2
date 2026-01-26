"""Helpers for reading secrets from env or macOS Keychain."""

from __future__ import annotations

import os
import subprocess
from typing import Optional


def get_env_or_keychain(
    env_var: str,
    keychain_service: str,
    user_env: str = "USER",
    allow_missing: bool = False,
) -> Optional[str]:
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
        output = subprocess.check_output(cmd, text=True).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        output = ""

    if output:
        return output
    if allow_missing:
        return None

    raise RuntimeError(
        f"No {env_var} found. Set env var or add to Keychain: "
        f"security add-generic-password -s '{keychain_service}' -a \"$USER\" -w '<KEY>'"
    )
