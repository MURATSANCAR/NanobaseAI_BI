import { useEffect, useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Loader2, Sparkles } from 'lucide-react';
import { ENGINE_ENABLED } from '../../engine';
import { Loading, Note, Pill, TableWrap, btnGhost, btnPrimary, errText, field, label as labelCls, td, th } from '../../admin/ui';
import { fmtDay, fmtInt, fmtMoney, fmtStamp } from '../api';
import { Block, SourceNote } from '../parts';
import { launchApi, type Launch, type LaunchMeta, type Review } from './api';

/** D+7 ve D+30 değerlendirmesi: rakam tablosu SQL'den (model yok), Zeki AI iki paragraf özet ve en çok üç öneri yazar
 *  (tabloda olmayan rakamı içeren cümle düşer). Karar — bütçeyi artır / aynı kalsın / kes — gerekçesiyle insanındır. */

const fmtVal = (v: number | null, birim: string) =>
  v === null || v === undefined ? '—' : birim === '%' ? `%${new Intl.NumberFormat('tr-TR', { maximumFractionDigits: 1 }).format(v)}` : birim === 'TL' ? fmtMoney(v) : `${fmtInt(v)} ${birim}`;

function Decide({ launch, meta, rv }: { launch: Launch; meta: LaunchMeta; rv: Review }) {
  const qc = useQueryClient();
  const [karar, setKarar] = useState('koru');
  const [why, setWhy] = useState('');
  const save = useMutation({
    mutationFn: () => launchApi.decide(launch.id, rv.gun, karar, why),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['launch'] }); toast.success('Karar kaydedildi; plan geçmişine de yazıldı.'); },
    onError: (e) => toast.error(errText(e, 'Karar kaydedilemedi.') ?? ''),
  });
  return (
    <form className="mt-3 grid grid-cols-1 gap-2 rounded-2xl bg-slate-50 p-2.5 sm:grid-cols-[200px_1fr_auto] sm:items-end"
      onSubmit={(e) => { e.preventDefault(); if (why.trim()) save.mutate(); }}>
      <label className="flex flex-col gap-1"><span className={labelCls}>Karar</span>
        <select className={field} value={karar} onChange={(e) => setKarar(e.target.value)}>
          {Object.entries(meta.decisions).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </select></label>
      <label className="flex min-w-0 flex-col gap-1"><span className={labelCls}>Gerekçe</span>
        <textarea className={`${field} min-h-[44px]`} value={why} onChange={(e) => setWhy(e.target.value)} placeholder="Ör. dijital bütçeyi ikinci haftaya kaydır; stok yeterli" /></label>
      <button type="submit" className={btnPrimary} disabled={!why.trim() || save.isPending}>Kararı kaydet</button>
    </form>
  );
}

