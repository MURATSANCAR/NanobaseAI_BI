import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { BookOpen, Cake, Calendar, Flag } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import { evApi, fmtWeekday, type AgendaItem, type ImportantDay } from '../events/api';
import SqlInfo from '../components/SqlInfo';
import { kaynakOf } from '../components/kaynakOf';

/** Kampüs «Önemli günler ve ajanda» (M27 `/api/v1/events/me/agenda`):
 *  - Ajandam: sorumlusu olduğum fuar kartları, bana atanan hazırlık görevleri, CRM'de sorumlusu olduğum etkinlikler.
 *  - Önemli günler (herkese aynı, `agenda_days.py`): CRM özel günleri (bağlı kitap sayısıyla) ve İK resmî tatilleri.
 *  - Doğum günleri: İK kaydından gün/ay. Gerçek kayıt yokken ÖRNEK satırlar gösterilir (kullanıcı isteği 2026-09-30:
 *    kart boş görünmesin); «örnek» etiketlidir, İK'ya ilk doğum günü girilince kendiliğinden kalkar.
 *  Her bölümde ilk beşi gösterilir, kalanın sayısı yazılır. */

const SHOW = 5;
const SHOW_BDAY = 3;

/** Örnek doğum günleri: bugünden 2, 9 ve 16 gün sonra; kişi değildir, yalnız kartın dolu hâlini göstermek için. */
function sampleBirthdays(today: string): ImportantDay[] {
  const [y, m, d] = today.split('-').map(Number);
  const at = (n: number) => new Date(Date.UTC(y, m - 1, d + n)).toISOString().slice(0, 10);
  return [
    { kind: 'dogum', id: 'ornek-1', title: 'Ayşe Yılmaz', where: 'Editörlük', day: at(2), daysLeft: 2 },
    { kind: 'dogum', id: 'ornek-2', title: 'Mehmet Kaya', where: 'Satış', day: at(9), daysLeft: 9 },
    { kind: 'dogum', id: 'ornek-3', title: 'Zeynep Arslan', where: 'Grafik Tasarım', day: at(16), daysLeft: 16 },
  ];
}
const day = new Intl.DateTimeFormat('tr-TR', { day: 'numeric', month: 'long', timeZone: 'UTC' });
const fmt = (iso: string) => {
  const [y, m, d] = iso.split('-').map(Number);
  return day.format(new Date(Date.UTC(y, m - 1, d)));
};

