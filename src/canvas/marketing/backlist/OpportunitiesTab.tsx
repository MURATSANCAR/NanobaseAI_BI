import { useEffect, useMemo, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Download, FileSpreadsheet, Loader2, Search, SlidersHorizontal } from 'lucide-react';
import { ENGINE_ENABLED, prefsApi } from '../../engine';
import { Note, Pill, TableWrap, btnGhost, btnPrimary, errText, field, label as labelCls, td, th } from '../../admin/ui';
import { Kpi, KpiRow, Pager, Panel, useDebounced } from '../../editorial/kit';
import { fmtMoney, fmtShortDay } from '../api';
import { Block } from '../parts';
import { M46_TONE, blApi, fmtChange, fmtN, runout, weightsText, type BlMeta, type ComponentKey, type ListParams, type Row, type Weights } from './api';
import OpportunityPanel from './OpportunityPanel';
import SqlInfo, { InfoLabel } from '../../components/SqlInfo';
import type { Kaynaklar } from '../../components/sqlInfo';
import { xlsxUrl } from '../../components/excel';

/** Fırsatlar: bütün backlist (tavan yok, sayfalı), bileşen çubukları, ağırlık kaydırıcıları, seçip aktivasyon planı.
 *  Süzgeçler adres çubuğunda; kişisel ağırlık kişinin tercihinde (sunucuda), ekip varsayılanı ayrı yetkiyle. */

const PREF = 'backlist:weights';
const M46_FILTER = [['', 'Hepsi'], ['acik', 'Açık sapma uyarısı'], ['sapma', 'Sapma'], ['izle', 'İzle'], ['iyi', 'İyi'], ['baslamadi', 'Başlamadı'], ['yok', 'Hedef yok']] as const;

