import { useEffect, useMemo, useRef, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Check, Download, ExternalLink, Plus, Search, Send, Sparkles, Trash2, Undo2, X } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import SqlInfo from '../components/SqlInfo';
import { Loading, Note, Pill, btnGhost, btnPrimary, errText, field, label as labelCls } from '../admin/ui';
import { useDebounced } from '../editorial/kit';
import { AskSheet } from '../budget/parts';
import {
  DROP_REASON, EVENT_LABEL, charCount, fmtInt, fmtStamp, socialApi, tagCount, todayIso,
  type AssetRef, type MetricKey, type Post, type PostInput,
} from './api';
import { AccountTag, Block, SocialFrame, StatusPill } from './parts';

/** Gönderi: metin, etiket, görsel, zaman; kitaptan içerik (CRM metinleri, alıntılar, stüdyo görselleri), Zeki AI'ın üç
 *  seçeneği, onay ve yayına hazır paket. Telefonda tek sütun: önce metin ve düğmeler, sonra kitap havuzu. */

type Ask = null | { kind: 'reject' | 'cancel' | 'published' | 'delete' };
type Form = { accountId: string | null; kind: string | null; text: string; hashtags: string; day: string; time: string; assets: AssetRef[] };
const EDITABLE = new Set(['fikir', 'taslak', 'onayli']);

function refKey(a: AssetRef) {
  return a.tip === 'studio' ? `s:${a.job}:${a.sid}` : `c:${a.id}`;
}

