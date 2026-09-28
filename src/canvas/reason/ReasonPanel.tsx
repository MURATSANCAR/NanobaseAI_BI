import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { toast } from 'sonner';
import { ChevronDown, Copy, HelpCircle, Loader2 } from 'lucide-react';
import { Note, Pill, btnGhost, errText } from '../admin/ui';
import { amount, share, signed, type Compare, type Reason, type ReasonDim, type ReasonOk } from './api';

/** «Neden?» — farkın kanal, cari ve kitap katkısı. Rakamlar köprüdeki SQL'den; Zeki AI yalnız 2–3 cümle anlatır ve
 *  metindeki her sayı olgularla denetlenir (tutmazsa «kurala göre» metin). Kapalı başlar; açılınca bir kez sorar.
 *  Telefon: boyutlar alt alta, satır adı kısalır, çubuk satırın altında. */

const TOP = 5;

export function NarrativePill({ kaynak }: { kaynak?: 'zeki' | 'kural' }) {
  return kaynak === 'zeki' ? <Pill tone="violet">Zeki AI</Pill> : <Pill tone="muted">Kurala göre</Pill>;
}

function DimBlock({ d, unit }: { d: ReasonDim; unit: string }) {
  const [all, setAll] = useState(false);
  const items = all ? d.kalemler : d.kalemler.slice(0, TOP);
  if (!d.kalemler.length) return null;
  return (
    <section className="min-w-0">
      <h4 className="flex flex-wrap items-baseline gap-x-2 text-[12px] font-extrabold uppercase tracking-wide text-canvas-muted">
        {d.ad}
        {d.karsi && <span className="text-[11px] font-semibold normal-case tracking-normal">· {d.karsi}</span>}
      </h4>
      <ul className="mt-1 flex flex-col gap-1.5">
        {items.map((it) => (
          <li key={it.anahtar} className="min-w-0">
            <div className="flex items-baseline justify-between gap-3 text-[12.5px]">
              <span className="min-w-0 truncate font-semibold" title={it.ad}>
                {it.ad}
                {it.yeni && <span className="ml-1 text-[11px] font-bold text-emerald-700">yeni</span>}
                {it.kayip && <span className="ml-1 text-[11px] font-bold text-red-700">yok</span>}
              </span>
              <span className={`shrink-0 font-mono tabular-nums font-bold ${it.fark > 0 ? 'text-emerald-700' : 'text-red-700'}`}>
                {signed(it.fark, unit)}
              </span>
            </div>
            <div className="mt-0.5 flex items-center gap-2">
              <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-slate-100" aria-hidden>
                <div
                  className={`h-full rounded-full ${it.fark > 0 ? 'bg-emerald-500/70' : 'bg-red-500/70'}`}
                  style={{ width: `${Math.max(2, Math.min(100, (it.payMutlak ?? 0) * 100))}%` }}
                />
              </div>
              <span className="hidden shrink-0 text-right text-[11px] tabular-nums text-canvas-muted sm:block">
                {amount(it.onceki, '')} → {amount(it.simdi, '')}
              </span>
            </div>
          </li>
        ))}
      </ul>
      {d.kalemler.length > TOP && (
        <button type="button" className="mt-1 min-h-9 text-[12px] font-bold text-canvas-violet" onClick={() => setAll((v) => !v)}>
          {all ? 'İlk 5' : `Tümü (${d.kalemSayisi})`}
        </button>
      )}
    </section>
  );
}

function SqlInfo({ items }: { items: Array<{ ad: string; sql: string }> }) {
  if (!items.length) return null;
  const copy = (s: string) =>
    navigator.clipboard?.writeText(s).then(() => toast.success('Sorgu kopyalandı.'), () => toast.error('Kopyalanamadı.'));
  return (
    <details className="mt-3 rounded-xl bg-slate-50 px-3 py-2 text-[12px]">
      <summary className="cursor-pointer select-none font-bold text-canvas-muted">Sorgu bilgisi ({items.length} sorgu)</summary>
      <ul className="mt-2 flex flex-col gap-2">
        {items.map((q, i) => (
          <li key={i} className="min-w-0">
            <div className="flex items-center justify-between gap-2">
              <span className="min-w-0 truncate font-semibold">{q.ad}</span>
              <button type="button" className="inline-flex min-h-9 items-center gap-1 text-[11.5px] font-bold text-canvas-violet" onClick={() => void copy(q.sql)}>
                <Copy aria-hidden className="h-3.5 w-3.5" /> Kopyala
              </button>
            </div>
            <pre className="mt-1 max-h-48 overflow-auto whitespace-pre rounded-lg bg-white p-2 font-mono text-[11px] leading-snug">{q.sql}</pre>
          </li>
        ))}
      </ul>
    </details>
  );
}

