"""Builder (features 12, 14 to 17, 20, 21): templates, palette, CTA, assets, compiling."""

from __future__ import annotations

import base64
import io
import json
import random
import re
import uuid
from pathlib import Path
from urllib.parse import unquote

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from pydantic import ValidationError
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from reel2play import audit
from reel2play.analysis import Box, CreativeBrief
from reel2play.builder.assets import photo_data_url, sprite_data_url, square_crop
from reel2play.builder.config import GameConfig
from reel2play.builder.cta import build_cta, coupon_code, order_message
from reel2play.builder.html import (
    BudgetExceededError,
    EngineMissingError,
    compile_game,
    script_json,
)
from reel2play.builder.proposal import (
    AssetInputs,
    GameProposal,
    assemble,
    choose_template,
    language_note,
    safe_offer,
)
from reel2play.builder.templates import (
    ParamRange,
    TemplateSpec,
    Tier,
    default_for,
    load_templates,
)
from reel2play.builder.theme import (
    MIN_CONTRAST,
    build_palette,
    contrast,
    palette_problems,
    pick_colours,
)
from reel2play.deps import get_storage
from reel2play.jobs.queue import run_due
from reel2play.models import Ad, Build, Shop, Video
from reel2play.settings import get_settings

ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.usefixtures("stop_after_build")
FIXTURES = ROOT / "fixtures/synthetic"
SPRITE = (FIXTURES / "synthetic-sprite.png").read_bytes()
PHOTO = (FIXTURES / "synthetic-photo.jpg").read_bytes()


@pytest.fixture
def templates() -> dict[str, TemplateSpec]:
    return load_templates(get_settings().templates_dir)


def brief(**changes: object) -> CreativeBrief:
    base: dict[str, object] = {
        "product": {
            "name": "Canvas sneaker",
            "category": "shoes",
            "description": "A sneaker.",
            "segment_prompt": "shoe",
        },
        "palette": ["#c8243a", "#ffffff", "#1c1a36", "#f2b705"],
        "mood": "bright",
        "audience": "young people",
        "tone_of_voice": "friendly",
        "language": "en",
        "price": "Rs 2,499",
        "offer_text": "20% off this week",
        "offer_source": "owner",
        "cod_available": True,
        "free_delivery": False,
        "seen_price": None,
        "cta": {"kind": "whatsapp", "target": "923001234567"},
        "key_frames": [{"index": 0, "time_s": 0.5, "key": "k.jpg", "reason": "sharp"}],
        "logo_key": None,
    }
    return CreativeBrief.model_validate({**base, **changes})


def proposal(**changes: object) -> GameProposal:
    base: dict[str, object] = {
        "template": "catch",
        "reason": "fun",
        "difficulty": "normal",
        "title": "Catch it!",
        "instruction": "Slide the bag.",
        "win_text": "You won!",
        "lose_text": "So close!",
        "cta_label": "Order now",
        "product_label": "Sneaker",
        "offer_line": "Save 20% this week",
        "primary_color": "#c8243a",
        "accent_color": "#f2b705",
    }
    return GameProposal.model_validate({**base, **changes})


ASSETS = AssetInputs(
    product=sprite_data_url(SPRITE), product_photo=photo_data_url(PHOTO, None), logo=None
)


# --- templates ----------------------------------------------------------------------------


def test_templates_load_and_resolve(templates: dict[str, TemplateSpec]) -> None:
    assert set(templates) == {
        "catch", "runner", "puzzle", "memory", "scratch", "spots", "stack", "quiz", "colours",
        "custom",
    }  # fmt: skip
    catch = templates["catch"]
    assert catch.resolve(Tier.NORMAL)["goal"] == 10
    assert catch.resolve(Tier.EASY, {"goal": 99, "unknown": 1})["goal"] == 14
    assert "Control: Drag or tap" in catch.catalog_line()
    assert templates["puzzle"].uses_photo
    assert default_for(brief().product.category, templates).id == "runner"
    other = brief(
        product={"name": "x", "category": "other", "description": "", "segment_prompt": "x"}
    )
    assert default_for(other.product.category, templates).id == "catch"


def test_template_files_are_checked(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="between min and max"):
        ParamRange(easy=1, normal=2, hard=9, min=0, max=5)
    folder = tmp_path / "wrong"
    folder.mkdir()
    spec = json.loads((get_settings().templates_dir / "catch/template.json").read_text())
    (folder / "template.json").write_text(json.dumps(spec))
    with pytest.raises(ValueError, match="must match its folder"):
        load_templates(folder.parent)
    with pytest.raises(FileNotFoundError):
        load_templates(tmp_path / "empty")


# --- palette ------------------------------------------------------------------------------


def test_palette_is_always_readable() -> None:
    rng = random.Random(4)
    for _ in range(200):
        colours = [f"#{rng.randrange(0, 0xFFFFFF):06x}" for _ in range(rng.randint(1, 5))]
        palette = build_palette(colours)
        assert palette_problems(palette) == []
        assert contrast(palette.primary_ink, palette.primary) >= MIN_CONTRAST
        assert contrast(palette.accent_ink, palette.accent) >= MIN_CONTRAST


