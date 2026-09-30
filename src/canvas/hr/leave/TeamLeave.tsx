import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { AlertTriangle, ChevronLeft, ChevronRight } from 'lucide-react';
import { ENGINE_ENABLED } from '../../engine';
import { Loading, Note, Pill, btnGhost, btnPrimary, errText } from '../../admin/ui';
import { EmptyHint } from '../../components/Explain';
import { AskSheet, Block, HrFrame } from '../parts';
import { localIso, monthName } from '../portal/portalApi';
import { STATUS_TONE, gun, leaveApi, shortDay, span, type LeaveRequest, type Team } from './leaveApi';

/** Ekibimin izinleri (/ik/izin/ekip): yöneticisi olduğum kişilerin onay kuyruğu, ay takvimi, çakışma. Hassas izin türü
 *  (rapor, doğum) yalnız «İzin» diye görünür. */
export default function TeamLeave() {
  const qc = useQueryClient();
  const [month, setMonth] = useState(() => localIso(new Date()).slice(0, 7));
  const q = useQuery({ queryKey: ['hr', 'leave', 'team', month], queryFn: () => leaveApi.team(month), enabled: ENGINE_ENABLED });
  const [reject, setReject] = useState<LeaveRequest | null>(null);
  const refresh = () => void qc.invalidateQueries({ queryKey: ['hr', 'leave'] });
  const decide = useMutation({
    mutationFn: (v: { id: string; action: 'onayla' | 'reddet'; reason?: string }) => leaveApi.decide(v.id, v.action, v.reason),
    onSuccess: (r) => { setReject(null); toast.success(r.status === 'ik' ? 'Onaylandı; İK onayına gitti.' : r.status === 'onaylandi' ? 'İzin onaylandı.' : 'Talep reddedildi.'); refresh(); },
    onError: (e) => toast.error(errText(e, 'Kaydedilemedi.')),
    onSettled: () => setReject(null),
  });
  const shift = (n: number) => {
    const [y, m] = month.split('-').map(Number);
    const d = new Date(y, m - 1 + n, 1);
    setMonth(`${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`);
  };
  const t = q.data;
  return (
    <HrFrame crumb="Ekibimin izinleri" title="Ekibimin izinleri" back={{ to: '/ik/izin', label: 'İzinlerim' }}
      lead="Yöneticisi olduğunuz çalışanların izin talepleri ve ay takvimi. Onayladığınız izin çalışanın bakiyesinden düşer."
      aside={
        <div className="flex items-center justify-between gap-2 rounded-2xl bg-white/85 p-1.5">
          <button type="button" className={btnGhost} aria-label="Önceki ay" onClick={() => shift(-1)}><ChevronLeft aria-hidden className="h-4 w-4" /></button>
          <span className="text-[14px] font-extrabold">{monthName(Number(month.slice(5, 7)))} {month.slice(0, 4)}</span>
          <button type="button" className={btnGhost} aria-label="Sonraki ay" onClick={() => shift(1)}><ChevronRight aria-hidden className="h-4 w-4" /></button>
        </div>
      }>
      {q.error && <Note tone="err">{errText(q.error, 'Ekip bilgisi okunamadı.')}</Note>}
      {q.isLoading && <Loading />}
      {t && !t.linked && <EmptyHint title="Özlük kaydınız bağlı değil" why="Ekibinizi görmek için İK'nın portal hesabınızı özlük kaydınıza bağlaması gerekir." />}
      {t?.linked && !t.members.length && !t.queue.length && (
        <EmptyHint title="Size bağlı çalışan yok" why="Özlük kayıtlarında «Yöneticisi» alanı sizin personel numaranız olan çalışanlar burada görünür." />
      )}
      {t?.linked && (t.members.length > 0 || t.queue.length > 0) && (
        <>
          <Block title="Onayınızı bekleyenler" help={t.queue.length ? undefined : 'Bekleyen talep yok.'}>
            <ul className="flex flex-col gap-2">
              {t.queue.map((r) => (
                <li key={r.id} className="flex flex-col gap-2 rounded-xl bg-white/85 px-3 py-2 sm:flex-row sm:items-center sm:justify-between">
                  <div className="min-w-0">
                    <div className="text-[13px] font-bold">{r.adSoyad} · {r.typeLabel}</div>
                    <div className="text-[12px] text-canvas-muted">{span(r.start, r.end)} · {gun(r.days)}{r.deputy ? ` · vekil ${r.deputy}` : ''}</div>
                    {r.note && <div className="mt-0.5 whitespace-pre-line text-[12px]">{r.note}</div>}
                  </div>
                  <div className="flex shrink-0 gap-2">
                    <button type="button" className={btnGhost} disabled={decide.isPending} onClick={() => setReject(r)}>Reddet</button>
                    <button type="button" className={btnPrimary} disabled={decide.isPending} onClick={() => decide.mutate({ id: r.id, action: 'onayla' })}>Onayla</button>
                  </div>
                </li>
              ))}
            </ul>
          </Block>
          {t.conflicts.length > 0 && (
            <Note tone="warn">
              <AlertTriangle aria-hidden className="mr-1 inline h-4 w-4" />
              Ekibin %{t.conflictPct} ya da fazlasının izinli olduğu günler: {t.conflicts.map((c) => `${shortDay(c.day)} (${c.off}/${c.team})`).join(', ')}
            </Note>
          )}
          <Calendar t={t} />
          <Block title="Ekibin bakiyesi" help="Kullanılabilir yıllık izin (onay bekleyenler düşülmüş).">
            <ul className="grid grid-cols-1 gap-2 sm:grid-cols-2 xl:grid-cols-3">
              {t.members.map((m) => (
                <li key={m.id} className="flex items-center justify-between gap-2 rounded-xl bg-white/85 px-3 py-2 text-[12.5px]">
                  <span className="min-w-0"><span className="block truncate font-bold">{m.adSoyad}</span><span className="block truncate text-canvas-muted">{m.unvan || '—'}</span></span>
                  <span className="shrink-0 font-mono tabular-nums">{gun(m.balance)}</span>
                </li>
              ))}
            </ul>
          </Block>
        </>
      )}
      <AskSheet open={!!reject} title="Talebi reddet" danger confirm="Reddet" input="Gerekçe (çalışan görür)" required busy={decide.isPending}
        message={<>{reject ? `${reject.adSoyad} · ${span(reject.start, reject.end)}` : ''} talebi reddedilecek.</>}
        onClose={() => setReject(null)} onConfirm={(reason) => reject && decide.mutate({ id: reject.id, action: 'reddet', reason })} />
    </HrFrame>
  );
}

