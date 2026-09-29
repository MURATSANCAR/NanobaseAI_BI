import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { ChevronRight, Download } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import { Loading, Note, Pill, TableWrap, btnGhost, btnPrimary, errText, td, th } from '../admin/ui';
import { Kpi, KpiRow, Panel } from '../editorial/kit';
import { Explain } from '../components/Explain';
import SqlInfo, { InfoLabel } from '../components/SqlInfo';
import type { Kaynaklar } from '../components/sqlInfo';
import { fmtDay, fmtMoney, fmtPct, fmtShort } from '../budget/api';
import { channelsApi, coverageText, platformName, type ChannelsMeta, type PlatformCard, type Suggestion } from './api';
import { AskSheet, ChannelsFrame, DataBar, Facts, PeriodPicker, deltaTone, signedPct, useChannelsMeta, usePeriod } from './parts';

/** M42 kanal karnesi (/kanallar): platform kartları (kanala satış, iskonto, iade, marj, hedef), kanallar arası kıyas,
 * uyarılar ve karar bekleyen öneriler. */

function PlatformTile({ c, canMargin, k }: { c: PlatformCard; canMargin: boolean; k?: Kaynaklar }) {
  const d = c.donem;
  const unmapped = c.platform === 'eslenmemis';
  const to = unmapped ? '/kanallar/eslesme' : `/kanallar/${encodeURIComponent(c.platform)}`;
  // «i» kartın bağlantısının dışında (iç içe etkileşim olmasın): kart göreli kutuda, «i» sağ üstte okun solunda.
  return (
    <div className="relative">
    <Link
      to={to}
      className="glass-panel group flex h-full flex-col gap-2 rounded-2xl p-3.5 text-left shadow-glass-float transition-transform duration-150 ease-out active:scale-[0.98] sm:rounded-3xl sm:p-4"
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="truncate pr-6 text-[15px] font-extrabold">{c.label}</div>
          <div className="text-[11px] font-semibold text-canvas-muted">
            {unmapped ? 'Platforma bağlanmamış e-ticaret carileri' : `${c.grupSayisi} cari / kanal kodu`}
          </div>
        </div>
        <ChevronRight aria-hidden className="mt-1 h-4 w-4 shrink-0 text-canvas-muted" />
      </div>
      <div>
        <div className="font-mono text-[26px] font-bold leading-none tabular-nums tracking-tight">{fmtShort(d.netCiro)} ₺</div>
        <div className="mt-1 text-[11.5px] font-semibold">
          <span className={deltaTone(c.degisim)}>{signedPct(c.degisim)}</span>
          <span className="text-canvas-muted"> geçen yılın aynı dönemine göre · e-ticaretin {fmtPct(c.payEticaret, 0)}'i</span>
        </div>
      </div>
      <Facts
        rows={[
          ['İskonto oranı', fmtPct(d.iskontoOrani)],
          ['İade oranı', fmtPct(d.iadeOrani)],
          ...(canMargin ? ([['Brüt marj', fmtPct(d.marj ?? null)], ['İade sonrası marj', fmtPct(d.iadeSonrasiMarj ?? null)]] as Array<[string, string]>) : []),
          ...(c.hedef ? ([['CRM hedef gerçekleşme', fmtPct(c.hedef.oran, 0)]] as Array<[string, string]>) : []),
        ]}
      />
      {canMargin && d.maliyetsizSatir > 0 && <p className="text-[11px] leading-snug text-canvas-muted">{coverageText(d)}</p>}
    </Link>
    <span className="absolute right-9 top-3.5 sm:top-4"><SqlInfo k={k} alan="platforms" label={`${c.label}: kanal ölçüleri`} /></span>
    </div>
  );
}

