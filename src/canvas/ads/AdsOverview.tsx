import { useState } from 'react';
import { Link } from 'react-router-dom';
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { FileSpreadsheet, FileText, RefreshCw, Sparkles, Upload } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import SqlInfo from '../components/SqlInfo';
import { Explain } from '../components/Explain';
import { Loading, Note, Pill, TableWrap, btnGhost, errText, td, th } from '../admin/ui';
import { Kpi, KpiRow, Panel } from '../editorial/kit';
import { Block } from '../marketing/parts';
import { LINK_TONE, adsApi, fmtDay, fmtInt, fmtMoney, fmtMoney2, fmtPct, fmtRatio, type Overview } from './api';
import { AdsFrame, DataEnd, PeriodPicker, SuggestionCard, useAdsMeta, usePeriod } from './parts';

/** M21 ilk açılış: dönem + dört gösterge, kanal ve kampanya tablosu, kitap bazında harcama ↔ e-ticaret cirosu, öneriler. */
export default function AdsOverview() {
  const qc = useQueryClient();
  const meta = useAdsMeta();
  const m = meta.data;
  const [period, setPeriod] = usePeriod();
  const [comment, setComment] = useState<string | null>(null);
  const ov = useQuery({
    queryKey: ['ads', 'overview', period],
    queryFn: () => adsApi.overview(period),
    enabled: ENGINE_ENABLED && !!m,
    placeholderData: keepPreviousData,
  });
  const refresh = useMutation({
    mutationFn: adsApi.refresh,
    onSuccess: (r) => {
      toast.success(r.basladi ? 'Satış verisi yenileniyor; birkaç dakika sürebilir.' : r.not ?? 'Yenileme sürüyor.');
      qc.invalidateQueries({ queryKey: ['ads', 'meta'] });
    },
    onError: (e) => toast.error(errText(e, 'Yenileme başlatılamadı.') ?? ''),
  });
  const summary = useMutation({
    mutationFn: () => adsApi.summary(period),
    onSuccess: (r) => {
      setComment(r.metin);
      if (!r.metin) toast.error('Zeki AI yorumu denetimden geçmedi; rakamlar raporda aynen duruyor.');
    },
    onError: (e) => toast.error(errText(e, 'Yorum yazılamadı.') ?? ''),
  });
  const d = ov.data;
  const g = d?.gosterge;

  const aside = m ? (
    <div className="flex flex-col gap-2">
      <PeriodPicker period={period} onChange={setPeriod} meta={m} />
      <div className="flex flex-wrap gap-1.5">
        {m.me.canEdit && (
          <Link to="/reklam/yukle" className={btnGhost}><Upload aria-hidden className="h-4 w-4" />Dosya yükle</Link>
        )}
        {m.me.canEdit && (
          <button type="button" className={btnGhost} onClick={() => refresh.mutate()} disabled={refresh.isPending || m.refresh?.durum === 'calisiyor'}>
            <RefreshCw aria-hidden className="h-4 w-4" />Satış verisini yenile
          </button>
        )}
        {m.me.canExport && (
          <>
            <a className={btnGhost} href={adsApi.pdfUrl(period)} download><FileText aria-hidden className="h-4 w-4" />PDF indir</a>
            <a className={btnGhost} href={adsApi.xlsxUrl(period)} download><FileSpreadsheet aria-hidden className="h-4 w-4" />Excel indir</a>
          </>
        )}
      </div>
    </div>
  ) : null;

  return (
    <AdsFrame
      title="Dijital pazarlama ve reklam"
      lead="Google, Meta, TikTok gibi bütün reklam kanallarının harcaması tek yerde ve kitap kitap Logo'daki e-ticaret satışıyla yan yana. Veriyi platformdan indirdiğiniz raporla yüklersiniz; Zeki AI önerir, para kararını pazarlama müdürü verir. Portal reklam hesaplarında hiçbir değişiklik yapmaz."
      meta={m}
      aside={aside}
    >
      {meta.error && <Note tone="err">{errText(meta.error, 'Reklam bilgisi açılamadı.')}</Note>}
      <DataEnd meta={m} verimDonemi={d ? d.verimDonemi : undefined} />
      {d?.uyarilar.map((u) => <Note key={u} tone="warn">{u}</Note>)}
      {m && m.accounts.length === 0 && (
        <Note tone="info">
          Henüz reklam verisi yok. Platformun raporunu (günlük kırılımlı CSV ya da Excel) <Link className="underline" to="/reklam/yukle">Veri yükle</Link> ekranından yükleyin.
        </Note>
      )}
      {ov.error && <Note tone="err">{errText(ov.error, 'Özet açılamadı.')}</Note>}
      {ov.isLoading && <Loading />}

      {g && d && (
        <KpiRow>
          <Kpi label="Harcama" value={fmtMoney(g.harcama)} help={`${fmtInt(g.tiklama)} tıklama · TBM ${fmtMoney2(g.tbm)}`} info={<SqlInfo k={d.kaynaklar} alan="kanallar" label="Harcama, tıklama, TBM" />}
            explain="Seçili dönemde bütün reklam kanallarına harcanan tutar (TL). Alt satırdaki TBM, tıklama başı maliyettir: harcama ÷ tıklama." />
          <Kpi label="Platform ROAS" value={fmtRatio(g.platformRoas)} help={`Platformun bildirdiği dönüşüm değeri ${fmtMoney(g.donusumDegeri)}; gerçek getiri değildir`} info={<SqlInfo k={d.kaynaklar} alan="kanallar" label="Platform ROAS" />}
            explain="Reklam platformunun kendi bildirdiği satış değerinin harcamaya bölümü (ör. 3,0 = her 1 ₺ için 3 ₺). Platform kendi payını geniş sayar; gerçek getiri için «Pazarlama verimi»ne bakın." />
          <Kpi label="E-ticaret net ciro" value={fmtMoney(g.eticaretCiro)} help={d.verimDonemi ? `Logo, ${fmtDay(d.verimDonemi.bas)} – ${fmtDay(d.verimDonemi.bit)}` : 'Bu dönemde Logo satış verisi yok'} info={<SqlInfo k={d.kaynaklar} alan="gosterge" label="E-ticaret net ciro" />}
            explain="Aynı günlerde Logo'ya işlenmiş e-ticaret satışının iadesi düşülmüş tutarı. Logo verisi geriden gelir; hangi günlere kadar olduğu alt satırda yazar." />
          <Kpi label="Pazarlama verimi" value={fmtRatio(g.verim)} help={d.verimDonemi ? `E-ticaret ciro ÷ aynı günlerin harcaması (${fmtMoney(g.harcamaVeriIcinde)})` : 'Satış verisi olan günlerde hesaplanır'} info={<SqlInfo k={d.kaynaklar} alan="gosterge" label="Pazarlama verimi" />}
            explain="Logo e-ticaret net cirosunun, aynı günlerdeki reklam harcamasına bölümü. Yalnız Logo satış verisi olan günler hesaba girer. Satışa reklam dışı etkiler de karışır; neden-sonuç göstermez." />
        </KpiRow>
      )}

      {d && (
        <div className="grid grid-cols-1 gap-3 xl:grid-cols-[minmax(0,1fr)_380px] xl:gap-4">
          <div className="flex min-w-0 flex-col gap-3 lg:gap-4">
            <Block title="Kanallar" info={<SqlInfo k={d.kaynaklar} alan="kanallar" label="Kanallar ve bağsız harcama" />} help={`Kitaba bağlanmamış kampanyaların harcaması ${fmtMoney(d.bagsiz.harcama)} (${fmtPct(d.bagsiz.pay)}); bu harcama kitap verimine girmez. Hedef: %10'un altı.`}>
              {Object.keys(d.digerParaBirimi).length > 0 && (
                <Note tone="warn">TL dışı harcama toplama katılmadı: {Object.entries(d.digerParaBirimi).map(([k, v]) => `${k} ${v.toLocaleString('tr-TR')}`).join(', ')}</Note>
              )}
              <ChannelTable d={d} />
            </Block>
            <Block title="Kitaplar" info={<SqlInfo k={d.kaynaklar} alan="kitaplar" label="Kitaplar: harcama, e-ticaret ciro, verim, stok, plan" />} help="Kitaba bağlı kampanyaların harcaması, kitabın aynı günlerdeki Logo e-ticaret cirosu ve stok durumu. Son sütun, kitabın onaylı pazarlama planında reklama ayrılan tutardır. Stok kırmızıysa reklam stok bitene kadar sürmeyebilir.">
              <BookTable d={d} stockDays={m?.settings.stockDays ?? null} />
            </Block>
            <Block title="Kampanyalar" info={<SqlInfo k={d.kaynaklar} alan="kampanyalar" label="Kampanyalar" />} help="Harcamaya göre sıralı. Bağ ve kitap seçimi Kampanyalar ekranında." action={<Link to="/reklam/kampanyalar" className={btnGhost}>Kampanyalar</Link>}>
              <CampaignTable d={d} />
            </Block>
          </div>
          <aside className="flex min-w-0 flex-col gap-3">
            <Panel>
              <h2 className="flex items-center gap-1 text-[15px] font-extrabold tracking-tight">Öneriler ve uyarılar<SqlInfo k={d.kaynaklar} alan="oneriler" label="Öneriler" /></h2>
              <p className="mt-0.5 text-[11.5px] leading-snug text-canvas-muted">Kurallar her sabah çalışır; eşiği girilmeyen kural kapalıdır (Yönetim → Dijital pazarlama ve reklam).</p>
              <div className="mt-2 flex flex-col gap-2">
                {d.oneriler.length === 0 && <p className="py-3 text-[12px] text-canvas-muted">Açık öneri yok. Kurallar her sabah yeniden bakar; stok, satış dışı kitap ya da bütçe aşımı olursa burada görünür.</p>}
                {d.oneriler.map((s) => <SuggestionCard key={s.id} s={s} meta={m} />)}
              </div>
              {m && (
                <p className="mt-2 text-[11px] leading-snug text-canvas-muted">
                  Kapalı kurallar: {Object.entries(m.settings.rules).filter(([, on]) => !on).map(([k]) => m.kinds[k] ?? k).join(', ') || 'yok'}.
                </p>
              )}
            </Panel>
            <Panel>
              <h2 className="text-[15px] font-extrabold tracking-tight">Zeki AI yorumu</h2>
              <p className="mt-0.5 text-[11.5px] leading-snug text-canvas-muted">Hesaplanmış rakamlara beş cümlelik yorum; yeni rakam yazmaz. PDF raporuna girer.</p>
              {comment && <p className="mt-2 whitespace-pre-line text-[12.5px] leading-snug">{comment}</p>}
              <button type="button" className={`${btnGhost} mt-2`} disabled={summary.isPending || !m?.modelReady} onClick={() => summary.mutate()}>
                <Sparkles aria-hidden className="h-4 w-4" />{summary.isPending ? 'Yazılıyor…' : 'Yorum yaz'}
              </button>
            </Panel>
          </aside>
        </div>
      )}
    </AdsFrame>
  );
}

