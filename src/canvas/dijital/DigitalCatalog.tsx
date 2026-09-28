import { useCallback, useState } from 'react';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Loader2, RefreshCw, Search } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import { Note, Pill, btnGhost, errText, field, fmtDate, label as labelCls } from '../admin/ui';
import { Kpi, KpiRow, Panel, Pager, useDebounced } from '../editorial/kit';
import { dijitalApi, fmtInt, type Meta, type Overview, type RiskRow, type TitleRow } from './api';
import { Chips, DigitalFrame, ListHead, RightPill, Tabs } from './parts';
import SqlInfo, { InfoLabel } from '../components/SqlInfo';
import DigitalTitleDrawer from './DigitalTitleDrawer';
import PlatformsTab from './PlatformsTab';

/** M36 Dijital katalog: kitap başına hak (e-kitap / sesli), e-ISBN, e-kitap dosyası, platform durumu; hak riski ve telif
 *  kararı; CRM'e işlenecekler; platform tanımları. Sekme ve süzgeçler adres çubuğunda; kitap ayrıntısı /dijital-yayin/kitap/:id. */

const TABS = [
  { key: 'katalog', label: 'Katalog' },
  { key: 'risk', label: 'Hak riski' },
  { key: 'crm', label: "CRM'e işlenecek" },
  { key: 'platformlar', label: 'Platformlar' },
] as const;
type Tab = (typeof TABS)[number]['key'];

const DURUM = [
  { key: '', label: 'Hepsi' },
  { key: 'dijitalde', label: 'Dijitalde (e-kitap)' },
  { key: 'dijitalde-yok', label: 'Hakkı var, dijitalde yok' },
  { key: 'firsat', label: 'Fırsat listesinde' },
  { key: 'risk', label: 'Hak riski' },
  { key: 'epub-hazir', label: 'Stüdyoda e-kitap hazır' },
  { key: 'yeni-baski', label: 'Yeni baskı / kapak değişti' },
  { key: 'crm-islenecek', label: "CRM'e işlenecek alanı var" },
];

