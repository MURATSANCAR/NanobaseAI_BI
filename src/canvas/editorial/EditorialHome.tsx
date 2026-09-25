import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { ArrowRight, CalendarClock, ChevronRight } from 'lucide-react';
import { ENGINE_ENABLED, type Work, type ContractPage, type IntakeCard } from '../engine';
import { useTimasSession } from '../TimasSession';
import { useAdminMe } from '../useAdmin';
import { editorialHomeOptions } from './homeQuery';
import { intakeBoardOptions } from './queries';
import { MARK_LABEL, MarkButton, Progress, waitingSentence, waitingText } from './intake/parts';
import { Note, Pill, errText, nf, fmtDate } from '../admin/ui';
import { dateTime } from '../format';
import { Kpi, KpiRow, ModuleFrame, Panel } from './kit';
import SearchBox from './SearchBox';
import AskBox from './AskBox';

/** Masam: editörün ana ekranı. En üstte bugün yapacağı iş, altında kendisine atanmış bütün dosyalar.
 *  Dosya, CRM proje kartında editörü oturumdaki kişi olan yazar giriş süreci projesidir. */

/** Kişinin masasında duran iş: karar bekleyen öneri, onaylanmamış bölüm, imza bekleyen prova. */
function Desk({ works, user }: { works: Work[]; user: string }) {
  const mine = works.filter((w) => w.createdBy.toLowerCase() === user.toLowerCase() || w.members.includes(user.toLowerCase()) || w.signatures.total > 0);
  const openChapters = mine.reduce((a, w) => a + (w.chapters.total - w.chapters.approved), 0);
  const waitingProofs = mine.filter((w) => w.proof && w.signatures.signed < w.signatures.total);
  if (!mine.length) return null;
  return (
    <Panel>
      <div className="flex flex-wrap items-baseline justify-between gap-2 px-1">
        <h2 className="text-[13px] font-extrabold">Masanızdaki eserler</h2>
        <Link to="/redaksiyon" className="text-[11.5px] font-bold text-canvas-violet underline">
          Redaksiyona git
        </Link>
      </div>
      <ul className="mt-2 space-y-1.5">
        {mine.slice(0, 6).map((w) => {
          const open = w.chapters.total - w.chapters.approved;
          return (
            <li key={w.id} className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-slate-100 bg-white/85 px-3 py-2 text-[12.5px]">
              <span className="min-w-0">
                <span className="block break-words font-semibold leading-snug">{w.title}</span>
                <span className="block text-[11px] text-canvas-muted">
                  {w.manuscript ? `${nf.format(w.chapters.approved)}/${nf.format(w.chapters.total)} bölüm onaylı` : 'Metin yüklenmedi'}
                  {w.proof ? ` · prova v${w.proof.version}` : ''}
                </span>
              </span>
              <span className="flex shrink-0 gap-1.5">
                {open > 0 && <Pill tone="warn">{nf.format(open)} bölüm sürüyor</Pill>}
                {w.proof && w.signatures.total > 0 && w.signatures.signed < w.signatures.total && (
                  <Pill tone="err">{nf.format(w.signatures.total - w.signatures.signed)} imza bekliyor</Pill>
                )}
              </span>
            </li>
          );
        })}
      </ul>
      {(openChapters > 0 || waitingProofs.length > 0) && (
        <p className="mt-2 px-1 text-[11.5px] leading-snug text-canvas-muted">
          Toplam {nf.format(openChapters)} bölüm sürüyor
          {waitingProofs.length ? `, ${nf.format(waitingProofs.length)} prova imza bekliyor` : ''}.
        </p>
      )}
    </Panel>
  );
}

function Expiring({ data }: { data?: ContractPage }) {
  const items = (data?.items ?? []).slice(0, 5);
  if (!items.length) return null;
  return (
    <Panel>
      <div className="flex flex-wrap items-baseline justify-between gap-2 px-1">
        <h2 className="text-[13px] font-extrabold">Süresi yaklaşan sözleşmeler</h2>
        <Link to="/telif-sozlesme" className="text-[11.5px] font-bold text-canvas-violet underline">
          Hepsi ({nf.format(data?.total ?? 0)})
        </Link>
      </div>
      <ul className="mt-2 space-y-1.5">
        {items.map((c) => (
          <li key={c.id} className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-slate-100 bg-white/85 px-3 py-2 text-[12.5px]">
            <span className="min-w-0">
              <span className="block break-words font-semibold leading-snug">{c.books.map((b) => b.title).join(' · ') || 'Kitap bağlanmamış'}</span>
              <span className="block text-[11px] text-canvas-muted">
                {c.parties.map((p) => p.name).join(', ') || 'Taraf kaydı yok'} · {c.no}
              </span>
            </span>
            <Pill tone={c.daysLeft != null && c.daysLeft <= 14 ? 'err' : 'warn'}>{c.daysLeft != null ? `${nf.format(c.daysLeft)} gün` : dateTime(c.end)}</Pill>
          </li>
        ))}
      </ul>
    </Panel>
  );
}

