import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { btnGhost, btnPrimary, errText } from '../admin/ui';
import { AskSheet } from '../budget/parts';
import { stockApi, type Suggestion } from './api';

/** Öneriye karar: kabul (hedef modüle not olarak düşer, onların kaydına yazılmaz) ya da gerekçeli ret. */
export function SuggestionActions({ s, canDecide }: { s: Suggestion; canDecide: boolean }) {
  const qc = useQueryClient();
  const [ask, setAsk] = useState(false);
  const decide = useMutation({
    mutationFn: (v: { karar: 'kabul' | 'red'; not?: string }) => stockApi.decide(s.id, v.karar, v.not),
    onSuccess: (r) => {
      toast.success(r.durum === 'kabul' ? `Kabul edildi${r.hedefEtiket ? ` — ${r.hedefEtiket} için kayıtta` : ''}.` : 'Reddedildi.');
      setAsk(false);
      qc.invalidateQueries({ queryKey: ['stock'] });
    },
    onError: (e) => toast.error(errText(e, 'Karar kaydedilemedi.') ?? ''),
  });
  if (!canDecide) return null;
  return (
    <div className="mt-2 flex flex-wrap justify-end gap-2">
      <button type="button" className={btnGhost} disabled={decide.isPending} onClick={() => setAsk(true)}>Reddet</button>
      <button type="button" className={btnPrimary} disabled={decide.isPending} onClick={() => decide.mutate({ karar: 'kabul' })}>Kabul et</button>
      <AskSheet
        open={ask}
        title="Öneriyi reddet"
        message="Gerekçe kayda geçer; aynı öneri bir süre yeniden açılmaz."
        confirm="Reddet"
        danger
        input="Gerekçe"
        required
        busy={decide.isPending}
        onClose={() => setAsk(false)}
        onConfirm={(t) => decide.mutate({ karar: 'red', not: t })}
      />
    </div>
  );
}