export default function DigitalCatalog() {
  const [params, setParams] = useSearchParams();
  const { id } = useParams();
  const nav = useNavigate();
  const qc = useQueryClient();
  const meta = useQuery({ queryKey: ['dijital', 'meta'], queryFn: dijitalApi.meta, enabled: ENGINE_ENABLED, staleTime: 30_000 });
  const ov = useQuery({ queryKey: ['dijital', 'overview'], queryFn: dijitalApi.overview, enabled: ENGINE_ENABLED });
  const tab: Tab = (TABS.find((t) => t.key === params.get('sekme'))?.key ?? 'katalog') as Tab;
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
  const refresh = useMutation({
    mutationFn: dijitalApi.refresh,
    onSuccess: (r) => {
      toast.success(r.started ? 'Okuma başladı; birkaç dakika sürebilir.' : 'Okuma zaten sürüyor.');
      qc.invalidateQueries({ queryKey: ['dijital', 'meta'] });
    },
    onError: (e) => toast.error(errText(e, 'Başlatılamadı.') ?? ''),
  });
  const me = meta.data?.me;
  const k = ov.data?.kpi;
  const src = ov.data?.kaynaklar;
  const okuma = meta.data?.okuma;
  return (
    <DigitalFrame
      crumb="Dijital yayın"
      me={me}
      title="Dijital yayın ve e-kitap"
      lead="Her kitabın e-kitap ve sesli kitap hakkı (CRM sözleşmeleri), e-ISBN, e-kitap dosyası ve platform durumu tek satırda. Platform durumu yalnız sizin girdiğiniz ya da onaylı rapordan gelen bilgidir; portal hiçbir platforma, CRM'e ya da Logo'ya bir şey göndermez."
      aside={
        me?.canWrite ? (
          <div className="flex justify-start lg:justify-end">
            <button type="button" className={btnGhost} disabled={refresh.isPending || okuma?.running} onClick={() => refresh.mutate()}>
              {refresh.isPending || okuma?.running ? <Loader2 aria-hidden className="h-4 w-4 animate-spin" /> : <RefreshCw aria-hidden className="h-4 w-4" />}
              {okuma?.running ? 'Okunuyor…' : 'Yeniden oku'}
            </button>
          </div>
        ) : undefined
      }
    >
      {!ENGINE_ENABLED && <Note tone="warn">Bu kurulumda veri bağlantısı tanımlı değil.</Note>}
      {(meta.error || ov.error) && <Note tone="err">{errText(meta.error || ov.error, 'Ekran bilgisi okunamadı.')}</Note>}
      <ReadingNote ov={ov.data} />
      <KpiRow>
        <Kpi label="Dijitalde" value={fmtInt(k?.dijitalde)} help={`${fmtInt(k?.kitap)} kitaptan; e-kitap stok kodu ya da platformda`}
          active={params.get('durum') === 'dijitalde'} onClick={() => update({ sekme: null, durum: 'dijitalde' })}
          info={<SqlInfo k={src} alan="kart.dijitalde" label="Dijitalde" />} />
        <Kpi label="Hakkı var, dijitalde yok" value={fmtInt(k?.hakliDijitalYok)} help={`${fmtInt(k?.firsat)} tanesi fırsat listesinde`}
          active={params.get('durum') === 'dijitalde-yok'} onClick={() => update({ sekme: null, durum: 'dijitalde-yok' })}
          info={<SqlInfo k={src} alan="kart.hakliDijitalYok" label="Hakkı var, dijitalde yok" />} />
        <Kpi label="Hak riski" value={fmtInt(k?.hakRiski)} help={`Dijitalde ama hakkı eksik/yok/incele · ${fmtInt(k?.incele)} kitap karar bekliyor`}
          active={tab === 'risk'} onClick={() => update({ sekme: 'risk' })}
          info={<SqlInfo k={src} alan="kart.hakRiski" label="Hak riski" />} />
        <Kpi label="Son satış raporu" value={ov.data?.sonRapor?.donem ?? '—'} help={ov.data?.sonRapor?.platform ?? 'Henüz onaylı rapor yok'}
          info={<SqlInfo k={src} alan="sonRapor" label="Son satış raporu" />} />
      </KpiRow>
      <Tabs tabs={TABS.map((t) => ({ ...t, badge: t.key === 'risk' ? k?.hakRiski : t.key === 'crm' ? k?.crmIslenecek : null }))} value={tab}
        onChange={(t) => update({ sekme: t === 'katalog' ? null : t })} />
      {tab === 'katalog' && meta.data && <CatalogList meta={meta.data} params={params} update={update} onOpen={(kid) => nav(`/dijital-yayin/kitap/${kid}?${params.toString()}`)} />}
      {tab === 'risk' && meta.data && <RiskTab meta={meta.data} onOpen={(kid) => nav(`/dijital-yayin/kitap/${kid}?${params.toString()}`)} />}
      {tab === 'crm' && <PendingTab onOpen={(kid) => nav(`/dijital-yayin/kitap/${kid}?${params.toString()}`)} />}
      {tab === 'platformlar' && meta.data && <PlatformsTab meta={meta.data} />}
      {meta.data && (
        <DigitalTitleDrawer id={id ?? null} meta={meta.data} onClose={() => nav(`/dijital-yayin${params.toString() ? `?${params.toString()}` : ''}`)} />
      )}
    </DigitalFrame>
  );
}

function ReadingNote({ ov }: { ov?: Overview }) {
  if (!ov) return null;
  const o = ov.okuma;
  if (!o || (!o.ok && !o.error)) {
    return <Note tone="info">Dijital katalog henüz okunmadı. Gece 04:00'te kendiliğinden okunur; yetkiniz varsa «Yeniden oku» ile şimdi başlatabilirsiniz.</Note>;
  }
  if (!o.ok) return <Note tone="err">Son okuma tamamlanamadı: {o.error}. Ekrandaki bilgi bir önceki okumadandır.</Note>;
  const w = ov.logo?.pencere;
  return (
    <Note tone={o.notlar?.length ? 'warn' : 'info'}>
      Son okuma {fmtDate(o.at ?? o._at)} · hak kaynağı {o.hakKaynagi ?? 'CRM sözleşmeleri'}
      {w ? ` · basılı satış penceresi ${w[0]} – ${w[1]} (Logo faturalı satır, son veri ${ov.logo.veriSonu})` : ''}.
      <SqlInfo k={ov.kaynaklar} alan={w ? 'logo' : 'okuma'} label={w ? 'Basılı satış penceresi' : 'Son okuma'} className="ml-0.5" />
      {o.notlar?.map((n) => <span key={n} className="mt-1 block">{n}</span>)}
    </Note>
  );
}

