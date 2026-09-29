import { useEffect, useMemo, useState, type ReactNode } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Download, Lock, Trash2 } from 'lucide-react';
import { Loading, Note, btnGhost, btnPrimary, errText, field as fieldCls, label as labelCls } from '../../../admin/ui';
import Sheet from '../../../editorial/studio/reader/Sheet';
import { FilePick } from '../../../components/FileDrop';
import { AskSheet } from '../../parts';
import { fileSize, longDay, portalApi, type PersonField, type PersonRow, type PortalMeta, type Value } from '../portalApi';

/** Personel kartı (İK yönetimi): alanlar gruplu form, belgeler (kayıt açıldıktan sonra), silme. Hassas alan yalnız
 *  yetkisi olana gelir; köprü görmediği alanı yazmaz. */
export default function PersonSheet({ id, meta, fields, people, onClose, onSaved }: {
  id: string | 'new' | null;
  meta: PortalMeta;
  fields: PersonField[];
  people: PersonRow[];
  onClose: () => void;
  onSaved: (id: string) => void;
}) {
  const qc = useQueryClient();
  const isNew = id === 'new';
  const detail = useQuery({ queryKey: ['hr', 'portal', 'person', id], queryFn: () => portalApi.person(id as string), enabled: !!id && !isNew });
  const [data, setData] = useState<Record<string, Value>>({});
  const [username, setUsername] = useState('');
  const [err, setErr] = useState<string | null>(null);
  const [askDelete, setAskDelete] = useState(false);
  const [askFile, setAskFile] = useState<{ id: string; name: string } | null>(null);
  const [uploading, setUploading] = useState<string | null>(null);
  const p = detail.data;
  useEffect(() => {
    setErr(null);
    if (isNew) { setData({ durum: 'Aktif' }); setUsername(''); }
    else if (p) { setData(p.data); setUsername(p.username ?? ''); }
  }, [isNew, p]);
  const visible = useMemo(() => fields.filter((f) => f.active && f.showAdmin && (meta.rights.sensitive || !f.sensitive)), [fields, meta.rights.sensitive]);
  const groups = useMemo(() => {
    const m = new Map<string, PersonField[]>();
    visible.filter((f) => f.type !== 'file').forEach((f) => m.set(f.group, [...(m.get(f.group) ?? []), f]));
    return [...m.entries()];
  }, [visible]);
  const docFields = visible.filter((f) => f.type === 'file');
  const canEdit = meta.rights.edit;
  const hiddenSensitive = !meta.rights.sensitive && fields.some((f) => f.active && f.sensitive && f.showAdmin);
  const refresh = () => {
    void qc.invalidateQueries({ queryKey: ['hr', 'portal'] });
  };
  const save = useMutation({
    mutationFn: () => {
      // Portal hesabı Profilim'i açar; köprü yalnız hassas yetkiyle yazar, yetkisiz gönderilmez.
      const body = meta.rights.sensitive ? { data, username: username.trim() || null } : { data };
      return isNew ? portalApi.createPerson(body) : portalApi.updatePerson(id as string, body);
    },
    onSuccess: (out) => { toast.success(isNew ? 'Personel kaydı açıldı.' : 'Kaydedildi.'); setErr(null); refresh(); onSaved(out.id); },
    onError: (e) => setErr(errText(e, 'Kaydedilemedi.')),
  });
  const del = useMutation({
    mutationFn: () => portalApi.deletePerson(id as string),
    onSuccess: () => { setAskDelete(false); toast.success('Personel kaydı silindi.'); refresh(); onClose(); },
    onError: (e) => toast.error(errText(e, 'Silinemedi.')),
    onSettled: () => setAskDelete(false),
  });
  const delFile = useMutation({
    mutationFn: (fid: string) => portalApi.deletePersonFile(id as string, fid),
    onSuccess: () => { setAskFile(null); toast.success('Belge silindi.'); refresh(); },
    onError: (e) => toast.error(errText(e, 'Silinemedi.')),
    onSettled: () => setAskFile(null),
  });
  const upload = async (fieldKey: string, file: File) => {
    setUploading(fieldKey);
    try {
      await portalApi.uploadPersonFile(id as string, fieldKey, file);
      toast.success('Belge yüklendi.');
      refresh();
    } catch (e) {
      toast.error(errText(e, 'Yüklenemedi.'));
    } finally {
      setUploading(null);
    }
  };
  const set = (k: string, v: string) => setData((d) => ({ ...d, [k]: v }));
  const title = isNew ? 'Yeni personel' : p ? p.adSoyad : 'Personel kartı';
  const managers = people.filter((x) => x.id !== id);
  return (
    <Sheet open={!!id} modal wide onClose={onClose} title={title}
      subtitle={p ? `Personel no ${p.idNo} · son değişiklik ${longDay(p.updatedAt)}${p.updatedBy ? ` · ${p.updatedBy}` : ''}` : 'Zorunlu alanlar * ile işaretli.'}>
      {detail.error && <Note tone="err">{errText(detail.error, 'Kart okunamadı.')}</Note>}
      {!isNew && detail.isLoading && <Loading />}
      {(isNew || p) && (
        <form className="flex flex-col gap-4" onSubmit={(e) => { e.preventDefault(); if (canEdit) save.mutate(); }}>
          {hiddenSensitive && (
            <Note tone="info"><Lock aria-hidden className="mr-1 inline h-3.5 w-3.5" />Hassas alanlar (T.C. kimlik, IBAN, adres, sağlık, yakın bilgisi, belgeler) «Hassas özlük verisi» yetkisiyle görünür; kayıttaki değerleri korunur.</Note>
          )}
          {groups.map(([g, fs]) => (
            <fieldset key={g} className="flex flex-col gap-2" disabled={!canEdit}>
              <legend className="mb-1 text-[13px] font-extrabold tracking-tight">{meta.groups[g] ?? g}</legend>
              <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-2">
                {fs.map((f) => (
                  <FieldInput key={f.key} f={f} value={data[f.key]} onChange={(v) => set(f.key, v)} managers={f.key === 'yonetici_id_no' ? managers : undefined}
                    selfNo={f.key === 'yonetici_id_no' ? String(data.id_no ?? '') : undefined} />
                ))}
                {g === 'kimlik' && meta.rights.sensitive && (
                  <label className="flex flex-col gap-1">
                    <span className={labelCls}>Portal hesabı</span>
                    <input className={fieldCls} value={username} onChange={(e) => setUsername(e.target.value)} placeholder="AD kullanıcı adı (ör. zeki)" autoComplete="off" />
                    <span className="text-[11px] leading-snug text-canvas-muted">Profilim bu hesapla eşleşir. Boşsa e-postanın @ öncesi kullanılır.</span>
                  </label>
                )}
              </div>
            </fieldset>
          ))}
          {err && <Note tone="err">{err}</Note>}
          {canEdit && (
            <div className="sticky bottom-0 -mx-4 flex flex-wrap items-center justify-between gap-2 border-t border-slate-100 bg-white/95 px-4 py-3 backdrop-blur">
              {!isNew && meta.rights.sensitive ? (
                <button type="button" className={`${btnGhost} !text-red-700`} onClick={() => setAskDelete(true)}><Trash2 aria-hidden className="h-4 w-4" />Kaydı sil</button>
              ) : <span />}
              <div className="flex gap-2">
                <button type="button" className={btnGhost} onClick={onClose}>Vazgeç</button>
                <button type="submit" className={btnPrimary} disabled={save.isPending}>{save.isPending ? 'Kaydediliyor…' : isNew ? 'Kaydı aç' : 'Kaydet'}</button>
              </div>
            </div>
          )}
        </form>
      )}
      {p && docFields.length > 0 && (
        <section className="mt-5 flex flex-col gap-2">
          <h3 className="text-[13px] font-extrabold tracking-tight">Belgeler</h3>
          <p className="text-[11.5px] text-canvas-muted">PDF, görsel ya da Word/Excel; en çok {meta.fileMaxMb} MB. Fotoğraf tek dosyadır, yenisi eskisinin yerine geçer.</p>
          <ul className="grid grid-cols-1 gap-2 sm:grid-cols-2">
            {docFields.map((f) => {
              const files = p.files.filter((x) => x.field === f.key);
              return (
                <li key={f.key} className="flex flex-col gap-1.5 rounded-xl bg-slate-50 p-2.5">
                  <div className="flex items-center justify-between gap-2">
                    <span className="flex min-w-0 items-center gap-1 text-[12.5px] font-bold">
                      <span className="truncate">{f.label}</span>
                      {f.required && <span className="text-red-600">*</span>}
                      {f.sensitive && <Lock aria-label="Hassas" className="h-3 w-3 shrink-0 text-canvas-muted" />}
                    </span>
                    {canEdit && (
                      <FilePick label={files.length && f.key === 'fotograf' ? 'Değiştir' : 'Yükle'} busy={uploading === f.key}
                        accept={f.key === 'fotograf' ? meta.imageAccept : meta.fileAccept} maxBytes={meta.fileMaxMb * 1024 * 1024}
                        onPick={(file) => void upload(f.key, file)} />
                    )}
                  </div>
                  {files.length ? files.map((x) => (
                    <div key={x.id} className="flex items-center gap-1.5 text-[12px]">
                      <button type="button" className="flex min-h-11 min-w-0 flex-1 items-center gap-1.5 rounded-lg px-1 text-left text-canvas-violet hover:bg-violet-50 sm:min-h-8"
                        onClick={() => void portalApi.personFile(p.id, x).catch((e) => toast.error(errText(e, 'İndirilemedi.')))}>
                        <Download aria-hidden className="h-3.5 w-3.5 shrink-0" />
                        <span className="min-w-0 flex-1 truncate">{x.filename}</span>
                        <span className="shrink-0 text-canvas-muted">{fileSize(x.size)}</span>
                      </button>
                      {canEdit && (
                        <button type="button" aria-label={`${x.filename} dosyasını sil`} className="inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-lg text-red-700 hover:bg-red-50 sm:h-8 sm:w-8"
                          onClick={() => setAskFile({ id: x.id, name: x.filename })}>
                          <Trash2 aria-hidden className="h-3.5 w-3.5" />
                        </button>
                      )}
                    </div>
                  )) : <span className="text-[11.5px] text-canvas-muted">Yüklenmemiş</span>}
                </li>
              );
            })}
          </ul>
        </section>
      )}
      {isNew && docFields.length > 0 && <p className="mt-4 text-[12px] text-canvas-muted">Belgeler, kayıt açıldıktan sonra bu karttan yüklenir.</p>}
      <AskSheet open={askDelete} title="Personel kaydını sil" danger confirm="Sil" busy={del.isPending}
        message={<>«{p?.adSoyad}» ({p?.idNo}) kaydı ve yüklü {p?.files.length ?? 0} belgesi silinecek. Ayrılan çalışan için kaydı silmek yerine durumunu «Pasif» yapın. Bu işlem geri alınamaz.</>}
        onClose={() => setAskDelete(false)} onConfirm={() => del.mutate()} />
      <AskSheet open={!!askFile} title="Belgeyi sil" danger confirm="Sil" busy={delFile.isPending}
        message={<>«{askFile?.name}» silinecek. Bu işlem geri alınamaz.</>}
        onClose={() => setAskFile(null)} onConfirm={() => askFile && delFile.mutate(askFile.id)} />
    </Sheet>
  );
}

