import { useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { Copy, FileText, Loader2, RefreshCw, Sparkles } from 'lucide-react';
import { toast } from 'sonner';
import { Note, Pill, btnGhost, field } from '../../admin/ui';
import { Panel } from '../kit';
import { Field, Sheet, errMsg } from '../contracts/ui';
import { royaltyApi, type CoverEmail, type Party, type Run, type RunNote } from './api';

/** M54 taslakları: koşu özeti (yöneticiye) ve beyanname kapak e-postası. Sayılar koşunun kendi toplamlarından; metin
 *  sayı denetimli. Portal e-posta göndermez: taslak kopyalanır, gönderen insandır. */

async function copyText(text: string) {
  try {
    await navigator.clipboard.writeText(text);
    toast.success('Kopyalandı.');
  } catch {
    toast.error('Kopyalanamadı; metni seçip kopyalayın.');
  }
}

/** Koşu özeti: olgular SQL'den (sorgu «Sorgu» açılırında), anlatım Zeki AI ya da kural metni. */
export function RunNotePanel({ run }: { run: Run }) {
  const [note, setNote] = useState<RunNote | null>(null);
  const ask = useMutation({
    mutationFn: (fresh: boolean) => royaltyApi.summaryNote(run.id, fresh),
    onSuccess: setNote,
    onError: (e) => toast.error(errMsg(e) ?? 'Özet yazılamadı.'),
  });
  if (run.status === 'taslak' || run.status === 'hesaplaniyor') return null;
  return (
    <Panel>
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="min-w-0 flex-1 text-[13px] font-extrabold">Koşu özeti</h3>
        <button type="button" className={btnGhost} disabled={ask.isPending} onClick={() => ask.mutate(!!note)}>
          {ask.isPending ? <Loader2 aria-hidden className="h-4 w-4 animate-spin" /> : note ? <RefreshCw aria-hidden className="h-4 w-4" /> : <Sparkles aria-hidden className="h-4 w-4" />}
          {note ? 'Yeniden yaz' : 'Özet yaz'}
        </button>
      </div>
      {!note && <p className="mt-1 text-[12px] text-canvas-muted">Yöneticiye 3–5 cümle: hesaplanan ve istisnadaki sözleşmeler, ödenecek toplam, önceki onaylı koşuya fark.</p>}
      {note && (
        <div className="mt-2 space-y-2">
          <Pill tone={note.kaynak === 'zeki' ? 'violet' : 'muted'}>{note.kaynak === 'zeki' ? 'Zeki AI özeti' : 'Kurala göre özet'}</Pill>
          <p className="whitespace-pre-wrap break-words text-[12.5px] leading-relaxed">{note.metin}</p>
          <p className="text-[11px] text-canvas-muted">Sayılar koşu satırlarından okunur; metindeki her sayı bu olgularla denetlenir.{note.saklanan ? ' Olgular değişmediği için saklanan özet gösteriliyor.' : ''}</p>
          <details className="text-[11.5px]">
            <summary className="inline-flex min-h-11 cursor-pointer items-center font-bold text-canvas-violet sm:min-h-0">Sorgu</summary>
            {note.sql.map((s, i) => <pre key={i} className="mt-1 max-w-full overflow-x-auto whitespace-pre-wrap break-words rounded-lg bg-slate-50 p-2 font-mono text-[11px]">{s}</pre>)}
          </details>
        </div>
      )}
    </Panel>
  );
}

/** Hak sahibi satırındaki «Kapak e-postası» düğmesi ve taslak penceresi. */
export function CoverEmailButton({ run, party }: { run: Run; party: Party }) {
  const [draft, setDraft] = useState<CoverEmail | null>(null);
  const ask = useMutation({
    mutationFn: () => royaltyApi.coverEmail(run.id, party.key),
    onSuccess: setDraft,
    onError: (e) => toast.error(errMsg(e) ?? 'Taslak yazılamadı.'),
  });
  return (
    <>
      <button type="button" className={btnGhost} disabled={ask.isPending} onClick={() => ask.mutate()}>
        {ask.isPending ? <Loader2 aria-hidden className="h-4 w-4 animate-spin" /> : <FileText aria-hidden className="h-4 w-4" />}
        Kapak e-postası
      </button>
      {draft && <CoverEmailSheet draft={draft} onClose={() => setDraft(null)} />}
    </>
  );
}

function CoverEmailSheet({ draft, onClose }: { draft: CoverEmail; onClose: () => void }) {
  const [subject, setSubject] = useState(draft.konu);
  const [body, setBody] = useState(draft.metin);
  return (
    <Sheet title="Kapak e-postası taslağı" onClose={onClose} wide
      footer={
        <>
          <button type="button" className={btnGhost} onClick={onClose}>Kapat</button>
          <button type="button" className={btnGhost} onClick={() => copyText(`${subject}\n\n${body}`)}>
            <Copy aria-hidden className="h-4 w-4" /> Konu ve metni kopyala
          </button>
        </>
      }>
      <div className="space-y-3">
        <Note tone="info">{draft.not}</Note>
        <div className="flex flex-wrap items-center gap-2 text-[12px]">
          <Pill tone={draft.kaynak === 'zeki' ? 'violet' : 'muted'}>{draft.kaynak === 'zeki' ? 'Zeki AI taslağı' : 'Kurala göre taslak'}</Pill>
          <span className="text-canvas-muted">{draft.hakSahibi}{draft.alici ? ` · ${draft.alici}` : ' · e-posta adresi kayıtlı değil'}</span>
        </div>
        <Field label="Konu"><input value={subject} onChange={(e) => setSubject(e.target.value)} className={field} /></Field>
        <Field label="Metin" hint="Tutarlar beyannameden kopyalanır; değiştirirseniz beyannameyle karşılaştırın.">
          <textarea value={body} onChange={(e) => setBody(e.target.value)} rows={12} className={field} />
        </Field>
      </div>
    </Sheet>
  );
}
