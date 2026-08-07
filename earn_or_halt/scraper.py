from __future__ import annotations

import ipaddress
import socket
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from typing import Any


class _PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title = ""
        self.description = ""
        self.h1 = ""
        self.paragraph = ""
        self._capture: str | None = None
        self._buffer: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        attributes = {key.lower(): (value or "") for key, value in attrs}
        if tag == "meta" and attributes.get("name", "").lower() == "description":
            self.description = attributes.get("content", "").strip()[:500]
        if tag in {"title", "h1", "p"}:
            target = "paragraph" if tag == "p" else tag
            if target == "title" and self.title:
                return
            if target == "h1" and self.h1:
                return
            if target == "paragraph" and self.paragraph:
                return
            self._capture = target
            self._buffer = []

    def handle_endtag(self, tag: str) -> None:
        target = "paragraph" if tag.lower() == "p" else tag.lower()
        if self._capture != target:
            return
        text = " ".join("".join(self._buffer).split())[:1000]
        if text:
            setattr(self, target, text)
        self._capture = None
        self._buffer = []

    def handle_data(self, data: str) -> None:
        if self._capture:
            self._buffer.append(data)


def _validate_public_url(url: str, *, allow_http: bool) -> urllib.parse.ParseResult:
    parsed = urllib.parse.urlparse(url)
    allowed = {"https"}
    if allow_http:
        allowed.add("http")
    if parsed.scheme.lower() not in allowed:
        raise ValueError("company_url must use HTTPS")
    if not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("company_url contains an invalid authority")
    if parsed.port not in {None, 80, 443}:
        raise ValueError("company_url uses a blocked port")

    addresses = socket.getaddrinfo(parsed.hostname, parsed.port or 443, type=socket.SOCK_STREAM)
    if not addresses:
        raise ValueError("company_url hostname did not resolve")
    for address in addresses:
        ip = ipaddress.ip_address(address[4][0])
        if not ip.is_global:
            raise ValueError("company_url resolves to a non-public address")
    return parsed


class _SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    def __init__(self, *, allow_http: bool):
        super().__init__()
        self.allow_http = allow_http

    def redirect_request(self, req: Any, fp: Any, code: int, msg: str, headers: Any, newurl: str):
        _validate_public_url(newurl, allow_http=self.allow_http)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch_company_context(
    url: str,
    *,
    allow_http: bool = False,
    timeout_seconds: int = 8,
    maximum_bytes: int = 262_144,
) -> dict[str, str]:
    _validate_public_url(url, allow_http=allow_http)
    opener = urllib.request.build_opener(_SafeRedirectHandler(allow_http=allow_http))
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "EarnOrHalt/0.1 (+https://example.invalid/earn-or-halt)",
            "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.1",
        },
    )
    with opener.open(request, timeout=timeout_seconds) as response:
        content_type = response.headers.get_content_type()
        if content_type not in {"text/html", "application/xhtml+xml"}:
            raise ValueError(f"unsupported company page content type: {content_type}")
        raw = response.read(maximum_bytes + 1)
        if len(raw) > maximum_bytes:
            raise ValueError("company page is too large")
        charset = response.headers.get_content_charset() or "utf-8"
    parser = _PageParser()
    parser.feed(raw.decode(charset, errors="replace"))
    return {
        key: value
        for key, value in {
            "title": parser.title,
            "description": parser.description,
            "h1": parser.h1,
            "paragraph": parser.paragraph,
        }.items()
        if value
    }