function CatalogList({ meta, params, update, onOpen }: {
  meta: Meta; params: URLSearchParams; update: (n: Record<string, string | null>) => void; onOpen: (id: string) => void;
}) {
  const durum = params.get('durum') ?? '';
  const hak = params.get('hak') ?? '';
  const tur = params.get('tur') ?? 'kitap';
  const page = Number(params.get('sayfa') ?? 0) || 0;
  const [q, setQ] = useState(params.get('q') ?? '');
  const dq = useDebounced(q, 300);
  const list = useQuery({
    queryKey: ['dijital', 'titles', durum, hak, tur, dq, page],
    queryFn: () => dijitalApi.titles({ durum, hak, tur, q: dq, page }),
    enabled: ENGINE_ENABLED,
    placeholderData: keepPreviousData,
  });
  const items = list.data?.items ?? [];
  return (
    <Panel>
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-[1.4fr_1fr_1fr_1fr]">
        <label className="flex flex-col gap-1">
          <span className={labelCls}>Ara</span>
          <span className="relative flex items-center">
            <Search aria-hidden className="pointer-events-none absolute left-3 h-4 w-4 text-canvas-muted" />
            <input className={`${field} pl-9`} value={q} placeholder="Kitap, yazar, stok kodu, ISBN, e-ISBN"
              onChange={(e) => { setQ(e.target.value); update({ q: e.target.value || null, sayfa: null }); }} />
          </span>
        </label>
        <label className="flex flex-col gap-1">
          <span className={labelCls}>Durum</span>
          <select className={field} value={durum} onChange={(e) => update({ durum: e.target.value || null, sayfa: null })}>
            {DURUM.map((d) => <option key={d.key} value={d.key}>{d.label}</option>)}
          </select>
        </label>
        <label className="flex flex-col gap-1">
          <span className={labelCls}>E-kitap hakkı</span>
          <select className={field} value={hak} onChange={(e) => update({ hak: e.target.value || null, sayfa: null })}>
            <option value="">Hepsi</option>
            {Object.entries(meta.haklar).map(([key, v]) => <option key={key} value={key}>{v}</option>)}
          </select>
        </label>
        <label className="flex flex-col gap-1">
          <span className={labelCls}>Kart türü</span>
          <select className={field} value={tur} onChange={(e) => update({ tur: e.target.value === 'kitap' ? null : e.target.value, sayfa: null })}>
            <option value="kitap">Basılı kitap kartları</option>
            <option value="dijital">E-kitap / sesli kitap kartları</option>
            <option value="hepsi">Bütün kartlar</option>
          </select>
        </label>
      </div>
      {list.data && (
        <ListHead>
          <InfoLabel k={list.data.kaynaklar} alan="total" label="Süzgeçteki kitap sayısı">{`${fmtInt(list.data.total)} kitap`}</InfoLabel>
          <InfoLabel k={list.data.kaynaklar} alan="items[].basili12Adet" label="Basılı adet, son 12 ay">Sağdaki sayı: basılı adet, son 12 ay</InfoLabel>
        </ListHead>
      )}
      <div className="mt-2 flex flex-col gap-2">
        {list.isLoading && <div className="py-8 text-center text-[12px] text-canvas-muted">Yükleniyor…</div>}
        {list.error && <Note tone="err">{errText(list.error, 'Liste okunamadı.')}</Note>}
        {list.data && !items.length && <div className="py-8 text-center text-[12.5px] text-canvas-muted">Bu süzgeçte kitap yok.</div>}
        {items.map((t) => <TitleCard key={t.kitapId} t={t} onOpen={onOpen} />)}
      </div>
      {list.data && (
        <Pager page={page} pageSize={list.data.pageSize} total={list.data.total} shown={items.length} loading={list.isLoading}
          fetching={list.isFetching} onPage={(p) => update({ sayfa: p ? String(p) : null })} />
      )}
    </Panel>
  );
}

