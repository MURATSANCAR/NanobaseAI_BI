import { useCallback, useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Calculator, Download, FileSpreadsheet, Loader2, RefreshCw } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import { Note, Pill, btnGhost, btnPrimary, errText, field, label as labelCls } from '../admin/ui';
import { Kpi, KpiRow } from '../editorial/kit';
import { budgetApi, fmtDay, fmtPct, fmtShort, STATUS_TONE, type Plan } from './api';
import { AskSheet, BudgetFrame, Tabs } from './parts';
import TrackingTab from './TrackingTab';
import TargetsTab from './TargetsTab';
import ProgramTab from './ProgramTab';
import DeptTab from './DeptTab';
import ScenariosTab from './ScenariosTab';
import GenerateSheet from './GenerateSheet';
import SqlInfo from '../components/SqlInfo';
import { xlsxUrl } from '../components/excel';

/** M46 Bütçe planlama ve kontrolü. Yıl, plan ve sekme adres çubuğunda (?yil=, ?plan=, ?sekme=); bağlantı paylaşılabilir. */

const TABS = [
  { key: 'izleme', label: 'İzleme' },
  { key: 'hedefler', label: 'Kitap hedefleri' },
  { key: 'program', label: 'Yeni kitap programı' },
  { key: 'departman', label: 'Departman bütçesi' },
  { key: 'senaryo', label: 'Senaryolar ve onay' },
] as const;
type Tab = (typeof TABS)[number]['key'];

/** Yılın varsayılan planı: yürürlükteki, yoksa onay bekleyen, yoksa en yeni temel taslak, yoksa en yeni. */
function pickDefault(plans: Plan[]): Plan | undefined {
  return (
    plans.find((p) => p.status === 'onayli') ??
    plans.find((p) => p.status === 'onayda') ??
    plans.find((p) => p.status === 'taslak' && p.scenario === 'temel') ??
    plans.find((p) => p.status !== 'arsiv') ??
    plans[0]
  );
}

type Ask = null | 'submit' | 'withdraw' | 'approve' | 'reject' | 'revise' | 'delete';

