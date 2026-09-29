import { useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Bell, Plus } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import SqlInfo from '../components/SqlInfo';
import { Note, Pill, btnPrimary, errText, field, label as labelCls } from '../admin/ui';
import { Kpi, KpiRow, Panel } from '../editorial/kit';
import { STAGE_TONE, fmtMoney, inflApi, type Board, type Collab, type Meta, type Stage } from './api';
import CollabSheet, { CollabCardBody } from './CollabSheet';
import NewCollabSheet from './NewCollabSheet';
import { InflFrame, useMeta } from './parts';

/** M23 İşbirlikleri panosu: teklif → kitap gönderildi → içerik bekleniyor → içerik onayda → yayında → rapor → ödeme.
 *  Masaüstünde sütunlar yan yana (kendi kabında kayar), telefonda tek sütun + aşama seçici. Açık kart ?is= ile adreste. */
export default function CollabBoard() {
  const meta = useMeta();
  const [params, setParams] = useSearchParams();
  const mine = params.get('benim') === '1';
  const board = useQuery({ queryKey: ['influencers', 'board', mine], queryFn: () => inflApi.board(mine), enabled: ENGINE_ENABLED });
  const [creating, setCreating] = useState(false);
  const open = params.get('is');
  const setOpen = (id: string | null) => {
    const p = new URLSearchParams(params);
    if (id) p.set('is', id);
    else p.delete('is');
    setParams(p, { replace: !id });
  };
  const me = meta.data?.me;
  return (
    <InflFrame
      title="İşbirlikleri"
      lead="Kitaplarımızı tanıtan içerik üreticileriyle (kitap blogcusu, Instagram, YouTube, TikTok hesapları) yapılan işbirlikleri: tekliften kitap gönderimine, paylaşımdan ödemeye kadar tek panoda. Portal içerik üreticisine yazmaz, paylaşım yapmaz."
      aside={me?.canEdit ? (
        <button type="button" className={btnPrimary} onClick={() => setCreating(true)}>
          <Plus aria-hidden className="h-4 w-4" /> Yeni işbirliği
        </button>
      ) : undefined}
    >
      {!ENGINE_ENABLED && <Note tone="warn">Veri bağlantısı kurulu değil; bu ekran şu an veri gösteremez. Sistem yöneticinize haber verin.</Note>}
      {(meta.error || board.error) && <Note tone="err">{errText(meta.error ?? board.error, 'Pano okunamadı.')}</Note>}
      {board.data && meta.data && (
        <>
          <KpiRow>
            <Kpi label="Açık işbirliği" value={String(board.data.open)} help={mine ? 'Açtıklarım' : 'Hepsi'} active={!mine}
              onClick={() => setParams(mine ? {} : { benim: '1' }, { replace: true })} info={<SqlInfo k={board.data.kaynaklar} alan="open" label="Açık işbirliği" />}
              explain="Kapanmamış bütün işbirlikleri. Karta dokunarak yalnız sizin açtıklarınızla hepsi arasında geçiş yaparsınız." />
            <Kpi label="Onay bekleyen teklif" value={String(board.data.waitingApproval)} help="Seçim ve ücret onayı" info={<SqlInfo k={board.data.kaynaklar} alan="waitingApproval" label="Onay bekleyen teklif" />}
              explain="Kişi seçimi ve ücreti onay bekleyen teklifler. Onay gelmeden iş ilerlemez; teklifi öneren kişi kendisi onaylayamaz." />
            <Kpi label="Bağlantısı geciken" value={String(board.data.linkLate)} help={`Yayın tarihinden ${meta.data.ayarlar.linkGraceDays} gün sonra bağlantı yok`} info={<SqlInfo k={board.data.kaynaklar} alan="linkLate" label="Bağlantısı geciken" />}
              explain="Kararlaştırılan yayın tarihinin üstünden süre geçtiği hâlde paylaşım bağlantısı girilmemiş işbirlikleri. İçerik üreticisine ulaşıp bağlantıyı isteyin." />
            <Kpi label="Bu ay" value={board.data.month.spend !== null ? fmtMoney(board.data.month.spend) : String(board.data.month.collabs)}
              help={board.data.month.spend !== null ? `${board.data.month.collabs} işbirliği${board.data.month.budget ? ` · bütçe ${fmtMoney(board.data.month.budget)}` : ''}` : 'işbirliği (ücretler yetkiyle görünür)'} info={<SqlInfo k={board.data.kaynaklar} alan="month" label="Bu ay" />}
              explain="Bu ay yapılan işbirliği harcaması ve sayısı; aylık bütçe girildiyse yanında yazar. Ücretleri yalnız onay ya da ödeme yetkisi olanlar görür." />
          </KpiRow>
          <Reminders board={board.data} onOpen={setOpen} />
          <Columns board={board.data} meta={meta.data} onOpen={setOpen} />
          {board.data.closedRecent.length > 0 && (
            <Panel>
              <h2 className="mb-2 flex items-center gap-1 text-[13px] font-extrabold">Son 30 günde kapanan<SqlInfo k={board.data.kaynaklar} alan="closedRecent" label="Son 30 günde kapanan" /></h2>
              <div className="flex flex-col gap-1">
                {board.data.closedRecent.map((c) => (
                  <button key={c.id} type="button" onClick={() => setOpen(c.id)}
                    className="flex min-h-11 flex-wrap items-center gap-2 rounded-xl px-2 text-left text-[12.5px] hover:bg-slate-50">
                    <Pill tone={STAGE_TONE[c.stage]}>{c.stageLabel}</Pill>
                    <span className="font-bold">{c.personName}</span>
                    <span className="text-canvas-muted">{c.bookTitle}</span>
                  </button>
                ))}
              </div>
            </Panel>
          )}
        </>
      )}
      {board.isLoading && <Panel><div className="py-8 text-center text-[12px] text-canvas-muted">Yükleniyor…</div></Panel>}
      {meta.data && <CollabSheet id={open} meta={meta.data} onClose={() => setOpen(null)} />}
      {meta.data && <NewCollabSheet open={creating} meta={meta.data} onClose={() => setCreating(false)} onCreated={setOpen} />}
    </InflFrame>
  );
}