function Suggestions({ meta }: { meta: ChannelsMeta }) {
  const qc = useQueryClient();
  const [ask, setAsk] = useState<{ s: Suggestion; karar: 'onayli' | 'red' } | null>(null);
  const q = useQuery({ queryKey: ['channels', 'suggestions', 'taslak'], queryFn: () => channelsApi.suggestions({ durum: 'taslak' }), enabled: ENGINE_ENABLED });
  const act = useMutation({
    mutationFn: ({ s, karar, not }: { s: Suggestion; karar: 'onayli' | 'red'; not?: string }) => channelsApi.decide(s.id, karar, not),
    onSuccess: (_, v) => {
      setAsk(null);
      qc.invalidateQueries({ queryKey: ['channels', 'suggestions'] });
      toast.success(v.karar === 'onayli' ? 'Öneri onaylandı (portal kaydı; hiçbir platforma gönderilmez).' : 'Öneri gerekçesiyle reddedildi.');
    },
    onError: (e) => toast.error(errText(e, 'Karar kaydedilemedi.') ?? ''),
  });
  const items = q.data?.items ?? [];
  if (!q.isLoading && !items.length) return null;
  return (
    <Panel>
      <h2 className="flex items-center gap-1 text-[15px] font-extrabold">Karar bekleyen öneriler <SqlInfo k={q.data?.kaynaklar} alan="items" label="Karar bekleyen öneriler" /></h2>
      <p className="mb-2 text-[12px] text-canvas-muted">Ekibin hazırladığı iskonto, stok payı ve timas.com.tr set önerileri. Onay yalnız portalda kayıt olur; pazar yerine, siteye ya da CRM'e gönderilmez, uygulamayı ekip yapar. Kendi önerinize başka bir yetkili karar verir.</p>
      {q.isLoading ? <Loading /> : (
        <ul className="flex flex-col gap-2">
          {items.map((s) => {
            const mine = s.olusturan.toLowerCase() === meta.me.username.toLowerCase();
            return (
              <li key={s.id} className="flex flex-col gap-2 rounded-xl bg-white/70 px-3 py-2 sm:flex-row sm:items-center sm:justify-between">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-1.5">
                    <Pill tone="violet">{meta.suggestionTypes[s.tur] ?? s.tur}</Pill>
                    <span className="text-[13px] font-bold">{s.baslik}</span>
                  </div>
                  <div className="text-[11.5px] text-canvas-muted">{s.olusturan} · {fmtDay(s.olusturma)} · {platformName(meta, s.platform)}</div>
                  {s.gerekce && <p className="mt-1 text-[12px] leading-snug">{s.gerekce}</p>}
                </div>
                {meta.me.canDecide && !mine && (
                  <div className="flex shrink-0 gap-2">
                    <button type="button" className={btnGhost} onClick={() => setAsk({ s, karar: 'red' })}>Reddet</button>
                    <button type="button" className={btnPrimary} onClick={() => setAsk({ s, karar: 'onayli' })}>Onayla</button>
                  </div>
                )}
                {meta.me.canDecide && mine && <span className="text-[11.5px] font-semibold text-canvas-muted">Kararı başka bir yetkili verir.</span>}
              </li>
            );
          })}
        </ul>
      )}
      <AskSheet
        open={!!ask}
        busy={act.isPending}
        title={ask?.karar === 'red' ? 'Öneriyi reddet' : 'Öneriyi onayla'}
        message={ask ? <><strong>{ask.s.baslik}</strong><br />Onay yalnız portalda kayıt olur; uygulama (sözleşme, kampanya) ekibin işidir.</> : ''}
        confirm={ask?.karar === 'red' ? 'Reddet' : 'Onayla'}
        danger={ask?.karar === 'red'}
        input={ask?.karar === 'red' ? 'Gerekçe' : 'Not (isteğe bağlı)'}
        required={ask?.karar === 'red'}
        onClose={() => setAsk(null)}
        onConfirm={(text) => ask && act.mutate({ s: ask.s, karar: ask.karar, not: text || undefined })}
      />
    </Panel>
  );
}

