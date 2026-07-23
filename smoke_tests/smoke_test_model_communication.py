from __future__ import annotations

import socket
import subprocess
import sys
import traceback
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = PROJECT_ROOT / "src"

if str(SOURCE_DIR) not in sys.path:
    sys.path.insert(0, str(SOURCE_DIR))
# Local imports must follow direct-script source-path bootstrapping.
from config import QWEN_MODEL  # noqa: E402
from model_client import (  # noqa: E402
    ModelClient,
    ModelClientConfig,
    ModelClientError,
    ModelResponse,
)
from qwen_server import (  # noqa: E402
    CONTAINER_NAME,
    HOST_PORT,
    SERVED_MODEL_NAME,
    get_qwen_container_state,
    start_qwen_server,
)


EXPECTED_TEXT = "BENZAITEN_OK"
PROMPT = f"Reply with exactly: {EXPECTED_TEXT}"


def is_port_occupied(port: int) -> bool:
    """Return whether the local TCP port cannot be reserved."""

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        try:
            probe.bind(("127.0.0.1", port))
        except OSError:
            return True

    return False


def stop_owned_qwen_server() -> None:
    """Stop the Qwen container started by this smoke-test run."""

    result = subprocess.run(
        ["docker", "stop", CONTAINER_NAME],
        capture_output=True,
        text=True,
        check=False,
    )

    if result.returncode != 0:
        error_message = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(
            f"Could not stop owned Qwen container: {error_message}"
        )


def print_model_client_error(error: ModelClientError) -> None:
    """Print the complete structured model-client failure."""

    print("ModelClientError:")
    print(f"  request ID: {error.request_id}")
    print(f"  kind: {error.kind}")
    print(f"  message: {error}")
    print(f"  status code: {error.status_code}")
    print(f"  retryable: {error.retryable}")
    print(f"  response excerpt: {error.response_excerpt}")

    if error.__cause__ is not None:
        print(f"  original exception: {error.__cause__!r}")


def print_result(response: ModelResponse) -> None:
    """Print the successful communication result."""

    print("Result: PASS")
    print(f"Request ID: {response.request_id}")
    print(f"Model name: {response.model_name}")
    print(f"Response text: {response.text}")
    print(f"Finish reason: {response.finish_reason}")
    print(f"Latency (ms): {response.latency_ms:.2f}")
    print(f"Prompt tokens: {response.prompt_tokens}")
    print(f"Completion tokens: {response.completion_tokens}")
    print(f"Total tokens: {response.total_tokens}")


def main() -> int:
    """Run one real request through the local Qwen communication path."""

    client: ModelClient | None = None
    response: ModelResponse | None = None
    server_owned = False
    failure: BaseException | None = None

    stages = {
        "server launch": False,
        "readiness": False,
        "client construction": False,
        "request transmission": False,
        "response parsing": False,
        "console result": False,
        "client cleanup": False,
        "server cleanup": False,
    }

    endpoint_url = QWEN_MODEL.endpoint_url
    endpoint_port = QWEN_MODEL.endpoint_port

    if endpoint_url is None or endpoint_port is None:
        print("Result: FAIL")
        print("Qwen endpoint URL or port is not configured.")
        return 2

    if endpoint_port != HOST_PORT:
        print("Result: FAIL")
        print(
            "Configured Qwen port does not match the launcher port: "
            f"{endpoint_port} != {HOST_PORT}."
        )
        return 2

    if QWEN_MODEL.model_name != SERVED_MODEL_NAME:
        print("Result: FAIL")
        print(
            "Configured Qwen model does not match the served model: "
            f"{QWEN_MODEL.model_name} != {SERVED_MODEL_NAME}."
        )
        return 2

    if is_port_occupied(endpoint_port):
        print("Result: FAIL")
        print(
            f"Port {endpoint_port} is already occupied. "
            "The smoke test will not use or stop an externally owned server."
        )
        return 2

    initial_container_state = get_qwen_container_state()

    if initial_container_state == "running":
        print("Result: FAIL")
        print(
            f"Container {CONTAINER_NAME} is already running. "
            "The smoke test will not take ownership of it."
        )
        return 2

    try:
        server_owned = True

        try:
            start_qwen_server()
        except BaseException:
            stages["server launch"] = (
                get_qwen_container_state() == "running"
            )
            raise

        stages["server launch"] = True
        stages["readiness"] = True

        client_config = ModelClientConfig(
            base_url=endpoint_url,
            model_name=QWEN_MODEL.model_name,
            max_completion_tokens=QWEN_MODEL.output_tokens,
            temperature=QWEN_MODEL.temperature,
            api_key=None,
        )
        client = ModelClient(client_config)
        stages["client construction"] = True

        response = client.call_model(
            [{"role": "user", "content": PROMPT}]
        )
        stages["request transmission"] = True

        if not isinstance(response, ModelResponse):
            raise AssertionError(
                "ModelClient.call_model() did not return ModelResponse."
            )

        if not response.request_id:
            raise AssertionError("The model response has no request ID.")

        if response.model_name != QWEN_MODEL.model_name:
            raise AssertionError(
                "Unexpected response model name: "
                f"{response.model_name!r}."
            )

        if EXPECTED_TEXT not in response.text:
            raise AssertionError(
                f"Response does not contain {EXPECTED_TEXT!r}: "
                f"{response.text!r}."
            )

        if response.latency_ms < 0:
            raise AssertionError("Response latency is unavailable.")

        stages["response parsing"] = True

    except ModelClientError as error:
        failure = error
        print_model_client_error(error)
        traceback.print_exception(error)
    except KeyboardInterrupt as error:
        failure = error
        print("Smoke test interrupted by user.")
    except BaseException as error:
        failure = error
        traceback.print_exception(error)
    finally:
        if client is not None:
            try:
                client.close()
                stages["client cleanup"] = True
            except BaseException as cleanup_error:
                if failure is None:
                    failure = cleanup_error
                traceback.print_exception(cleanup_error)
        else:
            stages["client cleanup"] = True

        if server_owned:
            try:
                if get_qwen_container_state() == "running":
                    stop_owned_qwen_server()
                stages["server cleanup"] = True
            except BaseException as cleanup_error:
                if failure is None:
                    failure = cleanup_error
                traceback.print_exception(cleanup_error)
        else:
            stages["server cleanup"] = True

    if failure is None and response is not None:
        print_result(response)
        stages["console result"] = True
    else:
        print("Result: FAIL")

    print("Stages:")
    for stage_name, succeeded in stages.items():
        status = "PASS" if succeeded else "FAIL"
        print(f"  {stage_name}: {status}")

    return 0 if failure is None and response is not None else 1


if __name__ == "__main__":
    sys.exit(main())
