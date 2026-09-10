import json
from unittest.mock import Mock
import pytest
import sqlalchemy as sa
from semantic_layer.nightly import Release,execute_release,capture,digest,MUTABLE,Conflict,save
from semantic_layer.store import schema as S
from semantic_layer.store.catalog_store import open_store
from semantic_layer.tests.test_runtime import catalog  # noqa: F401
from semantic_layer.tests.conftest import TENANT,DS


def snap(store):
    with store.engine.connect() as c:return capture(c,TENANT,DS)


def change(dsn):
    stage=open_store(dsn,create=False)
    with stage.engine.begin() as c:
        c.execute(S.sl_mapping.update().where(S.sl_mapping.c.formula.is_not(None)).values(formula="SUM(INVOICE.TOTALVAT)"))
        c.execute(S.sl_concept.update().values(status="REJECTED"))
        c.execute(S.sl_schema_profile.update().values(description="candidate profile"))
        c.execute(S.sl_evidence.delete())
    stage.engine.dispose()


def setup(catalog,tmp_path):
    return Release(catalog,TENANT,DS,tmp_path/"journal.json"),"sqlite:///"+str(tmp_path/"stage.sqlite")


def test_failed_candidate_never_changes_live_catalog(catalog,tmp_path):
    before=snap(catalog);r,dsn=setup(catalog,tmp_path);reload=Mock()
    with pytest.raises(RuntimeError,match="quality"):
        execute_release(r,dsn,change,Mock(side_effect=RuntimeError("quality")),reload)
    assert digest(snap(catalog))==digest(before)
    reload.assert_not_called()


def test_failed_published_quality_restores_formulas_profiles_status_evidence(catalog,tmp_path):
    before=snap(catalog);r,dsn=setup(catalog,tmp_path);reload=Mock()
    gate=Mock(side_effect=[None,RuntimeError("post quality")])
    with pytest.raises(RuntimeError,match="post quality"):
        execute_release(r,dsn,change,gate,reload)
    assert digest(snap(catalog),MUTABLE)==digest(before,MUTABLE)
    assert reload.call_count==2
    assert json.loads(r.journal.read_text())["state"]=="rolled_back"


def test_reload_failure_rolls_back_and_reloads_old_catalog(catalog,tmp_path):
    before=snap(catalog);r,dsn=setup(catalog,tmp_path)
    reload=Mock(side_effect=[RuntimeError("reload"),None])
    with pytest.raises(RuntimeError,match="reload"):
        execute_release(r,dsn,change,Mock(),reload)
    assert digest(snap(catalog),MUTABLE)==digest(before,MUTABLE)
    assert reload.call_count==2


def test_failed_recovery_reload_is_not_success(catalog,tmp_path):
    r,dsn=setup(catalog,tmp_path)
    with pytest.raises(RuntimeError,match="offline"):
        execute_release(r,dsn,change,Mock(),Mock(side_effect=RuntimeError("offline")))
    assert json.loads(r.journal.read_text())["state"]=="rolled_back"


def test_new_live_query_logs_survive_rollback(catalog,tmp_path):
    r,dsn=setup(catalog,tmp_path)
    def gate(dsn):
        if dsn is None:
            catalog.log_query(TENANT,DS,"arrived during publication",executed=False,sql=None,compiler="test",catalog_version=1,resolved={})
            raise RuntimeError("quality")
    with pytest.raises(RuntimeError):execute_release(r,dsn,change,gate,Mock())
    with catalog.engine.connect() as c:
        assert c.execute(sa.select(sa.func.count()).select_from(S.sl_query_log).where(S.sl_query_log.c.question=="arrived during publication")).scalar()==1


def test_concurrent_catalog_edit_aborts_publication(catalog,tmp_path):
    r,dsn=setup(catalog,tmp_path)
    def build(dsn):
        change(dsn)
        with catalog.engine.begin() as c:c.execute(S.sl_schema_profile.update().values(description="user edit"))
    with pytest.raises(Conflict):execute_release(r,dsn,build,Mock(),Mock())
    assert all(p["description"]=="user edit" for p in snap(catalog)[S.sl_schema_profile.name])
    assert json.loads(r.journal.read_text())["state"]=="aborted"


def test_interrupted_publication_is_recovered_from_journal(catalog,tmp_path):
    before=snap(catalog);r,dsn=setup(catalog,tmp_path);stage=r.prepare(dsn);change(dsn);r.publish(stage)
    data=json.loads(r.journal.read_text());data["state"]="publishing";save(r.journal,data)
    recovered=Release(catalog,TENANT,DS,r.journal)
    assert recovered.rollback()
    assert digest(snap(catalog),MUTABLE)==digest(before,MUTABLE)
    # Simulate death after rollback committed but before journal state was flushed.
    save(r.journal,data)
    assert recovered.rollback()
    assert digest(snap(catalog),MUTABLE)==digest(before,MUTABLE)


def test_concurrent_edit_after_publication_is_not_overwritten(catalog,tmp_path):
    r,dsn=setup(catalog,tmp_path);stage=r.prepare(dsn);change(dsn);r.publish(stage)
    with catalog.engine.begin() as c:c.execute(S.sl_schema_profile.update().values(description="late user edit"))
    with pytest.raises(Conflict):r.rollback()
    assert all(p["description"]=="late user edit" for p in snap(catalog)[S.sl_schema_profile.name])


def test_success_publishes_once(catalog,tmp_path):
    r,dsn=setup(catalog,tmp_path);reload=Mock();gate=Mock()
    execute_release(r,dsn,change,gate,reload)
    assert json.loads(r.journal.read_text())["state"]=="complete"
    assert reload.call_count==1 and gate.call_count==2
    assert all(p["description"]=="candidate profile" for p in snap(catalog)[S.sl_schema_profile.name])


def test_certified_vocabulary_cannot_disappear(catalog,tmp_path):
    from semantic_layer.nightly import validate_candidate
    before=snap(catalog)
    validate_candidate(before,before)
    r,dsn=setup(catalog,tmp_path)
    stage=r.prepare(dsn);change(dsn)
    with pytest.raises(RuntimeError,match="certified concepts"):
        validate_candidate(before,snap(stage))


def test_publication_transaction_is_atomic(catalog,tmp_path,monkeypatch):
    import semantic_layer.nightly as nightly
    before=snap(catalog);r,dsn=setup(catalog,tmp_path)
    monkeypatch.setattr(nightly,"version",Mock(side_effect=RuntimeError("version failure")))
    with pytest.raises(RuntimeError,match="version failure"):
        execute_release(r,dsn,change,Mock(),Mock())
    assert digest(snap(catalog))==digest(before)
