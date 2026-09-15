import { useCallback, useEffect, useMemo, useRef, useState, type PointerEvent as ReactPointerEvent, type ReactNode } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { CalendarDays, ChevronLeft, ChevronRight, Loader2, MapPin, Plus, Trash2, Users, X } from 'lucide-react';
import { EngineAuthError, RoomsError, roomsApi, type Room, type RoomBooking, type RoomsDay } from '../engine';
import { addDays, dayLabel, dayLong, duration, istanbulMinutes, istanbulToday, toHHMM, toMin } from './time';
import './rooms.css';

/**
 * Toplantı odası takvimi. Satırlar saat aralıkları, sütunlar odalar. Boş hücreye tıklamak bir aralık seçer,
 * fareyle sürüklemek ya da Shift+tıklamak aralığı uzatır; dokunmatikte başlangıç/bitiş kutuları kullanılır.
 * Rezervasyonlar herkese açıktır: dolu blokta kimin aldığı yazar. Ekran açıkken 30 sn'de bir yenilenir.
 *
 * Yerel <dialog>: odak tuzağı, Esc ve arka planın erişilemez olması tarayıcıdan gelir.
 */

/** Bir saat aralığının yüksekliği: farede 30 px, dokunmatikte parmak için 44 px. */
const rowHeight = (): number => (typeof window !== 'undefined' && window.matchMedia?.('(pointer: coarse)').matches ? 44 : 30);
const STRIP_DAYS = 14;
const CLOSE_MS = 150;

type Selection = { roomId: string; s: number; e: number };

export default function RoomBookingDialog({
  open,
  onClose,
  initialRoomId,
}: {
  open: boolean;
  onClose: () => void;
  initialRoomId?: string;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const [closing, setClosing] = useState(false);
  // Esc hem keydown hem yerel cancel olarak aynı anda gelebilir; ikinci çağrı durumu beklemeden durmalı.
  const closingRef = useRef(false);

  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    if (open && !d.open) {
      closingRef.current = false;
      setClosing(false);
      d.showModal();
    }
  }, [open]);

  const close = useCallback(() => {
    const d = ref.current;
    if (!d?.open || closingRef.current) return;
    closingRef.current = true;
    setClosing(true);
    window.setTimeout(() => {
      d.close();
      closingRef.current = false;
      setClosing(false);
      onClose();
    }, CLOSE_MS);
  }, [onClose]);

  // Bazı tarayıcı ve gömülü görünümler Esc'te cancel olayı üretmez. Rezerve et düğmesi kaybolunca odak
  // pencereden çıkabildiği için dinleyici pencerede değil belgede durur.
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && ref.current?.open) {
        e.preventDefault();
        close();
      }
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [open, close]);

  return (
    <dialog
      ref={ref}
      className="rb-dialog w-[min(1180px,calc(100vw-24px))] max-w-none rounded-3xl border border-slate-200/80 bg-white p-0 text-ink shadow-canvas-card"
      data-closing={closing || undefined}
      aria-labelledby="rb-title"
      onCancel={(e) => {
        e.preventDefault();
        close();
      }}

      onClick={(e) => {
        if (e.target === e.currentTarget) close();
      }}
    >
      {open && <Body initialRoomId={initialRoomId} onClose={close} />}
    </dialog>
  );
}

