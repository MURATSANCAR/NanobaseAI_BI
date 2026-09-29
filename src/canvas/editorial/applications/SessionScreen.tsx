import { useEffect, useState } from 'react';
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { ChevronDown, FileText, Lock, Pencil, Trash2 } from 'lucide-react';
import { ENGINE_ENABLED } from '../../engine';
import { Loading, Note, Pill, btnGhost, btnPrimary, errText, field, label, nf } from '../../admin/ui';
import Sheet from '../studio/reader/Sheet';
import { ModuleFrame, Panel } from '../kit';
import { fmtDay } from '../authors/shared';
import { applicationsApi, boardApi, type AgendaItem, type SessionDetail, type VoteChoice } from './api';
import { BoardReportView } from './ReportPanel';
import SessionForm from './SessionForm';
import { AXES, DECISION_TONE, ScoreField, TallyView, errMsg, invalidateApps, useAppMeta } from './shared';
import { EmptyHint, Explain } from '../../components/Explain';

/** Kurul oturumu: gündemdeki her başvuru için üyenin kendi puanı ve oyu, oy dağılımı, başkanın kararı.
 *  Üye oy verene kadar başkalarının oylarını görmez; adıyla oylar başkana ve yetkili kişilere açıktır. */

function ReportSheet({ item, onClose }: { item: AgendaItem | null; onClose: () => void }) {
  const q = useQuery({
    queryKey: ['applications', 'report', item?.appId ?? ''],
    queryFn: () => applicationsApi.report(item!.appId),
    enabled: ENGINE_ENABLED && !!item,
  });
  return (
    <Sheet open={!!item} onClose={onClose} modal wide title="Yayın Kurulu Raporu" subtitle={item ? `${item.no} · ${item.title}` : undefined}>
      {q.isLoading && <Loading />}
      {q.error && <Note tone="err">{errMsg(q.error, 'Rapor okunamadı.')}</Note>}
      {q.data?.status === 'hazirlaniyor' && !q.data.content && <p className="text-[12.5px] text-canvas-muted">Rapor hazırlanıyor…</p>}
      {q.data?.status === 'hata' && !q.data.content && <Note tone="err">{q.data.error ?? 'Rapor üretilemedi.'}</Note>}
      {q.data?.status === null && <p className="text-[12.5px] text-canvas-muted">Bu başvuru için rapor üretilmedi.</p>}
      {q.data?.content && <BoardReportView r={q.data.content} />}
    </Sheet>
  );
}

