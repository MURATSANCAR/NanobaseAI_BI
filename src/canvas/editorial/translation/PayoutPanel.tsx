import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ArrowRightLeft, BriefcaseBusiness, Loader2 } from 'lucide-react';
import {
  ENGINE_ENABLED,
  translationPayoutApi,
  type FlPayoutHead,
  type FlTaskStatus,
  type PayoutBasis,
  type TranslationJobDetail,
} from '../../engine';
import { Loading, Note, Pill, btn, btnGhost, errText, field, label, nf } from '../../admin/ui';
import { canSeePage, usePageAccess } from '../../useAdmin';
import { Panel } from '../kit';
import { PAYOUT_STATUS, TASK_STATUS, day, editNum, parseNum, stamp, tl } from '../freelance/shared';
import SqlInfo from '../../components/SqlInfo';
import { kaynakOf } from '../../components/kaynakOf';

/** Çeviri işinin serbest çalışan tarafı (M4 → M8): çevirmenin M8 kaydı, kelime ücreti ve hakediş esası; M8'de iş
 *  paketi ve hakedişe aktarım. Aktarım yalnız son aktarımdan sonra onaylanan (ya da çevrilen) kelimeyi gönderir;
 *  hakediş belgesi M8 Serbest çalışanlar › Hakediş'te hazırlanır. */