def test_palette_choices() -> None:
    assert pick_colours(["#ffffff", "#000000"], None, None) == ("#3949ab", "#f2b705")
    assert pick_colours(["#c8243a", "#1c5bd9"], "#1C5BD9", "#c8243a") == ("#1c5bd9", "#c8243a")
    assert pick_colours(["#c8243a"], "#123456", None)[0] == "#c8243a"
    bad = build_palette(["#c8243a"]).model_copy(update={"muted": "#eeeeee"})
    assert "muted on surface" in palette_problems(bad)[0]


# --- call to action -----------------------------------------------------------------------


def test_whatsapp_link_has_the_order_written() -> None:
    ad_id = uuid.UUID("12345678-1234-5678-1234-567812345678")
    code = coupon_code(ad_id)
    assert re.fullmatch(r"R2P-[A-HJ-NP-Z2-9]{4}", code)
    assert coupon_code(ad_id) == code
    message = order_message("en", "Ali Shoes", "Sneaker", code)
    cta = build_cta("whatsapp", "923001234567", message)
    assert cta.url.startswith("https://wa.me/923001234567?text=")
    assert (
        unquote(cta.url.split("text=")[1])
        == f"Hi Ali Shoes! I played your game and want to order: Sneaker. My code: {code}"
    )
    assert "میرا کوڈ" in order_message("ur", "علی", "جوتا", code)
    assert order_message("en", "S", "P", None).endswith("order: P.")
    assert build_cta("link", "https://shop.pk/item", "x").url == "https://shop.pk/item"
    with pytest.raises(ValueError, match="WhatsApp number or an https"):
        build_cta("link", None, "x")


# --- assets -------------------------------------------------------------------------------


def test_assets_are_small_and_right_shaped() -> None:
    url = sprite_data_url(SPRITE)
    assert url.startswith("data:image/webp;base64,")
    assert len(url) < 30_000
    photo = photo_data_url(PHOTO, Box(x0=0.2, y0=0.3, x1=0.8, y1=0.7))
    image = Image.open(io.BytesIO(base64.b64decode(photo.split(",", 1)[1])))
    assert image.size == (480, 480)
    assert square_crop(640, 360, None) == (140, 0, 500, 360)
    assert square_crop(100, 100, Box(x0=0.9, y0=0.9, x1=1, y1=1)) == (87, 87, 100, 100)


# --- assembling the config ----------------------------------------------------------------


def test_assemble_builds_a_valid_config(templates: dict[str, TemplateSpec]) -> None:
    result = assemble(
        ad_id=uuid.uuid4(),
        shop_name="Ali Shoes",
        brief=brief(),
        proposal=proposal(),
        templates=templates,
        assets=ASSETS,
        seed=5,
    )
    config = result.config
    assert config.template == "catch"
    assert config.text.price == "Rs 2,499"
    assert config.text.offer == "Save 20% this week"
    assert config.assets.product_photo is None  # only the puzzle uses the photo
    assert config.difficulty["goal"] == 10
    assert config.cta.url.startswith("https://wa.me/923001234567")
    assert result.notes == []
    wire = config.wire()
    assert wire["palette"]["primaryInk"] in ("#ffffff", "#23232e")  # type: ignore[index]
    assert "maxSeconds" in wire


def test_code_corrects_the_proposal(templates: dict[str, TemplateSpec]) -> None:
    spec, note = choose_template(proposal(template="dance_off"), brief(), templates)
    assert spec.id == "runner"
    assert note is not None
    assert "not available" in note
    assert safe_offer("Save 50% now", "20% off") == (
        "20% off",
        "the offer line changed the numbers; used the offer as given",
    )
    assert safe_offer("Big sale", None)[0] is None
    assert safe_offer(None, None) == (None, None)
    assert safe_offer(None, "20% off") == ("20% off", None)
    result = assemble(
        ad_id=uuid.uuid4(),
        shop_name="S",
        brief=brief(language="ur", offer_text=None, price=None),
        proposal=proposal(
            template="puzzle", difficulty="hard", difficulty_overrides={"misplaced": 2}
        ),
        templates=templates,
        assets=ASSETS,
        seed=1,
    )
    assert result.config.direction == "rtl"
    assert result.config.text.offer is None
    assert result.config.text.price is None
    assert result.config.assets.product_photo is not None
    assert result.config.difficulty["misplaced"] == 4  # clamped to the template's minimum
    assert any("not in Urdu" in n for n in result.notes)
    assert language_note("en", result.config.text) is None


