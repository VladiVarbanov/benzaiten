# /home/vladi/local_ai/benzaiten/src/model_client.py

from __future__ import annotations

import time
from dataclasses import dataclass
from math import isfinite
from time import perf_counter
from typing import Any, Literal, Mapping, Sequence
from uuid import uuid4
import logging

logger = logging.getLogger(__name__)
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


class ModelClient:
    CHAT_COMPLETIONS_PATH = "/v1/chat/completions"

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
    ) -> dict[str, object] | None:
        if not messages:
            logger.warning(
                "Model request skipped because no messages were provided."
            )
            return None

        normalized_messages: list[dict[str, str]] = []

        for index, message in enumerate(messages):
            unsupported_keys = set(message) - {"role", "content"}

            if unsupported_keys:
                unsupported = ", ".join(sorted(unsupported_keys))

                raise ValueError(
                    f"Message {index} contains unsupported fields: "
                    f"{unsupported}."
                )

            role = message.get("role")
            content = message.get("content")

            if not isinstance(role, str) or not role:
                logger.warning(
                    "Model request skipped: message %s has an invalid role.",
                    index,
                )
                return None

            if not isinstance(content, str):
                logger.warning(
                    "Model request skipped: message %s content is not text.",
                    index,
                )
                return None

            if not content.strip():
                logger.warning(
                    "Model request skipped: message %s content is empty.",
                    index,
                )
                return None

            normalized_messages.append(
                {
                    "role": role,
                    "content": content,
                }
            )

        return {
            "model": self.config.model_name,
            "messages": normalized_messages,
            "max_completion_tokens": (
                self.config.max_completion_tokens
            ),
            "temperature": self.config.temperature,
            "top_p": self.config.top_p,
            "stream": False,
        }


    def _send_http_request(
            self,
            request_id: str,
            payload: Mapping[str, object],
    ) -> httpx.Response:
        try:
            return self._http_client.post(
                self.CHAT_COMPLETIONS_PATH,
                json=payload,
            )
        except httpx.HTTPError as error:
            raise ModelClientError(
                request_id=None,
                kind="transport_error",
                status_code=None,
                retryable=True,
                retry_after_seconds=None,
                response_excerpt=str(error),
            ) from error


    def _parse_model_response(
            self,
            request_id: str,
            response: httpx.Response,
            latency_ms: int,
    ) -> ModelResponse:
        response_data = response.json()

        choices = response_data.get("choices") or []

        if not choices:
            logger.warning(
                "Model response %s contains no choices.",
                request_id,
            )

            return ModelResponse(
                request_id=request_id,
                server_request_id=response_data.get("id"),
                model_name=response_data.get(
                    "model",
                    self.config.model_name,
                ),
                text="",
                reasoning_text=None,
                finish_reason="empty_response",
                prompt_tokens=0,
                completion_tokens=0,
                total_tokens=0,
                latency_ms=latency_ms,
            )

        choice = choices[0]
        message = choice.get("message") or {}
        usage = response_data.get("usage") or {}

        reasoning_text = (
                message.get("reasoning")
                or message.get("reasoning_content")
        )

        return ModelResponse(
            request_id=request_id,
            server_request_id=response_data.get("id"),
            model_name=response_data.get(
                "model",
                self.config.model_name,
            ),
            text=message.get("content") or "",
            reasoning_text=reasoning_text,
            finish_reason=choice.get("finish_reason"),
            prompt_tokens=usage.get("prompt_tokens", 0),
            completion_tokens=usage.get(
                "completion_tokens",
                0,
            ),
            total_tokens=usage.get("total_tokens", 0),
            latency_ms=latency_ms,
        )


    @staticmethod
    def _normalize_model_error(
            self,
            request_id: str,
            error: Exception,
            response: httpx.Response | None = None,
    ) -> ModelClientError:
        if isinstance(error, ModelClientError):
            return error

        error_response = (
            error.response
            if isinstance(error, httpx.HTTPStatusError)
            else response
        )

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
            kind = "timeout"
            message = "Model request timed out."
            retryable = True

        elif isinstance(error, httpx.ConnectError):
            kind = "connection"
            message = "Could not connect to the model endpoint."
            retryable = True

        elif isinstance(error, httpx.HTTPStatusError):
            kind = "http_status"
            message = f"Model endpoint returned HTTP {status_code}."
            retryable = (
                    status_code in {408, 429}
                    or status_code is not None
                    and 500 <= status_code < 600
            )

        elif isinstance(error, httpx.RequestError):
            kind = "request"
            message = "Model request failed."
            retryable = True

        elif isinstance(error, ValueError):
            kind = "invalid_response"
            message = "Model endpoint returned an invalid response."
            retryable = False

        else:
            kind = "unexpected"
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

        payload = self._build_request_payload(messages)

        if payload is None:
            return ModelResponse(
                request_id=request_id,
                server_request_id=None,
                model_name=self.config.model_name,
                text="",
                reasoning_text=None,
                finish_reason=None,
                prompt_tokens=0,
                completion_tokens=0,
                total_tokens=0,
                latency_ms=0,
            )

        response: httpx.Response | None = None
        started_at = time.perf_counter()

        try:
            response = self._send_http_request(
                request_id=request_id,
                payload=payload,
            )

            response.raise_for_status()

            latency_ms = int(
                (time.perf_counter() - started_at) * 1000
            )

            return self._parse_model_response(
                request_id=request_id,
                response=response,
                latency_ms=latency_ms,
            )

        except Exception as error:
            raise self._normalize_model_error(
                request_id=request_id,
                error=error,
                response=response,
            ) from error

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