function Body({ initialRoomId, onClose }: { initialRoomId?: string; onClose: () => void }) {
  const qc = useQueryClient();
  const [today, setToday] = useState(istanbulToday);
  const [date, setDate] = useState(today);
  const [nowMin, setNowMin] = useState(istanbulMinutes);
  const [sel, setSel] = useState<Selection | null>(null);
  const [title, setTitle] = useState('');
  const [msg, setMsg] = useState<{ kind: 'ok' | 'err'; text: string } | null>(null);
  const [confirmCancel, setConfirmCancel] = useState<string | null>(null);
  const [ROW] = useState(rowHeight);

  useEffect(() => {
    const t = window.setInterval(() => {
      setNowMin(istanbulMinutes());
      setToday(istanbulToday());
    }, 60_000);
    return () => window.clearInterval(t);
  }, []);

  const q = useQuery({
    queryKey: ['rooms', 'day', date],
    queryFn: () => roomsApi.day(date),
    refetchInterval: 30_000,
    refetchOnWindowFocus: true,
    retry: false,
  });
  const data = q.data;
  const serverToday = data?.today ?? today;

  const grid = data?.grid;
  const step = grid?.slotMinutes ?? 30;
  const slots = useMemo(() => {
    if (!grid) return [] as number[];
    const out: number[] = [];
    for (let m = grid.startMin; m < grid.endMin; m += step) out.push(m);
    return out;
  }, [grid, step]);

  /** Odanın o gündeki dolu aralıkları, dakika cinsinden. */
  const busy = useMemo(() => {
    const map = new Map<string, Array<{ s: number; e: number; b: RoomBooking }>>();
    for (const b of data?.bookings ?? []) {
      const s = b.date < date ? 0 : toMin(b.startLocal);
      const e = toMin(b.endLocal);
      const list = map.get(b.roomId) ?? [];
      list.push({ s, e, b });
      map.set(b.roomId, list);
    }
    return map;
  }, [data?.bookings, date]);

  const isPast = useCallback(
    (m: number) => date < serverToday || (date === serverToday && m + step <= nowMin),
    [date, serverToday, nowMin, step],
  );
  const holder = useCallback(
    (roomId: string, m: number) => busy.get(roomId)?.find((x) => x.s < m + step && x.e > m) ?? null,
    [busy, step],
  );
  const free = useCallback((roomId: string, m: number) => !isPast(m) && !holder(roomId, m), [isPast, holder]);

  // Gün ya da veri değişince, artık boş olmayan seçim sessizce yanlış kalmasın.
  useEffect(() => {
    if (!sel) return;
    for (let m = sel.s; m < sel.e; m += step) {
      if (!free(sel.roomId, m)) {
        const h = holder(sel.roomId, m);
        setSel(null);
        // 409 mesajı saati de söyler; yenileme onu daha kısa bir cümleyle ezmesin.
        setMsg((prev) => (prev?.kind === 'err' ? prev : h ? { kind: 'err', text: `Seçtiğin saat artık dolu: ${h.b.displayName} aldı.` } : null));
        return;
      }
    }
  }, [sel, free, holder, step]);

  /** Tutamaktan hedefe doğru, ilk dolu hücrede duran aralık. */
  const span = useCallback(
    (roomId: string, anchor: number, target: number): Selection => {
      let s = anchor;
      let e = anchor + step;
      if (target >= anchor) {
        for (let m = anchor + step; m <= target && free(roomId, m); m += step) e = m + step;
      } else {
        for (let m = anchor - step; m >= target && free(roomId, m); m -= step) s = m;
      }
      return { roomId, s, e };
    },
    [free, step],
  );

  const anchor = useRef<{ roomId: string; m: number } | null>(null);
  const dragging = useRef(false);

  const slotAt = (e: ReactPointerEvent<HTMLDivElement>): number | null => {
    if (!grid) return null;
    const rect = e.currentTarget.getBoundingClientRect();
    const i = Math.floor((e.clientY - rect.top) / ROW);
    if (i < 0 || i >= slots.length) return null;
    return slots[i];
  };

  const onDown = (roomId: string) => (e: ReactPointerEvent<HTMLDivElement>) => {
    // Dokunmatikte seçim parmak kalkınca (tıklamada) yapılır; yoksa kaydırmaya başlamak saat seçer.
    if (e.pointerType !== 'mouse') return;
    if (e.button !== 0 || (e.target as HTMLElement).closest('[data-booking]')) return;
    const m = slotAt(e);
    if (m == null || !free(roomId, m)) return;
    setMsg(null);
    if (e.shiftKey && anchor.current?.roomId === roomId) {
      setSel(span(roomId, anchor.current.m, m));
      return;
    }
    anchor.current = { roomId, m };
    setSel({ roomId, s: m, e: m + step });
    dragging.current = true;
    e.currentTarget.setPointerCapture(e.pointerId);
  };
  const onMove = (roomId: string) => (e: ReactPointerEvent<HTMLDivElement>) => {
    if (!dragging.current || anchor.current?.roomId !== roomId) return;
    const m = slotAt(e);
    if (m != null) setSel(span(roomId, anchor.current.m, m));
  };
  const onUp = () => {
    dragging.current = false;
  };

  const rooms = data?.rooms ?? [];
  const selRoom = rooms.find((r) => r.id === sel?.roomId) ?? null;

  // İlk açılışta karttan gelen oda için ilk boş aralığı önceden seç.
  const primed = useRef(false);
  useEffect(() => {
    if (primed.current || !data || !initialRoomId) return;
    primed.current = true;
    const m = slots.find((x) => free(initialRoomId, x));
    if (m != null) {
      anchor.current = { roomId: initialRoomId, m };
      setSel({ roomId: initialRoomId, s: m, e: m + step });
    }
  }, [data, initialRoomId, slots, free, step]);

  const book = useMutation({
    mutationFn: (s: Selection) => roomsApi.book(s.roomId, { date, start: toHHMM(s.s), end: toHHMM(s.e), title }),
    onSuccess: (b) => {
      setMsg({ kind: 'ok', text: `${b.roomName ?? 'Oda'} ${dayLabel(b.date, serverToday).toLocaleLowerCase('tr')} ${b.startLocal}–${b.endLocal} senin adına ayrıldı.` });
      setSel(null);
      setTitle('');
      qc.setQueryData<RoomsDay>(['rooms', 'day', date], (old) => (old ? { ...old, bookings: [...old.bookings, b] } : old));
      void qc.invalidateQueries({ queryKey: ['rooms'] });
    },
    onError: (err) => {
      setMsg({ kind: 'err', text: errorText(err) });
      void qc.invalidateQueries({ queryKey: ['rooms'] });
    },
  });

  const cancel = useMutation({
    mutationFn: (id: string) => roomsApi.cancel(id),
    onSuccess: () => {
      setMsg({ kind: 'ok', text: 'Rezervasyon iptal edildi.' });
      setConfirmCancel(null);
      void qc.invalidateQueries({ queryKey: ['rooms'] });
    },
    onError: (err) => setMsg({ kind: 'err', text: errorText(err) }),
  });

  const strip = useMemo(() => Array.from({ length: STRIP_DAYS }, (_, i) => addDays(serverToday, i)), [serverToday]);
  const pickDay = (d: string) => {
    if (!d) return;
    setDate(d < serverToday ? serverToday : d);
    setSel(null);
    setMsg(null);
    setConfirmCancel(null);
  };

  // Başlangıç/bitiş kutuları: ızgarayla aynı seçimi yazar.
  const startOptions = sel ? slots.filter((m) => free(sel.roomId, m)) : [];
  const endOptions = sel ? span(sel.roomId, sel.s, grid ? grid.endMin - step : sel.s) : null;
  const endChoices: number[] = [];
  if (sel && endOptions) for (let m = sel.s + step; m <= endOptions.e; m += step) endChoices.push(m);

  // Gün açılınca ızgara seçili saate ya da şu ana kayar; 08:00'de kalıp işi ekran dışında bırakmaz.
  const scroller = useRef<HTMLDivElement>(null);
  const scrolledFor = useRef<string | null>(null);
  useEffect(() => {
    const el = scroller.current;
    if (!el || !grid || !data || scrolledFor.current === date) return;
    scrolledFor.current = date;
    const target = sel?.s ?? (date === serverToday ? nowMin : null);
    if (target == null || target <= grid.startMin) return;
    el.scrollTop = Math.max(0, ((target - grid.startMin) / step) * ROW - ROW * 2);
  }, [data, grid, date, sel, serverToday, nowMin, step, ROW]);

  const nowTop = grid && date === serverToday && nowMin >= grid.startMin && nowMin <= grid.endMin ? ((nowMin - grid.startMin) / step) * ROW : null;

  return (
    <div className="flex max-h-[calc(100dvh-24px)] flex-col">
      {/* Başlık ve gün şeridi */}
      <header className="flex flex-col gap-3 border-b border-slate-200/70 px-4 pb-3 pt-4 sm:px-6">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <h2 id="rb-title" className="kp-display flex items-center gap-2 text-lg font-extrabold text-ink">
              <CalendarDays className="h-5 w-5 text-violet" aria-hidden /> <span className="sm:hidden">Oda rezervasyonu</span>
              <span className="hidden sm:inline">Toplantı odası rezervasyonu</span>
            </h2>
            <p className="mt-0.5 text-xs text-muted">
              <span className="hidden sm:inline">Boş saate tıkla, sürükleyerek uzat. Dolu saatlerde kimin aldığı yazar. </span>
              {dayLong(date)}
            </p>
          </div>
          <button type="button" onClick={onClose} aria-label="Kapat" className="kp-press flex h-11 w-11 shrink-0 items-center justify-center rounded-xl text-muted hover:bg-slate-100 hover:text-ink sm:h-9 sm:w-9">
            <X className="h-5 w-5" />
          </button>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            aria-label="Önceki gün"
            disabled={date <= serverToday}
            onClick={() => pickDay(addDays(date, -1))}
            className="kp-press flex h-11 w-11 shrink-0 items-center justify-center rounded-xl border border-slate-200 text-ink hover:bg-slate-50 disabled:opacity-40 sm:h-9 sm:w-9"
          >
            <ChevronLeft className="h-4 w-4" />
          </button>
          <div className="rb-strip flex min-w-0 flex-1 gap-1.5 overflow-x-auto" role="tablist" aria-label="Gün">
            {strip.map((d) => (
              <button
                key={d}
                type="button"
                role="tab"
                aria-selected={d === date}
                onClick={() => pickDay(d)}
                className={`kp-press min-h-11 shrink-0 whitespace-nowrap rounded-xl px-3 text-xs font-bold sm:min-h-9 ${
                  d === date ? 'bg-ink text-white' : 'bg-slate-100 text-ink/80 hover:bg-slate-200'
                }`}
              >
                {dayLabel(d, serverToday)}
              </button>
            ))}
          </div>
          <button
            type="button"
            aria-label="Sonraki gün"
            onClick={() => pickDay(addDays(date, 1))}
            className="kp-press flex h-11 w-11 shrink-0 items-center justify-center rounded-xl border border-slate-200 text-ink hover:bg-slate-50 sm:h-9 sm:w-9"
          >
            <ChevronRight className="h-4 w-4" />
          </button>
          <label className="sr-only" htmlFor="rb-date">
            Başka bir gün
          </label>
          <input
            id="rb-date"
            type="date"
            min={serverToday}
            value={date}
            onChange={(e) => pickDay(e.target.value)}
            className="hidden h-9 shrink-0 rounded-xl border border-slate-200 px-2 text-xs font-semibold text-ink sm:block"
          />
        </div>
      </header>

      {/* Izgara */}
      <div ref={scroller} className="min-h-0 flex-1 overflow-auto sm:px-4">
        {q.isLoading && (
          <div className="flex h-60 items-center justify-center gap-2 text-sm text-muted">
            <Loader2 className="h-4 w-4 animate-spin" /> Takvim okunuyor…
          </div>
        )}
        {q.error && (
          <p className="m-4 rounded-xl bg-rose-50 p-3 text-sm text-rose-800">
            {q.error instanceof EngineAuthError ? 'Oturumun düşmüş. Sayfayı yenileyip yeniden giriş yap.' : errorText(q.error)}
          </p>
        )}
        {data && rooms.length === 0 && (
          <div className="m-4 rounded-2xl border border-dashed border-slate-300 p-6 text-center text-sm text-muted">
            <p className="font-bold text-ink">Henüz oda tanımlı değil.</p>
            <p className="mt-1">{data.me.admin ? 'Aşağıdan ilk odayı ekle.' : 'Yönetici oda ekleyince burada görünür.'}</p>
          </div>
        )}
        {data && grid && rooms.length > 0 && (
          <div
            className="relative my-3 grid"
            style={{ gridTemplateColumns: `52px repeat(${rooms.length}, minmax(148px, 1fr))` }}
          >
            {/* Oda başlıkları */}
            <div className="sticky left-0 top-0 z-30 bg-white" />
            {rooms.map((r) => (
              <div key={r.id} className="sticky top-0 z-20 border-b border-slate-200 bg-white px-2 pb-2">
                <p className="truncate text-xs font-extrabold text-ink" title={r.name}>
                  {r.name}
                </p>
                <p className="flex items-center gap-2 truncate text-[11px] text-muted">
                  {r.location && (
                    <span className="flex items-center gap-0.5 truncate">
                      <MapPin className="h-3 w-3 shrink-0" aria-hidden /> {r.location}
                    </span>
                  )}
                  {r.capacity != null && (
                    <span className="flex shrink-0 items-center gap-0.5">
                      <Users className="h-3 w-3" aria-hidden /> {r.capacity}
                    </span>
                  )}
                </p>
              </div>
            ))}

            {/* Saat etiketleri */}
            <div className="sticky left-0 z-20 bg-white" style={{ height: slots.length * ROW }}>
              {slots.map((m, i) =>
                m % 60 === 0 ? (
                  <span key={m} className={`kp-mono absolute right-2 text-[11px] font-semibold text-muted ${i === 0 ? '' : '-translate-y-1/2'}`} style={{ top: i * ROW }}>
                    {toHHMM(m)}
                  </span>
                ) : null,
              )}
            </div>

            {rooms.map((r) => (
              <RoomColumn
                key={r.id}
                room={r}
                row={ROW}
                slots={slots}
                step={step}
                startMin={grid.startMin}
                busy={busy.get(r.id) ?? []}
                isPast={isPast}
                sel={sel?.roomId === r.id ? sel : null}
                nowTop={nowTop}
                confirmCancel={confirmCancel}
                cancelling={cancel.isPending ? cancel.variables : null}
                onAskCancel={setConfirmCancel}
                onCancel={(id) => cancel.mutate(id)}
                onDown={onDown(r.id)}
                onMove={onMove(r.id)}
                onUp={onUp}
                onKeyPick={(m, shift) => {
                  setMsg(null);
                  if (shift && anchor.current?.roomId === r.id) setSel(span(r.id, anchor.current.m, m));
                  else {
                    anchor.current = { roomId: r.id, m };
                    setSel({ roomId: r.id, s: m, e: m + step });
                  }
                }}
                free={free}
              />
            ))}
          </div>
        )}
      </div>

      {/* Özet ve onay */}
      <footer className="border-t border-slate-200/70 bg-slate-50/70 px-4 py-3 sm:px-6">
        <p aria-live="polite" className={`mb-1 min-h-[1rem] text-xs font-semibold sm:mb-2 sm:min-h-[1.25rem] ${msg?.kind === 'err' ? 'text-rose-700' : 'text-emerald-700'}`}>
          {msg?.text}
        </p>
        {sel && selRoom ? (
          <form
            className="flex flex-col gap-2 lg:flex-row lg:items-end"
            onSubmit={(e) => {
              e.preventDefault();
              if (!book.isPending) book.mutate(sel);
            }}
          >
            <div className="grid flex-1 grid-cols-2 gap-2 sm:grid-cols-[1.3fr_0.8fr_0.8fr_2fr]">
              <Field label="Oda" className="hidden sm:flex">
                <select
                  value={sel.roomId}
                  onChange={(e) => {
                    const id = e.target.value;
                    const m = slots.find((x) => x >= sel.s && free(id, x)) ?? slots.find((x) => free(id, x));
                    if (m == null) {
                      setSel(null);
                      setMsg({ kind: 'err', text: 'Bu odada bu gün boş saat yok.' });
                      return;
                    }
                    anchor.current = { roomId: id, m };
                    setSel(span(id, m, m + (sel.e - sel.s) - step));
                  }}
                  className={input}
                >
                  {rooms.map((r) => (
                    <option key={r.id} value={r.id}>
                      {r.name}
                    </option>
                  ))}
                </select>
              </Field>
              <Field label="Başlangıç">
                <select
                  value={sel.s}
                  onChange={(e) => {
                    const s = Number(e.target.value);
                    anchor.current = { roomId: sel.roomId, m: s };
                    setSel(span(sel.roomId, s, s + (sel.e - sel.s) - step));
                  }}
                  className={input}
                >
                  {startOptions.map((m) => (
                    <option key={m} value={m}>
                      {toHHMM(m)}
                    </option>
                  ))}
                </select>
              </Field>
              <Field label="Bitiş">
                <select value={sel.e} onChange={(e) => setSel({ ...sel, e: Number(e.target.value) })} className={input}>
                  {endChoices.map((m) => (
                    <option key={m} value={m}>
                      {toHHMM(m)}
                    </option>
                  ))}
                </select>
              </Field>
              <Field label="Konu (isteğe bağlı)" className="col-span-2 sm:col-span-1">
                <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Yayın kurulu hazırlığı" className={input} />
              </Field>
            </div>
            <div className="flex items-center justify-between gap-3 lg:flex-col lg:items-end">
              <span className="kp-mono text-[11px] font-semibold text-muted">
                <span className="sm:hidden">{selRoom.name} · </span>
                {dayLabel(date, serverToday)} · {toHHMM(sel.s)}–{toHHMM(sel.e)} · {duration(sel.e - sel.s)}
              </span>
              <button
                type="submit"
                className="kp-press flex min-h-11 shrink-0 items-center gap-2 whitespace-nowrap rounded-xl bg-violet px-5 text-sm font-extrabold text-white shadow-sm hover:bg-violet-600 sm:min-h-10"
              >
                {book.isPending && <Loader2 className="h-4 w-4 animate-spin" aria-hidden />}
                Rezerve et
              </button>
            </div>
          </form>
        ) : (
          data &&
          rooms.length > 0 && <p className="text-xs text-muted">Bir odanın boş saatine tıkla. Seçim burada özetlenir, sonra “Rezerve et”e bas.</p>
        )}
        {data?.me.admin && <RoomAdmin rooms={rooms} onMessage={setMsg} />}
      </footer>
    </div>
  );
}

