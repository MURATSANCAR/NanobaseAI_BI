"""Unit tests for generic intent slot detection + matcher gates."""

from __future__ import annotations

from nanobase_api.scenario_engine.application.intent_slots import (
    detect_family,
    detect_period,
    entity_score,
    period_compatible,
)
from nanobase_api.scenario_engine.application.matcher import ScenarioMatcher
from nanobase_api.scenario_engine.domain.logical_plan import LogicalPlan
from nanobase_api.scenario_engine.domain.period import PeriodKind
from nanobase_api.scenario_engine.domain.risk import RiskTier
from nanobase_api.scenario_engine.domain.scenario import ScenarioInstance, ScenarioParaphrase
from nanobase_api.scenario_engine.domain.status import ScenarioStatus
from nanobase_api.scenario_engine.infrastructure.store import ScenarioStore


def test_period_ytd_beats_bare_bugune():
    q = "yıl başından bugüne kadar ne kadar alış faturamız var"
    assert detect_period(q) == PeriodKind.YEAR_TO_DATE
    assert detect_period("bugünkü faturaları getir") == PeriodKind.TODAY
    assert detect_period("ay başından bugüne olan kayıtlar") == PeriodKind.MONTH_TO_DATE


def test_family_ne_kadar_var_is_count_not_sum():
    assert detect_family("ne kadar alış faturamız var") == "COUNT_ENTITY"
    assert detect_family("yıl başından bugüne kadar ne kadar alış faturamız var") == "COUNT_ENTITY"
    assert detect_family("kaç müşteri var") == "COUNT_ENTITY"
    assert detect_family("bu ayki fatura toplamı nedir") == "SUM_MEASURE"
    assert detect_family("ne kadar tutar var") == "SUM_MEASURE"
    assert detect_family("alış faturalarını listele") == "LIST_ENTITY"


def test_entity_prefers_specific_table_tokens():
    q = "ne kadar alış faturamız var"
    alis = entity_score(q, "alis_faturalari", "public.alis_faturalari")
    inv = entity_score(q, "invoice", "public.faturalar")
    assert alis > inv
    assert alis >= 0.35


def test_entity_generic_fatura_not_forced_to_alis():
    q = "bugünkü faturaları getir"
    alis = entity_score(q, "alis_faturalari", "public.alis_faturalari")
    inv = entity_score(q, "invoice", "public.faturalar")
    assert inv > alis


def test_period_hard_gate():
    assert period_compatible(PeriodKind.YEAR_TO_DATE, "YEAR_TO_DATE")
    assert not period_compatible(PeriodKind.YEAR_TO_DATE, "TODAY")
    assert period_compatible(None, "TODAY")


def test_matcher_natural_ytd_count_not_invoice_today():
    store = ScenarioStore()
    inv = ScenarioInstance(
        id="scn-inv-today",
        tenant_id="default",
        datasource_id="erp",
        scenario_code="invoice.list.today.lim25",
        family="LIST_ENTITY",
        logical_plan=LogicalPlan(
            family="LIST_ENTITY",
            entity="invoice",
            period="TODAY",
            physical_table="public.faturalar",
            limit=25,
        ),
        schema_version="1",
        semantic_version="1",
        risk_tier=RiskTier.A,
        status=ScenarioStatus.PUBLISHED,
        canonical_question="Bugüne ait faturaları getir.",
    )
    alis = ScenarioInstance(
        id="scn-alis-ytd",
        tenant_id="default",
        datasource_id="erp",
        scenario_code="alis_faturalari.count.year_to_date",
        family="COUNT_ENTITY",
        logical_plan=LogicalPlan(
            family="COUNT_ENTITY",
            entity="alis_faturalari",
            period="YEAR_TO_DATE",
            physical_table="public.alis_faturalari",
            limit=1,
        ),
        schema_version="1",
        semantic_version="1",
        risk_tier=RiskTier.A,
        status=ScenarioStatus.PUBLISHED,
        canonical_question="Yıl başından bugüne olan kaç alis faturalari var?",
    )
    store.save_instance(inv)
    store.save_instance(alis)
    store.save_paraphrase(
        ScenarioParaphrase(
            id="par-1",
            scenario_id=alis.id,
            language="tr",
            tenant_id="default",
            datasource_id="erp",
            text="Yıl başından bugüne olan alis faturalari kayıtları sayısı nedir?",
            status=ScenarioStatus.PUBLISHED,
        )
    )

    m = ScenarioMatcher(store=store).match(
        "yıl başından bugüne kadar ne kadar alış faturamız var",
        tenant_id="default",
        datasource_id="erp",
    )
    assert m.matched
    assert m.scenario_code == "alis_faturalari.count.year_to_date"
    assert m.detail.get("detectedPeriod") == "YEAR_TO_DATE"
    assert m.detail.get("detectedFamily") == "COUNT_ENTITY"


