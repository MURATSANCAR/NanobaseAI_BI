import { useState, type ReactNode } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { ChevronLeft, Copy, Download } from 'lucide-react';
import Shell, { ZoomStage } from '../stitch/Shell';
import Sheet from '../editorial/studio/reader/Sheet';
import { ENGINE_ENABLED } from '../engine';
import { Note, Pill, btnGhost, btnPrimary, errText } from '../admin/ui';
import { canOpenRoute, usePageAccess } from '../useAdmin';
import { AskSheet } from '../budget/parts';
import { STATE_LABEL, fmtInt, supplyApi, type CardBrief, type CellState, type Suggestion } from './api';

/** M52 Tedarik ekranlarının ortak parçaları: kabuk, ekranlar arası bağlantı, sorgu anahtarları, hücre rengi, öneri
 *  kartı, taslak penceresi. */

export const SCREENS = [
  { to: '/tedarik', label: 'Özet' },
  { to: '/tedarik/yuk', label: 'Baskı yükü' },
  { to: '/tedarik/kagit', label: 'Kağıt ve malzeme' },
  { to: '/tedarik/tedarikciler', label: 'Tedarikçiler' },
  { to: '/tedarik/maliyet', label: 'Maliyet eğilimi' },
] as const;

export function useSupplyMeta() {
  return useQuery({ queryKey: ['supply', 'meta'], queryFn: supplyApi.meta, enabled: ENGINE_ENABLED, staleTime: 10 * 60_000 });
}

export function SupplyFrame({ title, lead, source, back, aside, children }: {
  title: string;
  lead: string;
  source?: string;
  /** Detay sayfası: geri bağlantısı (adres, ad). */
  back?: { to: string; label: string };
  aside?: ReactNode;
  children: ReactNode;
}) {
  const { pathname } = useLocation();
  const access = usePageAccess();
  const here = pathname.replace(/\/+$/, '');
  const screens = SCREENS.filter((s) => canOpenRoute(access, s.to));
  return (
    <Shell head={{ tenant: 'Timaş Yayınları', section: 'Lojistik', crumb: title, source: source ?? 'Kaynak: üretim kartı · CRM · Logo', presence: 'Tedarik ve baskı', detail: back ? title : undefined }}>
      <main className="absolute bottom-2 left-2 right-2 top-16 overflow-y-auto overscroll-contain sm:bottom-6 sm:left-6 sm:right-6 sm:top-[84px]">
        <ZoomStage>
          <div className="mx-auto flex w-full max-w-[1760px] flex-col gap-3 pb-6 lg:gap-4">
            <header className="relative z-20 flex flex-col gap-3 px-1 lg:flex-row lg:items-start lg:justify-between lg:gap-6">
              <div className="min-w-0">
                {back ? (
                  <Link to={back.to} className="inline-flex min-h-11 items-center gap-1 text-[11px] font-bold uppercase tracking-wide text-canvas-violet hover:underline sm:min-h-0">
                    <ChevronLeft aria-hidden className="h-3.5 w-3.5" />
                    {back.label}
                  </Link>
                ) : (
                  <div className="text-[11px] font-bold uppercase tracking-wide text-canvas-violet">Lojistik · Tedarik ve baskı</div>
                )}
                <h1 className="mt-0.5 break-words text-[22px] font-extrabold leading-tight tracking-tight sm:text-[28px]">{title}</h1>
                <p className="mt-1 max-w-[76ch] text-[12.5px] leading-snug text-canvas-muted">{lead}</p>
              </div>
              {aside && <div className="w-full shrink-0 lg:w-[460px]">{aside}</div>}
            </header>
            {!back && screens.length > 1 && (
              <nav aria-label="Tedarik ekranları" className="-mx-1 overflow-x-auto px-1">
                <div className="flex w-max min-w-full gap-1 rounded-2xl bg-slate-100 p-1">
                  {screens.map((s) => {
                    const on = here === s.to;
                    return (
                      <Link
                        key={s.to}
                        to={s.to}
                        aria-current={on ? 'page' : undefined}
                        className={`inline-flex min-h-11 shrink-0 items-center whitespace-nowrap rounded-xl px-3 text-[12.5px] font-extrabold transition-colors duration-150 sm:min-h-9 ${
                          on ? 'bg-canvas-violet text-white shadow-md' : 'text-canvas-ink hover:bg-white/70'
                        }`}
                      >
                        {s.label}
                      </Link>
                    );
                  })}
                </div>
              </nav>
            )}
            {!ENGINE_ENABLED && <Note tone="warn">Bu kurulumda veri bağlantısı tanımlı değil.</Note>}
            {children}
          </div>
        </ZoomStage>
      </main>
    </Shell>
  );
}