function TitleCard({ t, onOpen }: { t: TitleRow; onOpen: (id: string) => void }) {
  return (
    <button
      type="button"
      onClick={() => onOpen(t.kitapId)}
      className="grid grid-cols-1 gap-2 rounded-2xl border border-slate-100 bg-white/80 p-3 text-left transition-colors duration-150 hover:border-canvas-violet/40 md:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)_minmax(0,1.2fr)_110px] md:items-center"
    >
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-1.5">
          {t.firsatPuani !== null && <Pill tone="violet">Fırsat</Pill>}
          {t.baskiDegisim && <Pill tone="warn">{t.baskiDegisim.tur}</Pill>}
          <span className="text-[11px] font-semibold text-canvas-muted">{[t.stokKodu, t.tipAdi, t.hedefKitle].filter(Boolean).join(' · ')}</span>
        </div>
        <div className="mt-1 break-words text-[13.5px] font-extrabold leading-snug">{t.ad ?? '—'}</div>
        <div className="truncate text-[12px] text-canvas-muted">{t.yazar ?? ''}</div>
      </div>
      <div className="flex flex-wrap items-center gap-1.5">
        <span className="text-[11px] font-bold uppercase tracking-wide text-canvas-muted">Hak</span>
        <span className="text-[11px] text-canvas-muted">e-kitap</span>
        <RightPill value={t.hakEkitap} label={t.hakEkitapAdi} />
        <span className="text-[11px] text-canvas-muted">sesli</span>
        <RightPill value={t.hakSesli} label={t.hakSesliAdi} />
      </div>
      <div className="flex min-w-0 flex-col gap-1">
        <div className="flex flex-wrap items-center gap-1.5 text-[11.5px]">
          <span className="font-bold text-canvas-muted">e-ISBN</span>
          <span className="font-mono">{t.eIsbn ?? 'yok'}</span>
          <span className="font-bold text-canvas-muted">e-kitap</span>
          <span>{t.ekitapStokKodu ? `stok ${t.ekitapStokKodu}` : t.studioDurumu !== 'yok' ? t.studioDurumuAdi : t.epubCrm ? "CRM'de E-Pub: Evet" : 'dosya bilgisi yok'}</span>
        </div>
        <Chips items={t.platformlar} />
      </div>
      <div className="flex items-center gap-2 md:flex-col md:items-end md:gap-0.5">
        <span className="text-[11px] font-bold uppercase tracking-wide text-canvas-muted md:hidden">Basılı 12 ay</span>
        <span className="font-mono text-[12.5px] font-bold tabular-nums">{fmtInt(t.basili12Adet)}</span>
        <span className="hidden text-[10.5px] text-canvas-muted md:block">basılı adet, 12 ay</span>
      </div>
    </button>
  );
}

