from __future__ import annotations

import json
import mimetypes
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import certifi


BASE_URL = "https://api.folio.no/v2"
API_DOCS_URL = "https://api.folio.no/v2/api"
OPENAPI_URL = "https://api.folio.no/v2/api.yml"


class FolioError(RuntimeError):
    def __init__(self, status: int, body: str):
        super().__init__(f"Folio API-feil {status}: {body}")
        self.status = status
        self.body = body


@dataclass
class Response:
    data: Any
    headers: dict[str, str]
    status: int


class FolioClient:
    def __init__(self, token: str, base_url: str = BASE_URL) -> None:
        self.token = token
        self.base_url = base_url.rstrip("/")
        self._last_request = 0.0

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_request
        if elapsed < 0.25:
            time.sleep(0.25 - elapsed)

    def get(self, path: str, params: dict[str, Any] | None = None) -> Response:
        return self.request("GET", path, params=params)

    def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        body: Any | None = None,
        headers: dict[str, str] | None = None,
    ) -> Response:
        if not path.startswith("/"):
            path = "/" + path
        url = self.base_url + path
        if params:
            clean = {key: value for key, value in params.items() if value is not None}
            if clean:
                url += "?" + urllib.parse.urlencode(clean)

        req_headers = {
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/json",
                "User-Agent": "regnskap-agent/0.1",
        }
        data = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            req_headers["Content-Type"] = "application/json"
        if headers:
            req_headers.update(headers)
        request = urllib.request.Request(url, data=data, headers=req_headers, method=method.upper())
        self._throttle()
        context = ssl.create_default_context(cafile=certifi.where())
        try:
            with urllib.request.urlopen(request, timeout=60, context=context) as response:
                self._last_request = time.monotonic()
                raw = response.read()
                return Response(
                    data=_decode_body(raw),
                    headers=dict(response.headers.items()),
                    status=response.status,
                )
        except urllib.error.HTTPError as exc:
            self._last_request = time.monotonic()
            body_text = exc.read().decode("utf-8", errors="replace")
            raise FolioError(exc.code, body_text) from exc

    def get_bytes(self, path: str, params: dict[str, Any] | None = None) -> Response:
        if not path.startswith("/"):
            path = "/" + path
        url = self.base_url + path
        if params:
            clean = {key: value for key, value in params.items() if value is not None}
            if clean:
                url += "?" + urllib.parse.urlencode(clean)
        request = urllib.request.Request(
            url,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Accept": "*/*",
                "User-Agent": "regnskap-agent/0.1",
            },
            method="GET",
        )
        self._throttle()
        context = ssl.create_default_context(cafile=certifi.where())
        try:
            with urllib.request.urlopen(request, timeout=60, context=context) as response:
                self._last_request = time.monotonic()
                return Response(data=response.read(), headers=dict(response.headers.items()), status=response.status)
        except urllib.error.HTTPError as exc:
            self._last_request = time.monotonic()
            body_text = exc.read().decode("utf-8", errors="replace")
            raise FolioError(exc.code, body_text) from exc

    def upload_bytes(
        self,
        path: str,
        file_path: Path,
        *,
        content_type: str | None = None,
        filename: str | None = None,
    ) -> Response:
        content_type = content_type or mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
        headers = {"Content-Type": content_type}
        if filename or file_path.name:
            headers["Content-Disposition"] = f'attachment; filename="{filename or file_path.name}"'
        if not path.startswith("/"):
            path = "/" + path
        url = self.base_url + path
        request = urllib.request.Request(
            url,
            data=file_path.read_bytes(),
            headers={
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/json",
                "User-Agent": "regnskap-agent/0.1",
                **headers,
            },
            method="POST",
        )
        self._throttle()
        context = ssl.create_default_context(cafile=certifi.where())
        try:
            with urllib.request.urlopen(request, timeout=120, context=context) as response:
                self._last_request = time.monotonic()
                return Response(
                    data=_decode_body(response.read()),
                    headers=dict(response.headers.items()),
                    status=response.status,
                )
        except urllib.error.HTTPError as exc:
            self._last_request = time.monotonic()
            body_text = exc.read().decode("utf-8", errors="replace")
            raise FolioError(exc.code, body_text) from exc


def _decode_body(raw: bytes) -> Any:
    if not raw:
        return None
    text = raw.decode("utf-8", errors="replace")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text
