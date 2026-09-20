import { useEffect, useMemo, useState } from 'react';
import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { ChevronLeft, ChevronRight, Loader2, Search } from 'lucide-react';
import Shell, { ZoomStage } from '../stitch/Shell';
import { railFor } from '../stitch/screens';
import DbTimingBadge from '../DbTiming';
import { ENGINE_ENABLED, contractsApi, type Contract, type ContractSummary } from '../engine';
import { Note, Pill, btnGhost, errText, field, nf } from '../admin/ui';
import { dateTime, pct } from '../format';

/** M6 Telif & Sözleşme. Sözleşme portföyü CRM'den okunur; CRM'de kaydı olmayan şey (hakediş,
 *  ödeme takvimi, telif kademesi) ekranda yer almaz. */

const money = new Intl.NumberFormat('tr-TR', { maximumFractionDigits: 0 });

function useDebounced<T>(value: T, ms: number): T {
  const [v, setV] = useState(value);
  useEffect(() => {
    const id = window.setTimeout(() => setV(value), ms);
    return () => window.clearTimeout(id);
  }, [value, ms]);
  return v;
}

const statusTone = (s: string | null): 'ok' | 'warn' | 'err' | 'muted' => {
  const t = (s || '').toLocaleLowerCase('tr');
  if (t.includes('yenileme')) return 'warn';
  if (t.startsWith('aktif')) return 'ok';
  if (t.includes('fesih') || t.includes('iptal')) return 'err';
  return 'muted';
};

function DaysLeft({ c, warnDays }: { c: Contract; warnDays: number }) {
  if (c.openEnded) return <Pill tone="muted">Süresiz</Pill>;
  if (c.daysLeft == null) return null;
  if (c.daysLeft < 0) return <Pill tone="muted">{nf.format(-c.daysLeft)} gün önce bitti</Pill>;
  return <Pill tone={c.daysLeft <= warnDays ? 'err' : 'muted'}>{nf.format(c.daysLeft)} gün kaldı</Pill>;
}

function Parties({ c }: { c: Contract }) {
  if (!c.parties.length) return <span className="text-canvas-muted">Taraf kaydı yok</span>;
  return (
    <ul className="space-y-0.5">
      {c.parties.map((p, i) => (
        <li key={`${p.name}-${i}`} className="flex flex-wrap items-baseline gap-x-1.5">
          <span className="font-semibold">{p.name}</span>
          {p.share != null && <span className="font-mono text-[11px] tabular-nums text-canvas-muted">{pct(p.share, 0)}</span>}
          {p.viaAgent && <span className="text-[11px] text-canvas-muted">aracılı</span>}
        </li>
      ))}
    </ul>
  );
}

function Rates({ c }: { c: Contract }) {
  if (!c.rates.length) return <span className="text-canvas-muted">Oran girilmemiş</span>;
  return (
    <div className="flex flex-wrap gap-1">
      {c.rates.map((r) => (
        <span key={r.format} className="inline-flex items-baseline gap-1 rounded-md bg-slate-100 px-1.5 py-0.5 text-[11px]">
          <span className="text-canvas-muted">{r.format}</span>
          <span className="font-mono font-bold tabular-nums">{pct(r.percent, 0)}</span>
        </span>
      ))}
    </div>
  );
}

function Title({ c }: { c: Contract }) {
  const books = c.books.map((b) => b.title);
  return (
    <div className="min-w-0">
      <div className="break-words font-extrabold leading-snug">{books.length ? books.join(' · ') : 'Kitap bağlanmamış'}</div>
      <div className="mt-0.5 font-mono text-[11px] text-canvas-muted">{c.no || c.code || '—'}</div>
    </div>
  );
}

function Terms({ c }: { c: Contract }) {
  const advance = c.advance ? `Avans ${money.format(c.advance)}${c.currency ? ` ${c.currency}` : ''}` : null;
  const parts = [c.kind, c.payment, c.basis, advance].filter(Boolean);
  return <div className="text-[11px] leading-snug text-canvas-muted">{parts.join(' · ') || '—'}</div>;
}

function Period({ c }: { c: Contract }) {
  if (!c.start && !c.end) return <span className="text-canvas-muted">Tarih girilmemiş</span>;
  return (
    <span className="whitespace-nowrap font-mono text-[11.5px] tabular-nums">
      {dateTime(c.start)} – {c.openEnded ? 'süresiz' : dateTime(c.end)}
    </span>
  );
}

function Kpi({ label, value, help, active, onClick }: { label: string; value: string; help: string; active?: boolean; onClick?: () => void }) {
  const body = (
    <>
      <div className="text-[11px] font-bold uppercase tracking-wide text-canvas-muted">{label}</div>
      <div className="mt-1 font-mono text-[26px] font-bold leading-none tabular-nums tracking-tight sm:text-[30px]">{value}</div>
      <div className="mt-1.5 text-[11.5px] leading-snug text-canvas-muted">{help}</div>
    </>
  );
  const cls = `glass-panel rounded-2xl p-3.5 text-left shadow-glass-float sm:rounded-3xl sm:p-4 ${active ? 'ring-2 ring-canvas-violet' : ''}`;
  if (!onClick) return <div className={cls}>{body}</div>;
  return (
    <button type="button" onClick={onClick} aria-pressed={active} className={`${cls} transition-transform duration-150 ease-out active:scale-[0.98]`}>
      {body}
    </button>
  );
}

