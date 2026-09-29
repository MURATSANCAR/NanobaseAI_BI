import { useCallback, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Copy, Loader2, Plus, Sparkles } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import SqlInfo, { InfoLabel } from '../components/SqlInfo';
import type { Kaynaklar } from '../components/sqlInfo';
import { Note, Pill, TableWrap, btnGhost, btnPrimary, errText, field, label as labelCls, td, th } from '../admin/ui';
import { Kpi, KpiRow, Panel, useDebounced } from '../editorial/kit';
import Sheet from '../editorial/studio/reader/Sheet';
import {
  PROGRAM_TONE, SEGMENT_TONE, fmtDay, fmtInt, okurApi,
  type EventGroup, type OkurMeta, type Program, type ProgramInput, type ProgramState, type ProgramType,
} from './api';
import { AskSheet, OkurFrame, Tabs } from './parts';
import { EmptyHint } from '../components/Explain';

/** M37 «Topluluk programları»: okuma kulübü, imza günü, anket ve çevrim içi etkinlik takvimi, Zeki AI duyuru taslağı
 *  (gönderilmez; kopyalanıp mevcut kanaldan insan gönderir) ve CRM'deki geçmiş etkinliklerin katılım/satış özeti. */

const TABS = [
  { key: 'takvim', label: 'Takvim' },
  { key: 'gecmis', label: 'Geçmiş etkinlikler' },
] as const;
type Tab = (typeof TABS)[number]['key'];

export default function ProgramsScreen() {
  const [params, setParams] = useSearchParams();
  const meta = useQuery({ queryKey: ['okur', 'meta'], queryFn: okurApi.meta, enabled: ENGINE_ENABLED, staleTime: 60_000 });
  const tab: Tab = (TABS.find((t) => t.key === params.get('sekme'))?.key ?? 'takvim') as Tab;
  const [editing, setEditing] = useState<Program | 'new' | null>(null);
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
  const m = meta.data;
  return (
    <OkurFrame
      crumb="Topluluk programları"
      title="Topluluk programları"
      lead="Okuma kulübü, imza günü, anket ve çevrim içi etkinlik planı. Zeki AI duyuru taslağı hazırlar; portal okura ileti göndermez, metin kopyalanıp mevcut kanaldan gönderilir. Geçmiş etkinliklerin katılım ve satılan kitap adedi CRM'den gelir."
      source="Kaynak: portal kaydı · CRM etkinlik"
      aside={m?.me.canProgram && tab === 'takvim' ? (
        <div className="flex justify-start lg:justify-end">
          <button type="button" className={btnPrimary} onClick={() => setEditing('new')}>
            <Plus aria-hidden className="h-4 w-4" />
            Yeni program ekle
          </button>
        </div>
      ) : undefined}
    >
      {!ENGINE_ENABLED && <Note tone="warn">Bu ekranın veri bağlantısı kurulmamış; liste açılamaz. Lütfen sistem yöneticinize bildirin.</Note>}
      {meta.error && <Note tone="err">{errText(meta.error, 'Ekran bilgisi okunamadı.')}</Note>}
      <Tabs tabs={TABS} value={tab} onChange={(t) => update({ sekme: t === 'takvim' ? null : t })} />
      {m && tab === 'takvim' && <Calendar meta={m} kapsam={params.get('kapsam') ?? 'yaklasan'} setKapsam={(k) => update({ kapsam: k === 'yaklasan' ? null : k })} onOpen={setEditing} />}
      {tab === 'gecmis' && <PastEvents yil={Number(params.get('yil')) || 0} setYil={(y) => update({ yil: y ? String(y) : null })} />}
      {m && editing && <ProgramSheet meta={m} program={editing === 'new' ? null : editing} onClose={() => setEditing(null)} />}
    </OkurFrame>
  );
}

const today = () => new Date().toISOString().slice(0, 10);

