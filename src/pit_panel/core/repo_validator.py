"""Strict repository URL validation for all git network entry points."""

import asyncio
import ipaddress
import os
import socket
from urllib.parse import urlparse

ALLOWED_REPOSITORY_HOSTS = {"github.com", "gitlab.com", "bitbucket.org"}
_DNS_RESOLUTION_LIMIT = asyncio.Semaphore(16)


def isolated_git_env() -> dict[str, str]:
    env = os.environ.copy()
    env["GIT_CONFIG_NOSYSTEM"] = "1"
    env["GIT_CONFIG_GLOBAL"] = os.devnull
    return env


def redact_repository_url(repo_url: str) -> str:
    parsed = urlparse(repo_url)
    if parsed.scheme and parsed.netloc:
        return parsed._replace(netloc=parsed.hostname or "", query="", fragment="").geturl()
    if repo_url.startswith("git@"):
        return "git@" + repo_url[4:].split(":", 1)[0] + ":…"
    return "<redacted>"


def validate_repository_url(repo_url: str) -> bool:
    if not repo_url or repo_url.startswith("-"):
        return False
    if repo_url.startswith("git@"):
        host = repo_url[4:].split(":", 1)[0].lower().rstrip(".")
        scheme = "ssh"
    else:
        parsed = urlparse(repo_url)
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            return False
        scheme = parsed.scheme
        host = (parsed.hostname or "").lower().rstrip(".")
    if scheme not in {"http", "https", "git", "ssh"} or not host:
        return False
    if host not in ALLOWED_REPOSITORY_HOSTS and not any(
        host.endswith("." + allowed) for allowed in ALLOWED_REPOSITORY_HOSTS
    ):
        return False
    try:
        for info in socket.getaddrinfo(host, None):
            address = ipaddress.ip_address(info[4][0])
            if any(
                (
                    address.is_private,
                    address.is_loopback,
                    address.is_link_local,
                    address.is_reserved,
                    address.is_multicast,
                )
            ):
                return False
    except OSError:
        return False
    return True


async def validate_repository_url_async(repo_url: str, timeout: float = 2.0) -> bool:
    """Run blocking DNS validation off the event loop with a hard request bound."""
    try:
        await asyncio.wait_for(_DNS_RESOLUTION_LIMIT.acquire(), timeout)
        worker = asyncio.create_task(asyncio.to_thread(validate_repository_url, repo_url))
        try:
            result = await asyncio.wait_for(asyncio.shield(worker), timeout)
        except (TimeoutError, asyncio.CancelledError):
            worker.add_done_callback(lambda _: _DNS_RESOLUTION_LIMIT.release())
            raise
        else:
            _DNS_RESOLUTION_LIMIT.release()
            return result
    except (TimeoutError, OSError):
        return False
