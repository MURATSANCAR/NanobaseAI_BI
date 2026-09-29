import { useEffect, useMemo, useState, type ReactNode } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Link2, X } from 'lucide-react';
import { ENGINE_ENABLED, authorsApi } from '../../engine';
import { Note, Pill, btnGhost, btnPrimary, field, label } from '../../admin/ui';
import Sheet from '../studio/reader/Sheet';
import SearchSelect from '../../components/SearchSelect';
import { useDebounced } from '../kit';
import { nowLocal } from '../authors/shared';
import { applicationsApi, type AppDetail, type AppInput } from './api';
import { errMsg, invalidateApps, useAppMeta, useCategories } from './shared';
import { FileDrop } from '../../components/FileDrop';
import { MB, titleFromFilename } from '../../components/fileDropRules';

/** Yeni başvuru ve başvuru bilgilerini düzeltme. İş tanımındaki başvuru dosyası: yazar/ajans bilgisi ve biyografi,
 *  eser özeti, hedef kitle, sayfa tahmini, seri bilgisi ve yayınevi notu. Yazar adı yazılırken CRM'deki aynı adlı
 *  kişiler gösterilir; seçilirse kurul raporuna yazarın CRM geçmişi girer. */

type Form = {
  title: string;
  authorName: string;
  authorEmail: string;
  authorPhone: string;
  agencyName: string;
  agencyContact: string;
  authorBio: string;
  authorExpertise: string;
  authorHistory: string;
  crmContactId: string | null;
  crmName: string | null;
  summary: string;
  audience: string;
  ageFrom: string;
  ageTo: string;
  pageEstimate: string;
  genre: string;
  categoryId: string;
  series: string;
  publisherNote: string;
  channel: string;
  receivedOn: string;
};

const empty = (): Form => ({
  title: '', authorName: '', authorEmail: '', authorPhone: '', agencyName: '', agencyContact: '', authorBio: '',
  authorExpertise: '', authorHistory: '', crmContactId: null, crmName: null, summary: '', audience: '', ageFrom: '',
  ageTo: '', pageEstimate: '', genre: '', categoryId: '', series: '', publisherNote: '', channel: 'eposta',
  receivedOn: nowLocal().date,
});

const fromApp = (a: AppDetail): Form => ({
  title: a.title, authorName: a.authorName, authorEmail: a.authorEmail ?? '', authorPhone: a.authorPhone ?? '',
  agencyName: a.agencyName ?? '', agencyContact: a.agencyContact ?? '', authorBio: a.authorBio ?? '',
  authorExpertise: a.authorExpertise ?? '', authorHistory: a.authorHistory ?? '', crmContactId: a.crmContactId,
  crmName: a.crmContactId ? a.authorName : null, summary: a.summary, audience: a.audience ?? '',
  ageFrom: a.ageFrom == null ? '' : String(a.ageFrom), ageTo: a.ageTo == null ? '' : String(a.ageTo),
  pageEstimate: String(a.pageEstimate), genre: a.genre ?? '', categoryId: a.categoryId ?? '', series: a.series ?? '',
  publisherNote: a.publisherNote ?? '', channel: a.channel, receivedOn: a.receivedOn,
});

function Field({ title, required, children, hint }: { title: string; required?: boolean; children: ReactNode; hint?: string }) {
  return (
    <label className="block">
      <span className={label}>
        {title}
        {required && <span className="text-red-700"> *</span>}
      </span>
      <span className="mt-1 block">{children}</span>
      {hint && <span className="mt-0.5 block text-[11px] leading-snug text-canvas-muted">{hint}</span>}
    </label>
  );
}

function Group({ title, children }: { title: string; children: ReactNode }) {
  return (
    <fieldset className="space-y-3 rounded-2xl border border-slate-100 bg-white/70 p-3">
      <legend className="px-1 text-[12.5px] font-extrabold">{title}</legend>
      {children}
    </fieldset>
  );
}