function RoomColumn({
  room,
  row: ROW,
  slots,
  step,
  startMin,
  busy,
  isPast,
  sel,
  nowTop,
  confirmCancel,
  cancelling,
  onAskCancel,
  onCancel,
  onDown,
  onMove,
  onUp,
  onKeyPick,
  free,
}: {
  room: Room;
  row: number;
  slots: number[];
  step: number;
  startMin: number;
  busy: Array<{ s: number; e: number; b: RoomBooking }>;
  isPast: (m: number) => boolean;
  sel: Selection | null;
  nowTop: number | null;
  confirmCancel: string | null;
  cancelling: string | null | undefined;
  onAskCancel: (id: string | null) => void;
  onCancel: (id: string) => void;
  onDown: (e: ReactPointerEvent<HTMLDivElement>) => void;
  onMove: (e: ReactPointerEvent<HTMLDivElement>) => void;
  onUp: () => void;
  onKeyPick: (m: number, shift: boolean) => void;
  free: (roomId: string, m: number) => boolean;
}) {
  const end = startMin + slots.length * step;
  return (
    <div
      className="rb-col relative select-none border-l border-slate-200/80"
      style={{ height: slots.length * ROW }}
      onPointerDown={onDown}
      onPointerMove={onMove}
      onPointerUp={onUp}
      onPointerCancel={onUp}
    >
      {slots.map((m, i) => {
        const past = isPast(m);
        const ok = free(room.id, m);
        return (
          <button
            key={m}
            type="button"
            tabIndex={ok ? 0 : -1}
            aria-disabled={!ok}
            aria-label={`${room.name} ${toHHMM(m)}–${toHHMM(m + step)} ${ok ? 'boş' : past ? 'geçti' : 'dolu'}`}
            onClick={(e) => {
              // Fare seçimi pointerdown'da yapıldı; burada klavye (detail 0) ve dokunmatik dokunuş kalır.
              const type = (e.nativeEvent as PointerEvent).pointerType;
              if (ok && (e.detail === 0 || (type && type !== 'mouse'))) onKeyPick(m, e.shiftKey);
            }}
            className={`rb-slot absolute inset-x-0 block ${m % 60 === 0 ? 'border-t border-slate-200' : 'border-t border-dashed border-slate-100'} ${
              past ? 'rb-past cursor-not-allowed' : ok ? 'cursor-pointer' : ''
            }`}
            style={{ top: i * ROW, height: ROW }}
          />
        );
      })}

      {sel && (
        <div
          className="pointer-events-none absolute inset-x-1 z-10 flex items-start justify-between rounded-lg border-2 border-violet bg-violet/10 px-2 py-1"
          style={{ top: ((sel.s - startMin) / step) * ROW, height: ((sel.e - sel.s) / step) * ROW }}
        >
          <span className="kp-mono text-[11px] font-extrabold text-violet">
            {toHHMM(sel.s)}–{toHHMM(sel.e)}
          </span>
        </div>
      )}

      {busy.map(({ s, e, b }) => {
        const top = ((Math.max(s, startMin) - startMin) / step) * ROW;
        const height = ((Math.min(e, end) - Math.max(s, startMin)) / step) * ROW;
        if (height <= 0) return null;
        const asking = confirmCancel === b.id;
        const tall = height >= ROW * 2;
        const compact = height < ROW * 1.5 && !asking;
        return (
          <div
            key={b.id}
            data-booking
            className={`absolute inset-x-1 z-10 overflow-hidden rounded-lg px-2 py-1 text-[11px] leading-tight ${
              b.mine ? 'border border-violet/40 bg-violet text-white' : 'border border-slate-300 bg-slate-100 text-ink'
            }`}
            // İptal onayı kısa blokta sığmaz; onay süresince blok iki satır kadar uzar ve üstte kalır.
            style={{ top: top + 1, height: asking ? Math.max(height, ROW * 2) - 2 : height - 2, zIndex: asking ? 30 : undefined }}
            title={`${b.displayName} · ${b.startLocal}–${b.endLocal}${b.title ? ` · ${b.title}` : ''}`}
          >
            <div className="flex items-start justify-between gap-1">
              <p className="min-w-0 truncate font-extrabold">
                {b.mine ? 'Sen' : b.displayName}
                {compact && (
                  <span className={`kp-mono font-semibold ${b.mine ? 'text-white/85' : 'text-muted'}`}>
                    {' '}
                    · {b.startLocal}–{b.endLocal}
                    {b.title ? ` · ${b.title}` : ''}
                  </span>
                )}
              </p>
              {b.canCancel && !asking && (
                <button
                  type="button"
                  onClick={() => onAskCancel(b.id)}
                  className={`kp-press -mr-1 shrink-0 rounded px-1 font-bold underline-offset-2 hover:underline ${b.mine ? 'text-white/90' : 'text-rose-700'}`}
                >
                  İptal
                </button>
              )}
            </div>
            {compact ? null : asking ? (
              <div className="mt-0.5 flex items-center gap-1">
                <button
                  type="button"
                  onClick={() => onCancel(b.id)}
                  className="kp-press rounded bg-rose-600 px-1.5 py-0.5 font-bold text-white"
                >
                  {cancelling === b.id ? 'İptal ediliyor…' : 'Evet, iptal et'}
                </button>
                <button type="button" onClick={() => onAskCancel(null)} className="kp-press rounded px-1.5 py-0.5 font-bold">
                  Vazgeç
                </button>
              </div>
            ) : (
              <p className={`kp-mono truncate ${b.mine ? 'text-white/85' : 'text-muted'}`}>
                {b.startLocal}–{b.endLocal}
                {tall && b.title ? '' : b.title ? ` · ${b.title}` : ''}
              </p>
            )}
            {tall && b.title && !asking && <p className={`mt-0.5 line-clamp-2 ${b.mine ? 'text-white/90' : 'text-ink/80'}`}>{b.title}</p>}
          </div>
        );
      })}

      {nowTop != null && (
        <div className="pointer-events-none absolute inset-x-0 z-[5] h-0.5 bg-coral" style={{ top: nowTop }} aria-hidden />
      )}
    </div>
  );
}

