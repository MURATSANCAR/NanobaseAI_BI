import { useMemo, useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { CalendarClock, Download, Loader2, Mail, Pause, PencilLine, Play, Plus, Sparkles, Trash2, X } from 'lucide-react';
import Shell from '../stitch/Shell';
import { railFor } from '../stitch/screens';
import {
  ENGINE_ENABLED,
  EngineAuthError,
  reportsApi,
  type ReportDraft,
  type ReportDto,
  type ReportFormat,
  type ReportInput,
  type ReportLastStatus,
  type ReportRecurrence,
} from '../engine';

const nf = new Intl.NumberFormat('tr-TR');
const dtf = new Intl.DateTimeFormat('tr-TR', {
  timeZone: 'Europe/Istanbul',
  day: '2-digit',
  month: 'short',
  hour: '2-digit',
  minute: '2-digit',
});
const fmtDate = (iso: string | null) => (iso ? dtf.format(new Date(iso)) : '—');

const WEEKDAYS = ['Pazartesi', 'Salı', 'Çarşamba', 'Perşembe', 'Cuma', 'Cumartesi', 'Pazar'];
const RECURRENCE: Array<{ v: ReportRecurrence; label: string }> = [
  { v: 'daily', label: 'Her gün' },
  { v: 'weekly', label: 'Haftalık' },
  { v: 'monthly', label: 'Aylık' },
  { v: 'once', label: 'Bir kez' },
];

const LAST: Record<Exclude<ReportLastStatus, null>, { label: string; tone: string }> = {
  sent: { label: 'Gönderildi', tone: 'bg-emerald-50 text-emerald-700' },
  no_smtp: { label: 'Dosya hazır · e-posta ayarı yok', tone: 'bg-amber-50 text-amber-800' },
  no_recipient: { label: 'Dosya hazır · alıcı yok', tone: 'bg-slate-100 text-canvas-ink' },
  failed: { label: 'Hata', tone: 'bg-red-50 text-red-700' },
};

const EXAMPLE = "Her pazartesi 08:30'da geçen haftanın yayınevlerine göre net cirosunu Excel olarak ad@timas.com.tr'ye gönder";

/** Formun tuttuğu plan; yeni raporda cümleden, düzenlemede kayıttan dolar. */
type Plan = {
  title: string;
  question: string;
  recurrence: ReportRecurrence;
  at: string;
  weekday: number;
  monthday: number;
  onceAt: string;
  recipients: string;
  fmt: ReportFormat;
};

/** datetime-local alanı İstanbul saatini gösterir (UTC+3, yaz saati yok). */
const IST_MS = 3 * 3600_000;
const toLocalInput = (iso: string | null) => (iso ? new Date(new Date(iso).getTime() + IST_MS).toISOString().slice(0, 16) : '');
const tomorrowAt = (at: string) => `${new Date(Date.now() + IST_MS + 86_400_000).toISOString().slice(0, 10)}T${at}`;

const fromDraft = (d: ReportDraft): Plan => ({
  title: d.title,
  question: d.question,
  recurrence: d.recurrence,
  at: d.at,
  weekday: d.weekday ?? 0,
  monthday: d.monthday ?? 1,
  onceAt: tomorrowAt(d.at),
  recipients: d.recipients.join(', '),
  fmt: d.fmt,
});

const fromReport = (r: ReportDto): Plan => ({
  title: r.title,
  question: r.question,
  recurrence: r.recurrence,
  at: r.at,
  weekday: r.weekday ?? 0,
  monthday: r.monthday ?? 1,
  onceAt: toLocalInput(r.onceAt) || tomorrowAt(r.at),
  recipients: r.recipients.join(', '),
  fmt: r.fmt,
});

const toInput = (p: Plan): ReportInput => ({
  title: p.title.trim(),
  question: p.question.trim(),
  recurrence: p.recurrence,
  at: p.recurrence === 'once' && p.onceAt ? p.onceAt.slice(11, 16) : p.at,
  weekday: p.recurrence === 'weekly' ? p.weekday : null,
  monthday: p.recurrence === 'monthly' ? p.monthday : null,
  onceAt: p.recurrence === 'once' && p.onceAt ? `${p.onceAt}:00+03:00` : null,
  recipients: p.recipients
    .split(/[,;\s]+/)
    .map((s) => s.trim())
    .filter(Boolean),
  fmt: p.fmt,
});

const errMsg = (e: unknown, fallback: string) =>
  e instanceof EngineAuthError ? 'Oturum gerekli.' : e ? (e as Error).message || fallback : null;

const btn =
  'flex min-h-11 items-center gap-1.5 rounded-xl px-4 py-2.5 text-[12.5px] font-extrabold transition-transform duration-150 ease-out active:scale-[0.97] disabled:opacity-50 disabled:active:scale-100 sm:min-h-0';
const field =
  'mt-1 w-full rounded-xl border border-slate-200 bg-white/90 px-3 py-2 text-base font-semibold outline-none focus:border-canvas-violet sm:text-[12.5px]';
const label = 'text-[11px] font-bold text-canvas-muted';
const chip = (on: boolean, onTone: string) =>
  ['min-h-11 rounded-xl px-3 py-1.5 text-[12px] font-bold transition-colors sm:min-h-0', on ? onTone : 'bg-slate-100 text-canvas-ink hover:bg-slate-200'].join(' ');

function PlanForm({ plan, onChange }: { plan: Plan; onChange: (p: Plan) => void }) {
  const set = <K extends keyof Plan>(k: K, v: Plan[K]) => onChange({ ...plan, [k]: v });
  return (
    <div className="space-y-4">
      <div>
        <label className={label} htmlFor="rp-title">
          Başlık
        </label>
        <input id="rp-title" value={plan.title} onChange={(e) => set('title', e.target.value)} className={field} />
      </div>
      <div>
        <label className={label} htmlFor="rp-q">
          Veri sorusu <span className="font-normal">(her çalışmada yeniden sorulur; “bu ay” o günü anlatır)</span>
        </label>
        <textarea id="rp-q" rows={2} value={plan.question} onChange={(e) => set('question', e.target.value)} className={field} />
      </div>

      <div>
        <div className={label}>Ne zaman</div>
        <div className="mt-1 flex flex-wrap gap-1.5">
          {RECURRENCE.map((r) => (
            <button
              key={r.v}
              type="button"
              onClick={() => set('recurrence', r.v)}
              aria-pressed={plan.recurrence === r.v}
              className={chip(plan.recurrence === r.v, 'bg-canvas-violet text-white shadow-sm')}
            >
              {r.label}
            </button>
          ))}
        </div>
        <div className="mt-2 flex flex-wrap items-end gap-3">
          {plan.recurrence === 'weekly' && (
            <div>
              <label className={label} htmlFor="rp-wd">
                Gün
              </label>
              <select id="rp-wd" value={plan.weekday} onChange={(e) => set('weekday', Number(e.target.value))} className={field}>
                {WEEKDAYS.map((w, i) => (
                  <option key={w} value={i}>
                    {w}
                  </option>
                ))}
              </select>
            </div>
          )}
          {plan.recurrence === 'monthly' && (
            <div>
              <label className={label} htmlFor="rp-md">
                Ayın kaçı
              </label>
              <input
                id="rp-md"
                type="number"
                min={1}
                max={28}
                value={plan.monthday}
                onChange={(e) => set('monthday', Math.max(1, Math.min(28, Number(e.target.value) || 1)))}
                className={`${field} w-24 tabular-nums`}
              />
            </div>
          )}
          {plan.recurrence === 'once' ? (
            <div>
              <label className={label} htmlFor="rp-once">
                Tarih ve saat
              </label>
              <input id="rp-once" type="datetime-local" value={plan.onceAt} onChange={(e) => set('onceAt', e.target.value)} className={field} />
            </div>
          ) : (
            <div>
              <label className={label} htmlFor="rp-at">
                Saat
              </label>
              <input id="rp-at" type="time" value={plan.at} onChange={(e) => set('at', e.target.value)} className={`${field} w-32 tabular-nums`} />
            </div>
          )}
        </div>
      </div>

      <div className="grid gap-3 sm:grid-cols-[1fr_auto]">
        <div>
          <label className={label} htmlFor="rp-to">
            Alıcılar <span className="font-normal">(virgülle; boşsa yalnız dosya üretilir)</span>
          </label>
          <input
            id="rp-to"
            value={plan.recipients}
            onChange={(e) => set('recipients', e.target.value)}
            placeholder="ad@timas.com.tr, ekip@timas.com.tr"
            autoCapitalize="none"
            spellCheck={false}
            className={field}
          />
        </div>
        <div>
          <div className={label}>Biçim</div>
          <div className="mt-1 flex gap-1.5">
            {(['xlsx', 'csv'] as const).map((f) => (
              <button key={f} type="button" onClick={() => set('fmt', f)} aria-pressed={plan.fmt === f} className={chip(plan.fmt === f, 'bg-canvas-ink text-white')}>
                {f === 'xlsx' ? 'Excel' : 'CSV'}
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

function Preview({ draft }: { draft: ReportDraft }) {
  const cols = draft.columns.map((c) => c.name);
  const rows = draft.records.slice(0, 20);
  return (
    <div>
      <div className="flex flex-wrap items-baseline justify-between gap-x-2">
        <div className={label}>Önizleme</div>
        <div className="text-[11px] text-canvas-muted">
          {draft.rowCount != null ? `${nf.format(draft.rowCount)} satır · ` : ''}ilk {rows.length} satır; dosyaya tamamı yazılır
        </div>
      </div>
      {draft.summary && <p className="mt-1 text-[12.5px] leading-snug text-canvas-ink">{draft.summary}</p>}
      {cols.length > 0 ? (
        <div className="mt-1.5 max-h-72 overflow-auto rounded-xl border border-slate-100">
          <table className="w-full text-[11.5px]">
            <thead className="sticky top-0 bg-slate-50">
              <tr>
                {cols.map((c) => (
                  <th key={c} className="whitespace-nowrap px-2.5 py-1.5 text-left font-bold">
                    {c}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((r, i) => (
                <tr key={i} className="odd:bg-slate-50/60">
                  {cols.map((c) => {
                    const v = r[c];
                    const num = typeof v === 'number';
                    return (
                      <td key={c} className={`whitespace-nowrap px-2.5 py-1 ${num ? 'text-right font-mono tabular-nums' : ''}`}>
                        {num ? nf.format(v) : String(v ?? '—')}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="mt-1.5 rounded-xl bg-slate-50 px-3 py-2 text-[12px] text-canvas-muted">
          Soru satır döndürmedi. Veri sorusunu değiştirip yeniden deneyin.
        </div>
      )}
      {draft.sql && (
        <details className="mt-2">
          <summary className="cursor-pointer text-[11px] font-bold text-canvas-muted">Üretilen SQL</summary>
          <pre className="mt-1 max-h-48 overflow-auto rounded-xl bg-slate-900 p-3 text-[11px] leading-relaxed text-slate-100">{draft.sql}</pre>
        </details>
      )}
    </div>
  );
}

function Stat({ k, v }: { k: string; v: string }) {
  return (
    <div>
      <div className="text-[11px] font-bold uppercase tracking-wide text-canvas-muted">{k}</div>
      <div className="font-semibold tabular-nums">{v}</div>
    </div>
  );
}

export default function ReportsScreen() {
  const qc = useQueryClient();
  /** '' = yeni rapor; aksi halde seçili raporun kimliği. */
  const [sel, setSel] = useState('');
  const [text, setText] = useState('');
  const [draft, setDraft] = useState<ReportDraft | null>(null);
  const [plan, setPlan] = useState<Plan | null>(null);
  const [editing, setEditing] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [done, setDone] = useState<string | null>(null);
  const detailRef = useRef<HTMLDivElement | null>(null);

  const list = useQuery({
    queryKey: ['planli-raporlar'],
    queryFn: reportsApi.list,
    enabled: ENGINE_ENABLED,
    staleTime: 20_000,
    refetchInterval: 60_000,
    retry: false,
  });
  const reports = useMemo(() => list.data?.reports ?? [], [list.data]);
  const cur = reports.find((r) => r.id === sel) ?? null;
  const email = list.data?.email;
  const authRequired = list.error instanceof EngineAuthError;

  const flash = (msg: string) => {
    setDone(msg);
    window.setTimeout(() => setDone(null), 2500);
  };
  const refresh = () => qc.invalidateQueries({ queryKey: ['planli-raporlar'] });

  const open = (id: string) => {
    setSel(id);
    setEditing(false);
    setConfirmDelete(false);
    if (window.innerWidth < 768) {
      const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
      requestAnimationFrame(() => detailRef.current?.scrollIntoView({ behavior: reduce ? 'auto' : 'smooth', block: 'start' }));
    }
  };
  const startNew = () => {
    open('');
    setDraft(null);
    setPlan(null);
    setText('');
  };

  const parse = useMutation({
    mutationFn: (t: string) => reportsApi.parse(t),
    onSuccess: (d) => {
      setDraft(d);
      setPlan(fromDraft(d));
    },
  });

  const create = useMutation({
    mutationFn: (p: Plan) => reportsApi.create({ ...toInput(p), prompt: text.trim() || undefined, sql: draft?.sql || undefined }),
    onSuccess: async (r) => {
      await refresh();
      setDraft(null);
      setPlan(null);
      setText('');
      open(r.id);
      flash('Rapor planlandı');
    },
  });

  const update = useMutation({
    mutationFn: ({ id, body }: { id: string; body: Partial<ReportInput> }) => reportsApi.update(id, body),
    onSuccess: async (_r, v) => {
      await refresh();
      setEditing(false);
      setPlan(null);
      flash(v.body.status === 'paused' ? 'Duraklatıldı' : v.body.status === 'active' ? 'Yeniden etkin' : 'Kaydedildi');
    },
  });

  const run = useMutation({
    mutationFn: (id: string) => reportsApi.run(id),
    onSuccess: async (r) => {
      await refresh();
      flash(r.lastStatus === 'failed' ? 'Çalıştı ama hata verdi' : `Çalıştı · ${nf.format(r.lastRows ?? 0)} satır`);
    },
  });

  const remove = useMutation({
    mutationFn: (id: string) => reportsApi.remove(id),
    onSuccess: async () => {
      await refresh();
      startNew();
      flash('Rapor silindi');
    },
  });

  const errText =
    errMsg(parse.error, 'Cümle çözülemedi.') ??
    errMsg(create.error, 'Rapor kaydedilemedi.') ??
    errMsg(update.error, 'Değişiklik kaydedilemedi.') ??
    errMsg(run.error, 'Rapor çalıştırılamadı.') ??
    errMsg(remove.error, 'Rapor silinemedi.');

  const planValid = !!plan && plan.question.trim().length > 0 && (plan.recurrence !== 'once' || !!plan.onceAt);
  const active = reports.filter((r) => r.status === 'active').length;
  const submitParse = () => {
    if (text.trim() && !parse.isPending) parse.mutate(text.trim());
  };

  return (
    <Shell
      head={{
        tenant: 'Timaş Yayınları',
        section: 'Yapay Zeka Raporları',
        crumb: 'Planlı raporlar',
        source: `${nf.format(active)} etkin plan`,
        presence: email?.configured ? 'E-posta hazır' : 'E-posta ayarı yok',
        zoom: '%100',
      }}
      rail={railFor('/planli-raporlar')}
    >
      <main className="absolute bottom-2 left-14 right-2 top-16 overflow-y-auto overscroll-contain sm:bottom-6 sm:left-[92px] sm:right-6 sm:top-[84px] md:overflow-visible">
        <div className="mx-auto flex w-full max-w-[1760px] flex-col gap-3 pb-4 md:h-full md:flex-row md:gap-4 md:pb-0">
          {/* Planlar */}
          <div className="glass-panel flex max-h-[38vh] w-full shrink-0 flex-col rounded-2xl p-3 shadow-glass-float sm:rounded-3xl sm:p-4 md:max-h-none md:w-[360px]">
            <div className="flex items-center justify-between">
              <span className="text-[13px] font-extrabold">Planlı raporlar</span>
              <span className="text-[11px] font-bold text-canvas-muted">{reports.length} plan</span>
            </div>
            <button type="button" onClick={startNew} className={`${btn} mt-2.5 justify-center bg-gradient-to-r from-canvas-coral to-canvas-violet text-white shadow-md`}>
              <Plus className="h-4 w-4" />
              Yeni rapor
            </button>
            <div className="mt-2 flex-1 space-y-1 overflow-auto pr-1">
              {list.isLoading && (
                <div className="flex h-24 items-center justify-center text-canvas-muted">
                  <Loader2 className="h-4 w-4 animate-spin" />
                </div>
              )}
              {authRequired && <div className="p-3 text-[12px] text-canvas-muted">Oturum gerekli.</div>}
              {!list.isLoading && !authRequired && !reports.length && (
                <div className="p-3 text-[12px] leading-snug text-canvas-muted">Henüz plan yok. Ne istediğinizi yandaki kutuya bir cümleyle yazın.</div>
              )}
              {reports.map((r) => (
                <button
                  key={r.id}
                  type="button"
                  onClick={() => open(r.id)}
                  className={[
                    'flex min-h-11 w-full flex-col justify-center rounded-xl px-2.5 py-2 text-left transition-colors sm:min-h-0',
                    sel === r.id ? 'bg-white shadow-sm' : 'hover:bg-white/70',
                  ].join(' ')}
                >
                  <span className="truncate text-[12.5px] font-semibold">{r.title}</span>
                  <span className="flex min-w-0 items-center gap-2 text-[11px] text-canvas-muted">
                    <span className="truncate">{r.when}</span>
                    {r.status === 'paused' && <span className="shrink-0 rounded bg-slate-200 px-1.5 font-bold text-canvas-ink">Duraklatıldı</span>}
                    {r.status === 'done' && <span className="shrink-0 rounded bg-slate-200 px-1.5 font-bold text-canvas-ink">Bitti</span>}
                    {r.lastStatus === 'failed' && <span className="shrink-0 rounded bg-red-50 px-1.5 font-bold text-red-700">Hata</span>}
                  </span>
                </button>
              ))}
            </div>
          </div>

          {/* Ayrıntı */}
          <div
            ref={detailRef}
            className="glass-card min-w-0 shrink-0 scroll-mt-2 rounded-2xl p-4 shadow-canvas-card sm:rounded-3xl sm:p-6 md:min-h-0 md:flex-1 md:shrink md:overflow-auto"
          >
            <div className="mx-auto max-w-3xl space-y-5">
              {email && !email.configured && (
                <div className="flex gap-2 rounded-xl bg-amber-50 px-3 py-2 text-[12px] leading-snug text-amber-800">
                  <Mail className="mt-0.5 h-4 w-4 shrink-0" />
                  <span>E-posta ayarı henüz yok. Raporlar zamanında üretilir ve buradan indirilir; ayar girilince alıcılara kendiliğinden gider.</span>
                </div>
              )}
              {errText && <div className="rounded-xl bg-red-50 px-3 py-2 text-[12px] font-semibold text-red-700">{errText}</div>}
              {done && <div className="rounded-xl bg-emerald-50 px-3 py-2 text-[12px] font-semibold text-emerald-700">{done}</div>}

              {!cur ? (
                <>
                  <div>
                    <div className="text-[11px] font-bold uppercase tracking-[.16em] text-canvas-muted">Yeni planlı rapor</div>
                    <h2 className="mt-1 text-2xl font-extrabold tracking-tight">Ne istediğinizi bir cümleyle yazın</h2>
                    <p className="mt-1 text-[12.5px] text-canvas-muted">
                      Sistem zamanı, sıklığı, alıcıları ve veri sorusunu ayırır; kaydetmeden önce hepsini düzeltebilirsiniz.
                    </p>
                  </div>
                  <div>
                    <textarea
                      value={text}
                      onChange={(e) => setText(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) submitParse();
                      }}
                      rows={3}
                      placeholder={EXAMPLE}
                      className={field}
                    />
                    <div className="mt-2 flex flex-wrap items-center gap-3">
                      <button type="button" disabled={!text.trim() || parse.isPending} onClick={submitParse} className={`${btn} bg-canvas-violet text-white shadow-md`}>
                        {parse.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
                        {parse.isPending ? 'Soru motora soruluyor…' : 'Planı çıkar'}
                      </button>
                      {!text && (
                        <button type="button" onClick={() => setText(EXAMPLE)} className="min-h-11 text-[12px] font-bold text-canvas-violet hover:underline sm:min-h-0">
                          Örneği kullan
                        </button>
                      )}
                    </div>
                  </div>

                  {draft && plan && (
                    <div className="space-y-5 border-t border-slate-100 pt-5">
                      <PlanForm plan={plan} onChange={setPlan} />
                      <Preview draft={draft} />
                      <div className="flex flex-wrap gap-2 border-t border-slate-100 pt-4">
                        <button
                          type="button"
                          disabled={!planValid || create.isPending}
                          onClick={() => plan && create.mutate(plan)}
                          className={`${btn} bg-gradient-to-r from-canvas-mint to-emerald-600 text-white shadow-md`}
                        >
                          {create.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <CalendarClock className="h-4 w-4" />}
                          Planla
                        </button>
                        <button
                          type="button"
                          onClick={() => {
                            setDraft(null);
                            setPlan(null);
                          }}
                          className={`${btn} bg-slate-100 text-canvas-ink hover:bg-slate-200`}
                        >
                          <X className="h-4 w-4" />
                          Vazgeç
                        </button>
                      </div>
                    </div>
                  )}
                </>
              ) : editing && plan ? (
                <>
                  <div>
                    <div className="text-[11px] font-bold uppercase tracking-[.16em] text-canvas-muted">Planı düzenle</div>
                    <h2 className="mt-1 text-2xl font-extrabold tracking-tight">{cur.title}</h2>
                  </div>
                  <PlanForm plan={plan} onChange={setPlan} />
                  <div className="flex flex-wrap gap-2 border-t border-slate-100 pt-4">
                    <button
                      type="button"
                      disabled={!planValid || update.isPending}
                      onClick={() => {
                        const b = toInput(plan);
                        // Soru değiştiyse eski SQL artık o soruya ait değil; sonraki çalışmada yeniden üretilir.
                        update.mutate({ id: cur.id, body: b.question !== cur.question ? { ...b, sql: '' } : b });
                      }}
                      className={`${btn} bg-canvas-violet text-white shadow-md`}
                    >
                      {update.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <PencilLine className="h-4 w-4" />}
                      Kaydet
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        setEditing(false);
                        setPlan(null);
                      }}
                      className={`${btn} bg-slate-100 text-canvas-ink hover:bg-slate-200`}
                    >
                      Vazgeç
                    </button>
                  </div>
                </>
              ) : (
                <>
                  <div>
                    <div className="text-[11px] font-bold uppercase tracking-[.16em] text-canvas-muted">
                      {cur.status === 'paused' ? 'Duraklatılmış plan' : cur.status === 'done' ? 'Tamamlanmış plan' : 'Etkin plan'}
                    </div>
                    <h2 className="mt-1 text-2xl font-extrabold tracking-tight">{cur.title}</h2>
                    <p className="mt-1 text-[13px] text-canvas-ink">{cur.question}</p>
                  </div>

                  <div className="grid grid-cols-2 gap-3 text-[12px] sm:grid-cols-4">
                    <Stat k="Plan" v={cur.when} />
                    <Stat k="Sıradaki" v={cur.status === 'active' ? fmtDate(cur.nextRunAt) : '—'} />
                    <Stat k="Son çalışma" v={fmtDate(cur.lastRunAt)} />
                    <Stat k="Biçim" v={cur.fmt === 'xlsx' ? 'Excel' : 'CSV'} />
                  </div>

                  {cur.lastStatus && (
                    <div className={`rounded-xl px-3 py-2 text-[12px] font-semibold ${LAST[cur.lastStatus].tone}`}>
                      {LAST[cur.lastStatus].label}
                      {cur.lastRows != null && cur.lastStatus !== 'failed' ? ` · ${nf.format(cur.lastRows)} satır` : ''}
                      {cur.lastError && <div className="mt-0.5 font-normal">{cur.lastError}</div>}
                    </div>
                  )}

                  <div>
                    <div className="text-[11px] font-bold uppercase tracking-wide text-canvas-muted">Alıcılar</div>
                    {cur.recipients.length ? (
                      <div className="mt-1 flex flex-wrap gap-1.5">
                        {cur.recipients.map((r) => (
                          <span key={r} className="rounded-lg bg-slate-100 px-2 py-0.5 text-[11.5px] font-semibold">
                            {r}
                          </span>
                        ))}
                      </div>
                    ) : (
                      <div className="mt-1 text-[12px] text-canvas-muted">Alıcı yok; dosya yalnız buradan indirilir.</div>
                    )}
                  </div>

                  {cur.sql && (
                    <details>
                      <summary className="cursor-pointer text-[11px] font-bold text-canvas-muted">Son kullanılan SQL</summary>
                      <pre className="mt-1 max-h-48 overflow-auto rounded-xl bg-slate-900 p-3 text-[11px] leading-relaxed text-slate-100">{cur.sql}</pre>
                    </details>
                  )}

                  <div className="flex flex-wrap gap-2 border-t border-slate-100 pt-4">
                    <button
                      type="button"
                      disabled={run.isPending}
                      onClick={() => run.mutate(cur.id)}
                      className={`${btn} bg-gradient-to-r from-canvas-mint to-emerald-600 text-white shadow-md`}
                    >
                      {run.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
                      {run.isPending ? 'Çalışıyor…' : 'Şimdi çalıştır'}
                    </button>
                    {cur.hasFile && (
                      <a href={reportsApi.fileUrl(cur.id)} className={`${btn} bg-canvas-ink text-white shadow-md`}>
                        <Download className="h-4 w-4" />
                        Son dosyayı indir
                      </a>
                    )}
                    <button
                      type="button"
                      onClick={() => {
                        setPlan(fromReport(cur));
                        setEditing(true);
                        setConfirmDelete(false);
                      }}
                      className={`${btn} bg-slate-100 text-canvas-ink hover:bg-slate-200`}
                    >
                      <PencilLine className="h-4 w-4" />
                      Düzenle
                    </button>
                    {cur.status !== 'done' && (
                      <button
                        type="button"
                        disabled={update.isPending}
                        onClick={() => update.mutate({ id: cur.id, body: { status: cur.status === 'active' ? 'paused' : 'active' } })}
                        className={`${btn} bg-slate-100 text-canvas-ink hover:bg-slate-200`}
                      >
                        {cur.status === 'active' ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4" />}
                        {cur.status === 'active' ? 'Duraklat' : 'Sürdür'}
                      </button>
                    )}
                    {confirmDelete ? (
                      <button type="button" disabled={remove.isPending} onClick={() => remove.mutate(cur.id)} className={`${btn} bg-red-600 text-white shadow-md`}>
                        {remove.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Trash2 className="h-4 w-4" />}
                        Evet, sil
                      </button>
                    ) : (
                      <button type="button" onClick={() => setConfirmDelete(true)} className={`${btn} bg-slate-100 text-canvas-ink hover:bg-red-50 hover:text-red-700`}>
                        <Trash2 className="h-4 w-4" />
                        Sil
                      </button>
                    )}
                  </div>
                </>
              )}
            </div>
          </div>
        </div>
      </main>
    </Shell>
  );
}
