import { useEffect, useState } from 'react';
import { TableWrap, td, th } from '../admin/ui';
import SqlInfo from '../components/SqlInfo';
import type { Kaynaklar } from '../components/sqlInfo';
import { day, num, parseNum, pct, tl0, tl2, type CompareRow, type LadderGroup } from './api';

/**
 * Eski kitap fiyat çalışmasının parçaları (Fiyat Çalışması Excel'inin ekrandaki karşılığı): emsal merdiveni,
 * satır içi yeni fiyat kutusu, künye satırı.
 */

const money0 = new Intl.NumberFormat('tr-TR', { maximumFractionDigits: 0 });
const pct1 = new Intl.NumberFormat('tr-TR', { maximumFractionDigits: 1 });
const month = new Intl.DateTimeFormat('tr-TR', { month: 'short', year: 'numeric', timeZone: 'UTC' });

export const signedPct = (v: number | null | undefined) => (v == null ? '—' : `${v > 0 ? '+' : v < 0 ? '−' : ''}%${pct1.format(Math.abs(v) * 100)}`);

/** «Mar 2026 · önceki 220 ₺»; pencere boyunca değişmediyse «değişmedi · kayıt Eki 2023 başlıyor». */
export function priceChangeText(r: CompareRow): string {
  if (r.priceChanged) {
    const m = month.format(new Date(`${r.priceChanged.slice(0, 10)}T00:00:00Z`));
    return r.prevPrice != null ? `${m} · önceki ${money0.format(r.prevPrice)} ₺` : m;
  }
  if (r.priceSince) return `değişmedi · kayıt ${month.format(new Date(`${r.priceSince}T00:00:00Z`))} başlıyor`;
  return 'Logo satışı yok';
}

/** Kitap adının altındaki künye: ebat · cilt · renk · gramaj · son baskı · tek ödeme · telif. */
export function BookMeta({ r }: { r: CompareRow }) {
  const spec = [r.trim, r.binding, r.color, r.gsm ? `${num(r.gsm)} gr` : null].filter(Boolean).join(' · ');
  const print = r.lastPrintDate ? `son baskı ${day(r.lastPrintDate)}${r.lastPrintQty ? `, ${num(r.lastPrintQty)} adet` : ''}` : null;
  const roy = Object.entries(r.royalties ?? {})
    .map(([t, v]) => `${shortType(t)} %${v.karton ?? '—'}${v.sert != null ? `/${v.sert}` : ''}`)
    .join(' · ');
  return (
    <>
      {(spec || print) && <div className="text-[11px] text-canvas-muted">{[spec, print].filter(Boolean).join(' · ')}</div>}
      {(roy || r.singlePay) && (
        <div className="text-[11px] text-canvas-muted" title="Telif: karton/sert kapak oranı (CRM sözleşmesi)">
          {[roy ? `telif ${roy}` : null, r.singlePay ? `tek ödeme ${tl0(r.singlePay)}` : null].filter(Boolean).join(' · ')}
        </div>
      )}
    </>
  );
}

/** Sözleşme türünün kısa adı (künye satırına sığsın). */
function shortType(t: string): string {
  const x = t.toLocaleLowerCase('tr-TR');
  if (x.startsWith('metin (yabancı')) return 'yabancı metin';
  if (x.startsWith('metin')) return 'metin';
  if (x.startsWith('ajans')) return 'ajans';
  if (x.includes('yabancı') && x.startsWith('çizim')) return 'yabancı çizim';
  if (x.startsWith('çizim')) return 'çizim';
  if (x.startsWith('yayına')) return 'yayına haz.';
  if (x.startsWith('grafik')) return 'grafik';
  return x;
}

/**
 * Satır içi yeni fiyat. Enter ya da odak kaybında kaydeder, Esc geri alır; boş bırakmak siler.
 * Kaydederken satırın tıklanması (kitap hesabını açma) tetiklenmez.
 */