function ChannelTable({ d }: { d: Overview }) {
  if (!d.kanallar.length) return <p className="py-3 text-[12px] text-canvas-muted">Bu dönemde harcama yok. Dönemi değiştirin ya da platform raporunu «Veri yükle» ekranından yükleyin.</p>;
  return (
    <TableWrap>
      <thead>
        <tr><th className={th}>Kanal</th><th className={`${th} text-right`}>Harcama</th><th className={`${th} text-right`}>Pay</th><th className={`${th} text-right`}>Tıklama</th><th className={`${th} text-right`}><span className="inline-flex items-center justify-end gap-1">TBM<Explain label="TBM" title="Tıklama başı maliyet">Harcamanın tıklama sayısına bölümü: reklama gelen her tıklama için ortalama kaç lira ödendiği.</Explain></span></th><th className={`${th} text-right`}><span className="inline-flex items-center justify-end gap-1">Platform ROAS<Explain label="Platform ROAS" title="Platformun bildirdiği getiri">Reklam platformunun kendi saydığı satış değerinin harcamaya bölümü. Platform kendi reklamının payını geniş sayar; gerçek satış için «Pazarlama verimi»ne bakın.</Explain></span></th></tr>
      </thead>
      <tbody className="font-mono tabular-nums">
        {d.kanallar.map((c) => (
          <tr key={c.kanal} className="border-t border-slate-100">
            <td className={`${td} font-sans font-bold`}>{c.kanalAdi}</td>
            <td className={`${td} text-right`}>{fmtMoney(c.harcama)}</td>
            <td className={`${td} text-right`}>{fmtPct(c.pay)}</td>
            <td className={`${td} text-right`}>{fmtInt(c.tiklama)}</td>
            <td className={`${td} text-right`}>{fmtMoney2(c.tbm)}</td>
            <td className={`${td} text-right`}>{fmtRatio(c.platformRoas)}</td>
          </tr>
        ))}
      </tbody>
    </TableWrap>
  );
}