function VoteForm({ s, it }: { s: SessionDetail; it: AgendaItem }) {
  const qc = useQueryClient();
  const meta = useAppMeta();
  const mine = it.myVote;
  const [vote, setVote] = useState<VoteChoice | ''>(mine?.vote ?? '');
  const [scores, setScores] = useState({ mission: mine?.mission ?? null, publishing: mine?.publishing ?? null, commercial: mine?.commercial ?? null });
  const [note, setNote] = useState(mine?.note ?? '');
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    setVote(mine?.vote ?? '');
    setScores({ mission: mine?.mission ?? null, publishing: mine?.publishing ?? null, commercial: mine?.commercial ?? null });
    setNote(mine?.note ?? '');
  }, [mine?.updatedAt]); // eslint-disable-line react-hooks/exhaustive-deps
  const save = useMutation({
    mutationFn: () => boardApi.vote(s.id, it.appId, { vote: vote as VoteChoice, ...scores, note }),
    onSuccess: async () => {
      setErr(null);
      await invalidateApps(qc);
      toast.success(mine ? 'Oyunuz güncellendi' : 'Oyunuz kaydedildi');
    },
    onError: (e) => setErr(errMsg(e)),
  });
  const total = scores.mission != null && scores.publishing != null && scores.commercial != null ? Math.round((scores.mission + scores.publishing + scores.commercial) / 3) : null;
  return (
    <form
      className="space-y-3 rounded-2xl border border-canvas-violet/20 bg-canvas-violet/[0.03] p-3 text-[12.5px]"
      onSubmit={(e) => {
        e.preventDefault();
        save.mutate();
      }}
    >
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h4 className="text-[13px] font-extrabold">Puanınız ve oyunuz</h4>
        <span className="text-[11.5px] text-canvas-muted">{mine ? `Kaydedildi ${fmtDay(mine.updatedAt)} · karar kaydedilene kadar değiştirilebilir` : 'Henüz oy vermediniz'}</span>
      </div>
      <div className="grid gap-3 sm:grid-cols-3">
        {AXES.map((ax) => (
          <ScoreField key={ax.key} title={ax.title} hint={ax.hint} value={scores[ax.key]} onChange={(v) => setScores((p) => ({ ...p, [ax.key]: v }))} />
        ))}
      </div>
      <p className="flex flex-wrap items-center gap-1 text-[12px] text-canvas-muted">
        Toplam karar skorunuz: <b className="font-mono text-canvas-ink">{total ?? '—'}</b>
        <Explain label="Toplam karar skoru">Üç eksende verdiğiniz puanların ortalamasıdır; üç puan da girilince hesaplanır.</Explain>
      </p>
      {!mine && it.tally.hidden && <p className="text-[11.5px] leading-snug text-canvas-muted">Diğer üyelerin oy dağılımı, siz oyunuzu kaydettikten sonra açılır.</p>}
      <fieldset>
        <legend className={label}>Oyunuz</legend>
        <div className="mt-1 grid grid-cols-2 gap-1.5 sm:grid-cols-4">
          {(meta.data?.votes ?? []).map((o) => (
            <label key={o.value} className={`flex min-h-11 cursor-pointer items-center justify-center gap-2 rounded-xl border px-2 py-2 sm:min-h-0 ${vote === o.value ? 'border-canvas-violet bg-white' : 'border-slate-200 bg-white/70'}`}>
              <input type="radio" name={`vote-${it.appId}`} value={o.value} checked={vote === o.value} onChange={() => setVote(o.value as VoteChoice)} className="accent-[theme(colors.canvas.violet)]" />
              <span className="font-extrabold">{o.label}</span>
            </label>
          ))}
        </div>
      </fieldset>
      <label className="block">
        <span className={label}>
          Gerekçe{(vote === 'red' || vote === 'revizyon') && <span className="text-red-700"> *</span>}
        </span>
        <textarea rows={3} maxLength={4000} value={note} onChange={(e) => setNote(e.target.value)} className={`${field} mt-1`} placeholder="Kısa not; red ve revizyonda zorunlu" />
      </label>
      {err && <Note tone="err">{err}</Note>}
      <div className="flex justify-end">
        <button type="submit" className={btnPrimary} disabled={!vote || save.isPending}>
          {save.isPending ? 'Kaydediliyor…' : mine ? 'Oyumu güncelle' : 'Oyumu kaydet'}
        </button>
      </div>
    </form>
  );
}

