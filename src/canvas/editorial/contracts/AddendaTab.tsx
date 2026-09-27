import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { Download, FilePlus2, Loader2 } from 'lucide-react';
import { toast } from 'sonner';
import { Note, Pill, btnGhost, btnPrimary, field } from '../../admin/ui';
import { Panel } from '../kit';
import { contractApi, downloadDocx, type Addendum, type Detail, type Meta, type Terms } from './api';
import { changedFields, show } from './terms';
import TermsForm from './TermsForm';
import { Field, Sheet, day, errMsg, stamp, today } from './ui';

/** Zeyilname: imzalı sözleşmenin şart değişikliği. Taslakta hazırlanır, «imzalandı» işaretlenince şartlara işlenir. */

/** Zeyilnamedeki değişiklikleri şartlara uygular (formu açarken taslağın yeni değerleri görünsün). */
function applied(terms: Terms, a: Addendum | null): Terms {
  if (!a) return terms;
  const t = JSON.parse(JSON.stringify(terms)) as Record<string, unknown>;
  for (const c of a.changes) {
    if (c.field.includes('.')) {
      const [g, s] = c.field.split('.');
      t[g] = { ...(t[g] as object), [s]: c.new };
    } else t[c.field] = c.new;
  }
  return t as unknown as Terms;
}

function AddendumSheet({ d, meta, a, onClose }: { d: Detail; meta: Meta; a: Addendum | null; onClose: () => void }) {
  const qc = useQueryClient();
  const [title, setTitle] = useState(a?.title ?? '');
  const [effectiveOn, setEffectiveOn] = useState(a?.effectiveOn ?? today());
  const [reason, setReason] = useState(a?.reason ?? '');
  const [terms, setTerms] = useState<Terms>(applied(d.terms, a));
  const changes = changedFields(d.terms, terms, meta);
  const n = Object.keys(changes).length;
  const save = useMutation({
    mutationFn: () =>
      a
        ? contractApi.addendumUpdate(a.id, { title, effectiveOn, reason, changes })
        : contractApi.addendum(d.key, { title, effectiveOn, reason, changes }),
    onSuccess: () => {
      toast.success(a ? 'Zeyilname güncellendi.' : 'Zeyilname taslağı açıldı.');
      qc.invalidateQueries({ queryKey: ['contracts'] });
      onClose();
    },
  });
  return (
    <Sheet
      title={a ? `${a.no} taslağı` : 'Yeni zeyilname'}
      onClose={onClose}
      wide
      footer={
        <>
          <button type="button" className={btnGhost} onClick={onClose}>Vazgeç</button>
          <button type="button" className={btnPrimary} disabled={!n || !title.trim() || save.isPending} onClick={() => save.mutate()}>
            {save.isPending && <Loader2 aria-hidden className="h-4 w-4 animate-spin" />}
            {n ? `${n} değişiklikle kaydet` : 'Değişiklik girin'}
          </button>
        </>
      }
    >
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Konu" wide>
          <input value={title} onChange={(e) => setTitle(e.target.value)} className={field} placeholder="ör. Süre uzatımı, e-kitap hakkı eklenmesi" />
        </Field>
        <Field label="Yürürlük tarihi">
          <input type="date" value={effectiveOn ?? ''} onChange={(e) => setEffectiveOn(e.target.value)} className={field} />
        </Field>
        <Field label="Gerekçe" wide>
          <textarea value={reason} onChange={(e) => setReason(e.target.value)} rows={2} className={field} />
        </Field>
      </div>
      <p className="mt-3 text-[12px] text-canvas-muted">Aşağıda yalnız değişecek alanları değiştirin; değişmeyen alanlar zeyilnameye girmez.</p>
      {n > 0 && (
        <ul className="mt-2 space-y-0.5 rounded-2xl bg-violet-50/70 p-3 text-[12px]">
          {Object.entries(changes).map(([k, v]) => (
            <li key={k}>
              <span className="font-semibold">{meta.labels[k] ?? k}</span>: {show(k, flat(d.terms, k), meta, d.terms.currency)} → {show(k, v, meta, terms.currency)}
            </li>
          ))}
        </ul>
      )}
      <div className="mt-3">
        <TermsForm value={terms} onChange={setTerms} meta={meta} />
      </div>
      {save.error && <div className="mt-3"><Note tone="err">{errMsg(save.error)}</Note></div>}
    </Sheet>
  );
}

function flat(t: Terms, key: string): unknown {
  if (!key.includes('.')) return (t as unknown as Record<string, unknown>)[key];
  const [g, s] = key.split('.');
  return ((t as unknown as Record<string, Record<string, unknown>>)[g] ?? {})[s];
}