/** Uyarılar (kaynak düştü, Logo kopyası geride…) tek tek, tekrar etmeden. */
export function Warnings({ items }: { items: string[] | undefined }) {
  const list = [...new Set(items ?? [])];
  if (!list.length) return null;
  return (
    <div className="flex flex-col gap-2">
      {list.map((w) => (
        <Note key={w} tone="warn">
          {w}
        </Note>
      ))}
    </div>
  );
}

export function ErrorNote({ error, fallback }: { error: unknown; fallback: string }) {
  const t = errText(error, fallback);
  return t ? <Note tone="err">{t}</Note> : null;
}

/** Yük hücresinin rengi: kapasite aşımı kırmızı, referans üstü amber, eşik altında yoğunluğa göre mor tonu. */
export function cellTone(state: CellState, rate: number | null): string {
  if (state === 'asim') return 'bg-red-100 text-red-800 ring-1 ring-red-200';
  if (state === 'referans-ustu') return 'bg-amber-100 text-amber-900 ring-1 ring-amber-200';
  if (state === 'bos') return 'bg-white/60 text-canvas-muted';
  if (state === 'olculemedi') return 'bg-slate-100 text-canvas-ink';
  const r = rate ?? 0;
  return r >= 0.8 ? 'bg-canvas-violet/25 text-canvas-ink' : r >= 0.5 ? 'bg-canvas-violet/15 text-canvas-ink' : 'bg-canvas-violet/5 text-canvas-ink';
}

export function StatePill({ state }: { state: CellState }) {
  const tone = state === 'asim' ? 'err' : state === 'referans-ustu' ? 'warn' : state === 'bos' ? 'muted' : 'violet';
  return <Pill tone={tone}>{STATE_LABEL[state]}</Pill>;
}

export function ExportLink({ href, label = 'Excel' }: { href: string; label?: string }) {
  return (
    <a href={href} className={btnGhost} download>
      <Download aria-hidden className="h-4 w-4" />
      {label}
    </a>
  );
}

/** Kart satırı: kitap, baskı no, adet, aşama, plan tarihi. */
export function CardLine({ c, right }: { c: CardBrief; right?: ReactNode }) {
  return (
    <div className="flex flex-wrap items-start justify-between gap-2 border-b border-slate-100 py-2 last:border-0">
      <div className="min-w-0">
        <div className="truncate text-[13px] font-bold">{c.kitap ?? '—'}</div>
        <div className="text-[11.5px] text-canvas-muted">
          {c.stokKodu ?? 'stok kodu yok'} · {c.baskiNo ? `${c.baskiNo}. baskı` : 'baskı no yok'} · {c.asamaAdi}
          {c.oncelik ? ` · öncelik ${c.oncelik}` : ''}
          {c.gecikme ? ` · ${c.gecikme} gün gecikme` : ''}
        </div>
      </div>
      <div className="flex shrink-0 items-center gap-2">
        <span className="font-mono text-[12.5px] font-bold tabular-nums">{fmtInt(c.adet)} adet</span>
        {right}
      </div>
    </div>
  );
}

/** Taslak penceresi: şartname (kalıp) ya da gecikme yazısı (Zeki AI). Gönderim yok; kopyala. */
export function DraftSheet({ draft, onClose }: { draft: Suggestion | null; onClose: () => void }) {
  return (
    <Sheet open={!!draft} onClose={onClose} modal wide title={draft?.baslik ?? 'Taslak'} subtitle="Taslaktır: portal göndermez; kopyalayıp düzenleyerek siz gönderirsiniz.">
      {draft && (
        <div className="flex flex-col gap-3">
          <pre className="whitespace-pre-wrap break-words rounded-xl bg-slate-50 p-3 font-sans text-[13px] leading-relaxed">{draft.metin}</pre>
          <div className="flex justify-end">
            <button
              type="button"
              className={btnPrimary}
              onClick={() => {
                void navigator.clipboard?.writeText(draft.metin ?? '').then(
                  () => toast.success('Taslak panoya kopyalandı.'),
                  () => toast.error('Kopyalanamadı; metni seçip kopyalayın.'),
                );
              }}
            >
              <Copy aria-hidden className="h-4 w-4" />
              Kopyala
            </button>
          </div>
        </div>
      )}
    </Sheet>
  );
}