function BookTable({ d, stockDays }: { d: Overview; stockDays: number | null }) {
  if (!d.kitaplar.length) return <p className="py-3 text-[12px] text-canvas-muted">Bu dönemde kitaba bağlı kampanya harcaması yok. Kampanyaları Kampanyalar ekranında kitaba bağlayın.</p>;
  return (
    <TableWrap>
      <thead>
        <tr>
          <th className={th}>Kitap</th><th className={`${th} text-right`}>Harcama</th><th className={`${th} text-right`}>E-ticaret ciro</th>
          <th className={`${th} text-right`}><span className="inline-flex items-center justify-end gap-1">Verim<Explain label="Verim">Kitabın Logo e-ticaret cirosunun, kitaba bağlı reklam harcamasına bölümü (aynı günler).</Explain></span></th><th className={`${th} text-right`}>Stok</th><th className={`${th} text-right`}>Plandaki reklam bütçesi</th>
        </tr>
      </thead>
      <tbody>
        {d.kitaplar.map((k) => {
          const s = k.stok;
          const low = s && (s.bakiye <= 0 || (stockDays !== null && s.gun !== null && s.gun < stockDays));
          return (
            <tr key={k.stokKodu} className="border-t border-slate-100">
              <td className={td}>
                <div className="font-bold">{k.ad ?? k.stokKodu}</div>
                <div className="flex flex-wrap items-center gap-1 text-[11px] text-canvas-muted">
                  <span className="font-mono">{k.stokKodu}</span> · {k.kampanya} kampanya
                  {k.satisDisi && <Pill tone="err">{k.yayinDurumu ?? 'satış dışı'}</Pill>}
                </div>
              </td>
              <td className={`${td} text-right font-mono tabular-nums`}>{fmtMoney(k.harcama)}</td>
              <td className={`${td} text-right font-mono tabular-nums`}>{k.satis ? fmtMoney(k.satis.eticaretCiro) : '—'}</td>
              <td className={`${td} text-right font-mono tabular-nums`}>{fmtRatio(k.verim)}</td>
              <td className={`${td} text-right`}>
                {s ? (
                  <span className={`font-mono tabular-nums ${low ? 'font-bold text-red-700' : ''}`}>
                    {fmtInt(s.bakiye)}{s.gun !== null ? ` · ${fmtInt(s.gun)} gün` : ''}
                  </span>
                ) : '—'}
              </td>
              <td className={`${td} text-right font-mono tabular-nums`}>{k.m15 ? fmtMoney(k.m15.tutar) : '—'}</td>
            </tr>
          );
        })}
      </tbody>
    </TableWrap>
  );
}

