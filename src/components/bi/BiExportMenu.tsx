import { Download, FileSpreadsheet, FileText } from 'lucide-react';
import { useEffect, useId, useRef, useState } from 'react';
import clsx from 'clsx';
import { api } from '@/api/client';
import { useApiConfig } from '@/context/ApiContext';
import { t } from '@/i18n';

type Props = {
  sql?: string;
  onClose?: () => void;
  /** Compact trigger button (e.g. inside chat bubble). */
  className?: string;
};

export default function BiExportMenu({ sql, onClose, className }: Props) {
  const { config } = useApiConfig();
  const [busy, setBusy] = useState<string | null>(null);
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const menuId = useId();

  const exportFmt = async (fmt: 'csv' | 'xlsx' | 'pdf') => {
    if (!sql) return;
    setBusy(fmt);
    try {
      await api.bi.exportQuery(config, sql, fmt);
      setOpen(false);
      onClose?.();
    } finally {
      setBusy(null);
    }
  };

  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      if (!rootRef.current?.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false);
    };
    document.addEventListener('mousedown', onDoc);
    window.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDoc);
      window.removeEventListener('keydown', onKey);
    };
  }, [open]);

  if (!sql) return null;

  return (
    <div ref={rootRef} className={clsx('relative inline-flex', className)}>
      <button
        type="button"
        className="inline-flex min-h-10 items-center gap-1.5 rounded-lg border border-violet-200 bg-violet-50 px-2.5 text-xs font-semibold text-violet-800 hover:bg-violet-100"
        aria-expanded={open}
        aria-controls={menuId}
        onClick={() => setOpen((v) => !v)}
      >
        <Download className="h-3.5 w-3.5" />
        {t('bi.exportData')}
      </button>
      {open && (
        <div
          id={menuId}
          role="menu"
          className="absolute bottom-full right-0 z-20 mb-1 min-w-[11rem] overflow-hidden rounded-xl border border-surface-border bg-white py-1 shadow-lg sm:bottom-auto sm:top-full sm:mb-0 sm:mt-1"
        >
          {(['csv', 'xlsx', 'pdf'] as const).map((fmt) => (
            <button
              key={fmt}
              type="button"
              role="menuitem"
              className="flex min-h-11 w-full items-center gap-2 px-3 text-left text-sm text-slate-700 hover:bg-surface-overlay/80 disabled:opacity-50"
              disabled={Boolean(busy)}
              onClick={() => void exportFmt(fmt)}
            >
              {fmt === 'csv' ? (
                <Download className="h-4 w-4" />
              ) : fmt === 'xlsx' ? (
                <FileSpreadsheet className="h-4 w-4" />
              ) : (
                <FileText className="h-4 w-4" />
              )}
              {fmt.toUpperCase()}
              {busy === fmt ? '…' : ''}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
