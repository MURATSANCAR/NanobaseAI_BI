import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { RefreshCw } from 'lucide-react';
import { ENGINE_ENABLED } from '../../engine';
import { btnGhost, errText, nf } from '../../admin/ui';
import { stamp } from '../../format';
import { applicationsApi } from './api';

/** Yazar başvuru formları (Google E-Tablo yanıtları): 15 dakikada bir okunur, her yanıt bir kez «Yeni başvuru» olur.
 *  Burada son okuma, tablo başına aktarılan başvuru ve paylaşılmamış tablo uyarısı görünür; «Şimdi al» beklemeden okur. */
export default function FormsPanel() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ['applications', 'forms'], queryFn: applicationsApi.forms, enabled: ENGINE_ENABLED, staleTime: 60_000 });
  const sync = useMutation({
    mutationFn: applicationsApi.syncForms,
    onSuccess: (r) => {
      qc.invalidateQueries({ queryKey: ['applications'] });
      toast.success(r.new ? `${nf.format(r.new)} yeni başvuru formdan alındı` : 'Formlarda yeni başvuru yok', {
        description: r.errors ? `${nf.format(r.errors)} tablo okunamadı; ayrıntı panelde.` : undefined,
      });
    },
    onError: (e) => toast.error(errText(e, 'Formlar okunamadı.') ?? ''),
  });
  const d = q.data;
  if (!d || !d.configured) return null;
  const run = d.lastRun;
  const errors = (run?.sheets ?? []).filter((s) => s.error);
  const total = d.sheets.reduce((a, s) => a + s.applications, 0);
  return (
    <section aria-labelledby="basvuru-formlari" className="rounded-2xl border border-slate-100 bg-white/85 p-3 text-[12px]">
      <div className="flex items-baseline justify-between gap-2">
        <h2 id="basvuru-formlari" className="text-[12.5px] font-extrabold">Başvuru formları</h2>
        <span className="font-mono text-[11px] tabular-nums text-canvas-muted">{nf.format(total)} başvuru</span>
      </div>
      <p className="mt-0.5 leading-snug text-canvas-muted">
        {run ? `Son okuma ${stamp(Date.parse(run.at))}${run.new ? ` · ${nf.format(run.new)} yeni` : ''}` : 'Henüz okunmadı'} · 15 dakikada bir
      </p>
      <ul className="mt-1.5 space-y-0.5">
        {d.sheets.map((s) => {
          const err = errors.find((e) => e.sheetId === s.sheetId);
          return (
            <li key={s.sheetId} className="flex items-baseline justify-between gap-2">
              <span className={`min-w-0 truncate ${err ? 'text-amber-800' : ''}`} title={err?.error ?? s.title ?? s.sheetId}>
                {s.title ?? (err ? 'Paylaşılmamış tablo' : 'Okunmadı')}
              </span>
              <span className="shrink-0 font-mono tabular-nums text-canvas-muted">{err ? 'erişim yok' : nf.format(s.applications)}</span>
            </li>
          );
        })}
      </ul>
      {errors.length > 0 && (
        <p className="mt-1.5 leading-snug text-amber-800">
          {nf.format(errors.length)} tablo servis hesabıyla paylaşılmamış; tablo sahibi Görüntüleyici olarak eklemeli.
        </p>
      )}
      {d.canSync && (
        <button type="button" className={`${btnGhost} mt-2 w-full`} disabled={sync.isPending} onClick={() => sync.mutate()}>
          <RefreshCw aria-hidden className={`h-4 w-4 ${sync.isPending ? 'animate-spin motion-reduce:animate-none' : ''}`} />
          {sync.isPending ? 'Okunuyor…' : 'Şimdi al'}
        </button>
      )}
    </section>
  );
}
