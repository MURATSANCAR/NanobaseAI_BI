import { useMemo, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Plus } from 'lucide-react';
import { ENGINE_ENABLED } from '../../engine';
import { Note, Pill, btnPrimary, errText, field, label as labelCls } from '../../admin/ui';
import { Kpi, KpiRow, Panel } from '../../editorial/kit';
import Sheet from '../../editorial/studio/reader/Sheet';
import { STAGE_ORDER, daysText, recruitApi, type Card, type Pipeline, type RecruitMeta, type Stage } from '../hrApi';
import { HrFrame, Tabs } from '../parts';
import { FileDrop } from '../../components/FileDrop';
import { MB, titleFromFilename } from '../../components/fileDropRules';

/** M55 işe alım panosu: dört sayaç ve pozisyon başına aşama sütunları. Telefonda sütunlar sekmeye döner; aşama değişikliği
 *  kartın seçicisinden (sürükleme zorunlu değil). Kartta yalnız ad, pozisyon ve aşamadaki gün — puan ya da sıra yok. */

export default function RecruitBoard() {
  const [params, setParams] = useSearchParams();
  const position = params.get('pozisyon') ?? '';
  const [stageTab, setStageTab] = useState<Stage>('basvurdu');
  const [creating, setCreating] = useState(false);
  const [cv, setCv] = useState<File | null>(null);
  const meta = useQuery({ queryKey: ['hr', 'recruit', 'meta'], queryFn: recruitApi.meta, enabled: ENGINE_ENABLED, staleTime: 60_000 });
  const board = useQuery({ queryKey: ['hr', 'recruit', 'pipeline', position], queryFn: () => recruitApi.pipeline(position), enabled: ENGINE_ENABLED });
  const can = meta.data?.me.can;
  const setPosition = (v: string) => {
    const p = new URLSearchParams(params);
    if (v) p.set('pozisyon', v);
    else p.delete('pozisyon');
    setParams(p, { replace: true });
  };

  return (
    <HrFrame
      crumb="İşe alım panosu"
      title="İşe alım"
      lead="Bütün başvurular aşamasıyla tek yerde. Zeki AI özgeçmişteki kanıtı gösterir; adayı elemez, puanlamaz, sıralamaz — her aşama kararı bir kişinin kaydıdır. Portal adaya e-posta göndermez; mektup taslağı hazırlanır, gönderimi siz yaparsınız."
      aside={
        can?.all ? (
          <div className="flex justify-start lg:justify-end">
            <button type="button" className={btnPrimary} onClick={() => setCreating(true)}>
              <Plus aria-hidden className="h-4 w-4" />
              Yeni aday
            </button>
          </div>
        ) : undefined
      }
    >
      {!ENGINE_ENABLED && <Note tone="warn">Bu kurulumda veri bağlantısı tanımlı değil.</Note>}
      {board.error && <Note tone="err">{errText(board.error, 'Pano okunamadı.')}</Note>}
      {meta.data && !can?.all && !can?.see && (
        <Note tone="info">Rolünüzde aday görme yetkisi yok; pozisyonlar ve sayaçlar görünür, aday kartları görünmez.</Note>
      )}
      {/* Birincil eylem: özgeçmişi bırak → yeni aday penceresi dosya ekli ve ad dosya adından dolu açılır. */}
      <Panel>
        <FileDrop
          title="Özgeçmiş yükle (yeni aday)"
          hint="Aday penceresi özgeçmiş ekli açılır; ad soyadı dosya adından gelir, düzeltip pozisyonu seçersiniz. Kimlik ve iletişim bilgileri maskelenir."
          accept=".pdf,.docx,.odt,.txt"
          maxBytes={meta.data?.fileMaxMb ? meta.data.fileMaxMb * MB : undefined}
          feature="ik.aday-hepsi"
          allowed={meta.data ? !!can?.all : undefined}
          onPick={(f) => {
            setCv(f);
            setCreating(true);
          }}
        />
      </Panel>
      {board.data && <Counters data={board.data} />}
      {board.data && (
        <Panel>
          <div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
            <label className="flex min-w-0 flex-col gap-1 sm:w-[360px]">
              <span className={labelCls}>Pozisyon</span>
              <select className={field} value={position} onChange={(e) => setPosition(e.target.value)}>
                <option value="">Bütün pozisyonlar</option>
                {can?.all && <option value="-">Pozisyonsuz başvurular</option>}
                {board.data.positions.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.title} · {meta.data?.positionStates[p.state] ?? p.state}
                  </option>
                ))}
              </select>
            </label>
            <div className="font-mono text-[11.5px] text-canvas-muted">{board.data.total} aday</div>
          </div>
          <div className="mt-3 lg:hidden">
            <Tabs
              tabs={STAGE_ORDER.map((s) => ({ key: s, label: board.data.stages[s], badge: board.data.columns[s].length || null }))}
              value={stageTab}
              onChange={setStageTab}
            />
            <Column stage={stageTab} data={board.data} meta={meta.data} className="mt-2" />
          </div>
          <div className="mt-3 hidden gap-3 lg:grid lg:grid-cols-5">
            {STAGE_ORDER.map((s) => (
              <div key={s} className="min-w-0 rounded-2xl bg-slate-50/80 p-2">
                <div className="mb-1.5 flex items-center justify-between px-1">
                  <h3 className="text-[12.5px] font-extrabold">{board.data.stages[s]}</h3>
                  <span className="font-mono text-[11px] font-bold tabular-nums text-canvas-muted">{board.data.columns[s].length}</span>
                </div>
                <Column stage={s} data={board.data} meta={meta.data} />
              </div>
            ))}
          </div>
        </Panel>
      )}
      {board.isLoading && <div className="py-8 text-center text-[12px] text-canvas-muted">Yükleniyor…</div>}
      {meta.data && board.data && (
        <NewCandidateSheet
          open={creating}
          meta={meta.data}
          positions={board.data.positions}
          initialFile={cv}
          onClose={() => {
            setCreating(false);
            setCv(null);
          }}
        />
      )}
    </HrFrame>
  );
}

