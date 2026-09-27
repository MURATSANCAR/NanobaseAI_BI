import { useEffect, useId, useRef, useState, type ReactNode } from 'react';
import { Check, ChevronDown, FileText, Loader2, Play } from 'lucide-react';
import { press } from '../shared';
import { voicesApi, type NarrationVoice } from './api';

/** Ses seçimi: kütüphane grup başlıklarıyla (Anlatıcı, Çocuk kitabı anlatıcısı, Yetişkin kitap okuyucusu, Karakter
 *  sesleri; önerilen ses rozetli, sunucunun verdiği sırayla erkek anlatıcıların en üstünde) ve her sesin yanında «dinle» (kısa örnek; sunucu ses başına bir kez üretir, sonra hemen çalar). Yüklenmiş
 *  seste sahibinin adı ve izin belgesi bağlantısı. Liste yerinde açılır (telefonda da tam genişlik), açılış hareketsiz:
 *  gün içinde defalarca açılan bir seçici. Seçince kapanır; Esc kapatır ve odağı düğmeye döndürür. */

type Props = {
  id: string;
  value: string;                                   // '' = anlatıcının sesi (allowNarrator)
  voices: NarrationVoice[];
  groups: Record<string, string>;
  onChange: (v: string) => void;
  onPlay: (voice: string, key: string) => void;
  playing: string | null;
  canPlay: boolean;
  allowNarrator?: boolean;
  label?: string;
};

export default function VoicePicker({ id, value, voices, groups, onChange, onPlay, playing, canPlay, allowNarrator, label }: Props) {
  const [open, setOpen] = useState(false);
  const btn = useRef<HTMLButtonElement>(null);
  const listId = useId();
  const cur = voices.find((v) => v.id === value);
  const order = Object.keys(groups);
  const byGroup = order.map((g) => [g, voices.filter((v) => v.group === g)] as const).filter(([, l]) => l.length);

  useEffect(() => {
    if (!open) return;
    const esc = (e: KeyboardEvent) => {
      if (e.key === 'Escape') { setOpen(false); btn.current?.focus(); }
    };
    document.addEventListener('keydown', esc);
    return () => document.removeEventListener('keydown', esc);
  }, [open]);

  const pick = (v: string) => {
    onChange(v);
    setOpen(false);
    btn.current?.focus();
  };

  return (
    <div className="min-w-0 flex-1">
      <button id={id} ref={btn} type="button" aria-expanded={open} aria-controls={listId} aria-label={label}
        onClick={() => setOpen((o) => !o)}
        className={`flex min-h-10 w-full min-w-0 items-center gap-2 rounded-xl border border-slate-200 bg-white/90 px-2.5 text-left text-[13px] outline-none focus-visible:border-canvas-violet ${press}`}>
        <span className="min-w-0 flex-1 truncate">
          {cur ? <><b>{cur.label}</b><span className="text-canvas-muted"> · {cur.note || groups[cur.group]}</span></>
            : allowNarrator && !value ? <span className="text-canvas-muted">Anlatıcının sesi</span>
              : <span className="text-canvas-muted">Ses seçin</span>}
        </span>
        <ChevronDown className={`h-4 w-4 shrink-0 text-canvas-muted ${open ? 'rotate-180' : ''}`} aria-hidden />
      </button>
      {open && (
        <div id={listId} role="radiogroup" aria-label={label ?? 'Ses'}
          className="mt-1.5 max-h-[60vh] overflow-y-auto overscroll-contain rounded-2xl border border-slate-200 bg-white p-1.5 shadow-lg">
          {allowNarrator && (
            <Row selected={!value} onPick={() => pick('')} title="Anlatıcının sesi" note="bu karakter anlatıcıyla okunur" />
          )}
          {byGroup.map(([g, list]) => (
            <div key={g} className="mt-1 first:mt-0">
              <p className="px-2 pb-1 pt-2 text-[10.5px] font-bold uppercase tracking-wide text-canvas-muted">{groups[g]}</p>
              {list.map((v) => (
                <Row key={v.id} selected={v.id === value} onPick={() => pick(v.id)} title={v.label} recommended={v.recommended}
                  note={v.uploaded ? `yüklenen ses · ${v.owner ?? ''}` : v.note}
                  extra={v.uploaded && v.document ? (
                    <a href={voicesApi.documentUrl(v.id)} target="_blank" rel="noopener noreferrer"
                      className="inline-flex min-h-10 shrink-0 items-center gap-1 rounded-lg px-1.5 text-[11px] font-bold text-canvas-violet underline">
                      <FileText className="h-3.5 w-3.5" aria-hidden />izin belgesi
                    </a>
                  ) : null}
                  play={(
                    <button type="button" aria-label={`«${v.label}» sesini dinle`} title="Dinle" disabled={!canPlay || !!playing}
                      onClick={() => onPlay(v.id, `lib-${v.id}`)}
                      className={`inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border border-slate-200 bg-white text-canvas-violet disabled:opacity-40 ${press}`}>
                      {playing === `lib-${v.id}` ? <Loader2 className="h-4 w-4 animate-spin motion-reduce:animate-none" aria-hidden /> : <Play className="h-4 w-4" aria-hidden />}
                    </button>
                  )} />
              ))}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function Row({ selected, onPick, title, note, extra, play, recommended }: {
  selected: boolean; onPick: () => void; title: string; note: string; extra?: ReactNode; play?: ReactNode; recommended?: boolean;
}) {
  return (
    <div className={`flex items-center gap-1.5 rounded-xl px-1 ${selected ? 'bg-violet-50/80' : ''}`}>
      <button type="button" role="radio" aria-checked={selected} onClick={onPick}
        className={`flex min-h-11 min-w-0 flex-1 items-center gap-2 rounded-lg px-1.5 text-left ${press}`}>
        <span className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-full border ${selected ? 'border-canvas-violet bg-canvas-violet text-white' : 'border-slate-300'}`}>
          {selected && <Check className="h-3 w-3" aria-hidden />}
        </span>
        <span className="min-w-0">
          <span className="flex min-w-0 items-center gap-1.5">
            <span className="truncate text-[13px] font-bold">{title}</span>
            {recommended && <span className="shrink-0 rounded-full bg-violet-100 px-1.5 py-0.5 text-[10px] font-bold text-canvas-violet">önerilen</span>}
          </span>
          {note && <span className="block truncate text-[11px] text-canvas-muted">{note}</span>}
        </span>
      </button>
      {extra}
      {play}
    </div>
  );
}
