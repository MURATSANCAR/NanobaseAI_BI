import { useId, useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Sparkles } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import { Note, btnGhost, btnPrimary, errText, field, label as labelCls } from '../admin/ui';
import Sheet from '../editorial/studio/reader/Sheet';
import VoiceNoteButton from '../voice/VoiceNoteButton';
import { appendNote } from '../voice/api';
import { schoolsApi, type BookRef, type VisitInput } from './api';
import { invalidateSchools, useSchoolsMeta } from './parts';

/** Ziyaret raporu (telefondan ~1 dakika): kiminle görüşüldü, ilgi, istenen kitaplar, bayi yönlendirmesi, sıradaki adım.
 *  Serbest nottan Zeki AI alan önerir, temsilci onaylar. Öğrenci verisi alınmaz; görüşülen kişi rolüyle yazılır. */

const chip = (on: boolean) =>
  `inline-flex min-h-11 items-center rounded-xl px-3 text-[12.5px] font-bold transition-transform duration-150 ease-out active:scale-[0.97] sm:min-h-9 ${
    on ? 'bg-canvas-violet text-white shadow-md' : 'bg-slate-100 text-canvas-ink hover:bg-slate-200'
  }`;

export default function VisitReportSheet({
  open,
  schoolId,
  schoolName,
  planId,
  onClose,
}: {
  open: boolean;
  schoolId: string;
  schoolName: string;
  planId?: string | null;
  onClose: () => void;
}) {
  const qc = useQueryClient();
  const meta = useSchoolsMeta();
  const today = meta.data?.today ?? new Date().toISOString().slice(0, 10);
  const [day, setDay] = useState(today);
  const [role, setRole] = useState<string | null>(null);
  const [interest, setInterest] = useState<string | null>(null);
  const [books, setBooks] = useState<BookRef[]>([]);
  const [bookQ, setBookQ] = useState('');
  const [routed, setRouted] = useState(false);
  const [dealer, setDealer] = useState('');
  const [next, setNext] = useState('');
  const [nextDay, setNextDay] = useState('');
  const [note, setNote] = useState('');
  const [secret, setSecret] = useState(false);
  const noteId = useId();

  const catalog = useQuery({
    queryKey: ['schools', 'catalog-preview', schoolId],
    queryFn: () => schoolsApi.catalog(schoolId, { adet: 'hepsi', onizleme: true }),
    enabled: ENGINE_ENABLED && open,
    staleTime: 5 * 60_000,
    retry: false,
  });
  const dealers = useQuery({
    queryKey: ['schools', 'dealers', schoolId],
    queryFn: () => schoolsApi.dealers(schoolId),
    enabled: ENGINE_ENABLED && open && routed,
    staleTime: 5 * 60_000,
  });

  const picked = new Set(books.map((b) => b.code));
  const shownBooks = useMemo(() => {
    const all = catalog.data?.items ?? [];
    const q = bookQ.trim().toLocaleLowerCase('tr');
    return (q ? all.filter((b) => (b.title ?? '').toLocaleLowerCase('tr').includes(q)) : all).slice(0, q ? 30 : 12);
  }, [catalog.data, bookQ]);

  const suggest = useMutation({
    mutationFn: () => schoolsApi.suggest(schoolId, note),
    onSuccess: (r) => {
      if (!r.ai) {
        toast.message(r.message ?? 'Zeki AI şu an cevap vermiyor.');
        return;
      }
      const f = r.fields;
      if (f.ilgi) setInterest(f.ilgi);
      if (f.kisiRolu) setRole(f.kisiRolu);
      if (f.sonrakiAdim) setNext(f.sonrakiAdim);
      if (typeof f.bayiYonlendirildi === 'boolean') setRouted(f.bayiYonlendirildi);
      if (f.istenenKitaplar?.length) setBooks((cur) => [...cur, ...f.istenenKitaplar!.filter((b) => !cur.some((c) => c.code === b.code))]);
      toast.success('Zeki AI alanları doldurdu; kontrol edip kaydedin.');
    },
    onError: (e) => toast.error(errText(e, 'Öneri alınamadı.') ?? 'Öneri alınamadı.'),
  });

  const save = useMutation({
    mutationFn: () => {
      const b: VisitInput = {
        durum: 'yapildi',
        gerceklesen: day,
        kisiRolu: role,
        ilgi: interest,
        istenenKitaplar: books,
        bayiYonlendirildi: routed,
        bayi: routed ? dealer || null : null,
        sonrakiAdim: next || null,
        sonrakiTarih: nextDay || null,
        not: note || null,
        gizli: secret,
        planId: planId ?? null,
      };
      return schoolsApi.addVisit(schoolId, b);
    },
    onSuccess: (v) => {
      toast.success(v.link && v.link.state === 'oneri' ? 'Rapor kaydedildi; bayi eşleşmesi onaya gitti.' : 'Rapor kaydedildi.');
      invalidateSchools(qc);
      onClose();
    },
    onError: (e) => toast.error(errText(e, 'Kaydedilemedi.') ?? 'Kaydedilemedi.'),
  });

  const dealerOptions = [
    ...(dealers.data?.links ?? []).filter((l) => l.state === 'onayli' && l.code).map((l) => ({ code: l.code!, label: `${l.name ?? l.code} (bağlı)` })),
    ...(dealers.data?.candidates ?? []).filter((c) => !c.linked).map((c) => ({ code: c.code, label: `${c.name ?? c.code}${c.ilce ? ` · ${c.ilce}` : ''}` })),
  ];

  return (
    <Sheet open={open} onClose={onClose} modal title="Ziyaret raporu" subtitle={schoolName}>
      <div className="flex flex-col gap-4">
        <label className="flex flex-col gap-1">
          <span className={labelCls}>Ziyaret günü</span>
          <input type="date" className={field} value={day} max={today} onChange={(e) => setDay(e.target.value)} />
        </label>

        <fieldset>
          <legend className={labelCls}>Kiminle görüştünüz</legend>
          <div className="mt-1.5 flex flex-wrap gap-1.5">
            {(meta.data?.roles ?? []).map((r) => (
              <button key={r.key} type="button" className={chip(role === r.key)} aria-pressed={role === r.key} onClick={() => setRole(role === r.key ? null : r.key)}>
                {r.label}
              </button>
            ))}
          </div>
        </fieldset>

        <fieldset>
          <legend className={labelCls}>İlgi düzeyi</legend>
          <div className="mt-1.5 grid grid-cols-3 gap-1.5">
            {(meta.data?.interest ?? []).map((r) => (
              <button key={r.key} type="button" className={`${chip(interest === r.key)} justify-center`} aria-pressed={interest === r.key} onClick={() => setInterest(r.key)}>
                {r.label}
              </button>
            ))}
          </div>
        </fieldset>

        <fieldset>
          <legend className={labelCls}>İstenen kitaplar</legend>
          {books.length > 0 && (
            <div className="mt-1.5 flex flex-wrap gap-1.5">
              {books.map((b) => (
                <button key={b.code} type="button" className={chip(true)} onClick={() => setBooks(books.filter((x) => x.code !== b.code))} aria-label={`${b.title ?? b.code} çıkar`}>
                  {b.title ?? b.code} ×
                </button>
              ))}
            </div>
          )}
          <input className={`${field} mt-1.5`} placeholder="Kademeye uygun kitaplarda ara" value={bookQ} onChange={(e) => setBookQ(e.target.value)} />
          {catalog.error && <div className="mt-1 text-[11.5px] text-canvas-muted">{errText(catalog.error, 'Kitap listesi okunamadı.')}</div>}
          <div className="mt-1.5 flex flex-wrap gap-1.5">
            {shownBooks
              .filter((b) => !picked.has(b.code))
              .map((b) => (
                <button key={b.code} type="button" className={chip(false)} onClick={() => setBooks([...books, { code: b.code, title: b.title }])}>
                  {b.title ?? b.code}
                </button>
              ))}
          </div>
        </fieldset>

        <fieldset className="flex flex-col gap-2">
          <label className="flex min-h-11 items-center gap-2 text-[13px] font-bold">
            <input type="checkbox" className="h-5 w-5 accent-[#5b3cc4]" checked={routed} onChange={(e) => setRouted(e.target.checked)} />
            Öğretmeni / okulu bir bayiye yönlendirdim
          </label>
          {routed && (
            <select className={field} value={dealer} onChange={(e) => setDealer(e.target.value)}>
              <option value="">{dealers.isLoading ? 'Bayiler okunuyor…' : 'Bayi seçin'}</option>
              {dealerOptions.map((o) => (
                <option key={o.code} value={o.code}>
                  {o.label}
                </option>
              ))}
            </select>
          )}
        </fieldset>

        <div className="grid grid-cols-1 gap-2 sm:grid-cols-[1fr_170px]">
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Sıradaki adım</span>
            <input className={field} value={next} maxLength={300} onChange={(e) => setNext(e.target.value)} placeholder="Ör. 3 kitap için sınıf seti teklifini götür" />
          </label>
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Ne zaman</span>
            <input type="date" className={field} value={nextDay} min={today} onChange={(e) => setNextDay(e.target.value)} />
          </label>
        </div>

        <div className="flex flex-col gap-1">
          <div className="flex items-start justify-between gap-2">
            <label htmlFor={noteId} className={`${labelCls} pt-2.5`}>
              Not
            </label>
            <VoiceNoteButton context={{ baglam: 'okul', ad: schoolName }} onText={(t) => setNote((cur) => appendNote(cur, t))} disabled={save.isPending} />
          </div>
          <textarea id={noteId} className={`${field} min-h-24`} value={note} maxLength={4000} onChange={(e) => setNote(e.target.value)} placeholder="Kısa not; öğrenci adı yazmayın." />
        </div>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <button type="button" className={btnGhost} disabled={!note.trim() || suggest.isPending} onClick={() => suggest.mutate()}>
            <Sparkles aria-hidden className="h-4 w-4" />
            {suggest.isPending ? 'Zeki AI okuyor…' : 'Nottan alanları doldur'}
          </button>
          <label className="flex min-h-11 items-center gap-2 text-[12.5px] font-semibold">
            <input type="checkbox" className="h-5 w-5 accent-[#5b3cc4]" checked={secret} onChange={(e) => setSecret(e.target.checked)} />
            Notu yalnız ben göreyim
          </label>
        </div>

        {!interest && <Note tone="info">Kaydetmek için ilgi düzeyini seçin.</Note>}
        <div className="sticky bottom-0 -mx-4 flex gap-2 border-t border-slate-100 bg-white/95 px-4 py-3">
          <button type="button" className={`${btnGhost} flex-1`} onClick={onClose}>
            Vazgeç
          </button>
          <button type="button" className={`${btnPrimary} flex-[2]`} disabled={!interest || (routed && !dealer) || save.isPending} onClick={() => save.mutate()}>
            {save.isPending ? 'Kaydediliyor…' : 'Raporu kaydet'}
          </button>
        </div>
      </div>
    </Sheet>
  );
}
