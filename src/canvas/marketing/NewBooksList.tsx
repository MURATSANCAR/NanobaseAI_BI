import { Link } from 'react-router-dom';
import { Loader2, Sparkles } from 'lucide-react';
import { Pill, TableWrap, btnGhost, btnPrimary, td, th } from '../admin/ui';
import { STATUS_TONE, fmtInt, fmtMoney, fmtShortDay, type BookRow, type Meta } from './api';
import { DaysLeft } from './parts';
import SqlInfo, { InfoLabel } from '../components/SqlInfo';
import type { Kaynaklar } from '../components/sqlInfo';

/** Plan bekleyen / planlı yeni kitaplar. Masaüstünde tablo, telefonda kart; sayfalama üst bileşende (tavan yok). */
export default function NewBooksList({ rows, meta, busy, k, onCreate }: {
  rows: BookRow[];
  meta: Meta;
  busy: string | null;
  k?: Kaynaklar;
  onCreate: (stok: string, withAi: boolean) => void;
}) {
  const me = meta.me;
  const src = (k: string) => meta.dateSources[k] ?? k;
  const materials = (r: BookRow) =>
    r.plan && r.plan.eksikMateryal.length ? `Eksik: ${r.plan.eksikMateryal.map((t) => meta.materials[t] ?? t).join(', ')}` : null;

  const action = (r: BookRow, full: boolean) => {
    if (r.plan) {
      return (
        <Link to={`/pazarlama/plan/${encodeURIComponent(r.plan.id)}`} className={`${btnGhost} ${full ? 'w-full' : ''}`}>
          Planı aç
        </Link>
      );
    }
    if (!me.canWrite) return <span className="text-[11.5px] text-canvas-muted">Plan yok</span>;
    const pending = busy === r.stokKodu;
    return (
      <div className={`flex gap-1.5 ${full ? 'w-full' : ''}`}>
        <button type="button" className={`${btnPrimary} ${full ? 'flex-1' : ''}`} disabled={!!busy} onClick={() => onCreate(r.stokKodu, true)}>
          {pending ? <Loader2 aria-hidden className="h-4 w-4 animate-spin" /> : <Sparkles aria-hidden className="h-4 w-4" />}
          Zeki AI taslağı
        </button>
        <button type="button" className={btnGhost} disabled={!!busy} onClick={() => onCreate(r.stokKodu, false)}>
          Boş plan
        </button>
      </div>
    );
  };

  return (
    <>
      {/* Telefon: kart görünümü */}
      <ul className="flex flex-col gap-2 sm:hidden">
        {rows.map((r) => (
          <li key={r.stokKodu} className="rounded-2xl border border-slate-100 bg-white/85 p-3">
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0">
                <div className="break-words text-[14px] font-extrabold leading-snug">{r.ad ?? r.stokKodu}</div>
                <div className="mt-0.5 text-[11.5px] text-canvas-muted">{[r.yazar, r.yayinevi].filter(Boolean).join(' · ') || '—'}</div>
              </div>
              <span className="flex shrink-0 items-center gap-0.5"><DaysLeft days={r.kalanGun} /><SqlInfo k={k} alan="items[].kalanGun" label="Kalan gün" /></span>
            </div>
            <div className="mt-2 flex flex-wrap items-center gap-1.5 text-[11.5px]">
              <span className="font-semibold">{fmtShortDay(r.yayinTarihi)}</span>
              <span className="text-canvas-muted">({src(r.yayinKaynagi)})</span>
              {r.plan ? <Pill tone={STATUS_TONE[r.plan.durum]}>{r.plan.durumAdi}</Pill> : <Pill tone="err">Plan yok</Pill>}
              {r.plan?.hedefDegisti && <Pill tone="warn">Hedef değişti</Pill>}
            </div>
            <div className="mt-1 text-[11.5px] text-canvas-muted">
              Hedef: {r.hedef ? `${fmtInt(r.hedef.adet)} adet${me.canSeeBudget ? ` · ${fmtMoney(r.hedef.ciro)}` : ''}` : 'onaylı hedef yok'}
              {me.canSeeBudget && r.plan ? ` · Bütçe ${fmtMoney(r.plan.butce)}` : ''}
              <SqlInfo k={k} alan="items[].hedef" label="Hedef" className="ml-0.5" />
              {me.canSeeBudget && r.plan && <SqlInfo k={k} alan="items[].plan" label="Plan bütçesi" className="ml-0.5" />}
            </div>
            {materials(r) && <div className="mt-1 text-[11.5px] font-semibold text-amber-800">{materials(r)}</div>}
            <div className="mt-2.5">{action(r, true)}</div>
          </li>
        ))}
      </ul>

      {/* Masaüstü: tablo */}
      <div className="hidden sm:block">
        <TableWrap>
          <thead>
            <tr className="border-b border-slate-100">
              <th className={th}>Kitap</th>
              <th className={th}>Yayın</th>
              <th className={th}><InfoLabel k={k} alan="items[].kalanGun">Kalan</InfoLabel></th>
              <th className={th}><InfoLabel k={k} alan="items[].hedef">Hedef</InfoLabel></th>
              <th className={th}>Plan</th>
              {me.canSeeBudget && <th className={`${th} text-right`}><InfoLabel k={k} alan="items[].plan">Bütçe</InfoLabel></th>}
              <th className={th}>Sorumlu</th>
              <th className={th} aria-label="İşlem" />
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.stokKodu} className="border-b border-slate-50 last:border-0">
                <td className={td}>
                  <div className="max-w-[340px] font-bold leading-snug">{r.ad ?? r.stokKodu}</div>
                  <div className="text-[11px] text-canvas-muted">
                    {[r.yazar, r.yayinevi, r.kitaplik].filter(Boolean).join(' · ')} · <span className="font-mono">{r.stokKodu}</span>
                  </div>
                </td>
                <td className={td}>
                  <div className="whitespace-nowrap font-semibold">{fmtShortDay(r.yayinTarihi)}</div>
                  <div className="text-[11px] text-canvas-muted">{src(r.yayinKaynagi)}</div>
                </td>
                <td className={td}><DaysLeft days={r.kalanGun} /></td>
                <td className={`${td} whitespace-nowrap font-mono tabular-nums`}>
                  {r.hedef ? (
                    <>
                      <div>{fmtInt(r.hedef.adet)} adet</div>
                      {me.canSeeBudget && <div className="text-[11px] text-canvas-muted">{fmtMoney(r.hedef.ciro)}</div>}
                    </>
                  ) : (
                    <span className="font-sans text-[11.5px] text-canvas-muted">onaylı hedef yok</span>
                  )}
                </td>
                <td className={td}>
                  <div className="flex flex-wrap gap-1">
                    {r.plan ? <Pill tone={STATUS_TONE[r.plan.durum]}>{r.plan.durumAdi}</Pill> : <Pill tone="err">Plan yok</Pill>}
                    {r.plan?.hedefDegisti && <Pill tone="warn">Hedef değişti</Pill>}
                    {r.plan?.ustOnayGerekli && r.plan.durum === 'onayda' && <Pill tone="violet">Üst onay</Pill>}
                  </div>
                  {materials(r) && <div className="mt-0.5 max-w-[220px] text-[11px] text-amber-800">{materials(r)}</div>}
                </td>
                {me.canSeeBudget && <td className={`${td} text-right font-mono tabular-nums`}>{r.plan ? fmtMoney(r.plan.butce) : '—'}</td>}
                <td className={`${td} text-[11.5px]`}>{r.plan?.sahip ?? r.sorumlu ?? '—'}</td>
                <td className={`${td} text-right`}>{action(r, false)}</td>
              </tr>
            ))}
          </tbody>
        </TableWrap>
      </div>
    </>
  );
}
