from __future__ import annotations

import json
import mimetypes
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import certifi


@dataclass
class ApiResponse:
    data: Any
    headers: dict[str, str]
    status: int


class ApiError(RuntimeError):
    def __init__(self, provider: str, status: int, body: str):
        super().__init__(f"{provider} API-feil {status}: {body}")
        self.provider = provider
        self.status = status
        self.body = body


class JsonApiClient:
    def __init__(
        self,
        *,
        provider: str,
        base_url: str,
        default_headers: dict[str, str],
        min_interval_seconds: float = 0.25,
    ) -> None:
        self.provider = provider
        self.base_url = base_url.rstrip("/")
        self.default_headers = default_headers
        self.min_interval_seconds = min_interval_seconds
        self._last_request = 0.0

    def get(self, path: str, params: dict[str, Any] | None = None) -> ApiResponse:
        return self.request("GET", path, params=params)

    def post(self, path: str, body: Any | None = None, params: dict[str, Any] | None = None) -> ApiResponse:
        return self.request("POST", path, params=params, body=body)

    def put(self, path: str, body: Any | None = None, params: dict[str, Any] | None = None) -> ApiResponse:
        return self.request("PUT", path, params=params, body=body)

    def delete(self, path: str, params: dict[str, Any] | None = None) -> ApiResponse:
        return self.request("DELETE", path, params=params)

    def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        body: Any | None = None,
        headers: dict[str, str] | None = None,
    ) -> ApiResponse:
        url = self._url(path, params)
        req_headers = dict(self.default_headers)
        data = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            req_headers["Content-Type"] = "application/json"
        if headers:
            req_headers.update(headers)

        request = urllib.request.Request(url, data=data, headers=req_headers, method=method.upper())
        return self._open(request, timeout=60)

    def get_bytes(self, path: str, params: dict[str, Any] | None = None) -> ApiResponse:
        request = urllib.request.Request(
            self._url(path, params),
            headers={**self.default_headers, "Accept": "*/*"},
            method="GET",
        )
        return self._open(request, timeout=120, decode=False)

    def upload_multipart(
        self,
        path: str,
        file_path: Path,
        *,
        fields: dict[str, str | bool | int] | None = None,
        file_field: str = "file",
        params: dict[str, Any] | None = None,
    ) -> ApiResponse:
        boundary = "----regnskap-agent-" + uuid.uuid4().hex
        body = multipart_body(boundary, file_path, fields or {}, file_field=file_field)
        request = urllib.request.Request(
            self._url(path, params),
            data=body,
            headers={
                **self.default_headers,
                "Accept": "application/json",
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                "Content-Length": str(len(body)),
            },
            method="POST",
        )
        return self._open(request, timeout=120)

    def _url(self, path: str, params: dict[str, Any] | None = None) -> str:
        if not path.startswith("/"):
            path = "/" + path
        url = self.base_url + path
        if params:
            clean = {key: value for key, value in params.items() if value is not None}
            if clean:
                url += "?" + urllib.parse.urlencode(clean)
        return url

    def _open(self, request: urllib.request.Request, *, timeout: int, decode: bool = True) -> ApiResponse:
        elapsed = time.monotonic() - self._last_request
        if elapsed < self.min_interval_seconds:
            time.sleep(self.min_interval_seconds - elapsed)
        context = ssl.create_default_context(cafile=certifi.where())
        try:
            with urllib.request.urlopen(request, timeout=timeout, context=context) as response:
                self._last_request = time.monotonic()
                raw = response.read()
                return ApiResponse(
                    data=decode_body(raw) if decode else raw,
                    headers=dict(response.headers.items()),
                    status=response.status,
                )
        except urllib.error.HTTPError as exc:
            self._last_request = time.monotonic()
            body_text = exc.read().decode("utf-8", errors="replace")
            raise ApiError(self.provider, exc.code, body_text) from exc


def decode_body(raw: bytes) -> Any:
    if not raw:
        return None
    text = raw.decode("utf-8", errors="replace")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


def multipart_body(
    boundary: str,
    file_path: Path,
    fields: dict[str, str | bool | int],
    *,
    file_field: str,
) -> bytes:
    parts: list[bytes] = []
    for name, value in fields.items():
        rendered = "true" if value is True else "false" if value is False else str(value)
        parts.append(
            (
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="{name}"\r\n\r\n'
                f"{rendered}\r\n"
            ).encode("utf-8")
        )

    filename = file_path.name
    content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    parts.append(
        (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="{file_field}"; filename="{filename}"\r\n'
            f"Content-Type: {content_type}\r\n\r\n"
        ).encode("utf-8")
        + file_path.read_bytes()
        + b"\r\n"
    )
    parts.append(f"--{boundary}--\r\n".encode("utf-8"))
    return b"".join(parts)
