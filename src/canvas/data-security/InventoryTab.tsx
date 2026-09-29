import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { ENGINE_ENABLED } from '../engine';
import { Note, Pill, TableWrap, errText, field, label as labelCls, td, th } from '../admin/ui';
import { Kpi, KpiRow, Panel } from '../editorial/kit';
import { fmtBytes, fmtN, securityApi } from './api';
import SqlInfo, { InfoLabel } from '../components/SqlInfo';
import { kaynakOf } from '../components/kaynakOf';
import ColName from '../components/ColName';
import { readableName, readableText } from '../components/readableName';
import { EmptyHint, ExplainLabel } from '../components/Explain';

/** Kişisel veri envanteri: kaynakta (Logo, CRM) kişisel veri kolonları — değer gösterilmez — ve portalın kendi
 *  kopyaları (tablo/klasör, amaç, saklama). */
export default function InventoryTab() {
  const q = useQuery({ queryKey: ['security', 'inventory'], queryFn: securityApi.inventory, enabled: ENGINE_ENABLED, staleTime: 300_000 });
  const [filter, setFilter] = useState('');
  const [src, setSrc] = useState('');
  const d = q.data;
  const sources = useMemo(() => Object.keys(d?.sourceCounts ?? {}).sort(), [d]);
  const rows = useMemo(() => {
    const f = filter.trim().toLocaleLowerCase('tr-TR');
    return (d?.source ?? []).filter(
      (s) => (!src || s.source === src) && (!f || `${s.entity} ${s.column} ${readableName(s.entity)} ${readableName(s.column)} ${s.reason}`.toLocaleLowerCase('tr-TR').includes(f)),
    );
  }, [d, filter, src]);
  if (q.error) return <Note tone="err">{errText(q.error, 'Envanter okunamadı.')}</Note>;
  if (!d) return <div className="py-10 text-center text-[12px] text-canvas-muted">Yükleniyor…</div>;
  return (
    <>
      <KpiRow>
        <Kpi label="Maskeli kolon" value={fmtN(d.sensitiveCount)} help="TC, e-posta, telefon, IBAN, adres, doğum tarihi, parola"
          explain="Logo ve CRM’de kişisel veri taşıyan ve maskelenen kolon sayısı. Maskeli kolonun değeri portalda hiç okunmaz, Zeki AI’a gitmez." info={<SqlInfo k={kaynakOf(d)} alan="sensitiveCount" label="Maskeli kolon" />} />
        <Kpi label="Ad-soyad kolonu" value={fmtN(d.nameCount)} help="Kişisel veri; sorgu için maskelenmez"
          explain="Kişi adı taşıyan kolonlar. Kişisel veridir ama müşteri ya da yazar adıyla arama yapılabilsin diye maskelenmez; yalnız burada kayıt altındadır." info={<SqlInfo k={kaynakOf(d)} alan="nameCount" label="Ad-soyad kolonu" />} />
        <Kpi label="Portal kopyası" value={fmtN(d.portal.length)} help="Tablo ve klasör"
          explain="Portalın kendi içinde tuttuğu ve kişisel veri içeren kayıt türleri (tablo ya da dosya klasörü)." info={<SqlInfo k={kaynakOf(d)} alan="portal" label="Portal kopyası" />} />
        <Kpi label="Saklama süresi olan" value={fmtN(d.portal.filter((p) => p.retentionDays).length)} help="Kalanlar iş kaydı"
          explain="Belirli bir süre sonra silinen ya da boşaltılan portal kopyaları. Kalanlar iş kaydı olduğu için süresiz tutulur." info={<SqlInfo k={kaynakOf(d)} alan="portal" label="Saklama süresi olan" />} />
      </KpiRow>
      <Panel>
        <h2 className="text-[16px] font-extrabold tracking-tight">Portal içi kopyalar</h2>
        <p className="text-[12px] text-canvas-muted">
          Portalın kendi tuttuğu kişisel veri. Yeni kişisel veri yazan her modül buraya bir satır ekler.
        </p>
        <div className="mt-3">
          <TableWrap>
            <thead>
              <tr className="border-b border-slate-100">
                <th className={th}>Kayıt</th>
                <th className={th}>Hangi veri</th>
                <th className={th}>Kimin</th>
                <th className={th}>Amaç</th>
                <th className={`${th} text-right`}><InfoLabel k={kaynakOf(d)} alan="portal">Büyüklük</InfoLabel></th>
                <th className={th}>
                  <ExplainLabel label="Saklama">Kaydın portalda ne kadar tutulacağı. Süreler «Saklama süreleri» sekmesinden değiştirilir.</ExplainLabel>
                </th>
              </tr>
            </thead>
            <tbody>
              {d.portal.map((p) => (
                <tr key={p.object} className="border-b border-slate-50 last:border-0">
                  <td className={td}>
                    {/* Ham tablo adı yalnız üstüne gelince görünür; klasörde yol ekranda kalır (yol bir veritabanı adı değil). */}
                    <div className="font-bold" title={p.kind === 'tablo' ? p.object : undefined}>{p.kind === 'tablo' ? p.purpose : readableText(p.object)}</div>
                    {p.kind !== 'tablo' && <div className="font-mono text-[10.5px] text-canvas-muted">{p.path}</div>}
                  </td>
                  <td className={`${td} max-w-[320px] break-words`}>{p.data}</td>
                  <td className={td}>{p.subjects}</td>
                  <td className={td}>{p.module}</td>
                  <td className={`${td} whitespace-nowrap text-right font-mono tabular-nums`}>
                    {p.error ? <span className="text-[11px] text-canvas-muted">{p.error}</span> : p.kind === 'tablo' ? `${fmtN(p.rows)} satır` : `${fmtN(p.files)} dosya · ${fmtBytes(p.bytes)}`}
                  </td>
                  <td className={`${td} max-w-[260px]`}>
                    {p.retentionDays ? <Pill tone="ok">{p.retentionDays} gün</Pill> : p.retention ? <Pill tone="muted">süresiz</Pill> : null}
                    {p.retentionNote && <div className="text-[11px] text-canvas-muted">{p.retentionNote}</div>}
                  </td>
                </tr>
              ))}
            </tbody>
          </TableWrap>
        </div>
      </Panel>
      <Panel>
        <h2 className="text-[16px] font-extrabold tracking-tight">Kaynakta kişisel veri kolonları</h2>
        <p className="text-[12px] text-canvas-muted">
          Kaynak tabloların düzenli taramasında, kolon adına ve değerin biçimine bakılarak bulunan kolonlar. Maskeli kolonun değeri hiç
          okunmaz ve Zeki AI’a gitmez; ad-soyad kolonları aramayı bozmamak için maskelenmez, yalnız burada sınıflanır. Değerler gösterilmez.
        </p>
        <div className="mt-3 grid gap-2 sm:grid-cols-3">
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Kaynak</span>
            <select className={field} value={src} onChange={(e) => setSrc(e.target.value)}>
              <option value="">Hepsi</option>
              {sources.map((s) => <option key={s} value={s}>{readableName(s)} ({fmtN(d.sourceCounts[s].masked + d.sourceCounts[s].names)})</option>)}
            </select>
          </label>
          <label className="flex flex-col gap-1 sm:col-span-2">
            <span className={labelCls}>Ara</span>
            <input className={field} value={filter} onChange={(e) => setFilter(e.target.value)} placeholder="tablo, kolon ya da tür (ör. TC kimlik)" />
          </label>
        </div>
        {!rows.length && (
          <div className="mt-3">
            <EmptyHint title="Aramaya uyan kolon yok" why="Arama kutusunu temizleyin ya da kaynağı «Hepsi» yapın." />
          </div>
        )}
        {!!rows.length && (
        <div className="mt-3">
          <TableWrap>
            <thead>
              <tr className="border-b border-slate-100">
                <th className={th}>Kaynak</th>
                <th className={th}>Tablo</th>
                <th className={th}>Kolon</th>
                <th className={th}>Tür</th>
                <th className={th}>
                  <ExplainLabel label="Durum">«Maskeli»: değer hiç okunmaz. «Maskesiz (ad)»: kişi adı; arama için açık bırakılır.</ExplainLabel>
                </th>
              </tr>
            </thead>
            <tbody>
              {rows.map((s) => (
                <tr key={`${s.source}:${s.entity}:${s.column}`} className="border-b border-slate-50 last:border-0">
                  <td className={td}><ColName name={s.source} /></td>
                  <td className={`${td} text-[12px]`}><ColName name={s.entity} />{s.tables > 1 ? <span className="ml-1 text-canvas-muted">×{s.tables}</span> : null}</td>
                  <td className={`${td} text-[12px]`}><ColName name={s.column} /></td>
                  <td className={td}>{s.reason}</td>
                  <td className={td}>{s.masked ? <Pill tone="ok">maskeli</Pill> : <Pill tone="warn">maskesiz (ad)</Pill>}</td>
                </tr>
              ))}
            </tbody>
          </TableWrap>
        </div>
        )}
        <p className="mt-2 text-[11.5px] text-canvas-muted">{fmtN(rows.length)} kolon listelendi.</p>
      </Panel>
    </>
  );
}
