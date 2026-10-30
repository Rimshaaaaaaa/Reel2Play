"""Which videos the evaluation runs on, and what each shop told us about them.

The real set is 30 videos, five from each of six kinds of business, each from a shop that
agreed (or filmed by the team); ``consent`` says who agreed. The CI set is synthetic.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from reel2play.analysis import ProductCategory

BUSINESS_KINDS = (
    ProductCategory.CLOTHING,
    ProductCategory.BAKERY_FOOD,
    ProductCategory.SHOES,
    ProductCategory.COSMETICS,
    ProductCategory.PHONE_ACCESSORIES,
    ProductCategory.HOME_DECOR,
)


class EvalVideo(BaseModel):
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{0,39}$")
    category: ProductCategory
    file: str
    shop_name: str = Field(min_length=1, max_length=120)
    language: Literal["auto", "ur", "en"] = "auto"
    price: str | None = None
    offer: str | None = None
    whatsapp_number: str | None = None
    shop_url: str | None = "https://example.com/"
    consent: str = Field(min_length=3, description="Who agreed to this video being used")
    synthetic: bool = False
    mock_key: str | None = Field(default=None, description="Recorded answers for mock runs")

    @model_validator(mode="after")
    def _filled_in(self) -> EvalVideo:
        """The example manifest's <...> blanks must be replaced before a run."""
        blanks = [
            name
            for name, value in self.model_dump().items()
            if isinstance(value, str) and value.startswith("<") and value.endswith(">")
        ]
        if blanks:
            raise ValueError(f"{self.id}: fill in {', '.join(blanks)}")
        return self

    @model_validator(mode="after")
    def _contact(self) -> EvalVideo:
        if not self.whatsapp_number and not self.shop_url:
            raise ValueError(f"{self.id}: needs a WhatsApp number or a shop link")
        if self.category not in BUSINESS_KINDS:
            raise ValueError(f"{self.id}: category must be one of the six kinds of business")
        return self


class EvalManifest(BaseModel):
    name: str
    videos: list[EvalVideo] = Field(min_length=1)
    folder: Path = Path()

    @model_validator(mode="after")
    def _unique(self) -> EvalManifest:
        ids = [v.id for v in self.videos]
        if len(ids) != len(set(ids)):
            raise ValueError("video ids must be unique")
        return self

    def path_of(self, video: EvalVideo) -> Path:
        return (self.folder / video.file).resolve()


def load_manifest(path: Path) -> EvalManifest:
    data = json.loads(path.read_text(encoding="utf-8"))
    data.pop("_note", None)
    manifest = EvalManifest.model_validate({**data, "folder": path.parent})
    missing = [v.file for v in manifest.videos if not manifest.path_of(v).is_file()]
    if missing:
        raise FileNotFoundError(f"videos not found next to {path.name}: {', '.join(missing)}")
    return manifest
