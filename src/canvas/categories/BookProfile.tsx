import { useMemo, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Check, ChevronLeft, Loader2, PenLine, Sparkles, X } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import { Loading, Note, Pill, btnGhost, btnPrimary, errText, field, fmtDate, label as labelCls } from '../admin/ui';
import { Panel } from '../editorial/kit';
import {
  categoriesApi, fmtDay, fmtInt, fmtProb, showValue, STATUS_TONE,
  type BookDetail, type FieldKey, type FieldValue, type ProfileField,
} from './api';
import { CategoriesFrame, Confidence, ROOT, useMeta } from './parts';
import SqlInfo from '../components/SqlInfo';
import { kaynakOf } from '../components/kaynakOf';
import { readableText } from '../components/readableName';

/** Kitap profili: solda CRM'deki bugünkü sınıflamalar (ve site kategorisi), sağda alan alan öneri ve karar. */
export default function BookProfile() {
  const { id = '' } = useParams();
  const qc = useQueryClient();
  const meta = useMeta();
  const me = meta.data?.me;
  const book = useQuery({ queryKey: ['categories', 'book', id], queryFn: () => categoriesApi.book(id), enabled: ENGINE_ENABLED && !!id });
  const text = useQuery({ queryKey: ['categories', 'book-text', id], queryFn: () => categoriesApi.bookText(id), enabled: ENGINE_ENABLED && !!id, retry: false, staleTime: 5 * 60_000 });
  const tree = useQuery({ queryKey: ['categories', 'tree'], queryFn: categoriesApi.tree, enabled: ENGINE_ENABLED, staleTime: 60_000 });
  const options = useQuery({ queryKey: ['categories', 'options'], queryFn: categoriesApi.options, enabled: ENGINE_ENABLED, staleTime: 5 * 60_000 });

  const done = (b: BookDetail) => {
    qc.setQueryData(['categories', 'book', id], (old: BookDetail | undefined) => ({ ...b, canDecide: old?.canDecide ?? b.canDecide }));
    qc.invalidateQueries({ queryKey: ['categories', 'books'] });
    qc.invalidateQueries({ queryKey: ['categories', 'overview'] });
  };
  const propose = useMutation({
    mutationFn: (reset: boolean) => categoriesApi.propose(id, { reset }),
    onSuccess: (b) => { done(b); toast.success(b.modelCalls ? `Öneri hazır (${b.modelCalls} Zeki AI sorusu).` : 'Öneri hazır: CRM beyanından.'); },
    onError: (e) => toast.error(errText(e, 'Öneri üretilemedi.') ?? ''),
  });
  const decide = useMutation({
    mutationFn: (body: Parameters<typeof categoriesApi.decide>[1]) => categoriesApi.decide(id, body),
    onSuccess: (b) => {
      done(b);
      toast.success(b.status === 'onayli' ? 'Profil onaylandı.' : 'Karar kaydedildi.');
      if (b.newTags?.length) toast.message(`Yeni etiket önerisi: ${b.newTags.join(', ')}`, { description: 'Etiket sözlüğünde onay bekliyor.' });
    },
    onError: (e) => toast.error(errText(e, 'Karar kaydedilemedi.') ?? ''),
  });

  const b = book.data;
  const fields = b?.fields ?? {};
  const pendingSure = Object.values(fields).filter((f) => f?.state === 'oneri' && f.confident !== false && f.proposed != null).length;
  const canDecide = !!b?.canDecide;
  const busy = propose.isPending || decide.isPending;
  const nodes = useMemo(() => (tree.data?.inForce?.nodes ?? []).filter((n) => n.status === 'aktif'), [tree.data]);

  return (
    <CategoriesFrame presence={b ? `${b.name ?? ''} · ${b.statusLabel}` : 'Kitap profili'}>
      <Link to={`${ROOT}/kuyruk`} className="inline-flex items-center gap-1 px-1 text-[12px] font-extrabold text-canvas-violet hover:underline">
        <ChevronLeft aria-hidden className="h-3.5 w-3.5" /> Onay kuyruğu
      </Link>
      {book.isLoading && <Loading />}
      {book.error && <Note tone="err">{errText(book.error, 'Kitap açılamadı.')}</Note>}
      {b && (
        <>
          <Panel>
            <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <h2 className="text-[19px] font-extrabold leading-tight tracking-tight">{b.name ?? '—'}</h2>
                  <Pill tone={STATUS_TONE[b.status]}>{b.statusLabel}</Pill>
                </div>
                <p className="mt-1 text-[12px] font-semibold text-canvas-muted">
                  {b.crm.stok ?? '—'} · ISBN {b.crm.isbn ?? '—'} · {b.crm.marka?.name ?? 'yayınevi yok'} · {b.crm.yazar ?? 'yazar yok'}
                  {b.crm.yayincilikStatusu ? ` · ${b.crm.yayincilikStatusu}` : ''}
                </p>
                <p className="mt-0.5 text-[12px] font-semibold text-canvas-muted">
                  Son {b.priorityWindow?.months ?? meta.data?.thresholds.priorityMonths ?? 24} ay{b.priorityWindow?.end ? ` (${fmtDay(b.priorityWindow.end)} tarihine kadar)` : ''} net satış <span className="font-mono tabular-nums text-canvas-ink">{fmtInt(b.priority)}</span> adet
                  <SqlInfo k={kaynakOf(book.data)} alan="_hepsi" label="Kitabın sayıları" className="mx-0.5" /> · Editör {b.crm.editor?.name ?? '—'} · Yayın yönetmeni {b.crm.yonetmen?.name ?? '—'}
                </p>
              </div>
              <div className="flex flex-wrap gap-2">
                {me?.canPropose && (
                  <button type="button" className={btnGhost} disabled={busy} onClick={() => propose.mutate(false)}>
                    {propose.isPending ? <Loader2 aria-hidden className="h-4 w-4 animate-spin" /> : <Sparkles aria-hidden className="h-4 w-4" />}
                    {b.status === 'yok' ? 'Zeki AI önerisi üret' : 'Zeki AI’a yeniden önerdir'}
                  </button>
                )}
                {canDecide && (
                  <button type="button" className={btnPrimary} disabled={busy || !pendingSure} onClick={() => decide.mutate({ all: 'kabul' })}>
                    <Check aria-hidden className="h-4 w-4" /> Emin önerileri onayla{pendingSure ? ` (${pendingSure})` : ''}
                  </button>
                )}
              </div>
            </div>
            {!canDecide && me && (
              <p className="mt-2 text-[11.5px] font-semibold text-canvas-muted">
                {me.canDecide ? 'Bu kitabın editörü ya da yayın yönetmeni değilsiniz; karar için «herkesin kitabı» yetkisi gerekir.' : 'Profil onayı rolünüzde yok; önerileri görebilirsiniz.'}
              </p>
            )}
            {propose.isPending && <p className="mt-2 text-[12px] font-semibold text-canvas-muted">Zeki AI kitabın künyesini ve arka kapak metnini okuyup ağaçta düzey düzey seçiyor…</p>}
            <p className="mt-2 text-[11.5px] leading-snug text-canvas-muted">
              Aşağıda CRM'deki bugünkü sınıflamalar ve Zeki AI'ın alan alan önerileri var. Her öneriyi kabul edin, düzeltin ya da reddedin; «Emin önerileri onayla»
              yalnız Zeki AI'ın emin olduğu önerileri kabul eder. Portal CRM'e yazmaz: onaylanan fark «CRM'e işlenecek» listesine düşer.
            </p>
          </Panel>

          <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.35fr)] lg:gap-4">
            <div className="flex flex-col gap-3 lg:gap-4">
              <Panel>
                <h3 className="text-[14px] font-extrabold">CRM'deki bugünkü sınıflamalar</h3>
                <dl className="mt-2 grid grid-cols-[minmax(0,130px)_minmax(0,1fr)] gap-x-3 gap-y-1.5 text-[12px]">
                  <Row k="Kitaplık" v={b.crm.kitaplik?.name} warn={!b.crm.kitaplik} />
                  <Row k="Dizi" v={b.crm.dizi?.name} />
                  <Row k="Hedef kitle" v={b.crm.hedefKitle?.label} />
                  <Row k="Yaş" v={b.crm.yas ? `${b.crm.yas.bas ?? ''}-${b.crm.yas.bit ?? ''}` : b.crm.yasMetni} />
                  <Row k="Tür" v={b.crm.tur.map((x) => x.name).join(', ') || b.crm.turMetni} warn={!b.crm.tur.length && !b.crm.turMetni} />
                  <Row k="Raf türü" v={b.crm.rafTuru} />
                  <Row k="Web kategorisi" v={b.crm.web} />
                  <Row k="Ürün kategorisi" v={b.crm.urunkategorisi.map((x) => x.name).join(', ')} warn={!b.crm.urunkategorisi.length} />
                  <Row k="Raf kategorisi" v={b.crm.raf.map((x) => x.name).join(', ')} />
                  <Row k="Sergilenecek" v={b.crm.sergilenecek.map((x) => x.name).join(', ')} />
                  <Row k="Tema" v={b.crm.tema.map((x) => x.name).join(', ')} />
                  <Row k="Anahtar kelime" v={b.crm.anahtarkelime.map((x) => x.name).join(', ')} />
                  <Row k="Sitede" v={b.crm.tsoft ? (b.crm.tsoft.categoryPath || b.crm.tsoft.categoryName) : b.crm.ean ? 'Sitede bulunamadı' : 'Barkod yok'} />
                </dl>
                <div className="mt-3 rounded-xl bg-slate-50 px-3 py-2 text-[12px] leading-snug">
                  <span className="font-bold">Ağaçtaki yeri: </span>
                  {b.resolution.path ?? <span className="text-canvas-muted">{b.resolution.reason}</span>}
                  {b.resolution.path && <span className="text-canvas-muted"> — {b.resolution.reason}</span>}
                  {!b.resolution.path && b.resolution.candidatePaths.length > 0 && (
                    <div className="mt-1 text-canvas-muted">Adaylar: {b.resolution.candidatePaths.join(' · ')}</div>
                  )}
                </div>
              </Panel>
              {b.findingsList.some((f) => f.status === 'acik') && (
                <Panel>
                  <h3 className="text-[14px] font-extrabold">Açık tutarsızlıklar</h3>
                  <ul className="mt-2 flex flex-col gap-1.5 text-[12px]">
                    {b.findingsList.filter((f) => f.status === 'acik').map((f) => (
                      <li key={f.id} className="rounded-xl bg-red-50 px-3 py-2 font-semibold text-red-800">
                        {f.ruleLabel}
                        {typeof f.detail?.neden === 'string' && <span className="font-normal"> — {f.detail.neden as string}</span>}
                      </li>
                    ))}
                  </ul>
                </Panel>
              )}
              <Panel>
                <h3 className="text-[14px] font-extrabold">Arka kapak metni</h3>
                {text.isLoading ? <Loading /> : text.error ? (
                  <p className="mt-1 text-[12px] text-canvas-muted">{errText(text.error, 'Metin CRM\'den okunamadı.')}</p>
                ) : (
                  <p className="mt-1 max-h-72 overflow-y-auto whitespace-pre-line text-[12.5px] leading-relaxed">{text.data?.ozet ?? 'CRM\'de arka kapak metni yok.'}</p>
                )}
                {text.data?.spot && <p className="mt-2 text-[12px] italic text-canvas-muted">{text.data.spot}</p>}
              </Panel>
            </div>

            <div className="flex flex-col gap-2">
              {(Object.keys(b.fieldDefs) as FieldKey[]).map((k) => (
                <FieldCard
                  key={k}
                  fkey={k}
                  label={b.fieldDefs[k].label}
                  kind={b.fieldDefs[k].kind}
                  f={fields[k]}
                  canDecide={canDecide}
                  busy={busy}
                  nodes={nodes}
                  choices={k === 'tur' ? (options.data?.tur ?? []).filter((x) => x.active !== false).map((x) => x.name)
                    : k === 'tema' ? (options.data?.tema ?? []).filter((x) => x.active !== false).map((x) => x.name)
                      : k === 'hedef_kitle' ? (options.data?.hedefKitle ?? []).map((x) => x.name)
                        : k === 'etiket' ? options.data?.etiket ?? [] : []}
                  onDecide={(action, value) => {
                    const one: Partial<Record<FieldKey, { action: 'kabul' | 'duzeltme' | 'ret'; value?: FieldValue }>> = {};
                    one[k] = { action, value };
                    decide.mutate({ fields: one });
                  }}
                />
              ))}
              {b.events.length > 0 && (
                <details className="rounded-2xl bg-white/70 px-3 py-2 text-[12px]">
                  <summary className="cursor-pointer font-extrabold">Geçmiş ({b.events.length})</summary>
                  <ul className="mt-2 flex flex-col gap-1">
                    {b.events.map((e, i) => (
                      <li key={i} className="flex flex-wrap gap-x-2 text-canvas-muted">
                        <span className="font-mono">{fmtDate(e.at)}</span>
                        <span className="font-bold text-canvas-ink">{e.user}</span>
                        <span>{b.fieldDefs[e.field as FieldKey]?.label ?? e.field}: {EVENT[e.action] ?? e.action}</span>
                      </li>
                    ))}
                  </ul>
                </details>
              )}
            </div>
          </div>
        </>
      )}
    </CategoriesFrame>
  );
}

