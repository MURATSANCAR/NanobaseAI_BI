import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Loader2, RefreshCw } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import { Note, Pill, btnGhost, errText } from '../admin/ui';
import { Kpi, KpiRow, Panel } from '../editorial/kit';
import SqlInfo from '../components/SqlInfo';
import { EmptyHint } from '../components/Explain';
import { KIND_TONE, ecomApi, fmtDay, fmtInt, fmtWhen, type DiffKind, type Meta, type Overview } from './api';
import { DiffCard, EticaretFrame, Stamp } from './parts';
import ItemDrawer from './ItemDrawer';

/** M34 Platform durumu (ilk açılış): dört gösterge (her birinin kaynağı ve kesim tarihi yanında), bugün bakılacaklar,
 *  türe göre açık farklar, onay bekleyen Zeki AI önerileri, son okumanın kaynak durumu. */
export default function EticaretHome() {
  const qc = useQueryClient();
  const [open, setOpen] = useState<string | null>(null);
  const meta = useQuery({ queryKey: ['eticaret', 'meta'], queryFn: ecomApi.meta, enabled: ENGINE_ENABLED, staleTime: 60_000 });
  const ov = useQuery({
    queryKey: ['eticaret', 'overview'], queryFn: ecomApi.overview, enabled: ENGINE_ENABLED,
    refetchInterval: (q) => (q.state.data?.durum.running ? 5_000 : false),
  });
  const props = useQuery({
    queryKey: ['eticaret', 'proposals', 'hazir'], queryFn: () => ecomApi.proposals('hazir'),
    enabled: ENGINE_ENABLED && !!meta.data?.me.canApprove,
  });
  const refresh = useMutation({
    mutationFn: ecomApi.refresh,
    onSuccess: (r) => { toast.success(r.started ? 'Okuma başladı; birkaç dakika sürebilir.' : 'Başka bir okuma sürüyor.'); qc.invalidateQueries({ queryKey: ['eticaret'] }); },
    onError: (e) => toast.error(errText(e, 'Okuma başlatılamadı.') ?? ''),
  });
  const running = !!ov.data?.durum.running;
  return (
    <EticaretFrame
      title="Platform durumu"
      lead="Sitedeki (T-soft) ürünler her gece CRM kitap kartı ve Logo kaydıyla karşılaştırılır; fiyat ve stok farkı, eksik kart ve satışta olmaması gereken kitap burada görünür. Düzeltmeyi T-soft'ta ya da CRM'de siz yaparsınız, ertesi gece doğrulanır."
      source="Kaynak: site kaydı · CRM · Logo"
      aside={meta.data?.me.canMark ? (
        <button type="button" className={btnGhost} disabled={running || refresh.isPending} onClick={() => refresh.mutate()}>
          {running || refresh.isPending ? <Loader2 aria-hidden className="h-4 w-4 animate-spin" /> : <RefreshCw aria-hidden className="h-4 w-4" />}
          {running ? 'Okunuyor…' : 'Şimdi yeniden oku'}
        </button>
      ) : undefined}
    >
      {!ENGINE_ENABLED && <Note tone="warn">Bu ekranın veri bağlantısı kurulmamış; liste açılamaz. Lütfen sistem yöneticinize bildirin.</Note>}
      {(meta.error || ov.error) && <Note tone="err">{errText(meta.error || ov.error, 'Ekran bilgisi okunamadı.')}</Note>}
      {ov.isLoading && <div className="py-10 text-center text-[12px] text-canvas-muted">Yükleniyor…</div>}
      {ov.data && meta.data && <Body ov={ov.data} meta={meta.data} onOpen={setOpen} />}
      {meta.data?.me.canApprove && !!props.data?.items.length && (
        <Panel>
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <h2 className="text-[16px] font-extrabold">Onay bekleyen Zeki AI kart önerileri</h2>
            <Stamp>
              <span className="inline-flex items-center gap-1">
                {props.data.items.length} öneri · öneriyi isteyen onaylayamaz
                <SqlInfo k={props.data.kaynaklar} alan="items" label="Onay bekleyen öneriler" />
              </span>
            </Stamp>
          </div>
          <ul className="mt-2 flex flex-col gap-1.5">
            {props.data.items.map((p) => (
              <li key={p.id}>
                <button type="button" onClick={() => p.productKey && setOpen(p.productKey)} disabled={!p.productKey}
                  className="flex min-h-11 w-full flex-wrap items-center justify-between gap-2 rounded-xl bg-white/80 px-3 py-2 text-left transition-colors duration-150 hover:bg-white sm:min-h-0">
                  <span className="min-w-0 break-words text-[13px] font-bold">{p.ad || p.productId}</span>
                  <span className="text-[11.5px] text-canvas-muted">{p.createdBy} · {fmtWhen(p.createdAt)}</span>
                </button>
              </li>
            ))}
          </ul>
        </Panel>
      )}
      {meta.data && <ItemDrawer itemKey={open} meta={meta.data} onClose={() => setOpen(null)} />}
    </EticaretFrame>
  );
}

