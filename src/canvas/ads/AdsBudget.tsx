import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Save } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import SqlInfo from '../components/SqlInfo';
import { Loading, Note, TableWrap, btnGhost, btnPrimary, errText, field, label as labelCls, td, th } from '../admin/ui';
import { Kpi, KpiRow } from '../editorial/kit';
import { Block } from '../marketing/parts';
import { parseNum } from '../marketing/api';
import { adsApi, fmtMoney, monthName, type BudgetCell, type Platform } from './api';
import { AdsFrame, DataEnd, useAdsMeta } from './parts';

/** Ay × kanal reklam bütçesi: bu ekranda girilen plan, yüklenen dosyalardan harcama, içinde bulunulan ayın sonu tahmini;
 *  karşılaştırma için M15 onaylı kitap planlarının reklam kanalı satırları ve CRM pazarlama bütçe kayıtları. */
export default function AdsBudget() {
  const qc = useQueryClient();
  const meta = useAdsMeta();
  const m = meta.data;
  const [year, setYear] = useState(new Date().getFullYear());
  const [edits, setEdits] = useState<Record<string, string>>({});
  const q = useQuery({ queryKey: ['ads', 'budget', year], queryFn: () => adsApi.budget(year), enabled: ENGINE_ENABLED });
  const save = useMutation({
    mutationFn: () =>
      adsApi.putBudget(Object.entries(edits).map(([k, v]) => {
        const [ay, kanal] = k.split('|');
        return { ay, kanal: kanal as Platform, plan: v.trim() === '' ? null : parseNum(v) };
      })),
    onSuccess: (r) => {
      toast.success(`Bütçe kaydedildi (${r.degisen} hücre).`);
      setEdits({});
      qc.invalidateQueries({ queryKey: ['ads'] });
    },
    onError: (e) => toast.error(errText(e, 'Bütçe kaydedilemedi.') ?? ''),
  });
  const b = q.data;
  const cell = useMemo(() => {
    const out: Record<string, BudgetCell> = {};
    b?.hucreler.forEach((c) => { out[`${c.ay}|${c.kanal}`] = c; });
    return out;
  }, [b]);
  const m15 = useMemo(() => {
    const out: Record<string, number> = {};
    b?.m15.ay.forEach((x) => { out[x.ay] = (out[x.ay] ?? 0) + x.tutar; });
    return out;
  }, [b]);
  const crm = useMemo(() => Object.fromEntries((b?.crm ?? []).map((x) => [x.ay, x.tutar])), [b]);
  const canEdit = !!m?.me.canEdit;
  const bad = Object.values(edits).some((v) => v.trim() !== '' && (parseNum(v) === null || (parseNum(v) ?? 0) < 0));
  const channels = Object.entries(b?.kanallar ?? {}) as Array<[Platform, string]>;

  return (
    <AdsFrame
      title="Reklam bütçesi"
      lead="Ay × kanal plan ve gerçekleşme. Plan portalda tutulur; CRM'e ve platformlara yazılmaz. Ay sonu tahmini yalnız içinde bulunulan ay için: harcama ÷ geçen gün × ayın günü."
      meta={m}
      aside={
        <div className="flex items-end gap-2">
          <label className="flex flex-1 flex-col gap-1">
            <span className={labelCls}>Yıl</span>
            <select className={field} value={year} onChange={(e) => { setYear(Number(e.target.value)); setEdits({}); }}>
              {[year - 1, year, year + 1].map((y) => <option key={y} value={y}>{y}</option>)}
            </select>
          </label>
          {canEdit && (
            <button type="button" className={btnPrimary} disabled={!Object.keys(edits).length || bad || save.isPending} onClick={() => save.mutate()}>
              <Save aria-hidden className="h-4 w-4" />Kaydet
            </button>
          )}
        </div>
      }
    >
      <DataEnd meta={m} />
      {q.error && <Note tone="err">{errText(q.error, 'Bütçe açılamadı.')}</Note>}
      {b?.uyarilar?.map((u) => <Note key={u} tone="warn">{u}</Note>)}
      {q.isLoading && <Loading />}
      {b && (
        <>
          <KpiRow>
            <Kpi label="Plan" value={fmtMoney(b.toplam.plan)} help={`${b.yil} bu ekranda girilen`} info={<SqlInfo k={b.kaynaklar} alan="toplam" label="Plan" />} />
            <Kpi label="Harcama" value={fmtMoney(b.toplam.harcama)} help="Yüklenen dosyalar, TL" info={<SqlInfo k={b.kaynaklar} alan="toplam" label="Harcama" />} />
            <Kpi label="M15 reklam satırları" value={fmtMoney(b.toplam.m15)} help={`Onaylı yeni kitap planları (${Object.values(b.m15.kanalEsleme).filter((v, i, a) => a.indexOf(v) === i).join(', ')})`} info={<SqlInfo k={b.kaynaklar} alan="m15" label="M15 reklam satırları" />} />
            <Kpi label="CRM pazarlama bütçesi" value={fmtMoney(b.toplam.crm)} help="Sosyal medya ve dijital pazarlama tipli kayıtlar" info={<SqlInfo k={b.kaynaklar} alan="crm" label="CRM pazarlama bütçesi" />} />
          </KpiRow>
          <Block title="Ay × kanal" info={<SqlInfo k={b.kaynaklar} alan="hucreler" label="Ay × kanal" />} help={canEdit ? 'Plan hücresine tutar yazın (boş bırakılan silinir), sonra Kaydet.' : undefined}>
            <TableWrap>
              <thead>
                <tr>
                  <th className={th}>Ay</th>
                  {channels.map(([k, v]) => <th key={k} className={`${th} text-right`}>{v}</th>)}
                  <th className={`${th} text-right`}>M15</th>
                  <th className={`${th} text-right`}>CRM</th>
                </tr>
              </thead>
              <tbody>
                {b.aylar.map((ay) => (
                  <tr key={ay} className="border-t border-slate-100 align-top">
                    <td className={`${td} whitespace-nowrap font-bold capitalize`}>{monthName(ay)}</td>
                    {channels.map(([k]) => {
                      const key = `${ay}|${k}`;
                      const c = cell[key];
                      const v = edits[key] ?? (c?.plan != null ? String(c.plan) : '');
                      return (
                        <td key={k} className={`${td} min-w-[132px] text-right`}>
                          {canEdit ? (
                            <input aria-label={`${monthName(ay)} ${k} planı`} inputMode="decimal" className={`${field} text-right font-mono tabular-nums`}
                              value={v} placeholder="plan" onChange={(e) => setEdits({ ...edits, [key]: e.target.value })} />
                          ) : (
                            <div className="font-mono tabular-nums">{c?.plan != null ? fmtMoney(c.plan) : '—'}</div>
                          )}
                          <div className="mt-0.5 font-mono text-[11px] tabular-nums text-canvas-muted">{c?.harcama ? `harcama ${fmtMoney(c.harcama)}` : ''}</div>
                          {c?.tahmin != null && (
                            <div className={`font-mono text-[11px] tabular-nums ${c.asim ? 'font-bold text-red-700' : 'text-canvas-muted'}`}>tahmin {fmtMoney(c.tahmin)}</div>
                          )}
                        </td>
                      );
                    })}
                    <td className={`${td} text-right font-mono tabular-nums`}>{m15[ay] ? fmtMoney(m15[ay]) : '—'}</td>
                    <td className={`${td} text-right font-mono tabular-nums`}>{crm[ay] ? fmtMoney(crm[ay]) : '—'}</td>
                  </tr>
                ))}
              </tbody>
            </TableWrap>
          </Block>
          <Block title="M15 kitap planlarının reklam satırları" info={<SqlInfo k={b.kaynaklar} alan="m15" label="M15 reklam satırları" />} help="Yeni kitap pazarlama planında onaylanmış, reklam kanalına düşen satırlar; tutar başlangıç–bitiş günlerine göre aylara bölünür."
            action={<Link to="/pazarlama/yeni-kitap" className={btnGhost}>Yeni kitap planları</Link>}>
            {b.m15.satirlar.length === 0 ? (
              <p className="py-3 text-[12px] text-canvas-muted">Bu yıl onaylı planda reklam kanalı satırı yok.</p>
            ) : (
              <TableWrap>
                <thead><tr><th className={th}>Plan</th><th className={th}>Kanal</th><th className={th}>Tarih</th><th className={`${th} text-right`}>Tutar</th></tr></thead>
                <tbody>
                  {b.m15.satirlar.map((s, i) => (
                    <tr key={`${s.planId}-${i}`} className="border-t border-slate-100">
                      <td className={td}><Link className="font-bold text-canvas-violet hover:underline" to={`/pazarlama/plan/${encodeURIComponent(s.planId)}`}>{s.plan}</Link><div className="font-mono text-[11px] text-canvas-muted">{s.planId} · {s.stokKodu ?? '—'}</div></td>
                      <td className={td}>{s.kanalAdi}</td>
                      <td className={`${td} whitespace-nowrap`}>{s.bas ?? '—'} – {s.bit ?? '—'}</td>
                      <td className={`${td} text-right font-mono tabular-nums`}>{fmtMoney(s.tutar)}</td>
                    </tr>
                  ))}
                </tbody>
              </TableWrap>
            )}
          </Block>
          <CrmBlock year={year} />
        </>
      )}
    </AdsFrame>
  );
}

