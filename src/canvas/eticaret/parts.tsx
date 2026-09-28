import { useState, type ReactNode } from 'react';
import { NavLink } from 'react-router-dom';
import { Loader2, Sparkles } from 'lucide-react';
import Shell, { ZoomStage } from '../stitch/Shell';
import Sheet from '../editorial/studio/reader/Sheet';
import { Pill, btnGhost, btnPrimary, field, label as labelCls } from '../admin/ui';
import { canOpenRoute, usePageAccess } from '../useAdmin';
import { KIND_TONE, STATE_TONE, fmtDay, fmtPct, type Diff, type MarkState, type Meta } from './api';

/** E-ticaret ekranlarının ortak kabuğu: başlık, dört ekran arası geçiş (yalnız rolünde olanlar) ve «yazma yok» notu. */

const SCREENS = [
  { to: '/e-ticaret', label: 'Platform durumu', end: true },
  { to: '/e-ticaret/farklar', label: 'Farklar' },
  { to: '/e-ticaret/huni', label: 'Huni' },
  { to: '/e-ticaret/pazar-yerleri', label: 'Pazar yerleri' },
] as const;

export function EticaretFrame({ title, lead, source, aside, children }: {
  title: string;
  lead: string;
  source: string;
  aside?: ReactNode;
  children: ReactNode;
}) {
  const pages = usePageAccess();
  const screens = SCREENS.filter((s) => canOpenRoute(pages, s.to));
  return (
    <Shell head={{ tenant: 'Timaş Yayınları', section: 'Pazarlama', crumb: 'E-ticaret', source, presence: 'E-ticaret' }}>
      <main className="absolute bottom-2 left-2 right-2 top-16 overflow-y-auto overscroll-contain sm:bottom-6 sm:left-6 sm:right-6 sm:top-[84px]">
        <ZoomStage>
          <div className="mx-auto flex w-full max-w-[1760px] flex-col gap-3 pb-6 lg:gap-4">
            <header className="relative z-20 flex flex-col gap-3 px-1 lg:flex-row lg:items-start lg:justify-between lg:gap-6">
              <div className="min-w-0">
                <div className="text-[11px] font-bold uppercase tracking-wide text-canvas-violet">Dijital ve topluluk · E-ticaret</div>
                <h1 className="mt-0.5 break-words text-[22px] font-extrabold leading-tight tracking-tight sm:text-[28px]">{title}</h1>
                <p className="mt-1 max-w-[80ch] text-[12.5px] leading-snug text-canvas-muted">{lead}</p>
              </div>
              {aside && <div className="w-full shrink-0 lg:w-auto">{aside}</div>}
            </header>
            {screens.length > 1 && (
              <nav aria-label="E-ticaret ekranları" className="-mx-1 overflow-x-auto px-1">
                <div className="flex w-max min-w-full gap-1 rounded-2xl bg-slate-100 p-1">
                  {screens.map((s) => (
                    <NavLink
                      key={s.to}
                      to={s.to}
                      end={'end' in s ? s.end : false}
                      className={({ isActive }) =>
                        `inline-flex min-h-11 shrink-0 items-center whitespace-nowrap rounded-xl px-3 text-[12.5px] font-extrabold transition-colors duration-150 sm:min-h-9 ${
                          isActive ? 'bg-canvas-violet text-white shadow-md' : 'text-canvas-ink hover:bg-white/70'
                        }`
                      }
                    >
                      {s.label}
                    </NavLink>
                  ))}
                </div>
              </nav>
            )}
            {children}
          </div>
        </ZoomStage>
      </main>
    </Shell>
  );
}

/** Üç kaynağın değeri yan yana; boş olan tire. Telefonda alt alta. */
export function ThreeValues({ crm, logo, site }: { crm: ReactNode; logo: ReactNode; site: ReactNode }) {
  const cell = (k: string, v: ReactNode) => (
    <div className="min-w-0 rounded-lg bg-slate-50 px-2 py-1">
      <div className="text-[10px] font-bold uppercase tracking-wide text-canvas-muted">{k}</div>
      <div className="break-words font-mono text-[12px] font-semibold tabular-nums">{v ?? '—'}</div>
    </div>
  );
  return (
    <div className="grid grid-cols-1 gap-1.5 sm:grid-cols-3">
      {cell('CRM', crm)}
      {cell('Logo', logo)}
      {cell('Site', site)}
    </div>
  );
}

