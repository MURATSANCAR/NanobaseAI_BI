import { useEffect, useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Plus, Trash2 } from 'lucide-react';
import { Note, Pill, btnGhost, btnPrimary, errText, field, label as labelCls } from '../admin/ui';
import { dayTag, fmtDay, mktApi, type Meta, type Plan, type Task, type TaskStatus } from './api';
import { Block } from './parts';
import SqlInfo from '../components/SqlInfo';

const TONE: Record<TaskStatus, 'ok' | 'muted' | 'warn'> = { bekliyor: 'warn', yapildi: 'ok', atlandi: 'muted' };

/** Yayın gününden geri sayan takvim. Taslakta iş eklenir/silinir/taşınır; onaylı planda yalnız durum ve kanıt işlenir.
 *  Tarihi geçmiş ve yapılmamış iş kırmızı. Dış kanala gönderim/yayın işini ekip yapar; burada yalnız kaydedilir. */
export default function CalendarTab({ plan, meta, editable, canMark, onSaved }: {
  plan: Plan; meta: Meta; editable: boolean; canMark: boolean; onSaved: (p: Plan) => void;
}) {
  const [rows, setRows] = useState<Task[]>(plan.tasks);
  useEffect(() => setRows(plan.tasks), [plan]);
  const today = new Date().toISOString().slice(0, 10);
  const dirty = JSON.stringify(rows) !== JSON.stringify(plan.tasks);

  const save = useMutation({
    mutationFn: () => mktApi.tasks(plan.id, rows),
    onSuccess: (p) => { onSaved(p); toast.success('Takvim kaydedildi.'); },
    onError: (e) => toast.error(errText(e, 'Takvim kaydedilemedi.') ?? ''),
  });
  const set = (i: number, patch: Partial<Task>) => setRows((xs) => xs.map((x, j) => (j === i ? { ...x, ...patch } : x)));
  const sorted = rows.map((r, i) => ({ r, i })).sort((a, b) => (a.r.tarih ?? '9999').localeCompare(b.r.tarih ?? '9999'));

  return (
    <Block
      title="Takvim"
      info={<SqlInfo k={plan.kaynaklar} alan="tasks[]" label="Takvim işleri ve gün farkı" />}
      help={plan.yayinTarihi ? `Yayın günü ${fmtDay(plan.yayinTarihi)}. Hazır işler yayın gününe göre dizilir, yayın günü değişince kendiliğinden kayar. Tarihi geçen ve yapılmamış iş kırmızı görünür.` : 'Yayın tarihi yok: önce plan başlığındaki yayın tarihini girin.'}
      action={editable && (
        <button type="button" className={btnGhost}
          onClick={() => setRows((xs) => [...xs, { tarih: plan.yayinTarihi, gunFarki: 0, is: 'Yeni iş', kanal: null, sorumlu: null, durum: 'bekliyor', kanitUrl: null, kaynak: 'kullanici' }])}>
          <Plus aria-hidden className="h-4 w-4" />İş ekle
        </button>
      )}
    >
      {rows.length === 0 && <Note tone="info">Takvimde iş yok. Plan açılırken yayın gününe göre hazır işler eklenir; yayın günü belli değilse takvim boş kalır. {editable ? '«İş ekle» ile elle ekleyebilirsiniz.' : ''}</Note>}
      <ol className="flex flex-col gap-1.5">
        {sorted.map(({ r, i }) => {
          const late = r.durum === 'bekliyor' && !!r.tarih && r.tarih < today;
          return (
            <li key={r.id ?? `n${i}`} className={`rounded-2xl border p-3 ${late ? 'border-red-200 bg-red-50/60' : 'border-slate-100 bg-white/80'}`}>
              <div className="grid grid-cols-1 gap-2 md:grid-cols-[150px_1fr_170px_150px] md:items-end">
                <div className="flex flex-col gap-1">
                  <span className={labelCls}>{dayTag(r.gunFarki) || 'Tarih'}</span>
                  {editable ? (
                    <input type="date" className={field} value={r.tarih ?? ''} onChange={(e) => set(i, { tarih: e.target.value || null })} />
                  ) : (
                    <span className="text-[12.5px] font-semibold">{fmtDay(r.tarih)}</span>
                  )}
                </div>
                <div className="flex min-w-0 flex-col gap-1">
                  <span className={labelCls}>İş</span>
                  {editable ? (
                    <input className={field} value={r.is} onChange={(e) => set(i, { is: e.target.value })} />
                  ) : (
                    <span className="break-words text-[12.5px] font-semibold leading-snug">{r.is}</span>
                  )}
                </div>
                <label className="flex flex-col gap-1">
                  <span className={labelCls}>Kanal</span>
                  <select className={field} value={r.kanal ?? ''} disabled={!editable} onChange={(e) => set(i, { kanal: e.target.value || null })}>
                    <option value="">—</option>
                    {Object.entries(meta.channels).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                  </select>
                </label>
                <label className="flex flex-col gap-1">
                  <span className={labelCls}>Durum</span>
                  <select className={field} value={r.durum} disabled={!(editable || canMark)} onChange={(e) => set(i, { durum: e.target.value as TaskStatus })}>
                    {Object.entries(meta.taskStatuses).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                  </select>
                </label>
              </div>
              <div className="mt-2 flex flex-wrap items-center gap-2 text-[11px] text-canvas-muted">
                <Pill tone={late ? 'err' : TONE[r.durum]}>{late ? 'Gecikti' : meta.taskStatuses[r.durum]}</Pill>
                {r.materyalTur && <Pill tone="muted">{meta.materials[r.materyalTur] ?? r.materyalTur}</Pill>}
                {r.kaynak === 'ozel-gun' && <Pill tone="violet">Özel gün</Pill>}
                {(editable || canMark) ? (
                  <input className={`${field} min-w-0 flex-1`} placeholder="Kanıt bağlantısı (yayın adresi, e-posta konusu…)" value={r.kanitUrl ?? ''}
                    onChange={(e) => set(i, { kanitUrl: e.target.value || null })} />
                ) : r.kanitUrl ? <span className="break-all">{r.kanitUrl}</span> : null}
                {editable && (
                  <button type="button" aria-label="İşi sil" className={btnGhost} onClick={() => setRows((xs) => xs.filter((_, j) => j !== i))}>
                    <Trash2 aria-hidden className="h-4 w-4" />
                  </button>
                )}
              </div>
            </li>
          );
        })}
      </ol>
      {(editable || canMark) && (
        <div className="mt-3 flex flex-wrap items-center justify-end gap-2">
          {dirty && <span className="text-[11.5px] font-semibold text-amber-800">Kaydedilmemiş değişiklik var</span>}
          <button type="button" className={btnPrimary} onClick={() => save.mutate()} disabled={!dirty || save.isPending}>Kaydet</button>
        </div>
      )}
    </Block>
  );
}
