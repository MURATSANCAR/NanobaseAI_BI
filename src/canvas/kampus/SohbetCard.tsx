import { useQuery } from '@tanstack/react-query';
import { ArrowRight, MessagesSquare } from 'lucide-react';
import { ENGINE_BASE, ENGINE_ENABLED } from '../engine';
import PersonAvatar from './PersonAvatar';

/**
 * Ekip sohbeti (ZEKI AI CHAT, apps/zeki-chat): kaç kişinin şu an çevrimiçi olduğu ve kimler olduğu. Sohbet portalla
 * aynı adreste `/timas/sohbet/` altında çalışır; portal (AD) oturumu olan kişi orada kendiliğinden girer (giriş
 * servisi `/chat-sso`). Sayı giriş servisinin `/chat-presence` ucundan gelir; sohbet bu kurulumda yoksa (404)
 * kart hiç çizilmez. Kişiye basınca onunla doğrudan mesaj açılır. Sohbet hep aynı sekmede açılır (`zeki-sohbet`).
 */
type Status = 'online' | 'busy' | 'away';
type Presence = { online: number; people: { username: string; name: string; status: Status }[] };

class NoChat extends Error {}

const CHAT_BASE = `${ENGINE_BASE}/sohbet`;
const CHAT_TAB = 'zeki-sohbet';

const STATUS: Record<Status, { label: string; dot: string }> = {
  online: { label: 'Çevrimiçi', dot: 'bg-emerald-500' },
  busy: { label: 'Meşgul', dot: 'bg-rose-500' },
  away: { label: 'Uzakta', dot: 'bg-amber-400' },
};

async function fetchPresence(): Promise<Presence> {
  const res = await fetch(`${ENGINE_BASE}/auth/chat-presence`, { credentials: 'include' });
  if (res.status === 404) throw new NoChat();
  if (!res.ok) throw new Error('Sohbet şu an cevap vermiyor.');
  return res.json();
}

export default function SohbetCard({
  me,
  photoOf,
}: {
  /** Ekrandaki kişinin hesap adı: listede «siz» yazılır, kendine mesaj bağlantısı verilmez. */
  me: string;
  /** Rehberdeki fotoğraf sürümü (aynı AD hesap adı); yoksa baş harfler. */
  photoOf: (username: string) => number | null;
}) {
  const presence = useQuery({
    queryKey: ['chat-presence'],
    queryFn: fetchPresence,
    enabled: ENGINE_ENABLED,
    retry: false,
    refetchInterval: (q) => (q.state.error instanceof NoChat ? false : 30_000),
  });
  if (!ENGINE_ENABLED || presence.error instanceof NoChat) return null;

  const people = presence.data?.people ?? [];
  const online = presence.data?.online ?? 0;
  const self = me.toLocaleLowerCase('tr');

  return (
    <section id="ekip-sohbeti" className="kp-card rounded-3xl border border-white/80 bg-white/90 p-4">
      <div className="mb-3 flex items-center justify-between gap-2">
        <div className="flex min-w-0 items-center gap-2">
          <MessagesSquare aria-hidden className="h-4 w-4 shrink-0 text-violet" />
          <h3 className="kp-display truncate text-xs font-bold uppercase tracking-wider text-ink">Ekip Sohbeti</h3>
        </div>
        <span
          className="kp-mono flex shrink-0 items-center gap-1.5 whitespace-nowrap rounded-full border border-emerald-200 bg-emerald-50 px-2 py-0.5 text-[11px] font-bold text-emerald-700"
          aria-live="polite"
        >
          <span className={`h-1.5 w-1.5 rounded-full ${online ? 'animate-pulse bg-emerald-500' : 'bg-slate-300'}`} />
          {presence.isLoading ? '…' : presence.error ? '—' : `${online} kişi çevrimiçi`}
        </span>
      </div>

      {presence.error ? (
        <p className="text-xs text-muted">Sohbet şu an cevap vermiyor; kimin çevrimiçi olduğu okunamadı. Sohbeti yine de açabilirsiniz.</p>
      ) : presence.data && people.length === 0 ? (
        <p className="text-xs text-muted">Şu an sohbette çevrimiçi kimse yok. Mesajınız, kişi bağlandığında karşısına çıkar.</p>
      ) : (
        <ul className="kp-scroll -mx-1 max-h-60 space-y-0.5 overflow-y-auto">
          {people.map((p) => {
            const mine = p.username.toLocaleLowerCase('tr') === self;
            const row = (
              <>
                <span className="relative shrink-0">
                  <PersonAvatar username={p.username} name={p.name} photoVersion={photoOf(p.username)} className="h-8 w-8 rounded-full text-[11px]" />
                  <span aria-hidden className={`absolute -bottom-0.5 -right-0.5 h-2.5 w-2.5 rounded-full ring-2 ring-white ${STATUS[p.status].dot}`} />
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-xs font-bold text-ink">
                    {p.name}
                    {mine && <span className="font-medium text-muted"> (siz)</span>}
                  </span>
                  <span className="block text-[11px] text-muted">{STATUS[p.status].label}</span>
                </span>
              </>
            );
            return (
              <li key={p.username}>
                {mine ? (
                  <div className="flex items-center gap-2.5 rounded-xl px-1 py-1.5">{row}</div>
                ) : (
                  <a
                    href={`${CHAT_BASE}/direct/${encodeURIComponent(p.username)}`}
                    target={CHAT_TAB}
                    title={`${p.name} ile mesajlaş`}
                    aria-label={`${p.name} ile mesajlaş (${STATUS[p.status].label})`}
                    className="kp-press group flex items-center gap-2.5 rounded-xl px-1 py-1.5 hover:bg-violet/5"
                  >
                    {row}
                    <MessagesSquare aria-hidden className="h-3.5 w-3.5 shrink-0 text-muted/50 group-hover:text-violet" />
                  </a>
                )}
              </li>
            );
          })}
        </ul>
      )}

      <a
        href={`${CHAT_BASE}/`}
        target={CHAT_TAB}
        className="kp-press mt-3 flex min-h-11 w-full items-center justify-center gap-1.5 rounded-xl bg-violet px-3 text-xs font-semibold text-white hover:bg-violet/90 sm:min-h-0 sm:py-2"
      >
        Sohbeti aç <ArrowRight aria-hidden className="h-3.5 w-3.5" />
      </a>
    </section>
  );
}
