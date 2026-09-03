# /home/vladi/local_ai/benzaiten/src/qwen_server.py

from __future__ import annotations

from pathlib import Path

from model_server import ModelServer, ModelServerProfile


# =====================================================================
# 1. QWEN SERVER PROFILE
# =====================================================================


MODELS_ROOT = Path("/home/vladi/local_ai/models")


QWEN_SERVER_PROFILE = ModelServerProfile(
    server_name="Qwen",

    container_name="benzaiten-qwen",

    # Exact local image that successfully loaded Qwen.
    image=(
        "sha256:"
        "953d3a06d5e64ab582985cd7401289d3"
        "abf2a2c14ef2158e9a84313daeec77d7"
    ),

    models_root=MODELS_ROOT,
    model_directory=(
        MODELS_ROOT / "Qwen3-30B-A3B-NVFP4"
    ),
    container_model_path=(
        "/models/Qwen3-30B-A3B-NVFP4"
    ),

    served_model_name="qwen3-30b-a3b-nvfp4",

    host_port=8001,
    container_port=8000,

    max_num_sequences=1,
    gpu_memory_utilization=0.92,

    extra_vllm_args=(
        "--max-model-len",
        "8192",

        "--cpu-offload-gb",
        "8",

        "--enable-auto-tool-choice",

        "--tool-call-parser",
        "hermes",
    ),

    ready_timeout_seconds=300.0,
    ready_poll_interval_seconds=2.0,
    ready_request_timeout_seconds=2.0,
)


# =====================================================================
# 2. QWEN SERVER INSTANCE
# =====================================================================


QWEN_SERVER = ModelServer(
    QWEN_SERVER_PROFILE
)


# =====================================================================
# 3. PUBLIC QWEN SERVER INTERFACE
# =====================================================================


def validate_qwen_server_settings() -> None:
    """Validate the Qwen server profile and runtime."""

    QWEN_SERVER.validate()


def build_qwen_server_command() -> list[str]:
    """Build the Docker command for the Qwen server."""

    return QWEN_SERVER.build_run_command()


def wait_until_qwen_ready() -> None:
    """Wait until the Qwen endpoint is ready."""

    QWEN_SERVER.wait_until_ready()


def get_qwen_container_state() -> str | None:
    """Return the current Qwen Docker container state."""

    return QWEN_SERVER.get_container_state()


def start_qwen_server() -> str:
    """Start Qwen and wait until its endpoint is ready."""

    return QWEN_SERVER.start()


def stop_qwen_server() -> None:
    """Stop the Qwen Docker container."""

    QWEN_SERVER.stop()


def restart_qwen_server() -> str:
    """Restart Qwen and wait until its endpoint is ready."""

    return QWEN_SERVER.restart()


def get_qwen_server_status() -> str:
    """Return a human-readable Qwen server status."""

    return QWEN_SERVER.status()


def show_qwen_server_logs(
    *,
    tail: int = 100,
) -> None:
    """Print recent Qwen Docker logs."""

    QWEN_SERVER.print_logs(
        tail=tail
    )


# =====================================================================
# 4. COMMAND-LINE ENTRYPOINT
# =====================================================================


def main() -> None:
    start_qwen_server()


if __name__ == "__main__":
    main()