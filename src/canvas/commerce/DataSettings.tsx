import { useEffect, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Loader2 } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import { Loading, Note, Pill, btnPrimary, errText, field, label } from '../admin/ui';
import { Panel } from '../editorial/kit';
import SqlInfo from '../components/SqlInfo';
import { commerceApi, fmtDay, fmtInt, type Settings } from './api';
import { useMeta } from './parts';

/** Veri ve eşikler: T-soft okumasının tazeliği, hangi alanın bulunduğu (ölçüm), eksik alanlar; RFM ve kampanya eşikleri. */
export default function DataSettings() {
  const meta = useMeta();
  const s = useQuery({ queryKey: ['commerce', 'settings'], queryFn: commerceApi.settings, enabled: ENGINE_ENABLED });
  if (meta.isLoading || s.isLoading) return <Loading />;
  if (meta.error) return <Note tone="err">{errText(meta.error, 'Veri durumu açılamadı.')}</Note>;
  const fr = meta.data?.freshness;
  return (
    <div className="grid gap-3 lg:grid-cols-2 lg:gap-4">
      <Panel>
        <h2 className="flex items-center gap-1 text-[15px] font-extrabold">Site verisi <SqlInfo k={meta.data?.kaynaklar} alan="freshness" label="Site verisi okuması" /></h2>
        {!meta.data?.tsoftConfigured && <div className="mt-2"><Note tone="warn">T-soft kullanıcısı girilmemiş (Yönetim → SEO & GEO).</Note></div>}
        {fr && (
          <dl className="mt-2 grid grid-cols-2 gap-x-3 gap-y-1 text-[12.5px]">
            <dt className="font-bold">Son okuma</dt><dd>{fmtDay(fr.okAt)} {fr.full ? '(tam tur)' : '(son günler)'} {fr.stale && <Pill tone="warn">Eski</Pill>}</dd>
            <dt className="font-bold">Son sipariş</dt><dd>{fmtDay(fr.lastOrder)}</dd>
            <dt className="font-bold">Okunan sipariş</dt><dd className="font-mono tabular-nums">{fmtInt(fr.orders)} (iptal/iade {fmtInt(fr.invalid)}, anahtarsız {fmtInt(fr.unkeyed)})</dd>
            <dt className="font-bold">Okunan üye</dt><dd className="font-mono tabular-nums">{fmtInt(fr.members)}</dd>
          </dl>
        )}
        {fr?.error && <div className="mt-2"><Note tone="err">{fr.error}</Note></div>}
        {fr?.memberError && <div className="mt-2"><Note tone="warn">Üyeler okunamadı: {fr.memberError}</Note></div>}
        {fr && fr.missing.length > 0 && (
          <div className="mt-2"><Note tone="warn">Bulunamayan alan: {fr.missing.join(', ')}. Alan adı Yönetim → E-ticaret müşterileri → «T-soft alan adları» ile verilir.</Note></div>
        )}
        {fr && Object.keys(fr.fields).length > 0 && (
          <details className="mt-2 text-[12px]">
            <summary className="min-h-11 cursor-pointer content-center font-bold sm:min-h-0">Alan eşlemesi (ölçüm)</summary>
            <ul className="mt-1 space-y-0.5 text-canvas-muted">
              {Object.entries(fr.fields).map(([role, name]) => <li key={role}><span className="font-mono">{role}</span> ← {name}</li>)}
            </ul>
          </details>
        )}
        <p className="mt-2 text-[11.5px] leading-snug text-canvas-muted">
          Kişisel alanlar (e-posta, telefon, ad) okunduğu anda özetlenir; portalda düz metin durmaz. Gece 02:50'de son günler, pazar gecesi
          bütün siparişler okunur. Görüntülenme sayısı SEO eşitlemesinden gelir.
        </p>
        {meta.data?.me.canSettings && <RefreshButtons />}
      </Panel>
      {s.data && <SettingsForm values={s.data.values} labels={s.data.labels} limits={s.data.limits} canEdit={!!meta.data?.me.canSettings} />}
    </div>
  );
}