export default function SocialPost() {
  const { id = '' } = useParams();
  const nav = useNavigate();
  const qc = useQueryClient();
  const meta = useQuery({ queryKey: ['social', 'meta'], queryFn: socialApi.meta, enabled: ENGINE_ENABLED, staleTime: 60_000 });
  const accounts = useQuery({ queryKey: ['social', 'accounts'], queryFn: socialApi.accounts, enabled: ENGINE_ENABLED });
  const post = useQuery({ queryKey: ['social', 'post', id], queryFn: () => socialApi.post(id), enabled: ENGINE_ENABLED && !!id });
  const p = post.data;
  const platform = p?.account?.platform ?? '';
  const content = useQuery({
    queryKey: ['social', 'content', p?.stokKodu, platform],
    queryFn: () => socialApi.content(p!.stokKodu!, platform),
    enabled: ENGINE_ENABLED && !!p?.stokKodu,
    staleTime: 5 * 60_000,
  });
  const jobs = useQuery({
    queryKey: ['social', 'jobs', id],
    queryFn: () => socialApi.jobs(id),
    enabled: ENGINE_ENABLED && !!id,
    refetchInterval: (q) => (q.state.data?.items?.[0] && ['bekliyor', 'calisiyor'].includes(q.state.data.items[0].durum) ? 2500 : false),
  });
  const events = useQuery({ queryKey: ['social', 'events', id], queryFn: () => socialApi.events(id), enabled: ENGINE_ENABLED && !!id });

  // Form: gönderi yüklenince (ya da sunucuda değişince) doldurulur; kaydedilmemiş değişiklik ayrıca izlenir.
  const [form, setForm] = useState<Form>({ accountId: null, kind: null, text: '', hashtags: '', day: '', time: '', assets: [] });
  const stamp = p ? `${p.id}:${p.status}:${p.text}:${p.hashtags}:${p.plannedAt}:${p.accountId}:${p.kind}:${p.assets.length}` : '';
  useEffect(() => {
    if (!p) return;
    setForm({ accountId: p.accountId, kind: p.kind, text: p.text ?? '', hashtags: p.hashtags ?? '', day: p.plannedAt?.slice(0, 10) ?? '',
      time: p.plannedAt?.slice(11, 16) ?? '', assets: p.assets });
  }, [stamp]); // eslint-disable-line react-hooks/exhaustive-deps

  const lastJob = jobs.data?.items?.[0];
  const wasRunning = useRef(false);
  useEffect(() => {
    const running = !!lastJob && ['bekliyor', 'calisiyor'].includes(lastJob.durum);
    if (wasRunning.current && !running) {
      qc.invalidateQueries({ queryKey: ['social', 'post', id] });
      if (lastJob?.durum === 'hata') toast.error(lastJob.hata || 'Zeki AI taslağı yazılamadı.');
      else if (lastJob?.sonuc && (lastJob.sonuc as { uyari?: string }).uyari) toast.warning(String((lastJob.sonuc as { uyari?: string }).uyari));
    }
    wasRunning.current = running;
  }, [lastJob, id, qc]);

  const [ask, setAsk] = useState<Ask>(null);
  const [q, setQ] = useState('');
  const dq = useDebounced(q, 300);
  const books = useQuery({ queryKey: ['social', 'books', dq, 0], queryFn: () => socialApi.books(dq, 0), enabled: ENGINE_ENABLED && !p?.stokKodu && dq.trim().length >= 2, placeholderData: keepPreviousData });
  const [metric, setMetric] = useState<Partial<Record<MetricKey, string>> & { day: string }>({ day: todayIso() });

  const refresh = (np?: Post) => {
    if (np) qc.setQueryData(['social', 'post', id], (old: Post | undefined) => ({ ...(old ?? {}), ...np }) as Post);
    qc.invalidateQueries({ queryKey: ['social'] });
  };
  const save = useMutation({
    mutationFn: (b: PostInput) => socialApi.update(id, b),
    onSuccess: (np, b) => {
      refresh(np);
      if (p?.status === 'onayli' && np.status === 'taslak') toast.warning('İçerik değişti: onay düştü, yeniden onaya gönderin.');
      else if (!('assets' in b) || Object.keys(b).length > 1) toast.success('Kaydedildi.');
    },
    onError: (e) => toast.error(errText(e, 'Kaydedilemedi.') ?? ''),
  });
  const act = useMutation({
    mutationFn: ({ action, note, url }: { action: Parameters<typeof socialApi.act>[1]; note?: string; url?: string }) => socialApi.act(id, action, { note, url }),
    onSuccess: (np) => {
      refresh(np);
      setAsk(null);
      toast.success(np.statusAdi);
    },
    onError: (e) => toast.error(errText(e, 'İşlem yapılamadı.') ?? ''),
  });
  const draft = useMutation({
    mutationFn: () => socialApi.draft(id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['social', 'jobs', id] }); toast.message('Zeki AI üç seçenek yazıyor…'); },
    onError: (e) => toast.error(errText(e, 'Zeki AI taslağı başlatılamadı.') ?? ''),
  });
  const remove = useMutation({
    mutationFn: () => socialApi.remove(id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['social'] }); nav('/sosyal-medya'); },
    onError: (e) => toast.error(errText(e, 'Silinemedi.') ?? ''),
  });
  const addMetric = useMutation({
    mutationFn: () => {
      const b: Partial<Record<MetricKey, number | null>> & { day?: string } = { day: metric.day };
      for (const k of ['impressions', 'reach', 'likes', 'comments', 'shares', 'saves'] as MetricKey[]) {
        const v = (metric[k] ?? '').trim().replace(/\./g, '').replace(',', '.');
        if (v) b[k] = Number(v);
      }
      return socialApi.addMetric(id, b);
    },
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['social', 'post', id] }); setMetric({ day: todayIso() }); toast.success('İçgörü kaydedildi.'); },
    onError: (e) => toast.error(errText(e, 'İçgörü kaydedilemedi.') ?? ''),
  });

  const m = meta.data;
  const editable = !!p && EDITABLE.has(p.status) && !!m?.me.canEdit;
  const limit = m && platform ? m.settings.limits[platform] : undefined;
  const tagLimit = m && platform ? m.settings.tagLimits[platform] : undefined;
  const count = charCount(form.text, form.hashtags);
  const tags = tagCount(form.hashtags);
  const planned = form.day ? `${form.day} ${form.time || m?.settings.defaultHour || '10:00'}` : null;
  const dirty = !!p && (form.accountId !== p.accountId || (form.kind ?? null) !== (p.kind ?? null) || form.text !== (p.text ?? '')
    || form.hashtags !== (p.hashtags ?? '') || planned !== p.plannedAt);
  const selected = useMemo(() => new Set(form.assets.map(refKey)), [form.assets]);
  const running = !!lastJob && ['bekliyor', 'calisiyor'].includes(lastJob.durum);

  const saveForm = () =>
    save.mutate(p?.status === 'yayinlandi'
      ? { kind: form.kind || null }
      : { accountId: form.accountId, kind: form.kind || null, text: form.text || null, hashtags: form.hashtags || null, plannedAt: planned });
  const toggleAsset = (a: AssetRef) => {
    const next = selected.has(refKey(a)) ? form.assets.filter((x) => refKey(x) !== refKey(a)) : [...form.assets, a];
    setForm({ ...form, assets: next });
    save.mutate({ assets: next });
  };
  const append = (s: string) => setForm((f) => ({ ...f, text: f.text ? `${f.text.trimEnd()}\n\n${s}` : s }));

  if (!ENGINE_ENABLED) return <SocialFrame crumb="Gönderi" title="Gönderi" source="—" presence="—"><Note tone="warn">Veri bağlantısı kurulu değil; bu ekran şu an veri gösteremez. Sistem yöneticinize haber verin.</Note></SocialFrame>;

  const title = p ? p.kitapAd || p.occasionAd || (p.text ?? '').slice(0, 60) || p.id : 'Gönderi';
  const c = content.data;

  return (
    <SocialFrame
      crumb="Gönderi"
      title={title}
      source={p ? `${p.id} · ${p.createdBy}` : '…'}
      presence={p?.statusAdi ?? '…'}
      lead="Tek gönderinin metni, etiketleri, görselleri ve onayı. Adımlar: fikir → taslak → onayda → onaylı → yayınlandı. Paylaşımı siz kendi hesabınızdan yaparsınız, sonra bağlantıyı girip «yayınlandı» işaretlersiniz."
      back={{ to: '/sosyal-medya', label: 'Takvim' }}
      tabs={false}
    >
      {post.error && <Note tone="err">{errText(post.error, 'Gönderi açılamadı.')}</Note>}
      {post.isLoading && <Loading />}
      {p && m && (
        <>
          <div className="flex flex-wrap items-center gap-2 px-1">
            <StatusPill status={p.status} label={p.statusAdi} />
            <AccountTag account={p.account} />
            {p.kindAdi && <Pill tone="muted">{p.kindAdi}{p.kindSource === 'zeki' ? ' · Zeki AI' : ''}</Pill>}
            {p.occasionAd && <Pill tone="violet">{p.occasionAd}</Pill>}
            {p.approvedBy && <span className="text-[11.5px] text-canvas-muted">Onaylayan {p.approvedBy} · {fmtStamp(p.approvedAt)}</span>}
          </div>
          {p.note && p.status === 'taslak' && <Note tone="warn">Geri gönderme gerekçesi: {p.note}</Note>}
          {p.note && p.status === 'iptal' && <Note tone="err">İptal gerekçesi: {p.note}</Note>}
          {(p.uyarilar ?? []).map((w) => <Note key={w.kod} tone={w.kod === 'lisans' ? 'info' : 'warn'}>{w.metin}</Note>)}
          {p.status === 'onayli' && editable && <Note tone="info">Onaylı gönderinin metnini, etiketini, hesabını ya da görselini değiştirirseniz onay düşer; yalnız saati değiştirmek onayı korur.</Note>}

          <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_420px] lg:gap-4">
            <div className="flex min-w-0 flex-col gap-3">
              <Block title="Gönderi" info={<SqlInfo k={p.kaynaklar} alan="uyarilar" label="Karakter, etiket ve tür olasılığı" />}>
                <div className="grid gap-2 sm:grid-cols-2">
                  <label className="flex flex-col gap-1 sm:col-span-2">
                    <span className={labelCls}>Hesap</span>
                    <select className={field} disabled={!editable} value={form.accountId ?? ''} onChange={(e) => setForm({ ...form, accountId: e.target.value || null })}>
                      <option value="">Seçilmedi</option>
                      {(accounts.data?.items ?? []).filter((a) => a.aktif || a.id === form.accountId).map((a) => (
                        <option key={a.id} value={a.id}>{a.ad} ({a.platformAdi} {a.handle})</option>
                      ))}
                    </select>
                  </label>
                  <label className="flex flex-col gap-1">
                    <span className={labelCls}>Gün</span>
                    <input type="date" className={field} disabled={!editable} value={form.day} onChange={(e) => setForm({ ...form, day: e.target.value })} />
                  </label>
                  <label className="flex flex-col gap-1">
                    <span className={labelCls}>Saat</span>
                    <input type="time" className={field} disabled={!editable} value={form.time} onChange={(e) => setForm({ ...form, time: e.target.value })} />
                  </label>
                  <label className="flex flex-col gap-1 sm:col-span-2">
                    <span className={labelCls}>İçerik türü</span>
                    <select className={field} disabled={!m.me.canEdit || p.status === 'onayda' || p.status === 'iptal'} value={form.kind ?? ''}
                      onChange={(e) => setForm({ ...form, kind: e.target.value || null })}>
                      <option value="">Girilmedi (Zeki AI önerir)</option>
                      {Object.entries(m.kinds).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                    </select>
                  </label>
                  <label className="flex flex-col gap-1 sm:col-span-2">
                    <span className="flex items-baseline justify-between gap-2">
                      <span className={labelCls}>Metin</span>
                      <span className={`font-mono text-[11px] font-bold tabular-nums ${limit && count > limit ? 'text-red-700' : 'text-canvas-muted'}`}>
                        {fmtInt(count)}{limit ? ` / ${fmtInt(limit)}` : ''}
                      </span>
                    </span>
                    <textarea className={`${field} min-h-[180px] leading-relaxed`} disabled={!editable} value={form.text}
                      onChange={(e) => setForm({ ...form, text: e.target.value })} placeholder="Paylaşım metni" />
                  </label>
                  <label className="flex flex-col gap-1 sm:col-span-2">
                    <span className="flex items-baseline justify-between gap-2">
                      <span className={labelCls}>Etiketler</span>
                      <span className={`font-mono text-[11px] font-bold tabular-nums ${tagLimit && tags > tagLimit ? 'text-red-700' : 'text-canvas-muted'}`}>
                        {tags}{tagLimit ? ` / ${tagLimit}` : ''}
                      </span>
                    </span>
                    <input className={field} disabled={!editable} value={form.hashtags} placeholder="#kitap #okuma"
                      onChange={(e) => setForm({ ...form, hashtags: e.target.value })} />
                  </label>
                </div>

                <div className="mt-3 flex flex-wrap gap-2">
                  {m.me.canEdit && (EDITABLE.has(p.status) || p.status === 'yayinlandi') && (
                    <button type="button" className={btnPrimary} disabled={!dirty || save.isPending} onClick={saveForm}>Kaydet</button>
                  )}
                  {m.me.canEdit && (p.status === 'fikir' || p.status === 'taslak') && (
                    <>
                      <button type="button" className={btnGhost} disabled={running || draft.isPending || !m.modelReady} onClick={() => draft.mutate()}
                        title={m.modelReady ? undefined : 'Zeki AI şu an bağlı değil'}>
                        <Sparkles aria-hidden className="h-4 w-4" />
                        {running ? (lastJob?.adim || 'Zeki AI yazıyor…') : 'Zeki AI taslağı'}
                      </button>
                      <button type="button" className={btnGhost} disabled={dirty || act.isPending} onClick={() => act.mutate({ action: 'submit' })}
                        title={dirty ? 'Önce kaydedin' : undefined}>
                        <Send aria-hidden className="h-4 w-4" />
                        Onaya gönder
                      </button>
                    </>
                  )}
                  {p.status === 'onayda' && m.me.canEdit && (
                    <button type="button" className={btnGhost} disabled={act.isPending} onClick={() => act.mutate({ action: 'withdraw' })}>
                      <Undo2 aria-hidden className="h-4 w-4" />
                      Onaydan geri çek
                    </button>
                  )}
                  {p.status === 'onayda' && m.me.canApprove && p.submittedBy?.toLowerCase() !== m.me.username.toLowerCase() && (
                    <>
                      <button type="button" className={btnPrimary} disabled={act.isPending} onClick={() => act.mutate({ action: 'approve' })}>
                        <Check aria-hidden className="h-4 w-4" />
                        Onayla
                      </button>
                      <button type="button" className={btnGhost} onClick={() => setAsk({ kind: 'reject' })}>Geri gönder</button>
                    </>
                  )}
                  {(p.status === 'onayli' || p.status === 'yayinlandi') && m.me.canExport && (
                    <a className={btnGhost} href={socialApi.packageUrl(p.id)} download>
                      <Download aria-hidden className="h-4 w-4" />
                      Paylaşıma hazır paketi indir
                    </a>
                  )}
                  {p.status === 'onayli' && m.me.canEdit && (
                    <button type="button" className={btnPrimary} onClick={() => setAsk({ kind: 'published' })}>Yayınlandı olarak işaretle</button>
                  )}
                  {p.status === 'yayinlandi' && p.publishedUrl && (
                    <a className={btnGhost} href={p.publishedUrl} target="_blank" rel="noreferrer">
                      <ExternalLink aria-hidden className="h-4 w-4" />
                      Paylaşımı aç
                    </a>
                  )}
                  {m.me.canEdit && !['yayinlandi', 'iptal'].includes(p.status) && (
                    <button type="button" className={btnGhost} onClick={() => setAsk({ kind: 'cancel' })}>İptal et</button>
                  )}
                  {m.me.canEdit && p.status === 'iptal' && (
                    <button type="button" className={btnGhost} disabled={act.isPending} onClick={() => act.mutate({ action: 'reopen' })}>Yeniden aç</button>
                  )}
                  {m.me.canEdit && (p.status === 'fikir' || p.status === 'taslak') && (
                    <button type="button" className={`${btnGhost} text-red-700`} onClick={() => setAsk({ kind: 'delete' })}>
                      <Trash2 aria-hidden className="h-4 w-4" />
                      Sil
                    </button>
                  )}
                </div>
              </Block>

              {p.draft && p.draft.secenekler.length > 0 && (
                <Block title="Zeki AI seçenekleri"
                  info={<SqlInfo k={p.kaynaklar} alan="draft" label="Zeki AI seçenekleri" />}
                  help={`${fmtStamp(p.draft.zaman)} · ${p.draft.kim}. Kaynakta olmayan alıntı, rakam ya da kanıtsız iddia içeren ${p.draft.dusen} cümle düşürüldü. Seçtiğiniz metin forma gelir; kaydetmeden bir şey değişmez.`}>
                  <div className="grid gap-2 xl:grid-cols-3">
                    {p.draft.secenekler.map((o, i) => (
                      <div key={i} className="flex flex-col gap-2 rounded-xl bg-white/80 p-2.5">
                        <p className="whitespace-pre-wrap break-words text-[12.5px] leading-relaxed">{o.metin}</p>
                        {o.etiketler && <p className="break-words text-[12px] font-semibold text-canvas-violet">{o.etiketler}</p>}
                        <div className="mt-auto flex items-center justify-between gap-2">
                          <span className={`font-mono text-[11px] font-bold ${o.uzun ? 'text-red-700' : 'text-canvas-muted'}`}>{fmtInt(o.karakter)} karakter{o.uzun ? ' · uzun' : ''}</span>
                          {editable && (
                            <button type="button" className={btnGhost} onClick={() => setForm({ ...form, text: o.metin, hashtags: o.etiketler })}>Kullan</button>
                          )}
                        </div>
                        {o.dusen.length > 0 && (
                          <details className="text-[11px] text-canvas-muted">
                            <summary className="inline-flex min-h-8 cursor-pointer items-center font-bold">Düşen cümleler ({o.dusen.length})</summary>
                            <ul className="mt-1 list-disc pl-4">{o.dusen.map((d, j) => <li key={j}>{d.cumle} — {DROP_REASON[d.neden] ?? d.neden}</li>)}</ul>
                          </details>
                        )}
                      </div>
                    ))}
                  </div>
                </Block>
              )}

              <Block title={`Görseller (${form.assets.length})`}
                help="Görselin kendisi kaynağında durur (kitap tasarım stüdyosu ya da içerik arşivi); paylaşıma hazır pakete oradan girer.">
                {form.assets.length === 0 && <p className="text-[12px] text-canvas-muted">Görsel eklenmedi. Kitap havuzundan seçin.</p>}
                <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
                  {form.assets.map((a) => (
                    <div key={refKey(a)} className="relative overflow-hidden rounded-xl bg-white/80">
                      {a.tip === 'studio' && a.job && a.sid
                        ? <img src={socialApi.studioImageUrl(a.job, a.sid, 320)} alt={a.ad || 'Stüdyo görseli'} className="aspect-square w-full object-cover" loading="lazy" />
                        : <div className="flex aspect-square items-center justify-center p-2 text-center text-[11.5px] text-canvas-muted">{a.ad || a.id}</div>}
                      <div className="flex items-center justify-between gap-1 px-2 py-1 text-[11px] font-semibold">
                        <span className="truncate">{a.ad || (a.tip === 'studio' ? 'Stüdyo' : 'Arşiv')}</span>
                        {editable && (
                          <button type="button" aria-label="Görseli çıkar" onClick={() => toggleAsset(a)}
                            className="inline-flex h-8 w-8 items-center justify-center rounded-lg transition-transform duration-150 ease-out hover:bg-slate-100 active:scale-[0.97]">
                            <X aria-hidden className="h-3.5 w-3.5" />
                          </button>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </Block>

              {p.status === 'yayinlandi' && (
                <Block title="İçgörü" info={<SqlInfo k={p.kaynaklar} alan="olcumler" label="İçgörü" />} help="Platformun kendi ekranından okunan sayılar ya da Rapor sekmesinden içe aktarılan dosya. Portal platformlara bağlanmaz.">
                  {(p.olcumler ?? []).length > 0 && (
                    <div className="mb-2 overflow-x-auto">
                      <table className="w-full min-w-[520px] text-[12px]">
                        <thead><tr className="text-left text-[11px] uppercase tracking-wide text-canvas-muted">
                          <th className="py-1">Gün</th>{(['reach', 'impressions', 'likes', 'comments', 'shares', 'saves'] as MetricKey[]).map((k) => <th key={k} className="py-1">{m.metrics[k]}</th>)}<th className="py-1">Kaynak</th>
                        </tr></thead>
                        <tbody>{(p.olcumler ?? []).map((r) => (
                          <tr key={r.id} className="border-t border-slate-100">
                            <td className="py-1 font-mono">{r.day}</td>
                            {(['reach', 'impressions', 'likes', 'comments', 'shares', 'saves'] as MetricKey[]).map((k) => <td key={k} className="py-1 font-mono tabular-nums">{fmtInt(r[k] ?? null)}</td>)}
                            <td className="py-1">{r.kaynak === 'elle' ? 'Elle' : 'Dosya'}</td>
                          </tr>))}
                        </tbody>
                      </table>
                    </div>
                  )}
                  {m.me.canEdit && (
                    <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
                      <label className="flex flex-col gap-1">
                        <span className={labelCls}>Gün</span>
                        <input type="date" className={field} value={metric.day} onChange={(e) => setMetric({ ...metric, day: e.target.value })} />
                      </label>
                      {(['reach', 'impressions', 'likes', 'comments', 'shares', 'saves'] as MetricKey[]).map((k) => (
                        <label key={k} className="flex flex-col gap-1">
                          <span className={labelCls}>{m.metrics[k]}</span>
                          <input inputMode="numeric" className={field} value={metric[k] ?? ''} onChange={(e) => setMetric({ ...metric, [k]: e.target.value })} />
                        </label>
                      ))}
                      <div className="flex items-end">
                        <button type="button" className={btnPrimary} disabled={addMetric.isPending} onClick={() => addMetric.mutate()}>Kaydet</button>
                      </div>
                    </div>
                  )}
                </Block>
              )}

              <Block title="Geçmiş" info={<SqlInfo k={events.data?.kaynaklar} alan="items" label="Gönderi geçmişi" />}>
                <ol className="flex flex-col gap-1.5">
                  {(events.data?.items ?? []).map((e) => (
                    <li key={e.id} className="text-[12px] leading-snug">
                      <span className="font-bold">{EVENT_LABEL[e.ne] ?? e.ne}</span> · {e.kim} · <span className="text-canvas-muted">{fmtStamp(e.zaman)}</span>
                      {e.not && <div className="text-canvas-muted">{e.not}</div>}
                    </li>
                  ))}
                </ol>
              </Block>
            </div>

            <div className="flex min-w-0 flex-col gap-3">
              <Block title="Kitaptan içerik" info={<SqlInfo k={c?.kaynaklar} alan="kitap" label="Kitaptan içerik" />} help={p.stokKodu ? `${p.kitapAd ?? ''} · ${p.stokKodu}` : 'Kitap bağlanınca CRM metinleri, alıntılar ve stüdyo görselleri burada.'}>
                {!p.stokKodu && editable && (
                  <div className="flex flex-col gap-1.5">
                    <span className="relative flex items-center">
                      <Search aria-hidden className="pointer-events-none absolute left-3 h-4 w-4 text-canvas-muted" />
                      <input className={`${field} pl-9`} value={q} placeholder="Kitap adı ya da stok kodu" onChange={(e) => setQ(e.target.value)} />
                    </span>
                    {(books.data?.items ?? []).map((b) => (
                      <button key={b.stokKodu} type="button" className="flex min-h-11 flex-col items-start rounded-xl bg-white/80 px-2.5 py-2 text-left transition-colors duration-150 hover:bg-white"
                        onClick={() => save.mutate({ stokKodu: b.stokKodu, kitapAd: b.ad, crmBookId: b.kitapId })}>
                        <span className="text-[12.5px] font-bold">{b.ad}</span>
                        <span className="text-[11px] text-canvas-muted">{[b.yazar, b.yayinevi, b.stokKodu].filter(Boolean).join(' · ')}</span>
                      </button>
                    ))}
                  </div>
                )}
                {content.isLoading && <Loading />}
                {content.error && <Note tone="err">{errText(content.error, 'Kitap bilgisi okunamadı.')}</Note>}
                {c && (
                  <div className="flex flex-col gap-3">
                    {c.haklar.length > 0 && (
                      <Note tone="warn">
                        Telif sözleşmesinde hak açıklaması var; kitaptan alıntı paylaşmadan önce okuyun:{' '}
                        {c.haklar.map((h) => `${h.sozlesme ?? ''}: ${h.hak ?? ''}`).join(' · ')}
                      </Note>
                    )}
                    {c.kitap.metinler.map((t) => (
                      <details key={t.alan} className="rounded-xl bg-white/80 p-2.5" open={t.alan === 'new_sosyalmedyametni'}>
                        <summary className="flex min-h-8 cursor-pointer items-center justify-between gap-2 text-[12.5px] font-bold">
                          {t.ad}
                          {editable && t.alan !== 'new_hastag' && t.alan !== 'new_AnahtarKelimeler' && (
                            <button type="button" className={btnGhost} onClick={(e) => { e.preventDefault(); append(t.metin); }}>
                              <Plus aria-hidden className="h-3.5 w-3.5" />
                              Metne ekle
                            </button>
                          )}
                          {editable && t.alan === 'new_hastag' && (
                            <button type="button" className={btnGhost} onClick={(e) => { e.preventDefault(); setForm({ ...form, hashtags: `${form.hashtags} ${t.metin}`.trim() }); }}>
                              Etiketlere ekle
                            </button>
                          )}
                        </summary>
                        <p className="mt-1.5 whitespace-pre-wrap break-words text-[12px] leading-relaxed text-canvas-ink">{t.metin}</p>
                      </details>
                    ))}
                    {(c.alintilar.crm.length > 0 || c.alintilar.studyo.length > 0) && (
                      <div>
                        <h3 className="mb-1 text-[12.5px] font-extrabold">Alıntılar</h3>
                        <p className="mb-1.5 text-[11px] text-canvas-muted">Alıntıyı kısa tutun (en çok iki cümle).</p>
                        <ul className="flex flex-col gap-1.5">
                          {[...c.alintilar.crm.map((x) => ({ x, s: 'CRM' })), ...c.alintilar.studyo.map((x) => ({ x, s: 'Kitap metni' }))].map(({ x, s }, i) => (
                            <li key={i} className="flex items-start justify-between gap-2 rounded-xl bg-white/80 p-2 text-[12px] leading-snug">
                              <span className="min-w-0 break-words">«{x}» <span className="text-[10.5px] text-canvas-muted">{s}</span></span>
                              {editable && (
                                <button type="button" aria-label="Alıntıyı metne ekle" className={btnGhost} onClick={() => append(`«${x}»`)}>
                                  <Plus aria-hidden className="h-3.5 w-3.5" />
                                </button>
                              )}
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}
                    <div>
                      <h3 className="mb-1 text-[12.5px] font-extrabold">Stüdyo sosyal görselleri</h3>
                      {c.gorseller.studyoHata && <p className="text-[11.5px] text-amber-800">{c.gorseller.studyoHata}</p>}
                      {c.gorseller.studyo.length === 0 && !c.gorseller.studyoHata && (
                        <p className="text-[11.5px] text-canvas-muted">Bu kitabın stüdyoda sosyal görseli yok (Kitap Tasarım Stüdyosu → Pazarlama kiti).</p>
                      )}
                      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-2">
                        {c.gorseller.studyo.map((a) => {
                          const on = selected.has(refKey(a));
                          return (
                            <button key={refKey(a)} type="button" disabled={!editable} onClick={() => toggleAsset(a)} aria-pressed={on}
                              className={`overflow-hidden rounded-xl bg-white/80 text-left transition-transform duration-150 ease-out active:scale-[0.98] ${on ? 'ring-2 ring-canvas-violet' : ''}`}>
                              {a.job && a.sid && <img src={socialApi.studioImageUrl(a.job, a.sid, 320)} alt={a.ad || 'Stüdyo görseli'} className="aspect-square w-full object-cover" loading="lazy" />}
                              <span className="flex items-center justify-between gap-1 px-2 py-1 text-[11px] font-semibold">
                                <span className="truncate">{a.boyut}</span>
                                {a.onayli ? <Pill tone="ok">Onaylı</Pill> : <Pill tone="muted">Taslak</Pill>}
                              </span>
                            </button>
                          );
                        })}
                      </div>
                    </div>
                    {c.gorseller.arsiv.bagli && (
                      <div>
                        <h3 className="mb-1 text-[12.5px] font-extrabold">İçerik arşivi (onaylı)</h3>
                        {c.gorseller.arsiv.items.length === 0 && <p className="text-[11.5px] text-canvas-muted">Bu kitabın onaylı arşiv varlığı yok.</p>}
                        <div className="flex flex-col gap-1.5">
                          {c.gorseller.arsiv.items.map((a) => (
                            <button key={refKey(a)} type="button" disabled={!editable} onClick={() => toggleAsset(a)} aria-pressed={selected.has(refKey(a))}
                              className={`flex min-h-11 items-center justify-between gap-2 rounded-xl bg-white/80 px-2.5 text-left text-[12px] font-semibold ${selected.has(refKey(a)) ? 'ring-2 ring-canvas-violet' : ''}`}>
                              <span className="truncate">{a.ad}</span>
                              <span className="text-[11px] text-canvas-muted">{a.boyut}</span>
                            </button>
                          ))}
                        </div>
                      </div>
                    )}
                    {c.gonderiler.filter((x) => x.id !== p.id).length > 0 && (
                      <div>
                        <h3 className="mb-1 text-[12.5px] font-extrabold">Bu kitabın diğer gönderileri</h3>
                        <ul className="flex flex-col gap-1">
                          {c.gonderiler.filter((x) => x.id !== p.id).map((x) => (
                            <li key={x.id}>
                              <Link to={`/sosyal-medya/gonderi/${encodeURIComponent(x.id)}`} className="flex min-h-9 items-center justify-between gap-2 text-[12px] hover:underline">
                                <span className="truncate">{x.plannedAt ?? 'Tarihsiz'} · {x.account?.ad ?? 'hesap yok'}</span>
                                <StatusPill status={x.status} label={x.statusAdi} />
                              </Link>
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </div>
                )}
              </Block>
            </div>
          </div>
        </>
      )}

      <AskSheet open={ask?.kind === 'reject'} title="Geri gönder" message="Gönderi taslağa döner; gerekçe gönderene iletilir." confirm="Geri gönder"
        input="Gerekçe" required busy={act.isPending} onClose={() => setAsk(null)} onConfirm={(note) => act.mutate({ action: 'reject', note })} />
      <AskSheet open={ask?.kind === 'cancel'} title="Gönderiyi iptal et" message="İptal edilen gönderi takvimde kalır ama paylaşılmaz; yeniden açılabilir." confirm="İptal et"
        danger input="Gerekçe" required busy={act.isPending} onClose={() => setAsk(null)} onConfirm={(note) => act.mutate({ action: 'cancel', note })} />
      <AskSheet open={ask?.kind === 'published'} title="Yayınlandı olarak işaretle"
        message="Paylaşımı kendi hesabınızdan yaptıktan sonra bağlantısını yapıştırın. İçgörü bu bağlantıyla eşleşir." confirm="Yayınlandı"
        input="Paylaşımın bağlantısı (https://…)" required busy={act.isPending} onClose={() => setAsk(null)} onConfirm={(url) => act.mutate({ action: 'published', url })} />
      <AskSheet open={ask?.kind === 'delete'} title="Gönderiyi sil" message="Taslak ve geçmişi silinir. Geri alınamaz." confirm="Sil" danger
        busy={remove.isPending} onClose={() => setAsk(null)} onConfirm={() => remove.mutate()} />
    </SocialFrame>
  );
}
