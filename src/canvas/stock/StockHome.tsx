import { useCallback, useState, type ReactNode } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Sparkles } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import { Note, btnGhost, errText, field, label as labelCls } from '../admin/ui';
import { EmptyHint, Explain } from '../components/Explain';
import { Kpi, KpiRow, Pager, Panel, useDebounced } from '../editorial/kit';
import SearchSelect from '../components/SearchSelect';
import { canOpenRoute, usePageAccess } from '../useAdmin';
import { fmtDay } from '../budget/api';
import SqlInfo, { InfoLabel } from '../components/SqlInfo';
import type { Kaynaklar } from '../components/sqlInfo';
import { gunText, n0, stockApi, tl, type DagitimIsaret, type StockState } from './api';
import ItemList from './ItemList';
import { BookCell, Chips, DataDay, Empty, ExportLink, Loading, SourcesButton, StockFrame } from './parts';
import { RULES } from './rules';

/** M43 açılış (/stok): dört gösterge, kitap sor, bugün ilgilenilecekler, stok listesi (süzgeçler adreste). */

const STATES: Array<{ key: '' | StockState; label: string }> = [
  { key: '', label: 'Hepsi' },
  { key: 'stoksuz', label: 'Stokta yok' },
  { key: 'bitecek', label: 'Bitecek' },
  { key: 'yeterli', label: 'Yeterli' },
  { key: 'fazla', label: 'Fazla' },
  { key: 'olu', label: 'Hareketsiz' },
  { key: 'satissiz', label: 'Satışı yok' },
];

const ASK = [
  'Önümüzdeki 30 günde stoğu bitecek çocuk kitapları hangileri?',
  'Son 12 ayda hiç satmamış ama stokta 1.000’den fazla olan kitaplar?',
  'Bekleyen siparişi en çok olan 20 kitap ve stok durumu?',
  'Geçen ayki sayım eksiği kaç adet, hangi raflarda?',
];


