# /home/vladi/local_ai/benzaiten/src/model_client.py

from __future__ import annotations

import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal
from uuid import uuid4

import httpx


ModelErrorKind = Literal[
    "connection",
    "timeout",
    "authentication",
    "rate_limit",
    "bad_request",
    "context_length",
    "server_error",
    "protocol_error",
    "empty_response",
    "internal_error",
]

@dataclass(frozen=True, slots=True)
class ModelClientConfig:
    base_url: str
    model_name: str

    max_completion_tokens: int | None = None
    temperature: float | None = None
    top_p: float | None = None

    connect_timeout_seconds: float = 10.0
    read_timeout_seconds: float = 600.0

    api_key: str | None = None


@dataclass(frozen=True, slots=True)
class ModelResponse:
    request_id: str
    server_request_id: str | None
    model_name: str

    text: str
    reasoning_text: str | None
    finish_reason: str | None

    prompt_tokens: int | None
    completion_tokens: int | None
    total_tokens: int | None

    latency_ms: float


class ModelClientError(RuntimeError):
    def __init__(
        self,
        *,
        request_id: str,
        kind: ModelErrorKind,
        message: str,
        status_code: int | None = None,
        retryable: bool = False,
        retry_after_seconds: float | None = None,
        response_excerpt: str | None = None,
    ) -> None:
        super().__init__(message)

        self.request_id = request_id
        self.kind = kind
        self.status_code = status_code
        self.retryable = retryable
        self.retry_after_seconds = retry_after_seconds
        self.response_excerpt = response_excerpt

class _ModelRequestValidationError(ValueError):
    """Raised when the caller supplies an invalid model request."""


class _ModelProtocolError(ValueError):
    """Raised when the model endpoint returns an incompatible response."""


class _EmptyModelResponseError(ValueError):
    """Raised when the model endpoint returns no usable text output."""


