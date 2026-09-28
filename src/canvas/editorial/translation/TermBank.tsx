import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Check, Download, Loader2, Pencil, Plus, Trash2 } from 'lucide-react';
import { ENGINE_ENABLED, translationApi, type Term } from '../../engine';
import { Loading, Note, Pill, btn, btnGhost, errText, field, label, nf } from '../../admin/ui';
import { useCan } from '../../useAdmin';
import { useDebounced, Panel } from '../kit';
import { FileButton, LANGS, langName } from './parts';
import { translationIoApi } from './ioApi';

/** Terim bankası: dil çifti başına genel terimler ve işe özel terimler. Onaylı terimi «Terim bankası düzenleme»
 *  yetkisi olan yazar; çevirmenin önerisi «aday» olarak gelir, burada onaylanır. */

type Draft = { source: string; target: string; forbidden: string; note: string };
const empty: Draft = { source: '', target: '', forbidden: '', note: '' };

function TermForm({
  initial,
  submit,
  pending,
  error,
  onCancel,
  submitLabel,
}: {
  initial: Draft;
  submit: (d: Draft) => void;
  pending: boolean;
  error: unknown;
  onCancel?: () => void;
  submitLabel: string;
}) {
  const [d, setD] = useState<Draft>(initial);
  const set = (k: keyof Draft) => (e: { target: { value: string } }) => setD({ ...d, [k]: e.target.value });
  return (
    <form
      className="grid gap-2 sm:grid-cols-2"
      onSubmit={(e) => {
        e.preventDefault();
        if (d.source.trim() && d.target.trim()) submit(d);
      }}
    >
      <label className="block">
        <span className={label}>Kaynak terim</span>
        <input value={d.source} onChange={set('source')} className={`${field} mt-1`} />
      </label>
      <label className="block">
        <span className={label}>Karşılık</span>
        <input value={d.target} onChange={set('target')} className={`${field} mt-1`} placeholder="Birden çok kabul için | ile ayırın" />
      </label>
      <label className="block">
        <span className={label}>Kullanılmayacak karşılıklar</span>
        <input value={d.forbidden} onChange={set('forbidden')} className={`${field} mt-1`} placeholder="; ile ayırın" />
      </label>
      <label className="block">
        <span className={label}>Not</span>
        <input value={d.note} onChange={set('note')} className={`${field} mt-1`} placeholder="Bağlam, kaynak, karar" />
      </label>
      {error ? (
        <div className="sm:col-span-2">
          <Note tone="err">{errText(error, 'Kaydedilemedi.')}</Note>
        </div>
      ) : null}
      <div className="flex gap-1.5 sm:col-span-2">
        <button type="submit" disabled={!d.source.trim() || !d.target.trim() || pending} className={`${btn} bg-canvas-violet text-white`}>
          {pending ? <Loader2 aria-hidden className="h-4 w-4 animate-spin" /> : null}
          {submitLabel}
        </button>
        {onCancel && (
          <button type="button" className={btnGhost} onClick={onCancel}>
            Vazgeç
          </button>
        )}
      </div>
    </form>
  );
}

const toDraft = (t: Term): Draft => ({ source: t.source, target: t.target, forbidden: t.forbidden.join('; '), note: t.note ?? '' });
const toBody = (d: Draft) => ({ source: d.source.trim(), target: d.target.trim(), forbidden: d.forbidden, note: d.note.trim() });

