#!/usr/bin/env python3
"""
Automatic Gemini/Vertex AI authentication via foundry_aws_gateway.

This script extracts a GCP OAuth2 access token from foundry_aws_gateway and
outputs environment variables needed to call Gemini models through Vertex AI's
OpenAI-compatible endpoint.

Usage:
    # Print env vars (source-able)
    python3 gemini_auth.py

    # Source directly in bash
    eval "$(python3 gemini_auth.py)"

    # JSON output (for programmatic use)
    python3 gemini_auth.py --json

    # Test the token
    python3 gemini_auth.py --test

    # Generate Harbor --ae flags
    python3 gemini_auth.py --harbor-ae

Prerequisites:
    - foundry_aws_gateway[llm] installed
    - PLUTO_AUTH_TOKEN set (auto-injected on Pluto pods)

How it works:
    1. foundry_aws_gateway exchanges PLUTO_AUTH_TOKEN for GCP credentials
    2. We extract the OAuth2 access token (valid ~60 minutes)
    3. We configure litellm's openai/ provider with Vertex AI's OpenAI-compatible endpoint
    4. Model string: "openai/google/gemini-2.5-flash" (or pro, lite variants)

Available models:
    - openai/google/gemini-2.5-flash       (fast, good quality)
    - openai/google/gemini-2.5-flash-lite   (fastest, lowest cost)
    - openai/google/gemini-2.5-pro          (highest quality)
    - openai/google/gemini-2.0-flash        (previous gen)
"""

import argparse
import json
import os
import sys
import time


def get_credentials():
    """Get GCP credentials from foundry_aws_gateway."""
    try:
        import foundry_aws_gateway.llm as llm
    except ImportError:
        print(
            "ERROR: foundry_aws_gateway[llm] not installed.\n"
            "Install with: pip install foundry-aws-gateway[llm] "
            '--extra-index-url "https://:${ARTIFACTORY_UW2_API_TOKEN}'
            '@artifactory-uw2.adobeitc.com/artifactory/api/pypi/pypi-adobeshared-release/simple"',
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        creds = llm.get_gcp_credentials()
    except Exception as e:
        print(f"ERROR: Failed to get GCP credentials: {e}", file=sys.stderr)
        print(
            "Make sure PLUTO_AUTH_TOKEN is set (auto-injected on Pluto pods)",
            file=sys.stderr,
        )
        sys.exit(1)

    remaining_min = (creds.expiration_epoch - time.time()) / 60
    if remaining_min < 5:
        print(
            f"WARNING: Token expires in {remaining_min:.1f} minutes",
            file=sys.stderr,
        )

    return creds


def get_env_vars(creds):
    """Return dict of environment variables for Gemini access."""
    location = "us-west1"
    base_url = (
        f"https://{location}-aiplatform.googleapis.com/v1/"
        f"projects/{creds.project_id}/locations/{location}/endpoints/openapi"
    )

    return {
        "GEMINI_VERTEX_TOKEN": creds.token,
        "GEMINI_VERTEX_BASE_URL": base_url,
        "GEMINI_VERTEX_PROJECT": creds.project_id,
        "GEMINI_VERTEX_LOCATION": location,
        "GEMINI_TOKEN_EXPIRY": str(int(creds.expiration_epoch)),
    }


def test_token(creds):
    """Test the token by making a simple API call."""
    env = get_env_vars(creds)

    # Test with direct REST API (no litellm dependency needed)
    import requests

    url = (
        f"https://{env['GEMINI_VERTEX_LOCATION']}-aiplatform.googleapis.com/v1/"
        f"projects/{env['GEMINI_VERTEX_PROJECT']}/"
        f"locations/{env['GEMINI_VERTEX_LOCATION']}/"
        f"publishers/google/models/gemini-2.5-flash:generateContent"
    )
    headers = {
        "Authorization": f"Bearer {creds.token}",
        "Content-Type": "application/json",
    }
    data = {
        "contents": [
            {"role": "user", "parts": [{"text": "Say hello in 3 words"}]}
        ]
    }

    resp = requests.post(url, headers=headers, json=data, timeout=30)
    if resp.ok:
        result = resp.json()
        text = result["candidates"][0]["content"]["parts"][0]["text"]
        remaining = (creds.expiration_epoch - time.time()) / 60
        print(f"Token valid: {remaining:.0f} min remaining", file=sys.stderr)
        print(f"Project: {creds.project_id}", file=sys.stderr)
        print(f"Model response: {text}", file=sys.stderr)
        return True
    else:
        print(f"ERROR: API call failed: {resp.status_code}", file=sys.stderr)
        print(resp.text[:500], file=sys.stderr)
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Get Gemini/Vertex AI auth credentials"
    )
    parser.add_argument(
        "--json", action="store_true", help="Output as JSON"
    )
    parser.add_argument(
        "--test", action="store_true", help="Test the token"
    )
    parser.add_argument(
        "--harbor-ae",
        action="store_true",
        help="Output as Harbor --ae flags",
    )
    parser.add_argument(
        "--token-only",
        action="store_true",
        help="Output only the access token",
    )
    args = parser.parse_args()

    creds = get_credentials()
    env = get_env_vars(creds)

    if args.test:
        success = test_token(creds)
        sys.exit(0 if success else 1)

    if args.token_only:
        print(creds.token)
        return

    if args.json:
        remaining = (creds.expiration_epoch - time.time()) / 60
        output = {**env, "token_valid_minutes": round(remaining, 1)}
        print(json.dumps(output, indent=2))
        return

    if args.harbor_ae:
        for key, val in env.items():
            print(f'--ae "{key}={val}"')
        return

    # Default: shell-sourceable export statements
    for key, val in env.items():
        print(f'export {key}="{val}"')

    # Print info to stderr
    remaining = (creds.expiration_epoch - time.time()) / 60
    print(
        f"# Token valid for {remaining:.0f} minutes "
        f"(project: {creds.project_id})",
        file=sys.stderr,
    )
    print(
        "# Use model: openai/google/gemini-2.5-flash (or -pro, -lite)",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
