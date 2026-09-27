import { useEffect, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Trash2 } from 'lucide-react';
import { ENGINE_ENABLED, authorsApi, roomsApi, type AuthorMeeting, type AuthorMeetingInput } from '../../engine';
import { Note, btnGhost, btnPrimary, field, label } from '../../admin/ui';
import Sheet from '../studio/reader/Sheet';
import { ConfirmDialog } from '../studio/dialogs';
import SearchSelect from '../../components/SearchSelect';
import { invalidateAuthors, nowLocal, useAuthorsMeta, usePeopleOptions } from './shared';

/** Randevu (planlanan görüşme) ve görüşme notu (yapılmış görüşme) aynı kayıttır; randevu yapılınca nota döner.
 *  Yeni kayıt ya bir yazar kartına ya da CRM kişisine yazılır (kart yoksa köprü açar). */

export type MeetingTarget = { cardId?: string | null; crm?: { id: string; name: string } | null; name: string };
export type MeetingMode = 'randevu' | 'not';

const DURATIONS = [15, 30, 45, 60, 90, 120, 180];
const RELEASE = '__birak';

type Form = {
  date: string;
  time: string;
  minutes: string;
  channel: string;
  location: string;
  roomId: string;
  topic: string;
  notes: string;
  tone: string;
  nextStep: string;
  nextDue: string;
  private: boolean;
  participants: string[];
};

function initial(m: AuthorMeeting | null | undefined, mode: MeetingMode): Form {
  if (m) {
    return {
      date: m.date, time: m.time, minutes: m.minutes ? String(m.minutes) : '', channel: m.channel, location: m.location ?? '',
      roomId: '', topic: m.hidden ? '' : m.topic, notes: m.notes ?? '', tone: m.tone ?? '', nextStep: m.nextStep ?? '',
      nextDue: m.nextDue ?? '', private: m.private, participants: m.participants.map((p) => p.username),
    };
  }
  const n = nowLocal();
  return {
    date: n.date, time: mode === 'randevu' ? '10:00' : n.time, minutes: '60', channel: 'yuz_yuze', location: '', roomId: '',
    topic: '', notes: '', tone: '', nextStep: '', nextDue: '', private: false, participants: [],
  };
}