const EVENT: Record<string, string> = { oneri: 'öneri', kabul: 'kabul', duzeltme: 'düzeltme', ret: 'ret', sifirla: 'karar sıfırlandı' };

function Row({ k, v, warn }: { k: string; v: string | null | undefined; warn?: boolean }) {
  return (
    <>
      <dt className="font-bold text-canvas-muted">{k}</dt>
      <dd className={`min-w-0 break-words ${warn ? 'font-bold text-red-700' : ''}`}>{v || (warn ? 'Boş' : '—')}</dd>
    </>
  );
}

const STATE_TEXT: Record<string, { text: string; tone: 'ok' | 'warn' | 'err' | 'muted' | 'violet' }> = {
  yok: { text: 'Öneri yok', tone: 'muted' },
  oneri: { text: 'Karar bekliyor', tone: 'violet' },
  kabul: { text: 'Kabul', tone: 'ok' },
  duzeltme: { text: 'Düzeltildi', tone: 'ok' },
  ret: { text: 'Reddedildi', tone: 'err' },
};

function FieldCard({ fkey, label, kind, f, canDecide, busy, nodes, choices, onDecide }: {
  fkey: FieldKey;
  label: string;
  kind: 'node' | 'one' | 'many';
  f?: ProfileField;
  canDecide: boolean;
  busy: boolean;
  nodes: Array<{ id: string; path: string }>;
  choices: string[];
  onDecide: (action: 'kabul' | 'duzeltme' | 'ret', value?: FieldValue) => void;
}) {
  const [editing, setEditing] = useState(false);
  const state = f?.state ?? 'yok';
  const decided = state === 'kabul' || state === 'duzeltme' || state === 'ret';
  const st = STATE_TEXT[state] ?? STATE_TEXT.yok;
  return (
    <section className="glass-panel rounded-2xl p-3 shadow-glass-float">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <h3 className="text-[14px] font-extrabold">{label}</h3>
          <Pill tone={st.tone}>{st.text}</Pill>
          {state === 'oneri' && <Confidence probability={f?.probability} confident={f?.confident} method={f?.method} />}
        </div>
        {canDecide && (state === 'oneri' || decided || state === 'yok') && (
          <div className="flex flex-wrap gap-1.5">
            {state === 'oneri' && f?.proposed != null && (
              <button type="button" className={`${btnPrimary} !min-h-9 !px-2.5`} disabled={busy} onClick={() => onDecide('kabul')}>
                <Check aria-hidden className="h-3.5 w-3.5" /> Kabul
              </button>
            )}
            <button type="button" className={`${btnGhost} !min-h-9 !px-2.5`} disabled={busy} onClick={() => setEditing((v) => !v)} aria-expanded={editing}>
              <PenLine aria-hidden className="h-3.5 w-3.5" /> Düzelt
            </button>
            {state === 'oneri' && (
              <button type="button" className={`${btnGhost} !min-h-9 !px-2.5`} disabled={busy} onClick={() => onDecide('ret')}>
                <X aria-hidden className="h-3.5 w-3.5" /> Ret
              </button>
            )}
          </div>
        )}
      </div>
      <div className="mt-2 grid gap-2 text-[12.5px] sm:grid-cols-2">
        <div className="min-w-0 rounded-xl bg-slate-50 px-3 py-2">
          <div className={labelCls}>CRM'de</div>
          <div className="mt-0.5 break-words font-semibold">{showValue(f?.current, f?.currentPath)}</div>
        </div>
        <div className={`min-w-0 rounded-xl px-3 py-2 ${decided ? 'bg-emerald-50' : 'bg-canvas-violet/5'}`}>
          <div className={labelCls}>{decided ? 'Karar' : 'Öneri'}</div>
          <div className="mt-0.5 break-words font-semibold">
            {decided ? (state === 'ret' ? 'Öneri reddedildi; CRM değeri kalır' : showValue(f?.value, f?.valuePath)) : showValue(f?.proposed, f?.proposedPath)}
          </div>
          {decided && f?.by && <div className="mt-0.5 text-[11px] text-canvas-muted">{f.by} · {fmtDate(f.at ?? null)}</div>}
        </div>
      </div>
      {(f?.source || (f?.evidence?.length ?? 0) > 0 || (f?.alternatives?.length ?? 0) > 0) && (
        <details className="mt-2 text-[12px]">
          <summary className="cursor-pointer font-bold text-canvas-muted">Kaynak ve kanıt</summary>
          <div className="mt-1.5 flex flex-col gap-1 leading-snug">
            {f?.source && <div><span className="font-bold">Kaynak:</span> {readableText(f.source)}</div>}
            {(f?.evidence ?? []).map((e, i) => (
              <div key={i} className="rounded-lg bg-white/80 px-2 py-1">
                {e.term && <span className="font-bold">{e.term} {fmtProb(e.probability) ? `(${fmtProb(e.probability)})` : ''}: </span>}
                {e.text}
              </div>
            ))}
            {(f?.alternatives ?? []).length > 1 && (
              <div className="text-canvas-muted">
                Diğer seçenekler: {(f?.alternatives ?? []).slice(1).map((a) => `${a.path ?? a.label} (${fmtProb(a.probability)})`).join(' · ')}
              </div>
            )}
            {(f?.weak ?? []).length > 0 && (
              <div className="text-canvas-muted">Emin olunmayan adaylar: {(f?.weak ?? []).map((w) => `${w.term} (${fmtProb(w.probability)})`).join(', ')}</div>
            )}
          </div>
        </details>
      )}
      {editing && canDecide && (
        <Editor
          fkey={fkey}
          kind={kind}
          initial={(decided ? f?.value : f?.proposed) ?? f?.current ?? null}
          nodes={nodes}
          choices={choices}
          busy={busy}
          onCancel={() => setEditing(false)}
          onSave={(v) => { onDecide('duzeltme', v); setEditing(false); }}
        />
      )}
    </section>
  );
}

