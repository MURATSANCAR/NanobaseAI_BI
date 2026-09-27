"""Kampüs sesli bülteni: ekleme, biçim denetimi, yayın, Range ile çalma, silme."""
import pytest
import sqlalchemy as sa

from semantic_bridge import bulletins as B

MP3 = b"ID3\x04\x00\x00\x00\x00\x00\x00" + bytes(range(256)) * 40


@pytest.fixture()
def engine(tmp_path, monkeypatch):
    monkeypatch.setenv("KAMPUS_BULLETIN_DIR", str(tmp_path / "ses"))
    return sa.create_engine(f"sqlite:///{tmp_path / 'b.db'}")


def test_added_bulletin_is_a_draft_until_published(engine):
    b = B.add(engine, "t", "admin", MP3, original_name="haftanin_bulteni-42.mp3", duration_sec="842.4")
    assert b["status"] == B.DRAFT and b["mime"] == "audio/mpeg"
    assert b["title"] == "haftanin bulteni 42" and b["durationSec"] == 842.4
    assert B.current(engine, "t") is None
    B.update(engine, "t", b["id"], {"status": B.PUBLISHED, "title": "Matbaadan Raflara", "episode": "42"})
    cur = B.current(engine, "t")
    assert cur["id"] == b["id"] and cur["title"] == "Matbaadan Raflara" and cur["episode"] == 42 and cur["publishedAt"]


def test_latest_published_is_current(engine):
    a = B.add(engine, "t", "u", MP3, title="Eski", publish=True)
    b = B.add(engine, "t", "u", MP3, title="Yeni", publish=True)
    assert B.current(engine, "t")["id"] == b["id"]
    B.update(engine, "t", b["id"], {"status": B.DRAFT})
    assert B.current(engine, "t")["id"] == a["id"]


def test_non_audio_and_oversize_are_refused(engine, monkeypatch):
    with pytest.raises(B.BulletinError) as e:
        B.add(engine, "t", "u", b"%PDF-1.7 not audio")
    assert e.value.status == 415
    monkeypatch.setenv("BULLETIN_MAX_MB", "1")
    with pytest.raises(B.BulletinError) as e:
        B.add(engine, "t", "u", b"ID3" + b"\0" * (1024 * 1024 + 1))
    assert e.value.status == 413


def test_audio_is_served_in_ranges_and_drafts_stay_private(engine):
    b = B.add(engine, "t", "u", MP3)
    with pytest.raises(B.BulletinError):
        B.audio(engine, "t", b["id"], None, published_only=True)        # taslak herkese çalmaz
    full = B.audio(engine, "t", b["id"], None, published_only=False)
    assert full.status_code == 200 and full.body == MP3 and full.headers["accept-ranges"] == "bytes"
    part = B.audio(engine, "t", b["id"], "bytes=10-19", published_only=False)
    assert part.status_code == 206 and part.body == MP3[10:20]
    assert part.headers["content-range"] == f"bytes 10-19/{len(MP3)}"
    assert B.audio(engine, "t", b["id"], f"bytes={len(MP3) + 5}-", published_only=False).status_code == 416


def test_remove_deletes_the_file(engine):
    b = B.add(engine, "t", "u", MP3)
    path = B.root() / f"{b['id']}.mp3"
    assert path.is_file()
    B.remove(engine, "t", b["id"])
    assert not path.exists() and B.listing(engine, "t", published_only=False) == []


def test_unwritable_folder_is_a_plain_error(engine, tmp_path, monkeypatch):
    blocker = tmp_path / "dosya"
    blocker.write_text("klasör değil")
    monkeypatch.setenv("KAMPUS_BULLETIN_DIR", str(blocker / "ses"))
    with pytest.raises(B.BulletinError) as e:
        B.add(engine, "t", "u", MP3)
    assert e.value.status == 500 and "yazılamıyor" in str(e.value)
    assert B.listing(engine, "t", published_only=False) == []
