import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Mail, Phone, Search } from 'lucide-react';
import { ENGINE_ENABLED } from '../../engine';
import { Loading, Note, errText, field, label as labelCls } from '../../admin/ui';
import { EmptyHint } from '../../components/Explain';
import { useDebounced } from '../../editorial/kit';
import { Block, HrFrame } from '../parts';
import { Avatar } from './parts';
import { portalApi } from './portalApi';

/** Personel rehberi (/ik/rehber): aktif personel departmana göre; yalnız «rehber» işaretli alanlar. */
export default function Directory() {
  const q = useQuery({ queryKey: ['hr', 'portal', 'directory'], queryFn: portalApi.directory, enabled: ENGINE_ENABLED });
  const [text, setText] = useState('');
  const [dept, setDept] = useState('');
  const dq = useDebounced(text, 200).trim().toLocaleLowerCase('tr-TR');
  const items = q.data?.items ?? [];
  const fields = q.data?.fields ?? [];
  const depts = useMemo(() => [...new Set(items.map((x) => String(x.data.departman ?? '')).filter(Boolean))].sort((a, b) => a.localeCompare(b, 'tr')), [items]);
  const shown = items.filter((x) =>
    (!dept || x.data.departman === dept) &&
    (!dq || [x.adSoyad, ...Object.values(x.data)].join(' ').toLocaleLowerCase('tr-TR').includes(dq)));
  const groups = new Map<string, typeof shown>();
  shown.forEach((x) => {
    const g = String(x.data.departman || 'Departmanı girilmemiş');
    groups.set(g, [...(groups.get(g) ?? []), x]);
  });
  const extra = fields.filter((f) => !['ad_soyad', 'departman', 'unvan', 'mail_adresi', 'sirket_hatti_no', 'dahili_no'].includes(f.key));
  return (
    <HrFrame crumb="Personel rehberi" title="Personel rehberi" back={{ to: '/ik', label: 'İK ana sayfası' }}
      lead="Aktif çalışanların departman, unvan ve iletişim bilgileri. E-postaya dokununca e-posta, telefona dokununca arama açılır."
      aside={
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-[1.4fr_1fr]">
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Ara</span>
            <span className="relative flex items-center">
              <Search aria-hidden className="pointer-events-none absolute left-3 h-4 w-4 text-canvas-muted" />
              <input className={`${field} pl-9`} value={text} onChange={(e) => setText(e.target.value)} placeholder="Ad, unvan, ekip, dahili" />
            </span>
          </label>
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Departman</span>
            <select className={field} value={dept} onChange={(e) => setDept(e.target.value)}>
              <option value="">Bütün departmanlar</option>
              {depts.map((d) => <option key={d} value={d}>{d}</option>)}
            </select>
          </label>
        </div>
      }>
      {q.error && <Note tone="err">{errText(q.error, 'Rehber okunamadı.')}</Note>}
      {q.isLoading && <Loading />}
      {q.data && !shown.length && (
        <EmptyHint title={items.length ? 'Aramaya uyan kişi yok' : 'Rehber henüz boş'} why={items.length ? 'Aramayı ya da departman süzgecini temizleyin.' : 'İK personel kayıtlarını girince rehber dolar.'} />
      )}
      {[...groups.entries()].map(([g, people]) => (
        <Block key={g} title={g} help={`${people.length} kişi`}>
          <ul className="grid grid-cols-1 gap-2 sm:grid-cols-2 xl:grid-cols-3">
            {people.map((x) => {
              const mail = x.data.mail_adresi ? String(x.data.mail_adresi) : '';
              const line = x.data.sirket_hatti_no ? String(x.data.sirket_hatti_no) : '';
              return (
                <li key={x.id} className="flex min-w-0 gap-3 rounded-xl bg-white/85 p-3">
                  <Avatar name={x.adSoyad} src={x.hasPhoto ? `/portal/photo/${x.id}` : null} size={44} />
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-[13.5px] font-extrabold">{x.adSoyad}</div>
                    <div className="truncate text-[12px] text-canvas-muted">{String(x.data.unvan ?? '') || '—'}</div>
                    {extra.map((f) => x.data[f.key] ? (
                      <div key={f.key} className="truncate text-[11.5px] text-canvas-muted">{f.label}: <span className="text-canvas-ink">{String(x.data[f.key])}</span></div>
                    ) : null)}
                    <div className="mt-1.5 flex flex-wrap gap-1.5">
                      {mail && (
                        <a href={`mailto:${mail}`} className="inline-flex min-h-11 max-w-full items-center gap-1 rounded-lg bg-slate-100 px-2 text-[11.5px] font-bold text-canvas-ink hover:bg-slate-200 sm:min-h-7">
                          <Mail aria-hidden className="h-3.5 w-3.5 shrink-0" /><span className="truncate">{mail}</span>
                        </a>
                      )}
                      {line && (
                        <a href={`tel:${line.replace(/[^+0-9]/g, '')}`} className="inline-flex min-h-11 items-center gap-1 rounded-lg bg-slate-100 px-2 text-[11.5px] font-bold text-canvas-ink hover:bg-slate-200 sm:min-h-7">
                          <Phone aria-hidden className="h-3.5 w-3.5" />{line}
                        </a>
                      )}
                      {x.data.dahili_no ? <span className="inline-flex min-h-7 items-center rounded-lg bg-violet-50 px-2 text-[11.5px] font-bold text-canvas-violet">Dahili {String(x.data.dahili_no)}</span> : null}
                    </div>
                  </div>
                </li>
              );
            })}
          </ul>
        </Block>
      ))}
    </HrFrame>
  );
}
