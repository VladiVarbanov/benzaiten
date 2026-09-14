# /home/vladi/local_ai/benzaiten/src/gemma_server.py

from __future__ import annotations

import json
from pathlib import Path

from model_server import ModelServer, ModelServerProfile


# =====================================================================
# 1. DIFFUSIONGEMMA SERVER PROFILE
# =====================================================================


MODELS_ROOT = Path("/home/vladi/local_ai/models")


GEMMA_SERVER_PROFILE = ModelServerProfile(
    server_name="DiffusionGemma",

    container_name="benzaiten-gemma",

    image="vllm/vllm-openai:v0.26.0-ubuntu2404",

    models_root=MODELS_ROOT,
    model_directory=(
        MODELS_ROOT
        / "diffusiongemma-26B-A4B-it-NVFP4"
    ),
    container_model_path=(
        "/models/diffusiongemma-26B-A4B-it-NVFP4"
    ),

    served_model_name=(
        "diffusiongemma-26b-a4b-it-nvfp4"
    ),

    host_port=8003,
    container_port=8000,

    max_num_sequences=1,
    gpu_memory_utilization=0.85,

    extra_vllm_args=(
        "--generation-config",
        "vllm",

        "--diffusion-config",
        json.dumps(
            {
                "canvas_length": 256,
            },
            separators=(",", ":"),
        ),

        "--hf-overrides",
        json.dumps(
            {
                "diffusion_sampler": "entropy_bound",
                "diffusion_entropy_bound": 0.1,
            },
            separators=(",", ":"),
        ),

        "--reasoning-parser",
        "gemma4",

        "--enable-auto-tool-choice",

        "--tool-call-parser",
        "gemma4",
    ),

    ready_timeout_seconds=300.0,
    ready_poll_interval_seconds=2.0,
    ready_request_timeout_seconds=2.0,
)


# =====================================================================
# 2. DIFFUSIONGEMMA SERVER INSTANCE
# =====================================================================


GEMMA_SERVER = ModelServer(
    GEMMA_SERVER_PROFILE
)


# =====================================================================
# 3. PUBLIC DIFFUSIONGEMMA SERVER INTERFACE
# =====================================================================


def validate_gemma_server_settings() -> None:
    """Validate the DiffusionGemma server profile and runtime."""

    GEMMA_SERVER.validate()


def build_gemma_server_command() -> list[str]:
    """Build the Docker command for DiffusionGemma."""

    return GEMMA_SERVER.build_run_command()


def wait_until_gemma_ready() -> None:
    """Wait until the DiffusionGemma endpoint is ready."""

    GEMMA_SERVER.wait_until_ready()


def get_gemma_container_state() -> str | None:
    """Return the current DiffusionGemma Docker container state."""

    return GEMMA_SERVER.get_container_state()


def start_gemma_server() -> str:
    """Start DiffusionGemma and wait until its endpoint is ready."""

    return GEMMA_SERVER.start()


def stop_gemma_server() -> None:
    """Stop the DiffusionGemma Docker container."""

    GEMMA_SERVER.stop()


def restart_gemma_server() -> str:
    """Restart DiffusionGemma and wait until its endpoint is ready."""

    return GEMMA_SERVER.restart()


def get_gemma_server_status() -> str:
    """Return a human-readable DiffusionGemma server status."""

    return GEMMA_SERVER.status()


def show_gemma_server_logs(
    *,
    tail: int = 100,
) -> None:
    """Print recent DiffusionGemma Docker logs."""

    GEMMA_SERVER.print_logs(
        tail=tail
    )


# =====================================================================
# 4. COMMAND-LINE ENTRYPOINT
# =====================================================================


def main() -> None:
    start_gemma_server()


if __name__ == "__main__":
    main()