/** CRM'deki reklam planları ve pazarlama bütçe kayıtları (yalnız okuma; C20: onay/teslim alanları çoğunlukla boş). */
function CrmBlock({ year }: { year: number }) {
  const q = useQuery({
    queryKey: ['ads', 'crm', year],
    queryFn: () => adsApi.crm({ frm: `${year}-01-01`, to: `${year}-12-31` }),
    enabled: ENGINE_ENABLED,
  });
  const d = q.data;
  return (
    <Block title="CRM kayıtları" info={<SqlInfo k={d?.kaynaklar} alan="reklamPlanlari" label="CRM reklam planları ve bütçe kayıtları" />} help="CRM «Reklam Planı» ve «Pazarlama Bütçe Modülü» kayıtları, yalnız okunur. Portaldaki plan CRM'e yazılmaz.">
      {q.error && <Note tone="err">{errText(q.error, 'CRM okunamadı.')}</Note>}
      {q.isLoading && <Loading />}
      {d && (
        <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
          <div>
            <p className="text-[12.5px]"><b>{d.reklamPlanlari.toplam}</b> etkin reklam planı; {d.reklamPlanlari.onaysiz} tanesinde onay tarihi boş. {year} ile kesişen: {d.reklamPlanlari.donemde.length}.</p>
            <ul className="mt-2 flex flex-col gap-1">
              {d.reklamPlanlari.donemde.map((p) => (
                <li key={p.id} className="rounded-xl bg-slate-50 px-3 py-2 text-[12px]">
                  <div className="font-bold">{p.ad ?? '—'}</div>
                  <div className="text-[11px] text-canvas-muted">{[p.mecra, p.tip, p.durum].filter(Boolean).join(' · ')} · {p.bas ?? '—'} – {p.bit ?? '—'} · {fmtMoney(p.tutar)}
                    {p.kitaplar.length ? ` · ${p.kitaplar.map((k) => k.ad ?? k.stokKodu).join(', ')}` : ''}</div>
                </li>
              ))}
            </ul>
          </div>
          <div>
            <p className="text-[12.5px]">Bütçe kayıtları: <b>{fmtMoney(d.butceKayitlari.toplam)}</b> ({d.butceKayitlari.items.length} kayıt); sosyal medya ve dijital pazarlama tipli: <b>{fmtMoney(d.butceKayitlari.reklamToplam)}</b>.</p>
            <ul className="mt-2 flex flex-col gap-1">
              {d.butceKayitlari.items.map((r) => (
                <li key={r.id} className="rounded-xl bg-slate-50 px-3 py-2 text-[12px]">
                  <div className="font-bold">{r.ad ?? '—'}</div>
                  <div className="text-[11px] text-canvas-muted">{[r.tipAdi, r.mecra].filter(Boolean).join(' · ')} · {r.baslangic ?? '—'} – {r.bitis ?? '—'} · {fmtMoney(r.tutar)}</div>
                </li>
              ))}
            </ul>
          </div>
        </div>
      )}
    </Block>
  );
}