function Editor({ fkey, kind, initial, nodes, choices, busy, onCancel, onSave }: {
  fkey: FieldKey;
  kind: 'node' | 'one' | 'many';
  initial: FieldValue;
  nodes: Array<{ id: string; path: string }>;
  choices: string[];
  busy: boolean;
  onCancel: () => void;
  onSave: (v: FieldValue) => void;
}) {
  const [one, setOne] = useState<string>(typeof initial === 'string' ? initial : '');
  const [many, setMany] = useState<string[]>(Array.isArray(initial) ? initial : []);
  const [q, setQ] = useState('');
  const [free, setFree] = useState('');
  const SHOW = 200;
  const matched = useMemo(() => {
    const t = q.trim().toLocaleLowerCase('tr');
    return t ? choices.filter((c) => c.toLocaleLowerCase('tr').includes(t)) : choices;
  }, [q, choices]);
  const shown = matched.slice(0, SHOW);
  const id = `ed-${fkey}`;
  const value: FieldValue = kind === 'many'
    ? [...many, ...(fkey === 'etiket' ? free.split(',').map((x) => x.trim()).filter(Boolean) : [])]
    : one || null;
  return (
    <div className="mt-2 flex flex-col gap-2 rounded-xl border border-slate-200 bg-white/90 p-2.5">
      {kind === 'node' && (
        <label htmlFor={id} className="flex flex-col gap-1">
          <span className={labelCls}>Ağaç düğümü</span>
          <select id={id} className={field} value={one} onChange={(e) => setOne(e.target.value)}>
            <option value="">Seçin</option>
            {nodes.map((n) => <option key={n.id} value={n.id}>{n.path}</option>)}
          </select>
          {!nodes.length && <span className="text-[11px] text-red-700">Yürürlükte ağaç yok; kategori ağaç onaylanınca seçilir.</span>}
        </label>
      )}
      {kind === 'one' && fkey === 'hedef_kitle' && (
        <label htmlFor={id} className="flex flex-col gap-1">
          <span className={labelCls}>Hedef kitle</span>
          <select id={id} className={field} value={one} onChange={(e) => setOne(e.target.value)}>
            <option value="">Seçin</option>
            {choices.map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
        </label>
      )}
      {kind === 'one' && fkey === 'yas' && (
        <label htmlFor={id} className="flex flex-col gap-1">
          <span className={labelCls}>Yaş aralığı (ör. 6-10)</span>
          <input id={id} className={field} inputMode="numeric" value={one} onChange={(e) => setOne(e.target.value)} />
        </label>
      )}
      {kind === 'many' && (
        <div className="flex flex-col gap-1.5">
          {many.length > 0 && (
            <div className="flex flex-wrap gap-1">
              {many.map((m) => (
                <button key={m} type="button" onClick={() => setMany(many.filter((x) => x !== m))}
                  className="inline-flex min-h-8 items-center gap-1 rounded-lg bg-canvas-violet/10 px-2 text-[12px] font-bold text-canvas-violet">
                  {m} <X aria-hidden className="h-3 w-3" />
                </button>
              ))}
            </div>
          )}
          <input className={field} placeholder="Sözlükte ara" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Sözlükte ara" />
          <div className="max-h-44 overflow-y-auto rounded-lg border border-slate-100">
            {shown.map((c) => (
              <label key={c} className="flex min-h-9 cursor-pointer items-center gap-2 px-2 text-[12.5px] hover:bg-slate-50">
                <input type="checkbox" checked={many.includes(c)} onChange={(e) => setMany(e.target.checked ? [...many, c] : many.filter((x) => x !== c))} />
                {c}
              </label>
            ))}
            {!shown.length && <p className="px-2 py-2 text-[12px] text-canvas-muted">Sözlükte eşleşen kayıt yok.</p>}
          </div>
          {matched.length > SHOW && (
            <p className="text-[11px] text-canvas-muted">{matched.length} kayıttan ilk {SHOW}'ü listede; aramayı daraltın.</p>
          )}
          {fkey === 'etiket' && (
            <label className="flex flex-col gap-1">
              <span className={labelCls}>Sözlükte olmayan etiket (virgülle) — onaya düşer</span>
              <input className={field} value={free} onChange={(e) => setFree(e.target.value)} />
            </label>
          )}
        </div>
      )}
      <div className="flex justify-end gap-2">
        <button type="button" className={btnGhost} onClick={onCancel}>Vazgeç</button>
        <button type="button" className={btnPrimary} disabled={busy || value === null || (Array.isArray(value) && !value.length)} onClick={() => onSave(value)}>
          Düzeltmeyi kaydet
        </button>
      </div>
    </div>
  );
}
