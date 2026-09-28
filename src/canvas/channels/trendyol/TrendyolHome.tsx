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
      <h2 className="text-[15px] font-extrabold">Logo'da Trendyol adlı cariler</h2>
      <p className="mb-2 text-[12px] text-canvas-muted">
        Unvanında {d?.desenler?.join(', ') ?? '—'} geçen cariler (Logo). Trendyol'a toptan satış varsa fatura bu carilerdedir; kanal karnesinde
        sayılması için cari Trendyol olarak onaylanmalı. Boş liste «Trendyol'a satış yok» demek değildir.
      </p>
      {q.isLoading ? <Loading /> : !d?.adayCariler.length ? (
        <Note tone="info">{d?.okundu ? 'Unvanında bu adlar geçen cari bulunmadı.' : 'Henüz okunmadı: «Veriyi yenile» Logo carilerini de okur.'}</Note>
      ) : (
        <TableWrap>
          <thead><tr><th className={th}>Cari</th><th className={th}>Kanal kodu</th><th className={th}>Eşleme</th><th className={th} /></tr></thead>
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
      lead="Stok ve fiyat farkı, sipariş ve iade, cevapsız soru ve düşük puanlı yorum: yüklenen panel dosyalarıyla Logo yan yana. Mağazaya hiçbir şey gönderilmez; düzeltmeyi kişi panelden yapar."
    >
      <TrendyolData meta={m} />
      {q.error && <Note tone="err">{errText(q.error, 'Özet açılamadı.')}</Note>}
      {q.isLoading && <Loading />}
      {d && (
        <>
          <KpiRow>
            <Kpi label="Stok farkı" value={fmtInt(diff)} help={`Satışta ama depoda yok: ${fmtInt(d.stokFarki['trendyolda-var-depoda-yok'] ?? 0)} · depoda var, kapalı: ${fmtInt(d.stokFarki['depoda-var-kapali'] ?? 0)}`} />
            <Kpi label="Cevapsız soru" value={fmtInt(d.soru.cevapsiz)} help={`${fmtInt(d.soru.geciken)} tanesi ${m?.settings.soruSaat ?? 24} saati geçti`} />
            <Kpi label="Düşük puanlı yorum" value={fmtInt(d.yorum.dusuk)} help={`3 ve altı · ortalama ${d.yorum.ortalama ?? '—'} / 5 (${fmtInt(d.yorum.toplam)} yorum)`} />
            <Kpi label="Geciken paket" value={fmtInt(d.siparis.geciken)} help={`${fmtInt(d.siparis.paket)} paket · ${d.siparis.aralik.bas ? `${fmtDay(d.siparis.aralik.bas)} – ${fmtDay(d.siparis.aralik.bit)}` : 'sipariş dosyası yok'}`} />
          </KpiRow>
          <Panel>
            <h2 className="text-[15px] font-extrabold">Trendyol'a faturalanan (toptan)</h2>
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
            <h2 className="text-[15px] font-extrabold">Yüklenen dosyalar</h2>
            <TableWrap>
              <thead><tr><th className={th}>Tür</th><th className={th}>Son dosya</th><th className={`${th} text-right`}>Satır</th><th className={th}>Tarih</th></tr></thead>
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
