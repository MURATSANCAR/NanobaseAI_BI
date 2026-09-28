import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Calendar, Flag } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import { evApi, fmtWeekday, type AgendaItem } from '../events/api';
import SqlInfo from '../components/SqlInfo';
import { kaynakOf } from '../components/kaynakOf';

/** Kampüs «Önemli günler ve ajanda»: sorumlusu olduğum yaklaşan fuar kartları, bana atanan hazırlık görevleri ve CRM'de
 *  sorumlusu olduğum etkinlikler (M27 `/api/v1/events/me/agenda`). Yalnız kişinin kendi kayıtları; ilk beşi gösterilir,
 *  kalanın sayısı yazılır. */

const SHOW = 5;
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
      {d?.warnings.map((w) => <p key={w} className="mt-2 text-[11px] text-muted">{w}</p>)}
    </section>
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
