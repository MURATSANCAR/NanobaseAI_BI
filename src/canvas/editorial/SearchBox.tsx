import { useEffect, useRef, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { BookOpen, FolderOpen, Loader2, Search, User, X } from 'lucide-react';
import { ENGINE_ENABLED, editorialSearchApi, type SearchHit } from '../engine';
import { Note, Pill, errText, nf } from '../admin/ui';
import { dateTime } from '../format';
import { useDebounced } from './kit';

/** Editoryal ana ekranın sağ üstündeki kitap arama: yazılan metin kitap adında, proje adında ve esere
 *  katkı veren kişilerin adında aranır. Sonuçlar alanın altında açılan bir panelde listelenir. Kitaba
 *  tıklayınca o kitabın bütün süreçleri açılır; kişiye tıklayınca kişinin kitapları listelenir.
 *  Arama CRM'de yapılır; uydurma sonuç yoktur. */

const ICON = { kitap: BookOpen, proje: FolderOpen, kisi: User } as const;

function Hit({ h, onPick }: { h: SearchHit; onPick: () => void }) {
  const Icon = ICON[h.kind];
  const body = (
    <>
      <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-canvas-violet/10 text-canvas-violet">
        <Icon aria-hidden className="h-4 w-4" />
      </span>
      <span className="min-w-0 flex-1">
        <span className="block break-words text-[13px] font-semibold leading-snug">{h.title}</span>
        <span className="block truncate text-[11px] text-canvas-muted">
          {[h.note, h.extra, h.date && dateTime(h.date)].filter(Boolean).join(' · ') || (h.kind === 'kisi' ? 'Esere katkı vermiş' : '')}
        </span>
      </span>
      {h.status && h.kind !== 'kisi' && <Pill tone="muted">{h.status}</Pill>}
    </>
  );
  const cls = 'zk-press flex w-full items-center gap-2.5 rounded-xl px-2.5 py-2 text-left hover:bg-canvas-violet/5';
  return h.kind === 'kitap' ? (
    <li>
      <Link to={`/kitap/${h.id}`} className={cls}>
        {body}
      </Link>
    </li>
  ) : (
    <li>
      <button type="button" onClick={onPick} className={cls}>
        {body}
      </button>
    </li>
  );
}

function PersonBooks({ person, onClose }: { person: SearchHit; onClose: () => void }) {
  const q = useQuery({ queryKey: ['editorial', 'personBooks', person.id], queryFn: () => editorialSearchApi.personBooks(person.id), enabled: ENGINE_ENABLED });
  const items = q.data?.items ?? [];
  return (
    <div className="mt-2 rounded-xl bg-slate-50/80 p-2.5">
      <div className="flex flex-wrap items-baseline justify-between gap-2 px-1">
        <h3 className="text-[12.5px] font-extrabold">{person.title} · eserleri</h3>
        <button type="button" onClick={onClose} className="text-[11.5px] font-bold text-canvas-violet underline">
          Kapat
        </button>
      </div>
      {q.isLoading && <p className="mt-2 px-1 text-[12px] text-canvas-muted">Okunuyor…</p>}
      {!q.isLoading && !items.length && <p className="mt-2 px-1 text-[12px] text-canvas-muted">Bu kişiye bağlı kitap bulunamadı.</p>}
      <ul className="mt-1.5 space-y-0.5">
        {items.map((h) => (
          <li key={`${h.id}-${h.extra}`}>
            <Link to={`/kitap/${h.id}`} className="flex items-center justify-between gap-2 rounded-lg px-2 py-1.5 text-[12.5px] transition-colors duration-150 hover:bg-white">
              <span className="min-w-0 break-words font-semibold leading-snug">{h.title}</span>
              <span className="shrink-0 text-[11px] text-canvas-muted">{h.extra}</span>
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}

export default function SearchBox() {
  const [text, setText] = useState('');
  const [open, setOpen] = useState(false);
  const [person, setPerson] = useState<SearchHit | null>(null);
  const wrap = useRef<HTMLDivElement>(null);
  const navigate = useNavigate();
  const q = useDebounced(text.trim(), 400);
  const res = useQuery({ queryKey: ['editorial', 'search', q], queryFn: () => editorialSearchApi.search(q), enabled: ENGINE_ENABLED && q.length >= 2 });
  const d = res.data;
  const total = (d?.books.length ?? 0) + (d?.projects.length ?? 0) + (d?.people.length ?? 0);
  const err = errText(res.error, 'Arama yapılamadı.');
  const show = open && q.length >= 2 && (!!d || !!err || res.isFetching);

  // Panel dışına tıklanınca kapanır.
  useEffect(() => {
    if (!open) return;
    const onDown = (e: PointerEvent) => {
      if (wrap.current && !wrap.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('pointerdown', onDown);
    return () => document.removeEventListener('pointerdown', onDown);
  }, [open]);

  return (
    <div ref={wrap} className="relative">
      <form
        className="zk-search-ring group relative rounded-2xl p-[2px] shadow-[0_14px_40px_-14px_rgba(124,92,255,.45)]"
        onSubmit={(e) => {
          e.preventDefault();
          const first = d?.books[0];
          if (first) navigate(`/kitap/${first.id}`);
        }}
      >
        <div className="relative rounded-[14px] bg-white">
          <span className="pointer-events-none absolute left-2.5 top-1/2 flex h-9 w-9 -translate-y-1/2 items-center justify-center rounded-xl bg-gradient-to-br from-canvas-coral to-canvas-violet text-white shadow-md">
            <Search aria-hidden className="h-[18px] w-[18px]" strokeWidth={2.5} />
          </span>
          <input
            type="search"
            value={text}
            onChange={(e) => {
              setText(e.target.value);
              setPerson(null);
              setOpen(true);
            }}
            onFocus={() => setOpen(true)}
            onKeyDown={(e) => {
              if (e.key === 'Escape') setOpen(false);
            }}
            placeholder="Kitap, yazar ya da proje ara…"
            aria-label="Kitap, proje ya da kişi ara"
            aria-expanded={show}
            className="min-h-[58px] w-full rounded-[14px] bg-transparent pl-[58px] pr-11 text-[16px] font-bold text-canvas-ink outline-none placeholder:font-semibold placeholder:text-canvas-muted/75 [&::-webkit-search-cancel-button]:hidden"
          />
          {res.isFetching ? (
            <Loader2 aria-hidden className="absolute right-4 top-1/2 h-4 w-4 -translate-y-1/2 animate-spin text-canvas-violet" />
          ) : (
            text && (
              <button
                type="button"
                aria-label="Aramayı temizle"
                onClick={() => {
                  setText('');
                  setPerson(null);
                }}
                className="absolute right-2.5 top-1/2 flex h-8 w-8 -translate-y-1/2 items-center justify-center rounded-lg text-canvas-muted transition-colors duration-150 hover:bg-slate-100 hover:text-canvas-ink"
              >
                <X aria-hidden className="h-4 w-4" />
              </button>
            )
          )}
        </div>
      </form>

      {show && (
        <div className="zk-pop absolute right-0 top-full z-30 mt-2 max-h-[70vh] w-full overflow-y-auto overscroll-contain rounded-2xl border border-white/70 bg-white/95 p-2 shadow-dock-shadow backdrop-blur-xl lg:w-[560px]">
          {err && <Note tone="err">{err}</Note>}
          {d && !total && !res.isFetching && <p className="px-2 py-3 text-center text-[12.5px] text-canvas-muted">“{q}” için kitap, proje ya da kişi bulunamadı.</p>}
          {!d && res.isFetching && <p className="px-2 py-3 text-center text-[12.5px] text-canvas-muted">Aranıyor…</p>}
          {d && total > 0 && (
            <div className="space-y-2">
              {d.books.length > 0 && (
                <div>
                  <h3 className="px-2.5 pb-0.5 pt-1 text-[10.5px] font-bold uppercase tracking-wide text-canvas-muted">Kitaplar ({nf.format(d.books.length)})</h3>
                  <ul>
                    {d.books.map((h) => (
                      <Hit key={h.id} h={h} onPick={() => undefined} />
                    ))}
                  </ul>
                </div>
              )}
              {d.people.length > 0 && (
                <div>
                  <h3 className="px-2.5 pb-0.5 pt-1 text-[10.5px] font-bold uppercase tracking-wide text-canvas-muted">Kişiler ({nf.format(d.people.length)})</h3>
                  <ul>
                    {d.people.map((h) => (
                      <Hit key={h.id} h={h} onPick={() => setPerson(h)} />
                    ))}
                  </ul>
                  {person && <PersonBooks person={person} onClose={() => setPerson(null)} />}
                </div>
              )}
              {d.projects.length > 0 && (
                <div>
                  <h3 className="px-2.5 pb-0.5 pt-1 text-[10.5px] font-bold uppercase tracking-wide text-canvas-muted">Projeler ({nf.format(d.projects.length)})</h3>
                  <ul>
                    {d.projects.map((h) => (
                      <Hit key={h.id} h={h} onPick={() => navigate('/editor-atama')} />
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
