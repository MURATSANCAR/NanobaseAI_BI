import { useEffect, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Link2 } from 'lucide-react';
import { ENGINE_ENABLED, authorsApi, type AuthorCard, type AuthorCardInput } from '../../engine';
import { Note, Pill, btnGhost, btnPrimary, field, label } from '../../admin/ui';
import Sheet from '../studio/reader/Sheet';
import SearchSelect from '../../components/SearchSelect';
import SqlInfo from '../../components/SqlInfo';
import { useDebounced } from '../kit';
import { invalidateAuthors, useAuthorsMeta, usePeopleOptions } from './shared';

/** Yeni yazar kartı ve kart düzenleme. Ad yazılırken aynı adlı kart ve CRM kişileri gösterilir: çift kart açılmaz,
 *  CRM'de zaten olan kişiye bağlanılır. */

type Form = {
  name: string;
  stage: string;
  genre: string;
  source: string;
  sourceNote: string;
  email: string;
  phone: string;
  city: string;
  links: string;
  tags: string;
  owner: string;
  bio: string;
  crmContactId: string | null;
  crmName: string | null;
};

const empty = (me: string): Form => ({
  name: '', stage: 'aday', genre: '', source: '', sourceNote: '', email: '', phone: '', city: '', links: '', tags: '',
  owner: me, bio: '', crmContactId: null, crmName: null,
});

const fromCard = (c: AuthorCard): Form => ({
  name: c.name, stage: c.stage, genre: c.genre ?? '', source: c.source ?? '', sourceNote: c.sourceNote ?? '',
  email: c.email ?? '', phone: c.phone ?? '', city: c.city ?? '', links: c.links.join('\n'), tags: c.tags.join(', '),
  owner: c.owner ?? '', bio: c.bio ?? '', crmContactId: c.crmContactId, crmName: c.crmContactId ? c.name : null,
});

