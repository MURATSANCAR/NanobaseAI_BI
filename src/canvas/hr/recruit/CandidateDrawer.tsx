import { useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Download, FileText, Loader2, Sparkles, Trash2 } from 'lucide-react';
import { ENGINE_ENABLED } from '../../engine';
import { Note, Pill, btnGhost, btnPrimary, errText, field, label as labelCls } from '../../admin/ui';
import Sheet from '../../editorial/studio/reader/Sheet';
import {
  STAGE_ORDER, daysText, fmtDateTime, fmtDay, fmtSize, hrApi, recruitApi, waitJob,
  type Candidate, type Message, type Outcome, type RecruitMeta, type Stage, type WithK,
} from '../hrApi';
import SqlInfo from '../../components/SqlInfo';
import { AskSheet, Block, Fact, FilePick, HrFrame, splitUsers } from '../parts';
import { MB } from '../../components/fileDropRules';

/** M55 aday kartı (/ik/ise-alim/aday/:id). Görünen her şey yetkiye göre köprüden gelir: e-posta, telefon ve özgün
 *  özgeçmiş yalnız bütün adayları görme yetkisinde; görüşmeci maskeli metni görür. Her açılış erişim kaydına yazılır. */

export default function CandidateDrawer() {
  const { id = '' } = useParams();
  const meta = useQuery({ queryKey: ['hr', 'recruit', 'meta'], queryFn: recruitApi.meta, enabled: ENGINE_ENABLED, staleTime: 60_000 });
  const q = useQuery({ queryKey: ['hr', 'recruit', 'candidate', id], queryFn: () => recruitApi.candidate(id), enabled: ENGINE_ENABLED && !!id });
  const c = q.data;
  return (
    <HrFrame
      crumb="İşe alım panosu"
      title={c ? c.fullName : 'Aday'}
      detail={c?.fullName}
      back={{ to: c?.position ? `/ik/ise-alim?pozisyon=${c.position.id}` : '/ik/ise-alim', label: 'İşe alım panosu' }}
      lead={c ? `${c.position?.title ?? 'Pozisyonsuz başvuru'} · ${c.sourceLabel} · başvuru ${fmtDay(c.createdAt)}` : 'Aday kartı'}
    >
      {q.error && <Note tone="err">{errText(q.error, 'Aday kartı açılamadı.')}</Note>}
      {q.isLoading && <div className="py-8 text-center text-[12px] text-canvas-muted">Yükleniyor…</div>}
      {c && meta.data && <Body c={c} meta={meta.data} />}
    </HrFrame>
  );
}

function useRefresh(id: string) {
  const qc = useQueryClient();
  return () => {
    void qc.invalidateQueries({ queryKey: ['hr', 'recruit', 'candidate', id] });
    void qc.invalidateQueries({ queryKey: ['hr', 'recruit', 'pipeline'] });
  };
}

