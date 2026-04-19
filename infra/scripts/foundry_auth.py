#!/usr/bin/env python3
"""
Automatic LLM authentication via foundry_aws_gateway.

Extracts credentials for Gemini (Vertex AI) and GPT-5 (Azure OpenAI) from
foundry_aws_gateway and outputs environment variables for use with litellm
in Harbor benchmark runs.

Usage:
    # Get Gemini credentials
    eval "$(python3 foundry_auth.py gemini)"

    # Get Azure OpenAI (GPT-5) credentials
    eval "$(python3 foundry_auth.py azure)"

    # Get all credentials as JSON
    python3 foundry_auth.py all --json

    # Test all providers
    python3 foundry_auth.py all --test

    # Generate Harbor --ae flags for Gemini
    python3 foundry_auth.py gemini --harbor-ae

Model strings for Harbor/litellm:
    Gemini:   openai/google/gemini-2.5-flash   (via Vertex AI OpenAI-compat endpoint)
    Gemini:   openai/google/gemini-2.5-pro
    GPT-5:    azure/gpt-5                       (via Azure OpenAI)

Prerequisites:
    - foundry_aws_gateway[llm] installed
    - PLUTO_AUTH_TOKEN set (auto-injected on Pluto pods)
"""

import argparse
import json
import sys
import time


def get_gemini_credentials():
    """Get Gemini/Vertex AI credentials."""
    import foundry_aws_gateway.llm as llm

    creds = llm.get_gcp_credentials()
    location = "us-west1"
    base_url = (
        f"https://{location}-aiplatform.googleapis.com/v1/"
        f"projects/{creds.project_id}/locations/{location}/endpoints/openapi"
    )

    remaining_min = (creds.expiration_epoch - time.time()) / 60
    return {
        "env": {
            "GEMINI_VERTEX_TOKEN": creds.token,
            "GEMINI_VERTEX_BASE_URL": base_url,
            "GEMINI_VERTEX_PROJECT": creds.project_id,
            "GEMINI_VERTEX_LOCATION": location,
            "GEMINI_TOKEN_EXPIRY": str(int(creds.expiration_epoch)),
        },
        "token_valid_minutes": round(remaining_min, 1),
        "models": [
            "openai/google/gemini-2.5-flash",
            "openai/google/gemini-2.5-flash-lite",
            "openai/google/gemini-2.5-pro",
            "openai/google/gemini-2.0-flash",
        ],
        "litellm_config": {
            "api_key_env": "GEMINI_VERTEX_TOKEN",
            "api_base_env": "GEMINI_VERTEX_BASE_URL",
        },
    }


def get_azure_credentials():
    """Get Azure OpenAI (GPT-5) credentials."""
    import foundry_aws_gateway.llm as llm

    creds = llm.get_azure_credentials()
    remaining_min = (creds.expiration_epoch - time.time()) / 60

    return {
        "env": {
            "AZURE_API_KEY": creds.token,
            "AZURE_API_BASE": creds.endpoint,
            "AZURE_API_VERSION": "2025-04-01-preview",
        },
        "token_valid_minutes": round(remaining_min, 1),
        "models": ["azure/gpt-5"],
        "litellm_config": {
            "api_key_env": "AZURE_API_KEY",
            "api_base_env": "AZURE_API_BASE",
        },
    }


def test_gemini(creds_info):
    """Test Gemini token."""
    import requests

    env = creds_info["env"]
    url = (
        f"https://{env['GEMINI_VERTEX_LOCATION']}-aiplatform.googleapis.com/v1/"
        f"projects/{env['GEMINI_VERTEX_PROJECT']}/"
        f"locations/{env['GEMINI_VERTEX_LOCATION']}/"
        f"publishers/google/models/gemini-2.5-flash:generateContent"
    )
    headers = {
        "Authorization": f"Bearer {env['GEMINI_VERTEX_TOKEN']}",
        "Content-Type": "application/json",
    }
    data = {"contents": [{"role": "user", "parts": [{"text": "Say hello"}]}]}

    resp = requests.post(url, headers=headers, json=data, timeout=30)
    if resp.ok:
        text = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
        print(
            f"  Gemini OK ({creds_info['token_valid_minutes']:.0f}m remaining): {text}",
            file=sys.stderr,
        )
        return True
    else:
        print(f"  Gemini FAIL: {resp.status_code} {resp.text[:200]}", file=sys.stderr)
        return False


