import { useEffect, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Plus, Trash2, Upload } from 'lucide-react';
import { ENGINE_ENABLED } from '../../engine';
import { Loading, Note, btnGhost, btnPrimary, errText, field, label } from '../../admin/ui';
import { Panel } from '../../editorial/kit';
import { creativeApi, fmtDay, type Banned } from './api';

/** Marka kiti (sürümlü): palet (kitapsız işlerde zemin rengi seçeneklerinin başına eklenir), logo ve yazı tipi
 *  dosyaları (yazı tipinde sunucuda kullanım lisansı notu zorunlu), marka kuralları (Zeki AI metin istemine girer)
 *  ve yasaklı kalıp listesi (metin denetiminde uyarı). Düzenleme `icerik.marka` ister. */

export default function BrandKit({ canEdit }: { canEdit: boolean }) {
  const qc = useQueryClient();
  const brand = useQuery({ queryKey: ['creative', 'brand'], queryFn: creativeApi.brand, enabled: ENGINE_ENABLED });
  const banned = useQuery({ queryKey: ['creative', 'banned'], queryFn: creativeApi.banned, enabled: ENGINE_ENABLED });
  const [palet, setPalet] = useState<string[]>([]);
  const [rules, setRules] = useState('');
  const [color, setColor] = useState('#1F3B73');
  const [phrases, setPhrases] = useState<Array<Pick<Banned, 'kalip' | 'aciklama'>>>([]);
  const [fontLicense, setFontLicense] = useState('');
  useEffect(() => { if (brand.data) { setPalet(brand.data.palet); setRules(brand.data.kurallar); } }, [brand.data]);
  useEffect(() => { if (banned.data) setPhrases(banned.data.items.map(({ kalip, aciklama }) => ({ kalip, aciklama }))); }, [banned.data]);

  const done = (msg: string) => { toast.success(msg); return qc.invalidateQueries({ queryKey: ['creative'] }); };
  const save = useMutation({ mutationFn: () => creativeApi.saveBrand({ palet, kurallar: rules }), onSuccess: () => done('Marka kiti kaydedildi (yeni sürüm).') });
  const upload = useMutation({
    mutationFn: (x: { tur: 'logo' | 'font'; f: File }) => creativeApi.uploadBrandFile(x.tur, x.f, x.tur === 'font' ? fontLicense : ''),
    onSuccess: () => done('Dosya yüklendi.'),
  });
  const removeFile = useMutation({
    mutationFn: (id: string) => creativeApi.saveBrand({
      logolar: (brand.data?.logolar ?? []).filter((x) => x.id !== id), yaziTipleri: (brand.data?.yaziTipleri ?? []).filter((x) => x.id !== id),
    }),
    onSuccess: () => done('Dosya kitten çıkarıldı.'),
  });
  const saveBanned = useMutation({ mutationFn: () => creativeApi.saveBanned(phrases.filter((p) => p.kalip.trim())), onSuccess: () => done('Yasaklı kalıp listesi kaydedildi.') });
  const b = brand.data;
  const err = errText(brand.error || banned.error || save.error || upload.error || removeFile.error || saveBanned.error, 'İşlem yapılamadı.');

  return (
    <div className="grid min-w-0 gap-3 lg:grid-cols-2 lg:gap-4">
      <Panel>
        <div className="flex flex-col gap-3">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <h2 className="text-[16px] font-extrabold">Marka kiti</h2>
            {b && b.surum > 0 && <span className="text-[11.5px] text-canvas-muted">Sürüm {b.surum} · {b.yukleyen} · {fmtDay(b.zaman)}</span>}
          </div>
          {brand.isLoading && <Loading />}
          {err && <Note tone="err">{err}</Note>}
          {!canEdit && <Note tone="info">Marka kitini görüntülüyorsunuz; düzenleme rolünüzde yok.</Note>}

          <div className="flex flex-col gap-1.5">
            <span className={label}>Palet</span>
            <div className="flex flex-wrap items-center gap-2">
              {palet.map((c) => (
                <span key={c} className="inline-flex items-center gap-1 rounded-full border border-slate-200 bg-white py-1 pl-1 pr-2 text-[11.5px] font-mono">
                  <span className="h-6 w-6 rounded-full border border-black/10" style={{ background: c }} aria-hidden />{c}
                  {canEdit && <button type="button" aria-label={`${c} rengini çıkar`} className="ml-0.5 inline-flex h-7 w-7 items-center justify-center rounded-full hover:bg-slate-100"
                    onClick={() => setPalet((o) => o.filter((x) => x !== c))}><Trash2 className="h-3.5 w-3.5" aria-hidden /></button>}
                </span>
              ))}
              {palet.length === 0 && <span className="text-[12px] text-canvas-muted">Palet boş; kapaktan çıkan renkler kullanılır.</span>}
            </div>
            {canEdit && (
              <div className="flex flex-wrap items-center gap-2">
                <input type="color" aria-label="Renk seç" value={color} onChange={(e) => setColor(e.target.value.toUpperCase())} className="h-10 w-14 cursor-pointer rounded-lg border border-slate-200 bg-white" />
                <input className={`${field} w-32 font-mono`} value={color} onChange={(e) => setColor(e.target.value.toUpperCase())} maxLength={7} aria-label="Renk kodu" />
                <button type="button" className={btnGhost} disabled={!/^#[0-9A-F]{6}$/.test(color) || palet.includes(color)} onClick={() => setPalet((o) => [...o, color])}>
                  <Plus className="h-4 w-4" aria-hidden />Ekle
                </button>
              </div>
            )}
          </div>

          <label className="flex flex-col gap-1.5">
            <span className={label}>Marka kuralları (Zeki AI metin yazarken uyar)</span>
            <textarea className={field} rows={6} value={rules} onChange={(e) => setRules(e.target.value)} readOnly={!canEdit} maxLength={8000}
              placeholder="Ör. «Timaş» adı her zaman bu yazımla; ünlem en çok bir; çocuk kitaplarında sen diliyle…" />
          </label>
          {canEdit && (
            <div className="flex justify-end">
              <button type="button" className={btnPrimary} disabled={save.isPending} onClick={() => save.mutate()}>Paleti ve kuralları kaydet</button>
            </div>
          )}

          <div className="flex flex-col gap-1.5">
            <span className={label}>Logolar</span>
            <ul className="flex flex-col gap-1">
              {b?.logolar.map((f) => (
                <li key={f.id} className="flex items-center justify-between gap-2 rounded-xl bg-white/80 px-3 py-2 text-[12.5px]">
                  <a className="min-w-0 truncate font-semibold hover:underline" href={creativeApi.brandFileUrl(f.id)}>{f.ad}</a>
                  {canEdit && <button type="button" className={btnGhost} aria-label={`${f.ad} çıkar`} onClick={() => removeFile.mutate(f.id)}><Trash2 className="h-4 w-4" aria-hidden /></button>}
                </li>
              ))}
              {b && b.logolar.length === 0 && <li className="text-[12px] text-canvas-muted">Logo yüklenmedi.</li>}
            </ul>
            {canEdit && (
              <label className={`${btnGhost} cursor-pointer self-start`}>
                <Upload className="h-4 w-4" aria-hidden />Logo yükle (PNG, SVG, JPEG, WebP)
                <input type="file" className="sr-only" accept=".png,.svg,.jpg,.jpeg,.webp"
                  onChange={(e) => { const f = e.target.files?.[0]; if (f) upload.mutate({ tur: 'logo', f }); e.target.value = ''; }} />
              </label>
            )}
          </div>

          <div className="flex flex-col gap-1.5">
            <span className={label}>Yazı tipleri</span>
            <ul className="flex flex-col gap-1">
              {b?.yaziTipleri.map((f) => (
                <li key={f.id} className="flex items-center justify-between gap-2 rounded-xl bg-white/80 px-3 py-2 text-[12.5px]">
                  <span className="min-w-0"><span className="block truncate font-semibold">{f.ad}</span><span className="block truncate text-[11px] text-canvas-muted">Lisans: {f.lisans}</span></span>
                  {canEdit && <button type="button" className={btnGhost} aria-label={`${f.ad} çıkar`} onClick={() => removeFile.mutate(f.id)}><Trash2 className="h-4 w-4" aria-hidden /></button>}
                </li>
              ))}
              {b && b.yaziTipleri.length === 0 && <li className="text-[12px] text-canvas-muted">Kurum yazı tipi yüklenmedi; dizimde stüdyonun açık lisanslı yazı tipleri kullanılır.</li>}
            </ul>
            {canEdit && (
              <div className="flex flex-col gap-1.5">
                <input className={field} value={fontLicense} onChange={(e) => setFontLicense(e.target.value)} maxLength={400}
                  placeholder="Lisans notu (zorunlu): sunucuda kullanım izni, kaynak, sözleşme" />
                <label className={`${btnGhost} self-start ${fontLicense.trim() ? 'cursor-pointer' : 'pointer-events-none opacity-50'}`}>
                  <Upload className="h-4 w-4" aria-hidden />Yazı tipi yükle (TTF, OTF, WOFF)
                  <input type="file" className="sr-only" accept=".ttf,.otf,.woff,.woff2" disabled={!fontLicense.trim()}
                    onChange={(e) => { const f = e.target.files?.[0]; if (f) upload.mutate({ tur: 'font', f }); e.target.value = ''; }} />
                </label>
              </div>
            )}
          </div>
        </div>
      </Panel>

      <Panel>
        <div className="flex flex-col gap-3">
          <h2 className="text-[16px] font-extrabold">Yasaklı kalıplar</h2>
          <p className="text-[12px] leading-snug text-canvas-muted">
            Metinde geçerse varyant «uyarı» alır, onaycı karar verir. Büyük/küçük harf ve Türkçe harf farkı gözetilmez; «re:» ile başlayan kalıp düzenli ifadedir.
          </p>
          <ul className="flex flex-col gap-1.5">
            {phrases.map((p, i) => (
              <li key={i} className="grid grid-cols-[minmax(0,1fr)_auto] gap-1.5 sm:grid-cols-[minmax(0,1fr)_minmax(0,1.3fr)_auto]">
                <input className={field} value={p.kalip} readOnly={!canEdit} aria-label="Kalıp" maxLength={200}
                  onChange={(e) => setPhrases((o) => o.map((x, j) => (j === i ? { ...x, kalip: e.target.value } : x)))} />
                <input className={`${field} col-span-2 row-start-2 sm:col-span-1 sm:row-start-auto`} value={p.aciklama ?? ''} readOnly={!canEdit} aria-label="Açıklama" maxLength={400}
                  placeholder="Neden" onChange={(e) => setPhrases((o) => o.map((x, j) => (j === i ? { ...x, aciklama: e.target.value } : x)))} />
                {canEdit && <button type="button" className={`${btnGhost} col-start-2 row-start-1 sm:col-start-auto`} aria-label="Kalıbı sil"
                  onClick={() => setPhrases((o) => o.filter((_, j) => j !== i))}><Trash2 className="h-4 w-4" aria-hidden /></button>}
              </li>
            ))}
            {phrases.length === 0 && <li className="text-[12px] text-canvas-muted">Liste boş.</li>}
          </ul>
          {canEdit && (
            <div className="flex flex-wrap justify-between gap-2">
              <button type="button" className={btnGhost} onClick={() => setPhrases((o) => [...o, { kalip: '', aciklama: '' }])}><Plus className="h-4 w-4" aria-hidden />Kalıp ekle</button>
              <button type="button" className={btnPrimary} disabled={saveBanned.isPending} onClick={() => saveBanned.mutate()}>Listeyi kaydet</button>
            </div>
          )}
        </div>
      </Panel>
    </div>
  );
}
