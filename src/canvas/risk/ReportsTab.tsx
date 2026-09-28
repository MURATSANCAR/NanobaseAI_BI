import { useEffect, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import SqlInfo from '../components/SqlInfo';
import { toast } from 'sonner';
import { Check, Download, FileText, Loader2, Sparkles } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import { Loading, Note, Pill, btnGhost, btnPrimary, errText, field } from '../admin/ui';
import { Panel } from '../editorial/kit';
import { currentQuarter, fmtTime, riskApi, waitJob, type RiskMeta } from './api';
import { AskSheet, Empty, TextInput } from './parts';

/** Çeyreklik kurul risk brifingi: Zeki AI taslağı (bütün sayılar göstergelerden; girdide olmayan sayı çıkarsa kural
 *  metnine düşülür), koordinatör düzeltir, başka bir yetkili onaylar. Onaylı metin Word olarak alınır. */
export default function ReportsTab({ meta }: { meta: RiskMeta }) {
  const qc = useQueryClient();
  const list = useQuery({ queryKey: ['risk', 'reports'], queryFn: riskApi.reports, enabled: ENGINE_ENABLED });
  const [sel, setSel] = useState<string | null>(null);
  const [donem, setDonem] = useState(currentQuarter());
  const draft = useMutation({
    mutationFn: async () => {
      const j = await riskApi.draftReport(donem);
      const done = await waitJob(j.id);
      return { ...done, raporId: j.raporId };
    },
    onSuccess: (j) => {
      if (j.durum === 'hata') toast.error(j.hata ?? 'Taslak hazırlanamadı.');
      else toast.success('Brifing taslağı hazır');
      qc.invalidateQueries({ queryKey: ['risk', 'reports'] });
      if (j.raporId) setSel(j.raporId);
    },
    onError: (e) => toast.error(errText(e, 'Taslak hazırlanamadı.')),
  });
  const canDraft = meta.me.canWrite && meta.me.seeAll;
  const items = list.data?.items ?? [];
  return (
    <>
      {canDraft && (
        <Panel>
          <div className="grid grid-cols-1 items-end gap-2 sm:grid-cols-[200px_auto]">
            <TextInput id="rp-donem" label="Dönem" value={donem} onChange={setDonem} />
            <button type="button" className={`${btnPrimary} sm:justify-self-start`} disabled={draft.isPending || !donem.trim()} onClick={() => draft.mutate()}>
              {draft.isPending ? <Loader2 aria-hidden className="h-4 w-4 animate-spin" /> : <Sparkles aria-hidden className="h-4 w-4" />}
              {draft.isPending ? 'Hazırlanıyor…' : 'Brifing taslağı hazırla'}
            </button>
          </div>
          <p className="mt-2 text-[11.5px] leading-snug text-canvas-muted">
            Taslak bütün risklerden, göstergelerden, geciken aksiyonlardan ve bu ayın uyumundan hazırlanır. {meta.modelVar ? 'Zeki AI metni yazar; sayılar yalnız girdiden gelir.' : 'Zeki AI bu kurulumda yok; kural metni hazırlanır.'}
          </p>
        </Panel>
      )}
      <div className="grid grid-cols-1 gap-3 lg:grid-cols-[minmax(0,320px)_minmax(0,1fr)] lg:gap-4">
        <Panel>
          <h2 className="mb-2 text-[15px] font-extrabold tracking-tight">Brifingler</h2>
          {list.isLoading ? <Loading /> : items.length === 0 ? <Empty>Henüz brifing yok.</Empty> : (
            <ul className="flex flex-col gap-1.5">
              {items.map((r) => (
                <li key={r.id}>
                  <button type="button" aria-pressed={sel === r.id} onClick={() => setSel(r.id)}
                    className={`flex min-h-11 w-full items-center justify-between gap-2 rounded-xl px-3 py-2 text-left transition-transform duration-150 ease-out active:scale-[0.98] ${sel === r.id ? 'bg-canvas-violet/10' : 'bg-white/80 hover:bg-white'}`}>
                    <span className="min-w-0">
                      <span className="block text-[13px] font-bold">{r.donem}</span>
                      <span className="block text-[11px] text-canvas-muted">{fmtTime(r.olusturma)} · {r.olusturan}</span>
                    </span>
                    <Pill tone={r.durum === 'onayli' ? 'ok' : r.durum === 'hata' ? 'err' : r.durum === 'taslak' ? 'violet' : 'muted'}>{r.durumAdi}</Pill>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </Panel>
        {sel ? <ReportView key={sel} id={sel} meta={meta} /> : <Panel><Empty><FileText aria-hidden className="mx-auto mb-1 h-5 w-5" />Soldan bir brifing seçin.</Empty></Panel>}
      </div>
    </>
  );
}

function ReportView({ id, meta }: { id: string; meta: RiskMeta }) {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ['risk', 'report', id], queryFn: () => riskApi.report(id), enabled: ENGINE_ENABLED,
    refetchInterval: (query) => (query.state.data?.durum === 'hazirlaniyor' ? 3000 : false) });
  const [text, setText] = useState('');
  const [asking, setAsking] = useState(false);
  useEffect(() => { if (q.data?.metin != null) setText(q.data.metin); }, [q.data?.metin]);
  const save = useMutation({
    mutationFn: () => riskApi.editReport(id, text),
    onSuccess: () => { toast.success('Metin kaydedildi'); qc.invalidateQueries({ queryKey: ['risk', 'report', id] }); },
    onError: (e) => toast.error(errText(e, 'Kaydedilemedi.')),
  });
  const approve = useMutation({
    mutationFn: () => riskApi.approveReport(id),
    onSuccess: () => { toast.success('Brifing onaylandı'); setAsking(false); qc.invalidateQueries({ queryKey: ['risk'] }); },
    onError: (e) => toast.error(errText(e, 'Onaylanamadı.')),
  });
  if (q.isLoading) return <Panel><Loading /></Panel>;
  if (q.error) return <Panel><Note tone="err">{errText(q.error, 'Brifing okunamadı.')}</Note></Panel>;
  const r = q.data!;
  const editable = r.durum === 'taslak' && meta.me.canWrite && meta.me.seeAll;
  const dirty = text !== (r.metin ?? '');
  return (
    <Panel>
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <h2 className="flex items-center gap-1 text-[15px] font-extrabold tracking-tight">Risk brifingi {r.donem}<SqlInfo k={r.kaynaklar} alan="girdi" label="Brifingin dayandığı olgular" /></h2>
        <span className="flex flex-wrap gap-1.5">
          <Pill tone={r.kaynak === 'zeki' ? 'violet' : 'muted'}>{r.kaynak === 'zeki' ? 'Zeki AI taslağı' : r.kaynak === 'kural' ? 'Kural metni' : '—'}</Pill>
          {r.onaylayan && <Pill tone="ok">{r.onaylayan} onayladı</Pill>}
        </span>
      </div>
      {r.durum === 'hazirlaniyor' && <Note tone="info">Taslak hazırlanıyor…</Note>}
      {r.kaynakNotu && <Note tone="warn">{r.kaynakNotu}</Note>}
      {r.durum !== 'hazirlaniyor' && (
        editable ? (
          <textarea className={`${field} mt-2 min-h-[420px] font-mono text-[12.5px] leading-relaxed`} value={text} onChange={(e) => setText(e.target.value)} aria-label="Brifing metni" />
        ) : (
          <pre className="mt-2 max-h-[70vh] overflow-auto whitespace-pre-wrap break-words rounded-xl bg-white/80 p-3 font-canvas text-[12.5px] leading-relaxed">{r.metin ?? '—'}</pre>
        )
      )}
      <div className="mt-3 flex flex-wrap gap-2">
        {editable && <button type="button" className={btnGhost} disabled={!dirty || save.isPending} onClick={() => save.mutate()}>Metni kaydet</button>}
        {r.durum === 'taslak' && meta.me.canReportApprove && r.olusturan !== meta.me.username && (
          <button type="button" className={btnPrimary} disabled={dirty} onClick={() => setAsking(true)} title={dirty ? 'Önce metni kaydedin' : undefined}>
            <Check aria-hidden className="h-4 w-4" />Onayla
          </button>
        )}
        {meta.me.canExport && r.metin && <a className={btnGhost} href={riskApi.reportDocxUrl(id)}><Download aria-hidden className="h-4 w-4" />Word</a>}
      </div>
      <AskSheet open={asking} title="Brifingi onayla" message="Onaylanan metin kurul paketine gider; sonra düzenlenemez." confirm="Onayla"
        busy={approve.isPending} onClose={() => setAsking(false)} onConfirm={() => approve.mutate()} />
    </Panel>
  );
}
