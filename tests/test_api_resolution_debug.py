"""Debug test: print effective api_format, base_url, and api_key resolution."""

from __future__ import annotations

import os
import sys

# Simulate CLI overrides that would be passed to build_runtime
CLI_OVERRIDES = {
    "model": None,
    "max_turns": None,
    "base_url": None,
    "system_prompt": None,
    "api_key": None,
    "api_format": None,
    "active_profile": None,
    "permission_mode": None,
}


def test_api_resolution_debug():
    from openharness.config.settings import load_settings

    print("=" * 60)
    print("API Resolution Debug Report")
    print("=" * 60)

    # 1. Show environment variables
    print("\n[1] Environment Variables")
    env_vars = [
        "ANTHROPIC_API_KEY",
        "OPENAI_API_KEY",
        "ANTHROPIC_BASE_URL",
        "OPENAI_BASE_URL",
        "OPENHARNESS_BASE_URL",
        "ANTHROPIC_MODEL",
        "OPENHARNESS_MODEL",
        "OPENHARNESS_API_FORMAT",
        "OPENHARNESS_PROVIDER",
    ]
    for var in env_vars:
        value = os.environ.get(var, "")
        if var.endswith("KEY") and value:
            value = value[:8] + "..."  # mask API key
        print(f"  {var}: {value or '(not set)'}")

    # 2. Load settings with CLI overrides
    print("\n[2] Settings After CLI Overrides Merge")
    settings = load_settings().merge_cli_overrides(**CLI_OVERRIDES)

    print(f"  api_format : {settings.api_format!r}")
    print(f"  base_url   : {settings.base_url!r}")
    print(f"  api_key    : {settings.api_key[:8] + '...' if settings.api_key else '(not set)'!r}")
    print(f"  provider   : {settings.provider!r}")
    print(f"  model      : {settings.model!r}")
    print(f"  active_profile: {settings.active_profile!r}")

    # 3. Resolved profile
    print("\n[3] Active Profile Details")
    profile_name, profile = settings.resolve_profile()
    print(f"  profile name: {profile_name!r}")
    print(f"  provider    : {profile.provider!r}")
    print(f"  api_format  : {profile.api_format!r}")
    print(f"  base_url    : {profile.base_url!r}")
    print(f"  default_model: {profile.default_model!r}")
    print(f"  last_model  : {profile.last_model!r}")
    print(f"  resolved_model: {profile.resolved_model!r}")
    print(f"  auth_source : {profile.auth_source!r}")
    print(f"  credential_slot: {profile.credential_slot!r}")

    # 4. Auth resolution
    print("\n[4] Auth Resolution")
    try:
        auth = settings.resolve_auth()
        print(f"  provider  : {auth.provider!r}")
        print(f"  auth_kind : {auth.auth_kind!r}")
        print(f"  value     : {auth.value[:8] + '...' if auth.value else '(empty)'!r}")
        print(f"  source    : {auth.source!r}")
        print(f"  state     : {auth.state!r}")
    except ValueError as e:
        print(f"  ERROR: {e}")

    # 5. API client that would be constructed
    print("\n[5] API Client Construction")
    from openharness.ui.runtime import _resolve_api_client_from_settings
    client = _resolve_api_client_from_settings(settings)
    print(f"  client type: {type(client).__name__}")
    if hasattr(client, "_base_url"):
        print(f"  base_url   : {client._base_url!r}")
    if hasattr(client, "_api_key"):
        print(f"  api_key    : {client._api_key[:8] + '...' if client._api_key else '(not set)'!r}")
    if hasattr(client, "_auth_token"):
        print(f"  auth_token : {client._auth_token[:8] + '...' if client._auth_token else '(not set)'!r}")

    print("\n" + "=" * 60)


if __name__ == "__main__":
    main()