function DecisionForm({ s, it }: { s: SessionDetail; it: AgendaItem }) {
  const qc = useQueryClient();
  const meta = useAppMeta();
  const suggestion = it.tally.majority ?? it.tally.byScore ?? '';
  const [decision, setDecision] = useState<string>(it.decision ?? '');
  const [note, setNote] = useState(it.decisionNote ?? '');
  const [printRun, setPrintRun] = useState(it.printRun ? String(it.printRun) : '');
  const [price, setPrice] = useState(it.price ? String(it.price) : '');
  const [royalty, setRoyalty] = useState(it.royalty ? String(it.royalty) : '');
  const [publishOn, setPublishOn] = useState(it.publishOn ?? '');
  const [err, setErr] = useState<string | null>(null);
  const save = useMutation({
    mutationFn: (undo: boolean) =>
      boardApi.decide(s.id, it.appId, undo ? { decision: '' } : { decision, note, printRun, price, royalty, publishOn }),
    onSuccess: async (out, undo) => {
      setErr(null);
      await invalidateApps(qc);
      toast.success(undo ? 'Karar geri alındı' : out.decision === 'ertele' ? 'Sonraki kurula ertelendi' : 'Karar kaydedildi; yazı taslağı hazır');
    },
    onError: (e) => setErr(errMsg(e)),
  });
  if (it.decision && it.decision !== 'ertelendi') {
    return (
      <div className="flex flex-wrap items-center justify-between gap-2 rounded-2xl bg-slate-50 p-3 text-[12.5px]">
        <span>
          Karar: <b>{it.decisionLabel}</b>
          {it.decidedByName && <span className="text-canvas-muted"> · {it.decidedByName}, {fmtDay(it.decidedAt)}</span>}
        </span>
        <button type="button" className={btnGhost} disabled={save.isPending} onClick={() => save.mutate(true)}>
          Kararı geri al
        </button>
        {err && <div className="w-full"><Note tone="err">{err}</Note></div>}
      </div>
    );
  }
  return (
    <form
      className="space-y-3 rounded-2xl border border-slate-200 bg-white p-3 text-[12.5px]"
      onSubmit={(e) => {
        e.preventDefault();
        save.mutate(false);
      }}
    >
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h4 className="text-[13px] font-extrabold">Kurul kararı</h4>
        {suggestion && (
          <span className="inline-flex items-center gap-1 text-[11.5px] text-canvas-muted">
            Öneri: {it.tally.majorityLabel ?? it.tally.byScoreLabel}
            <Explain label="Karar önerisi">Oy çoğunluğu varsa odur; yoksa üyelerin puanlarından çıkan skor önerisidir. Yalnız yol gösterir, kararı siz seçersiniz.</Explain>
          </span>
        )}
      </div>
      <div className="grid grid-cols-2 gap-1.5 sm:grid-cols-4">
        {(meta.data?.decisions ?? []).map((o) => (
          <label key={o.value} className={`flex min-h-11 cursor-pointer items-center justify-center gap-2 rounded-xl border px-2 py-2 text-center sm:min-h-0 ${decision === o.value ? 'border-canvas-violet bg-canvas-violet/5' : 'border-slate-200'}`}>
            <input type="radio" name={`decision-${it.appId}`} value={o.value} checked={decision === o.value} onChange={() => setDecision(o.value)} className="accent-[theme(colors.canvas.violet)]" />
            <span className="font-extrabold">{o.value === 'ertele' ? 'Ertele' : o.label}</span>
          </label>
        ))}
      </div>
      {decision === 'kabul' && (
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          <label className="block">
            <span className={label}>İlk baskı</span>
            <input inputMode="numeric" value={printRun} onChange={(e) => setPrintRun(e.target.value.replace(/\D/g, ''))} placeholder="Ör. 3000" className={`${field} mt-1`} />
          </label>
          <label className="block">
            <span className={label}>Fiyat (₺)</span>
            <input inputMode="decimal" value={price} onChange={(e) => setPrice(e.target.value)} placeholder="Ör. 250" className={`${field} mt-1`} />
          </label>
          <label className="block">
            <span className={label}>Telif (%)</span>
            <input inputMode="decimal" value={royalty} onChange={(e) => setRoyalty(e.target.value)} placeholder="Ör. 10" className={`${field} mt-1`} />
          </label>
          <label className="block">
            <span className={label}>Yayın tarihi</span>
            <input type="date" value={publishOn} onChange={(e) => setPublishOn(e.target.value)} className={`${field} mt-1`} />
          </label>
        </div>
      )}
      <label className="block">
        <span className={label}>
          Karar notu{(decision === 'red' || decision === 'revizyon') && <span className="text-red-700"> *</span>}
        </span>
        <textarea rows={3} maxLength={8000} value={note} onChange={(e) => setNote(e.target.value)} className={`${field} mt-1`} placeholder="Yazara gidecek yazının temeli olur" />
      </label>
      {err && <Note tone="err">{err}</Note>}
      <div className="flex justify-end">
        <button type="submit" className={btnPrimary} disabled={!decision || save.isPending}>
          {save.isPending ? 'Kaydediliyor…' : 'Kararı kaydet'}
        </button>
      </div>
    </form>
  );
}

