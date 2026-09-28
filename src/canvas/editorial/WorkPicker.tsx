import { useEffect, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Loader2, Plus } from 'lucide-react';
import { ENGINE_ENABLED, deskApi, type Work } from '../engine';
import { Note, btn, btnGhost, errText, field, label, nf } from '../admin/ui';
import { dateTime } from '../format';
import { FileDrop } from '../components/FileDrop';
import { MB } from '../components/fileDropRules';
import { Panel } from './kit';

/** M3 ve M5'in ortak eser seçicisi: sayfanın üstündeki yükleme alanı (dosyadan eser açar), eser listesi, boş eser. */

export const fmtBytes = (n: number) => (n >= 1e6 ? `${nf.format(Math.round(n / 1e5) / 10)} MB` : `${nf.format(Math.round(n / 1024))} KB`);

/** Köprüdeki sınır (editorial_desk.MAX_BYTES). */
export const DESK_MAX_BYTES = 120 * MB;

export function useWorks() {
  return useQuery({ queryKey: ['editorial', 'works'], queryFn: deskApi.works, enabled: ENGINE_ENABLED });
}

type Uploaded = { workId: string; title: string; version: number; isNew: boolean };

/** Redaksiyon ve son okumanın birincil yükleme alanı: sayfanın üstünde, liste boşken de görünür. Hedef «yeni eser»
 *  ise eser dosyası dosya adından açılır (köprü `works-from-file`; yükleme reddedilirse açılan eser geri alınır);
 *  bir eser seçiliyse o esere yeni sürüm yüklenir. Dosyadan açılan eserin adı hemen altında düzeltilir. */
export function WorkUpload({
  kind,
  works,
  selected,
  onUploaded,
  bare,
}: {
  kind: 'manuscript' | 'proof';
  works: Work[];
  selected: string | null;
  onUploaded: (workId: string) => void;
  /** Başka bir panelin içinde (son okumadaki «Belge / Prova» seçimi): kendi paneli çizilmez. */
  bare?: boolean;
}) {
  const qc = useQueryClient();
  const [target, setTarget] = useState<string>(selected ?? 'new');
  const [created, setCreated] = useState<{ id: string; title: string } | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  // Soldan başka eser seçilince hedef de ona döner; liste boşsa hedef yeni eserdir.
  useEffect(() => {
    setTarget(selected && works.some((w) => w.id === selected) ? selected : 'new');
  }, [selected, works]);
  const current = works.find((w) => w.id === target);
  const noun = kind === 'manuscript' ? 'metin' : 'prova';
  const run = async (f: File): Promise<Uploaded> => {
    if (current) {
      const r = kind === 'manuscript' ? await deskApi.uploadManuscript(current.id, f) : await deskApi.uploadProof(current.id, f);
      return { workId: current.id, title: current.title, version: r.version, isNew: false };
    }
    const r = await deskApi.createFromFile(kind, f);
    return { workId: r.workId, title: r.title, version: r.version, isNew: true };
  };
  const body = (
    <>
      <div className="grid gap-2.5 md:grid-cols-[minmax(0,260px)_minmax(0,1fr)] md:items-start">
        <label className="block min-w-0">
          <span className={label}>Nereye yüklensin</span>
          <select value={target} onChange={(e) => setTarget(e.target.value)} className={`${field} mt-1`}>
            <option value="new">Yeni eser dosyası (adı dosya adından)</option>
            {works.map((w) => (
              <option key={w.id} value={w.id}>
                {w.title} — yeni {noun} sürümü
              </option>
            ))}
          </select>
        </label>
        <FileDrop<Uploaded>
          accept={kind === 'manuscript' ? '.docx,.pdf,.txt,.md' : '.pdf'}
          maxBytes={DESK_MAX_BYTES}
          title={kind === 'manuscript' ? 'Metin dosyası yükle' : "Prova PDF'i yükle"}
          hint={
            current
              ? `«${current.title}» için yeni ${noun} sürümü açılır${kind === 'manuscript' ? '; bölümler baştan kurulur' : '; kontroller yeniden ölçülür, imzalar sıfırlanır'}.`
              : `Eser dosyası dosya adından açılır, ${noun} ilk sürüm olarak yüklenir; adı sonra düzeltebilirsiniz.`
          }
          run={run}
          onDone={async (r) => {
            setCreated(r.isNew ? { id: r.workId, title: r.title } : null);
            setNotice(r.isNew ? `«${r.title}» eser dosyası açıldı, ${noun} v${r.version} yüklendi.` : `«${r.title}»: ${noun} v${r.version} yüklendi.`);
            await qc.invalidateQueries({ queryKey: ['editorial'] });
            onUploaded(r.workId);
          }}
        />
      </div>
      {notice && (
        <div className="mt-2.5">
          <Note tone="ok">{notice}</Note>
        </div>
      )}
      {created && <RenameWork key={created.id} work={created} onSaved={(t) => setCreated({ id: created.id, title: t })} />}
    </>
  );
  return bare ? body : <Panel>{body}</Panel>;
}

