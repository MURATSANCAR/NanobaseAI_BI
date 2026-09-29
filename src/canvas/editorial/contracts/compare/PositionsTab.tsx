import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Check, Pencil, Plus, Sparkles, Trash2 } from 'lucide-react';
import { Note, Pill, btnGhost, btnPrimary, field, nf } from '../../../admin/ui';
import { InfoLabel } from '../../../components/SqlInfo';
import { Panel } from '../../kit';
import { Field, Sheet, errMsg, stamp } from '../ui';
import { compareApi, type Meta, type Position, type PositionClause } from './api';

/**
 * Standart pozisyonlar (hukuk biriminin kırmızı çizgileri): kural yazılır ya da emsalden öneri üretilir; öneri
 * onaylanmadan hiçbir sözleşmede denetlenmez. Onaylı kurallar sözleşme görünümünde, taramada ve belge farkında (madde
 * türü kuralları) ihlal olarak çıkar. Yazma yetkisi açıkça verilir.
 */
export default function PositionsTab({ meta }: { meta: Meta }) {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ['contracts', 'compare', 'positions'], queryFn: compareApi.positions });
  const [edit, setEdit] = useState<Partial<Position> | null>(null);
  const [tip, setTip] = useState('');
  const [odeme, setOdeme] = useState('');
  const done = () => qc.invalidateQueries({ queryKey: ['contracts', 'compare'] });
  const approve = useMutation({ mutationFn: compareApi.positionApprove, onSuccess: done });
  const remove = useMutation({ mutationFn: compareApi.positionDelete, onSuccess: done });
  const suggest = useMutation({
    mutationFn: () => compareApi.positionSuggest(tip ? Number(tip) : undefined, odeme ? Number(odeme) : undefined),
    onSuccess: done,
  });
  const d = q.data;
  const can = !!d?.can.position;
  const items = d?.items ?? [];
  const pending = items.filter((p) => p.state === 'oneri');
  const approved = items.filter((p) => p.state === 'onayli');
  const label = (key: string) => d?.clauses.find((c) => c.key === key)?.label ?? key;
  const scopeText = (p: Position) =>
    [
      p.scope.tip != null ? d?.facets.tip.find((x) => x.kod === p.scope.tip)?.ad : null,
      p.scope.odeme != null ? d?.facets.odeme.find((x) => x.kod === p.scope.odeme)?.ad : null,
      p.scope.para != null ? d?.facets.para.find((x) => x.kod === p.scope.para)?.ad : null,
    ].filter(Boolean).join(' · ') || 'Bütün sözleşmeler';

  return (
    <>
      {q.error && <Note tone="err">{errMsg(q.error)}</Note>}
      <Panel>
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div className="min-w-0">
            <h2 className="text-[15px] font-extrabold">
              <InfoLabel k={d?.kaynaklar} alan="items[]" label="Standart pozisyonlar">Standart pozisyonlar</InfoLabel>
            </h2>
            <p className="mt-0.5 max-w-[75ch] text-[11.5px] leading-snug text-canvas-muted">
              Hukuk biriminin sözleşme kuralları: «karton telif en çok %12», «iletim hakkı olmalı», «belgede fesih maddesi olmalı». Onaylı kurala aykırı sözleşme, sözleşme görünümünde ve taramada işaretlenir. Öneri, onaylanmadan denetlenmez.
            </p>
          </div>
          {can && (
            <button type="button" className={btnPrimary} onClick={() => setEdit({ level: 'uyari', op: 'max', scope: { tip: null, odeme: null, para: null } })}>
              <Plus aria-hidden className="h-4 w-4" />
              Yeni kural
            </button>
          )}
        </div>
        {can && d && (
          <div className="mt-3 grid gap-2 rounded-2xl border border-violet-100 bg-violet-50/40 p-3 sm:grid-cols-[1fr_1fr_auto] sm:items-end">
            <Field label="Sözleşme tipi">
              <select className={field} value={tip} onChange={(e) => setTip(e.target.value)}>
                <option value="">Hepsi</option>
                {d.facets.tip.map((x) => <option key={x.kod} value={x.kod}>{x.ad}</option>)}
              </select>
            </Field>
            <Field label="Ödeme türü">
              <select className={field} value={odeme} onChange={(e) => setOdeme(e.target.value)}>
                <option value="">Hepsi</option>
                {d.facets.odeme.map((x) => <option key={x.kod} value={x.kod}>{x.ad}</option>)}
              </select>
            </Field>
            <button type="button" className={btnGhost} disabled={suggest.isPending} onClick={() => suggest.mutate()}>
              <Sparkles aria-hidden className="h-4 w-4" />
              Emsalden öneri üret
            </button>
            <p className="text-[11.5px] leading-snug text-canvas-muted sm:col-span-3">
              {`Son ${meta.ayarlar.yil} yılın emsalinden: sayısal maddede %5–%95 aralığı, %95'inde olan madde «olmalı», %95'i aynı seçim «eşit». Tutarlar önerilmez. Öneriler aşağıda onay bekler.`}
            </p>
            {suggest.data && <p className="text-[12px] font-semibold text-emerald-800 sm:col-span-3">{`${suggest.data.eklenen} öneri eklendi; ${suggest.data.atlanan} kural zaten vardı.`}</p>}
            {suggest.error && <div className="sm:col-span-3"><Note tone="err">{errMsg(suggest.error)}</Note></div>}
          </div>
        )}
        {!can && d && <p className="mt-2 text-[12px] text-canvas-muted">Kural yazma yetkiniz yok (Yönetim → Yetkiler → «Standart pozisyon (hukuk)»); kuralları görebilirsiniz.</p>}
      </Panel>

      {[['Onay bekleyen öneriler', pending], ['Onaylı kurallar', approved]].map(([title, list]) => (
        <Panel key={title as string}>
          <h3 className="text-[13px] font-extrabold">{`${title} (${nf.format((list as Position[]).length)})`}</h3>
          {!(list as Position[]).length && <p className="mt-2 text-[12px] text-canvas-muted">Kural yok.</p>}
          <ul className="mt-2 divide-y divide-slate-100 rounded-2xl border border-slate-100 bg-white/85">
            {(list as Position[]).map((p) => (
              <li key={p.id} className="flex flex-col gap-2 p-3 text-[12.5px] sm:flex-row sm:items-start sm:justify-between">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-1.5">
                    <Pill tone={p.level === 'kirmizi' ? 'err' : 'warn'}>{p.levelLabel}</Pill>
                    <span className="font-bold">{p.text}</span>
                  </div>
                  <div className="mt-0.5 text-[11.5px] text-canvas-muted">{`${scopeText(p)} · ${label(p.clause)}`}</div>
                  {p.reason && <div className="mt-0.5 text-[11.5px] leading-snug">{p.reason}</div>}
                  <div className="mt-0.5 text-[11px] text-canvas-muted">
                    {p.state === 'onayli' ? `Onaylayan ${p.approvedBy ?? '—'} · ${stamp(p.approvedAt)}` : `Öneren ${p.createdBy}`}
                  </div>
                </div>
                {can && (
                  <div className="flex shrink-0 flex-wrap gap-1.5">
                    {p.state === 'oneri' && (
                      <button type="button" className={btnPrimary} disabled={approve.isPending} onClick={() => approve.mutate(p.id)}>
                        <Check aria-hidden className="h-4 w-4" />
                        Onayla
                      </button>
                    )}
                    <button type="button" className={btnGhost} onClick={() => setEdit(p)} aria-label="Kuralı düzelt">
                      <Pencil aria-hidden className="h-4 w-4" />
                    </button>
                    <button type="button" className={btnGhost} aria-label="Kuralı sil" disabled={remove.isPending}
                      onClick={() => window.confirm(`«${p.text}» kuralı silinsin mi?`) && remove.mutate(p.id)}>
                      <Trash2 aria-hidden className="h-4 w-4" />
                    </button>
                  </div>
                )}
              </li>
            ))}
          </ul>
        </Panel>
      ))}
      {(approve.error || remove.error) && <Note tone="err">{errMsg(approve.error || remove.error)}</Note>}
      {edit && d && <RuleSheet init={edit} clauses={d.clauses} facets={d.facets} onClose={() => setEdit(null)} onSaved={() => { done(); setEdit(null); }} />}
    </>
  );
}