function Counters({ data }: { data: Pipeline }) {
  const c = data.counters;
  return (
    <KpiRow>
      <Kpi label="Açık pozisyon" value={String(c.openPositions)} help="Onaylanmış, başvuru alan" />
      <Kpi label="Bu hafta gelen" value={String(c.thisWeek)} help="Son 7 günde açılan aday kaydı" />
      <Kpi
        label="Aşamasında bekleyen"
        value={c.overSla === null ? '—' : String(c.overSla)}
        help={c.slaDays === null ? 'Bekleme eşiği ayarlanmadı (Portal ayarları)' : `${c.slaDays} günden uzun aynı aşamada`}
      />
      <Kpi label="Cevap bekleyen" value={String(c.waitingReply)} help={`Sonuçlandı, adaya yazılmadı · 30 günü aşan açık başvuru ${c.unanswered30}`} />
    </KpiRow>
  );
}

function Column({ stage, data, meta, className = '' }: { stage: Stage; data: Pipeline; meta?: RecruitMeta; className?: string }) {
  const cards = data.columns[stage];
  if (!cards.length) return <div className={`py-6 text-center text-[12px] text-canvas-muted ${className}`}>Bu aşamada aday yok.</div>;
  return (
    <ul className={`flex flex-col gap-2 ${className}`}>
      {cards.map((c) => (
        <CandidateCard key={c.id} c={c} data={data} canDecide={!!meta?.me.can.decide} />
      ))}
    </ul>
  );
}

function CandidateCard({ c, data, canDecide }: { c: Card; data: Pipeline; canDecide: boolean }) {
  const qc = useQueryClient();
  const move = useMutation({
    mutationFn: (to: Stage) => recruitApi.stage(c.id, { stage: to }),
    onSuccess: (r) => {
      toast.success(`Aday «${data.stages[r.to]}» aşamasına alındı.`);
      void qc.invalidateQueries({ queryKey: ['hr', 'recruit'] });
    },
    onError: (e) => toast.error(errText(e, 'Aşama değiştirilemedi.')),
  });
  return (
    <li className="rounded-xl border border-slate-100 bg-white p-2.5 shadow-sm">
      <Link to={`/ik/ise-alim/aday/${c.id}`} className="block min-w-0 rounded-lg outline-none focus-visible:ring-2 focus-visible:ring-canvas-violet">
        <div className="break-words text-[13px] font-extrabold leading-snug">{c.name || 'Aday'}</div>
        <div className="truncate text-[11.5px] text-canvas-muted">{c.positionTitle || 'Pozisyonsuz başvuru'}</div>
      </Link>
      <div className="mt-1.5 flex flex-wrap items-center gap-1">
        <span className="font-mono text-[11px] tabular-nums text-canvas-muted">{daysText(c.daysInStage)}</span>
        {c.outcomeLabel && <Pill tone={c.outcome === 'ise_alindi' ? 'ok' : 'muted'}>{c.outcomeLabel}</Pill>}
        {c.overSla && <Pill tone="warn">Bekliyor</Pill>}
        {c.needsReply && <Pill tone="err">Adaya yazılmadı</Pill>}
        {c.hasEvidence && <Pill tone="violet">Kanıtlı özet</Pill>}
      </div>
      {canDecide && c.stage !== 'sonuc' && (
        <label className="mt-2 flex items-center gap-2">
          <span className="sr-only">Aşamaya al</span>
          <select
            className={`${field} !min-h-9 !py-1 text-[12px]`}
            value=""
            disabled={move.isPending}
            onChange={(e) => e.target.value && move.mutate(e.target.value as Stage)}
          >
            <option value="">Aşamaya al…</option>
            {STAGE_ORDER.filter((s) => s !== c.stage && s !== 'sonuc').map((s) => (
              <option key={s} value={s}>{data.stages[s]}</option>
            ))}
          </select>
        </label>
      )}
    </li>
  );
}