/** Dosya adından açılan eserin adını hemen düzeltme. */
function RenameWork({ work, onSaved }: { work: { id: string; title: string }; onSaved: (title: string) => void }) {
  const qc = useQueryClient();
  const [title, setTitle] = useState(work.title);
  const save = useMutation({
    mutationFn: () => deskApi.updateWork(work.id, { title: title.trim() }),
    onSuccess: async () => {
      onSaved(title.trim());
      await qc.invalidateQueries({ queryKey: ['editorial'] });
    },
  });
  const dirty = !!title.trim() && title.trim() !== work.title;
  return (
    <form
      className="mt-2 flex flex-wrap items-end gap-1.5"
      onSubmit={(e) => {
        e.preventDefault();
        if (dirty && !save.isPending) save.mutate();
      }}
    >
      <label className="block min-w-0 flex-1 basis-56">
        <span className={label}>Eser adı (dosya adından geldi)</span>
        <input value={title} onChange={(e) => setTitle(e.target.value)} className={`${field} mt-1`} />
      </label>
      <button type="submit" disabled={!dirty || save.isPending} className={btnGhost}>
        {save.isPending ? <Loader2 aria-hidden className="h-4 w-4 animate-spin" /> : 'Adı kaydet'}
      </button>
      {save.error && (
        <div className="w-full">
          <Note tone="err">{errText(save.error, 'Ad kaydedilemedi.')}</Note>
        </div>
      )}
    </form>
  );
}

function NewWork({ onCreated }: { onCreated: (id: string) => void }) {
  const [open, setOpen] = useState(false);
  const [title, setTitle] = useState('');
  const [author, setAuthor] = useState('');
  const qc = useQueryClient();
  const create = useMutation({
    mutationFn: () => deskApi.createWork({ title: title.trim(), author: author.trim() || undefined }),
    onSuccess: async (w) => {
      setOpen(false);
      setTitle('');
      setAuthor('');
      await qc.invalidateQueries({ queryKey: ['editorial', 'works'] });
      onCreated(w.id);
    },
  });
  if (!open)
    return (
      <button type="button" className={`${btnGhost} w-full justify-center`} onClick={() => setOpen(true)}>
        <Plus aria-hidden className="h-4 w-4" />
        Boş eser dosyası aç
      </button>
    );
  return (
    <form
      className="space-y-2 rounded-2xl border border-slate-100 bg-white/85 p-3"
      onSubmit={(e) => {
        e.preventDefault();
        if (title.trim() && !create.isPending) create.mutate();
      }}
    >
      <div>
        <span className={label}>Eser adı</span>
        <input autoFocus value={title} onChange={(e) => setTitle(e.target.value)} className={`${field} mt-1`} />
      </div>
      <div>
        <span className={label}>Yazar</span>
        <input value={author} onChange={(e) => setAuthor(e.target.value)} className={`${field} mt-1`} />
      </div>
      {create.error && <Note tone="err">{errText(create.error, 'Eser açılamadı.')}</Note>}
      <div className="flex gap-1.5">
        <button type="submit" disabled={!title.trim() || create.isPending} className={`${btn} flex-1 justify-center bg-canvas-violet text-white`}>
          {create.isPending ? <Loader2 aria-hidden className="h-4 w-4 animate-spin" /> : 'Aç'}
        </button>
        <button type="button" className={btnGhost} onClick={() => setOpen(false)}>
          Vazgeç
        </button>
      </div>
    </form>
  );
}

export function WorkList({
  works,
  selected,
  onSelect,
  progress,
}: {
  works: Work[];
  selected: string | null;
  onSelect: (id: string) => void;
  progress: (w: Work) => string;
}) {
  return (
    <Panel>
      <div className="flex items-baseline justify-between gap-2 px-1">
        <h2 className="text-[13px] font-extrabold">Eser dosyaları</h2>
        <span className="font-mono text-[11px] tabular-nums text-canvas-muted">{nf.format(works.length)}</span>
      </div>
      {!works.length && (
        <p className="mt-2 px-1 text-[12px] leading-snug text-canvas-muted">
          Henüz eser dosyası yok. Yukarıdaki yükleme alanına dosyayı bırakın; eser dosyası dosya adından açılır.
        </p>
      )}
      <ul className="mt-2 space-y-1.5">
        {works.map((w) => (
          <li key={w.id}>
            <button
              type="button"
              onClick={() => onSelect(w.id)}
              aria-pressed={selected === w.id}
              className={`w-full rounded-2xl border px-3 py-2.5 text-left text-[12.5px] transition-colors duration-150 ${
                selected === w.id ? 'border-canvas-violet bg-white' : 'border-slate-100 bg-white/85 hover:bg-white'
              }`}
            >
              <span className="block break-words font-extrabold leading-snug">{w.title}</span>
              <span className="mt-0.5 block text-[11px] leading-snug text-canvas-muted">{w.author ? `${w.author} · ` : ''}{dateTime(w.createdAt)}</span>
              <span className="mt-1 block text-[11px] font-semibold text-canvas-ink">{progress(w)}</span>
            </button>
          </li>
        ))}
      </ul>
      <div className="mt-2">
        <NewWork onCreated={onSelect} />
      </div>
    </Panel>
  );
}
