import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { ENGINE_ENABLED } from '../../engine';
import { Note, TableWrap, errText, field, td, th } from '../../admin/ui';
import { NAV } from '../../nav/navModel';
import { Block } from '../parts';
import SqlInfo, { InfoLabel } from '../../components/SqlInfo';
import { learningApi } from './learningApi';
import { LearningFrame, fmtDay } from './parts';

/** ZEKİ kullanım haritası: ekran × birim, pencere içinde en az bir kez kullanan farklı kişi sayısı. Kişi adı yoktur; kişi
 *  bazında görünüm yalnız kişinin kendisinde (Eğitimlerim). Gizlilik eşiği girildiyse küçük birimler tek sütunda birleşir. */

const NAV_LABEL = new Map(NAV.flatMap((g) => g.items.map((i) => [i.id, { label: i.label, group: g.label }] as const)));

export default function UsageMap() {
  const [days, setDays] = useState(30);
  const [group, setGroup] = useState('');
  const q = useQuery({ queryKey: ['hr', 'learning', 'usage', days], queryFn: () => learningApi.usageMap(days), enabled: ENGINE_ENABLED });
  const d = q.data;
  const modules = useMemo(() => {
    if (!d) return [];
    return d.modules
      .map((m) => {
        const nav = NAV_LABEL.get(m.key);
        return { key: m.key, label: m.label ?? nav?.label ?? m.key, group: m.label ? 'Kayıt ve soru' : nav?.group ?? 'Diğer', total: d.totals[m.key] ?? 0 };
      })
      .filter((m) => !group || m.group === group)
      .sort((a, b) => b.total - a.total || a.label.localeCompare(b.label, 'tr'));
  }, [d, group]);
  const groups = useMemo(() => [...new Set((d?.modules ?? []).map((m) => (m.label ? 'Kayıt ve soru' : NAV_LABEL.get(m.key)?.group ?? 'Diğer')))].sort((a, b) => a.localeCompare(b, 'tr')), [d]);
  // Hiç kullanılmayan menü ekranları: eğitimi yöneltmek için.
  const unused = useMemo(() => {
    if (!d) return [];
    const seen = new Set(d.modules.map((m) => m.key));
    return NAV.filter((g) => g.id !== 'kampus' && g.id !== 'yonetim').flatMap((g) => g.items.filter((i) => !seen.has(i.id)).map((i) => `${g.label} › ${i.label}`));
  }, [d]);
  return (
    <LearningFrame
      crumb="Eğitim ve gelişim"
      title="Kullanım haritası"
      lead="Hangi birimde hangi ekranın kullanıldığı: hücre, pencere içinde o ekranı en az bir kez açan farklı kişi sayısıdır. Kişi adı gösterilmez ve bu sayılar performans değerlendirmesinde kullanılmaz."
    >
      {q.error && <Note tone="err">{errText(q.error, 'Harita okunamadı.')}</Note>}
      {d?.note && <Note tone="warn">{d.note}</Note>}
      {d && d.minGroup && <Note tone="info">{d.minGroup} kişiden az çalışanı olan {d.smallUnits} birim ve çalışan kaydında olmayan hesaplar tek sütunda birleştirildi.</Note>}
      <Block
        title="Ekran × birim"
        help={d ? `${fmtDay(d.since)} ve sonrası · ${d.days} gün` : undefined}
        info={<SqlInfo k={d?.kaynaklar} alan="rows" label="Ekran × birim kullanıcı sayısı" />}
        action={
          <>
            <select className={`${field} w-auto`} value={group} onChange={(e) => setGroup(e.target.value)} aria-label="Çalışma alanı">
              <option value="">Bütün alanlar</option>
              {groups.map((g) => <option key={g} value={g}>{g}</option>)}
            </select>
            <select className={`${field} w-auto`} value={days} onChange={(e) => setDays(Number(e.target.value))} aria-label="Pencere">
              {[7, 30, 90, 180].map((n) => <option key={n} value={n}>Son {n} gün</option>)}
            </select>
          </>
        }
      >
        {q.isLoading && <p className="text-[12px] text-canvas-muted">Yükleniyor…</p>}
        {d && modules.length === 0 && <p className="text-[12px] text-canvas-muted">Bu pencerede kayıtlı kullanım yok. Ekran sayacı yeni kuruldu ise veriler günler içinde birikir.</p>}
        {d && modules.length > 0 && (
          <TableWrap>
            <thead>
              <tr>
                <th className={`${th} sticky left-0 bg-white`}>Ekran</th>
                <th className={`${th} text-right`}><InfoLabel k={d.kaynaklar} alan="totals" label="Ekranı açan farklı kişi">Toplam</InfoLabel></th>
                {d.rows.map((r) => (
                  <th key={r.key} className={`${th} text-right`} title={r.unitName}>
                    <span className="block max-w-[140px] truncate">{r.unitName}</span>
                    <span className="block font-normal normal-case">{r.employees === null ? 'kişi sayısı yok' : `${r.employees} kişi`}</span>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {modules.map((m) => (
                <tr key={m.key} className="border-t border-slate-100">
                  <td className={`${td} sticky left-0 bg-white font-bold`}>
                    {m.label}
                    <div className="text-[10.5px] font-normal text-canvas-muted">{m.group}</div>
                  </td>
                  <td className={`${td} text-right font-mono tabular-nums`}>{m.total}</td>
                  {d.rows.map((r) => {
                    const n = r.cells[m.key] ?? 0;
                    return (
                      <td key={r.key} className={`${td} text-right font-mono tabular-nums ${n === 0 ? 'text-red-600' : ''}`}>{n}</td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </TableWrap>
        )}
      </Block>
      {d && unused.length > 0 && (
        <Block title="Pencerede hiç açılmayan ekranlar" help="Hiçbir birimde kullanılmayan menü ekranları; eğitim ya da rehber için aday.">
          <div className="flex flex-wrap gap-1.5 text-[12px]">
            {unused.map((u) => <span key={u} className="rounded-md bg-slate-100 px-2 py-1 font-semibold">{u}</span>)}
          </div>
        </Block>
      )}
    </LearningFrame>
  );
}
