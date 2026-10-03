import { useMemo, useState, type ReactNode } from 'react';
import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ChevronDown, Database, Download, FileText, MousePointerClick, Search, Send, ShieldCheck, ShieldAlert } from 'lucide-react';
import {
  adminApi,
  type TrailDetail,
  type TrailItem,
  type TrailQuery,
  type TrailRequest,
  type TrailRow,
  type TrailType,
  type TrailUi,
} from '../engine';
import SearchSelect from '../components/SearchSelect';
import { readableName, readableText } from '../components/readableName';
import { EmptyHint } from '../components/Explain';
import { ACTION_LABEL, FIELD_LABEL, Loading, Note, Pill, Section, btnGhost, errText, field, fmtDate, nf, show } from './ui';

/**
 * Yönetim → Denetim kaydı. Dört katman tek akışta (köprü `audit_trail.py`):
 * ekran olayı (sayfa/düğme/seçim), istek (gönderilen içerik dahil), veri değişikliği (eski → yeni), işlem kaydı.
 * Bir satıra dokununca o isteğin bütün izi açılır: kim, nereden, hangi ekranda, ne gönderdi, hangi kayıtlar değişti.
 */

const LAYERS: Array<{ id: string; label: string; types: TrailType[] }> = [
  { id: 'ui', label: 'Ekran', types: ['ui'] },
  { id: 'write', label: 'Gönderilen', types: ['request'] },
  { id: 'read', label: 'Görüntülenen', types: ['request'] },
  { id: 'row', label: 'Veri değişikliği', types: ['row'] },
  { id: 'action', label: 'İşlem', types: ['action'] },
];

const OP_LABEL: Record<string, { label: string; tone: 'ok' | 'violet' | 'err' }> = {
  INSERT: { label: 'Ekledi', tone: 'ok' },
  UPDATE: { label: 'Değiştirdi', tone: 'violet' },
  DELETE: { label: 'Sildi', tone: 'err' },
};

const TABLE_LABEL: Record<string, string> = {
  semantic_audit: 'İşlem kaydı',
  semantic_audit_requests: 'İstek kaydı',
  semantic_audit_rows: 'Veri değişikliği kaydı',
  semantic_audit_ui: 'Ekran olayı kaydı',
};

const METHOD_LABEL: Record<string, string> = { GET: 'Açtı', POST: 'Gönderdi', PUT: 'Kaydetti', PATCH: 'Güncelledi', DELETE: 'Silme istedi' };

