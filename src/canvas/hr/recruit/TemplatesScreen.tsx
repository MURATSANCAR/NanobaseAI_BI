import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Plus } from 'lucide-react';
import { ENGINE_ENABLED } from '../../engine';
import { Note, Pill, btnGhost, btnPrimary, errText, field, label as labelCls } from '../../admin/ui';
import Sheet from '../../editorial/studio/reader/Sheet';
import { fmtDateTime, recruitApi, type Template } from '../hrApi';
import { Block, HrFrame } from '../parts';

/** M55 İK belgeleri: ilan, «başvurunuz alındı», mülakat daveti, teklif ve ret şablonları. `{{alan}}` yer tutucuları aday
 *  kartında mektup hazırlanırken doldurulur. Yürürlükteki şablon kullanılır; metin değişince sürüm artar. */

export default function TemplatesScreen() {
  const meta = useQuery({ queryKey: ['hr', 'recruit', 'meta'], queryFn: recruitApi.meta, enabled: ENGINE_ENABLED, staleTime: 60_000 });
  const list = useQuery({ queryKey: ['hr', 'recruit', 'templates'], queryFn: () => recruitApi.templates(), enabled: ENGINE_ENABLED });
  const [editing, setEditing] = useState<Template | 'new' | null>(null);
  const canEdit = !!meta.data?.me.can.templates;
  const kinds = list.data?.kinds ?? {};
  return (
    <HrFrame
      crumb="Belgeler"
      title="İK belgeleri"
      lead="İlan, «başvurunuz alındı», mülakat daveti, teklif ve ret şablonları. Mektup aday kartında şablondan taslak olur; gönderimi siz yaparsınız. «Başvurunuz alındı» şablonu aday aydınlatma metnine atıf yapmalıdır."
      aside={
        canEdit ? (
          <div className="flex justify-start lg:justify-end">
            <button type="button" className={btnPrimary} onClick={() => setEditing('new')}>
              <Plus aria-hidden className="h-4 w-4" />
              Yeni şablon
            </button>
          </div>
        ) : undefined
      }
    >
      {list.error && <Note tone="err">{errText(list.error, 'Şablonlar okunamadı.')}</Note>}
      {list.data && !list.data.items.length && (
        <Note tone="info">Henüz şablon yok. {canEdit ? '«Yeni şablon» ile başlayın; başlangıç metinlerinden birini yükleyip düzeltebilirsiniz.' : ''}</Note>
      )}
      <div className="grid grid-cols-1 gap-3 lg:grid-cols-2 lg:gap-4">
        {Object.entries(kinds).map(([kind, label]) => {
          const rows = (list.data?.items ?? []).filter((t) => t.kind === kind);
          return (
            <Block key={kind} title={label} help={rows.some((t) => t.state === 'yururlukte') ? undefined : 'Yürürlükte şablon yok; bu türde mektup hazırlanamaz.'}>
              {!rows.length && <div className="py-3 text-center text-[12px] text-canvas-muted">Şablon yok.</div>}
              <ul className="flex flex-col gap-1.5">
                {rows.map((t) => (
                  <li key={t.id}>
                    <button type="button" onClick={() => setEditing(t)} className="w-full rounded-xl border border-slate-100 bg-white/80 p-2.5 text-left transition-colors duration-150 hover:border-canvas-violet/40">
                      <div className="flex flex-wrap items-center gap-1.5">
                        <span className="min-w-0 break-words text-[13px] font-extrabold">{t.name}</span>
                        <Pill tone={t.state === 'yururlukte' ? 'ok' : t.state === 'arsiv' ? 'muted' : 'warn'}>{t.stateLabel}</Pill>
                        <span className="font-mono text-[11px] text-canvas-muted">s{t.version}</span>
                      </div>
                      <div className="text-[11.5px] text-canvas-muted">{t.updatedBy ?? '—'} · {fmtDateTime(t.updatedAt)}</div>
                      {t.unknown.length > 0 && <div className="mt-0.5 text-[11.5px] text-amber-800">Tanınmayan alan: {t.unknown.join(', ')}</div>}
                    </button>
                  </li>
                ))}
              </ul>
            </Block>
          );
        })}
      </div>
      {editing !== null && list.data && (
        <EditorSheet
          key={editing === 'new' ? 'new' : editing.id + editing.version + editing.state}
          t={editing === 'new' ? null : editing}
          kinds={kinds}
          fields={list.data.fields}
          canEdit={canEdit}
          onClose={() => setEditing(null)}
        />
      )}
    </HrFrame>
  );
}

