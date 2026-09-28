import { useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Check, Sparkles, Undo2 } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import { Loading, Note, Pill, btnGhost, btnPrimary, errText, field } from '../admin/ui';
import Sheet from '../editorial/studio/reader/Sheet';
import { MAP_LABEL, SOURCE_LABEL, financeApi, fmtMoney, fmtPct, type AccountMap, type Mapping, type Meta } from './api';
import SqlInfo from '../components/SqlInfo';

/** Hesap → gelir tablosu satırı eşlemesi. Muhasebe onaylar (açıkça verilen yetki); Zeki AI yalnız kuralı olmayan
 *  hesaba kapalı kümeden aday önerir. Grup (3 haneli) kararı alt hesaplara geçer, alt hesapta ayrı karar önceliklidir. */

type Filter = 'yok' | 'oneri' | 'onayli' | 'hepsi';
const FILTERS: Array<[Filter, string]> = [['yok', 'Eşlenmemiş'], ['oneri', 'Onay bekleyen'], ['onayli', 'Karar verilmiş'], ['hepsi', 'Hepsi']];

export default function AccountMapSheet({ open, meta, year, onClose }: { open: boolean; meta: Meta; year: number; onClose: () => void }) {
  const qc = useQueryClient();
  const [filter, setFilter] = useState<Filter>('oneri');
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const [onlyMoving, setOnlyMoving] = useState(true);
  const q = useQuery({
    queryKey: ['finance', 'account-map', year],
    queryFn: () => financeApi.accountMap(year),
    enabled: ENGINE_ENABLED && open,
    refetchInterval: (qq) => ((qq.state.data as AccountMap | undefined)?.suggest?.running ? 4000 : false),
  });
  const canMap = meta.me.canMap;
  const leaves = meta.lines.filter((l) => l.tur === 'gelir' || l.tur === 'gider');
  const lineName = (k: string | null) => (k === 'dislandi' ? 'Gelir tablosu dışı' : leaves.find((l) => l.kod === k)?.ad ?? '—');
  const done = () => {
    qc.invalidateQueries({ queryKey: ['finance'] });
  };
  const approve = useMutation({
    mutationFn: (codes: string[]) => financeApi.approveMappings(codes),
    onSuccess: (r) => {
      toast.success(`${r.approved.length} hesap onaylandı${r.skipped.length ? `, ${r.skipped.length} atlandı` : ''}.`);
      setPicked(new Set());
      done();
    },
    onError: (e) => toast.error(errText(e, 'Onaylanamadı.') ?? ''),
  });
  const setOne = useMutation({
    mutationFn: ({ hesap, satir }: { hesap: string; satir: string }) => financeApi.setMapping(hesap, satir),
    onSuccess: () => { toast.success('Eşleme kaydedildi.'); done(); },
    onError: (e) => toast.error(errText(e, 'Kaydedilemedi.') ?? ''),
  });
  const reset = useMutation({
    mutationFn: (hesap: string) => financeApi.resetMapping(hesap),
    onSuccess: () => { toast.success('Karar geri alındı.'); done(); },
    onError: (e) => toast.error(errText(e, 'Geri alınamadı.') ?? ''),
  });
  const suggest = useMutation({
    mutationFn: () => financeApi.suggestMappings(),
    onSuccess: (r) => { toast.success(r.started ? `${r.count} hesap için Zeki AI önerisi hazırlanıyor.` : r.message ?? 'Öneri bekleyen hesap yok.'); done(); },
    onError: (e) => toast.error(errText(e, 'Öneri başlatılamadı.') ?? ''),
  });

  const d = q.data;
  const groups = useMemo(() => {
    const m = new Map<string, AccountMap['items']>();
    for (const i of d?.items ?? []) {
      if (onlyMoving && !i.hareketli) continue;
      const decided = i.esleme.durum === 'onayli' || i.esleme.durum === 'dislandi';
      if (filter === 'yok' && i.esleme.durum !== 'yok') continue;
      if (filter === 'oneri' && i.esleme.durum !== 'oneri') continue;
      if (filter === 'onayli' && !decided) continue;
      m.set(i.grup, [...(m.get(i.grup) ?? []), i]);
    }
    return [...m.entries()].sort(([a], [b]) => a.localeCompare(b));
  }, [d, filter, onlyMoving]);

  const toggle = (h: string) => setPicked((s) => {
    const n = new Set(s);
    if (n.has(h)) n.delete(h);
    else n.add(h);
    return n;
  });

  const badge = (e: Mapping) => (
    <span className="flex flex-wrap items-center gap-1.5">
      <Pill tone={MAP_LABEL[e.durum].tone}>{MAP_LABEL[e.durum].label}</Pill>
      {e.kaynak && <span className="text-[11px] text-canvas-muted">{SOURCE_LABEL[e.kaynak]}{e.kayit ? ` · ${e.kayit}` : ''}</span>}
      {e.kaynak === 'zeki' && e.olasilik !== undefined && e.olasilik !== null && <span className="text-[11px] text-canvas-muted">olasılık {fmtPct(e.olasilik)}</span>}
    </span>
  );

  return (
    <Sheet open={open} onClose={onClose} modal wide title="Hesap eşlemesi"
      subtitle="Her muhasebe hesabının gelir tablosundaki satırı. Tekdüzen hesap planı kuralı ve Zeki AI önerisi taslaktır; muhasebe onaylayınca kesinleşir. Eşlenmemiş hesap raporda kaybolmaz, «Eşlenmemiş hesaplar» satırında durur.">
      {q.isLoading ? <Loading /> : q.error ? <Note tone="err">{errText(q.error, 'Eşleme okunamadı.')}</Note> : d && (
        <div className="flex flex-col gap-3">
          <div className="grid grid-cols-2 gap-2 text-[12px] sm:grid-cols-4">
            {(['onayli', 'dislandi', 'oneri', 'yok'] as const).map((k) => (
              <div key={k} className="rounded-xl bg-white/80 p-2.5">
                <div className="font-bold">{MAP_LABEL[k].label}</div>
                <div className="font-mono tabular-nums">{d.counts[k]} hesap · {fmtMoney(d.amounts[k])} <SqlInfo k={d.kaynaklar} alan="counts" label="Eşleme durumu sayıları" /></div>
              </div>
            ))}
          </div>
          {!canMap && <Note tone="info">Eşleme kararını muhasebe verir; bu rolde yalnız görüntüleme var.</Note>}
          {d.suggest?.running && <Note tone="info">Zeki AI {d.suggest.count} hesap için öneri hazırlıyor…</Note>}
          {d.suggest?.error && <Note tone="err">Son öneri işi: {d.suggest.error}</Note>}
          <div className="flex flex-wrap items-center gap-2">
            <div className="flex gap-1 rounded-xl bg-slate-100 p-1" role="tablist" aria-label="Durum">
              {FILTERS.map(([k, label]) => (
                <button key={k} type="button" role="tab" aria-selected={filter === k} onClick={() => setFilter(k)}
                  className={`min-h-9 rounded-lg px-2.5 text-[12px] font-bold ${filter === k ? 'bg-white shadow-sm' : ''}`}>{label}</button>
              ))}
            </div>
            <label className="flex min-h-9 items-center gap-1.5 text-[12px] font-semibold">
              <input type="checkbox" checked={onlyMoving} onChange={(e) => setOnlyMoving(e.target.checked)} />
              Yalnız {d.year} hareketi olanlar
            </label>
            {canMap && (
              <div className="ml-auto flex flex-wrap gap-2">
                <button type="button" className={btnGhost} onClick={() => suggest.mutate()} disabled={suggest.isPending || !!d.suggest?.running}>
                  <Sparkles aria-hidden className="h-4 w-4" /> Zeki AI önerisi
                </button>
                <button type="button" className={btnPrimary} disabled={!picked.size || approve.isPending} onClick={() => approve.mutate([...picked])}>
                  <Check aria-hidden className="h-4 w-4" /> Seçilenleri onayla ({picked.size})
                </button>
              </div>
            )}
          </div>
          {!groups.length ? <Note tone="ok">Bu süzgeçte hesap yok.</Note> : (
            <div className="flex flex-col gap-3">
              {groups.map(([g, rows]) => (
                <section key={g} className="rounded-2xl border border-slate-100 bg-white/80">
                  <header className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 px-3 py-2">
                    <div className="text-[12.5px] font-extrabold">Grup {g} · {rows.length} hesap</div>
                    {canMap && rows.some((r) => r.esleme.durum === 'oneri') && (
                      <button type="button" className={btnGhost} onClick={() => approve.mutate([g])} disabled={approve.isPending}>
                        Grubu öneriyle onayla
                      </button>
                    )}
                  </header>
                  <ul>
                    {rows.map((r) => (
                      <li key={r.hesap} className="flex flex-col gap-2 border-t border-slate-50 px-3 py-2 first:border-t-0 sm:flex-row sm:items-center">
                        <label className="flex min-w-0 flex-1 items-start gap-2">
                          {canMap && r.esleme.durum === 'oneri' && (
                            <input type="checkbox" className="mt-1 h-4 w-4" checked={picked.has(r.hesap)} onChange={() => toggle(r.hesap)} aria-label={`${r.hesap} seç`} />
                          )}
                          <span className="min-w-0">
                            <span className="block truncate text-[12.5px] font-bold"><span className="font-mono">{r.hesap}</span> · {r.ad ?? '—'}</span>
                            <span className="mt-0.5 block">{badge(r.esleme)}</span>
                            {r.esleme.not && <span className="block text-[11px] text-canvas-muted">{r.esleme.not}</span>}
                          </span>
                        </label>
                        <span className="inline-flex shrink-0 items-center gap-1 font-mono text-[12px] tabular-nums">{fmtMoney(r.etki)}<SqlInfo k={d.kaynaklar} alan="items[].etki" label={`${r.hesap} · yıllık kâr etkisi`} /></span>
                        {canMap ? (
                          <div className="flex shrink-0 items-center gap-1.5">
                            <select className={`${field} min-w-[200px]`} aria-label={`${r.hesap} satırı`}
                              value={r.esleme.satir ?? ''} onChange={(e) => e.target.value && setOne.mutate({ hesap: r.hesap, satir: e.target.value })}>
                              <option value="">— satır seçin —</option>
                              {leaves.map((l) => <option key={l.kod} value={l.kod}>{l.ad}</option>)}
                              <option value="dislandi">Gelir tablosu dışı (dışla)</option>
                            </select>
                            {(r.esleme.durum === 'onayli' || r.esleme.durum === 'dislandi') && r.esleme.kayit === r.hesap && (
                              <button type="button" className={btnGhost} aria-label="Kararı geri al" onClick={() => reset.mutate(r.hesap)}>
                                <Undo2 aria-hidden className="h-4 w-4" />
                              </button>
                            )}
                          </div>
                        ) : (
                          <span className="shrink-0 text-[12px] font-semibold">{lineName(r.esleme.satir)}</span>
                        )}
                      </li>
                    ))}
                  </ul>
                </section>
              ))}
            </div>
          )}
        </div>
      )}
    </Sheet>
  );
}
