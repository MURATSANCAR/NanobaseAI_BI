import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { BellRing, ChevronDown, Search } from 'lucide-react';
import { ENGINE_ENABLED, type IntakeCard } from '../../engine';
import { intakeBoardOptions } from '../queries';
import { Note, btnGhost, errText, field, nf } from '../../admin/ui';
import { dateTime, stamp } from '../../format';
import { ModuleFrame, Panel, useDebounced } from '../kit';
import { ProjectCard, TodoGroups, waitingText } from './parts';

/** Yazar giriş süreci: müşterinin 9 adımı üç evrede. Her kart bir CRM projesi; sütunda en uzun bekleyen üstte. */

const STEP_PAGE = 30;

const matches = (c: IntakeCard, q: string) => {
  if (!q) return true;
  const t = q.toLocaleLowerCase('tr');
  return [c.name, c.author, c.editor].some((v) => (v || '').toLocaleLowerCase('tr').includes(t));
};

function Column({ no, title, lead, steps, cards }: { no: number; title: string; lead: string; steps: string[]; cards: IntakeCard[] }) {
  const [shown, setShown] = useState(STEP_PAGE);
  return (
    <Panel>
      <div className="flex items-center justify-between gap-2">
        <h2 className="flex min-w-0 items-center gap-2 text-[15px] font-extrabold tracking-tight">
          <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-canvas-violet/10 font-mono text-[12px] text-canvas-violet">{no}</span>
          {title}
        </h2>
        <span className="shrink-0 font-mono text-[12px] font-bold tabular-nums text-canvas-muted">{nf.format(cards.length)} proje</span>
      </div>
      <p className="mt-1 text-[12px] text-canvas-muted">{lead}</p>
      <p className="mt-0.5 text-[11px] leading-snug text-canvas-muted">{steps.join(' · ')}</p>
      {cards.length === 0 ? (
        <p className="py-8 text-center text-[12.5px] text-canvas-muted">Bu evrede bekleyen proje yok.</p>
      ) : (
        <ul className="mt-3 space-y-2">
          {cards.slice(0, shown).map((c) => (
            <ProjectCard key={c.id} c={c} showEditor={no === 1} />
          ))}
        </ul>
      )}
      {cards.length > shown && (
        <button type="button" className={`${btnGhost} mt-3 w-full`} onClick={() => setShown((n) => n + STEP_PAGE)}>
          {nf.format(Math.min(STEP_PAGE, cards.length - shown))} proje daha göster ({nf.format(cards.length - shown)} kaldı)
        </button>
      )}
    </Panel>
  );
}

function Folded({ title, cards }: { title: string; cards: IntakeCard[] }) {
  const [open, setOpen] = useState(false);
  const [shown, setShown] = useState(STEP_PAGE);
  if (!cards.length) return null;
  return (
    <Panel>
      <button type="button" onClick={() => setOpen((v) => !v)} aria-expanded={open} className="flex w-full items-center justify-between gap-2 text-left">
        <span className="text-[13.5px] font-extrabold">
          {title} <span className="font-mono font-semibold tabular-nums text-canvas-muted">({nf.format(cards.length)})</span>
        </span>
        <ChevronDown aria-hidden className={`h-4 w-4 shrink-0 text-canvas-muted transition-transform duration-200 ease-out ${open ? 'rotate-180' : ''}`} />
      </button>
      {open && (
        <>
          <ul className="mt-3 grid gap-2 md:grid-cols-2 xl:grid-cols-3">
            {cards.slice(0, shown).map((c) => (
              <ProjectCard key={c.id} c={c} />
            ))}
          </ul>
          {cards.length > shown && (
            <button type="button" className={`${btnGhost} mt-3 w-full`} onClick={() => setShown((n) => n + STEP_PAGE)}>
              {nf.format(cards.length - shown)} proje daha var, göster
            </button>
          )}
        </>
      )}
    </Panel>
  );
}

