import { useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { ENGINE_ENABLED } from '../engine';
import { Note, Pill, TableWrap, btnGhost, btnPrimary, errText, td, th } from '../admin/ui';
import { Panel } from '../editorial/kit';
import { AskSheet } from '../budget/parts';
import { SEVERITY, fmtAt, fmtN, securityApi, type SecurityMeta } from './api';
import SqlInfo from '../components/SqlInfo';
import { kaynakOf } from '../components/kaynakOf';
import { EmptyHint, ExplainLabel } from '../components/Explain';

/** Hesap hijyeni (AD, CRM ve portal izlerinin kesişimi) ve «Herkes» daraltma önizlemesi. */
export default function HygieneTab({ meta }: { meta?: SecurityMeta }) {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ['security', 'hygiene'], queryFn: securityApi.hygiene, enabled: ENGINE_ENABLED, staleTime: 120_000 });
  const [kind, setKind] = useState('');
  const [ask, setAsk] = useState<string | null>(null);
  const revoke = useMutation({
    mutationFn: (username: string) => securityApi.revoke({ username }),
    onSuccess: (out) => {
      setAsk(null);
      qc.invalidateQueries({ queryKey: ['security'] });
      toast.success(out.revoked ? `${out.revoked} oturum kapatıldı.` : 'Açık oturum kalmamıştı.');
    },
    onError: (e) => toast.error(errText(e, 'Oturum kapatılamadı.') ?? ''),
  });
  const hy = q.data;
  const items = (hy?.items ?? []).filter((i) => !kind || i.kind === kind);

  return (
    <>
      <Panel>
        <div className="flex flex-wrap items-end justify-between gap-2">
          <div>
            <h2 className="flex items-center gap-1 text-[16px] font-extrabold tracking-tight">
              Hesap hijyeni
              <SqlInfo k={kaynakOf(q.data)} alan="_hepsi" label="Hesap hijyeni sayıları" />
            </h2>
            <p className="text-[12px] text-canvas-muted">
              Active Directory’de kapalı ama portalda izi olan, uzun süredir girmeyen, test adı taşıyan ya da rolü olmayan hesaplar.
              Portal Active Directory’ye ve CRM’e yazmaz; hesabı kapatmak BT’nin işidir, burada yalnız portal oturumu kapatılır.
            </p>
          </div>
          <button type="button" className={btnGhost} disabled={q.isFetching} onClick={() => q.refetch()}>
            {q.isFetching ? 'Taranıyor…' : 'Yeniden tara'}
          </button>
        </div>
        {q.error && <div className="mt-2"><Note tone="err">{errText(q.error, 'Hesap hijyeni okunamadı.')}</Note></div>}
        {hy?.notes.map((n) => <div key={n} className="mt-2"><Note tone="warn">{n}</Note></div>)}
        {hy && (
          <div className="mt-3 flex flex-wrap gap-1.5">
            <button type="button" onClick={() => setKind('')} className={`min-h-11 rounded-lg px-2.5 text-[12px] font-bold sm:min-h-8 ${!kind ? 'bg-canvas-violet text-white' : 'bg-slate-100'}`}>
              Hepsi {fmtN(hy.items.length)}
            </button>
            {Object.entries(hy.kinds).map(([k, v]) =>
              hy.counts[k] ? (
                <button key={k} type="button" onClick={() => setKind(k)} className={`min-h-11 rounded-lg px-2.5 text-[12px] font-bold sm:min-h-8 ${kind === k ? 'bg-canvas-violet text-white' : 'bg-slate-100'}`}>
                  {v.label} {fmtN(hy.counts[k])}
                </button>
              ) : null,
            )}
          </div>
        )}
        {hy && !items.length && (
          <div className="mt-3">
            <EmptyHint title={kind ? 'Bu türde bulgu yok' : 'Bulgu yok'} why="Taranan hesapların hiçbirinde temizlenmesi gereken bir durum bulunmadı." />
          </div>
        )}
        {hy && (
          <div className="mt-3">
            {!!items.length && (
            <TableWrap>
              <thead>
                <tr className="border-b border-slate-100">
                  <th className={th}>
                    <ExplainLabel label="Önem">«Kritik» hemen bakılmalı (ör. şirket hesabı kapalı ama portal oturumu açık); diğerleri düzenli temizlikte ele alınabilir.</ExplainLabel>
                  </th>
                  <th className={th}>Kişi</th>
                  <th className={th}>Bulgu</th>
                  <th className={th}>Son giriş</th>
                  {meta?.me.canRevoke && <th className={th}><span className="sr-only">İşlem</span></th>}
                </tr>
              </thead>
              <tbody>
                {items.map((i) => (
                  <tr key={`${i.kind}:${i.username}`} className="border-b border-slate-50 last:border-0">
                    <td className={td}><Pill tone={SEVERITY[i.severity].tone}>{SEVERITY[i.severity].label}</Pill></td>
                    <td className={td}>
                      <div className="font-bold">{i.display}</div>
                      <div className="font-mono text-[11px] text-canvas-muted">{i.username}</div>
                    </td>
                    <td className={`${td} max-w-[460px]`}>
                      <div className="font-bold">{i.kindLabel}</div>
                      <div className="break-words text-[11.5px] text-canvas-muted">{i.detail}</div>
                    </td>
                    <td className={`${td} whitespace-nowrap`}>{fmtAt(i.lastLogin)}</td>
                    {meta?.me.canRevoke && (
                      <td className={`${td} text-right`}>
                        {i.kind === 'oturum_ad_disi' && (
                          <button type="button" className={btnGhost} onClick={() => setAsk(i.username)}>Oturumlarını kapat</button>
                        )}
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </TableWrap>
            )}
            <p className="mt-2 text-[11.5px] text-canvas-muted">
              Kaynaklar: Active Directory {hy.sources.ad ? `${fmtN(hy.sources.adPeople)} etkin kişi` : 'okunamadı'} · CRM{' '}
              {hy.sources.crm ? `${fmtN(hy.sources.crmUsers)} etkin kullanıcı` : 'okunamadı'} · giriş kaydı{' '}
              {hy.loginsSince ? `${fmtAt(hy.loginsSince)}'den beri` : 'boş'} · tarama {fmtAt(hy.at)}
            </p>
          </div>
        )}
      </Panel>
      <EveryonePreviewPanel />
      <AskSheet
        open={!!ask}
        title="Oturumlarını kapat"
        message={<p>«{ask}» kişisinin bütün açık portal oturumları kapanacak. Active Directory hesabı etkin olmadığı için yeniden giriş yapamaz.</p>}
        confirm="Oturumları kapat"
        danger
        busy={revoke.isPending}
        onClose={() => setAsk(null)}
        onConfirm={() => ask && revoke.mutate(ask)}
      />
    </>
  );
}

/** «Herkes» rolü daraltılırsa kim hangi sayfayı kaybeder. Önce «yalnız Kampüs» hâli hesaplanır; sayfa seçilirse yalnız
 *  seçilenler çıkarılmış hâl. Hesap sunucuda, bugünkü rol ve bağlarla; hiçbir şey kaydedilmez. */
function EveryonePreviewPanel() {
  const [picked, setPicked] = useState<string[]>([]);
  const [run, setRun] = useState(false);
  const all = useQuery({ queryKey: ['security', 'everyone', 'all'], queryFn: () => securityApi.previewEveryone({ perms: [] }), enabled: ENGINE_ENABLED && run, staleTime: 120_000 });
  const some = useQuery({
    queryKey: ['security', 'everyone', picked],
    queryFn: () => securityApi.previewEveryone({ remove: picked }),
    enabled: ENGINE_ENABLED && run && picked.length > 0,
    staleTime: 120_000,
  });
  const pages = useMemo(() => (all.data?.byKey ?? []).filter((k) => k.key.startsWith('sayfa:')), [all.data]);
  const view = picked.length ? some.data : all.data;
  const err = picked.length ? some.error : all.error;
  const loading = picked.length ? some.isFetching : all.isFetching;

  return (
    <Panel>
      <h2 className="flex items-center gap-1 text-[16px] font-extrabold tracking-tight">
        «Herkes» daraltma önizlemesi
        <SqlInfo k={kaynakOf(view)} alan="_hepsi" label="Kaybeden kişi sayıları" />
      </h2>
      <p className="text-[12px] text-canvas-muted">
        «Herkes» rolü giriş yapan her çalışana uygulanır ve daraltılması önerilir. Bu önizleme, daraltılırsa kimin hangi sayfayı
        kaybedeceğini bugünkü roller ve Active Directory grup üyelikleriyle hesaplar. Burada hiçbir şey değişmez; daraltma Yönetim → Yetkiler’de yapılır.
      </p>
      {!run && (
        <div className="mt-3">
          <button type="button" className={btnPrimary} onClick={() => setRun(true)}>Önizlemeyi hesapla</button>
        </div>
      )}
      {err && <div className="mt-2"><Note tone="err">{errText(err, 'Önizleme hesaplanamadı.')}</Note></div>}
      {view?.note && <div className="mt-2"><Note tone="warn">{view.note}</Note></div>}
      {run && loading && !view && <p className="mt-3 text-[12px] text-canvas-muted">Hesaplanıyor…</p>}
      {pages.length > 0 && (
        <div className="mt-3">
          <div className="text-[11px] font-bold uppercase tracking-wide text-canvas-muted">Yalnız şu sayfaları çıkar (seçilmezse: yalnız Kampüs kalır)</div>
          <div className="mt-1.5 flex flex-wrap gap-1.5">
            {pages.map((p) => {
              const on = picked.includes(p.key);
              return (
                <button
                  key={p.key}
                  type="button"
                  aria-pressed={on}
                  onClick={() => setPicked(on ? picked.filter((x) => x !== p.key) : [...picked, p.key])}
                  className={`min-h-11 rounded-lg px-2.5 text-[12px] font-bold sm:min-h-8 ${on ? 'bg-canvas-violet text-white' : 'bg-slate-100'}`}
                >
                  {p.label}
                </button>
              );
            })}
          </div>
        </div>
      )}
      {view && (
        <>
          <p className="mt-3 text-[12.5px] font-bold">
            {fmtN(view.people)} kişiden {fmtN(view.affected)} kişi bir şey kaybeder
            {view.admins ? ` (${fmtN(view.admins)} yönetici hesaplanmadı: her şeyi görür)` : ''}.
          </p>
          <div className="mt-2 grid gap-3 lg:grid-cols-2">
            <TableWrap>
              <thead>
                <tr className="border-b border-slate-100">
                  <th className={th}>Yetki</th>
                  <th className={`${th} text-right`}>Kaybeden kişi</th>
                </tr>
              </thead>
              <tbody>
                {view.byKey.map((k) => (
                  <tr key={k.key} className="border-b border-slate-50 last:border-0">
                    <td className={td}>{k.label}</td>
                    <td className={`${td} text-right font-mono tabular-nums`}>{fmtN(k.lose)}</td>
                  </tr>
                ))}
                {!view.byKey.length && <tr><td className={td} colSpan={2}>Kimse bir şey kaybetmiyor.</td></tr>}
              </tbody>
            </TableWrap>
            <TableWrap>
              <thead>
                <tr className="border-b border-slate-100">
                  <th className={th}>Kişi</th>
                  <th className={th}>Kaybedilen sayfalar</th>
                </tr>
              </thead>
              <tbody>
                {view.items.map((r) => (
                  <tr key={r.username} className="border-b border-slate-50 last:border-0">
                    <td className={td}>
                      <div className="font-bold">{r.display}</div>
                      <div className="text-[11px] text-canvas-muted">{r.roles.length ? r.roles.join(', ') : 'rolü yok'}</div>
                    </td>
                    <td className={`${td} max-w-[420px] break-words text-[11.5px]`}>
                      {r.lostPages.length ? r.lostPages.join(', ') : `${r.lost.length} işlem/veri yetkisi`}
                    </td>
                  </tr>
                ))}
              </tbody>
            </TableWrap>
          </div>
        </>
      )}
    </Panel>
  );
}