export default function StockHome() {
  const nav = useNavigate();
  const pages = usePageAccess();
  const [params, setParams] = useSearchParams();
  const meta = useQuery({ queryKey: ['stock', 'meta'], queryFn: stockApi.meta, enabled: ENGINE_ENABLED, staleTime: 60_000 });
  const ov = useQuery({ queryKey: ['stock', 'overview'], queryFn: stockApi.overview, enabled: ENGINE_ENABLED });
  const names = useQuery({ queryKey: ['stock', 'names'], queryFn: stockApi.names, enabled: ENGINE_ENABLED && !!ov.data, staleTime: 5 * 60_000 });
  const durum = (params.get('durum') ?? '') as '' | StockState;
  const yayinevi = params.get('yayinevi') ?? '';
  const depo = params.get('depo') ?? '';
  const sira = params.get('sira') ?? 'gun';
  const dagitim = (params.get('dagitim') ?? '') as '' | DagitimIsaret;
  const sayfa = Number(params.get('sayfa') ?? 0) || 0;
  const [q, setQ] = useState(params.get('q') ?? '');
  const dq = useDebounced(q, 250);

  const update = useCallback(
    (next: Record<string, string | null>) => {
      const p = new URLSearchParams(params);
      for (const [k, v] of Object.entries(next)) {
        if (v) p.set(k, v);
        else p.delete(k);
      }
      if (!('sayfa' in next)) p.delete('sayfa');
      setParams(p, { replace: true });
    },
    [params, setParams],
  );

  const list = useQuery({
    queryKey: ['stock', 'items', dq, durum, yayinevi, depo, sira, sayfa, dagitim],
    queryFn: () => stockApi.items({ q: dq, durum, yayinevi, depo, sira, sayfa, dagitim }),
    enabled: ENGINE_ENABLED && !!ov.data,
    placeholderData: (prev) => prev,
  });

  const me = meta.data?.me;
  const o = ov.data;
  const go = (to: string) => (canOpenRoute(pages, to) ? () => nav(to) : undefined);
  const canAsk = canOpenRoute(pages, '/genel-bakis');

  return (
    <StockFrame
      crumb="Stok"
      title="Depo ve stok"
      lead="Her kitabın Logo stoğu, CRM raf dağılımı, satış hızı ve kaç gün yeteceği tek yerde. Bitecekler, fazla stok, Logo ile CRM arasındaki fark ve Logo’ya geçmemiş hareketler buradan izlenir; Logo’ya ve CRM’e hiçbir şey yazılmaz."
      source={o?.veriSonu ? `Logo · ${fmtDay(o.veriSonu)}` : 'Logo + CRM'}
      aside={
        <>
          <SourcesButton rules={RULES} />
          <ExportLink show={!!me?.canExport} href={stockApi.exportUrl('stok', { durum, q: dq })} />
        </>
      }
    >
      {ov.error && <Note tone="err">{errText(ov.error, 'Stok verisi okunamadı.')}</Note>}
      {ov.isLoading && <Loading what="Stok" />}
      {o && (
        <>
          <DataDay day={o.veriSonu} extra={o.yenileniyor ? 'Veriler arka planda tazeleniyor.' : undefined} />
          {o.uyarilar.map((w) => (
            <Note key={w} tone="warn">{w}</Note>
          ))}
          <KpiRow>
            <Kpi label="Toplam stok" value={n0(o.toplamStok)} help={`${n0(o.stokluKitap)} kitapta, adet${o.deger ? ` · değeri ${tl(o.deger.toplam)}` : ''}`}
              explain="Logo’daki bütün ambarlarda duran kitap adedi (giriş − çıkış). Henüz depoya girmemiş ileri tarihli üretim sayılmaz."
              info={<SqlInfo k={o.kaynaklar} alan={o.deger ? 'deger' : 'toplamStok'} label={o.deger ? 'Toplam stok ve stok değeri' : 'Toplam stok'} />} />
            <Kpi label="Stokta yok" value={n0(o.stoksuzAktif)} help="Satışı olan ama Logo stoğu bitmiş kitap" onClick={() => update({ durum: 'stoksuz' })} active={durum === 'stoksuz'}
              explain="Hâlâ satılan ama Logo stoğu sıfıra inmiş kitaplar. Karta dokunursanız aşağıdaki liste yalnız bunları gösterir."
              info={<SqlInfo k={o.kaynaklar} alan="stoksuzAktif" label="Stokta yok" />} />
            <Kpi label={`${o.bitecekGun} günde bitecek`} value={n0(o.bitecek)} help={`${n0(o.kartsizKritik)} tanesinin açık üretim kartı yok · baskı süresi ${o.baskiSuresi} gün`} onClick={go('/stok/bitecekler')}
              explain="Bugünkü satış hızıyla stoğu bu süre içinde ya da yeni baskının depoya gelmesinden önce bitecek kitaplar. «Açık üretim kartı yok» olanlar için henüz baskı planlanmamış."
              info={<SqlInfo k={o.kaynaklar} alan="kartsizKritik" label="Bitecek ve kartsız kritik kitaplar" />} />
            <Kpi label="Logo’ya geçmemiş" value={n0(o.aktarimHatasi)} help={`Hata mesajlı hareket; mesajsız bekleyen ${n0(o.aktarimBekleyen)}`} onClick={go('/stok/aktarim')}
              explain="CRM’de yapılıp Logo’ya aktarılamamış depo hareketleri. Bunlar düzelmeden Logo stoğu ile raftaki adet tutmaz."
              info={<SqlInfo k={o.kaynaklar} alan="aktarimHatasi" label="Logo’ya geçmemiş hareketler" />} />
          </KpiRow>
        </>
      )}

      {o && (
        <Panel>
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Kitap sor — stok, raf, bekleyen sipariş, üretim</span>
            <SearchSelect
              label="Kitap sor"
              placeholder={names.isLoading ? 'Kitaplar okunuyor…' : 'Kitap adı ya da stok kodu yazın'}
              options={names.data?.items ?? []}
              value=""
              onChange={(v) => v && nav(`/stok/${encodeURIComponent(v)}`)}
            />
          </label>
        </Panel>
      )}

      {o && (
        <div className="grid gap-3 lg:grid-cols-3 lg:gap-4">
          <Today title="En önce bitecekler" total={o.bitecek} to="/stok/bitecekler" pages={pages} k={o.kaynaklar} alan="bugun.bitecek.items[].gun">
            {o.bugun.bitecek.items.slice(0, 8).map((i) => (
              <li key={i.stokKodu} className="flex items-start justify-between gap-2 py-1.5">
                <BookCell it={i} />
                <span className="shrink-0 text-right font-mono text-[12px] tabular-nums">
                  {gunText(i.gun)}
                  {!i.uretim && i.baskiUyarisi ? <span className="block text-[10.5px] font-bold text-amber-700">kart yok</span> : null}
                </span>
              </li>
            ))}
          </Today>
          <Today title="Logo’ya aktarılamayan" total={o.aktarimHatasi} to="/stok/aktarim" pages={pages} k={o.kaynaklar} alan="bugun.aktarim.items[].yasGun">
            {o.bugun.aktarim.items.slice(0, 8).map((t) => (
              <li key={t.id} className="py-1.5">
                <div className="flex justify-between gap-2 text-[12px] font-bold">
                  <span className="break-words">{t.fisNo ?? '—'} · {t.islemTuruEtiket}</span>
                  <span className="shrink-0 font-mono tabular-nums text-canvas-muted">{t.yasGun ?? '—'} gün</span>
                </div>
                <div className="line-clamp-2 text-[11.5px] text-canvas-muted">{t.sinif ? `${t.sinif} · ` : ''}{t.mesaj}</div>
              </li>
            ))}
          </Today>
          <Today title="Logo–CRM farkı en büyük" total={o.farkliKitap} to="/stok/fark" pages={pages} k={o.kaynaklar} alan="bugun.fark.items[].fark">
            {o.bugun.fark.items.slice(0, 8).map((i) => (
              <li key={i.stokKodu} className="flex items-start justify-between gap-2 py-1.5">
                <BookCell it={i} />
                <span className="shrink-0 text-right font-mono text-[12px] tabular-nums">
                  {i.fark !== null && i.fark > 0 ? '+' : ''}
                  {n0(i.fark)}
                </span>
              </li>
            ))}
          </Today>
        </div>
      )}

      {o && (
        <Panel>
          <div className="mb-3 flex flex-col gap-2">
            <div className="flex items-center gap-1">
              <div className="min-w-0 flex-1">
                <Chips label="Durum" items={STATES.map((s) => ({ ...s, count: s.key ? o.durumlar.find((d) => d.key === s.key)?.adet : null }))} value={durum} onChange={(k) => update({ durum: k })} />
              </div>
              <Explain label="Durumlar" title="Durumlar ne demek?">
                <span className="block"><b>Stokta yok:</b> satışı var, Logo stoğu bitmiş.</span>
                <span className="block"><b>Bitecek:</b> stok, seçilen gün içinde ya da yeni baskı gelmeden bitiyor.</span>
                <span className="block"><b>Fazla:</b> stok varsayılan olarak 2 yıldan uzun yetiyor.</span>
                <span className="block"><b>Hareketsiz:</b> son bir yılda hiç stok hareketi yok.</span>
                <span className="block"><b>Satışı yok:</b> stok hareketi var ama satış yok.</span>
                <span className="block"><b>Yeterli:</b> yukarıdakilerin hiçbiri; stok makul süre yetiyor.</span>
              </Explain>
              <SqlInfo k={o.kaynaklar} alan="durumlar" label="Durum sayaçları" />
            </div>
            {list.data?.dagitim && (
              <div className="flex items-center gap-1">
                <div className="min-w-0 flex-1">
                  <Chips<'' | DagitimIsaret>
                    label="Dağıtımcıda"
                    items={[
                      { key: '', label: 'Dağıtımcı: hepsi' },
                      ...(['baskisi_yok', 'tukendi'] as const).map((k) => ({
                        key: k,
                        label: list.data?.dagitim?.etiketler[k] ?? k,
                        count: list.data?.dagitim?.isaretler[k] ?? 0,
                      })),
                    ]}
                    value={dagitim}
                    onChange={(k) => update({ dagitim: k || null })}
                  />
                </div>
                <Explain label="Dağıtımcı" title="Dağıtımcıda ne görünüyor?">
                  <span className="block"><b>Başarı’da baskısı yok görünüyor:</b> bizde Logo stoğu var, Başarı kataloğu kitapçılara «Baskısı Yok» ya da «Temin Edilemiyor» diyor.</span>
                  <span className="block"><b>Başarı deposunda tükenmiş:</b> bizde stok var, Başarı’da «Satışta» ama deposu boş.</span>
                  <span className="block">
                    Son görüntü: Başarı {list.data.dagitim.sonGoruntu.basari ? fmtDay(list.data.dagitim.sonGoruntu.basari) : 'okunmadı'} · D&amp;R{' '}
                    {list.data.dagitim.sonGoruntu.dr ? fmtDay(list.data.dagitim.sonGoruntu.dr) : 'okunmadı'}.
                  </span>
                </Explain>
                <SqlInfo k={list.data.kaynaklar} alan="items[].dagitim" label="Dağıtımcı bilgisi" />
              </div>
            )}
            <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
              <label className="flex flex-col gap-1">
                <span className={labelCls}>Ara</span>
                <input className={field} value={q} onChange={(e) => { setQ(e.target.value); update({ q: e.target.value }); }} placeholder="Ad, stok kodu, yazar" />
              </label>
              <label className="flex flex-col gap-1">
                <span className={labelCls}>Yayınevi</span>
                <SearchSelect label="Yayınevi" options={list.data?.yayinevleri ?? []} value={yayinevi} onChange={(v) => update({ yayinevi: v })} />
              </label>
              <label className="flex flex-col gap-1">
                <span className={labelCls}>Logo ambarı</span>
                <select className={field} value={depo} onChange={(e) => update({ depo: e.target.value })}>
                  <option value="">Bütün ambarlar</option>
                  {(list.data?.ambarlar ?? []).map((a) => (
                    <option key={a.no} value={String(a.no)}>{a.no} · {a.ad}</option>
                  ))}
                </select>
              </label>
              <label className="flex flex-col gap-1">
                <span className={labelCls}>Sıra</span>
                <select className={field} value={sira} onChange={(e) => update({ sira: e.target.value })}>
                  <option value="gun">En önce bitecek</option>
                  <option value="bakiye">En çok stok</option>
                  <option value="hiz">En hızlı satan</option>
                  <option value="ad">Ada göre</option>
                </select>
              </label>
            </div>
          </div>
          {list.error && <Note tone="err">{errText(list.error, 'Liste okunamadı.')}</Note>}
          {list.data && !list.data.items.length && (
            <EmptyHint
              title="Bu süzgeçte kitap yok"
              why="Seçtiğiniz durum, yayınevi, ambar ya da aramaya uyan kitap bulunamadı."
              action={(durum || yayinevi || depo || dq || dagitim) ? <button type="button" className={btnGhost} onClick={() => { setQ(''); update({ durum: null, yayinevi: null, depo: null, q: null, dagitim: null }); }}>Süzgeçleri temizle</button> : undefined}
            />
          )}
          {!!list.data?.items.length && (
            <ItemList k={list.data.kaynaklar} items={list.data.items} cols={['bakiye', 'crmRaf', 'hiz', 'gun', 'tukenme', 'bekleyen', 'durum', 'dagitim', 'deger']} />
          )}
          {list.data && (
            <Pager page={list.data.page} pageSize={list.data.pageSize} total={list.data.total} shown={list.data.items.length}
              loading={list.isLoading} fetching={list.isFetching} onPage={(p) => update({ sayfa: String(p) })} />
          )}
        </Panel>
      )}

      {canAsk && o && (
        <Panel>
          <div className="mb-2 flex items-center gap-2 text-[12px] font-extrabold">
            <Sparkles aria-hidden className="h-4 w-4 text-canvas-violet" />
            Zeki AI’a sorun
          </div>
          <div className="flex flex-wrap gap-2">
            {ASK.map((s) => (
              <Link key={s} to={`/genel-bakis?soru=${encodeURIComponent(s)}`} className="min-h-11 rounded-xl bg-slate-100 px-3 py-2 text-[12px] font-semibold text-canvas-ink transition-colors duration-150 hover:bg-slate-200 sm:min-h-0">
                {s}
              </Link>
            ))}
          </div>
        </Panel>
      )}
    </StockFrame>
  );
}