function ItemCard({ s, it, open, onToggle, onReport }: { s: SessionDetail; it: AgendaItem; open: boolean; onToggle: () => void; onReport: () => void }) {
  const qc = useQueryClient();
  const live = s.state === 'planli';
  const remove = useMutation({
    mutationFn: () => boardApi.removeAgenda(s.id, it.appId),
    onSuccess: async () => {
      await invalidateApps(qc);
      toast.success('Gündemden çıkarıldı');
    },
    onError: (e) => toast.error(errMsg(e)),
  });
  const e = it.editor;
  return (
    <li id={`gundem-${it.appId}`} className="rounded-2xl border border-slate-100 bg-white/85">
      <button type="button" onClick={onToggle} aria-expanded={open} className="flex w-full items-start gap-3 p-3 text-left">
        <span className="w-6 shrink-0 pt-0.5 font-mono text-[12px] tabular-nums text-canvas-muted">{String(it.position).padStart(2, '0')}</span>
        <span className="min-w-0 flex-1">
          <span className="block break-words text-[13.5px] font-extrabold leading-snug">{it.title}</span>
          <span className="mt-0.5 block break-words text-[11.5px] text-canvas-muted">
            {[it.no, it.authorName, it.categoryName, it.evaluatorName && `Editör: ${it.evaluatorName}`].filter(Boolean).join(' · ')}
          </span>
          <span className="mt-1.5 flex flex-wrap gap-1.5 text-[11px]">
            {e?.recommendationLabel && <Pill tone={e.recommendation === 'kabul' ? 'ok' : e.recommendation === 'red' ? 'err' : 'warn'}>Editör: {e.recommendationLabel}</Pill>}
            <Pill tone="muted">
              {nf.format(it.tally.voted)} / {nf.format(it.tally.members)} oy
            </Pill>
            {s.isMember && live && !it.decision && <Pill tone={it.myVote ? 'ok' : 'warn'}>{it.myVote ? 'Oy verdiniz' : 'Oyunuz bekleniyor'}</Pill>}
          </span>
        </span>
        <span className="flex shrink-0 items-center gap-1.5">
          <Pill tone={it.decision ? DECISION_TONE[it.decision] ?? 'muted' : 'violet'}>{it.decisionLabel ?? 'Karar bekliyor'}</Pill>
          <ChevronDown aria-hidden className={`h-4 w-4 text-canvas-muted transition-transform duration-200 ease-out ${open ? 'rotate-180' : ''}`} />
        </span>
      </button>
      {open && (
        <div className="space-y-3 border-t border-slate-100 p-3">
          <div className="flex flex-wrap gap-1.5">
            <button type="button" className={btnGhost} onClick={onReport}>
              <FileText aria-hidden className="h-4 w-4" />
              Kurul raporu
              {it.report === 'hazirlaniyor' && ' (hazırlanıyor)'}
            </button>
            <Link to={`/basvurular/${it.appId}`} className={btnGhost}>
              Başvuru dosyası
            </Link>
            {s.canRun && live && !it.decision && it.tally.voted === 0 && (
              <button type="button" className={btnGhost} disabled={remove.isPending} onClick={() => remove.mutate()}>
                <Trash2 aria-hidden className="h-4 w-4" />
                Gündemden çıkar
              </button>
            )}
          </div>
          {e && (
            <p className="text-[12px] text-canvas-muted">
              <Explain label="Editör puanı" className="mr-1">Başvuruyu değerlendiren editörün raporunda verdiği puanlar. Kurul üyelerinin puanlarından ayrıdır.</Explain>
              Editör puanı: içerik <b className="font-mono text-canvas-ink">{e.contentScore ?? '—'}</b> · misyon <b className="font-mono text-canvas-ink">{e.mission ?? '—'}</b> ·
              yayıncılık <b className="font-mono text-canvas-ink">{e.publishing ?? '—'}</b> · ticari <b className="font-mono text-canvas-ink">{e.commercial ?? '—'}</b>
              {e.redline && e.redline !== 'temiz' && <span className="font-semibold text-rose-700"> · Yayın ilkeleri: {e.redlineLabel}</span>}
            </p>
          )}
          {s.isMember && live && !it.decision && <VoteForm s={s} it={it} />}
          {it.myVote && (it.decision || !live) && (
            <p className="text-[12px]">
              Oyunuz: <b>{it.myVote.voteLabel}</b>
              {it.myVote.mission != null && <span className="font-mono text-canvas-muted"> · {it.myVote.mission}/{it.myVote.publishing}/{it.myVote.commercial}</span>}
            </p>
          )}
          <div>
            <h4 className="mb-1 text-[13px] font-extrabold">Oylar</h4>
            <TallyView tally={it.tally} />
            {it.votes && it.votes.length > 0 && (
              <ul className="mt-2 space-y-1 text-[12px]">
                {it.votes.map((v) => (
                  <li key={v.member} className="rounded-lg bg-slate-50 px-2.5 py-1.5">
                    <b>{v.memberName}</b> · {v.voteLabel}
                    {v.mission != null && <span className="font-mono text-canvas-muted"> · misyon {v.mission} · yayıncılık {v.publishing} · ticari {v.commercial}</span>}
                    {v.note && <span className="block text-canvas-muted">{v.note}</span>}
                  </li>
                ))}
              </ul>
            )}
          </div>
          {it.decision && it.decisionNote && <p className="whitespace-pre-line rounded-xl bg-slate-50 px-3 py-2 text-[12.5px]">{it.decisionNote}</p>}
          {s.canRun && live && <DecisionForm key={`${it.decision}-${it.decidedAt}`} s={s} it={it} />}
        </div>
      )}
    </li>
  );
}

