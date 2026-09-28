import { useEffect, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import Sheet from '../editorial/studio/reader/Sheet';
import { btnGhost, btnPrimary, field, label as labelCls } from '../admin/ui';
import { ENGINE_ENABLED } from '../engine';
import { evApi, fmtDay, parseNum, type FairDetail, type FairInput, type Meta } from './api';

/** Fuar/etkinlik kartı formu: yeni kart ve kart özetinin düzenlenmesi. Zorunlu yalnız ad ve tarih; gerisi sonra da girilir
 *  (fuar alanında uzun form doldurulmaz). */
export default function FairForm({ open, meta, initial, busy, onClose, onSave }: {
  open: boolean;
  meta: Meta;
  initial?: FairDetail | null;
  busy?: boolean;
  onClose: () => void;
  onSave: (b: FairInput) => void;
}) {
  const [name, setName] = useState('');
  const [kind, setKind] = useState('stant');
  const [startsOn, setStartsOn] = useState('');
  const [endsOn, setEndsOn] = useState('');
  const [city, setCity] = useState('');
  const [venue, setVenue] = useState('');
  const [budget, setBudget] = useState('');
  const [owner, setOwner] = useState('');
  const [prev, setPrev] = useState('');
  const [stand, setStand] = useState('');
  const [note, setNote] = useState('');

  useEffect(() => {
    if (!open) return;
    setName(initial?.name ?? '');
    setKind(initial?.kind ?? 'stant');
    setStartsOn(initial?.startsOn ?? '');
    setEndsOn(initial?.endsOn ?? '');
    setCity(initial?.city ?? '');
    setVenue(initial?.venue ?? '');
    setBudget(initial?.budgetPlanned != null ? String(initial.budgetPlanned).replace('.', ',') : '');
    setOwner(initial?.owner ?? meta.me.username);
    setPrev(initial?.prevFairId ?? '');
    setStand(initial?.standInfo ?? '');
    setNote(initial?.note ?? '');
  }, [open, initial, meta.me.username]);

  const fairs = useQuery({ queryKey: ['ev', 'fairs', 'all'], queryFn: () => evApi.fairs(), enabled: ENGINE_ENABLED && open, staleTime: 60_000 });
  const budgetNum = budget.trim() ? parseNum(budget) : null;
  const bad = !name.trim() || !startsOn || (endsOn !== '' && endsOn < startsOn) || (budget.trim() !== '' && budgetNum === null);
  const approved = initial?.status === 'onayli';
  const budgetChanged = approved && (budgetNum ?? null) !== (initial?.budgetPlanned ?? null);
  const datesChanged = approved && (startsOn !== initial?.startsOn || (endsOn || startsOn) !== initial?.endsOn);

  return (
    <Sheet open={open} modal onClose={onClose} title={initial ? 'Kartı düzenle' : 'Yeni fuar ya da etkinlik'}
      subtitle={initial ? `${initial.name} · ${fmtDay(initial.startsOn)}` : 'Ad ve tarih yeter; bütçe, yer ve öncekiyle bağ sonra da girilir.'}>
      <form
        className="flex flex-col gap-3"
        onSubmit={(e) => {
          e.preventDefault();
          if (bad) return;
          onSave({
            name: name.trim(), kind, startsOn, endsOn: endsOn || startsOn, city: city.trim() || null, venue: venue.trim() || null,
            budgetPlanned: budgetNum, ownerUser: owner.trim() || null, prevFairId: prev || null, standInfo: stand.trim() || null,
            note: note.trim() || null,
          });
        }}
      >
        <label className="flex flex-col gap-1">
          <span className={labelCls}>Ad</span>
          <input className={field} value={name} onChange={(e) => setName(e.target.value)} placeholder="ör. İstanbul Kitap Fuarı 2026" required />
        </label>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Tür</span>
            <select className={field} value={kind} onChange={(e) => setKind(e.target.value)}>
              {Object.entries(meta.kinds).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
          </label>
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Başlangıç</span>
            <input type="date" className={field} value={startsOn} onChange={(e) => setStartsOn(e.target.value)} required />
          </label>
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Bitiş</span>
            <input type="date" className={field} value={endsOn} min={startsOn || undefined} onChange={(e) => setEndsOn(e.target.value)} />
          </label>
        </div>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Şehir</span>
            <input className={field} value={city} onChange={(e) => setCity(e.target.value)} />
          </label>
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Yer / salon</span>
            <input className={field} value={venue} onChange={(e) => setVenue(e.target.value)} />
          </label>
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Planlanan bütçe (₺)</span>
            <input inputMode="decimal" className={`${field} font-mono tabular-nums`} value={budget} onChange={(e) => setBudget(e.target.value)} placeholder="ör. 250.000" />
          </label>
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Sorumlu (kullanıcı adı)</span>
            <input className={field} value={owner} autoCapitalize="none" onChange={(e) => setOwner(e.target.value)} />
          </label>
        </div>
        <label className="flex flex-col gap-1">
          <span className={labelCls}>Geçen yılın aynı fuarı</span>
          <select className={field} value={prev} onChange={(e) => setPrev(e.target.value)}>
            <option value="">Bağlı değil (aynı günlerin geçen yılı kullanılır)</option>
            {(fairs.data?.items ?? []).filter((f) => f.id !== initial?.id).map((f) => (
              <option key={f.id} value={f.id}>{f.name} · {fmtDay(f.startsOn)}</option>
            ))}
          </select>
          <span className="text-[11px] leading-snug text-canvas-muted">Kitap/adet önerisi ve sonuç karşılaştırması bu kartın tarihlerine ve carilerine göre yapılır.</span>
        </label>
        <label className="flex flex-col gap-1">
          <span className={labelCls}>Stant bilgisi</span>
          <textarea className={`${field} min-h-[64px]`} value={stand} onChange={(e) => setStand(e.target.value)} placeholder="Salon, stant no, metrekare" />
        </label>
        <label className="flex flex-col gap-1">
          <span className={labelCls}>Not</span>
          <textarea className={`${field} min-h-[64px]`} value={note} onChange={(e) => setNote(e.target.value)} />
        </label>
        {(budgetChanged || datesChanged) && (
          <p className="rounded-xl bg-amber-50 px-3 py-2 text-[12px] font-semibold text-amber-800">
            Kart onaylı: tarih ya da bütçe değişince katılım kararı yeniden gerekir, kart «karar bekliyor»a döner.
          </p>
        )}
        <div className="flex flex-wrap justify-end gap-2">
          <button type="button" className={btnGhost} onClick={onClose}>Vazgeç</button>
          <button type="submit" className={btnPrimary} disabled={bad || busy}>{initial ? 'Kaydet' : 'Kartı aç'}</button>
        </div>
      </form>
    </Sheet>
  );
}
