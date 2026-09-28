import { useEffect, useState, type ReactNode } from 'react';
import { Link, NavLink } from 'react-router-dom';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { ChevronRight } from 'lucide-react';
import Sheet from '../editorial/studio/reader/Sheet';
import { Note, btnGhost, btnPrimary, errText, field, label as labelCls } from '../admin/ui';
import { Chips } from '../field/parts';
import { fmtDay, fmtShort } from '../field/api';
import { fmtChange, levelTone, musteriApi, type Account, type Action, type Level, type Meta } from './api';

/** Müşteri ilişkileri ekranlarının ortak parçaları. Telefon önce (320/390 px): listeler kart, dokunma hedefleri en az
 *  44 px; hareket yalnız basma geri bildirimi (M30 kartlarıyla aynı). */

const TONE = {
  err: 'bg-red-50 text-red-700',
  warn: 'bg-amber-50 text-amber-800',
  muted: 'bg-slate-100 text-canvas-ink',
} as const;

export function LevelBadge({ level, label, puan }: { level: Level | null; label: string; puan?: number | null }) {
  return (
    <span
      className={`inline-flex h-9 min-w-9 shrink-0 flex-col items-center justify-center rounded-xl px-1.5 leading-none ${TONE[levelTone(level)]}`}
      title={`Kayıp riski: ${label || 'değerlendirilmedi'}${puan !== null && puan !== undefined ? ` (puan ${Math.round(puan)})` : ''}`}
    >
      <span className="font-mono text-[13px] font-extrabold tabular-nums">{puan === null || puan === undefined || level === 'yok' ? '—' : Math.round(puan)}</span>
      {level === 'kayip' && <span className="mt-0.5 text-[8.5px] font-extrabold uppercase">kayıp</span>}
    </span>
  );
}

/** Alt gezinme: Özet · Cariler · Portföyüm · Veri sağlığı (yetkiye göre). Telefonda yatay kayar. */
export function SubNav({ meta }: { meta: Meta | undefined }) {
  const items = [
    { to: '/musteri-iliskileri', label: 'Özet', end: true },
    { to: '/musteri-iliskileri/cariler', label: 'Cariler', end: false },
    { to: '/musteri-iliskileri/portfoyum', label: 'Portföyüm', end: false },
    ...(meta?.me.canHealth ? [{ to: '/musteri-iliskileri/veri-sagligi', label: 'Veri sağlığı', end: false }] : []),
  ];
  return (
    <nav className="-mx-1 overflow-x-auto px-1" aria-label="Müşteri ilişkileri">
      <div className="flex w-max min-w-full gap-1 rounded-2xl bg-slate-100 p-1">
        {items.map((i) => (
          <NavLink
            key={i.to}
            to={i.to}
            end={i.end}
            className={({ isActive }) =>
              `inline-flex min-h-11 shrink-0 items-center whitespace-nowrap rounded-xl px-3 text-[12.5px] font-extrabold transition-colors duration-150 sm:min-h-9 ${
                isActive ? 'bg-canvas-violet text-white shadow-md' : 'text-canvas-ink hover:bg-white/70'
              }`
            }
          >
            {i.label}
          </NavLink>
        ))}
      </div>
    </nav>
  );
}

