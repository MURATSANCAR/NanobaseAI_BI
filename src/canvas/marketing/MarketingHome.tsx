import { useCallback, useEffect, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { RefreshCw, Search } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import { Loading, Note, btnGhost, errText, field, label as labelCls } from '../admin/ui';
import { Kpi, KpiRow, Pager, Panel, useDebounced } from '../editorial/kit';
import { fmtDay, mktApi } from './api';
import { MarketingFrame } from './parts';
import NewBooksList from './NewBooksList';

/** M15 Yeni kitap pazarlama planı — ilk açılış. Süzgeçler adres çubuğunda (?durum=, ?kim=, ?bas=, ?bit=, ?yayinevi=, ?q=). */

const DURUM = [
  ['', 'Hepsi'],
  ['plansiz', 'Planı yok'],
  ['taslak', 'Taslak'],
  ['geri', 'Geri gönderildi'],
  ['onayda', 'Onay bekliyor'],
  ['onayli', 'Onaylı'],
  ['materyal', 'Materyali eksik'],
  ['hedef', 'Hedefi değişen'],
] as const;

const iso = (d: Date) => d.toISOString().slice(0, 10);

export default function MarketingHome() {
  const qc = useQueryClient();
  const nav = useNavigate();
  const [params, setParams] = useSearchParams();
  const meta = useQuery({ queryKey: ['mkt', 'meta'], queryFn: mktApi.meta, enabled: ENGINE_ENABLED, staleTime: 60_000 });
  const horizon = meta.data?.settings.horizonDays ?? 120;
  const today = new Date();
  const frm = params.get('bas') || iso(today);
  const to = params.get('bit') || iso(new Date(today.getTime() + horizon * 86_400_000));
  const durum = params.get('durum') ?? '';
  const kim = params.get('kim') ?? 'ben';
  const yayinevi = params.get('yayinevi') ?? '';
  const [q, setQ] = useState(params.get('q') ?? '');
  const dq = useDebounced(q, 300);
  const [page, setPage] = useState(0);
  const [busy, setBusy] = useState<string | null>(null);

  const update = useCallback(
    (next: Record<string, string | null>) => {
      const p = new URLSearchParams(params);
      for (const [k, v] of Object.entries(next)) {
        if (v) p.set(k, v);
        else p.delete(k);
      }
      setParams(p, { replace: true });
      setPage(0);
    },
    [params, setParams],
  );
  useEffect(() => {
    if ((params.get('q') ?? '') !== dq) update({ q: dq || null });
  }, [dq]); // eslint-disable-line react-hooks/exhaustive-deps

  const list = useQuery({
    queryKey: ['mkt', 'new-books', frm, to, durum, kim, yayinevi, dq, page],
    queryFn: () => mktApi.newBooks({ frm, to, durum, sahip: kim === 'ben' ? 'ben' : '', yayinevi, q: dq, page }),
    enabled: ENGINE_ENABLED && !!meta.data,
    placeholderData: keepPreviousData,
  });

  const refresh = useMutation({
    mutationFn: () => mktApi.newBooks({ frm, to, durum, sahip: kim === 'ben' ? 'ben' : '', yayinevi, q: dq, page, yenile: true }),
    onSuccess: (d) => qc.setQueryData(['mkt', 'new-books', frm, to, durum, kim, yayinevi, dq, page], d),
    onError: (e) => toast.error(errText(e, 'CRM okunamadı.') ?? ''),
  });

  const create = useMutation({
    mutationFn: async ({ stok, ai }: { stok: string; ai: boolean }) => {
      setBusy(stok);
      const plan = await mktApi.create(stok);
      if (ai) await mktApi.suggest(plan.id);
      return { plan, ai };
    },
    onSuccess: ({ plan, ai }) => {
      qc.invalidateQueries({ queryKey: ['mkt'] });
      toast.success(ai ? 'Plan açıldı; Zeki AI önerisi hazırlanıyor.' : 'Plan açıldı.');
      nav(`/pazarlama/plan/${encodeURIComponent(plan.id)}`);
    },
    onError: (e) => toast.error(errText(e, 'Plan açılamadı.') ?? ''),
    onSettled: () => setBusy(null),
  });

  const m = meta.data;
  const d = list.data;
  const k = d?.kpi;
  const setDurum = (v: string) => update({ durum: v || null, kim: 'hepsi' });

  const aside = m ? (
    <div className="flex flex-col gap-2">
      <div className="grid grid-cols-2 gap-2">
        <label className="flex flex-col gap-1">
          <span className={labelCls}>Yayın başı</span>
          <input type="date" className={field} value={frm} onChange={(e) => update({ bas: e.target.value || null })} />
        </label>
        <label className="flex flex-col gap-1">
          <span className={labelCls}>Yayın sonu</span>
          <input type="date" className={field} value={to} onChange={(e) => update({ bit: e.target.value || null })} />
        </label>
      </div>
      <div className="flex rounded-xl bg-slate-100 p-1" role="radiogroup" aria-label="Kimin işleri">
        {[['ben', 'Bana düşenler'], ['hepsi', 'Hepsi']].map(([v, l]) => (
          <button key={v} type="button" role="radio" aria-checked={kim === v}
            className={`min-h-11 flex-1 rounded-lg text-[12.5px] font-extrabold transition-colors duration-150 sm:min-h-9 ${kim === v ? 'bg-white text-canvas-ink shadow-sm' : 'text-canvas-muted'}`}
            onClick={() => update({ kim: v })}>
            {l}
          </button>
        ))}
      </div>
    </div>
  ) : null;

  return (
    <MarketingFrame
      crumb="Yeni kitap planı"
      title="Yeni kitap pazarlama planı"
      lead="Yayına hazırlanan her kitap için karne (emsal ve yazarın gerçek satışı, onaylı hedef), kanal ve bütçe, yayın gününden geri sayan takvim ve materyal taslakları. Zeki AI önerir, pazarlama müdürü onaylar; dış kanala hiçbir şey kendiliğinden gönderilmez."
      source={m?.lastRun?.tarih ? `CRM · son hatırlatma ${fmtDay(m.lastRun.tarih)}` : 'CRM + Logo'}
      presence={d ? `${d.hepsi.toLocaleString('tr-TR')} kitap` : '…'}
      aside={aside}
    >
      {!ENGINE_ENABLED && <Note tone="warn">Zeki AI bağlantısı bu derlemede tanımlı değil.</Note>}
      {meta.error && <Note tone="err">{errText(meta.error, 'Pazarlama bilgisi açılamadı.')}</Note>}
      {m?.lastRun?.eposta === 'no_smtp' && <Note tone="warn">Günlük hatırlatma gönderilemedi: e-posta ayarı yok (Yönetim → E-posta).</Note>}
      {m?.lastRun?.eposta === 'no_recipient' && <Note tone="warn">Günlük hatırlatma gönderilemedi: alıcı yok (Yönetim → Pazarlama planları).</Note>}

      {k && m && (
        <KpiRow>
          <Kpi label="Planı yok" value={k.plansiz.toLocaleString('tr-TR')} help={`Yayına ${m.settings.noPlanDays} gün ya da daha az kalan`} active={durum === 'plansiz'} onClick={() => setDurum(durum === 'plansiz' ? '' : 'plansiz')} />
          <Kpi label="Onay bekleyen" value={k.onayda.toLocaleString('tr-TR')} help="Onaya gönderilmiş planlar" active={durum === 'onayda'} onClick={() => setDurum(durum === 'onayda' ? '' : 'onayda')} />
          <Kpi label="Materyali eksik" value={k.materyalEksik.toLocaleString('tr-TR')} help={`Yayına ${m.settings.materialDays} gün kala onaylı materyali eksik`} active={durum === 'materyal'} onClick={() => setDurum(durum === 'materyal' ? '' : 'materyal')} />
          <Kpi label="Hedefi değişen" value={k.hedefDegisti.toLocaleString('tr-TR')} help="Bütçe planı revize edildi; plan gözden geçirilmeli" active={durum === 'hedef'} onClick={() => setDurum(durum === 'hedef' ? '' : 'hedef')} />
        </KpiRow>
      )}

      <Panel>
        <div className="mb-3 flex flex-col gap-2 lg:flex-row lg:items-end">
          <label className="flex min-w-0 flex-1 flex-col gap-1">
            <span className={labelCls}>Ara</span>
            <span className="relative flex items-center">
              <Search aria-hidden className="pointer-events-none absolute left-3 h-4 w-4 text-canvas-muted" />
              <input className={`${field} pl-9`} value={q} placeholder="Kitap adı, yazar ya da stok kodu" onChange={(e) => setQ(e.target.value)} />
            </span>
          </label>
          <label className="flex flex-col gap-1 lg:w-[200px]">
            <span className={labelCls}>Durum</span>
            <select className={field} value={durum} onChange={(e) => update({ durum: e.target.value || null })}>
              {DURUM.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </select>
          </label>
          <label className="flex flex-col gap-1 lg:w-[220px]">
            <span className={labelCls}>Yayınevi</span>
            <select className={field} value={yayinevi} onChange={(e) => update({ yayinevi: e.target.value || null })}>
              <option value="">Hepsi</option>
              {(d?.yayinevleri ?? []).map((y) => <option key={y} value={y}>{y}</option>)}
            </select>
          </label>
          <button type="button" className={btnGhost} onClick={() => refresh.mutate()} disabled={refresh.isPending}>
            <RefreshCw aria-hidden className={`h-4 w-4 ${refresh.isPending ? 'animate-spin' : ''}`} />
            CRM'den yenile
          </button>
        </div>

        {list.error && <Note tone="err">{errText(list.error, 'Liste açılamadı.')}</Note>}
        {list.isLoading && <Loading />}
        {d && m && d.items.length > 0 && <NewBooksList rows={d.items} meta={m} busy={busy} onCreate={(stok, ai) => create.mutate({ stok, ai })} />}
        {d && d.items.length === 0 && (
          <div className="flex flex-col items-start gap-2 py-6 text-[12.5px] text-canvas-muted">
            {kim === 'ben' && d.hepsi > 0
              ? <>Bu aralıkta size düşen kitap yok (sorumlusu olduğunuz ya da onayınızı bekleyen). Aralıkta {d.hepsi.toLocaleString('tr-TR')} kitap var.
                  <button type="button" className={btnGhost} onClick={() => update({ kim: 'hepsi' })}>Hepsini göster</button></>
              : 'Bu süzgeçle kitap yok.'}
          </div>
        )}
        {d && d.total > 0 && (
          <Pager page={page} pageSize={d.pageSize} total={d.total} shown={d.items.length} loading={list.isLoading} fetching={list.isFetching} onPage={setPage} />
        )}
      </Panel>
    </MarketingFrame>
  );
}
