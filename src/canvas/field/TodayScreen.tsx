import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Bell, CalendarPlus, NotebookPen, Search, Sparkles } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import { Loading, Note, btnGhost, errText, field } from '../admin/ui';
import { trFold } from '../nav/navModel';
import { fieldApi, fmtDay, fmtMoney, fmtPct, fmtShort, type FieldMeta, type Visit } from './api';
import { CustomerRow, Empty, Stat } from './parts';
import VisitNoteSheet from './VisitNoteSheet';

/** «Bugün» (telefonun ilk ekranı): üstte 3 sayı, bugün planlanan ziyaretler, sonra kural puanıyla sıralı müşteri listesi
 *  (gerekçe çipleriyle). Sıralamayı temsilci ziyaret planlayarak değiştirir; müdür önceliği gerekçesiyle üste çıkarır. */

const STEP = 40;

export default function TodayTab({ meta, temsilci }: { meta: FieldMeta; temsilci: string }) {
  const qc = useQueryClient();
  const [q, setQ] = useState('');
  const [shown, setShown] = useState(STEP);
  const [sheet, setSheet] = useState<null | { code: string; unvan: string | null; mode: 'not' | 'plan'; visit?: Visit | null }>(null);
  const today = useQuery({ queryKey: ['field', 'today', temsilci], queryFn: () => fieldApi.today(temsilci || undefined), enabled: ENGINE_ENABLED });
  const seen = useMutation({ mutationFn: fieldApi.seen, onSuccess: () => void qc.invalidateQueries({ queryKey: ['field', 'today'] }) });
  const t = today.data;

  const items = useMemo(() => {
    const all = t?.items ?? [];
    const f = trFold(q.trim());
    return f ? all.filter((c) => trFold(`${c.unvan ?? ''} ${c.code} ${c.il ?? ''}`).includes(f)) : all;
  }, [t, q]);
  const unseen = (t?.events ?? []).filter((e) => !e.goruldu);
  const canNote = meta.me.canNote;

  if (today.isLoading) return <Loading />;
  const err = errText(today.error, 'Bugünün listesi okunamadı.');
  if (err) return <Note tone="err">{err}</Note>;
  if (!t) return null;

  return (
    <div className="flex flex-col gap-3">
      {t.warning && <Note tone="warn">{t.warning}</Note>}
      <div className="grid grid-cols-3 gap-2">
        <Stat label="Vadesi geçmiş" value={fmtShort(t.kpi.vadesiGecmis)} help={`90+ gün ${fmtShort(t.kpi.k90)}`} tone={t.kpi.k90 > 0 ? 'err' : undefined} />
        <Stat label="Onay bekleyen" value={String(t.kpi.onayBekleyen)} help={`CRM tahsilatı · ${fmtShort(t.kpi.onayBekleyenTutar)}`} tone={t.kpi.onayBekleyen ? 'warn' : undefined} />
        <Stat label="Hedef oranı" value={fmtPct(t.kpi.hedefOrani)} help="Yıl başından, beklenene göre" />
      </div>

      {unseen.length > 0 && (
        <section className="rounded-2xl border border-amber-200 bg-amber-50/80 p-3" aria-label="Bildirimler">
          <div className="flex items-center justify-between gap-2">
            <div className="flex items-center gap-1.5 text-[12.5px] font-extrabold text-amber-900">
              <Bell aria-hidden className="h-4 w-4" />
              {unseen.length} yeni bildirim
            </div>
            <button type="button" className={`${btnGhost} !min-h-9 !bg-white/70`} onClick={() => seen.mutate()} disabled={seen.isPending}>
              Gördüm
            </button>
          </div>
          <ul className="mt-2 flex flex-col gap-1.5">
            {unseen.map((e) => (
              <li key={e.id} className="text-[12px] leading-snug">
                {e.code ? (
                  <Link to={`/saha/musteri/${encodeURIComponent(e.code)}`} className="font-bold text-amber-950 underline-offset-2 hover:underline">
                    {e.baslik}
                  </Link>
                ) : (
                  <span className="font-bold">{e.baslik}</span>
                )}
                {e.detay && <span className="text-amber-900"> — {e.detay}</span>}
              </li>
            ))}
          </ul>
        </section>
      )}

      <section aria-label="Bugün planlanan ziyaretler" className="flex flex-col gap-2">
        <h2 className="px-1 text-[15px] font-extrabold tracking-tight">Bugün planlanan ({t.planned.length})</h2>
        {t.planned.length === 0 ? (
          <Empty>Bugün için planlanmış ziyaret yok. Listeden bir müşteriyi «Planla» ile bugüne alabilirsiniz.</Empty>
        ) : (
          <ul className="flex flex-col gap-2">
            {t.planned.map((v) =>
              v.musteri ? (
                <CustomerRow
                  key={v.id}
                  c={v.musteri}
                  trailing={
                    canNote && v.durum === 'planlandi' ? (
                      <button
                        type="button"
                        aria-label={`${v.musteri.unvan ?? v.hedef} için not bırak`}
                        className={`${btnGhost} !min-h-14 !w-14 !px-0`}
                        onClick={() => setSheet({ code: v.hedef, unvan: v.musteri?.unvan ?? v.hedefAd, mode: 'not', visit: v })}
                      >
                        <NotebookPen aria-hidden className="h-5 w-5" />
                      </button>
                    ) : (
                      <span className="flex w-14 items-center justify-center rounded-2xl bg-emerald-50 text-[10.5px] font-extrabold text-emerald-700">Yapıldı</span>
                    )
                  }
                />
              ) : (
                <li key={v.id} className="rounded-2xl border border-slate-100 bg-white/85 p-3 text-[12.5px]">
                  {v.hedefAd || v.hedef} · {v.durumAd}
                </li>
              ),
            )}
          </ul>
        )}
      </section>

      <section aria-label="Öncelik listesi" className="flex flex-col gap-2">
        <div className="flex flex-wrap items-end justify-between gap-2 px-1">
          <div>
            <h2 className="text-[15px] font-extrabold tracking-tight">Öncelik sırası ({items.length})</h2>
            <p className="text-[11.5px] text-canvas-muted">
              Veri {fmtDay(t.asof)} sabahı · Logo {fmtDay(t.dataEnd)} tarihine kadar
            </p>
          </div>
          <label className="relative w-full sm:w-64">
            <span className="sr-only">Müşteri ara</span>
            <Search aria-hidden className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-canvas-muted" />
            <input className={`${field} pl-9`} value={q} placeholder="Unvan, cari kodu, il" onChange={(e) => { setQ(e.target.value); setShown(STEP); }} />
          </label>
        </div>
        {items.length === 0 ? (
          <Empty>
            {t.kpi.cari === 0
              ? meta.run.asof
                ? 'CRM\'de size atanmış (sahibi siz olan ya da ilinizin temsilcisi olduğunuz) müşteri carisi yok.'
                : 'Saha verisi henüz hazırlanmadı; ilk gece turundan sonra liste dolar.'
              : 'Aramaya uyan müşteri yok.'}
          </Empty>
        ) : (
          <ul className="flex flex-col gap-2">
            {items.slice(0, shown).map((c) => (
              <CustomerRow
                key={c.code}
                c={c}
                showRep={meta.me.canAll && !temsilci}
                trailing={
                  canNote ? (
                    <button
                      type="button"
                      aria-label={`${c.unvan ?? c.code} ziyaretini planla`}
                      className={`${btnGhost} !min-h-14 !w-14 !flex-col !gap-0.5 !px-0 !text-[10px]`}
                      onClick={() => setSheet({ code: c.code, unvan: c.unvan, mode: 'plan' })}
                    >
                      <CalendarPlus aria-hidden className="h-5 w-5" />
                      Planla
                    </button>
                  ) : undefined
                }
              />
            ))}
          </ul>
        )}
        {items.length > shown && (
          <button type="button" className={`${btnGhost} w-full`} onClick={() => setShown((s) => s + STEP)}>
            {Math.min(STEP, items.length - shown)} müşteri daha göster (kalan {items.length - shown})
          </button>
        )}
      </section>

      <details className="rounded-2xl border border-slate-100 bg-white/70 p-3 text-[12px]">
        <summary className="min-h-8 cursor-pointer font-extrabold">Sıra nasıl belirleniyor?</summary>
        <p className="mt-2 leading-snug text-canvas-muted">
          Puan kuraldır, model vermez. Her bileşenin en çok puanı yanında; toplam 100'de kesilir. Vadesi geçmiş alacak yaşa göre
          ağırlıklıdır ve sizin portföyünüzdeki sırasına göre puanlanır. Tutarlar yaklaşıktır: Logo'da ödeme kapama kullanılmadığı için
          bakiye en yeni vadelerden geriye dağıtılır (FIFO).
        </p>
        <ul className="mt-2 grid gap-1 sm:grid-cols-2">
          {meta.weights.map((w) => (
            <li key={w.key} className="flex justify-between gap-2 border-b border-slate-100 py-1">
              <span className="min-w-0">{w.label}</span>
              <span className="shrink-0 font-mono font-bold tabular-nums">{w.max}</span>
            </li>
          ))}
        </ul>
        {meta.run.target?.kaynak && (
          <p className="mt-2 leading-snug text-canvas-muted">
            Hedef: {meta.run.target.kaynak === 'm46'
              ? `yürürlükteki bütçe planı (${fmtMoney(meta.run.target.toplamHedef)}) carilere önceki yılın net alım payıyla dağıtılır; cari hedeflerinin toplamı planın toplamına eşittir.`
              : 'CRM\'deki cari yıl hedefi; beklenen takvim günü oranıyla.'}
          </p>
        )}
      </details>

      <section className="rounded-2xl border border-slate-100 bg-white/70 p-3" aria-label="Zeki AI'ya sor">
        <div className="flex items-center gap-1.5 text-[12.5px] font-extrabold">
          <Sparkles aria-hidden className="h-4 w-4 text-canvas-violet" />
          Zeki AI'ya sorun
        </div>
        <div className="mt-2 flex flex-wrap gap-1.5">
          {meta.zekiQuestions.map((s) => (
            <Link
              key={s}
              to={`/genel-bakis?soru=${encodeURIComponent(s)}`}
              className="inline-flex min-h-9 items-center rounded-xl bg-canvas-violet/10 px-2.5 text-[12px] font-bold text-canvas-violet transition-transform duration-150 ease-out active:scale-[0.97]"
            >
              {s}
            </Link>
          ))}
        </div>
      </section>

      {sheet && (
        <VisitNoteSheet open onClose={() => setSheet(null)} code={sheet.code} unvan={sheet.unvan} mode={sheet.mode} visit={sheet.visit} />
      )}
    </div>
  );
}