function Body({ ov, meta, onOpen }: { ov: Overview; meta: Meta; onOpen: (k: string) => void }) {
  const g = ov.gostergeler;
  const src = (ov.sonOkuma?.ozet?.kaynaklar ?? {}) as Record<string, Record<string, unknown>>;
  const siteAt = (src.site?.okundu as string | undefined) ?? null;
  const cut = ov.logoKesim;
  const errors = Object.entries(src).filter(([, v]) => v && typeof v === 'object' && 'hata' in v) as Array<[string, { hata: string }]>;
  const kinds = (Object.keys(meta.turler) as DiffKind[]).filter((k) => ov.turSayilari[k] > 0);
  const k = ov.kaynaklar;
  return (
    <>
      <KpiRow>
        <Kpi label="Sitede satışta" value={fmtInt(g.siteAktif)} help={`Site kaydı ${fmtWhen(siteAt)} · CRM'de «TSOFT Aktif» ${fmtInt(g.crmTsoftAktif)}`}
          explain="Sitede şu an satışa açık ürün sayısı. Altında CRM'de «TSOFT Aktif» işaretli kitap sayısı yazar; ikisi arasındaki fark da incelenecek bir farktır."
          info={<SqlInfo k={k} alan="gostergeler.siteAktif" label="Sitede satışta" />} />
        <Kpi label="Açık fark" value={fmtInt(g.acikFark)} help={`Son okuma ${fmtWhen(ov.sonOkuma?.bitti)} · Logo kesimi ${fmtDay(cut)}`}
          explain="Site, CRM ve Logo arasında bulunan ve henüz kapanmamış farkların sayısı (fiyat, stok, aktiflik, barkod, kart). Fark düzeltilince sonraki gece okumasında kendiliğinden kapanır."
          info={<SqlInfo k={k} alan="gostergeler.acikFark" label="Açık fark" />} />
        <Kpi label="Eksik ürün kartı" value={fmtInt(g.eksikKart)} help="Sitede satışta, CRM kartında zorunlu alan boş"
          explain="Sitede satışta olduğu hâlde CRM kitap kartında zorunlu bir alanı boş kalan ürünler. Kartı CRM'de tamamlayınca listeden düşer."
          info={<SqlInfo k={k} alan="gostergeler.eksikKart" label="Eksik ürün kartı" />} />
        <Kpi label="Satışta olmaması gereken" value={fmtInt(g.satistaOlmamali)} help="CRM yayın durumu: bizim değil, devredildi, iptal, çekildi…"
          explain="Sitede satışta görünen ama CRM'deki yayın durumuna göre satılmaması gereken kitaplar (ör. hakkı devredilmiş ya da iptal edilmiş). Hukuki risk taşıdığı için önce bunlara bakın."
          info={<SqlInfo k={k} alan="gostergeler.satistaOlmamali" label="Satışta olmaması gereken" />} />
      </KpiRow>
      {!ov.sonOkuma && <Note tone="info">Henüz okuma yapılmadı. Gece 04:30'da kendiliğinden koşar; yetkiniz varsa «Şimdi yeniden oku».</Note>}
      {ov.sonOkuma?.hata && <Note tone="err">Son okuma tamamlanamadı: {ov.sonOkuma.hata}</Note>}
      {errors.map(([k, v]) => (
        <Note key={k} tone="warn">{k === 'crm' ? 'CRM' : k === 'logo' ? 'Logo' : k} okunamadı: {v.hata}. Bu kaynağa bağlı fark türleri bu turda hesaplanmadı ve kapanmadı.</Note>
      ))}
      {ov.durum.running && <Note tone="info">Okuma sürüyor ({ov.durum.step ?? 'başladı'}).</Note>}
      <div className="grid grid-cols-1 gap-3 lg:grid-cols-[minmax(0,1fr)_340px] lg:gap-4">
        <Panel>
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <h2 className="inline-flex items-center gap-1 text-[16px] font-extrabold">
              Bugün bakılacaklar <SqlInfo k={k} alan="bugun.items" label="Bugün bakılacaklar" />
            </h2>
            <Stamp>Önce hukuki risk, sonra fiyat ve stok; aynı türde son dönem satışı büyük olan önde</Stamp>
          </div>
          <div className="mt-2 flex flex-col gap-2">
            {!ov.bugun.items.length && <EmptyHint title="Bugün bakılacak fark yok" why="Site, CRM ve Logo kayıtları son okumada birbiriyle uyumlu görünüyor." />}
            {ov.bugun.items.map((d) => <DiffCard key={d.id} d={d} onOpen={onOpen} k={k} alan="bugun.items" />)}
          </div>
          {ov.bugun.total > ov.bugun.items.length && (
            <div className="mt-2 text-right">
              <Link to="/e-ticaret/farklar" className="text-[12.5px] font-bold text-canvas-violet hover:underline">
                İlk {ov.bugun.items.length} gösteriliyor; {fmtInt(ov.bugun.total)} açık farkın hepsi Farklar'da →
              </Link>
              <SqlInfo k={k} alan="bugun.total" label="Açık fark sayısı (bugün)" className="ml-1" />
            </div>
          )}
        </Panel>
        <div className="flex flex-col gap-3">
          <Panel>
            <h2 className="inline-flex items-center gap-1 text-[15px] font-extrabold">
              Türe göre açık farklar <SqlInfo k={k} alan="turSayilari" label="Türe göre açık farklar" />
            </h2>
            <ul className="mt-2 flex flex-col gap-1">
              {!kinds.length && <li className="text-[12px] text-canvas-muted">Açık fark yok.</li>}
              {kinds.map((k) => (
                <li key={k}>
                  <Link to={`/e-ticaret/farklar?tur=${k}`}
                    className="flex min-h-11 items-center justify-between gap-2 rounded-xl px-2 py-1.5 transition-colors duration-150 hover:bg-white/70 sm:min-h-0">
                    <Pill tone={KIND_TONE[k]}>{meta.turler[k]}</Pill>
                    <span className="font-mono text-[13px] font-bold tabular-nums">{fmtInt(ov.turSayilari[k])}</span>
                  </Link>
                </li>
              ))}
            </ul>
          </Panel>
          <Panel>
            <h2 className="inline-flex items-center gap-1 text-[15px] font-extrabold">
              Son 7 gün <SqlInfo k={k} alan="haftalik" label="Son 7 gün" />
            </h2>
            <p className="mt-1 text-[12.5px]">
              {fmtInt(ov.haftalik.kapanan)} fark kapandı
              {ov.haftalik.ortalamaKapanmaGun !== null ? `; ortalama kapanma ${ov.haftalik.ortalamaKapanmaGun.toLocaleString('tr-TR')} gün` : ''}.
            </p>
            <p className="mt-1 text-[12px] text-canvas-muted">
              Bilerek bırakılan {fmtInt(ov.durumSayilari.bilincli)} · doğrulama bekleyen {fmtInt(ov.durumSayilari.duzeltildi)} · sonraya {fmtInt(ov.durumSayilari.sonra)}
              <SqlInfo k={k} alan="durumSayilari" label="Durum sayıları" className="ml-0.5" />
            </p>
            <p className="mt-2 text-[11.5px] leading-snug text-canvas-muted">
              Bildirim: {meta.ayarlar.bildirim ? 'fark ilk görüldüğünde e-posta gider' : 'alıcı tanımlı değil (Yönetim → E-ticaret)'} ·
              Haftalık özet: {meta.ayarlar.haftalik ? 'pazartesi sabahı' : 'alıcı tanımlı değil'}
            </p>
          </Panel>
        </div>
      </div>
    </>
  );
}
