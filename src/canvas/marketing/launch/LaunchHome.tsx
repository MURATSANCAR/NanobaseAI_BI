import { useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { AlertTriangle, Check, Rocket } from 'lucide-react';
import { ENGINE_ENABLED } from '../../engine';
import { Loading, Note, Pill, btnPrimary, errText, field, label as labelCls } from '../../admin/ui';
import { fmtDay } from '../api';
import { Block, MarketingFrame } from '../parts';
import { TONE_CLASS, TONE_LABEL, dLabel, launchApi, type LaunchHead, type LaunchRisk, type RiskLevel, type TodayTask } from './api';

/** M16 Lansman — ilk açılış: bu hafta ve gelecek 4 haftanın lansman şeridi (yayında ve ilk ay izlemesinde olanlar da),
 *  altında bütün lansmanların bugün yapılacak ve geciken maddeleri. Telefonda şerit yatay kayar, maddeler 44 px. */

const iso = (d: Date) => d.toISOString().slice(0, 10);

function Strip({ items }: { items: LaunchHead[] }) {
  return (
    <div className="-mx-1 overflow-x-auto px-1 pb-1">
      <ol className="flex w-max min-w-full snap-x gap-2.5">
        {items.map((x) => (
          <li key={x.id} className="w-[250px] shrink-0 snap-start sm:w-[280px]">
            <Link
              to={`/pazarlama/lansman/${encodeURIComponent(x.id)}`}
              className="glass-panel flex h-full min-h-11 flex-col gap-2 rounded-2xl p-3 shadow-glass-float transition-transform duration-150 ease-out active:scale-[0.98]"
            >
              <div className="flex items-start gap-2.5">
                {x.kapak ? (
                  <img src={x.kapak} alt="" loading="lazy" className="h-16 w-11 shrink-0 rounded-md bg-slate-100 object-cover" />
                ) : (
                  <div aria-hidden className="h-16 w-11 shrink-0 rounded-md bg-slate-100" />
                )}
                <div className="min-w-0">
                  <div className="line-clamp-2 break-words text-[13px] font-extrabold leading-snug">{x.baslik}</div>
                  <div className="mt-0.5 text-[11px] text-canvas-muted">{fmtDay(x.yayinGunu)} · {x.stokKodu}</div>
                </div>
              </div>
              <div className="mt-auto flex flex-wrap items-center gap-1.5">
                <span className="rounded-md bg-slate-900 px-1.5 py-0.5 font-mono text-[11px] font-bold tabular-nums text-white">{dLabel(x.gun)}</span>
                {x.renk && <span className={`rounded-md px-1.5 py-0.5 text-[11px] font-bold ring-1 ring-inset ${TONE_CLASS[x.renk]}`}>{TONE_LABEL[x.renk]}</span>}
                <Pill tone="muted">{x.durumAdi}</Pill>
                {!!x.gecikenMadde && <Pill tone="err">{x.gecikenMadde} gecikmiş madde</Pill>}
              </div>
              {x.risk && x.risk.duzey !== 'yok' ? (
                <RiskLine risk={x.risk} />
              ) : (
                x.uyarilar[0] && <div className="line-clamp-2 text-[11px] leading-snug text-canvas-muted">{x.uyarilar[0]}</div>
              )}
            </Link>
          </li>
        ))}
      </ol>
    </div>
  );
}

const RISK_CLASS: Record<Exclude<RiskLevel, 'yok'>, string> = {
  yuksek: 'bg-red-50 text-red-800 ring-red-200',
  orta: 'bg-amber-50 text-amber-900 ring-amber-200',
};

/** Kural eşikli risk bayrağı + tek cümle. Bayrak kuraldır; cümleyi Zeki AI yazdıysa (gece, denetimli) öyle etiketlenir. */
function RiskLine({ risk }: { risk: LaunchRisk }) {
  if (risk.duzey === 'yok') return null;
  return (
    <div className={`rounded-xl px-2 py-1.5 ring-1 ring-inset ${RISK_CLASS[risk.duzey]}`}>
      <div className="flex flex-wrap items-center gap-1 text-[11px] font-extrabold">
        <AlertTriangle aria-hidden className="h-3.5 w-3.5 shrink-0" />
        <span>{risk.duzeyAdi}</span>
        <span className="font-semibold opacity-80">· {risk.nedenler.map((n) => n.ad).join(', ')}</span>
      </div>
      {risk.cumle && (
        <p className="mt-0.5 line-clamp-3 break-words text-[11px] leading-snug">
          {risk.cumle}
          <span className="ml-1 whitespace-nowrap text-[10.5px] font-bold opacity-70">{risk.cumleKaynak === 'zeki' ? '· Zeki AI' : '· kurala göre'}</span>
        </p>
      )}
    </div>
  );
}

function TodayList({ items, canWrite, onDone, busy }: { items: TodayTask[]; canWrite: boolean; onDone: (t: TodayTask) => void; busy: string | null }) {
  const groups = new Map<string, TodayTask[]>();
  items.forEach((t) => groups.set(t.lansman, [...(groups.get(t.lansman) ?? []), t]));
  return (
    <div className="flex flex-col gap-3">
      {[...groups.entries()].map(([lid, ts]) => (
        <div key={lid}>
          <Link to={`/pazarlama/lansman/${encodeURIComponent(lid)}`} className="inline-flex min-h-8 items-center text-[12.5px] font-extrabold text-canvas-violet hover:underline">
            {ts[0].lansmanBaslik} · yayın {fmtDay(ts[0].yayinGunu)}
          </Link>
          <ul className="mt-1 flex flex-col gap-1.5">
            {ts.map((t) => (
              <li key={t.id} className={`flex min-h-11 items-center gap-2 rounded-xl border px-3 py-2 ${t.gecikti ? 'border-red-200 bg-red-50/60' : 'border-slate-100 bg-white/80'}`}>
                <div className="min-w-0 flex-1">
                  <div className="break-words text-[12.5px] font-semibold leading-snug">{t.is}</div>
                  <div className="text-[11px] text-canvas-muted">
                    {dLabel(t.gunFarki)} · {fmtDay(t.tarih)}{t.gecikti ? ' · gecikti' : ''} · {t.sorumluEtkin ?? 'sorumlu yok'}
                  </div>
                </div>
                {canWrite && (
                  <button type="button" disabled={busy === t.id} onClick={() => onDone(t)} aria-label={`«${t.is}» yapıldı`}
                    className="inline-flex min-h-11 shrink-0 items-center gap-1 rounded-xl bg-emerald-600 px-3 text-[12px] font-extrabold text-white transition-transform duration-150 ease-out active:scale-[0.97] disabled:opacity-60">
                    <Check aria-hidden className="h-4 w-4" />Yapıldı
                  </button>
                )}
              </li>
            ))}
          </ul>
        </div>
      ))}
    </div>
  );
}

export default function LaunchHome() {
  const qc = useQueryClient();
  const nav = useNavigate();
  const [params, setParams] = useSearchParams();
  const kim = params.get('kim') ?? 'ben';
  const [pick, setPick] = useState('');
  const [busy, setBusy] = useState<string | null>(null);
  const today = new Date();
  const frm = iso(new Date(today.getTime() - 31 * 86_400_000));
  const to = iso(new Date(today.getTime() + 35 * 86_400_000));

  const meta = useQuery({ queryKey: ['launch', 'meta'], queryFn: launchApi.meta, enabled: ENGINE_ENABLED, staleTime: 60_000 });
  const list = useQuery({ queryKey: ['launch', 'list', frm, to, kim], queryFn: () => launchApi.list({ frm, to, kim, durum: 'hazirlik,yayinda,izleme' }), enabled: ENGINE_ENABLED });
  const todo = useQuery({ queryKey: ['launch', 'today', kim], queryFn: () => launchApi.today(kim), enabled: ENGINE_ENABLED });
  const cands = useQuery({ queryKey: ['launch', 'candidates'], queryFn: launchApi.candidates, enabled: ENGINE_ENABLED && !!meta.data?.me.canWrite });

  const done = useMutation({
    mutationFn: (t: TodayTask) => { setBusy(t.id ?? null); return launchApi.task(t.lansman, t.id ?? '', { durum: 'yapildi' }); },
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['launch'] }); toast.success('Madde yapıldı olarak işaretlendi.'); },
    onError: (e) => toast.error(errText(e, 'Madde işaretlenemedi.') ?? ''),
    onSettled: () => setBusy(null),
  });
  const open = useMutation({
    mutationFn: (planId: string) => launchApi.create(planId),
    onSuccess: (l) => { qc.invalidateQueries({ queryKey: ['launch'] }); toast.success('Lansman paketi açıldı; veriler okunuyor.'); nav(`/pazarlama/lansman/${encodeURIComponent(l.id)}`); },
    onError: (e) => toast.error(errText(e, 'Lansman açılamadı.') ?? ''),
  });

  const m = meta.data;
  const items = list.data?.items ?? [];
  const soon = items.filter((x) => (x.gun ?? 0) < 0);
  const live = items.filter((x) => (x.gun ?? 0) >= 0);

  const aside = m ? (
    <div className="flex flex-col gap-2">
      <div className="flex rounded-xl bg-slate-100 p-1" role="radiogroup" aria-label="Kimin lansmanları">
        {[['ben', 'Bana düşenler'], ['hepsi', 'Hepsi']].map(([v, l]) => (
          <button key={v} type="button" role="radio" aria-checked={kim === v}
            className={`min-h-11 flex-1 rounded-lg text-[12.5px] font-extrabold transition-colors duration-150 sm:min-h-9 ${kim === v ? 'bg-white text-canvas-ink shadow-sm' : 'text-canvas-muted'}`}
            onClick={() => setParams({ kim: v }, { replace: true })}>
            {l}
          </button>
        ))}
      </div>
      {m.me.canWrite && (
        <div className="flex gap-2">
          <label className="flex min-w-0 flex-1 flex-col gap-1">
            <span className={labelCls}>Onaylı plandan lansman aç</span>
            <select className={field} value={pick} onChange={(e) => setPick(e.target.value)}>
              <option value="">{cands.data?.items.length ? 'Plan seçin' : 'Lansmanı açılmamış onaylı plan yok'}</option>
              {(cands.data?.items ?? []).map((p) => <option key={p.id} value={p.id}>{fmtDay(p.yayinTarihi)} · {p.baslik}</option>)}
            </select>
          </label>
          <button type="button" className={`${btnPrimary} self-end`} disabled={!pick || open.isPending} onClick={() => open.mutate(pick)}>
            <Rocket aria-hidden className="h-4 w-4" />Aç
          </button>
        </div>
      )}
    </div>
  ) : null;

  return (
    <MarketingFrame
      crumb="Lansman"
      title="Lansman ve yayın ayı"
      lead={`Onaylı pazarlama planından açılan lansman paketi: yayın gününe göre kontrol listesi, ilk 7 ve 30 günün sipariş, faturalı satış, stok ve hedef takibi, D+7 ve D+30 değerlendirmesi. Lansman, yayına ${m?.settings.openDays ?? 14} gün kala kendiliğinden açılır. Dış kanala hiçbir şey kendiliğinden gönderilmez; gönderiyi ekip yapar, burada işaretler.`}
      source={m?.lastRun?.tarih ? `CRM + Logo · son okuma ${fmtDay(m.lastRun.tarih)}` : 'CRM + Logo'}
      presence={list.data ? `${list.data.total} lansman` : '…'}
      aside={aside}
    >
      {!ENGINE_ENABLED && <Note tone="warn">Zeki AI bağlantısı bu derlemede tanımlı değil.</Note>}
      {meta.error && <Note tone="err">{errText(meta.error, 'Lansman bilgisi açılamadı.')}</Note>}
      {list.error && <Note tone="err">{errText(list.error, 'Lansmanlar açılamadı.')}</Note>}
      {list.isLoading && <Loading />}

      {list.data && (
        <>
          <Block title="Yayında ve ilk ay izlemesinde" help="Yayın gününden bu yana 30 gün dolmamış lansmanlar. Renk: stok–talep çatışması ya da hedef payının eşik altı kırmızı; geciken madde ya da hedefin altı sarı. Risk bayrağı kuraldır (stok, dağılım, hedef payı, emsal sapması, siparişsiz gün); karar sizindir.">
            {live.length ? <Strip items={live} /> : <p className="text-[12.5px] text-canvas-muted">Şu an yayında olan lansman yok.</p>}
          </Block>
          <Block title="Bu hafta ve gelecek 4 hafta" help="Yayın günü yaklaşan lansmanlar; gün sayacı yayın gününe göre.">
            {soon.length ? <Strip items={soon} /> : <p className="text-[12.5px] text-canvas-muted">Önümüzdeki 5 haftada açılmış lansman yok.</p>}
          </Block>
        </>
      )}

      <Block title="Bugün yapılacaklar" help={kim === 'ben' ? 'Sorumlusu siz olan maddeler (sorumlusu boşsa lansman sahibi). Geciken maddeler kırmızı.' : 'Bütün açık lansmanların bugün ve geciken maddeleri.'}>
        {todo.error && <Note tone="err">{errText(todo.error, 'Maddeler açılamadı.')}</Note>}
        {todo.isLoading && <Loading />}
        {todo.data && todo.data.items.length === 0 && <p className="text-[12.5px] text-canvas-muted">Bugün için bekleyen madde yok.</p>}
        {todo.data && todo.data.items.length > 0 && m && (
          <TodayList items={todo.data.items} canWrite={m.me.canWrite} busy={busy} onDone={(t) => done.mutate(t)} />
        )}
      </Block>
    </MarketingFrame>
  );
}
