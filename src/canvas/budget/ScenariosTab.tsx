import { useEffect, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Calculator, Loader2 } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import { Loading, Note, Pill, TableWrap, btnGhost, btnPrimary, errText, td, th } from '../admin/ui';
import { Panel } from '../editorial/kit';
import { STATUS_TONE, budgetApi, fmtDay, fmtMoney, fmtPct, fmtShort, type Plan } from './api';
import { ParamsForm, fromText, toText, type ParamText } from './GenerateSheet';
import SqlInfo, { InfoLabel } from '../components/SqlInfo';

function diff(v: number, base: number | undefined) {
  if (!base) return '';
  const d = v / base - 1;
  return `${d >= 0 ? '+' : ''}${fmtPct(d)}`;
}

export default function ScenariosTab({ year, current, canEdit, onOpen, onGenerate }: {
  year: number; current: Plan; canEdit: boolean; onOpen: (id: string) => void; onGenerate: () => void;
}) {
  const qc = useQueryClient();
  const cmp = useQuery({ queryKey: ['budget', 'compare', year], queryFn: () => budgetApi.compare(year), enabled: ENGINE_ENABLED });
  const history = useQuery({ queryKey: ['budget', 'plans', year], queryFn: () => budgetApi.plans(year), enabled: ENGINE_ENABLED });
  const [text, setText] = useState<ParamText>(() => toText(current.params));
  useEffect(() => setText(toText(current.params)), [current.id, current.params]);
  const recompute = useMutation({
    mutationFn: () => budgetApi.recompute(current.id, fromText(text)),
    onSuccess: () => {
      toast.success('Öneri yeniden hesaplandı; elle düzeltilen satırlar korundu.');
      qc.invalidateQueries({ queryKey: ['budget'] });
    },
    onError: (e) => toast.error(errText(e, 'Yeniden hesaplanamadı.') ?? ''),
  });
  const base = cmp.data?.taban;
  const archived = (history.data?.items ?? []).filter((p) => p.status === 'arsiv');

  return (
    <div className="flex flex-col gap-3 lg:gap-4">
      <Panel>
        <div className="mb-2 flex flex-wrap items-end justify-between gap-2">
          <div>
            <h3 className="flex items-center gap-1.5 text-[15px] font-extrabold">{year} senaryoları<SqlInfo k={cmp.data?.kaynaklar} alan="items[].totals" label={`${year} senaryolarının toplamları`} /></h3>
            <p className="text-[12px] text-canvas-muted">
              {base ? <>Taban dönem ({base.pencere}): net ciro {fmtShort(base.ciro)} ₺, net adet {fmtShort(base.adet)}, gider {fmtShort(base.gider)} ₺. Yüzdeler tabana göre.<SqlInfo k={cmp.data?.kaynaklar} alan="taban" label="Taban dönemi" className="ml-1" /></> : 'Taban hesaplanıyor…'}
            </p>
          </div>
          {canEdit && (
            <button type="button" className={btnGhost} onClick={onGenerate}>
              <Calculator aria-hidden className="h-4 w-4" />
              Yeni öneri
            </button>
          )}
        </div>
        {cmp.isLoading ? <Loading /> : cmp.error ? <Note tone="err">{errText(cmp.error, 'Karşılaştırma okunamadı.')}</Note> : (
          <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-2 xl:grid-cols-3">
            {(cmp.data?.items ?? []).map((p) => (
              <div key={p.id} className="relative">
              <button type="button" onClick={() => onOpen(p.id)}
                className={`flex h-full w-full flex-col gap-2 rounded-2xl border bg-white/80 p-3.5 pb-9 text-left transition-transform duration-150 ease-out active:scale-[0.98] ${p.id === current.id ? 'border-canvas-violet ring-2 ring-canvas-violet/30' : 'border-slate-100'}`}>
                <div className="flex items-center justify-between gap-2">
                  <span className="text-[14px] font-extrabold">{p.scenarioLabel} <span className="font-semibold text-canvas-muted">· sürüm {p.version}</span></span>
                  <Pill tone={STATUS_TONE[p.status]}>{p.statusLabel}</Pill>
                </div>
                <dl className="grid grid-cols-[1fr_auto_auto] gap-x-2 gap-y-1 text-[12px]">
                  <dt className="text-canvas-muted">Net ciro</dt>
                  <dd className="text-right font-mono tabular-nums">{fmtShort(p.totals.ciro)} ₺</dd>
                  <dd className="text-right font-mono text-[11px] tabular-nums text-canvas-muted">{diff(p.totals.ciro, base?.ciro)}</dd>
                  <dt className="text-canvas-muted">Net adet</dt>
                  <dd className="text-right font-mono tabular-nums">{fmtShort(p.totals.adet)}</dd>
                  <dd className="text-right font-mono text-[11px] tabular-nums text-canvas-muted">{diff(p.totals.adet, base?.adet)}</dd>
                  <dt className="text-canvas-muted">Brüt marj</dt>
                  <dd className="text-right font-mono tabular-nums">{fmtPct(p.totals.marj)}</dd>
                  <dd />
                  <dt className="text-canvas-muted">Gider bütçesi</dt>
                  <dd className="text-right font-mono tabular-nums">{fmtShort(p.totals.gider)} ₺</dd>
                  <dd className="text-right font-mono text-[11px] tabular-nums text-canvas-muted">{diff(p.totals.gider, base?.gider)}</dd>
                </dl>
                {p.basis.tahmin?.bant && (
                  <div className="rounded-xl bg-violet-50/70 px-2.5 py-2 text-[11.5px] leading-snug">
                    <div className="flex flex-wrap items-center gap-1.5 font-bold">
                      ZEKİ AI tahmini · 12 ay
                      <span className="rounded bg-white/80 px-1 text-[10px] font-extrabold uppercase tracking-wide text-canvas-violet">tahmin</span>
                    </div>
                    {p.basis.tahmin.bant.aralik ? (
                      <div className="mt-0.5 font-mono tabular-nums">
                        {fmtShort(p.basis.tahmin.bant.p10)} – <b>{fmtShort(p.basis.tahmin.bant.p50)}</b> – {fmtShort(p.basis.tahmin.bant.p90)} adet
                      </div>
                    ) : (
                      <div className="mt-0.5 font-mono tabular-nums">{fmtShort(p.basis.tahmin.bant.p50)} adet <span className="font-sans text-canvas-muted">(aralık yok)</span></div>
                    )}
                    <div className="text-canvas-muted">
                      {p.basis.tahmin.bant.kitap} backlist kitabı · muhafazakâr – temel – iyimser
                      {p.basis.tahmin.kantil ? ` · bu senaryonun tabanı ${p.basis.tahmin.kantil === 'p10' ? 'alt sınır' : p.basis.tahmin.kantil === 'p90' ? 'üst sınır' : 'beklenen değer'}` : ''}
                    </div>
                  </div>
                )}
                <span className="text-[11px] text-canvas-muted">{p.createdBy}, {fmtDay(p.createdAt)}</span>
              </button>
              <div className="pointer-events-none absolute inset-x-3.5 bottom-3 flex items-center justify-between gap-2">
                <span className="flex min-w-0 items-center gap-0.5 text-[11px] text-canvas-muted">
                  <span className="truncate">Hacim {fmtPct(p.params.hacim?.[p.scenario] ?? null)} · fiyat {fmtPct(p.params.fiyat)}</span>
                  <span className="pointer-events-auto"><SqlInfo k={cmp.data?.kaynaklar} alan="items[].params" row={p.id} label={`${p.scenarioLabel} senaryo · varsayımlar`} /></span>
                </span>
                <span className="pointer-events-auto">
                  <SqlInfo k={cmp.data?.kaynaklar} alan="items[].totals" row={p.id} label={`${p.scenarioLabel} senaryo · sürüm ${p.version}`} />
                </span>
              </div>
              </div>
            ))}
          </div>
        )}
      </Panel>

      <Panel>
        <h3 className="text-[15px] font-extrabold">Seçili planın varsayımları</h3>
        <p className="mb-3 text-[12px] text-canvas-muted">
          {current.status === 'taslak'
            ? 'Değiştirip «Yeniden hesapla» deyin: öneri satırları yeniden kurulur, elle düzeltilen kitap, program ve departman satırları korunur.'
            : 'Bu plan taslak değil; varsayımlar yalnız okunur. Değiştirmek için yürürlükteki planı revize edin.'}
        </p>
        <fieldset disabled={current.status !== 'taslak' || !canEdit} className="disabled:opacity-80">
          <ParamsForm value={text} onChange={setText} only={current.scenario}
            sources={{ fiyat: current.params.fiyatKaynak, gider: current.params.giderKaynak }}
            info={(_key, l) => <SqlInfo k={history.data?.kaynaklar} alan="items[].params" row={current.id} label={`${current.scenarioLabel} · ${l}`} />}
            forecast={current.basis.tahmin?.baslangic ?? null} />
        </fieldset>
        {current.status === 'taslak' && canEdit && (
          <div className="mt-3 flex justify-end">
            <button type="button" className={btnPrimary} onClick={() => recompute.mutate()} disabled={recompute.isPending}>
              {recompute.isPending && <Loader2 aria-hidden className="h-4 w-4 animate-spin" />}
              Yeniden hesapla
            </button>
          </div>
        )}
      </Panel>

      {archived.length > 0 && (
        <Panel>
          <h3 className="mb-2 text-[15px] font-extrabold">Önceki sürümler</h3>
          <TableWrap>
            <thead>
              <tr>
                <th className={th}>Plan</th>
                <th className={`${th} text-right`}><InfoLabel k={history.data?.kaynaklar} alan="items[].totals">Net ciro</InfoLabel></th>
                <th className={th}>Onaylayan</th>
                <th className={th}>Revizyon gerekçesi</th>
              </tr>
            </thead>
            <tbody>
              {archived.map((p) => (
                <tr key={p.id} onClick={() => onOpen(p.id)} className="cursor-pointer border-t border-slate-100 hover:bg-slate-50/80">
                  <td className={`${td} font-semibold`}>{p.title}</td>
                  <td className={`${td} text-right font-mono tabular-nums`}>{fmtMoney(p.totals.ciro)}</td>
                  <td className={td}>{p.decidedBy ?? '—'}{p.decidedAt ? `, ${fmtDay(p.decidedAt)}` : ''}</td>
                  <td className={`${td} text-canvas-muted`}>{p.revisionReason ?? '—'}</td>
                </tr>
              ))}
            </tbody>
          </TableWrap>
        </Panel>
      )}
    </div>
  );
}
