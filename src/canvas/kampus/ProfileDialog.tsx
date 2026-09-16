import { useCallback, useEffect, useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Camera, Loader2, Trash2, X } from 'lucide-react';
import { toast } from 'sonner';
import { peopleApi, type MyProfile, type ProfileFields } from '../engine';
import PersonAvatar from './PersonAvatar';
import './profile.css';

/**
 * Kişinin kendi profili. CRM'deki bilgiler salt okunur gelir; CRM'de olmayan dahili/kat/masa/cep/hakkımda
 * alanlarını ve fotoğrafı kişi kendisi girer, kayıt sunucudadır. CRM'de dolu bir alan rehberde her zaman önce
 * gelir; bu yüzden CRM'de dolu olan alanın altında "CRM'de: …" yazar.
 *
 * Yerel <dialog>: odak tuzağı, Esc ve arka planın erişilemez olması tarayıcıdan gelir.
 */

const CLOSE_MS = 150;
/** Fotoğraf yüklenmeden önce tarayıcıda bu kenara küçültülür (rehberde 36px, burada 80px görünür). */
const PHOTO_EDGE = 512;

const EMPTY: ProfileFields = { extension: '', floor: '', desk: '', mobile: '', about: '' };

const FIELDS: Array<{ key: keyof ProfileFields; label: string; placeholder: string; crm?: 'extension' | 'floor' | 'mobile'; inputMode?: 'tel' }> = [
  { key: 'extension', label: 'Dahili numara', placeholder: 'örn. 1045', crm: 'extension', inputMode: 'tel' },
  { key: 'floor', label: 'Kat', placeholder: 'örn. 4. Kat', crm: 'floor' },
  { key: 'desk', label: 'Masa / oda', placeholder: 'örn. E-12' },
  { key: 'mobile', label: 'Cep telefonu', placeholder: 'örn. 0532 000 00 00', crm: 'mobile', inputMode: 'tel' },
];

export const PROFILE_KEY = ['me-profile'] as const;

export function useMyProfile(enabled: boolean) {
  return useQuery({ queryKey: PROFILE_KEY, queryFn: peopleApi.me, enabled, retry: false, staleTime: 60_000 });
}

async function shrink(file: File): Promise<string> {
  const bitmap = await createImageBitmap(file).catch(() => {
    throw new Error('Bu dosya açılamadı; JPEG, PNG ya da WebP seçin.');
  });
  const scale = Math.min(1, PHOTO_EDGE / Math.max(bitmap.width, bitmap.height));
  const canvas = document.createElement('canvas');
  canvas.width = Math.round(bitmap.width * scale);
  canvas.height = Math.round(bitmap.height * scale);
  canvas.getContext('2d')!.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
  bitmap.close();
  return canvas.toDataURL('image/jpeg', 0.86);
}

