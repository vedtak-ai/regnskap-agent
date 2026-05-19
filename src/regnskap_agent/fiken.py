from __future__ import annotations

import json
import mimetypes
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any


BASE_URL = "https://api.fiken.no/api/v2"


class FikenError(RuntimeError):
    def __init__(self, status: int, body: str):
        super().__init__(f"Fiken API-feil {status}: {body}")
        self.status = status
        self.body = body


@dataclass
class Response:
    data: Any
    headers: dict[str, str]
    status: int


class FikenClient:
    def __init__(self, token: str, base_url: str = BASE_URL) -> None:
        self.token = token
        self.base_url = base_url.rstrip("/")
        self._last_request = 0.0

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_request
        if elapsed < 0.25:
            time.sleep(0.25 - elapsed)

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
            clean = {k: v for k, v in params.items() if v is not None}
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

        req = urllib.request.Request(url, data=data, headers=req_headers, method=method.upper())
        self._throttle()
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                self._last_request = time.monotonic()
                raw = resp.read()
                return Response(
                    data=_decode_body(raw),
                    headers=dict(resp.headers.items()),
                    status=resp.status,
                )
        except urllib.error.HTTPError as exc:
            self._last_request = time.monotonic()
            body_text = exc.read().decode("utf-8", errors="replace")
            raise FikenError(exc.code, body_text) from exc

    def get(self, path: str, params: dict[str, Any] | None = None) -> Response:
        return self.request("GET", path, params=params)

    def post(self, path: str, body: Any) -> Response:
        return self.request("POST", path, body=body)

    def patch(self, path: str, params: dict[str, Any] | None = None) -> Response:
        return self.request("PATCH", path, params=params)

    def get_paginated(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        page: int = 0,
        page_size: int = 25,
        all_pages: bool = False,
    ) -> dict[str, Any]:
        params = dict(params or {})
        results: list[Any] = []
        current = page
        pagination: dict[str, int] = {}

        while True:
            params["page"] = current
            params["pageSize"] = page_size
            response = self.get(path, params=params)
            page_data = response.data or []
            if isinstance(page_data, list):
                results.extend(page_data)
            else:
                results.append(page_data)

            pagination = _pagination_from_headers(response.headers, len(results), page_size)
            if not all_pages or current + 1 >= pagination["pageCount"] or not page_data:
                break
            current += 1

        return {"data": results, "pagination": pagination}

    def upload_file(
        self,
        path: str,
        file_path: Path,
        *,
        fields: dict[str, str | bool] | None = None,
        file_field: str = "file",
    ) -> Response:
        if not path.startswith("/"):
            path = "/" + path
        boundary = "----regnskap-agent-" + uuid.uuid4().hex
        body = _multipart_body(boundary, file_path, fields or {}, file_field=file_field)
        headers = {
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Content-Length": str(len(body)),
        }
        url = self.base_url + path
        req_headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/json",
            "User-Agent": "regnskap-agent/0.1",
            **headers,
        }
        req = urllib.request.Request(url, data=body, headers=req_headers, method="POST")
        self._throttle()
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                self._last_request = time.monotonic()
                raw = resp.read()
                return Response(
                    data=_decode_body(raw),
                    headers=dict(resp.headers.items()),
                    status=resp.status,
                )
        except urllib.error.HTTPError as exc:
            self._last_request = time.monotonic()
            body_text = exc.read().decode("utf-8", errors="replace")
            raise FikenError(exc.code, body_text) from exc


def company_path(company: str, resource: str) -> str:
    resource = resource.strip("/")
    return f"/companies/{company}/{resource}"


def _decode_body(raw: bytes) -> Any:
    if not raw:
        return None
    text = raw.decode("utf-8", errors="replace")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


def _pagination_from_headers(headers: dict[str, str], result_count: int, page_size: int) -> dict[str, int]:
    def read(name: str, fallback: int) -> int:
        value = headers.get(name) or headers.get(name.lower())
        if value is None:
            return fallback
        try:
            return int(value)
        except ValueError:
            return fallback

    return {
        "page": read("Fiken-Api-Page", 0),
        "pageSize": read("Fiken-Api-Page-Size", page_size),
        "pageCount": read("Fiken-Api-Page-Count", 1),
        "resultCount": read("Fiken-Api-Result-Count", result_count),
    }


def _multipart_body(
    boundary: str,
    file_path: Path,
    fields: dict[str, str | bool],
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
    mime_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    parts.append(
        (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="{file_field}"; filename="{filename}"\r\n'
            f"Content-Type: {mime_type}\r\n\r\n"
        ).encode("utf-8")
    )
    parts.append(file_path.read_bytes())
    parts.append(f"\r\n--{boundary}--\r\n".encode("utf-8"))
    return b"".join(parts)