export default function PayoutPanel({ job }: { job: TranslationJobDetail }) {
  const qc = useQueryClient();
  const access = usePageAccess();
  const canOpenM8 = canSeePage(access, 'serbest-calisanlar');
  const q = useQuery({
    // İlerleme değişince (segment onayı) aktarılacak kelime de değişir.
    queryKey: ['translation', 'payout', job.id, job.words.approved, job.words.done, job.words.total],
    queryFn: () => translationPayoutApi.get(job.id),
    enabled: ENGINE_ENABLED,
  });
  const d = q.data;
  const [personId, setPersonId] = useState('');
  const [rate, setRate] = useState('');
  const [basis, setBasis] = useState<PayoutBasis>('onaylanan');
  const [notice, setNotice] = useState<string | null>(null);
  useEffect(() => {
    if (!d) return;
    setPersonId(d.link?.personId ?? '');
    setRate(d.link ? editNum(d.link.rate) : '');
    setBasis(d.link?.basis ?? 'onaylanan');
    // Yalnız kayıtlı bağ değişince forma yazılır; kişinin yazdığı ezilmez.
  }, [d?.link?.personId, d?.link?.rate, d?.link?.basis]); // eslint-disable-line react-hooks/exhaustive-deps

  const refresh = async () => {
    await qc.invalidateQueries({ queryKey: ['translation', 'payout', job.id] });
    await qc.invalidateQueries({ queryKey: ['fl'] });
  };
  const rateNum = parseNum(rate);
  const save = useMutation({
    mutationFn: () => translationPayoutApi.save(job.id, { personId, rate: String(rateNum), basis }),
    onSuccess: async () => {
      setNotice(null);
      await refresh();
    },
  });
  const pkg = useMutation({
    mutationFn: () => translationPayoutApi.openPackage(job.id),
    onSuccess: async (r) => {
      setNotice(
        r.created
          ? `M8'de iş paketi açıldı: ${nf.format(r.units)} kelimelik görev çevirmene atandı.`
          : `M8'deki görev güncellendi (${nf.format(r.units)} kelime).`,
      );
      await refresh();
    },
  });
  const move = useMutation({
    mutationFn: () => translationPayoutApi.transfer(job.id),
    onSuccess: async (r) => {
      setNotice(
        r.moved
          ? `${nf.format(r.moved)} kelime (${tl(r.amount)}) M8'de kabul edilmiş işe dönüştü; hakediş belgesi Serbest çalışanlar › Hakediş'te hazırlanır.`
          : 'Aktarılacak yeni kelime yok.',
      );
      await refresh();
    },
  });

  if (!d) return <Panel>{q.error ? <Note tone="err">{errText(q.error, 'Hakediş bilgisi okunamadı.')}</Note> : <Loading />}</Panel>;

  const link = d.link;
  const people = [...d.people];
  if (link && !people.some((p) => p.id === link.personId)) {
    // Pasif ya da çeviri rolü kaldırılmış kişi: seçili kalsın, listede görünsün.
    people.unshift({ id: link.personId, name: `${link.personName ?? 'Kayıtlı kişi'} (pasif)`, city: null, email: null, rate: null });
  }
  const dirty = !link || personId !== link.personId || basis !== link.basis || rateNum !== link.rate;
  const rateOk = Number.isFinite(rateNum) && rateNum > 0;
  const task = d.task;
  const busy = save.isPending || pkg.isPending || move.isPending;
  const err = errText(save.error || pkg.error || move.error, 'İşlem yapılamadı.');
  const pending = link?.pending ?? 0;
  const canTransfer = !!link && !dirty && !!(task || d.package) && pending > 0;

  return (
    <Panel>
      <h3 className="flex items-center gap-1 px-1 text-[13px] font-extrabold">
        Serbest çalışan ve hakediş
        {d && <SqlInfo k={kaynakOf(d)} alan="_hepsi" label="Hakediş kelimesi ve tutarı" />}
      </h3>
      <p className="mt-0.5 px-1 text-[11.5px] leading-snug text-canvas-muted">
        Dışarıdan çalışan çevirmenin emeği Serbest çalışanlar ekranında iş paketi ve hakediş olur. Ödenecek kelime inceleyenin onayladığı (ya da
        çevrilen) segmentlerden hesaplanır; her aktarımda yalnız son aktarımdan sonraki kelimeler gider. Tutarlar brüt, KDV hariçtir.
      </p>

      {!d.people.length && (
        <div className="mt-2.5">
          <Note tone="info">
            Serbest çalışanlarda çeviri rolünde kayıtlı aktif kişi yok.{' '}
            {canOpenM8 && (
              <Link to="/serbest-calisanlar?bolum=kisiler" className="underline">
                Kişi ekleyin
              </Link>
            )}
          </Note>
        </div>
      )}

      <form
        className="mt-2.5 grid gap-2.5 sm:grid-cols-3"
        onSubmit={(e) => {
          e.preventDefault();
          if (personId && rateOk && dirty && !busy) save.mutate();
        }}
      >
        <label className="block min-w-0">
          <span className={label}>Serbest çalışan</span>
          <select
            value={personId}
            className={`${field} mt-1`}
            onChange={(e) => {
              const next = people.find((p) => p.id === e.target.value);
              const prev = people.find((p) => p.id === personId);
              // Ücret boşsa ya da önceki kişinin kart ücretiyse yeni kişinin kart ücreti gelir.
              if (next?.rate != null && (!rate || (prev?.rate != null && parseNum(rate) === prev.rate))) setRate(editNum(next.rate));
              setPersonId(e.target.value);
            }}
          >
            <option value="">Seçin</option>
            {people.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
                {p.city ? ` · ${p.city}` : ''}
              </option>
            ))}
          </select>
        </label>
        <label className="block min-w-0">
          <span className={label}>Kelime ücreti (₺)</span>
          <input value={rate} inputMode="decimal" placeholder="0,45" onChange={(e) => setRate(e.target.value)} className={`${field} mt-1 font-mono tabular-nums`} />
        </label>
        <label className="block min-w-0">
          <span className={label}>Hakediş esası</span>
          <select value={basis} onChange={(e) => setBasis(e.target.value as PayoutBasis)} className={`${field} mt-1`}>
            {(Object.keys(d.bases) as PayoutBasis[]).map((k) => (
              <option key={k} value={k}>
                {d.bases[k]}
              </option>
            ))}
          </select>
        </label>
        <div className="flex flex-wrap items-center gap-2 sm:col-span-3">
          <button type="submit" disabled={!personId || !rateOk || !dirty || busy} className={`${btn} bg-canvas-violet text-white`}>
            {save.isPending ? <Loader2 aria-hidden className="h-4 w-4 animate-spin" /> : null}
            Kaydet
          </button>
          {rate && !rateOk && <span className="text-[11.5px] font-semibold text-amber-700">Ücret sıfırdan büyük bir sayı olmalı.</span>}
          {link && !dirty && (
            <span className="text-[11.5px] text-canvas-muted">
              Son değişiklik {link.updatedBy}, {stamp(link.updatedAt)}
            </span>
          )}
        </div>
      </form>

      {link && (
        <>
          <dl className="mt-3 grid grid-cols-2 gap-2 rounded-2xl border border-slate-100 bg-white/85 p-3 text-[11.5px] sm:grid-cols-4">
            <div>
              <dt className="text-canvas-muted">{d.bases[link.basis]}</dt>
              <dd className="font-mono text-[14px] font-bold tabular-nums">{nf.format(link.basisWords)}</dd>
            </div>
            <div>
              <dt className="text-canvas-muted">Aktarılan</dt>
              <dd className="font-mono text-[14px] font-bold tabular-nums">{nf.format(link.transferred)}</dd>
              <dd className="text-canvas-muted">{tl(link.transferredAmount)}</dd>
            </div>
            <div>
              <dt className="text-canvas-muted">Aktarılacak</dt>
              <dd className="font-mono text-[14px] font-bold tabular-nums">{nf.format(pending)}</dd>
              <dd className="text-canvas-muted">{tl(link.pendingAmount)}</dd>
            </div>
            <div className="min-w-0">
              <dt className="text-canvas-muted">Görev</dt>
              <dd className="mt-0.5">
                {task ? (
                  <Pill tone={TASK_STATUS[task.status as FlTaskStatus]?.tone ?? 'muted'}>{TASK_STATUS[task.status as FlTaskStatus]?.label ?? task.status}</Pill>
                ) : (
                  <Pill tone="muted">Açılmadı</Pill>
                )}
              </dd>
              {task?.open && (
                <dd className="mt-0.5 text-canvas-muted">
                  {nf.format(task.units)} kelime{task.due ? ` · termin ${day(task.due)}` : ''}
                </dd>
              )}
            </div>
          </dl>

          {!link.personActive && (
            <div className="mt-2">
              <Note tone="warn">{link.personName ?? 'Seçili kişi'} Serbest çalışanlarda pasif; yeni iş atanamaz.</Note>
            </div>
          )}
          {link.ahead > 0 && (
            <div className="mt-2">
              <Note tone="warn">
                Esas kelime aktarılandan {nf.format(link.ahead)} kelime az (yeni kaynak sürümü onayları düşürmüş olabilir). Aktarılan geri alınmaz; yeni
                onaylar önce bu farkı kapatır.
              </Note>
            </div>
          )}

          <div className="mt-2.5 flex flex-wrap gap-2">
            <button
              type="button"
              disabled={busy || dirty || !job.words.total}
              onClick={() => pkg.mutate()}
              className={task?.open ? btnGhost : `${btn} bg-canvas-violet text-white`}
            >
              {pkg.isPending ? <Loader2 aria-hidden className="h-4 w-4 animate-spin" /> : <BriefcaseBusiness aria-hidden className="h-4 w-4" />}
              {task?.open ? 'İş paketini güncelle' : 'İş paketi aç'}
            </button>
            <button
              type="button"
              disabled={busy || !canTransfer}
              onClick={() => {
                if (window.confirm(`${nf.format(pending)} kelime × ${tl(link.rate)} = ${tl(link.pendingAmount)} Serbest çalışanlarda ödenecek işlere aktarılsın mı?`))
                  move.mutate();
              }}
              className={`${btn} bg-canvas-mint/15 text-emerald-700`}
            >
              {move.isPending ? <Loader2 aria-hidden className="h-4 w-4 animate-spin" /> : <ArrowRightLeft aria-hidden className="h-4 w-4" />}
              Hakedişe aktar ({nf.format(pending)} kelime)
            </button>
          </div>
          {!job.words.total && <p className="mt-1.5 px-1 text-[11.5px] text-canvas-muted">İş paketi kaynak yüklenince açılır; miktar kaynağın kelimesidir.</p>}
          {dirty && <p className="mt-1.5 px-1 text-[11.5px] text-canvas-muted">Önce değişikliği kaydedin.</p>}

          {d.package && canOpenM8 && (
            <p className="mt-2 px-1 text-[12px] leading-snug">
              <Link to={`/serbest-calisanlar?bolum=paketler&paket=${encodeURIComponent(d.package.id)}`} className="break-words font-bold text-canvas-violet underline">
                {d.package.title}
              </Link>
              {' · '}
              <Link to="/serbest-calisanlar?bolum=hakedis" className="font-bold text-canvas-violet underline">
                Hakediş
              </Link>
            </p>
          )}

          {d.moves.length > 0 && (
            <div className="mt-3">
              <h4 className="px-1 text-[12px] font-extrabold">Aktarımlar</h4>
              <ul className="mt-1.5 space-y-1.5">
                {d.moves.map((m) => (
                  <li key={m.id} className="flex flex-wrap items-center justify-between gap-x-2 gap-y-1 rounded-xl border border-slate-100 bg-white/85 px-3 py-2 text-[12px]">
                    <span className="min-w-0">
                      <span className="font-mono font-bold tabular-nums">{nf.format(m.words)} kelime</span>
                      <span className="text-canvas-muted">
                        {' '}
                        · {tl(m.amount)} · {m.by}, {stamp(m.at)}
                      </span>
                    </span>
                    {m.payout ? (
                      <Pill tone={PAYOUT_STATUS[m.payout.status as FlPayoutHead['status']]?.tone ?? 'muted'}>
                        Hakediş #{m.payout.no} · {PAYOUT_STATUS[m.payout.status as FlPayoutHead['status']]?.label ?? m.payout.status}
                      </Pill>
                    ) : (
                      <Pill tone="violet">Ödenecek işlerde</Pill>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </>
      )}

      {!link && d.people.length > 0 && (
        <p className="mt-2 px-1 text-[11.5px] text-canvas-muted">
          Kişiyi ve kelime ücretini kaydedince iş paketi açılabilir. Kaynak {nf.format(d.words.total)} kelime.
        </p>
      )}
      {notice && (
        <div className="mt-2">
          <Note tone="ok">{notice}</Note>
        </div>
      )}
      {err && (
        <div className="mt-2">
          <Note tone="err">{err}</Note>
        </div>
      )}
    </Panel>
  );
}