function TermRow({ t, canEdit, onChanged }: { t: Term; canEdit: boolean; onChanged: () => void }) {
  const [editing, setEditing] = useState(false);
  const upd = useMutation({ mutationFn: (b: Record<string, unknown>) => translationApi.updateTerm(t.id, b), onSuccess: () => { setEditing(false); onChanged(); } });
  const del = useMutation({ mutationFn: () => translationApi.deleteTerm(t.id), onSuccess: onChanged });
  if (editing)
    return (
      <li className="rounded-2xl border border-canvas-violet/40 bg-white p-3">
        <TermForm initial={toDraft(t)} submit={(d) => upd.mutate(toBody(d))} pending={upd.isPending} error={upd.error} onCancel={() => setEditing(false)} submitLabel="Kaydet" />
      </li>
    );
  return (
    <li className="rounded-2xl border border-slate-100 bg-white/85 px-3 py-2.5 text-[12.5px]">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="break-words leading-snug">
            <span className="font-extrabold">{t.source}</span>
            <span className="mx-1.5 text-canvas-muted">→</span>
            <span className="font-semibold">{t.target || '—'}</span>
          </p>
          {t.forbidden.length > 0 && <p className="mt-0.5 text-[11.5px] text-rose-700">Kullanılmaz: {t.forbidden.join(', ')}</p>}
          {t.note && <p className="mt-0.5 text-[11.5px] leading-snug text-canvas-muted">{t.note}</p>}
          <p className="mt-1 flex flex-wrap items-center gap-1.5 text-[11px] text-canvas-muted">
            <span>
              {langName(t.sourceLang)} → {langName(t.targetLang)}
            </span>
            {t.status === 'aday' ? <Pill tone="warn">Aday</Pill> : <Pill tone="ok">Onaylı</Pill>}
            {t.jobId ? <Pill tone="muted">Yalnız: {t.jobTitle ?? 'bir iş'}</Pill> : null}
            <span>{t.updatedBy ?? t.createdBy}</span>
          </p>
        </div>
        {canEdit && (
          <div className="flex shrink-0 gap-1">
            {t.status === 'aday' && (
              <button
                type="button"
                disabled={upd.isPending || !t.target}
                title={t.target ? 'Onayla' : 'Önce karşılık girin'}
                onClick={() => upd.mutate({ status: 'onayli' })}
                className={`${btn} min-h-9 bg-canvas-mint/15 px-2.5 text-emerald-700`}
              >
                <Check aria-hidden className="h-4 w-4" />
                Onayla
              </button>
            )}
            {t.jobId && t.status === 'onayli' && (
              <button type="button" disabled={upd.isPending} onClick={() => upd.mutate({ global: true })} className={`${btnGhost} min-h-9 px-2.5`} title="Bu dil çiftinin bütün işlerinde geçerli olsun">
                Genel yap
              </button>
            )}
            <button type="button" aria-label="Düzelt" onClick={() => setEditing(true)} className={`${btnGhost} min-h-9 px-2.5`}>
              <Pencil aria-hidden className="h-4 w-4" />
            </button>
            <button
              type="button"
              aria-label="Sil"
              disabled={del.isPending}
              onClick={() => {
                if (window.confirm(`«${t.source}» terimi silinsin mi?`)) del.mutate();
              }}
              className={`${btnGhost} min-h-9 px-2.5 text-rose-700`}
            >
              <Trash2 aria-hidden className="h-4 w-4" />
            </button>
          </div>
        )}
      </div>
      {(upd.error || del.error) && (
        <div className="mt-2">
          <Note tone="err">{errText(upd.error || del.error, 'İşlem yapılamadı.')}</Note>
        </div>
      )}
    </li>
  );
}