function SignSheet({ a, onClose }: { a: Addendum; onClose: () => void }) {
  const qc = useQueryClient();
  const [on, setOn] = useState(today());
  const sign = useMutation({
    mutationFn: () => contractApi.addendumStatus(a.id, 'imzalandi', on),
    onSuccess: () => {
      toast.success(`${a.no} imzalandı; şartlara işlendi.`);
      qc.invalidateQueries({ queryKey: ['contracts'] });
      qc.invalidateQueries({ queryKey: ['editorial', 'contracts'] });
      onClose();
    },
  });
  return (
    <Sheet
      title={`${a.no} imzalandı`}
      onClose={onClose}
      footer={
        <>
          <button type="button" className={btnGhost} onClick={onClose}>Vazgeç</button>
          <button type="button" className={btnPrimary} disabled={sign.isPending} onClick={() => sign.mutate()}>
            {sign.isPending && <Loader2 aria-hidden className="h-4 w-4 animate-spin" />}
            İmzalandı, şartlara işle
          </button>
        </>
      }
    >
      <div className="space-y-3">
        <Field label="İmza tarihi">
          <input type="date" value={on} onChange={(e) => setOn(e.target.value)} className={field} />
        </Field>
        <Note tone="info">İşaretlenince {a.changes.length} değişiklik sözleşme şartlarına yazılır. Eski değerler zeyilnamede kalır; geri almak için yeni bir zeyilname gerekir.</Note>
        {sign.error && <Note tone="err">{errMsg(sign.error)}</Note>}
      </div>
    </Sheet>
  );
}

export default function AddendaTab({ d, meta }: { d: Detail; meta: Meta }) {
  const qc = useQueryClient();
  const [open, setOpen] = useState<Addendum | 'new' | null>(null);
  const [signing, setSigning] = useState<Addendum | null>(null);
  const cancel = useMutation({
    mutationFn: (a: Addendum) => contractApi.addendumStatus(a.id, 'iptal'),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['contracts'] }),
    onError: (e) => toast.error(errMsg(e) ?? 'İptal edilemedi.'),
  });
  const signed = !['taslak', 'imzada', 'iptal'].includes(d.status);
  const download = async (a: Addendum) => {
    try {
      const missing = await downloadDocx(`/addenda/${encodeURIComponent(a.id)}/document.docx`);
      if (missing.length) toast.warning(`Belgede doldurulamayan alan: ${missing.join(', ')}`);
    } catch (e) {
      toast.error(errMsg(e) ?? 'Belge indirilemedi.');
    }
  };
  return (
    <Panel>
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <p className="max-w-[70ch] text-[12px] text-canvas-muted">
          İmzalı sözleşmenin şartı zeyilnameyle değişir: süre uzatımı, oran değişikliği, yeni hak. «İmzalandı» işaretlenince şartlara işlenir.
        </p>
        {d.can.edit && signed && (
          <button type="button" className={btnPrimary} onClick={() => setOpen('new')}>
            <FilePlus2 aria-hidden className="h-4 w-4" />
            Yeni zeyilname
          </button>
        )}
      </div>
      {!signed && <Note tone="info">Sözleşme «{d.statusLabel}»; zeyilname imzalı sözleşmeye yapılır. Taslağı doğrudan düzenleyin.</Note>}
      {!d.addenda.length && signed && <p className="py-6 text-center text-[12.5px] text-canvas-muted">Zeyilname yok.</p>}
      <ul className="space-y-2">
        {d.addenda.map((a) => (
          <li key={a.id} className="rounded-2xl border border-slate-100 bg-white/85 p-3 text-[12.5px]">
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-mono text-[11.5px] font-bold">{a.no}</span>
              <span className="font-extrabold">{a.title}</span>
              <Pill tone={a.status === 'imzalandi' ? 'ok' : a.status === 'iptal' ? 'err' : 'warn'}>{a.statusLabel}</Pill>
              <span className="text-[11.5px] text-canvas-muted">
                Yürürlük {day(a.effectiveOn)}{a.signedOn ? ` · imza ${day(a.signedOn)} (${a.signedBy})` : ` · ${stamp(a.createdAt)} ${a.createdBy}`}
              </span>
            </div>
            <ul className="mt-1.5 space-y-0.5 text-[12px]">
              {a.changes.map((c) => (
                <li key={c.field}>
                  <span className="font-semibold">{c.label}</span>: <span className="text-canvas-muted line-through decoration-slate-300">{show(c.field, c.old, meta, d.terms.currency)}</span> → {show(c.field, c.new, meta, d.terms.currency)}
                </li>
              ))}
            </ul>
            {a.reason && <p className="mt-1 text-[11.5px] text-canvas-muted">Gerekçe: {a.reason}</p>}
            <div className="mt-2 flex flex-wrap gap-1.5">
              <button type="button" className={btnGhost} onClick={() => download(a)}>
                <Download aria-hidden className="h-4 w-4" />
                Word
              </button>
              {a.status === 'taslak' && d.can.edit && (
                <>
                  <button type="button" className={btnGhost} onClick={() => setOpen(a)}>Düzenle</button>
                  <button type="button" className={btnPrimary} onClick={() => setSigning(a)}>İmzalandı</button>
                  <button type="button" className={btnGhost} disabled={cancel.isPending} onClick={() => window.confirm(`${a.no} iptal edilsin mi?`) && cancel.mutate(a)}>İptal et</button>
                </>
              )}
            </div>
          </li>
        ))}
      </ul>
      {open && <AddendumSheet d={d} meta={meta} a={open === 'new' ? null : open} onClose={() => setOpen(null)} />}
      {signing && <SignSheet a={signing} onClose={() => setSigning(null)} />}
    </Panel>
  );
}
