import { useEffect, useMemo, useRef, useState } from 'react';
import { useLocation } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { FileSpreadsheet, MapPin, Upload } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import { Loading, Note, btnGhost, errText } from '../admin/ui';
import { MONTHS, evApi, fileToBase64, fmtShort, type FairPlan as Plan, type PlanFair } from './api';
import { Block } from './parts';

/** Fuar takvimi: pazarlamanın FUARLAR.xlsx dosyası ekranda. Excel'deki ay × gün çizelgesi masaüstünde zaman çizelgesi
 *  (her fuar bir satır, çubuk başlangıçtan bitişe; TİMAŞ standı mor, bayi mavi; bugün çizgisi), telefonda aya göre kart
 *  listesi. Dosya köprüde okunur (`fair_plan.py`); yeni yükleme eskisinin yerine geçer. */

const DAY = 7; // px / gün (masaüstü çizelge)
const NAME_W = 280;

type Who = 'hepsi' | 'timas' | 'bayi';

const utc = (iso: string) => {
  const [y, m, d] = iso.split('-').map(Number);
  return Date.UTC(y, m - 1, d);
};
const dayDiff = (a: string, b: string) => Math.round((utc(b) - utc(a)) / 86_400_000);
const isoOf = (t: number) => new Date(t).toISOString().slice(0, 10);

export const isTimas = (f: PlanFair) => f.participant === 'timas';

export function planStatus(f: PlanFair): { text: string; cls: string } {
  if (f.phase === 'bitti') return { text: 'Bitti', cls: 'bg-slate-100 text-canvas-muted' };
  if (f.phase === 'suruyor') return { text: f.daysLeft === 0 ? 'Son gün' : `Sürüyor · ${f.daysLeft} gün kaldı`, cls: 'bg-emerald-50 text-emerald-700' };
  return {
    text: f.daysLeft === 1 ? 'Yarın' : `${f.daysLeft} gün sonra`,
    cls: f.daysLeft <= 7 ? 'bg-amber-50 text-amber-800' : 'bg-slate-100 text-canvas-ink',
  };
}

export function WhoPill({ f }: { f: PlanFair }) {
  if (!f.participantLabel) return null;
  return (
    <span className={`inline-flex shrink-0 items-center rounded-md px-1.5 py-0.5 text-[10.5px] font-extrabold uppercase tracking-wide ${
      isTimas(f) ? 'bg-canvas-violet/10 text-canvas-violet' : 'bg-sky-50 text-sky-700'
    }`}>
      {isTimas(f) ? 'TİMAŞ standı' : f.participantLabel}
    </span>
  );
}