class ModelClient:
    CHAT_COMPLETIONS_PATH = "/chat/completions"

    SUPPORTED_TEXT_ROLES = frozenset(
        {
            "system",
            "user",
            "assistant",
        }
    )

    def __init__(self, config: ModelClientConfig) -> None:
        self.config = config

        timeout = httpx.Timeout(
            connect=config.connect_timeout_seconds,
            read=config.read_timeout_seconds,
            write=30.0,
            pool=10.0,
        )

        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

        if config.api_key is not None:
            headers["Authorization"] = f"Bearer {config.api_key}"

        self._http_client = httpx.Client(
            base_url=config.base_url.rstrip("/"),
            headers=headers,
            timeout=timeout,
        )

    def _build_request_payload(
            self,
            messages: Sequence[Mapping[str, object]],
    ) -> dict[str, object]:
        if (
            not isinstance(messages, Sequence)
            or isinstance(messages, (str, bytes, bytearray))
        ):
            raise _ModelRequestValidationError(
                "Model messages must be a sequence."
            )
        if not messages:
            raise _ModelRequestValidationError(
                "At least one model message is required."
            )

        normalized_messages: list[dict[str, str]] = []

        for index, message in enumerate(messages):
            if not isinstance(message, Mapping):
                raise _ModelRequestValidationError(
                    f"Message {index} must be a mapping."
                )

            if not all(isinstance(key, str) for key in message):
                raise _ModelRequestValidationError(
                    f"Message {index} contains a non-string field name."
                )
            unsupported_keys = set(message) - {"role", "content"}

            if unsupported_keys:
                unsupported = ", ".join(sorted(unsupported_keys))
                raise _ModelRequestValidationError(
                    f"Message {index} contains unsupported fields: "
                    f"{unsupported}."
                )

            role = message.get("role")
            content = message.get("content")

            if not isinstance(role, str) or not role:
                raise _ModelRequestValidationError(
                    f"Message {index} has an invalid role."
                )

            if role not in self.SUPPORTED_TEXT_ROLES:
                raise _ModelRequestValidationError(
                    f"Message {index} has unsupported role: {role}."
                )

            if not isinstance(content, str):
                raise _ModelRequestValidationError(
                    f"Message {index} content must be text."
                )

            if not content.strip():
                raise _ModelRequestValidationError(
                    f"Message {index} content cannot be empty."
                )

            normalized_messages.append(
                {
                    "role": role,
                    "content": content,
                }
            )

        payload: dict[str, object] = {
            "model": self.config.model_name,
            "messages": normalized_messages,
            "stream": False,
        }
        if self.config.max_completion_tokens is not None:
            payload["max_tokens"] = self.config.max_completion_tokens

        if self.config.temperature is not None:
            payload["temperature"] = self.config.temperature

        if self.config.top_p is not None:
            payload["top_p"] = self.config.top_p

        return payload


    def _send_http_request(
            self,
            payload: Mapping[str, object],
    ) -> httpx.Response:
        return self._http_client.post(
            self.CHAT_COMPLETIONS_PATH,
            json=payload,
        )


    def _parse_model_response(
            self,
            request_id: str,
            response: httpx.Response,
            latency_ms: float,
    ) -> ModelResponse:
        try:
            decoded_response: object = response.json()
        except ValueError as error:
            raise _ModelProtocolError(
                "Model endpoint returned malformed JSON."
            ) from error

        if not isinstance(decoded_response, Mapping):
            raise _ModelProtocolError(
                "Model response must be a JSON object."
            )

        response_data: Mapping[object, object] = decoded_response
        choices_value = response_data.get("choices")

        if choices_value is None:
            raise _EmptyModelResponseError(
                "Model response contains no choices."
            )

        if (
            not isinstance(choices_value, Sequence)
            or isinstance(choices_value, (str, bytes, bytearray))
        ):
            raise _ModelProtocolError(
                "Model response choices must be a sequence."
            )

        if not choices_value:
            raise _EmptyModelResponseError(
                "Model response contains no usable choices."
            )

        first_choice: object = choices_value[0]

        if not isinstance(first_choice, Mapping):
            raise _ModelProtocolError(
                "The first model response choice must be an object."
            )

        choice: Mapping[object, object] = first_choice
        message_value = choice.get("message")

        if message_value is None:
            raise _EmptyModelResponseError(
                "The first model response choice contains no message."
            )

        if not isinstance(message_value, Mapping):
            raise _ModelProtocolError(
                "The model response message must be an object."
            )

        message: Mapping[object, object] = message_value
        content_value = message.get("content")

        if content_value is None:
            raise _EmptyModelResponseError(
                "The model response message contains no content."
            )

        if not isinstance(content_value, str):
            raise _ModelProtocolError(
                "The model response content must be text."
            )

        if not content_value.strip():
            raise _EmptyModelResponseError(
                "The model response content is empty."
            )

        reasoning_value = message.get("reasoning")

        if reasoning_value is None:
            reasoning_value = message.get("reasoning_content")

        if reasoning_value is not None and not isinstance(
            reasoning_value,
            str,
        ):
            raise _ModelProtocolError(
                "The model response reasoning content must be text."
            )

        finish_reason_value = choice.get("finish_reason")

        if (
            finish_reason_value is not None
            and not isinstance(finish_reason_value, str)
        ):
            raise _ModelProtocolError(
                "The model response finish reason must be text."
            )

        server_request_id_value = response_data.get("id")

        if (
            server_request_id_value is not None
            and not isinstance(server_request_id_value, str)
        ):
            raise _ModelProtocolError(
                "The model response request ID must be text."
            )

        model_name_value = response_data.get(
            "model",
            self.config.model_name,
        )

        if not isinstance(model_name_value, str):
            raise _ModelProtocolError(
                "The model response model name must be text."
            )

        usage_value = response_data.get("usage")

        if usage_value is None:
            usage: Mapping[object, object] = {}
        elif isinstance(usage_value, Mapping):
            usage = usage_value
        else:
            raise _ModelProtocolError(
                "The model response usage must be an object."
            )

        prompt_tokens_value = self._parse_token_count(
            usage.get("prompt_tokens", 0),
            "prompt_tokens",
        )
        completion_tokens_value = self._parse_token_count(
            usage.get("completion_tokens", 0),
            "completion_tokens",
        )
        total_tokens_value = self._parse_token_count(
            usage.get("total_tokens", 0),
            "total_tokens",
        )

        return ModelResponse(
            request_id=request_id,
            server_request_id=server_request_id_value,
            model_name=model_name_value,
            text=content_value,
            reasoning_text=reasoning_value,
            finish_reason=finish_reason_value,
            prompt_tokens=prompt_tokens_value,
            completion_tokens=completion_tokens_value,
            total_tokens=total_tokens_value,
            latency_ms=latency_ms,
        )
    @staticmethod
    def _parse_token_count(
            value: object,
            field_name: str,
    ) -> int | None:
        if value is None:
            return None

        if not isinstance(value, int) or isinstance(value, bool):
            raise _ModelProtocolError(
                f"Model response {field_name} must be an integer."
            )

        return value

    @staticmethod
    def _response_indicates_context_length(
            response: httpx.Response,
    ) -> bool:
        if response.status_code == 413:
            return True

        if response.status_code != 400:
            return False

        response_text = response.text.lower()
        context_length_markers = (
            "context length",
            "context_length",
            "context window",
            "maximum context",
            "max context",
            "too many tokens",
            "token limit",
            "prompt is too long",
            "input is too long",
        )

        return any(
            marker in response_text
            for marker in context_length_markers
        )


    @staticmethod
    def _normalize_model_error(
            request_id: str,
            error: Exception,
            response: httpx.Response | None = None,
    ) -> ModelClientError:
        if isinstance(error, ModelClientError):
            return error

        if isinstance(error, httpx.HTTPStatusError):
            error_response = error.response
        else:
            error_response = response

        status_code = (
            error_response.status_code
            if error_response is not None
            else None
        )

        response_excerpt = None

        if error_response is not None:
            response_text = error_response.text.strip()

            if response_text:
                response_excerpt = response_text[:500]

        retry_after_seconds = None

        if error_response is not None:
            retry_after = error_response.headers.get("Retry-After")

            if retry_after is not None:
                try:
                    retry_after_seconds = float(retry_after)
                except ValueError:
                    pass

        if isinstance(error, httpx.TimeoutException):
            kind: ModelErrorKind = "timeout"
            message = "Model request timed out."
            retryable = True

        elif isinstance(error, httpx.ConnectError):
            kind = "connection"
            message = "Could not connect to the model endpoint."
            retryable = True

        elif isinstance(error, httpx.HTTPStatusError):
            message = f"Model endpoint returned HTTP {status_code}."

            if status_code in {401, 403}:
                kind = "authentication"
                retryable = False
            elif status_code == 429:
                kind = "rate_limit"
                retryable = True
            elif (
                error_response is not None
                and ModelClient._response_indicates_context_length(
                    error_response
                )
            ):
                kind = "context_length"
                retryable = False
            elif status_code is not None and 400 <= status_code < 500:
                kind = "bad_request"
                retryable = status_code == 408
            elif status_code is not None and 500 <= status_code < 600:
                kind = "server_error"
                retryable = True
            else:
                kind = "protocol_error"
                retryable = False

        elif isinstance(error, httpx.RequestError):
            kind = "connection"
            message = "Model request failed."
            retryable = True
        elif isinstance(error, _ModelRequestValidationError):
            kind = "bad_request"
            message = "Invalid model request."
            retryable = False

        elif isinstance(error, _ModelProtocolError):
            kind = "protocol_error"
            message = "Model endpoint returned an invalid response."
            retryable = False
        elif isinstance(error, _EmptyModelResponseError):
            kind = "empty_response"
            message = "Model endpoint returned no usable output."
            retryable = False

        else:
            kind = "internal_error"
            message = "Unexpected model client failure."
            retryable = False

        error_details = str(error).strip()

        if error_details:
            message = f"{message} {error_details}"

        return ModelClientError(
            request_id=request_id,
            kind=kind,
            message=message,
            status_code=status_code,
            retryable=retryable,
            retry_after_seconds=retry_after_seconds,
            response_excerpt=response_excerpt,
        )

    def call_model(
            self,
            messages: Sequence[Mapping[str, object]],
    ) -> ModelResponse:
        request_id = uuid4().hex

        response: httpx.Response | None = None
        started_at = time.perf_counter()

        try:
            payload = self._build_request_payload(messages)
            successful_response = self._send_http_request(
                payload=payload,
            )
            response = successful_response

            successful_response.raise_for_status()

            latency_ms = (
                (time.perf_counter() - started_at) * 1000
            )

            return self._parse_model_response(
                request_id=request_id,
                response=successful_response,
                latency_ms=latency_ms,
            )

        except Exception as error:
            normalized_error = self._normalize_model_error(
                request_id=request_id,
                error=error,
                response=response,
            )

            if normalized_error is error:
                raise

            raise normalized_error from error

    def close(self) -> None:
        self._http_client.close()

    def __enter__(self) -> ModelClient:
        return self

    def __exit__(
        self,
        exception_type: object,
        exception: object,
        traceback: object,
    ) -> None:
        self.close()