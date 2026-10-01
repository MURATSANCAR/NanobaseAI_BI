import { useQuery } from '@tanstack/react-query';
import { ArrowRight, MessagesSquare } from 'lucide-react';
import { ENGINE_BASE, ENGINE_ENABLED } from '../engine';
import PersonAvatar from './PersonAvatar';

/**
 * Ekip sohbeti (ZEKI AI CHAT, apps/zeki-chat): kaç kişinin şu an çevrimiçi olduğu ve kimler olduğu. Sohbet portalla
 * aynı adreste `/timas/sohbet/` altında çalışır; portal (AD) oturumu olan kişi orada kendiliğinden girer (giriş
 * servisi `/chat-sso`). Sayı giriş servisinin `/chat-presence` ucundan gelir; sohbet bu kurulumda yoksa (404)
 * kart hiç çizilmez. Kişiye basınca onunla doğrudan mesaj açılır. Sohbet hep aynı sekmede açılır (`zeki-sohbet`).
 * Görünüm (2026-09-30, kullanıcı isteği «wow olsun»): renkli başlık bandında canlı sayı, üst üste yüzler ve durum
 * dağılımı; liste kendisi → çevrimiçi → meşgul → uzakta sırasıyla, satırda «Mesaj» düğmesi.
 */
type Status = 'online' | 'busy' | 'away';
type Presence = { online: number; people: { username: string; name: string; status: Status }[] };

class NoChat extends Error {}

const CHAT_BASE = `${ENGINE_BASE}/sohbet`;
const CHAT_TAB = 'zeki-sohbet';

const STATUS: Record<Status, { label: string; dot: string; text: string }> = {
  online: { label: 'Çevrimiçi', dot: 'bg-emerald-500', text: 'text-emerald-700' },
  busy: { label: 'Meşgul', dot: 'bg-rose-500', text: 'text-rose-700' },
  away: { label: 'Uzakta', dot: 'bg-amber-400', text: 'text-amber-700' },
};
const RANK: Record<Status, number> = { online: 0, busy: 1, away: 2 };
/** Başlık bandında üst üste gösterilen yüz sayısı; kalanı «+N». */
const FACES = 5;

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

  const self = me.toLocaleLowerCase('tr');
  // Sıra: kişinin kendisi en üstte, sonra çevrimiçi → meşgul → uzakta (aynı durumda sunucunun sırası korunur).
  const people = [...(presence.data?.people ?? [])].sort(
    (a, b) => Number(b.username.toLocaleLowerCase('tr') === self) - Number(a.username.toLocaleLowerCase('tr') === self) || RANK[a.status] - RANK[b.status],
  );
  const online = presence.data?.online ?? 0;
  const counts = (['online', 'busy', 'away'] as const).map((k) => [k, people.filter((p) => p.status === k).length] as const).filter(([, n]) => n > 0);
  const faces = people.slice(0, FACES);

  return (
    <section id="ekip-sohbeti" className="kp-card overflow-hidden rounded-3xl border border-white/80 bg-white/90">
      {/* Başlık bandı: canlı sayı, yüzler, durum dağılımı (süs daireleri sabit, hareket yok). */}
      <div className="relative overflow-hidden bg-gradient-to-br from-violet via-violet to-coral p-4 text-white">
        <div aria-hidden className="pointer-events-none absolute -right-10 -top-12 h-36 w-36 rounded-full bg-white/15 blur-2xl" />
        <div aria-hidden className="pointer-events-none absolute -bottom-14 -left-8 h-32 w-32 rounded-full bg-coral/40 blur-2xl" />
        <div className="relative flex items-center justify-between gap-2">
          <div className="flex min-w-0 items-center gap-2">
            <span className="grid h-7 w-7 shrink-0 place-items-center rounded-lg bg-white/20 ring-1 ring-white/30">
              <MessagesSquare aria-hidden className="h-4 w-4" />
            </span>
            <h3 className="kp-display truncate text-xs font-bold uppercase tracking-wider">Ekip Sohbeti</h3>
          </div>
          <span
            className="kp-mono flex shrink-0 items-center gap-1.5 whitespace-nowrap rounded-full bg-white/20 px-2 py-0.5 text-[11px] font-bold ring-1 ring-white/30"
            aria-live="polite"
          >
            <span className={`h-1.5 w-1.5 rounded-full ${online ? 'animate-pulse bg-emerald-300' : 'bg-white/50'}`} />
            {presence.isLoading ? '…' : presence.error ? '—' : `${online} kişi çevrimiçi`}
          </span>
        </div>

        <div className="relative mt-4 flex items-end justify-between gap-3">
          {faces.length > 0 ? (
            <div className="flex items-center">
              <div className="flex -space-x-2.5">
                {faces.map((p) => (
                  <span key={p.username} className="relative rounded-full ring-2 ring-white/90" title={p.name}>
                    <PersonAvatar username={p.username} name={p.name} photoVersion={photoOf(p.username)} className="h-9 w-9 rounded-full text-[11px]" />
                  </span>
                ))}
              </div>
              {people.length > FACES && (
                <span className="kp-mono -ml-2.5 grid h-9 w-9 place-items-center rounded-full bg-white/25 text-[11px] font-bold ring-2 ring-white/90 backdrop-blur-sm">
                  {`+${people.length - FACES}`}
                </span>
              )}
            </div>
          ) : (
            <p className="text-xs text-white/85">{presence.isLoading ? 'Bakılıyor…' : 'Şimdilik sessiz.'}</p>
          )}
          {counts.length > 0 && (
            <ul className="flex flex-col items-end gap-0.5 text-[11px] font-semibold text-white/90">
              {counts.map(([k, n]) => (
                <li key={k} className="flex items-center gap-1.5">
                  <span aria-hidden className={`h-1.5 w-1.5 rounded-full ${STATUS[k].dot} ring-1 ring-white/70`} />
                  {`${n} ${STATUS[k].label.toLocaleLowerCase('tr')}`}
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>

      <div className="p-4 pt-3">
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
                    <span className={`block text-[11px] ${STATUS[p.status].text}`}>{STATUS[p.status].label}</span>
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
                      <span className="flex shrink-0 items-center gap-1 rounded-full border border-slate-200 px-2 py-0.5 text-[11px] font-semibold text-muted group-hover:border-violet/30 group-hover:bg-violet group-hover:text-white">
                        <MessagesSquare aria-hidden className="h-3 w-3" /> Mesaj
                      </span>
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
          className="kp-press mt-3 flex min-h-11 w-full items-center justify-center gap-1.5 rounded-xl bg-gradient-to-r from-violet to-coral px-3 text-xs font-semibold text-white shadow-md shadow-violet/25 hover:brightness-105 sm:min-h-0 sm:py-2"
        >
          Sohbeti aç <ArrowRight aria-hidden className="h-3.5 w-3.5" />
        </a>
      </div>
    </section>
  );
}