const greeting = () => {
  const h = new Date().getHours();
  return h < 11 ? 'Günaydın' : h < 18 ? 'İyi günler' : 'İyi akşamlar';
};

/** "Şimdi yapılacaklar": tek iş, tek düğme. İşaretlenebilen adımda düğme işi kapatır, öbürlerinde projeyi açar. */
function TodoCard({ c }: { c: IntakeCard }) {
  const label = c.step ? MARK_LABEL[c.step] : undefined;
  return (
    <li className="flex flex-col rounded-2xl border border-slate-100 bg-white/90 p-3.5">
      <span className={`self-start rounded-md px-1.5 py-0.5 font-mono text-[11px] font-bold tabular-nums ${c.late ? 'bg-red-50 text-red-700' : 'bg-amber-50 text-amber-800'}`}>
        {waitingSentence(c)}
        {c.late ? ', gecikti' : ''}
      </span>
      <Link to={`/yazar-giris/${c.id}`} className="mt-2 break-words text-[14px] font-extrabold leading-snug hover:underline">
        {c.name || 'Adsız proje'}
      </Link>
      <span className="text-[11.5px] text-canvas-muted">{c.author || 'Yazar girilmemiş'}</span>
      <span className="mt-2 rounded-xl bg-slate-50 px-3 py-2 text-[12.5px] font-semibold leading-snug">{c.line}</span>
      <div className="mt-auto pt-3">
        {label && c.step ? (
          <MarkButton projectId={c.id} step={c.step} label={label} className="[&_button]:w-full" />
        ) : (
          <Link to={`/yazar-giris/${c.id}`} className="inline-flex min-h-11 w-full items-center justify-center gap-1.5 rounded-xl bg-canvas-violet px-3.5 py-2 text-[12.5px] font-extrabold text-white shadow-md transition-transform duration-150 ease-out active:scale-[0.97] sm:min-h-0">
            Aç
            <ArrowRight aria-hidden className="h-4 w-4" />
          </Link>
        )}
      </div>
    </li>
  );
}

const FILTERS = [
  { key: 'all', label: 'Tümü' },
  { key: 'waiting', label: 'Sizde bekleyen' },
  { key: 'board', label: 'Kurulda' },
  { key: 'done', label: 'Tamamlanan' },
] as const;

