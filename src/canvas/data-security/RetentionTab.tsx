import { useEffect, useMemo, useState } from 'react';
import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { ENGINE_ENABLED } from '../engine';
import { Note, Pill, TableWrap, btnGhost, btnPrimary, errText, field, td, th } from '../admin/ui';
import { Panel } from '../editorial/kit';
import { AskSheet } from '../budget/parts';
import { fmtAt, fmtDay, fmtN, securityApi, type RetentionObject, type SecurityMeta } from './api';
import SqlInfo from '../components/SqlInfo';
import { kaynakOf } from '../components/kaynakOf';
import { ExplainLabel } from '../components/Explain';

/** Saklama süreleri: her kayıt türü için süre, «bu süreyle kaç satır etkilenir» önizlemesi, uygulama anahtarı ve gece
 *  işinin kanıt satırları. Kapalıyken hiçbir kayıt silinmez; açmak `guvenlik.saklama` ister ve önizleme gösterilir. */
export default function RetentionTab({ meta }: { meta?: SecurityMeta }) {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ['security', 'retention'], queryFn: securityApi.retention, enabled: ENGINE_ENABLED });
  const can = !!meta?.me.canRetention;
  const [days, setDays] = useState<Record<string, string>>({});
  const [shown, setShown] = useState<RetentionObject[] | null>(null);
  const [ask, setAsk] = useState<null | 'on' | 'off'>(null);
  useEffect(() => {
    if (q.data) setDays(Object.fromEntries(q.data.objects.map((o) => [o.id, String(o.days)])));
  }, [q.data]);
  const parsed = useMemo(() => Object.fromEntries(Object.entries(days).map(([k, v]) => [k, Math.max(0, Number.parseInt(v, 10) || 0)])), [days]);
  const dirty = !!q.data && q.data.objects.some((o) => parsed[o.id] !== o.days);

  const preview = useMutation({
    mutationFn: () => securityApi.retentionPreview(parsed),
    onSuccess: (out) => setShown(out.objects),
    onError: (e) => toast.error(errText(e, 'Önizleme hesaplanamadı.') ?? ''),
  });
  const save = useMutation({
    mutationFn: (body: Parameters<typeof securityApi.saveRetention>[0]) => securityApi.saveRetention(body),
    onSuccess: (out) => {
      setAsk(null);
      setShown(null);
      qc.invalidateQueries({ queryKey: ['security'] });
      toast.success(out.apply ? 'Saklama süresi uygulanıyor; ilk silme bu gece çalışır.' : 'Kaydedildi.');
    },
    onError: (e) => toast.error(errText(e, 'Kaydedilemedi.') ?? ''),
  });
  const runs = useInfiniteQuery({
    queryKey: ['security', 'runs'],
    queryFn: ({ pageParam }) => securityApi.runs(pageParam),
    initialPageParam: null as number | null,
    getNextPageParam: (last) => (typeof last.next === 'number' ? last.next : undefined),
    enabled: ENGINE_ENABLED,
  });

  if (q.error) return <Note tone="err">{errText(q.error, 'Saklama süreleri okunamadı.')}</Note>;
  const d = q.data;
  if (!d) return <div className="py-10 text-center text-[12px] text-canvas-muted">Yükleniyor…</div>;
  const view = shown ?? d.objects;
  const total = view.reduce((s, o) => s + (o.rows ?? 0), 0);

  return (
    <>
      <Panel>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <h2 className="flex items-center gap-1 text-[16px] font-extrabold tracking-tight">
              Saklama süreleri
              <SqlInfo k={kaynakOf(q.data)} alan="objects" label="Süresi dolmuş satır" />
            </h2>
            <p className="max-w-[80ch] text-[12px] text-canvas-muted">
              Süresi dolan kayıt yalnız «uygula» açıkken ve her gece {d.dailyAt}'ten sonra işlenir; önce kaç satırın etkileneceği
              yazılır, sonra işlenen satır sayısı ve tarih aralığı. Zeki AI soru kaydında satır silinmez, yalnız cevapta dönen sonuç
              verisi boşaltılır. Önerilen süreler hukuk birimiyle teyit edilecektir.
            </p>
          </div>
          <div className="flex flex-col items-start gap-1.5 sm:items-end">
            <Pill tone={d.apply ? 'ok' : 'warn'}>{d.apply ? 'Uygulanıyor' : 'Yalnız önizleme — hiçbir şey silinmiyor'}</Pill>
            {d.apply && d.applyOn && <span className="text-[11px] text-canvas-muted">Açıldı: {fmtAt(d.applyOn)} · son başarılı iş {fmtAt(d.lastOk)}</span>}
            {can && (
              <button
                type="button"
                className={d.apply ? btnGhost : btnPrimary}
                disabled={dirty || save.isPending}
                title={dirty ? 'Önce süreleri kaydedin' : undefined}
                onClick={() => setAsk(d.apply ? 'off' : 'on')}
              >
                {d.apply ? 'Uygulamayı durdur' : 'Uygulamayı aç…'}
              </button>
            )}
          </div>
        </div>
        <div className="mt-3">
          <TableWrap>
            <thead>
              <tr className="border-b border-slate-100">
                <th className={th}>Kayıt</th>
                <th className={th}>
                  <ExplainLabel label="Süre (gün)">Kaydın kaç gün tutulacağı. 0 ya da boş: süresiz, hiç silinmez.</ExplainLabel>
                </th>
                <th className={`${th} text-right`}>
                  <ExplainLabel label="Süresi dolmuş satır">Bugünkü süreyle silinecek ya da boşaltılacak satır sayısı. Uygulama kapalıyken yalnız sayılır.</ExplainLabel>
                </th>
                <th className={th}>Tarih aralığı</th>
              </tr>
            </thead>
            <tbody>
              {view.map((o) => (
                <tr key={o.id} className="border-b border-slate-50 last:border-0">
                  <td className={`${td} max-w-[420px]`}>
                    <div className="font-bold">{o.label}</div>
                    <div className="break-words text-[11.5px] text-canvas-muted">{o.what}</div>
                  </td>
                  <td className={td}>
                    {can ? (
                      <input
                        aria-label={`${o.label} saklama süresi (gün)`}
                        inputMode="numeric"
                        className={`${field} w-24 font-mono tabular-nums`}
                        value={days[o.id] ?? ''}
                        onChange={(e) => { setDays({ ...days, [o.id]: e.target.value.replace(/\D/g, '') }); setShown(null); }}
                      />
                    ) : (
                      <span className="font-mono tabular-nums">{o.days || 'süresiz'}</span>
                    )}
                    <div className="text-[10.5px] text-canvas-muted">önerilen {o.defaultDays || 'süresiz'}</div>
                  </td>
                  <td className={`${td} text-right font-mono tabular-nums`}>
                    {o.error ? <span className="text-[11px] text-red-700">{o.error}</span> : o.days ? fmtN(o.rows) : '—'}
                  </td>
                  <td className={`${td} whitespace-nowrap text-[11.5px]`}>{o.rows ? `${fmtDay(o.from)} – ${fmtDay(o.to)}` : o.days ? `${fmtDay(o.cutoff)} öncesi` : 'süresiz'}</td>
                </tr>
              ))}
            </tbody>
          </TableWrap>
        </div>
        {can && (
          <div className="mt-3 flex flex-wrap gap-2">
            <button type="button" className={btnGhost} disabled={!dirty || preview.isPending} onClick={() => preview.mutate()}>
              {preview.isPending ? 'Hesaplanıyor…' : 'Bu sürelerle önizle'}
            </button>
            <button type="button" className={btnPrimary} disabled={!dirty || save.isPending} onClick={() => save.mutate({ days: parsed })}>
              Süreleri kaydet
            </button>
            {shown && <span className="self-center text-[12px] text-canvas-muted">Önizleme: yeni sürelerle {fmtN(total)} satır etkilenir (kaydedilmedi).</span>}
          </div>
        )}
      </Panel>

      <Panel>
        <h2 className="text-[16px] font-extrabold tracking-tight">Gece işinin kaydı</h2>
        <p className="text-[12px] text-canvas-muted">Saklama işinin her gece ne yaptığı: «önizleme» satırında yalnız sayıldı, «uygulandı» satırında gerçekten silindi ya da boşaltıldı.</p>
        {runs.error && <div className="mt-2"><Note tone="err">{errText(runs.error, 'Kanıt satırları okunamadı.')}</Note></div>}
        <div className="mt-3">
          <TableWrap>
            <thead>
              <tr className="border-b border-slate-100">
                <th className={th}>Zaman</th>
                <th className={th}>Kayıt</th>
                <th className={th}>Tür</th>
                <th className={`${th} text-right`}>Satır</th>
                <th className={th}>Aralık</th>
                <th className={th}>Sonuç</th>
              </tr>
            </thead>
            <tbody>
              {(runs.data?.pages.flatMap((p) => p.items) ?? []).map((r) => (
                <tr key={r.id} className="border-b border-slate-50 last:border-0">
                  <td className={`${td} whitespace-nowrap`}>{fmtAt(r.at)}</td>
                  <td className={td}>{r.objectLabel}</td>
                  <td className={td}><Pill tone={r.mode === 'uygulama' ? 'violet' : 'muted'}>{r.mode === 'uygulama' ? 'uygulandı' : 'önizleme'}</Pill></td>
                  <td className={`${td} text-right font-mono tabular-nums`}>{r.days ? fmtN(r.rows) : '—'}</td>
                  <td className={`${td} whitespace-nowrap text-[11.5px]`}>{r.rows ? `${fmtDay(r.from)} – ${fmtDay(r.to)}` : '—'}</td>
                  <td className={td}>{r.ok ? <Pill tone="ok">tamam</Pill> : <span className="text-[11px] text-red-700">{r.error}</span>}</td>
                </tr>
              ))}
              {runs.data && !runs.data.pages[0].items.length && <tr><td className={td} colSpan={6}>Gece işi henüz çalışmadı.</td></tr>}
            </tbody>
          </TableWrap>
        </div>
        {runs.hasNextPage && (
          <div className="mt-3 flex justify-center">
            <button type="button" className={btnGhost} disabled={runs.isFetchingNextPage} onClick={() => runs.fetchNextPage()}>Daha eski kayıtlar</button>
          </div>
        )}
      </Panel>

      <AskSheet
        open={ask === 'on'}
        title="Saklama süresini uygula"
        message={
          <div className="space-y-2">
            <p>Açılırsa bu gece {d.dailyAt}'ten sonra aşağıdaki kayıtlar kalıcı olarak işlenir (boşaltılır ya da silinir). Geri alınamaz.</p>
            <ul className="space-y-1">
              {d.objects.filter((o) => o.days > 0).map((o) => (
                <li key={o.id} className="flex justify-between gap-3 text-[12.5px]">
                  <span>{o.label} · {o.days} günden eski</span>
                  <span className="font-mono font-bold tabular-nums">{fmtN(o.rows)} satır</span>
                </li>
              ))}
            </ul>
          </div>
        }
        confirm="Uygulamayı aç"
        danger
        busy={save.isPending}
        onClose={() => setAsk(null)}
        onConfirm={() => save.mutate({ apply: true, onizlemeGoruldu: true })}
      />
      <AskSheet
        open={ask === 'off'}
        title="Uygulamayı durdur"
        message={<p>Gece işi yalnız önizleme yazmaya döner; hiçbir kayıt silinmez.</p>}
        confirm="Uygulamayı durdur"
        busy={save.isPending}
        onClose={() => setAsk(null)}
        onConfirm={() => save.mutate({ apply: false })}
      />
    </>
  );
}
