import { useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Check, ChevronLeft, ChevronRight, Plus, Undo2 } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import { Loading, Note, btnGhost, btnPrimary, errText, field, label as labelCls } from '../admin/ui';
import { Kpi, KpiRow } from '../editorial/kit';
import { AskSheet } from '../budget/parts';
import { addDays, fmtDay, fmtShort, mondayOf, socialApi, timeOf, todayIso, type Post } from './api';
import { AccountTag, Block, DaysLeft, SocialFrame, StatusPill } from './parts';
import NewPost, { type NewPostSeed } from './NewPost';

/** M22 ilk açılış: bütün hesapların tek takvimi. Telefonda gün görünümü, masaüstünde hafta. Sağda onay bekleyenler
 *  (onay yetkisi olan tek dokunuşla onaylar) ve yaklaşan fırsatlar. Adres: ?gun=YYYY-AA-GG&gorunum=gun|hafta&hesap=… */

const isPhone = () => typeof window !== 'undefined' && window.matchMedia('(max-width: 767px)').matches;

function PostChip({ p }: { p: Post }) {
  const warn = (p.uyarilar ?? []).filter((w) => w.kod !== 'lisans');
  return (
    <Link to={`/sosyal-medya/gonderi/${encodeURIComponent(p.id)}`}
      className="flex min-h-11 flex-col gap-1 rounded-xl border border-slate-100 bg-white/90 px-2.5 py-2 text-left transition-colors duration-150 hover:border-canvas-violet/40">
      <span className="flex items-center justify-between gap-2">
        <span className="font-mono text-[11px] font-bold tabular-nums text-canvas-muted">{timeOf(p.plannedAt) || '—'}</span>
        <StatusPill status={p.status} label={p.statusAdi} />
      </span>
      <AccountTag account={p.account} />
      <span className="line-clamp-2 break-words text-[12px] font-semibold leading-snug">
        {p.kitapAd || p.occasionAd || p.text || 'Başlıksız fikir'}
      </span>
      {warn.length > 0 && p.status !== 'yayinlandi' && (
        <span className="text-[11px] font-semibold leading-snug text-amber-800">{warn.map((w) => w.metin).join(' ')}</span>
      )}
    </Link>
  );
}

