import { useState, type ReactNode } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { FileUp, Loader2, Plus } from 'lucide-react';
import { ENGINE_ENABLED, deskApi, type Work } from '../engine';
import { Note, btn, btnGhost, errText, field, label, nf } from '../admin/ui';
import { dateTime } from '../format';
import { Panel } from './kit';

/** M3 ve M5'in ortak eser seçicisi: eser listesi, yeni eser ve dosya yükleme. */

export const fmtBytes = (n: number) => (n >= 1e6 ? `${nf.format(Math.round(n / 1e5) / 10)} MB` : `${nf.format(Math.round(n / 1024))} KB`);

export function useWorks() {
  return useQuery({ queryKey: ['editorial', 'works'], queryFn: deskApi.works, enabled: ENGINE_ENABLED });
}

export function UploadButton({
  workId,
  kind,
  accept,
  children,
  onDone,
}: {
  workId: string;
  kind: 'manuscript' | 'proof';
  accept: string;
  children: ReactNode;
  onDone: () => void;
}) {
  const [err, setErr] = useState<string | null>(null);
  const up = useMutation({
    mutationFn: (f: File) => (kind === 'manuscript' ? deskApi.uploadManuscript(workId, f) : deskApi.uploadProof(workId, f)),
    onSuccess: () => {
      setErr(null);
      onDone();
    },
    onError: (e) => setErr(errText(e, 'Dosya yüklenemedi.')),
  });
  return (
    <div className="min-w-0">
      <label className={`${btn} cursor-pointer justify-center bg-gradient-to-r from-canvas-coral to-canvas-violet text-white shadow-md ${up.isPending ? 'pointer-events-none opacity-60' : ''}`}>
        {up.isPending ? <Loader2 aria-hidden className="h-4 w-4 animate-spin" /> : <FileUp aria-hidden className="h-4 w-4" />}
        {up.isPending ? 'Yükleniyor…' : children}
        <input
          type="file"
          accept={accept}
          className="sr-only"
          disabled={up.isPending}
          onChange={(e) => {
            const f = e.target.files?.[0];
            e.target.value = '';
            if (f) up.mutate(f);
          }}
        />
      </label>
      {err && (
        <div className="mt-2">
          <Note tone="err">{err}</Note>
        </div>
      )}
    </div>
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
        Yeni eser dosyası
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
      <div className="mt-2">
        <NewWork onCreated={onSelect} />
      </div>
      {!works.length && <p className="mt-3 px-1 text-[12px] leading-snug text-canvas-muted">Henüz eser dosyası yok. Yeni bir dosya açıp metni ya da provayı yükleyin.</p>}
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
    </Panel>
  );
}
