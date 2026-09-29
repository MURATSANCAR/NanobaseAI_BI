import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Trash2 } from 'lucide-react';
import { ENGINE_ENABLED } from '../../engine';
import { Loading, Note, TableWrap, btnGhost, errText, fmtDate, td, th } from '../../admin/ui';
import { FileDrop } from '../../components/FileDrop';
import { MB } from '../../components/fileDropRules';
import { Panel } from '../../editorial/kit';
import { fmtInt } from '../../budget/api';
import { AskSheet } from '../../budget/parts';
import { Chips } from '../platformKit';
import { trendyolApi, type ImportType } from './api';
import { TrendyolFrame, useTrendyolMeta } from './parts';
import SqlInfo, { InfoLabel } from '../../components/SqlInfo';
import { EmptyHint, Explain } from '../../components/Explain';

const HELP: Record<ImportType, string> = {
  urun: 'Mağazanın bütün ürünleri. Beklenen kolonlar: barkod, satıcı stok kodu, durum (satışta/kapalı), stok, Trendyol satış fiyatı. Yeni liste eskisinin yerine geçer; stok ve fiyat farkı bu dosyadan hesaplanır.',
  siparis: 'Beklenen kolonlar: paket ya da sipariş no, sipariş tarihi, durum, kargo firması, kargoya son gün (termin), barkod, adet, tutar. Aynı paket yeniden gelirse son dosya geçerli olur.',
  iade: 'Beklenen kolonlar: talep no, barkod, iade nedeni, açıklama, tarih. Açıklamadaki e-posta ve telefon gizlenir.',
  soru: 'Beklenen kolonlar: soru metni, barkod, cevap ya da durum, tarih. Müşteri adı kolonu içeri alınmaz.',
  yorum: 'Beklenen kolonlar: puan, yorum metni, barkod ya da ürün adı, tarih.',
};