function One({ launch, meta, gun, rv, running }: { launch: Launch; meta: LaunchMeta; gun: 7 | 30; rv: Review | undefined; running: boolean }) {
  const qc = useQueryClient();
  const due = new Date(Date.parse(launch.yayinGunu) + gun * 86_400_000).toISOString().slice(0, 10);
  const draft = useMutation({
    mutationFn: () => launchApi.draft(launch.id, gun),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['launch', 'reviews', launch.id] }); toast.success('Rakamlar hazır; Zeki AI özeti yazılıyor.'); },
    onError: (e) => toast.error(errText(e, 'Rapor hazırlanamadı.') ?? ''),
  });
  const sqlText = rv ? Object.entries(rv.rakam.sql).map(([k, v]) => `-- ${k}\n${Array.isArray(v) ? v.join('\n\n') : v}`).join('\n\n') : null;
  return (
    <Block
      title={`D+${gun} değerlendirmesi`}
      help={rv ? `İlk ${gun} gün (${fmtDay(rv.rakam.pencere.bas)} – ${fmtDay(rv.rakam.pencere.bit)}) · hazırlayan ${rv.hazirlayan} · ${fmtStamp(rv.hazirlama)}` : `${fmtDay(due)} sabahı kendiliğinden hazırlanır.`}
      action={meta.me.canWrite && rv?.durum !== 'karar' && (
        <button type="button" className={btnGhost} disabled={running || draft.isPending} onClick={() => draft.mutate()}>
          {running || draft.isPending ? <Loader2 aria-hidden className="h-4 w-4 animate-spin" /> : <Sparkles aria-hidden className="h-4 w-4" />}
          {rv ? 'Yeniden hazırla' : 'Şimdi hazırla'}
        </button>
      )}
    >
      {!rv && <p className="text-[12.5px] text-canvas-muted">Henüz rapor yok.</p>}
      {rv && (
        <>
          {rv.rakam.eksikGun > 0 && <Note tone="warn">{gun} gün henüz dolmadı ({rv.rakam.eksikGun} gün eksik): rakamlar bugüne kadardır.</Note>}
          <div className="mt-2">
            <TableWrap>
              <thead className="bg-slate-50"><tr><th className={th}>Ölçü</th><th className={th}>Değer</th><th className={th}>Kaynak</th></tr></thead>
              <tbody>
                {rv.rakam.satirlar.filter((r) => !(r.para && !meta.me.canSeeBudget)).map((r) => (
                  <tr key={r.anahtar} className="border-t border-slate-100">
                    <td className={td}>{r.ad}</td>
                    <td className={`${td} whitespace-nowrap font-mono tabular-nums`}>{fmtVal(r.deger, r.birim)}</td>
                    <td className={`${td} text-canvas-muted`}>{r.kaynak}</td>
                  </tr>
                ))}
              </tbody>
            </TableWrap>
          </div>
          <SourceNote text="Rapor rakamları günlük tablodan ve bu sorgulardan; Zeki AI bu tablodaki rakamı aynen kullanır, yeni rakam yazamaz." sql={sqlText} />
          <div className="mt-3">
            <div className="text-[11px] font-bold uppercase tracking-wide text-canvas-muted">Zeki AI özeti</div>
            {rv.ozet ? <p className="mt-1 whitespace-pre-line text-[13px] leading-relaxed">{rv.ozet}</p>
              : <p className="mt-1 text-[12.5px] text-canvas-muted">{running ? 'Yazılıyor…' : 'Özet yok (model bağlı değil ya da denetimden geçen cümle kalmadı).'}</p>}
            {rv.oneriler.length > 0 && (
              <>
                <div className="mt-2 text-[11px] font-bold uppercase tracking-wide text-canvas-muted">Öneriler</div>
                <ul className="mt-1 list-disc pl-5 text-[13px] leading-snug">{rv.oneriler.map((s) => <li key={s}>{s}</li>)}</ul>
              </>
            )}
            {!!rv.dogrulama?.dusenSayisi && <p className="mt-1 text-[11px] text-canvas-muted">Denetimde {rv.dogrulama.dusenSayisi} cümle düştü (tabloda olmayan rakam ya da kanıtsız iddia).</p>}
          </div>
          {rv.rakam.yapilmayan.length > 0 && (
            <p className="mt-2 text-[12px] text-canvas-muted">Yapılmayan maddeler: {rv.rakam.yapilmayan.map((x) => x.is).join('; ')}</p>
          )}
          {rv.karar ? (
            <div className="mt-3 flex flex-wrap items-center gap-2 rounded-2xl bg-emerald-50/60 p-2.5 text-[12.5px]">
              <Pill tone="ok">{rv.kararAdi}</Pill>
              <span className="min-w-0 break-words">{rv.gerekce}</span>
              <span className="text-canvas-muted">— {rv.kararVeren}, {fmtStamp(rv.kararZamani)}</span>
            </div>
          ) : meta.me.canDecide ? (
            <Decide launch={launch} meta={meta} rv={rv} />
          ) : (
            <p className="mt-3 text-[12px] text-canvas-muted">Karar pazarlama planı onay yetkisi olan kişi tarafından kaydedilir.</p>
          )}
        </>
      )}
    </Block>
  );
}

export default function ReviewTab({ launch, meta }: { launch: Launch; meta: LaunchMeta }) {
  const qc = useQueryClient();
  const q = useQuery({
    queryKey: ['launch', 'reviews', launch.id],
    queryFn: () => launchApi.reviews(launch.id),
    enabled: ENGINE_ENABLED,
    refetchInterval: (s) => (s.state.data?.jobs.some((j) => j.durum === 'bekliyor' || j.durum === 'calisiyor') ? 3000 : false),
  });
  const jobs = q.data?.jobs ?? [];
  const runningFor = (g: number) => jobs.some((j) => j.tur === `lansman-rapor-${g}` && (j.durum === 'bekliyor' || j.durum === 'calisiyor'));
  const anyRunning = runningFor(7) || runningFor(30);
  const was = useRef(false);
  useEffect(() => {
    if (anyRunning) was.current = true;
    else if (was.current) {
      was.current = false;
      qc.invalidateQueries({ queryKey: ['launch', launch.id] });
      const last = jobs[0];
      if (last?.durum === 'hata') toast.error(last.hata ?? 'Özet yazılamadı.');
    }
  }, [anyRunning, jobs, qc, launch.id]);
  const last = jobs[0];
  const uyari = last?.durum === 'bitti' && typeof last.sonuc?.uyari === 'string' ? (last.sonuc.uyari as string) : null;
  return (
    <div className="flex flex-col gap-3">
      {q.error && <Note tone="err">{errText(q.error, 'Değerlendirme açılamadı.')}</Note>}
      {q.isLoading && <Loading />}
      {!meta.modelReady && <Note tone="warn">Zeki AI modeli bu kurulumda bağlı değil: rapor yalnız rakam tablosuyla hazırlanır.</Note>}
      {uyari && <Note tone="warn">{uyari}</Note>}
      {q.data && ([7, 30] as const).map((g) => (
        <One key={g} launch={launch} meta={meta} gun={g} rv={q.data.items.find((r) => r.gun === g)} running={runningFor(g)} />
      ))}
    </div>
  );
}
