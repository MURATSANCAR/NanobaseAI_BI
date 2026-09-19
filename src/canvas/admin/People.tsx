import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Loader2, ShieldCheck, UserPlus } from 'lucide-react';
import { adminApi } from '../engine';
import { Loading, Note, Pill, Section, TableWrap, btnPrimary, errText, field, fmtDate, nf, td, th } from './ui';

export default function People({ me }: { me: string }) {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ['admin', 'users'], queryFn: adminApi.users, retry: false });
  const [add, setAdd] = useState('');

  const admins = (q.data?.items ?? []).filter((u) => u.admin).map((u) => u.username.toLowerCase());
  const setAdmins = useMutation({
    mutationFn: (list: string[]) => adminApi.saveSettings({ TIMAS_ADMIN_USERS: list.join(',') }),
    onSuccess: () => {
      setAdd('');
      void qc.invalidateQueries({ queryKey: ['admin'] });
    },
  });

  const toggle = (u: string, on: boolean) =>
    setAdmins.mutate(on ? [...new Set([...admins, u.toLowerCase()])] : admins.filter((a) => a !== u.toLowerCase()));

  return (
    <Section title="Kişiler" help="Sistemde tanımı ya da kaydı olan AD hesapları. Yöneticiler bu ekranı açabilir; herkes kendi pano ve raporunu yönetir.">
      <form
        className="flex flex-col gap-2 sm:flex-row"
        onSubmit={(e) => {
          e.preventDefault();
          if (add.trim()) toggle(add.trim().replace(/^timas\\/i, '').split('@')[0], true);
        }}
      >
        <input value={add} onChange={(e) => setAdd(e.target.value)} placeholder="AD hesap adı, örn. ali.yilmaz" autoCapitalize="none" spellCheck={false} className={field} />
        <button type="submit" disabled={!add.trim() || setAdmins.isPending} className={`${btnPrimary} shrink-0`}>
          {setAdmins.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <UserPlus className="h-4 w-4" />}
          Yönetici ekle
        </button>
      </form>
      {setAdmins.error && <Note tone="err">{errText(setAdmins.error, 'Yöneticiler değiştirilemedi.')}</Note>}
      {q.isLoading ? (
        <Loading />
      ) : q.error ? (
        <Note tone="err">{errText(q.error, 'Kişiler okunamadı.')}</Note>
      ) : (
        <TableWrap>
          <thead className="bg-slate-50/80">
            <tr>
              <th className={th}>Hesap</th>
              <th className={`${th} text-right`}>Pano kartı</th>
              <th className={`${th} text-right`}>Planlı rapor</th>
              <th className={`${th} text-right`}>Kayıtlı işlem</th>
              <th className={th}>Son hareket</th>
              <th className={`${th} text-right`}>Yetki</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {(q.data?.items ?? []).map((u) => {
              const self = u.username.toLowerCase() === me.toLowerCase();
              return (
                <tr key={u.username}>
                  <td className={td}>
                    <span className="flex items-center gap-1.5 font-semibold">
                      {u.username}
                      {self && <Pill tone="muted">siz</Pill>}
                    </span>
                  </td>
                  <td className={`${td} text-right tabular-nums`}>{nf.format(u.cards)}</td>
                  <td className={`${td} text-right tabular-nums`}>{nf.format(u.reports)}</td>
                  <td className={`${td} text-right tabular-nums`}>{nf.format(u.actions)}</td>
                  <td className={`${td} tabular-nums`}>{fmtDate(u.lastSeen)}</td>
                  <td className={`${td} text-right`}>
                    {u.admin ? (
                      <span className="inline-flex items-center gap-1.5">
                        <Pill tone="violet">
                          <ShieldCheck className="mr-1 h-3 w-3" />
                          Yönetici
                        </Pill>
                        {!self && (
                          <button type="button" disabled={setAdmins.isPending} onClick={() => toggle(u.username, false)} className="min-h-11 text-[11.5px] font-bold text-canvas-muted hover:text-red-700 sm:min-h-0">
                            Kaldır
                          </button>
                        )}
                      </span>
                    ) : (
                      <button type="button" disabled={setAdmins.isPending} onClick={() => toggle(u.username, true)} className="min-h-11 text-[11.5px] font-bold text-canvas-violet hover:underline sm:min-h-0">
                        Yönetici yap
                      </button>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </TableWrap>
      )}
    </Section>
  );
}