function CampaignTable({ d }: { d: Overview }) {
  if (!d.kampanyalar.length) return <p className="py-3 text-[12px] text-canvas-muted">Bu dönemde kampanya harcaması yok.</p>;
  return (
    <TableWrap>
      <thead>
        <tr>
          <th className={th}>Kampanya</th><th className={th}>Kitap</th><th className={`${th} text-right`}>Harcama</th><th className={`${th} text-right`}>Tıklama</th>
          <th className={`${th} text-right`}><span className="inline-flex items-center justify-end gap-1">TBM<Explain label="TBM" title="Tıklama başı maliyet">Harcamanın tıklama sayısına bölümü: reklama gelen her tıklama için ortalama kaç lira ödendiği.</Explain></span></th><th className={`${th} text-right`}><span className="inline-flex items-center justify-end gap-1">Platform ROAS<Explain label="Platform ROAS" title="Platformun bildirdiği getiri">Reklam platformunun kendi saydığı satış değerinin harcamaya bölümü. Platform kendi reklamının payını geniş sayar; gerçek satış için «Pazarlama verimi»ne bakın.</Explain></span></th>
        </tr>
      </thead>
      <tbody>
        {d.kampanyalar.map((c) => (
          <tr key={c.id} className="border-t border-slate-100">
            <td className={td}>
              <div className="max-w-[340px] break-words font-bold">{c.ad}</div>
              <div className="text-[11px] text-canvas-muted">{c.platformAdi}{c.durum ? ` · ${c.durum}` : ''}</div>
            </td>
            <td className={td}>
              <Pill tone={LINK_TONE[c.bag]}>{c.bagAdi}</Pill>
              {c.kitapAdi && <div className="mt-0.5 max-w-[220px] text-[11.5px]">{c.kitapAdi}</div>}
            </td>
            <td className={`${td} text-right font-mono tabular-nums`}>{fmtMoney(c.harcama)}</td>
            <td className={`${td} text-right font-mono tabular-nums`}>{fmtInt(c.tiklama)}</td>
            <td className={`${td} text-right font-mono tabular-nums`}>{fmtMoney2(c.tbm)}</td>
            <td className={`${td} text-right font-mono tabular-nums`}>{fmtRatio(c.platformRoas)}</td>
          </tr>
        ))}
      </tbody>
    </TableWrap>
  );
}