export default function ApplicationForm({
  open,
  onClose,
  app,
  onSaved,
  initialFile,
}: {
  open: boolean;
  onClose: () => void;
  /** Başvuru listesinin üstündeki alana bırakılan eser dosyası: form bu dosya ekli ve eser adı dosya adından dolu açılır. */
  initialFile?: File | null;
  /** Düzenlenen başvuru; yoksa yeni başvuru. */
  app?: AppDetail | null;
  onSaved: (a: AppDetail) => void;
}) {
  const qc = useQueryClient();
  const meta = useAppMeta();
  const cats = useCategories(open);
  const [f, setF] = useState<Form>(() => (app ? fromApp(app) : empty()));
  const [files, setFiles] = useState<File[]>([]);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (open) {
      setF(app ? fromApp(app) : initialFile ? { ...empty(), title: titleFromFilename(initialFile.name) } : empty());
      setFiles(!app && initialFile ? [initialFile] : []);
      setErr(null);
    }
  }, [open, app, initialFile]);

  const set = <K extends keyof Form>(k: K, v: Form[K]) => setF((p) => ({ ...p, [k]: v }));
  const name = useDebounced(f.authorName.trim(), 400);
  const similar = useQuery({
    queryKey: ['applications', 'author-similar', name],
    queryFn: () => authorsApi.similar(name),
    enabled: ENGINE_ENABLED && open && name.length >= 3 && !f.crmContactId,
    staleTime: 60_000,
  });
  const crm = (similar.data?.crm ?? []).slice();
  const catOptions = useMemo(
    () => (cats.data?.items ?? []).map((c) => ({ value: c.id, label: c.name })),
    [cats.data],
  );
  const catName = (cats.data?.items ?? []).find((c) => c.id === f.categoryId)?.name ?? app?.categoryName ?? null;

  const save = useMutation({
    mutationFn: async () => {
      const body: AppInput = {
        title: f.title, authorName: f.authorName, authorEmail: f.authorEmail, authorPhone: f.authorPhone,
        agencyName: f.agencyName, agencyContact: f.agencyContact, authorBio: f.authorBio, authorExpertise: f.authorExpertise,
        authorHistory: f.authorHistory, crmContactId: f.crmContactId, summary: f.summary, audience: f.audience,
        ageFrom: f.ageFrom, ageTo: f.ageTo, pageEstimate: f.pageEstimate, genre: f.genre,
        categoryId: f.categoryId || null, categoryName: f.categoryId ? catName : null, series: f.series,
        publisherNote: f.publisherNote, channel: f.channel, receivedOn: f.receivedOn,
      };
      const saved = app ? await applicationsApi.update(app.id, body) : await applicationsApi.create(body);
      const failed: string[] = [];
      for (const file of files) {
        try {
          await applicationsApi.upload(saved.id, 'dosya', file);
        } catch (e) {
          failed.push(`${file.name}: ${errMsg(e, 'yüklenemedi')}`);
        }
      }
      return { saved, failed };
    },
    onSuccess: async ({ saved, failed }) => {
      await invalidateApps(qc);
      toast.success(app ? 'Başvuru güncellendi' : `Başvuru kaydedildi · ${saved.no}`, { description: saved.title });
      if (failed.length) toast.error('Bazı dosyalar yüklenemedi', { description: failed.join('\n') });
      onSaved(saved);
    },
    onError: (e) => setErr(errMsg(e)),
  });

  const max = meta.data?.fileMaxMb ?? 10;

  return (
    <Sheet open={open} onClose={onClose} modal wide title={app ? 'Başvuruyu düzenle' : 'Yeni başvuru'} subtitle={app ? `${app.no} · ${app.title}` : 'Yazar ya da ajanstan gelen yeni kitap dosyası'}>
      <form
        className="space-y-3 text-[12.5px]"
        onSubmit={(e) => {
          e.preventDefault();
          setErr(null);
          save.mutate();
        }}
      >
        <Group title="Eser">
          <Field title="Eser adı" required>
            <input required maxLength={300} value={f.title} onChange={(e) => set('title', e.target.value)} autoFocus={!app} className={field} />
          </Field>
          <Field title="Eser özeti" required hint="Konu, yaklaşım, bölümler; kurul raporuna olduğu gibi girer.">
            <textarea required rows={5} maxLength={20000} value={f.summary} onChange={(e) => set('summary', e.target.value)} className={field} />
          </Field>
          <div className="grid gap-3 sm:grid-cols-2">
            <Field title="Hedef kitle">
              <select value={f.audience} onChange={(e) => set('audience', e.target.value)} className={field}>
                <option value="">Seçilmedi</option>
                {(meta.data?.audiences ?? []).map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </select>
            </Field>
            <div className="grid grid-cols-2 gap-2">
              <Field title="Yaş (en az)">
                <input inputMode="numeric" value={f.ageFrom} onChange={(e) => set('ageFrom', e.target.value.replace(/\D/g, ''))} placeholder="Ör. 8" className={field} />
              </Field>
              <Field title="Yaş (en çok)">
                <input inputMode="numeric" value={f.ageTo} onChange={(e) => set('ageTo', e.target.value.replace(/\D/g, ''))} placeholder="Ör. 12" className={field} />
              </Field>
            </div>
            <Field title="Sayfa tahmini" required>
              <input required inputMode="numeric" value={f.pageEstimate} onChange={(e) => set('pageEstimate', e.target.value.replace(/\D/g, ''))} placeholder="Ör. 240" className={field} />
            </Field>
            <Field title="Tür" hint="Roman, inceleme, biyografi, etkinlik…">
              <input maxLength={120} value={f.genre} onChange={(e) => set('genre', e.target.value)} className={field} />
            </Field>
          </div>
          <Field title="Kategori (CRM'deki kitaplık)" hint="Kurul raporundaki benzer kitap satışları ve baskı önerisi bu kategoriden hesaplanır.">
            <SearchSelect
              label="Kategori"
              placeholder={cats.isLoading ? 'CRM okunuyor…' : 'Seçilmedi'}
              options={catOptions}
              value={f.categoryId}
              onChange={(v) => set('categoryId', v)}
            />
          </Field>
          {cats.error && <Note tone="warn">{errMsg(cats.error, 'Kategoriler CRM\'den okunamadı.')}</Note>}
          <div className="grid gap-3 sm:grid-cols-2">
            <Field title="Seri bilgisi">
              <input maxLength={300} value={f.series} onChange={(e) => set('series', e.target.value)} placeholder="Ör. dizinin adı ve kaçıncı kitap olduğu" className={field} />
            </Field>
            <Field title="Geliş kanalı">
              <select value={f.channel} onChange={(e) => set('channel', e.target.value)} className={field}>
                {(meta.data?.channels ?? []).map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </select>
            </Field>
            <Field title="Geliş tarihi" required>
              <input required type="date" value={f.receivedOn} max={nowLocal().date} onChange={(e) => set('receivedOn', e.target.value)} className={field} />
            </Field>
          </div>
          <Field title="Yayınevi notu" hint="Dosyayı getirenin ya da yayın yönetmeninin notu.">
            <textarea rows={2} maxLength={8000} value={f.publisherNote} onChange={(e) => set('publisherNote', e.target.value)} className={field} />
          </Field>
        </Group>

        <Group title="Yazar ve ajans">
          <div className="grid gap-3 sm:grid-cols-2">
            <Field title="Yazar adı" required>
              <input required maxLength={200} value={f.authorName} onChange={(e) => set('authorName', e.target.value)} className={field} />
            </Field>
            <Field title="E-posta">
              <input type="email" maxLength={200} value={f.authorEmail} onChange={(e) => set('authorEmail', e.target.value)} className={field} />
            </Field>
            <Field title="Telefon">
              <input type="tel" maxLength={60} value={f.authorPhone} onChange={(e) => set('authorPhone', e.target.value)} className={field} />
            </Field>
            <Field title="Ajans / temsilci">
              <input maxLength={200} value={f.agencyName} onChange={(e) => set('agencyName', e.target.value)} className={field} />
            </Field>
          </div>
          {f.agencyName && (
            <Field title="Ajans iletişim">
              <input maxLength={200} value={f.agencyContact} onChange={(e) => set('agencyContact', e.target.value)} className={field} />
            </Field>
          )}
          {f.crmContactId ? (
            <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl bg-canvas-violet/5 px-3 py-2">
              <span className="min-w-0 break-words">
                <Link2 aria-hidden className="mr-1 inline h-3.5 w-3.5 text-canvas-violet" />
                CRM kişisine bağlı: <b>{f.crmName ?? f.authorName}</b>
              </span>
              <button type="button" className={`${btnGhost} !min-h-9 !py-1`} onClick={() => setF((p) => ({ ...p, crmContactId: null, crmName: null }))}>
                <X aria-hidden className="h-4 w-4" />
                Bağı kaldır
              </button>
            </div>
          ) : (
            crm.length > 0 && (
              <div className="rounded-2xl border border-amber-200 bg-amber-50/70 p-3">
                <div className="text-[12px] font-extrabold text-amber-900">CRM'de bu adla kişi var</div>
                <p className="text-[11.5px] text-amber-900/80">Aynı kişiyse bağlayın: kurul raporuna yazarın eserleri ve sözleşmeleri girer.</p>
                <ul className="mt-1.5 space-y-1.5">
                  {crm.map((c) => (
                    <li key={c.crmContactId} className="flex flex-wrap items-center justify-between gap-2">
                      <span className="min-w-0 break-words font-semibold">
                        {c.name} <Pill tone={c.author ? 'violet' : 'muted'}>{c.author ? 'CRM yazarı' : 'CRM kişisi'}</Pill>
                      </span>
                      <button type="button" className={`${btnGhost} !min-h-9 !py-1`} onClick={() => setF((p) => ({ ...p, crmContactId: c.crmContactId, crmName: c.name }))}>
                        Bu kişiye bağla
                      </button>
                    </li>
                  ))}
                </ul>
                {similar.data && similar.data.crmTotal > crm.length && (
                  <p className="mt-1 text-[11px] text-amber-900/80">CRM'de bu adla {similar.data.crmTotal} kişi var; ad soyadı tam yazın.</p>
                )}
              </div>
            )
          )}
          <Field title="Biyografi" required>
            <textarea required rows={4} maxLength={8000} value={f.authorBio} onChange={(e) => set('authorBio', e.target.value)} className={field} />
          </Field>
          <Field title="Uzmanlık">
            <textarea rows={2} maxLength={4000} value={f.authorExpertise} onChange={(e) => set('authorExpertise', e.target.value)} className={field} />
          </Field>
          <Field title="Yayıncılık geçmişi" hint="Önceki kitapları, yayınevleri, ödüller.">
            <textarea rows={2} maxLength={8000} value={f.authorHistory} onChange={(e) => set('authorHistory', e.target.value)} className={field} />
          </Field>
        </Group>

        {!app && (
          <Group title="Dosyalar">
            <Field title="Eser dosyası" hint="Sonradan başvuru sayfasından da eklenir.">
              <FileDrop
                size="sm"
                multiple
                title="Eser dosyalarını ekle"
                accept=".pdf,.docx,.doc"
                maxBytes={max * MB}
                onPick={(f) => setFiles((xs) => (xs.some((x) => x.name === f.name && x.size === f.size) ? xs : [...xs, f]))}
              />
            </Field>
            {files.length > 0 && (
              <ul className="flex flex-col gap-1 text-[12px]">
                {files.map((x) => (
                  <li key={`${x.name}-${x.size}`} className="flex items-center justify-between gap-2 rounded-xl bg-white/80 px-3 py-1.5">
                    <span className="min-w-0 truncate font-semibold">{x.name}</span>
                    <button type="button" className={`${btnGhost} !min-h-9 !py-1`} aria-label={`${x.name} çıkar`} onClick={() => setFiles((xs) => xs.filter((y) => y !== x))}>
                      <X aria-hidden className="h-4 w-4" />
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </Group>
        )}

        {err && <Note tone="err">{err}</Note>}
        <div className="sticky bottom-0 -mx-4 flex flex-wrap justify-end gap-2 border-t border-slate-100 bg-white/95 px-4 py-3">
          <button type="button" className={btnGhost} onClick={onClose}>
            Vazgeç
          </button>
          <button type="submit" className={btnPrimary} disabled={save.isPending}>
            {save.isPending ? 'Kaydediliyor…' : app ? 'Kaydet' : 'Başvuruyu kaydet'}
          </button>
        </div>
      </form>
    </Sheet>
  );
}