def test_azure(creds_info):
    """Test Azure OpenAI token."""
    import openai

    env = creds_info["env"]
    client = openai.AzureOpenAI(
        api_key=env["AZURE_API_KEY"],
        azure_endpoint=env["AZURE_API_BASE"],
        api_version=env["AZURE_API_VERSION"],
    )
    try:
        resp = client.chat.completions.create(
            model="gpt-5",
            messages=[{"role": "user", "content": "Say hello"}],
            max_completion_tokens=20,
        )
        print(f"  Azure GPT-5 OK: {resp.choices[0].message.content}", file=sys.stderr)
        return True
    except Exception as e:
        print(f"  Azure GPT-5 FAIL: {e}", file=sys.stderr)
        return False


def main():
    parser = argparse.ArgumentParser(description="Get LLM auth credentials")
    parser.add_argument(
        "provider",
        choices=["gemini", "azure", "all"],
        help="Which provider to authenticate",
    )
    parser.add_argument("--json", action="store_true", help="JSON output")
    parser.add_argument("--test", action="store_true", help="Test credentials")
    parser.add_argument(
        "--harbor-ae", action="store_true", help="Output as Harbor --ae flags"
    )
    parser.add_argument(
        "--token-only", action="store_true", help="Output only the token"
    )
    args = parser.parse_args()

    try:
        import foundry_aws_gateway.llm  # noqa: F401
    except ImportError:
        print(
            "ERROR: foundry_aws_gateway[llm] not installed.\n"
            "Install: pip install foundry-aws-gateway[llm] "
            '--extra-index-url "https://:${ARTIFACTORY_UW2_API_TOKEN}'
            '@artifactory-uw2.adobeitc.com/artifactory/api/pypi/'
            'pypi-adobeshared-release/simple"',
            file=sys.stderr,
        )
        sys.exit(1)

    providers = {}
    if args.provider in ("gemini", "all"):
        try:
            providers["gemini"] = get_gemini_credentials()
        except Exception as e:
            print(f"ERROR getting Gemini creds: {e}", file=sys.stderr)
            if args.provider == "gemini":
                sys.exit(1)

    if args.provider in ("azure", "all"):
        try:
            providers["azure"] = get_azure_credentials()
        except Exception as e:
            print(f"ERROR getting Azure creds: {e}", file=sys.stderr)
            if args.provider == "azure":
                sys.exit(1)

    if args.test:
        ok = True
        if "gemini" in providers:
            ok &= test_gemini(providers["gemini"])
        if "azure" in providers:
            ok &= test_azure(providers["azure"])
        sys.exit(0 if ok else 1)

    if args.json:
        output = {}
        for name, info in providers.items():
            output[name] = {
                "env": info["env"],
                "models": info["models"],
            }
            if "token_valid_minutes" in info:
                output[name]["token_valid_minutes"] = info["token_valid_minutes"]
        print(json.dumps(output, indent=2))
        return

    # Default: shell export format or harbor-ae format
    for name, info in providers.items():
        if args.harbor_ae:
            for key, val in info["env"].items():
                print(f'--ae "{key}={val}"')
        elif args.token_only:
            for key, val in info["env"].items():
                if "TOKEN" in key or "KEY" in key:
                    print(val)
                    break
        else:
            print(f"# === {name} ===")
            for key, val in info["env"].items():
                print(f'export {key}="{val}"')
            print(f"# Models: {', '.join(info['models'])}")
            if "token_valid_minutes" in info:
                print(f"# Token valid: {info['token_valid_minutes']:.0f} min")
            print()


if __name__ == "__main__":
    main()
