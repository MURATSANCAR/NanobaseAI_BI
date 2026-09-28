import { useState, type ReactNode } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { ENGINE_ENABLED } from '../../engine';
import { Note, Pill, btnGhost, btnPrimary, errText, field, label as labelCls } from '../../admin/ui';
import { fmtDay } from '../hrApi';
import { Block, HrFrame } from '../parts';
import { engApi, type EngMeta, type Suggestion } from './engApi';

/** M58 Öneri kutusu: herkes adlı ya da adsız öneri verir ve durumunu izler (adsızda takip koduyla). İK konu düzeltir, birime
 *  yönlendirir, cevaplar; yönlendirilen birimin yöneticisi kendine gelenleri cevaplar. «Bir çalışanla ilgili şikâyet» İK'da kalır. */
export default function SuggestionsScreen() {
  const meta = useQuery({ queryKey: ['hr', 'eng', 'meta'], queryFn: engApi.meta, enabled: ENGINE_ENABLED, staleTime: 60_000 });
  const can = meta.data?.me.can;
  return (
    <HrFrame crumb="Öneri kutusu" title="Öneri kutusu" lead="Önerinizi adınızla ya da adsız verin. Adsız öneride adınız hiçbir yere yazılmaz; durumunu size verilen takip koduyla izlersiniz.">
      <NewSuggestion />
      <Mine />
      {meta.data && (can?.suggestionAdmin || can?.suggestionAnswer) && <Inbox meta={meta.data} />}
    </HrFrame>
  );
}

function NewSuggestion() {
  const qc = useQueryClient();
  const [text, setText] = useState('');
  const [anon, setAnon] = useState(false);
  const [code, setCode] = useState<string | null>(null);
  const send = useMutation({
    mutationFn: () => engApi.createSuggestion(text, anon),
    onSuccess: (r) => { setText(''); setCode(r.followCode); toast.success('Öneriniz alındı.'); void qc.invalidateQueries({ queryKey: ['hr', 'eng', 'sugg'] }); },
    onError: (e) => toast.error(errText(e, 'Gönderilemedi.')),
  });
  return (
    <Block title="Öneri ver">
      <textarea className={`${field} min-h-[110px]`} value={text} maxLength={4000} onChange={(e) => setText(e.target.value)} placeholder="Önerinizi yazın" />
      <div className="mt-2 flex flex-wrap items-center justify-between gap-2">
        <label className="flex min-h-11 items-center gap-2 text-[12.5px] font-bold"><input type="checkbox" checked={anon} onChange={(e) => setAnon(e.target.checked)} />Adsız gönder</label>
        <button type="button" className={btnPrimary} disabled={send.isPending || text.trim().length < 5} onClick={() => send.mutate()}>Gönder</button>
      </div>
      {code && <Note tone="warn">Takip kodunuz: <b className="font-mono">{code}</b> — bir yere not edin; tekrar gösterilmez.</Note>}
    </Block>
  );
}

function Mine() {
  const mine = useQuery({ queryKey: ['hr', 'eng', 'sugg', 'mine'], queryFn: engApi.mySuggestions, enabled: ENGINE_ENABLED });
  const [code, setCode] = useState('');
  const track = useMutation({ mutationFn: () => engApi.track(code), onError: (e) => toast.error(errText(e, 'Kod bulunamadı.')) });
  return (
    <div className="grid grid-cols-1 gap-3 lg:grid-cols-2 lg:gap-4">
      <Block title="Adlı önerilerim">
        {!mine.data?.items.length && <div className="text-[12px] text-canvas-muted">Adlı öneriniz yok.</div>}
        <ul className="flex flex-col gap-1.5">{(mine.data?.items ?? []).map((s) => <li key={s.id}><Card s={s} /></li>)}</ul>
      </Block>
      <Block title="Adsız önerimi izle">
        <div className="flex gap-2">
          <input className={field} value={code} onChange={(e) => setCode(e.target.value.toUpperCase())} placeholder="ABCDE-FGHJK" />
          <button type="button" className={btnGhost} disabled={track.isPending || code.replace(/[^A-Z0-9]/g, '').length !== 10} onClick={() => track.mutate()}>Bak</button>
        </div>
        {track.data && <div className="mt-2"><Card s={track.data} /></div>}
      </Block>
    </div>
  );
}

