import { useEffect, useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Loader2, Sparkles } from 'lucide-react';
import { Note, Pill, btnGhost, btnPrimary, errText, field, label as labelCls } from '../admin/ui';
import { DROP_REASON, MATERIAL_TONE, SOURCE_LABEL, fmtStamp, mktApi, type Material, type Meta, type Plan } from './api';
import { Block } from './parts';
import { BACKLIST_MATERIALS, blApi } from './backlist/api';

/** Materyaller: CRM'den kaynağıyla alınanlar, Zeki AI taslakları, elle yazılanlar. Akış taslak → editoryal onay →
 *  pazarlama onayı; metin değişince onay düşer. Onaylılar «yayına hazır paket»e girer, hiçbir yere gönderilmez. */
export default function MaterialsTab({ plan, meta, running }: { plan: Plan; meta: Meta; running: boolean }) {
  const qc = useQueryClient();
  const me = meta.me;
  const open = plan.durum !== 'arsiv';
  // Backlist planında yalnız backlist türleri (taslak Backlist ucundan); yeni kitap planında onlar görünmez.
  const bl = plan.kind === 'backlist';
  const kinds = Object.entries(meta.materials).filter(([k]) => BACKLIST_MATERIALS.includes(k) === bl);
  const [tur, setTur] = useState(kinds[0]?.[0] ?? 'foy');
  const [manual, setManual] = useState<string | null>(null);

  const refresh = () => {
    qc.invalidateQueries({ queryKey: ['mkt', 'plan', plan.id] });
    qc.invalidateQueries({ queryKey: ['mkt', 'jobs', plan.id] });
  };
  const create = useMutation({
    mutationFn: (metin?: string) => (bl ? blApi.newMaterial(plan.id, tur, metin) : mktApi.newMaterial(plan.id, tur, metin)),
    onSuccess: (out) => {
      setManual(null);
      refresh();
      toast.success(out.job ? 'Zeki AI taslağı hazırlanıyor.' : 'Materyal eklendi.');
    },
    onError: (e) => toast.error(errText(e, 'Materyal eklenemedi.') ?? ''),
  });

  const byType = Object.keys(meta.materials).map((t) => ({ t, items: plan.materials.filter((m) => m.tur === t) })).filter((g) => g.items.length);

  return (
    <div className="flex flex-col gap-3">
      {me.canWrite && open && (
        <Block title="Yeni materyal" help="Zeki AI yalnız CRM'deki metinlere ve karneye dayanır; kaynakta birebir geçmeyen alıntı, kaynaksız rakam ve kanıtsız iddia içeren cümle düşer.">
          <div className="flex flex-col gap-2 sm:flex-row sm:items-end">
            <label className="flex flex-col gap-1 sm:w-[260px]">
              <span className={labelCls}>Tür</span>
              <select className={field} value={tur} onChange={(e) => setTur(e.target.value)}>
                {kinds.map(([k, v]) => <option key={k} value={k}>{v}</option>)}
              </select>
            </label>
            <button type="button" className={btnPrimary} disabled={running || create.isPending || !meta.modelReady} onClick={() => create.mutate(undefined)}>
              {running || create.isPending ? <Loader2 aria-hidden className="h-4 w-4 animate-spin" /> : <Sparkles aria-hidden className="h-4 w-4" />}
              Zeki AI ile yaz
            </button>
            <button type="button" className={btnGhost} onClick={() => setManual('')}>Elle yaz</button>
          </div>
          {manual !== null && (
            <div className="mt-2 flex flex-col gap-2">
              <textarea className={`${field} min-h-[160px]`} value={manual} onChange={(e) => setManual(e.target.value)} />
              <div className="flex justify-end gap-2">
                <button type="button" className={btnGhost} onClick={() => setManual(null)}>Vazgeç</button>
                <button type="button" className={btnPrimary} disabled={!manual.trim() || create.isPending} onClick={() => create.mutate(manual)}>Ekle</button>
              </div>
            </div>
          )}
        </Block>
      )}
      {!plan.materials.length && <Note tone="info">Henüz materyal yok. Kitap kartında pazarlama metni varsa plan açılırken buraya alınır; yoksa Zeki AI ile yazdırın.</Note>}
      {byType.map(({ t, items }) => (
        <Block key={t} title={meta.materials[t] ?? t}>
          <div className="flex flex-col gap-3">
            {items.map((m) => <MaterialCard key={m.id} m={m} plan={plan} meta={meta} onChange={refresh} />)}
          </div>
        </Block>
      ))}
    </div>
  );
}