function AddToAgenda({ s }: { s: SessionDetail }) {
  const qc = useQueryClient();
  const [pick, setPick] = useState('');
  const waiting = useQuery({
    queryKey: ['applications', 'list', 'kuyruk', '', 'kurul_bekliyor', false],
    queryFn: () => applicationsApi.list({ view: 'kuyruk', status: 'kurul_bekliyor' }),
    enabled: ENGINE_ENABLED,
  });
  const add = useMutation({
    mutationFn: () => boardApi.addAgenda(s.id, pick),
    onSuccess: async () => {
      setPick('');
      await invalidateApps(qc);
      toast.success('Gündeme eklendi');
    },
    onError: (e) => toast.error(errMsg(e)),
  });
  const items = waiting.data?.items ?? [];
  return (
    <Panel>
      <h2 className="text-[15px] font-extrabold">Gündeme başvuru ekle</h2>
      {items.length === 0 ? (
        <p className="mt-1 text-[12.5px] text-canvas-muted">Kurula çıkacak başvuru yok. Editör raporu kurula gönderilen başvuru burada seçilebilir hâle gelir.</p>
      ) : (
        <div className="mt-2 flex flex-col gap-2 sm:flex-row">
          <select aria-label="Başvuru" value={pick} onChange={(e) => setPick(e.target.value)} className={`${field} min-w-0 flex-1`}>
            <option value="">Başvuru seçin ({nf.format(items.length)})</option>
            {items.map((a) => (
              <option key={a.id} value={a.id}>
                {a.no} · {a.title} — {a.authorName}
              </option>
            ))}
          </select>
          <button type="button" className={btnPrimary} disabled={!pick || add.isPending} onClick={() => add.mutate()}>
            Gündeme ekle
          </button>
        </div>
      )}
    </Panel>
  );
}