export function useDraft() {
  const [draft, setDraft] = useState<Suggestion | null>(null);
  const qc = useQueryClient();
  const make = useMutation({
    mutationFn: (v: { tur: 'sartname' | 'eskalasyon'; kartId: string }) => supplyApi.draft(v.tur, v.kartId),
    onSuccess: (d) => {
      setDraft(d);
      void qc.invalidateQueries({ queryKey: ['supply', 'suggestions'] });
    },
    onError: (e) => toast.error(errText(e, 'Taslak hazırlanamadı.') ?? 'Taslak hazırlanamadı.'),
  });
  return { draft, close: () => setDraft(null), make };
}

/** Öneri listesi: kural hesabı + Zeki AI gerekçesi; kabul / ret (ret gerekçeli). Karar CRM'i değiştirmez. */
export function SuggestionList({ tur, canDecide, empty }: { tur: 'yuk' | 'kagit'; canDecide: boolean; empty: string }) {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ['supply', 'suggestions', tur], queryFn: () => supplyApi.suggestions(tur, 'bekliyor'), enabled: ENGINE_ENABLED });
  const [rejecting, setRejecting] = useState<Suggestion | null>(null);
  const decide = useMutation({
    mutationFn: (v: { id: string; karar: 'kabul' | 'ret'; not?: string }) => supplyApi.decide(v.id, v.karar, v.not),
    onSuccess: (s) => {
      toast.success(s.durum === 'kabul' ? 'Kabul edildi. Kartı M12/CRM\'de değiştirmek sizin işiniz; portal değiştirmez.' : 'Reddedildi.');
      setRejecting(null);
      void qc.invalidateQueries({ queryKey: ['supply'] });
    },
    onError: (e) => toast.error(errText(e, 'Karar kaydedilemedi.') ?? 'Karar kaydedilemedi.'),
  });
  if (q.error) return <ErrorNote error={q.error} fallback="Öneriler okunamadı." />;
  const items = q.data?.items ?? [];
  if (q.isLoading) return <div className="py-4 text-[12px] text-canvas-muted">Yükleniyor…</div>;
  if (!items.length) return <Note tone="info">{empty}</Note>;
  return (
    <div className="flex flex-col gap-2">
      {items.map((s) => (
        <article key={s.id} className="rounded-2xl border border-slate-100 bg-white/80 p-3">
          <div className="flex flex-wrap items-start justify-between gap-2">
            <h3 className="min-w-0 break-words text-[13px] font-extrabold">{s.baslik}</h3>
            <Pill tone="violet">{s.turAdi}</Pill>
          </div>
          {s.metin && <p className="mt-1 text-[12.5px] leading-snug text-canvas-ink">{s.metin}</p>}
          {canDecide && (
            <div className="mt-2 flex flex-wrap justify-end gap-2">
              <button type="button" className={btnGhost} disabled={decide.isPending} onClick={() => setRejecting(s)}>
                Reddet
              </button>
              <button type="button" className={btnPrimary} disabled={decide.isPending} onClick={() => decide.mutate({ id: s.id, karar: 'kabul' })}>
                Kabul et
              </button>
            </div>
          )}
        </article>
      ))}
      <AskSheet
        open={!!rejecting}
        title="Öneriyi reddet"
        message={<span>{rejecting?.baslik}</span>}
        confirm="Reddet"
        danger
        input="Gerekçe"
        required
        busy={decide.isPending}
        onClose={() => setRejecting(null)}
        onConfirm={(t) => rejecting && decide.mutate({ id: rejecting.id, karar: 'ret', not: t })}
      />
    </div>
  );
}
