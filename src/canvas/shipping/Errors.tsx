import { useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { ENGINE_ENABLED } from '../engine';
import { Note, Pill, errText, field, label as labelCls } from '../admin/ui';
import { Panel } from '../editorial/kit';
import { fmtInt, shippingApi } from './api';
import { Empty, ExportButton, OrderRow, ShippingFrame } from './parts';

/** M44 Entegrasyon hataları (/kargo/hatalar): takip numarası oluşmamış, kargo firması servisi hata döndürmüş siparişler.
 *  Hata mesajı Zeki AI ile kapalı kümeye sınıflanır (gece turunda, mesaj başına bir kez); sınıf yoksa «Sınıflanmadı».
 *  Süzgeç adres çubuğunda (?entegrasyon=, ?sinif=). */

export default function Errors() {
  const [params, setParams] = useSearchParams();
  const ent = params.get('entegrasyon') ?? '';
  const sinif = params.get('sinif') ?? '';
  const meta = useQuery({ queryKey: ['shipping', 'meta'], queryFn: shippingApi.meta, enabled: ENGINE_ENABLED, staleTime: 60_000 });
  const list = useQuery({
    queryKey: ['shipping', 'list', 'errors', ent, sinif],
    queryFn: () => shippingApi.errors({ entegrasyon: ent, sinif }),
    enabled: ENGINE_ENABLED,
    placeholderData: (prev) => prev,
  });
  const set = (k: string, v: string) => {
    const p = new URLSearchParams(params);
    if (v) p.set(k, v);
    else p.delete(k);
    setParams(p, { replace: true });
  };
  const d = list.data;
  const classes = [...(meta.data?.hataSiniflari ?? []), 'Sınıflanmadı'];
  return (
    <ShippingFrame
      crumb="Entegrasyon hataları"
      title="Entegrasyon hataları"
      lead="Etiketi basılamayan ya da takip numarası oluşmayan siparişler: kargo firmasının servisinden dönen sonuç ve mesaj. Yeniden deneme CRM'in kendi ekranından yapılır; portal kargo firmasına istek göndermez."
      meta={meta.data}
      aside={
        meta.data && (
          <div className="flex justify-start lg:justify-end">
            <ExportButton list="hatalar" can={meta.data.me.disaAktar} label="Excel'e al" />
          </div>
        )
      }
    >
      {list.error && <Note tone="err">{errText(list.error, 'Liste okunamadı.')}</Note>}
      <Panel>
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:max-w-[720px]">
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Entegrasyon</span>
            <select className={field} value={ent} onChange={(e) => set('entegrasyon', e.target.value)}>
              <option value="">Hepsi</option>
              {(d?.entegrasyonlar ?? []).map((x) => <option key={x} value={x}>{x}</option>)}
            </select>
          </label>
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Zeki AI sınıfı</span>
            <select className={field} value={sinif} onChange={(e) => set('sinif', e.target.value)}>
              <option value="">Hepsi</option>
              {classes.map((x) => <option key={x} value={x}>{x}</option>)}
            </select>
          </label>
        </div>
        {d && (
          <p className="mt-2 text-[11.5px] text-canvas-muted">
            Son {d.pencereGun} günün siparişleri · {fmtInt(d.toplam)} sipariş. {d.not}
          </p>
        )}
        <div className="mt-3 flex flex-col gap-2">
          {list.isLoading && <Empty>Okunuyor…</Empty>}
          {d && !d.items.length && <Empty>Bu süzgeçte entegrasyon hatası yok.</Empty>}
          {d?.items.map((o) => (
            <OrderRow
              key={o.id}
              o={o}
              extra={
                <div className="mt-1.5 flex flex-col gap-1">
                  {(o.hatalar ?? []).map((f) => (
                    <div key={f.mesajHash} className="flex flex-wrap items-start gap-1.5 text-[11.5px]">
                      <Pill tone="err">{f.entegrasyon}</Pill>
                      {f.sinif && <Pill tone="violet">{f.sinif}</Pill>}
                      <span className="min-w-0 break-words text-canvas-ink line-clamp-2">{f.sonuc ?? ''}{f.sonuc && f.mesaj ? ' — ' : ''}{f.mesaj ?? ''}</span>
                    </div>
                  ))}
                </div>
              }
            />
          ))}
        </div>
      </Panel>
    </ShippingFrame>
  );
}
