from __future__ import annotations

from urllib.parse import urlparse

from config import MODELS, PC1_HOST, PC2_HOST, PC2_INFERENCE_TRIAL_MODEL
from gemma_server import GEMMA_SERVER_PROFILE
from qwen_server import QWEN_SERVER_PROFILE


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
