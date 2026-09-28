#!/usr/bin/env python3
"""M57 kabul testinin bıraktığı kayıtları siler (AGENTS.md «Test kullanıcısı ve test verisi bırakılmaz»).

    set -a; . /etc/nanobase/semantic-bridge.env; set +a
    cd <kaynak>/backend && python3 ../scripts/acceptance/M57/temizlik.py --ids /tmp/claude-<oturum>/m57-ids.json

Silinenler: kabul.py --yazma'nın açtığı geçici rol ve kişi bağı; yapay eğitim kartları ve oturumlar (adı «KABUL TESTİ M57»
ile başlayan artıklar dahil) ile bunların katılım, sertifika, anket jetonu, anket yanıtı ve iş kayıtları; test rehberi ve
oyları; test için açılan çalışan kaydı (yalnız testin kendisi açtıysa); test boyunca test hesabının yazdığı İK erişim kaydı
satırları ve ilgili değişiklik kaydı (`semantic_audit`) satırları. Ziyaret sayacı testten önceki değerine döndürülür.
Logo'ya ve CRM'e dokunulmaz (zaten yazılmaz). Silinen satır sayıları yazdırılır; günlüğe geçirilir.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "backend"))

import sqlalchemy as sa  # noqa: E402

from semantic_bridge import access as A  # noqa: E402
from semantic_bridge import admin as admin_mod  # noqa: E402
from semantic_bridge import hr_core as H  # noqa: E402
from semantic_bridge import hr_learning as L  # noqa: E402
from semantic_layer.store.catalog_store import open_store  # noqa: E402

PREFIX = "KABUL TESTİ M57"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", default="m57-ids.json")
    args = ap.parse_args()
    engine = open_store(os.environ["SEMANTIC_STORE_DSN"], create=False).engine
    admin_mod.ensure(engine)
    L.ensure(engine)
    tenant = os.environ.get("SEMANTIC_TENANT_ID", "default")
    ids = json.loads(Path(args.ids).read_text()) if Path(args.ids).exists() else {}
    user = ids.get("user") or os.environ.get("KABUL_USER", "timasai")
    out: dict[str, int] = {}
    with engine.begin() as c:
        courses = set(ids.get("courses") or []) | set(c.execute(sa.select(L.COURSES.c.id).where(
            L.COURSES.c.tenant_id == tenant, L.COURSES.c.title.like(PREFIX + "%"))).scalars())
        cl = sorted(courses) or [""]
        sessions = set(ids.get("sessions") or []) | set(c.execute(sa.select(L.SESSIONS.c.id).where(L.SESSIONS.c.course_id.in_(cl))).scalars())
        sl = sorted(sessions) or [""]
        enr = [r for r in c.execute(sa.select(L.ENROLLMENTS.c.id).where(L.ENROLLMENTS.c.session_id.in_(sl))).scalars()]
        certs = [r for r in c.execute(sa.select(L.CERTIFICATES.c.id).where(
            sa.or_(L.CERTIFICATES.c.session_id.in_(sl), L.CERTIFICATES.c.course_id.in_(cl)))).scalars()]
        out["anket_yaniti"] = c.execute(L.FEEDBACK.delete().where(L.FEEDBACK.c.session_id.in_(sl))).rowcount or 0
        out["anket_jetonu"] = c.execute(L.FEEDBACK_TOKENS.delete().where(L.FEEDBACK_TOKENS.c.session_id.in_(sl))).rowcount or 0
        out["sertifika"] = c.execute(L.CERTIFICATES.delete().where(L.CERTIFICATES.c.id.in_(certs or [""]))).rowcount or 0
        out["katilim"] = c.execute(L.ENROLLMENTS.delete().where(L.ENROLLMENTS.c.session_id.in_(sl))).rowcount or 0
        out["is"] = c.execute(H.JOBS.delete().where(H.JOBS.c.subject_id.in_(sl))).rowcount or 0
        out["oturum"] = c.execute(L.SESSIONS.delete().where(L.SESSIONS.c.id.in_(sl))).rowcount or 0
        out["egitim"] = c.execute(L.COURSES.delete().where(L.COURSES.c.id.in_(cl))).rowcount or 0
        guides = set(ids.get("guides") or []) | set(c.execute(sa.select(L.GUIDES.c.id).where(
            L.GUIDES.c.tenant_id == tenant, L.GUIDES.c.title.like(PREFIX + "%"))).scalars())
        gl = sorted(guides) or [""]
        out["rehber_oyu"] = c.execute(L.GUIDE_VOTES.delete().where(L.GUIDE_VOTES.c.guide_id.in_(gl))).rowcount or 0
        out["rehber"] = c.execute(L.GUIDES.delete().where(L.GUIDES.c.id.in_(gl))).rowcount or 0
        emp = ids.get("employee_created")
        if emp:
            out["calisan"] = c.execute(H.EMPLOYEES.delete().where(H.EMPLOYEES.c.id == emp, H.EMPLOYEES.c.tenant_id == tenant)).rowcount or 0
        vb = ids.get("visit_before")
        if vb:
            key = sa.and_(L.PAGE_VISITS.c.tenant_id == tenant, L.PAGE_VISITS.c.day == date.fromisoformat(vb["day"]),
                          L.PAGE_VISITS.c.route_prefix == "ik-egitim", L.PAGE_VISITS.c.username == user)
            if vb.get("count") in (None, 0):
                out["ziyaret"] = c.execute(L.PAGE_VISITS.delete().where(key)).rowcount or 0
            else:
                out["ziyaret"] = c.execute(L.PAGE_VISITS.update().where(key).values(count=int(vb["count"]))).rowcount or 0
        if ids.get("start"):
            since = datetime.fromisoformat(ids["start"])
            out["erisim_kaydi"] = c.execute(H.ACCESS_LOG.delete().where(H.ACCESS_LOG.c.tenant_id == tenant, H.ACCESS_LOG.c.username == user,
                                                                        H.ACCESS_LOG.c.at >= since)).rowcount or 0
        objs = sorted((set(cl) | set(sl) | set(enr) | set(certs) | set(gl) | ({emp} if emp else set())) - {""})
        out["degisiklik_kaydi"] = c.execute(admin_mod.AUDIT.delete().where(
            admin_mod.AUDIT.c.kind.in_(("hr_course", "hr_session", "hr_enrollment", "hr_certificate", "hr_guide", "hr_employee")),
            admin_mod.AUDIT.c.object_id.in_(objs or [""]))).rowcount or 0
    roles = list(ids.get("roles") or [])
    for rl in A.list_roles(engine, tenant):
        if rl["name"].startswith(PREFIX) and rl["id"] not in roles:
            roles.append(rl["id"])
    out["rol"] = 0
    for rid in roles:
        if A.delete_role(engine, tenant, rid):
            out["rol"] += 1
    with engine.begin() as c:
        out["rol_kaydi"] = c.execute(admin_mod.AUDIT.delete().where(admin_mod.AUDIT.c.kind == "access",
                                                                    admin_mod.AUDIT.c.title.like(PREFIX + "%"))).rowcount or 0
    print(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