export default function SessionScreen() {
  const { id = '' } = useParams();
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ['board', 'session', id], queryFn: () => boardApi.get(id), enabled: ENGINE_ENABLED && !!id });
  const s = q.data;
  const [open, setOpen] = useState<string | null>(params.get('basvuru'));
  const [report, setReport] = useState<AgendaItem | null>(null);
  const [editing, setEditing] = useState(false);
  const [closing, setClosing] = useState(false);
  useEffect(() => {
    if (s && !open && s.items.length === 1) setOpen(s.items[0].appId);
  }, [s, open]);
  const close = useMutation({
    mutationFn: () => boardApi.close(id),
    onSuccess: async (out) => {
      setClosing(false);
      await invalidateApps(qc);
      toast.success('Oturum kapandı', { description: out.postponed ? `${out.postponed} başvuru karar verilmeden ertelendi` : undefined });
    },
    onError: (e) => toast.error(errMsg(e)),
  });
  const remove = useMutation({
    mutationFn: () => boardApi.remove(id),
    onSuccess: async () => {
      await invalidateApps(qc);
      toast.success('Oturum silindi');
      navigate('/yayin-kurulu');
    },
    onError: (e) => toast.error(errMsg(e)),
  });
  const pending = s ? s.items.filter((x) => !x.decision).length : 0;

  return (
    <ModuleFrame
      route="/yayin-kurulu"
      crumb="Yayın kurulu"
      title={s ? s.title : 'Kurul oturumu'}
      lead={s ? [fmtDay(s.date), s.time, s.place, `Başkan: ${s.chairName}`, `Üyeler: ${s.members.map((m) => m.display).join(', ')}`].filter(Boolean).join(' · ') : ''}
      source={s ? s.stateLabel : 'Portal'}
      presence="Kaynak: portal"
      aside={
        s ? (
          <div className="flex flex-col gap-2">
            <div className="flex flex-wrap items-center gap-2">
              <Pill tone={s.state === 'kapandi' ? 'muted' : 'violet'}>{s.stateLabel}</Pill>
              {s.isMember && <Pill tone="ok">Üyesiniz</Pill>}
              <Link to="/yayin-kurulu" className="ml-auto text-[12px] font-bold text-canvas-violet hover:underline">
                Bütün oturumlar
              </Link>
            </div>
            {s.canRun && s.state === 'planli' && (
              <div className="grid grid-cols-2 gap-1.5">
                <button type="button" className={btnGhost} onClick={() => setEditing(true)}>
                  <Pencil aria-hidden className="h-4 w-4" />
                  Düzenle
                </button>
                {s.items.length === 0 ? (
                  <button type="button" className={btnGhost} disabled={remove.isPending} onClick={() => remove.mutate()}>
                    <Trash2 aria-hidden className="h-4 w-4" />
                    Oturumu sil
                  </button>
                ) : (
                  <button type="button" className={btnGhost} onClick={() => setClosing(true)}>
                    <Lock aria-hidden className="h-4 w-4" />
                    Oturumu kapat
                  </button>
                )}
              </div>
            )}
          </div>
        ) : undefined
      }
    >
      {q.isLoading && <Loading />}
      {q.error && <Note tone="err">{errText(q.error, 'Oturum okunamadı.')}</Note>}
      {s && (
        <>
          {s.note && <Note tone="info">{s.note}</Note>}
          {s.canRun && s.state === 'planli' && <AddToAgenda s={s} />}
          <Panel>
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <h2 className="text-[15px] font-extrabold">Gündem</h2>
              <span className="text-[11.5px] text-canvas-muted">
                {nf.format(s.items.length)} başvuru · {nf.format(pending)} karar bekliyor · skor eşikleri: kabul ≥ {s.thresholds.accept}, revizyon ≥ {s.thresholds.revise}
              </span>
            </div>
            {s.items.length === 0 && (
              <div className="mt-2">
                <EmptyHint
                  title="Gündem boş"
                  why={s.canRun && s.state === 'planli' ? 'Yukarıdaki «Gündeme başvuru ekle» bölümünden kurula çıkacak başvuruları ekleyin.' : 'Bu oturuma henüz başvuru eklenmedi.'}
                />
              </div>
            )}
            {s.items.length > 0 && <p className="mt-1 text-[11.5px] text-canvas-muted">Oy vermek, raporu açmak ya da kararı görmek için başvuruya dokunun.</p>}
            <ol className="mt-2 space-y-2">
              {s.items.map((it) => (
                <ItemCard key={it.appId} s={s} it={it} open={open === it.appId} onToggle={() => setOpen((v) => (v === it.appId ? null : it.appId))} onReport={() => setReport(it)} />
              ))}
            </ol>
            {!s.canSeeNames && s.items.some((x) => x.tally.voted > 0) && (
              <p className="mt-2 text-[11px] text-canvas-muted">Üyelerin adıyla oylarını başkan ve yetkili kişiler görür.</p>
            )}
          </Panel>
        </>
      )}
      <ReportSheet item={report} onClose={() => setReport(null)} />
      {s && <SessionForm open={editing} session={s} onClose={() => setEditing(false)} onSaved={() => setEditing(false)} />}
      <Sheet open={closing} onClose={() => setClosing(false)} modal title="Oturumu kapat" subtitle={s?.title}>
        <div className="space-y-3 text-[12.5px]">
          <p>
            {pending
              ? `${pending} başvurunun kararı kaydedilmedi. Kapatınca bu başvurular «karar verilmeden ertelendi» olur ve kurul sırasına döner.`
              : 'Bütün gündem karara bağlandı.'}{' '}
            Kapanan oturumda oy ve karar değişmez.
          </p>
          <div className="flex justify-end gap-2">
            <button type="button" className={btnGhost} onClick={() => setClosing(false)}>
              Vazgeç
            </button>
            <button type="button" className={btnPrimary} disabled={close.isPending} onClick={() => close.mutate()}>
              Oturumu kapat
            </button>
          </div>
        </div>
      </Sheet>
    </ModuleFrame>
  );
}