export default function FairPlan() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ['ev', 'plan'], queryFn: evApi.plan, enabled: ENGINE_ENABLED, staleTime: 5 * 60_000 });
  const [who, setWho] = useState<Who>('hepsi');
  const fileRef = useRef<HTMLInputElement>(null);
  const boxRef = useRef<HTMLDivElement>(null);
  const { hash } = useLocation();
  const loaded = !!q.data;

  // Kampüs'teki «Fuar takvimi» bağlantısı (#fuar-takvimi): veri gelince bölüme kaydır.
  useEffect(() => {
    if (loaded && hash === '#fuar-takvimi') boxRef.current?.scrollIntoView({ block: 'start' });
  }, [loaded, hash]);

  const up = useMutation({
    mutationFn: async (f: File) => evApi.uploadPlan({ fileName: f.name, dataBase64: await fileToBase64(f) }),
    onSuccess: (d) => {
      qc.setQueryData(['ev', 'plan'], d);
      qc.invalidateQueries({ queryKey: ['ev', 'plan'] });
      toast.success(`Fuar takvimi güncellendi: ${d.items.length} fuar.`);
    },
    onError: (e) => toast.error(errText(e, 'Dosya okunamadı.') ?? ''),
  });

  const p = q.data;
  const all = p?.items ?? [];
  const items = useMemo(() => all.filter((f) => who === 'hepsi' || (who === 'timas' ? isTimas(f) : !isTimas(f))), [all, who]);
  const timasN = all.filter(isTimas).length;
  const live = all.filter((f) => f.phase === 'suruyor');
  const next = all.find((f) => f.phase === 'yaklasan');

  const action = (
    <div className="flex flex-wrap items-center gap-1.5">
      {all.length > 0 && (
        <div className="flex gap-1 rounded-xl bg-slate-100 p-1" role="group" aria-label="Katılımcı">
          {([['hepsi', `Hepsi ${all.length}`], ['timas', `TİMAŞ ${timasN}`], ['bayi', `Bayi ${all.length - timasN}`]] as Array<[Who, string]>).map(([k, v]) => (
            <button key={k} type="button" aria-pressed={who === k} onClick={() => setWho(k)}
              className={`inline-flex min-h-9 items-center rounded-lg px-2.5 text-[11.5px] font-bold transition-[background-color,color,transform] duration-150 active:scale-[0.97] ${
                who === k ? 'bg-white text-canvas-ink shadow-sm' : 'text-canvas-muted hover:text-canvas-ink'
              }`}>
              {v}
            </button>
          ))}
        </div>
      )}
      {p?.canEdit && (
        <>
          <input ref={fileRef} type="file" accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" className="hidden"
            onChange={(e) => {
              const f = e.target.files?.[0];
              e.target.value = '';
              if (f) up.mutate(f);
            }} />
          <button type="button" className={`${btnGhost} active:scale-[0.97]`} disabled={up.isPending} onClick={() => fileRef.current?.click()}>
            <Upload aria-hidden className="h-4 w-4" />
            {up.isPending ? 'Okunuyor…' : 'Excel yükle'}
          </button>
        </>
      )}
    </div>
  );

  const help = p?.uploadedAt
    ? `Pazarlamanın fuar listesi${p.fileName ? ` (${p.fileName})` : ''} · son yükleme ${fmtShort(p.uploadedAt.slice(0, 10))}${p.uploadedBy ? `, ${p.uploadedBy}` : ''}. Çubuk fuarın başlangıcından bitişine uzanır; mor TİMAŞ standı, mavi bayi.`
    : 'Pazarlamanın fuar listesi (Excel) burada çizelge olarak görünür.';

  return (
    <div id="fuar-takvimi" ref={boxRef} className="scroll-mt-4">
      <Block title="Fuar takvimi" help={help} action={action}>
        {q.isLoading && <Loading />}
        {q.error && <Note tone="err">{errText(q.error, 'Fuar takvimi açılamadı.')}</Note>}
        {p && all.length === 0 && (
          <div className="flex flex-col items-start gap-1 rounded-2xl border border-dashed border-slate-200 bg-white/60 p-4 text-[12.5px] text-canvas-muted">
            <FileSpreadsheet aria-hidden className="h-5 w-5 text-canvas-violet" />
            Henüz fuar takvimi yüklenmedi.{p.canEdit ? ' «Excel yükle» ile FUARLAR.xlsx dosyasını seçin; ay, gün, fuar alanı, düzenleyen ve katılımcı sütunları okunur.' : ''}
          </div>
        )}

        {all.length > 0 && (
          <div className="mb-3 grid grid-cols-2 gap-2 lg:grid-cols-4">
            <Stat label="Toplam fuar" value={String(all.length)} sub={`${fmtShort(all[0].startsOn)} – ${fmtShort(all[all.length - 1].endsOn)}`} />
            <Stat label="TİMAŞ standı" value={String(timasN)} sub={`${all.length - timasN} fuarda bayi`} tone="violet" />
            <Stat label="Şu an süren" value={String(live.length)} sub={live.length ? live.map((f) => f.name.replace(/ Kitap (Fuarı|Günleri)$/i, '')).join(', ') : 'yok'} tone="ok" />
            <Stat label="Sıradaki" value={next ? (next.daysLeft === 1 ? 'Yarın' : `${next.daysLeft} gün`) : '—'} sub={next ? next.name : 'yaklaşan fuar yok'} />
          </div>
        )}

        {items.length > 0 && p && (
          <>
            <div className="hidden md:block"><Gantt items={items} today={p.today} /></div>
            <div className="md:hidden"><MonthList items={items} /></div>
          </>
        )}
        {all.length > 0 && items.length === 0 && <p className="py-3 text-[12.5px] text-canvas-muted">Bu süzgeçte fuar yok.</p>}

        {p?.pending && p.pending.items.length > 0 && (
          <div className="mt-3 rounded-2xl bg-amber-50/70 p-3">
            <div className="text-[11px] font-bold uppercase tracking-wide text-amber-800">{p.pending.title || 'Tarihi netleşmeyen fuarlar'}</div>
            <div className="mt-1.5 flex flex-wrap gap-1.5">
              {p.pending.items.map((n) => (
                <span key={n} className="rounded-lg bg-white px-2 py-1 text-[12px] font-bold text-canvas-ink">{n}</span>
              ))}
            </div>
          </div>
        )}
        {p && p.warnings.length > 0 && (
          <details className="mt-2 text-[11.5px] text-canvas-muted">
            <summary className="cursor-pointer font-bold">Dosyadaki {p.warnings.length} uyarı</summary>
            <ul className="mt-1 list-disc pl-5">{p.warnings.map((w) => <li key={w}>{w}</li>)}</ul>
          </details>
        )}
      </Block>
    </div>
  );
}