/** Cari kartı: risk, unvan, değer ve değişim, nedenler; tamamı ayrıntıya götürür (tek dokunuş). */
export function AccountRow({ a, showRep, trailing }: { a: Account; showRep?: boolean; trailing?: ReactNode }) {
  return (
    <li className="flex items-stretch gap-2">
      <Link
        to={`/musteri-iliskileri/cari/${encodeURIComponent(a.code)}`}
        className="flex min-h-14 min-w-0 flex-1 items-start gap-2.5 rounded-2xl border border-slate-100 bg-white/85 p-3 transition-transform duration-150 ease-out active:scale-[0.98]"
      >
        <LevelBadge level={a.duzey} label={a.duzeyAd} puan={a.puan} />
        <div className="min-w-0 flex-1">
          <div className="flex items-baseline justify-between gap-2">
            <div className="min-w-0 truncate text-[13.5px] font-extrabold">{a.ad || a.code}</div>
            <div className="shrink-0 font-mono text-[12px] font-bold tabular-nums">{fmtShort(a.net12)}</div>
          </div>
          <div className="mt-0.5 flex items-baseline justify-between gap-2 text-[11.5px] text-canvas-muted">
            <span className="min-w-0 truncate">
              {[a.logoKanal || a.kanal, a.bolge, showRep ? a.temsilciAd || a.temsilci || 'temsilcisiz' : null, a.sonFatura ? `son fatura ${fmtDay(a.sonFatura)}` : null]
                .filter(Boolean)
                .join(' · ')}
            </span>
            <span className={`shrink-0 font-mono font-bold tabular-nums ${a.degisim !== null && a.degisim < -0.1 ? 'text-red-700' : ''}`}>{fmtChange(a.degisim)}</span>
          </div>
          {a.nedenler.length > 0 && (
            <div className="mt-1.5">
              <Chips chips={a.nedenler} limit={2} />
            </div>
          )}
        </div>
        <ChevronRight aria-hidden className="mt-2 h-4 w-4 shrink-0 text-canvas-muted" />
      </Link>
      {trailing}
    </li>
  );
}

const TODAY = () => new Intl.DateTimeFormat('en-CA', { timeZone: 'Europe/Istanbul' }).format(new Date());