export default function AgendaCard({ className = '' }: { className?: string }) {
  const q = useQuery({ queryKey: ['ev', 'agenda'], queryFn: evApi.agenda, enabled: ENGINE_ENABLED, retry: false, staleTime: 5 * 60_000 });
  const d = q.data;
  const items = d?.items ?? [];
  const fairs = items.filter((i) => i.kind === 'fuar');
  const rest = items.filter((i) => i.kind !== 'fuar');
  const shown = rest.slice(0, SHOW);
  const special = d?.importantDays ?? [];
  const realBdays = d?.birthdays ?? [];
  const sample = d != null && realBdays.length === 0;
  const bdays = sample ? sampleBirthdays(d.today) : realBdays;

  return (
    <section id="ajanda" className={`kp-card rounded-3xl border border-white/80 bg-white/90 p-4 ${className}`}>
      <div className="mb-3 flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <Calendar className="h-4 w-4 text-sky-600" aria-hidden />
          <h3 className="kp-display text-xs font-bold uppercase tracking-wider text-ink">Önemli Günler &amp; Ajanda</h3>
        </div>
        {d?.canOpen && <Link to="/etkinlikler" className="shrink-0 text-[11px] font-medium text-violet hover:underline">Takvim</Link>}
      </div>
      {q.isLoading && <p className="text-[11px] text-muted">Yükleniyor…</p>}
      {q.error && <p className="text-[11px] text-muted">Ajanda şu an okunamadı.</p>}

      {d && <SubHead top>Ajandam</SubHead>}
      {d && items.length === 0 && (
        <p className="text-[11px] leading-snug text-muted">Önümüzdeki günlerde sorumlusu olduğunuz etkinlik ya da görev yok.</p>
      )}
      {shown.length > 0 && (
        <div className="relative space-y-3.5 border-l-2 border-slate-200/70 pl-3.5 text-xs">
          {shown.map((i) => <Row key={`${i.kind}${i.id}`} i={i} />)}
        </div>
      )}
      {rest.length > SHOW && (
        <p className="mt-2 text-[11px] text-muted">
          +{rest.length - SHOW} kayıt daha
          <SqlInfo k={kaynakOf(d)} alan="_hepsi" label="Ajanda kayıtları" className="ml-0.5" />
          {d?.canOpen ? <> · <Link to="/etkinlikler" className="font-medium text-violet hover:underline">takvimde gör</Link></> : null}
        </p>
      )}
      {fairs.map((f) => (
        <FairBox key={f.id} f={f} />
      ))}

      {special.length > 0 && (
        <>
          <SubHead
            action={d?.canSeasons ? <Link to="/seo-geo/takvim" className="text-[11px] font-medium normal-case tracking-normal text-violet hover:underline">Sezon takvimi</Link> : null}
          >
            Önemli günler
          </SubHead>
          <ul className="space-y-2 text-xs">
            {special.slice(0, SHOW).map((g) => <DayRow key={`${g.kind}${g.id}`} g={g} />)}
          </ul>
          {special.length > SHOW && <p className="mt-2 text-[11px] text-muted">+{special.length - SHOW} gün daha</p>}
        </>
      )}

      {bdays.length > 0 && (
        <>
          <SubHead>Doğum günleri</SubHead>
          <ul className="space-y-2 text-xs">
            {bdays.slice(0, SHOW_BDAY).map((b) => <BirthdayRow key={b.id} b={b} sample={sample} />)}
          </ul>
          {bdays.length > SHOW_BDAY && <p className="mt-2 text-[11px] text-muted">+{bdays.length - SHOW_BDAY} kişi daha</p>}
        </>
      )}

      {d?.warnings.map((w) => <p key={w} className="mt-2 text-[11px] text-muted">{w}</p>)}
    </section>
  );
}

function SubHead({ children, action, top = false }: { children: ReactNode; action?: ReactNode; top?: boolean }) {
  return (
    <div className={`mb-2 flex items-center justify-between gap-2 ${top ? '' : 'mt-4'}`}>
      <span className="text-[11px] font-bold uppercase tracking-wide text-muted">{children}</span>
      {action}
    </div>
  );
}

const when = (n: number) => (n <= 0 ? 'Bugün' : n === 1 ? 'Yarın' : `${n} gün`);

function DayRow({ g }: { g: ImportantDay }) {
  const range = g.startsOn && g.endsOn && g.endsOn !== g.startsOn;
  const date = g.precision === 'hafta' && range ? `${fmt(g.startsOn!)} – ${fmt(g.endsOn!)}` : `${fmt(g.day)} ${fmtWeekday(g.day)}`;
  const holiday = g.kind === 'tatil' || g.holiday;
  return (
    <li className="flex flex-wrap items-start gap-x-2.5 gap-y-1">
      <span
        className={`kp-mono mt-0.5 w-14 shrink-0 rounded-md px-1 py-0.5 text-center text-[11px] font-semibold ${holiday ? 'bg-rose-50 text-rose-700' : 'bg-sky-50 text-sky-700'}`}
      >
        {when(g.daysLeft)}
      </span>
      <div className="min-w-[10rem] flex-1">
        <p className="font-bold leading-snug text-ink">{g.title}</p>
        <p className="text-[11px] text-muted">
          {g.precision === 'yaklasik' ? '≈ ' : ''}
          {date}
          {g.precision === 'hafta' ? ' · hafta' : ''}
          {holiday ? (g.half ? ' · yarım gün tatil' : ' · resmî tatil') : ''}
          {g.books ? (
            <span className="ml-1 inline-flex items-center gap-0.5 whitespace-nowrap">
              · <BookOpen className="h-3 w-3" aria-hidden /> {g.books} kitap
            </span>
          ) : null}
        </p>
      </div>
    </li>
  );
}