export default function MeetingForm({
  open,
  onClose,
  target,
  mode: startMode,
  meeting,
}: {
  open: boolean;
  onClose: () => void;
  target: MeetingTarget;
  mode: MeetingMode;
  /** Düzenlenen kayıt; yoksa yeni kayıt. */
  meeting?: AuthorMeeting | null;
}) {
  const qc = useQueryClient();
  const meta = useAuthorsMeta();
  const people = usePeopleOptions();
  const [mode, setMode] = useState<MeetingMode>(startMode);
  const [f, setF] = useState<Form>(() => initial(meeting, startMode));
  const [err, setErr] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);

  useEffect(() => {
    if (open) {
      setMode(startMode);
      setF(initial(meeting, startMode));
      setErr(null);
    }
  }, [open, meeting, startMode]);

  const set = <K extends keyof Form>(k: K, v: Form[K]) => setF((p) => ({ ...p, [k]: v }));
  const planned = mode === 'randevu';
  const faceToFace = f.channel === 'yuz_yuze';
  const rooms = useQuery({
    queryKey: ['rooms', 'day', f.date],
    queryFn: () => roomsApi.day(f.date),
    enabled: ENGINE_ENABLED && open && planned && faceToFace && /^\d{4}-\d{2}-\d{2}$/.test(f.date),
    staleTime: 60_000,
  });

  const save = useMutation({
    mutationFn: () => {
      const body: AuthorMeetingInput = {
        status: planned ? 'planlandi' : 'yapildi',
        date: f.date,
        time: f.time,
        minutes: f.minutes ? Number(f.minutes) : null,
        channel: f.channel,
        location: f.location,
        topic: f.topic,
        notes: planned ? (meeting?.notes ?? '') : f.notes,
        tone: planned ? null : f.tone || null,
        nextStep: f.nextStep,
        nextDue: f.nextDue,
        private: f.private,
        participants: f.participants.map((u) => ({ username: u, display: people.byUser.get(u) ?? u })),
      };
      // Oda: boş seçim var olan rezervasyonu korur (saat değişirse aynı oda yeni saate taşınır), «bırak» iptal eder.
      if (planned && faceToFace && f.roomId) body.roomId = f.roomId === RELEASE ? '' : f.roomId;
      if (meeting?.roomBookingId && planned && !faceToFace) body.roomId = '';
      if (meeting) return authorsApi.updateMeeting(meeting.id, body);
      if (target.cardId) return authorsApi.createMeeting({ ...body, cardId: target.cardId });
      return authorsApi.createMeeting({ ...body, crmContactId: target.crm?.id, name: target.crm?.name ?? target.name });
    },
    onSuccess: async (m) => {
      await invalidateAuthors(qc);
      qc.invalidateQueries({ queryKey: ['rooms'] });
      toast.success(planned ? 'Randevu kaydedildi' : 'Görüşme notu kaydedildi', {
        description: m.roomName ? `${m.roomName} ayrıldı` : undefined,
      });
      onClose();
    },
    onError: (e) => setErr(e instanceof Error ? e.message : 'Kaydedilemedi.'),
  });

  const remove = useMutation({
    mutationFn: () => authorsApi.deleteMeeting(meeting!.id),
    onSuccess: async () => {
      await invalidateAuthors(qc);
      qc.invalidateQueries({ queryKey: ['rooms'] });
      toast.success('Kayıt silindi');
      setConfirmDelete(false);
      onClose();
    },
    onError: (e) => {
      setConfirmDelete(false);
      setErr(e instanceof Error ? e.message : 'Silinemedi.');
    },
  });

  const title = meeting ? (planned ? 'Randevuyu düzenle' : 'Görüşme notunu düzenle') : planned ? 'Randevu ekle' : 'Görüşme notu yaz';
  const busy = save.isPending || remove.isPending;
  const roomList = rooms.data?.rooms ?? [];
  const keepRoom = meeting?.roomName && planned && faceToFace && !f.roomId;

  return (
    <>
      <Sheet open={open} onClose={onClose} modal title={title} subtitle={target.name}>
        <form
          className="space-y-3 text-[12.5px]"
          onSubmit={(e) => {
            e.preventDefault();
            setErr(null);
            save.mutate();
          }}
        >
          {meeting?.status === 'planlandi' && (
            <div className="grid grid-cols-2 gap-1 rounded-2xl bg-slate-100 p-1" role="tablist" aria-label="Kayıt türü">
              {(['randevu', 'not'] as const).map((k) => (
                <button
                  key={k}
                  type="button"
                  role="tab"
                  aria-selected={mode === k}
                  onClick={() => setMode(k)}
                  className={`min-h-11 rounded-xl px-2 text-[12px] font-extrabold transition-colors duration-150 sm:min-h-9 ${
                    mode === k ? 'bg-canvas-violet text-white shadow-md' : 'text-canvas-ink hover:bg-white/70'
                  }`}
                >
                  {k === 'randevu' ? 'Randevu' : 'Yapıldı: not yaz'}
                </button>
              ))}
            </div>
          )}

          <div className="grid grid-cols-2 gap-2">
            <label className="block">
              <span className={label}>Tarih</span>
              <input type="date" required value={f.date} onChange={(e) => set('date', e.target.value)} className={`${field} mt-1`} />
            </label>
            <label className="block">
              <span className={label}>Saat</span>
              <input type="time" required step={300} value={f.time} onChange={(e) => set('time', e.target.value)} className={`${field} mt-1`} />
            </label>
            <label className="block">
              <span className={label}>Süre</span>
              <select value={f.minutes} onChange={(e) => set('minutes', e.target.value)} className={`${field} mt-1`}>
                <option value="">Belirtilmedi</option>
                {DURATIONS.map((d) => (
                  <option key={d} value={d}>
                    {d < 60 ? `${d} dk` : `${d / 60} saat`.replace('.5', ',5')}
                  </option>
                ))}
              </select>
            </label>
            <label className="block">
              <span className={label}>Kanal</span>
              <select value={f.channel} onChange={(e) => set('channel', e.target.value)} className={`${field} mt-1`}>
                {(meta.data?.channels ?? []).map((c) => (
                  <option key={c.key} value={c.key}>
                    {c.label}
                  </option>
                ))}
              </select>
            </label>
          </div>

          <label className="block">
            <span className={label}>Konu</span>
            <input required maxLength={300} value={f.topic} onChange={(e) => set('topic', e.target.value)} placeholder="ör. Yeni roman dosyası, sözleşme yenileme" className={`${field} mt-1`} />
          </label>

          <label className="block">
            <span className={label}>{f.channel === 'video' ? 'Bağlantı / yer' : 'Yer'}</span>
            <input maxLength={200} value={f.location} onChange={(e) => set('location', e.target.value)} placeholder={faceToFace ? 'ör. Yayınevi, kafe, fuar standı' : ''} className={`${field} mt-1`} />
          </label>

          {planned && faceToFace && (
            <label className="block">
              <span className={label}>Toplantı odası</span>
              <select value={f.roomId} onChange={(e) => set('roomId', e.target.value)} className={`${field} mt-1`}>
                <option value="">{keepRoom ? `${meeting?.roomName} (ayrılmış)` : 'Oda ayırma'}</option>
                {keepRoom && <option value={RELEASE}>Odayı bırak</option>}
                {roomList.filter((r) => r.name !== meeting?.roomName || !keepRoom).map((r) => (
                  <option key={r.id} value={r.id}>
                    {r.name}
                    {r.capacity ? ` · ${r.capacity} kişi` : ''}
                  </option>
                ))}
              </select>
              <span className="mt-1 block text-[11px] text-canvas-muted">
                {rooms.isError ? 'Odalar okunamadı.' : roomList.length ? 'Seçilirse süre boyunca oda sizin adınıza ayrılır; çakışma varsa kaydedilmez.' : rooms.isLoading ? 'Odalar okunuyor…' : 'Tanımlı oda yok.'}
              </span>
            </label>
          )}

          <div>
            <span className={label}>Katılımcılar (yayınevinden)</span>
            <SearchSelect
              multiple
              label="Katılımcılar"
              placeholder="Kişi seçin"
              options={people.options}
              value={f.participants}
              onChange={(v) => set('participants', v)}
              className="mt-1"
            />
          </div>

          {!planned && (
            <>
              <label className="block">
                <span className={label}>Görüşme notu</span>
                <textarea rows={6} maxLength={20000} value={f.notes} onChange={(e) => set('notes', e.target.value)} placeholder="Ne konuşuldu, yazarın beklentisi, verilen söz…" className={`${field} mt-1 resize-y leading-snug`} />
              </label>
              <fieldset>
                <legend className={label}>Görüşmenin tonu</legend>
                <div className="mt-1 grid grid-cols-4 gap-1 rounded-2xl bg-slate-100 p-1">
                  {[{ key: '', label: 'Belirtme' }, ...(meta.data?.tones ?? [])].map((t) => (
                    <button
                      key={t.key || 'none'}
                      type="button"
                      aria-pressed={f.tone === t.key}
                      onClick={() => set('tone', t.key)}
                      className={`min-h-11 rounded-xl px-1 text-[12px] font-extrabold transition-colors duration-150 sm:min-h-9 ${
                        f.tone === t.key ? 'bg-white shadow-sm' : 'text-canvas-muted hover:bg-white/60'
                      }`}
                    >
                      {t.label}
                    </button>
                  ))}
                </div>
              </fieldset>
            </>
          )}

          <div className="grid gap-2 sm:grid-cols-[minmax(0,1fr)_150px]">
            <label className="block">
              <span className={label}>Sıradaki adım</span>
              <input maxLength={500} value={f.nextStep} onChange={(e) => set('nextStep', e.target.value)} placeholder="ör. Dosyanın ilk 3 bölümü istenecek" className={`${field} mt-1`} />
            </label>
            <label className="block">
              <span className={label}>Adım tarihi</span>
              <input type="date" value={f.nextDue} onChange={(e) => set('nextDue', e.target.value)} className={`${field} mt-1`} />
            </label>
          </div>

          <label className="flex min-h-11 items-center gap-2 font-semibold">
            <input type="checkbox" checked={f.private} onChange={(e) => set('private', e.target.checked)} className="h-4 w-4 accent-[#6D4AFF]" />
            Yalnız ben ve katılımcılar okusun
          </label>

          {err && <Note tone="err">{err}</Note>}

          <div className="flex flex-wrap items-center justify-between gap-2 pt-1">
            {meeting?.canEdit ? (
              <button type="button" className={`${btnGhost} text-rose-700`} disabled={busy} onClick={() => setConfirmDelete(true)}>
                <Trash2 aria-hidden className="h-4 w-4" />
                Sil
              </button>
            ) : (
              <span />
            )}
            <div className="flex gap-2">
              <button type="button" className={btnGhost} onClick={onClose} disabled={busy}>
                Vazgeç
              </button>
              <button type="submit" className={btnPrimary} disabled={busy || !f.topic.trim()}>
                {save.isPending ? 'Kaydediliyor…' : 'Kaydet'}
              </button>
            </div>
          </div>
        </form>
      </Sheet>
      <ConfirmDialog
        open={confirmDelete}
        title="Kayıt silinsin mi?"
        body="Görüşme kaydı ve ayrılmış oda birlikte silinir. Geri alınamaz."
        confirm="Sil"
        danger
        onClose={() => setConfirmDelete(false)}
        onConfirm={() => remove.mutate()}
      />
    </>
  );
}