def test_matcher_generic_other_table_mtd_sum():
    store = ScenarioStore()
    inst = ScenarioInstance(
        id="scn-kom-mtd",
        tenant_id="default",
        datasource_id="sigorta",
        scenario_code="komisyon_odemeleri.sum.tutar.month_to_date",
        family="SUM_MEASURE",
        logical_plan=LogicalPlan(
            family="SUM_MEASURE",
            entity="komisyon_odemeleri",
            period="MONTH_TO_DATE",
            physical_table="public.komisyon_odemeleri",
            aggregation="SUM",
            metric="tutar",
            limit=1,
        ),
        schema_version="1",
        semantic_version="1",
        risk_tier=RiskTier.A,
        status=ScenarioStatus.PUBLISHED,
        canonical_question="Ay başından bugüne olan komisyon odemeleri toplamı nedir?",
    )
    distractor = ScenarioInstance(
        id="scn-kom-today-list",
        tenant_id="default",
        datasource_id="sigorta",
        scenario_code="komisyon_odemeleri.list.today.lim25",
        family="LIST_ENTITY",
        logical_plan=LogicalPlan(
            family="LIST_ENTITY",
            entity="komisyon_odemeleri",
            period="TODAY",
            physical_table="public.komisyon_odemeleri",
            limit=25,
        ),
        schema_version="1",
        semantic_version="1",
        risk_tier=RiskTier.A,
        status=ScenarioStatus.PUBLISHED,
        canonical_question="Bugüne ait komisyon odemeleri getir.",
    )
    store.save_instance(inst)
    store.save_instance(distractor)

    m = ScenarioMatcher(store=store).match(
        "ay başından bugüne kadar komisyon ödeme toplamı nedir",
        tenant_id="default",
        datasource_id="sigorta",
    )
    assert m.matched
    assert m.scenario_code == "komisyon_odemeleri.sum.tutar.month_to_date"


def test_matcher_ignores_poisoned_exact_paraphrase():
    store = ScenarioStore()
    inv = ScenarioInstance(
        id="scn-inv-today",
        tenant_id="default",
        datasource_id="erp",
        scenario_code="invoice.list.today.lim25",
        family="LIST_ENTITY",
        logical_plan=LogicalPlan(
            family="LIST_ENTITY",
            entity="invoice",
            period="TODAY",
            physical_table="public.faturalar",
            limit=25,
        ),
        schema_version="1",
        semantic_version="1",
        risk_tier=RiskTier.A,
        status=ScenarioStatus.PUBLISHED,
        canonical_question="Bugüne ait faturaları getir.",
    )
    alis = ScenarioInstance(
        id="scn-alis-ytd",
        tenant_id="default",
        datasource_id="erp",
        scenario_code="alis_faturalari.count.year_to_date",
        family="COUNT_ENTITY",
        logical_plan=LogicalPlan(
            family="COUNT_ENTITY",
            entity="alis_faturalari",
            period="YEAR_TO_DATE",
            physical_table="public.alis_faturalari",
            limit=1,
        ),
        schema_version="1",
        semantic_version="1",
        risk_tier=RiskTier.A,
        status=ScenarioStatus.PUBLISHED,
        canonical_question="Yıl başından bugüne olan kaç alis faturalari var?",
    )
    store.save_instance(inv)
    store.save_instance(alis)
    poison_q = "yıl başından bugüne kadar ne kadar alış faturamız var"
    store.save_paraphrase(
        ScenarioParaphrase(
            id="par-poison",
            scenario_id=inv.id,
            language="tr",
            tenant_id="default",
            datasource_id="erp",
            text=poison_q,
            status=ScenarioStatus.PUBLISHED,
        )
    )
    m = ScenarioMatcher(store=store).match(
        poison_q, tenant_id="default", datasource_id="erp"
    )
    assert m.matched
    assert m.scenario_code == "alis_faturalari.count.year_to_date"
