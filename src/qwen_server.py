from __future__ import annotations

import shlex
import shutil
import subprocess
from pathlib import Path
import json
import time
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, build_opener

#Probably not the best place
#docker stop benzaiten-qwen
#docker ps -a --filter name=benzaiten-qwen
#source .venv/bin/activate  python src/qwen_server.py
# docker logs -f benzaiten-qwen

#TODO: later export the settings in different config file. Create Base. Add inheritance class for different models.
#stop_qwen_server()
#restart_qwen_server()
#show_qwen_server_logs()
#get_qwen_server_status()
# =====================================================================
# 1. PROVEN QWEN SERVER PROFILE
# =====================================================================

CONTAINER_NAME = "benzaiten-qwen"

# Exact local image that successfully loaded Qwen with vLLM 0.22.1.
VLLM_IMAGE = (
    "sha256:953d3a06d5e64ab582985cd7401289d3abf2a2c14ef2158e9a84313daeec77d7"
)

MODELS_ROOT = Path("/home/vladi/local_ai/models")
MODEL_DIRECTORY = MODELS_ROOT / "Qwen3-30B-A3B-NVFP4"
CONTAINER_MODEL_PATH = "/models/Qwen3-30B-A3B-NVFP4"

SERVED_MODEL_NAME = "qwen3-30b-a3b-nvfp4"

HOST_PORT = 8001
CONTAINER_PORT = 8000

MAX_MODEL_LENGTH = 8192
MAX_NUM_SEQUENCES = 1
GPU_MEMORY_UTILIZATION = 0.92
CPU_OFFLOAD_GB = 8

TOOL_CALL_PARSER = "hermes"

QWEN_READY_URL = f"http://127.0.0.1:{HOST_PORT}/v1/models"
QWEN_READY_TIMEOUT_SECONDS = 300
QWEN_READY_POLL_INTERVAL_SECONDS = 2
QWEN_READY_REQUEST_TIMEOUT_SECONDS = 2

# =====================================================================
# 2. VALIDATION
# =====================================================================

