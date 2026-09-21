import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { BookOpen, FolderOpen, Loader2, Search, User } from 'lucide-react';
import { ENGINE_ENABLED, editorialSearchApi, type SearchHit } from '../engine';
import { Note, Pill, errText, nf } from '../admin/ui';
import { dateTime } from '../format';
import { useDebounced } from './kit';
import AskBox from './AskBox';

/** Editoryal ana ekranın arama alanı: yazılan metin kitap adında, proje adında ve esere katkı veren
 *  kişilerin adında aranır. Kitaba tıklayınca o kitabın bütün süreçleri açılır. Kişiye tıklayınca
 *  kişinin kitapları listelenir. Arama CRM'de yapılır; uydurma sonuç yoktur. */

const ICON = { kitap: BookOpen, proje: FolderOpen, kisi: User } as const;

function Hit({ h, onPick }: { h: SearchHit; onPick: () => void }) {
  const Icon = ICON[h.kind];
  const body = (
    <>
      <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-canvas-violet/10 text-canvas-violet">
        <Icon aria-hidden className="h-3.5 w-3.5" />
      </span>
      <span className="min-w-0 flex-1">
        <span className="block break-words text-[12.5px] font-semibold leading-snug">{h.title}</span>
        <span className="block truncate text-[11px] text-canvas-muted">
          {[h.note, h.extra, h.date && dateTime(h.date)].filter(Boolean).join(' · ') || (h.kind === 'kisi' ? 'Esere katkı vermiş' : '')}
        </span>
      </span>
      {h.status && h.kind !== 'kisi' && <Pill tone="muted">{h.status}</Pill>}
    </>
  );
  const cls = 'flex w-full items-center gap-2 rounded-xl border border-slate-100 bg-white/85 px-2.5 py-2 text-left transition-colors duration-150 hover:bg-white active:scale-[0.99]';
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
    <div className="mt-3 rounded-2xl border border-slate-100 bg-white/85 p-3">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="text-[12.5px] font-extrabold">{person.title} · eserleri</h3>
        <button type="button" onClick={onClose} className="text-[11.5px] font-bold text-canvas-violet underline">
          Kapat
        </button>
      </div>
      {q.isLoading && <p className="mt-2 text-[12px] text-canvas-muted">Okunuyor…</p>}
      {!q.isLoading && !items.length && <p className="mt-2 text-[12px] text-canvas-muted">Bu kişiye bağlı kitap bulunamadı.</p>}
      <ul className="mt-2 space-y-1">
        {items.map((h) => (
          <li key={`${h.id}-${h.extra}`}>
            <Link to={`/kitap/${h.id}`} className="flex items-center justify-between gap-2 rounded-xl px-2 py-1.5 text-[12.5px] transition-colors duration-150 hover:bg-slate-50">
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
  const [person, setPerson] = useState<SearchHit | null>(null);
  const [tab, setTab] = useState<'ara' | 'sor'>('ara');
  const navigate = useNavigate();
  const q = useDebounced(text.trim(), 400);
  const res = useQuery({ queryKey: ['editorial', 'search', q], queryFn: () => editorialSearchApi.search(q), enabled: ENGINE_ENABLED && q.length >= 2 });
  const d = res.data;
  const total = (d?.books.length ?? 0) + (d?.projects.length ?? 0) + (d?.people.length ?? 0);
  const err = errText(res.error, 'Arama yapılamadı.');

  const TABS = [
    { id: 'ara' as const, label: 'Kitap ara', help: 'Kitap adı, proje adı ya da kişi yazın. Kitaba tıklayınca o kitabın bütün süreçleri tek ekranda açılır.' },
    { id: 'sor' as const, label: 'Kitaba sor', help: 'Okunmuş bir kitabın içeriğine sorun. Cevap kitabın metninden, sayfa numarasıyla gelir.' },
  ];

  return (
    <section className="glass-panel rounded-2xl p-4 shadow-glass-float sm:rounded-3xl sm:p-6">
      <div className="mx-auto max-w-[760px]">
        <div className="mx-auto flex w-fit gap-1 rounded-xl bg-slate-100/80 p-1">
          {TABS.map((t) => (
            <button
              key={t.id}
              type="button"
              onClick={() => setTab(t.id)}
              aria-pressed={tab === t.id}
              className={`min-h-9 rounded-lg px-3.5 text-[12.5px] font-bold transition-colors duration-150 ${
                tab === t.id ? 'bg-white text-canvas-ink shadow-sm' : 'text-canvas-muted hover:text-canvas-ink'
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>
        <p className="mx-auto mt-2.5 max-w-[60ch] text-center text-[12px] leading-snug text-canvas-muted">
          {TABS.find((t) => t.id === tab)?.help}
        </p>

        {tab === 'sor' ? (
          <div className="mt-3">
            <AskBox />
          </div>
        ) : (
          <>
        <form
          className="relative mt-3"
          onSubmit={(e) => {
            e.preventDefault();
            const first = d?.books[0];
            if (first) navigate(`/kitap/${first.id}`);
          }}
        >
          <Search aria-hidden className="pointer-events-none absolute left-4 top-1/2 h-5 w-5 -translate-y-1/2 text-canvas-muted" />
          <input
            type="search"
            value={text}
            onChange={(e) => {
              setText(e.target.value);
              setPerson(null);
            }}
            placeholder="Örnek: Kayıp Atlas, Ahmet Şimşirgil, kapak yenileme…"
            aria-label="Kitap, proje ya da kişi ara"
            className="min-h-[52px] w-full rounded-2xl border border-slate-200 bg-white/95 pl-12 pr-11 text-[15px] font-semibold outline-none transition-[border-color,box-shadow] duration-150 placeholder:font-medium placeholder:text-canvas-muted/70 focus:border-canvas-violet focus:shadow-[0_0_0_3px_rgba(124,92,255,.12)]"
          />
          {res.isFetching && <Loader2 aria-hidden className="absolute right-4 top-1/2 h-4 w-4 -translate-y-1/2 animate-spin text-canvas-muted" />}
        </form>

        {err && (
          <div className="mt-3">
            <Note tone="err">{err}</Note>
          </div>
        )}
        {q.length >= 2 && d && !total && !res.isFetching && (
          <p className="mt-3 text-center text-[12.5px] text-canvas-muted">“{q}” için kitap, proje ya da kişi bulunamadı.</p>
        )}

        {d && total > 0 && (
          <div className="mt-3 space-y-3">
            {d.books.length > 0 && (
              <div>
                <h3 className="px-1 pb-1 text-[11px] font-bold uppercase tracking-wide text-canvas-muted">Kitaplar ({nf.format(d.books.length)})</h3>
                <ul className="space-y-1">
                  {d.books.map((h) => (
                    <Hit key={h.id} h={h} onPick={() => undefined} />
                  ))}
                </ul>
              </div>
            )}
            {d.people.length > 0 && (
              <div>
                <h3 className="px-1 pb-1 text-[11px] font-bold uppercase tracking-wide text-canvas-muted">Kişiler ({nf.format(d.people.length)})</h3>
                <ul className="space-y-1">
                  {d.people.map((h) => (
                    <Hit key={h.id} h={h} onPick={() => setPerson(h)} />
                  ))}
                </ul>
                {person && <PersonBooks person={person} onClose={() => setPerson(null)} />}
              </div>
            )}
            {d.projects.length > 0 && (
              <div>
                <h3 className="px-1 pb-1 text-[11px] font-bold uppercase tracking-wide text-canvas-muted">Projeler ({nf.format(d.projects.length)})</h3>
                <ul className="space-y-1">
                  {d.projects.map((h) => (
                    <Hit key={h.id} h={h} onPick={() => navigate('/editor-atama')} />
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}
          </>
        )}
      </div>
    </section>
  );
}
