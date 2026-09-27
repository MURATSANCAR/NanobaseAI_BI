import { useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Archive, ChevronLeft, Download, Eye, FileUp, Loader2, Plus, RotateCcw } from 'lucide-react';
import { toast } from 'sonner';
import { Note, Pill, btnGhost, btnPrimary, field } from '../../admin/ui';
import { ModuleFrame, Panel } from '../kit';
import { contractApi, downloadDocx, metaOptions, type Template } from './api';
import { Field, Sheet, errMsg, stamp } from './ui';

/** Şablon kütüphanesi: sözleşme, zeyilname ve hakediş bildirimi metinleri. Metin portalda yazılır ya da
 *  hukuk biriminin Word dosyası yüklenir; ikisinde de `{{alan}}` yer tutucuları doldurulur. */

function Editor({ t, fields, targets, kinds, onClose }: { t: Template | null; fields: Record<string, string>; targets: Record<string, string>; kinds: Record<string, string>; onClose: () => void }) {
  const qc = useQueryClient();
  const [name, setName] = useState(t?.name ?? '');
  const [target, setTarget] = useState<string>(t?.target ?? 'sozlesme');
  const [kind, setKind] = useState(t?.kind ?? '');
  const [description, setDescription] = useState(t?.description ?? '');
  const [body, setBody] = useState(t?.body ?? '');
  const [filter, setFilter] = useState('');
  const area = useRef<HTMLTextAreaElement>(null);
  const save = useMutation({
    mutationFn: () => contractApi.templateSave({ name, target: target as Template['target'], kind: kind || null, description, body, version: t?.version }, t?.id),
    onSuccess: () => {
      toast.success('Şablon kaydedildi.');
      qc.invalidateQueries({ queryKey: ['contracts', 'templates'] });
      onClose();
    },
  });
  const insert = (key: string) => {
    const el = area.current;
    const token = `{{${key}}}`;
    if (!el) return setBody((b) => b + token);
    const s = el.selectionStart ?? body.length;
    const e = el.selectionEnd ?? body.length;
    const next = body.slice(0, s) + token + body.slice(e);
    setBody(next);
    requestAnimationFrame(() => {
      el.focus();
      el.setSelectionRange(s + token.length, s + token.length);
    });
  };
  const used = new Set(Array.from(body.matchAll(/\{\{\s*([a-z0-9_.]+)\s*\}\}/g)).map((m) => m[1]));
  const unknown = [...used].filter((k) => !(k in fields));
  const shown = Object.entries(fields).filter(([k, v]) => !filter || `${k} ${v}`.toLocaleLowerCase('tr').includes(filter.toLocaleLowerCase('tr')));
  return (
    <Sheet
      title={t ? `${t.name} · sürüm ${t.version}` : 'Yeni şablon'}
      onClose={onClose}
      wide
      footer={
        <>
          <button type="button" className={btnGhost} onClick={onClose}>Vazgeç</button>
          <button type="button" className={btnPrimary} disabled={!name.trim() || save.isPending} onClick={() => save.mutate()}>
            {save.isPending && <Loader2 aria-hidden className="h-4 w-4 animate-spin" />}
            Kaydet
          </button>
        </>
      }
    >
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Ad" wide>
          <input value={name} onChange={(e) => setName(e.target.value)} className={field} />
        </Field>
        <Field label="Belge türü">
          <select value={target} onChange={(e) => setTarget(e.target.value)} className={field}>
            {Object.entries(targets).map(([k, v]) => (
              <option key={k} value={k}>{v}</option>
            ))}
          </select>
        </Field>
        <Field label="Sözleşme türü" hint="Boşsa her türde kullanılır.">
          <select value={kind} onChange={(e) => setKind(e.target.value)} className={field}>
            <option value="">Hepsi</option>
            {Object.entries(kinds).map(([k, v]) => (
              <option key={k} value={k}>{v}</option>
            ))}
          </select>
        </Field>
        <Field label="Açıklama" wide>
          <input value={description} onChange={(e) => setDescription(e.target.value)} className={field} />
        </Field>
      </div>
      <div className="mt-3 grid gap-3 lg:grid-cols-[minmax(0,1fr)_240px]">
        <div className="min-w-0">
          <span className="text-[11px] font-bold uppercase tracking-wide text-canvas-muted">Metin</span>
          <textarea
            ref={area}
            aria-label="Şablon metni"
            value={body}
            onChange={(e) => setBody(e.target.value)}
            rows={20}
            className={`${field} mt-1 min-h-[45dvh] font-serif text-[14px] leading-relaxed sm:text-[13px]`}
            placeholder={'# SÖZLEŞME BAŞLIĞI\n\n## Madde 1 — Taraflar\n{{yayinevi}} ile {{taraflar}} arasında…'}
          />
          <p className="mt-1 text-[11px] text-canvas-muted">«# » başlık, «## » madde başlığı; boş satır paragrafı ayırır. Word dosyası yüklüyse belge Word dosyasından üretilir.</p>
          {unknown.length > 0 && <div className="mt-2"><Note tone="warn">Tanınmayan alan: {unknown.map((u) => `{{${u}}}`).join(', ')} — belgede boş kalır.</Note></div>}
        </div>
        <div className="min-w-0">
          <span className="text-[11px] font-bold uppercase tracking-wide text-canvas-muted">Alanlar</span>
          <input type="search" value={filter} onChange={(e) => setFilter(e.target.value)} placeholder="Alan ara" className={`${field} mt-1`} />
          <ul className="mt-2 max-h-[40dvh] space-y-1 overflow-y-auto pr-1">
            {shown.map(([k, v]) => (
              <li key={k}>
                <button type="button" onClick={() => insert(k)} className="w-full rounded-lg px-2 py-1.5 text-left transition-transform duration-150 ease-out hover:bg-violet-50 active:scale-[0.98]">
                  <span className={`block font-mono text-[11px] ${used.has(k) ? 'text-canvas-violet' : ''}`}>{`{{${k}}}`}</span>
                  <span className="block text-[11px] leading-snug text-canvas-muted">{v}</span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      </div>
      {save.error && <div className="mt-3"><Note tone="err">{errMsg(save.error)}</Note></div>}
    </Sheet>
  );
}

function Preview({ t, onClose }: { t: Template; onClose: () => void }) {
  const [contract, setContract] = useState('');
  const q = useQuery({ queryKey: ['contracts', 'templates', 'preview', t.id, t.version, contract], queryFn: () => contractApi.templatePreview(t.id, contract || undefined) });
  return (
    <Sheet title={`Önizleme · ${t.name}`} onClose={onClose} wide>
      <Field label="Sözleşme (isteğe bağlı)" hint="Portal kaydı kimliği ya da CRM kimliği. Boşsa örnek değerlerle doldurulur.">
        <input value={contract} onChange={(e) => setContract(e.target.value.trim())} className={`${field} font-mono`} placeholder="ör. 3f2a…" />
      </Field>
      {q.error && <div className="mt-2"><Note tone="err">{errMsg(q.error)}</Note></div>}
      {q.data && (
        <>
          {q.data.sample && <div className="mt-2"><Note tone="info">Örnek değerlerle dolduruldu.</Note></div>}
          {q.data.fromDocx && <div className="mt-2"><Note tone="info">Word dosyasının düz metni; biçim indirilen belgede korunur.</Note></div>}
          {q.data.missing.length > 0 && <div className="mt-2"><Note tone="warn">Doldurulamayan: {q.data.missing.join(', ')}</Note></div>}
          <pre className="mt-3 whitespace-pre-wrap rounded-2xl border border-slate-100 bg-white p-3 font-serif text-[13px] leading-relaxed">{q.data.text}</pre>
        </>
      )}
      {q.isLoading && <p className="py-6 text-center text-[12.5px] text-canvas-muted">Dolduruluyor…</p>}
    </Sheet>
  );
}

function Card({ t, can, onEdit, onPreview }: { t: Template; can: boolean; onEdit: () => void; onPreview: () => void }) {
  const qc = useQueryClient();
  const file = useRef<HTMLInputElement>(null);
  const done = () => qc.invalidateQueries({ queryKey: ['contracts', 'templates'] });
  const upload = useMutation({ mutationFn: (f: File) => contractApi.templateDocx(t.id, f), onSuccess: (r) => { toast.success(`Word şablonu yüklendi (${r.fields.length} alan).`); done(); }, onError: (e) => toast.error(errMsg(e) ?? 'Yüklenemedi.') });
  const removeDocx = useMutation({ mutationFn: () => contractApi.templateDocxRemove(t.id), onSuccess: done, onError: (e) => toast.error(errMsg(e) ?? 'Kaldırılamadı.') });
  const archive = useMutation({ mutationFn: () => contractApi.templateSave({ active: !t.active, version: t.version }, t.id), onSuccess: done, onError: (e) => toast.error(errMsg(e) ?? 'Değiştirilemedi.') });
  return (
    <li className={`rounded-2xl border border-slate-100 bg-white/85 p-3 text-[12.5px] ${t.active ? '' : 'opacity-70'}`}>
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-extrabold">{t.name}</span>
        <Pill tone="violet">{t.targetLabel}</Pill>
        {t.kind && <Pill tone="muted">{t.kind}</Pill>}
        {t.hasDocx && <Pill tone="ok">Word: {t.docxName}</Pill>}
        {!t.active && <Pill tone="muted">Arşivde</Pill>}
        <span className="text-[11.5px] text-canvas-muted">sürüm {t.version} · {stamp(t.updatedAt)} {t.updatedBy}</span>
      </div>
      {t.description && <p className="mt-1 text-[11.5px] text-canvas-muted">{t.description}</p>}
      <p className="mt-1 text-[11.5px] text-canvas-muted">{t.fields.length} alan{t.unknownFields.length ? ` · tanınmayan: ${t.unknownFields.join(', ')}` : ''}</p>
      <div className="mt-2 flex flex-wrap gap-1.5">
        <button type="button" className={btnGhost} onClick={onPreview}>
          <Eye aria-hidden className="h-4 w-4" />
          Önizle
        </button>
        {t.hasDocx && (
          <button type="button" className={btnGhost} onClick={() => downloadDocx(`/templates/${encodeURIComponent(t.id)}/docx`).catch((e) => toast.error(errMsg(e) ?? 'İndirilemedi.'))}>
            <Download aria-hidden className="h-4 w-4" />
            Word şablonu
          </button>
        )}
        {can && (
          <>
            <button type="button" className={btnGhost} onClick={onEdit}>Düzenle</button>
            <input ref={file} type="file" accept=".docx,application/vnd.openxmlformats-officedocument.wordprocessingml.document" className="hidden" onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) upload.mutate(f);
              e.target.value = '';
            }} />
            <button type="button" className={btnGhost} disabled={upload.isPending} onClick={() => file.current?.click()}>
              {upload.isPending ? <Loader2 aria-hidden className="h-4 w-4 animate-spin" /> : <FileUp aria-hidden className="h-4 w-4" />}
              {t.hasDocx ? 'Word dosyasını değiştir' : 'Word yükle'}
            </button>
            {t.hasDocx && <button type="button" className={btnGhost} onClick={() => window.confirm('Word dosyası kaldırılsın mı? Belge metin şablonundan üretilir.') && removeDocx.mutate()}>Word'ü kaldır</button>}
            <button type="button" className={btnGhost} onClick={() => archive.mutate()}>
              {t.active ? <Archive aria-hidden className="h-4 w-4" /> : <RotateCcw aria-hidden className="h-4 w-4" />}
              {t.active ? 'Arşivle' : 'Geri al'}
            </button>
          </>
        )}
      </div>
    </li>
  );
}

export default function TemplatesScreen() {
  const [archived, setArchived] = useState(false);
  const meta = useQuery(metaOptions());
  const q = useQuery({ queryKey: ['contracts', 'templates', 'all', archived], queryFn: () => contractApi.templates({ archived }) });
  const [edit, setEdit] = useState<Template | 'new' | null>(null);
  const [preview, setPreview] = useState<Template | null>(null);
  const data = q.data;
  const can = !!data?.can.templates;
  const groups = Object.entries(data?.targets ?? {}).map(([k, v]) => ({ k, v, items: (data?.items ?? []).filter((t) => t.target === k) }));
  return (
    <ModuleFrame route="/telif-sozlesme" crumb="Sözleşmeler" title="Şablon kütüphanesi" lead="Sözleşme, zeyilname ve hakediş bildirimi şablonları. Her kayıt sürümü bir artırır; sözleşme hangi sürümden üretildiğini geçmişine yazar." source="Portal">
      <div className="flex flex-wrap items-center justify-between gap-2 px-1">
        <Link to="/telif-sozlesme" className="inline-flex min-h-11 items-center gap-1 text-[12px] font-bold text-canvas-violet hover:underline sm:min-h-0">
          <ChevronLeft aria-hidden className="h-4 w-4" />
          Bütün sözleşmeler
        </Link>
        <div className="flex flex-wrap items-center gap-2">
          <label className="flex min-h-11 items-center gap-2 text-[12px] font-semibold sm:min-h-0">
            <input type="checkbox" checked={archived} onChange={(e) => setArchived(e.target.checked)} className="h-4 w-4 accent-[#7c3aed]" />
            Arşivdekileri göster
          </label>
          {can && (
            <button type="button" className={btnPrimary} onClick={() => setEdit('new')}>
              <Plus aria-hidden className="h-4 w-4" />
              Yeni şablon
            </button>
          )}
        </div>
      </div>
      {q.error && <Note tone="err">{errMsg(q.error)}</Note>}
      {q.isLoading && <p className="py-10 text-center text-[12.5px] text-canvas-muted">Okunuyor…</p>}
      {groups.map((g) => (
        <Panel key={g.k}>
          <h2 className="mb-2 text-[14px] font-extrabold">{g.v}</h2>
          {!g.items.length && <p className="text-[12px] text-canvas-muted">Şablon yok.</p>}
          <ul className="space-y-2">
            {g.items.map((t) => (
              <Card key={t.id} t={t} can={can} onEdit={() => setEdit(t)} onPreview={() => setPreview(t)} />
            ))}
          </ul>
        </Panel>
      ))}
      {edit && data && meta.data && (
        <Editor t={edit === 'new' ? null : edit} fields={data.fields} targets={data.targets} kinds={meta.data.kinds} onClose={() => setEdit(null)} />
      )}
      {preview && <Preview t={preview} onClose={() => setPreview(null)} />}
    </ModuleFrame>
  );
}
