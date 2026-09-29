import { useCallback, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { ArrowRight, CalendarPlus, Loader2, Pencil, Plus, RefreshCw, Trash2, UserPlus } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import { Loading, Note, Pill, TableWrap, btnGhost, btnPrimary, errText, field, td, th } from '../admin/ui';
import { Panel } from '../editorial/kit';
import Sheet from '../editorial/studio/reader/Sheet';
import SqlInfo, { InfoLabel } from '../components/SqlInfo';
import type { Kaynaklar } from '../components/sqlInfo';
import {
  fmtDay, fmtLeft, fmtTime, fmtValue, kurulApi, parseNum,
  type Action, type IndicatorDef, type KurulMeta, type Meeting, type Member,
} from './api';
import { AskSheet, ColorBadge, Empty, KurulFrame, SelectInput, Tabs, TextInput } from './parts';
import IndicatorTile from './IndicatorTile';
import IndicatorSheet from './IndicatorSheet';
import { Explain } from '../components/Explain';

/** DYK: kurulun tek sayfası. Panel (bölüm kartları, kritik şerit), toplantılar, kararlar ve aksiyonlar, paketler; yetkiyle
 *  gösterge kataloğu ve kurul üyeleri. Sekme ve dönem adres çubuğunda. Telefonda tek sütun. */

const ALL_TABS = [
  { key: 'panel', label: 'Panel' },
  { key: 'toplantilar', label: 'Toplantılar' },
  { key: 'aksiyonlar', label: 'Kararlar ve aksiyonlar' },
  { key: 'paketler', label: 'Paketler' },
  { key: 'katalog', label: 'Gösterge kataloğu' },
  { key: 'uyeler', label: 'Kurul üyeleri' },
] as const;
type Tab = (typeof ALL_TABS)[number]['key'];

export default function KurulScreen() {
  const [params, setParams] = useSearchParams();
  const meta = useQuery({ queryKey: ['kurul', 'meta'], queryFn: kurulApi.meta, enabled: ENGINE_ENABLED, staleTime: 60_000 });
  const me = meta.data?.me;
  const tabs = ALL_TABS.filter((t) => (t.key === 'katalog' ? me?.canCatalog : t.key === 'uyeler' ? me?.canPrepare || me?.canFreeze : true));
  const tab: Tab = (tabs.find((t) => t.key === params.get('sekme'))?.key ?? 'panel') as Tab;
  const update = useCallback(
    (next: Record<string, string | null>) => {
      const p = new URLSearchParams(params);
      for (const [k, v] of Object.entries(next)) {
        if (v) p.set(k, v);
        else p.delete(k);
      }
      setParams(p, { replace: true });
    },
    [params, setParams],
  );
  return (
    <KurulFrame
      title="Kurul"
      lead="Kurul için şirketin durumu tek sayfada: modüllerin onaylı sonuçlarından gelen göstergeler, toplantılar, kararlar, aksiyonlar ve dondurulan kurul paketi. Kaynağı olmayan gösterge gri kalır."
    >
      {!ENGINE_ENABLED && <Note tone="warn">Sunucu bağlantısı yok; kurul verileri gösterilemiyor.</Note>}
      {meta.error && <Note tone="err">{errText(meta.error, 'Ekran bilgisi okunamadı; biraz sonra sayfayı yenileyin.')}</Note>}
      <Tabs tabs={tabs} value={tab} onChange={(t) => update({ sekme: t === 'panel' ? null : t })} />
      {meta.data && tab === 'panel' && <PanelTab meta={meta.data} donem={params.get('donem') ?? ''} setDonem={(d) => update({ donem: d || null })} />}
      {meta.data && tab === 'toplantilar' && <MeetingsTab meta={meta.data} />}
      {meta.data && tab === 'aksiyonlar' && <ActionsTab meta={meta.data} />}
      {meta.data && tab === 'paketler' && <PackagesTab />}
      {meta.data && tab === 'katalog' && <CatalogTab meta={meta.data} />}
      {meta.data && tab === 'uyeler' && <MembersTab meta={meta.data} />}
    </KurulFrame>
  );
}

/* ------------------------------------------------------------------ Panel */

function PanelTab({ meta, donem, setDonem }: { meta: KurulMeta; donem: string; setDonem: (d: string) => void }) {
  const qc = useQueryClient();
  const [open, setOpen] = useState<string | null>(null);
  const q = useQuery({
    queryKey: ['kurul', 'panel', donem],
    queryFn: () => kurulApi.panel(donem || undefined),
    enabled: ENGINE_ENABLED,
    refetchInterval: (query) => (query.state.data?.olcumSuruyor ? 5000 : false),
  });
  const meetings = useQuery({ queryKey: ['kurul', 'meetings'], queryFn: kurulApi.meetings, enabled: ENGINE_ENABLED });
  const late = useQuery({ queryKey: ['kurul', 'actions', 'geciken'], queryFn: () => kurulApi.actions({ durum: 'geciken' }), enabled: ENGINE_ENABLED });
  const measure = useMutation({
    mutationFn: kurulApi.refresh,
    onSuccess: (r) => {
      toast.success(r.started ? 'Göstergeler okunuyor; birazdan güncellenir.' : 'Ölçüm zaten sürüyor.');
      qc.invalidateQueries({ queryKey: ['kurul', 'panel'] });
    },
    onError: (e) => toast.error(errText(e, 'Ölçüm başlatılamadı.')),
  });
  if (q.isLoading) return <Loading />;
  if (q.error) return <Note tone="err">{errText(q.error, 'Panel okunamadı; biraz sonra yeniden deneyin.')}</Note>;
  if (!q.data) return null;
  const p = q.data;
  const next = meetings.data?.siradaki;
  return (
    <>
      <div className="flex flex-col gap-2 px-1 sm:flex-row sm:flex-wrap sm:items-center sm:justify-between">
        <div className="flex flex-wrap items-center gap-2 text-[12px] text-canvas-muted">
          {p.donemler.length > 1 ? (
            <select aria-label="Dönem" className={`${field} w-auto`} value={donem || p.donem} onChange={(e) => setDonem(e.target.value === p.donemler[0] ? '' : e.target.value)}>
              {p.donemler.map((d) => <option key={d} value={d}>{d}</option>)}
            </select>
          ) : (
            <span className="font-bold text-canvas-ink">{p.donemAdi}</span>
          )}
          <span>
            <Explain label="Gösterge renkleri" title="Renkler ne demek?">
              Yolunda (yeşil): değer eşiğin iyi tarafında. İzlenmeli (sarı): uyarı eşiği aşıldı. Dikkat (kırmızı): kırmızı eşik aşıldı; sahibinin yorumu beklenir. Eşik yok: değer ölçüldü ama eşik tanımlı değil. Kaynak yok: kaynak modülde bu dönem için onaylı sonuç yok, sayı yazılmaz. Okunamadı: kaynak şu an okunamadı.
            </Explain>{' '}
            {p.sayilar.toplam} göstergeden {p.sayilar.hazir} hazır, {p.sayilar.gri} kaynak yok{p.sayilar.hata ? `, ${p.sayilar.hata} okunamadı` : ''}
            <SqlInfo k={p.kaynaklar} alan="sayilar" label="Gösterge sayıları" className="ml-0.5" />
            {p.olcum ? ` · son ölçüm ${fmtTime(p.olcum.at)}` : ''}
            {p.olcum && <SqlInfo k={p.kaynaklar} alan="olcum" label="Son ölçüm" className="ml-0.5" />}
          </span>
          {p.olcumSuruyor && <span className="inline-flex items-center gap-1 font-bold text-canvas-violet"><Loader2 aria-hidden className="h-3.5 w-3.5 animate-spin" /> okunuyor</span>}
        </div>
        {meta.me.canPrepare && (
          <button type="button" className={btnGhost} disabled={measure.isPending || p.olcumSuruyor} onClick={() => measure.mutate()}>
            <RefreshCw aria-hidden className="h-4 w-4" /> Şimdi ölç
          </button>
        )}
      </div>
      {p.enEskiVeri && (
        <Note tone="info">Rakamlar kaynak modüllerin veri son gününe kadardır (en eskisi {fmtDay(p.enEskiVeri)}); her kutuda kendi günü yazar.</Note>
      )}

      <div className="grid grid-cols-1 gap-3 lg:grid-cols-3 lg:gap-4">
        <Panel>
          <h2 className="mb-2 flex items-center gap-1 text-[15px] font-extrabold tracking-tight">
            Dikkat isteyenler <SqlInfo k={p.kaynaklar} alan="kritik[]" label="Dikkat isteyenler" />
          </h2>
          {p.kritik.length === 0 ? (
            <Empty>Kırmızı gösterge yok; bu dönem dikkat isteyen bir rakam görünmüyor.</Empty>
          ) : (
            <ul className="flex flex-col gap-1.5">
              {p.kritik.map((g) => (
                <li key={g.kod} className="flex items-start gap-1">
                  <button type="button" onClick={() => setOpen(g.kod)} className="flex min-h-11 min-w-0 flex-1 flex-col gap-0.5 rounded-xl bg-white/80 px-3 py-2 text-left transition-transform duration-150 ease-out hover:bg-white active:scale-[0.98]">
                    <span className="flex items-center justify-between gap-2">
                      <span className="min-w-0 break-words text-[12.5px] font-bold">{g.ad}</span>
                      <span className="shrink-0 font-mono text-[12.5px] font-bold tabular-nums">{g.degerKisa}</span>
                    </span>
                    <span className="text-[11.5px] leading-snug text-canvas-muted">{g.yorum ? g.yorum.metin : 'Sahibinin yorumu bekleniyor.'}</span>
                  </button>
                  <SqlInfo k={p.kaynaklar} alan="kritik[]" row={g.kod} label={g.ad} className="mt-2.5" />
                </li>
              ))}
            </ul>
          )}
        </Panel>
        <Panel>
          <h2 className="mb-2 text-[15px] font-extrabold tracking-tight">Sıradaki toplantı</h2>
          {next ? (
            <div className="flex items-center gap-1">
              <Link to={`/kurul/toplanti/${next.id}`} className="flex min-h-11 min-w-0 flex-1 items-center justify-between gap-2 rounded-xl bg-white/80 px-3 py-2 hover:bg-white">
                <span className="min-w-0">
                  <span className="block break-words text-[13px] font-bold">{next.baslik}</span>
                  <span className="block text-[11.5px] text-canvas-muted">{fmtDay(next.tarih)} · {fmtLeft(next.kalanGun)}{next.paketDondu ? ' · paket donduruldu' : ''}</span>
                </span>
                <ArrowRight aria-hidden className="h-4 w-4 shrink-0" />
              </Link>
              <SqlInfo k={meetings.data?.kaynaklar} alan="siradaki" label="Sıradaki toplantı" />
            </div>
          ) : (
            <Empty>Planlanmış toplantı yok.{meta.me.canPrepare ? ' «Toplantılar» sekmesinden yeni toplantı açabilirsiniz.' : ''}</Empty>
          )}
        </Panel>
        <Panel>
          <h2 className="mb-2 flex items-center gap-1 text-[15px] font-extrabold tracking-tight">
            Geciken kurul aksiyonu <SqlInfo k={late.data?.kaynaklar} alan="total" label="Geciken kurul aksiyonu" />
          </h2>
          <div className="font-mono text-[28px] font-bold tabular-nums">{late.data ? late.data.total : '—'}</div>
          <p className="text-[11.5px] text-canvas-muted">Termini geçmiş, kapanmamış aksiyonlar (Kararlar ve aksiyonlar sekmesi).</p>
        </Panel>
      </div>

      <div className="grid grid-cols-1 gap-3 xl:grid-cols-2 xl:gap-4">
        {p.bolumler.map((b) => (
          <Panel key={b.id}>
            <h2 className="mb-2 text-[15px] font-extrabold tracking-tight">{b.ad}</h2>
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
              {b.gostergeler.map((g) => <IndicatorTile key={g.kod} g={g} k={p.kaynaklar} onOpen={setOpen} />)}
            </div>
          </Panel>
        ))}
      </div>
      <IndicatorSheet kod={open} donem={p.donem} meta={meta} onClose={() => setOpen(null)} />
    </>
  );
}

/* ------------------------------------------------------------------ Toplantılar */

function MeetingsTab({ meta }: { meta: KurulMeta }) {
  const nav = useNavigate();
  const q = useQuery({ queryKey: ['kurul', 'meetings'], queryFn: kurulApi.meetings, enabled: ENGINE_ENABLED });
  const [creating, setCreating] = useState(false);
  if (q.isLoading) return <Loading />;
  if (q.error) return <Note tone="err">{errText(q.error, 'Toplantılar okunamadı.')}</Note>;
  const items = q.data?.items ?? [];
  return (
    <>
      {meta.me.canPrepare && (
        <div className="flex justify-start px-1">
          <button type="button" className={btnPrimary} onClick={() => setCreating(true)}>
            <CalendarPlus aria-hidden className="h-4 w-4" /> Yeni toplantı
          </button>
        </div>
      )}
      {items.length === 0 ? (
        <Empty>Kayıtlı toplantı yok.{meta.me.canPrepare ? ' «Yeni toplantı» ile başlayın.' : ''}</Empty>
      ) : (
        <ul className="grid grid-cols-1 gap-2 lg:grid-cols-2">
          {items.map((m) => (
            <li key={m.id} className="relative">
              <Link to={`/kurul/toplanti/${m.id}`} className="glass-panel flex h-full min-h-11 flex-col gap-1 rounded-2xl p-3 shadow-glass-float transition-transform duration-150 ease-out active:scale-[0.99]">
                <span className="flex flex-wrap items-center justify-between gap-2">
                  <span className="min-w-0 break-words text-[14px] font-extrabold">{m.baslik}</span>
                  <Pill tone={m.durum === 'yapildi' ? 'ok' : m.durum === 'iptal' ? 'muted' : 'violet'}>{m.durumAdi}</Pill>
                </span>
                <span className="text-[12px] text-canvas-muted">
                  {m.turAdi} · {fmtDay(m.tarih)}{m.saat ? ` ${m.saat}` : ''}{m.yer ? ` · ${m.yer}` : ''}
                  {m.durum === 'planlandi' && m.kalanGun !== undefined ? ` · ${fmtLeft(m.kalanGun)}` : ''}
                </span>
                <span className="pr-7 text-[11.5px] text-canvas-muted">
                  {m.kararSayisi ?`${m.kararSayisi} karar` : 'karar yok'} · {m.paketSurum ? `paket v${m.paketSurum}${m.paketDondu ? ' (donduruldu)' : ''}` : 'paket yok'}
                </span>
              </Link>
              <span className="absolute bottom-2.5 right-2.5">
                <SqlInfo k={q.data?.kaynaklar} alan="items[]" label={`${m.baslik}: kalan gün ve karar sayısı`} />
              </span>
            </li>
          ))}
        </ul>
      )}
      {creating && <MeetingSheet open meta={meta} onClose={() => setCreating(false)} onSaved={(id) => nav(`/kurul/toplanti/${id}`)} />}
    </>
  );
}

export function MeetingSheet({ open, meta, initial, onClose, onSaved }: {
  open: boolean; meta: KurulMeta; initial?: { id: string; tur: string; baslik: string; tarih: string; saat: string | null; yer: string | null; durum: string; katilimcilar: string[] };
  onClose: () => void; onSaved: (id: string) => void;
}) {
  const qc = useQueryClient();
  const [f, setF] = useState(() => ({
    tur: initial?.tur ?? 'yonetim', baslik: initial?.baslik ?? '', tarih: initial?.tarih ?? '', saat: initial?.saat ?? '',
    yer: initial?.yer ?? '', durum: initial?.durum ?? 'planlandi', katilimcilar: (initial?.katilimcilar ?? []).join(', '),
  }));
  const save = useMutation({
    mutationFn: () => {
      const b: Partial<Meeting> = { tur: f.tur as Meeting['tur'], baslik: f.baslik || undefined, tarih: f.tarih, saat: f.saat || null,
        yer: f.yer || null, durum: f.durum as Meeting['durum'], katilimcilar: f.katilimcilar.split(',').map((x) => x.trim()).filter(Boolean) };
      return initial ? kurulApi.updateMeeting(initial.id, b) : kurulApi.createMeeting(b);
    },
    onSuccess: (m) => {
      toast.success(initial ? 'Toplantı güncellendi.' : 'Toplantı açıldı.');
      qc.invalidateQueries({ queryKey: ['kurul'] });
      onClose();
      onSaved(m.id);
    },
    onError: (e) => toast.error(errText(e, 'Toplantı kaydedilemedi.')),
  });
  return (
    <Sheet open={open} modal onClose={onClose} title={initial ? 'Toplantıyı düzenle' : 'Yeni toplantı'}>
      <form className="flex flex-col gap-3" onSubmit={(e) => { e.preventDefault(); save.mutate(); }}>
        <SelectInput id="k-tur" label="Kurul" value={f.tur} onChange={(v) => setF({ ...f, tur: v })} options={meta.toplantiTurleri} />
        <TextInput id="k-baslik" label="Başlık" value={f.baslik} onChange={(v) => setF({ ...f, baslik: v })} placeholder="Boşsa «Yönetim kurulu toplantısı»" />
        <div className="grid grid-cols-2 gap-2">
          <TextInput id="k-tarih" label="Tarih" type="date" value={f.tarih} onChange={(v) => setF({ ...f, tarih: v })} />
          <TextInput id="k-saat" label="Saat" type="time" value={f.saat} onChange={(v) => setF({ ...f, saat: v })} />
        </div>
        <TextInput id="k-yer" label="Yer" value={f.yer} onChange={(v) => setF({ ...f, yer: v })} placeholder="Ör. Genel merkez toplantı salonu" />
        {initial && <SelectInput id="k-durum" label="Durum" value={f.durum} onChange={(v) => setF({ ...f, durum: v })} options={meta.toplantiDurumlari} />}
        <TextInput id="k-kat" label="Katılımcılar" value={f.katilimcilar} onChange={(v) => setF({ ...f, katilimcilar: v })} help="Adları virgülle ayırın" placeholder="Ör. Ayşe Yılmaz, Mehmet Demir" area />
        <div className="flex justify-end gap-2">
          <button type="button" className={btnGhost} onClick={onClose}>Vazgeç</button>
          <button type="submit" className={btnPrimary} disabled={!f.tarih || save.isPending}>Kaydet</button>
        </div>
      </form>
    </Sheet>
  );
}

/* ------------------------------------------------------------------ Kararlar ve aksiyonlar */

const ACTION_FILTERS = { acik: 'Açık', geciken: 'Geciken', tamamlandi: 'Tamamlanan', hepsi: 'Hepsi' };

function ActionsTab({ meta }: { meta: KurulMeta }) {
  const [durum, setDurum] = useState('acik');
  const [mine, setMine] = useState(false);
  const q = useQuery({ queryKey: ['kurul', 'actions', durum, mine], queryFn: () => kurulApi.actions({ durum, mine }), enabled: ENGINE_ENABLED });
  return (
    <>
      <div className="flex flex-wrap items-end gap-2 px-1">
        <div className="w-44"><SelectInput id="k-af" label="Durum" value={durum} onChange={setDurum} options={ACTION_FILTERS} /></div>
        <label className="inline-flex min-h-11 items-center gap-2 text-[12.5px] font-bold">
          <input type="checkbox" className="h-4 w-4" checked={mine} onChange={(e) => setMine(e.target.checked)} /> Yalnız bana atananlar
        </label>
      </div>
      {q.isLoading && <Loading />}
      {q.error && <Note tone="err">{errText(q.error, 'Aksiyonlar okunamadı.')}</Note>}
      {q.data && (q.data.items.length === 0 ? <Empty>Bu süzgeçte aksiyon yok. Kurul aksiyonları toplantı sayfasında kararla birlikte açılır.</Empty> : (
        <ul className="grid grid-cols-1 gap-2 lg:grid-cols-2">
          {q.data.items.map((a) => <li key={a.id}><ActionCard a={a} meta={meta} k={q.data?.kaynaklar} alan="items[]" /></li>)}
        </ul>
      ))}
    </>
  );
}

export function ActionCard({ a, meta, k, alan }: { a: Action; meta: KurulMeta; k?: Kaynaklar; alan?: string }) {
  const qc = useQueryClient();
  const [note, setNote] = useState('');
  const mine = !!a.sahip && a.sahip.toLowerCase() === meta.me.username.toLowerCase();
  const canEdit = meta.me.canPrepare || (mine && meta.me.canAction);
  const save = useMutation({
    mutationFn: (b: { durum?: string; sonNot?: string }) => kurulApi.updateAction(a.id, b),
    onSuccess: () => {
      toast.success('Aksiyon güncellendi.');
      setNote('');
      qc.invalidateQueries({ queryKey: ['kurul'] });
    },
    onError: (e) => toast.error(errText(e, 'Aksiyon güncellenemedi.')),
  });
  return (
    <div className="glass-panel flex h-full flex-col gap-1.5 rounded-2xl p-3 shadow-glass-float">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <Pill tone={a.gecikti ? 'err' : a.durum === 'tamamlandi' ? 'ok' : a.durum === 'iptal' ? 'muted' : 'violet'}>{a.durumAdi}</Pill>
        <span className={`inline-flex items-center gap-0.5 text-[11.5px] font-bold ${a.gecikti ? 'text-red-700' : 'text-canvas-muted'}`}>
          {a.termin ? `${fmtDay(a.termin)} · ${fmtLeft(a.kalanGun)}` : 'termin yok'}
          {a.termin && k && alan && <SqlInfo k={k} alan={alan} label={`${a.eylem}: kalan gün`} className="ml-0.5" />}
        </span>
      </div>
      <p className="break-words text-[13px] font-bold leading-snug">{a.eylem}</p>
      <p className="text-[11.5px] text-canvas-muted">
        Sahip: {a.sahip ?? 'atanmadı'}{a.toplanti ? ` · ${a.toplanti} (${fmtDay(a.toplantiTarihi)})` : ''}
      </p>
      {a.karar && <p className="line-clamp-2 text-[11.5px] text-canvas-muted">Karar: {a.karar}</p>}
      {a.sonNot && <p className="rounded-lg bg-slate-50 px-2 py-1 text-[12px]">Son not: {a.sonNot}</p>}
      {canEdit && a.durum === 'acik' && (
        <div className="mt-1 flex flex-col gap-2">
          <input aria-label="Durum notu" className={field} value={note} placeholder="Durum notu" onChange={(e) => setNote(e.target.value)} />
          <div className="flex flex-wrap gap-2">
            <button type="button" className={btnGhost} disabled={!note.trim() || save.isPending} onClick={() => save.mutate({ sonNot: note })}>Notu kaydet</button>
            <button type="button" className={btnPrimary} disabled={save.isPending} onClick={() => save.mutate(note.trim() ? { durum: 'tamamlandi', sonNot: note } : { durum: 'tamamlandi' })}>Tamamlandı</button>
            {meta.me.canPrepare && <button type="button" className={btnGhost} disabled={save.isPending} onClick={() => save.mutate({ durum: 'iptal' })}>İptal</button>}
          </div>
        </div>
      )}
      {canEdit && a.durum !== 'acik' && (
        <button type="button" className={`${btnGhost} self-start`} disabled={save.isPending} onClick={() => save.mutate({ durum: 'acik' })}>Yeniden aç</button>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ Paketler */

function PackagesTab() {
  const q = useQuery({ queryKey: ['kurul', 'packages'], queryFn: kurulApi.packages, enabled: ENGINE_ENABLED });
  if (q.isLoading) return <Loading />;
  if (q.error) return <Note tone="err">{errText(q.error, 'Paketler okunamadı.')}</Note>;
  const items = q.data?.items ?? [];
  if (!items.length) return <Empty>Henüz kurul paketi yok. Paket, toplantı sayfasındaki «Paketi derle» ile hazırlanır.</Empty>;
  return (
    <ul className="grid grid-cols-1 gap-2 lg:grid-cols-2">
      {items.map((p) => (
        <li key={p.id}>
          <Link to={`/kurul/paket/${p.id}`} className="glass-panel flex min-h-11 items-center justify-between gap-2 rounded-2xl p-3 shadow-glass-float">
            <span className="min-w-0">
              <span className="block break-words text-[13.5px] font-extrabold">{p.toplanti} · v{p.surum}</span>
              <span className="block text-[11.5px] text-canvas-muted">
                {fmtDay(p.toplantiTarihi)} · derlendi {fmtTime(p.derleme)}{p.dondurma ? ` · donduruldu ${fmtTime(p.dondurma)}` : ''}
              </span>
            </span>
            <Pill tone={p.durum === 'taslak' ? 'warn' : 'ok'}>{p.durumAdi}</Pill>
          </Link>
        </li>
      ))}
    </ul>
  );
}

/* ------------------------------------------------------------------ Gösterge kataloğu */

function CatalogTab({ meta }: { meta: KurulMeta }) {
  const q = useQuery({ queryKey: ['kurul', 'indicators'], queryFn: kurulApi.indicators, enabled: ENGINE_ENABLED });
  const [edit, setEdit] = useState<IndicatorDef | null>(null);
  if (q.isLoading) return <Loading />;
  if (q.error) return <Note tone="err">{errText(q.error, 'Katalog okunamadı.')}</Note>;
  return (
    <>
      <Note tone="info">Rakam kaynağı (sağlayıcı) kodla bağlıdır ve burada değişmez. Eşik girilmeyen göstergenin rengi kaynak modülün kendi kuralından gelir ya da «eşik yok» kalır.</Note>
      <TableWrap>
        <thead>
          <tr><th className={th}>Gösterge</th><th className={th}>Bölüm</th><th className={th}>Kaynak</th><th className={th}><InfoLabel k={q.data?.kaynaklar} alan="items[]" label="Eşikler (sarı / kırmızı)">Eşik (sarı / kırmızı)</InfoLabel></th><th className={th}>Sahip</th><th className={th}>Durum</th><th className={th} /></tr>
        </thead>
        <tbody>
          {(q.data?.items ?? []).map((g) => (
            <tr key={g.kod} className="border-t border-slate-100">
              <td className={td}><div className="font-bold">{g.ad}</div><div className="font-mono text-[10.5px] text-canvas-muted">{g.kod} · v{g.surum}</div></td>
              <td className={td}>{g.bolumAdi}</td>
              <td className={td}>{g.saglayici ? meta.saglayicilar[g.saglayici] ?? g.saglayici : <ColorBadge durum="kaynak_yok" renk={null} />}</td>
              <td className={`${td} font-mono tabular-nums`}>{fmtValue(g.esikSari, g.birim)} / {fmtValue(g.esikKirmizi, g.birim)}<div className="font-sans text-[10.5px] text-canvas-muted">{g.yonAdi}</div></td>
              <td className={td}>{g.sahip ?? '—'}</td>
              <td className={td}>{g.aktif ? <Pill tone="ok">Panelde</Pill> : <Pill tone="muted">Gizli</Pill>}</td>
              <td className={td}><button type="button" className={btnGhost} onClick={() => setEdit(g)} aria-label={`${g.ad} düzenle`}><Pencil aria-hidden className="h-4 w-4" /></button></td>
            </tr>
          ))}
        </tbody>
      </TableWrap>
      {edit && <IndicatorEdit key={edit.kod} g={edit} meta={meta} onClose={() => setEdit(null)} />}
    </>
  );
}

function IndicatorEdit({ g, meta, onClose }: { g: IndicatorDef; meta: KurulMeta; onClose: () => void }) {
  const qc = useQueryClient();
  const [f, setF] = useState({
    ad: g.ad, aciklama: g.aciklama ?? '', yon: g.yon as string, sari: g.esikSari === null ? '' : String(g.esikSari).replace('.', ','),
    kirmizi: g.esikKirmizi === null ? '' : String(g.esikKirmizi).replace('.', ','), sahip: g.sahip ?? '', eposta: g.sahipEposta ?? '',
    sira: String(g.sira), aktif: g.aktif,
  });
  const save = useMutation({
    mutationFn: () => kurulApi.updateIndicator(g.kod, {
      ad: f.ad, aciklama: f.aciklama, yon: f.yon as IndicatorDef['yon'], esikSari: parseNum(f.sari), esikKirmizi: parseNum(f.kirmizi),
      sahip: f.sahip, sahipEposta: f.eposta, sira: Number(f.sira) || 0, aktif: f.aktif,
    }),
    onSuccess: () => {
      toast.success('Gösterge güncellendi; renk bir sonraki ölçümde yeni eşikle hesaplanır.');
      qc.invalidateQueries({ queryKey: ['kurul'] });
      onClose();
    },
    onError: (e) => toast.error(errText(e, 'Gösterge kaydedilemedi.')),
  });
  const unit = meta.birimler[g.birim] ?? '';
  return (
    <Sheet open modal onClose={onClose} title={g.ad} subtitle={`${g.bolumAdi} · birim ${unit}`}>
      <form className="flex flex-col gap-3" onSubmit={(e) => { e.preventDefault(); save.mutate(); }}>
        <TextInput id="gi-ad" label="Ad" value={f.ad} onChange={(v) => setF({ ...f, ad: v })} />
        <TextInput id="gi-ac" label="Açıklama" value={f.aciklama} onChange={(v) => setF({ ...f, aciklama: v })} area />
        <SelectInput id="gi-yon" label="Yön" value={f.yon} onChange={(v) => setF({ ...f, yon: v })} options={meta.yonler} />
        <div className="grid grid-cols-2 gap-2">
          <TextInput id="gi-s" label={`Sarı eşik (${unit})`} value={f.sari} onChange={(v) => setF({ ...f, sari: v })} />
          <TextInput id="gi-k" label={`Kırmızı eşik (${unit})`} value={f.kirmizi} onChange={(v) => setF({ ...f, kirmizi: v })} />
        </div>
        <TextInput id="gi-sahip" label="Sahip (portal hesabı)" value={f.sahip} onChange={(v) => setF({ ...f, sahip: v })} help="Bölüm yöneticisinin giriş adı; yorumu o yazar" />
        <TextInput id="gi-ep" label="Sahibin e-postası" value={f.eposta} onChange={(v) => setF({ ...f, eposta: v })} help="Yorum hatırlatması yalnız iç adrese gider" />
        <div className="grid grid-cols-2 gap-2">
          <TextInput id="gi-sira" label="Sıra" value={f.sira} onChange={(v) => setF({ ...f, sira: v })} help="Bölüm içindeki gösterim sırası; küçük sayı önce gelir" />
          <label className="mt-5 inline-flex min-h-11 items-center gap-2 text-[12.5px] font-bold">
            <input type="checkbox" className="h-4 w-4" checked={f.aktif} onChange={(e) => setF({ ...f, aktif: e.target.checked })} /> Panelde göster
          </label>
        </div>
        <div className="flex justify-end gap-2">
          <button type="button" className={btnGhost} onClick={onClose}>Vazgeç</button>
          <button type="submit" className={btnPrimary} disabled={save.isPending}>Kaydet</button>
        </div>
      </form>
    </Sheet>
  );
}

/* ------------------------------------------------------------------ Kurul üyeleri */

function MembersTab({ meta }: { meta: KurulMeta }) {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ['kurul', 'members'], queryFn: kurulApi.members, enabled: ENGINE_ENABLED });
  const [edit, setEdit] = useState<Member | 'new' | null>(null);
  const [removing, setRemoving] = useState<Member | null>(null);
  const del = useMutation({
    mutationFn: (m: Member) => kurulApi.deleteMember(m.id),
    onSuccess: () => {
      toast.success('Üye kaldırıldı (dağıtım kaydı olan üye pasife alınır).');
      setRemoving(null);
      qc.invalidateQueries({ queryKey: ['kurul', 'members'] });
    },
    onError: (e) => toast.error(errText(e, 'Üye kaldırılamadı.')),
  });
  if (q.isLoading) return <Loading />;
  if (q.error) return <Note tone="err">{errText(q.error, 'Üyeler okunamadı.')}</Note>;
  const items = q.data?.items ?? [];
  return (
    <>
      <Note tone="info">Portal girişi yalnız şirket hesabıyladır. Hesabı olan üye paketi portaldan açar; olmayan üyeye dondurulmuş paketin PDF'ini siz iletirsiniz — portal kimseye e-posta göndermez.</Note>
      {meta.me.canPrepare && (
        <div className="px-1"><button type="button" className={btnPrimary} onClick={() => setEdit('new')}><UserPlus aria-hidden className="h-4 w-4" /> Üye ekle</button></div>
      )}
      {items.length === 0 ? <Empty>Kurul üyesi kaydı yok.</Empty> : (
        <ul className="grid grid-cols-1 gap-2 lg:grid-cols-2">
          {items.map((m) => (
            <li key={m.id} className="glass-panel flex items-center justify-between gap-2 rounded-2xl p-3 shadow-glass-float">
              <span className="min-w-0">
                <span className="block break-words text-[13.5px] font-bold">{m.ad}{!m.aktif && ' (pasif)'}</span>
                <span className="block text-[11.5px] text-canvas-muted">{m.kurulAdi}{m.gorev ? ` · ${m.gorev}` : ''} · {m.adHesabi ? `portal hesabı ${m.adHesabi}` : 'portal hesabı yok (PDF)'}</span>
              </span>
              {meta.me.canPrepare && (
                <span className="flex shrink-0 gap-1">
                  <button type="button" className={btnGhost} aria-label={`${m.ad} düzenle`} onClick={() => setEdit(m)}><Pencil aria-hidden className="h-4 w-4" /></button>
                  <button type="button" className={btnGhost} aria-label={`${m.ad} kaldır`} onClick={() => setRemoving(m)}><Trash2 aria-hidden className="h-4 w-4" /></button>
                </span>
              )}
            </li>
          ))}
        </ul>
      )}
      {edit && <MemberEdit key={edit === 'new' ? 'new' : edit.id} m={edit === 'new' ? null : edit} meta={meta} onClose={() => setEdit(null)} />}
      <AskSheet open={!!removing} title="Üyeyi kaldır" message={`${removing?.ad ?? ''} kurul listesinden kaldırılsın mı?`} confirm="Kaldır" danger
        busy={del.isPending} onClose={() => setRemoving(null)} onConfirm={() => removing && del.mutate(removing)} />
    </>
  );
}

function MemberEdit({ m, meta, onClose }: { m: Member | null; meta: KurulMeta; onClose: () => void }) {
  const qc = useQueryClient();
  const [f, setF] = useState({ ad: m?.ad ?? '', eposta: m?.eposta ?? '', adHesabi: m?.adHesabi ?? '', kurul: m?.kurul ?? 'yonetim', gorev: m?.gorev ?? '', aktif: m?.aktif ?? true });
  const save = useMutation({
    mutationFn: () => kurulApi.saveMember(m?.id ?? null, { ...f, kurul: f.kurul as Member['kurul'] }),
    onSuccess: () => {
      toast.success('Üye kaydedildi.');
      qc.invalidateQueries({ queryKey: ['kurul', 'members'] });
      onClose();
    },
    onError: (e) => toast.error(errText(e, 'Üye kaydedilemedi.')),
  });
  return (
    <Sheet open modal onClose={onClose} title={m ? 'Üyeyi düzenle' : 'Üye ekle'}>
      <form className="flex flex-col gap-3" onSubmit={(e) => { e.preventDefault(); save.mutate(); }}>
        <TextInput id="u-ad" label="Ad soyad" value={f.ad} onChange={(v) => setF({ ...f, ad: v })} />
        <SelectInput id="u-kurul" label="Kurul" value={f.kurul} onChange={(v) => setF({ ...f, kurul: v as Member['kurul'] })} options={meta.toplantiTurleri} />
        <TextInput id="u-gorev" label="Görev" value={f.gorev} onChange={(v) => setF({ ...f, gorev: v })} placeholder="Başkan, üye, bağımsız üye…" />
        <TextInput id="u-hesap" label="Portal hesabı" value={f.adHesabi} onChange={(v) => setF({ ...f, adHesabi: v })} help="Şirket hesabı varsa giriş adı; yoksa boş" />
        <TextInput id="u-ep" label="E-posta" value={f.eposta} onChange={(v) => setF({ ...f, eposta: v })} />
        {m && (
          <label className="inline-flex min-h-11 items-center gap-2 text-[12.5px] font-bold">
            <input type="checkbox" className="h-4 w-4" checked={f.aktif} onChange={(e) => setF({ ...f, aktif: e.target.checked })} /> Etkin
          </label>
        )}
        <div className="flex justify-end gap-2">
          <button type="button" className={btnGhost} onClick={onClose}>Vazgeç</button>
          <button type="submit" className={btnPrimary} disabled={!f.ad.trim() || save.isPending}><Plus aria-hidden className="h-4 w-4" /> Kaydet</button>
        </div>
      </form>
    </Sheet>
  );
}