function Kpis({ s, expiring, onExpiring }: { s: ContractSummary; expiring: boolean; onExpiring: () => void }) {
  return (
    <div className="grid grid-cols-2 gap-2.5 lg:grid-cols-4 lg:gap-4">
      <Kpi label="Yürürlükte" value={nf.format(s.active)} help={`${nf.format(s.total)} etkin kayıt içinde`} />
      <Kpi label="Yenilemede" value={nf.format(s.renewal)} help="Durumu “Aktif - Yenileme”" />
      <Kpi
        label={`${s.warnDays} günde bitiyor`}
        value={nf.format(s.expiring)}
        help={expiring ? 'Süzgeç açık; kapatmak için dokunun' : 'Listede görmek için dokunun'}
        active={expiring}
        onClick={onExpiring}
      />
      <Kpi label="Ortalama telif" value={pct(s.avgRoyalty, 1)} help={`Karton kapak oranı dolu ${nf.format(s.avgRoyaltyOver)} yürürlükteki sözleşme`} />
    </div>
  );
}

export default function ContractsScreen() {
  const [text, setText] = useState('');
  const [status, setStatus] = useState('');
  const [kind, setKind] = useState('');
  const [expiring, setExpiring] = useState(false);
  const [order, setOrder] = useState('bitis');
  const [page, setPage] = useState(0);
  const q = useDebounced(text.trim(), 350);

  useEffect(() => setPage(0), [q, status, kind, expiring, order]);

  const summary = useQuery({ queryKey: ['editorial', 'contracts', 'summary'], queryFn: contractsApi.summary, enabled: ENGINE_ENABLED });
  const list = useQuery({
    queryKey: ['editorial', 'contracts', q, status, kind, expiring, order, page],
    queryFn: () =>
      contractsApi.list({ q, status: status ? Number(status) : undefined, kind: kind ? Number(kind) : undefined, expiring, order, page }),
    enabled: ENGINE_ENABLED,
    placeholderData: keepPreviousData,
  });

  const s = summary.data;
  const data = list.data;
  const items = data?.items ?? [];
  const warnDays = s?.warnDays ?? 60;
  const range = useMemo(() => {
    if (!data || !data.total) return '';
    const from = data.page * data.pageSize + 1;
    return `${nf.format(from)}–${nf.format(from + items.length - 1)} / ${nf.format(data.total)}`;
  }, [data, items.length]);
  const lastPage = data ? (data.page + 1) * data.pageSize >= data.total : true;
  const err = errText(summary.error || list.error, 'Sözleşmeler okunamadı.');

  return (
    <Shell
      head={{
        tenant: 'Timaş Yayınları',
        section: 'Editoryal Süreç',
        crumb: 'M6 Telif & Sözleşme',
        source: s ? `${nf.format(s.active)} yürürlükte sözleşme` : 'CRM sözleşmeleri',
        presence: 'Kaynak: CRM',
      }}
      rail={railFor('/telif-sozlesme')}
    >
      <main className="absolute bottom-2 left-14 right-2 top-16 overflow-y-auto overscroll-contain sm:bottom-6 sm:left-[92px] sm:right-6 sm:top-[84px]">
        <ZoomStage>
          <div className="mx-auto flex w-full max-w-[1760px] flex-col gap-3 pb-6 lg:gap-4">
            <header className="px-1">
              <div className="text-[11px] font-bold uppercase tracking-wide text-canvas-violet">M6 · Editoryal Süreç</div>
              <h1 className="mt-0.5 text-[22px] font-extrabold leading-tight tracking-tight sm:text-[28px]">Telif ve lisans sözleşmeleri</h1>
              <p className="mt-1 max-w-[70ch] text-[12.5px] leading-snug text-canvas-muted">
                CRM'deki sözleşme kayıtları: kitap, hak sahibi, telif oranları, süre ve durum. Hakediş ve ödeme takvimi CRM'de tutulmadığı için burada yok.
              </p>
            </header>

            {!ENGINE_ENABLED && <Note tone="warn">Zeki AI bağlantısı bu derlemede tanımlı değil.</Note>}
            {err && <Note tone="err">{err}</Note>}
            {s && <Kpis s={s} expiring={expiring} onExpiring={() => setExpiring((v) => !v)} />}

            <section className="glass-panel rounded-2xl p-3 shadow-glass-float sm:rounded-3xl sm:p-4">
              <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-[minmax(0,1fr)_200px_180px_170px]">
                <label className="relative block">
                  <span className="sr-only">Sözleşmelerde ara</span>
                  <Search aria-hidden className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-canvas-muted" />
                  <input
                    type="search"
                    value={text}
                    onChange={(e) => setText(e.target.value)}
                    placeholder="Kitap, hak sahibi ya da sözleşme no"
                    className={`${field} pl-9`}
                  />
                </label>
                <select aria-label="Durum" value={status} onChange={(e) => setStatus(e.target.value)} className={field}>
                  <option value="">Tüm durumlar</option>
                  {s?.statuses.map((o) => (
                    <option key={o.code} value={o.code}>
                      {o.label} ({nf.format(o.count)})
                    </option>
                  ))}
                </select>
                <select aria-label="Sözleşme tipi" value={kind} onChange={(e) => setKind(e.target.value)} className={field}>
                  <option value="">Tüm tipler</option>
                  {s?.kinds.map((o) => (
                    <option key={o.code} value={o.code}>
                      {o.label} ({nf.format(o.count)})
                    </option>
                  ))}
                </select>
                <select aria-label="Sıralama" value={order} onChange={(e) => setOrder(e.target.value)} className={field}>
                  <option value="bitis">Bitişi en yakın</option>
                  <option value="yeni">Son değişen</option>
                  <option value="no">Sözleşme no</option>
                </select>
              </div>

              <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
                <div className="flex min-w-0 items-center gap-2 text-[12px] font-semibold text-canvas-muted">
                  {list.isFetching && <Loader2 aria-hidden className="h-3.5 w-3.5 animate-spin" />}
                  <span className="font-mono tabular-nums">{range || (list.isLoading ? 'Okunuyor…' : 'Kayıt yok')}</span>
                  <DbTimingBadge timing={data?.db ?? null} />
                </div>
                <div className="flex gap-1.5">
                  <button type="button" className={btnGhost} disabled={page === 0 || list.isFetching} onClick={() => setPage((p) => Math.max(0, p - 1))}>
                    <ChevronLeft aria-hidden className="h-4 w-4" />
                    Önceki
                  </button>
                  <button type="button" className={btnGhost} disabled={lastPage || list.isFetching} onClick={() => setPage((p) => p + 1)}>
                    Sonraki
                    <ChevronRight aria-hidden className="h-4 w-4" />
                  </button>
                </div>
              </div>

              {!list.isLoading && !items.length && !err && (
                <p className="py-10 text-center text-[12.5px] text-canvas-muted">Bu süzgece uyan sözleşme yok.</p>
              )}

              {/* Telefon ve tablet: kart listesi. */}
              <ul className="mt-3 space-y-2 lg:hidden">
                {items.map((c) => (
                  <li key={c.id} className="rounded-2xl border border-slate-100 bg-white/85 p-3 text-[12.5px]">
                    <div className="flex items-start justify-between gap-2">
                      <Title c={c} />
                      {c.status && <Pill tone={statusTone(c.status)}>{c.status}</Pill>}
                    </div>
                    <div className="mt-2">
                      <Parties c={c} />
                    </div>
                    <div className="mt-2">
                      <Rates c={c} />
                    </div>
                    <div className="mt-1.5">
                      <Terms c={c} />
                    </div>
                    <div className="mt-2 flex flex-wrap items-center gap-2">
                      <Period c={c} />
                      <DaysLeft c={c} warnDays={warnDays} />
                    </div>
                  </li>
                ))}
              </ul>

              {/* Masaüstü: tablo. */}
              {items.length > 0 && (
                <div className="mt-3 hidden overflow-x-auto rounded-2xl border border-slate-100 bg-white/85 lg:block">
                  <table className="w-full text-[12.5px]">
                    <thead>
                      <tr className="border-b border-slate-100 text-left text-[11px] font-bold uppercase tracking-wide text-canvas-muted">
                        <th className="px-3 py-2.5">Kitap ve sözleşme no</th>
                        <th className="px-3 py-2.5">Hak sahibi</th>
                        <th className="px-3 py-2.5">Telif oranları</th>
                        <th className="px-3 py-2.5">Süre</th>
                        <th className="px-3 py-2.5">Durum</th>
                      </tr>
                    </thead>
                    <tbody>
                      {items.map((c) => (
                        <tr key={c.id} className="border-b border-slate-100 align-top last:border-0">
                          <td className="max-w-[340px] px-3 py-2.5">
                            <Title c={c} />
                          </td>
                          <td className="max-w-[280px] px-3 py-2.5">
                            <Parties c={c} />
                          </td>
                          <td className="max-w-[320px] px-3 py-2.5">
                            <Rates c={c} />
                            <div className="mt-1">
                              <Terms c={c} />
                            </div>
                          </td>
                          <td className="px-3 py-2.5">
                            <Period c={c} />
                            <div className="mt-1">
                              <DaysLeft c={c} warnDays={warnDays} />
                            </div>
                          </td>
                          <td className="px-3 py-2.5">
                            {c.status && <Pill tone={statusTone(c.status)}>{c.status}</Pill>}
                            {c.stage && <div className="mt-1 text-[11px] leading-snug text-canvas-muted">{c.stage}</div>}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </section>
          </div>
        </ZoomStage>
      </main>
    </Shell>
  );
}
