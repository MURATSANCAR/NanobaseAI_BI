import { useState, type ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Cake, Megaphone, PartyPopper, Sparkles, TreePalm } from 'lucide-react';
import { ENGINE_ENABLED, greetingsApi } from '../engine';
import { canSeePage, usePageAccess } from '../useAdmin';
import { hrSend } from '../hr/hrApi';
import { Avatar } from '../hr/portal/parts';
import { dayMonth, longDay, portalSrc } from '../hr/portal/portalApi';

/** Kampüs'ün İK kartları (kullanıcı kararı 2026-09-29): herkese aynı insan tarafı — şirket içi duyurular, kutlamalar
 *  (doğum günü, iş yıldönümü, aramıza katılanlar) ve bugün izinde. Kaynak `/api/v1/hr/portal/kampus` (hr_brief.kampus):
 *  yalnız aktif kişiler; yaş, doğum yılı, izin türü ve özlük alanı gönderilmez. Gösterecek bir şey yoksa kart çizilmez.
 *  «Kutla» alkış duvarına yazar (aynı kişiye günde bir). */

type Person = { id: string; adSoyad: string; departman: string | null; unvan: string | null; hasPhoto: boolean };
type KampusHr = {
  today: string;
  posts: { id: string; category: string; title: string; body: string; publishDate: string; hasImage: boolean }[];
  newcomers: (Person & { day: number; month: number })[];
  birthdays: (Person & { day: number; month: number; inDays: number })[];
  anniversaries: (Person & { years: number; day: number; month: number; inDays: number })[];
  onLeave: { id: string; adSoyad: string; departman: string | null; back: string }[];
};

function useKampusHr() {
  const pages = usePageAccess();
  const allowed = canSeePage(pages, 'ik-anasayfa');
  const q = useQuery({
    queryKey: ['hr', 'portal', 'kampus'],
    queryFn: () => hrSend<KampusHr>('GET', '/portal/kampus'),
    enabled: ENGINE_ENABLED && allowed,
    retry: false,
    staleTime: 5 * 60_000,
  });
  return allowed ? q.data : undefined;
}

const cardCls = 'kp-card rounded-3xl border border-white/80 bg-white/90 p-4';

function Head({ icon, title, to, tone }: { icon: ReactNode; title: string; to: string; tone: string }) {
  return (
    <div className="mb-3 flex items-center justify-between gap-2">
      <div className="flex items-center gap-2">
        <span className={tone} aria-hidden>{icon}</span>
        <h3 className="kp-display text-xs font-bold uppercase tracking-wider text-ink">{title}</h3>
      </div>
      <Link to={to} className="shrink-0 text-[11px] font-medium text-violet hover:underline">Hepsi</Link>
    </div>
  );
}