export default function TermBank() {
  const qc = useQueryClient();
  const canEdit = useCan('ceviri.terim');
  const canExport = useCan('veri.disa-aktar');
  const [src, setSrc] = useState('en');
  const [tgt, setTgt] = useState('tr');
  const [status, setStatus] = useState('');
  const [text, setText] = useState('');
  const q = useDebounced(text, 250);
  const [adding, setAdding] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const terms = useQuery({
    queryKey: ['translation', 'terms', src, tgt, status, q],
    queryFn: () => translationApi.terms({ src, tgt, status, q }),
    enabled: ENGINE_ENABLED,
    placeholderData: (prev) => prev,
  });
  const changed = () => void qc.invalidateQueries({ queryKey: ['translation', 'terms'] });
  const create = useMutation({
    mutationFn: (d: Draft) => translationApi.createTerm({ ...toBody(d), sourceLang: src, targetLang: tgt }),
    onSuccess: () => {
      setAdding(false);
      changed();
    },
  });
  const items = terms.data?.items ?? [];
  const candidates = items.filter((t) => t.status === 'aday').length;

  return (
    <div className="grid gap-3 lg:grid-cols-[minmax(0,320px)_minmax(0,1fr)] lg:items-start lg:gap-4">
      <Panel>
        <h2 className="px-1 text-[13px] font-extrabold">Dil çifti ve süzgeç</h2>
        <div className="mt-2 space-y-2">
          <div className="grid grid-cols-2 gap-2">
            <label className="block">
              <span className={label}>Kaynak</span>
              <select value={src} onChange={(e) => setSrc(e.target.value)} className={`${field} mt-1`}>
                {Object.entries(LANGS).map(([k, v]) => (
                  <option key={k} value={k}>
                    {v}
                  </option>
                ))}
              </select>
            </label>
            <label className="block">
              <span className={label}>Hedef</span>
              <select value={tgt} onChange={(e) => setTgt(e.target.value)} className={`${field} mt-1`}>
                {Object.entries(LANGS).map(([k, v]) => (
                  <option key={k} value={k}>
                    {v}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <label className="block">
            <span className={label}>Durum</span>
            <select value={status} onChange={(e) => setStatus(e.target.value)} className={`${field} mt-1`}>
              <option value="">Hepsi</option>
              <option value="onayli">Onaylı</option>
              <option value="aday">Aday (öneri)</option>
            </select>
          </label>
          <label className="block">
            <span className={label}>Ara</span>
            <input value={text} onChange={(e) => setText(e.target.value)} className={`${field} mt-1`} placeholder="Terim, karşılık ya da not" />
          </label>
        </div>
        <div className="mt-3 flex flex-wrap gap-2">
          {canEdit && (
            <FileButton
              tone="ghost"
              accept=".csv,.tsv,.txt"
              disabled={src === tgt}
              run={(f) => translationApi.importTerms(src, tgt, f)}
              onDone={(r) => {
                setNotice(`CSV: ${nf.format(r.added)} terim eklendi, ${nf.format(r.updated)} güncellendi${r.skipped ? `, ${nf.format(r.skipped)} satır boş olduğu için atlandı` : ''}.`);
                changed();
              }}
            >
              CSV içe aktar
            </FileButton>
          )}
          {canExport && (
            <a href={translationApi.termsCsvUrl(src, tgt)} className={btnGhost}>
              <Download aria-hidden className="h-4 w-4" />
              CSV indir
            </a>
          )}
          {canEdit && (
            <FileButton
              tone="ghost"
              accept=".tbx,.xml"
              disabled={src === tgt}
              run={(f) => translationIoApi.importTbx(src, tgt, f)}
              onDone={(r) => {
                setNotice(
                  `TBX: ${nf.format(r.added)} terim eklendi, ${nf.format(r.updated)} güncellendi` +
                    (r.unchanged ? `, ${nf.format(r.unchanged)} terim zaten aynıydı` : '') +
                    (r.skipped ? `, ${nf.format(r.skipped)} kayıtta bu dil çifti yoktu` : '') +
                    '.',
                );
                changed();
              }}
            >
              TBX içe aktar
            </FileButton>
          )}
          {canExport && src !== tgt && (
            <a href={translationIoApi.tbxUrl(src, tgt)} className={btnGhost}>
              <Download aria-hidden className="h-4 w-4" />
              TBX indir
            </a>
          )}
        </div>
        <p className="mt-2 px-1 text-[11px] leading-snug text-canvas-muted">
          CSV sütunları: kaynak; hedef; kullanılmayacak karşılıklar (; ile); not. İçe aktarım seçili dil çiftine yazılır, var olan terimi günceller.
        </p>
        <p className="mt-1 px-1 text-[11px] leading-snug text-canvas-muted">
          TBX (MultiTerm, memoQ, Phrase): tercih edilen karşılık ilk, kabul edilenler «|» ile eklenir; kullanımdan kalkmış terim kullanılmayacak karşılık olur. TBX indir yalnız onaylı terimleri verir.
        </p>
        {notice && (
          <div className="mt-2">
            <Note tone="ok">{notice}</Note>
          </div>
        )}
      </Panel>

      <Panel>
        <div className="flex flex-wrap items-baseline justify-between gap-2 px-1">
          <h2 className="text-[13px] font-extrabold">
            {langName(src)} → {langName(tgt)}
          </h2>
          <span className="font-mono text-[11px] tabular-nums text-canvas-muted">
            {nf.format(items.length)} terim{candidates ? ` · ${nf.format(candidates)} aday` : ''}
          </span>
        </div>
        {canEdit && (
          <div className="mt-2">
            {adding ? (
              <div className="rounded-2xl border border-slate-100 bg-white/85 p-3">
                <TermForm initial={empty} submit={(d) => create.mutate(d)} pending={create.isPending} error={create.error} onCancel={() => setAdding(false)} submitLabel="Ekle" />
              </div>
            ) : (
              <button type="button" className={`${btnGhost} w-full`} disabled={src === tgt} onClick={() => setAdding(true)}>
                <Plus aria-hidden className="h-4 w-4" />
                Terim ekle
              </button>
            )}
          </div>
        )}
        {!canEdit && (
          <p className="mt-1 px-1 text-[11.5px] leading-snug text-canvas-muted">Terim eklemek rolünüzde yok; çevirmen ekranından öneri gönderebilirsiniz.</p>
        )}
        {terms.error && <Note tone="err">{errText(terms.error, 'Terim bankası okunamadı.')}</Note>}
        {terms.isLoading ? (
          <Loading />
        ) : !items.length ? (
          <p className="mt-3 px-1 text-[12px] text-canvas-muted">{q ? 'Aramaya uyan terim yok.' : 'Bu dil çiftinde henüz terim yok.'}</p>
        ) : (
          <ul className="mt-2 space-y-1.5">
            {items.map((t) => (
              <TermRow key={t.id} t={t} canEdit={canEdit} onChanged={changed} />
            ))}
          </ul>
        )}
      </Panel>
    </div>
  );
}