function MyFiles({ running, todo, completed }: { running: IntakeCard[]; todo: IntakeCard[]; completed: IntakeCard[] }) {
  const [f, setF] = useState<(typeof FILTERS)[number]['key']>('all');
  const lists = { all: [...running, ...completed], waiting: todo, board: running.filter((c) => c.phase === 2), done: completed };
  const items = lists[f];
  return (
    <Panel>
      <div className="flex flex-wrap items-center justify-between gap-2 px-1">
        <h2 className="text-[13px] font-extrabold">Tüm dosyalarım</h2>
        <div className="flex flex-wrap gap-1.5" role="group" aria-label="Süzgeç">
          {FILTERS.map((x) => (
            <button
              key={x.key}
              type="button"
              aria-pressed={f === x.key}
              onClick={() => setF(x.key)}
              className={`min-h-9 rounded-xl px-2.5 text-[11.5px] font-extrabold transition-colors duration-150 ${f === x.key ? 'bg-canvas-violet text-white' : 'bg-slate-100 text-canvas-ink hover:bg-slate-200'}`}
            >
              {x.label} <span className="font-mono tabular-nums">{nf.format(lists[x.key].length)}</span>
            </button>
          ))}
        </div>
      </div>
      {items.length === 0 ? (
        <p className="py-6 text-center text-[12.5px] text-canvas-muted">Bu süzgece uyan dosya yok.</p>
      ) : (
        <ul className="mt-2">
          {items.map((c) => (
            <li key={c.id} className="border-t border-slate-100 first:border-t-0">
              <Link to={`/yazar-giris/${c.id}`} className="grid gap-1.5 py-2.5 sm:grid-cols-[minmax(0,1fr)_200px_110px] sm:items-center sm:gap-4">
                <span className="min-w-0">
                  <span className="block break-words text-[13px] font-extrabold leading-snug">{c.name || 'Adsız proje'}</span>
                  <span className="block text-[11.5px] text-canvas-muted">{c.author || 'Yazar girilmemiş'}</span>
                </span>
                <span>
                  <span className={`block text-[11.5px] font-semibold ${c.late ? 'text-red-700' : c.complete ? 'text-emerald-700' : ''}`}>
                    {c.step ? `${c.line} (adım ${c.step}/9)` : c.line}
                  </span>
                  <span className="mt-1 block">
                    <Progress card={c} />
                  </span>
                </span>
                <span className="font-mono text-[11px] tabular-nums text-canvas-muted sm:text-right">{dateTime(c.modifiedOn)}</span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </Panel>
  );
}

type EditorRow = { editor: string; running: number; late: number; board: number; waiting: IntakeCard[] };

const COLS = 'grid grid-cols-[minmax(0,1fr)_repeat(4,64px)] items-center gap-2 sm:grid-cols-[minmax(0,1fr)_repeat(4,92px)]';

/** Yönetici görünümü: editör başına süren, bekleyen, kuruldaki ve geciken dosya. Bekleyen işi olan satır
 *  açılır ve o editörün sırasındaki işleri gösterir; açılışta hepsi kapalıdır ki özet tek bakışta okunsun. */
function EditorTable({ items, todo }: { items: IntakeCard[]; todo: IntakeCard[] }) {
  const [open, setOpen] = useState<string | null>(null);
  const by = new Map<string, EditorRow>();
  for (const c of items) {
    const k = c.editor || 'Editör atanmamış';
    const r = by.get(k) ?? { editor: k, running: 0, late: 0, board: 0, waiting: [] };
    r.running += 1;
    if (c.late) r.late += 1;
    if (c.phase === 2) r.board += 1;
    by.set(k, r);
  }
  for (const c of todo) by.get(c.editor || 'Editör atanmamış')?.waiting.push(c);
  const rows = [...by.values()].sort((a, b) => b.late - a.late || b.running - a.running);
  return (
    <Panel>
      <div className="flex flex-wrap items-baseline justify-between gap-2 px-1">
        <h2 className="text-[13px] font-extrabold">Editörlere göre dosyalar</h2>
        <span className="text-[11.5px] text-canvas-muted">Bekleyen işleri görmek için satıra dokunun</span>
      </div>
      <div className="mt-2 overflow-x-auto">
        <div className="min-w-[440px] text-[12.5px]">
          <div className={`${COLS} px-2 py-1.5 text-[11px] font-bold uppercase tracking-wide text-canvas-muted`}>
            <span>Editör</span>
            <span className="text-right">Süren</span>
            <span className="text-right">Bekleyen</span>
            <span className="text-right">Kurulda</span>
            <span className="text-right">Geciken</span>
          </div>
          <ul>
            {rows.map((r) => {
              const expanded = open === r.editor;
              const can = r.waiting.length > 0;
              const cells = (
                <>
                  <span className="flex min-w-0 items-center gap-1.5 font-semibold">
                    <ChevronRight
                      aria-hidden
                      className={`h-3.5 w-3.5 shrink-0 text-canvas-muted transition-transform duration-150 ease-[cubic-bezier(0.23,1,0.32,1)] motion-reduce:transition-none ${expanded ? 'rotate-90' : ''} ${can ? '' : 'invisible'}`}
                    />
                    <span className="break-words">{r.editor}</span>
                  </span>
                  <span className="text-right font-mono tabular-nums">{nf.format(r.running)}</span>
                  <span className="text-right font-mono tabular-nums">{nf.format(r.waiting.length)}</span>
                  <span className="text-right font-mono tabular-nums">{nf.format(r.board)}</span>
                  <span className="text-right font-mono tabular-nums">{nf.format(r.late)}</span>
                </>
              );
              return (
                <li key={r.editor} className="border-t border-slate-100">
                  {can ? (
                    <button
                      type="button"
                      aria-expanded={expanded}
                      onClick={() => setOpen(expanded ? null : r.editor)}
                      className={`${COLS} min-h-11 w-full rounded-lg px-2 py-1.5 text-left transition-colors duration-150 hover:bg-slate-50 ${expanded ? 'bg-slate-50' : ''}`}
                    >
                      {cells}
                    </button>
                  ) : (
                    <div className={`${COLS} min-h-11 px-2 py-1.5`}>{cells}</div>
                  )}
                  {expanded && (
                    <ul className="zk-scroll mb-2 ml-7 mr-2 max-h-[360px] overflow-y-auto overscroll-contain rounded-xl border border-slate-100 bg-white/90 px-3">
                      {r.waiting.map((c) => (
                        <li key={c.id} className="border-t border-slate-100 first:border-t-0">
                          <Link to={`/yazar-giris/${c.id}`} className="flex items-baseline justify-between gap-3 py-2 hover:underline">
                            <span className="min-w-0 break-words">
                              <b className="font-bold">{c.name || 'Adsız proje'}</b>
                              <span className="block text-[11.5px] text-canvas-muted">{c.line}</span>
                            </span>
                            <span className="shrink-0 font-mono text-[11px] tabular-nums text-canvas-muted">{waitingText(c)}</span>
                          </Link>
                        </li>
                      ))}
                    </ul>
                  )}
                </li>
              );
            })}
          </ul>
        </div>
      </div>
    </Panel>
  );
}

const pct = (n: number, of: number) => (of ? `%${nf.format(Math.round((n / of) * 100))}` : '%0');

export default function EditorialHome() {
  const session = useTimasSession();
  const home = useQuery(editorialHomeOptions(session.data?.username ?? ''));
  const intake = useQuery(intakeBoardOptions());
  const parts = home.data?.parts;
  const works = { data: home.data?.works };
  const desk = works.data?.items ?? [];
  const updated = Object.values(parts ?? {}).flatMap((part) => (part.updatedAt ? [part.updatedAt] : []));
  const lastUpdated = updated.length ? Math.min(...updated) : null;
  const refreshFailed = Object.values(parts ?? {}).some((part) => part.error);
  const d = intake.data;
  const adminMe = useAdminMe();
  // Düzen, CRM verisi (~10 sn) gelmeden yönetici kararından seçilir; yoksa sohbet açılışta yer değiştirir.
  const all = d ? d.todoScope === 'all' : !!adminMe.data?.isAdmin;
  const running = (d?.items ?? []).filter((c) => c.mine);
  const completed = (d?.completed ?? []).filter((c) => c.mine);
  const todo = d?.todo ?? [];
  const firstName = (session.data?.displayName || session.data?.username || '').split(' ')[0];
  const err = errText(home.error || intake.error, 'Masa okunamadı.');
  const lateRunning = running.filter((c) => c.late).length;
  const boardRunning = running.filter((c) => c.phase === 2).length;
  const allLate = (d?.items ?? []).filter((c) => c.late).length;
  const unassigned = (d?.items ?? []).filter((c) => !c.editor);
  const unassignedWaiting = todo.filter((c) => !c.editor).length;
  const lateHelp = d?.lateDays ? `bir adımda ${nf.format(d.lateDays)} günden uzun` : 'bekleme süresi aşılmış';

  const side = (
    <div className="space-y-3">
      <Panel>
        <h2 className="px-1 text-[13px] font-extrabold">Yaklaşan</h2>
        <ul className="mt-2 space-y-1.5 text-[12.5px]">
          <li className="flex items-start gap-2 rounded-xl border border-slate-100 bg-white/85 px-3 py-2">
            <CalendarClock aria-hidden className="mt-0.5 h-4 w-4 shrink-0 text-canvas-violet" />
            <span className="min-w-0">
              <Link to="/yayin-kurulu" className="font-semibold hover:underline">
                {d?.lastBoard ? `Son yayın kurulu ${dateTime(d.lastBoard)}` : 'Yayın kurulu'}
              </Link>
              <span className="block text-[11px] text-canvas-muted">
                {all
                  ? `${nf.format((d?.items ?? []).filter((c) => c.phase === 2).length)} dosya kurul evresinde`
                  : boardRunning
                    ? `${nf.format(boardRunning)} dosyanız kurul evresinde`
                    : 'Kurul evresinde dosyanız yok'}
              </span>
            </span>
          </li>
        </ul>
      </Panel>
      <Expiring data={parts?.expiring.data} />
      <p className="px-1 text-[11px] text-canvas-muted">
        {lastUpdated ? `Son güncelleme: ${fmtDate(new Date(lastUpdated * 1000).toISOString())}` : 'Kaydedilmiş veriler alınıyor…'}
      </p>
    </div>
  );

  return (
    <ModuleFrame
      route="/editoryal"
      crumb="Masam"
      title={firstName ? `${greeting()} ${firstName}` : 'Masam'}
      lead={
        !d || d.loading
          ? (all ? 'Bütün editörlerin dosyaları CRM\'den okunuyor…' : 'Size atanmış dosyalar CRM\'den okunuyor…')
          : all
            ? 'Yönetici görünümü: bütün editörlerin dosyaları.'
            : running.length
            ? `Size atanmış ${nf.format(running.length)} dosya sürüyor.${todo.length ? ` ${nf.format(todo.length)} tanesi şu an sizi bekliyor.` : ' Şu an sizi bekleyen iş yok.'}`
            : 'Şu an size atanmış, süren dosya yok. Yeni dosya atanınca burada görünür.'
      }
      source="Kaynak: CRM"
      presence={all && d ? `${nf.format(d.items.length)} dosya` : undefined}
      aside={<SearchBox />}
    >
      {!ENGINE_ENABLED && <Note tone="warn">Zeki AI bağlantısı bu derlemede tanımlı değil.</Note>}
      {err && <Note tone="err">{home.data || d ? 'Veriler yenilenemedi; son alınan bilgiler gösteriliyor.' : err}</Note>}
      {(refreshFailed || home.data?.stale) && <Note tone="warn">Bazı veriler henüz yenilenemedi. Son başarılı bilgiler korunuyor; güncelleme yeniden denenecek.</Note>}

      {d && !d.loading && (
        <KpiRow>
          {all ? (
            <>
              <Kpi label="Süren dosya" value={nf.format(d.items.length)} help="CRM'de açık yazar giriş projesi" />
              <Kpi label="Editörlerde bekleyen" value={nf.format(todo.length)} help="Sırası editörde olan adım" />
              <Kpi label="Geciken" value={nf.format(allLate)} help={`${pct(allLate, d.items.length)} · ${lateHelp}`} />
              <Kpi label="Editör atanmamış" value={nf.format(unassigned.length)} help={`${nf.format(unassignedWaiting)} tanesinde iş bekliyor`} />
            </>
          ) : (
            <>
              <Kpi label="Süren dosyanız" value={nf.format(running.length)} help="Size atanmış açık proje" />
              <Kpi label="Sizi bekleyen" value={nf.format(todo.length)} help="Sırası sizde olan adım" />
              <Kpi label="Geciken" value={nf.format(lateRunning)} help={lateHelp} />
              <Kpi label="Kurulda" value={nf.format(boardRunning)} help="Yayın kurulu evresinde" />
            </>
          )}
        </KpiRow>
      )}

      {all ? (
        /* Yönetici: özet tablo solda, sohbet ve takvim sağda; ikisi de ilk ekranda görünür. */
        <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_minmax(0,440px)] lg:items-start lg:gap-4">
          <div className="space-y-3">
            {d && <EditorTable items={d.items} todo={todo} />}
            {(running.length > 0 || completed.length > 0) && <MyFiles running={running} todo={todo} completed={completed} />}
            {works.data && <Desk works={desk} user={works.data.user} />}
          </div>
          <div className="space-y-3">
            <AskBox />
            {side}
          </div>
        </div>
      ) : (
        <>
          {todo.length > 0 && (
            <section>
              <h2 className="px-1 text-[13px] font-extrabold">Şimdi yapılacaklar</h2>
              <ul className="mt-2 grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
                {todo.map((c) => (
                  <TodoCard key={c.id} c={c} />
                ))}
              </ul>
            </section>
          )}

          {/* Sohbet açılışta üstte kalır (kullanıcı kararı 09-22); dosyası olan editörde işlerin altına iner. */}
          <AskBox />

          <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_minmax(0,400px)] lg:items-start lg:gap-4">
            <div className="space-y-3">
              {(running.length > 0 || completed.length > 0) && <MyFiles running={running} todo={todo} completed={completed} />}
              {works.data && <Desk works={desk} user={works.data.user} />}
            </div>
            {side}
          </div>
        </>
      )}
    </ModuleFrame>
  );
}