/** Aksiyon yaz (3 dokunuş: aç → tür → kaydet). Sonuç 30/90 gün sonra Logo'dan kendiliğinden ölçülür. */
export function ActionSheet({
  open,
  onClose,
  code,
  ad,
  meta,
  edit,
}: {
  open: boolean;
  onClose: () => void;
  code: string;
  ad: string | null;
  meta: Meta;
  edit?: Action | null;
}) {
  const qc = useQueryClient();
  const [tur, setTur] = useState<Action['tur']>('arama');
  const [text, setText] = useState('');
  const [termin, setTermin] = useState('');
  const [durum, setDurum] = useState<Action['durum']>('acik');
  const [sonuc, setSonuc] = useState('');
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setErr(null);
    setTur(edit?.tur ?? 'arama');
    setText(edit?.aciklama ?? '');
    setTermin(edit?.termin ?? '');
    setDurum(edit?.durum ?? 'acik');
    setSonuc(edit?.sonucNotu ?? '');
  }, [open, edit]);

  const save = useMutation({
    mutationFn: () => {
      if (!text.trim()) throw new Error('Aksiyonu bir cümleyle yazın.');
      if (edit) return musteriApi.updateAction(edit.id, { aciklama: text.trim(), termin: termin || null, durum, sonucNotu: sonuc });
      return musteriApi.addAction(code, { tur, aciklama: text.trim(), termin: termin || null });
    },
    onSuccess: () => {
      toast.success(edit ? 'Aksiyon güncellendi' : 'Aksiyon kaydedildi');
      void qc.invalidateQueries({ queryKey: ['musteri'] });
      onClose();
    },
    onError: (e) => setErr(errText(e, 'Kaydedilemedi.')),
  });

  return (
    <Sheet open={open} modal onClose={onClose} title={edit ? 'Aksiyonu güncelle' : 'Aksiyon yaz'} subtitle={ad || code}>
      <form
        className="flex flex-col gap-3 text-[13px]"
        onSubmit={(e) => {
          e.preventDefault();
          setErr(null);
          save.mutate();
        }}
      >
        {!edit && (
          <fieldset className="flex flex-col gap-1">
            <legend className={labelCls}>Tür</legend>
            <div className="mt-1 grid grid-cols-2 gap-1 rounded-2xl bg-slate-100 p-1 sm:grid-cols-4">
              {meta.actionTypes.map((t) => (
                <button
                  key={t.key}
                  type="button"
                  aria-pressed={tur === t.key}
                  onClick={() => setTur(t.key)}
                  className={`min-h-11 rounded-xl px-2 text-[12.5px] font-extrabold transition-colors duration-150 ${tur === t.key ? 'bg-canvas-violet text-white shadow-md' : 'text-canvas-ink hover:bg-white/70'}`}
                >
                  {t.label}
                </button>
              ))}
            </div>
          </fieldset>
        )}
        <label className="flex flex-col gap-1">
          <span className={labelCls}>Ne yapılacak</span>
          <textarea
            className={`${field} min-h-[96px]`}
            value={text}
            maxLength={2000}
            placeholder="Örn. Bu hafta ziyaret; çocuk yeni çıkanlar ve okul dönemi kampanyası konuşulacak."
            onChange={(e) => setText(e.target.value)}
          />
        </label>
        <label className="flex min-w-0 flex-col gap-1 sm:max-w-[220px]">
          <span className={labelCls}>Termin</span>
          <input type="date" className={field} value={termin} min={edit ? undefined : TODAY()} onChange={(e) => setTermin(e.target.value)} />
        </label>
        {edit && (
          <>
            <fieldset className="flex flex-col gap-1">
              <legend className={labelCls}>Durum</legend>
              <div className="mt-1 grid grid-cols-3 gap-1 rounded-2xl bg-slate-100 p-1">
                {(
                  [
                    ['acik', 'Açık'],
                    ['yapildi', 'Yapıldı'],
                    ['iptal', 'İptal'],
                  ] as const
                ).map(([k, l]) => (
                  <button
                    key={k}
                    type="button"
                    aria-pressed={durum === k}
                    onClick={() => setDurum(k)}
                    className={`min-h-11 rounded-xl text-[12.5px] font-extrabold transition-colors duration-150 ${durum === k ? 'bg-canvas-violet text-white shadow-md' : 'text-canvas-ink hover:bg-white/70'}`}
                  >
                    {l}
                  </button>
                ))}
              </div>
            </fieldset>
            <label className="flex flex-col gap-1">
              <span className={labelCls}>Sonuç notu</span>
              <textarea className={`${field} min-h-[72px]`} value={sonuc} maxLength={2000} onChange={(e) => setSonuc(e.target.value)} />
            </label>
          </>
        )}
        {err && <Note tone="err">{err}</Note>}
        <p className="text-[11px] leading-snug text-canvas-muted">Aksiyon portalda tutulur, CRM'e aktarılmaz. 30 ve 90 gün sonraki alım Logo'dan kendiliğinden ölçülür.</p>
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

/** Aksiyon satırı: tür, açıklama, termin, 30/90 gün sonucu (olgunlaşınca). */
export function ActionItem({ a, onEdit, showCari }: { a: Action; onEdit?: (a: Action) => void; showCari?: boolean }) {
  const res = (v: number | null, d: number) => (v === null ? `${d} gün: bekliyor` : `${d} gün: ${v > 0 ? fmtShort(v) : 'alım yok'}`);
  return (
    <li className="rounded-2xl border border-slate-100 bg-white/85 p-3">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="text-[11px] font-bold uppercase tracking-wide text-canvas-muted">
            {a.turAd} · {a.durumAd} · {fmtDay(a.tarih)}
            {a.termin ? ` · termin ${fmtDay(a.termin)}` : ''}
          </div>
          {showCari && (
            <Link to={`/musteri-iliskileri/cari/${encodeURIComponent(a.code)}`} className="mt-0.5 block truncate text-[13px] font-extrabold hover:underline">
              {a.cariAd || a.code}
            </Link>
          )}
          <p className="mt-0.5 break-words text-[12.5px] leading-snug">{a.aciklama}</p>
          {a.sonucNotu && <p className="mt-1 break-words text-[12px] leading-snug text-canvas-muted">Sonuç: {a.sonucNotu}</p>}
          <div className="mt-1 text-[11.5px] text-canvas-muted">
            {a.sahip} · {res(a.sonuc30, 30)} · {res(a.sonuc90, 90)}
          </div>
        </div>
        {onEdit && (
          <button type="button" className={`${btnGhost} !min-h-9 shrink-0`} onClick={() => onEdit(a)}>
            Güncelle
          </button>
        )}
      </div>
    </li>
  );
}
