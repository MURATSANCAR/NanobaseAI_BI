import { useCallback, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Loader2, RotateCw } from 'lucide-react';
import Shell, { ZoomStage } from '../stitch/Shell';
import { ENGINE_ENABLED } from '../engine';
import { Loading, Note, Pill, btnPrimary, errText } from '../admin/ui';
import { Tabs } from '../budget/parts';
import { fmtAt, fmtMinutes, itOpsApi, type Incident, type RingId, type Status } from './api';
import RingCard from './RingCard';
import SqlInfo from '../components/SqlInfo';
import { kaynakOf } from '../components/kaynakOf';
import IncidentPanel from './IncidentPanel';
import { CapacityTab, IncidentsTab, JobsTab, ReleasesTab, SettingsTab } from './tabs';

/** M48 Sistem durumu: ZEKİ'yi ayakta tutan yedi halka, olaylar, zamanlanmış işler, sürümler ve kapasite. Sekme ve
 *  açık olay adres çubuğunda (?sekme=, ?olay=); bağlantı paylaşılabilir. Denetimler yalnız okur, servis başlatmaz. */

const TABS = [
  { key: 'durum', label: 'Durum' },
  { key: 'olaylar', label: 'Olaylar' },
  { key: 'isler', label: 'Zamanlanmış işler' },
  { key: 'surumler', label: 'Sürümler' },
  { key: 'kapasite', label: 'Kapasite' },
  { key: 'ayarlar', label: 'Ayarlar' },
] as const;
type Tab = (typeof TABS)[number]['key'];

const BAND: Record<Status['summary']['tone'], string> = {
  ok: 'bg-emerald-50 text-emerald-800 border-emerald-100',
  warn: 'bg-amber-50 text-amber-900 border-amber-100',
  err: 'bg-red-50 text-red-800 border-red-100',
  unknown: 'bg-slate-50 text-canvas-ink border-slate-100',
};