function EditorSheet({ t, kinds, fields, canEdit, onClose }: {
  t: Template | null; kinds: Record<string, string>; fields: Record<string, string>; canEdit: boolean; onClose: () => void;
}) {
  const qc = useQueryClient();
  const [f, setF] = useState({ kind: t?.kind ?? 'ret', name: t?.name ?? '', body: t?.body ?? '', state: t?.state ?? 'taslak' });
  const starters = useQuery({ queryKey: ['hr', 'recruit', 'starters'], queryFn: recruitApi.starters, enabled: canEdit, staleTime: Infinity });
  const save = useMutation({
    mutationFn: () => (t ? recruitApi.updateTemplate(t.id, f) : recruitApi.createTemplate(f)),
    onSuccess: (r) => {
      toast.success(r.unknown.length ? `Kaydedildi; tanınmayan alan: ${r.unknown.join(', ')}` : 'Şablon kaydedildi.');
      void qc.invalidateQueries({ queryKey: ['hr', 'recruit', 'templates'] });
      onClose();
    },
    onError: (e) => toast.error(errText(e, 'Şablon kaydedilemedi.')),
  });
  const starter = starters.data?.items[f.kind];
  return (
    <Sheet open modal wide onClose={onClose} title={t ? t.name : 'Yeni şablon'} subtitle={t ? `${t.kindLabel} · sürüm ${t.version}` : undefined}>
      <fieldset disabled={!canEdit} className="flex flex-col gap-3">
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Tür</span>
            <select className={field} value={f.kind} onChange={(e) => setF({ ...f, kind: e.target.value })}>
              {Object.entries(kinds).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
          </label>
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Ad</span>
            <input className={field} value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} />
          </label>
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Durum</span>
            <select className={field} value={f.state} onChange={(e) => setF({ ...f, state: e.target.value as Template['state'] })}>
              <option value="taslak">Taslak</option>
              <option value="yururlukte">Yürürlükte</option>
              <option value="arsiv">Arşiv</option>
            </select>
          </label>
        </div>
        <label className="flex flex-col gap-1">
          <span className={labelCls}>Metin (# başlık, ## ara başlık; boş satır paragraf)</span>
          <textarea className={`${field} min-h-[280px] font-sans`} value={f.body} onChange={(e) => setF({ ...f, body: e.target.value })} />
        </label>
        {canEdit && starter && (
          <div className="flex justify-start">
            <button type="button" className={btnGhost} onClick={() => setF({ ...f, body: starter })}>Başlangıç metnini yükle</button>
          </div>
        )}
        <details className="rounded-xl bg-slate-50 p-2.5">
          <summary className="cursor-pointer text-[12.5px] font-bold">Kullanılabilen alanlar</summary>
          <ul className="mt-1 grid grid-cols-1 gap-0.5 text-[12px] sm:grid-cols-2">
            {Object.entries(fields).map(([k, v]) => (
              <li key={k}><code className="font-mono text-[11.5px]">{`{{${k}}}`}</code> — {v}</li>
            ))}
          </ul>
        </details>
      </fieldset>
      {canEdit && (
        <div className="mt-3 flex justify-end gap-2">
          <button type="button" className={btnGhost} onClick={onClose}>Vazgeç</button>
          <button type="button" className={btnPrimary} disabled={save.isPending || !f.name.trim() || !f.body.trim()} onClick={() => save.mutate()}>Kaydet</button>
        </div>
      )}
    </Sheet>
  );
}
