import { useEffect, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Check, FileText, Loader2, Sparkles } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import { Note, Pill, btnGhost, btnPrimary, errText, field } from '../admin/ui';
import { Panel } from '../editorial/kit';
import { financeApi, fmtDay, type Commentary, type Meta } from './api';

/** Aylık finansal yorum taslağı (M45 §13). Rakamlar ve karşılaştırmalar kodla hesaplanır; Zeki AI yalnız anlatır ve
 *  metindeki her sayı olgularla denetlenir — tutmazsa olgular «kurala göre» yazılır. Metin taslaktır: CFO düzeltir ve
 *  açıkça verilen yetkiyle onaylar; onaylı metin kurul panelinde finans göstergesine gider. */

const SOURCE: Record<string, { tone: 'violet' | 'muted' | 'ok'; label: string }> = {
  zeki: { tone: 'violet', label: 'Zeki AI taslağı' },
  kural: { tone: 'muted', label: 'Kurala göre taslak (olgular)' },
  insan: { tone: 'ok', label: 'Elle düzeltildi' },
};

function reasonText(n: string | null | undefined): string | null {
  if (!n) return null;
  if (n === 'model-yok') return 'Zeki AI bu kurulumda tanımlı değil; olgular olduğu gibi yazıldı.';
  if (n.startsWith('olgu-disi-sayi')) return 'Zeki AI metninde olgularda olmayan bir sayı vardı; metin kullanılmadı, olgular olduğu gibi yazıldı.';
  if (n === 'teknoloji-adi') return 'Zeki AI metni denetimden geçmedi; olgular olduğu gibi yazıldı.';
  return 'Zeki AI metni alınamadı; olgular olduğu gibi yazıldı.';
}

export default function CommentaryPanel({ year, month, monthName, me }: { year: number; month: number; monthName: string; me: Meta['me'] }) {
  const qc = useQueryClient();
  const key = ['finance', 'commentary', year, month];
  const q = useQuery({ queryKey: key, queryFn: () => financeApi.commentary(year, month), enabled: ENGINE_ENABLED });
  const [text, setText] = useState('');
  const [editing, setEditing] = useState(false);
  const c = q.data;
  useEffect(() => {
    setText(c?.metin ?? '');
    setEditing(false);
  }, [c?.metin, c?.durum]);

  const done = (d: Commentary, msg: string) => {
    qc.setQueryData(key, d);
    toast.success(msg);
  };
  const draft = useMutation({
    mutationFn: () => financeApi.commentaryDraft(year, month),
    onSuccess: (d) => done(d, d.kaynak === 'zeki' ? 'Zeki AI taslağı hazır; okuyup düzeltin.' : 'Taslak olgulardan yazıldı.'),
    onError: (e) => toast.error(errText(e, 'Taslak hazırlanamadı.')),
  });
  const save = useMutation({
    mutationFn: () => financeApi.commentarySave(year, month, text),
    onSuccess: (d) => done(d, 'Yorum kaydedildi (taslak).'),
    onError: (e) => toast.error(errText(e, 'Yorum kaydedilemedi.')),
  });
  const approve = useMutation({
    mutationFn: () => financeApi.commentaryApprove(year, month),
    onSuccess: (d) => done(d, 'Yorum onaylandı.'),
    onError: (e) => toast.error(errText(e, 'Onaylanamadı.')),
  });

  const canWrite = !!me.canComment;
  const src = c?.kaynak ? SOURCE[c.kaynak] : null;
  const busy = draft.isPending || save.isPending || approve.isPending;
  return (
    <Panel>
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <h3 className="flex min-w-0 items-center gap-2 text-[15px] font-extrabold">
          <FileText aria-hidden className="h-4 w-4 shrink-0 text-canvas-violet" />
          <span className="min-w-0">Aylık finansal yorum · {monthName} {year}</span>
        </h3>
        <div className="flex flex-wrap items-center gap-1.5">
          {c?.durum && <Pill tone={c.durum === 'onayli' ? 'ok' : 'warn'}>{c.durum === 'onayli' ? 'Onaylı' : 'Taslak'}</Pill>}
          {src && <Pill tone={src.tone}>{src.label}</Pill>}
        </div>
      </div>
      {q.isLoading && <p className="text-[12.5px] text-canvas-muted">Yükleniyor…</p>}
      {q.error && <Note tone="err">{errText(q.error, 'Yorum okunamadı.')}</Note>}
      {c && !c.metin && (
        <p className="text-[12.5px] leading-snug text-canvas-muted">
          Bu ay için yorum yok. Taslak; gelir tablosu, önceki ay ve geçen yılın aynı ayı, maliyet kapsamı, kanal kârlılığı ve
          «bu ay dikkat» olgularından 5–8 cümle olarak yazılır. Metindeki her rakam bu olgularda geçmek zorundadır.
        </p>
      )}
      {c?.metin && !editing && <p className="whitespace-pre-line text-[13px] leading-relaxed">{c.metin}</p>}
      {c?.metin && editing && (
        <textarea aria-label="Yorum metni" className={`${field} min-h-[180px] leading-relaxed`} value={text} maxLength={6000}
          onChange={(e) => setText(e.target.value)} />
      )}
      {c?.kaynak === 'kural' && reasonText(c.neden) && <p className="mt-2 text-[11.5px] text-canvas-muted">{reasonText(c.neden)}</p>}
      {!!c?.olguDisiSayilar?.length && (
        <Note tone="warn">Metinde olgularda olmayan sayı var: {c.olguDisiSayilar.join(', ')}. Onaydan önce kontrol edin.</Note>
      )}
      {c?.metin && (
        <p className="mt-2 text-[11px] text-canvas-muted">
          Hazırlayan {c.hazirlayan ?? '—'}{c.onaylayan ? ` · onaylayan ${c.onaylayan}` : ''}{c.tarih ? ` · ${fmtDay(c.tarih)}` : ''}
        </p>
      )}
      {canWrite && c && (
        <div className="mt-3 flex flex-wrap gap-2">
          {!editing && (
            <button type="button" className={btnGhost} disabled={busy} onClick={() => draft.mutate()}>
              {draft.isPending ? <Loader2 aria-hidden className="h-4 w-4 animate-spin" /> : <Sparkles aria-hidden className="h-4 w-4" />}
              {c.metin ? 'Yeniden taslak hazırla' : 'Taslak hazırla'}
            </button>
          )}
          {c.metin && !editing && (
            <button type="button" className={btnGhost} disabled={busy} onClick={() => setEditing(true)}>Düzelt</button>
          )}
          {editing && (
            <>
              <button type="button" className={btnPrimary} disabled={busy || !text.trim()} onClick={() => save.mutate()}>Kaydet</button>
              <button type="button" className={btnGhost} disabled={busy} onClick={() => { setText(c.metin ?? ''); setEditing(false); }}>Vazgeç</button>
            </>
          )}
          {c.metin && c.durum === 'taslak' && !editing && me.canApproveComment && (
            <button type="button" className={btnPrimary} disabled={busy} onClick={() => approve.mutate()}>
              <Check aria-hidden className="h-4 w-4" /> Onayla
            </button>
          )}
        </div>
      )}
    </Panel>
  );
}
