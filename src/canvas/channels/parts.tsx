import { useCallback, useEffect, type ReactNode } from 'react';
import { Link, NavLink, useSearchParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { ChevronLeft, Loader2, RefreshCw } from 'lucide-react';
import Shell, { ZoomStage } from '../stitch/Shell';
import { ENGINE_ENABLED } from '../engine';
import { Note, btnGhost, errText, field, label as labelCls } from '../admin/ui';
import { fmtDay } from '../budget/api';
import { channelsApi, type ChannelsMeta, type YM } from './api';

/** Platform ve kanallar ekranlarının ortak parçaları: kabuk, bölüm bağlantıları, dönem seçici, veri şeridi. */

export { AskSheet } from '../budget/parts';

const SECTIONS = [
  { to: '/kanallar', label: 'Kanal karnesi', page: 'kanallar' },
  { to: '/kanallar/matris', label: 'Kitap × kanal', page: 'matris' },
  { to: '/kanallar/d2c', label: 'D2C büyüme', page: 'd2c' },
  { to: '/kanallar/eslesme', label: 'Cari eşleme', page: 'eslesme' },
] as const;

export function useChannelsMeta() {
  return useQuery({ queryKey: ['channels', 'meta'], queryFn: channelsApi.meta, enabled: ENGINE_ENABLED, staleTime: 60_000 });
}

/** Dönem adres çubuğunda (?yil=, ?ay=): bağlantı paylaşılınca aynı karne açılır. */
export function usePeriod(meta: ChannelsMeta | undefined): YM & { set: (next: Record<string, string | null>) => void; params: URLSearchParams } {
  const [params, setParams] = useSearchParams();
  const yil = Number(params.get('yil')) || meta?.defaultYear || undefined;
  const ay = Number(params.get('ay')) || undefined;
  const set = useCallback(
    (next: Record<string, string | null>) => {
      const p = new URLSearchParams(params);
      for (const [k, v] of Object.entries(next)) {
        if (v) p.set(k, v);
        else p.delete(k);
      }
      setParams(p, { replace: true });
    },
    [params, setParams],
  );
  return { yil, ay, set, params };
}

export function ChannelsFrame({ title, lead, detail, back, aside, children }: {
  title: string;
  lead: string;
  detail?: string;
  back?: boolean;
  aside?: ReactNode;
  children: ReactNode;
}) {
  const meta = useChannelsMeta();
  const pages = meta.data?.me.pages;
  return (
    <Shell head={{ tenant: 'Timaş Yayınları', section: 'Platform', crumb: 'Kanallar', source: 'Logo · CRM · portal kaydı', presence: 'Kanal yönetimi', detail }}>
      <main className="absolute bottom-2 left-2 right-2 top-16 overflow-y-auto overscroll-contain sm:bottom-6 sm:left-6 sm:right-6 sm:top-[84px]">
        <ZoomStage>
          <div className="mx-auto flex w-full max-w-[1760px] flex-col gap-3 pb-6 lg:gap-4">
            <header className="relative z-20 flex flex-col gap-3 px-1 lg:flex-row lg:items-start lg:justify-between lg:gap-6">
              <div className="min-w-0">
                {back ? (
                  <Link to="/kanallar" className="inline-flex min-h-11 items-center gap-1 text-[11px] font-bold uppercase tracking-wide text-canvas-violet hover:underline sm:min-h-0">
                    <ChevronLeft aria-hidden className="h-3.5 w-3.5" />
                    Kanal karnesi
                  </Link>
                ) : (
                  <div className="text-[11px] font-bold uppercase tracking-wide text-canvas-violet">Platform · Kanallar</div>
                )}
                <h1 className="mt-0.5 break-words text-[22px] font-extrabold leading-tight tracking-tight sm:text-[28px]">{title}</h1>
                <p className="mt-1 max-w-[76ch] text-[12.5px] leading-snug text-canvas-muted">{lead}</p>
              </div>
              {aside && <div className="w-full shrink-0 lg:w-[460px]">{aside}</div>}
            </header>
            <nav aria-label="Kanal bölümleri" className="-mx-1 overflow-x-auto px-1">
              <div className="flex w-max min-w-full gap-1 rounded-2xl bg-slate-100 p-1">
                {SECTIONS.filter((s) => !pages || pages[s.page]).map((s) => (
                  <NavLink
                    key={s.to}
                    to={s.to}
                    end={s.to === '/kanallar'}
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
            {!ENGINE_ENABLED && <Note tone="warn">ZEKİ AI bağlantısı bu derlemede tanımlı değil.</Note>}
            {meta.error && <Note tone="err">{errText(meta.error, 'Kanal bilgisi açılamadı.')}</Note>}
            {children}
          </div>
        </ZoomStage>
      </main>
    </Shell>
  );
}

/** Yıl ve «şu aya kadar» seçimi. Ay boşsa verinin bittiği ay. */
export function PeriodPicker({ meta, yil, ay, onChange }: { meta: ChannelsMeta | undefined; yil?: number; ay?: number; onChange: (next: Record<string, string | null>) => void }) {
  const years = [...new Set([...(meta?.years ?? []), ...(yil ? [yil] : [])])].sort((a, b) => b - a);
  const months = meta?.months ?? [];
  return (
    <div className="grid grid-cols-2 gap-2">
      <label className="flex flex-col gap-1">
        <span className={labelCls}>Yıl</span>
        <select className={field} value={yil ?? ''} onChange={(e) => onChange({ yil: e.target.value || null, ay: null })}>
          {years.map((y) => <option key={y} value={y}>{y}</option>)}
        </select>
      </label>
      <label className="flex flex-col gap-1">
        <span className={labelCls}>Şu aya kadar</span>
        <select className={field} value={ay ?? ''} onChange={(e) => onChange({ ay: e.target.value || null })}>
          <option value="">Verinin son ayı</option>
          {months.map((m, i) => <option key={m} value={i + 1}>{m}</option>)}
        </select>
      </label>
    </div>
  );
}

/** Logo verisinin bittiği gün, okuma durumu, eşleme sonrası eksik kapsam ve yenile düğmesi. */
export function DataBar({ meta, yil }: { meta: ChannelsMeta | undefined; yil?: number }) {
  const qc = useQueryClient();
  const running = meta?.data.running;
  const status = useQuery({
    queryKey: ['channels', 'status'],
    queryFn: channelsApi.status,
    enabled: ENGINE_ENABLED && !!running,
    refetchInterval: (q) => (q.state.data && !q.state.data.running ? false : 4000),
  });
  useEffect(() => {
    if (running && status.data && !status.data.running) {
      qc.invalidateQueries({ queryKey: ['channels'] });
      if (status.data.error) toast.error(status.data.error);
      else toast.success('Kanal verisi güncellendi.');
    }
  }, [running, status.data, qc]);
  const refresh = useMutation({
    mutationFn: () => channelsApi.refresh(yil),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['channels', 'meta'] }),
    onError: (e) => toast.error(errText(e, 'Okuma başlatılamadı.') ?? ''),
  });
  if (!meta) return null;
  const d = meta.data;
  const read = yil ? d.years[String(yil)] : undefined;
  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center justify-between gap-2 rounded-2xl bg-white/70 px-3 py-2 text-[12px] font-semibold text-canvas-muted">
        <span className="min-w-0">
          {d.dataEnd ? <>Logo verisi <strong className="text-canvas-ink">{fmtDay(d.dataEnd)}</strong> tarihinde bitiyor. </> : 'Logo verisi henüz okunmadı. '}
          Rakamlar kanala satıştır (TİMAŞ'ın kanala faturaladığı); kanalın son tüketiciye sattığı adet yalnız yüklenen panel dosyasından gelir.
          {read?._at && <> · Son okuma {fmtDay(read._at)}</>}
          {running && <> · Okunuyor: {status.data?.step ?? d.step ?? '…'}</>}
          {d.error && !running && <span className="text-red-700"> · Son okuma: {d.error}</span>}
          {d.crm?.error && <span className="text-amber-800"> · CRM okunamadı: {d.crm.error}</span>}
        </span>
        <button type="button" className={btnGhost} onClick={() => refresh.mutate()} disabled={!!running || refresh.isPending}>
          {running || refresh.isPending ? <Loader2 aria-hidden className="h-4 w-4 animate-spin" /> : <RefreshCw aria-hidden className="h-4 w-4" />}
          Veriyi yenile
        </button>
      </div>
      {meta.missingScope.length > 0 && !running && (
        <Note tone="warn">
          Eşleme değişti: yeni eklenen carilerin {meta.missingScope.join(', ')} satışları henüz okunmadı. «Veriyi yenile» ile okunur; o zamana kadar karnede eksik kalır.
        </Note>
      )}
    </div>
  );
}

/** Oran rengi: artış iyi mi kötü mü (iade/iskonto artışı kötü). */
export function deltaTone(v: number | null | undefined, goodWhenUp = true): string {
  if (v === null || v === undefined || !Number.isFinite(v) || Math.abs(v) < 0.005) return 'text-canvas-muted';
  return (v > 0) === goodWhenUp ? 'text-emerald-700' : 'text-red-700';
}

export function signedPct(v: number | null | undefined): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return '—';
  const s = new Intl.NumberFormat('tr-TR', { style: 'percent', maximumFractionDigits: 1, signDisplay: 'exceptZero' }).format(v);
  return s;
}

/** Tek satırlık «anahtar: değer» ızgarası (kartlarda). */
export function Facts({ rows }: { rows: Array<[string, ReactNode]> }) {
  return (
    <dl className="grid grid-cols-[1fr_auto] gap-x-3 gap-y-0.5 text-[11.5px] leading-snug">
      {rows.map(([k, v]) => (
        <div key={k} className="contents">
          <dt className="text-canvas-muted">{k}</dt>
          <dd className="text-right font-mono tabular-nums text-canvas-ink">{v}</dd>
        </div>
      ))}
    </dl>
  );
}
