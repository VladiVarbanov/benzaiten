# /home/vladi/local_ai/benzaiten/src/model_server.py

from __future__ import annotations

import json
import shlex
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, build_opener


# =====================================================================
# 1. MODEL SERVER PROFILE
# =====================================================================


@dataclass(frozen=True, slots=True)
class ModelServerProfile:
    """Configuration for one local vLLM Docker model server."""

    server_name: str

    container_name: str
    image: str

    models_root: Path
    model_directory: Path
    container_model_path: str

    served_model_name: str

    host_port: int
    container_port: int = 8000

    max_num_sequences: int = 1
    gpu_memory_utilization: float = 0.85

    # Model-specific vLLM arguments.
    #
    # Examples:
    #
    # Qwen:
    #   --max-model-len
    #   --cpu-offload-gb
    #   --enable-auto-tool-choice
    #   --tool-call-parser
    #
    # DiffusionGemma:
    #   --generation-config
    #   --diffusion-config
    #   --hf-overrides
    #   --reasoning-parser
    extra_vllm_args: tuple[str, ...] = ()

    ready_timeout_seconds: float = 300.0
    ready_poll_interval_seconds: float = 2.0
    ready_request_timeout_seconds: float = 2.0

    @property
    def ready_url(self) -> str:
        """Return the local OpenAI-compatible model-list endpoint."""

        return (
            f"http://127.0.0.1:"
            f"{self.host_port}/v1/models"
        )


# =====================================================================
# 2. MODEL SERVER
# =====================================================================


