import { useEffect, useId, useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import Sheet from '../editorial/studio/reader/Sheet';
import { Note, btnGhost, btnPrimary, errText, field, label as labelCls } from '../admin/ui';
import VoiceNoteButton from '../voice/VoiceNoteButton';
import { appendNote } from '../voice/api';
import { fieldApi, istanbulToday, parseTr, TONE_LABEL, type Visit, type VisitInput } from './api';

/** Ziyaret notu / ziyaret planı. Telefonda alttan açılır; en sık iş «not bırak»: metin + ton + (isteğe bağlı) sonraki adım ve
 *  ödeme sözü. Tahsilat burada girilmez (CRM'de girilir). Gizli not yalnız yazana görünür, özete de girmez. */

type Mode = 'not' | 'plan';

export default function VisitNoteSheet({
  open,
  onClose,
  code,
  unvan,
  mode,
  visit,
}: {
  open: boolean;
  onClose: () => void;
  code: string;
  unvan: string | null;
  mode: Mode;
  /** Var olan kaydı düzenlerken (planlanan ziyarete not yazmak dahil). */
  visit?: Visit | null;
}) {
  const qc = useQueryClient();
  const today = istanbulToday();
  const [when, setWhen] = useState(today);
  const [time, setTime] = useState('');
  const [text, setText] = useState('');
  const [ton, setTon] = useState<Visit['ton']>(null);
  const [next, setNext] = useState('');
  const [nextDay, setNextDay] = useState('');
  const [promiseDay, setPromiseDay] = useState('');
  const [promiseAmt, setPromiseAmt] = useState('');
  const [secret, setSecret] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const noteId = useId();

  useEffect(() => {
    if (!open) return;
    setErr(null);
    setWhen((visit?.planlanan || today).slice(0, 10));
    setTime(visit?.planlanan && visit.planlanan.length > 10 ? visit.planlanan.slice(11, 16) : '');
    setText(visit?.notu ?? '');
    setTon(visit?.ton ?? null);
    setNext(visit?.sonrakiAdim ?? '');
    setNextDay(visit?.sonrakiTarih ?? '');
    setPromiseDay(visit?.sozOdemeTarihi ?? '');
    setPromiseAmt(visit?.sozOdemeTutari ? String(visit.sozOdemeTutari).replace('.', ',') : '');
    setSecret(visit?.gizli ?? false);
  }, [open, visit, today]);

  const save = useMutation({
    mutationFn: () => {
      const amt = parseTr(promiseAmt);
      if (Number.isNaN(amt)) throw new Error('Söz verilen tutar sayı olmalı (örn. 20.000).');
      if (mode === 'plan') {
        const planned = time ? `${when}T${time}` : when;
        return visit ? fieldApi.updateVisit(visit.id, { planlanan: planned }) : fieldApi.addVisit({ tur: 'cari', hedef: code, planlanan: planned, durum: 'planlandi' });
      }
      if (!text.trim()) throw new Error('Not boş olamaz.');
      const body: VisitInput = {
        durum: 'yapildi',
        notu: text.trim(),
        ton,
        sonrakiAdim: next.trim(),
        sonrakiTarih: nextDay || null,
        sozOdemeTarihi: promiseDay || null,
        sozOdemeTutari: amt,
        gizli: secret,
      };
      return visit ? fieldApi.updateVisit(visit.id, body) : fieldApi.addVisit({ ...body, tur: 'cari', hedef: code });
    },
    onSuccess: () => {
      toast.success(mode === 'plan' ? 'Ziyaret planlandı' : 'Not kaydedildi');
      void qc.invalidateQueries({ queryKey: ['field'] });
      onClose();
    },
    onError: (e) => setErr(errText(e, 'Kaydedilemedi.')),
  });

  return (
    <Sheet open={open} modal onClose={onClose} title={mode === 'plan' ? 'Ziyaret planla' : 'Görüşme notu'} subtitle={unvan || code}>
      <form
        className="flex flex-col gap-3 text-[13px]"
        onSubmit={(e) => {
          e.preventDefault();
          setErr(null);
          save.mutate();
        }}
      >
        {mode === 'plan' ? (
          <div className="grid grid-cols-2 gap-2">
            <label className="flex min-w-0 flex-col gap-1">
              <span className={labelCls}>Gün</span>
              <input type="date" required className={field} value={when} min={today} onChange={(e) => setWhen(e.target.value)} />
            </label>
            <label className="flex min-w-0 flex-col gap-1">
              <span className={labelCls}>Saat (isteğe bağlı)</span>
              <input type="time" className={field} value={time} onChange={(e) => setTime(e.target.value)} />
            </label>
          </div>
        ) : (
          <>
            <div className="flex flex-col gap-1">
              <div className="flex items-start justify-between gap-2">
                <label htmlFor={noteId} className={`${labelCls} pt-2.5`}>
                  Ne konuşuldu
                </label>
                <VoiceNoteButton context={{ baglam: 'saha', ad: unvan }} onText={(t) => setText((cur) => appendNote(cur, t))} disabled={save.isPending} />
              </div>
              <textarea
                id={noteId}
                autoFocus
                className={`${field} min-h-[120px]`}
                value={text}
                maxLength={4000}
                placeholder="Örn. Kalanı 15 Ekim'de çekle ödeyecek; çocuk kitaplarından yeni sipariş verecek."
                onChange={(e) => setText(e.target.value)}
              />
            </div>
            <fieldset className="flex flex-col gap-1">
              <legend className={labelCls}>Görüşmenin tonu</legend>
              <div className="mt-1 grid grid-cols-3 gap-1 rounded-2xl bg-slate-100 p-1">
                {(Object.keys(TONE_LABEL) as Array<NonNullable<Visit['ton']>>).map((k) => (
                  <button
                    key={k}
                    type="button"
                    aria-pressed={ton === k}
                    onClick={() => setTon(ton === k ? null : k)}
                    className={`min-h-11 rounded-xl text-[12.5px] font-extrabold transition-colors duration-150 ${ton === k ? 'bg-canvas-violet text-white shadow-md' : 'text-canvas-ink hover:bg-white/70'}`}
                  >
                    {TONE_LABEL[k]}
                  </button>
                ))}
              </div>
            </fieldset>
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-[1fr_150px]">
              <label className="flex min-w-0 flex-col gap-1">
                <span className={labelCls}>Sonraki adım</span>
                <input className={field} value={next} maxLength={500} placeholder="Örn. Katalog gönder, 2 hafta sonra uğra" onChange={(e) => setNext(e.target.value)} />
              </label>
              <label className="flex min-w-0 flex-col gap-1">
                <span className={labelCls}>Ne zaman</span>
                <input type="date" className={field} value={nextDay} onChange={(e) => setNextDay(e.target.value)} />
              </label>
            </div>
            <div className="rounded-2xl bg-slate-50 p-3">
              <div className={labelCls}>Ödeme sözü</div>
              <p className="mt-0.5 text-[11.5px] leading-snug text-canvas-muted">Tarihi geçer ve Logo'da ödeme görünmezse müşteri ertesi gün listenin üstüne çıkar.</p>
              <div className="mt-2 grid grid-cols-2 gap-2">
                <label className="flex min-w-0 flex-col gap-1">
                  <span className="text-[11px] font-bold text-canvas-muted">Tarih</span>
                  <input type="date" className={field} value={promiseDay} onChange={(e) => setPromiseDay(e.target.value)} />
                </label>
                <label className="flex min-w-0 flex-col gap-1">
                  <span className="text-[11px] font-bold text-canvas-muted">Tutar (₺)</span>
                  <input inputMode="decimal" autoComplete="off" className={`${field} font-mono tabular-nums`} value={promiseAmt} placeholder="Örn. 20.000" onChange={(e) => setPromiseAmt(e.target.value)} />
                </label>
              </div>
            </div>
            <label className="flex min-h-11 items-center gap-2.5 text-[12.5px] font-semibold">
              <input type="checkbox" className="h-5 w-5 accent-canvas-violet" checked={secret} onChange={(e) => setSecret(e.target.checked)} />
              Gizli not — metni yalnız ben görürüm (Zeki AI özetine de girmez)
            </label>
          </>
        )}
        {err && <Note tone="err">{err}</Note>}
        <p className="text-[11px] leading-snug text-canvas-muted">Tahsilat CRM'de ya da saha uygulamasında girilir; burada tekrar girilmez. Not CRM'e aktarılmaz.</p>
        <div className="sticky bottom-0 -mx-4 flex justify-end gap-2 border-t border-slate-100 bg-white/95 px-4 py-3">
          <button type="button" className={btnGhost} onClick={onClose}>
            Vazgeç
          </button>
          <button type="submit" className={btnPrimary} disabled={save.isPending}>
            {save.isPending ? 'Kaydediliyor…' : 'Kaydet'}
          </button>
        </div>
      </form>
    </Sheet>
  );
}