function Today({ title, total, to, pages, children, k, alan }: { title: string; total: number; to: string; pages: ReturnType<typeof usePageAccess>; children: ReactNode; k?: Kaynaklar; alan: string }) {
  return (
    <Panel>
      <div className="mb-1 flex items-baseline justify-between gap-2">
        <h2 className="text-[13px] font-extrabold"><InfoLabel k={k} alan={alan} label={title}>{title}</InfoLabel></h2>
        <span className="inline-flex shrink-0 items-center gap-1">
          {canOpenRoute(pages, to) ? (
            <Link to={to} className="inline-flex min-h-11 items-center text-[12px] font-bold text-canvas-violet hover:underline sm:min-h-0">
              Tümü ({n0(total)})
            </Link>
          ) : (
            <span className="font-mono text-[12px] tabular-nums text-canvas-muted">{n0(total)}</span>
          )}
          <SqlInfo k={k} alan={alan.replace(/\.items\[\]\..*$/, '.total')} label={`${title} · sayı`} />
        </span>
      </div>
      {total ? <ul className="divide-y divide-slate-100">{children}</ul> : <Empty>Şu an bu başlıkta ilgilenilecek kitap yok.</Empty>}
      {total > 8 && <div className="mt-1 text-[11px] text-canvas-muted">En acil 8 kayıt; hepsi «Tümü» sayfasında, sayfalı.</div>}
    </Panel>
  );
}