function Calendar({ meta, kapsam, setKapsam, onOpen }: { meta: OkurMeta; kapsam: string; setKapsam: (k: string) => void; onOpen: (p: Program) => void }) {
  const range = kapsam === 'yaklasan' ? { from: today() } : kapsam === 'gecmis' ? { to: today() } : {};
  const list = useQuery({ queryKey: ['okur', 'programs', kapsam], queryFn: () => okurApi.programs(range), enabled: ENGINE_ENABLED });
  const items = kapsam === 'gecmis' ? [...(list.data?.items ?? [])].reverse() : list.data?.items ?? [];
  const groups = new Map<string, Program[]>();
  for (const p of items) {
    const k = p.tarih ? p.tarih.slice(0, 7) : 'Tarihsiz';
    groups.set(k, [...(groups.get(k) ?? []), p]);
  }
  const monthName = (k: string) =>
    k === 'Tarihsiz' ? k : new Date(`${k}-01T12:00:00`).toLocaleDateString('tr-TR', { month: 'long', year: 'numeric' });
  return (
    <Panel>
      <div className="mb-3 flex flex-wrap gap-1.5">
        {[['yaklasan', 'Yaklaşan'], ['gecmis', 'Geçmiş'], ['hepsi', 'Hepsi']].map(([k, v]) => (
          <button key={k} type="button" onClick={() => setKapsam(k)} aria-pressed={kapsam === k}
            className={`min-h-11 rounded-xl px-3 text-[12px] font-extrabold transition-transform duration-150 ease-out active:scale-[0.97] sm:min-h-8 ${kapsam === k ? 'bg-canvas-violet text-white' : 'bg-slate-100'}`}>
            {v}
          </button>
        ))}
        {list.data && (
          <span className="ml-auto inline-flex items-center gap-1 self-center text-[11.5px] text-canvas-muted">
            {fmtInt(list.data.total)} program<SqlInfo k={list.data.kaynaklar} alan="items" label="Program takvimi" />
          </span>
        )}
      </div>
      {list.isLoading && <div className="py-8 text-center text-[12px] text-canvas-muted">Yükleniyor…</div>}
      {list.error && <Note tone="err">{errText(list.error, 'Programlar okunamadı.')}</Note>}
      {list.data && !items.length && (
        <EmptyHint
          title={kapsam === 'yaklasan' ? 'Yaklaşan program yok' : 'Bu aralıkta program yok'}
          why={meta.me.canProgram ? 'Okuma kulübü, imza günü, anket ya da çevrim içi etkinliği «Yeni program ekle» ile takvime alın.' : 'Başka bir aralık seçin.'}
        />
      )}
      <div className="flex flex-col gap-4">
        {[...groups.entries()].map(([k, ps]) => (
          <section key={k}>
            <h3 className="mb-1.5 text-[12px] font-extrabold uppercase tracking-wide text-canvas-muted">{monthName(k)}</h3>
            <div className="flex flex-col gap-1.5">
              {ps.map((p) => (
                <button key={p.id} type="button" onClick={() => onOpen(p)}
                  className="grid grid-cols-[64px_minmax(0,1fr)] gap-3 rounded-2xl border border-slate-100 bg-white/80 p-3 text-left transition-colors duration-150 hover:border-canvas-violet/40">
                  <div className="text-center">
                    <div className="font-mono text-[20px] font-bold leading-none tabular-nums">{p.tarih ? p.tarih.slice(8, 10) : '—'}</div>
                    <div className="mt-0.5 text-[11px] font-bold text-canvas-muted">{p.saat ?? ''}</div>
                  </div>
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-1.5">
                      <Pill tone={PROGRAM_TONE[p.durum]}>{p.durumAdi}</Pill>
                      <span className="text-[11px] font-semibold text-canvas-muted">{p.turAdi}{p.sehir ? ` · ${p.sehir}` : ''}</span>
                      {p.segment && <Pill tone={SEGMENT_TONE[p.segment.durum]}>{p.segment.onayli ? 'Onaylı segment' : `Segment: ${p.segment.durumAdi}`}</Pill>}
                      {p.duyuruTaslagi && <Pill tone="violet">Duyuru taslağı var</Pill>}
                    </div>
                    <div className="mt-1 break-words text-[13.5px] font-extrabold leading-snug">{p.ad}</div>
                    <div className="break-words text-[12px] text-canvas-muted">{[p.kitapAdi, p.yazarAdi].filter(Boolean).join(' · ') || '—'}</div>
                  </div>
                </button>
              ))}
            </div>
          </section>
        ))}
      </div>
    </Panel>
  );
}

type Form = Record<'tur' | 'ad' | 'durum' | 'tarih' | 'saat' | 'sehir' | 'yer' | 'yazarAdi' | 'sorumlu' | 'notlar' | 'katilimci' | 'segmentId' | 'kitapId' | 'kitapAdi' | 'duyuruTaslagi', string>;

const EMPTY: Form = {
  tur: 'okuma_kulubu', ad: '', durum: 'taslak', tarih: '', saat: '', sehir: '', yer: '', yazarAdi: '', sorumlu: '', notlar: '', katilimci: '', segmentId: '', kitapId: '', kitapAdi: '', duyuruTaslagi: '',
};

