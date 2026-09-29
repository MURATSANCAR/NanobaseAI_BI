import { useEffect, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Check, Copy, PenLine, Sparkles, Trash2 } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import SqlInfo from '../components/SqlInfo';
import { Loading, Note, Pill, btnGhost, btnPrimary, errText, field, label as labelCls } from '../admin/ui';
import { Panel } from '../editorial/kit';
import { AskSheet } from '../budget/parts';
import { adsApi, type Brief, type Campaign } from './api';
import { AdsFrame, BookPicker, useAdsMeta } from './parts';

const TONE: Record<Brief['durum'], 'ok' | 'warn' | 'err' | 'muted'> = { hazirlaniyor: 'warn', taslak: 'muted', onayli: 'ok', hata: 'err' };

/** Kampanya brief'i taslağı: hedef kitle, mesaj, kanal, reklam metni önerisi. Zeki AI yalnız CRM'deki kitap bilgisinden
 *  yazar; rakam, alıntı ve iddia denetiminden geçmeyen cümle düşer. Taslak düzeltilir, onaylanır; ajansa gönderimi ekip yapar. */
export default function AdsBriefs() {
  const qc = useQueryClient();
  const meta = useAdsMeta();
  const m = meta.data;
  const [book, setBook] = useState<{ stokKodu: string } | null>(null);
  const [picking, setPicking] = useState(false);
  const [note, setNote] = useState('');
  const [fresh, setFresh] = useState<string | null>(null);
  const list = useQuery({
    queryKey: ['ads', 'briefs'],
    queryFn: adsApi.briefs,
    enabled: ENGINE_ENABLED,
    refetchInterval: (q) => (q.state.data?.items.some((b) => b.durum === 'hazirlaniyor') ? 4000 : false),
  });
  // elle: Zeki AI'a gitmeden boş taslak açılır; aşağıdaki kartta metin yazılıp kaydedilir.
  const create = useMutation({
    mutationFn: (elle: boolean) => adsApi.newBrief(book!.stokKodu, note.trim() || undefined, elle),
    onSuccess: (b, elle) => {
      toast.success(elle ? `Boş brief açıldı: ${b.kitapAdi ?? b.stokKodu}. Metni aşağıda yazıp kaydedin.` : `Brief hazırlanıyor: ${b.kitapAdi ?? b.stokKodu}`);
      setFresh(elle ? b.id : null);
      setBook(null);
      setNote('');
      qc.invalidateQueries({ queryKey: ['ads', 'briefs'] });
    },
    onError: (e, elle) => toast.error(errText(e, elle ? 'Brief açılamadı.' : 'Brief istenemedi.') ?? ''),
  });
  const canEdit = !!m?.me.canEdit;
  const fake: Campaign | null = picking ? ({ ad: 'Brief yazılacak kitap' } as Campaign) : null;

  return (
    <AdsFrame
      title="Kampanya brief'i"
      lead="Brief, reklamı hazırlayacak kişiye verilen kısa iş tanımıdır. Bir kitap seçin; Zeki AI hedef kitle, ana mesaj, kanal önerisi ve üç reklam metni taslağı yazar, siz düzeltip onaylarsınız. İsterseniz brief'i baştan kendiniz de yazabilirsiniz. Kanıtı olmayan indirim ya da «en çok satan» gibi iddialar yazılmaz; müşteri listemiz reklam hedeflemesi için önerilmez."
      meta={m}
    >
      {m && !m.modelReady && <Note tone="warn">Zeki AI şu an bağlı değil; taslak hazırlatamazsınız. «Brief'i elle yaz» ile brief'i kendiniz yazabilir, var olan brief'leri düzenleyebilirsiniz.</Note>}
      {canEdit && (
        <Panel>
          <h2 className="text-[15px] font-extrabold tracking-tight">Yeni brief</h2>
          <div className="mt-2 grid grid-cols-1 gap-2 lg:grid-cols-[minmax(0,1fr)_minmax(0,2fr)_auto] lg:items-end">
            <div className="flex flex-col gap-1">
              <span className={labelCls}>Kitap</span>
              <button type="button" className={`${btnGhost} justify-start`} onClick={() => setPicking(true)}>
                {book ? <span className="font-mono">{book.stokKodu}</span> : 'Kitap seç'}
              </button>
            </div>
            <label className="flex flex-col gap-1">
              <span className={labelCls}>Not (isteğe bağlı)</span>
              <input className={field} value={note} maxLength={1000} placeholder="ör. yetişkin okura, lansman ayı, Instagram ağırlıklı" onChange={(e) => setNote(e.target.value)} />
            </label>
            <div className="flex flex-wrap gap-1.5">
              <button type="button" className={btnGhost} disabled={!book || create.isPending} onClick={() => create.mutate(true)}>
                <PenLine aria-hidden className="h-4 w-4" />Brief'i elle yaz
              </button>
              <button type="button" className={btnPrimary} disabled={!book || create.isPending || !m?.modelReady} onClick={() => create.mutate(false)}>
                <Sparkles aria-hidden className="h-4 w-4" />Zeki AI taslağı iste
              </button>
            </div>
          </div>
        </Panel>
      )}
      {list.error && <Note tone="err">{errText(list.error, 'Brief listesi açılamadı.')}</Note>}
      {list.isLoading && <Loading />}
      {list.data && <p className="flex items-center gap-1 px-1 text-[11.5px] text-canvas-muted">Brief kayıtları ve denetim sayıları<SqlInfo k={list.data.kaynaklar} alan="items" label="Brief'ler" /></p>}
      {list.data && list.data.items.length === 0 && <p className="px-1 py-4 text-[12.5px] text-canvas-muted">Henüz brief yok. Yukarıdan kitap seçip «Zeki AI taslağı iste» ile hazırlatın ya da «Brief'i elle yaz» ile kendiniz yazın.</p>}
      <div className="grid grid-cols-1 gap-3 xl:grid-cols-2">
        {list.data?.items.map((b) => <BriefCard key={b.id} b={b} canEdit={canEdit} focus={b.id === fresh} />)}
      </div>
      <BookPicker campaign={fake} title="Brief için kitap" busy={false} onClose={() => setPicking(false)}
        onPick={(stok) => { setBook({ stokKodu: stok }); setPicking(false); }} />
    </AdsFrame>
  );
}

function BriefCard({ b, canEdit, focus }: { b: Brief; canEdit: boolean; focus: boolean }) {
  const qc = useQueryClient();
  const [text, setText] = useState(b.metin ?? '');
  const [del, setDel] = useState(false);
  useEffect(() => setText(b.metin ?? ''), [b.metin]);
  const save = useMutation({
    mutationFn: (onayla: boolean) => adsApi.saveBrief(b.id, { ...(text !== (b.metin ?? '') ? { metin: text } : {}), ...(onayla ? { onayla } : {}) }),
    onSuccess: (x) => { toast.success(x.durum === 'onayli' ? 'Brief onaylandı.' : 'Kaydedildi.'); qc.invalidateQueries({ queryKey: ['ads', 'briefs'] }); },
    onError: (e) => toast.error(errText(e, 'Kaydedilemedi.') ?? ''),
  });
  const remove = useMutation({
    mutationFn: () => adsApi.deleteBrief(b.id),
    onSuccess: () => { setDel(false); qc.invalidateQueries({ queryKey: ['ads', 'briefs'] }); },
    onError: (e) => toast.error(errText(e, 'Silinemedi.') ?? ''),
  });
  const dirty = text !== (b.metin ?? '');
  return (
    <Panel>
      <div className="flex flex-wrap items-center gap-1.5">
        <span className="text-[14px] font-extrabold">{b.kitapAdi ?? b.stokKodu}</span>
        <Pill tone={TONE[b.durum]}>{b.durumAdi}</Pill>
        {!!b.denetim?.dusenSayisi && <Pill tone="muted">{b.denetim.dusenSayisi} cümle denetimde düştü</Pill>}
      </div>
      <p className="mt-0.5 text-[11px] text-canvas-muted">
        <span className="font-mono">{b.stokKodu}</span> · {b.olusturan}{b.istek ? ` · «${b.istek}»` : ''}{b.onaylayan ? ` · onaylayan ${b.onaylayan}` : ''}
      </p>
      {b.durum === 'hazirlaniyor' && <p className="mt-3 text-[12.5px] text-canvas-muted">Zeki AI yazıyor…</p>}
      {b.hata && <div className="mt-2"><Note tone="err">{b.hata}</Note></div>}
      {b.durum !== 'hazirlaniyor' && (b.metin !== null || canEdit) && (
        <textarea className={`${field} mt-2 min-h-[260px] font-normal leading-snug`} value={text} readOnly={!canEdit} autoFocus={focus && canEdit}
          aria-label={`${b.kitapAdi ?? b.stokKodu ?? ''} brief metni`}
          placeholder={canEdit ? 'Hedef kitle, ana mesaj ve konumlama, önerilen kanallar, reklam metni önerileri, görsel yön, kaçınılacaklar' : undefined}
          onChange={(e) => setText(e.target.value)} />
      )}
      <div className="mt-2 flex flex-wrap gap-1.5">
        {canEdit && b.durum !== 'hazirlaniyor' && (
          <>
            {dirty && <button type="button" className={btnGhost} disabled={save.isPending || !text.trim()} onClick={() => save.mutate(false)}>Kaydet</button>}
            {(b.durum === 'taslak' || dirty) && text.trim() && (
              <button type="button" className={btnPrimary} disabled={save.isPending} onClick={() => save.mutate(true)}><Check aria-hidden className="h-4 w-4" />Onayla</button>
            )}
          </>
        )}
        {b.metin && (
          <button type="button" className={btnGhost} onClick={() => navigator.clipboard?.writeText(b.metin ?? '').then(() => toast.success('Kopyalandı.'))}>
            <Copy aria-hidden className="h-4 w-4" />Kopyala
          </button>
        )}
        {canEdit && <button type="button" className={btnGhost} onClick={() => setDel(true)}><Trash2 aria-hidden className="h-4 w-4" />Brief'i sil</button>}
      </div>
      <AskSheet open={del} title="Brief'i sil" message={`${b.kitapAdi ?? b.stokKodu} brief'i silinecek. Bu işlem geri alınamaz.`} confirm="Sil" danger busy={remove.isPending}
        onClose={() => setDel(false)} onConfirm={() => remove.mutate()} />
    </Panel>
  );
}
