import { lazy, Suspense, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { CalendarDays, DoorClosed } from 'lucide-react';
import { EngineAuthError, ENGINE_ENABLED, roomsApi, type RoomBooking, type RoomNow } from '../engine';
import { dayLabel } from './time';

const RoomBookingDialog = lazy(() => import('./RoomBookingDialog'));

/**
 * Kampüs kartı: her odanın şu anki durumu ve sıradaki rezervasyonu. Kimin aldığı herkese görünür.
 * "Rezerve et" takvimi o oda seçili açar. 30 sn'de bir ve sekmeye dönüldüğünde yenilenir.
 */
export default function RoomsCard({ className = '' }: { className?: string }) {
  const [open, setOpen] = useState(false);
  const [roomId, setRoomId] = useState<string | undefined>();
  const q = useQuery({
    queryKey: ['rooms', 'now'],
    queryFn: roomsApi.now,
    enabled: ENGINE_ENABLED,
    refetchInterval: 30_000,
    refetchOnWindowFocus: true,
    retry: false,
  });

  const openFor = (id?: string) => {
    setRoomId(id);
    setOpen(true);
  };

  const rooms = q.data?.rooms ?? [];
  const today = q.data?.today ?? '';
  const busyCount = rooms.filter((r) => r.current).length;

  return (
    <section id="studios-hub" className={`kp-card rounded-3xl border border-white/80 bg-white/90 p-4 ${className}`}>
      <div className="mb-3 flex items-center justify-between gap-2">
        <div className="flex min-w-0 items-center gap-2">
          <DoorClosed className="h-4 w-4 shrink-0 text-emerald-600" aria-hidden />
          <h3 className="kp-display truncate text-xs font-bold uppercase tracking-wider text-ink">Toplantı odaları</h3>
        </div>
        <button
          type="button"
          onClick={() => openFor()}
          className="kp-press flex min-h-11 shrink-0 items-center gap-1 rounded-full border border-violet/30 bg-violet/5 px-3 text-[11px] font-bold text-violet hover:bg-violet/10 sm:min-h-0 sm:py-1"
        >
          <CalendarDays className="h-3.5 w-3.5" aria-hidden /> Takvim
        </button>
      </div>

      {q.isLoading && (
        <div className="space-y-2.5" aria-hidden>
          {[0, 1, 2].map((i) => (
            <div key={i} className="h-[54px] animate-pulse rounded-xl bg-slate-100" />
          ))}
        </div>
      )}

      {q.error && (
        <p className="rounded-xl bg-rose-50 p-2.5 text-[11px] text-rose-800">
          {q.error instanceof EngineAuthError ? 'Oda durumunu görmek için oturum gerekli.' : 'Oda durumu okunamadı. Birazdan yeniden denenecek.'}
        </p>
      )}

      {q.data && rooms.length === 0 && (
        <div className="rounded-xl border border-dashed border-slate-300 p-3 text-center text-[11px] text-muted">
          <p className="font-bold text-ink">Henüz oda tanımlı değil.</p>
          {q.data.me.admin ? (
            <button type="button" onClick={() => openFor()} className="kp-press mt-1 min-h-11 font-bold text-violet sm:min-h-0">
              İlk odayı ekle
            </button>
          ) : (
            <p className="mt-0.5">Yönetici oda ekleyince burada görünür.</p>
          )}
        </div>
      )}

      {rooms.length > 0 && (
        <>
          <p className="kp-mono mb-2 text-[11px] font-semibold text-muted">
            {rooms.length - busyCount} boş · {busyCount} dolu
          </p>
          <ul className="space-y-2.5 text-xs">
            {rooms.map((r) => (
              <li key={r.id} className="flex items-center justify-between gap-2 rounded-xl border border-slate-200/70 bg-slate-50/80 p-2.5">
                <div className="min-w-0">
                  <div className="flex items-center gap-1.5">
                    <span className={`h-2 w-2 shrink-0 rounded-full ${r.current ? 'bg-rose-500' : 'bg-emerald-500'}`} aria-hidden />
                    <span className="truncate font-semibold text-ink">{r.name}</span>
                    {r.location && <span className="hidden truncate text-[11px] text-muted xl:inline">· {r.location}</span>}
                  </div>
                  <p className="mt-0.5 line-clamp-2 text-[11px] leading-snug text-muted" title={status(r, today)}>
                    {status(r, today)}
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => openFor(r.id)}
                  aria-label={`${r.name} için rezervasyon yap`}
                  className="kp-press min-h-11 shrink-0 whitespace-nowrap rounded-lg border border-slate-200 bg-white px-3 py-1 text-xs font-medium hover:border-violet hover:text-violet sm:min-h-0 sm:px-2 sm:text-[11px]"
                >
                  Rezerve et
                </button>
              </li>
            ))}
          </ul>
        </>
      )}

      {open && (
        <Suspense fallback={null}>
          <RoomBookingDialog open={open} initialRoomId={roomId} onClose={() => setOpen(false)} />
        </Suspense>
      )}
    </section>
  );
}

function who(b: RoomBooking): string {
  return b.mine ? 'sen' : b.displayName;
}

function status(r: RoomNow, today: string): string {
  if (r.current) {
    const tail = r.current.title ? ` · ${r.current.title}` : '';
    return `Dolu · ${who(r.current)} · bitiş ${r.current.endLocal}${tail}`;
  }
  if (!r.next) return 'Şu an boş · ileri tarihli rezervasyon yok';
  const when = r.next.date === today ? r.next.startLocal : `${dayLabel(r.next.date, today)} ${r.next.startLocal}`;
  return `Şu an boş · sıradaki ${when}, ${who(r.next)}`;
}
