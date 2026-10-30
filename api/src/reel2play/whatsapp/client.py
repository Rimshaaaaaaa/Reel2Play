"""Calls to the WhatsApp Cloud API (official API only), with timeouts and retries.

Phone numbers pass through these calls and are never logged.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

import httpx

from reel2play.net import ExternalServiceError, make_client, raise_for_status, with_retries
from reel2play.settings import Settings, get_settings

SERVICE = "WhatsApp Cloud API"
MAX_MEDIA_BYTES = 16 * 1024 * 1024  # WhatsApp's own limit for videos
BUTTON_TITLE_MAX = 20


class WhatsAppClient:
    def __init__(self, settings: Settings, http: httpx.Client | None = None) -> None:
        self._base = f"{settings.graph_base_url.rstrip('/')}/{settings.graph_api_version}"
        self._phone_id = settings.whatsapp_phone_number_id
        self._token = settings.whatsapp_token.get_secret_value()
        self._http = http or make_client()

    @property
    def _auth(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._token}"}

    def _send(self, to: str, message: dict[str, object]) -> str:
        body = {"messaging_product": "whatsapp", "recipient_type": "individual", "to": to}

        def call() -> str:
            response = self._http.post(
                f"{self._base}/{self._phone_id}/messages",
                json={**body, **message},
                headers=self._auth,
            )
            raise_for_status(SERVICE, response)
            return str(response.json()["messages"][0]["id"])

        return with_retries(call)

    def send_text(self, to: str, text: str) -> str:
        return self._send(to, {"type": "text", "text": {"body": text, "preview_url": True}})

    def send_buttons(self, to: str, text: str, buttons: list[tuple[str, str]]) -> str:
        replies = [
            {"type": "reply", "reply": {"id": key, "title": title[:BUTTON_TITLE_MAX]}}
            for key, title in buttons
        ]
        interactive = {"type": "button", "body": {"text": text}, "action": {"buttons": replies}}
        return self._send(to, {"type": "interactive", "interactive": interactive})

    def send_video(self, to: str, link: str, caption: str) -> str:
        return self._send(to, {"type": "video", "video": {"link": link, "caption": caption}})

    def download_media(self, media_id: str) -> bytes:
        """Look up the media's short-lived URL, then download it with the same token."""

        def lookup() -> dict[str, object]:
            response = self._http.get(f"{self._base}/{media_id}", headers=self._auth)
            raise_for_status(SERVICE, response)
            data: dict[str, object] = response.json()
            return data

        info = with_retries(lookup)
        if int(str(info.get("file_size", 0))) > MAX_MEDIA_BYTES:
            raise ExternalServiceError(SERVICE, "the file is larger than 16 MB", status=413)

        def download() -> bytes:
            response = self._http.get(str(info["url"]), headers=self._auth)
            raise_for_status(SERVICE, response)
            return response.content

        return with_retries(download)


@dataclass
class ClientFactory:
    """Builds the client; tests swap ``build`` for one with a fake transport."""

    build: Callable[[Settings], WhatsAppClient] = field(default=lambda s: WhatsAppClient(s))

    def __call__(self) -> WhatsAppClient:
        return self.build(get_settings())


CLIENTS = ClientFactory()