function ProgramSheet({ meta, program, onClose }: { meta: OkurMeta; program: Program | null; onClose: () => void }) {
  const qc = useQueryClient();
  const [f, setF] = useState<Form>(() => program ? {
    tur: program.tur, ad: program.ad, durum: program.durum, tarih: program.tarih ?? '', saat: program.saat ?? '', sehir: program.sehir ?? '', yer: program.yer ?? '',
    yazarAdi: program.yazarAdi ?? '', sorumlu: program.sorumlu ?? '', notlar: program.notlar ?? '', katilimci: program.katilimci !== null ? String(program.katilimci) : '',
    segmentId: program.segmentId ?? '', kitapId: program.kitapId ?? '', kitapAdi: program.kitapAdi ?? '', duyuruTaslagi: program.duyuruTaslagi ?? '',
  } : EMPTY);
  const [id, setId] = useState<string | null>(program?.id ?? null);
  const [savedDraft, setSavedDraft] = useState(program?.duyuruTaslagi ?? '');
  const [bookQ, setBookQ] = useState('');
  const [ask, setAsk] = useState(false);
  const dq = useDebounced(bookQ, 300);
  const books = useQuery({ queryKey: ['okur', 'books', dq], queryFn: () => okurApi.books(dq), enabled: ENGINE_ENABLED && dq.trim().length >= 2 });
  const segs = useQuery({ queryKey: ['okur', 'segments', ''], queryFn: () => okurApi.segments(''), enabled: ENGINE_ENABLED });
  const set = (k: keyof Form) => (v: string) => setF((x) => ({ ...x, [k]: v }));
  const ro = !meta.me.canProgram;
  const body = (): ProgramInput => ({
    tur: f.tur as ProgramType, ad: f.ad.trim(), durum: f.durum as ProgramState, tarih: f.tarih || null, saat: f.saat || null, sehir: f.sehir.trim(),
    yer: f.yer.trim(), yazarAdi: f.yazarAdi.trim(), sorumlu: f.sorumlu.trim(), notlar: f.notlar.trim(), segmentId: f.segmentId || null,
    kitapId: f.kitapId || null, kitapAdi: f.kitapAdi || null, katilimci: f.katilimci.trim() ? Number(f.katilimci) : null,
    ...(id && f.duyuruTaslagi !== savedDraft ? { duyuruTaslagi: f.duyuruTaslagi } : {}),
  });
  const save = useMutation({
    mutationFn: () => (id ? okurApi.updateProgram(id, body()) : okurApi.createProgram(body())),
    onSuccess: (p) => {
      qc.invalidateQueries({ queryKey: ['okur'] });
      toast.success(id ? 'Program kaydedildi.' : 'Program kaydedildi; şimdi Zeki AI duyuru taslağı alabilirsiniz.');
      setId(p.id);
      setSavedDraft(p.duyuruTaslagi ?? '');
    },
    onError: (e) => toast.error(errText(e, 'Kaydedilemedi.') ?? ''),
  });
  const draft = useMutation({
    mutationFn: () => okurApi.draftProgram(id as string),
    onSuccess: (p) => {
      qc.invalidateQueries({ queryKey: ['okur'] });
      setF((x) => ({ ...x, duyuruTaslagi: p.duyuruTaslagi ?? '' }));
      setSavedDraft(p.duyuruTaslagi ?? '');
      toast.success('Duyuru taslağı hazır; gözden geçirip düzenleyin.');
    },
    onError: (e) => toast.error(errText(e, 'Taslak üretilemedi.') ?? ''),
  });
  const del = useMutation({
    mutationFn: () => okurApi.deleteProgram(id as string),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['okur'] }); toast.success('Program silindi.'); onClose(); },
    onError: (e) => toast.error(errText(e, 'Silinemedi.') ?? ''),
  });
  const bad = !f.ad.trim() || (f.katilimci.trim() !== '' && !(Number(f.katilimci) >= 0));
  const selSeg = segs.data?.items.find((s) => s.id === f.segmentId);
  const inp = (k: keyof Form, lbl: string, type = 'text', placeholder = '') => (
    <label className="flex flex-col gap-1">
      <span className={labelCls}>{lbl}</span>
      <input className={field} type={type} value={f[k]} disabled={ro} placeholder={placeholder} onChange={(e) => set(k)(e.target.value)} />
    </label>
  );
  return (
    <Sheet open modal wide onClose={onClose} title={program ? program.ad : 'Yeni program'} subtitle={program ? `${program.turAdi} · ${program.durumAdi}` : 'Program kaydedildikten sonra Zeki AI duyuru taslağı alınabilir.'}>
      <div className="flex flex-col gap-3 text-[13px]">
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Tür *</span>
            <select className={field} value={f.tur} disabled={ro} onChange={(e) => set('tur')(e.target.value)}>
              {Object.entries(meta.programTurleri).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
          </label>
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Durum</span>
            <select className={field} value={f.durum} disabled={ro} onChange={(e) => set('durum')(e.target.value)}>
              {Object.entries(meta.programDurumlari).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
          </label>
        </div>
        {inp('ad', 'Program adı *', 'text', 'Örn. Kasım okuma kulübü')}
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {inp('tarih', 'Tarih', 'date')}
          {inp('saat', 'Saat', 'time')}
          {inp('sehir', 'Şehir')}
          {inp('yer', 'Yer')}
        </div>
        <div className="rounded-2xl border border-slate-100 bg-white/70 p-3">
          <div className={labelCls}>Kitap (CRM kitap kartı)</div>
          {f.kitapAdi ? (
            <div className="mt-1 flex flex-wrap items-center gap-2">
              <span className="font-bold">{f.kitapAdi}</span>
              {!ro && <button type="button" className={btnGhost} onClick={() => setF((x) => ({ ...x, kitapId: '', kitapAdi: '' }))}>Kaldır</button>}
            </div>
          ) : !ro ? (
            <>
              <input className={`${field} mt-1`} value={bookQ} onChange={(e) => setBookQ(e.target.value)} placeholder="Kitap adı, yazar ya da stok kodu" />
              {books.isFetching && <p className="mt-1 text-[12px] text-canvas-muted">Aranıyor…</p>}
              {books.error && <Note tone="err">{errText(books.error, 'Kitap aranamadı.')}</Note>}
              <div className="mt-1 flex max-h-56 flex-col gap-1 overflow-y-auto">
                {books.data?.items.map((b) => (
                  <button key={b.id} type="button" className="rounded-xl bg-slate-50 px-2.5 py-2 text-left text-[12.5px] transition-colors duration-150 hover:bg-slate-100"
                    onClick={() => { setF((x) => ({ ...x, kitapId: b.id, kitapAdi: b.ad ?? '', yazarAdi: x.yazarAdi || b.yazar || '' })); setBookQ(''); }}>
                    <span className="font-bold">{b.ad}</span>
                    <span className="text-canvas-muted">{b.yazar ? ` · ${b.yazar}` : ''}{b.stokKodu ? ` · ${b.stokKodu}` : ''}</span>
                  </button>
                ))}
                {books.data && dq.trim().length >= 2 && !books.data.items.length && <p className="text-[12px] text-canvas-muted">Aramaya uyan kitap yok; başka bir ad, yazar ya da stok kodu deneyin.</p>}
              </div>
            </>
          ) : <p className="mt-1 text-[12px] text-canvas-muted">—</p>}
        </div>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          {inp('yazarAdi', 'Yazar')}
          {inp('sorumlu', 'Sorumlu')}
        </div>
        <label className="flex flex-col gap-1">
          <span className={labelCls}>Hedef segment</span>
          <select className={field} value={f.segmentId} disabled={ro} onChange={(e) => set('segmentId')(e.target.value)}>
            <option value="">Yok</option>
            {segs.data?.items.map((s) => <option key={s.id} value={s.id}>{s.ad} — {s.durumAdi}</option>)}
          </select>
          {selSeg && selSeg.durum !== 'onaylandi' && <span className="text-[11.5px] text-amber-800">Segment onaylı değil; duyuru bu kitleye onay gelmeden gönderilmemeli.</span>}
        </label>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          {inp('katilimci', 'Gerçekleşen katılımcı', 'number')}
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Not</span>
            <textarea className={`${field} min-h-[44px]`} value={f.notlar} disabled={ro} onChange={(e) => set('notlar')(e.target.value)} />
          </label>
        </div>
        <div className="rounded-2xl border border-slate-100 bg-white/70 p-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span className={labelCls}>Duyuru taslağı {program?.duyuruKaynak === 'zeki' ? '· Zeki AI' : ''}</span>
            <div className="flex flex-wrap gap-2">
              {f.duyuruTaslagi && (
                <button type="button" className={btnGhost} onClick={() => navigator.clipboard?.writeText(f.duyuruTaslagi).then(() => toast.success('Kopyalandı.'), () => toast.error('Kopyalanamadı.'))}>
                  <Copy aria-hidden className="h-4 w-4" />
                  Kopyala
                </button>
              )}
              {!ro && meta.modelVar && (
                <button type="button" className={btnGhost} disabled={!id || draft.isPending} onClick={() => draft.mutate()} title={id ? '' : 'Önce programı kaydedin'}>
                  {draft.isPending ? <Loader2 aria-hidden className="h-4 w-4 animate-spin" /> : <Sparkles aria-hidden className="h-4 w-4" />}
                  Zeki AI taslağı
                </button>
              )}
            </div>
          </div>
          <textarea className={`${field} mt-2 min-h-[140px]`} value={f.duyuruTaslagi} disabled={ro || !id} onChange={(e) => set('duyuruTaslagi')(e.target.value)}
            placeholder={id ? 'Taslak yok' : 'Program kaydedilince yazılır'} />
          <p className="mt-1 text-[11.5px] text-canvas-muted">Portal bu metni göndermez. Onaylı segmentin kanalından insan gönderir.</p>
        </div>
        {!ro && (
          <div className="flex flex-wrap justify-end gap-2">
            {id && <button type="button" className={btnGhost} disabled={del.isPending} onClick={() => setAsk(true)}>Programı sil</button>}
            <button type="button" className={btnPrimary} disabled={bad || save.isPending} onClick={() => save.mutate()}>
              {save.isPending && <Loader2 aria-hidden className="h-4 w-4 animate-spin" />}
              Kaydet
            </button>
          </div>
        )}
      </div>
      <AskSheet open={ask} title="Programı sil" message="Program ve duyuru taslağı silinir; silme kayda geçer." confirm="Sil" danger busy={del.isPending}
        onClose={() => setAsk(false)} onConfirm={() => del.mutate()} />
    </Sheet>
  );
}

function GroupTable({ title, rows, first, k, alan }: { title: string; rows: EventGroup[]; first: string; k?: Kaynaklar; alan: string }) {
  return (
    <Panel>
      <h2 className="mb-2 flex items-center gap-1 text-[15px] font-extrabold tracking-tight">{title}<SqlInfo k={k} alan={alan} label={title} /></h2>
      <TableWrap>
        <thead>
          <tr>
            <th className={th}>{first}</th>
            <th className={`${th} text-right`}><InfoLabel k={k} alan={alan}>Etkinlik</InfoLabel></th>
            <th className={`${th} text-right`}><InfoLabel k={k} alan={alan}>Katılımcı</InfoLabel></th>
            <th className={`${th} text-right`}><InfoLabel k={k} alan={alan}>Satılan kitap</InfoLabel></th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.ad} className="border-t border-slate-100">
              <td className={`${td} font-bold`}>{r.ad}</td>
              <td className={`${td} text-right font-mono tabular-nums`}>{fmtInt(r.etkinlik)}</td>
              <td className={`${td} text-right font-mono tabular-nums`}>{fmtInt(r.katilimci)}</td>
              <td className={`${td} text-right font-mono tabular-nums`}>{fmtInt(r.satilan)}</td>
            </tr>
          ))}
          {!rows.length && <tr><td className={`${td} text-canvas-muted`} colSpan={4}>Tamamlanan etkinlik yok.</td></tr>}
        </tbody>
      </TableWrap>
    </Panel>
  );
}