function MaterialCard({ m, plan, meta, onChange }: { m: Material; plan: Plan; meta: Meta; onChange: () => void }) {
  const me = meta.me;
  const [text, setText] = useState(m.metin);
  useEffect(() => setText(m.metin), [m.metin]);
  const canEdit = me.canWrite && plan.durum !== 'arsiv';
  const dirty = text !== m.metin;
  const save = useMutation({
    mutationFn: () => mktApi.saveMaterial(m.id, text),
    onSuccess: () => { onChange(); toast.success('Kaydedildi; onay yeniden gerekir.'); },
    onError: (e) => toast.error(errText(e, 'Kaydedilemedi.') ?? ''),
  });
  const approve = useMutation({
    mutationFn: (seviye: 'editoryal' | 'pazarlama') => mktApi.approveMaterial(m.id, seviye),
    onSuccess: () => { onChange(); toast.success('Onay kaydedildi.'); },
    onError: (e) => toast.error(errText(e, 'Onaylanamadı.') ?? ''),
  });
  const dropped = m.dogrulama?.dusen ?? [];
  const sameEditor = (m.editoryalOnaylayan ?? '').toLowerCase() === me.username.toLowerCase();

  return (
    <article className="rounded-2xl border border-slate-100 bg-white/85 p-3">
      <div className="mb-2 flex flex-wrap items-center gap-1.5 text-[11px]">
        <Pill tone={MATERIAL_TONE[m.durum]}>{m.durumAdi}</Pill>
        <Pill tone={m.kaynak === 'zeki' ? 'violet' : 'muted'}>{SOURCE_LABEL(m.kaynak)}</Pill>
        <span className="text-canvas-muted">sürüm {m.surum} · {fmtStamp(m.guncelleme)}</span>
        {m.editoryalOnaylayan && <span className="text-canvas-muted">· editoryal onay {m.editoryalOnaylayan}</span>}
        {m.onaylayan && <span className="text-canvas-muted">· pazarlama onayı {m.onaylayan}</span>}
      </div>
      {canEdit ? (
        <textarea className={`${field} min-h-[180px] leading-snug`} value={text} onChange={(e) => setText(e.target.value)} aria-label={m.turAdi} />
      ) : (
        <p className="whitespace-pre-line text-[12.5px] leading-snug">{m.metin}</p>
      )}
      {dropped.length > 0 && (
        <details className="mt-2 text-[11.5px]">
          <summary className="inline-flex min-h-8 cursor-pointer items-center font-bold text-amber-800">Denetimde düşen {dropped.length} cümle</summary>
          <ul className="mt-1 flex flex-col gap-1 text-canvas-muted">
            {dropped.map((d, i) => <li key={i}><strong>{DROP_REASON[d.neden] ?? d.neden}:</strong> {d.cumle}</li>)}
          </ul>
        </details>
      )}
      <div className="mt-2 flex flex-wrap justify-end gap-2">
        {canEdit && dirty && <button type="button" className={btnGhost} onClick={() => setText(m.metin)}>Geri al</button>}
        {canEdit && <button type="button" className={btnGhost} disabled={!dirty || save.isPending} onClick={() => save.mutate()}>Kaydet</button>}
        {m.durum === 'taslak' && me.canEditorial && !dirty && (
          <button type="button" className={btnPrimary} disabled={approve.isPending} onClick={() => approve.mutate('editoryal')}>Editoryal onay</button>
        )}
        {m.durum === 'editoryal-onayli' && me.canApprove && !sameEditor && !dirty && (
          <button type="button" className={btnPrimary} disabled={approve.isPending} onClick={() => approve.mutate('pazarlama')}>Pazarlama onayı</button>
        )}
      </div>
    </article>
  );
}
