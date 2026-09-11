import { useEffect, useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { Loader2, Pause, Play, RotateCw, Trash2, X } from 'lucide-react';
import {
  alertsApi,
  ask as askEngine,
  EngineAuthError,
  type AlertCondition,
  type AlertEmail,
  type AlertRule,
} from '../engine';

/**
 * Uyarı kuralları paneli. Kural bir sorudur ("bu ayın iade tutarı"), bir koşul ve bir eşik. Kontrolü
 * sunucu yapar; bu panel kuralı kurar, gösterir, duraklatır, siler. Kaydetmeden önce sorunun şu anki
 * değeri ölçülür: kişi neyi izlediğini görmeden kural kurmaz.
 */

const nf = new Intl.NumberFormat('tr-TR', { maximumFractionDigits: 2 });
const COND: Record<AlertCondition, string> = { gt: '>', gte: '≥', lt: '<', lte: '≤' };
const QUERY_KEY = ['zeki-uyarilar'];

export type RuleDraft = { question: string; condition: AlertCondition; threshold: number | null };

const MULT: Record<string, number> = { bin: 1e3, milyon: 1e6, mn: 1e6, m: 1e6, milyar: 1e9, mlr: 1e9 };

/** "5.000.000", "5,5 milyon", "750 bin" → sayı. Anlaşılmazsa null. */
export function parseAmount(raw: string): number | null {
  const m = raw
    .trim()
    .toLocaleLowerCase('tr')
    .match(/^(-?\d[\d.,]*)\s*(milyar|mlr|milyon|mn|bin|m)?\.?$/);
  if (!m) return null;
  let n = m[1];
  if (/^-?\d{1,3}(\.\d{3})+(,\d+)?$/.test(n)) n = n.replace(/\./g, '').replace(',', '.');
  else if (/^-?\d{1,3}(,\d{3})+(\.\d+)?$/.test(n)) n = n.replace(/,/g, '');
  else n = n.replace(',', '.');
  const v = Number(n) * (m[2] ? MULT[m[2]] : 1);
  return Number.isFinite(v) ? v : null;
}

/** "bu ayın iade tutarı 5 milyonu aşarsa haber ver" → soru + koşul + eşik. Kişi formda düzeltir. */
export function parseRule(text: string): RuleDraft {
  const t = text.trim();
  const low = t.toLocaleLowerCase('tr');
  const below = /(alt[ıi]n[ae]|d[üu]şerse|azal[ıi]rsa|inerse|gerilerse|küçük)/.test(low);
  const m = low.match(/(-?\d[\d.,]*)\s*(milyar|mlr|milyon|mn|bin|m)?(?=[^\dA-Za-zçğıöşü]|[a-zçğıöşü]|$)/);
  let threshold: number | null = null;
  let question = t;
  if (m && m.index !== undefined) {
    threshold = parseAmount(`${m[1]} ${m[2] ?? ''}`.trim());
    question = t.slice(0, m.index);
  }
  question = question
    .replace(/(^|\s)(eğer|şayet)(\s|$)/giu, ' ')
    .replace(/[\s,;:]+$/u, '')
    .replace(/\s+/g, ' ')
    .trim();
  return { question: question || t, condition: below ? 'lt' : 'gt', threshold };
}

const breached = (v: number, c: AlertCondition, t: number) =>
  c === 'gt' ? v > t : c === 'gte' ? v >= t : c === 'lt' ? v < t : v <= t;

const asNumber = (v: unknown): number | null => {
  if (typeof v === 'number') return Number.isFinite(v) ? v : null;
  if (typeof v === 'string' && v.trim() !== '' && Number.isFinite(Number(v))) return Number(v);
  return null;
};

/** Cevaptan tek sayı. Birden çok satır bir değer değildir; sunucudaki kuralla aynı. */
function singleValue(records: Array<Record<string, unknown>> | undefined): { value: number; column: string } | string {
  const recs = records ?? [];
  if (!recs.length) return 'Soru satır döndürmedi.';
  if (recs.length > 1)
    return `Bu soru ${nf.format(recs.length)} satır döndürüyor; uyarı tek bir değer ister. Soruyu tek sayıya indirin (örn. “bu ayın iade tutarı”).`;
  const nums = Object.entries(recs[0])
    .map(([k, v]) => [k, asNumber(v)] as const)
    .filter(([, v]) => v !== null);
  if (nums.length !== 1) return 'Cevapta tek bir sayı yok; soruyu tek bir ölçüye indirin.';
  return { value: nums[0][1] as number, column: nums[0][0] };
}

function relative(iso: string | null): string {
  if (!iso) return 'hiç';
  const min = (Date.now() - Date.parse(iso)) / 60_000;
  if (!Number.isFinite(min)) return '—';
  if (min < 1) return 'az önce';
  if (min < 60) return `${Math.round(min)} dk önce`;
  const h = min / 60;
  if (h < 24) return `${Math.round(h)} sa önce`;
  return `${Math.round(h / 24)} gün önce`;
}

const STATE: Record<AlertRule['state'], { label: string; cls: string }> = {
  ok: { label: 'Sakin', cls: 'bg-emerald-50 text-emerald-700' },
  triggered: { label: 'Eşik aşıldı', cls: 'bg-red-50 text-red-700' },
  error: { label: 'Ölçülemedi', cls: 'bg-amber-50 text-amber-800' },
  unknown: { label: 'Ölçülmedi', cls: 'bg-slate-100 text-slate-600' },
};

const NOTIFY: Record<string, string> = {
  sent: 'e-posta gönderildi',
  failed: 'e-posta gönderilemedi',
  no_smtp: 'e-posta hesabı tanımlı değil',
  no_recipient: 'alıcı yok',
};

const errText = (e: unknown) => (e instanceof EngineAuthError ? 'Oturum gerekli.' : (e as Error)?.message || 'İşlem yapılamadı.');

export default function AlertsPanel({
  mode,
  onMode,
  onClose,
  rules,
  email,
  draft,
}: {
  mode: 'kurallar' | 'yeni';
  onMode: (m: 'kurallar' | 'yeni') => void;
  onClose: () => void;
  rules: AlertRule[];
  email: AlertEmail;
  draft: RuleDraft | null;
}) {
  return (
    <div className="absolute bottom-28 left-[92px] right-6 z-50 flex justify-center">
      <div className="max-h-[calc(100dvh-230px)] w-full max-w-[1040px] overflow-auto rounded-3xl border border-white bg-white p-5 text-canvas-ink shadow-canvas-card ring-1 ring-slate-900/5">
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-1 rounded-xl bg-slate-100 p-1">
            {(
              [
                ['kurallar', `Kurallar (${rules.length})`],
                ['yeni', 'Yeni kural'],
              ] as const
            ).map(([m, label]) => (
              <button
                key={m}
                type="button"
                onClick={() => onMode(m)}
                className={[
                  'rounded-lg px-3 py-1.5 text-[12px] font-extrabold transition',
                  mode === m ? 'bg-white text-canvas-ink shadow-sm' : 'text-canvas-muted hover:text-canvas-ink',
                ].join(' ')}
              >
                {label}
              </button>
            ))}
          </div>
          <button type="button" onClick={onClose} title="Kapat" className="rounded-lg p-1.5 text-canvas-muted hover:bg-slate-100">
            <X className="h-4 w-4" />
          </button>
        </div>

        {!email.configured && (
          <div className="mt-3 rounded-xl bg-amber-50 px-3 py-2 text-[12px] leading-snug text-amber-900">
            <strong>E-posta gönderici hesabı henüz tanımlı değil.</strong> Kurallar yine düzenli kontrol edilir ve eşik aşılınca
            burada görünür. Hesap tanımlandığında bekleyen uyarılar e-postayla gönderilir.
          </div>
        )}

        <div className="mt-4">{mode === 'yeni' ? <NewRule draft={draft} onSaved={() => onMode('kurallar')} /> : <RuleList rules={rules} onNew={() => onMode('yeni')} />}</div>
      </div>
    </div>
  );
}

function NewRule({ draft, onSaved }: { draft: RuleDraft | null; onSaved: () => void }) {
  const qc = useQueryClient();
  const [question, setQuestion] = useState(draft?.question ?? '');
  const [condition, setCondition] = useState<AlertCondition>(draft?.condition ?? 'gt');
  const [threshold, setThreshold] = useState(draft?.threshold != null ? nf.format(draft.threshold) : '');
  const [title, setTitle] = useState('');
  const [recipients, setRecipients] = useState('');
  const [probe, setProbe] = useState<{ value: number; column: string; sql?: string } | null>(null);
  const [probeErr, setProbeErr] = useState<string | null>(null);
  const [probing, setProbing] = useState(false);

  useEffect(() => {
    if (!draft) return;
    setQuestion(draft.question);
    setCondition(draft.condition);
    setThreshold(draft.threshold != null ? nf.format(draft.threshold) : '');
    setProbe(null);
    setProbeErr(null);
  }, [draft]);

  const thr = parseAmount(threshold);
  const recips = recipients.split(/[,;\s]+/).filter(Boolean);

  const measure = async () => {
    const q = question.trim();
    if (!q) return;
    setProbing(true);
    setProbe(null);
    setProbeErr(null);
    try {
      const a = await askEngine(q);
      if (!a.records) {
        setProbeErr(a.summary || a.explanation || 'Motor bu soruya bir değer döndürmedi.');
        return;
      }
      const v = singleValue(a.records as Array<Record<string, unknown>>);
      if (typeof v === 'string') setProbeErr(v);
      else setProbe({ ...v, sql: a.sql });
    } catch (e) {
      setProbeErr(e instanceof EngineAuthError ? 'Oturum gerekli.' : 'Motor yanıt vermedi.');
    } finally {
      setProbing(false);
    }
  };

  const save = useMutation({
    mutationFn: () =>
      alertsApi.create({
        title: title.trim() || question.trim(),
        question: question.trim(),
        condition,
        threshold: thr as number,
        recipients: recips,
        column: probe?.column ?? null,
      }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: QUERY_KEY });
      onSaved();
    },
  });

  const field = 'mt-1 w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-[13px] outline-none focus:border-canvas-violet';
  const label = 'text-[11px] font-bold text-canvas-muted';

  return (
    <div className="space-y-3">
      <div>
        <label className={label} htmlFor="kural-soru">
          Neyi izleyelim? <span className="font-normal">Tek bir sayı döndüren soru</span>
        </label>
        <div className="flex gap-2">
          <input
            id="kural-soru"
            value={question}
            onChange={(e) => {
              setQuestion(e.target.value);
              setProbe(null);
              setProbeErr(null);
            }}
            placeholder="örn. bu ayın iade tutarı"
            className={field}
          />
          <button
            type="button"
            onClick={measure}
            disabled={probing || !question.trim()}
            className="mt-1 flex shrink-0 items-center gap-1.5 rounded-xl bg-slate-100 px-3 text-[12px] font-extrabold text-canvas-ink transition hover:bg-slate-200 disabled:opacity-50"
          >
            {probing ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RotateCw className="h-3.5 w-3.5" />}
            Şu anki değeri ölç
          </button>
        </div>
      </div>

      {probeErr && <div className="rounded-xl bg-amber-50 px-3 py-2 text-[12px] text-amber-900">{probeErr}</div>}
      {probe && (
        <div className="rounded-xl bg-slate-50 px-3 py-2 text-[12.5px]">
          Şu anki değer <strong className="font-mono tabular-nums">{nf.format(probe.value)}</strong>
          {thr != null && (
            <>
              {' '}
              · kural şimdi{' '}
              <strong className={breached(probe.value, condition, thr) ? 'text-red-700' : 'text-emerald-700'}>
                {breached(probe.value, condition, thr) ? 'tetiklenirdi' : 'sakin kalırdı'}
              </strong>
            </>
          )}
          {probe.sql && <div className="mt-1 truncate font-mono text-[10.5px] text-canvas-muted" title={probe.sql}>{probe.sql}</div>}
        </div>
      )}

      <div className="grid grid-cols-[140px_1fr] gap-3">
        <div>
          <label className={label} htmlFor="kural-kosul">
            Koşul
          </label>
          <select id="kural-kosul" value={condition} onChange={(e) => setCondition(e.target.value as AlertCondition)} className={field}>
            <option value="gt">büyükse (&gt;)</option>
            <option value="gte">büyük ya da eşitse (≥)</option>
            <option value="lt">küçükse (&lt;)</option>
            <option value="lte">küçük ya da eşitse (≤)</option>
          </select>
        </div>
        <div>
          <label className={label} htmlFor="kural-esik">
            Eşik <span className="font-normal">örn. 5.000.000 ya da 5 milyon</span>
          </label>
          <input id="kural-esik" value={threshold} onChange={(e) => setThreshold(e.target.value)} className={field} />
          {threshold && thr == null && <div className="mt-1 text-[11px] font-semibold text-red-600">Sayı anlaşılamadı.</div>}
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className={label} htmlFor="kural-ad">
            Kural adı <span className="font-normal">boş kalırsa soru kullanılır</span>
          </label>
          <input id="kural-ad" value={title} onChange={(e) => setTitle(e.target.value)} className={field} />
        </div>
        <div>
          <label className={label} htmlFor="kural-alici">
            E-posta alıcıları <span className="font-normal">virgülle ayırın</span>
          </label>
          <input
            id="kural-alici"
            value={recipients}
            onChange={(e) => setRecipients(e.target.value)}
            placeholder="ad@timas.com.tr"
            className={field}
          />
        </div>
      </div>

      {save.isError && <div className="rounded-xl bg-red-50 px-3 py-2 text-[12px] font-semibold text-red-700">{errText(save.error)}</div>}

      <div className="flex items-center justify-between gap-3 border-t border-slate-100 pt-3">
        <span className="text-[11.5px] text-canvas-muted">
          {!probe ? 'Kaydetmeden önce şu anki değeri ölçün.' : thr == null ? 'Eşiği yazın.' : 'Kural her 15 dakikada bir kontrol edilir.'}
        </span>
        <button
          type="button"
          disabled={!probe || thr == null || save.isPending}
          onClick={() => save.mutate()}
          className="flex items-center gap-1.5 rounded-xl bg-gradient-to-r from-canvas-coral to-canvas-violet px-4 py-2 text-[12.5px] font-extrabold text-white shadow-md disabled:opacity-40"
        >
          {save.isPending && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
          Kuralı kaydet
        </button>
      </div>
    </div>
  );
}

