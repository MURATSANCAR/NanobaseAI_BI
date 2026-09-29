import { useCallback, useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Check, EyeOff, RotateCcw } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import { Note, Pill, btnGhost, btnPrimary, errText, field, label as labelCls } from '../admin/ui';
import { Pager, Panel, useDebounced } from '../editorial/kit';
import { categoriesApi, fmtInt, STATUS_TONE, type Finding, type Rule } from './api';
import { ROOT, useMeta } from './parts';
import SqlInfo from '../components/SqlInfo';
import { kaynakOf } from '../components/kaynakOf';

/** Tutarsızlıklar: deterministik kurallar (ekrandan açılıp kapanır), kitap listesi, toplu «öneriyi uygula». */

function detailText(f: Finding): string {
  const d = f.detail as Record<string, unknown>;
  if (typeof d.neden === 'string') return d.neden;
  if (f.rule === 'hedef_kitle_web') return `Hedef kitle ${d.hedefKitle}, web kategorisi «${d.webKategori}»`;
  if (f.rule === 'tsoft_kategori') return `Sitede «${d.tsoftAd ?? d.tsoft}», düğüm ${d.dugum}`;
  return '';
}

export default function Findings() {
  const qc = useQueryClient();
  const meta = useMeta();
  const me = meta.data?.me;
  const [params, setParams] = useSearchParams();
  const [q, setQ] = useState(params.get('q') ?? '');
  const dq = useDebounced(q, 300);
  const f = { rule: params.get('kural') ?? '', status: params.get('durum') ?? 'acik', owner: params.get('sahip') === 'ben' ? 'me' : '', q: dq, page: Number(params.get('sayfa')) || 0 };
  const list = useQuery({ queryKey: ['categories', 'findings', f], queryFn: () => categoriesApi.findings(f), enabled: ENGINE_ENABLED, placeholderData: keepPreviousData });
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const set = useCallback((next: Record<string, string | null>) => {
    const p = new URLSearchParams(params);
    for (const [k, v] of Object.entries(next)) {
      if (v) p.set(k, v);
      else p.delete(k);
    }
    if (!('sayfa' in next)) p.delete('sayfa');
    setParams(p, { replace: true });
    setPicked(new Set());
  }, [params, setParams]);

  const apply = useMutation({
    mutationFn: () => categoriesApi.applyFindings([...picked]),
    onSuccess: (r) => {
      setPicked(new Set());
      qc.invalidateQueries({ queryKey: ['categories'] });
      toast.success(`${r.applied.length} öneri kabul edildi${r.skipped.length ? `, ${r.skipped.length} atlandı` : ''}.`, {
        description: r.skipped.length ? [...new Set(r.skipped.map((s) => s.reason))].join(' ') : undefined,
      });
    },
    onError: (e) => toast.error(errText(e, 'Uygulanamadı.') ?? ''),
  });
  const status = useMutation({
    mutationFn: ({ id, s }: { id: string; s: 'acik' | 'yoksay' }) => categoriesApi.findingStatus(id, s),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['categories'] }),
    onError: (e) => toast.error(errText(e, 'Kaydedilemedi.') ?? ''),
  });
  const rule = useMutation({
    mutationFn: ({ key, body }: { key: string; body: { enabled?: boolean; params?: Record<string, number> } }) => categoriesApi.updateRule(key, body),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['categories'] }); toast.success('Kural güncellendi; bulgular yeniden hesaplandı.'); },
    onError: (e) => toast.error(errText(e, 'Kural güncellenemedi.') ?? ''),
  });

  const items = list.data?.items ?? [];
  const allPicked = items.length > 0 && items.every((x) => picked.has(x.id));
  const rules: Rule[] = list.data?.rules ?? [];
  const canAct = !!me?.canDecide;
  const openBy = list.data?.openByRule ?? {};
  const ruleOptions = useMemo(() => rules.map((r) => ({ ...r, open: openBy[r.key] ?? 0 })), [rules, openBy]);

  return (
    <div className="flex flex-col gap-3 lg:gap-4">
      <Panel>
        <p className="mb-2 text-[12px] leading-snug text-canvas-muted">
          CRM'deki sınıflamaların birbiriyle çeliştiği ya da eksik kaldığı kitaplar; aşağıdaki kurallarla bulunur. Kitaba dokunup profilini düzeltin
          ya da Zeki AI'ın emin olduğu öneriyi toplu uygulayın.
        </p>
        <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-[1.4fr_1.4fr_1fr_1fr]">
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Ara</span>
            <input className={field} value={q} placeholder="Kitap adı ya da stok kodu" onChange={(e) => { setQ(e.target.value); set({ q: e.target.value || null }); }} />
          </label>
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Kural</span>
            <select className={field} value={f.rule} onChange={(e) => set({ kural: e.target.value || null })}>
              <option value="">Hepsi</option>
              {ruleOptions.map((r) => <option key={r.key} value={r.key}>{r.label} ({fmtInt(r.open)})</option>)}
            </select>
          </label>
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Durum</span>
            <select className={field} value={f.status} onChange={(e) => set({ durum: e.target.value === 'acik' ? null : e.target.value })}>
              <option value="acik">Açık</option>
              <option value="yoksay">Yok sayılan</option>
              <option value="duzeltildi">Kaynağında düzelen</option>
            </select>
          </label>
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Kimin</span>
            <select className={field} value={params.get('sahip') ?? ''} onChange={(e) => set({ sahip: e.target.value || null })}>
              <option value="">Bütün katalog</option>
              <option value="ben">Benim kitaplarım</option>
            </select>
          </label>
        </div>
        {canAct && f.status === 'acik' && (
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <label className="inline-flex min-h-11 items-center gap-2 text-[12.5px] font-bold">
              <input type="checkbox" checked={allPicked} onChange={(e) => setPicked(e.target.checked ? new Set(items.map((x) => x.id)) : new Set())} />
              Bu sayfadakilerin tümü
            </label>
            <button type="button" className={btnPrimary} disabled={!picked.size || apply.isPending} onClick={() => apply.mutate()}>
              <Check aria-hidden className="h-4 w-4" /> Öneriyi uygula{picked.size ? ` (${picked.size})` : ''}
            </button>
            <span className="text-[11.5px] text-canvas-muted">Seçili kitapların bu alandaki bekleyen ve emin Zeki AI önerisi kabul edilir; önerisi olmayan atlanır.</span>
          </div>
        )}
        {list.error && <div className="mt-3"><Note tone="err">{errText(list.error, 'Liste açılamadı.')}</Note></div>}
        <ul className="mt-3 flex flex-col gap-1.5">
          {items.map((x) => (
            <li key={x.id} className="grid gap-1.5 rounded-2xl border border-slate-100 bg-white/80 px-3 py-2.5 sm:grid-cols-[auto_minmax(0,2fr)_minmax(0,2fr)_auto] sm:items-center sm:gap-3">
              {canAct && f.status === 'acik' ? (
                <input type="checkbox" aria-label={`${x.name} seç`} className="h-5 w-5" checked={picked.has(x.id)}
                  onChange={(e) => { const n = new Set(picked); if (e.target.checked) n.add(x.id); else n.delete(x.id); setPicked(n); }} />
              ) : <span className="hidden sm:block" />}
              <div className="min-w-0">
                <Link to={`${ROOT}/kitap/${x.bookId}`} className="block truncate text-[13px] font-extrabold hover:text-canvas-violet">{x.name ?? '—'}</Link>
                <div className="truncate text-[11.5px] font-semibold text-canvas-muted">{x.stockCode} · {x.brand ?? '—'} · {fmtInt(x.priority ?? 0)} adet</div>
              </div>
              <div className="min-w-0 text-[12px]">
                <div className="font-bold">{x.ruleLabel}</div>
                {detailText(x) && <div className="text-canvas-muted">{detailText(x)}</div>}
              </div>
              <div className="flex items-center gap-1.5">
                {x.profileStatus && <Pill tone={STATUS_TONE[x.profileStatus]}>{meta.data?.profileStatus[x.profileStatus] ?? x.profileStatus}</Pill>}
                {canAct && x.status === 'acik' && (
                  <button type="button" className={`${btnGhost} !min-h-9 !px-2`} onClick={() => status.mutate({ id: x.id, s: 'yoksay' })} title="Yok say">
                    <EyeOff aria-hidden className="h-3.5 w-3.5" /><span className="sr-only">Yok say</span>
                  </button>
                )}
                {canAct && x.status === 'yoksay' && (
                  <button type="button" className={`${btnGhost} !min-h-9 !px-2`} onClick={() => status.mutate({ id: x.id, s: 'acik' })} title="Yeniden aç">
                    <RotateCcw aria-hidden className="h-3.5 w-3.5" /><span className="sr-only">Yeniden aç</span>
                  </button>
                )}
              </div>
            </li>
          ))}
        </ul>
        {list.data && !list.data.total && !list.isFetching && <p className="mt-3 text-[12.5px] text-canvas-muted">{f.status === 'acik' && !f.rule && !q ? 'Açık tutarsızlık yok.' : 'Bu süzgeçte bulgu yok; kural, durum ya da aramayı değiştirin.'}</p>}
        <Pager page={f.page} pageSize={list.data?.pageSize ?? 50} total={list.data?.total ?? 0} shown={items.length}
          loading={list.isLoading} fetching={list.isFetching} onPage={(p) => set({ sayfa: p ? String(p) : null })} />
      </Panel>

      <Panel>
        <h2 className="flex items-center gap-1 text-[15px] font-extrabold">
          Kurallar
          <SqlInfo k={kaynakOf(list.data)} alan="_hepsi" label="Kural başına açık bulgu ve öncelik" />
        </h2>
        <p className="mt-0.5 text-[12px] text-canvas-muted">Kurallar yalnız liste üretir; CRM'e ya da siteye dokunmaz. Kapatılan kuralın açık bulguları kapanır.</p>
        <ul className="mt-2 flex flex-col divide-y divide-slate-100">
          {rules.map((r) => (
            <li key={r.key} className="flex flex-col gap-1.5 py-2 sm:flex-row sm:items-center sm:justify-between">
              <div className="min-w-0">
                <div className="text-[12.5px] font-extrabold">{r.label} <span className="font-mono font-semibold text-canvas-muted">({fmtInt(openBy[r.key] ?? 0)})</span></div>
                <div className="text-[11.5px] leading-snug text-canvas-muted">{r.help}</div>
              </div>
              <div className="flex shrink-0 items-center gap-2">
                {Object.entries(r.params).map(([k, v]) => (
                  <label key={k} className="flex items-center gap-1 text-[11.5px] font-bold">
                    {k === 'yetiskin_yas' ? 'Yetişkin yaşı' : k}
                    <input type="number" className={`${field} !w-20`} defaultValue={v} disabled={!me?.canEditTree}
                      onBlur={(e) => { const n = Number(e.target.value); if (Number.isFinite(n) && n !== v) rule.mutate({ key: r.key, body: { params: { [k]: n } } }); }} />
                  </label>
                ))}
                <Pill tone={r.enabled ? 'ok' : 'muted'}>{r.enabled ? 'Açık' : 'Kapalı'}</Pill>
                <button type="button" className={btnGhost} disabled={!me?.canEditTree || rule.isPending} onClick={() => rule.mutate({ key: r.key, body: { enabled: !r.enabled } })}>
                  {r.enabled ? 'Kuralı kapat' : 'Kuralı aç'}
                </button>
              </div>
            </li>
          ))}
        </ul>
      </Panel>
    </div>
  );
}
