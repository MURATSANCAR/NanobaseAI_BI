import { useEffect, useState, type ReactNode } from 'react';
import { Note, btnGhost, btnPrimary, field, label } from '../../admin/ui';
import Sheet from '../studio/reader/Sheet';

/** Gerekçe isteyen işlemler (red, revizyon, geri çekilme, yeniden açma) için kısa onay paneli. */
export default function NoteSheet({
  open,
  onClose,
  title,
  subtitle,
  noteLabel,
  required,
  confirm,
  tone = 'primary',
  pending,
  error,
  onConfirm,
  children,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  subtitle?: string;
  noteLabel: string;
  required?: boolean;
  confirm: string;
  tone?: 'primary' | 'danger';
  pending?: boolean;
  error?: string | null;
  onConfirm: (note: string) => void;
  children?: ReactNode;
}) {
  const [note, setNote] = useState('');
  useEffect(() => {
    if (open) setNote('');
  }, [open]);
  return (
    <Sheet open={open} onClose={onClose} modal title={title} subtitle={subtitle}>
      <form
        className="space-y-3 text-[12.5px]"
        onSubmit={(e) => {
          e.preventDefault();
          onConfirm(note.trim());
        }}
      >
        {children}
        <label className="block">
          <span className={label}>
            {noteLabel}
            {required && <span className="text-red-700"> *</span>}
          </span>
          <textarea required={required} rows={5} maxLength={8000} value={note} onChange={(e) => setNote(e.target.value)} className={`${field} mt-1`} autoFocus />
        </label>
        {error && <Note tone="err">{error}</Note>}
        <div className="flex flex-wrap justify-end gap-2">
          <button type="button" className={btnGhost} onClick={onClose}>
            Vazgeç
          </button>
          <button type="submit" disabled={pending} className={tone === 'danger' ? `${btnPrimary} !bg-rose-600` : btnPrimary}>
            {pending ? 'Kaydediliyor…' : confirm}
          </button>
        </div>
      </form>
    </Sheet>
  );
}