function RuleList({ rules, onNew }: { rules: AlertRule[]; onNew: () => void }) {
  const qc = useQueryClient();
  const refresh = () => void qc.invalidateQueries({ queryKey: QUERY_KEY });
  const checkAll = useMutation({ mutationFn: () => alertsApi.check(), onSuccess: refresh });

  if (!rules.length) {
    return (
      <div className="py-8 text-center text-[13px] text-canvas-muted">
        Henüz kural yok.{' '}
        <button type="button" onClick={onNew} className="font-bold text-canvas-violet underline-offset-2 hover:underline">
          İlk kuralı kurun
        </button>{' '}
        ya da aşağıdaki çubuğa “bu ayın iade tutarı 5 milyonu aşarsa haber ver” yazın.
      </div>
    );
  }

  return (
    <div>
      <div className="mb-2 flex items-center justify-between gap-3">
        <span className="text-[12px] text-canvas-muted">
          {checkAll.data
            ? `${checkAll.data.checked} kural kontrol edildi · ${checkAll.data.triggered} tanesi eşiği aşıyor${checkAll.data.errors.length ? ` · ${checkAll.data.errors.length} ölçülemedi` : ''}`
            : 'Sunucu her 15 dakikada bir kontrol eder.'}
        </span>
        <button
          type="button"
          onClick={() => checkAll.mutate()}
          disabled={checkAll.isPending}
          className="flex items-center gap-1.5 rounded-xl bg-slate-100 px-3 py-1.5 text-[12px] font-extrabold hover:bg-slate-200 disabled:opacity-50"
        >
          {checkAll.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RotateCw className="h-3.5 w-3.5" />}
          Hepsini şimdi kontrol et
        </button>
      </div>
      {checkAll.isError && <div className="mb-2 rounded-xl bg-red-50 px-3 py-2 text-[12px] text-red-700">{errText(checkAll.error)}</div>}
      <div className="divide-y divide-slate-100 rounded-2xl border border-slate-100">
        {rules.map((r) => (
          <RuleRow key={r.id} rule={r} onChanged={refresh} />
        ))}
      </div>
    </div>
  );
}

