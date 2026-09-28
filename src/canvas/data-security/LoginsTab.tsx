import { useState } from 'react';
import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { ENGINE_ENABLED } from '../engine';
import { Note, Pill, TableWrap, btnGhost, errText, field, label as labelCls, td, th } from '../admin/ui';
import { Panel } from '../editorial/kit';
import { AskSheet } from '../budget/parts';
import { fmtAt, fmtEpoch, securityApi, type SecurityMeta, type SessionRow } from './api';

/** Açık portal oturumları (kapatma: `guvenlik.oturum-kapat`) ve giriş olayları (başarılı/başarısız, adres). */
export default function LoginsTab({ meta }: { meta?: SecurityMeta }) {
  const qc = useQueryClient();
  const [user, setUser] = useState('');
  const [ok, setOk] = useState('');
  const [since, setSince] = useState('');
  const [ask, setAsk] = useState<null | { username?: string; session?: SessionRow }>(null);
  const sessions = useQuery({ queryKey: ['security', 'sessions'], queryFn: securityApi.sessions, enabled: ENGINE_ENABLED, refetchInterval: 60_000 });
  const logins = useInfiniteQuery({
    queryKey: ['security', 'logins', user.trim().toLowerCase(), ok, since],
    queryFn: ({ pageParam }) => securityApi.logins({ user: user.trim(), ok, since, before: pageParam }),
    initialPageParam: null as number | null,
    getNextPageParam: (last) => (typeof last.next === 'number' ? last.next : undefined),
    enabled: ENGINE_ENABLED,
  });
  const revoke = useMutation({
    mutationFn: (b: { username?: string; session?: string }) => securityApi.revoke(b),
    onSuccess: (out) => {
      setAsk(null);
      qc.invalidateQueries({ queryKey: ['security'] });
      toast.success(out.revoked ? `${out.revoked} oturum kapatıldı.` : 'Kapatılacak açık oturum kalmamıştı.');
    },
    onError: (e) => toast.error(errText(e, 'Oturum kapatılamadı.') ?? ''),
  });
  const canRevoke = !!meta?.me.canRevoke;
  const rows = logins.data?.pages.flatMap((p) => p.items) ?? [];
  const pull = logins.data?.pages[0]?.pull;

  return (
    <>
      <Panel>
        <h2 className="text-[16px] font-extrabold tracking-tight">Açık oturumlar</h2>
        <p className="text-[12px] text-canvas-muted">
          Portal oturumu 8 saat sürer. İşten ayrılan ya da cihazını kaybeden kişinin oturumu buradan kapatılır; AD hesabını
          kapatmak BT'nin işidir.
        </p>
        {sessions.error && <div className="mt-2"><Note tone="err">{errText(sessions.error, 'Oturumlar okunamadı.')}</Note></div>}
        {sessions.data?.note && <div className="mt-2"><Note tone="warn">{sessions.data.note}</Note></div>}
        {sessions.data && !sessions.data.configured && <p className="mt-2 text-[12.5px] text-canvas-muted">Giriş servisi bağlı değil.</p>}
        {sessions.data?.configured && (
          <div className="mt-3">
            <TableWrap>
              <thead>
                <tr className="border-b border-slate-100">
                  <th className={th}>Kişi</th>
                  <th className={th}>Açıldı</th>
                  <th className={th}>Bitiş</th>
                  <th className={th}>Adres</th>
                  <th className={th}>AD</th>
                  {canRevoke && <th className={th}><span className="sr-only">İşlem</span></th>}
                </tr>
              </thead>
              <tbody>
                {sessions.data.items.map((s) => (
                  <tr key={s.id} className="border-b border-slate-50 last:border-0">
                    <td className={td}>
                      <div className="font-bold">{s.display || s.username}</div>
                      <div className="font-mono text-[11px] text-canvas-muted">{s.username}</div>
                    </td>
                    <td className={`${td} whitespace-nowrap`}>{fmtEpoch(s.created)}</td>
                    <td className={`${td} whitespace-nowrap`}>{fmtEpoch(s.expires)}</td>
                    <td className={`${td} font-mono text-[11.5px]`}>{s.addr ?? '—'}</td>
                    <td className={td}>
                      {s.adEnabled === null ? <Pill tone="muted">bilinmiyor</Pill> : s.adEnabled ? <Pill tone="ok">etkin</Pill> : <Pill tone="err">etkin değil</Pill>}
                    </td>
                    {canRevoke && (
                      <td className={`${td} text-right`}>
                        <div className="flex flex-wrap justify-end gap-1.5">
                          <button type="button" className={btnGhost} onClick={() => setAsk({ session: s })}>Bu oturumu kapat</button>
                          <button type="button" className={btnGhost} onClick={() => setAsk({ username: s.username })}>Kişinin bütün oturumları</button>
                        </div>
                      </td>
                    )}
                  </tr>
                ))}
                {!sessions.data.items.length && (
                  <tr><td className={td} colSpan={canRevoke ? 6 : 5}>Açık oturum yok.</td></tr>
                )}
              </tbody>
            </TableWrap>
          </div>
        )}
      </Panel>

      <Panel>
        <h2 className="text-[16px] font-extrabold tracking-tight">Giriş kaydı</h2>
        <p className="text-[12px] text-canvas-muted">
          Başarılı ve başarısız girişler, çıkışlar ve yönetici kapatmaları. Parola hiçbir yerde tutulmaz; dizinde olmayan bir ad
          yazıldığında ad da tutulmaz (kişi parolasını ad kutusuna yazmış olabilir).
          {pull ? ` Son çekiş: ${fmtAt(pull.at)}${pull.ok ? '' : ` — ${pull.error ?? 'hata'}`}.` : ''}
        </p>
        <div className="mt-3 grid gap-2 sm:grid-cols-3">
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Hesap</span>
            <input className={field} value={user} onChange={(e) => setUser(e.target.value)} placeholder="ör. ahmety" autoComplete="off" />
          </label>
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Sonuç</span>
            <select className={field} value={ok} onChange={(e) => setOk(e.target.value)}>
              <option value="">Hepsi</option>
              <option value="0">Başarısız</option>
              <option value="1">Başarılı / çıkış</option>
            </select>
          </label>
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Şu tarihten beri</span>
            <input type="date" className={field} value={since} onChange={(e) => setSince(e.target.value)} />
          </label>
        </div>
        {logins.error && <div className="mt-2"><Note tone="err">{errText(logins.error, 'Giriş kaydı okunamadı.')}</Note></div>}
        <div className="mt-3">
          <TableWrap>
            <thead>
              <tr className="border-b border-slate-100">
                <th className={th}>Zaman</th>
                <th className={th}>Hesap</th>
                <th className={th}>Sonuç</th>
                <th className={th}>Adres</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id} className="border-b border-slate-50 last:border-0">
                  <td className={`${td} whitespace-nowrap`}>{fmtAt(r.at)}</td>
                  <td className={`${td} font-mono`}>
                    <button type="button" className="hover:underline" onClick={() => setUser(r.username)}>{r.username}</button>
                  </td>
                  <td className={td}><Pill tone={r.reason === 'ok' ? 'ok' : r.ok ? 'muted' : 'err'}>{r.reasonLabel}</Pill></td>
                  <td className={`${td} font-mono text-[11.5px]`}>{r.addr ?? '—'}</td>
                </tr>
              ))}
              {logins.data && !rows.length && <tr><td className={td} colSpan={4}>Kayıt yok.</td></tr>}
            </tbody>
          </TableWrap>
        </div>
        {logins.hasNextPage && (
          <div className="mt-3 flex justify-center">
            <button type="button" className={btnGhost} disabled={logins.isFetchingNextPage} onClick={() => logins.fetchNextPage()}>
              {logins.isFetchingNextPage ? 'Yükleniyor…' : 'Daha eski girişler'}
            </button>
          </div>
        )}
      </Panel>

      <AskSheet
        open={!!ask}
        title="Oturumu kapat"
        message={
          ask?.session ? (
            <p>«{ask.session.display || ask.session.username}» kişisinin {fmtEpoch(ask.session.created)} tarihinde açılan oturumu kapanacak. Kişi yeniden giriş yapmak zorunda kalır.</p>
          ) : (
            <p>«{ask?.username}» kişisinin bütün açık portal oturumları kapanacak. AD hesabı açık kalır; kişi yeniden giriş yapabilir.</p>
          )
        }
        confirm="Oturumu kapat"
        danger
        busy={revoke.isPending}
        onClose={() => setAsk(null)}
        onConfirm={() => ask && revoke.mutate(ask.session ? { session: ask.session.id } : { username: ask.username })}
      />
    </>
  );
}
