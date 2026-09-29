import { Link } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { ENGINE_ENABLED } from '../../engine';
import { Loading, Note, Pill, TableWrap, btnGhost, errText, td, th } from '../../admin/ui';
import { Kpi, KpiRow, Panel } from '../../editorial/kit';
import { fmtDay, fmtInt, fmtPct, fmtShort } from '../../budget/api';
import { signedPct } from '../parts';
import { trendyolApi, type Candidate } from './api';
import { TrendyolData, TrendyolFrame, useTrendyolMeta } from './parts';
import SqlInfo, { InfoLabel } from '../../components/SqlInfo';
import { EmptyHint, ExplainLabel } from '../../components/Explain';

const CAND: Record<Candidate['durum'], { label: string; tone: 'ok' | 'warn' | 'muted' | 'violet' | 'err' }> = {
  onayli: { label: 'Trendyol olarak onaylı', tone: 'ok' },
  aday: { label: 'Aday — onay bekliyor', tone: 'violet' },
  bekliyor: { label: 'Eşleme listesinde', tone: 'muted' },
  'listede-yok': { label: 'Eşleme listesinde yok', tone: 'warn' },
  'baska-platform': { label: 'Başka platforma bağlı', tone: 'muted' },
};

function Accounts({ canMap }: { canMap: boolean }) {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ['trendyol', 'accounts'], queryFn: trendyolApi.accounts, enabled: ENGINE_ENABLED });
  const add = useMutation({
    mutationFn: (kod: string) => trendyolApi.addAccount(kod),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['trendyol', 'accounts'] });
      toast.success('Cari eşleme listesine aday olarak eklendi; onay Cari eşleme ekranında.');
    },
    onError: (e) => toast.error(errText(e, 'Eklenemedi.') ?? ''),
  });
  const d = q.data;
  return (
    <Panel>
      <h2 className="flex items-center gap-1 text-[15px] font-extrabold">Logo'da Trendyol adlı cariler <SqlInfo k={d?.kaynaklar} alan="adayCariler" label="Logo'da Trendyol adlı cariler" /></h2>
      <p className="mb-2 text-[12px] text-canvas-muted">
        Logo’da unvanında {d?.desenler?.join(', ') ?? '—'} geçen cariler. Trendyol'a toptan (faturalı) satış varsa fatura bu carilere kesilir; kanal karnesinde
        sayılması için carinin «Cari eşleme» ekranında Trendyol olarak onaylanması gerekir. Liste boşsa bu, Trendyol'a satış olmadığı anlamına gelmez.
      </p>
      {q.isLoading ? <Loading /> : !d?.adayCariler.length ? (
        d?.okundu ? (
          <EmptyHint title="Unvanında Trendyol geçen cari bulunmadı" why="Trendyol’a başka adla fatura kesiliyorsa carisini «Cari eşleme» ekranında elle Trendyol’a bağlayabilirsiniz." />
        ) : (
          <EmptyHint title="Logo carileri henüz okunmadı" why="Üstteki «Veriyi yenile» düğmesi Logo carilerini de okur." />
        )
      ) : (
        <TableWrap>
          <thead><tr><th className={th}>Cari</th><th className={th}>Kanal kodu</th><th className={th}><ExplainLabel label="Eşleme">Cari, kanal karnesinde Trendyol olarak sayılıyor mu? «Aday» onay bekler; «eşleme listesinde yok» olanı aday olarak ekleyebilirsiniz.</ExplainLabel></th><th className={th}><span className="sr-only">İşlem</span></th></tr></thead>
          <tbody>
            {d.adayCariler.map((c) => (
              <tr key={c.cariKodu} className="border-t border-slate-100">
                <td className={td}><div className="font-semibold">{c.unvan ?? '—'}</div><div className="font-mono text-[11px] text-canvas-muted">{c.cariKodu}</div></td>
                <td className={td}>{c.kanal || '—'}</td>
                <td className={td}><Pill tone={CAND[c.durum].tone}>{CAND[c.durum].label}</Pill></td>
                <td className={`${td} text-right`}>
                  {canMap && (c.durum === 'listede-yok' || c.durum === 'bekliyor') && (
                    <button type="button" className={btnGhost} disabled={add.isPending} onClick={() => add.mutate(c.cariKodu)}>Aday olarak ekle</button>
                  )}
                  {c.durum === 'aday' && <Link className="text-[12px] font-bold text-canvas-violet hover:underline" to="/kanallar/eslesme">Onaya git</Link>}
                </td>
              </tr>
            ))}
          </tbody>
        </TableWrap>
      )}
    </Panel>
  );
}