export default function SocialCalendar() {
  const qc = useQueryClient();
  const [params, setParams] = useSearchParams();
  const view = (params.get('gorunum') as 'gun' | 'hafta' | null) ?? (isPhone() ? 'gun' : 'hafta');
  const anchor = params.get('gun') || todayIso();
  const account = params.get('hesap') ?? '';
  const frm = view === 'hafta' ? mondayOf(anchor) : anchor;
  const to = view === 'hafta' ? addDays(frm, 6) : anchor;
  const [seed, setSeed] = useState<NewPostSeed | null>(null);
  const [rejecting, setRejecting] = useState<Post | null>(null);

  const set = (next: Record<string, string | null>) => {
    const p = new URLSearchParams(params);
    for (const [k, v] of Object.entries(next)) {
      if (v) p.set(k, v);
      else p.delete(k);
    }
    setParams(p, { replace: true });
  };

  const meta = useQuery({ queryKey: ['social', 'meta'], queryFn: socialApi.meta, enabled: ENGINE_ENABLED, staleTime: 60_000 });
  const accounts = useQuery({ queryKey: ['social', 'accounts'], queryFn: socialApi.accounts, enabled: ENGINE_ENABLED });
  const cal = useQuery({ queryKey: ['social', 'calendar', frm, to, account], queryFn: () => socialApi.calendar(frm, to, account), enabled: ENGINE_ENABLED });
  const opp = useQuery({ queryKey: ['social', 'opportunities', 'home'], queryFn: () => socialApi.opportunities(), enabled: ENGINE_ENABLED, staleTime: 5 * 60_000 });

  const decide = useMutation({
    mutationFn: ({ id, ok, note }: { id: string; ok: boolean; note?: string }) => socialApi.act(id, ok ? 'approve' : 'reject', { note }),
    onSuccess: (p) => {
      qc.invalidateQueries({ queryKey: ['social'] });
      toast.success(p.status === 'onayli' ? 'Onaylandı. Paylaşımı ekip yapar.' : 'Geri gönderildi.');
      setRejecting(null);
    },
    onError: (e) => toast.error(errText(e, 'İşlem yapılamadı.') ?? ''),
  });

  const days = useMemo(() => {
    const n = view === 'hafta' ? 7 : 1;
    return Array.from({ length: n }, (_, i) => addDays(frm, i));
  }, [frm, view]);
  const byDay = useMemo(() => {
    const m: Record<string, Post[]> = {};
    for (const p of cal.data?.items ?? []) (m[(p.plannedAt ?? '').slice(0, 10)] ??= []).push(p);
    return m;
  }, [cal.data]);

  const m = meta.data;
  const c = cal.data?.counts ?? {};
  const step = view === 'hafta' ? 7 : 1;
  const today = todayIso();
  const pending = cal.data?.onayBekleyen ?? [];
  const warnDays = (opp.data?.ozelGunler ?? []).filter((o) => o.uyari);

  const aside = m ? (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-end gap-2">
        <div className="flex rounded-xl bg-slate-100 p-1" role="radiogroup" aria-label="Görünüm">
          {([['gun', 'Gün'], ['hafta', 'Hafta']] as const).map(([v, l]) => (
            <button key={v} type="button" role="radio" aria-checked={view === v}
              className={`min-h-11 rounded-lg px-3 text-[12.5px] font-extrabold transition-colors duration-150 sm:min-h-9 ${view === v ? 'bg-white text-canvas-ink shadow-sm' : 'text-canvas-muted'}`}
              onClick={() => set({ gorunum: v })}>
              {l}
            </button>
          ))}
        </div>
        <label className="flex min-w-[180px] flex-1 flex-col gap-1">
          <span className={labelCls}>Hesap</span>
          <select className={field} value={account} onChange={(e) => set({ hesap: e.target.value || null })}>
            <option value="">Bütün hesaplar</option>
            {(accounts.data?.items ?? []).map((a) => <option key={a.id} value={a.id}>{a.ad}</option>)}
          </select>
        </label>
      </div>
      <div className="flex items-center gap-1.5">
        <button type="button" className={btnGhost} aria-label="Önceki" onClick={() => set({ gun: addDays(anchor, -step) })}>
          <ChevronLeft aria-hidden className="h-4 w-4" />
        </button>
        <button type="button" className={btnGhost} onClick={() => set({ gun: null })}>Bugün</button>
        <button type="button" className={btnGhost} aria-label="Sonraki" onClick={() => set({ gun: addDays(anchor, step) })}>
          <ChevronRight aria-hidden className="h-4 w-4" />
        </button>
        <span className="min-w-0 flex-1 truncate text-right text-[12.5px] font-bold">
          {view === 'hafta' ? `${fmtShort(frm)} – ${fmtShort(to)}` : fmtDay(anchor)}
        </span>
        {m.me.canEdit && (
          <button type="button" className={btnPrimary} onClick={() => setSeed({ day: view === 'gun' ? anchor : today >= frm && today <= to ? today : frm })}>
            <Plus aria-hidden className="h-4 w-4" />
            Yeni
          </button>
        )}
      </div>
    </div>
  ) : null;

  return (
    <SocialFrame
      crumb="Sosyal medya"
      title="Sosyal medya takvimi"
      lead="Bütün imprint hesaplarının paylaşımları tek takvimde: kitaptan içerik, onay ve yayına hazır paket. Portal hiçbir hesaba kendiliğinden paylaşım yapmaz; onaylı gönderiyi ekip paylaşır ve bağlantısını girer."
      source={m?.lastRun?.tarih ? `CRM · son özet ${fmtShort(m.lastRun.tarih)}` : 'CRM + stüdyo'}
      presence={cal.data ? `${cal.data.total.toLocaleString('tr-TR')} gönderi` : '…'}
      aside={aside}
    >
      {!ENGINE_ENABLED && <Note tone="warn">Zeki AI bağlantısı bu derlemede tanımlı değil.</Note>}
      {meta.error && <Note tone="err">{errText(meta.error, 'Sosyal medya bilgisi açılamadı.')}</Note>}
      {m?.lastRun?.eposta === 'no_recipient' && <Note tone="warn">Sabah özeti gönderilemedi: alıcı yok (Yönetim → Sosyal medya).</Note>}
      {m?.lastRun?.eposta === 'no_smtp' && <Note tone="warn">Sabah özeti gönderilemedi: e-posta ayarı yok (Yönetim → E-posta).</Note>}
      {accounts.data && accounts.data.total === 0 && (
        <Note tone="info">
          Henüz hesap tanımlı değil. <Link className="font-extrabold text-canvas-violet underline" to="/sosyal-medya/hesaplar">Hesaplar</Link> sekmesinden
          imprint hesaplarını ekleyin (CRM'deki marka kartlarının Instagram adları öneri olarak gelir).
        </Note>
      )}

      {cal.data && (
        <KpiRow>
          <Kpi label="Taslak ve fikir" value={((c.taslak ?? 0) + (c.fikir ?? 0)).toLocaleString('tr-TR')} help="Bu aralıkta metni ya da onayı bekleyen" />
          <Kpi label="Onay bekleyen" value={pending.length.toLocaleString('tr-TR')} help="Bütün tarihlerde onaya gönderilmiş" />
          <Kpi label="Onaylı" value={(c.onayli ?? 0).toLocaleString('tr-TR')} help="Paket hazır; paylaşım ekipte" />
          <Kpi label="Yayınlandı" value={(c.yayinlandi ?? 0).toLocaleString('tr-TR')} help="Bağlantısı girilmiş" />
        </KpiRow>
      )}

      <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_360px] lg:gap-4">
        <section className="glass-panel min-w-0 rounded-2xl p-3 shadow-glass-float sm:rounded-3xl sm:p-4" aria-label="Takvim">
          {cal.error && <Note tone="err">{errText(cal.error, 'Takvim açılamadı.')}</Note>}
          {cal.isLoading && <Loading />}
          {cal.data && (
            <div className={`grid gap-2 ${view === 'hafta' ? 'md:grid-cols-2 xl:grid-cols-7' : ''}`}>
              {days.map((d) => (
                <div key={d} className={`flex min-w-0 flex-col gap-1.5 rounded-2xl p-2 ${d === today ? 'bg-canvas-violet/5 ring-1 ring-canvas-violet/30' : 'bg-slate-50/70'}`}>
                  <div className="flex items-center justify-between gap-1">
                    <span className={`text-[12px] font-extrabold ${d === today ? 'text-canvas-violet' : ''}`}>{fmtDay(d)}</span>
                    {m?.me.canEdit && (
                      <button type="button" aria-label={`${fmtDay(d)} için yeni gönderi`} onClick={() => setSeed({ day: d })}
                        className="inline-flex h-9 w-9 items-center justify-center rounded-lg text-canvas-muted transition-transform duration-150 ease-out hover:bg-white active:scale-[0.97]">
                        <Plus aria-hidden className="h-4 w-4" />
                      </button>
                    )}
                  </div>
                  {(byDay[d] ?? []).map((p) => <PostChip key={p.id} p={p} />)}
                  {!(byDay[d] ?? []).length && <span className="px-1 pb-1 text-[11px] text-canvas-muted">Paylaşım yok</span>}
                </div>
              ))}
            </div>
          )}
          {cal.data && cal.data.unscheduled.length > 0 && (
            <div className="mt-3">
              <h2 className="mb-1.5 text-[13px] font-extrabold">Tarihsiz fikir ve taslaklar ({cal.data.unscheduled.length})</h2>
              <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
                {cal.data.unscheduled.map((p) => <PostChip key={p.id} p={p} />)}
              </div>
            </div>
          )}
        </section>

        <div className="flex min-w-0 flex-col gap-3">
          <Block title={`Onay bekleyen (${pending.length})`} help={m?.me.canApprove ? 'Onaya gönderen kişi aynı gönderiyi onaylayamaz.' : 'Onay yetkisi olan kişi onaylar.'}>
            {pending.length === 0 && <p className="text-[12px] text-canvas-muted">Onay bekleyen gönderi yok.</p>}
            <div className="flex flex-col gap-2">
              {pending.map((p) => (
                <div key={p.id} className="flex flex-col gap-1.5 rounded-xl bg-white/80 p-2.5">
                  <Link to={`/sosyal-medya/gonderi/${encodeURIComponent(p.id)}`} className="min-w-0 hover:underline">
                    <AccountTag account={p.account} />
                    <div className="mt-0.5 line-clamp-2 text-[12px] font-semibold">{p.kitapAd || p.occasionAd || p.text}</div>
                    <div className="text-[11px] text-canvas-muted">{p.plannedAt ? `${fmtShort(p.plannedAt)} ${timeOf(p.plannedAt)}` : 'Tarihsiz'} · {p.submittedBy}</div>
                  </Link>
                  {m?.me.canApprove && p.submittedBy?.toLowerCase() !== m.me.username.toLowerCase() && (
                    <div className="flex gap-1.5">
                      <button type="button" className={`${btnPrimary} flex-1`} disabled={decide.isPending} onClick={() => decide.mutate({ id: p.id, ok: true })}>
                        <Check aria-hidden className="h-4 w-4" />
                        Onayla
                      </button>
                      <button type="button" className={`${btnGhost} flex-1`} disabled={decide.isPending} onClick={() => setRejecting(p)}>
                        <Undo2 aria-hidden className="h-4 w-4" />
                        Geri gönder
                      </button>
                    </div>
                  )}
                </div>
              ))}
            </div>
          </Block>

          <Block title="Yaklaşan fırsatlar" action={<Link to="/sosyal-medya/firsatlar" className={btnGhost}>Hepsi</Link>}
            help={m ? `Özel güne ${m.settings.leadDays} gün ya da daha az kalıp bağlı kitaplardan hiçbiri takvimde değilse uyarı.` : undefined}>
            {opp.isLoading && <Loading />}
            {opp.error && <Note tone="err">{errText(opp.error, 'Fırsatlar okunamadı.')}</Note>}
            {opp.data && (
              <div className="flex flex-col gap-1.5">
                {(warnDays.length ? warnDays : opp.data.ozelGunler.slice(0, 5)).map((o) => (
                  <Link key={o.key} to={`/sosyal-medya/firsatlar#${o.key}`}
                    className="flex min-h-11 items-center justify-between gap-2 rounded-xl bg-white/80 px-2.5 py-2 transition-colors duration-150 hover:bg-white">
                    <span className="min-w-0">
                      <span className="block truncate text-[12.5px] font-bold">{o.ad}</span>
                      <span className="text-[11px] text-canvas-muted">{o.kitapSayisi} bağlı kitap · {o.takvimde} takvimde</span>
                    </span>
                    <DaysLeft days={o.kalanGun} running={o.suruyor} />
                  </Link>
                ))}
                {opp.data.ozelGunler.length === 0 && <p className="text-[12px] text-canvas-muted">Pencerede özel gün yok.</p>}
                <p className="pt-1 text-[11.5px] text-canvas-muted">
                  Bu ay ve yakında çıkan {opp.data.yeniKitaplar.items.length.toLocaleString('tr-TR')} kitaptan{' '}
                  {opp.data.yeniKitaplar.items.filter((b) => !b.takvimde).length.toLocaleString('tr-TR')} tanesi takvimde değil.
                </p>
              </div>
            )}
          </Block>
        </div>
      </div>

      {m && accounts.data && <NewPost open={!!seed} seed={seed} meta={m} accounts={accounts.data.items} onClose={() => setSeed(null)} />}
      <AskSheet open={!!rejecting} title="Geri gönder" message={<>Gönderi taslağa döner; gerekçe gönderene iletilir.</>} confirm="Geri gönder"
        input="Gerekçe" required busy={decide.isPending} onClose={() => setRejecting(null)}
        onConfirm={(note) => rejecting && decide.mutate({ id: rejecting.id, ok: false, note })} />
    </SocialFrame>
  );
}
