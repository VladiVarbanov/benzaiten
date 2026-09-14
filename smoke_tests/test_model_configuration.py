from __future__ import annotations

from urllib.parse import urlparse

from config import (
    MODELS,
    PC1_GPU0,
    PC1_HOST,
    PC2_HOST,
    PC2_INFERENCE_TRIAL_MODEL,
    QWEN_MODEL,
)
from gemma_server import GEMMA_SERVER_PROFILE
from qwen_server import QWEN_SERVER_PROFILE
from model_client import ModelClient, ModelClientConfig


def test_pc2_trial_model_is_qwen_remote_openai_endpoint() -> None:
    model = MODELS[PC2_INFERENCE_TRIAL_MODEL]
    endpoint_url = model.endpoint_url

    assert PC2_INFERENCE_TRIAL_MODEL == "qwen"
    assert model.node.startswith(f"{PC2_HOST.phys_host}.")
    assert model.interface_type == "openai_compatible_api"
    assert model.cli_command is None
    assert model.working_dir is None
    assert endpoint_url is not None
    assert urlparse(endpoint_url).hostname == PC2_HOST.address_local
    assert urlparse(endpoint_url).port == model.endpoint_port
    assert model.model_name == QWEN_SERVER_PROFILE.served_model_name
    assert model.endpoint_port == QWEN_SERVER_PROFILE.host_port
    assert QWEN_SERVER_PROFILE.image == "vllm/vllm-openai:v0.23.0"
    assert not QWEN_SERVER_PROFILE.image.startswith("sha256:")


def test_gemma_uses_one_local_openai_vllm_definition() -> None:
    model = MODELS["diffusion_gemma"]
    endpoint_url = model.endpoint_url

    assert model.node.startswith(f"{PC1_HOST.phys_host}.")
    assert model.interface_type == "openai_compatible_api"
    assert model.cli_command is None
    assert model.working_dir is None
    assert endpoint_url is not None
    assert urlparse(endpoint_url).hostname == "127.0.0.1"
    assert model.model_name == GEMMA_SERVER_PROFILE.served_model_name
    assert model.endpoint_port == GEMMA_SERVER_PROFILE.host_port
    assert model.temperature is None
    assert "--enable-auto-tool-choice" in GEMMA_SERVER_PROFILE.extra_vllm_args
    tool_parser_index = GEMMA_SERVER_PROFILE.extra_vllm_args.index(
        "--tool-call-parser"
    )
    assert GEMMA_SERVER_PROFILE.extra_vllm_args[tool_parser_index + 1] == "gemma4"


def test_qwen_uses_its_registered_reasoning_parser() -> None:
    parser_index = QWEN_SERVER_PROFILE.extra_vllm_args.index(
        "--reasoning-parser"
    )
    assert QWEN_SERVER_PROFILE.extra_vllm_args[parser_index + 1] == "qwen3"


def test_qwen_retains_configured_temperature() -> None:
    assert QWEN_MODEL.temperature == 0.1
    assert QWEN_MODEL.supports_json_schema is True
    assert QWEN_MODEL.structured_output_chat_template_kwargs == {
        "enable_thinking": False,
    }


def test_model_client_omits_unconfigured_temperature() -> None:
    with ModelClient(
        ModelClientConfig(
            base_url="http://127.0.0.1:8003/v1",
            model_name="diffusion-gemma",
            temperature=None,
        )
    ) as client:
        payload = client._build_request_payload(
            [{"role": "user", "content": "Test prompt"}]
        )

    assert "temperature" not in payload


def test_model_client_forwards_generic_structured_response_format() -> None:
    response_format = {
        "type": "json_schema",
        "json_schema": {
            "name": "test_object",
            "strict": True,
            "schema": {
                "type": "object",
                "properties": {"value": {"type": "string"}},
                "required": ["value"],
                "additionalProperties": False,
            },
        },
    }
    with ModelClient(
        ModelClientConfig(
            base_url="http://127.0.0.1:8003/v1",
            model_name="test-model",
        )
    ) as client:
        payload = client._build_request_payload(
            [{"role": "user", "content": "Test prompt"}],
            response_format=response_format,
        )

    assert payload["response_format"] == response_format
    assert payload["response_format"] is not response_format


def test_model_client_forwards_generic_chat_template_kwargs() -> None:
    kwargs = {"enable_thinking": False}
    with ModelClient(
        ModelClientConfig(
            base_url="http://127.0.0.1:8003/v1",
            model_name="test-model",
        )
    ) as client:
        payload = client._build_request_payload(
            [{"role": "user", "content": "Test prompt"}],
            chat_template_kwargs=kwargs,
        )

    assert payload["chat_template_kwargs"] == kwargs
    assert payload["chat_template_kwargs"] is not kwargs


def test_pc1_gpu_metadata_matches_authoritative_hardware() -> None:
    assert PC1_GPU0.device_name == "NVIDIA_RTX_PRO_4500_Blackwell_32GB"
    assert PC1_GPU0.memory.total_gb == 32.0


def test_qwen_metadata_covers_configured_v0_work() -> None:
    assert {"reasoning", "worker", "reviewer", "assessor"} <= set(QWEN_MODEL.role)
