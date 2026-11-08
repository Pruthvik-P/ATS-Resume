from __future__ import annotations

import asyncio
import html
import ipaddress
import re
import socket
from urllib.parse import urlparse

import httpx

from app.core.errors import AppError

MAX_HTML_BYTES = 2 * 1024 * 1024
_SCRIPT_STYLE_RE = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")
_BREAK_RE = re.compile(r"</?(?:p|div|li|h[1-6]|br|tr)[^>]*>", re.IGNORECASE)


async def _assert_public_host(host: str) -> None:
    try:
        loop = asyncio.get_running_loop()
        infos = await loop.getaddrinfo(host, None)
    except socket.gaierror as exc:
        raise AppError("jd_fetch_failed", f"Could not resolve host: {host}") from exc

    for info in infos:
        address = info[4][0]
        try:
            ip = ipaddress.ip_address(address)
        except ValueError:
            continue
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        ):
            raise AppError(
                "jd_url_blocked",
                "That URL resolves to a private or reserved address and is blocked.",
            )


def _html_to_text(raw: str) -> str:
    raw = _SCRIPT_STYLE_RE.sub(" ", raw)
    raw = _BREAK_RE.sub("\n", raw)
    raw = _TAG_RE.sub(" ", raw)
    raw = html.unescape(raw)
    raw = re.sub(r"[ \t]+", " ", raw)
    raw = re.sub(r"\n\s*\n+", "\n\n", raw)
    return raw.strip()


async def fetch_jd_from_url(url: str) -> str:
    """Fetch a job posting URL with SSRF guards and a hard size limit."""

    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise AppError("jd_url_invalid", "Only http and https URLs are supported.")
    if not parsed.hostname:
        raise AppError("jd_url_invalid", "The URL has no host.")
    await _assert_public_host(parsed.hostname)

    try:
        async with (
            httpx.AsyncClient(
                timeout=httpx.Timeout(10.0, connect=5.0),
                follow_redirects=False,
                headers={"User-Agent": "ats-engine/0.1 (+job-description-fetch)"},
            ) as client,
            client.stream("GET", url) as response,
        ):
                if response.status_code >= 300:
                    raise AppError(
                        "jd_fetch_failed",
                        f"The job page returned HTTP {response.status_code}. Paste the text instead.",
                    )
                content_type = response.headers.get("content-type", "")
                if not any(token in content_type for token in ("text/html", "text/plain", "application/xhtml")):
                    raise AppError(
                        "jd_fetch_unsupported",
                        f"Unsupported content type '{content_type}'. Paste the job text instead.",
                    )
                chunks: list[bytes] = []
                total = 0
                async for chunk in response.aiter_bytes():
                    total += len(chunk)
                    if total > MAX_HTML_BYTES:
                        raise AppError(
                            "jd_fetch_too_large",
                            "The job page is larger than 2 MB. Paste the relevant text instead.",
                        )
                    chunks.append(chunk)
    except httpx.HTTPError as exc:
        raise AppError("jd_fetch_failed", f"Could not fetch the job page: {exc}") from exc

    text = b"".join(chunks).decode("utf-8", errors="replace")
    cleaned = _html_to_text(text) if "html" in content_type else text.strip()
    if len(cleaned) < 100:
        raise AppError(
            "jd_fetch_empty",
            "The page did not contain enough readable text. It may require JavaScript; paste the JD instead.",
        )
    return cleaned[:60_000]