function Card({ s, children }: { s: Suggestion; children?: ReactNode }) {
  return (
    <div className="rounded-xl bg-white/80 p-2.5 text-[12.5px]">
      <div className="flex flex-wrap items-center gap-1.5">
        <span className="text-[11.5px] text-canvas-muted">{fmtDay(s.createdDay)}</span>
        <Pill tone={s.state === 'cevaplandi' ? 'ok' : s.state === 'kapandi' ? 'muted' : 'warn'}>{s.stateLabel}</Pill>
        {s.topic && <Pill tone={s.personal ? 'err' : 'violet'}>{s.topic}{s.topicSource === 'zeki' && s.topicProb !== null ? ` · Zeki AI %${Math.round(s.topicProb * 100)}` : ''}</Pill>}
        {s.routedUnitName && <Pill tone="muted">→ {s.routedUnitName}</Pill>}
        {s.author && <span className="text-[11.5px] font-bold">{s.author}</span>}
        {s.anonymous && <span className="text-[11.5px] text-canvas-muted">adsız</span>}
      </div>
      <div className="mt-1 whitespace-pre-wrap break-words">{s.text}</div>
      {s.answer && <div className="mt-1.5 rounded-lg bg-emerald-50 px-2.5 py-1.5"><span className="font-bold">Cevap:</span> {s.answer}</div>}
      {children}
    </div>
  );
}

function Inbox({ meta }: { meta: EngMeta }) {
  const qc = useQueryClient();
  const [state, setState] = useState('');
  const q = useQuery({ queryKey: ['hr', 'eng', 'sugg', 'inbox', state], queryFn: () => engApi.suggestions(state) });
  const act = useMutation({
    mutationFn: ({ id, a, b }: { id: string; a: 'route' | 'topic' | 'answer' | 'close'; b: Record<string, unknown> }) => engApi.suggestionAction(id, a, b),
    onSuccess: () => { toast.success('Kaydedildi.'); void qc.invalidateQueries({ queryKey: ['hr', 'eng', 'sugg'] }); },
    onError: (e) => toast.error(errText(e, 'İşlem yapılamadı.')),
  });
  const admin = meta.me.can.suggestionAdmin;
  return (
    <Block title={admin ? 'Gelen öneriler' : 'Birimime yönlendirilen öneriler'}
      action={
        <select className={`${field} w-auto`} value={state} onChange={(e) => setState(e.target.value)} aria-label="Durum">
          <option value="">Hepsi</option>{Object.entries(meta.suggestionStates).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </select>
      }>
      {q.error && <Note tone="err">{errText(q.error, 'Öneriler okunamadı.')}</Note>}
      {q.data && !q.data.items.length && <div className="text-[12px] text-canvas-muted">Öneri yok.</div>}
      <ul className="flex flex-col gap-2">
        {(q.data?.items ?? []).map((s) => (
          <li key={s.id}>
            <Card s={s}><Handle s={s} admin={admin} meta={meta} topics={q.data?.topics ?? meta.topics} busy={act.isPending} onAct={(a, b) => act.mutate({ id: s.id, a, b })} /></Card>
          </li>
        ))}
      </ul>
    </Block>
  );
}

function Handle({ s, admin, meta, topics, busy, onAct }: {
  s: Suggestion; admin: boolean; meta: EngMeta; topics: string[]; busy: boolean; onAct: (a: 'route' | 'topic' | 'answer' | 'close', b: Record<string, unknown>) => void;
}) {
  const [unit, setUnit] = useState(s.routedUnitId ?? '');
  const [answer, setAnswer] = useState('');
  if (s.state === 'kapandi') return null;
  return (
    <div className="mt-2 flex flex-col gap-2 border-t border-slate-100 pt-2">
      {admin && (
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
          <label className="flex flex-col gap-1"><span className={labelCls}>Konu</span>
            <select className={field} value={s.topic ?? ''} disabled={busy} onChange={(e) => onAct('topic', { topic: e.target.value })}>
              <option value="" disabled>Seçin</option>{topics.map((t) => <option key={t} value={t}>{t}</option>)}
            </select>
          </label>
          {!s.personal && s.state !== 'cevaplandi' && (
            <label className="flex flex-col gap-1"><span className={labelCls}>Birime yönlendir</span>
              <div className="flex gap-2">
                <select className={field} value={unit} onChange={(e) => setUnit(e.target.value)}><option value="">Seçin</option>{meta.units.map((u) => <option key={u.id} value={u.id}>{u.name}</option>)}</select>
                <button type="button" className={btnGhost} disabled={busy || !unit} onClick={() => onAct('route', { unitId: unit })}>Yönlendir</button>
              </div>
            </label>
          )}
          {s.personal && <Note tone="warn">Bir çalışanla ilgili şikâyet: birime yönlendirilmez, İK'da kalır.</Note>}
        </div>
      )}
      {s.state !== 'cevaplandi' && (
        <div className="flex flex-col gap-2 sm:flex-row">
          <textarea className={`${field} min-h-[60px] flex-1`} value={answer} onChange={(e) => setAnswer(e.target.value)} placeholder="Cevap" />
          <button type="button" className={btnPrimary} disabled={busy || !answer.trim()} onClick={() => onAct('answer', { answer })}>Cevapla</button>
        </div>
      )}
      {admin && <div className="flex justify-end"><button type="button" className={btnGhost} disabled={busy} onClick={() => onAct('close', {})}>Kapat</button></div>}
    </div>
  );
}