function Body({ c, meta }: { c: Candidate & WithK; meta: RecruitMeta }) {
  return (
    <div className="grid grid-cols-1 gap-3 xl:grid-cols-[minmax(0,1.35fr)_minmax(0,1fr)] xl:gap-4">
      <div className="flex min-w-0 flex-col gap-3 lg:gap-4">
        <Summary c={c} meta={meta} />
        <Evidence c={c} meta={meta} />
        <Files c={c} meta={meta} />
        <Interviews c={c} />
      </div>
      <div className="flex min-w-0 flex-col gap-3 lg:gap-4">
        <Letters c={c} meta={meta} />
        <Kvkk c={c} />
        <History c={c} meta={meta} />
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ özet ve aşama kararı */

function Summary({ c, meta }: { c: Candidate & WithK; meta: RecruitMeta }) {
  const [deciding, setDeciding] = useState(false);
  const [editing, setEditing] = useState(false);
  return (
    <Block
      title="Aday"
      action={
        <>
          {c.can.edit && <button type="button" className={btnGhost} onClick={() => setEditing(true)}>Düzelt</button>}
          {c.can.decide && !c.employeeId && <button type="button" className={btnPrimary} onClick={() => setDeciding(true)}>Aşama kararı</button>}
        </>
      }
    >
      <div className="grid grid-cols-2 gap-2 lg:grid-cols-4">
        <Fact label="Aşama" value={<span className="inline-flex flex-wrap items-center gap-1">{c.stageLabel}{c.outcomeLabel && <Pill tone={c.outcome === 'ise_alindi' ? 'ok' : 'muted'}>{c.outcomeLabel}</Pill>}</span>} />
        <Fact label="Bu aşamada" value={daysText(c.daysInStage)} help={c.overSla ? 'Bekleme eşiğini aştı' : undefined}
          info={<SqlInfo k={c.kaynaklar} alan="daysInStage" label="Bu aşamada geçen gün" />} />
        <Fact label="E-posta" value={c.email ?? (c.can.edit ? '—' : 'yetkiyle görünür')} />
        <Fact label="Telefon" value={c.phone ?? (c.can.edit ? '—' : 'yetkiyle görünür')} />
      </div>
      {c.employeeId && <Note tone="ok">Aday işe alındı; kaydı çalışan kaydına geçti (Çalışan ve KVKK kayıtları).</Note>}
      <StageSheet open={deciding} c={c} meta={meta} onClose={() => setDeciding(false)} />
      {c.can.edit && <EditSheet open={editing} c={c} meta={meta} onClose={() => setEditing(false)} />}
    </Block>
  );
}

function StageSheet({ open, c, meta, onClose }: { open: boolean; c: Candidate; meta: RecruitMeta; onClose: () => void }) {
  const refresh = useRefresh(c.id);
  const [stage, setStage] = useState<Stage>(c.stage);
  const [outcome, setOutcome] = useState<Outcome | ''>('');
  const [reason, setReason] = useState('');
  const [startDate, setStartDate] = useState('');
  const save = useMutation({
    mutationFn: () => recruitApi.stage(c.id, { stage, outcome: stage === 'sonuc' ? (outcome || undefined) : undefined, reason: reason.trim() || undefined,
      startDate: outcome === 'ise_alindi' && startDate ? startDate : undefined }),
    onSuccess: (r) => {
      toast.success(r.employeeId ? 'Aday işe alındı; çalışan kaydı açıldı.' : 'Aşama kaydedildi.');
      refresh();
      setReason('');
      onClose();
    },
    onError: (e) => toast.error(errText(e, 'Aşama kaydedilemedi.')),
  });
  const same = stage === c.stage && (stage !== 'sonuc' || outcome === (c.outcome ?? ''));
  return (
    <Sheet open={open} modal onClose={onClose} title="Aşama kararı" subtitle="Kararı siz verirsiniz; Zeki AI'ın özeti yalnız kanıt gösterir. Gerekçe isteğe bağlıdır ve adaya gitmez.">
      <div className="flex flex-col gap-3">
        <div role="radiogroup" aria-label="Aşama" className="grid grid-cols-2 gap-1.5 sm:grid-cols-5">
          {STAGE_ORDER.map((s) => (
            <button
              key={s}
              type="button"
              role="radio"
              aria-checked={stage === s}
              onClick={() => setStage(s)}
              className={`min-h-11 rounded-xl px-2 text-[12.5px] font-extrabold transition-colors duration-150 sm:min-h-9 ${stage === s ? 'bg-canvas-violet text-white' : 'bg-slate-100 text-canvas-ink hover:bg-slate-200'}`}
            >
              {meta.stages[s]}
            </button>
          ))}
        </div>
        {stage === 'sonuc' && (
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Sonuç</span>
            <select className={field} value={outcome} onChange={(e) => setOutcome(e.target.value as Outcome | '')}>
              <option value="">Seçin…</option>
              {Object.entries(meta.outcomes).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
          </label>
        )}
        {stage === 'sonuc' && outcome === 'ise_alindi' && (
          <label className="flex flex-col gap-1">
            <span className={labelCls}>İşe giriş tarihi (biliniyorsa)</span>
            <input type="date" className={field} value={startDate} onChange={(e) => setStartDate(e.target.value)} />
          </label>
        )}
        <label className="flex flex-col gap-1">
          <span className={labelCls}>Not (isteğe bağlı)</span>
          <textarea className={`${field} min-h-[80px]`} value={reason} onChange={(e) => setReason(e.target.value)} />
        </label>
        {stage === 'sonuc' && outcome === 'ret' && (
          <Note tone="info">Ret sonrası adaya yazmayı unutmayın: Yazışma bölümünden şablondan ret mektubu hazırlayın.</Note>
        )}
        <div className="flex flex-wrap justify-end gap-2">
          <button type="button" className={btnGhost} onClick={onClose}>Vazgeç</button>
          <button type="button" className={btnPrimary} disabled={save.isPending || same || (stage === 'sonuc' && !outcome)} onClick={() => save.mutate()}>
            Kaydet
          </button>
        </div>
      </div>
    </Sheet>
  );
}

function EditSheet({ open, c, meta, onClose }: { open: boolean; c: Candidate; meta: RecruitMeta; onClose: () => void }) {
  const refresh = useRefresh(c.id);
  const positions = useQuery({ queryKey: ['hr', 'recruit', 'positions', ''], queryFn: () => recruitApi.positions(), enabled: open });
  const [f, setF] = useState({ fullName: c.fullName, email: c.email ?? '', phone: c.phone ?? '', positionId: c.position?.id ?? '', source: c.source });
  const save = useMutation({
    mutationFn: () => recruitApi.updateCandidate(c.id, { ...f, positionId: f.positionId || null }),
    onSuccess: () => {
      toast.success('Aday kaydı düzeltildi.');
      refresh();
      onClose();
    },
    onError: (e) => toast.error(errText(e, 'Kaydedilemedi.')),
  });
  return (
    <Sheet open={open} modal onClose={onClose} title="Aday kaydını düzelt">
      <div className="flex flex-col gap-3">
        <label className="flex flex-col gap-1">
          <span className={labelCls}>Ad soyad</span>
          <input className={field} value={f.fullName} onChange={(e) => setF({ ...f, fullName: e.target.value })} />
        </label>
        <label className="flex flex-col gap-1">
          <span className={labelCls}>E-posta</span>
          <input className={field} type="email" value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} />
        </label>
        <label className="flex flex-col gap-1">
          <span className={labelCls}>Telefon</span>
          <input className={field} inputMode="tel" value={f.phone} onChange={(e) => setF({ ...f, phone: e.target.value })} />
        </label>
        <label className="flex flex-col gap-1">
          <span className={labelCls}>Pozisyon</span>
          <select className={field} value={f.positionId} onChange={(e) => setF({ ...f, positionId: e.target.value })}>
            <option value="">Pozisyonsuz</option>
            {(positions.data?.items ?? []).filter((p) => p.state !== 'kapandi' || p.id === f.positionId).map((p) => (
              <option key={p.id} value={p.id}>{p.title}</option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1">
          <span className={labelCls}>Kaynak</span>
          <select className={field} value={f.source} onChange={(e) => setF({ ...f, source: e.target.value })}>
            {Object.entries(meta.sources).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
        </label>
        <div className="flex justify-end gap-2">
          <button type="button" className={btnGhost} onClick={onClose}>Vazgeç</button>
          <button type="button" className={btnPrimary} disabled={save.isPending || !f.fullName.trim()} onClick={() => save.mutate()}>Kaydet</button>
        </div>
      </div>
    </Sheet>
  );
}

/* ------------------------------------------------------------------ kanıtlı özet */

function Evidence({ c, meta }: { c: Candidate & WithK; meta: RecruitMeta }) {
  const refresh = useRefresh(c.id);
  const [progress, setProgress] = useState<string | null>(null);
  const run = useMutation({
    mutationFn: async () => {
      const job = await recruitApi.evidence(c.id);
      const done = await waitJob(job.id, (j) => setProgress(j.total ? `${j.progress}/${j.total}` : 'başladı'));
      if (done.state === 'hata') throw new Error(done.error || 'Kanıtlı özet çıkarılamadı.');
      return done;
    },
    onSuccess: () => {
      toast.success('Kanıtlı özet hazır.');
      refresh();
    },
    onError: (e) => toast.error(errText(e, 'Kanıtlı özet çıkarılamadı.')),
    onSettled: () => setProgress(null),
  });
  const canRun = (c.can.decide || c.can.edit) && !!c.position && c.files.length > 0 && meta.modelVar;
  const found = c.evidence.filter((e) => e.verdict === 'kanit_var').length;
  return (
    <Block
      title="Kanıtlı özet"
      help="Pozisyonun her yetkinliği için özgeçmişte onu destekleyen satır. Puan ve sıralama yoktur; «kanıt yok» bir ret değildir, özgeçmişte yazılmamış olabilir. Zeki AI yalnız maskeli metni görür."
      action={
        canRun ? (
          <button type="button" className={btnPrimary} disabled={run.isPending} onClick={() => run.mutate()}>
            {run.isPending ? <Loader2 aria-hidden className="h-4 w-4 animate-spin" /> : <Sparkles aria-hidden className="h-4 w-4" />}
            {run.isPending ? `Çıkarılıyor${progress ? ` (${progress})` : '…'}` : c.evidence.length ? 'Yeniden çıkar' : 'Zeki AI ile çıkar'}
          </button>
        ) : undefined
      }
    >
      {!c.position && <Note tone="info">Adayın pozisyonu yok; özet pozisyonun yetkinliklerine göre çıkar.</Note>}
      {c.position && !c.files.length && <Note tone="info">Önce özgeçmiş yüklenmeli.</Note>}
      {!meta.modelVar && <Note tone="warn">Zeki AI bu kurulumda tanımlı değil.</Note>}
      {c.evidence.length > 0 && (
        <>
          <div className="mb-2 text-[11.5px] text-canvas-muted">
            <SqlInfo k={c.kaynaklar} alan="evidence" label="Yetkinlik ve kanıt sayısı" className="mr-1" />
            Yetkinlik {c.evidence.length} · kanıt bulunan {found} · {fmtDateTime(c.evidenceAt)}
          </div>
          <ul className="flex flex-col gap-2">
            {c.evidence.map((e) => (
              <li key={e.competency} className="rounded-xl border border-slate-100 bg-white/80 p-2.5">
                <div className="flex flex-wrap items-center gap-1.5">
                  <span className="text-[13px] font-extrabold">{e.competency}</span>
                  <Pill tone={e.verdict === 'kanit_var' ? 'ok' : 'muted'}>{e.verdict === 'kanit_var' ? 'Kanıt var' : 'Kanıt yok'}</Pill>
                </div>
                {e.quotes.map((q) => (
                  <blockquote key={q.line} className="mt-1 border-l-2 border-canvas-violet/40 pl-2 text-[12.5px] leading-snug">
                    <span className="mr-1 font-mono text-[10.5px] text-canvas-muted">satır {q.line}</span>
                    {q.text}
                  </blockquote>
                ))}
              </li>
            ))}
          </ul>
        </>
      )}
    </Block>
  );
}

/* ------------------------------------------------------------------ özgeçmiş dosyaları */

function Files({ c, meta }: { c: Candidate; meta: RecruitMeta }) {
  const refresh = useRefresh(c.id);
  const [removing, setRemoving] = useState<string | null>(null);
  const add = useMutation({
    mutationFn: (f: File) => recruitApi.addFile(c.id, f),
    onSuccess: (r) => {
      const n = Object.values(r.maskCounts).reduce((a, b) => a + b, 0);
      const ocr = r.okuma?.ocrSayfa.length
        ? ` ${r.okuma.ocrSayfa.length} sayfa taranmış görüntüden okundu (OCR)${r.okuma.enDusukGuven != null ? `, en düşük güven %${Math.round(r.okuma.enDusukGuven * 100)}` : ''}.`
        : '';
      toast.success((n ? `Özgeçmiş yüklendi; ${n} kişisel bilgi maskelendi.` : 'Özgeçmiş yüklendi.') + ocr);
      refresh();
    },
    onError: (e) => toast.error(errText(e, 'Dosya yüklenemedi.')),
  });
  const del = useMutation({
    mutationFn: (fid: string) => recruitApi.deleteFile(c.id, fid),
    onSuccess: () => {
      toast.success('Dosya silindi.');
      refresh();
      setRemoving(null);
    },
    onError: (e) => toast.error(errText(e, 'Dosya silinemedi.')),
  });
  return (
    <Block
      title="Özgeçmiş"
      help={c.can.downloadOriginal ? 'Maskeli metin Zeki AI\'a giden metindir; özgün dosya yalnız İK yetkisiyle iner ve indirme erişim kaydına yazılır.' : 'Yalnız maskeli metni görürsünüz; kimlik, iletişim ve özel nitelikli bilgiler gizlidir.'}
      action={<FilePick label="Dosya ekle" accept=".pdf,.docx,.odt,.txt" maxBytes={meta.fileMaxMb ? meta.fileMaxMb * MB : undefined} busy={add.isPending} allowed={c.can.files} deniedText="Bu işlem için yetkiniz yok: aday dosyasını pozisyonun sahibi ya da İK ekler." onPick={(f) => add.mutate(f)} />}
    >
      {!c.files.length && <div className="py-4 text-center text-[12px] text-canvas-muted">Dosya yok. Özgeçmişi yukarıdaki «Dosya ekle» alanına bırakın.</div>}
      <ul className="flex flex-col gap-2">
        {c.files.map((f) => {
          const masked = Object.entries(f.maskCounts).filter(([, n]) => n > 0);
          return (
            <li key={f.id} className="rounded-xl border border-slate-100 bg-white/80 p-2.5">
              <div className="flex flex-wrap items-center gap-2">
                <FileText aria-hidden className="h-4 w-4 shrink-0 text-canvas-muted" />
                <span className="min-w-0 flex-1 break-all text-[12.5px] font-bold">{f.filename}</span>
                <span className="font-mono text-[11px] text-canvas-muted">{fmtSize(f.size)} · {fmtDay(f.createdAt)}</span>
                {c.can.downloadOriginal && (
                  <button type="button" className={btnGhost} onClick={() => recruitApi.downloadFile(c.id, f.id, f.filename).catch((e) => toast.error(errText(e, 'İndirilemedi.')))}>
                    <Download aria-hidden className="h-4 w-4" />
                    <span className="sr-only sm:not-sr-only">Özgün</span>
                  </button>
                )}
                {c.can.files && (
                  <button type="button" className={btnGhost} aria-label="Dosyayı sil" onClick={() => setRemoving(f.id)}>
                    <Trash2 aria-hidden className="h-4 w-4" />
                  </button>
                )}
              </div>
              <div className="mt-1 flex flex-wrap gap-1">
                {masked.map(([k, n]) => <Pill key={k} tone="muted">{k}: {n}</Pill>)}
                <Pill tone={f.modelChecked ? 'ok' : 'warn'}>{f.modelChecked ? 'Zeki AI denetledi' : 'Zeki AI denetimi özetle birlikte'}</Pill>
              </div>
              <details className="mt-1.5">
                <summary className="cursor-pointer text-[12px] font-bold text-canvas-violet">Maskeli metni göster</summary>
                <pre className="mt-1 max-h-[360px] overflow-auto whitespace-pre-wrap break-words rounded-lg bg-slate-50 p-2 font-sans text-[12px] leading-snug">{f.maskedText}</pre>
              </details>
              {f.originalText !== null && (
                <details className="mt-1">
                  <summary className="cursor-pointer text-[12px] font-bold text-canvas-muted">Özgün metin (yalnız İK)</summary>
                  <pre className="mt-1 max-h-[360px] overflow-auto whitespace-pre-wrap break-words rounded-lg bg-slate-50 p-2 font-sans text-[12px] leading-snug">{f.originalText}</pre>
                </details>
              )}
            </li>
          );
        })}
      </ul>
      <AskSheet
        open={removing !== null}
        title="Dosyayı sil"
        message="Dosya, çıkarılan metin ve maskeli metin silinir. Kanıtlı özet yeniden çıkarılana kadar eski hâliyle kalır."
        confirm="Sil"
        danger
        busy={del.isPending}
        onClose={() => setRemoving(null)}
        onConfirm={() => removing && del.mutate(removing)}
      />
    </Block>
  );
}

/* ------------------------------------------------------------------ mülakat */

function Interviews({ c }: { c: Candidate & WithK }) {
  const refresh = useRefresh(c.id);
  const [open, setOpen] = useState(false);
  const [f, setF] = useState({ startsAt: '', location: '', interviewers: '' });
  const create = useMutation({
    mutationFn: () => recruitApi.createInterview({ candidateId: c.id, startsAt: new Date(f.startsAt).toISOString(), location: f.location.trim(),
      interviewers: splitUsers(f.interviewers) }),
    onSuccess: () => {
      toast.success('Mülakat planlandı.');
      refresh();
      setOpen(false);
      setF({ startsAt: '', location: '', interviewers: '' });
    },
    onError: (e) => toast.error(errText(e, 'Mülakat kaydedilemedi.')),
  });
  const kit = c.position?.interviewKit ?? [];
  return (
    <Block
      title="Mülakat"
      help="Görüşmeciler, kendi notlarını teslim edene kadar birbirlerinin notunu görmez. Puan 1–5, görüşmecinin kendi değerlendirmesidir."
      action={c.can.decide ? <button type="button" className={btnGhost} onClick={() => setOpen((x) => !x)}>{open ? 'Vazgeç' : 'Mülakat planla'}</button> : undefined}
    >
      {open && (
        <form
          className="mb-3 grid grid-cols-1 gap-2 rounded-xl bg-slate-50 p-2.5 sm:grid-cols-2"
          onSubmit={(e) => {
            e.preventDefault();
            create.mutate();
          }}
        >
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Tarih ve saat</span>
            <input type="datetime-local" className={field} value={f.startsAt} onChange={(e) => setF({ ...f, startsAt: e.target.value })} required />
          </label>
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Yer (toplantı odası)</span>
            <input className={field} value={f.location} onChange={(e) => setF({ ...f, location: e.target.value })} placeholder="Oda adı ya da görüntülü görüşme" />
          </label>
          <label className="flex flex-col gap-1 sm:col-span-2">
            <span className={labelCls}>Görüşmeciler (hesap adları, virgülle)</span>
            <input className={field} value={f.interviewers} onChange={(e) => setF({ ...f, interviewers: e.target.value })} placeholder="ayse.yilmaz, mehmet.kaya" required />
          </label>
          <div className="flex flex-wrap items-center justify-between gap-2 sm:col-span-2">
            <Link to="/" className="text-[12px] font-bold text-canvas-violet hover:underline">Odayı Kampüs'ten ayırın</Link>
            <button type="submit" className={btnPrimary} disabled={create.isPending || !f.startsAt || !splitUsers(f.interviewers).length}>Kaydet</button>
          </div>
        </form>
      )}
      {kit.length > 0 && (
        <details className="mb-2 rounded-xl bg-slate-50 p-2.5">
          <summary className="cursor-pointer text-[12.5px] font-extrabold">Pozisyonun mülakat soru seti</summary>
          <ul className="mt-1.5 flex flex-col gap-2">
            {kit.map((k) => (
              <li key={k.competency}>
                <div className="text-[12.5px] font-bold">{k.competency}</div>
                <ul className="ml-4 list-disc text-[12.5px] leading-snug">{k.questions.map((q) => <li key={q}>{q}</li>)}</ul>
                {k.criteria && <div className="text-[11.5px] text-canvas-muted">Ölçüt: {k.criteria}</div>}
              </li>
            ))}
          </ul>
        </details>
      )}
      {!c.interviews.length && <div className="py-3 text-center text-[12px] text-canvas-muted">Planlanmış mülakat yok.</div>}
      <ul className="flex flex-col gap-2">
        {c.interviews.map((iv) => (
          <li key={iv.id} className="rounded-xl border border-slate-100 bg-white/80 p-2.5">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-[13px] font-extrabold">{fmtDateTime(iv.startsAt)}</span>
              {iv.location && <span className="text-[12px] text-canvas-muted">{iv.location}</span>}
            </div>
            <div className="mt-0.5 text-[11.5px] text-canvas-muted">Görüşmeciler: {iv.interviewers.join(', ')}</div>
            {iv.hiddenOthers && <Note tone="info">Diğer görüşmecilerin notu, kendi notunuzu teslim edince görünür.</Note>}
            {iv.notes.map((n) => (
              <div key={n.id} className="mt-1.5 rounded-lg bg-slate-50 p-2">
                <div className="flex flex-wrap items-center gap-1.5 text-[12px] font-bold">
                  {n.mine ? 'Notunuz' : n.author}
                  <Pill tone={n.submittedAt ? 'ok' : 'warn'}>{n.submittedAt ? 'Teslim edildi' : 'Taslak'}</Pill>
                  {Object.keys(n.scores).length > 0 && <SqlInfo k={c.kaynaklar} alan="interviews" label="Görüşme notu puanları" />}
                </div>
                {Object.keys(n.scores).length > 0 && (
                  <div className="mt-0.5 flex flex-wrap gap-1">
                    {Object.entries(n.scores).map(([k, v]) => <Pill key={k} tone="muted">{k}: {v}</Pill>)}
                  </div>
                )}
                {n.note && <p className="mt-0.5 whitespace-pre-wrap break-words text-[12.5px] leading-snug">{n.note}</p>}
              </div>
            ))}
            {iv.iAmInterviewer && !iv.notes.some((n) => n.mine && n.submittedAt) && (
              <NoteForm iid={iv.id} competencies={c.position?.competencies ?? []} draft={iv.notes.find((n) => n.mine)} onSaved={refresh} />
            )}
          </li>
        ))}
      </ul>
    </Block>
  );
}

function NoteForm({ iid, competencies, draft, onSaved }: {
  iid: string; competencies: string[]; draft?: { scores: Record<string, number>; note: string }; onSaved: () => void;
}) {
  const [scores, setScores] = useState<Record<string, number>>(draft?.scores ?? {});
  const [note, setNote] = useState(draft?.note ?? '');
  const save = useMutation({
    mutationFn: (submit: boolean) => recruitApi.saveNote(iid, { scores, note, submit }),
    onSuccess: (r) => {
      toast.success(r.submitted ? 'Notunuz teslim edildi.' : 'Taslak kaydedildi.');
      onSaved();
    },
    onError: (e) => toast.error(errText(e, 'Not kaydedilemedi.')),
  });
  return (
    <div className="mt-2 flex flex-col gap-2 rounded-lg border border-dashed border-slate-200 p-2">
      {competencies.map((k) => (
        <label key={k} className="flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between">
          <span className="text-[12.5px] font-semibold">{k}</span>
          <select className={`${field} sm:w-[140px]`} value={scores[k] ?? ''} onChange={(e) => {
            const v = e.target.value;
            setScores((s) => {
              const next = { ...s };
              if (v) next[k] = Number(v);
              else delete next[k];
              return next;
            });
          }}>
            <option value="">Puan yok</option>
            {[1, 2, 3, 4, 5].map((n) => <option key={n} value={n}>{n}</option>)}
          </select>
        </label>
      ))}
      <label className="flex flex-col gap-1">
        <span className={labelCls}>Görüşme notu</span>
        <textarea className={`${field} min-h-[88px]`} value={note} onChange={(e) => setNote(e.target.value)} />
      </label>
      <div className="flex flex-wrap justify-end gap-2">
        <button type="button" className={btnGhost} disabled={save.isPending} onClick={() => save.mutate(false)}>Taslak kaydet</button>
        <button type="button" className={btnPrimary} disabled={save.isPending} onClick={() => save.mutate(true)}>Teslim et</button>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ yazışma */

const LETTERS: Array<{ kind: string; label: string }> = [
  { kind: 'alindi', label: 'Başvurunuz alındı' },
  { kind: 'davet', label: 'Mülakat daveti' },
  { kind: 'teklif', label: 'Teklif' },
  { kind: 'ret', label: 'Ret' },
];

function Letters({ c, meta }: { c: Candidate; meta: RecruitMeta }) {
  const refresh = useRefresh(c.id);
  const [kind, setKind] = useState('');
  const [soften, setSoften] = useState(false);
  const [fields, setFields] = useState({ gorusme_tarihi: '', gorusme_yeri: '' });
  const draft = useMutation({
    mutationFn: () => recruitApi.letter(c.id, kind, { soften, fields: kind === 'davet' ? fields : undefined }),
    onSuccess: (m) => {
      if (m.softenNote) toast.warning(m.softenNote);
      else toast.success('Taslak hazır; okuyup gönderin.');
      if (m.missing?.length) toast.warning(`Şablonda doldurulamayan alan: ${m.missing.join(', ')}`);
      setKind('');
      refresh();
    },
    onError: (e) => toast.error(errText(e, 'Taslak hazırlanamadı.')),
  });
  if (!c.can.letters && !c.messages.length) return null;
  return (
    <Block title="Yazışma" help="Mektup şablondan taslak olur. Portal adaya e-posta göndermez: metni kendi e-postanızdan gönderip «gönderildi» deyin. Teklif mektubu gönderilmeden önce onaylanır.">
      {c.can.letters && (
        <div className="mb-3 flex flex-col gap-2 rounded-xl bg-slate-50 p-2.5">
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Mektup</span>
            <select className={field} value={kind} onChange={(e) => setKind(e.target.value)}>
              <option value="">Tür seçin…</option>
              {LETTERS.map((l) => <option key={l.kind} value={l.kind}>{l.label}</option>)}
            </select>
          </label>
          {kind === 'davet' && (
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
              <label className="flex flex-col gap-1">
                <span className={labelCls}>{meta.fields.gorusme_tarihi ?? 'Mülakat tarihi'}</span>
                <input className={field} value={fields.gorusme_tarihi} onChange={(e) => setFields({ ...fields, gorusme_tarihi: e.target.value })} placeholder="12.10.2026 14:00" />
              </label>
              <label className="flex flex-col gap-1">
                <span className={labelCls}>{meta.fields.gorusme_yeri ?? 'Mülakat yeri'}</span>
                <input className={field} value={fields.gorusme_yeri} onChange={(e) => setFields({ ...fields, gorusme_yeri: e.target.value })} />
              </label>
            </div>
          )}
          <label className="flex min-h-11 items-center gap-2 sm:min-h-0">
            <input type="checkbox" className="h-4 w-4 accent-canvas-violet" checked={soften} disabled={!meta.modelVar} onChange={(e) => setSoften(e.target.checked)} />
            <span className="text-[12.5px]">Zeki AI tonu yumuşatsın (bilgi eklemez; bir bilgi kaybolursa şablon metni kalır)</span>
          </label>
          <div className="flex justify-end">
            <button type="button" className={btnPrimary} disabled={!kind || draft.isPending} onClick={() => draft.mutate()}>
              {draft.isPending ? 'Hazırlanıyor…' : 'Taslak hazırla'}
            </button>
          </div>
        </div>
      )}
      {!c.messages.length && <div className="py-3 text-center text-[12px] text-canvas-muted">Yazışma yok.</div>}
      <ul className="flex flex-col gap-2">
        {c.messages.map((m) => <MessageItem key={m.id} m={m} c={c} meta={meta} onChanged={refresh} />)}
      </ul>
    </Block>
  );
}

function MessageItem({ m, c, meta, onChanged }: { m: Message; c: Candidate; meta: RecruitMeta; onChanged: () => void }) {
  const [text, setText] = useState(m.body);
  const [ask, setAsk] = useState<'reject' | 'sent' | null>(null);
  const [channel, setChannel] = useState('eposta');
  const act = useMutation({
    mutationFn: (p: { action: 'edit' | 'submit' | 'approve' | 'reject' | 'sent' | 'cancel'; body?: Record<string, unknown> }) =>
      recruitApi.messageAction(m.id, p.action, p.body ?? {}),
    onSuccess: (r) => {
      toast.success(`Yazışma: ${r.statusLabel}.`);
      setAsk(null);
      onChanged();
    },
    onError: (e) => toast.error(errText(e, 'İşlem yapılamadı.')),
  });
  const editable = m.status === 'taslak' && c.can.letters;
  const canSend = c.can.letters && ((m.kind === 'teklif' && m.status === 'onaylandi') || (m.kind !== 'teklif' && m.status === 'taslak'));
  const tone = m.status === 'gonderildi' ? 'ok' : m.status === 'iptal' ? 'muted' : m.status === 'onayda' ? 'warn' : 'violet';
  return (
    <li className="rounded-xl border border-slate-100 bg-white/80 p-2.5">
      <div className="flex flex-wrap items-center gap-1.5">
        <span className="text-[13px] font-extrabold">{m.kindLabel}</span>
        <Pill tone={tone}>{m.statusLabel}</Pill>
        <span className="text-[11px] text-canvas-muted">
          {m.sentAt ? `gönderildi ${fmtDateTime(m.sentAt)} · ${meta.sendChannels[m.channel ?? ''] ?? m.channel}` : `hazırlandı ${fmtDateTime(m.createdAt)}`}
        </span>
      </div>
      {m.note && <Note tone="warn">Geri gönderme notu: {m.note}</Note>}
      {editable ? (
        <textarea className={`${field} mt-1.5 min-h-[160px] font-sans`} value={text} onChange={(e) => setText(e.target.value)} />
      ) : (
        <details className="mt-1">
          <summary className="cursor-pointer text-[12px] font-bold text-canvas-violet">Metni göster</summary>
          <pre className="mt-1 whitespace-pre-wrap break-words rounded-lg bg-slate-50 p-2 font-sans text-[12.5px] leading-snug">{m.body}</pre>
        </details>
      )}
      <div className="mt-1.5 flex flex-wrap justify-end gap-1.5">
        <button type="button" className={btnGhost} onClick={() => recruitApi.downloadMessage(m.id).catch((e) => toast.error(errText(e, 'İndirilemedi.')))}>
          <Download aria-hidden className="h-4 w-4" />
          Word
        </button>
        {editable && text !== m.body && (
          <button type="button" className={btnGhost} disabled={act.isPending} onClick={() => act.mutate({ action: 'edit', body: { body: text } })}>Kaydet</button>
        )}
        {editable && m.kind === 'teklif' && (
          <button type="button" className={btnPrimary} disabled={act.isPending || text !== m.body} onClick={() => act.mutate({ action: 'submit' })}>Onaya gönder</button>
        )}
        {m.status === 'onayda' && c.can.approveOffer && (
          <>
            <button type="button" className={btnGhost} disabled={act.isPending} onClick={() => setAsk('reject')}>Geri gönder</button>
            <button type="button" className={btnPrimary} disabled={act.isPending} onClick={() => act.mutate({ action: 'approve' })}>Onayla</button>
          </>
        )}
        {canSend && (
          <button type="button" className={btnPrimary} disabled={act.isPending || text !== m.body} onClick={() => setAsk('sent')}>Gönderdim</button>
        )}
        {c.can.letters && !['gonderildi', 'iptal'].includes(m.status) && (
          <button type="button" className={btnGhost} disabled={act.isPending} onClick={() => act.mutate({ action: 'cancel' })}>İptal</button>
        )}
      </div>
      <AskSheet
        open={ask === 'reject'}
        title="Teklifi geri gönder"
        message="Hazırlayan kişi notunuzu görür ve teklifi düzeltir."
        confirm="Geri gönder"
        input="Gerekçe"
        required
        busy={act.isPending}
        onClose={() => setAsk(null)}
        onConfirm={(note) => act.mutate({ action: 'reject', body: { note } })}
      />
      <Sheet open={ask === 'sent'} modal onClose={() => setAsk(null)} title="Gönderildi olarak kaydet" subtitle="Mektubu kendi e-postanızdan ya da elden verdiyseniz kaydedin; portal gönderim yapmaz.">
        <div className="flex flex-col gap-3">
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Kanal</span>
            <select className={field} value={channel} onChange={(e) => setChannel(e.target.value)}>
              {Object.entries(meta.sendChannels).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
          </label>
          <div className="flex justify-end gap-2">
            <button type="button" className={btnGhost} onClick={() => setAsk(null)}>Vazgeç</button>
            <button type="button" className={btnPrimary} disabled={act.isPending} onClick={() => act.mutate({ action: 'sent', body: { channel } })}>Kaydet</button>
          </div>
        </div>
      </Sheet>
    </li>
  );
}

/* ------------------------------------------------------------------ KVKK */

function Kvkk({ c }: { c: Candidate }) {
  const refresh = useRefresh(c.id);
  const nav = useNavigate();
  const [consent, setConsent] = useState({ purpose: 'aday_havuzu', channel: 'eposta', evidence: '' });
  const [deleting, setDeleting] = useState(false);
  const hrMeta = useQuery({ queryKey: ['hr', 'meta'], queryFn: hrApi.meta, enabled: ENGINE_ENABLED && c.can.consents, staleTime: 60_000 });
  const add = useMutation({
    mutationFn: () => hrApi.addConsent({ subjectType: 'aday', subjectId: c.id, ...consent }),
    onSuccess: () => {
      toast.success('Rıza kaydedildi.');
      setConsent({ ...consent, evidence: '' });
      refresh();
    },
    onError: (e) => toast.error(errText(e, 'Rıza kaydedilemedi.')),
  });
  const withdraw = useMutation({
    mutationFn: (id: string) => hrApi.withdrawConsent(id),
    onSuccess: () => {
      toast.success('Rıza geri çekildi.');
      refresh();
    },
    onError: (e) => toast.error(errText(e, 'Geri çekilemedi.')),
  });
  const del = useMutation({
    mutationFn: (reason: string) => recruitApi.deleteCandidate(c.id, reason),
    onSuccess: () => {
      toast.success('Adayın kişisel verisi silindi; tutanak yazıldı.');
      nav('/ik/ise-alim');
    },
    onError: (e) => toast.error(errText(e, 'Silinemedi.')),
  });
  const purposes = Object.entries(hrMeta.data?.purposes ?? {}).filter(([, p]) => p.subject === 'aday');
  const r = c.retention;
  return (
    <Block title="KVKK" help="Başvurunun değerlendirilmesi açık rıza istemez (sözleşmenin kurulması). Rıza yalnız havuzda tutma, referans görüşmesi ve gereksiz özel nitelikli veri içindir.">
      <div className="rounded-xl bg-slate-50 p-2.5 text-[12.5px] leading-snug">
        {c.employeeId ? 'Kayıt çalışan kaydına geçti; aday imhasına girmez.'
          : !c.outcome ? 'Süreç sürüyor; saklama süresi sonuçlanınca başlar.'
          : r.until ? `${r.label ?? 'Aday'} · bu kayıt ${fmtDay(r.until)} tarihinde silinecek.`
          : `${r.label ?? 'Aday'} · saklama süresi girilmemiş; süre girilene kadar silinmez (Çalışan ve KVKK kayıtları).`}
      </div>
      {c.can.consents && (
        <>
          <ul className="mt-2 flex flex-col gap-1.5">
            {(c.consents ?? []).map((x) => (
              <li key={x.id} className="flex flex-wrap items-center gap-1.5 rounded-lg bg-white/80 px-2 py-1.5 text-[12.5px]">
                <span className="font-bold">{x.purposeLabel}</span>
                <Pill tone={x.active ? 'ok' : 'muted'}>{x.active ? 'geçerli' : `geri çekildi ${fmtDay(x.withdrawnAt)}`}</Pill>
                <span className="text-[11px] text-canvas-muted">{fmtDay(x.givenAt)} · {x.channelLabel} · aydınlatma sürüm {x.noticeVersion}</span>
                {x.active && (
                  <button type="button" className="ml-auto text-[12px] font-bold text-red-700 hover:underline" disabled={withdraw.isPending} onClick={() => withdraw.mutate(x.id)}>
                    Geri çek
                  </button>
                )}
              </li>
            ))}
          </ul>
          <div className="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-2">
            <label className="flex flex-col gap-1">
              <span className={labelCls}>Rıza amacı</span>
              <select className={field} value={consent.purpose} onChange={(e) => setConsent({ ...consent, purpose: e.target.value })}>
                {purposes.map(([k, p]) => <option key={k} value={k}>{p.label}</option>)}
              </select>
            </label>
            <label className="flex flex-col gap-1">
              <span className={labelCls}>Kanal</span>
              <select className={field} value={consent.channel} onChange={(e) => setConsent({ ...consent, channel: e.target.value })}>
                {Object.entries(hrMeta.data?.channels ?? {}).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
              </select>
            </label>
            <label className="flex flex-col gap-1 sm:col-span-2">
              <span className={labelCls}>Kanıt (nerede duruyor)</span>
              <input className={field} value={consent.evidence} onChange={(e) => setConsent({ ...consent, evidence: e.target.value })} placeholder="ör. adayın 12.10 tarihli e-postası, İK klasörü" />
            </label>
            <div className="flex justify-end sm:col-span-2">
              <button type="button" className={btnGhost} disabled={add.isPending} onClick={() => add.mutate()}>Rıza kaydet</button>
            </div>
          </div>
        </>
      )}
      {(c.can.export || c.can.delete) && (
        <div className="mt-3 flex flex-wrap justify-end gap-2 border-t border-dashed border-slate-200 pt-2">
          {c.can.export && (
            <button type="button" className={btnGhost} onClick={() => recruitApi.exportCandidate(c.id).catch((e) => toast.error(errText(e, 'Dışa aktarılamadı.')))}>
              <Download aria-hidden className="h-4 w-4" />
              İlgili kişi talebi: dışa aktar
            </button>
          )}
          {c.can.delete && !c.employeeId && (
            <button type="button" className={`${btnGhost} !text-red-700`} onClick={() => setDeleting(true)}>
              <Trash2 aria-hidden className="h-4 w-4" />
              Talep üzerine sil
            </button>
          )}
        </div>
      )}
      <AskSheet
        open={deleting}
        title="Adayın verisini sil"
        message="Ad, iletişim bilgisi, özgeçmiş, kanıt, mülakat notu ve yazışmalar kalıcı olarak silinir; imha tutanağı yazılır. Geri alınamaz."
        confirm="Kalıcı olarak sil"
        danger
        input="Talebin kaydı (tarih, kanal)"
        required
        busy={del.isPending}
        onClose={() => setDeleting(false)}
        onConfirm={(reason) => del.mutate(reason)}
      />
    </Block>
  );
}

/* ------------------------------------------------------------------ aşama geçmişi */

function History({ c, meta }: { c: Candidate; meta: RecruitMeta }) {
  return (
    <Block title="Aşama geçmişi" help="Her aşama değişikliği bir kişinin kaydıdır.">
      <ol className="flex flex-col gap-1.5">
        {c.stageLog.map((x, i) => (
          <li key={i} className="rounded-lg bg-white/80 px-2 py-1.5 text-[12.5px] leading-snug">
            <span className="font-bold">{meta.stages[x.to]}</span>
            {x.outcome && <span> · {meta.outcomes[x.outcome]}</span>}
            <span className="text-canvas-muted"> — {x.actor}, {fmtDateTime(x.at)}</span>
            {x.reason && <div className="mt-0.5 whitespace-pre-wrap break-words text-canvas-muted">{x.reason}</div>}
          </li>
        ))}
      </ol>
    </Block>
  );
}
