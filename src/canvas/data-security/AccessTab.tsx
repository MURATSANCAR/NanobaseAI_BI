import { useState } from 'react';
import { useInfiniteQuery } from '@tanstack/react-query';
import { ENGINE_ENABLED } from '../engine';
import { Note, Pill, TableWrap, btnGhost, errText, field, label as labelCls, td, th } from '../admin/ui';
import { Panel } from '../editorial/kit';
import { fmtAt, securityApi, type AccessRow } from './api';

const KINDS = [
  { key: '', label: 'Hepsi' },
  { key: 'forbidden', label: 'Yetkisiz erişim denemesi' },
  { key: 'export', label: 'Dışa aktarma' },
  { key: 'not_permitted', label: 'Yetki dışı soru' },
];

function what(r: AccessRow): string {
  const d = r.detail ?? {};
  if (r.kind === 'not_permitted') return String(d.question ?? '');
  if (r.kind === 'export' && d.client) return `${String(d.what ?? '')} (${String(d.format ?? '').toUpperCase()}${d.rows != null ? `, ${d.rows} satır` : ''})`;
  return r.path ?? '';
}

/** Erişim kaydı: sayfa kapısının 403 kararları, dışa aktarmalar (sunucu ve tarayıcı) ve ZEKİ AI'ın yetki dışı soruları. */
export default function AccessTab() {
  const [kind, setKind] = useState('');
  const [user, setUser] = useState('');
  const [since, setSince] = useState('');
  const q = useInfiniteQuery({
    queryKey: ['security', 'access', kind, user.trim().toLowerCase(), since],
    queryFn: ({ pageParam }) => securityApi.access({ kind, user: user.trim(), since, before: pageParam }),
    initialPageParam: null as string | null,
    getNextPageParam: (last) => (typeof last.next === 'string' ? last.next : undefined),
    enabled: ENGINE_ENABLED,
  });
  const rows = q.data?.pages.flatMap((p) => p.items) ?? [];
  return (
    <Panel>
      <h2 className="text-[16px] font-extrabold tracking-tight">Erişim kaydı</h2>
      <p className="text-[12px] text-canvas-muted">
        Her istek değil, yalnız reddedilen istekler ve dışa aktarmalar yazılır (ölçülülük). Mesai dışı satırlar işaretlidir.
      </p>
      <div className="mt-3 grid gap-2 sm:grid-cols-3">
        <label className="flex flex-col gap-1">
          <span className={labelCls}>Tür</span>
          <select className={field} value={kind} onChange={(e) => setKind(e.target.value)}>
            {KINDS.map((k) => <option key={k.key} value={k.key}>{k.label}</option>)}
          </select>
        </label>
        <label className="flex flex-col gap-1">
          <span className={labelCls}>Hesap</span>
          <input className={field} value={user} onChange={(e) => setUser(e.target.value)} placeholder="ör. ahmety" autoComplete="off" />
        </label>
        <label className="flex flex-col gap-1">
          <span className={labelCls}>Şu tarihten beri</span>
          <input type="date" className={field} value={since} onChange={(e) => setSince(e.target.value)} />
        </label>
      </div>
      {q.error && <div className="mt-2"><Note tone="err">{errText(q.error, 'Erişim kaydı okunamadı.')}</Note></div>}
      <div className="mt-3">
        <TableWrap>
          <thead>
            <tr className="border-b border-slate-100">
              <th className={th}>Zaman</th>
              <th className={th}>Hesap</th>
              <th className={th}>Tür</th>
              <th className={th}>Ne</th>
              <th className={th}>Yetki</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id} className="border-b border-slate-50 last:border-0">
                <td className={`${td} whitespace-nowrap`}>
                  {fmtAt(r.at)}
                  {r.offHours && <div><Pill tone="warn">mesai dışı</Pill></div>}
                </td>
                <td className={`${td} font-mono`}>
                  <button type="button" className="hover:underline" onClick={() => setUser(r.username)}>{r.username}</button>
                </td>
                <td className={td}><Pill tone={r.kind === 'export' ? 'violet' : 'err'}>{r.kindLabel}</Pill></td>
                <td className={`${td} max-w-[420px] break-words`}>{what(r)}</td>
                <td className={`${td} font-mono text-[11px] text-canvas-muted`}>{r.permKey ?? '—'}</td>
              </tr>
            ))}
            {q.data && !rows.length && <tr><td className={td} colSpan={5}>Kayıt yok.</td></tr>}
          </tbody>
        </TableWrap>
      </div>
      {q.hasNextPage && (
        <div className="mt-3 flex justify-center">
          <button type="button" className={btnGhost} disabled={q.isFetchingNextPage} onClick={() => q.fetchNextPage()}>
            {q.isFetchingNextPage ? 'Yükleniyor…' : 'Daha eski kayıtlar'}
          </button>
        </div>
      )}
    </Panel>
  );
}
