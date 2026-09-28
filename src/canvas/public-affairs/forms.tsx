import { useEffect, useState } from 'react';
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Loader2, Search, Sparkles } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import { Note, Pill, btnGhost, btnPrimary, errText, field, label } from '../admin/ui';
import SearchSelect from '../components/SearchSelect';
import SqlInfo from '../components/SqlInfo';
import Sheet from '../editorial/studio/reader/Sheet';
import { useDebounced } from '../editorial/kit';
import { nowLocal, usePeopleOptions } from '../editorial/authors/shared';
import { fmtInt, paApi, type Note as PaNote, type Person, type Place } from './api';
import { invalidatePa, usePaMeta } from './parts';

/** M28 formları: temas notu (telefonda iki dokunuş), kişi kartı (CRM'den bağlama ya da elle), kurum kartı. */

/* ------------------------------------------------------------------ temas notu */

export function NoteForm({
  open,
  onClose,
  target,
  note,
}: {
  open: boolean;
  onClose: () => void;
  target: { personId?: string; orgId?: string; name: string };
  note?: PaNote | null;
}) {
  const qc = useQueryClient();
  const meta = usePaMeta();
  const people = usePeopleOptions();
  const blank = () => {
    const n = nowLocal();
    return {
      date: n.date, time: n.time, channel: 'telefon', tone: '', topic: '', text: '', visibility: 'herkes',
      participants: [] as string[], nextStep: '', nextOn: '',
    };
  };
  const [f, setF] = useState(blank);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    if (!open) return;
    setErr(null);
    setF(
      note
        ? {
            date: note.date, time: note.time, channel: note.channel, tone: note.tone ?? '', topic: note.topic, text: note.text ?? '',
            visibility: note.visibility, participants: note.participants.map((p) => p.username), nextStep: note.nextStep ?? '', nextOn: note.nextOn ?? '',
          }
        : blank(),
    );
  }, [open, note]);
  const set = <K extends keyof ReturnType<typeof blank>>(k: K, v: ReturnType<typeof blank>[K]) => setF((p) => ({ ...p, [k]: v }));

  const save = useMutation({
    mutationFn: () => {
      const body = {
        ...f,
        tone: f.tone || null,
        participants: f.participants.map((u) => ({ username: u, display: people.byUser.get(u) ?? u })),
        nextStep: f.nextStep || null,
        nextOn: f.nextOn || null,
      };
      if (note) return paApi.updateNote(note.id, body);
      return target.personId ? paApi.addPersonNote(target.personId, body) : paApi.addOrgNote(target.orgId as string, body);
    },
    onSuccess: async () => {
      await invalidatePa(qc);
      toast.success(note ? 'Not güncellendi.' : 'Not kaydedildi.');
      onClose();
    },
    onError: (e) => setErr(errText(e, 'Not kaydedilemedi.')),
  });

  return (
    <Sheet open={open} onClose={onClose} modal title={note ? 'Notu düzenle' : 'Temas notu'} subtitle={target.name}>
      <form
        className="space-y-3 text-[12.5px]"
        onSubmit={(e) => {
          e.preventDefault();
          setErr(null);
          save.mutate();
        }}
      >
        <label className="block">
          <span className={label}>Konu</span>
          <input required maxLength={300} value={f.topic} onChange={(e) => set('topic', e.target.value)} autoFocus placeholder="ör. Kitap teşekkürü, proje görüşmesi" className={`${field} mt-1`} />
        </label>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          <label className="block">
            <span className={label}>Tarih</span>
            <input type="date" required value={f.date} onChange={(e) => set('date', e.target.value)} className={`${field} mt-1`} />
          </label>
          <label className="block">
            <span className={label}>Saat</span>
            <input type="time" required value={f.time} onChange={(e) => set('time', e.target.value)} className={`${field} mt-1`} />
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
          <label className="block">
            <span className={label}>Ton</span>
            <select value={f.tone} onChange={(e) => set('tone', e.target.value)} className={`${field} mt-1`}>
              <option value="">Belirtilmedi</option>
              {(meta.data?.tones ?? []).map((c) => (
                <option key={c.key} value={c.key}>
                  {c.label}
                </option>
              ))}
            </select>
          </label>
        </div>
        <label className="block">
          <span className={label}>Not</span>
          <textarea rows={4} maxLength={20000} value={f.text} onChange={(e) => set('text', e.target.value)} className={`${field} mt-1 resize-y leading-snug`} />
        </label>
        <div className="grid gap-2 sm:grid-cols-[1fr_170px]">
          <label className="block">
            <span className={label}>Sıradaki adım</span>
            <input maxLength={500} value={f.nextStep} onChange={(e) => set('nextStep', e.target.value)} placeholder="ör. Yeni kitabı gönder" className={`${field} mt-1`} />
          </label>
          <label className="block">
            <span className={label}>Adım tarihi</span>
            <input type="date" value={f.nextOn} onChange={(e) => set('nextOn', e.target.value)} className={`${field} mt-1`} />
          </label>
        </div>
        <fieldset>
          <legend className={label}>Kim görür</legend>
          <div className="mt-1 grid gap-1.5 sm:grid-cols-2">
            {(meta.data?.visibility ?? []).map((v) => (
              <label key={v.key} className={`flex min-h-11 cursor-pointer items-center gap-2 rounded-xl border px-3 ${f.visibility === v.key ? 'border-canvas-violet bg-violet-50/60' : 'border-slate-200 bg-white/80'}`}>
                <input type="radio" name="visibility" value={v.key} checked={f.visibility === v.key} onChange={() => set('visibility', v.key)} />
                <span className="font-semibold">{v.label}</span>
              </label>
            ))}
          </div>
        </fieldset>
        {f.visibility === 'ozel' && (
          <div>
            <span className={label}>Katılımcılar (notu görebilir)</span>
            <SearchSelect multiple label="Katılımcılar" placeholder="Yalnız ben" options={people.options} value={f.participants} onChange={(v) => set('participants', v)} className="mt-1" />
          </div>
        )}
        {err && <Note tone="err">{err}</Note>}
        <div className="flex justify-end gap-2 pt-1">
          <button type="button" className={btnGhost} onClick={onClose} disabled={save.isPending}>
            Vazgeç
          </button>
          <button type="submit" className={btnPrimary} disabled={save.isPending || !f.topic.trim()}>
            {save.isPending ? 'Kaydediliyor…' : 'Kaydet'}
          </button>
        </div>
      </form>
    </Sheet>
  );
}