const EMPTY = { fullName: '', email: '', phone: '', positionId: '', source: 'elle' };

function NewCandidateSheet({ open, meta, positions, initialFile, onClose }: {
  open: boolean; meta: RecruitMeta; positions: Pipeline['positions']; initialFile?: File | null; onClose: () => void;
}) {
  const qc = useQueryClient();
  const nav = useNavigate();
  const [f, setF] = useState(EMPTY);
  const [file, setFile] = useState<File | null>(null);
  // Sayfanın üstündeki alana bırakılan özgeçmiş: pencere dosya ekli, ad dosya adından dolu açılır.
  const [seenFile, setSeenFile] = useState<File | null>(null);
  if (open && initialFile && initialFile !== seenFile) {
    setSeenFile(initialFile);
    setFile(initialFile);
    setF((x) => (x.fullName.trim() ? x : { ...x, fullName: titleFromFilename(initialFile.name) }));
  }
  const set = (k: keyof typeof EMPTY) => (v: string) => setF((x) => ({ ...x, [k]: v }));
  const openPositions = useMemo(() => positions.filter((p) => p.state === 'acik' || p.state === 'beklemede'), [positions]);
  const create = useMutation({
    mutationFn: async () => {
      const made = await recruitApi.createCandidate({
        fullName: f.fullName.trim(), email: f.email.trim() || undefined, phone: f.phone.trim() || undefined,
        positionId: f.positionId || null, source: f.source,
      });
      if (file) await recruitApi.addFile(made.id, file);
      return made;
    },
    onSuccess: (made) => {
      toast.success(made.ackDraft ? 'Aday açıldı; «başvurunuz alındı» taslağı hazır.' : 'Aday açıldı.');
      void qc.invalidateQueries({ queryKey: ['hr', 'recruit'] });
      setF(EMPTY);
      setFile(null);
      onClose();
      nav(`/ik/ise-alim/aday/${made.id}`);
    },
    onError: (e) => toast.error(errText(e, 'Aday açılamadı.')),
  });
  return (
    <Sheet open={open} modal onClose={onClose} title="Yeni aday" subtitle="E-postayla gelen başvurular kurumsal e-posta modülünden kendiliğinden gelir; buradan elle ya da ilan sitesinden gelen başvuru girilir.">
      <form
        className="flex flex-col gap-3"
        onSubmit={(e) => {
          e.preventDefault();
          create.mutate();
        }}
      >
        <label className="flex flex-col gap-1">
          <span className={labelCls}>Ad soyad</span>
          <input className={field} value={f.fullName} onChange={(e) => set('fullName')(e.target.value)} autoComplete="off" required />
        </label>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <label className="flex flex-col gap-1">
            <span className={labelCls}>E-posta</span>
            <input className={field} type="email" inputMode="email" value={f.email} onChange={(e) => set('email')(e.target.value)} autoComplete="off" />
          </label>
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Telefon</span>
            <input className={field} inputMode="tel" value={f.phone} onChange={(e) => set('phone')(e.target.value)} autoComplete="off" />
          </label>
        </div>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Pozisyon</span>
            <select className={field} value={f.positionId} onChange={(e) => set('positionId')(e.target.value)}>
              <option value="">Pozisyonsuz (genel başvuru)</option>
              {openPositions.map((p) => <option key={p.id} value={p.id}>{p.title}</option>)}
            </select>
          </label>
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Kaynak</span>
            <select className={field} value={f.source} onChange={(e) => set('source')(e.target.value)}>
              {Object.entries(meta.sources).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
          </label>
        </div>
        <FileDrop
          size="sm"
          title={file ? 'Özgeçmişi değiştir' : 'Özgeçmiş ekle'}
          accept=".pdf,.docx,.odt,.txt"
          maxBytes={meta.fileMaxMb ? meta.fileMaxMb * MB : undefined}
          picked={file}
          onPick={setFile}
        />
        <Note tone="info">
          Özgeçmişteki kimlik no, telefon, adres, doğum tarihi, medeni hal ve özel nitelikli bilgiler maskelenir; Zeki AI yalnız maskeli metni görür.
        </Note>
        <div className="flex justify-end">
          <button type="submit" className={btnPrimary} disabled={create.isPending || !f.fullName.trim()}>
            {create.isPending ? 'Açılıyor…' : 'Adayı aç'}
          </button>
        </div>
      </form>
    </Sheet>
  );
}