function PastEvents({ yil, setYil }: { yil: number; setYil: (y: number) => void }) {
  const ev = useQuery({ queryKey: ['okur', 'events', yil], queryFn: () => okurApi.events(yil || undefined), enabled: ENGINE_ENABLED, staleTime: 5 * 60_000 });
  const [show, setShow] = useState(50);
  const d = ev.data;
  return (
    <>
      {ev.isLoading && <div className="py-8 text-center text-[12px] text-canvas-muted">CRM etkinlikleri okunuyor…</div>}
      {ev.error && <Note tone="err">{errText(ev.error, 'CRM etkinlikleri okunamadı.')}</Note>}
      {d && (
        <>
          <div className="flex flex-wrap items-end gap-3">
            <label className="flex flex-col gap-1">
              <span className={labelCls}>Yıl</span>
              <select className={field} value={d.yil} onChange={(e) => setYil(Number(e.target.value))}>
                {d.yillar.map((y) => <option key={y} value={y}>{y}</option>)}
              </select>
            </label>
            <p className="max-w-[70ch] pb-1 text-[11.5px] leading-snug text-canvas-muted">
              Başlangıç tarihine göre. {d.ziyaretHaric ? 'Okul ve cari ziyareti (satış ziyareti) kayıtları dışarıda. ' : ''}
              {d.tipSuzgeci.length ? `Yalnız şu tipler: ${d.tipSuzgeci.join(', ')}. ` : 'Bütün etkinlik tipleri. '}
              Katılımcı ve satılan adet yalnız «Tamamlandı» kayıtlarda toplanır.
            </p>
          </div>
          <KpiRow>
            <Kpi label="Etkinlik" value={fmtInt(d.toplam)} help={Object.entries(d.durumlar).map(([k, v]) => `${k} ${fmtInt(v)}`).join(' · ') || '—'} info={<SqlInfo k={d.kaynaklar} alan="toplam" label="Etkinlik" />} />
            <Kpi label="Tamamlanan" value={fmtInt(d.tamamlanan)} help="CRM durumu Tamamlandı" info={<SqlInfo k={d.kaynaklar} alan="tamamlanan" label="Tamamlanan" />} />
            <Kpi label="Katılımcı" value={fmtInt(d.katilimci)} help={d.katilimciBos ? `${fmtInt(d.katilimciBos)} etkinlikte katılımcı girilmemiş` : 'Tamamlananlarda'} info={<SqlInfo k={d.kaynaklar} alan="katilimci" label="Katılımcı" />} />
            <Kpi label="Satılan kitap" value={fmtInt(d.satilan)} help="Etkinlik kaydındaki adet" info={<SqlInfo k={d.kaynaklar} alan="satilan" label="Satılan kitap" />} />
          </KpiRow>
          <div className="grid grid-cols-1 gap-3 lg:grid-cols-3 lg:gap-4">
            <GroupTable title="Etkinlik tipine göre" rows={d.tipler} first="Tip" k={d.kaynaklar} alan="tipler" />
            <GroupTable title="İle göre" rows={d.iller} first="İl" k={d.kaynaklar} alan="iller" />
            <GroupTable title="Yazara göre" rows={d.yazarlar} first="Yazar" k={d.kaynaklar} alan="yazarlar" />
          </div>
          <Panel>
            <h2 className="mb-2 flex items-center gap-1 text-[15px] font-extrabold tracking-tight">Etkinlikler ({fmtInt(d.etkinlikler.length)})<SqlInfo k={d.kaynaklar} alan="etkinlikler" label="Etkinlikler" /></h2>
            <TableWrap>
              <thead>
                <tr>
                  <th className={th}>Tarih</th>
                  <th className={th}>Etkinlik</th>
                  <th className={th}>Tip</th>
                  <th className={th}>İl</th>
                  <th className={th}>Yazar · kitap</th>
                  <th className={th}>Durum</th>
                  <th className={`${th} text-right`}><InfoLabel k={d.kaynaklar} alan="etkinlikler">Katılımcı</InfoLabel></th>
                  <th className={`${th} text-right`}><InfoLabel k={d.kaynaklar} alan="etkinlikler">Satılan</InfoLabel></th>
                </tr>
              </thead>
              <tbody>
                {d.etkinlikler.slice(0, show).map((e) => (
                  <tr key={e.id} className="border-t border-slate-100">
                    <td className={`${td} whitespace-nowrap font-mono tabular-nums`}>{fmtDay(e.tarih)}</td>
                    <td className={`${td} font-bold`}>{e.ad ?? '—'}</td>
                    <td className={td}>{e.tip}</td>
                    <td className={td}>{e.il ?? '—'}</td>
                    <td className={td}>{[e.yazar, e.kitap].filter(Boolean).join(' · ') || '—'}</td>
                    <td className={td}>{e.durumAdi ?? '—'}</td>
                    <td className={`${td} text-right font-mono tabular-nums`}>{fmtInt(e.katilimci)}</td>
                    <td className={`${td} text-right font-mono tabular-nums`}>{fmtInt(e.satilan)}</td>
                  </tr>
                ))}
              </tbody>
            </TableWrap>
            {d.etkinlikler.length > show && (
              <div className="mt-2 flex justify-center">
                <button type="button" className={btnGhost} onClick={() => setShow((n) => n + 100)}>
                  Devamını göster ({fmtInt(d.etkinlikler.length - show)} kaldı)
                </button>
              </div>
            )}
          </Panel>
        </>
      )}
    </>
  );
}