const OPS_BY_KIND: Record<string, Array<Position['op']>> = {
  tur: ['zorunlu', 'yasak'],
  bayrak: ['eq', 'zorunlu', 'yasak'],
  secim: ['eq', 'in', 'zorunlu', 'yasak'],
  metin: ['zorunlu', 'yasak'],
};
const OP_LABEL: Record<Position['op'], string> = { min: 'En az', max: 'En çok', eq: 'Eşit', in: 'Şunlardan biri', zorunlu: 'Olmalı', yasak: 'Olmamalı' };

function RuleSheet({ init, clauses, facets, onClose, onSaved }: {
  init: Partial<Position>;
  clauses: PositionClause[];
  facets: Meta['facets'];
  onClose: () => void;
  onSaved: () => void;
}) {
  const [clause, setClause] = useState(init.clause ?? clauses[0]?.key ?? '');
  const c = clauses.find((x) => x.key === clause);
  const ops = OPS_BY_KIND[c?.kind ?? ''] ?? (['min', 'max', 'zorunlu', 'yasak'] as Array<Position['op']>);
  const [op, setOp] = useState<Position['op']>(init.op && ops.includes(init.op) ? init.op : ops[0]);
  const [value, setValue] = useState<unknown>(init.value ?? null);
  const [scope, setScope] = useState({ tip: init.scope?.tip ?? null, odeme: init.scope?.odeme ?? null, para: init.scope?.para ?? null });
  const [level, setLevel] = useState<Position['level']>(init.level ?? 'uyari');
  const [reason, setReason] = useState(init.reason ?? '');
  const save = useMutation({
    mutationFn: () => compareApi.positionSave({ id: init.id, clause, op, value, level, reason, scope }),
    onSuccess: onSaved,
  });
  const opNow = ops.includes(op) ? op : ops[0];
  const num = (v: string) => (v === '' ? null : Number(v));
  return (
    <Sheet title={init.id ? 'Kuralı düzelt' : 'Yeni kural'} onClose={onClose} wide
      footer={
        <>
          <button type="button" className={btnGhost} onClick={onClose}>Vazgeç</button>
          <button type="button" className={btnPrimary} disabled={save.isPending || !clause} onClick={() => save.mutate()}>Kaydet</button>
        </>
      }>
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Madde" wide>
          <select className={field} value={clause} onChange={(e) => { setClause(e.target.value); setValue(null); }}>
            <optgroup label="Sözleşme maddeleri (CRM)">
              {clauses.filter((x) => x.kind !== 'tur').map((x) => <option key={x.key} value={x.key}>{x.label}</option>)}
            </optgroup>
            <optgroup label="Belge madde türleri">
              {clauses.filter((x) => x.kind === 'tur').map((x) => <option key={x.key} value={x.key}>{x.label}</option>)}
            </optgroup>
          </select>
        </Field>
        <Field label="Kural">
          <select className={field} value={opNow} onChange={(e) => { setOp(e.target.value as Position['op']); setValue(null); }}>
            {ops.map((o) => <option key={o} value={o}>{OP_LABEL[o]}</option>)}
          </select>
        </Field>
        <Field label="Değer">
          {opNow === 'min' || opNow === 'max' ? (
            <input className={field} inputMode="decimal" value={value == null ? '' : String(value)} onChange={(e) => setValue(e.target.value)} />
          ) : opNow === 'eq' && c?.kind === 'bayrak' ? (
            <select className={field} value={value == null ? '' : value ? '1' : '0'} onChange={(e) => setValue(e.target.value === '1')}>
              <option value="">Seçin</option>
              <option value="1">Var</option>
              <option value="0">Yok</option>
            </select>
          ) : opNow === 'eq' ? (
            <select className={field} value={value == null ? '' : String(value)} onChange={(e) => setValue(e.target.value === '' ? null : Number(e.target.value))}>
              <option value="">Seçin</option>
              {(c?.options ?? []).map((o) => <option key={o.kod} value={o.kod}>{o.ad}</option>)}
            </select>
          ) : opNow === 'in' ? (
            <div className="grid gap-1">
              {(c?.options ?? []).map((o) => {
                const list = Array.isArray(value) ? (value as number[]) : [];
                return (
                  <label key={o.kod} className="flex min-h-11 items-center gap-2 text-[12.5px] sm:min-h-0">
                    <input type="checkbox" className="accent-canvas-violet" checked={list.includes(o.kod)}
                      onChange={(e) => setValue(e.target.checked ? [...list, o.kod] : list.filter((x) => x !== o.kod))} />
                    {o.ad}
                  </label>
                );
              })}
            </div>
          ) : (
            <p className="py-2 text-[12px] text-canvas-muted">Değer gerekmez.</p>
          )}
        </Field>
        <Field label="Sözleşme tipi (kapsam)">
          <select className={field} value={scope.tip ?? ''} onChange={(e) => setScope({ ...scope, tip: num(e.target.value) })}>
            <option value="">Hepsi</option>
            {facets.tip.map((x) => <option key={x.kod} value={x.kod}>{x.ad}</option>)}
          </select>
        </Field>
        <Field label="Ödeme türü (kapsam)">
          <select className={field} value={scope.odeme ?? ''} onChange={(e) => setScope({ ...scope, odeme: num(e.target.value) })}>
            <option value="">Hepsi</option>
            {facets.odeme.map((x) => <option key={x.kod} value={x.kod}>{x.ad}</option>)}
          </select>
        </Field>
        <Field label="Para birimi (kapsam)" hint="Tutar kuralında para birimini seçin; değer o para birimindedir.">
          <select className={field} value={scope.para ?? ''} onChange={(e) => setScope({ ...scope, para: num(e.target.value) })}>
            <option value="">Hepsi</option>
            {facets.para.map((x) => <option key={x.kod} value={x.kod}>{x.ad}</option>)}
          </select>
        </Field>
        <Field label="Düzey">
          <select className={field} value={level} onChange={(e) => setLevel(e.target.value as Position['level'])}>
            <option value="uyari">Uyarı</option>
            <option value="kirmizi">Kırmızı çizgi</option>
          </select>
        </Field>
        <Field label="Gerekçe" wide>
          <textarea className={`${field} min-h-20`} value={reason} maxLength={2000} onChange={(e) => setReason(e.target.value)} />
        </Field>
      </div>
      {save.error && <div className="mt-2"><Note tone="err">{errMsg(save.error)}</Note></div>}
    </Sheet>
  );
}
