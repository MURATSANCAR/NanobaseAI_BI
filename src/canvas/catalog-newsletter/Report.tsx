import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Loading, Note, TableWrap, errText, td, th } from '../admin/ui';
import { Kpi, KpiRow } from '../editorial/kit';
import { cnApi, fmtDay, fmtInt, fmtPct } from './api';
import { Block } from './parts';
import SqlInfo from '../components/SqlInfo';
import { ExplainLabel } from '../components/Explain';

const SOURCE: Record<string, string> = { crm: 'CRM kampanyası', dosya: 'Araç dosyası', elle: 'Elle' };

/** Bülten sonuçları: portalda hazırlanan bültenler (CRM kampanyası ya da araç dosyasından) ve CRM'deki e-posta/SMS kampanyaları. */
export default function Report() {
  const q = useQuery({ queryKey: ['cn', 'report'], queryFn: cnApi.report });
  const r = q.data;
  return (
    <div className="flex flex-col gap-3 lg:gap-4">
      {q.error && <Note tone="err">{errText(q.error, 'Rapor açılamadı.')}</Note>}
      {q.isLoading && <Loading />}
      {r && (
        <>
          <KpiRow>
            <Kpi label="Sonucu olan bülten" value={fmtInt(r.toplam.bulten)} help="Gönderim sayısı girilmiş bültenler" info={<SqlInfo k={r.kaynaklar} alan="toplam" label="Sonucu olan bülten" />} />
            <Kpi label="Gönderilen" value={fmtInt(r.toplam.gonderilen)} help="Bültenlerin son sonuçlarının toplamı" info={<SqlInfo k={r.kaynaklar} alan="toplam" label="Gönderilen" />} />
            <Kpi label="Açılma oranı" value={fmtPct(r.toplam.acilmaOrani)} help="Açılan ÷ gönderilen" info={<SqlInfo k={r.kaynaklar} alan="toplam" label="Açılma oranı" />}
              explain="Bülteni açan kişi sayısının gönderilen kişi sayısına oranı. Bazı e-posta programları açılmayı saymadığı için gerçek oran biraz daha yüksek olabilir." />
            <Kpi label="Tıklama oranı" value={fmtPct(r.toplam.tiklamaOrani)} help="Tıklanan ÷ gönderilen" info={<SqlInfo k={r.kaynaklar} alan="toplam" label="Tıklama oranı" />}
              explain="Bültendeki bir bağlantıya tıklayan kişi sayısının gönderilen kişi sayısına oranı. Bültenin ilgi çekip çekmediğini en iyi bu gösterir." />
          </KpiRow>
          <Block title="Portalda hazırlanan bültenler" info={<SqlInfo k={r.kaynaklar} alan="items[]" label="Bülten sonuçları" />} help="Sonuç, bağlı CRM kampanyasından her sabah okunur ya da e-posta aracının dışa aktarım dosyasından alınır (yalnız toplamlar).">
            {r.items.length === 0 ? (
              <p className="py-4 text-[12.5px] text-canvas-muted">Henüz onaylanmış bülten yok. Bültenler sekmesinden bülten hazırlayıp onaylatınca sonuçları burada görünür.</p>
            ) : (
              <TableWrap>
                <thead><tr>
                  <th className={th}>Bülten</th><th className={th}>Gönderim</th><th className={`${th} text-right`}>Segment</th>
                  <th className={`${th} text-right`}>Gönderilen</th><th className={`${th} text-right`}>Açılma</th>
                  <th className={`${th} text-right`}>Tıklama</th><th className={th}>Kaynak</th>
                </tr></thead>
                <tbody>
                  {r.items.map((i) => (
                    <tr key={i.id} className="border-t border-slate-100">
                      <td className={td}><Link className="font-bold text-canvas-violet hover:underline" to={`/katalog-bulten/bulten/${encodeURIComponent(i.id)}`}>{i.baslik}</Link>
                        <div className="text-[11px] text-canvas-muted">{i.durumAdi}</div></td>
                      <td className={td}>{fmtDay(i.gonderimTarihi)}</td>
                      <td className={`${td} text-right font-mono tabular-nums`}>{fmtInt(i.segmentBuyuklugu)}</td>
                      <td className={`${td} text-right font-mono tabular-nums`}>{fmtInt(i.sonuc?.gonderilen)}</td>
                      <td className={`${td} text-right font-mono tabular-nums`}>{fmtPct(i.sonuc?.acilmaOrani)}</td>
                      <td className={`${td} text-right font-mono tabular-nums`}>{fmtPct(i.sonuc?.tiklamaOrani)}</td>
                      <td className={td}>{i.sonuc ? SOURCE[i.sonuc.kaynak] : 'sonuç yok'}</td>
                    </tr>
                  ))}
                </tbody>
              </TableWrap>
            )}
          </Block>
          <Block title="CRM e-posta ve SMS kampanyaları" info={<SqlInfo k={r.kaynaklar} alan="crm[]" label="CRM kampanya sayaçları" />} help="CRM'deki kampanya kayıtlarının sayaçları (yalnız okuma). Kayıt sayısı küçükse bugün başka bir gönderim aracı kullanılıyor olabilir.">
            {r.crmHata && <Note tone="warn">CRM okunamadı: {r.crmHata}</Note>}
            {r.crm && r.crm.length === 0 && <p className="py-4 text-[12.5px] text-canvas-muted">CRM'de kampanya kaydı yok.</p>}
            {r.crm && r.crm.length > 0 && (
              <TableWrap>
                <thead><tr>
                  <th className={th}>Kampanya</th><th className={th}>Tür</th><th className={th}>Başlangıç</th>
                  <th className={`${th} text-right`}>Gönderim</th><th className={`${th} text-right`}>Okunan</th>
                  <th className={`${th} text-right`}>Tıklanan</th><th className={`${th} text-right`}><ExplainLabel label="Kara liste">CRM kampanya kartındaki «Kara Liste Adedi»: kara listede olduğu için bu gönderimin ulaşmadığı alıcı sayısı.</ExplainLabel></th><th className={th}>Son gönderim kaydı</th>
                </tr></thead>
                <tbody>
                  {r.crm.map((c) => (
                    <tr key={c.id} className="border-t border-slate-100">
                      <td className={td}><span className="font-bold">{c.ad ?? '—'}</span>{!c.etkin && <div className="text-[11px] text-canvas-muted">etkin değil</div>}</td>
                      <td className={td}>{c.tur ?? '—'}</td>
                      <td className={td}>{fmtDay(c.baslangic ?? c.olusturma)}</td>
                      <td className={`${td} text-right font-mono tabular-nums`}>{fmtInt(c.toplam)}</td>
                      <td className={`${td} text-right font-mono tabular-nums`}>{fmtInt(c.okunan)}</td>
                      <td className={`${td} text-right font-mono tabular-nums`}>{fmtInt(c.tiklanan)}</td>
                      <td className={`${td} text-right font-mono tabular-nums`}>{fmtInt(c.karaListe)}</td>
                      <td className={td}>{fmtDay(c.sonGonderim)}</td>
                    </tr>
                  ))}
                </tbody>
              </TableWrap>
            )}
          </Block>
        </>
      )}
    </div>
  );
}