function FieldInput({ f, value, onChange, managers, selfNo }: { f: PersonField; value: Value; onChange: (v: string) => void; managers?: PersonRow[]; selfNo?: string }) {
  const v = value === null || value === undefined ? '' : String(value);
  const wide = f.type === 'long_text';
  const head = (
    <span className={`${labelCls} flex items-center gap-1`}>
      {f.label}
      {f.required && <span className="text-red-600" aria-label="zorunlu">*</span>}
      {f.sensitive && <Lock aria-label="Hassas" className="h-3 w-3" />}
    </span>
  );
  let input: ReactNode;
  if (managers) {
    input = (
      <select className={fieldCls} value={v} onChange={(e) => onChange(e.target.value)} required={f.required}>
        <option value="">Seçin</option>
        {selfNo && <option value={selfNo}>Kendisi (en üst yönetici)</option>}
        {v && v !== selfNo && !managers.some((m) => m.idNo === v) && <option value={v}>{v}</option>}
        {managers.map((m) => <option key={m.id} value={m.idNo}>{m.adSoyad} · {m.idNo}</option>)}
      </select>
    );
  } else if (f.type === 'enum') {
    input = (
      <select className={fieldCls} value={v} onChange={(e) => onChange(e.target.value)} required={f.required}>
        <option value="">Seçin</option>
        {v && !f.options.includes(v) && <option value={v}>{v}</option>}
        {f.options.map((o) => <option key={o} value={o}>{o}</option>)}
      </select>
    );
  } else if (f.type === 'long_text') {
    input = <textarea className={`${fieldCls} min-h-[72px]`} value={v} onChange={(e) => onChange(e.target.value)} required={f.required} />;
  } else {
    const type = f.type === 'date' ? 'date' : f.type === 'email' ? 'email' : f.type === 'phone' ? 'tel' : 'text';
    const mode = f.type === 'number' ? 'decimal' : f.type === 'phone' ? 'tel' : undefined;
    input = <input className={fieldCls} type={type} inputMode={mode} value={v.slice(0, f.type === 'date' ? 10 : undefined)} onChange={(e) => onChange(e.target.value)} required={f.required} autoComplete="off" />;
  }
  return <label className={`flex min-w-0 flex-col gap-1 ${wide ? 'sm:col-span-2' : ''}`}>{head}{input}</label>;
}