export function ReasonBody({ r }: { r: ReasonOk }) {
  const unit = r.olcu.birim ?? '';
  const t = r.toplam;
  return (
    <div className="flex flex-col gap-3">
      {r.anlatim?.metin && (
        <div>
          <div className="mb-1 flex items-center gap-1.5"><NarrativePill kaynak={r.anlatim.kaynak} /></div>
          <p className="text-[13px] leading-relaxed">{r.anlatim.metin}</p>
        </div>
      )}
      <div className="grid grid-cols-1 gap-2 text-[12px] sm:grid-cols-3">
        <div className="rounded-xl bg-white/80 p-2.5">
          <div className="text-[11px] font-bold uppercase text-canvas-muted">{r.donem.etiket}</div>
          <div className="font-mono text-[15px] font-bold tabular-nums">{amount(t.simdi, unit)}</div>
        </div>
        <div className="rounded-xl bg-white/80 p-2.5">
          <div className="text-[11px] font-bold uppercase text-canvas-muted">{r.karsi.ad}</div>
          <div className="font-mono text-[15px] font-bold tabular-nums">{amount(t.onceki, unit)}</div>
          <div className="text-[11px] text-canvas-muted">{r.karsi.etiket}</div>
        </div>
        <div className="rounded-xl bg-white/80 p-2.5">
          <div className="text-[11px] font-bold uppercase text-canvas-muted">Fark</div>
          <div className={`font-mono text-[15px] font-bold tabular-nums ${t.fark > 0 ? 'text-emerald-700' : t.fark < 0 ? 'text-red-700' : ''}`}>
            {signed(t.fark, unit)}
          </div>
          {t.oran != null && <div className="text-[11px] text-canvas-muted">{share(t.oran)} {t.fark >= 0 ? 'artış' : 'azalış'}</div>}
        </div>
      </div>
      {r.kirpildi && (
        <p className="text-[11.5px] text-canvas-muted">
          Veri {r.veriSonu ? r.veriSonu.split('-').reverse().join('.') : 'dönem sonundan önce'} gününde bitiyor; karşı dönem aynı uzunluğa kırpıldı.
        </p>
      )}
      {(r.notlar ?? []).map((n) => <Note key={n} tone="info">{n}</Note>)}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        {r.boyutlar.map((d) => <DimBlock key={d.id} d={d} unit={unit} />)}
      </div>
      <SqlInfo items={r.kaynak?.sql ?? []} />
    </div>
  );
}

type Props = {
  /** Sorgu anahtarı (önbellek): aynı cevap için yeniden sorulmaz. */
  queryKey: unknown[];
  load: (karsi: Compare) => Promise<Reason>;
  /** Karşı dönem seçimi (geçen yıl / önceki dönem); bütçe sapmasında yok (taban hedeftir). */
  compare?: boolean;
  label?: string;
  className?: string;
};

export default function ReasonPanel({ queryKey, load, compare = true, label = 'Neden?', className = '' }: Props) {
  const [open, setOpen] = useState(false);
  const [karsi, setKarsi] = useState<Compare>('gecen-yil');
  const q = useQuery({ queryKey: [...queryKey, karsi], queryFn: () => load(karsi), enabled: open, staleTime: 10 * 60_000, retry: false });
  const r = q.data;
  return (
    <div className={className}>
      <button type="button" className={btnGhost} aria-expanded={open} onClick={() => setOpen((v) => !v)}>
        <HelpCircle aria-hidden className="h-4 w-4" />
        {label}
        <ChevronDown aria-hidden className={`h-4 w-4 ${open ? 'rotate-180' : ''}`} />
      </button>
      {open && (
        <div className="mt-2 rounded-2xl border border-slate-200 bg-white/70 p-3">
          {compare && (
            <div role="group" aria-label="Karşılaştırma" className="mb-3 inline-flex rounded-xl bg-slate-100 p-0.5 text-[12px] font-bold">
              {(['gecen-yil', 'onceki-donem'] as Compare[]).map((k) => (
                <button key={k} type="button" aria-pressed={karsi === k}
                  className={`min-h-9 rounded-lg px-3 ${karsi === k ? 'bg-white shadow-sm' : 'text-canvas-muted'}`}
                  onClick={() => setKarsi(k)}>
                  {k === 'gecen-yil' ? 'Geçen yıl' : 'Önceki dönem'}
                </button>
              ))}
            </div>
          )}
          {q.isLoading && (
            <p className="flex items-center gap-2 text-[12.5px] text-canvas-muted">
              <Loader2 aria-hidden className="h-4 w-4 animate-spin" /> Kırılımlar hesaplanıyor…
            </p>
          )}
          {q.error && <Note tone="err">{errText(q.error, 'Ayrıştırma yapılamadı.')}</Note>}
          {r && !r.ok && <Note tone="info">{r.neden}</Note>}
          {r && r.ok && <ReasonBody r={r} />}
        </div>
      )}
    </div>
  );
}
