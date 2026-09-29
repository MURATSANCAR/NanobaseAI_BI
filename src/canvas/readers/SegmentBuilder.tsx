import { useEffect, useMemo, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { ArrowLeft, Download, FileSpreadsheet, Loader2, Plus, Sparkles, Trash2 } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import { Loading, Note, Pill, btnGhost, btnPrimary, errText, field, label } from '../admin/ui';
import { Panel, useDebounced } from '../editorial/kit';
import {
  CHANNELS, emptyRule, fmtDay, fmtInt, readersApi, SEGMENT_TONE,
  type Channel, type Counts, type Definition, type FieldSpec, type Rule, type Segment,
} from './api';
import { ROOT, useMeta } from './parts';
import SqlInfo from '../components/SqlInfo';

const EMPTY: Definition = { match: 'all', rules: [] };

/** Segment kurucu: kural + anlık büyüklük (toplam / e-posta / SMS), Zeki AI taslağı, onay akışı, izin denetimli dışa aktarım. */
export default function SegmentBuilder({ id }: { id?: string }) {
  const meta = useMeta();
  const me = meta.data?.me;
  const qc = useQueryClient();
  const nav = useNavigate();
  const fields = useQuery({ queryKey: ['readers', 'fields'], queryFn: readersApi.fields, enabled: ENGINE_ENABLED, staleTime: 5 * 60_000 });
  const seg = useQuery({ queryKey: ['readers', 'segment', id], queryFn: () => readersApi.segment(id!), enabled: ENGINE_ENABLED && !!id });
  const s = seg.data;

  const [name, setName] = useState('');
  const [defn, setDefn] = useState<Definition>(EMPTY);
  const [origin, setOrigin] = useState<string | undefined>();
  const [notes, setNotes] = useState<string[]>([]);
  useEffect(() => {
    if (s) {
      setName(s.name);
      setDefn(s.definition);
    }
  }, [s]);

  const editable = !id || (s && s.status !== 'arsiv');
  const canEdit = !!me?.canSegment && !!editable;
  const dirty = !s || name !== s.name || JSON.stringify(defn) !== JSON.stringify(s.definition);
  const debounced = useDebounced(defn, 350);
  const preview = useQuery({
    queryKey: ['readers', 'preview', debounced],
    queryFn: () => readersApi.preview(debounced),
    enabled: ENGINE_ENABLED && !!fields.data,
    placeholderData: (prev) => prev,
  });

  const byField = useMemo(() => Object.fromEntries((fields.data?.fields ?? []).map((f) => [f.field, f])), [fields.data]);

  const save = useMutation({
    mutationFn: () => (id ? readersApi.updateSegment(id, { name, definition: defn }) : readersApi.createSegment({ name, definition: defn, origin })),
    onSuccess: (r) => {
      toast.success(id ? (r.status === 'taslak' && s?.status === 'onayli' ? 'Kaydedildi; kural değiştiği için segment yeniden onay ister.' : 'Kaydedildi.') : 'Segment taslağı açıldı.');
      qc.invalidateQueries({ queryKey: ['readers', 'segments'] });
      qc.setQueryData(['readers', 'segment', r.id], (old: Segment | undefined) => ({ ...(old ?? {}), ...r }));
      if (!id) nav(`${ROOT}/segmentler/${r.id}`, { replace: true });
    },
    onError: (e) => toast.error(errText(e, 'Kaydedilemedi.') ?? ''),
  });
  const flow = useMutation({
    mutationFn: async (v: { act: 'submit' | 'approve' | 'reject' | 'archive'; note?: string }) => {
      if (!id) throw new Error('Önce kaydedin.');
      if (v.act === 'submit') return readersApi.submit(id);
      if (v.act === 'approve') return readersApi.approve(id, v.note);
      if (v.act === 'reject') return readersApi.reject(id, v.note ?? '');
      return readersApi.archive(id);
    },
    onSuccess: (r) => {
      toast.success(`Segment: ${r.statusLabel}.`);
      qc.invalidateQueries({ queryKey: ['readers', 'segment', id] });
      qc.invalidateQueries({ queryKey: ['readers', 'segments'] });
    },
    onError: (e) => toast.error(errText(e, 'İşlem yapılamadı.') ?? ''),
  });

  if (id && seg.isLoading) return <Loading />;
  if (id && seg.error) return <Note tone="err">{errText(seg.error, 'Segment açılamadı.')}</Note>;

  const setRule = (i: number, r: Rule) => setDefn((d) => ({ ...d, rules: d.rules.map((x, j) => (j === i ? r : x)) }));
  const addRule = (f: FieldSpec) => setDefn((d) => ({ ...d, rules: [...d.rules, emptyRule(f)] }));
  const dropRule = (i: number) => setDefn((d) => ({ ...d, rules: d.rules.filter((_, j) => j !== i) }));
  const iAmAuthor = !!s && !!me && [s.owner, s.updatedBy].some((u) => (u ?? '').toLowerCase() === me.username.toLowerCase());

  return (
    <div className="flex flex-col gap-3 lg:gap-4">
      <Link to={`${ROOT}/segmentler`} className="inline-flex items-center gap-1 px-1 text-[12.5px] font-extrabold text-canvas-violet hover:underline">
        <ArrowLeft aria-hidden className="h-3.5 w-3.5" /> Segmentler
      </Link>

      <div className="grid gap-3 lg:grid-cols-[1.35fr_1fr] lg:gap-4">
        <div className="flex flex-col gap-3 lg:gap-4">
          <Panel>
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="text-[15px] font-extrabold">{id ? 'Segment' : 'Yeni segment'}</h2>
              {s && <Pill tone={SEGMENT_TONE[s.status]}>{s.statusLabel}</Pill>}
              {s && <span className="font-mono text-[11px] text-canvas-muted">v{s.version} · {s.owner}</span>}
            </div>
            <label className={`${label} mt-3 block`} htmlFor="seg-ad">Ad</label>
            <input id="seg-ad" className={field} value={name} onChange={(e) => setName(e.target.value)} disabled={!canEdit} placeholder="Örn. Çocuk kitabı ilgisi, e-posta izinli" />
            {s?.decisionNote && <Note tone={s.status === 'taslak' ? 'warn' : 'info'}>Karar notu: {s.decisionNote}</Note>}
          </Panel>

          {canEdit && <ZekiDraft onDraft={(d) => { setDefn(d.definition); if (!name) setName(d.name); setOrigin('zeki'); setNotes(d.notes); }} modelVar={!!meta.data?.modelVar} />}
          {notes.length > 0 && <Note tone="warn">Zeki AI önerisinden atılanlar: {notes.join(' ')}</Note>}

          <Panel>
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h2 className="text-[15px] font-extrabold">Kurallar</h2>
              <div className="flex gap-1" role="radiogroup" aria-label="Eşleşme">
                {(['all', 'any'] as const).map((m) => (
                  <button key={m} type="button" role="radio" aria-checked={defn.match === m} disabled={!canEdit}
                    onClick={() => setDefn((d) => ({ ...d, match: m }))}
                    className={`min-h-11 rounded-xl px-3 text-[12px] font-extrabold transition-colors duration-150 sm:min-h-8 ${defn.match === m ? 'bg-canvas-violet text-white' : 'bg-slate-100 hover:bg-slate-200'}`}>
                    {m === 'all' ? 'Hepsi sağlansın' : 'Biri yeter'}
                  </button>
                ))}
              </div>
            </div>
            {fields.isLoading && <Loading />}
            {defn.rules.length === 0 && <p className="mt-2 text-[12.5px] text-canvas-muted">Kural yok: bütün etkin okurlar.</p>}
            <ol className="mt-2 flex flex-col gap-2">
              {defn.rules.map((r, i) => (
                <RuleRow key={i} rule={r} spec={byField[r.field]} disabled={!canEdit} onChange={(x) => setRule(i, x)} onDrop={() => dropRule(i)} />
              ))}
            </ol>
            {canEdit && fields.data && <AddRule fields={fields.data.fields} onAdd={addRule} />}
          </Panel>

          {canEdit && (
            <div className="flex flex-wrap gap-2">
              <button type="button" className={btnPrimary} disabled={!dirty || save.isPending || name.trim().length < 3} onClick={() => save.mutate()}>
                {save.isPending && <Loader2 aria-hidden className="h-4 w-4 animate-spin" />}{id ? 'Kaydet' : 'Taslak olarak kaydet'}
              </button>
              {s?.status === 'onayli' && dirty && <span className="self-center text-[11.5px] text-amber-800">Kural değişirse segment yeniden onay ister.</span>}
            </div>
          )}
        </div>

        <div className="flex flex-col gap-3 lg:gap-4">
          <SizePanel counts={preview.data} loading={preview.isFetching} error={preview.error} excludeLabels={meta.data?.excludeLabels ?? {}} />
          {s && (
            <Panel>
              <h2 className="text-[15px] font-extrabold">Onay</h2>
              <p className="mt-1 text-[12px] text-canvas-muted">
                {s.status === 'onayli' ? `${s.approvedBy} onayladı, ${fmtDay(s.approvedAt)}.`
                  : s.status === 'onay-bekliyor' ? `Onaya gönderildi, ${fmtDay(s.submittedAt)}. Yazan ya da son değiştiren onaylayamaz.`
                    : s.status === 'arsiv' ? 'Arşivde.' : 'Taslak. Onaylı segment gece sayılır ve dışa aktarılabilir.'}
              </p>
              <FlowButtons s={s} dirty={dirty} canSegment={!!me?.canSegment} canApprove={!!me?.canApprove && !iAmAuthor} busy={flow.isPending}
                onAct={(act, note) => flow.mutate({ act, note })} />
            </Panel>
          )}
          {s?.status === 'onayli' && <ExportPanel s={s} />}
          {s?.history && s.history.length > 0 && (
            <Panel>
              <h2 className="flex items-center gap-1 text-[15px] font-extrabold">Gece sayımları<SqlInfo k={s.kaynaklar} alan="history[]" label="Gece sayımları" /></h2>
              <ul className="mt-2 max-h-56 space-y-0.5 overflow-y-auto text-[12px]">
                {[...s.history].reverse().map((h, i) => (
                  <li key={i} className="flex justify-between gap-2 font-mono tabular-nums">
                    <span className="text-canvas-muted">{fmtDay(h.at)} v{h.version}</span>
                    <span>{fmtInt(h.total)} · e-posta {fmtInt(h.email)} · SMS {fmtInt(h.sms)}</span>
                  </li>
                ))}
              </ul>
            </Panel>
          )}
        </div>
      </div>
    </div>
  );
}

function ZekiDraft({ onDraft, modelVar }: { onDraft: (d: Awaited<ReturnType<typeof readersApi.draft>>) => void; modelVar: boolean }) {
  const [text, setText] = useState('');
  const m = useMutation({
    mutationFn: () => readersApi.draft(text),
    onSuccess: (d) => { onDraft(d); toast.success('Zeki AI kural taslağı önerdi; kuralları kontrol edip kaydedin.'); },
    onError: (e) => toast.error(errText(e, 'Zeki AI öneri veremedi.') ?? ''),
  });
  if (!modelVar) return null;
  return (
    <Panel>
      <h2 className="flex items-center gap-1.5 text-[15px] font-extrabold"><Sparkles aria-hidden className="h-4 w-4 text-canvas-violet" />Zeki AI ile kur</h2>
      <p className="mt-0.5 text-[11.5px] text-canvas-muted">Kimi hedeflediğinizi yazın; Zeki AI yalnız bu kurulumdaki alan ve değerlerden kural önerir. Sayılar kuraldan hesaplanır.</p>
      <div className="mt-2 flex flex-col gap-2 sm:flex-row">
        <label className="sr-only" htmlFor="zeki-istek">İstek</label>
        <input id="zeki-istek" className={field} value={text} onChange={(e) => setText(e.target.value)} placeholder="Örn. İstanbul'daki 25–40 yaş, e-posta izni olan okurlar" />
        <button type="button" className={btnGhost} disabled={m.isPending || text.trim().length < 5} onClick={() => m.mutate()}>
          {m.isPending ? <Loader2 aria-hidden className="h-4 w-4 animate-spin" /> : <Sparkles aria-hidden className="h-4 w-4" />}Öner
        </button>
      </div>
    </Panel>
  );
}

function AddRule({ fields, onAdd }: { fields: FieldSpec[]; onAdd: (f: FieldSpec) => void }) {
  const [pick, setPick] = useState('');
  return (
    <div className="mt-3 flex flex-col gap-2 sm:flex-row">
      <label className="sr-only" htmlFor="kural-ekle">Alan</label>
      <select id="kural-ekle" className={field} value={pick} onChange={(e) => setPick(e.target.value)}>
        <option value="">Alan seçin…</option>
        {fields.map((f) => <option key={f.field} value={f.field}>{f.label}</option>)}
      </select>
      <button type="button" className={btnGhost} disabled={!pick} onClick={() => { const f = fields.find((x) => x.field === pick); if (f) onAdd(f); setPick(''); }}>
        <Plus aria-hidden className="h-4 w-4" />Kural ekle
      </button>
    </div>
  );
}

const OPS_TEXT: Record<string, string> = {
  in: 'şunlardan biri', not_in: 'şunlardan biri değil', between: 'arası', gte: 'en az', lte: 'en çok',
  within: 'son … gün içinde', older: '… günden eski', is: 'olsun mu',
};

function RuleRow({ rule, spec, disabled, onChange, onDrop }: { rule: Rule; spec?: FieldSpec; disabled: boolean; onChange: (r: Rule) => void; onDrop: () => void }) {
  if (!spec) return <li className="rounded-xl bg-red-50 p-2 text-[12px] text-red-700">Bilinmeyen alan: {rule.field}</li>;
  return (
    <li className="rounded-xl border border-slate-100 bg-white/70 p-2.5">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-[12.5px] font-extrabold">{spec.label}</span>
        {spec.ops.length > 1 ? (
          <select aria-label="Koşul" className="rounded-lg border border-slate-200 bg-white px-2 py-1 text-[12px] font-semibold" value={rule.op} disabled={disabled}
            onChange={(e) => onChange({ ...rule, op: e.target.value })}>
            {spec.ops.map((o) => <option key={o} value={o}>{OPS_TEXT[o] ?? o}</option>)}
          </select>
        ) : <span className="text-[12px] text-canvas-muted">{OPS_TEXT[rule.op] ?? rule.op}</span>}
        {!disabled && (
          <button type="button" aria-label="Kuralı sil" onClick={onDrop} className="ml-auto flex h-9 w-9 items-center justify-center rounded-lg text-canvas-muted transition-colors duration-150 hover:bg-red-50 hover:text-red-700">
            <Trash2 aria-hidden className="h-4 w-4" />
          </button>
        )}
      </div>
      <div className="mt-1.5"><ValueEditor rule={rule} spec={spec} disabled={disabled} onChange={onChange} /></div>
      {spec.help && <p className="mt-1 text-[11px] text-canvas-muted">{spec.help}</p>}
    </li>
  );
}

function ValueEditor({ rule, spec, disabled, onChange }: { rule: Rule; spec: FieldSpec; disabled: boolean; onChange: (r: Rule) => void }) {
  const num = 'w-24 rounded-lg border border-slate-200 bg-white px-2 py-1.5 text-base font-semibold sm:text-[12.5px]';
  if (spec.kind === 'set') return <OptionPicker spec={spec} value={(rule.value as string[]) ?? []} disabled={disabled} onChange={(v) => onChange({ ...rule, value: v })} />;
  if (spec.kind === 'range') {
    const [lo, hi] = (rule.value as Array<number | null>) ?? [null, null];
    const set = (i: 0 | 1, v: string) => { const x: Array<number | null> = [lo, hi]; x[i] = v === '' ? null : Number(v); onChange({ ...rule, value: x }); };
    return (
      <div className="flex items-center gap-2 text-[12px]">
        <input aria-label="En az" type="number" inputMode="numeric" className={num} value={lo ?? ''} disabled={disabled} onChange={(e) => set(0, e.target.value)} />
        <span>–</span>
        <input aria-label="En çok" type="number" inputMode="numeric" className={num} value={hi ?? ''} disabled={disabled} onChange={(e) => set(1, e.target.value)} />
      </div>
    );
  }
  if (spec.kind === 'bool') {
    return (
      <div className="flex gap-1">
        {[true, false].map((b) => (
          <button key={String(b)} type="button" aria-pressed={rule.value === b} disabled={disabled} onClick={() => onChange({ ...rule, value: b })}
            className={`min-h-11 rounded-lg px-3 text-[12px] font-bold transition-colors duration-150 sm:min-h-8 ${rule.value === b ? 'bg-canvas-violet text-white' : 'bg-slate-100'}`}>
            {b ? 'Evet' : 'Hayır'}
          </button>
        ))}
      </div>
    );
  }
  return (
    <div className="flex items-center gap-2 text-[12px]">
      <input aria-label="Değer" type="number" min={0} inputMode="numeric" className={num} value={rule.value as number} disabled={disabled}
        onChange={(e) => onChange({ ...rule, value: e.target.value === '' ? 0 : Number(e.target.value) })} />
      {spec.kind === 'days' && <span className="text-canvas-muted">gün</span>}
    </div>
  );
}

function OptionPicker({ spec, value, disabled, onChange }: { spec: FieldSpec; value: string[]; disabled: boolean; onChange: (v: string[]) => void }) {
  const [q, setQ] = useState('');
  const opts = spec.options ?? [];
  const show = (o: string) => spec.optionLabels?.[o] ?? o;
  const fold = (s: string) => s.toLocaleLowerCase('tr');
  const list = q ? opts.filter((o) => fold(show(o)).includes(fold(q))) : opts;
  const toggle = (o: string) => onChange(value.includes(o) ? value.filter((x) => x !== o) : [...value, o]);
  return (
    <div className="flex flex-col gap-1.5">
      {value.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {value.map((v) => (
            <button key={v} type="button" disabled={disabled} onClick={() => toggle(v)} className="rounded-md bg-canvas-violet/10 px-1.5 py-0.5 text-[11.5px] font-bold text-canvas-violet">
              {show(v)}{!disabled && ' ×'}
            </button>
          ))}
        </div>
      )}
      {!disabled && (
        <>
          {opts.length > 8 && (
            <input aria-label={`${spec.label} içinde ara`} className="rounded-lg border border-slate-200 bg-white px-2 py-1.5 text-base sm:text-[12px]" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Ara…" />
          )}
          {opts.length === 0 ? <p className="text-[11.5px] text-canvas-muted">Bu alan veride boş.</p> : (
            <div className="max-h-44 overflow-y-auto overscroll-contain rounded-lg bg-slate-50 p-1">
              {list.map((o) => (
                <label key={o} className="flex min-h-9 cursor-pointer items-center gap-2 rounded-md px-1.5 text-[12px] hover:bg-white">
                  <input type="checkbox" checked={value.includes(o)} onChange={() => toggle(o)} />
                  <span className="truncate">{show(o)}</span>
                </label>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}

function SizePanel({ counts, loading, error, excludeLabels }: { counts?: Counts; loading: boolean; error: unknown; excludeLabels: Record<string, string> }) {
  return (
    <Panel>
      <div className="flex items-center justify-between gap-2">
        <h2 className="flex items-center gap-1 text-[15px] font-extrabold">Büyüklük<SqlInfo k={counts?.kaynaklar} alan="total" label="Segment büyüklüğü" /></h2>
        {loading && <Loader2 aria-label="Hesaplanıyor" className="h-4 w-4 animate-spin text-canvas-muted" />}
      </div>
      {error ? <Note tone="err">{errText(error, 'Hesaplanamadı.')}</Note> : null}
      {counts && (
        <>
          <div className="mt-2 grid grid-cols-3 gap-2">
            <Big label="Toplam" value={counts.total} sub={counts.of != null ? `${fmtInt(counts.of)} okurdan` : undefined} />
            <Big label="E-posta izinli" value={counts.email.izinli} sub={`listeye ${fmtInt(counts.email.exportable)}`} />
            <Big label="SMS izinli" value={counts.sms.izinli} sub={`listeye ${fmtInt(counts.sms.exportable)}`} />
          </div>
          {counts.explanation && <p className="mt-3 rounded-xl bg-slate-50 p-2.5 text-[12px] leading-snug">{counts.explanation}</p>}
          <details className="mt-2 text-[11.5px] text-canvas-muted">
            <summary className="cursor-pointer font-bold">Kimler neden dışarıda kalıyor</summary>
            {(['email', 'sms'] as const).map((ch) => (
              <div key={ch} className="mt-1.5">
                <div className="font-bold text-canvas-ink">{ch === 'email' ? 'E-posta' : 'SMS'} listesi</div>
                <ul>
                  {Object.entries(counts[ch].excluded).map(([k, n]) => (
                    <li key={k} className="flex justify-between gap-2"><span>{excludeLabels[k] ?? k}</span><span className="font-mono tabular-nums">{fmtInt(n)}</span></li>
                  ))}
                </ul>
              </div>
            ))}
            <p className="mt-1.5">18 yaş altı: {fmtInt(counts.minors)}.</p>
          </details>
        </>
      )}
    </Panel>
  );
}

function Big({ label: l, value, sub }: { label: string; value: number; sub?: string }) {
  return (
    <div className="rounded-xl bg-slate-50 p-2.5">
      <div className="text-[10.5px] font-bold uppercase tracking-wide text-canvas-muted">{l}</div>
      <div className="font-mono text-[20px] font-bold tabular-nums leading-tight sm:text-[24px]">{fmtInt(value)}</div>
      {sub && <div className="text-[11px] text-canvas-muted">{sub}</div>}
    </div>
  );
}

function FlowButtons({ s, dirty, canSegment, canApprove, busy, onAct }: {
  s: Segment; dirty: boolean; canSegment: boolean; canApprove: boolean; busy: boolean;
  onAct: (act: 'submit' | 'approve' | 'reject' | 'archive', note?: string) => void;
}) {
  const [note, setNote] = useState('');
  return (
    <div className="mt-2 flex flex-col gap-2">
      {s.status === 'taslak' && canSegment && (
        <button type="button" className={btnPrimary} disabled={busy || dirty} onClick={() => onAct('submit')} title={dirty ? 'Önce kaydedin' : undefined}>Onaya gönder</button>
      )}
      {s.status === 'onay-bekliyor' && canApprove && (
        <>
          <label className="sr-only" htmlFor="karar-notu">Not</label>
          <input id="karar-notu" className={field} value={note} onChange={(e) => setNote(e.target.value)} placeholder="Not (geri göndermede zorunlu)" />
          <div className="flex flex-wrap gap-2">
            <button type="button" className={btnPrimary} disabled={busy} onClick={() => onAct('approve', note)}>Onayla</button>
            <button type="button" className={btnGhost} disabled={busy || note.trim().length < 3} onClick={() => onAct('reject', note)}>Geri gönder</button>
          </div>
        </>
      )}
      {s.status !== 'arsiv' && canSegment && (
        <button type="button" className={btnGhost} disabled={busy} onClick={() => onAct('archive')}>Arşive kaldır</button>
      )}
    </div>
  );
}

function ExportPanel({ s }: { s: Segment }) {
  const meta = useMeta();
  const me = meta.data?.me;
  const enabled = meta.data?.settings.exportEnabled;
  const [channel, setChannel] = useState<Channel>('email');
  const [purpose, setPurpose] = useState('');
  const qc = useQueryClient();
  const m = useMutation({
    mutationFn: (excel: boolean) => readersApi.exportList(s.id, channel, purpose, excel),
    onSuccess: (r) => {
      toast.success(`Liste indirildi: ${fmtInt(r.count)} kişi${r.excluded ? `, izin/koşul nedeniyle ${fmtInt(r.excluded)} kişi dışarıda` : ''}.`);
      qc.invalidateQueries({ queryKey: ['readers', 'exports'] });
      setPurpose('');
    },
    onError: (e) => toast.error(errText(e, 'Liste alınamadı.') ?? ''),
  });
  if (!me?.canList || !me.canExport) return null;
  const labels = meta.data?.channels ?? { email: 'E-posta', sms: 'SMS', call: 'Arama' };
  return (
    <Panel>
      <h2 className="text-[15px] font-extrabold">Liste al</h2>
      {!enabled ? (
        <p className="mt-1 text-[12px] text-canvas-muted">Dışa aktarım hukuk teyidine kadar kapalı; yönetici ayarı açınca kullanılır.</p>
      ) : (
        <>
          <p className="mt-0.5 text-[11.5px] text-canvas-muted">
            Yalnız izinli{meta.data?.settings.requireKvkk ? ', KVKK rızalı' : ''} ve 18 yaş üstü okurlar; CRM'deki güncel ret yeniden denetlenir.
            Liste portalda saklanmaz; kimin, hangi amaçla aldığı kaydedilir.
          </p>
          <div className="mt-2 flex flex-wrap gap-1" role="radiogroup" aria-label="Kanal">
            {CHANNELS.map((c) => (
              <button key={c} type="button" role="radio" aria-checked={channel === c} onClick={() => setChannel(c)}
                className={`min-h-11 rounded-xl px-3 text-[12px] font-extrabold transition-colors duration-150 sm:min-h-8 ${channel === c ? 'bg-canvas-violet text-white' : 'bg-slate-100 hover:bg-slate-200'}`}>
                {labels[c]}
              </button>
            ))}
          </div>
          <label className={`${label} mt-2 block`} htmlFor="aktarim-amac">Amaç</label>
          <input id="aktarim-amac" className={field} value={purpose} onChange={(e) => setPurpose(e.target.value)} placeholder="Örn. Ekim çocuk bülteni" />
          <div className="mt-2 flex flex-wrap gap-2">
            <button type="button" className={btnPrimary} disabled={m.isPending || purpose.trim().length < 5} onClick={() => m.mutate(false)}>
              {m.isPending && !m.variables ? <Loader2 aria-hidden className="h-4 w-4 animate-spin" /> : <Download aria-hidden className="h-4 w-4" />}
              Listeyi indir (CSV)
            </button>
            <button type="button" className={btnPrimary} disabled={m.isPending || purpose.trim().length < 5} onClick={() => m.mutate(true)}>
              {m.isPending && m.variables ? <Loader2 aria-hidden className="h-4 w-4 animate-spin" /> : <FileSpreadsheet aria-hidden className="h-4 w-4" />}
              Listeyi indir (Excel)
            </button>
          </div>
        </>
      )}
    </Panel>
  );
}