function RuleRow({ rule, onChanged }: { rule: AlertRule; onChanged: () => void }) {
  const [confirm, setConfirm] = useState(false);
  const toggle = useMutation({
    mutationFn: () => alertsApi.update(rule.id, { status: rule.status === 'paused' ? 'active' : 'paused' }),
    onSuccess: onChanged,
  });
  const check = useMutation({ mutationFn: () => alertsApi.check(rule.id), onSuccess: onChanged });
  const del = useMutation({ mutationFn: () => alertsApi.remove(rule.id), onSuccess: onChanged });
  const st = rule.status === 'paused' ? { label: 'Duraklatıldı', cls: 'bg-slate-100 text-slate-600' } : STATE[rule.state];
  const err = toggle.error ?? check.error ?? del.error;
  const btn = 'rounded-lg p-1.5 text-canvas-muted transition hover:bg-slate-100 hover:text-canvas-ink disabled:opacity-40';

  return (
    <div className="grid grid-cols-[minmax(0,1fr)_auto] gap-3 px-3 py-2.5">
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          <span className="truncate text-[13px] font-extrabold">{rule.title}</span>
          <span className={`rounded-md px-1.5 py-0.5 text-[10.5px] font-bold ${st.cls}`}>{st.label}</span>
        </div>
        {rule.question && rule.question !== rule.title && (
          <div className="truncate text-[11.5px] text-canvas-muted">{rule.question}</div>
        )}
        <div className="mt-0.5 flex flex-wrap gap-x-4 gap-y-0.5 text-[11.5px] text-canvas-muted">
          <span>
            Son değer{' '}
            <strong className="font-mono tabular-nums text-canvas-ink">{rule.last_value != null ? nf.format(rule.last_value) : '—'}</strong>{' '}
            · koşul {COND[rule.condition]} <span className="font-mono tabular-nums">{nf.format(rule.threshold)}</span>
          </span>
          <span>Son kontrol {relative(rule.last_checked_at)}</span>
          <span>{rule.recipients.length ? rule.recipients.join(', ') : 'alıcı yok'}</span>
          {rule.last_notify && rule.last_notify !== 'no_recipient' && <span>{NOTIFY[rule.last_notify] ?? rule.last_notify}</span>}
        </div>
        {rule.state === 'error' && rule.last_error && (
          <div className="mt-1 text-[11.5px] font-semibold text-amber-800">{rule.last_error}</div>
        )}
        {err && <div className="mt-1 text-[11.5px] font-semibold text-red-700">{errText(err)}</div>}
      </div>
      <div className="flex items-center gap-0.5">
        <button type="button" title="Şimdi kontrol et" onClick={() => check.mutate()} disabled={check.isPending} className={btn}>
          {check.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <RotateCw className="h-4 w-4" />}
        </button>
        <button
          type="button"
          title={rule.status === 'paused' ? 'Sürdür' : 'Duraklat'}
          onClick={() => toggle.mutate()}
          disabled={toggle.isPending}
          className={btn}
        >
          {rule.status === 'paused' ? <Play className="h-4 w-4" /> : <Pause className="h-4 w-4" />}
        </button>
        {confirm ? (
          <button
            type="button"
            onClick={() => del.mutate()}
            disabled={del.isPending}
            className="rounded-lg bg-red-50 px-2 py-1 text-[11.5px] font-extrabold text-red-700 hover:bg-red-100"
          >
            Silinsin mi? Evet
          </button>
        ) : (
          <button type="button" title="Sil" onClick={() => setConfirm(true)} className={btn}>
            <Trash2 className="h-4 w-4" />
          </button>
        )}
      </div>
    </div>
  );
}