class ModelServer:
    """Manage one local vLLM model server running in Docker."""

    def __init__(self, profile: ModelServerProfile) -> None:
        self.profile = profile

    # =================================================================
    # 3. VALIDATION
    # =================================================================

    def validate(self) -> None:
        """Validate configuration and local runtime requirements."""

        profile = self.profile

        if not profile.server_name.strip():
            raise ValueError(
                "Model server name cannot be empty."
            )

        if not profile.container_name.strip():
            raise ValueError(
                "Docker container name cannot be empty."
            )

        if not profile.image.strip():
            raise ValueError(
                "Docker image cannot be empty."
            )

        if not profile.container_model_path.strip():
            raise ValueError(
                "Container model path cannot be empty."
            )

        if not profile.served_model_name.strip():
            raise ValueError(
                "Served model name cannot be empty."
            )

        if not (1 <= profile.host_port <= 65535):
            raise ValueError(
                f"Invalid host port: {profile.host_port}"
            )

        if not (1 <= profile.container_port <= 65535):
            raise ValueError(
                f"Invalid container port: "
                f"{profile.container_port}"
            )

        if profile.max_num_sequences < 1:
            raise ValueError(
                "max_num_sequences must be at least 1."
            )

        if not (
            0.0 < profile.gpu_memory_utilization <= 1.0
        ):
            raise ValueError(
                "gpu_memory_utilization must be "
                "greater than 0 and at most 1."
            )

        if profile.ready_timeout_seconds <= 0:
            raise ValueError(
                "ready_timeout_seconds must be positive."
            )

        if profile.ready_poll_interval_seconds <= 0:
            raise ValueError(
                "ready_poll_interval_seconds must be positive."
            )

        if profile.ready_request_timeout_seconds <= 0:
            raise ValueError(
                "ready_request_timeout_seconds must be positive."
            )

        if not all(
            isinstance(argument, str)
            for argument in profile.extra_vllm_args
        ):
            raise ValueError(
                "All extra_vllm_args values must be strings."
            )

        if shutil.which("docker") is None:
            raise RuntimeError(
                "Docker executable was not found on PATH."
            )

        if not profile.models_root.is_dir():
            raise FileNotFoundError(
                f"Models root does not exist: "
                f"{profile.models_root}"
            )

        if not profile.model_directory.is_dir():
            raise FileNotFoundError(
                f"Model directory does not exist: "
                f"{profile.model_directory}"
            )

        model_config_path = (
            profile.model_directory / "config.json"
        )

        if not model_config_path.is_file():
            raise FileNotFoundError(
                f"Model config does not exist: "
                f"{model_config_path}"
            )

        self._validate_docker_image()
        self._validate_container_lookup()

    def _validate_docker_image(self) -> None:
        """Verify that the configured Docker image exists locally."""

        result = subprocess.run(
            [
                "docker",
                "image",
                "inspect",
                self.profile.image,
            ],
            capture_output=True,
            text=True,
            check=False,
        )

        if result.returncode == 0:
            return

        error_message = result.stderr.strip()

        raise RuntimeError(
            f"Required Docker image was not found: "
            f"{self.profile.image}. "
            f"{error_message}"
        )

    def _validate_container_lookup(self) -> None:
        """Verify that Docker can inspect the container name."""

        result = subprocess.run(
            [
                "docker",
                "container",
                "inspect",
                self.profile.container_name,
            ],
            capture_output=True,
            text=True,
            check=False,
        )

        if result.returncode == 0:
            return

        error_message = result.stderr.strip()

        # A missing container is expected when starting a model
        # for the first time.
        if "No such" in error_message:
            return

        raise RuntimeError(
            f"Could not inspect Docker container "
            f"{self.profile.container_name}: "
            f"{error_message}"
        )

    # =================================================================
    # 4. COMMAND CONSTRUCTION
    # =================================================================

    def build_run_command(self) -> list[str]:
        """Build the Docker command for a new model container."""

        profile = self.profile

        command = [
            "docker",
            "run",
            "-d",
            "--name",
            profile.container_name,
            "--gpus",
            "all",
            "--ipc=host",
            "-p",
            (
                f"{profile.host_port}:"
                f"{profile.container_port}"
            ),
            "-v",
            f"{profile.models_root}:/models",
            profile.image,
            "--model",
            profile.container_model_path,
            "--served-model-name",
            profile.served_model_name,
            "--host",
            "0.0.0.0",
            "--port",
            str(profile.container_port),
            "--max-num-seqs",
            str(profile.max_num_sequences),
            "--gpu-memory-utilization",
            str(profile.gpu_memory_utilization),
        ]

        command.extend(profile.extra_vllm_args)

        return command

    # =================================================================
    # 5. CONTAINER STATE
    # =================================================================

    def get_container_state(self) -> str | None:
        """Return Docker container state, or None if absent."""

        result = subprocess.run(
            [
                "docker",
                "container",
                "inspect",
                "--format",
                "{{.State.Status}}",
                self.profile.container_name,
            ],
            capture_output=True,
            text=True,
            check=False,
        )

        if result.returncode != 0:
            return None

        state = result.stdout.strip()

        return state or None

    def is_running(self) -> bool:
        """Return whether the configured container is running."""

        return self.get_container_state() == "running"

    # =================================================================
    # 6. ENDPOINT READINESS
    # =================================================================

    def wait_until_ready(self) -> None:
        """Wait until vLLM exposes the configured served model."""

        profile = self.profile

        deadline = (
            time.monotonic()
            + profile.ready_timeout_seconds
        )

        # Do not use HTTP_PROXY or HTTPS_PROXY for localhost.
        opener = build_opener(
            ProxyHandler({})
        )

        print(
            f"Waiting for {profile.server_name} endpoint: "
            f"{profile.ready_url}"
        )

        while time.monotonic() < deadline:
            try:
                with opener.open(
                    profile.ready_url,
                    timeout=(
                        profile.ready_request_timeout_seconds
                    ),
                ) as response:
                    if response.status != 200:
                        time.sleep(
                            profile.ready_poll_interval_seconds
                        )
                        continue

                    response_body = (
                        response.read().decode("utf-8")
                    )

                    response_data = json.loads(
                        response_body
                    )

                    if not isinstance(
                        response_data,
                        dict,
                    ):
                        time.sleep(
                            profile.ready_poll_interval_seconds
                        )
                        continue

                    models_value = response_data.get(
                        "data",
                        [],
                    )

                    if not isinstance(
                        models_value,
                        list,
                    ):
                        time.sleep(
                            profile.ready_poll_interval_seconds
                        )
                        continue

                    available_models = {
                        model["id"]
                        for model in models_value
                        if (
                            isinstance(model, dict)
                            and isinstance(
                                model.get("id"),
                                str,
                            )
                        )
                    }

                    if (
                        profile.served_model_name
                        in available_models
                    ):
                        print(
                            f"{profile.server_name} server "
                            f"is ready: "
                            f"{profile.served_model_name}"
                        )
                        return

            except (
                HTTPError,
                URLError,
                TimeoutError,
                OSError,
                json.JSONDecodeError,
            ):
                pass

            time.sleep(
                profile.ready_poll_interval_seconds
            )

        raise TimeoutError(
            f"{profile.server_name} did not become ready "
            f"within "
            f"{profile.ready_timeout_seconds:g} seconds. "
            f"Inspect the container with: "
            f"docker logs "
            f"{profile.container_name}"
        )

    # =================================================================
    # 7. SERVER START
    # =================================================================

    def start(self) -> str:
        """Validate and start the configured model server."""

        self.validate()

        container_state = self.get_container_state()

        if container_state == "running":
            print(
                f"{self.profile.server_name} container "
                f"is already running: "
                f"{self.profile.container_name}"
            )

            self.wait_until_ready()

            return self.profile.container_name

        if container_state is not None:
            return self._start_existing_container(
                container_state
            )

        return self._create_container()

    def _start_existing_container(
        self,
        container_state: str,
    ) -> str:
        """Start an existing stopped Docker container."""

        profile = self.profile

        print(
            f"Starting existing {profile.server_name} "
            f"container: "
            f"{profile.container_name} "
            f"({container_state})"
        )

        result = subprocess.run(
            [
                "docker",
                "start",
                profile.container_name,
            ],
            capture_output=True,
            text=True,
            check=False,
        )

        if result.returncode != 0:
            raise RuntimeError(
                f"Could not start "
                f"{profile.server_name} container: "
                f"{result.stderr.strip()}"
            )

        self.wait_until_ready()

        return profile.container_name

    def _create_container(self) -> str:
        """Create a new Docker container and wait for readiness."""

        profile = self.profile
        command = self.build_run_command()

        print(
            f"Starting {profile.server_name} server with:"
        )
        print(
            shlex.join(command)
        )

        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
        )

        if result.returncode != 0:
            error_message = (
                result.stderr.strip()
                or result.stdout.strip()
            )

            raise RuntimeError(
                f"{profile.server_name} Docker container "
                f"failed to start: "
                f"{error_message}"
            )

        container_id = result.stdout.strip()

        if not container_id:
            raise RuntimeError(
                "Docker reported success but returned "
                "no container ID."
            )

        print(
            f"Started Docker container: "
            f"{profile.container_name}"
        )
        print(
            f"Container ID: {container_id}"
        )
        print(
            f"Follow startup logs with: "
            f"docker logs -f "
            f"{profile.container_name}"
        )

        self.wait_until_ready()

        return container_id

    # =================================================================
    # 8. SERVER STOP / RESTART
    # =================================================================

    def stop(self) -> None:
        """Stop the configured container if it is running."""

        profile = self.profile
        container_state = self.get_container_state()

        if container_state is None:
            print(
                f"{profile.server_name} container "
                f"does not exist: "
                f"{profile.container_name}"
            )
            return

        if container_state != "running":
            print(
                f"{profile.server_name} container "
                f"is already stopped: "
                f"{profile.container_name} "
                f"({container_state})"
            )
            return

        result = subprocess.run(
            [
                "docker",
                "stop",
                profile.container_name,
            ],
            capture_output=True,
            text=True,
            check=False,
        )

        if result.returncode != 0:
            raise RuntimeError(
                f"Could not stop "
                f"{profile.server_name} container: "
                f"{result.stderr.strip()}"
            )

        print(
            f"Stopped {profile.server_name} container: "
            f"{profile.container_name}"
        )

    def restart(self) -> str:
        """Restart the configured container and wait for readiness."""

        profile = self.profile
        container_state = self.get_container_state()

        if container_state is None:
            return self.start()

        print(
            f"Restarting {profile.server_name} container: "
            f"{profile.container_name}"
        )

        result = subprocess.run(
            [
                "docker",
                "restart",
                profile.container_name,
            ],
            capture_output=True,
            text=True,
            check=False,
        )

        if result.returncode != 0:
            raise RuntimeError(
                f"Could not restart "
                f"{profile.server_name} container: "
                f"{result.stderr.strip()}"
            )

        self.wait_until_ready()

        return profile.container_name

    # =================================================================
    # 9. DIAGNOSTICS
    # =================================================================

    def status(self) -> str:
        """Return a concise human-readable server status."""

        profile = self.profile
        container_state = self.get_container_state()

        if container_state is None:
            return (
                f"{profile.server_name}: "
                f"container does not exist"
            )

        return (
            f"{profile.server_name}: "
            f"{container_state} "
            f"({profile.container_name})"
        )

    def print_logs(
        self,
        *,
        tail: int = 100,
    ) -> None:
        """Print recent Docker logs for the model server."""

        profile = self.profile

        if tail < 1:
            raise ValueError(
                "Log tail must be at least 1."
            )

        if self.get_container_state() is None:
            raise RuntimeError(
                f"Container does not exist: "
                f"{profile.container_name}"
            )

        result = subprocess.run(
            [
                "docker",
                "logs",
                "--tail",
                str(tail),
                profile.container_name,
            ],
            capture_output=True,
            text=True,
            check=False,
        )

        if result.returncode != 0:
            raise RuntimeError(
                f"Could not read Docker logs for "
                f"{profile.server_name}: "
                f"{result.stderr.strip()}"
            )

        if result.stdout:
            print(
                result.stdout,
                end=(
                    ""
                    if result.stdout.endswith("\n")
                    else "\n"
                ),
            )

        if result.stderr:
            print(
                result.stderr,
                end=(
                    ""
                    if result.stderr.endswith("\n")
                    else "\n"
                ),
            )