function BirthdayRow({ b, sample }: { b: ImportantDay; sample: boolean }) {
  return (
    <li className="flex items-center gap-2.5">
      <span className="grid h-7 w-7 shrink-0 place-items-center rounded-full bg-pink-100 text-pink-700">
        <Cake className="h-3.5 w-3.5" aria-hidden />
      </span>
      <div className="min-w-0 flex-1">
        <p className="truncate font-bold text-ink">
          {b.title}
          {sample && <span className="ml-1.5 rounded bg-slate-100 px-1 py-px text-[10px] font-semibold uppercase tracking-wide text-muted">örnek</span>}
        </p>
        <p className="truncate text-[11px] text-muted">{[`${fmt(b.day)} ${fmtWeekday(b.day)}`, b.where].filter(Boolean).join(' · ')}</p>
      </div>
      <span className="kp-mono shrink-0 text-[11px] font-semibold text-pink-700">{when(b.daysLeft)}</span>
    </li>
  );
}

function Row({ i }: { i: AgendaItem }) {
  const dot = i.kind === 'gorev' ? (i.late ? 'bg-rose-500' : 'bg-violet') : 'bg-sky-600';
  const tone = i.kind === 'gorev' ? (i.late ? 'text-rose-700' : 'text-violet') : 'text-sky-700';
  const body = (
    <>
      <div className={`absolute -left-[19px] top-1 h-2 w-2 rounded-full ${dot} ring-2 ring-white`} />
      <span className={`kp-mono text-[11px] font-semibold uppercase ${tone}`}>
        {fmt(i.day)} {fmtWeekday(i.day)}{i.time ? ` • ${i.time}` : ''}{i.kind === 'gorev' ? (i.late ? ' • gecikti' : ' • görev') : ''}
      </span>
      <h4 className="mt-0.5 font-bold text-ink">{i.title}</h4>
      {(i.where || i.type) && <p className="text-[11px] text-muted">{[i.where, i.kind === 'crm' ? i.type : null].filter(Boolean).join(' · ')}</p>}
    </>
  );
  return i.link ? <Link to={i.link} className="relative block rounded-lg hover:bg-slate-50">{body}</Link> : <div className="relative">{body}</div>;
}

function FairBox({ f }: { f: AgendaItem }) {
  const left = f.daysLeft ?? 0;
  return (
    <Link to={f.link ?? '/etkinlikler'} className="mt-3 block rounded-xl border border-violet/20 bg-violet/5 p-3 text-xs hover:bg-violet/10">
      <div className="flex items-center justify-between gap-2 font-bold text-ink">
        <span className="flex min-w-0 items-center gap-1">
          <Flag className="h-3.5 w-3.5 shrink-0 text-rose-500" aria-hidden /> <span className="truncate">{f.title}</span>
        </span>
        <span className="kp-mono whitespace-nowrap rounded bg-rose-100 px-1.5 py-0.5 text-[11px] text-rose-700">{left <= 0 ? 'Sürüyor' : `${left} Gün`}</span>
      </div>
      <p className="mt-1 text-[11px] text-muted">
        {fmt(f.startsOn ?? f.day)}{f.endsOn && f.endsOn !== f.startsOn ? ` – ${fmt(f.endsOn)}` : ''}{f.where ? ` · ${f.where}` : ''}
        {f.status === 'aday' ? ' · katılım kararı bekleniyor' : ''}
      </p>
    </Link>
  );
}