function Calendar({ t }: { t: Team }) {
  const byPerson = new Map<string, LeaveRequest[]>();
  t.requests.forEach((r) => byPerson.set(r.personId, [...(byPerson.get(r.personId) ?? []), r]));
  const cell = (pid: string, day: string) => (byPerson.get(pid) ?? []).find((r) => r.start <= day && day <= r.end);
  return (
    <Block title="Ay takvimi" help="Koyu: onaylı izin · açık: onay bekleyen. Gri sütun hafta sonu ya da resmî tatil.">
      {/* Telefon: kişi başına liste; geniş ekran: kişi × gün ızgarası (yalnız kendi kabında kayar). */}
      <ul className="flex flex-col gap-2 md:hidden">
        {t.members.map((m) => {
          const rs = byPerson.get(m.id) ?? [];
          return (
            <li key={m.id} className="rounded-xl bg-white/85 px-3 py-2 text-[12.5px]">
              <div className="font-bold">{m.adSoyad}</div>
              {rs.length ? rs.map((r) => (
                <div key={r.id} className="flex items-center justify-between gap-2 text-canvas-muted">
                  <span>{span(r.start, r.end)} · {r.typeLabel}</span><Pill tone={STATUS_TONE[r.status] ?? 'muted'}>{r.statusLabel}</Pill>
                </div>
              )) : <div className="text-canvas-muted">Bu ay izin yok</div>}
            </li>
          );
        })}
      </ul>
      <div className="hidden overflow-x-auto md:block">
        <table className="border-separate border-spacing-0 text-[11px]">
          <thead>
            <tr>
              <th className="sticky left-0 z-10 bg-white/95 px-2 py-1 text-left font-bold">Kişi</th>
              {t.days.map((d) => (
                <th key={d.day} className={`w-7 min-w-[28px] px-0 py-1 text-center font-mono font-normal ${d.weekday > 5 || d.holiday ? 'text-slate-400' : ''}`}>{Number(d.day.slice(8))}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {t.members.map((m) => (
              <tr key={m.id}>
                <td className="sticky left-0 z-10 max-w-[180px] truncate bg-white/95 px-2 py-1 font-bold">{m.adSoyad}</td>
                {t.days.map((d) => {
                  const r = cell(m.id, d.day);
                  const off = d.weekday > 5 || d.holiday;
                  return (
                    <td key={d.day} className={`h-7 border-l border-white p-0 ${off ? 'bg-slate-100' : ''}`}
                      title={r ? `${r.adSoyad}: ${r.typeLabel} · ${r.statusLabel}` : undefined}>
                      {r && <span className={`block h-5 rounded ${r.status === 'onaylandi' ? 'bg-canvas-violet' : 'bg-violet-200'}`} />}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Block>
  );
}
