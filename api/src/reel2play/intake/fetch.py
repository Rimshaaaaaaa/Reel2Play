"""Fetching a shop's video from a public web address (feature 52), safely.

- Only ``https://`` on the standard port, with no user name or password in the link.
- The host name must resolve only to public internet addresses: never this server, the
  private network or a cloud metadata address.
- The connection goes to the very address that was checked (the TLS certificate is still
  checked against the host name), so a name that changes its answer between the check and
  the connection cannot reach inside.
- Redirects are followed by hand, at most three, each checked the same way.
- The download stops as soon as it is larger than an upload may be.
"""

from __future__ import annotations

import ipaddress
import socket
from collections.abc import Callable
from dataclasses import dataclass, field

import httpx

MAX_REDIRECTS = 3
CHUNK = 256 * 1024
TIMEOUT_S = 30.0

Resolver = Callable[[str], list[str]]


class FetchError(ValueError):
    """The link cannot be fetched; the message says why, in plain words."""


def system_resolver(host: str) -> list[str]:
    try:
        found = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise FetchError("That web address does not exist.") from exc
    return list(dict.fromkeys(str(info[4][0]) for info in found))


def public_address(host: str, resolve: Resolver) -> str:
    """The address to connect to, if every address the host has is on the public internet."""
    try:
        literal = ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        addresses = resolve(host)
    else:
        addresses = [str(literal)]
    if not addresses:
        raise FetchError("That web address does not exist.")
    for address in addresses:
        ip = ipaddress.ip_address(address)
        if not ip.is_global or ip.is_multicast:
            raise FetchError("That link does not point to the public internet.")
    return addresses[0]


def checked_url(address: str) -> httpx.URL:
    try:
        url = httpx.URL(address)
    except httpx.InvalidURL as exc:
        raise FetchError("That is not a web address.") from exc
    if url.scheme != "https" or not url.host:
        raise FetchError("Only https:// links can be fetched.")
    if url.userinfo:
        raise FetchError("Links with a user name or password are not fetched.")
    if url.port not in (None, 443):
        raise FetchError("Only links on the standard https port are fetched.")
    return url


@dataclass
class Fetcher:
    """Downloads one file; tests give it a fake transport and resolver."""

    transport: httpx.BaseTransport | None = None
    resolve: Resolver = field(default=system_resolver)
    timeout: float = TIMEOUT_S

    def fetch(self, address: str, max_bytes: int) -> bytes:
        try:
            return self._fetch(address, max_bytes)
        except httpx.HTTPError as exc:
            raise FetchError("The link could not be reached. Check it opens in a browser.") from exc

    def _fetch(self, address: str, max_bytes: int) -> bytes:
        with httpx.Client(
            transport=self.transport, timeout=self.timeout, follow_redirects=False
        ) as http:
            for _ in range(MAX_REDIRECTS + 1):
                url = checked_url(address)
                ip = public_address(url.host, self.resolve)
                pinned = url.copy_with(host=ip)
                with http.stream(
                    "GET",
                    pinned,
                    headers={"Host": url.host, "Accept": "video/*, image/*"},
                    extensions={"sni_hostname": url.host},
                ) as response:
                    if response.is_redirect and "location" in response.headers:
                        address = str(url.join(response.headers["location"]))
                        continue
                    if not response.is_success:
                        raise FetchError(
                            f"The link answered with an error ({response.status_code})."
                        )
                    data = bytearray()
                    for chunk in response.iter_bytes(CHUNK):
                        data += chunk
                        if len(data) > max_bytes:
                            raise FetchError(
                                f"The file is larger than {max_bytes // (1024 * 1024)} MB."
                            )
                    return bytes(data)
        raise FetchError("The link kept sending us somewhere else.")


@dataclass
class FetcherFactory:
    build: Callable[[], Fetcher] = field(default=Fetcher)

    def __call__(self) -> Fetcher:
        return self.build()


FETCHERS = FetcherFactory()
