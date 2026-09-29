import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Trash2 } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import { InfoLabel } from '../components/SqlInfo';
import { EmptyHint } from '../components/Explain';
import { Loading, Note, TableWrap, btnGhost, btnPrimary, errText, field, label as labelCls, td, th } from '../admin/ui';
import { Panel } from '../editorial/kit';
import { AskSheet, NumField } from '../budget/parts';
import { fmtInt, supplyApi, type Capacity as CapacityRow } from './api';
import { ErrorNote, SupplyFrame, useSupplyMeta } from './parts';

/** M52 Matbaa kapasitesi (/tedarik/kapasite): aylık adet / forma kapasitesi. Ay boşsa her ay için geçerli; belirli ayın
 *  kaydı onu ezer. Kapasite hiçbir kaynakta yok; girilmeyen matbaada eşik yalnız geçmiş referanstır. */
export default function Capacity() {
  const qc = useQueryClient();
  const meta = useSupplyMeta();
  const can = !!meta.data?.me.canCapacity;
  const q = useQuery({ queryKey: ['supply', 'capacity'], queryFn: supplyApi.capacity, enabled: ENGINE_ENABLED });
  const [form, setForm] = useState({ matbaa: '', ay: '', adet: '', forma: '', not: '' });
  const [removing, setRemoving] = useState<CapacityRow | null>(null);
  const done = () => void qc.invalidateQueries({ queryKey: ['supply'] });
  const save = useMutation({
    mutationFn: () => supplyApi.saveCapacity({ matbaa: form.matbaa, ay: form.ay || null, kapasiteAdet: form.adet, kapasiteForma: form.forma, not: form.not }),
    onSuccess: () => {
      toast.success('Kapasite kaydedildi.');
      setForm({ matbaa: form.matbaa, ay: '', adet: '', forma: '', not: '' });
      done();
    },
    onError: (e) => toast.error(errText(e, 'Kaydedilemedi.') ?? 'Kaydedilemedi.'),
  });
  const remove = useMutation({
    mutationFn: supplyApi.deleteCapacity,
    onSuccess: () => {
      setRemoving(null);
      toast.success('Kapasite kaydı silindi.');
      done();
    },
    onError: (e) => toast.error(errText(e, 'Silinemedi.') ?? 'Silinemedi.'),
  });
  const printers = q.data?.printers ?? meta.data?.printers ?? [];
  return (
    <SupplyFrame
      title="Matbaa kapasitesi"
      lead="Bir matbaanın ayda en fazla kaç kitap (ya da forma) basabileceğini buraya girin. Bu bilgi başka hiçbir sistemde yok; girdiğiniz değer «Baskı yükü» tablosunda sınır olarak kullanılır. Girilmeyen matbaa, son 12 ayının en yoğun ayıyla karşılaştırılır."
      back={{ to: '/tedarik/yuk', label: 'Baskı yükü' }}
    >
      <ErrorNote error={q.error} fallback="Kapasite kayıtları okunamadı." />
      {can ? (
        <Panel>
          <h2 className="px-1 text-[13px] font-extrabold">Kapasite gir</h2>
          <p className="px-1 text-[12px] text-canvas-muted">Matbaayı seçin; adet ya da forma kapasitesinden en az birini yazın. Ayı boş bırakırsanız değer her ay için geçerli olur; belirli bir ay için girdiğiniz değer o ay bunun yerine kullanılır.</p>
          <div className="mt-2 grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
            <label className="flex flex-col gap-1">
              <span className={labelCls}>Matbaa</span>
              <select className={field} value={form.matbaa} onChange={(e) => setForm({ ...form, matbaa: e.target.value })}>
                <option value="">Seçin</option>
                {printers.map((p) => (
                  <option key={p} value={p}>
                    {p}
                  </option>
                ))}
              </select>
            </label>
            <label className="flex flex-col gap-1">
              <span className={labelCls}>Ay (boş = her ay)</span>
              <input type="month" className={field} value={form.ay} onChange={(e) => setForm({ ...form, ay: e.target.value })} />
            </label>
            <NumField id="cap-adet" label="Aylık adet" value={form.adet} onChange={(v) => setForm({ ...form, adet: v })} help="Ayda basabileceği kitap adedi" />
            <NumField id="cap-forma" label="Aylık forma" value={form.forma} onChange={(v) => setForm({ ...form, forma: v })} help="Forma sayısı × adet (forma-baskı); forma, tek tabakada basılan sayfa grubudur" />
            <label className="flex flex-col gap-1">
              <span className={labelCls}>Not (isteğe bağlı)</span>
              <input className={field} value={form.not} placeholder="ör. yeni makine Mart'ta devrede" onChange={(e) => setForm({ ...form, not: e.target.value })} />
            </label>
          </div>
          <div className="mt-3 flex justify-end">
            <button type="button" className={btnPrimary} disabled={!form.matbaa || (!form.adet && !form.forma) || save.isPending} onClick={() => save.mutate()}>
              Kapasiteyi kaydet
            </button>
          </div>
        </Panel>
      ) : (
        <Note tone="info">Kapasite girmek için «matbaa kapasitesi» yetkisi gerekir; aşağıdaki kayıtları görebilirsiniz. Değişiklik gerekiyorsa yetkili kişiye iletin.</Note>
      )}
      {q.isLoading && <Loading />}
      {q.data && (
        <Panel>
          {q.data.items.length === 0 ? (
            <EmptyHint title="Henüz kapasite girilmedi" why={can ? 'Yukarıdaki formla ilk matbaanın aylık kapasitesini girin. Girilene kadar baskı yükü yalnız geçmiş yoğunlukla karşılaştırılır.' : 'Girilene kadar baskı yükü yalnız geçmiş yoğunlukla karşılaştırılır.'} />
          ) : (
            <TableWrap>
              <thead>
                <tr className="border-b border-slate-100">
                  <th className={th}>Matbaa</th>
                  <th className={th}>Ay</th>
                  <th className={`${th} text-right`}><InfoLabel k={q.data.kaynaklar} alan="items[]">Adet</InfoLabel></th>
                  <th className={`${th} text-right`}><InfoLabel k={q.data.kaynaklar} alan="items[]">Forma</InfoLabel></th>
                  <th className={th}>Not</th>
                  <th className={th}>Giren</th>
                  {can && <th className={th}><span className="sr-only">İşlem</span></th>}
                </tr>
              </thead>
              <tbody>
                {q.data.items.map((r) => (
                  <tr key={r.id} className="border-b border-slate-50 last:border-0">
                    <td className={`${td} font-bold`}>{r.matbaa}</td>
                    <td className={td}>{r.ay ?? 'Her ay'}</td>
                    <td className={`${td} text-right font-mono tabular-nums`}>{fmtInt(r.kapasiteAdet)}</td>
                    <td className={`${td} text-right font-mono tabular-nums`}>{fmtInt(r.kapasiteForma)}</td>
                    <td className={td}>{r.not ?? ''}</td>
                    <td className={td}>{r.byName}</td>
                    {can && (
                      <td className={td}>
                        <button type="button" className={btnGhost} aria-label="Kapasite kaydını sil (geri alınamaz)" title="Kapasite kaydını sil (geri alınamaz)" disabled={remove.isPending} onClick={() => setRemoving(r)}>
                          <Trash2 aria-hidden className="h-4 w-4" />
                        </button>
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </TableWrap>
          )}
          <p className="mt-2 px-1 text-[11.5px] text-canvas-muted">Aynı matbaa ve ay için en son girilen kayıt geçerlidir; eskiler listede kalır.</p>
        </Panel>
      )}
      <AskSheet open={!!removing} title="Kapasite kaydını sil" confirm="Kaydı sil" danger busy={remove.isPending}
        message={removing
          ? `${removing.matbaa} için ${removing.ay ? `${removing.ay} ayının` : 'her ay geçerli'} kapasite kaydı (${[removing.kapasiteAdet !== null ? `${fmtInt(removing.kapasiteAdet)} adet` : '', removing.kapasiteForma !== null ? `${fmtInt(removing.kapasiteForma)} forma` : ''].filter(Boolean).join(', ') || 'değer girilmemiş'}; giren ${removing.byName}) silinecek. «Baskı yükü» bundan sonra varsa aynı ay için daha önce girilen kaydı, yoksa geçmiş referansı kullanır. Bu işlem geri alınamaz.`
          : ''}
        onClose={() => setRemoving(null)} onConfirm={() => removing && remove.mutate(removing.id)} />
    </SupplyFrame>
  );
}
