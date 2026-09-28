import { useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { ArrowDown, ArrowRight, ArrowUp, FileStack, Lightbulb, Loader2, Pencil, Plus, Sparkles, Trash2, X } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import { Loading, Note, Pill, btnGhost, btnPrimary, errText, field, label as labelCls } from '../admin/ui';
import { Panel } from '../editorial/kit';
import { fmtDay, fmtTime, kurulApi, waitJob, type AgendaItem, type Decision, type KurulMeta, type Meeting, type MinuteSuggestion } from './api';
import { AskSheet, Empty, KurulFrame, SelectInput, TextInput } from './parts';
import { ActionCard, MeetingSheet } from './KurulScreen';

/** Toplantı sayfası: gündem (sırala, öneri al), kararlar ve aksiyonları, sekreter notu ve Zeki AI karar önerisi,
 *  kurul paketleri. Yazma yalnız hazırlama yetkisiyle; kurul üyesi okur, kendi aksiyonunu günceller. */

type ActionDraft = { eylem: string; sahip: string; termin: string };
type DecisionDraft = { metin: string; gundemSira: string; oyOzeti: string; aksiyonlar: ActionDraft[] };
const EMPTY_DECISION: DecisionDraft = { metin: '', gundemSira: '', oyOzeti: '', aksiyonlar: [] };

export default function MeetingPage() {
  const { id = '' } = useParams();
  const meta = useQuery({ queryKey: ['kurul', 'meta'], queryFn: kurulApi.meta, enabled: ENGINE_ENABLED, staleTime: 60_000 });
  const q = useQuery({ queryKey: ['kurul', 'meeting', id], queryFn: () => kurulApi.meeting(id), enabled: ENGINE_ENABLED && !!id });
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<DecisionDraft>(EMPTY_DECISION);
  const m = q.data;
  const me = meta.data?.me;
  return (
    <KurulFrame
      title={m?.baslik ?? 'Toplantı'}
      lead={m ? `${m.turAdi} · ${fmtDay(m.tarih)}${m.saat ? ` ${m.saat}` : ''}${m.yer ? ` · ${m.yer}` : ''} · ${m.durumAdi}` : 'Toplantı okunuyor…'}
      back={{ to: '/kurul?sekme=toplantilar', label: 'Toplantılar' }}
      aside={me?.canPrepare && m ? (
        <div className="flex justify-start lg:justify-end">
          <button type="button" className={btnGhost} onClick={() => setEditing(true)}><Pencil aria-hidden className="h-4 w-4" /> Düzenle</button>
        </div>
      ) : undefined}
    >
      {q.isLoading && <Loading />}
      {q.error && <Note tone="err">{errText(q.error, 'Toplantı okunamadı.')}</Note>}
      {m && meta.data && (
        <>
          {m.katilimcilar.length > 0 && <p className="px-1 text-[12px] text-canvas-muted">Katılımcılar: {m.katilimcilar.join(', ')}</p>}
          <div className="grid grid-cols-1 gap-3 lg:grid-cols-2 lg:gap-4">
            <AgendaPanel key={JSON.stringify(m.gundem ?? [])} m={m} meta={meta.data} />
            <PackagesPanel m={m} meta={meta.data} />
          </div>
          <Decisions m={m} meta={meta.data} />
          {meta.data.me.canPrepare && (
            <div className="grid grid-cols-1 gap-3 lg:grid-cols-2 lg:gap-4">
              <DecisionForm m={m} draft={draft} setDraft={setDraft} />
              <MinutesPanel m={m} meta={meta.data} onUse={(s) => setDraft({
                metin: s.metin, gundemSira: s.gundemSira ? String(s.gundemSira) : '', oyOzeti: '',
                aksiyonlar: s.aksiyonlar.map((a) => ({ eylem: a.eylem + (a.sahipAdayi ? ` (notta: ${a.sahipAdayi})` : ''), sahip: '', termin: a.terminAdayi ?? '' })),
              })} />
            </div>
          )}
          {editing && <MeetingSheet open meta={meta.data} initial={m} onClose={() => setEditing(false)} onSaved={() => undefined} />}
        </>
      )}
    </KurulFrame>
  );
}

/* ------------------------------------------------------------------ gündem */

function AgendaPanel({ m, meta }: { m: Meeting; meta: KurulMeta }) {
  const qc = useQueryClient();
  const prep = meta.me.canPrepare;
  const [items, setItems] = useState<AgendaItem[]>(m.gundem ?? []);
  const [dirty, setDirty] = useState(false);
  const suggest = useQuery({ queryKey: ['kurul', 'agenda-suggest', m.id], queryFn: () => kurulApi.suggestAgenda(m.id), enabled: false });
  const save = useMutation({
    mutationFn: () => kurulApi.setAgenda(m.id, items),
    onSuccess: () => {
      toast.success('Gündem kaydedildi.');
      setDirty(false);
      qc.invalidateQueries({ queryKey: ['kurul', 'meeting', m.id] });
    },
    onError: (e) => toast.error(errText(e, 'Gündem kaydedilemedi.')),
  });
  const set = (next: AgendaItem[]) => {
    setItems(next);
    setDirty(true);
  };
  const move = (i: number, d: number) => {
    const next = [...items];
    const [x] = next.splice(i, 1);
    next.splice(i + d, 0, x);
    set(next);
  };
  return (
    <Panel>
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-[15px] font-extrabold tracking-tight">Gündem</h2>
        {prep && (
          <span className="flex flex-wrap gap-2">
            <button type="button" className={btnGhost} onClick={() => suggest.refetch()} disabled={suggest.isFetching}>
              {suggest.isFetching ? <Loader2 aria-hidden className="h-4 w-4 animate-spin" /> : <Lightbulb aria-hidden className="h-4 w-4" />} Öneri al
            </button>
            <button type="button" className={btnGhost} onClick={() => set([...items, { baslik: '', tur: 'bilgi', sunan: null, sureDk: null, ekRef: null }])}>
              <Plus aria-hidden className="h-4 w-4" /> Madde
            </button>
          </span>
        )}
      </div>
      {suggest.data && suggest.data.items.length > 0 && prep && (
        <div className="mb-2 flex flex-col gap-1.5 rounded-xl bg-slate-50 p-2">
          <span className={labelCls}>Geciken aksiyon ve kırmızı göstergelerden öneri</span>
          {suggest.data.items.map((s, i) => (
            <button key={i} type="button" className="flex min-h-11 items-center justify-between gap-2 rounded-lg bg-white px-2 py-1.5 text-left text-[12.5px] hover:bg-white/70 sm:min-h-0"
              onClick={() => set([...items, { baslik: s.baslik, tur: s.tur, sunan: s.sunan ?? null, sureDk: null, ekRef: null }])}>
              <span className="min-w-0 break-words font-bold">{s.baslik}</span>
              <Plus aria-hidden className="h-4 w-4 shrink-0" />
            </button>
          ))}
        </div>
      )}
      {suggest.data && suggest.data.items.length === 0 && prep && <p className="mb-2 text-[12px] text-canvas-muted">Geciken aksiyon ya da kırmızı gösterge yok.</p>}
      {items.length === 0 ? <Empty>Gündem girilmedi.</Empty> : (
        <ol className="flex flex-col gap-1.5">
          {items.map((it, i) => (
            <li key={i} className="rounded-xl bg-white/80 p-2 ring-1 ring-slate-100">
              {prep ? (
                <div className="flex flex-col gap-1.5">
                  <div className="flex items-center gap-1.5">
                    <span className="w-6 shrink-0 text-center font-mono text-[12px] font-bold tabular-nums">{i + 1}.</span>
                    <input aria-label={`${i + 1}. madde başlığı`} className={field} value={it.baslik} onChange={(e) => set(items.map((x, j) => (j === i ? { ...x, baslik: e.target.value } : x)))} />
                  </div>
                  <div className="flex flex-wrap items-center gap-1.5 pl-7">
                    <select aria-label="Madde türü" className={`${field} w-auto`} value={it.tur} onChange={(e) => set(items.map((x, j) => (j === i ? { ...x, tur: e.target.value as AgendaItem['tur'] } : x)))}>
                      {Object.entries(meta.gundemTurleri).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                    </select>
                    <input aria-label="Sunan" placeholder="Sunan" className={`${field} w-36`} value={it.sunan ?? ''} onChange={(e) => set(items.map((x, j) => (j === i ? { ...x, sunan: e.target.value || null } : x)))} />
                    <input aria-label="Süre (dk)" placeholder="dk" inputMode="numeric" className={`${field} w-16`} value={it.sureDk ?? ''}
                      onChange={(e) => set(items.map((x, j) => (j === i ? { ...x, sureDk: e.target.value ? Number(e.target.value.replace(/\D/g, '')) || null : null } : x)))} />
                    <span className="ml-auto flex gap-1">
                      <button type="button" className={btnGhost} aria-label="Yukarı" disabled={i === 0} onClick={() => move(i, -1)}><ArrowUp aria-hidden className="h-4 w-4" /></button>
                      <button type="button" className={btnGhost} aria-label="Aşağı" disabled={i === items.length - 1} onClick={() => move(i, 1)}><ArrowDown aria-hidden className="h-4 w-4" /></button>
                      <button type="button" className={btnGhost} aria-label="Maddeyi sil" onClick={() => set(items.filter((_, j) => j !== i))}><X aria-hidden className="h-4 w-4" /></button>
                    </span>
                  </div>
                </div>
              ) : (
                <div className="flex flex-wrap items-baseline gap-x-2">
                  <span className="font-mono text-[12px] font-bold tabular-nums">{i + 1}.</span>
                  <span className="min-w-0 break-words text-[13px] font-bold">{it.baslik}</span>
                  <span className="text-[11.5px] text-canvas-muted">{[it.turAdi, it.sunan, it.sureDk ? `${it.sureDk} dk` : null].filter(Boolean).join(' · ')}</span>
                </div>
              )}
            </li>
          ))}
        </ol>
      )}
      {prep && dirty && (
        <div className="mt-2 flex justify-end gap-2">
          <button type="button" className={btnGhost} onClick={() => { setItems(m.gundem ?? []); setDirty(false); }}>Vazgeç</button>
          <button type="button" className={btnPrimary} disabled={save.isPending || items.some((x) => !x.baslik.trim())} onClick={() => save.mutate()}>Gündemi kaydet</button>
        </div>
      )}
    </Panel>
  );
}

/* ------------------------------------------------------------------ paketler */

function PackagesPanel({ m, meta }: { m: Meeting; meta: KurulMeta }) {
  const nav = useNavigate();
  const qc = useQueryClient();
  const compile = useMutation({
    mutationFn: () => kurulApi.compile(m.id),
    onSuccess: (p) => {
      toast.success(`Paket v${p.surum} derlendi.`);
      qc.invalidateQueries({ queryKey: ['kurul'] });
      nav(`/kurul/paket/${p.id}`);
    },
    onError: (e) => toast.error(errText(e, 'Paket derlenemedi.')),
  });
  const pk = m.paketler ?? [];
  return (
    <Panel>
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-[15px] font-extrabold tracking-tight">Kurul paketi</h2>
        {meta.me.canPrepare && (
          <button type="button" className={btnPrimary} disabled={compile.isPending} onClick={() => compile.mutate()}>
            {compile.isPending ? <Loader2 aria-hidden className="h-4 w-4 animate-spin" /> : <FileStack aria-hidden className="h-4 w-4" />}
            {pk.length && pk[0].durum === 'taslak' ? 'Yeniden derle' : 'Paketi derle'}
          </button>
        )}
      </div>
      <p className="mb-2 text-[11.5px] text-canvas-muted">Derleme göstergelerin son ölçümünü, onaylı yorumları, gündemi, önceki kararları ve onaylı risk/pazar özetlerini tek anlık görüntüde toplar. Dondurulan paket değişmez; düzeltme yeni sürümdür.</p>
      {pk.length === 0 ? <Empty>Paket yok.</Empty> : (
        <ul className="flex flex-col gap-1.5">
          {pk.map((p) => (
            <li key={p.id}>
              <Link to={`/kurul/paket/${p.id}`} className="flex min-h-11 items-center justify-between gap-2 rounded-xl bg-white/80 px-3 py-2 hover:bg-white">
                <span className="min-w-0">
                  <span className="block text-[13px] font-bold">Sürüm {p.surum}</span>
                  <span className="block text-[11.5px] text-canvas-muted">derlendi {fmtTime(p.derleme)}{p.dondurma ? ` · donduruldu ${fmtTime(p.dondurma)}` : ''}</span>
                </span>
                <span className="flex items-center gap-1.5"><Pill tone={p.durum === 'taslak' ? 'warn' : 'ok'}>{p.durumAdi}</Pill><ArrowRight aria-hidden className="h-4 w-4" /></span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </Panel>
  );
}

/* ------------------------------------------------------------------ kararlar */

function Decisions({ m, meta }: { m: Meeting; meta: KurulMeta }) {
  const decs = m.kararlar ?? [];
  return (
    <Panel>
      <h2 className="mb-2 text-[15px] font-extrabold tracking-tight">Kararlar ve aksiyonlar</h2>
      {decs.length === 0 ? <Empty>Bu toplantıda karar kaydı yok.</Empty> : (
        <ol className="flex flex-col gap-3">
          {decs.map((d, i) => <li key={d.id}><DecisionBlock d={d} n={i + 1} meta={meta} /></li>)}
        </ol>
      )}
    </Panel>
  );
}

function DecisionBlock({ d, n, meta }: { d: Decision; n: number; meta: KurulMeta }) {
  const qc = useQueryClient();
  const prep = meta.me.canPrepare;
  const [adding, setAdding] = useState(false);
  const [a, setA] = useState<ActionDraft>({ eylem: '', sahip: '', termin: '' });
  const [removing, setRemoving] = useState(false);
  const add = useMutation({
    mutationFn: () => kurulApi.addAction(d.id, { eylem: a.eylem, sahip: a.sahip || undefined, termin: a.termin || undefined }),
    onSuccess: () => {
      toast.success('Aksiyon eklendi.');
      setA({ eylem: '', sahip: '', termin: '' });
      setAdding(false);
      qc.invalidateQueries({ queryKey: ['kurul'] });
    },
    onError: (e) => toast.error(errText(e, 'Aksiyon eklenemedi.')),
  });
  const del = useMutation({
    mutationFn: () => kurulApi.deleteDecision(d.id),
    onSuccess: () => {
      toast.success('Karar silindi.');
      setRemoving(false);
      qc.invalidateQueries({ queryKey: ['kurul'] });
    },
    onError: (e) => toast.error(errText(e, 'Karar silinemedi.')),
  });
  return (
    <div className="rounded-2xl bg-white/70 p-3 ring-1 ring-slate-100">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="text-[11px] font-bold uppercase tracking-wide text-canvas-muted">Karar {n}{d.gundemSira ? ` · gündem ${d.gundemSira}` : ''}{d.oyOzeti ? ` · ${d.oyOzeti}` : ''}</div>
          <p className="whitespace-pre-wrap break-words text-[13.5px] font-bold leading-snug">{d.metin}</p>
        </div>
        {prep && (
          <button type="button" className={btnGhost} aria-label="Kararı sil" onClick={() => setRemoving(true)}><Trash2 aria-hidden className="h-4 w-4" /></button>
        )}
      </div>
      {d.aksiyonlar.length > 0 && (
        <div className="mt-2 grid grid-cols-1 gap-2 md:grid-cols-2">
          {d.aksiyonlar.map((x) => <ActionCard key={x.id} a={x} meta={meta} />)}
        </div>
      )}
      {prep && (adding ? (
        <form className="mt-2 flex flex-col gap-2" onSubmit={(e) => { e.preventDefault(); add.mutate(); }}>
          <TextInput id={`a-e-${d.id}`} label="Eylem" value={a.eylem} onChange={(v) => setA({ ...a, eylem: v })} />
          <div className="grid grid-cols-2 gap-2">
            <TextInput id={`a-s-${d.id}`} label="Sahip (portal hesabı)" value={a.sahip} onChange={(v) => setA({ ...a, sahip: v })} />
            <TextInput id={`a-t-${d.id}`} label="Termin" type="date" value={a.termin} onChange={(v) => setA({ ...a, termin: v })} />
          </div>
          <div className="flex justify-end gap-2">
            <button type="button" className={btnGhost} onClick={() => setAdding(false)}>Vazgeç</button>
            <button type="submit" className={btnPrimary} disabled={!a.eylem.trim() || add.isPending}>Ekle</button>
          </div>
        </form>
      ) : (
        <button type="button" className={`${btnGhost} mt-2`} onClick={() => setAdding(true)}><Plus aria-hidden className="h-4 w-4" /> Aksiyon</button>
      ))}
      <AskSheet open={removing} title="Kararı sil" message="Karar ve açık aksiyonları silinsin mi? Aksiyonu kapanmış karar silinmez." confirm="Sil" danger
        busy={del.isPending} onClose={() => setRemoving(false)} onConfirm={() => del.mutate()} />
    </div>
  );
}

function DecisionForm({ m, draft, setDraft }: { m: Meeting; draft: DecisionDraft; setDraft: (d: DecisionDraft) => void }) {
  const qc = useQueryClient();
  const agenda: Record<string, string> = Object.fromEntries((m.gundem ?? []).map((g, i) => [String(g.sira ?? i + 1), `${g.sira ?? i + 1}. ${g.baslik}`]));
  const save = useMutation({
    mutationFn: () => kurulApi.addDecision(m.id, {
      metin: draft.metin, gundemSira: draft.gundemSira ? Number(draft.gundemSira) : null, oyOzeti: draft.oyOzeti || undefined,
      aksiyonlar: draft.aksiyonlar.filter((a) => a.eylem.trim()).map((a) => ({ eylem: a.eylem, sahip: a.sahip || undefined, termin: a.termin || undefined })),
    }),
    onSuccess: () => {
      toast.success('Karar kaydedildi.');
      setDraft(EMPTY_DECISION);
      qc.invalidateQueries({ queryKey: ['kurul'] });
    },
    onError: (e) => toast.error(errText(e, 'Karar kaydedilemedi.')),
  });
  const setAct = (i: number, patch: Partial<ActionDraft>) => setDraft({ ...draft, aksiyonlar: draft.aksiyonlar.map((a, j) => (j === i ? { ...a, ...patch } : a)) });
  return (
    <Panel>
      <h2 className="mb-2 text-[15px] font-extrabold tracking-tight">Karar yaz</h2>
      <form className="flex flex-col gap-2" onSubmit={(e) => { e.preventDefault(); save.mutate(); }}>
        <TextInput id="d-metin" label="Karar metni" value={draft.metin} onChange={(v) => setDraft({ ...draft, metin: v })} area />
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
          <SelectInput id="d-gs" label="Gündem maddesi" value={draft.gundemSira} onChange={(v) => setDraft({ ...draft, gundemSira: v })} options={agenda} empty="—" />
          <TextInput id="d-oy" label="Oy özeti" value={draft.oyOzeti} onChange={(v) => setDraft({ ...draft, oyOzeti: v })} placeholder="Oybirliği, 4 kabul 1 ret…" />
        </div>
        {draft.aksiyonlar.map((a, i) => (
          <div key={i} className="flex flex-col gap-1.5 rounded-xl bg-slate-50 p-2">
            <div className="flex items-center justify-between">
              <span className={labelCls}>Aksiyon {i + 1}</span>
              <button type="button" className={btnGhost} aria-label="Aksiyonu çıkar" onClick={() => setDraft({ ...draft, aksiyonlar: draft.aksiyonlar.filter((_, j) => j !== i) })}><X aria-hidden className="h-4 w-4" /></button>
            </div>
            <input aria-label="Eylem" className={field} value={a.eylem} placeholder="Eylem" onChange={(e) => setAct(i, { eylem: e.target.value })} />
            <div className="grid grid-cols-2 gap-1.5">
              <input aria-label="Sahip (portal hesabı)" className={field} value={a.sahip} placeholder="Sahip (portal hesabı)" onChange={(e) => setAct(i, { sahip: e.target.value })} />
              <input aria-label="Termin" type="date" className={field} value={a.termin} onChange={(e) => setAct(i, { termin: e.target.value })} />
            </div>
          </div>
        ))}
        <div className="flex flex-wrap justify-between gap-2">
          <button type="button" className={btnGhost} onClick={() => setDraft({ ...draft, aksiyonlar: [...draft.aksiyonlar, { eylem: '', sahip: '', termin: '' }] })}>
            <Plus aria-hidden className="h-4 w-4" /> Aksiyon
          </button>
          <button type="submit" className={btnPrimary} disabled={!draft.metin.trim() || save.isPending}>Kararı kaydet</button>
        </div>
      </form>
    </Panel>
  );
}

/* ------------------------------------------------------------------ notlar ve Zeki AI karar önerisi */

function MinutesPanel({ m, meta, onUse }: { m: Meeting; meta: KurulMeta; onUse: (s: MinuteSuggestion) => void }) {
  const qc = useQueryClient();
  const [notes, setNotes] = useState(m.notlar ?? '');
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<{ oneriler: MinuteSuggestion[]; dusenler: string[] } | null>(null);
  const saveNotes = useMutation({
    mutationFn: () => kurulApi.updateMeeting(m.id, { notlar: notes }),
    onSuccess: () => {
      toast.success('Notlar kaydedildi.');
      qc.invalidateQueries({ queryKey: ['kurul', 'meeting', m.id] });
    },
    onError: (e) => toast.error(errText(e, 'Notlar kaydedilemedi.')),
  });
  async function draft() {
    setBusy(true);
    try {
      const j = await kurulApi.draftMinutes(m.id, notes);
      const done = await waitJob(j.id);
      if (done.durum === 'hata') toast.error(done.hata || 'Öneri hazırlanamadı.');
      else setResult(done.sonuc as { oneriler: MinuteSuggestion[]; dusenler: string[] });
    } catch (e) {
      toast.error(errText(e, 'Öneri istenemedi.'));
    } finally {
      setBusy(false);
    }
  }
  return (
    <Panel>
      <h2 className="mb-2 text-[15px] font-extrabold tracking-tight">Toplantı notları</h2>
      <textarea aria-label="Toplantı notları" className={`${field} min-h-[160px]`} value={notes} onChange={(e) => setNotes(e.target.value)}
        placeholder="Toplantıda konuşulanlar, alınan kararlar, kim ne yapacak…" />
      <div className="mt-2 flex flex-wrap gap-2">
        <button type="button" className={btnGhost} disabled={saveNotes.isPending} onClick={() => saveNotes.mutate()}>Notları kaydet</button>
        {meta.modelVar && (
          <button type="button" className={btnGhost} disabled={busy || !notes.trim()} onClick={draft}>
            {busy ? <Loader2 aria-hidden className="h-4 w-4 animate-spin" /> : <Sparkles aria-hidden className="h-4 w-4" />} Zeki AI karar önerisi
          </button>
        )}
      </div>
      <p className="mt-1 text-[11px] text-canvas-muted">Öneri kaydedilmez: «Forma al» ile karar formuna düşer, sahibi siz atarsınız. Notlarda geçmeyen sayı, tarih ya da kişi içeren öneri atılır.</p>
      {result && (
        <div className="mt-2 flex flex-col gap-1.5">
          {result.oneriler.length === 0 && <p className="text-[12px] text-canvas-muted">Notlardan karar çıkmadı.</p>}
          {result.oneriler.map((s, i) => (
            <div key={i} className="rounded-xl bg-white/80 p-2 ring-1 ring-slate-100">
              <p className="break-words text-[12.5px] font-bold">{s.metin}</p>
              {s.aksiyonlar.map((a, j) => <p key={j} className="text-[11.5px] text-canvas-muted">• {a.eylem}{a.sahipAdayi ? ` — ${a.sahipAdayi}` : ''}{a.terminAdayi ? `, ${fmtDay(a.terminAdayi)}` : ''}</p>)}
              <button type="button" className={`${btnGhost} mt-1`} onClick={() => onUse(s)}>Forma al</button>
            </div>
          ))}
          {result.dusenler.length > 0 && <Note tone="warn">{result.dusenler.length} öneri notlarda olmayan bilgi içerdiği için atıldı.</Note>}
        </div>
      )}
    </Panel>
  );
}
