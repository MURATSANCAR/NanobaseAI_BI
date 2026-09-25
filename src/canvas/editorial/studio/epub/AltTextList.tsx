import { useEffect, useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { Check, Loader2, Sparkles } from 'lucide-react';
import { Note, errText } from '../../../admin/ui';
import { Img, ghostBtn, press } from '../shared';
import { epubApi, useAlts, type AltItem, type AltSource } from './api';

/** Alt metinleri gözden geçir: her görselin küçüğü, hangi sayfada olduğu, metni ve nereden geldiği. Editörün yazdığı
 *  her zaman kazanır; «Yeniden öner» Zeki AI'dan yeni öneri alır. Varsayılan görünüm yalnız gözden geçirilmesi
 *  gerekenler (boş, sayfanın anından yazılmış ya da resim değiştiği için eskimiş). */

const SOURCE: Record<AltSource, string> = {
  editor: 'Editör yazdı',
  sahne: 'Sahne tarifinden',
  model: 'Görselden (Zeki AI)',
  tarif: 'Figürün tarifinden',
  an: 'Sayfanın anından · gözden geçirin',
  kapak: 'Kitap bilgisinden',
  '': 'Yok',
};

function where(it: AltItem): string {
  if (it.kind === 'kapak') return 'Kapak';
  const kind = it.kind[0].toLocaleUpperCase('tr') + it.kind.slice(1);
  return it.pages.length ? `${kind} · s. ${it.pages.join(', ')}` : kind;
}

function Row({ jobId, it }: { jobId: string; it: AltItem }) {
  const qc = useQueryClient();
  const [text, setText] = useState(it.text);
  useEffect(() => setText(it.text), [it.text]);
  const refresh = () => {
    qc.invalidateQueries({ queryKey: ['studio', 'epub', jobId] });
  };
  const save = useMutation({ mutationFn: (t: string) => epubApi.setAlt(jobId, it.key, t), onSuccess: refresh });
  const suggest = useMutation({ mutationFn: () => epubApi.suggestAlt(jobId, it.key), onSuccess: refresh });
  const dirty = text.trim() !== it.text.trim();
  const id = `alt-${it.key}`;
  const err = errText(save.error || suggest.error, '');
  return (
    <li className="grid gap-2 rounded-2xl border border-white/70 bg-white/70 p-2 sm:grid-cols-[112px_1fr]">
      {it.has_image ? (
        <Img src={epubApi.altImageUrl(jobId, it.key, 240)} alt="" fallback="görsel"
          className="aspect-[4/3] w-full rounded-lg bg-slate-100 object-cover sm:w-[112px]" />
      ) : <div className="flex aspect-[4/3] w-full items-center justify-center rounded-lg bg-slate-100 text-[11px] text-canvas-muted sm:w-[112px]">{it.kind === 'kapak' ? 'kapak' : 'görsel'}</div>}
      <div className="flex min-w-0 flex-col gap-1.5">
        <div className="flex flex-wrap items-center justify-between gap-1">
          <label htmlFor={id} className="text-[12px] font-extrabold">{where(it)}</label>
          <span className={`rounded-full px-2 py-0.5 text-[10.5px] font-bold ${it.review ? 'bg-amber-50 text-amber-700' : 'bg-slate-100 text-canvas-muted'}`}>
            {it.stale ? 'Resim değişti · gözden geçirin' : SOURCE[it.source] ?? SOURCE['']}
          </span>
        </div>
        <textarea id={id} value={text} onChange={(e) => setText(e.target.value)} rows={2} maxLength={1000}
          placeholder="Görselde ne görünüyor? (1–2 cümle)"
          className="rounded-xl border border-slate-200 bg-white/90 px-3 py-2 text-base outline-none focus:border-canvas-violet sm:text-[12.5px]" />
        <div className="flex flex-wrap gap-1.5">
          <button type="button" className={ghostBtn} disabled={!dirty || save.isPending} onClick={() => save.mutate(text)}>
            {save.isPending ? <Loader2 className="h-4 w-4 animate-spin motion-reduce:animate-none" aria-hidden /> : <Check className="h-4 w-4" aria-hidden />}
            Kaydet
          </button>
          <button type="button" className={ghostBtn} disabled={suggest.isPending} onClick={() => suggest.mutate()}
            title="Zeki AI görselden ya da sahnenin tarifinden yeni bir alt metin önerir; yazdığınızın yerine geçer">
            {suggest.isPending ? <Loader2 className="h-4 w-4 animate-spin motion-reduce:animate-none" aria-hidden /> : <Sparkles className="h-4 w-4" aria-hidden />}
            {suggest.isPending ? 'Öneriliyor…' : 'Yeniden öner'}
          </button>
        </div>
        {err && <Note tone="err">{err}</Note>}
      </div>
    </li>
  );
}

export default function AltTextList({ jobId }: { jobId: string }) {
  const q = useAlts(jobId, true);
  const [all, setAll] = useState(false);
  const items = q.data?.items ?? [];
  // Kaydedilen satır listeden hemen düşmesin: bu oturumda gözden geçirilecek görünen satırlar yerinde kalır.
  const [kept, setKept] = useState<Set<string>>(() => new Set());
  useEffect(() => {
    const add = items.filter((i) => i.review && !kept.has(i.key)).map((i) => i.key);
    if (add.length) setKept((s) => new Set([...s, ...add]));
  }, [items, kept]);
  const review = items.filter((i) => i.review);
  const shown = all ? items : items.filter((i) => i.review || kept.has(i.key));
  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-[13px] font-extrabold">Alt metinler <span className="font-bold text-canvas-muted">· {items.length} görsel</span></h3>
        <div role="radiogroup" aria-label="Gösterilen alt metinler" className="inline-flex rounded-xl bg-slate-100 p-0.5">
          {([[false, `Gözden geçirilecek (${review.length})`], [true, 'Hepsi']] as const).map(([v, t]) => (
            <button key={String(v)} type="button" role="radio" aria-checked={all === v} onClick={() => setAll(v)}
              className={`min-h-9 rounded-[10px] px-2.5 text-[11.5px] font-bold ${press} ${all === v ? 'bg-white text-canvas-ink shadow-sm' : 'text-canvas-muted'}`}>
              {t}
            </button>
          ))}
        </div>
      </div>
      {q.error && <Note tone="err">{errText(q.error, 'Alt metinler okunamadı.')}</Note>}
      {!q.isLoading && !shown.length && (
        <p className="text-[12px] text-canvas-muted">
          {items.length ? 'Gözden geçirilecek alt metin yok. «Hepsi» ile bütün görsellerin metinlerini görebilirsiniz.' :
            'E-kitaba girecek görsel yok.'}
        </p>
      )}
      <ul className="flex flex-col gap-2">
        {shown.map((it) => <Row key={it.key} jobId={jobId} it={it} />)}
      </ul>
    </div>
  );
}
