import { useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { Loader2, RotateCcw } from 'lucide-react';
import { errText } from '../admin/ui';
import { useFeatureAllowed } from '../components/FileDrop';

/** «Okunamadı» kitabı elle yeniden okut (Kitaba sor'un okutma listesi ve Kitap Eczanesi ayrıntısı ortak).
 *
 *  Kendini onarma denemeleri bitmiş kitap için: önce kısa onay («Kitap yeniden sıraya alınacak»), sonra köprü aynı
 *  kipte yeni okuma işi açar ve kitap «Sırada» olur (`onDone` listeyi tazeler). Yetki kitap yüklemeyle aynı
 *  (`kitap.okut`); yetkisi olmayana düğme görünmez. Hata kişiye köprünün sade cümlesiyle; teknik neden gösterilmez. */
export default function RereadButton({ title, run, onDone }: { title: string; run: () => Promise<unknown>; onDone: () => void }) {
  const allowed = useFeatureAllowed('kitap.okut');
  const [asking, setAsking] = useState(false);
  const go = useMutation({
    mutationFn: run,
    onSuccess: () => {
      setAsking(false);
      onDone();
    },
  });
  if (!allowed) return null;
  const btn =
    'zk-press inline-flex min-h-11 items-center justify-center gap-1.5 rounded-xl px-3.5 text-[12.5px] font-bold disabled:opacity-50';
  return (
    <div className="mt-2">
      {!asking ? (
        <button type="button" onClick={() => setAsking(true)} className={`${btn} bg-white text-canvas-ink ring-1 ring-slate-200 hover:ring-canvas-violet/40`} aria-label={`${title} kitabını yeniden okut`}>
          <RotateCcw aria-hidden className="h-4 w-4" />
          Yeniden okut
        </button>
      ) : (
        <div className="rounded-xl bg-slate-50 p-2.5 ring-1 ring-slate-200" role="group" aria-label="Yeniden okutma onayı">
          <p className="text-[12.5px] font-semibold text-canvas-ink">Kitap yeniden sıraya alınacak.</p>
          <div className="mt-2 flex flex-wrap gap-2">
            <button type="button" disabled={go.isPending} onClick={() => go.mutate()} className={`${btn} bg-canvas-violet text-white shadow-sm`}>
              {go.isPending ? <Loader2 aria-hidden className="h-4 w-4 animate-spin motion-reduce:animate-none" /> : <RotateCcw aria-hidden className="h-4 w-4" />}
              {go.isPending ? 'Sıraya alınıyor…' : 'Sıraya al'}
            </button>
            <button type="button" disabled={go.isPending} onClick={() => { setAsking(false); go.reset(); }} className={`${btn} bg-white text-canvas-ink ring-1 ring-slate-200`}>
              Vazgeç
            </button>
          </div>
        </div>
      )}
      {go.error ? (
        <p role="alert" className="mt-1.5 text-[11.5px] leading-snug text-red-700">
          {errText(go.error, 'Kitap şu an yeniden sıraya alınamadı; birazdan tekrar deneyin.')}
        </p>
      ) : null}
    </div>
  );
}