function Reminders({ board, onOpen }: { board: Board; onOpen: (id: string) => void }) {
  if (!board.reminders.length) return null;
  return (
    <Panel>
      <h2 className="mb-2 flex items-center gap-1.5 text-[13px] font-extrabold"><Bell aria-hidden className="h-4 w-4" /> Bugün<SqlInfo k={board.kaynaklar} alan="reminders" label="Hatırlatmalar" /></h2>
      <ul className="flex flex-col gap-1">
        {board.reminders.map((r) => (
          <li key={r.key}>
            {r.collabId ? (
              <button type="button" onClick={() => onOpen(r.collabId as string)} className="min-h-10 w-full rounded-xl px-2 py-1.5 text-left text-[12.5px] leading-snug hover:bg-slate-50">{r.text}</button>
            ) : r.personId ? (
              <Link to={`/isbirlikleri/kisi/${r.personId}`} className="block min-h-10 rounded-xl px-2 py-1.5 text-[12.5px] leading-snug hover:bg-slate-50">{r.text}</Link>
            ) : (
              <div className="px-2 py-1.5 text-[12.5px] leading-snug">{r.text}</div>
            )}
          </li>
        ))}
      </ul>
    </Panel>
  );
}

function Columns({ board, meta, onOpen }: { board: Board; meta: Meta; onOpen: (id: string) => void }) {
  const [phoneStage, setPhoneStage] = useState<Stage>('teklif');
  const showFee = meta.me.canSeeFee;
  const card = (c: Collab) => (
    <button key={c.id} type="button" onClick={() => onOpen(c.id)}
      className={`w-full rounded-2xl border bg-white/90 p-3 text-left transition-colors duration-150 hover:border-canvas-violet/40 ${c.linkLate ? 'border-red-200' : c.waitingApproval ? 'border-amber-200' : 'border-slate-100'}`}>
      <CollabCardBody c={c} showFee={showFee} />
      <div className="mt-1 flex flex-wrap gap-1">
        {c.waitingApproval && <Pill tone="warn">Onay bekliyor</Pill>}
        {c.linkLate && <Pill tone="err">Bağlantı yok</Pill>}
        {c.stage === 'yayinda' && c.disclosureOk !== true && <Pill tone="warn">Yasal etiket eksik</Pill>}
      </div>
    </button>
  );
  const col = board.columns.find((x) => x.stage === phoneStage) ?? board.columns[0];
  return (
    <>
      {/* Telefon: tek sütun, aşama seçici. */}
      <div className="flex flex-col gap-2 lg:hidden">
        <div className="flex items-center gap-1 px-1 text-[11px] text-canvas-muted">Aşama başına işbirliği sayısı<SqlInfo k={board.kaynaklar} alan="columns" label="Aşama başına işbirliği" /></div>
        <label className="flex flex-col gap-1 px-1">
          <span className={labelCls}>Aşama</span>
          <select className={field} value={phoneStage} onChange={(e) => setPhoneStage(e.target.value as Stage)}>
            {board.columns.map((x) => <option key={x.stage} value={x.stage}>{x.label} ({x.items.length})</option>)}
          </select>
        </label>
        <div className="flex flex-col gap-2">
          {col.items.length === 0 && <div className="py-6 text-center text-[12.5px] text-canvas-muted">Bu aşamada işbirliği yok. Başka bir aşama seçin.</div>}
          {col.items.map(card)}
        </div>
      </div>
      {/* Masaüstü: sütunlar yan yana; geniş pano kendi kabında kayar. */}
      <div className="hidden overflow-x-auto pb-2 lg:block">
        <div className="grid min-w-[1400px] grid-cols-7 gap-3">
          {board.columns.map((x) => (
            <section key={x.stage} className="flex min-w-0 flex-col gap-2 rounded-2xl bg-slate-50/80 p-2">
              <h2 className="flex items-center justify-between px-1 text-[12px] font-extrabold">
                {x.label}
                <span className="inline-flex items-center gap-1 font-mono text-[11px] text-canvas-muted">{x.items.length}<SqlInfo k={board.kaynaklar} alan="columns" label={`${x.label}: işbirliği sayısı`} /></span>
              </h2>
              {x.items.map(card)}
            </section>
          ))}
        </div>
      </div>
    </>
  );
}