export default function BudgetScreen() {
  const qc = useQueryClient();
  const [params, setParams] = useSearchParams();
  const [gen, setGen] = useState(false);
  const [ask, setAsk] = useState<Ask>(null);

  const meta = useQuery({ queryKey: ['budget', 'meta'], queryFn: budgetApi.meta, enabled: ENGINE_ENABLED, staleTime: 60_000 });
  const me = meta.data?.me;
  const year = Number(params.get('yil')) || meta.data?.defaultYear || new Date().getFullYear();
  const plans = useQuery({ queryKey: ['budget', 'plans', year], queryFn: () => budgetApi.plans(year), enabled: ENGINE_ENABLED && !!meta.data });
  const list = useMemo(() => (plans.data?.items ?? []).filter((p) => p.year === year), [plans.data, year]);
  const plan = list.find((p) => p.id === params.get('plan')) ?? pickDefault(list);
  const dataEnd = meta.data?.data.dataEnd ?? null;
  const trackable = !!plan && !!dataEnd && Number(dataEnd.slice(0, 4)) >= plan.year;
  const tab: Tab = (TABS.find((t) => t.key === params.get('sekme'))?.key ?? (plan?.status === 'onayli' && trackable ? 'izleme' : 'hedefler')) as Tab;

  const update = useCallback(
    (next: Record<string, string | null>) => {
      const p = new URLSearchParams(params);
      for (const [k, v] of Object.entries(next)) {
        if (v) p.set(k, v);
        else p.delete(k);
      }
      setParams(p, { replace: true });
    },
    [params, setParams],
  );

  // Gerçekleşme okunurken durum yoklanır; bitince bütün bütçe görünümleri tazelenir.
  const running = meta.data?.data.running;
  const status = useQuery({
    queryKey: ['budget', 'status'],
    queryFn: budgetApi.status,
    enabled: ENGINE_ENABLED && !!running,
    refetchInterval: (q) => (q.state.data && !q.state.data.running ? false : 4000),
  });
  useEffect(() => {
    if (running && status.data && !status.data.running) {
      qc.invalidateQueries({ queryKey: ['budget'] });
      if (status.data.error) toast.error(status.data.error);
      else toast.success('Logo gerçekleşmesi güncellendi.');
    }
  }, [running, status.data, qc]);

  const refresh = useMutation({
    mutationFn: budgetApi.refresh,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['budget', 'meta'] }),
    onError: (e) => toast.error(errText(e, 'Yenileme başlatılamadı.') ?? ''),
  });

  const act = useMutation({
    mutationFn: async ({ kind, text }: { kind: Exclude<Ask, null>; text: string }) => {
      if (!plan) throw new Error('Plan seçili değil.');
      switch (kind) {
        case 'submit': return budgetApi.submit(plan.id);
        case 'withdraw': return budgetApi.withdraw(plan.id);
        case 'approve': return budgetApi.approve(plan.id, text || undefined);
        case 'reject': return budgetApi.reject(plan.id, text);
        case 'revise': return budgetApi.revise(plan.id, text);
        case 'delete': await budgetApi.deletePlan(plan.id); return null;
      }
    },
    onSuccess: (out, { kind }) => {
      setAsk(null);
      qc.invalidateQueries({ queryKey: ['budget'] });
      const msg = { submit: 'Plan onaya gönderildi.', withdraw: 'Plan taslağa geri alındı.', approve: 'Plan yürürlüğe girdi.', reject: 'Plan gerekçesiyle geri gönderildi.', revise: 'Revizyon taslağı açıldı.', delete: 'Taslak silindi.' }[kind];
      toast.success(msg);
      if (kind === 'revise' && out) update({ plan: out.id, sekme: 'hedefler' });
      if (kind === 'delete') update({ plan: null });
    },
    onError: (e) => toast.error(errText(e, 'İşlem yapılamadı.') ?? ''),
  });

  const years = useMemo(() => {
    const s = new Set<number>([...(meta.data?.years ?? []), year]);
    return [...s].sort((a, b) => b - a);
  }, [meta.data, year]);

  const data = meta.data?.data;
  const t = plan?.totals;
  const mine = (plan?.submittedBy ?? '').toLowerCase() === (me?.username ?? '').toLowerCase();
  const editable = plan?.status === 'taslak' && !!me?.canEdit;

  const aside = (
    <div className="flex flex-col gap-2">
      <div className="grid grid-cols-[110px_1fr] gap-2">
        <label className="flex flex-col gap-1">
          <span className={labelCls}>Yıl</span>
          <select className={field} value={year} onChange={(e) => update({ yil: e.target.value, plan: null, sekme: null })}>
            {years.map((y) => <option key={y} value={y}>{y}</option>)}
          </select>
        </label>
        <label className="flex min-w-0 flex-col gap-1">
          <span className={labelCls}>Plan</span>
          <select className={field} value={plan?.id ?? ''} onChange={(e) => update({ plan: e.target.value || null })} disabled={!list.length}>
            {!list.length && <option value="">Bu yıl için plan yok</option>}
            {list.map((p) => (
              <option key={p.id} value={p.id}>{p.title} — {p.statusLabel}</option>
            ))}
          </select>
        </label>
      </div>
      <div className="flex flex-wrap gap-2">
        {me?.canEdit && (
          <button type="button" className={`${btnPrimary} flex-1`} onClick={() => setGen(true)} disabled={!data?.dataEnd}>
            <Calculator aria-hidden className="h-4 w-4" />
            Veriden öneri
          </button>
        )}
        {plan && (
          <>
            <a className={`${btnGhost} flex-1`} href={budgetApi.exportUrl(plan.id)} download>
              <Download aria-hidden className="h-4 w-4" />
              Hedefleri indir (CSV)
            </a>
            <a className={`${btnGhost} flex-1`} href={xlsxUrl(budgetApi.exportUrl(plan.id))} download>
              <FileSpreadsheet aria-hidden className="h-4 w-4" />
              Hedefleri indir (Excel)
            </a>
          </>
        )}
      </div>
    </div>
  );

  return (
    <BudgetFrame
      source={data?.dataEnd ? `Logo · ${fmtDay(data.dataEnd)}'e kadar` : 'Logo + CRM'}
      presence={plan ? `${plan.title} · ${plan.statusLabel}` : `${year}`}
      aside={aside}
    >
      {!ENGINE_ENABLED && <Note tone="warn">ZEKİ AI bağlantısı bu derlemede tanımlı değil.</Note>}
      {meta.error && <Note tone="err">{errText(meta.error, 'Bütçe bilgisi açılamadı.')}</Note>}

      {data && (
        <div className="flex flex-wrap items-center justify-between gap-2 rounded-2xl bg-white/70 px-3 py-2 text-[12px] font-semibold text-canvas-muted">
          <span>
            {data.dataEnd
              ? <>Logo satış ve muhasebe verisi <strong className="text-canvas-ink">{fmtDay(data.dataEnd)}</strong> tarihinde bitiyor; gerçekleşme ve beklenen bu güne kadar hesaplanır.</>
              : 'Logo gerçekleşmesi henüz okunmadı.'}
            {running && <> · Okunuyor: {status.data?.step ?? data.step ?? '…'}</>}
            {data.error && !running && <span className="text-red-700"> · Son okuma: {data.error}</span>}
          </span>
          {me?.canEdit && (
            <button type="button" className={btnGhost} onClick={() => refresh.mutate()} disabled={!!running || refresh.isPending}>
              {running || refresh.isPending ? <Loader2 aria-hidden className="h-4 w-4 animate-spin" /> : <RefreshCw aria-hidden className="h-4 w-4" />}
              Gerçekleşmeyi yenile
            </button>
          )}
        </div>
      )}

      {plan && t && (
        <>
          <div className="flex flex-wrap items-center gap-2 px-1">
            <Pill tone={STATUS_TONE[plan.status]}>{plan.statusLabel}</Pill>
            <span className="text-[12px] font-semibold text-canvas-muted">
              {plan.scenarioLabel} senaryo · taban {plan.basis.pencere}
              {plan.decidedAt && plan.status === 'onayli' && <> · {plan.decidedBy} onayladı, {fmtDay(plan.decidedAt)}</>}
              {plan.status === 'onayda' && <> · {plan.submittedBy} gönderdi</>}
              {plan.revisionReason && <> · Revizyon: {plan.revisionReason}</>}
            </span>
            <div className="ml-auto flex flex-wrap gap-2">
              {plan.status === 'taslak' && me?.canEdit && (
                <>
                  <button type="button" className={btnGhost} onClick={() => setAsk('delete')}>Taslağı sil</button>
                  <button type="button" className={btnPrimary} onClick={() => setAsk('submit')}>Onaya gönder</button>
                </>
              )}
              {plan.status === 'onayda' && me?.canEdit && <button type="button" className={btnGhost} onClick={() => setAsk('withdraw')}>Onaydan çek</button>}
              {plan.status === 'onayda' && me?.canApprove && !mine && (
                <>
                  <button type="button" className={btnGhost} onClick={() => setAsk('reject')}>Geri gönder</button>
                  <button type="button" className={btnPrimary} onClick={() => setAsk('approve')}>Onayla</button>
                </>
              )}
              {plan.status === 'onayli' && me?.canEdit && <button type="button" className={btnGhost} onClick={() => setAsk('revise')}>Revize et</button>}
            </div>
          </div>
          {plan.status === 'taslak' && plan.decisionNote && <Note tone="warn">Geri gönderildi ({plan.decidedBy}): {plan.decisionNote}</Note>}
          {plan.status === 'onayda' && me?.canApprove && mine && <Note tone="info">Bu planı siz onaya gönderdiniz; onayı başka bir yetkili verir.</Note>}

          <KpiRow>
            <Kpi label="Hedef net ciro" value={fmtShort(t.ciro)} help={`${t.kitap.toLocaleString('tr-TR')} kitap + ${t.program.ekBaslik.toLocaleString('tr-TR')} ek başlık`}
              info={<SqlInfo k={plans.data?.kaynaklar} alan="items[].totals" row={plan.id} label="Hedef net ciro" />} />
            <Kpi label="Hedef net adet" value={fmtShort(t.adet)} help={`Yeni ${fmtShort(t.segments.yeni?.adet ?? 0)} · backlist ${fmtShort(t.segments.backlist?.adet ?? 0)}`}
              info={<SqlInfo k={plans.data?.kaynaklar} alan="items[].totals" row={plan.id} label="Hedef net adet" />} />
            <Kpi label="Hedef brüt marj" value={fmtPct(t.marj)} help={`Brüt kâr ${fmtShort(t.brutKar)} ₺`}
              info={<SqlInfo k={plans.data?.kaynaklar} alan="items[].totals" row={plan.id} label="Hedef brüt marj" />} />
            <Kpi label="Departman bütçesi" value={fmtShort(t.gider)} help="Yıllık gider bütçesi (7 ile başlayan hesaplar)" active={tab === 'departman'} onClick={() => update({ sekme: 'departman' })}
              info={<SqlInfo k={plans.data?.kaynaklar} alan="items[].totals" row={plan.id} label="Departman bütçesi" />} />
          </KpiRow>
        </>
      )}

      {plans.isSuccess && !list.length && (
        <section className="glass-panel flex flex-col items-start gap-2 rounded-3xl p-5 shadow-glass-float">
          <h2 className="text-lg font-extrabold">{year} için henüz plan yok</h2>
          <p className="max-w-[70ch] text-[12.5px] text-canvas-muted">
            Veriden öneri, Logo gerçekleşmesinden (taban dönem), CRM kitap kartlarından ve baskı önerisinin ZEKİ AI satış tahmininden kurala göre üç senaryolu bir taslak hesaplar:
            muhafazakâr, temel ve iyimser. Taslaklar düzenlenir, biri onaya gönderilir; onaylanınca yılın yürürlükteki planı olur.
          </p>
          {me?.canEdit ? (
            <button type="button" className={btnPrimary} onClick={() => setGen(true)} disabled={!data?.dataEnd}>
              <Calculator aria-hidden className="h-4 w-4" />
              Veriden öneri oluştur
            </button>
          ) : (
            <Note tone="info">Taslak hazırlama yetkisi olan biri öneriyi oluşturabilir.</Note>
          )}
        </section>
      )}

      {plan && (
        <>
          <Tabs tabs={TABS} value={tab} onChange={(k) => update({ sekme: k })} />
          {tab === 'izleme' && <TrackingTab plan={plan} trackable={trackable} onFilter={(durum) => update({ sekme: 'hedefler', durum })} />}
          {tab === 'hedefler' && <TargetsTab plan={plan} editable={editable} trackable={trackable} durum={params.get('durum') ?? ''} onDurum={(d) => update({ durum: d || null })} />}
          {tab === 'program' && <ProgramTab plan={plan} editable={editable} />}
          {tab === 'departman' && <DeptTab plan={plan} editable={editable} />}
          {tab === 'senaryo' && <ScenariosTab year={year} current={plan} canEdit={!!me?.canEdit} onOpen={(id) => update({ plan: id })} onGenerate={() => setGen(true)} />}
        </>
      )}

      <GenerateSheet
        open={gen}
        year={year}
        years={[...new Set([...(meta.data?.years ?? []), year])].sort()}
        onClose={() => setGen(false)}
        onDone={(items) => {
          setGen(false);
          const temel = items.find((p) => p.scenario === 'temel') ?? items[0];
          if (temel) update({ yil: String(temel.year), plan: temel.id, sekme: 'senaryo' });
        }}
      />
      <AskSheet
        open={ask !== null}
        busy={act.isPending}
        title={{ submit: 'Onaya gönder', withdraw: 'Onaydan çek', approve: 'Planı onayla', reject: 'Geri gönder', revise: 'Planı revize et', delete: 'Taslağı sil', '': '' }[ask ?? '']}
        message={
          ask === 'submit' ? 'Plan onay bekleyenlere düşer; onayı sizden başka bir yetkili verir. Onayda iken satırlar değiştirilemez.'
            : ask === 'withdraw' ? 'Plan yeniden taslak olur; değişiklikten sonra tekrar gönderilebilir.'
            : ask === 'approve' ? `Plan ${plan?.year} yılının yürürlükteki planı olur. Varsa önceki yürürlükteki plan arşive geçer; hedefler pazarlama, dağılım ve saha modüllerine bu plandan gider.`
            : ask === 'reject' ? 'Plan gerekçenizle taslağa döner; hazırlayan düzeltip yeniden gönderir.'
            : ask === 'revise' ? 'Yürürlükteki planın kopyası yeni bir taslak sürüm olarak açılır. Onaylanana kadar mevcut hedefler geçerli kalır.'
            : 'Taslak ve bütün satırları silinir. Bu işlem geri alınmaz.'
        }
        confirm={{ submit: 'Onaya gönder', withdraw: 'Taslağa al', approve: 'Onayla', reject: 'Geri gönder', revise: 'Revizyon aç', delete: 'Sil', '': '' }[ask ?? '']}
        danger={ask === 'delete'}
        input={ask === 'reject' ? 'Gerekçe' : ask === 'revise' ? 'Revizyon gerekçesi (sezon, piyasa değişimi…)' : ask === 'approve' ? 'Not (isteğe bağlı)' : undefined}
        required={ask === 'reject' || ask === 'revise'}
        onClose={() => setAsk(null)}
        onConfirm={(text) => ask && act.mutate({ kind: ask, text })}
      />
    </BudgetFrame>
  );
}
