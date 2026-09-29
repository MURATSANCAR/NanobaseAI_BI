import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { btnGhost, btnPrimary, errText, field, label } from '../admin/ui';
import { Block, SourceLine } from './parts';
import { type Meta, type SupportClass, supportApi } from './api';

/** Zeki AI'ın seçtiği konu listesi (kapalı küme) ve portal SLA uyarı süreleri. Masanın kendi SLA'sı varsa kuyrukta o
 *  kullanılır; buradaki süreler yalnız masada SLA tanımlanmamış konular için portal uyarısıdır. */
export default function ClassesTab({ meta }: { meta: Meta }) {
  const [adding, setAdding] = useState(false);
  return (
    <Block
      title="Konu sınıfları"
      help="Zeki AI talebi bu listeden bir konuya koyar; emin değilse «sınıflanamadı» der ve temsilci seçer. Süre alanları o konudaki talebin kaç saat içinde ilk yanıtı ve çözümü alması gerektiğini söyler; destek masasında ayrı süre tanımlıysa o geçerlidir. «Diğer» kapatılamaz."
      action={meta.me.canSettings ? <button type="button" className={btnGhost} onClick={() => setAdding(true)}>Sınıf ekle</button> : undefined}
    >
      <ul className="flex flex-col gap-2">
        {adding && <ClassRow key="yeni" c={null} canEdit onDone={() => setAdding(false)} />}
        {meta.classes.map((c) => (
          <ClassRow key={c.klass} c={c} canEdit={meta.me.canSettings} />
        ))}
      </ul>
      <SourceLine>Konu listesi değişince Zeki AI'ın isabeti yeniden ölçülmeli (kalite panosu → Zeki AI karnesi).</SourceLine>
    </Block>
  );
}

function ClassRow({ c, canEdit, onDone }: { c: SupportClass | null; canEdit: boolean; onDone?: () => void }) {
  const qc = useQueryClient();
  const [klass, setKlass] = useState(c?.klass ?? '');
  const [name, setName] = useState(c?.label ?? '');
  const [desc, setDesc] = useState(c?.description ?? '');
  const [first, setFirst] = useState(c?.slaFirstHours?.toString() ?? '');
  const [resolve, setResolve] = useState(c?.slaResolveHours?.toString() ?? '');
  const [active, setActive] = useState(c?.active ?? true);
  const save = useMutation({
    mutationFn: () => supportApi.saveClass(klass.trim(), { label: name, description: desc, active, slaFirstHours: first === '' ? null : Number(first.replace(',', '.')), slaResolveHours: resolve === '' ? null : Number(resolve.replace(',', '.')) }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['support', 'meta'] });
      toast.success('Kaydedildi.');
      onDone?.();
    },
    onError: (e) => toast.error(errText(e, 'Kaydedilemedi.') ?? ''),
  });
  return (
    <li className="grid gap-2 rounded-2xl border border-slate-100 bg-white/80 p-3 md:grid-cols-[1fr_2fr_auto_auto_auto_auto] md:items-end">
      <label className="flex flex-col gap-1">
        <span className={label}>{c ? c.klass : 'Kod'}</span>
        {c ? <input className={field} value={name} onChange={(e) => setName(e.target.value)} disabled={!canEdit} aria-label="Ad" /> : (
          <>
            <input className={field} value={klass} onChange={(e) => setKlass(e.target.value)} placeholder="ör. yanlis-urun" />
            <input className={field} value={name} onChange={(e) => setName(e.target.value)} placeholder="Ekranda görünen ad (ör. Yanlış ürün)" aria-label="Ad" />
          </>
        )}
      </label>
      <label className="flex flex-col gap-1">
        <span className={label}>Anlamı (Zeki AI bunu okur)</span>
        <input className={field} value={desc} onChange={(e) => setDesc(e.target.value)} disabled={!canEdit} placeholder="ör. Müşteriye sipariş ettiğinden farklı kitap gitmiş" />
      </label>
      <label className="flex flex-col gap-1">
        <span className={label}>İlk yanıt (saat)</span>
        <input className={`${field} md:w-24`} inputMode="decimal" value={first} onChange={(e) => setFirst(e.target.value)} disabled={!canEdit} />
      </label>
      <label className="flex flex-col gap-1">
        <span className={label}>Çözüm (saat)</span>
        <input className={`${field} md:w-24`} inputMode="decimal" value={resolve} onChange={(e) => setResolve(e.target.value)} disabled={!canEdit} />
      </label>
      <label className="flex min-h-11 items-center gap-2 text-[12.5px] font-semibold">
        <input type="checkbox" checked={active} onChange={(e) => setActive(e.target.checked)} disabled={!canEdit || c?.klass === 'diger'} />
        Etkin
      </label>
      {canEdit && (
        <button type="button" className={btnPrimary} disabled={save.isPending || !name.trim() || !klass.trim()} onClick={() => save.mutate()}>
          {c ? 'Kaydet' : 'Sınıfı ekle'}
        </button>
      )}
    </li>
  );
}
