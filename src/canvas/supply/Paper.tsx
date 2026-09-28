import { useCallback } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { ENGINE_ENABLED } from '../engine';
import { Loading, Note, TableWrap, field, td, th } from '../admin/ui';
import { Panel } from '../editorial/kit';
import { Tabs } from '../budget/parts';
import { fmtInt, fmtKg, fmtPct, fmtUnit, supplyApi } from './api';
import { CardLine, ErrorNote, ExportLink, SuggestionList, SupplyFrame, Warnings, useSupplyMeta } from './parts';

/** M52 Kağıt ve malzeme (/tedarik/kagit): açık kartların baskı ayı × kağıt cinsi ihtiyacı (CRM kart alanları), kağıt
 *  alım zamanı önerisi, kağıt bilgisi eksik kartlar ve kağıtçı alış fiyatı eğilimi (Logo). */

const TABS = [
  { key: 'ihtiyac', label: 'Aylık ihtiyaç' },
  { key: 'oneri', label: 'Alım zamanı' },
  { key: 'eksik', label: 'Kağıt bilgisi eksik' },
  { key: 'fiyat', label: 'Alış fiyatı' },
] as const;
type Tab = (typeof TABS)[number]['key'];

export default function Paper() {
  const [params, setParams] = useSearchParams();
  const tab: Tab = (TABS.find((t) => t.key === params.get('sekme'))?.key ?? 'ihtiyac') as Tab;
  const months = Number(params.get('aylar') || 0) || undefined;
  const meta = useSupplyMeta();
  const me = meta.data?.me;
  const q = useQuery({ queryKey: ['supply', 'paper', months ?? 0], queryFn: () => supplyApi.paper(months), enabled: ENGINE_ENABLED });
  const p = q.data;

  const update = useCallback(
    (next: Record<string, string | null>) => {
      const n = new URLSearchParams(params);
      for (const [k, v] of Object.entries(next)) {
        if (v) n.set(k, v);
        else n.delete(k);
      }
      setParams(n, { replace: true });
    },
    [params, setParams],
  );

  return (
    <SupplyFrame
      title="Kağıt ve malzeme"
      lead="Baskıdan çıkmamış kartların CRM'deki kağıt ihtiyacı (kapak, iç, şömiz, harita, afiş, yan kağıt, ayraç), baskı ayı ve kağıt cinsine göre. Kağıdın bir kısmını Timaş, bir kısmını matbaa alıyor olabilir: alım önerisi bu ayara göre üretilir."
      aside={
        <div className="flex flex-wrap items-end justify-start gap-2 lg:justify-end">
          <label className="flex flex-col gap-1">
            <span className="text-[11px] font-bold uppercase tracking-wide text-canvas-muted">Ufuk</span>
            <select className={`${field} w-auto`} value={String(months ?? meta.data?.settings.paperMonths ?? 3)} onChange={(e) => update({ aylar: e.target.value })}>
              {[1, 2, 3, 6, 9, 12].map((n) => (
                <option key={n} value={n}>
                  {n} ay
                </option>
              ))}
            </select>
          </label>
          {me?.canExport && <ExportLink href={supplyApi.exportUrl('kagit')} />}
        </div>
      }
    >
      <ErrorNote error={q.error} fallback="Kağıt ihtiyacı okunamadı." />
      <Warnings items={p?.uyarilar} />
      <Tabs
        tabs={TABS.filter((x) => x.key !== 'fiyat' || me?.canCost).map((x) => ({ ...x, badge: x.key === 'eksik' ? p?.kapsam.bos ?? null : null }))}
        value={tab}
        onChange={(k) => update({ sekme: k === 'ihtiyac' ? null : k })}
      />
      {q.isLoading && <Loading />}
      {p && tab === 'ihtiyac' && (
        <Panel>
          <p className="px-1 text-[12px] leading-snug text-canvas-muted">
            Ölçü: {p.olcu === 'brut' ? 'brüt kg (fire dahil)' : 'net kg'} · toplam {fmtKg(p.toplamKg)} · kağıt bilgisi dolu {fmtInt(p.kapsam.dolu)} kart, boş{' '}
            {fmtInt(p.kapsam.bos)} kart. CRM'deki «toplam kağıt ihtiyacı» kolonunun birimi henüz doğrulanmadı; ayrı sütunda gösterilir.
          </p>
          <div className="mt-3">
            <TableWrap>
              <thead>
                <tr className="border-b border-slate-100">
                  <th className={th}>Kağıt cinsi</th>
                  {p.aylar.map((m) => (
                    <th key={m.key} className={`${th} text-right`}>
                      {m.label}
                    </th>
                  ))}
                  <th className={`${th} text-right`}>Toplam</th>
                </tr>
              </thead>
              <tbody>
                {p.cinsler.map((c) => (
                  <tr key={c.cins ?? '-'} className="border-b border-slate-50 last:border-0">
                    <td className={td}>
                      <div className="font-bold">{c.cinsAdi}</div>
                      {c.gramaj ? <div className="text-[10.5px] text-canvas-muted">{fmtInt(c.gramaj)} gr</div> : null}
                    </td>
                    {p.aylar.map((m) => (
                      <td key={m.key} className={`${td} text-right font-mono tabular-nums`}>
                        {c.aylar[m.key] ? fmtKg(c.aylar[m.key]) : <span className="text-canvas-muted">·</span>}
                      </td>
                    ))}
                    <td className={`${td} text-right font-mono font-bold tabular-nums`}>{fmtKg(c.kg)}</td>
                  </tr>
                ))}
                {p.cinsler.length === 0 && (
                  <tr>
                    <td className={td} colSpan={p.aylar.length + 2}>
                      Ufuktaki kartlarda kağıt ihtiyacı girilmemiş.
                    </td>
                  </tr>
                )}
              </tbody>
            </TableWrap>
          </div>
          <h2 className="mt-4 px-1 text-[13px] font-extrabold">Ay ve cins ayrıntısı</h2>
          <div className="mt-2">
            <TableWrap>
              <thead>
                <tr className="border-b border-slate-100">
                  <th className={th}>Baskı ayı</th>
                  <th className={th}>Kağıt cinsi</th>
                  <th className={`${th} text-right`}>{p.olcu === 'brut' ? 'Brüt kg' : 'Net kg'}</th>
                  <th className={`${th} text-right`}>{p.olcu === 'brut' ? 'Net kg' : 'Brüt kg'}</th>
                  <th className={`${th} text-right`}>CRM toplam</th>
                  <th className={`${th} text-right`}>Kart</th>
                  <th className={th}>Parça / ebat</th>
                </tr>
              </thead>
              <tbody>
                {p.satirlar.map((r) => (
                  <tr key={`${r.ay}-${r.cins ?? '-'}`} className="border-b border-slate-50 last:border-0">
                    <td className={td}>{r.ayAdi}</td>
                    <td className={td}>{r.cinsAdi}</td>
                    <td className={`${td} text-right font-mono tabular-nums`}>
                      {fmtInt(r.kg)}
                      {r.eksikOlcu ? <div className="text-[10.5px] text-amber-700">{r.eksikOlcu} parçada bu ölçü boş</div> : null}
                    </td>
                    <td className={`${td} text-right font-mono tabular-nums`}>{fmtInt(r.digerKg)}</td>
                    <td className={`${td} text-right font-mono tabular-nums`}>{fmtInt(r.toplam)}</td>
                    <td className={`${td} text-right font-mono tabular-nums`}>{fmtInt(r.kart)}</td>
                    <td className={`${td} text-[11.5px] text-canvas-muted`}>
                      {Object.entries(r.parcalar).map(([k, v]) => `${k} ${fmtInt(v)}`).join(' · ')}
                      {Object.keys(r.ebatlar).length ? <div>{Object.entries(r.ebatlar).map(([k, v]) => `${k}: ${fmtInt(v)}`).join(' · ')}</div> : null}
                    </td>
                  </tr>
                ))}
              </tbody>
            </TableWrap>
          </div>
        </Panel>
      )}
      {tab === 'oneri' && (
        <Panel>
          {p?.alici === 'matbaa' ? (
            <Note tone="info">Ayara göre kağıdı matbaa alıyor; alım zamanı önerisi üretilmiyor.</Note>
          ) : (
            <>
              <p className="mb-3 px-1 text-[12px] leading-snug text-canvas-muted">
                En geç alım tarihi = baskı ayının ilk günü − tedarik süresi ({meta.data?.settings.paperLeadDays ?? '—'} gün, ayar; gerçek süre ölçülecek). Planı geçmiş kartların ihtiyacı «hemen»dir.
              </p>
              <SuggestionList tur="kagit" canDecide={!!me?.canDecide} empty="Bekleyen kağıt alım önerisi yok." />
            </>
          )}
        </Panel>
      )}
      {p && tab === 'eksik' && (
        <Panel>
          {p.kagitsizKartlar.length === 0 ? (
            <Note tone="ok">Ufuktaki bütün kartlarda kağıt bilgisi var.</Note>
          ) : (
            <>
              <p className="px-1 text-[12px] text-canvas-muted">Bu kartlarda CRM'de kağıt ihtiyacı girilmemiş; ihtiyaç toplamına girmez. CRM kartında tamamlanmalı.</p>
              <div className="mt-2">
                {p.kagitsizKartlar.map((c) => (
                  <CardLine key={c.id} c={c} right={<span className="text-[11px] text-canvas-muted">{c.matbaa ?? 'matbaa yok'}</span>} />
                ))}
              </div>
            </>
          )}
        </Panel>
      )}
      {p && tab === 'fiyat' && me?.canCost && (
        <Panel>
          <p className="px-1 text-[12px] leading-snug text-canvas-muted">
            Kağıtçı carilerinden mal alım satırları (Logo, son 12 ay): birim fiyat = satır net tutarı ÷ miktar (KDV hariç). Ölçü birimi (kg, tabaka) karışmaz, ayrı satırdır.
          </p>
          {!p.fiyat?.length ? (
            <div className="mt-2">
              <Note tone="info">Kağıtçı carisi bulunamadı ya da alış satırı yok (özel kod ayarını Tedarikçiler → Eşleme'den kontrol edin).</Note>
            </div>
          ) : (
            <div className="mt-2">
              <TableWrap>
                <thead>
                  <tr className="border-b border-slate-100">
                    <th className={th}>Malzeme</th>
                    <th className={th}>Birim</th>
                    <th className={`${th} text-right`}>Miktar</th>
                    <th className={`${th} text-right`}>Ortalama</th>
                    <th className={`${th} text-right`}>İlk ay</th>
                    <th className={`${th} text-right`}>Son ay</th>
                    <th className={`${th} text-right`}>Değişim</th>
                  </tr>
                </thead>
                <tbody>
                  {p.fiyat.map((f) => (
                    <tr key={`${f.kod}-${f.birim}`} className="border-b border-slate-50 last:border-0">
                      <td className={td}>
                        <div className="font-bold">{f.ad}</div>
                        <div className="text-[10.5px] text-canvas-muted">{f.kod}</div>
                      </td>
                      <td className={td}>{f.birim || '—'}</td>
                      <td className={`${td} text-right font-mono tabular-nums`}>{fmtInt(f.miktar)}</td>
                      <td className={`${td} text-right font-mono tabular-nums`}>{fmtUnit(f.ortalama)}</td>
                      <td className={`${td} text-right font-mono tabular-nums`}>{fmtUnit(f.ilk)}</td>
                      <td className={`${td} text-right font-mono tabular-nums`}>{fmtUnit(f.son)}</td>
                      <td className={`${td} text-right font-mono tabular-nums`}>{fmtPct(f.degisim, true)}</td>
                    </tr>
                  ))}
                </tbody>
              </TableWrap>
            </div>
          )}
        </Panel>
      )}
    </SupplyFrame>
  );
}
