import { useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import SqlInfo, { InfoLabel } from '../components/SqlInfo';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { ENGINE_ENABLED } from '../engine';
import { Note, Pill, btnGhost, btnPrimary, errText } from '../admin/ui';
import { Pager, Panel } from '../editorial/kit';
import { AskSheet } from '../budget/parts';
import { fmtDay } from '../budget/api';
import { gunText, n0, n1, stockApi, type Proposal, type Threshold } from './api';
import { BookCell, Chips, ExportLink, Loading, SourcesButton, StockFrame } from './parts';
import { EmptyHint } from '../components/Explain';
import { RULES } from './rules';

/** Güvenlik stoku (/stok/esikler): Logo'da asgari seviye girilmediği için portal önerir (günlük satış × (baskı süresi +
 *  güvenlik günü)), stok planlama onaylar. Onay portalda durur; Logo `INVDEF`'e yazılmaz. */

type Durum = 'oneri' | 'taslak' | 'onayli' | 'red' | 'arsiv';
const TABS: Array<{ key: Durum; label: string }> = [
  { key: 'oneri', label: 'Öneriler' },
  { key: 'taslak', label: 'Onay bekleyen' },
  { key: 'onayli', label: 'Onaylı' },
  { key: 'red', label: 'Reddedilen' },
  { key: 'arsiv', label: 'Arşiv' },
];

export default function Thresholds() {
  const qc = useQueryClient();
  const [params, setParams] = useSearchParams();
  const durum = (TABS.find((t) => t.key === params.get('durum'))?.key ?? 'oneri') as Durum;
  const sayfa = Number(params.get('sayfa') ?? 0) || 0;
  const [reject, setReject] = useState<string | null>(null);
  const set = (k: string, v: string | null) => {
    const p = new URLSearchParams(params);
    if (v) p.set(k, v);
    else p.delete(k);
    if (k !== 'sayfa') p.delete('sayfa');
    setParams(p, { replace: true });
  };
  const meta = useQuery({ queryKey: ['stock', 'meta'], queryFn: stockApi.meta, enabled: ENGINE_ENABLED, staleTime: 60_000 });
  const q = useQuery({ queryKey: ['stock', 'thresholds', durum, sayfa], queryFn: () => stockApi.thresholds(durum, sayfa), enabled: ENGINE_ENABLED, placeholderData: (p) => p });
  const me = meta.data?.me;
  const done = () => qc.invalidateQueries({ queryKey: ['stock'] });
  const save = useMutation({
    mutationFn: (v: { p: Proposal; onayla: boolean }) =>
      stockApi.saveThreshold({ stokKodu: v.p.stokKodu, guvenlikGun: v.p.guvenlikGun, yenidenSiparisAdet: v.p.yenidenSiparisAdet, gerekce: v.p.gerekce, kaynak: 'oneri', onayla: v.onayla }),
    onSuccess: (t) => { toast.success(t.durum === 'onayli' ? 'Onaylandı.' : 'Taslak kaydedildi.'); done(); },
    onError: (e) => toast.error(errText(e, 'Kaydedilemedi.') ?? ''),
  });
  const approve = useMutation({ mutationFn: (id: string) => stockApi.approveThreshold(id), onSuccess: done, onError: (e) => toast.error(errText(e, 'Onaylanamadı.') ?? '') });
  const rej = useMutation({
    mutationFn: (v: { id: string; not: string }) => stockApi.rejectThreshold(v.id, v.not),
    onSuccess: () => { setReject(null); done(); },
    onError: (e) => toast.error(errText(e, 'Reddedilemedi.') ?? ''),
  });
  const d = q.data;

  return (
    <StockFrame
      crumb="Güvenlik stoku"
      title="Güvenlik stoku ve yeniden sipariş noktası"
      lead="Logo’da asgari stok seviyesi girilmemiş. Portal her satışlı kitap için güvenlik günü ve yeniden sipariş adedi önerir; stok planlama onaylar. Onaylanan eşik bitecek uyarısında kullanılır, Logo’ya yazılmaz."
      source="Logo + üretim kartları"
      aside={
        <>
          <SourcesButton rules={RULES} />
          <ExportLink show={!!me?.canExport} href={stockApi.exportUrl('esik-onerileri')} />
        </>
      }
    >
      <Chips<Durum> label="Durum" items={TABS} value={durum} onChange={(k) => set('durum', k === 'oneri' ? null : k)} />
      <Panel>
        {q.error && <Note tone="err">{errText(q.error, 'Liste okunamadı.')}</Note>}
        {q.isLoading && <Loading what="Eşikler" />}
        {d && !d.items.length && <EmptyHint title="Bu durumda eşik yok" why="Seçtiğiniz durumdaki güvenlik stoku kaydı bulunmadı; başka bir durumu seçin." />}
        {!!d?.items.length && (
          <div className="mb-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] font-semibold text-canvas-muted" aria-label="Rakamların sorgu bilgisi">
            {durum === 'oneri' ? (
              <>
                <InfoLabel k={d.kaynaklar} alan="items[].bakiye">Stok</InfoLabel>
                <InfoLabel k={d.kaynaklar} alan="items[].satisHizi">Aylık hız</InfoLabel>
                <InfoLabel k={d.kaynaklar} alan="items[].gun">Kaç gün yeter</InfoLabel>
                <InfoLabel k={d.kaynaklar} alan="items[].yenidenSiparisAdet">Önerilen gün ve adet</InfoLabel>
                <InfoLabel k={d.kaynaklar} alan="total">Kitap sayısı</InfoLabel>
              </>
            ) : (
              <span className="inline-flex items-center gap-1">Güvenlik günü ve adet<SqlInfo k={d.kaynaklar} alan="items[]" label="Eşik kayıtları" /></span>
            )}
          </div>
        )}
        <ul className="flex flex-col gap-2">
          {durum === 'oneri'
            ? (d?.items as Proposal[] | undefined)?.map((p) => (
                <li key={p.stokKodu} className="flex flex-col gap-2 rounded-2xl border border-slate-100 bg-white/80 p-3 text-[12.5px] sm:flex-row sm:items-center sm:justify-between">
                  <div className="min-w-0">
                    <BookCell it={{ stokKodu: p.stokKodu, ad: p.ad, yayinevi: null }} />
                    <div className="mt-1 text-canvas-muted">
                      Stok {n0(p.bakiye)} · aylık hız {n1(p.satisHizi)} · {gunText(p.gun)} · önerilen: <strong className="text-canvas-ink">{p.guvenlikGun} gün, {n0(p.yenidenSiparisAdet)} adet</strong>
                    </div>
                    <div className="text-[11px] text-canvas-muted">{p.gerekce}</div>
                  </div>
                  {me?.canDecide && (
                    <div className="flex shrink-0 gap-2">
                      <button type="button" className={btnGhost} disabled={save.isPending} onClick={() => save.mutate({ p, onayla: false })}>Taslak</button>
                      {me.canApprove && (
                        <button type="button" className={btnPrimary} disabled={save.isPending} onClick={() => save.mutate({ p, onayla: true })}>Onayla</button>
                      )}
                    </div>
                  )}
                </li>
              ))
            : (d?.items as Threshold[] | undefined)?.map((t) => (
                <li key={t.id} className="flex flex-col gap-2 rounded-2xl border border-slate-100 bg-white/80 p-3 text-[12.5px] sm:flex-row sm:items-center sm:justify-between">
                  <div className="min-w-0">
                    <BookCell it={{ stokKodu: t.stokKodu, ad: t.ad ?? null, yayinevi: null }} />
                    <div className="mt-1 flex flex-wrap items-center gap-2 text-canvas-muted">
                      <Pill tone={t.durum === 'onayli' ? 'ok' : t.durum === 'taslak' ? 'warn' : 'muted'}>{t.durumEtiket}</Pill>
                      <span>{t.guvenlikGun} gün{t.yenidenSiparisAdet !== null ? ` · ${n0(t.yenidenSiparisAdet)} adet` : ''}{t.depoNo ? ` · depo ${t.depoNo}` : ''}</span>
                      <span>· {t.olusturan}{t.onaylayan ? ` → ${t.onaylayan}` : ''}{t.onayTarihi ? ` · ${fmtDay(t.onayTarihi)}` : ''}</span>
                    </div>
                    {t.gerekce && <div className="text-[11px] text-canvas-muted">{t.gerekce}</div>}
                  </div>
                  {t.durum === 'taslak' && me?.canApprove && (
                    <div className="flex shrink-0 gap-2">
                      <button type="button" className={btnGhost} onClick={() => setReject(t.id)}>Reddet</button>
                      <button type="button" className={btnPrimary} disabled={approve.isPending} onClick={() => approve.mutate(t.id)}>Onayla</button>
                    </div>
                  )}
                </li>
              ))}
        </ul>
        {d && <Pager page={d.page} pageSize={d.pageSize} total={d.total} shown={d.items.length} loading={q.isLoading} fetching={q.isFetching} onPage={(p) => set('sayfa', String(p))} />}
      </Panel>
      <AskSheet
        open={!!reject}
        title="Güvenlik stokunu reddet"
        message="Gerekçe kayda geçer; taslağı yazan görür."
        confirm="Reddet"
        danger
        input="Gerekçe"
        required
        busy={rej.isPending}
        onClose={() => setReject(null)}
        onConfirm={(t) => reject && rej.mutate({ id: reject, not: t })}
      />
    </StockFrame>
  );
}
