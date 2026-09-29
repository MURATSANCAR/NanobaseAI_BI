import { useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { ShieldAlert } from 'lucide-react';
import { Note, Pill, btnGhost, errText, field } from '../admin/ui';
import { Panel } from '../editorial/kit';
import { fmtPct, tendersApi, type RiskFlag, type TenderDetail } from './api';

/** Şartnamedeki riskli koşullar (ceza, teminat, teslim süresi, numune, yerli malı…). Her işaret şartnameden birebir
 *  alıntıdır; kategori kapalı kümeden seçilir (Zeki AI ya da kurala göre). Engel kararı ihale sorumlusunundur. */

const TONE: Record<string, 'err' | 'warn' | 'muted' | 'ok'> = { engel: 'err', bilgi: 'warn', 'engel-degil': 'ok' };

export default function TenderRisks({ d, canEdit, modelVar, busy }: { d: TenderDetail; canEdit: boolean; modelVar: boolean; busy: boolean }) {
  const qc = useQueryClient();
  const [only, setOnly] = useState('');
  const q = useQuery({ queryKey: ['tenders', 'risks', d.id, d.isler[0]?.id ?? ''], queryFn: () => tendersApi.risks(d.id) });
  const hasSpec = d.dosyalar.some((f) => f.tur === 'sartname');
  const run = useMutation({
    mutationFn: () => tendersApi.runRisks(d.id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['tenders'] }); toast.success('Risk koşulları işaretleniyor.'); },
    onError: (e) => toast.error(errText(e, 'Başlatılamadı.') ?? ''),
  });
  const decide = useMutation({
    mutationFn: ({ id, karar }: { id: string; karar: string }) => tendersApi.decideRisk(d.id, id, { karar }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['tenders', 'risks', d.id] }),
    onError: (e) => toast.error(errText(e, 'Kaydedilemedi.') ?? ''),
  });
  const data = q.data;
  const items = useMemo(() => (data?.items ?? []).filter((r) => !only || r.kategori === only), [data, only]);
  const cats = useMemo(() => {
    const m = new Map<string, number>();
    for (const r of data?.items ?? []) if (r.kategori) m.set(r.kategori, (m.get(r.kategori) ?? 0) + 1);
    return [...m.entries()];
  }, [data]);

  return (
    <Panel>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <h2 className="text-[16px] font-extrabold tracking-tight">Riskli koşullar</h2>
          <p className="text-[12px] text-canvas-muted">Şartnamedeki ceza, teminat, süre, numune, yerli malı gibi koşullar; her biri şartnameden alıntıdır. «Engel mi» kararı sizindir.</p>
        </div>
        {canEdit && hasSpec && (
          <button type="button" className={btnGhost} disabled={busy || run.isPending} onClick={() => run.mutate()}>
            <ShieldAlert aria-hidden className="h-4 w-4" />
            {data?.items.length ? 'Yeniden işaretle' : 'Risk koşullarını işaretle'}
          </button>
        )}
      </div>
      {q.error && <div className="mt-2"><Note tone="err">{errText(q.error, 'Okunamadı.')}</Note></div>}
      {!hasSpec && <p className="mt-2 text-[12.5px] text-canvas-muted">Önce şartname dosyasını yükleyin.</p>}
      {data && !data.items.length && hasSpec && <p className="mt-2 text-[12.5px] text-canvas-muted">Henüz işaretlenmedi. «Risk koşullarını işaretle» ile şartnamedeki ceza, teminat ve süre gibi koşulları listeleyin.</p>}
      {!!data?.items.length && (
        <>
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <select aria-label="Kategori" value={only} onChange={(e) => setOnly(e.target.value)} className={`${field} w-auto`}>
              <option value="">Bütün kategoriler ({data.items.length})</option>
              {cats.map(([k, n]) => <option key={k} value={k}>{data.kategoriler[k] ?? k} ({n})</option>)}
            </select>
            {data.engel > 0 && <Pill tone="err">{data.engel} engel</Pill>}
            {data.kararsiz > 0 && <Pill tone="warn">{data.kararsiz} karar bekliyor</Pill>}
          </div>
          <ul className="mt-2 flex flex-col gap-1.5">
            {items.map((r: RiskFlag) => (
              <li key={r.id} className="rounded-xl border border-slate-100 bg-white/80 px-3 py-2">
                <div className="flex flex-wrap items-center gap-1.5 text-[12px]">
                  <Pill tone={r.kaynak === 'incele' ? 'warn' : 'violet'}>{r.kategoriAdi ?? 'Kategori belirsiz'}</Pill>
                  <span className="text-[11px] text-canvas-muted">
                    {r.kaynak === 'zeki' ? `Zeki AI${r.olasilik != null ? ` · ${fmtPct(r.olasilik)}` : ''}` : r.kaynak === 'kural' ? 'kurala göre' : 'incelenecek — kategori kuraldan'}
                  </span>
                  {r.karar && <Pill tone={TONE[r.karar] ?? 'muted'}>{r.kararAdi}</Pill>}
                </div>
                <q className="mt-1 block break-words text-[12.5px] italic leading-snug">{r.alinti}</q>
                {canEdit && (
                  <div className="mt-1.5 flex flex-wrap gap-1.5">
                    {Object.entries(data.kararlar).map(([k, v]) => (
                      <button key={k} type="button" aria-pressed={r.karar === k} disabled={decide.isPending}
                        onClick={() => decide.mutate({ id: r.id, karar: r.karar === k ? '' : k })}
                        className={`${btnGhost} ${r.karar === k ? 'ring-2 ring-canvas-violet/40' : ''}`}>
                        {v}
                      </button>
                    ))}
                  </div>
                )}
              </li>
            ))}
          </ul>
          <p className="mt-2 text-[11.5px] text-canvas-muted">
            {items[0]?.dosya ? `Kaynak: ${items[0].dosya}. ` : ''}{!modelVar ? 'Zeki AI bu kurulumda kapalı; kategoriler kurala göre seçildi.' : ''}
          </p>
        </>
      )}
    </Panel>
  );
}
