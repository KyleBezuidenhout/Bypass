"""Tests for the project-file writer and the per-person import builder.

Uses a synthetic .prj shaped exactly like a real GSA project (indexed [se] and
[keywords] blocks) so the tests are hermetic and do not depend on the machine.
"""
from __future__ import annotations

import pytest

from gsa_wrap import config_io, project_io
from gsa_wrap.config_io import ConfigError

SAMPLE_PRJ = """\
[misc]
proxies for se=0
proxies for parse=0
proxies for sending=0
se proxy type=3
parse proxy type=3
sending proxy type=3
only root domains=0
collect social=1
max pages=100

[keywords]
0=1:robotics outbound

[se]
0=0:1Two.org
1=1:4get
2=1:Yioop

[ident]
Empty=255\\x0111\\x01*empty*
email=1\\x011\\x01*mail*

[scheduler]
scraper on=0
import on=0
import file=
import min=30
import del on=0
"""


@pytest.fixture()
def prj(tmp_path):
    p = tmp_path / "sample project.prj"
    p.write_bytes(SAMPLE_PRJ.replace("\n", "\r\n").encode("latin-1"))
    return p


# ---------------------------------------------------------------- read
def test_read_summary(prj):
    s = project_io.read_summary(prj)
    assert s["name"] == "sample project"
    assert s["proxies"] == {
        "proxies for se": False, "proxies for parse": False, "proxies for sending": False}
    assert s["proxy_types"]["se proxy type"] == 3
    assert s["proxy_type_names"]["se proxy type"] == "socks5"
    assert s["keywords"] == [{"name": "robotics outbound", "enabled": True}]
    assert s["search_engines_total"] == 3
    assert s["search_engines_enabled"] == 2


# ---------------------------------------------------------------- write
def test_enable_proxies_is_verified_and_idempotent(prj):
    upd = {"misc::proxies for parse": True, "misc::proxies for sending": True}
    res = project_io.apply_settings(upd, prj)
    assert res["verified"] is True and not res["bounced"]
    assert project_io.read_summary(prj)["proxies"]["proxies for parse"] is True

    again = project_io.apply_settings(upd, prj)
    assert again["changed"] == []


def test_proxy_type_validates(prj):
    project_io.apply_settings({"misc::parse proxy type": 1}, prj)
    assert project_io.read_summary(prj)["proxy_types"]["parse proxy type"] == 1
    with pytest.raises(ConfigError):
        project_io.apply_settings({"misc::parse proxy type": 9}, prj)


def test_write_preserves_unrelated_bulk_and_crlf(prj):
    before = prj.read_bytes()
    project_io.apply_settings({"misc::proxies for se": True}, prj)
    after = prj.read_bytes()

    assert b"[se]" in after and b"[ident]" in after
    assert after.count(b"=1:4get") == 1
    # every line keeps CRLF
    assert after.count(b"\n") == after.count(b"\r\n")
    # only one line differs
    bl, al = before.split(b"\r\n"), after.split(b"\r\n")
    diff = [i for i, (x, y) in enumerate(zip(bl, al)) if x != y]
    assert len(diff) == 1


def test_backup_written(prj):
    res = project_io.apply_settings({"misc::collect social": False}, prj)
    assert res["backup_path"] and prj.with_suffix(".prj.bak").exists()


def test_atomic_no_tmp_left(prj):
    project_io.apply_settings({"misc::collect social": False}, prj)
    assert not prj.with_suffix(".prj.tmp").exists()


def test_keywords_rewrite(prj):
    from gsa_wrap import api
    api._apply_project_keywords(prj, ["robotics outbound", "cold email"])
    kws = [k["name"] for k in project_io.read_summary(prj)["keywords"]]
    assert kws == ["robotics outbound", "cold email"]
    # dense renumbering starting at 0
    txt = prj.read_bytes().decode("latin-1")
    assert "0=1:robotics outbound" in txt and "1=1:cold email" in txt

    # idempotent
    r = api._apply_project_keywords(prj, ["robotics outbound", "cold email"])
    assert r["changed"] == []


def test_keywords_remove(prj):
    from gsa_wrap import api
    api._apply_project_keywords(prj, ["robotics outbound", "cold email"])
    api._apply_project_keywords(prj, ["cold email"])
    assert [k["name"] for k in project_io.read_summary(prj)["keywords"]] == ["cold email"]


# ---------------------------------------------------------------- import csv
def test_import_csv_header_mapping():
    from gsa_wrap import import_csv as ic
    plan = ic.parse_delimited("URL,Message\nhttps://a.com,hi a\nhttps://b.com,hi b")
    assert plan.url_header == "URL" and plan.message_header == "Message"
    assert plan.message_macro == "%csv-Message%"
    out = ic.to_gsa_csv(plan)
    assert out.splitlines()[0] == "URL,Message"
    assert "hi a" in out


def test_import_csv_quotes_and_commas():
    from gsa_wrap import import_csv as ic
    plan = ic.parse_delimited('url,message\nhttps://x.com,"Hi, ""friend""!"')
    assert plan.rows[0]["message"] == 'Hi, "friend"!'


def test_import_tsv_and_pipe():
    from gsa_wrap import import_csv as ic
    tsv = ic.parse_delimited("https://c.com\tcustom c")
    assert tsv.message_header == "Message" and tsv.row_count == 1
    pipe = ic.parse_delimited("https://e.com | hello e")
    assert pipe.row_count == 1 and pipe.message_header == "Message"


def test_import_requires_url():
    from gsa_wrap import import_csv as ic
    with pytest.raises(ConfigError):
        ic.parse_delimited("\n\n")


def test_import_no_message_column_is_flagged():
    from gsa_wrap import import_csv as ic
    plan = ic.parse_delimited("URL\nhttps://a.com\nhttps://b.com")
    assert plan.message_header is None
    assert any("message column" in n for n in plan.notes)


def test_write_csv_roundtrip(tmp_path):
    from gsa_wrap import import_csv as ic
    plan = ic.parse_delimited("URL,Message\nhttps://a.com,hello")
    p = ic.write_csv(plan, "test batch", directory=tmp_path)
    assert p.exists()
    back = ic.parse_file(p.read_bytes(), filename=p.name)
    assert back.row_count == 1
    assert back.rows[0]["Message"] == "hello"


def test_recommended_updates_points_at_csv(tmp_path):
    from gsa_wrap import import_csv as ic
    plan = ic.parse_delimited("URL,Message\nhttps://a.com,hello")
    upd = ic.recommended_project_updates(plan, tmp_path / "x.csv")
    assert upd["scheduler::import on"] is True
    assert upd["scheduler::import file"].endswith("x.csv")


def test_recommended_updates_requires_message():
    from gsa_wrap import import_csv as ic
    plan = ic.parse_delimited("URL\nhttps://a.com")
    with pytest.raises(ConfigError):
        ic.recommended_project_updates(plan, "x.csv")


# ---------------------------------------------------------------- config append
def test_config_append_missing_key(tmp_path):
    """A key absent from config.ini is created inside its section, not appended at EOF."""
    p = tmp_path / "config.ini"
    p.write_bytes(b"[misc]\r\nmax threads=10\r\n\r\n[notify]\r\nssl=0\r\n")
    res = config_io.apply({"notify::email to": "a@b.com"}, p)
    assert res["verified"] is True
    txt = p.read_bytes().decode("latin-1")
    misc_i = txt.index("[misc]")
    notify_i = txt.index("[notify]")
    email_i = txt.index("email to=")
    assert notify_i < email_i, "should be added inside [notify]"
    assert txt.count("[notify]") == 1