/** Şirket içi duyurular: son üç duyuru; ilk duyurunun görseli varsa üstte. */
export function HrPostsCard({ className = '' }: { className?: string }) {
  const d = useKampusHr();
  if (!d?.posts.length) return null;
  const [first, ...rest] = d.posts;
  return (
    <section id="duyurular" className={`${cardCls} ${className}`}>
      <Head icon={<Megaphone className="h-4 w-4" />} title="Şirket içi duyurular" to="/ik/duyurular" tone="text-rose-600" />
      <Link to={`/ik/duyurular#${first.id}`} className="kp-press block overflow-hidden rounded-2xl border border-slate-200/70 bg-white">
        {first.hasImage && <img src={portalSrc(`/portal/posts/${first.id}/image`)} alt="" loading="lazy" className="aspect-[16/7] w-full bg-slate-100 object-cover" />}
        <div className="p-3">
          <div className="text-[10.5px] font-bold uppercase tracking-wide text-violet">{first.category} · {longDay(first.publishDate)}</div>
          <div className="text-[13px] font-bold leading-snug text-ink">{first.title}</div>
          <p className="mt-0.5 line-clamp-2 text-xs leading-snug text-muted">{first.body}</p>
        </div>
      </Link>
      {rest.length > 0 && (
        <ul className="mt-2 divide-y divide-slate-100">
          {rest.map((p) => (
            <li key={p.id}>
              <Link to={`/ik/duyurular#${p.id}`} className="flex min-h-11 items-center justify-between gap-2 py-1.5 text-xs">
                <span className="min-w-0 truncate font-semibold text-ink">{p.title}</span>
                <span className="shrink-0 text-[11px] text-muted">{longDay(p.publishDate)}</span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

/** Kutlamalar: bugün/bu hafta doğum günleri, bu hafta iş yıldönümleri, bu ay aramıza katılanlar. */
export function HrCelebrationsCard({ className = '' }: { className?: string }) {
  const d = useKampusHr();
  const qc = useQueryClient();
  const [sent, setSent] = useState<Set<string>>(new Set());
  if (!d || (!d.birthdays.length && !d.anniversaries.length && !d.newcomers.length)) return null;
  const cheer = async (id: string, name: string, occasion: string) => {
    try {
      const r = await greetingsApi.send(name, occasion);
      setSent((s) => new Set(s).add(id));
      toast.success(r.created ? `${name} kutlandı` : `${name} bugün zaten kutlanmış`, { description: r.created ? 'Alkış duvarında görünüyor.' : 'Aynı kişiye günde bir alkış gider.' });
      void qc.invalidateQueries({ queryKey: ['greetings'] });
    } catch (e) {
      toast.error('Kutlama gönderilemedi', { description: e instanceof Error ? e.message : undefined });
    }
  };
  const row = (p: Person, when: string, occasion: string, tag?: string) => (
    <li key={`${p.id}-${occasion}`} className="flex items-center gap-2.5">
      <Avatar name={p.adSoyad} src={p.hasPhoto ? `/portal/photo/${p.id}` : null} size={34} />
      <div className="min-w-0 flex-1">
        <div className="truncate text-xs font-bold text-ink">{p.adSoyad}{tag && <span className="ml-1 font-semibold text-violet">{tag}</span>}</div>
        <div className="truncate text-[11px] text-muted">{[p.departman, p.unvan].filter(Boolean).join(' · ') || '—'} · {when}</div>
      </div>
      <button type="button" disabled={sent.has(p.id)} onClick={() => void cheer(p.id, p.adSoyad, occasion)}
        className="kp-press min-h-11 shrink-0 rounded-lg border border-rose-200 bg-rose-50 px-2.5 text-[11px] font-semibold text-rose-700 hover:bg-rose-100 disabled:opacity-50 sm:min-h-8">
        {sent.has(p.id) ? 'Kutlandı' : 'Kutla'}
      </button>
    </li>
  );
  const when = (inDays: number, day: number, month: number) => (inDays === 0 ? 'bugün' : inDays === 1 ? 'yarın' : dayMonth(day, month));
  return (
    <section id="kutlamalar" className={`${cardCls} ${className}`}>
      <Head icon={<PartyPopper className="h-4 w-4" />} title="Kutlamalar" to="/ik/dogum-gunleri" tone="text-amber-600" />
      <div className="flex flex-col gap-3">
        {d.birthdays.length > 0 && (
          <div>
            <div className="mb-1.5 flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-wide text-pink-700"><Cake className="h-3.5 w-3.5" aria-hidden />Doğum günleri</div>
            <ul className="space-y-2">{d.birthdays.slice(0, 5).map((p) => row(p, when(p.inDays, p.day, p.month), 'Doğum günün kutlu olsun! 🎂'))}</ul>
          </div>
        )}
        {d.anniversaries.length > 0 && (
          <div>
            <div className="mb-1.5 flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-wide text-violet"><Sparkles className="h-3.5 w-3.5" aria-hidden />İş yıldönümleri</div>
            <ul className="space-y-2">{d.anniversaries.slice(0, 5).map((p) => row(p, when(p.inDays, p.day, p.month), `${p.years}. yılın kutlu olsun!`, `${p.years}. yıl`))}</ul>
          </div>
        )}
        {d.newcomers.length > 0 && (
          <div>
            <div className="mb-1.5 flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-wide text-emerald-700"><PartyPopper className="h-3.5 w-3.5" aria-hidden />Aramıza katılanlar</div>
            <ul className="space-y-2">{d.newcomers.slice(0, 5).map((p) => row(p, `${dayMonth(p.day, p.month)} itibarıyla`, 'Aramıza hoş geldin!'))}</ul>
          </div>
        )}
      </div>
    </section>
  );
}

/** Bugün izinde: ad, departman, dönüş günü (izin türü yok). */
export function HrOnLeaveCard({ className = '' }: { className?: string }) {
  const d = useKampusHr();
  if (!d?.onLeave.length) return null;
  return (
    <section id="bugun-izinde" className={`${cardCls} ${className}`}>
      <Head icon={<TreePalm className="h-4 w-4" />} title={`Bugün izinde · ${d.onLeave.length}`} to="/ik/rehber" tone="text-lime-700" />
      <ul className="space-y-1.5 text-xs">
        {d.onLeave.slice(0, 8).map((p) => (
          <li key={p.id} className="flex items-center justify-between gap-2">
            <span className="min-w-0"><span className="block truncate font-semibold text-ink">{p.adSoyad}</span><span className="block truncate text-[11px] text-muted">{p.departman || '—'}</span></span>
            <span className="shrink-0 text-[11px] text-muted">{dayMonth(Number(p.back.slice(8, 10)), Number(p.back.slice(5, 7)))} dönüyor</span>
          </li>
        ))}
        {d.onLeave.length > 8 && <li className="text-[11px] text-muted">ve {d.onLeave.length - 8} kişi daha</li>}
      </ul>
    </section>
  );
}
