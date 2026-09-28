import { useCallback, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { ArrowRight, Loader2, Plus, Search, Sparkles } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import { Loading, Note, Pill, btnGhost, btnPrimary, errText, field, label as labelCls } from '../admin/ui';
import { Kpi, KpiRow, Panel, useDebounced } from '../editorial/kit';
import SqlInfo from '../components/SqlInfo';
import Sheet from '../editorial/studio/reader/Sheet';
import { fmtDay, fmtLeft, fmtValue, riskApi, waitJob, type RiskInput, type RiskMeta, type Summary, type WithK } from './api';
import { Empty, LevelPill, RiskFrame, ScalePick, SelectInput, Tabs, TextInput } from './parts';
import HeatMap from './HeatMap';
import IndicatorsTab from './IndicatorCard';
import ComplianceCalendar from './ComplianceCalendar';
import ContinuityTab from './ContinuityTab';
import ReportsTab from './ReportsTab';

/** M47 Risk yönetimi ve uyum: özet (ısı haritası, gözden geçir kuyruğu, geciken aksiyon, bu ayın uyumu), risk kaydı,
 *  göstergeler, uyum takvimi, sigorta ve iş sürekliliği, kurul brifingi. Sekme ve süzgeçler adres çubuğunda. */

const TABS = [
  { key: 'ozet', label: 'Özet' },
  { key: 'kayit', label: 'Risk kaydı' },
  { key: 'gostergeler', label: 'Göstergeler' },
  { key: 'uyum', label: 'Uyum' },
  { key: 'sureklilik', label: 'BCP ve sigorta' },
  { key: 'raporlar', label: 'Raporlar' },
] as const;
type Tab = (typeof TABS)[number]['key'];

export default function RiskScreen() {
  const [params, setParams] = useSearchParams();
  const [creating, setCreating] = useState(false);
  const meta = useQuery({ queryKey: ['risk', 'meta'], queryFn: riskApi.meta, enabled: ENGINE_ENABLED, staleTime: 60_000 });
  const tab: Tab = (TABS.find((t) => t.key === params.get('sekme'))?.key ?? 'ozet') as Tab;
  const update = useCallback(
    (next: Record<string, string | null>) => {
      const p = new URLSearchParams(params);
      for (const [k, v] of Object.entries(next)) {
        if (v) p.set(k, v);
        else p.delete(k);
      }
      setParams(p, { replace: true });
    },
    [params, setParams],
  );
  const me = meta.data?.me;
  return (
    <RiskFrame
      title="Risk ve uyum"
      lead="Riskin sahibi, olasılık × etki puanı, aksiyonu ve gözden geçirmesi tek kayıtta. Göstergeler Logo, CRM ve portalın hazır raporlarından kendiliğinden ölçülür; eşiği aşan gösterge riski «gözden geçir» kuyruğuna koyar. Puanı ve kararı insan verir; göstergeler inceleme adayıdır."
      aside={
        me?.canWrite ? (
          <div className="flex justify-start lg:justify-end">
            <button type="button" className={btnPrimary} onClick={() => setCreating(true)}>
              <Plus aria-hidden className="h-4 w-4" />
              Yeni risk
            </button>
          </div>
        ) : undefined
      }
    >
      {!ENGINE_ENABLED && <Note tone="warn">Bu kurulumda veri bağlantısı tanımlı değil.</Note>}
      {meta.error && <Note tone="err">{errText(meta.error, 'Ekran bilgisi okunamadı.')}</Note>}
      <Tabs tabs={TABS} value={tab} onChange={(t) => update({ sekme: t === 'ozet' ? null : t, hucre: null })} />
      {meta.data && tab === 'ozet' && <Overview meta={meta.data} onCell={(h) => update({ sekme: 'kayit', hucre: h })} />}
      {meta.data && tab === 'kayit' && <Register meta={meta.data} params={params} update={update} />}
      {meta.data && tab === 'gostergeler' && <IndicatorsTab meta={meta.data} />}
      {meta.data && tab === 'uyum' && <ComplianceCalendar meta={meta.data} />}
      {meta.data && tab === 'sureklilik' && <ContinuityTab meta={meta.data} />}
      {meta.data && tab === 'raporlar' && <ReportsTab meta={meta.data} />}
      {meta.data && <RiskSheet open={creating} meta={meta.data} onClose={() => setCreating(false)} />}
    </RiskFrame>
  );
}

/* ------------------------------------------------------------------ Özet */

function Overview({ meta, onCell }: { meta: RiskMeta; onCell: (h: string) => void }) {
  const q = useQuery({ queryKey: ['risk', 'summary'], queryFn: riskApi.summary, enabled: ENGINE_ENABLED });
  const [cell, setCell] = useState<string | null>(null);
  if (q.isLoading) return <Loading />;
  if (q.error) return <Note tone="err">{errText(q.error, 'Özet okunamadı.')}</Note>;
  const s = q.data as Summary & WithK;
  const k = s.kaynaklar;
  const picked = cell ? s.isiHaritasi.flat().find((c) => `${c.olasilik}x${c.etki}` === cell) : null;
  return (
    <>
      <KpiRow>
        <Kpi label="Canlı risk" value={String(s.sayilar.canli)} help={`Kritik bantta ${s.sayilar.kritik}${s.puansiz ? ` · puansız ${s.puansiz}` : ''}`} info={<SqlInfo k={k} alan="sayilar" label="Canlı risk, kritik, puansız" />} />
        <Kpi label="Gözden geçir" value={String(s.kuyruk.length)} help="Eşiği aşan gösterge, tarihi gelen ya da sahipsiz risk" info={<SqlInfo k={k} alan="kuyruk" label="Gözden geçir kuyruğu" />} />
        <Kpi label="Geciken aksiyon" value={String(s.gecikenAksiyon.length)} help={`${meta.ayarlar.actionWarnDays} gün içinde termini gelen ${s.yaklasanAksiyon.length}`} info={<SqlInfo k={k} alan="gecikenAksiyon" label="Geciken ve yaklaşan aksiyon" />} />
        <Kpi label="Kırmızı gösterge" value={String(s.sayilar.kirmizi)} help={`${s.sayilar.gosterge} göstergeden; eşiği girilmemiş ${s.sayilar.esiksiz}`} info={<SqlInfo k={k} alan="sayilar.kirmizi" label="Kırmızı gösterge" />} />
      </KpiRow>
      {!s.tumunuGorur && <Note tone="info">Yalnız sahibi, açanı ya da aksiyon sahibi olduğunuz riskleri görüyorsunuz.</Note>}
      {s.oneriSayisi > 0 && <Note tone="info">Zeki AI'ın {s.oneriSayisi} risk önerisi kabul bekliyor (Risk kaydı → Öneriler).<SqlInfo k={k} alan="oneriSayisi" label="Öneri sayısı" className="ml-0.5" /></Note>}
      <div className="grid grid-cols-1 gap-3 lg:grid-cols-[minmax(0,420px)_minmax(0,1fr)] lg:gap-4">
        <Panel>
          <h2 className="mb-2 flex items-center gap-1 text-[15px] font-extrabold tracking-tight">Isı haritası<SqlInfo k={k} alan="isiHaritasi" label="Isı haritası" /></h2>
          <HeatMap grid={s.isiHaritasi} selected={cell} onSelect={setCell} levels={s.seviyeler} />
          {picked && (
            <div className="mt-3 flex flex-col gap-1">
              {picked.riskler.map((r) => (
                <Link key={r.id} to={`/risk-uyum/risk/${r.id}`} className="flex min-h-11 items-center justify-between gap-2 rounded-xl bg-white/80 px-3 py-2 text-[12.5px] font-bold hover:bg-white sm:min-h-0">
                  <span className="min-w-0 break-words">{r.baslik}</span>
                  <ArrowRight aria-hidden className="h-3.5 w-3.5 shrink-0" />
                </Link>
              ))}
              <button type="button" className={`${btnGhost} mt-1 self-start`} onClick={() => onCell(cell as string)}>Listede aç</button>
            </div>
          )}
        </Panel>
        <Panel>
          <h2 className="mb-2 flex items-center gap-1 text-[15px] font-extrabold tracking-tight">Gözden geçir kuyruğu<SqlInfo k={k} alan="kuyruk" label="Gözden geçir kuyruğu" /></h2>
          {s.kuyruk.length === 0 ? (
            <Empty>Kuyruk boş: eşiği aşan gösterge ya da tarihi gelen risk yok.</Empty>
          ) : (
            <ul className="flex flex-col gap-1.5">
              {s.kuyruk.map((k) => (
                <li key={k.risk.id}>
                  <Link to={`/risk-uyum/risk/${k.risk.id}?gozden=1`} className="flex min-h-11 flex-col gap-1 rounded-xl bg-white/80 px-3 py-2 hover:bg-white sm:flex-row sm:items-center sm:justify-between">
                    <span className="min-w-0">
                      <span className="block break-words text-[13px] font-bold">{k.risk.baslik}</span>
                      <span className="block text-[11.5px] leading-snug text-canvas-muted">
                        {k.nedenler.map((n) =>
                          n.tur === 'gosterge' ? `${n.ad}: ${fmtValue(n.deger ?? null, n.birim ?? '')} (kırmızı)` :
                          n.tur === 'tarih' ? `gözden geçirme ${n.gun ? `${n.gun} gün gecikti` : 'bugün'}` :
                          n.tur === 'sahipsiz' ? 'sahibi yok' : 'puanlanmadı').join(' · ')}
                        {k.risk.sahip ? ` — ${k.risk.sahip}` : ''}
                      </span>
                    </span>
                    <LevelPill level={k.risk.seviye} score={k.risk.puan} meta={meta} />
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </Panel>
      </div>
      <div className="grid grid-cols-1 gap-3 lg:grid-cols-3 lg:gap-4">
        <Panel>
          <h2 className="mb-2 flex items-center gap-1 text-[15px] font-extrabold tracking-tight">Geciken ve yaklaşan aksiyon<SqlInfo k={k} alan="gecikenAksiyon" label="Aksiyon kalan gün" /></h2>
          {s.gecikenAksiyon.length + s.yaklasanAksiyon.length === 0 ? (
            <Empty>Geciken ya da {meta.ayarlar.actionWarnDays} gün içinde termini gelen aksiyon yok.</Empty>
          ) : (
            <ul className="flex flex-col gap-1.5">
              {[...s.gecikenAksiyon, ...s.yaklasanAksiyon].map((a) => (
                <li key={a.id}>
                  <Link to={`/risk-uyum/risk/${a.riskId}`} className="flex min-h-11 items-start justify-between gap-2 rounded-xl bg-white/80 px-3 py-2 hover:bg-white">
                    <span className="min-w-0">
                      <span className="block break-words text-[12.5px] font-bold">{a.eylem}</span>
                      <span className="block text-[11px] text-canvas-muted">{a.riskBaslik} · {a.sahip ?? 'sahip yok'}</span>
                    </span>
                    <Pill tone={a.gecikti ? 'err' : 'warn'}>{fmtLeft(a.kalanGun)}</Pill>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </Panel>
        <Panel>
          <h2 className="mb-2 flex items-center gap-1 text-[15px] font-extrabold tracking-tight">Kırmızı göstergeler<SqlInfo k={k} alan="kirmiziGosterge[]" label="Kırmızı göstergeler" /></h2>
          {s.kirmiziGosterge.length === 0 ? (
            <Empty>Kırmızı gösterge yok. Eşiği girilmemiş gösterge renk almaz.</Empty>
          ) : (
            <ul className="flex flex-col gap-1.5">
              {s.kirmiziGosterge.map((g) => (
                <li key={g.kod} className="flex items-center justify-between gap-2 rounded-xl bg-red-50 px-3 py-2">
                  <span className="min-w-0 break-words text-[12.5px] font-bold text-red-800">{g.ad}</span>
                  <span className="inline-flex shrink-0 items-center gap-0.5 font-mono text-[12.5px] font-bold tabular-nums text-red-800">{fmtValue(g.deger, g.birim)}<SqlInfo k={k} alan="kirmiziGosterge[]" row={g.kod} label={g.ad} /></span>
                </li>
              ))}
            </ul>
          )}
        </Panel>
        <Panel>
          <h2 className="mb-2 flex items-center gap-1 text-[15px] font-extrabold tracking-tight">Bu ayın uyum yükümlülükleri<SqlInfo k={k} alan="uyumBuAy" label="Bu ayın uyum yükümlülükleri" /></h2>
          {s.uyumBuAy.length === 0 ? (
            <Empty>Bu ay son günü gelen ya da geciken yükümlülük yok.</Empty>
          ) : (
            <ul className="flex flex-col gap-1.5">
              {s.uyumBuAy.map((e) => (
                <li key={e.id} className="flex items-start justify-between gap-2 rounded-xl bg-white/80 px-3 py-2">
                  <span className="min-w-0">
                    <span className="block break-words text-[12.5px] font-bold">{e.madde}</span>
                    <span className="block text-[11px] text-canvas-muted">{e.alanAdi} · son gün {fmtDay(e.sonGun)}</span>
                  </span>
                  <Pill tone={e.durum === 'kapandi' ? 'ok' : e.gecikti ? 'err' : e.durum === 'kanit' ? 'violet' : 'warn'}>{e.durumAdi}</Pill>
                </li>
              ))}
            </ul>
          )}
        </Panel>
      </div>
      <Panel>
        <h2 className="mb-2 flex items-center gap-1 text-[15px] font-extrabold tracking-tight">Öncelikli 10 risk<SqlInfo k={k} alan="ilk10" label="Öncelikli 10 risk" /></h2>
        {s.ilk10.length === 0 ? <Empty>Kayıtlı risk yok. «Yeni risk» ile ilk kaydı açın.</Empty> : <RiskRows items={s.ilk10} meta={meta} />}
      </Panel>
    </>
  );
}

function RiskRows({ items, meta }: { items: Summary['ilk10']; meta: RiskMeta }) {
  return (
    <ul className="flex flex-col gap-1.5">
      {items.map((r) => (
        <li key={r.id}>
          <Link to={`/risk-uyum/risk/${r.id}`} className="grid min-h-11 grid-cols-[minmax(0,1fr)_auto] items-center gap-x-3 gap-y-1 rounded-xl bg-white/80 px-3 py-2 hover:bg-white sm:grid-cols-[minmax(0,1fr)_160px_120px_auto]">
            <span className="min-w-0">
              <span className="block break-words text-[13px] font-bold">{r.baslik}</span>
              <span className="block text-[11px] text-canvas-muted">{r.kategoriAdi}{r.durum !== 'acik' ? ` · ${r.durumAdi}` : ''}</span>
            </span>
            <span className="hidden text-[12px] sm:block">{r.sahip ?? <span className="text-canvas-muted">sahip yok</span>}</span>
            <span className="hidden text-[11.5px] text-canvas-muted sm:block">
              {r.gecikenAksiyon ? `${r.gecikenAksiyon} geciken aksiyon` : r.acikAksiyon ? `${r.acikAksiyon} açık aksiyon` : ''}
            </span>
            <LevelPill level={r.seviye} score={r.puan} meta={meta} />
          </Link>
        </li>
      ))}
    </ul>
  );
}

/* ------------------------------------------------------------------ Risk kaydı */

function Register({ meta, params, update }: { meta: RiskMeta; params: URLSearchParams; update: (n: Record<string, string | null>) => void }) {
  const durum = params.get('durum') ?? 'canli';
  const kategori = params.get('kategori') ?? '';
  const hucre = params.get('hucre') ?? '';
  const [q, setQ] = useState(params.get('q') ?? '');
  const dq = useDebounced(q, 300);
  const qc = useQueryClient();
  const list = useQuery({
    queryKey: ['risk', 'list', durum, kategori, hucre, dq],
    queryFn: () => riskApi.risks({ durum, kategori, hucre, q: dq }),
    enabled: ENGINE_ENABLED,
  });
  const suggest = useMutation({
    mutationFn: async () => {
      const j = await riskApi.suggest();
      return waitJob(j.id);
    },
    onSuccess: (j) => {
      if (j.durum === 'hata') toast.error(j.hata ?? 'Öneri hazırlanamadı.');
      else toast.success(`${Number(j.sonuc.oneri ?? 0)} risk önerisi hazır`);
      qc.invalidateQueries({ queryKey: ['risk'] });
      update({ durum: 'oneri' });
    },
    onError: (e) => toast.error(errText(e, 'Öneri hazırlanamadı.')),
  });
  const items = list.data?.items ?? [];
  return (
    <>
      <Panel>
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-[1.4fr_1fr_1fr_auto]">
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Ara</span>
            <span className="relative flex items-center">
              <Search aria-hidden className="pointer-events-none absolute left-3 h-4 w-4 text-canvas-muted" />
              <input className={`${field} pl-9`} value={q} placeholder="Başlık, tanım, sahip" onChange={(e) => { setQ(e.target.value); update({ q: e.target.value || null }); }} />
            </span>
          </label>
          <SelectInput id="rk-durum" label="Durum" value={durum} onChange={(v) => update({ durum: v === 'canli' ? null : v })}
            options={{ canli: 'Canlı (açık, izleniyor, kabul)', hepsi: 'Hepsi', ...meta.durumlar }} />
          <SelectInput id="rk-kat" label="Kategori" value={kategori} onChange={(v) => update({ kategori: v || null })} options={meta.kategoriler} empty="Hepsi" />
          {meta.me.canWrite && meta.modelVar && (
            <div className="flex items-end">
              <button type="button" className={btnGhost} disabled={suggest.isPending} onClick={() => suggest.mutate()}
                title="Eşiği aşan ve bağlı riski olmayan göstergeler için risk taslağı">
                {suggest.isPending ? <Loader2 aria-hidden className="h-4 w-4 animate-spin" /> : <Sparkles aria-hidden className="h-4 w-4" />}
                Zeki AI önerisi
              </button>
            </div>
          )}
        </div>
        {hucre && (
          <div className="mt-2 flex flex-wrap items-center gap-2 text-[12px]">
            <Pill tone="violet">Hücre: olasılık {hucre.split('x')[0]} × etki {hucre.split('x')[1]}</Pill>
            <button type="button" className="text-[12px] font-bold text-canvas-violet hover:underline" onClick={() => update({ hucre: null })}>Süzgeci kaldır</button>
          </div>
        )}
      </Panel>
      {list.error && <Note tone="err">{errText(list.error, 'Liste okunamadı.')}</Note>}
      {list.isLoading ? <Loading /> : items.length === 0 ? (
        <Empty>{durum === 'oneri' ? 'Kabul bekleyen öneri yok.' : 'Bu süzgeçte risk yok.'}</Empty>
      ) : (
        <Panel>
          <div className="mb-2 flex items-center gap-1 text-[11.5px] text-canvas-muted">{items.length} risk · puana göre<SqlInfo k={list.data?.kaynaklar} alan="items[]" label="Risk kaydı: puan ve aksiyon sayıları" /></div>
          <RiskRows items={items} meta={meta} />
        </Panel>
      )}
    </>
  );
}

/* ------------------------------------------------------------------ yeni risk / düzenleme penceresi */

export function RiskSheet({ open, meta, onClose, initial, id }: { open: boolean; meta: RiskMeta; onClose: () => void; initial?: RiskInput; id?: string }) {
  const qc = useQueryClient();
  const nav = useNavigate();
  const [f, setF] = useState<RiskInput>(initial ?? { kategori: 'operasyonel', sahip: meta.me.username });
  const ind = useQuery({ queryKey: ['risk', 'indicators'], queryFn: riskApi.indicators, enabled: open && ENGINE_ENABLED, staleTime: 60_000 });
  const set = (k: keyof RiskInput, v: unknown) => setF((p) => ({ ...p, [k]: v }));
  const classify = useMutation({
    mutationFn: () => riskApi.classify({ baslik: f.baslik, tanim: f.tanim }),
    onSuccess: (r) => {
      set('kategori', r.kategori);
      toast[r.emin ? 'success' : 'info'](r.emin ? `Zeki AI: ${r.kategoriAdi}` : `Zeki AI emin değil: ${r.kategoriAdi} — kontrol edin`);
    },
    onError: (e) => toast.error(errText(e, 'Kategori önerilemedi.')),
  });
  const save = useMutation({
    mutationFn: () => {
      const body = { ...f };
      if (id) {
        delete body.olasilik;
        delete body.etki;
        // Öneri durumu kabul/ret akışıyla değişir; düzenleme penceresi yalnız canlı durumlar arasında geçirir.
        if (body.durum === 'oneri' || body.durum === 'reddedildi') delete body.durum;
        return riskApi.update(id, body);
      }
      return riskApi.create(body);
    },
    onSuccess: (r) => {
      toast.success(id ? 'Risk güncellendi' : 'Risk kaydedildi');
      qc.invalidateQueries({ queryKey: ['risk'] });
      onClose();
      if (!id) nav(`/risk-uyum/risk/${r.id}`);
    },
    onError: (e) => toast.error(errText(e, 'Kaydedilemedi.')),
  });
  const codes = f.gostergeler ?? [];
  return (
    <Sheet open={open} modal wide onClose={onClose} title={id ? 'Riski düzenle' : 'Yeni risk'}
      subtitle={id ? 'Olasılık ve etki gözden geçirmeyle değişir; iz kalır.' : 'Olasılık ve etkiyi siz verirsiniz; sistem puanı değiştirmez.'}>
      <form className="flex flex-col gap-3" onSubmit={(e) => { e.preventDefault(); save.mutate(); }}>
        <TextInput id="rs-baslik" label="Başlık" value={f.baslik ?? ''} onChange={(v) => set('baslik', v)} />
        <TextInput id="rs-tanim" label="Tanım" area value={f.tanim ?? ''} onChange={(v) => set('tanim', v)} />
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <TextInput id="rs-neden" label="Neden" area value={f.neden ?? ''} onChange={(v) => set('neden', v)} />
          <TextInput id="rs-sonuc" label="Sonuç (gerçekleşirse)" area value={f.sonuc ?? ''} onChange={(v) => set('sonuc', v)} />
        </div>
        <div className="grid grid-cols-1 items-end gap-3 sm:grid-cols-[1fr_auto]">
          <SelectInput id="rs-kat" label="Kategori" value={f.kategori ?? ''} onChange={(v) => set('kategori', v)} options={meta.kategoriler} />
          {meta.modelVar && (
            <button type="button" className={btnGhost} disabled={classify.isPending || !(f.baslik || f.tanim)} onClick={() => classify.mutate()}>
              {classify.isPending ? <Loader2 aria-hidden className="h-4 w-4 animate-spin" /> : <Sparkles aria-hidden className="h-4 w-4" />}
              Zeki AI kategori önersin
            </button>
          )}
        </div>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <TextInput id="rs-sahip" label="Sahip (kullanıcı adı)" value={f.sahip ?? ''} onChange={(v) => set('sahip', v)} />
          <TextInput id="rs-eposta" label="Sahibin e-postası" type="email" value={f.sahipEposta ?? ''} onChange={(v) => set('sahipEposta', v)}
            help="Gösterge kırmızıya dönünce ve termin yaklaşınca buraya yazılır" />
        </div>
        {!id && (
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <ScalePick label="Olasılık" value={f.olasilik ?? null} onChange={(v) => set('olasilik', v)} hints={['çok düşük', 'çok yüksek']} />
            <ScalePick label="Etki" value={f.etki ?? null} onChange={(v) => set('etki', v)} hints={['önemsiz', 'çok ağır']} />
          </div>
        )}
        <fieldset className="flex flex-col gap-1">
          <legend className={labelCls}>Bağlı göstergeler</legend>
          <div className="mt-1 flex flex-wrap gap-1.5">
            {(ind.data?.items ?? []).map((g) => {
              const on = codes.includes(g.kod);
              return (
                <button key={g.kod} type="button" aria-pressed={on}
                  onClick={() => set('gostergeler', on ? codes.filter((c) => c !== g.kod) : [...codes, g.kod])}
                  className={`min-h-9 rounded-xl px-2.5 text-[12px] font-bold transition-transform duration-150 ease-out active:scale-[0.97] ${on ? 'bg-canvas-violet text-white' : 'bg-slate-100 text-canvas-ink hover:bg-slate-200'}`}>
                  {g.ad}
                </button>
              );
            })}
          </div>
        </fieldset>
        {id && f.durum !== 'oneri' && f.durum !== 'reddedildi' && <SelectInput id="rs-durum" label="Durum" value={f.durum ?? 'acik'} onChange={(v) => set('durum', v)}
          options={{ acik: meta.durumlar.acik, izleniyor: meta.durumlar.izleniyor, kabul: meta.durumlar.kabul, kapandi: meta.durumlar.kapandi }} />}
        <div className="flex flex-wrap justify-end gap-2 pt-1">
          <button type="button" className={btnGhost} onClick={onClose}>Vazgeç</button>
          <button type="submit" className={btnPrimary} disabled={save.isPending || !f.baslik?.trim()}>
            {save.isPending && <Loader2 aria-hidden className="h-4 w-4 animate-spin" />}
            Kaydet
          </button>
        </div>
      </form>
    </Sheet>
  );
}