const dayFmt = new Intl.DateTimeFormat('tr-TR', { timeZone: 'Europe/Istanbul', weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' });
const timeFmt = new Intl.DateTimeFormat('tr-TR', { timeZone: 'Europe/Istanbul', hour: '2-digit', minute: '2-digit', second: '2-digit' });
const dayKey = (iso: string) => new Intl.DateTimeFormat('en-CA', { timeZone: 'Europe/Istanbul' }).format(new Date(iso));

/** Portal öneki olmadan ekran yolu: «/timas/panolar?x=1» → «/panolar?x=1». */
const screenOf = (p: string | null | undefined) => (p ? p.replace(/^\/timas(?=\/|$)/, '') || '/' : '');
const pkText = (pk: Record<string, unknown> | null | undefined) =>
  pk ? Object.entries(pk).map(([k, v]) => (Object.keys(pk).length > 1 ? `${k}=${show(v)}` : show(v))).join(' · ') : '';

/** İstanbul gününün başı (YYYY-AA-GG → ISO). */
const dayStart = (d: string) => (d ? new Date(`${d}T00:00:00+03:00`).toISOString() : undefined);
const dayEnd = (d: string) => (d ? new Date(new Date(`${d}T00:00:00+03:00`).getTime() + 86_400_000).toISOString() : undefined);

function TypeIcon({ t }: { t: TrailType }) {
  const cls = 'h-3.5 w-3.5';
  const Icon = t === 'ui' ? MousePointerClick : t === 'request' ? Send : t === 'row' ? Database : FileText;
  const tone = t === 'ui' ? 'bg-sky-50 text-sky-700' : t === 'request' ? 'bg-slate-100 text-canvas-ink' : t === 'row' ? 'bg-amber-50 text-amber-800' : 'bg-canvas-violet/10 text-canvas-violet';
  return (
    <span className={`mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-lg ${tone}`} aria-hidden>
      <Icon className={cls} />
    </span>
  );
}

/** Satırın tek cümlelik özeti. */
function Summary({ it }: { it: TrailItem }) {
  if (it.type === 'ui') {
    const what =
      it.event === 'view' ? 'Sayfa açtı' : it.event === 'click' ? 'Bastı' : it.event === 'change' ? 'Seçti' : it.event === 'leave' ? 'Sayfadan çıktı' : it.event;
    return (
      <>
        <Pill tone="muted">{what}</Pill>
        {it.event !== 'view' && it.label && <span className="font-semibold">«{it.label}»</span>}
        <span className="truncate text-canvas-muted">{screenOf(it.page)}</span>
      </>
    );
  }
  if (it.type === 'request') {
    const bad = (it.status ?? 0) >= 400;
    return (
      <>
        <Pill tone={it.method === 'DELETE' ? 'err' : it.method === 'GET' ? 'muted' : 'violet'}>{METHOD_LABEL[it.method ?? ''] ?? it.method}</Pill>
        <span className="truncate font-mono text-[11.5px]">{it.path}</span>
        {it.status != null && <Pill tone={bad ? 'err' : 'ok'}>{it.status}</Pill>}
      </>
    );
  }
  if (it.type === 'row') {
    const o = OP_LABEL[it.op ?? ''] ?? { label: it.op, tone: 'muted' as const };
    return (
      <>
        <Pill tone={o.tone}>{o.label}</Pill>
        <span className="font-semibold">{readableName(it.table)}</span>
        <span className="truncate text-canvas-muted">{pkText(it.pk)}</span>
      </>
    );
  }
  const a = ACTION_LABEL[it.action ?? ''] ?? { label: it.action, tone: 'muted' as const };
  return (
    <>
      <Pill tone={a.tone}>{a.label}</Pill>
      <span className="text-canvas-muted">{it.kindLabel}</span>
      <span className="truncate font-semibold">{readableText(it.title || '—')}</span>
    </>
  );
}

function KV({ k, children }: { k: string; children: ReactNode }) {
  return (
    <div className="grid gap-x-2 sm:grid-cols-[110px_1fr]">
      <dt className="font-bold text-canvas-muted">{k}</dt>
      <dd className="min-w-0 break-words">{children}</dd>
    </div>
  );
}

function Pre({ v }: { v: unknown }) {
  const text = typeof v === 'string' ? v : JSON.stringify(v, null, 2);
  return <pre className="max-h-80 overflow-auto whitespace-pre-wrap break-words rounded-lg bg-white p-2 font-mono text-[11px] leading-relaxed">{text}</pre>;
}

function RequestBlock({ r }: { r: TrailRequest }) {
  return (
    <div className="space-y-2">
      <dl className="space-y-1">
        <KV k="Kişi">{r.actor ?? 'Oturumsuz'}</KV>
        <KV k="Zaman">{fmtDate(r.at)} · {timeFmt.format(new Date(r.at))}</KV>
        <KV k="Ekran">{screenOf(r.page) || '—'}</KV>
        <KV k="İstek">
          <span className="font-mono text-[11px]">
            {r.method} {r.path}
            {r.query ? `?${r.query}` : ''}
          </span>
        </KV>
        <KV k="Sonuç">
          {r.status ?? '—'} · {r.ms != null ? `${nf.format(r.ms)} ms` : '—'}
          {r.respBytes != null ? ` · ${nf.format(r.respBytes)} bayt` : ''}
        </KV>
        <KV k="Bölüm">{r.module ? r.module.split(',').map((m) => readableName(m.replace(/^sayfa:/, ''))).join(', ') : '—'}</KV>
        <KV k="IP">{r.ip ?? '—'}</KV>
        <KV k="Cihaz">{r.ua ?? '—'}</KV>
        <KV k="İstek no">
          <span className="font-mono text-[11px]">{r.rid}</span>
        </KV>
      </dl>
      {r.files && r.files.length > 0 && (
        <div>
          <div className="mb-1 font-bold text-canvas-muted">Yüklenen</div>
          <ul className="list-inside list-disc">
            {r.files.map((f, i) => (
              <li key={i}>
                {f.filename ? <span className="font-semibold">{f.filename}</span> : <span className="text-canvas-muted">alan</span>} <span className="text-canvas-muted">({f.name})</span>
              </li>
            ))}
          </ul>
          {r.reqBytes != null && <div className="text-canvas-muted">Toplam {nf.format(r.reqBytes)} bayt</div>}
        </div>
      )}
      {r.body != null && r.body !== '' && (
        <div>
          <div className="mb-1 font-bold text-canvas-muted">Gönderilen içerik</div>
          <Pre v={r.body} />
        </div>
      )}
    </div>
  );
}

/** Bir satır değişikliği: alan alan eski → yeni (eklemede yeni, silmede eski değerler). */
function RowBlock({ r, onHistory }: { r: TrailRow; onHistory?: (r: TrailRow) => void }) {
  const o = OP_LABEL[r.op];
  const keys = r.op === 'UPDATE' ? (r.changed ?? Object.keys(r.new ?? {})) : Object.keys((r.op === 'DELETE' ? r.old : r.new) ?? {});
  return (
    <div className="rounded-xl border border-slate-100 bg-white p-2.5">
      <div className="flex flex-wrap items-center gap-1.5">
        <Pill tone={o.tone}>{o.label}</Pill>
        <span className="font-semibold">{readableName(r.table)}</span>
        <span className="text-canvas-muted">{pkText(r.pk)}</span>
        <span className="ml-auto text-[11px] tabular-nums text-canvas-muted">{timeFmt.format(new Date(r.at))}</span>
      </div>
      <div className="mt-2 overflow-x-auto">
        <table className="w-full min-w-[420px] text-[11.5px]">
          <thead>
            <tr className="text-left text-[10.5px] uppercase tracking-wide text-canvas-muted">
              <th className="w-1/4 py-1 pr-2 font-bold">Alan</th>
              {r.op !== 'INSERT' && <th className="py-1 pr-2 font-bold">{r.op === 'DELETE' ? 'Silinen değer' : 'Önce'}</th>}
              {r.op !== 'DELETE' && <th className="py-1 font-bold">{r.op === 'INSERT' ? 'Değer' : 'Sonra'}</th>}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {keys.map((k) => (
              <tr key={k} className="align-top">
                <td className="py-1 pr-2 font-semibold">{FIELD_LABEL[k] ?? readableName(k)}</td>
                {r.op !== 'INSERT' && (
                  <td className={`max-w-[40ch] break-words py-1 pr-2 ${r.op === 'UPDATE' ? 'text-red-700' : ''}`}>{cell(r.old?.[k])}</td>
                )}
                {r.op !== 'DELETE' && <td className={`max-w-[40ch] break-words py-1 ${r.op === 'UPDATE' ? 'font-semibold text-emerald-700' : ''}`}>{cell(r.new?.[k])}</td>}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {onHistory && r.pk && (
        <button type="button" onClick={() => onHistory(r)} className="mt-2 text-[11.5px] font-bold text-canvas-violet hover:underline">
          Bu kaydın bütün geçmişi
        </button>
      )}
    </div>
  );
}

/** Uzun metin/JSON değerini hücrede okunur tutar (kesmez; kendi içinde kayar). */
function cell(v: unknown): ReactNode {
  if (v && typeof v === 'object') return <Pre v={v} />;
  if (typeof v === 'string' && v.length > 240) return <Pre v={v} />;
  if (typeof v === 'string' && /^[[{]/.test(v.trim())) {
    try {
      return <Pre v={JSON.parse(v)} />;
    } catch {
      /* düz metin */
    }
  }
  return show(v);
}

function UiLine({ u }: { u: TrailUi }) {
  const d = u.detail ?? {};
  return (
    <li className="flex flex-wrap gap-x-1.5">
      <span className="tabular-nums text-canvas-muted">{timeFmt.format(new Date(u.at))}</span>
      <span className="font-semibold">{u.event === 'view' ? 'Sayfa açtı' : u.event === 'click' ? 'Bastı' : u.event === 'change' ? 'Seçti' : u.event}</span>
      {u.label && u.event !== 'view' && <span>«{u.label}»</span>}
      {'value' in d && <span className="text-canvas-muted">→ {show(d.value)}</span>}
      {'checked' in d && <span className="text-canvas-muted">→ {d.checked ? 'işaretli' : 'işaretsiz'}</span>}
      {typeof d.section === 'string' && <span className="text-canvas-muted">· {d.section}</span>}
      <span className="truncate text-canvas-muted">· {screenOf(u.page)}</span>
    </li>
  );
}

function History({ table, pk, onClose }: { table: string; pk: Record<string, unknown>; onClose: () => void }) {
  const key = JSON.stringify(pk);
  const q = useQuery({ queryKey: ['admin', 'trail', 'record', table, key], queryFn: () => adminApi.trailRecord(table, key), retry: false });
  return (
    <div className="space-y-2 rounded-xl border border-canvas-violet/20 bg-canvas-violet/5 p-2.5">
      <div className="flex items-center gap-2">
        <span className="font-bold">
          {readableName(table)} · {pkText(pk)} — bütün geçmişi
        </span>
        <button type="button" onClick={onClose} className="ml-auto text-[11.5px] font-bold text-canvas-muted hover:text-canvas-ink">
          Kapat
        </button>
      </div>
      {q.isLoading ? (
        <Loading />
      ) : q.error ? (
        <Note tone="err">{errText(q.error, 'Geçmiş okunamadı.')}</Note>
      ) : (
        <ol className="space-y-2">
          {(q.data?.items ?? []).map((r) => (
            <li key={r.id}>
              <div className="mb-1 text-[11px] text-canvas-muted">
                {fmtDate(r.at)} · {r.actor ?? '—'}
              </div>
              <RowBlock r={r} />
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}

function Detail({ it }: { it: TrailItem }) {
  const q = useQuery({ queryKey: ['admin', 'trail', 'item', it.type, it.id], queryFn: () => adminApi.trailItem(it.type, it.id), retry: false, staleTime: 60_000 });
  const [hist, setHist] = useState<TrailRow | null>(null);
  if (q.isLoading) return <Loading />;
  if (q.error) return <Note tone="err">{errText(q.error, 'Ayrıntı okunamadı.')}</Note>;
  const d: TrailDetail = q.data ?? {};
  const rows = d.row ? [d.row] : (d.rows ?? []);
  return (
    <div className="mt-2 space-y-3 rounded-xl bg-slate-50 p-2.5 text-[11.5px]">
      {d.ui && d.ui.length > 0 && it.type !== 'ui' && (
        <div>
          <div className="mb-1 font-bold text-canvas-muted">Ekranda ondan hemen önce</div>
          <ul className="space-y-0.5">
            {d.ui.map((u) => (
              <UiLine key={u.id} u={u} />
            ))}
          </ul>
        </div>
      )}
      {it.type === 'ui' && d.ui?.[0] && (
        <dl className="space-y-1">
          <KV k="Olay">
            <ul>
              <UiLine u={d.ui[0]} />
            </ul>
          </KV>
          <KV k="IP">{d.ui[0].ip ?? '—'}</KV>
          <KV k="Cihaz">{d.ui[0].ua ?? '—'}</KV>
          {d.ui[0].detail && <KV k="Ayrıntı"><Pre v={d.ui[0].detail} /></KV>}
        </dl>
      )}
      {d.request && <RequestBlock r={d.request} />}
      {d.actions && d.actions.length > 0 && (
        <div>
          <div className="mb-1 font-bold text-canvas-muted">İşlem kaydı</div>
          <ul className="space-y-1">
            {d.actions.map((a) => (
              <li key={a.id} className="rounded-lg bg-white p-2">
                <div className="flex flex-wrap items-center gap-1.5">
                  <Pill tone={(ACTION_LABEL[a.action] ?? { tone: 'muted' as const }).tone}>{ACTION_LABEL[a.action]?.label ?? a.action}</Pill>
                  <span className="text-canvas-muted">{a.kindLabel}</span>
                  <span className="font-semibold">{readableText(a.title || a.objectId || '—')}</span>
                </div>
                {a.detail && Object.keys(a.detail).length > 0 && <Pre v={a.detail} />}
              </li>
            ))}
          </ul>
        </div>
      )}
      {rows.length > 0 && (
        <div className="space-y-2">
          <div className="font-bold text-canvas-muted">
            Değişen kayıtlar ({nf.format(rows.length)})
          </div>
          {rows.map((r) => (
            <RowBlock key={r.id} r={r} onHistory={setHist} />
          ))}
        </div>
      )}
      {hist?.pk && <History table={hist.table} pk={hist.pk} onClose={() => setHist(null)} />}
      {it.type === 'request' && d.request && !rows.length && !(d.actions ?? []).length && d.request.method !== 'GET' && (
        <div className="text-canvas-muted">Bu istek veride bir kayıt değiştirmedi.</div>
      )}
    </div>
  );
}

function Line({ it }: { it: TrailItem }) {
  const [open, setOpen] = useState(false);
  return (
    <li className="py-2">
      <button type="button" onClick={() => setOpen((o) => !o)} aria-expanded={open} className="flex w-full min-w-0 items-start gap-2.5 text-left">
        <span className="w-[62px] shrink-0 pt-1 text-[11px] tabular-nums text-canvas-muted">{timeFmt.format(new Date(it.at))}</span>
        <TypeIcon t={it.type} />
        <span className="min-w-0 flex-1">
          <span className="flex min-w-0 flex-wrap items-center gap-1.5 text-[12.5px]">
            <span className="font-bold">{it.actor ?? 'Oturumsuz'}</span>
            <Summary it={it} />
          </span>
          {it.type === 'request' && it.page && <span className="block truncate text-[11px] text-canvas-muted">Ekran: {screenOf(it.page)}</span>}
        </span>
        <ChevronDown className={`mt-1 h-4 w-4 shrink-0 text-canvas-muted transition-transform duration-200 ease-out ${open ? 'rotate-180' : ''}`} />
      </button>
      {open && <Detail it={it} />}
    </li>
  );
}

function SealPanel() {
  const qc = useQueryClient();
  const st = useQuery({ queryKey: ['admin', 'trail', 'status'], queryFn: adminApi.trailStatus, retry: false, refetchInterval: 60_000 });
  const verify = useMutation({
    mutationFn: adminApi.trailVerify,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['admin', 'trail', 'status'] }),
  });
  if (st.isLoading) return null;
  if (st.error) return <Note tone="err">{errText(st.error, 'Kayıt durumu okunamadı.')}</Note>;
  const s = st.data!.stats;
  const v = verify.data ?? st.data!.seal.lastVerify;
  const counters: Array<[string, number]> = [
    ['Ekran olayı', s.ui.count],
    ['İstek', s.request.count],
    ['Veri değişikliği', s.row.count],
    ['İşlem kaydı', s.action.count],
  ];
  return (
    <div className="grid gap-2 sm:grid-cols-[1fr_auto]">
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        {counters.map(([k, n]) => (
          <div key={k} className="rounded-xl border border-slate-100 bg-white/80 px-3 py-2">
            <div className="text-[11px] font-bold text-canvas-muted">{k}</div>
            <div className="text-[15px] font-extrabold tabular-nums">{nf.format(n)}</div>
          </div>
        ))}
      </div>
      <div className={`flex min-w-0 items-center gap-2 rounded-xl px-3 py-2 text-[12px] ${v && !v.ok ? 'bg-red-50 text-red-700' : 'bg-emerald-50 text-emerald-800'}`}>
        {v && !v.ok ? <ShieldAlert className="h-4 w-4 shrink-0" /> : <ShieldCheck className="h-4 w-4 shrink-0" />}
        <div className="min-w-0">
          <div className="font-bold">
            {verify.isPending ? 'Mühür doğrulanıyor…' : !v ? 'Mühür henüz doğrulanmadı' : v.ok ? 'Kayıt bütün: silinen ya da değiştirilen satır yok' : 'Kayıt bozulmuş'}
          </div>
          {v && (
            <div className="text-[11px] opacity-80">
              {fmtDate(v.at)} · {nf.format(v.tables.reduce((a, t) => a + t.checked, 0))} satır
              {!v.ok &&
                ' · ' +
                  v.tables
                    .filter((t) => !t.ok)
                    .map((t) => `${TABLE_LABEL[t.table] ?? t.table}: ${t.firstProblem?.why ?? `${t.broken} bozuk, ${t.missing} eksik`}`)
                    .join('; ')}
            </div>
          )}
          {verify.error && <div className="text-[11px]">{errText(verify.error, 'Doğrulama yapılamadı.')}</div>}
        </div>
        <button type="button" onClick={() => verify.mutate()} disabled={verify.isPending} className="ml-auto shrink-0 rounded-lg bg-white/80 px-2 py-1 text-[11.5px] font-bold text-canvas-ink transition-transform duration-150 ease-out hover:bg-white active:scale-[0.97] disabled:opacity-50">
          Doğrula
        </button>
      </div>
      {(s.spooled > 0 || s.queued > 50) && (
        <Note tone="warn">
          {s.spooled > 0 ? `${nf.format(s.spooled)} kayıt veritabanına yazılamadı, diskte bekliyor; bağlantı dönünce aktarılır.` : `${nf.format(s.queued)} kayıt yazılmayı bekliyor.`}
        </Note>
      )}
    </div>
  );
}

export default function AuditTrail() {
  const [actor, setActor] = useState('');
  const [since, setSince] = useState('');
  const [until, setUntil] = useState('');
  const [text, setText] = useState('');
  const [search, setSearch] = useState('');
  const [layers, setLayers] = useState<string[]>(['ui', 'write', 'row', 'action']);

  const actors = useQuery({ queryKey: ['admin', 'trail', 'actors'], queryFn: adminApi.trailActors, retry: false, staleTime: 60_000 });
  const filter: TrailQuery = useMemo(() => {
    const on = LAYERS.filter((l) => layers.includes(l.id));
    const types = Array.from(new Set(on.flatMap((l) => l.types)));
    return {
      types: types.join(',') || 'none',
      reads: layers.includes('read') ? (layers.includes('write') ? '1' : 'only') : undefined,
      actor: actor || undefined,
      since: dayStart(since),
      until: dayEnd(until),
      q: search || undefined,
    };
  }, [layers, actor, since, until, search]);

  const q = useInfiniteQuery({
    queryKey: ['admin', 'trail', filter],
    queryFn: ({ pageParam }) => adminApi.trail({ ...filter, before: pageParam ?? undefined }),
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.next,
    retry: false,
  });
  const items = q.data?.pages.flatMap((p) => p.items) ?? [];
  const groups = useMemo(() => {
    const out: Array<{ day: string; label: string; items: TrailItem[] }> = [];
    for (const it of items) {
      const k = dayKey(it.at);
      if (!out.length || out[out.length - 1].day !== k) out.push({ day: k, label: dayFmt.format(new Date(it.at)), items: [] });
      out[out.length - 1].items.push(it);
    }
    return out;
  }, [items]);

  const toggle = (id: string) => setLayers((l) => (l.includes(id) ? l.filter((x) => x !== id) : [...l, id]));
  const actorOptions = (actors.data?.items ?? []).map((a) => ({ value: a.actor, label: a.actor }));
  const filtered = !!(actor || since || until || search);

  return (
    <Section
      title="Denetim kaydı"
      help="Kim, ne zaman, hangi ekranda ne yaptı: açtığı sayfa, bastığı düğme, yazıp gönderdiği her şey, veride neyi ekleyip değiştirdiği ya da sildiği (eski ve yeni değeriyle). Satıra dokununca o işin bütün izi açılır."
      action={
        <a href={adminApi.trailExportUrl(filter)} className={btnGhost} download>
          <Download className="h-4 w-4" />
          Excel/CSV indir
        </a>
      }
    >
      <SealPanel />
      <div className="grid gap-2 sm:grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)_auto_auto]">
        <form
          className="relative"
          onSubmit={(e) => {
            e.preventDefault();
            setSearch(text.trim());
          }}
        >
          <Search className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-canvas-muted" />
          <input
            value={text}
            onChange={(e) => setText(e.target.value)}
            onBlur={() => setSearch(text.trim())}
            placeholder="Yazılan metin, ekran, kayıt no, tablo ara…"
            className={`${field} pl-8`}
            aria-label="Ara"
          />
        </form>
        <SearchSelect label="Kişi" placeholder="Herkes" options={actorOptions} value={actor} onChange={setActor} />
        <label className="flex items-center gap-1.5 text-[11.5px] font-bold text-canvas-muted">
          <span className="shrink-0">Başlangıç</span>
          <input type="date" value={since} onChange={(e) => setSince(e.target.value)} className={`${field} sm:w-[150px]`} />
        </label>
        <label className="flex items-center gap-1.5 text-[11.5px] font-bold text-canvas-muted">
          <span className="shrink-0">Bitiş</span>
          <input type="date" value={until} onChange={(e) => setUntil(e.target.value)} className={`${field} sm:w-[150px]`} />
        </label>
      </div>
      <div className="flex flex-wrap gap-1.5" role="group" aria-label="Gösterilen katmanlar">
        {LAYERS.map((l) => {
          const on = layers.includes(l.id);
          return (
            <button
              key={l.id}
              type="button"
              aria-pressed={on}
              onClick={() => toggle(l.id)}
              className={`min-h-9 rounded-full px-3 text-[12px] font-bold transition-[transform,background-color,color] duration-150 ease-out active:scale-[0.97] ${
                on ? 'bg-canvas-ink text-white' : 'bg-slate-100 text-canvas-muted hover:bg-slate-200'
              }`}
            >
              {l.label}
            </button>
          );
        })}
      </div>
      {q.isLoading ? (
        <Loading />
      ) : q.error ? (
        <Note tone="err">{errText(q.error, 'Kayıt okunamadı.')}</Note>
      ) : items.length ? (
        <div className="space-y-3">
          {groups.map((g) => (
            <div key={g.day} className="rounded-2xl border border-slate-100 bg-white/80 px-3 sm:px-4">
              <div className="sticky top-0 z-[1] -mx-3 border-b border-slate-100 bg-white/95 px-3 py-2 text-[12px] font-extrabold capitalize backdrop-blur sm:-mx-4 sm:px-4">
                {g.label}
              </div>
              <ul className="divide-y divide-slate-100">
                {g.items.map((it) => (
                  <Line key={`${it.type}:${it.id}`} it={it} />
                ))}
              </ul>
            </div>
          ))}
        </div>
      ) : (
        <EmptyHint
          title={filtered ? 'Bu süzgece uyan kayıt yok' : 'Henüz kayıt yok'}
          why={filtered ? 'Kişiyi «Herkes» yapın, tarih aralığını genişletin ya da aramayı temizleyin.' : 'Bundan sonra portalda yapılan her iş burada görünür.'}
        />
      )}
      {q.hasNextPage && (
        <button type="button" onClick={() => q.fetchNextPage()} disabled={q.isFetchingNextPage} className={btnGhost}>
          {q.isFetchingNextPage ? 'Yükleniyor…' : 'Daha eski kayıtlar'}
        </button>
      )}
    </Section>
  );
}