def test_config_schema_rejects_bad_values(templates: dict[str, TemplateSpec]) -> None:
    good = assemble(
        ad_id=uuid.uuid4(),
        shop_name="S",
        brief=brief(),
        proposal=proposal(),
        templates=templates,
        assets=ASSETS,
        seed=1,
    ).config
    raw = good.model_dump()
    raw["palette"]["primary"] = "red"
    with pytest.raises(ValidationError):
        GameConfig.model_validate(raw)
    with pytest.raises(ValidationError):
        GameConfig.model_validate({**good.model_dump(), "max_seconds": 45})


# --- compiling ----------------------------------------------------------------------------


def test_compile_fills_the_shell(templates: dict[str, TemplateSpec]) -> None:
    config = assemble(
        ad_id=uuid.uuid4(),
        shop_name="S",
        brief=brief(),
        proposal=proposal(title="</script><b>x"),
        templates=templates,
        assets=ASSETS,
        seed=1,
    ).config
    settings = get_settings()
    built = compile_game(config, settings.engine_dist_dir, settings.max_game_bytes)
    page = built.html.decode()
    assert "{{" not in page
    assert '<html lang="en" dir="ltr">' in page
    assert "</script><b>x" not in page
    assert "<title>&lt;/script&gt;&lt;b&gt;x</title>" in page
    assert built.size < 2 * 1024 * 1024
    assert len(built.sha256) == 64
    with pytest.raises(BudgetExceededError, match="limit is 0 MB"):
        compile_game(config, settings.engine_dist_dir, 1000)
    with pytest.raises(EngineMissingError):
        compile_game(config, Path("/nowhere"), settings.max_game_bytes)


def test_script_json_is_safe() -> None:
    text = script_json({"a": "</script>\u2028"})
    assert "<" not in text
    assert "\\u2028" in text


# --- the build step -----------------------------------------------------------------------


def _upload(client: TestClient, sample: Path, **fields: str) -> uuid.UUID:
    data = {"shop_name": "Synthetic Shoes", "rights_confirmed": "true", **fields}
    response = client.post(
        "/api/uploads", data=data, files=[("files", (sample.name, sample.read_bytes()))]
    )
    return uuid.UUID(response.json()["id"])


def test_pipeline_builds_a_game(
    client: TestClient, session: Session, sample_media: dict[str, Path]
) -> None:
    video_id = _upload(
        client,
        sample_media["product_video"],
        price="Rs 3,200",
        whatsapp_number="923001234567",
        offer="20% off this week",
    )
    assert run_due("test") == 4
    session.expire_all()
    ad = session.scalars(select(Ad).where(Ad.video_id == video_id)).one()
    assert ad.step == "build"
    assert ad.template == "catch"
    build = session.scalars(select(Build).where(Build.ad_id == ad.id)).one()
    assert build.number == 1
    assert build.size_bytes < 2 * 1024 * 1024
    assert "assets" not in build.config
    page = get_storage().get(build.html_key).decode()
    assert "Rs 3,200" in page
    assert "wa.me/923001234567" in page
    actions = [e.action for e in audit.entries_for(session, "ad", ad.id)]
    assert actions[-4:] == ["build.started", "game.designed", "build.done", "pipeline.stopped"]
    body = client.get(f"/api/ads/{ad.id}").json()
    assert body["template"] == "catch"
    preview = client.get(body["build_url"].removeprefix("http://testserver"))
    assert preview.headers["content-type"].startswith("text/html")
    assert "sandbox allow-scripts" in preview.headers["content-security-policy"]


def test_urdu_sample_builds_a_runner(
    client: TestClient, session: Session, sample_media: dict[str, Path]
) -> None:
    video_id = _upload(
        client, sample_media["product_video"], language="ur", shop_url="https://shop.example"
    )
    session.execute(update(Video).where(Video.id == video_id).values(sample_key="urdu"))
    session.commit()
    run_due("test")
    session.expire_all()
    ad = session.scalars(select(Ad).where(Ad.video_id == video_id)).one()
    build = session.scalars(select(Build).where(Build.ad_id == ad.id)).one()
    assert build.template == "runner"
    page = get_storage().get(build.html_key).decode()
    assert 'dir="rtl"' in page
    assert "https://shop.example" in page
    assert "دوڑیں اور جوتا جیتیں" in page


def test_build_needs_a_sprite(session: Session) -> None:
    from reel2play.jobs import enqueue
    from reel2play.models import Analysis
    from reel2play.pipeline.runner import STEP_JOB

    shop = Shop(name="S")
    session.add(shop)
    session.flush()
    video = Video(shop_id=shop.id)
    session.add(video)
    session.flush()
    ad = Ad(shop_id=shop.id, video_id=video.id)
    session.add(ad)
    session.flush()
    session.add(
        Analysis(ad_id=ad.id, video_id=video.id, reading={}, brief=brief().model_dump(mode="json"))
    )
    enqueue(session, STEP_JOB, {"ad_id": str(ad.id), "step": "build"})
    session.commit()
    run_due("test")
    session.refresh(ad)
    assert ad.status == "failed"
    assert ad.error == "the product has not been cut out yet"
