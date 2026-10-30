from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import update
from sqlalchemy.orm import Session

from reel2play import audit
from reel2play.models import AuditEntry


def test_chain_links_each_entry_to_the_previous(session: Session) -> None:
    first = audit.record(
        session, actor="system", action="a", subject_type="video", subject_id="v1", data={"n": 1}
    )
    second = audit.record(
        session, actor="director", action="b", subject_type="video", subject_id="v1", data={"n": 2}
    )
    assert first.prev_hash == audit.GENESIS_HASH
    assert second.prev_hash == first.entry_hash
    session.commit()
    assert audit.verify_chain(session) == audit.ChainCheck(ok=True, checked=2)


def test_tampering_is_detected(session: Session) -> None:
    for n in range(3):
        audit.record(
            session, actor="system", action="step", subject_type="ad", subject_id="x", data={"n": n}
        )
    session.commit()
    session.execute(update(AuditEntry).where(AuditEntry.id == 2).values(data={"n": 99}))
    session.commit()
    check = audit.verify_chain(session)
    assert not check.ok
    assert check.first_bad_id == 2
    assert check.checked == 1


def test_entries_for_filters_by_subject(session: Session) -> None:
    audit.record(session, actor="a", action="x", subject_type="video", subject_id="1")
    audit.record(session, actor="a", action="y", subject_type="video", subject_id="2")
    session.commit()
    assert [e.action for e in audit.entries_for(session, "video", "2")] == ["y"]


def test_audit_routes(client: TestClient, session: Session) -> None:
    audit.record(
        session,
        actor="shop",
        action="upload.received",
        subject_type="video",
        subject_id="abc",
        data={"files": 1},
    )
    session.commit()
    trail = client.get("/api/audit/video/abc").json()
    assert trail[0]["action"] == "upload.received"
    assert client.get("/api/audit/verify").json() == {
        "ok": True,
        "checked": 1,
        "first_bad_id": None,
    }