function RefreshButtons() {
  const qc = useQueryClient();
  const meta = useMeta();
  const running = meta.data?.job.running;
  const status = useQuery({
    queryKey: ['commerce', 'status'], queryFn: commerceApi.status, enabled: ENGINE_ENABLED && !!running,
    refetchInterval: (q) => (q.state.data && !q.state.data.running ? false : 5000),
  });
  useEffect(() => {
    if (running && status.data && !status.data.running) {
      qc.invalidateQueries({ queryKey: ['commerce'] });
      if (status.data.error) toast.error(status.data.error);
      else toast.success('Site siparişleri okundu.');
    }
  }, [running, status.data, qc]);
  const start = useMutation({
    mutationFn: (full: boolean) => commerceApi.refresh(full),
    onSuccess: (r) => { if (!r.started) toast.message('Okuma zaten sürüyor.'); qc.invalidateQueries({ queryKey: ['commerce', 'meta'] }); },
    onError: (e) => toast.error(errText(e, 'Okuma başlatılamadı.') ?? ''),
  });
  const busy = !!running || start.isPending;
  return (
    <div className="mt-3 flex flex-wrap gap-2">
      <button type="button" className={btnPrimary} disabled={busy} onClick={() => start.mutate(false)}>
        {busy && <Loader2 aria-hidden className="h-4 w-4 animate-spin" />}Son günleri yeniden oku
      </button>
      <button type="button" className={btnPrimary} disabled={busy} onClick={() => start.mutate(true)}>Bütün siparişleri oku</button>
    </div>
  );
}

function SettingsForm({ values, labels, limits, canEdit }: {
  values: Settings; labels: Record<keyof Settings, string>; limits: Record<keyof Settings, [number, number]>; canEdit: boolean;
}) {
  const qc = useQueryClient();
  const [draft, setDraft] = useState<Record<string, string>>(() => Object.fromEntries(Object.entries(values).map(([k, v]) => [k, String(v)])));
  const save = useMutation({
    mutationFn: () => {
      const body: Partial<Record<keyof Settings, number>> = {};
      (Object.keys(values) as Array<keyof Settings>).forEach((k) => {
        const n = Number(String(draft[k]).replace(',', '.'));
        if (!Number.isNaN(n) && n !== values[k]) body[k] = n;
      });
      return commerceApi.saveSettings(body);
    },
    onSuccess: () => { toast.success('Eşikler kaydedildi; segmentler bir sonraki okumada yeniden hesaplanır.'); qc.invalidateQueries({ queryKey: ['commerce'] }); },
    onError: (e) => toast.error(errText(e, 'Kaydedilemedi.') ?? ''),
  });
  return (
    <Panel>
      <h2 className="text-[15px] font-extrabold">Eşikler</h2>
      <form className="mt-2 grid gap-3 sm:grid-cols-2" onSubmit={(e) => { e.preventDefault(); save.mutate(); }}>
        {(Object.keys(values) as Array<keyof Settings>).map((k) => (
          <label key={k} className="flex flex-col gap-1">
            <span className={label}>{labels[k]}</span>
            <input className={field} inputMode="decimal" value={draft[k] ?? ''} disabled={!canEdit}
              onChange={(e) => setDraft((d) => ({ ...d, [k]: e.target.value }))} />
            <span className="text-[11px] text-canvas-muted">{limits[k][0]}–{limits[k][1]}</span>
          </label>
        ))}
        {canEdit && (
          <div className="sm:col-span-2">
            <button type="submit" className={btnPrimary} disabled={save.isPending}>{save.isPending && <Loader2 aria-hidden className="h-4 w-4 animate-spin" />}Kaydet</button>
          </div>
        )}
      </form>
    </Panel>
  );
}