export function PriceCell({ r, canWrite, saving, onSave }: {
  r: CompareRow;
  canWrite: boolean;
  saving: boolean;
  onSave: (price: number | null) => void;
}) {
  const shown = r.newPrice != null ? String(r.newPrice).replace('.', ',') : '';
  const [v, setV] = useState(shown);
  useEffect(() => setV(shown), [shown]);
  const commit = () => {
    const p = parseNum(v);
    if (v.trim() === shown) return;
    if (v.trim() !== '' && (p == null || p <= 0)) {
      setV(shown);
      return;
    }
    onSave(v.trim() === '' ? null : p);
  };
  const up = r.newPct ?? null;
  return (
    <div className="flex flex-col items-end gap-0.5" onClick={(e) => e.stopPropagation()}>
      {canWrite ? (
        <input
          className={`w-[84px] rounded-lg border bg-white px-2 py-1.5 text-right text-base font-bold tabular-nums outline-none focus:border-canvas-violet sm:text-[12.5px] ${
            r.newPrice != null ? 'border-canvas-violet/40' : 'border-slate-200'
          } ${saving ? 'opacity-60' : ''}`}
          inputMode="decimal"
          aria-label={`${r.name} yeni fiyat`}
          placeholder={r.ladder && r.ladder.price > r.price ? money0.format(r.ladder.price) : '—'}
          value={v}
          onChange={(e) => setV(e.target.value)}
          onBlur={commit}
          onKeyDown={(e) => {
            if (e.key === 'Enter') (e.target as HTMLInputElement).blur();
            if (e.key === 'Escape') {
              setV(shown);
              requestAnimationFrame(() => (e.target as HTMLInputElement).blur());
            }
          }}
        />
      ) : (
        <span className="font-bold tabular-nums">{tl0(r.newPrice)}</span>
      )}
      {r.newPrice != null && (
        <span className={`text-[11px] tabular-nums ${up != null && up > 0 ? 'text-amber-700' : 'text-canvas-muted'}`}>
          {signedPct(up)}
          {r.newPerPage != null ? ` · ${tl2(r.newPerPage)}/s.` : ''}
        </span>
      )}
    </div>
  );
}

/** Kitabın merdiven basamağı: kendi sayfasına eşit ya da altındaki en yakın basamağın fiyatı ve bir üstü. */
export function LadderCell({ r }: { r: CompareRow }) {
  const l = r.ladder;
  if (!l) return <span className="block text-right text-[12px] text-canvas-muted">—</span>;
  const tone = l.price > r.price ? 'text-amber-700' : 'text-canvas-ink';
  return (
    <div className="text-right">
      <div className={`font-bold tabular-nums ${tone}`}>{tl0(l.price)}</div>
      <div className="text-[11px] text-canvas-muted tabular-nums">
        {l.code === r.code ? 'en yükseği bu kitap' : `${num(l.pages)} s.`}
        {l.nextPages != null ? ` · ${num(l.nextPages)} s. ${tl0(l.nextPrice)}` : ''}
      </div>
    </div>
  );
}

/**
 * Emsal merdiveni (Excel'deki «Mak Fiyat» pivotu): seçilen yayınevi × ebat × renk × cilt grubundaki kitapların sayfa
 * sayısı başına en yüksek güncel fiyatı. Basamağa dokununca kitabın hesabı açılır.
 */
export function LadderPanel({ g, k, onOpen }: { g: LadderGroup; k?: Kaynaklar; onOpen: (code: string) => void }) {
  return (
    <section className="space-y-1.5">
      <h3 className="flex flex-wrap items-center gap-1.5 px-1 text-[13px] font-extrabold">
        Emsal merdiveni
        <SqlInfo k={k} alan="groups[]" label="Emsal merdiveni" />
        <span className="text-[11.5px] font-semibold text-canvas-muted">
          {g.key} · {num(g.books)} kitap · {num(g.steps.length)} basamak
        </span>
      </h3>
      {g.steps.length === 0 ? (
        <p className="px-1 text-[12px] text-canvas-muted">Bu grupta sayfa sayısı girilmiş kitap yok; merdiven kurulamadı.</p>
      ) : (
        <TableWrap>
          <thead>
            <tr>
              <th className={`${th} text-right`}>Sayfa</th>
              <th className={`${th} text-right`}>En yüksek fiyat</th>
              <th className={`${th} text-right`}>Sayfa başı</th>
              <th className={`${th} text-right`}>Kâr % (güncel)</th>
              <th className={th}>Kitap</th>
            </tr>
          </thead>
          <tbody>
            {g.steps.map((s) => (
              <tr key={s.pages} className="cursor-pointer border-t border-slate-100 hover:bg-slate-50" onClick={() => onOpen(s.code)}>
                <td className={`${td} text-right font-bold tabular-nums`}>{num(s.pages)}</td>
                <td className={`${td} text-right font-bold tabular-nums`}>{tl0(s.price)}</td>
                <td className={`${td} text-right tabular-nums`}>{tl2(s.price / s.pages)}</td>
                <td className={`${td} text-right tabular-nums`}>{pct(s.margin)}</td>
                <td className={td}>
                  {s.name}
                  <div className="text-[11px] text-canvas-muted">
                    {s.code}
                    {s.firstPub ? ` · ilk ${day(s.firstPub)}` : ''}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </TableWrap>
      )}
    </section>
  );
}