function RoomAdmin({ rooms, onMessage }: { rooms: Room[]; onMessage: (m: { kind: 'ok' | 'err'; text: string } | null) => void }) {
  const qc = useQueryClient();
  const [open, setOpen] = useState(rooms.length === 0);
  const [name, setName] = useState('');
  const [location, setLocation] = useState('');
  const [capacity, setCapacity] = useState('');
  const [confirm, setConfirm] = useState<string | null>(null);

  useEffect(() => {
    if (rooms.length === 0) setOpen(true);
  }, [rooms.length]);

  const add = useMutation({
    mutationFn: () => roomsApi.addRoom({ name: name.trim(), location: location.trim(), capacity: capacity ? Number(capacity) : null }),
    onSuccess: (r) => {
      onMessage({ kind: 'ok', text: `«${r.name}» eklendi.` });
      setName('');
      setLocation('');
      setCapacity('');
      void qc.invalidateQueries({ queryKey: ['rooms'] });
    },
    onError: (err) => onMessage({ kind: 'err', text: errorText(err) }),
  });
  const remove = useMutation({
    mutationFn: (id: string) => roomsApi.removeRoom(id),
    onSuccess: (r) => {
      onMessage({
        kind: 'ok',
        text: `«${r.name}» kaldırıldı${r.cancelledBookings ? `, ${r.cancelledBookings} ileri tarihli rezervasyon iptal edildi` : ''}.`,
      });
      setConfirm(null);
      void qc.invalidateQueries({ queryKey: ['rooms'] });
    },
    onError: (err) => onMessage({ kind: 'err', text: errorText(err) }),
  });

  return (
    <div className="mt-3 border-t border-slate-200/70 pt-2">
      <button type="button" onClick={() => setOpen((v) => !v)} aria-expanded={open} className="kp-press min-h-11 text-xs font-bold text-violet sm:min-h-0">
        {open ? 'Oda yönetimini kapat' : 'Odaları yönet (yönetici)'}
      </button>
      {open && (
        <div className="mt-2 grid gap-3 lg:grid-cols-2">
          <ul className="space-y-1.5">
            {rooms.map((r) => (
              <li key={r.id} className="flex items-center justify-between gap-2 rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs">
                <span className="min-w-0 truncate">
                  <b className="text-ink">{r.name}</b>
                  <span className="text-muted">
                    {r.location ? ` · ${r.location}` : ''}
                    {r.capacity != null ? ` · ${r.capacity} kişi` : ''}
                  </span>
                </span>
                {confirm === r.id ? (
                  <span className="flex shrink-0 items-center gap-1">
                    <button type="button" onClick={() => remove.mutate(r.id)} className="kp-press rounded-lg bg-rose-600 px-2 py-1 font-bold text-white">
                      Kaldır, ileri rezervasyonları iptal et
                    </button>
                    <button type="button" onClick={() => setConfirm(null)} className="kp-press rounded-lg px-2 py-1 font-bold text-ink">
                      Vazgeç
                    </button>
                  </span>
                ) : (
                  <button type="button" aria-label={`${r.name} odasını kaldır`} onClick={() => setConfirm(r.id)} className="kp-press flex h-9 w-9 shrink-0 items-center justify-center rounded-lg text-muted hover:bg-rose-50 hover:text-rose-700">
                    <Trash2 className="h-4 w-4" />
                  </button>
                )}
              </li>
            ))}
          </ul>
          <form
            className="grid grid-cols-2 gap-2 sm:grid-cols-[1.4fr_1fr_0.6fr_auto] sm:items-end"
            onSubmit={(e) => {
              e.preventDefault();
              if (!name.trim()) {
                onMessage({ kind: 'err', text: 'Oda adını yaz.' });
                return;
              }
              add.mutate();
            }}
          >
            <Field label="Oda adı" className="col-span-2 sm:col-span-1">
              <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Büyük Divan Salonu" className={input} />
            </Field>
            <Field label="Yeri">
              <input value={location} onChange={(e) => setLocation(e.target.value)} placeholder="3. kat" className={input} />
            </Field>
            <Field label="Kişi">
              <input value={capacity} onChange={(e) => setCapacity(e.target.value.replace(/\D/g, ''))} inputMode="numeric" placeholder="12" className={input} />
            </Field>
            <button type="submit" className="kp-press col-span-2 flex min-h-11 items-center justify-center gap-1 rounded-xl border border-violet/40 bg-white px-3 text-xs font-bold text-violet hover:bg-violet/5 sm:col-span-1 sm:min-h-9">
              <Plus className="h-4 w-4" aria-hidden /> Oda ekle
            </button>
          </form>
        </div>
      )}
    </div>
  );
}

const input = 'h-11 w-full rounded-xl border border-slate-200 bg-white px-2.5 text-sm font-semibold text-ink focus:border-violet focus:outline-none focus:ring-2 focus:ring-violet/30 sm:h-9 sm:text-xs';

function Field({ label, className = '', children }: { label: string; className?: string; children: ReactNode }) {
  return (
    <label className={`flex min-w-0 flex-col gap-1 ${className}`}>
      <span className="text-[11px] font-bold text-muted">{label}</span>
      {children}
    </label>
  );
}

function errorText(err: unknown): string {
  if (err instanceof EngineAuthError) return 'Oturumun düşmüş. Sayfayı yenileyip yeniden giriş yap.';
  if (err instanceof RoomsError) {
    if (err.status === 409 && err.booking) return `Bu saat az önce doldu: ${err.booking.displayName}, ${err.booking.startLocal}–${err.booking.endLocal}.`;
    return err.message;
  }
  return err instanceof Error ? err.message : 'Beklenmeyen bir hata oldu.';
}