function Stat({ label, value, sub, tone }: { label: string; value: string; sub: string; tone?: 'violet' | 'ok' }) {
  const c = tone === 'violet' ? 'text-canvas-violet' : tone === 'ok' ? 'text-emerald-700' : 'text-canvas-ink';
  return (
    <div className="min-w-0 rounded-2xl border border-slate-100 bg-white/80 px-3 py-2">
      <div className="text-[10.5px] font-bold uppercase tracking-wide text-canvas-muted">{label}</div>
      <div className={`font-mono text-[20px] font-extrabold tabular-nums leading-tight ${c}`}>{value}</div>
      <div className="truncate text-[11px] text-canvas-muted" title={sub}>{sub}</div>
    </div>
  );
}

/** Masaüstü: Excel'in ay × gün çizelgesi, kesintisiz zaman ekseninde. Ay başlarından ay sonlarına; ad sütunu sabit. */
function Gantt({ items, today }: { items: PlanFair[]; today: string }) {
  const scroller = useRef<HTMLDivElement>(null);
  const { start, total, months, groups } = useMemo(() => {
    const first = items.reduce((a, f) => (f.startsOn < a ? f.startsOn : a), items[0].startsOn);
    const last = items.reduce((a, f) => (f.endsOn > a ? f.endsOn : a), items[0].endsOn);
    const s = `${first.slice(0, 7)}-01`;
    const [ly, lm] = last.split('-').map(Number);
    const e = isoOf(Date.UTC(ly, lm, 0)); // son ayın son günü
    const ms: Array<{ key: string; label: string; x: number; w: number }> = [];
    for (let t = utc(s); t <= utc(e);) {
      const d = new Date(t);
      const next = Date.UTC(d.getUTCFullYear(), d.getUTCMonth() + 1, 1);
      ms.push({ key: isoOf(t), label: `${MONTHS[d.getUTCMonth()]} ${d.getUTCFullYear()}`, x: dayDiff(s, isoOf(t)) * DAY, w: ((next - t) / 86_400_000) * DAY });
      t = next;
    }
    const gs: Array<{ key: string; label: string; items: PlanFair[] }> = [];
    for (const f of items) {
      const k = f.startsOn.slice(0, 7);
      const g = gs[gs.length - 1];
      if (g && g.key === k) g.items.push(f);
      else gs.push({ key: k, label: `${MONTHS[Number(k.slice(5, 7)) - 1]} ${k.slice(0, 4)}`, items: [f] });
    }
    return { start: s, total: dayDiff(s, e) + 1, months: ms, groups: gs };
  }, [items]);

  const todayX = dayDiff(start, today) * DAY;
  const showToday = todayX >= 0 && todayX <= total * DAY;
  const width = total * DAY;

  // Açılışta bugün görünür olsun (çizelge geniş, geçmiş aylar solda kalır).
  useEffect(() => {
    const el = scroller.current;
    if (el && showToday) el.scrollLeft = Math.max(0, todayX - 3 * 7 * DAY);
  }, [showToday, todayX]);

  const ticks = (y: number) => (
    <>
      {months.map((m, i) => (
        <div key={m.key} aria-hidden className={`absolute inset-y-0 border-l border-slate-200/80 ${i % 2 ? 'bg-slate-50/60' : ''}`} style={{ left: m.x, width: m.w, top: y }} />
      ))}
      {showToday && <div aria-hidden className="absolute inset-y-0 z-[1] w-px bg-rose-500/70" style={{ left: todayX + DAY / 2 }} />}
    </>
  );

  return (
    <div ref={scroller} className="overflow-x-auto overscroll-x-contain rounded-2xl border border-slate-100 bg-white/80">
      <div style={{ width: NAME_W + width }} className="relative">
        {/* Ay ve gün başlığı */}
        <div className="sticky top-0 z-20 flex border-b border-slate-200 bg-white/95">
          <div className="sticky left-0 z-10 flex shrink-0 items-end border-r border-slate-200 bg-white px-3 pb-1.5 text-[10.5px] font-bold uppercase tracking-wide text-canvas-muted" style={{ width: NAME_W }}>
            Fuar
          </div>
          <div className="relative h-11 shrink-0" style={{ width }}>
            {months.map((m) => (
              <div key={m.key} className="absolute top-0 h-full border-l border-slate-200" style={{ left: m.x, width: m.w }}>
                <div className="truncate px-2 pt-1 text-[11.5px] font-extrabold text-canvas-ink">{m.label}</div>
                {[1, 8, 15, 22, 29].map((d) => d * DAY <= m.w && (
                  <span key={d} className="absolute bottom-1 font-mono text-[9.5px] tabular-nums text-canvas-muted" style={{ left: (d - 1) * DAY }}>{d}</span>
                ))}
              </div>
            ))}
            {showToday && (
              <span className="absolute bottom-0 z-[2] -translate-x-1/2 rounded-t-md bg-rose-500 px-1.5 text-[9.5px] font-extrabold uppercase text-white" style={{ left: todayX + DAY / 2 }}>
                Bugün
              </span>
            )}
          </div>
        </div>

        {groups.map((g) => (
          <div key={g.key}>
            <div className="flex border-b border-slate-100 bg-slate-50/90">
              <div className="sticky left-0 z-10 shrink-0 border-r border-slate-200 bg-slate-50 px-3 py-1 text-[11px] font-extrabold uppercase tracking-wide text-canvas-violet" style={{ width: NAME_W }}>
                {g.label} <span className="font-mono text-canvas-muted">· {g.items.length}</span>
              </div>
              <div className="relative shrink-0" style={{ width }}>{ticks(0)}</div>
            </div>
            {g.items.map((f) => {
              const x = dayDiff(start, f.startsOn) * DAY;
              const w = Math.max(DAY, f.days * DAY);
              const st = planStatus(f);
              const tip = [f.name, `${fmtShort(f.startsOn)} – ${fmtShort(f.endsOn)} · ${f.days} gün`, f.venue, f.organizer && `Düzenleyen: ${f.organizer}`, f.participantLabel && `Katılımcı: ${f.participantLabel}`].filter(Boolean).join('\n');
              return (
                <div key={f.id} className={`group flex border-b border-slate-100 last:border-b-0 ${f.phase === 'bitti' ? 'opacity-55' : ''}`}>
                  <div className="sticky left-0 z-10 shrink-0 border-r border-slate-200 bg-white px-3 py-1.5 transition-colors duration-150 group-hover:bg-slate-50" style={{ width: NAME_W }}>
                    <div className="flex min-w-0 items-center gap-1.5">
                      <span className="min-w-0 flex-1 truncate text-[12.5px] font-extrabold" title={f.name}>{f.name}</span>
                      {isTimas(f) && <span className="shrink-0 rounded bg-canvas-violet/10 px-1 text-[9.5px] font-extrabold text-canvas-violet">TİMAŞ</span>}
                    </div>
                    <div className="truncate text-[11px] text-canvas-muted" title={[f.venue, f.organizer].filter(Boolean).join(' · ')}>
                      <span className="font-mono tabular-nums">{fmtShort(f.startsOn)} – {fmtShort(f.endsOn)}</span>
                      {f.venue ? ` · ${f.venue}` : ''}{f.organizer ? ` · ${f.organizer}` : ''}
                    </div>
                  </div>
                  <div className="relative shrink-0" style={{ width }}>
                    {ticks(0)}
                    <div title={tip}
                      className={`absolute top-1/2 z-[2] flex h-6 -translate-y-1/2 items-center overflow-hidden rounded-md px-1.5 text-[10.5px] font-extrabold text-white shadow-sm ${
                        isTimas(f) ? 'bg-canvas-violet' : 'bg-sky-500'
                      } ${f.phase === 'suruyor' ? 'ring-2 ring-emerald-400 ring-offset-1' : ''}`}
                      style={{ left: x, width: w }}>
                      {w >= 44 && <span className="truncate">{f.days} gün</span>}
                    </div>
                    {f.phase !== 'bitti' && (
                      <span className={`absolute top-1/2 z-[2] ml-2 -translate-y-1/2 whitespace-nowrap rounded-md px-1.5 py-0.5 text-[10.5px] font-bold ${st.cls}`} style={{ left: x + w }}>
                        {st.text}
                      </span>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        ))}
      </div>
    </div>
  );
}

/** Telefon: aya göre kartlar (yatay çizelge dar ekranda okunmuyor). */
function MonthList({ items }: { items: PlanFair[] }) {
  const groups = useMemo(() => {
    const gs: Array<{ key: string; items: PlanFair[] }> = [];
    for (const f of items) {
      const k = f.startsOn.slice(0, 7);
      const g = gs[gs.length - 1];
      if (g && g.key === k) g.items.push(f);
      else gs.push({ key: k, items: [f] });
    }
    return gs;
  }, [items]);
  return (
    <div className="flex flex-col gap-3">
      {groups.map((g) => (
        <section key={g.key}>
          <h3 className="mb-1.5 px-1 text-[11.5px] font-extrabold uppercase tracking-wide text-canvas-violet">
            {MONTHS[Number(g.key.slice(5, 7)) - 1]} {g.key.slice(0, 4)} <span className="font-mono text-canvas-muted">· {g.items.length}</span>
          </h3>
          <ul className="flex flex-col gap-1.5">
            {g.items.map((f) => {
              const st = planStatus(f);
              return (
                <li key={f.id} className={`flex gap-2.5 rounded-2xl border border-slate-100 bg-white/85 p-2.5 ${f.phase === 'bitti' ? 'opacity-60' : ''}`}>
                  <div className={`w-1 shrink-0 rounded-full ${isTimas(f) ? 'bg-canvas-violet' : 'bg-sky-500'}`} aria-hidden />
                  <div className="min-w-0 flex-1">
                    <div className="flex items-start justify-between gap-2">
                      <span className="min-w-0 text-[13px] font-extrabold leading-snug">{f.name}</span>
                      <WhoPill f={f} />
                    </div>
                    <div className="mt-0.5 font-mono text-[11.5px] tabular-nums text-canvas-ink">{fmtShort(f.startsOn)} – {fmtShort(f.endsOn)} · {f.days} gün</div>
                    {(f.venue || f.organizer) && (
                      <div className="mt-0.5 flex items-start gap-1 text-[11.5px] text-canvas-muted">
                        <MapPin aria-hidden className="mt-0.5 h-3 w-3 shrink-0" />
                        <span className="min-w-0">{[f.venue, f.organizer].filter(Boolean).join(' · ')}</span>
                      </div>
                    )}
                    <span className={`mt-1.5 inline-flex rounded-md px-1.5 py-0.5 text-[10.5px] font-bold ${st.cls}`}>{st.text}</span>
                  </div>
                </li>
              );
            })}
          </ul>
        </section>
      ))}
    </div>
  );
}