def validate_qwen_server_settings() -> None:
    """Validate the local requirements before starting the Qwen server."""

    if shutil.which("docker") is None:
        raise RuntimeError("Docker executable was not found on PATH.")

    if not MODEL_DIRECTORY.is_dir():
        raise FileNotFoundError(
            f"Qwen model directory does not exist: {MODEL_DIRECTORY}"
        )

    model_config_path = MODEL_DIRECTORY / "config.json"

    if not model_config_path.is_file():
        raise FileNotFoundError(
            f"Qwen model config does not exist: {model_config_path}"
        )

    image_result = subprocess.run(
        [
            "docker",
            "image",
            "inspect",
            VLLM_IMAGE,
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    if image_result.returncode != 0:
        error_message = image_result.stderr.strip()

        raise RuntimeError(
            f"The required local vLLM image was not found: {VLLM_IMAGE}. "
            f"{error_message}"
        )

    container_result = subprocess.run(
        [
            "docker",
            "container",
            "inspect",
            CONTAINER_NAME,
        ],
        capture_output=True,
        text=True,
        check=False,
    )



    container_error = container_result.stderr.strip()

    if container_error and "No such" not in container_error:
        raise RuntimeError(
            f"Could not check Docker container name: {container_error}"
        )


# =====================================================================
# 3. COMMAND CONSTRUCTION
# =====================================================================

def build_qwen_server_command() -> list[str]:
    """Build the proven Docker command for the local Qwen vLLM server."""

    return [
        "docker",
        "run",
        "-d",
        "--name",
        CONTAINER_NAME,
        "--gpus",
        "all",
        "--ipc=host",
        "-p",
        f"{HOST_PORT}:{CONTAINER_PORT}",
        "-v",
        f"{MODELS_ROOT}:/models",
        VLLM_IMAGE,
        "--model",
        CONTAINER_MODEL_PATH,
        "--served-model-name",
        SERVED_MODEL_NAME,
        "--host",
        "0.0.0.0",
        "--port",
        str(CONTAINER_PORT),
        "--max-model-len",
        str(MAX_MODEL_LENGTH),
        "--max-num-seqs",
        str(MAX_NUM_SEQUENCES),
        "--gpu-memory-utilization",
        str(GPU_MEMORY_UTILIZATION),
        "--cpu-offload-gb",
        str(CPU_OFFLOAD_GB),
        "--enable-auto-tool-choice",
        "--tool-call-parser",
        TOOL_CALL_PARSER,
    ]

def wait_until_qwen_ready() -> None:
    """Wait until the Qwen endpoint reports the expected served model."""

    deadline = time.monotonic() + QWEN_READY_TIMEOUT_SECONDS

    # Do not use HTTP_PROXY or HTTPS_PROXY for the local endpoint.
    opener = build_opener(ProxyHandler({}))

    print(f"Waiting for Qwen endpoint: {QWEN_READY_URL}")

    while time.monotonic() < deadline:
        try:
            with opener.open(
                QWEN_READY_URL,
                timeout=QWEN_READY_REQUEST_TIMEOUT_SECONDS,
            ) as response:
                if response.status != 200:
                    time.sleep(QWEN_READY_POLL_INTERVAL_SECONDS)
                    continue

                response_body = response.read().decode("utf-8")
                response_data = json.loads(response_body)

                available_models = {
                    model["id"]
                    for model in response_data.get("data", [])
                    if isinstance(model, dict) and "id" in model
                }

                if SERVED_MODEL_NAME in available_models:
                    print(
                        f"Qwen server is ready: {SERVED_MODEL_NAME}"
                    )
                    return

        except (
            HTTPError,
            URLError,
            TimeoutError,
            OSError, #ConnectionResetError,
            json.JSONDecodeError,
        ):
            pass

        time.sleep(QWEN_READY_POLL_INTERVAL_SECONDS)

    raise TimeoutError(
        f"Qwen did not become ready within "
        f"{QWEN_READY_TIMEOUT_SECONDS} seconds. "
        f"Inspect the container with: docker logs {CONTAINER_NAME}"
    )


def get_qwen_container_state() -> str | None:
    """Return the Docker container state, or None if it does not exist."""

    result = subprocess.run(
        [
            "docker",
            "container",
            "inspect",
            "--format",
            "{{.State.Status}}",
            CONTAINER_NAME,
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    if result.returncode != 0:
        return None

    return result.stdout.strip()

# =====================================================================
# 4. SERVER START
# =====================================================================

def start_qwen_server() -> str:
    """Validate the launch profile and start Qwen in a Docker container."""

    validate_qwen_server_settings()

    container_state = get_qwen_container_state()

    if container_state == "running":
        print(f"Qwen container is already running: {CONTAINER_NAME}")
        wait_until_qwen_ready()
        return CONTAINER_NAME

    if container_state is not None:
        print(
            f"Starting existing Qwen container: "
            f"{CONTAINER_NAME} ({container_state})"
        )

        result = subprocess.run(
            [
                "docker",
                "start",
                CONTAINER_NAME,
            ],
            capture_output=True,
            text=True,
            check=False,
        )

        if result.returncode != 0:
            raise RuntimeError(
                f"Could not start Qwen container: "
                f"{result.stderr.strip()}"
            )

        wait_until_qwen_ready()
        return CONTAINER_NAME

    command = build_qwen_server_command()

    print("Starting Qwen server with:")
    print(shlex.join(command))

    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=False,
    )

    if result.returncode != 0:
        error_message = result.stderr.strip() or result.stdout.strip()

        raise RuntimeError(
            f"Qwen Docker container failed to start: {error_message}"
        )

    container_id = result.stdout.strip()

    if not container_id:
        raise RuntimeError(
            "Docker reported success but returned no container ID."
        )

    print(f"Started Docker container: {CONTAINER_NAME}")
    print(f"Container ID: {container_id}")
    print(
        f"Follow startup logs with: "
        f"docker logs -f {CONTAINER_NAME}"
    )

    wait_until_qwen_ready()

    return container_id

    return container_id


def main() -> None:
    start_qwen_server()


if __name__ == "__main__":
    main()