export default function ChannelsHome() {
  const meta = useChannelsMeta();
  const m = meta.data;
  const { yil, ay, set } = usePeriod(m);
  const q = useQuery({
    queryKey: ['channels', 'scorecard', yil, ay],
    queryFn: () => channelsApi.scorecard({ yil, ay }),
    enabled: ENGINE_ENABLED && !!m && !!yil && !!m.years.length,
  });
  const d = q.data;
  const canMargin = !!m?.me.canMargin;
  const t = d?.toplam;
  const eticDelta = t?.eticaretGecenYil ? t.eticaret.netCiro / (t.eticaretGecenYil.netCiro || NaN) - 1 : null;

  const aside = (
    <div className="flex flex-col gap-2">
      <PeriodPicker meta={m} yil={yil} ay={ay} onChange={set} />
      {m?.me.canExport && d && (
        <a className={btnGhost} href={channelsApi.exportUrl('karne', { yil, ay })} download>
          <Download aria-hidden className="h-4 w-4" />
          Karneyi indir
        </a>
      )}
    </div>
  );

  return (
    <ChannelsFrame
      title="Kanal karnesi"
      lead="Her pazar yerine ve timas.com.tr'ye ne kadar sattığımızı, ne kadar iskonto verdiğimizi, ne kadarının iade geldiğini ve hedefin neresinde olduğumuzu gösterir. Rakamlar Logo faturalarından gelir; hangi carinin hangi platform olduğu «Cari eşleme» sekmesinde belirlenir."
      aside={aside}
    >
      <DataBar meta={m} yil={yil} />
      {m && !m.years.length && !m.data.running && <Note tone="info">Kanal verisi henüz Logo'dan okunmadı. «Veriyi yenile» ile ilk okuma başlar (birkaç dakika sürebilir).</Note>}
      {q.error && <Note tone="err">{errText(q.error, 'Karne hesaplanamadı.')}</Note>}
      {m?.alerts.items && m.alerts.items.length > 0 && (
        <Note tone="warn">
          <SqlInfo k={m.kaynaklar} alan="alerts" label="Kanal uyarıları" className="mr-1" />
          <strong>Uyarılar ({fmtDay(m.alerts.tarih)}):</strong> {m.alerts.items.map((a) => a.metin).join(' · ')}
        </Note>
      )}
      {q.isLoading && <Loading />}
      {d && t && (
        <>
          <p className="px-1 text-[12px] font-semibold text-canvas-muted">
            <SqlInfo k={d.kaynaklar} alan="period" label="Dönem ve veri sonu" className="mr-1" />
            {d.period.yil} Ocak–{d.period.ayAdi}
            {d.period.kismiAy && <> · son ay {fmtDay(d.period.veriSonu)} tarihine kadar; geçen yılın aynı ayı gün oranıyla kıyaslanır</>}
            {!d.gecenYilOkundu && <> · geçen yıl okunmadı, kıyas yok</>}
          </p>
          <KpiRow>
            <Kpi label="E-ticaret net ciro" value={`${fmtShort(t.eticaret.netCiro)} ₺`} help={`Geçen yıla göre ${signedPct(eticDelta)} · kanala satış − iade`}
              explain="Platforma bağlanmış bütün e-ticaret carilerine kesilen satış faturaları eksi iade faturaları (satır tutarı). Pazar yerinin okura sattığı değil, bizim pazar yerine sattığımızdır."
              info={<SqlInfo k={d.kaynaklar} alan="toplam" label="E-ticaret net ciro" />} />
            <Kpi label="Şirket içindeki pay" value={fmtPct(t.eticaretPay)} help={`Şirket net cirosu ${fmtShort(t.sirket.netCiro)} ₺`}
              explain="E-ticaret net cirosunun, aynı dönemde şirketin bütün kanallardaki (kitapçı, dağıtıcı, e-ticaret…) net cirosuna oranı."
              info={<SqlInfo k={d.kaynaklar} alan="toplam" label="Şirket içindeki pay" />} />
            <Kpi label="timas.com.tr payı" value={fmtPct(t.d2cPay)} help="Kendi sitemizin e-ticaret içindeki payı"
              explain="Okura doğrudan sattığımız (D2C) timas.com.tr'nin net cirosunun, e-ticaret net cirosu içindeki payı."
              info={<SqlInfo k={d.kaynaklar} alan="toplam" label="D2C payı" />} />
            <Kpi
              label={canMargin ? 'E-ticaret brüt marjı' : 'E-ticaret iade oranı'}
              value={canMargin ? fmtPct(t.eticaret.marj ?? null) : fmtPct(t.eticaret.iadeOrani)}
              help={canMargin ? coverageText(t.eticaret) : `İskonto oranı ${fmtPct(t.eticaret.iskontoOrani)}`}
              explain={canMargin
                ? 'Satıştan kalan brüt kârın satışa oranı (1 − maliyet ÷ ciro). Yalnız Logo’da maliyeti girilmiş satırlarla hesaplanır; maliyetsiz satırlar altta ayrıca yazılır, marja katılmaz.'
                : 'İade faturası tutarının satış faturası tutarına oranı. Yükselmesi, kanalın kitapları satamayıp geri gönderdiğini gösterir.'}
              info={<SqlInfo k={d.kaynaklar} alan="toplam" label={canMargin ? 'E-ticaret brüt marjı' : 'E-ticaret iade oranı'} />}
            />
          </KpiRow>

          <div className="flex items-center gap-1 px-1">
            <h2 className="text-[15px] font-extrabold">Platformlar</h2>
            <Explain label="Platform kartları" title="Kartlardaki oranlar">
              <span className="block"><b>İskonto oranı:</b> faturada kanala yapılan indirimin, indirimsiz satış tutarına oranı.</span>
              <span className="block"><b>İade oranı:</b> iade faturası tutarının satış faturası tutarına oranı.</span>
              <span className="block"><b>Brüt marj:</b> maliyeti bilinen satışlarda kalan brüt kârın satışa oranı; «iade sonrası» olanda iadeler de düşülür.</span>
              <span className="block"><b>CRM hedef gerçekleşme:</b> CRM'deki bölge satış hedefinin (adet) bugüne düşen payının ne kadarı satıldı.</span>
              Karta dokunursanız platformun ay ay ve cari cari ayrıntısı açılır.
            </Explain>
          </div>
          <section className="grid grid-cols-1 gap-2.5 sm:grid-cols-2 lg:grid-cols-3 lg:gap-4 2xl:grid-cols-4">
            {d.platforms.map((c) => <PlatformTile key={c.platform} c={c} canMargin={canMargin} k={d.kaynaklar} />)}
          </section>
          {d.platformDisi.donem && (
            <p className="px-1 text-[12px] text-canvas-muted">
              «Platform değil» işaretlenen {d.platformDisi.grupSayisi} e-ticaret kodlu carinin net cirosu ({fmtMoney(d.platformDisi.donem.netCiro)}) karneye ve e-ticaret toplamına girmez.
              <SqlInfo k={d.kaynaklar} alan="platformDisi" label="Platform dışı cariler" className="ml-1" />
            </p>
          )}

          <Panel>
            <h2 className="flex items-center gap-1 text-[15px] font-extrabold">Kanallar arası kıyas <SqlInfo k={d.kaynaklar} alan="kanallar" label="Kanallar arası kıyas" /></h2>
            <p className="mb-2 text-[12px] text-canvas-muted">Şirketin bütün satışı, Logo cari kartındaki kanal koduna göre (kitapçı, dağıtıcı, e-ticaret …). E-ticaretin öteki kanallara göre ne kadar iskonto verip ne kadar iade aldığını buradan kıyaslayabilirsiniz; hesap platform kartlarıyla aynıdır.</p>
            <TableWrap>
              <thead>
                <tr>
                  <th className={th}>Kanal kodu</th>
                  <th className={`${th} text-right`}><InfoLabel k={d.kaynaklar} alan="kanallar">Net ciro</InfoLabel></th>
                  <th className={`${th} text-right`}><InfoLabel k={d.kaynaklar} alan="kanallar">Şirket payı</InfoLabel></th>
                  <th className={`${th} text-right`}><InfoLabel k={d.kaynaklar} alan="kanallar">İskonto oranı</InfoLabel></th>
                  <th className={`${th} text-right`}><InfoLabel k={d.kaynaklar} alan="kanallar">İade oranı</InfoLabel></th>
                  {canMargin && <th className={`${th} text-right`}><InfoLabel k={d.kaynaklar} alan="kanallar">Brüt marj</InfoLabel></th>}
                  {canMargin && (
                    <th className={`${th} text-right`}>
                      <span className="inline-flex items-center gap-1">
                        <InfoLabel k={d.kaynaklar} alan="kanallar">Maliyetli ciro payı</InfoLabel>
                        <Explain label="Maliyetli ciro payı">Satış tutarının ne kadarında Logo’da maliyet girilmiş. Bu oran düşükse brüt marj kanalın yalnız küçük bir kısmını yansıtır.</Explain>
                      </span>
                    </th>
                  )}
                </tr>
              </thead>
              <tbody>
                {d.kanallar.map((k) => (
                  <tr key={k.kanal} className="border-t border-slate-100">
                    <td className={`${td} font-semibold`}>{k.kanal === '#YOK' ? 'Kodsuz' : k.kanal}{m?.settings.specodes.includes(k.kanal) && <span className="ml-1.5"><Pill tone="violet">e-ticaret</Pill></span>}</td>
                    <td className={`${td} text-right font-mono tabular-nums`}>{fmtMoney(k.donem.netCiro)}</td>
                    <td className={`${td} text-right font-mono tabular-nums`}>{fmtPct(k.paySirket)}</td>
                    <td className={`${td} text-right font-mono tabular-nums`}>{fmtPct(k.donem.iskontoOrani)}</td>
                    <td className={`${td} text-right font-mono tabular-nums`}>{fmtPct(k.donem.iadeOrani)}</td>
                    {canMargin && <td className={`${td} text-right font-mono tabular-nums`}>{fmtPct(k.donem.marj ?? null)}</td>}
                    {canMargin && <td className={`${td} text-right font-mono tabular-nums`}>{fmtPct(k.donem.maliyetKapsami ?? null, 0)}</td>}
                  </tr>
                ))}
              </tbody>
            </TableWrap>
          </Panel>
        </>
      )}
      {m && <Suggestions meta={m} />}
    </ChannelsFrame>
  );
}
