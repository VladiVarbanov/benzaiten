"""Explicit live pc1 -> pc2 inference smoke test.

Run manually from the repository root. The model server on pc2 must already be
running; this script never starts, stops, or administers the remote server.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = PROJECT_ROOT / "src"

if str(SOURCE_DIR) not in sys.path:
    sys.path.insert(0, str(SOURCE_DIR))

from config import MODELS, PC2_INFERENCE_TRIAL_MODEL  # noqa: E402
from model_client import ModelClient, ModelClientConfig, ModelClientError  # noqa: E402


PROMPT = "Reply with one short word confirming that you received this request."


def main() -> int:
    """Send one ModelClient request to the explicitly selected pc2 model."""

    model = MODELS[PC2_INFERENCE_TRIAL_MODEL]
    endpoint_url = model.endpoint_url

    if model.interface_type != "openai_compatible_api" or endpoint_url is None:
        print("Result: FAIL")
        print("The pc2 trial model is not an OpenAI-compatible endpoint.")
        return 2

    api_key = os.environ.get(model.api_key_env) if model.api_key_env else None
    print(f"Configured trial model: {PC2_INFERENCE_TRIAL_MODEL}")
    print(f"Endpoint: {endpoint_url}")
    print(f"Served model: {model.model_name}")

    try:
        with ModelClient(
            ModelClientConfig(
                base_url=endpoint_url,
                model_name=model.model_name,
                max_completion_tokens=32,
                temperature=0.0,
                connect_timeout_seconds=5.0,
                read_timeout_seconds=120.0,
                api_key=api_key,
            )
        ) as client:
            response = client.call_model(
                [{"role": "user", "content": PROMPT}]
            )
    except ModelClientError as error:
        print("Result: FAIL")
        print(f"Request ID: {error.request_id}")
        print(f"Error kind: {error.kind}")
        print(f"Retryable: {error.retryable}")
        print(f"Details: {error}")
        if error.response_excerpt:
            print(f"Response excerpt: {error.response_excerpt}")
        return 1

    if not response.text.strip():
        print("Result: FAIL")
        print("The remote endpoint returned an empty response.")
        return 1

    print("Result: PASS")
    print(f"Request ID: {response.request_id}")
    print(f"Response model: {response.model_name}")
    print(f"Latency (ms): {response.latency_ms:.2f}")
    print(f"Response: {response.text}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