export default function OpportunitiesTab({ meta }: { meta: BlMeta }) {
  const qc = useQueryClient();
  const nav = useNavigate();
  const [params, setParams] = useSearchParams();
  const keys = meta.components.map((c) => c.key);
  const get = (k: string) => params.get(k) ?? '';
  const [q, setQ] = useState(get('q'));
  const dq = useDebounced(q, 300);
  const [page, setPage] = useState(0);
  const [open, setOpen] = useState<string | null>(null);
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const [showWeights, setShowWeights] = useState(false);

  const team = useMemo(() => ({ ...meta.defaultWeights, ...(meta.teamWeights ?? {}) }) as Weights, [meta]);
  const pref = useQuery({ queryKey: ['bl', 'pref'], queryFn: () => prefsApi.get<Weights>(PREF), enabled: ENGINE_ENABLED, staleTime: Infinity });
  const [weights, setWeights] = useState<Weights>(team);
  useEffect(() => {
    if (pref.data?.value) setWeights({ ...team, ...pref.data.value });
  }, [pref.data, team]);
  const debounced = useDebounced(weights, 400);
  // Hepsi sıfır ağırlık geçersiz: liste son geçerli (ekip) ağırlıkla kalır, uyarı kutuda.
  const dw = Object.values(debounced).some((v) => v > 0) ? debounced : team;
  const savePref = useMutation({ mutationFn: (w: Weights) => prefsApi.put(PREF, w) });
  useEffect(() => {
    if (pref.isFetched && JSON.stringify(dw) !== JSON.stringify(pref.data?.value ?? team)) savePref.mutate(dw);
  }, [dw]); // eslint-disable-line react-hooks/exhaustive-deps

  const update = (next: Record<string, string | null>) => {
    const p = new URLSearchParams(params);
    for (const [k, v] of Object.entries(next)) {
      if (v) p.set(k, v);
      else p.delete(k);
    }
    setParams(p, { replace: true });
    setPage(0);
  };
  useEffect(() => {
    if (get('q') !== dq) update({ q: dq || null });
  }, [dq]); // eslint-disable-line react-hooks/exhaustive-deps

  const lp: ListParams = {
    sirala: get('sirala') || 'oncelik', yayinevi: get('yayinevi'), kitaplik: get('kitaplik'), hedef_kitle: get('hedef'),
    m46: get('m46'), stokta: get('stokta') === '1', ozel_gun: get('gun'), plan: get('plan'), q: dq, agirlik: weightsText(dw, keys),
  };
  const list = useQuery({
    queryKey: ['bl', 'list', lp, page],
    queryFn: () => blApi.list({ ...lp, page }),
    enabled: ENGINE_ENABLED && pref.isFetched,
    placeholderData: keepPreviousData,
  });

  const create = useMutation({
    mutationFn: (codes: string[]) => blApi.createPlan(codes.map((stokKodu) => ({ stokKodu }))),
    onSuccess: (plan) => {
      qc.invalidateQueries({ queryKey: ['bl'] });
      toast.success('Aktivasyon planı taslağı açıldı.');
      nav(`/pazarlama/plan/${encodeURIComponent(plan.id)}`);
    },
    onError: (e) => toast.error(errText(e, 'Plan açılamadı.') ?? ''),
  });
  const saveTeam = useMutation({
    mutationFn: () => blApi.saveTeamWeights(weights),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['bl', 'meta'] });
      toast.success('Ekip varsayılanı kaydedildi.');
    },
    onError: (e) => toast.error(errText(e, 'Kaydedilemedi.') ?? ''),
  });

  const d = list.data;
  const me = meta.me;
  const toggle = (code: string) =>
    setPicked((s) => {
      const n = new Set(s);
      if (n.has(code)) n.delete(code);
      else n.add(code);
      return n;
    });

  return (
    <div className="flex flex-col gap-3 lg:gap-4">
      {d && (
        <KpiRow>
          <Kpi label="Backlist" value={fmtN(d.hepsi)} help={d.total === d.hepsi ? 'Süzgeç yok: bütün liste' : `Süzgeçle ${fmtN(d.total)} kitap`}
            active={!get('m46') && !get('gun') && !get('stokta')} onClick={() => update({ m46: null, gun: null, stokta: null })}
            info={<SqlInfo k={d.kaynaklar} alan="hepsi" label="Backlist" />} />
          <Kpi label="Açık sapma" value={fmtN(d.kpi.sapmaAcik)} help="Bu yılın satış hedefinde uyarısı açık" active={get('m46') === 'acik'}
            onClick={() => update({ m46: get('m46') === 'acik' ? null : 'acik' })}
            info={<SqlInfo k={d.kaynaklar} alan="kpi" label="Açık sapma" />} />
          <Kpi label="Yaklaşan özel gün" value={fmtN(d.kpi.yakinGun)} help={`Önümüzdeki ${meta.settings.agendaWeeks} haftada bağlı özel günü olan`}
            active={get('gun') === 'yakin'} onClick={() => update({ gun: get('gun') === 'yakin' ? null : 'yakin' })}
            info={<SqlInfo k={d.kaynaklar} alan="kpi" label="Yaklaşan özel gün" />} />
          <Kpi label="Stokta" value={fmtN(d.kpi.stokta)} help={`Aktivasyon planında: ${fmtN(d.kpi.planli)}`} active={get('stokta') === '1'}
            onClick={() => update({ stokta: get('stokta') === '1' ? null : '1' })}
            info={<SqlInfo k={d.kaynaklar} alan="kpi" label="Stokta" />} />
        </KpiRow>
      )}

      <Panel>
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-4 xl:grid-cols-8">
          <label className="flex flex-col gap-1 sm:col-span-2">
            <span className={labelCls}>Ara</span>
            <span className="relative">
              <Search aria-hidden className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-canvas-muted" />
              <input className={`${field} pl-9`} value={q} onChange={(e) => setQ(e.target.value)} placeholder="Kitap, yazar, stok kodu" />
            </span>
          </label>
          <Select label="Yayınevi" value={get('yayinevi')} onChange={(v) => update({ yayinevi: v })} options={d?.facets.yayinevleri ?? []} />
          <Select label="Kitaplık" value={get('kitaplik')} onChange={(v) => update({ kitaplik: v })} options={d?.facets.kitapliklar ?? []} />
          <Select label="Hedef kitle" value={get('hedef')} onChange={(v) => update({ hedef: v })} options={d?.facets.hedefKitleler ?? []} />
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Hedef durumu</span>
            <select className={field} value={get('m46')} onChange={(e) => update({ m46: e.target.value || null })}>
              {M46_FILTER.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </select>
          </label>
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Özel gün</span>
            <select className={field} value={get('gun')} onChange={(e) => update({ gun: e.target.value || null })}>
              <option value="">Hepsi</option>
              <option value="yakin">Yaklaşanı olan</option>
              {(d?.gunler ?? []).map((g) => <option key={g.id} value={g.id}>{g.ad} · {fmtShortDay(g.baslangic)} ({g.kitap})</option>)}
            </select>
          </label>
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Sırala</span>
            <select className={field} value={get('sirala') || 'oncelik'} onChange={(e) => update({ sirala: e.target.value })}>
              {Object.entries(meta.sorts).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
          </label>
        </div>
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <label className="inline-flex min-h-11 items-center gap-2 text-[12.5px] font-semibold sm:min-h-9">
            <input type="checkbox" className="h-4 w-4" checked={get('stokta') === '1'} onChange={(e) => update({ stokta: e.target.checked ? '1' : null })} />
            Yalnız stokta olanlar
          </label>
          <select aria-label="Aktivasyon planı" className={`${field} w-auto`} value={get('plan')} onChange={(e) => update({ plan: e.target.value || null })}>
            <option value="">Planlı ve plansız</option>
            <option value="yok">Aktivasyon planı olmayan</option>
            <option value="var">Aktivasyon planında</option>
          </select>
          <button type="button" className={btnGhost} aria-expanded={showWeights} onClick={() => setShowWeights((v) => !v)}>
            <SlidersHorizontal aria-hidden className="h-4 w-4" />Ağırlıklar
          </button>
          {me.canExport && (
            <>
              <a className={btnGhost} href={blApi.csvUrl({ ...lp, q: dq })} download><Download aria-hidden className="h-4 w-4" />CSV</a>
              <a className={btnGhost} href={xlsxUrl(blApi.csvUrl({ ...lp, q: dq }))} download><FileSpreadsheet aria-hidden className="h-4 w-4" />Excel</a>
            </>
          )}
        </div>
        {showWeights && (
          <WeightsBox meta={meta} weights={weights} team={team} onChange={setWeights} onSaveTeam={() => saveTeam.mutate()} saving={saveTeam.isPending} />
        )}
      </Panel>

      {picked.size > 0 && me.canWrite && (
        <div className="sticky top-0 z-10 flex flex-wrap items-center gap-2 rounded-2xl bg-canvas-violet/10 px-3 py-2 text-[12.5px] font-semibold">
          <span>{picked.size} kitap seçili</span>
          <button type="button" className={btnPrimary} disabled={create.isPending} onClick={() => create.mutate([...picked])}>
            {create.isPending && <Loader2 aria-hidden className="h-4 w-4 animate-spin" />}Aktivasyon planı oluştur
          </button>
          <button type="button" className={btnGhost} onClick={() => setPicked(new Set())}>Seçimi temizle</button>
        </div>
      )}

      <Block title="Fırsat listesi" help={meta.formula} info={<SqlInfo k={d?.kaynaklar} alan="items[]" label="Fırsat listesi" />}>
        {list.error && <Note tone="err">{errText(list.error, 'Liste açılamadı.')}</Note>}
        {d && !d.items.length && <Note tone="info">Süzgece uyan kitap yok.</Note>}
        {d && d.items.length > 0 && (
          <Rows rows={d.items} meta={meta} picked={picked} onPick={toggle} onOpen={setOpen} k={d.kaynaklar} />
        )}
        {d && (
          <Pager page={page} pageSize={d.pageSize} total={d.total} shown={d.items.length} loading={list.isLoading} fetching={list.isFetching} onPage={setPage} />
        )}
      </Block>

      <OpportunityPanel stok={open} meta={meta} agirlik={weightsText(dw, keys)} onClose={() => setOpen(null)} />
    </div>
  );
}

function Select({ label, value, onChange, options }: { label: string; value: string; onChange: (v: string | null) => void; options: string[] }) {
  return (
    <label className="flex flex-col gap-1">
      <span className={labelCls}>{label}</span>
      <select className={field} value={value} onChange={(e) => onChange(e.target.value || null)}>
        <option value="">Hepsi</option>
        {options.map((o) => <option key={o} value={o}>{o}</option>)}
      </select>
    </label>
  );
}

function WeightsBox({ meta, weights, team, onChange, onSaveTeam, saving }: {
  meta: BlMeta; weights: Weights; team: Weights; onChange: (w: Weights) => void; onSaveTeam: () => void; saving: boolean;
}) {
  const zero = Object.values(weights).every((v) => !v);
  return (
    <div className="mt-3 rounded-2xl border border-slate-100 bg-white/80 p-3">
      <p className="text-[11.5px] leading-snug text-canvas-muted">
        Ağırlıklar yalnız sizin görünümünüzü değiştirir ve tercihinize kaydedilir.
        {meta.teamWeightsBy ? ` Ekip varsayılanını ${meta.teamWeightsBy} kaydetti.` : ' Ekip varsayılanı eşit ağırlık.'}
      </p>
      <div className="mt-2 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-5">
        {meta.components.map((c) => (
          <label key={c.key} className="flex flex-col gap-1" title={c.aciklama}>
            <span className="flex items-center justify-between text-[12px] font-bold">
              {c.ad}<span className="font-mono tabular-nums text-canvas-muted">{weights[c.key].toLocaleString('tr-TR')}</span>
            </span>
            <input type="range" min={0} max={3} step={0.5} value={weights[c.key]} className="h-11 w-full accent-violet-700 sm:h-6"
              onChange={(e) => onChange({ ...weights, [c.key]: Number(e.target.value) } as Weights)} aria-label={`${c.ad} ağırlığı`} />
            <span className="text-[11px] leading-snug text-canvas-muted">{c.aciklama}</span>
          </label>
        ))}
      </div>
      {zero && <p className="mt-2 text-[11.5px] font-semibold text-red-700">En az bir ağırlık sıfırdan büyük olmalı.</p>}
      <div className="mt-2 flex flex-wrap gap-2">
        <button type="button" className={btnGhost} onClick={() => onChange({ ...meta.defaultWeights })}>Eşit ağırlık</button>
        <button type="button" className={btnGhost} onClick={() => onChange({ ...team })}>Ekip varsayılanı</button>
        {meta.me.canSetTeamWeights && (
          <button type="button" className={btnPrimary} disabled={saving || zero} onClick={onSaveTeam}>Ekip varsayılanı yap</button>
        )}
      </div>
    </div>
  );
}

/** Bileşen yüzdeliği: beş ince çubuk (0–100). Değeri olmayan bileşen kesikli çerçeve. */
export function ComponentBars({ row, meta }: { row: Row; meta: BlMeta }) {
  return (
    <div className="flex items-end gap-1" role="img"
      aria-label={meta.components.map((c) => `${c.ad} ${row.bilesen[c.key].yuzdelik ?? 'yok'}`).join(', ')}>
      {meta.components.map((c) => {
        const p = row.bilesen[c.key as ComponentKey].yuzdelik;
        return (
          <div key={c.key} title={`${c.ad}: ${p === null ? 'değer yok' : `yüzdelik ${Math.round(p)}`}`}
            className={`relative h-7 w-2.5 overflow-hidden rounded-sm ${p === null ? 'border border-dashed border-slate-300' : 'bg-slate-100'}`}>
            {p !== null && <div className="absolute inset-x-0 bottom-0 rounded-sm bg-canvas-violet" style={{ height: `${Math.max(4, p)}%` }} />}
          </div>
        );
      })}
    </div>
  );
}

function Rows({ rows, meta, picked, onPick, onOpen, k }: {
  rows: Row[]; meta: BlMeta; picked: Set<string>; onPick: (c: string) => void; onOpen: (c: string) => void; k?: Kaynaklar;
}) {
  const me = meta.me;
  const tag = (r: Row) => (
    <div className="flex flex-wrap gap-1">
      {r.m46.sapmaAcik && <Pill tone="err">Açık sapma</Pill>}
      {r.m46.durum && !r.m46.sapmaAcik && <Pill tone={M46_TONE[r.m46.durum] ?? 'muted'}>{r.m46.durumAdi ?? r.m46.durum}</Pill>}
      {(r.yaklasanGunler ?? []).slice(0, 2).map((g) => <Pill key={g.id} tone="violet">{g.ad} · {fmtShortDay(g.baslangic)}</Pill>)}
      {(r.yaklasanGunler?.length ?? 0) > 2 && <Pill tone="violet">+{(r.yaklasanGunler?.length ?? 0) - 2} gün</Pill>}
      {r.planlar.length > 0 && <Pill tone="ok">{r.planlar[0].durumAdi}</Pill>}
      {!r.dijital.ekitapStokKodu && !r.dijital.ekitapIsbn && <Pill tone="muted">e-kitap yok</Pill>}
    </div>
  );
  const check = (r: Row) =>
    me.canWrite ? (
      <input type="checkbox" className="h-5 w-5" checked={picked.has(r.stokKodu)} onChange={() => onPick(r.stokKodu)}
        aria-label={`${r.ad ?? r.stokKodu} seç`} disabled={r.stok !== null && r.stok <= 0} />
    ) : null;

  return (
    <>
      <ul className="flex flex-col gap-2 sm:hidden">
        {rows.map((r) => (
          <li key={r.stokKodu} className="rounded-2xl border border-slate-100 bg-white/85 p-3">
            <div className="flex items-start gap-2">
              {check(r)}
              <button type="button" className="min-w-0 flex-1 text-left" onClick={() => onOpen(r.stokKodu)}>
                <div className="break-words text-[14px] font-extrabold leading-snug">{r.ad ?? r.stokKodu}</div>
                <div className="mt-0.5 text-[11.5px] text-canvas-muted">{[r.yazar, r.kitaplik].filter(Boolean).join(' · ') || '—'}</div>
              </button>
              <div className="text-right">
                <div className="font-mono text-[20px] font-bold tabular-nums leading-none">{r.endeks === null ? '—' : Math.round(r.endeks)}</div>
                <div className="mt-1"><ComponentBars row={r} meta={meta} /></div>
              </div>
            </div>
            <div className="mt-2 text-[11.5px] text-canvas-muted">
              12 ay {fmtN(r.adetSon12)} adet ({fmtChange(r.degisim)}) · stok {fmtN(r.stok)} · {runout(r)}
              {me.canSeeBudget && r.ciroSon12 !== null ? ` · ${fmtMoney(r.ciroSon12)}` : ''}
              <SqlInfo k={k} alan="items[]" label="Kitabın rakamları" className="ml-0.5" />
            </div>
            <div className="mt-1.5">{tag(r)}</div>
          </li>
        ))}
      </ul>
      <div className="hidden sm:block">
        <TableWrap>
          <thead>
            <tr className="border-b border-slate-100">
              {me.canWrite && <th className={th}><span className="sr-only">Seç</span></th>}
              <th className={th}>Kitap</th>
              <th className={`${th} text-right`}><InfoLabel k={k} alan="items[].endeks">Endeks</InfoLabel></th>
              <th className={th}><InfoLabel k={k} alan="items[].bilesen">Bileşenler</InfoLabel></th>
              <th className={`${th} text-right`}><InfoLabel k={k} alan="items[]">Son 12 ay</InfoLabel></th>
              <th className={`${th} text-right`}><InfoLabel k={k} alan="items[]">Değişim</InfoLabel></th>
              <th className={`${th} text-right`}><InfoLabel k={k} alan="items[]">Stok</InfoLabel></th>
              <th className={`${th} text-right`}><InfoLabel k={k} alan="items[]">Tükenme</InfoLabel></th>
              <th className={`${th} text-right`}><InfoLabel k={k} alan="items[]">Tahmin 12 ay</InfoLabel></th>
              {me.canSeeBudget && <th className={`${th} text-right`}><InfoLabel k={k} alan="items[]">Marj</InfoLabel></th>}
              <th className={th}>Durum</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.stokKodu} className="border-b border-slate-50 align-top hover:bg-white/60">
                {me.canWrite && <td className={td}>{check(r)}</td>}
                <td className={`${td} max-w-[320px]`}>
                  <button type="button" className="text-left font-extrabold leading-snug text-canvas-ink hover:underline" onClick={() => onOpen(r.stokKodu)}>
                    {r.ad ?? r.stokKodu}
                  </button>
                  <div className="text-[11.5px] text-canvas-muted">{[r.stokKodu, r.yazar, r.yayinevi, r.kitaplik, r.ilkYayin?.slice(0, 4)].filter(Boolean).join(' · ')}</div>
                </td>
                <td className={`${td} text-right font-mono text-[15px] font-bold tabular-nums`}>{r.endeks === null ? '—' : Math.round(r.endeks)}</td>
                <td className={td}><ComponentBars row={r} meta={meta} /></td>
                <td className={`${td} text-right font-mono tabular-nums`}>{fmtN(r.adetSon12)}</td>
                <td className={`${td} text-right font-mono tabular-nums ${r.degisim !== null && r.degisim < 0 ? 'text-red-700' : ''}`}>{fmtChange(r.degisim)}</td>
                <td className={`${td} text-right font-mono tabular-nums`}>{fmtN(r.stok)}</td>
                <td className={`${td} text-right tabular-nums`}>{runout(r)}</td>
                <td className={`${td} text-right font-mono tabular-nums`}>{fmtN(r.tahmin12)}</td>
                {me.canSeeBudget && <td className={`${td} text-right font-mono tabular-nums`}>{r.marj === null ? '—' : `%${Math.round(r.marj * 100)}`}</td>}
                <td className={td}>{tag(r)}</td>
              </tr>
            ))}
          </tbody>
        </TableWrap>
      </div>
    </>
  );
}
