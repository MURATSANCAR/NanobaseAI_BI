import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { AlertTriangle, Pencil } from 'lucide-react';
import { ENGINE_ENABLED } from '../../engine';
import { Note, btnGhost, btnPrimary, errText, field, label } from '../../admin/ui';
import { Img } from '../../editorial/studio/shared';
import { creativeApi, fmtDay, type Meta, type RequestDetail } from './api';
import { Block } from './parts';
import { Explain } from '../../components/Explain';
import { invalidateCreative } from './useMeta';
import { FileDrop } from '../../components/FileDrop';
import { MB } from '../../components/fileDropRules';

/** Sol sütun: brief (talep alanları), kitabın CRM metinleri ve kapak. CRM yalnız okunur; kapak dosyası portalda saklanır. */

const KAPAK_KAYNAK: Record<string, string> = { yukleme: 'yüklenen dosya', crm: 'CRM kapak adresi', eticaret: 'e-ticaret ürün görseli' };

function Line({ k, v }: { k: string; v: string | null | undefined }) {
  if (!v) return null;
  return (
    <div className="min-w-0">
      <div className={label}>{k}</div>
      <p className="whitespace-pre-line break-words text-[12.5px] leading-snug">{v}</p>
    </div>
  );
}

export default function BriefPanel({ r, meta }: { r: RequestDetail; meta: Meta | undefined }) {
  const qc = useQueryClient();
  const me = meta?.me;
  const [edit, setEdit] = useState(false);
  const [f, setF] = useState({ brief: '', hedefKitle: '', ton: '', gorselBasligi: '', termin: '', kampanya: '', atanan: '', etiketler: '' });
  const book = useQuery({ queryKey: ['creative', 'book', r.stokKodu], queryFn: () => creativeApi.book(r.stokKodu), enabled: ENGINE_ENABLED, staleTime: 300_000 });
  const b = book.data?.kitap;

  const save = useMutation({
    mutationFn: () => creativeApi.update(r.id, { ...f, etiketler: f.etiketler.split(',').map((x) => x.trim()).filter(Boolean) }),
    onSuccess: () => { toast.success('Talep güncellendi.'); setEdit(false); return invalidateCreative(qc); },
  });
  const upload = useMutation({
    mutationFn: (file: File) => creativeApi.uploadCover(r.id, file),
    onSuccess: () => { toast.success('Kapak yüklendi; sonraki dizimde kullanılır.'); return invalidateCreative(qc); },
  });
  const startEdit = () => {
    setF({ brief: r.brief ?? '', hedefKitle: r.hedefKitle ?? '', ton: r.ton ?? '', gorselBasligi: r.gorselBasligi ?? '',
      termin: r.termin ?? '', kampanya: r.kampanya ?? '', atanan: r.atanan ?? '', etiketler: r.etiketler.join(', ') });
    setEdit(true);
  };
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => setF((o) => ({ ...o, [k]: e.target.value }));
  const cover = r.kapak;
  const small = !!(cover?.w && cover?.h && meta && Math.min(cover.w, cover.h) < meta.kapakMinPx);
  const canEdit = !!(me?.talep || me?.uret);

  return (
    <div className="flex min-w-0 flex-col gap-3">
      <Block title="Brief" aside={
        <span className="flex items-center gap-2">
          <Explain label="Brief">Tasarımcıya ve metin yazarına verilen kısa iş tanımı: amaç, ana mesaj, ton ve vurgulanacak nokta.</Explain>
          {canEdit && !edit ? <button type="button" className={btnGhost} onClick={startEdit}><Pencil className="h-4 w-4" aria-hidden />Düzenle</button> : null}
        </span>
      }>
        {edit ? (
          <div className="flex flex-col gap-2">
            <label className="flex flex-col gap-1"><span className={label}>Brief</span><textarea className={field} rows={4} value={f.brief} onChange={set('brief')} maxLength={8000} /></label>
            <label className="flex flex-col gap-1"><span className={label}>Görsel üstü yazı</span><input className={field} value={f.gorselBasligi} onChange={set('gorselBasligi')} maxLength={300} /></label>
            <div className="grid gap-2 sm:grid-cols-2">
              <label className="flex flex-col gap-1"><span className={label}>Hedef kitle</span><input className={field} value={f.hedefKitle} onChange={set('hedefKitle')} maxLength={300} /></label>
              <label className="flex flex-col gap-1"><span className={label}>Ton</span><input className={field} value={f.ton} onChange={set('ton')} maxLength={200} /></label>
              <label className="flex flex-col gap-1"><span className={label}>Termin</span><input type="date" className={field} value={f.termin} onChange={set('termin')} /></label>
              <label className="flex flex-col gap-1"><span className={label}>Atanan (AD hesabı)</span><input className={field} value={f.atanan} onChange={set('atanan')} maxLength={120} /></label>
              <label className="flex flex-col gap-1"><span className={label}>Kampanya</span><input className={field} value={f.kampanya} onChange={set('kampanya')} maxLength={200} /></label>
              <label className="flex flex-col gap-1"><span className={label}>Etiketler</span><input className={field} value={f.etiketler} onChange={set('etiketler')} /></label>
            </div>
            {save.error && <Note tone="err">{errText(save.error, 'Kaydedilemedi.')}</Note>}
            <div className="flex justify-end gap-2">
              <button type="button" className={btnGhost} onClick={() => setEdit(false)}>Vazgeç</button>
              <button type="button" className={btnPrimary} disabled={save.isPending} onClick={() => save.mutate()}>Kaydet</button>
            </div>
          </div>
        ) : (
          <div className="flex flex-col gap-2">
            <Line k="Brief" v={r.brief || 'Brief yazılmamış.'} />
            <Line k="Görsel üstü yazı" v={r.gorselBasligi} />
            <Line k="Hedef kitle" v={r.hedefKitle} />
            <Line k="Ton" v={r.ton} />
            <Line k="Kampanya" v={r.kampanya} />
            {r.planId && (
              <div className="min-w-0">
                <div className={label}>Pazarlama planı</div>
                <Link to={`/pazarlama/plan/${encodeURIComponent(r.planId)}`} className="text-[12.5px] font-bold text-canvas-violet hover:underline">
                  {r.planId}{r.materyalTur ? ` · ${r.materyalTur} materyali` : ''}
                </Link>
              </div>
            )}
            <Line k="Etiketler" v={r.etiketler.join(', ') || null} />
            <Line k="Termin · atanan" v={`${fmtDay(r.termin)}${r.atanan ? ` · ${r.atanan}` : ''}`} />
          </div>
        )}
      </Block>

      <Block title="Kapak">
        {r.kapak?.kaynak === 'yukleme' && (
          <Img src={creativeApi.coverUrl(r.id, 360)} alt="Yüklenen kapak" fallback="kapak" className="mx-auto max-h-64 w-auto rounded-xl object-contain" />
        )}
        <p className="text-[12px] leading-snug text-canvas-muted">
          {cover?.kaynak
            ? `Kaynak: ${KAPAK_KAYNAK[cover.kaynak] ?? cover.kaynak}${cover.w ? ` · ${cover.w}×${cover.h} px` : ''}.`
            : r.studioKind === 'kitap'
              ? 'Stüdyodaki işin dizilmiş ön kapağı kullanılır.'
              : 'Sırayla yüklenen dosya, CRM kapak adresi ve e-ticaret ürün görseli denenir.'}
        </p>
        {cover?.denenen && cover.denenen.length > 0 && <Note tone="warn">Kapak bulunamadı: {cover.denenen.join('; ')}. Yüksek çözünürlüklü dosyayı yükleyin.</Note>}
        {book.data && !book.data.kapakKaynaklari.crmKokAyarli && !cover?.kaynak && r.studioKind !== 'kitap' && (
          <Note tone="info">CRM'deki kapak adresi göreli; kök adres yönetimde tanımlı değil. Kapak dosyasını yükleyin.</Note>
        )}
        {small && (
          <p className="flex items-start gap-1 text-[12px] text-amber-800">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />Kapak düşük çözünürlüklü; büyük biçimlerde bulanık görünebilir. Yüksek çözünürlüklü dosya yükleyin.
          </p>
        )}
        {r.studioKind !== 'kitap' && (
          // Yetkisizde de görünür: kilitli, gereken yetki yazılı.
          <FileDrop
            size="sm"
            title="Yüksek çözünürlüklü kapak yükle"
            accept="image/png,image/jpeg,image/webp"
            maxBytes={25 * MB}
            feature="icerik.uret"
            allowed={meta ? !!me?.uret : undefined}
            busy={upload.isPending}
            onPick={(file) => upload.mutate(file)}
          />
        )}
        {upload.error && <Note tone="err">{errText(upload.error, 'Yüklenemedi.')}</Note>}
      </Block>

      <Block title="Kitabın CRM metinleri">
        {book.isLoading && <p className="text-[12px] text-canvas-muted">Okunuyor…</p>}
        {book.error && <Note tone="err">{errText(book.error, 'CRM kitap kartı okunamadı.')}</Note>}
        {b && (
          <div className="flex flex-col gap-2">
            <Line k="Yazar · stok kodu" v={[b.yazar, b.stok_kodu, b.isbn].filter(Boolean).join(' · ')} />
            <Line k="Kitabın en önemli cümlesi" v={b.onemli_cumle} />
            <Line k="Spot" v={b.spot} />
            <Line k="Hashtag" v={b.hashtag} />
            {b.alintilar.length > 0 && (
              <div>
                <div className={label}>Alıntılar ({b.alintilar.length})</div>
                <ul className="mt-0.5 flex max-h-48 flex-col gap-1 overflow-y-auto pr-1 text-[12px] leading-snug">
                  {b.alintilar.map((q) => <li key={q}>“{q}”</li>)}
                </ul>
              </div>
            )}
            {b.ozet && (
              <details>
                <summary className="cursor-pointer text-[11px] font-bold uppercase tracking-wide text-canvas-muted">Arka kapak metni</summary>
                <p className="mt-1 whitespace-pre-line text-[12px] leading-snug">{b.ozet}</p>
              </details>
            )}
            <p className="text-[11px] text-canvas-muted">Alıntı ve sayılar yalnız bu metinlerde (stüdyo işi varsa kitabın metninde) birebir aranır; CRM'e yazılmaz.</p>
          </div>
        )}
      </Block>
    </div>
  );
}