export default function SystemStatusScreen() {
  const qc = useQueryClient();
  const [params, setParams] = useSearchParams();
  const tab: Tab = (TABS.find((t) => t.key === params.get('sekme'))?.key ?? 'durum') as Tab;
  const incidentId = params.get('olay');
  const [busy, setBusy] = useState<RingId | 'all' | null>(null);

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

  const status = useQuery({ queryKey: ['itops', 'status'], queryFn: itOpsApi.status, enabled: ENGINE_ENABLED, refetchInterval: 60_000 });
  const s = status.data;

  const check = useMutation({
    mutationFn: (ring?: RingId) => itOpsApi.checkNow(ring),
    onMutate: (ring) => setBusy(ring ?? 'all'),
    onSettled: () => setBusy(null),
    onSuccess: (out) => {
      qc.setQueryData(['itops', 'status'], (old: Status | undefined) => (old ? { ...old, ...out } : old));
      qc.invalidateQueries({ queryKey: ['itops'] });
      if (out.failed.length) toast.error(`Başarısız: ${out.failed.map((r) => s?.rings.find((x) => x.id === r)?.label ?? r).join(', ')}`);
      else toast.success('Denendi, bağlantılar çalışıyor.');
    },
    onError: (e) => toast.error(errText(e, 'Denenemedi.') ?? ''),
  });

  const openIncident = (i: Incident) => update({ olay: i.id });
  const tabs = TABS.map((t) => ({ ...t, badge: t.key === 'olaylar' ? s?.open.length ?? null : t.key === 'isler' ? s?.jobs.failed ?? null : null }));

  return (
    <Shell head={{ tenant: 'Timaş Yayınları', section: 'Altyapı ve destek', crumb: 'Sistem durumu', source: s ? `Son tur ${fmtAt(s.rings.map((r) => r.at).filter(Boolean).sort().pop() ?? null)}` : '', presence: s?.env === 'vm' ? "Müşteri VM'i" : 'Test sunucusu' }}>
      <main className="absolute bottom-2 left-2 right-2 top-16 overflow-y-auto overscroll-contain sm:bottom-6 sm:left-6 sm:right-6 sm:top-[84px]">
        <ZoomStage>
          <div className="mx-auto flex w-full max-w-[1760px] flex-col gap-3 pb-6 lg:gap-4">
            <header className="flex flex-col gap-3 px-1 lg:flex-row lg:items-start lg:justify-between lg:gap-6">
              <div className="min-w-0">
                <div className="text-[11px] font-bold uppercase tracking-wide text-canvas-violet">Altyapı ve destek · IT altyapı ve sistem yönetimi</div>
                <h1 className="mt-0.5 text-[22px] font-extrabold leading-tight tracking-tight sm:text-[28px]">Sistem durumu</h1>
                <p className="mt-1 max-w-[72ch] text-[12.5px] leading-snug text-canvas-muted">
                  Logo, CRM, giriş, Zeki AI modeli, e-posta, şirket ağı bağlantısı ve müşteri VM'i 5 dakikada bir denenir. İki ardışık başarısız deneme
                  olay açar ve BT'ye e-postayla bildirilir; düzelince süresiyle ikinci bildirim gider. Denemeler yalnız okur, hiçbir servisi yeniden başlatmaz.
                </p>
              </div>
              {s?.me.canCheck && (
                <button type="button" className={`${btnPrimary} shrink-0`} disabled={!!busy} onClick={() => check.mutate(undefined)}>
                  {busy === 'all' ? <Loader2 aria-hidden className="h-4 w-4 animate-spin" /> : <RotateCw aria-hidden className="h-4 w-4" />}
                  Hepsini şimdi dene
                </button>
              )}
            </header>

            {!ENGINE_ENABLED && <Note tone="warn">Bu derlemede veri bağlantısı tanımlı değil.</Note>}
            {status.error && <Note tone="err">{errText(status.error, 'Sistem durumu okunamadı.')}</Note>}

            {s && (
              <div role="status" className={`rounded-2xl border px-3 py-2.5 text-[13.5px] font-extrabold leading-snug sm:px-4 sm:text-[15px] ${BAND[s.summary.tone]}`}>
                {s.summary.text}
              </div>
            )}

            <Tabs tabs={tabs} value={tab} onChange={(t) => update({ sekme: t === 'durum' ? null : t })} />

            {status.isLoading && <Loading />}

            {tab === 'durum' && s && (
              <div className="grid min-w-0 gap-3 xl:grid-cols-[minmax(0,1fr)_360px] xl:gap-4">
                <div className="grid min-w-0 gap-3 [grid-template-columns:repeat(auto-fill,minmax(min(100%,280px),1fr))]">
                  {s.rings.map((r) => (
                    <RingCard key={r.id} ring={r} k={kaynakOf(s)} canCheck={s.me.canCheck} busy={busy === r.id || busy === 'all'}
                      onCheck={() => check.mutate(r.id)} onIncident={openIncident} />
                  ))}
                </div>
                <aside className="flex min-w-0 flex-col gap-3">
                  <section className="glass-panel rounded-2xl p-3 shadow-glass-float sm:rounded-3xl sm:p-4">
                    <h2 className="flex items-center gap-1 text-[13px] font-extrabold">
                      Açık olaylar
                      <SqlInfo k={kaynakOf(s)} alan="open" label="Açık olaylar (sekme rozeti dahil)" />
                    </h2>
                    {!s.open.length && <p className="mt-1 text-[12.5px] text-canvas-muted">Açık olay yok.</p>}
                    <ul className="mt-2 flex flex-col gap-1.5">
                      {s.open.map((i) => (
                        <li key={i.id}>
                          <button type="button" onClick={() => openIncident(i)}
                            className="flex w-full min-w-0 items-center gap-2 rounded-xl bg-white/70 px-2.5 py-2 text-left transition-transform duration-150 ease-out hover:bg-white active:scale-[0.98]">
                            <Pill tone={i.kind === 'kopma' ? 'err' : 'warn'}>{i.kind === 'kopma' ? 'Kopuk' : 'Veri eski'}</Pill>
                            <span className="min-w-0 flex-1 truncate text-[12.5px] font-semibold">{i.ringLabel}</span>
                            <span className="shrink-0 text-[11.5px] tabular-nums text-canvas-muted">{fmtMinutes(i.minutes)}</span>
                          </button>
                        </li>
                      ))}
                    </ul>
                  </section>
                  <section className="glass-panel rounded-2xl p-3 text-[12.5px] shadow-glass-float sm:rounded-3xl sm:p-4">
                    <h2 className="text-[13px] font-extrabold">Bildirim</h2>
                    <p className="mt-1 leading-snug text-canvas-muted">
                      {!s.email.configured
                        ? 'E-posta ayarı yok: olaylar yalnız bu ekranda.'
                        : s.email.recipients.length
                          ? `${s.email.recipients.length} iç alıcıya gider.`
                          : 'Alıcı tanımlı değil: Ayarlar sekmesinden eklenir.'}
                    </p>
                    <h2 className="mt-3 flex items-center gap-1 text-[13px] font-extrabold">
                      Zamanlanmış işler
                      <SqlInfo k={kaynakOf(s)} alan="jobs" label="Zamanlanmış işler (sekme rozeti dahil)" />
                    </h2>
                    <button type="button" onClick={() => update({ sekme: 'isler' })} className="mt-1 text-left font-semibold text-canvas-violet underline-offset-2 hover:underline">
                      {s.jobs.failed ? `${s.jobs.failed} iş hatalı` : `${s.jobs.total} iş, hatasız`}
                    </button>
                    {s.releases.parity !== null && (
                      <>
                        <h2 className="mt-3 text-[13px] font-extrabold">Sürüm eşliği</h2>
                        <p className={`mt-1 font-semibold ${s.releases.parity ? 'text-emerald-700' : 'text-amber-800'}`}>
                          {s.releases.parity ? "Test sunucusu ve müşteri VM'i aynı sürümde" : "Test sunucusu ve müşteri VM'i farklı sürümde"}
                        </p>
                      </>
                    )}
                  </section>
                </aside>
              </div>
            )}
            {tab === 'olaylar' && <IncidentsTab status={s} onOpen={openIncident} />}
            {tab === 'isler' && <JobsTab />}
            {tab === 'surumler' && <ReleasesTab />}
            {tab === 'kapasite' && <CapacityTab />}
            {tab === 'ayarlar' && <SettingsTab status={s} />}
          </div>
        </ZoomStage>
      </main>
      <IncidentPanel id={incidentId} canClose={!!s?.me.canClose} onClose={() => update({ olay: null })} />
    </Shell>
  );
}