export default function TrendyolImports() {
  const meta = useTrendyolMeta();
  const m = meta.data;
  const qc = useQueryClient();
  const [tur, setTur] = useState<ImportType>('urun');
  const [del, setDel] = useState<string | null>(null);
  const list = useQuery({ queryKey: ['trendyol', 'imports'], queryFn: trendyolApi.imports, enabled: ENGINE_ENABLED });
  const up = useMutation({
    mutationFn: (f: File) => trendyolApi.upload(tur, f),
    onSuccess: (r) => {
      qc.invalidateQueries({ queryKey: ['trendyol'] });
      const skipped = r.kolonlar.atlananSatir ? `, ${r.kolonlar.atlananSatir} satır eksik alan yüzünden alınmadı` : '';
      toast.success(`${fmtInt(r.satir)} satır yüklendi, ${fmtInt(r.eslesen)}'i Logo kitabına bağlandı${skipped}.`);
    },
    onError: (e) => toast.error(errText(e, 'Dosya yüklenemedi.') ?? ''),
  });
  const remove = useMutation({
    mutationFn: (id: string) => trendyolApi.deleteImport(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['trendyol'] });
      setDel(null);
    },
    onError: (e) => toast.error(errText(e, 'Silinemedi.') ?? ''),
  });
  const types = m?.types ?? { urun: 'Ürün listesi', siparis: 'Siparişler', iade: 'İadeler', soru: 'Müşteri soruları', yorum: 'Yorumlar' };
  return (
    <TrendyolFrame
      title="Panel dosyası yükle"
      lead="Trendyol ekranlarındaki bilgiler, satıcı panelinden indirip buraya yüklediğiniz Excel ya da CSV dosyalarından gelir. Önce dosya türünü seçin, sonra dosyayı bırakın. Alıcı adı, adres, telefon gibi kolonlar okunmaz; yalnız adları kayda geçer."
    >
      {/* Birincil eylem: dosya türünü seç, dosyayı bırak. Yetkisi olmayan kişi kilitli alanı ve gereken yetkiyi görür. */}
      <Panel>
        <p className="mb-2 text-[11px] font-bold uppercase tracking-wide text-canvas-muted">1. Dosya türünü seçin</p>
        <Chips value={tur} onChange={setTur} items={(Object.keys(types) as ImportType[]).map((k) => ({ key: k, label: types[k] }))} />
        <p className="my-2 text-[12.5px] text-canvas-muted">{HELP[tur]}</p>
        <p className="mb-2 text-[11px] font-bold uppercase tracking-wide text-canvas-muted">2. Dosyayı bırakın (.xlsx ya da .csv, en çok 25 MB)</p>
        <FileDrop
          title={`${types[tur]} dosyasını yükle`}
          accept=".xlsx,.csv"
          maxBytes={25 * MB}
          feature="trendyol.yukle"
          allowed={m ? !!m.me.canImport : undefined}
          busy={up.isPending}
          onPick={(f) => up.mutate(f)}
        />
      </Panel>
      <Panel>
        <h2 className="flex items-center gap-1 mb-2 text-[15px] font-extrabold">Yüklemeler <SqlInfo k={list.data?.kaynaklar} alan="items" label="Yüklemeler" /></h2>
        {list.error && <Note tone="err">{errText(list.error, 'Liste açılamadı.')}</Note>}
        {list.isLoading ? <Loading /> : !list.data?.items.length ? (
          <EmptyHint title="Henüz dosya yüklenmedi" why="Trendyol satıcı panelinden indirdiğiniz dosyayı yukarıdaki alana bırakın. İşe ürün listesiyle başlamanızı öneririz; stok ve fiyat karşılaştırması ondan yapılır." />
        ) : (
          <TableWrap>
            <thead><tr><th className={th}>Tür</th><th className={th}>Dosya</th><th className={`${th} text-right`}><InfoLabel k={list.data?.kaynaklar} alan="items">Satır</InfoLabel></th><th className={`${th} text-right`}><span className="inline-flex items-center gap-1"><InfoLabel k={list.data?.kaynaklar} alan="items">Kitaba bağlanan</InfoLabel><Explain label="Kitaba bağlanan">Barkodu Logo'daki bir kitapla eşleşen satır sayısı. Eşleşmeyen satırlar stok ve fiyat karşılaştırmasına giremez; Logo'da barkodu eksik kitap olabilir.</Explain></span></th><th className={th}>İçeri alınmayan kolonlar</th><th className={th}>Yükleyen</th><th className={th}><span className="sr-only">İşlem</span></th></tr></thead>
            <tbody>
              {list.data.items.map((r) => (
                <tr key={r.id} className="border-t border-slate-100">
                  <td className={`${td} font-semibold`}>{r.turAd}</td>
                  <td className={td}>{r.dosya ?? '—'}</td>
                  <td className={`${td} text-right font-mono tabular-nums`}>{fmtInt(r.satir)}</td>
                  <td className={`${td} text-right font-mono tabular-nums`}>{fmtInt(r.eslesen)}</td>
                  <td className={`${td} max-w-[36ch] text-[11.5px]`}>
                    {r.kolonlar.atlanan?.length ? r.kolonlar.atlanan.join(', ') : '—'}
                    {!!r.kolonlar.kisiselOlabilir?.length && <div className="text-amber-800">Kişisel olabilir: {r.kolonlar.kisiselOlabilir.join(', ')}</div>}
                  </td>
                  <td className={td}>{r.yukleyen}<div className="text-[11px] text-canvas-muted">{fmtDate(r.tarih)}</div></td>
                  <td className={`${td} text-right`}>
                    {m?.me.canImport && (
                      <button type="button" className={btnGhost} aria-label="Yüklemeyi sil" onClick={() => setDel(r.id)}><Trash2 aria-hidden className="h-4 w-4" /></button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </TableWrap>
        )}
      </Panel>
      <AskSheet open={!!del} title="Yüklemeyi sil" message="Bu dosyadan gelen ve sonraki bir dosyayla güncellenmemiş satırlar silinir. Trendyol'a bir şey gönderilmez." confirm="Sil" danger
        busy={remove.isPending} onClose={() => setDel(null)} onConfirm={() => del && remove.mutate(del)} />
    </TrendyolFrame>
  );
}