export default function CardForm({
  open,
  onClose,
  card,
  onSaved,
  onOpenExisting,
}: {
  open: boolean;
  onClose: () => void;
  /** Düzenlenen kart; yoksa yeni kart. */
  card?: AuthorCard | null;
  onSaved: (card: AuthorCard) => void;
  /** Aynı adlı var olan kartı aç. */
  onOpenExisting: (cardId: string) => void;
}) {
  const qc = useQueryClient();
  const meta = useAuthorsMeta();
  const people = usePeopleOptions();
  const me = meta.data?.me.username ?? '';
  const [f, setF] = useState<Form>(() => (card ? fromCard(card) : empty(me)));
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (open) {
      setF(card ? fromCard(card) : empty(me));
      setErr(null);
    }
  }, [open, card, me]);

  const set = <K extends keyof Form>(k: K, v: Form[K]) => setF((p) => ({ ...p, [k]: v }));
  const name = useDebounced(f.name.trim(), 400);
  const similar = useQuery({
    queryKey: ['authors', 'similar', name],
    queryFn: () => authorsApi.similar(name),
    enabled: ENGINE_ENABLED && open && name.length >= 3 && (!card || name !== card.name),
    staleTime: 60_000,
  });
  const others = (similar.data?.cards ?? []).filter((c) => c.id !== card?.id);
  const crm = (similar.data?.crm ?? []).filter((c) => c.crmContactId !== f.crmContactId);

  const save = useMutation({
    mutationFn: () => {
      const body: AuthorCardInput = {
        name: f.name, stage: f.stage, genre: f.genre, source: f.source, sourceNote: f.sourceNote, email: f.email,
        phone: f.phone, city: f.city, bio: f.bio, owner: f.owner, ownerDisplay: people.byUser.get(f.owner) ?? f.owner,
        links: f.links.split('\n').map((x) => x.trim()).filter(Boolean),
        tags: f.tags.split(',').map((x) => x.trim()).filter(Boolean),
        crmContactId: f.crmContactId,
      };
      return card ? authorsApi.updateCard(card.id, body) : authorsApi.createCard(body);
    },
    onSuccess: async (c) => {
      await invalidateAuthors(qc);
      toast.success(card ? 'Kart güncellendi' : 'Yazar kartı açıldı', { description: c.name });
      onSaved(c);
    },
    onError: (e) => setErr(e instanceof Error ? e.message : 'Kaydedilemedi.'),
  });

  const stages = (meta.data?.stages ?? []).filter((s) => card?.stage === 'yazar' || s.key !== 'yazar');

  return (
    <Sheet open={open} onClose={onClose} modal title={card ? 'Yazar kartını düzenle' : 'Yeni yazar kartı'} subtitle={card ? card.name : 'CRM\'de henüz olmayan yazar ya da aday için'}>
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
          <input required maxLength={300} value={f.name} onChange={(e) => set('name', e.target.value)} autoFocus={!card} className={`${field} mt-1`} />
        </label>

        {(others.length > 0 || crm.length > 0) && (
          <div className="rounded-2xl border border-amber-200 bg-amber-50/70 p-3">
            <div className="text-[12px] font-extrabold text-amber-900">Bu adla kayıt var</div>
            <ul className="mt-1.5 space-y-1.5">
              {others.map((c) => (
                <li key={c.id} className="flex flex-wrap items-center justify-between gap-2">
                  <span className="min-w-0 break-words font-semibold">
                    {c.name} <Pill tone="muted">{c.archived ? 'Arşivde' : c.stageLabel}</Pill>
                  </span>
                  <button type="button" className={`${btnGhost} !min-h-9 !py-1`} onClick={() => onOpenExisting(c.id)}>
                    Kartı aç
                  </button>
                </li>
              ))}
              {crm.map((c) => (
                <li key={c.crmContactId} className="flex flex-wrap items-center justify-between gap-2">
                  <span className="min-w-0 break-words font-semibold">
                    {c.name} <Pill tone={c.author ? 'violet' : 'muted'}>{c.author ? 'CRM yazarı' : 'CRM kişisi'}</Pill>
                  </span>
                  {c.cardId ? (
                    <button type="button" className={`${btnGhost} !min-h-9 !py-1`} onClick={() => onOpenExisting(c.cardId as string)}>
                      Kartı aç
                    </button>
                  ) : (
                    <button
                      type="button"
                      className={`${btnGhost} !min-h-9 !py-1`}
                      onClick={() => setF((p) => ({ ...p, crmContactId: c.crmContactId, crmName: c.name, name: c.name || p.name, stage: c.author ? 'yazar' : p.stage }))}
                    >
                      <Link2 aria-hidden className="h-3.5 w-3.5" />
                      Bu kişiye bağla
                    </button>
                  )}
                </li>
              ))}
            </ul>
            {(similar.data?.crmTotal ?? 0) > crm.length + (f.crmContactId ? 1 : 0) && (
              <p className="mt-1.5 text-[11px] text-amber-900">
                CRM'de bu adla {similar.data?.crmTotal} kişi var
                <SqlInfo k={similar.data?.kaynaklar} alan="crmTotal" label="Aynı adlı CRM kişisi" className="ml-0.5" />; ilk {similar.data?.crm.length} tanesi
                gösteriliyor. Adı tam yazın.
              </p>
            )}
            {similar.data?.crmError && <p className="mt-1.5 text-[11px] text-amber-900">CRM şu an okunamadı; yalnız portal kartlarına bakıldı.</p>}
          </div>
        )}

        {f.crmContactId && (
          <Note tone="info">
            CRM kişisine bağlı: <b>{f.crmName}</b>.{' '}
            <button type="button" className="font-extrabold text-canvas-violet underline" onClick={() => setF((p) => ({ ...p, crmContactId: null, crmName: null }))}>
              Bağı kaldır
            </button>
          </Note>
        )}

        <div className="grid gap-2 sm:grid-cols-2">
          <label className="block">
            <span className={label}>Aşama</span>
            <select value={f.stage} onChange={(e) => set('stage', e.target.value)} className={`${field} mt-1`}>
              {stages.map((s) => (
                <option key={s.key} value={s.key}>
                  {s.label}
                </option>
              ))}
            </select>
          </label>
          <label className="block">
            <span className={label}>Alan / tür</span>
            <input maxLength={200} value={f.genre} onChange={(e) => set('genre', e.target.value)} placeholder="ör. Tarih, çocuk kitabı, deneme" className={`${field} mt-1`} />
          </label>
          <label className="block">
            <span className={label}>Nereden bulundu</span>
            <select value={f.source} onChange={(e) => set('source', e.target.value)} className={`${field} mt-1`}>
              <option value="">Belirtilmedi</option>
              {(meta.data?.sources ?? []).map((s) => (
                <option key={s.key} value={s.key}>
                  {s.label}
                </option>
              ))}
            </select>
          </label>
          <label className="block">
            <span className={label}>Kaynak notu</span>
            <input maxLength={300} value={f.sourceNote} onChange={(e) => set('sourceNote', e.target.value)} placeholder="ör. Kim önerdi, hangi etkinlik" className={`${field} mt-1`} />
          </label>
        </div>

        <div>
          <span className={label}>Sorumlu editör</span>
          <SearchSelect label="Sorumlu editör" placeholder="Seçilmedi" options={people.options} value={f.owner} onChange={(v) => set('owner', v)} className="mt-1" />
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

        <label className="block">
          <span className={label}>Bağlantılar (her satıra bir adres)</span>
          <textarea rows={2} value={f.links} onChange={(e) => set('links', e.target.value)} placeholder="https://…" className={`${field} mt-1 resize-y`} />
        </label>
        <label className="block">
          <span className={label}>Etiketler (virgülle)</span>
          <input value={f.tags} onChange={(e) => set('tags', e.target.value)} placeholder="ör. akademisyen, ilk kitap, dizi" className={`${field} mt-1`} />
        </label>
        <label className="block">
          <span className={label}>Kısa not</span>
          <textarea rows={4} maxLength={4000} value={f.bio} onChange={(e) => set('bio', e.target.value)} placeholder="Kim, ne yazıyor, neden ilgileniyoruz" className={`${field} mt-1 resize-y leading-snug`} />
        </label>

        {err && <Note tone="err">{err}</Note>}

        <div className="flex justify-end gap-2 pt-1">
          <button type="button" className={btnGhost} onClick={onClose} disabled={save.isPending}>
            Vazgeç
          </button>
          <button type="submit" className={btnPrimary} disabled={save.isPending || !f.name.trim()}>
            {save.isPending ? 'Kaydediliyor…' : card ? 'Kaydet' : 'Kartı aç'}
          </button>
        </div>
      </form>
    </Sheet>
  );
}
