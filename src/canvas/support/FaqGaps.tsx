import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Loading, Note, Pill, btnGhost, btnPrimary, errText, field, label } from '../admin/ui';
import { ENGINE_ENABLED } from '../engine';
import { Block, Empty, SourceLine } from './parts';
import { fmtDay, fmtInt, supportApi, type Gap } from './api';

/** Bilgi bankası açıkları: SSS eşleşmesi bulunamayan taleplerin konuya göre sayısı. Yönetici soru ve cevabı yazar, onaylar;
 *  onaylı metin portaldan siteye gönderilmez (T-soft'a yazma yok), siteye elle girilir ve «siteye elle girildi» işaretlenir.
 *  Onaylı maddeler Zeki AI'ın SSS eşleştirmesine hemen katılır. */
export default function FaqGaps() {
  const q = useQuery({ queryKey: ['support', 'gaps'], queryFn: supportApi.gaps, enabled: ENGINE_ENABLED });
  if (q.isLoading) return <Loading />;
  if (q.error) return <Note tone="err">{errText(q.error, 'Liste okunamadı.')}</Note>;
  const items = q.data?.items ?? [];
  return (
    <Block
      title="Bilgi bankası açıkları"
      help="Sitede cevabı olsa gelmeyecek talepler: Zeki AI benzer SSS bulamadı. Liste her gece yeniden sayılır."
    >
      {items.length === 0 ? (
        <Empty title="Açık yok">Gece sayımında eşik üstünde SSS'siz konu çıkmadı ya da henüz sayım yapılmadı.</Empty>
      ) : (
        <ul className="flex flex-col gap-2">
          {items.map((g) => (
            <GapItem key={g.id} gap={g} canEdit={!!q.data?.canEdit} />
          ))}
        </ul>
      )}
    </Block>
  );
}

function GapItem({ gap, canEdit }: { gap: Gap; canEdit: boolean }) {
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [question, setQuestion] = useState(gap.question ?? '');
  const [answer, setAnswer] = useState(gap.draft ?? '');
  const save = useMutation({
    mutationFn: (status?: string) => supportApi.patchGap(gap.id, { question, draft: answer, ...(status ? { status } : {}) }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['support', 'gaps'] });
      toast.success('Kaydedildi.');
    },
    onError: (e) => toast.error(errText(e, 'Kaydedilemedi.') ?? ''),
  });
  const tone = gap.status === 'onayli' || gap.status === 'yayinlandi-elle' ? 'ok' : gap.status === 'kapandi' ? 'muted' : 'warn';
  return (
    <li className="rounded-2xl border border-slate-100 bg-white/80 p-3">
      <button type="button" className="flex w-full flex-wrap items-center gap-2 text-left" onClick={() => setOpen(!open)} aria-expanded={open}>
        <span className="text-[13.5px] font-extrabold">{gap.label}</span>
        <Pill tone="muted">{fmtInt(gap.tickets)} talep · son {gap.windowDays ?? '—'} gün</Pill>
        <Pill tone={tone}>{gap.statusLabel}</Pill>
        {gap.question && <span className="min-w-0 flex-1 truncate text-[12px] text-canvas-muted">{gap.question}</span>}
      </button>
      {open && (
        <div className="mt-3 flex flex-col gap-2">
          <SourceLine>Örnek talepler: {gap.samples.join(', ') || '—'}</SourceLine>
          <label className="flex flex-col gap-1">
            <span className={label}>SSS sorusu</span>
            <input className={field} value={question} onChange={(e) => setQuestion(e.target.value)} disabled={!canEdit} placeholder="Örn. E-kitabımı nasıl indiririm?" />
          </label>
          <label className="flex flex-col gap-1">
            <span className={label}>Cevap</span>
            <textarea className={`${field} min-h-[120px] font-normal`} value={answer} onChange={(e) => setAnswer(e.target.value)} disabled={!canEdit} />
          </label>
          {canEdit ? (
            <div className="flex flex-wrap gap-1.5">
              <button type="button" className={btnGhost} disabled={save.isPending} onClick={() => save.mutate('taslak')}>
                Taslak kaydet
              </button>
              <button type="button" className={btnPrimary} disabled={save.isPending || !question.trim() || !answer.trim()} onClick={() => save.mutate('onayli')}>
                Onayla
              </button>
              {gap.status === 'onayli' && (
                <button type="button" className={btnGhost} disabled={save.isPending} onClick={() => save.mutate('yayinlandi-elle')}>
                  Siteye elle girildi
                </button>
              )}
              <button type="button" className={btnGhost} disabled={save.isPending} onClick={() => save.mutate('kapandi')}>
                Gerek yok
              </button>
            </div>
          ) : (
            <SourceLine>Düzeltme ve onay «SSS maddesi onayı» yetkisiyle yapılır.</SourceLine>
          )}
          {gap.approvedBy && <SourceLine>Onaylayan {gap.approvedBy} · {fmtDay(gap.approvedAt)}</SourceLine>}
        </div>
      )}
    </li>
  );
}