/* ------------------------------------------------------------------ kişi kartı */

type PersonDraft = {
  name: string; title: string; orgName: string; orgId: string; fieldKey: string; interests: string; city: string; email: string;
  phone: string; priority: string; isPublicOfficial: boolean; owner: string;
};

function draftOf(p?: Person | null): PersonDraft {
  return {
    name: p?.name ?? '', title: p?.title ?? '', orgName: p?.orgName ?? '', orgId: p?.orgId ?? '', fieldKey: p?.fieldKey ?? '',
    interests: (p?.interests ?? []).join(', '), city: p?.city ?? '', email: p?.email ?? '', phone: p?.phone ?? '',
    priority: p?.priority ?? 'normal', isPublicOfficial: p?.isPublicOfficial ?? false, owner: p?.owner ?? '',
  };
}

export function PersonForm({ open, onClose, person, onSaved }: { open: boolean; onClose: () => void; person?: Person | null; onSaved?: (id: string) => void }) {
  const qc = useQueryClient();
  const meta = usePaMeta();
  const people = usePeopleOptions();
  const [mode, setMode] = useState<'crm' | 'elle'>(person ? 'elle' : 'crm');
  const [f, setF] = useState<PersonDraft>(() => draftOf(person));
  const [q, setQ] = useState('');
  const [page, setPage] = useState(0);
  const [err, setErr] = useState<string | null>(null);
  const dq = useDebounced(q, 350);
  useEffect(() => {
    if (!open) return;
    setF(draftOf(person));
    setMode(person ? 'elle' : 'crm');
    setQ('');
    setPage(0);
    setErr(null);
  }, [open, person]);
  useEffect(() => setPage(0), [dq]);
  const set = <K extends keyof PersonDraft>(k: K, v: PersonDraft[K]) => setF((p) => ({ ...p, [k]: v }));

  const orgs = useQuery({ queryKey: ['pa', 'orgs', 'all'], queryFn: () => paApi.orgs(), enabled: ENGINE_ENABLED && open, staleTime: 60_000 });
  const crm = useQuery({
    queryKey: ['pa', 'crm-contacts', dq, page],
    queryFn: () => paApi.crmContacts({ q: dq, page }),
    enabled: ENGINE_ENABLED && open && mode === 'crm' && dq.trim().length >= 2,
    placeholderData: keepPreviousData,
  });

  const body = () => ({
    name: f.name, title: f.title || null, orgName: f.orgName || null, orgId: f.orgId || null, fieldKey: f.fieldKey || null,
    interests: f.interests, city: f.city || null, email: f.email || null, phone: f.phone || null, priority: f.priority,
    isPublicOfficial: f.isPublicOfficial, owner: f.owner || null, ownerDisplay: f.owner ? people.byUser.get(f.owner) ?? f.owner : null,
  });
  const done = async (id: string, msg: string) => {
    await invalidatePa(qc);
    toast.success(msg);
    onSaved?.(id);
    onClose();
  };
  const save = useMutation({
    mutationFn: () => (person ? paApi.updatePerson(person.id, body()) : paApi.addPerson(body())),
    onSuccess: (p) => done(p.id, person ? 'Kart güncellendi.' : 'Kişi kartı açıldı.'),
    onError: (e) => setErr(errText(e, 'Kart kaydedilemedi.')),
  });
  const link = useMutation({
    mutationFn: (crmContactId: string) =>
      paApi.addPerson({ fromCrm: true, crmContactId, priority: f.priority, isPublicOfficial: f.isPublicOfficial, fieldKey: f.fieldKey || null }),
    onSuccess: (p) => done(p.id, p.created ? 'Kişi CRM\'den alındı.' : 'Bu kişinin kartı zaten vardı; açılıyor.'),
    onError: (e) => setErr(errText(e, 'CRM kişisi alınamadı.')),
  });

  const fields = (meta.data?.fields ?? []).filter((x) => x.active || x.key === f.fieldKey);
  const common = (
    <>
      <div className="grid gap-2 sm:grid-cols-3">
        <label className="block">
          <span className={label}>Alan</span>
          <select value={f.fieldKey} onChange={(e) => set('fieldKey', e.target.value)} className={`${field} mt-1`}>
            <option value="">Seçilmedi</option>
            {fields.map((x) => (
              <option key={x.key} value={x.key}>
                {x.label}
              </option>
            ))}
          </select>
        </label>
        <label className="block">
          <span className={label}>Öncelik</span>
          <select value={f.priority} onChange={(e) => set('priority', e.target.value)} className={`${field} mt-1`}>
            {(meta.data?.priorities ?? []).map((x) => (
              <option key={x.key} value={x.key}>
                {x.label}
              </option>
            ))}
          </select>
        </label>
        <label className="flex min-h-11 items-center gap-2 self-end rounded-xl border border-slate-200 bg-white/80 px-3">
          <input type="checkbox" checked={f.isPublicOfficial} onChange={(e) => set('isPublicOfficial', e.target.checked)} />
          <span className="font-semibold">Kamu görevlisi</span>
        </label>
      </div>
      {f.isPublicOfficial && <p className="text-[11.5px] leading-snug text-amber-800">Kamu görevlisine hediye, onay sırasında hukuk onayı işaretlenmeden gönderilemez.</p>}
    </>
  );

  return (
    <Sheet open={open} onClose={onClose} modal title={person ? 'Kişi kartını düzenle' : 'Yeni kişi'} subtitle={person ? person.name : 'CRM\'deki kişiye bağlayın ya da elle açın'}>
      {!person && (
        <div className="mb-3 grid grid-cols-2 gap-1 rounded-2xl bg-slate-100 p-1" role="tablist" aria-label="Kaynak">
          {(['crm', 'elle'] as const).map((m) => (
            <button
              key={m}
              type="button"
              role="tab"
              aria-selected={mode === m}
              onClick={() => setMode(m)}
              className={`min-h-11 rounded-xl px-2 text-[12px] font-extrabold transition-colors duration-150 sm:min-h-9 ${mode === m ? 'bg-canvas-violet text-white shadow-md' : 'text-canvas-ink hover:bg-white/70'}`}
            >
              {m === 'crm' ? 'CRM\'den bağla' : 'Elle aç'}
            </button>
          ))}
        </div>
      )}
      {mode === 'crm' && !person ? (
        <div className="space-y-3 text-[12.5px]">
          <label className="block">
            <span className={label}>Ad, kurum ya da unvan</span>
            <div className="relative mt-1">
              <Search aria-hidden className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-canvas-muted" />
              <input value={q} onChange={(e) => setQ(e.target.value)} autoFocus placeholder="ör. Ahmet Yılmaz, Marmara Üniversitesi" className={`${field} pl-9`} />
            </div>
          </label>
          {common}
          {crm.isFetching && !crm.data && <p className="text-canvas-muted">CRM'de aranıyor…</p>}
          {crm.error && <Note tone="err">{errText(crm.error, 'CRM okunamadı.')}</Note>}
          {crm.data && (
            <>
              <p className="flex flex-wrap items-center gap-1 text-[11.5px] text-canvas-muted">
                CRM'de {fmtInt(crm.data.total)} kişi · {crm.data.items.length ? `${fmtInt(page * crm.data.pageSize + 1)}–${fmtInt(page * crm.data.pageSize + crm.data.items.length)}` : 'eşleşme yok'}
                <SqlInfo k={crm.data.kaynaklar} alan="total" label="CRM kişi araması" />
              </p>
              <ul className="divide-y divide-slate-100 rounded-2xl border border-slate-100 bg-white/80">
                {crm.data.items.map((c) => (
                  <li key={c.crmContactId} className="flex flex-wrap items-center justify-between gap-2 px-3 py-2">
                    <div className="min-w-0">
                      <div className="break-words font-extrabold">{c.name}</div>
                      <div className="text-[11.5px] text-canvas-muted">{[c.title || c.unvan || c.academicTitle, c.orgName, c.city].filter(Boolean).join(' · ') || '—'}</div>
                      {c.roleLabel && <Pill tone={c.role === 1 ? 'violet' : 'muted'}>{c.roleLabel}</Pill>}
                    </div>
                    <button type="button" className={`${c.personId ? btnGhost : btnPrimary} !min-h-9 !py-1`} disabled={link.isPending} onClick={() => c.crmContactId && link.mutate(c.crmContactId)}>
                      {c.personId ? 'Kartı aç' : 'Bu kişiyi al'}
                    </button>
                  </li>
                ))}
              </ul>
              {crm.data.total > (page + 1) * crm.data.pageSize && (
                <button type="button" className={`${btnGhost} w-full`} onClick={() => setPage((p) => p + 1)}>
                  Sonraki {crm.data.pageSize}
                </button>
              )}
              {page > 0 && (
                <button type="button" className={`${btnGhost} w-full`} onClick={() => setPage((p) => Math.max(0, p - 1))}>
                  Önceki
                </button>
              )}
            </>
          )}
          {err && <Note tone="err">{err}</Note>}
        </div>
      ) : (
        <form
          className="space-y-3 text-[12.5px]"
          onSubmit={(e) => {
            e.preventDefault();
            setErr(null);
            save.mutate();
          }}
        >
          <label className="block">
            <span className={label}>Ad soyad</span>
            <input required maxLength={300} value={f.name} onChange={(e) => set('name', e.target.value)} autoFocus={!person} className={`${field} mt-1`} />
          </label>
          <div className="grid gap-2 sm:grid-cols-2">
            <label className="block">
              <span className={label}>Unvan / görev</span>
              <input maxLength={300} value={f.title} onChange={(e) => set('title', e.target.value)} placeholder="ör. Tarih bölümü öğretim üyesi" className={`${field} mt-1`} />
            </label>
            <label className="block">
              <span className={label}>Kurum kartı</span>
              <select value={f.orgId} onChange={(e) => set('orgId', e.target.value)} className={`${field} mt-1`}>
                <option value="">Bağlı değil</option>
                {(orgs.data?.items ?? []).map((o) => (
                  <option key={o.id} value={o.id}>
                    {o.name}
                  </option>
                ))}
              </select>
            </label>
          </div>
          {!f.orgId && (
            <label className="block">
              <span className={label}>Kurum adı (kartı yoksa)</span>
              <input maxLength={300} value={f.orgName} onChange={(e) => set('orgName', e.target.value)} className={`${field} mt-1`} />
            </label>
          )}
          {common}
          <label className="block">
            <span className={label}>İlgi alanları (virgülle)</span>
            <input value={f.interests} onChange={(e) => set('interests', e.target.value)} placeholder="ör. Osmanlı tarihi, çocuk edebiyatı" className={`${field} mt-1`} />
            <span className="mt-1 block text-[11px] leading-snug text-canvas-muted">İnanç, siyasi görüş, köken gibi kişisel özellikler yazılmaz; yalnız mesleki ilgi.</span>
          </label>
          <div>
            <span className={label}>İlişki sahibi</span>
            <SearchSelect label="İlişki sahibi" placeholder="Seçilmedi" options={people.options} value={f.owner} onChange={(v) => set('owner', v)} className="mt-1" />
          </div>
          <div className="grid gap-2 sm:grid-cols-3">
            <label className="block">
              <span className={label}>E-posta</span>
              <input type="email" maxLength={200} value={f.email} onChange={(e) => set('email', e.target.value)} className={`${field} mt-1`} />
            </label>
            <label className="block">
              <span className={label}>Telefon</span>
              <input type="tel" maxLength={60} value={f.phone} onChange={(e) => set('phone', e.target.value)} className={`${field} mt-1`} />
            </label>
            <label className="block">
              <span className={label}>Şehir</span>
              <input maxLength={120} value={f.city} onChange={(e) => set('city', e.target.value)} className={`${field} mt-1`} />
            </label>
          </div>
          {err && <Note tone="err">{err}</Note>}
          <div className="flex justify-end gap-2 pt-1">
            <button type="button" className={btnGhost} onClick={onClose} disabled={save.isPending}>
              Vazgeç
            </button>
            <button type="submit" className={btnPrimary} disabled={save.isPending || !f.name.trim()}>
              {save.isPending ? 'Kaydediliyor…' : person ? 'Kaydet' : 'Kartı aç'}
            </button>
          </div>
        </form>
      )}
    </Sheet>
  );
}

/** Kişinin alanı için Zeki AI önerisi (onaylı listeden tek seçim; karta yazmaz, kullanıcı uygular). */
export function FieldSuggest({ person, onApply }: { person: Person; onApply: (key: string) => void }) {
  const meta = usePaMeta();
  const ask = useMutation({ mutationFn: () => paApi.suggestField(person.id), onError: (e) => toast.error(errText(e, 'Öneri alınamadı.') ?? '') });
  const r = ask.data;
  const lab = (k: string | null | undefined) => meta.data?.fields.find((x) => x.key === k)?.label ?? k;
  return (
    <div className="flex flex-wrap items-center gap-2">
      <button type="button" className={`${btnGhost} !min-h-9 !py-1`} disabled={ask.isPending} onClick={() => ask.mutate()}>
        {ask.isPending ? <Loader2 aria-hidden className="h-3.5 w-3.5 animate-spin" /> : <Sparkles aria-hidden className="h-3.5 w-3.5" />}
        Alan öner
      </button>
      {r && r.fieldKey && (
        <>
          <span className="text-[12px]">
            Öneri: <b>{lab(r.fieldKey)}</b>
            {r.probability != null && <span className="text-canvas-muted"> · olasılık %{Math.round(r.probability * 100)}</span>}
          </span>
          <button type="button" className={`${btnPrimary} !min-h-9 !py-1`} onClick={() => onApply(r.fieldKey as string)}>
            Uygula
          </button>
        </>
      )}
      {r && !r.fieldKey && <span className="text-[12px] text-canvas-muted">{r.reason}{r.candidate ? ` (aday: ${lab(r.candidate)})` : ''}</span>}
    </div>
  );
}

/* ------------------------------------------------------------------ kurum kartı */

export function OrgForm({ open, onClose, onSaved }: { open: boolean; onClose: () => void; onSaved?: (id: string) => void }) {
  const qc = useQueryClient();
  const meta = usePaMeta();
  const [mode, setMode] = useState<'crm' | 'elle'>('crm');
  const [q, setQ] = useState('');
  const [tip, setTip] = useState<number | ''>('');
  const [page, setPage] = useState(0);
  const [f, setF] = useState({ name: '', kind: 'diger', city: '', note: '' });
  const [err, setErr] = useState<string | null>(null);
  const dq = useDebounced(q, 350);
  useEffect(() => {
    if (!open) return;
    setMode('crm');
    setQ('');
    setTip('');
    setPage(0);
    setF({ name: '', kind: 'diger', city: '', note: '' });
    setErr(null);
  }, [open]);
  useEffect(() => setPage(0), [dq, tip]);
  const places = useQuery({
    queryKey: ['pa', 'crm-places', dq, tip, page],
    queryFn: () => paApi.crmPlaces({ q: dq, kurumTipi: tip, page }),
    enabled: ENGINE_ENABLED && open && mode === 'crm' && dq.trim().length >= 2,
    placeholderData: keepPreviousData,
  });
  const done = async (id: string, msg: string) => {
    await invalidatePa(qc);
    toast.success(msg);
    onSaved?.(id);
    onClose();
  };
  const link = useMutation({
    mutationFn: (p: Place) => paApi.addOrg({ fromCrm: true, crmVisitPlaceId: p.id }),
    onSuccess: (o) => done(o.id, o.created ? 'Kurum CRM\'den alındı.' : 'Bu kurumun kartı zaten vardı; açılıyor.'),
    onError: (e) => setErr(errText(e, 'Kurum alınamadı.')),
  });
  const save = useMutation({
    mutationFn: () => paApi.addOrg({ ...f, city: f.city || null, note: f.note || null }),
    onSuccess: (o) => done(o.id, 'Kurum kartı açıldı.'),
    onError: (e) => setErr(errText(e, 'Kurum kaydedilemedi.')),
  });

  return (
    <Sheet open={open} onClose={onClose} modal title="Yeni kurum" subtitle="CRM ziyaret yerine bağlayın ya da (Diyanet, kütüphane, STK gibi) elle açın">
      <div className="mb-3 grid grid-cols-2 gap-1 rounded-2xl bg-slate-100 p-1" role="tablist" aria-label="Kaynak">
        {(['crm', 'elle'] as const).map((m) => (
          <button
            key={m}
            type="button"
            role="tab"
            aria-selected={mode === m}
            onClick={() => setMode(m)}
            className={`min-h-11 rounded-xl px-2 text-[12px] font-extrabold transition-colors duration-150 sm:min-h-9 ${mode === m ? 'bg-canvas-violet text-white shadow-md' : 'text-canvas-ink hover:bg-white/70'}`}
          >
            {m === 'crm' ? 'CRM ziyaret yerlerinden' : 'Elle aç'}
          </button>
        ))}
      </div>
      {mode === 'crm' ? (
        <div className="space-y-3 text-[12.5px]">
          <div className="grid gap-2 sm:grid-cols-[1fr_170px]">
            <label className="block">
              <span className={label}>Kurum adı</span>
              <input value={q} onChange={(e) => setQ(e.target.value)} autoFocus placeholder="ör. Üsküdar Belediyesi" className={`${field} mt-1`} />
            </label>
            <label className="block">
              <span className={label}>Kurum tipi</span>
              <select value={tip} onChange={(e) => setTip(e.target.value ? Number(e.target.value) : '')} className={`${field} mt-1`}>
                <option value="">Hepsi</option>
                {(meta.data?.kurumTipi ?? []).map((k) => (
                  <option key={k.key} value={k.key}>
                    {k.label}
                  </option>
                ))}
              </select>
            </label>
          </div>
          {places.error && <Note tone="err">{errText(places.error, 'CRM okunamadı.')}</Note>}
          {places.data && (
            <>
              <p className="flex items-center gap-1 text-[11.5px] text-canvas-muted">CRM'de {fmtInt(places.data.total)} kurum<SqlInfo k={places.data.kaynaklar} alan="total" label="CRM ziyaret yeri araması" /></p>
              <ul className="divide-y divide-slate-100 rounded-2xl border border-slate-100 bg-white/80">
                {places.data.items.map((p) => (
                  <li key={p.id} className="flex flex-wrap items-center justify-between gap-2 px-3 py-2">
                    <div className="min-w-0">
                      <div className="break-words font-extrabold">{p.name}</div>
                      <div className="text-[11.5px] text-canvas-muted">
                        {[p.kurumTipiLabel, p.kurumTuru, [p.district, p.city].filter(Boolean).join(' / '), p.students != null ? `${fmtInt(p.students)} öğrenci` : null].filter(Boolean).join(' · ')}
                      </div>
                    </div>
                    <button type="button" className={`${p.orgId ? btnGhost : btnPrimary} !min-h-9 !py-1`} disabled={link.isPending} onClick={() => link.mutate(p)}>
                      {p.orgId ? 'Kartı aç' : 'Bu kurumu al'}
                    </button>
                  </li>
                ))}
              </ul>
              <div className="flex gap-2">
                {page > 0 && (
                  <button type="button" className={`${btnGhost} flex-1`} onClick={() => setPage((x) => Math.max(0, x - 1))}>
                    Önceki
                  </button>
                )}
                {places.data.total > (page + 1) * places.data.pageSize && (
                  <button type="button" className={`${btnGhost} flex-1`} onClick={() => setPage((x) => x + 1)}>
                    Sonraki {places.data.pageSize}
                  </button>
                )}
              </div>
            </>
          )}
          {err && <Note tone="err">{err}</Note>}
        </div>
      ) : (
        <form
          className="space-y-3 text-[12.5px]"
          onSubmit={(e) => {
            e.preventDefault();
            setErr(null);
            save.mutate();
          }}
        >
          <label className="block">
            <span className={label}>Kurum adı</span>
            <input required maxLength={300} value={f.name} onChange={(e) => setF((p) => ({ ...p, name: e.target.value }))} autoFocus className={`${field} mt-1`} />
          </label>
          <div className="grid gap-2 sm:grid-cols-2">
            <label className="block">
              <span className={label}>Tür</span>
              <select value={f.kind} onChange={(e) => setF((p) => ({ ...p, kind: e.target.value }))} className={`${field} mt-1`}>
                {(meta.data?.orgKinds ?? []).map((k) => (
                  <option key={k.key} value={k.key}>
                    {k.label}
                  </option>
                ))}
              </select>
            </label>
            <label className="block">
              <span className={label}>İl</span>
              <input maxLength={120} value={f.city} onChange={(e) => setF((p) => ({ ...p, city: e.target.value }))} className={`${field} mt-1`} />
            </label>
          </div>
          <label className="block">
            <span className={label}>Not</span>
            <textarea rows={3} maxLength={4000} value={f.note} onChange={(e) => setF((p) => ({ ...p, note: e.target.value }))} className={`${field} mt-1 resize-y`} />
          </label>
          {err && <Note tone="err">{err}</Note>}
          <div className="flex justify-end gap-2 pt-1">
            <button type="button" className={btnGhost} onClick={onClose} disabled={save.isPending}>
              Vazgeç
            </button>
            <button type="submit" className={btnPrimary} disabled={save.isPending || !f.name.trim()}>
              {save.isPending ? 'Kaydediliyor…' : 'Kartı aç'}
            </button>
          </div>
        </form>
      )}
    </Sheet>
  );
}