export function TodoStrip({ todo, all = false }: { todo: IntakeCard[]; all?: boolean }) {
  if (!todo.length) return null;
  if (all)
    return (
      <section className="rounded-2xl border border-amber-200 bg-amber-50/90 p-3 sm:rounded-3xl sm:p-4">
        <h2 className="flex items-center gap-2 text-[14px] font-extrabold text-amber-900">
          <BellRing aria-hidden className="h-4 w-4" />
          Editörlerin bekleyen işleri: {nf.format(todo.length)}
        </h2>
        <p className="mt-0.5 text-[11.5px] text-amber-900/80">Yönetici görünümü. Editörün adına tıklayın, işleri açılır.</p>
        <div className="mt-2">
          <TodoGroups todo={todo} />
        </div>
      </section>
    );
  return (
    <section className="rounded-2xl border border-amber-200 bg-amber-50/90 p-3 sm:rounded-3xl sm:p-4">
      <h2 className="flex items-center gap-2 text-[14px] font-extrabold text-amber-900">
        <BellRing aria-hidden className="h-4 w-4" />
        Sizi bekleyen {nf.format(todo.length)} iş
      </h2>
      <ul className="mt-2 space-y-1.5">
        {todo.map((c) => (
          <li key={c.id}>
            <Link
              to={`/yazar-giris/${c.id}`}
              className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-0.5 rounded-xl bg-white/90 px-3 py-2 text-[12.5px] transition-transform duration-150 ease-out hover:bg-white active:scale-[0.99]"
            >
              <span className="min-w-0 break-words">
                <b className="font-extrabold">{c.name || 'Adsız proje'}</b>
                <span className="text-canvas-muted"> — {c.line.charAt(0).toLocaleLowerCase('tr') + c.line.slice(1)}</span>
              </span>
              <span className={`shrink-0 font-mono text-[11.5px] tabular-nums ${c.late ? 'font-bold text-red-700' : 'text-canvas-muted'}`}>
                {waitingText(c)}
                {c.late ? ', gecikti' : ''}
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}

export default function IntakeBoardScreen() {
  const board = useQuery(intakeBoardOptions());
  const [text, setText] = useState('');
  const [onlyLate, setOnlyLate] = useState(false);
  const [onlyMine, setOnlyMine] = useState(false);
  const [phase, setPhase] = useState(1);
  const q = useDebounced(text.trim(), 200);
  const d = board.data;

  const filtered = useMemo(
    () => (d?.items ?? []).filter((c) => matches(c, q) && (!onlyLate || c.late) && (!onlyMine || c.mine)),
    [d, q, onlyLate, onlyMine],
  );
  const err = errText(board.error, 'Süreç okunamadı.');
  const lead = d?.since
    ? `${dateTime(d.since)} sonrası açılan yeni ve yenileme projeleri. Veriler CRM'den kendiliğinden gelir, beş dakikada bir tazelenir.`
    : "Başvurudan stok kartına 9 adım. Veriler CRM'den kendiliğinden gelir.";

  const search = (
    <label className="relative block">
      <span className="sr-only">Kitap, yazar ya da editör ara</span>
      <Search aria-hidden className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-canvas-muted" />
      <input type="search" value={text} onChange={(e) => setText(e.target.value)} placeholder="Kitap, yazar ya da editör ara" className={`${field} pl-9`} />
    </label>
  );

  return (
    <ModuleFrame
      route="/yazar-giris"
      crumb="Yazar giriş süreci"
      title="Yazar giriş süreci"
      lead={lead}
      source={d?.updatedAt ? `Son okuma ${stamp(d.updatedAt * 1000)}` : 'Kaynak: CRM projeleri'}
      aside={search}
    >
      {!ENGINE_ENABLED && <Note tone="warn">Zeki AI bağlantısı bu derlemede tanımlı değil.</Note>}
      {err && <Note tone="err">{err}</Note>}
      {d?.error && <Note tone="warn">{d.error}</Note>}
      {d?.loading && <Note tone="info">CRM ilk kez okunuyor; birkaç dakika sürebilir. Ekran kendiliğinden yenilenecek.</Note>}

      {d && <TodoStrip todo={d.todo} all={d.todoScope === 'all'} />}

      {d && !d.loading && (
        <div className="flex flex-wrap items-center gap-2 px-1 text-[12px]">
          <button type="button" aria-pressed={onlyLate} onClick={() => setOnlyLate((v) => !v)} className={`${btnGhost} ${onlyLate ? 'ring-2 ring-canvas-violet' : ''}`}>
            Yalnız gecikenler ({nf.format(d.items.filter((c) => c.late).length)})
          </button>
          <button type="button" aria-pressed={onlyMine} onClick={() => setOnlyMine((v) => !v)} className={`${btnGhost} ${onlyMine ? 'ring-2 ring-canvas-violet' : ''}`}>
            Yalnız benimkiler ({nf.format(d.items.filter((c) => c.mine).length)})
          </button>
          <span className="text-canvas-muted">
            Gecikme: bir adımda {nf.format(d.lateDays)} günden uzun bekleme.
            {d.lastBoard && <> Son kurul {dateTime(d.lastBoard)}.</>}
          </span>
        </div>
      )}

      {d && !d.loading && (
        <>
          {/* Telefonda tek sütun: evre seçiciyle. */}
          <div className="grid grid-cols-3 gap-1 rounded-2xl bg-slate-100 p-1 lg:hidden" role="tablist" aria-label="Evre">
            {d.phases.map((ph) => (
              <button
                key={ph.no}
                type="button"
                role="tab"
                aria-selected={phase === ph.no}
                onClick={() => setPhase(ph.no)}
                className={`min-h-11 rounded-xl px-2 text-[12px] font-extrabold transition-colors duration-150 ${
                  phase === ph.no ? 'bg-canvas-violet text-white shadow-md' : 'text-canvas-ink'
                }`}
              >
                {ph.title} <span className="font-mono tabular-nums">{nf.format(filtered.filter((c) => c.phase === ph.no).length)}</span>
              </button>
            ))}
          </div>
          <div className="grid gap-3 lg:grid-cols-3 lg:items-start lg:gap-4">
            {d.phases.map((ph) => (
              <div key={ph.no} className={phase === ph.no ? '' : 'hidden lg:block'}>
                <Column
                  no={ph.no}
                  title={ph.title}
                  lead={ph.lead}
                  steps={ph.steps.map((s) => s.title)}
                  cards={filtered.filter((c) => c.phase === ph.no)}
                />
              </div>
            ))}
          </div>
          <Folded title="Tamamlanan projeler" cards={d.completed.filter((c) => matches(c, q))} />
          <Folded title="Reddedilen ve iptal edilen projeler" cards={d.closed.filter((c) => matches(c, q))} />
          {!d.audit && (
            <p className="px-1 text-[11px] text-canvas-muted">
              Editör atama ve rapor tarihleri CRM değişiklik kaydından okunamadı; bu adımlarda bekleme bir önceki bilinen tarihten sayılıyor.
            </p>
          )}
        </>
      )}
    </ModuleFrame>
  );
}
