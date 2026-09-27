import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { ChevronDown } from 'lucide-react';
import { Note, errText } from '../admin/ui';
import { Panel } from '../editorial/kit';
import { fmtDay } from '../budget/api';
import { ENGINE_ENABLED } from '../engine';
import { distApi } from './api';
import { n0 } from './parts';

/** BMT görünümü (telefon öncelikli, salt okunur): onaylı planlarda kişinin carilerine düşen yeni kitaplar.
 *  Kitap kartına dokununca müşteri × adet × sevk. Bütün carileri görebilen kişi «Herkes» ile hepsini görür. */
export default function MyRegion({ canAll }: { canAll: boolean }) {
  const [all, setAll] = useState(false);
  const [open, setOpen] = useState<string | null>(null);
  const q = useQuery({ queryKey: ['dist', 'my-region', all], queryFn: () => distApi.myRegion(all), enabled: ENGINE_ENABLED });
  const items = q.data?.items ?? [];
  return (
    <Panel>
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div>
          <div className="text-[14px] font-extrabold">{all ? 'Bütün bölgelere gelen kitaplar' : 'Bölgenize gelen yeni kitaplar'}</div>
          <div className="text-[11.5px] text-canvas-muted">Onaylı dağılım planları, onaydan sonraki 8 hafta. Müşteri listesi CRM'de sahibi olduğunuz carilerden.</div>
        </div>
        {canAll && (
          <div className="flex gap-1 rounded-xl bg-slate-100 p-1" role="group" aria-label="Kapsam">
            {[false, true].map((v) => (
              <button key={String(v)} type="button" aria-pressed={all === v} onClick={() => setAll(v)}
                className={`min-h-11 rounded-lg px-3 text-[12px] font-bold transition-colors duration-150 sm:min-h-8 ${all === v ? 'bg-white shadow-sm' : 'text-canvas-muted'}`}>
                {v ? 'Herkes' : 'Benim'}
              </button>
            ))}
          </div>
        )}
      </div>
      {q.error && <Note tone="err">{errText(q.error, 'Liste okunamadı.')}</Note>}
      {q.isLoading && <div className="py-8 text-center text-[12px] text-canvas-muted">Okunuyor…</div>}
      {q.isSuccess && !items.length && (
        <div className="py-8 text-center text-[12.5px] text-canvas-muted">
          Son 8 haftada onaylanan planlarda {all ? '' : 'carilerinize düşen '}kitap yok.
        </div>
      )}
      <ul className="grid grid-cols-1 gap-2 md:grid-cols-2 xl:grid-cols-3">
        {items.map((b) => {
          const isOpen = open === b.planId;
          return (
            <li key={b.planId} className="rounded-2xl border border-slate-100 bg-white/80">
              <button type="button" onClick={() => setOpen(isOpen ? null : b.planId)} aria-expanded={isOpen}
                className="flex min-h-11 w-full items-start justify-between gap-2 p-3 text-left">
                <div className="min-w-0">
                  <div className="break-words text-[13.5px] font-extrabold leading-snug">{b.ad ?? b.stokKodu}</div>
                  <div className="mt-0.5 text-[11.5px] text-canvas-muted">Depoya giriş {fmtDay(b.depoGiris)} · onay {fmtDay(b.onay)}</div>
                  <div className="mt-2 flex gap-4 text-[12px]">
                    <span><strong className="font-mono tabular-nums">{n0(b.adet)}</strong> adet</span>
                    <span><strong className="font-mono tabular-nums">{n0(b.musteri)}</strong> müşteri</span>
                    <span><strong className="font-mono tabular-nums">{n0(b.sevk)}</strong> sevk</span>
                  </div>
                </div>
                <ChevronDown aria-hidden className={`mt-1 h-4 w-4 shrink-0 text-canvas-muted ${isOpen ? 'rotate-180' : ''}`} />
              </button>
              {isOpen && (
                <ul className="border-t border-slate-100 px-3 pb-2">
                  {b.cariler.map((c) => (
                    <li key={`${c.cariKodu}-${c.unvan}`} className="flex items-center justify-between gap-2 border-b border-slate-50 py-2 last:border-0">
                      <div className="min-w-0">
                        <div className="break-words text-[12.5px] font-bold">{c.unvan}</div>
                        <div className="text-[11px] text-canvas-muted">{c.il ?? 'İl yok'}{all && c.bmt ? ` · ${c.bmt}` : ''}</div>
                      </div>
                      <div className="shrink-0 text-right">
                        <div className="font-mono text-[14px] font-bold tabular-nums">{n0(c.adet)}</div>
                        <div className={`text-[11px] ${c.sevk > 0 ? 'text-emerald-700' : 'text-canvas-muted'}`}>{c.sevk > 0 ? `${n0(c.sevk)} sevk` : 'sevk yok'}</div>
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </li>
          );
        })}
      </ul>
    </Panel>
  );
}