export default function ProfileDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const ref = useRef<HTMLDialogElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const [closing, setClosing] = useState(false);
  const closingRef = useRef(false);
  const qc = useQueryClient();
  const profile = useMyProfile(open);
  const [form, setForm] = useState<ProfileFields>(EMPTY);
  const [preview, setPreview] = useState<string | null>(null);

  useEffect(() => {
    if (open && profile.data) setForm({ ...EMPTY, ...profile.data.fields });
  }, [open, profile.data]);

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
      setPreview(null);
      onClose();
    }, CLOSE_MS);
  }, [onClose]);

  const refresh = (data?: MyProfile) => {
    if (data) qc.setQueryData(PROFILE_KEY, data);
    else void qc.invalidateQueries({ queryKey: PROFILE_KEY });
    void qc.invalidateQueries({ queryKey: ['people'] });
  };

  const save = useMutation({
    mutationFn: () => peopleApi.save(form),
    onSuccess: (data) => {
      refresh(data);
      toast.success('Profil kaydedildi');
      close();
    },
    onError: (e) => toast.error('Profil kaydedilemedi', { description: e instanceof Error ? e.message : undefined }),
  });

  const upload = useMutation({
    mutationFn: async (file: File) => {
      const dataUrl = await shrink(file);
      setPreview(dataUrl);
      return peopleApi.savePhoto(dataUrl);
    },
    onSuccess: () => {
      refresh();
      toast.success('Fotoğraf güncellendi');
    },
    onError: (e) => {
      setPreview(null);
      toast.error('Fotoğraf yüklenemedi', { description: e instanceof Error ? e.message : undefined });
    },
  });

  const removePhoto = useMutation({
    mutationFn: peopleApi.deletePhoto,
    onSuccess: () => {
      setPreview(null);
      refresh();
    },
    onError: (e) => toast.error('Fotoğraf kaldırılamadı', { description: e instanceof Error ? e.message : undefined }),
  });

  const p = profile.data;
  const crm = p?.crm;
  const hasPhoto = Boolean(preview || p?.photoVersion);
  const busyPhoto = upload.isPending || removePhoto.isPending;

  return (
    <dialog
      ref={ref}
      className="pf-dialog w-[380px] max-w-[calc(100vw-32px)] rounded-3xl border border-slate-200/80 bg-white p-0 text-ink shadow-canvas-card"
      data-closing={closing || undefined}
      aria-labelledby="pf-title"
      onCancel={(e) => {
        e.preventDefault();
        close();
      }}
      onClick={(e) => {
        if (e.target === e.currentTarget) close();
      }}
    >
      <div className="flex max-h-[calc(100dvh-88px)] flex-col">
        <div className="flex items-center justify-between border-b border-slate-200/70 px-5 py-3">
          <h2 id="pf-title" className="kp-display text-sm font-bold">
            Profilim
          </h2>
          <button type="button" onClick={close} aria-label="Kapat" className="kp-press flex h-11 w-11 items-center justify-center rounded-xl text-muted hover:bg-slate-100 hover:text-ink sm:h-8 sm:w-8">
            <X className="h-4 w-4" />
          </button>
        </div>

        {profile.isLoading && (
          <div className="flex items-center justify-center gap-2 py-12 text-xs text-muted">
            <Loader2 className="h-4 w-4 animate-spin" /> Yükleniyor…
          </div>
        )}
        {profile.error && !p && (
          <p className="px-5 py-8 text-center text-xs text-rose-700">
            Profil okunamadı. {profile.error instanceof Error ? profile.error.message : ''}
          </p>
        )}

        {p && (
          <form
            className="flex min-h-0 flex-1 flex-col"
            onSubmit={(e) => {
              e.preventDefault();
              save.mutate();
            }}
          >
            <div className="kp-scroll min-h-0 flex-1 overflow-y-auto px-5 py-4">
              <div className="flex items-center gap-4">
                <div className="relative">
                  <PersonAvatar username={p.username} name={p.displayName} photoVersion={p.photoVersion} src={preview} className="h-20 w-20 rounded-2xl text-xl" />
                  {busyPhoto && (
                    <div className="absolute inset-0 flex items-center justify-center rounded-2xl bg-white/60">
                      <Loader2 className="h-5 w-5 animate-spin text-violet" />
                    </div>
                  )}
                </div>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-bold">{p.displayName}</p>
                  <p className="truncate text-xs text-muted">{[crm?.title, crm?.unit].filter(Boolean).join(' • ') || p.username}</p>
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    <input
                      ref={fileRef}
                      type="file"
                      accept="image/jpeg,image/png,image/webp"
                      className="hidden"
                      onChange={(e) => {
                        const f = e.target.files?.[0];
                        e.target.value = '';
                        if (f) upload.mutate(f);
                      }}
                    />
                    <button
                      type="button"
                      disabled={busyPhoto}
                      onClick={() => fileRef.current?.click()}
                      className="kp-press flex min-h-11 items-center gap-1.5 rounded-lg bg-violet/10 px-2.5 text-xs font-semibold text-violet hover:bg-violet/15 disabled:opacity-60 sm:min-h-8"
                    >
                      <Camera className="h-3.5 w-3.5" /> {hasPhoto ? 'Değiştir' : 'Fotoğraf ekle'}
                    </button>
                    {hasPhoto && (
                      <button
                        type="button"
                        disabled={busyPhoto}
                        onClick={() => removePhoto.mutate()}
                        className="kp-press flex min-h-11 items-center gap-1.5 rounded-lg px-2.5 text-xs font-medium text-muted hover:bg-slate-100 hover:text-rose-700 disabled:opacity-60 sm:min-h-8"
                      >
                        <Trash2 className="h-3.5 w-3.5" /> Kaldır
                      </button>
                    )}
                  </div>
                </div>
              </div>

              <dl className="mt-4 grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 rounded-xl border border-slate-200/70 bg-slate-50/80 p-3 text-xs">
                <dt className="text-muted">Hesap</dt>
                <dd className="truncate font-medium">{p.username}</dd>
                <dt className="text-muted">E-posta</dt>
                <dd className="truncate font-medium">{crm?.email || '—'}</dd>
                <dt className="text-muted">Unvan</dt>
                <dd className="truncate font-medium">{crm?.title || '—'}</dd>
                <dt className="text-muted">Birim</dt>
                <dd className="truncate font-medium">{crm?.unit || '—'}</dd>
              </dl>
              <p className="mt-1.5 text-[11px] text-muted">
                {p.inCrm ? 'Bu bilgiler CRM ve dizinden gelir; değişiklik için BT’ye başvurun.' : 'Hesabınız CRM kullanıcı listesinde bulunamadı.'}
              </p>

              <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2">
                {FIELDS.map((f) => {
                  const fromCrm = f.crm ? crm?.[f.crm] : '';
                  // Rehberde CRM değeri gösterilir; kişinin yazdığı yalnız CRM boşken görünür.
                  const shadowed = Boolean(fromCrm && fromCrm !== form[f.key]);
                  return (
                    <label key={f.key} className="flex flex-col gap-1 text-xs">
                      <span className="font-semibold text-ink/80">{f.label}</span>
                      <input
                        value={form[f.key]}
                        inputMode={f.inputMode}
                        placeholder={fromCrm || f.placeholder}
                        onChange={(e) => setForm((s) => ({ ...s, [f.key]: e.target.value }))}
                        className="rounded-xl border border-slate-200/70 bg-white px-3 py-2 text-base text-ink placeholder:text-muted/70 focus:border-violet focus:outline-none focus:ring-2 focus:ring-violet/25 sm:text-xs"
                      />
                      {shadowed && <span className="text-[11px] text-muted">Rehberde CRM/dizindeki değer görünür: {fromCrm}</span>}
                    </label>
                  );
                })}
              </div>
              <label className="mt-3 flex flex-col gap-1 text-xs">
                <span className="font-semibold text-ink/80">Hakkımda</span>
                <textarea
                  value={form.about}
                  rows={3}
                  maxLength={400}
                  placeholder="Ne üzerinde çalışıyorsunuz, size ne için ulaşılabilir?"
                  onChange={(e) => setForm((s) => ({ ...s, about: e.target.value }))}
                  className="resize-none rounded-xl border border-slate-200/70 bg-white px-3 py-2 text-base text-ink placeholder:text-muted/70 focus:border-violet focus:outline-none focus:ring-2 focus:ring-violet/25 sm:text-xs"
                />
              </label>
            </div>

            <div className="flex items-center justify-end gap-2 border-t border-slate-200/70 px-5 py-3">
              <button type="button" onClick={close} className="kp-press min-h-11 rounded-xl px-3 text-xs font-medium text-muted hover:bg-slate-100 sm:min-h-9">
                Vazgeç
              </button>
              <button
                type="submit"
                disabled={save.isPending}
                className="kp-press flex min-h-11 items-center gap-1.5 rounded-xl bg-violet px-4 text-xs font-bold text-white hover:bg-violet/90 disabled:opacity-60 sm:min-h-9"
              >
                {save.isPending && <Loader2 className="h-3.5 w-3.5 animate-spin" />} Kaydet
              </button>
            </div>
          </form>
        )}
      </div>
    </dialog>
  );
}