export default function TrendyolHome() {
  const meta = useTrendyolMeta();
  const m = meta.data;
  const q = useQuery({ queryKey: ['trendyol', 'overview'], queryFn: trendyolApi.overview, enabled: ENGINE_ENABLED });
  const d = q.data;
  const w = d?.toptan;
  const diff = d ? Object.values(d.stokFarki).reduce((a, b) => a + b, 0) - (d.stokFarki.eslesmedi ?? 0) : 0;
  return (
    <TrendyolFrame
      title="Trendyol mağazası"
      lead="Trendyol mağazasında bugün ilgilenilmesi gerekenler: depoyla tutmayan stok, cevapsız soru, düşük puanlı yorum ve geciken paket. Bilgi, Trendyol satıcı panelinden indirip yüklediğiniz dosyalardan gelir; mağazaya hiçbir şey gönderilmez, düzeltmeyi panelden siz yaparsınız."
    >
      <TrendyolData meta={m} />
      {q.error && <Note tone="err">{errText(q.error, 'Özet açılamadı.')}</Note>}
      {q.isLoading && <Loading />}
      {d && (
        <>
          <KpiRow>
            <Kpi label="Stok farkı" value={fmtInt(diff)} help={`Satışta ama depoda yok: ${fmtInt(d.stokFarki['trendyolda-var-depoda-yok'] ?? 0)} · depoda var, kapalı: ${fmtInt(d.stokFarki['depoda-var-kapali'] ?? 0)}`}
            explain="Trendyol stoğu ile Logo depo stoğunun tutmadığı ürün sayısı: Trendyol'da satışta ama depoda yok (sipariş iptali riski), depoda var ama Trendyol'da kapalı (kaçan satış) ya da Trendyol stoğu depodan fazla. Ayrıntısı «Ürün, stok, fiyat» sekmesinde."
            info={<SqlInfo k={d?.kaynaklar} alan="stokFarki" label="Stok farkı" />} />
            <Kpi label="Cevapsız soru" value={fmtInt(d.soru.cevapsiz)} help={`${fmtInt(d.soru.geciken)} tanesi ${m?.settings.soruSaat ?? 24} saati geçti`}
            explain="Yüklenen soru dosyalarında cevaplanmamış görünen müşteri soruları. Alttaki sayı, ayarlanan süreden daha uzun süredir bekleyenlerdir."
            info={<SqlInfo k={d?.kaynaklar} alan="soru" label="Cevapsız soru" />} />
            <Kpi label="Düşük puanlı yorum" value={fmtInt(d.yorum.dusuk)} help={`3 ve altı · ortalama ${d.yorum.ortalama ?? '—'} / 5 (${fmtInt(d.yorum.toplam)} yorum)`}
            info={<SqlInfo k={d?.kaynaklar} alan="yorum" label="Düşük puanlı yorum" />} />
            <Kpi label="Geciken paket" value={fmtInt(d.siparis.geciken)} help={`${fmtInt(d.siparis.paket)} paket · ${d.siparis.aralik.bas ? `${fmtDay(d.siparis.aralik.bas)} – ${fmtDay(d.siparis.aralik.bit)}` : 'sipariş dosyası yok'}`}
            explain="Sipariş dosyasında kargoya verme son tarihi geçtiği hâlde henüz kargoya verilmemiş, iptal ya da teslim olmamış paketler."
            info={<SqlInfo k={d?.kaynaklar} alan="siparis" label="Geciken paket" />} />
          </KpiRow>
          <Panel>
            <h2 className="flex items-center gap-1 text-[15px] font-extrabold">Trendyol'a faturalanan (toptan) <SqlInfo k={d?.kaynaklar} alan="toptan" label="Trendyol'a faturalanan (toptan)" /></h2>
            <p className="mb-1 text-[12px] text-canvas-muted">Trendyol'un bizden fatura ile satın aldığı kitaplar (Logo). Mağazadaki okur satışlarından ayrıdır.</p>
            {w?.eslendi && w.netCiro !== undefined ? (
              <p className="text-[12.5px]">
                {w.period?.yil} Ocak–{w.period?.ayAdi}: net <strong>{fmtShort(w.netCiro)} ₺</strong>, {fmtInt(w.netAdet ?? 0)} adet, iade oranı {fmtPct(w.iadeOrani ?? null)},
                geçen yıla göre {signedPct(w.degisim)}. Ayrıntı: <Link className="font-bold text-canvas-violet hover:underline" to="/kanallar/trendyol">kanal karnesi</Link>.
              </p>
            ) : (
              <Note tone="info">{w?.neden ?? '—'}</Note>
            )}
          </Panel>
          <Panel>
            <h2 className="flex items-center gap-1 text-[15px] font-extrabold">Yüklenen dosyalar <SqlInfo k={d?.kaynaklar} alan="yuklemeler" label="Yüklenen dosyalar" /></h2>
            <p className="mb-2 text-[12px] text-canvas-muted">Bu ekrandaki rakamlar ancak en son yüklenen dosyalar kadar günceldir. «Yüklenmedi» yazan türün sekmesi boş kalır.</p>
            <TableWrap>
              <thead><tr><th className={th}>Tür</th><th className={th}>Son dosya</th><th className={`${th} text-right`}><InfoLabel k={d?.kaynaklar} alan="yuklemeler">Satır</InfoLabel></th><th className={th}>Tarih</th></tr></thead>
              <tbody>
                {m && (Object.keys(m.types) as Array<keyof typeof m.types>).map((k) => {
                  const r = d.yuklemeler[k];
                  return (
                    <tr key={k} className="border-t border-slate-100">
                      <td className={`${td} font-semibold`}>{m.types[k]}</td>
                      <td className={td}>{r?.dosya ?? <span className="text-canvas-muted">yüklenmedi</span>}</td>
                      <td className={`${td} text-right font-mono tabular-nums`}>{r ? fmtInt(r.satir) : '—'}</td>
                      <td className={td}>{r ? `${fmtDay(r.tarih)} · ${r.yukleyen}` : '—'}</td>
                    </tr>
                  );
                })}
              </tbody>
            </TableWrap>
            {m?.me.canImport && <div className="mt-2"><Link to="/trendyol/yukle" className={btnGhost}>Dosya yükle</Link></div>}
          </Panel>
          <Accounts canMap={!!m?.me.canMap} />
        </>
      )}
    </TrendyolFrame>
  );
}
