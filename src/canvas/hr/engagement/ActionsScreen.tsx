import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Plus } from 'lucide-react';
import { ENGINE_ENABLED } from '../../engine';
import { Loading, Note, Pill, btnGhost, btnPrimary, errText, field, label as labelCls } from '../../admin/ui';
import Sheet from '../../editorial/studio/reader/Sheet';
import { fmtDay } from '../hrApi';
import { HrFrame } from '../parts';
import { engApi, type Action, type EngMeta } from './engApi';
import { EmptyHint } from '../../components/Explain';

/** M58 Aksiyon planı: anket sonrası «ne yapacağız». İK ekler ve düzenler; birim yöneticisi kendi biriminin aksiyonunda
 *  durum ve not yazar. Bir sonraki ankette ilgili madde bu aksiyonla yan yana izlenir. */
export default function ActionsScreen() {
  const meta = useQuery({ queryKey: ['hr', 'eng', 'meta'], queryFn: engApi.meta, enabled: ENGINE_ENABLED, staleTime: 60_000 });
  const q = useQuery({ queryKey: ['hr', 'eng', 'actions'], queryFn: () => engApi.actions(), enabled: ENGINE_ENABLED });
  const [edit, setEdit] = useState<Action | 'new' | null>(null);
  const today = new Date().toISOString().slice(0, 10);
  return (
    <HrFrame crumb="Aksiyon planı" title="Aksiyon planı" lead="Anket sonuçlarından çıkan işler: madde, sorumlu, son tarih ve durum. Anket sonrası hiçbir şey yapılmazsa bir sonraki ankete katılım düşer."
      aside={q.data?.canCreate ? <div className="flex justify-start lg:justify-end"><button type="button" className={btnPrimary} onClick={() => setEdit('new')}><Plus aria-hidden className="h-4 w-4" />Aksiyon ekle</button></div> : undefined}>
      {q.error && <Note tone="err">{errText(q.error, 'Aksiyonlar okunamadı.')}</Note>}
      {q.isLoading && <Loading />}
      {q.data && !q.data.items.length && (
        <EmptyHint
          title="Henüz aksiyon yok"
          why={q.data.canCreate ? 'Kapanan bir anketin sonucuna bakıp «Aksiyon ekle» ile yapılacak işi, sorumlu birimi ve son tarihi girin.' : 'İK anket sonrası aksiyon eklediğinde biriminizinkiler burada görünür.'}
        />
      )}
      <ul className="grid grid-cols-1 gap-2 md:grid-cols-2">
        {(q.data?.items ?? []).map((a) => {
          const late = a.dueOn && a.dueOn < today && (a.state === 'acik' || a.state === 'devam');
          return (
            <li key={a.id}>
              <button type="button" disabled={!a.canEdit} onClick={() => setEdit(a)} className="glass-panel flex w-full flex-col gap-1 rounded-2xl p-3 text-left shadow-glass-float disabled:cursor-default">
                <div className="flex flex-wrap items-center gap-1.5">
                  <span className="min-w-0 flex-1 break-words text-[14px] font-extrabold">{a.title}</span>
                  <Pill tone={a.state === 'tamam' ? 'ok' : a.state === 'iptal' ? 'muted' : late ? 'err' : 'warn'}>{late ? 'gecikti' : a.stateLabel}</Pill>
                </div>
                <div className="text-[11.5px] text-canvas-muted">{a.unitName ?? 'Şirket geneli'} · {a.ownerName ?? 'sorumlu yok'} · son {fmtDay(a.dueOn)}</div>
                {a.note && <div className="break-words text-[12px]">{a.note}</div>}
              </button>
            </li>
          );
        })}
      </ul>
      {edit !== null && meta.data && <ActionSheet a={edit === 'new' ? null : edit} admin={!!q.data?.canCreate} meta={meta.data} onClose={() => setEdit(null)} />}
    </HrFrame>
  );
}

function ActionSheet({ a, admin, meta, onClose }: { a: Action | null; admin: boolean; meta: EngMeta; onClose: () => void }) {
  const qc = useQueryClient();
  const surveys = useQuery({ queryKey: ['hr', 'eng', 'surveys'], queryFn: engApi.surveys, enabled: admin });
  const [f, setF] = useState({ title: a?.title ?? '', unitId: a?.unitId ?? '', surveyId: a?.surveyId ?? '', dueOn: a?.dueOn ?? '', state: a?.state ?? 'acik', note: a?.note ?? '' });
  const save = useMutation({
    mutationFn: () => {
      const b: Record<string, unknown> = admin ? { ...f, unitId: f.unitId || null, surveyId: f.surveyId || null, dueOn: f.dueOn || null } : { state: f.state, note: f.note };
      return a ? engApi.updateAction(a.id, b) : engApi.createAction(b);
    },
    onSuccess: () => { toast.success('Kaydedildi.'); void qc.invalidateQueries({ queryKey: ['hr', 'eng', 'actions'] }); onClose(); },
    onError: (e) => toast.error(errText(e, 'Kaydedilemedi.')),
  });
  return (
    <Sheet open modal onClose={onClose} title={a ? a.title : 'Yeni aksiyon'}>
      <div className="flex flex-col gap-3">
        <fieldset disabled={!admin} className="flex flex-col gap-3">
          <label className="flex flex-col gap-1"><span className={labelCls}>Aksiyon</span><input className={field} value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} placeholder="ör. Birim içi aylık bilgilendirme toplantısı başlatmak" /></label>
          <label className="flex flex-col gap-1"><span className={labelCls}>Birim</span>
            <select className={field} value={f.unitId} onChange={(e) => setF({ ...f, unitId: e.target.value })}><option value="">Şirket geneli</option>{meta.units.map((u) => <option key={u.id} value={u.id}>{u.name}</option>)}</select>
          </label>
          <label className="flex flex-col gap-1"><span className={labelCls}>Anket</span>
            <select className={field} value={f.surveyId} onChange={(e) => setF({ ...f, surveyId: e.target.value })}><option value="">—</option>{(surveys.data?.items ?? []).map((s) => <option key={s.id} value={s.id}>{s.title}</option>)}</select>
          </label>
          <label className="flex flex-col gap-1"><span className={labelCls}>Son tarih</span><input type="date" className={field} value={f.dueOn} onChange={(e) => setF({ ...f, dueOn: e.target.value })} /></label>
        </fieldset>
        <label className="flex flex-col gap-1"><span className={labelCls}>Durum</span>
          <select className={field} value={f.state} onChange={(e) => setF({ ...f, state: e.target.value as Action['state'] })}>{Object.entries(meta.actionStates).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select>
        </label>
        <label className="flex flex-col gap-1"><span className={labelCls}>Not</span><textarea className={`${field} min-h-[80px]`} value={f.note} onChange={(e) => setF({ ...f, note: e.target.value })} placeholder="Ne yapıldı, ne kaldı" /></label>
        <div className="flex justify-end gap-2">
          <button type="button" className={btnGhost} onClick={onClose}>Vazgeç</button>
          <button type="button" className={btnPrimary} disabled={save.isPending || (admin && !f.title.trim())} onClick={() => save.mutate()}>Kaydet</button>
        </div>
      </div>
    </Sheet>
  );
}