/** Bir fark satırı (kart). Tıklanınca kitabın çekmecesi açılır; seçim kutusu toplu işaret içindir. */
export function DiffCard({ d, onOpen, selected, onSelect, onMark }: {
  d: Diff;
  onOpen?: (key: string) => void;
  selected?: boolean;
  onSelect?: (on: boolean) => void;
  onMark?: (d: Diff) => void;
}) {
  return (
    <div className="flex gap-2 rounded-2xl border border-slate-100 bg-white/80 p-3 transition-colors duration-150 hover:border-canvas-violet/40">
      {onSelect && (
        <label className="flex min-h-11 min-w-8 cursor-pointer items-start justify-center pt-1 sm:min-h-0">
          <input type="checkbox" className="h-4 w-4 accent-canvas-violet" checked={!!selected}
            aria-label={`${d.ad ?? d.productKey} seç`} onChange={(e) => onSelect(e.target.checked)} />
        </label>
      )}
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-1.5">
          <Pill tone={KIND_TONE[d.tur]}>{d.turAdi}</Pill>
          <Pill tone={STATE_TONE[d.durum]}>{d.durumAdi}</Pill>
          {d.sahip && <span className="text-[11px] font-semibold text-canvas-muted">Sahip: {d.sahip}</span>}
          <span className="font-mono text-[11px] text-canvas-muted">{d.productKey}{d.stokKodu ? ` · ${d.stokKodu}` : ''}</span>
        </div>
        {onOpen ? (
          <button type="button" onClick={() => onOpen(d.productKey)}
            className="mt-1 block max-w-full break-words text-left text-[13.5px] font-extrabold leading-snug hover:text-canvas-violet hover:underline">
            {d.ad || d.productKey}
          </button>
        ) : (
          <div className="mt-1 break-words text-[13.5px] font-extrabold leading-snug">{d.ad || d.productKey}</div>
        )}
        <p className="mt-0.5 break-words text-[12px] leading-snug text-canvas-muted">{d.aciklama}</p>
        {(d.crm || d.logo || d.site) && (
          <div className="mt-2">
            <ThreeValues crm={d.crm} logo={d.logo} site={d.site} />
          </div>
        )}
        <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-canvas-muted">
          <span>İlk görüldü {fmtDay(d.ilkGoruldu)}</span>
          {d.etki > 0 && <span>Son dönem Logo satışı {Math.round(d.etki).toLocaleString('tr-TR')} adet</span>}
          {d.neden && (
            <span className="inline-flex items-center gap-1 font-semibold text-canvas-violet">
              <Sparkles aria-hidden className="h-3.5 w-3.5" />
              Zeki AI önerisi: {d.neden.oneri}{d.neden.olasilik !== null && d.neden.oneri !== 'belirsiz' ? ` (${fmtPct(d.neden.olasilik)})` : ''}
            </span>
          )}
          {d.not && <span className="break-words">Not: {d.not}</span>}
        </div>
      </div>
      {onMark && d.durum !== 'kapandi' && (
        <div className="shrink-0">
          <button type="button" className={btnGhost} onClick={() => onMark(d)}>İşaretle</button>
        </div>
      )}
    </div>
  );
}

const MARK_HELP: Record<MarkState, string> = {
  duzeltildi: 'Düzeltmeyi T-soft panelinde ya da CRM\'de siz yaptınız. Sonraki gece okumasında fark kalktıysa kayıt doğrulanıp kapanır; hâlâ varsa yeniden açılır.',
  bilincli: 'Fark bilerek böyle (ör. kampanya fiyatı). Değerler değişmedikçe yeniden açılmaz ve bildirim gitmez. Gerekçe şart.',
  sonra: 'Liste başından kalkar; süre dolunca yeniden açık olur.',
  acik: 'Kaydı yeniden açık yapar.',
};

/** İşaret penceresi: tek fark ya da seçilenlerin hepsi. */
export function MarkSheet({ open, meta, count, initial, busy, onClose, onSave }: {
  open: boolean;
  meta: Meta;
  count: number;
  initial?: { durum?: MarkState; sahip?: string | null };
  busy?: boolean;
  onClose: () => void;
  onSave: (b: { durum: MarkState; note: string; sahip: string | null }) => void;
}) {
  const [durum, setDurum] = useState<MarkState>(initial?.durum && initial.durum !== 'acik' ? initial.durum : 'duzeltildi');
  const [note, setNote] = useState('');
  const [sahip, setSahip] = useState(initial?.sahip ?? '');
  const need = durum === 'bilincli' && !note.trim();
  return (
    <Sheet open={open} modal onClose={onClose} title={count > 1 ? `${count} farkı işaretle` : 'Farkı işaretle'}
      subtitle="Portal hiçbir sisteme yazmaz; işaret yalnız bu kayıttadır.">
      <div className="flex flex-col gap-3 text-[13px]">
        <fieldset className="flex flex-col gap-1.5">
          <legend className={labelCls}>Durum</legend>
          {meta.isaretler.map((k) => (
            <label key={k} className={`flex min-h-11 cursor-pointer items-start gap-2 rounded-xl border px-3 py-2 transition-colors duration-150 sm:min-h-0 ${durum === k ? 'border-canvas-violet bg-canvas-violet/5' : 'border-slate-200'}`}>
              <input type="radio" name="durum" className="mt-0.5" checked={durum === k} onChange={() => setDurum(k)} />
              <span>
                <span className="block font-bold">{meta.durumlar[k]}{k === 'sonra' ? ` (${meta.ayarlar.snoozeDays} gün)` : ''}</span>
                <span className="block text-[11.5px] leading-snug text-canvas-muted">{MARK_HELP[k]}</span>
              </span>
            </label>
          ))}
        </fieldset>
        <label className="flex flex-col gap-1">
          <span className={labelCls}>{durum === 'bilincli' ? 'Gerekçe *' : 'Not'}</span>
          <textarea className={`${field} min-h-[72px]`} value={note} maxLength={1000} onChange={(e) => setNote(e.target.value)} />
        </label>
        <label className="flex flex-col gap-1">
          <span className={labelCls}>Sahip (kim düzeltir; kullanıcı adı)</span>
          <input className={field} value={sahip ?? ''} maxLength={120} onChange={(e) => setSahip(e.target.value)} autoComplete="off" />
        </label>
        <div className="flex flex-wrap justify-end gap-2">
          <button type="button" className={btnGhost} onClick={onClose}>Vazgeç</button>
          <button type="button" className={btnPrimary} disabled={busy || need}
            onClick={() => onSave({ durum, note: note.trim(), sahip: sahip.trim() === (initial?.sahip ?? '') ? null : sahip.trim() })}>
            {busy && <Loader2 aria-hidden className="h-4 w-4 animate-spin" />}
            Kaydet
          </button>
        </div>
      </div>
    </Sheet>
  );
}

/** Kaynağın okunma zamanı ve Logo kesim tarihi: «canlı» gibi görünmesin diye her göstergenin yanında. */
export function Stamp({ children }: { children: ReactNode }) {
  return <span className="text-[11px] leading-snug text-canvas-muted">{children}</span>;
}