function RiskTab({ meta, onOpen }: { meta: Meta; onOpen: (id: string) => void }) {
  const q = useQuery({ queryKey: ['dijital', 'risks'], queryFn: dijitalApi.risks, enabled: ENGINE_ENABLED });
  return (
    <>
      <Note tone="info">
        Hak riski: dijitalde görünen (e-kitap stok kodu, platform kaydı ya da Logo'da e-kitap faturası) ama hakkı eksik, yok ya da
        incelenmeli olan kitaplar. Hak notu olan sözleşme kendiliğinden «hak var» sayılmaz; kararı telif birimi yazar. Zeki AI
        notları yalnız önceliklendirmek için ön okur.
      </Note>
      {q.error && <Note tone="err">{errText(q.error, 'Liste okunamadı.')}</Note>}
      <Panel>
        <h2 className="flex flex-wrap items-center gap-1 text-[15px] font-extrabold">
          Dijitalde, hakkı sorunlu ({fmtInt(q.data?.risk.length)})
          <SqlInfo k={q.data?.kaynaklar} alan="sayac.risk" label="Dijitalde, hakkı sorunlu" />
        </h2>
        <div className="mt-2 flex flex-col gap-2">
          {q.isLoading && <div className="py-6 text-center text-[12px] text-canvas-muted">Yükleniyor…</div>}
          {q.data && !q.data.risk.length && <div className="py-6 text-center text-[12.5px] text-canvas-muted">Hak riski olan kitap yok.</div>}
          {q.data?.risk.map((r) => <RiskCard key={r.kitapId} r={r} meta={meta} onOpen={onOpen} />)}
        </div>
      </Panel>
      <Panel>
        <h2 className="flex flex-wrap items-center gap-1 text-[15px] font-extrabold">
          Telif kararı bekleyen hak notları ({fmtInt(q.data?.incele.length)})
          <SqlInfo k={q.data?.kaynaklar} alan="sayac.incele" label="Telif kararı bekleyen hak notları" />
        </h2>
        <p className="mt-0.5 text-[12px] text-canvas-muted">Dijitalde olmayan ama hak notu yüzünden «incelenmeli» kalan kitaplar; karar verilince fırsat listesine girebilir.</p>
        <div className="mt-2 flex flex-col gap-2">
          {q.data?.incele.map((r) => <RiskCard key={r.kitapId} r={r} meta={meta} onOpen={onOpen} />)}
        </div>
      </Panel>
    </>
  );
}

function RiskCard({ r, meta, onOpen }: { r: RiskRow; meta: Meta; onOpen: (id: string) => void }) {
  return (
    <div className="rounded-2xl border border-slate-100 bg-white/80 p-3">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-1.5">
            {r.riskBicim.map((b) => <Pill key={b} tone="err">{meta.bicimler[b]} dijitalde</Pill>)}
            {r.notOkuma && <Pill tone={r.notOkuma === 'kisitliyor' ? 'err' : r.notOkuma === 'belirsiz' ? 'warn' : 'muted'}>Zeki AI: not {meta.notAdlari[r.notOkuma] ?? r.notOkuma}</Pill>}
            <span className="text-[11px] font-semibold text-canvas-muted">{r.stokKodu}</span>
          </div>
          <div className="mt-1 break-words text-[13.5px] font-extrabold">{r.ad}</div>
        </div>
        <button type="button" className={btnGhost} onClick={() => onOpen(r.kitapId)}>Ayrıntı ve karar</button>
      </div>
      <div className="mt-2 grid grid-cols-1 gap-1 text-[12px] leading-snug md:grid-cols-2">
        <div><span className="font-bold">E-kitap: </span><RightPill value={r.hakEkitap} label={r.hakEkitapAdi} /> <span className="text-canvas-muted">{r.hakEkitapGerekce}</span></div>
        <div><span className="font-bold">Sesli: </span><RightPill value={r.hakSesli} label={r.hakSesliAdi} /> <span className="text-canvas-muted">{r.hakSesliGerekce}</span></div>
      </div>
      {r.notluSozlesmeler.map((c) => (
        <blockquote key={c.id} className="mt-2 break-words rounded-xl bg-amber-50 px-3 py-2 text-[12px] leading-snug">
          <span className="font-bold">{c.taraflar.join(', ') || c.ad}: </span>{c.not}
          {c.hakHaritasi && c.hakHaritasi.durum !== 'reddedildi' && c.hakHaritasi.ozet && (
            <span className="mt-0.5 block text-[11px] text-canvas-muted">
              Hak haritası ({c.hakHaritasi.onayli ? 'telif onaylı' : 'öneri'}): {c.hakHaritasi.ozet}
            </span>
          )}
        </blockquote>
      ))}
    </div>
  );
}

function PendingTab({ onOpen }: { onOpen: (id: string) => void }) {
  const [durum, setDurum] = useState('acik');
  const q = useQuery({ queryKey: ['dijital', 'pending', durum], queryFn: () => dijitalApi.pending(durum), enabled: ENGINE_ENABLED });
  return (
    <Panel>
      <div className="flex flex-wrap items-end justify-between gap-2">
        <div className="min-w-0">
          <h2 className="flex flex-wrap items-center gap-1 text-[15px] font-extrabold">
            CRM'e işlenecek alanlar{q.data ? ` (${fmtInt(q.data.items.length)})` : ''}
            <SqlInfo k={q.data?.kaynaklar} alan="sayac" label="CRM'e işlenecek alanlar" />
          </h2>
          <p className="mt-0.5 max-w-[80ch] text-[12px] leading-snug text-canvas-muted">
            Portal CRM'e yazmaz. Stüdyoda üretilen e-kitabın e-ISBN'i, hazır e-kitap için «E-Pub Durumu» ve platformda yayında olup
            e-kitap stok kodu açılmamış kitaplar burada listelenir; CRM'e işlendiğinde gece okumasında kendiliğinden kapanır.
          </p>
        </div>
        <select className={`${field} w-auto`} value={durum} onChange={(e) => setDurum(e.target.value)}>
          <option value="acik">Açık</option>
          <option value="kapandi">Kapanmış</option>
          <option value="hepsi">Hepsi</option>
        </select>
      </div>
      {q.error && <Note tone="err">{errText(q.error, 'Liste okunamadı.')}</Note>}
      <div className="mt-3 flex flex-col gap-2">
        {q.data && !q.data.items.length && <div className="py-6 text-center text-[12.5px] text-canvas-muted">Kayıt yok.</div>}
        {q.data?.items.map((p) => (
          <button key={p.id} type="button" onClick={() => onOpen(p.kitapId)}
            className="grid grid-cols-1 gap-1 rounded-2xl border border-slate-100 bg-white/80 p-3 text-left hover:border-canvas-violet/40 md:grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)_minmax(0,1.2fr)_120px] md:items-center">
            <div className="min-w-0"><div className="break-words text-[13px] font-extrabold">{p.ad ?? p.kitapId}</div><div className="text-[11px] text-canvas-muted">{p.stokKodu}</div></div>
            <div className="text-[12px]"><span className="font-bold">{p.alanAdi}</span></div>
            <div className="break-words text-[12px]"><span className="font-mono">{p.deger}</span><span className="block text-[11px] text-canvas-muted">{p.kaynak}</span></div>
            <div className="text-[11px] text-canvas-muted">{p.durum === 'acik' ? `açıldı ${fmtDate(p.acildi)}` : `kapandı ${fmtDate(p.kapandi)}`}</div>
          </button>
        ))}
      </div>
    </Panel>
  );
}

