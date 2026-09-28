import { useCallback, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Loader2, Plus, ShieldAlert } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import SqlInfo from '../components/SqlInfo';
import type { Kaynaklar } from '../components/sqlInfo';
import { Note, Pill, btnGhost, btnPrimary, errText, field, label as labelCls } from '../admin/ui';
import { Panel } from '../editorial/kit';
import Sheet from '../editorial/studio/reader/Sheet';
import {
  FLAG_TONE, SEGMENT_TONE, fmtDay, fmtInt, okurApi,
  type Channel, type Flag, type Interest, type Kvkk, type Measure, type OkurMeta, type Segment, type SegmentInput,
} from './api';
import { AskSheet, CoreMissing, Fact, OkurFrame, Tabs } from './parts';

/** M37 «Okur segmentleri»: kural → anlık büyüklük (toplam / izinli) → amaç, süre, kanal → KVKK onayı. Onaylanmamış
 *  segment dışa aktarılamaz; kişi listesi dışa aktarımı ikinci sürümde. İlgi alanlarının özel nitelikli çağrışım işareti
 *  ayrı sekmede. Sekme ve durum süzgeci adreste (?sekme=, ?durum=). */

const TABS = [
  { key: 'segmentler', label: 'Segmentler' },
  { key: 'ilgi', label: 'İlgi alanları ve KVKK' },
] as const;
type Tab = (typeof TABS)[number]['key'];

export default function SegmentsScreen() {
  const [params, setParams] = useSearchParams();
  const meta = useQuery({ queryKey: ['okur', 'meta'], queryFn: okurApi.meta, enabled: ENGINE_ENABLED, staleTime: 60_000 });
  const tab: Tab = (TABS.find((t) => t.key === params.get('sekme'))?.key ?? 'segmentler') as Tab;
  const [creating, setCreating] = useState(false);
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
  const m = meta.data;
  return (
    <OkurFrame
      crumb="Okur segmentleri"
      title="Okur segmentleri"
      lead="Segment kişiyle değil ölçütle kurulur: kural yazılır, büyüklüğü (toplam ve izinli) ölçülür, amacı ve süresi yazılır, KVKK sorumlusu onaylar. Din ve inanç çağrışımlı ilgi alanları hukuk kararı olmadan kullanılmaz."
      source="Kaynak: okur veri tabanı · portal kaydı"
      aside={m?.me.canSegment ? (
        <div className="flex justify-start lg:justify-end">
          <button type="button" className={btnPrimary} onClick={() => setCreating(true)}>
            <Plus aria-hidden className="h-4 w-4" />
            Yeni segment
          </button>
        </div>
      ) : undefined}
    >
      {!ENGINE_ENABLED && <Note tone="warn">Bu kurulumda veri bağlantısı tanımlı değil.</Note>}
      {meta.error && <Note tone="err">{errText(meta.error, 'Ekran bilgisi okunamadı.')}</Note>}
      {m && !m.cekirdek.bagli && <CoreMissing message={m.cekirdek.mesaj} />}
      <Tabs tabs={TABS} value={tab} onChange={(t) => update({ sekme: t === 'segmentler' ? null : t })} />
      {m && tab === 'segmentler' && <SegmentList meta={m} durum={params.get('durum') ?? ''} setDurum={(d) => update({ durum: d || null })} />}
      {m && tab === 'ilgi' && <InterestList meta={m} />}
      {m && <SegmentEditor open={creating} meta={m} onClose={() => setCreating(false)} />}
    </OkurFrame>
  );
}

function SegmentList({ meta, durum, setDurum }: { meta: OkurMeta; durum: string; setDurum: (d: string) => void }) {
  const list = useQuery({ queryKey: ['okur', 'segments', durum], queryFn: () => okurApi.segments(durum), enabled: ENGINE_ENABLED });
  const [open, setOpen] = useState<string | null>(null);
  const counts = list.data?.durumSayilari ?? {};
  return (
    <Panel>
      <div className="-mx-1 mb-3 flex flex-wrap gap-1.5 px-1">
        <button type="button" onClick={() => setDurum('')} aria-pressed={!durum}
          className={`min-h-11 rounded-xl px-3 text-[12px] font-extrabold transition-transform duration-150 ease-out active:scale-[0.97] sm:min-h-8 ${!durum ? 'bg-canvas-violet text-white' : 'bg-slate-100'}`}>
          Hepsi
        </button>
        {Object.entries(meta.segmentDurumlari).map(([k, v]) => (
          <button key={k} type="button" onClick={() => setDurum(k)} aria-pressed={durum === k}
            className={`min-h-11 rounded-xl px-3 text-[12px] font-extrabold transition-transform duration-150 ease-out active:scale-[0.97] sm:min-h-8 ${durum === k ? 'bg-canvas-violet text-white' : 'bg-slate-100'}`}>
            {v} <span className="font-mono tabular-nums opacity-80">{counts[k as keyof typeof counts] ?? 0}</span>
          </button>
        ))}
      </div>
      {list.data && (
        <p className="mb-2 flex flex-wrap items-center gap-1 text-[11.5px] text-canvas-muted">
          Durum sayıları<SqlInfo k={list.data.kaynaklar} alan="durumSayilari" label="Durum başına segment" />
          · toplam / izinli = son ölçüm<SqlInfo k={list.data.kaynaklar} alan="items[]" label="Segment büyüklükleri" />
        </p>
      )}
      {list.isLoading && <div className="py-8 text-center text-[12px] text-canvas-muted">Yükleniyor…</div>}
      {list.error && <Note tone="err">{errText(list.error, 'Segmentler okunamadı.')}</Note>}
      {list.data && !list.data.items.length && (
        <div className="py-8 text-center text-[12.5px] text-canvas-muted">Bu süzgeçte segment yok.{meta.me.canSegment ? ' «Yeni segment» ile başlayın.' : ''}</div>
      )}
      <div className="flex flex-col gap-2">
        {list.data?.items.map((s) => (
          <button key={s.id} type="button" onClick={() => setOpen(s.id)}
            className="grid grid-cols-1 gap-2 rounded-2xl border border-slate-100 bg-white/80 p-3 text-left transition-colors duration-150 hover:border-canvas-violet/40 md:grid-cols-[minmax(0,1fr)_150px_150px] md:items-center">
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-1.5">
                <Pill tone={SEGMENT_TONE[s.durum]}>{s.durumAdi}</Pill>
                <span className="text-[11px] font-semibold text-canvas-muted">{s.kanalAdi} · sürüm {s.surum}</span>
              </div>
              <div className="mt-1 break-words text-[13.5px] font-extrabold leading-snug">{s.ad}</div>
              <div className="line-clamp-2 break-words text-[12px] leading-snug text-canvas-muted">{s.amac || 'Amaç yazılmadı'}</div>
            </div>
            <div className="flex flex-wrap items-center gap-2 md:flex-col md:items-start md:gap-0.5">
              <span className="text-[11px] font-bold uppercase tracking-wide text-canvas-muted">Toplam / izinli</span>
              <span className="font-mono text-[13px] font-bold tabular-nums">{s.sonOlcum ? `${fmtInt(s.sonOlcum.toplam)} / ${fmtInt(s.sonOlcum.izinli ?? s.sonOlcum.eposta)}` : 'ölçülmedi'}</span>
            </div>
            <div className="flex flex-wrap items-center gap-2 md:flex-col md:items-start md:gap-0.5">
              <span className="text-[11px] font-bold uppercase tracking-wide text-canvas-muted">Süre bitişi</span>
              <span className="font-mono text-[12px] tabular-nums">{fmtDay(s.sureBitis)}</span>
            </div>
          </button>
        ))}
      </div>
      {open && <SegmentSheet id={open} meta={meta} onClose={() => setOpen(null)} />}
    </Panel>
  );
}

function MeasureFacts({ m }: { m: Measure | null | undefined }) {
  if (!m) return <p className="text-[12px] text-canvas-muted">Büyüklük ölçülmedi.</p>;
  return (
    <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
      <Fact label="Toplam" value={fmtInt(m.toplam)} />
      <Fact label="İzinli" value={fmtInt(m.izinli)} />
      <Fact label="E-posta izinli" value={fmtInt(m.eposta)} />
      <Fact label="SMS izinli" value={fmtInt(m.sms)} />
    </div>
  );
}

function KvkkNote({ k }: { k: Kvkk | undefined }) {
  if (!k) return null;
  if (!k.engel.length && !k.uyari.length) return <Note tone="ok">İlgi alanı denetimi: segmentte özel nitelikli çağrışımlı alan yok.</Note>;
  return (
    <>
      {k.engel.map((x) => <Note key={x.id} tone="err">{x.mesaj}</Note>)}
      {k.uyari.map((x) => <Note key={x.id} tone="warn">{x.mesaj}</Note>)}
    </>
  );
}

function SegmentSheet({ id, meta, onClose }: { id: string; meta: OkurMeta; onClose: () => void }) {
  const qc = useQueryClient();
  const seg = useQuery({ queryKey: ['okur', 'segment', id], queryFn: () => okurApi.segment(id), enabled: ENGINE_ENABLED });
  const [editing, setEditing] = useState(false);
  const [ask, setAsk] = useState<null | 'onayla' | 'reddet' | 'sil'>(null);
  const done = (msg: string) => () => {
    qc.invalidateQueries({ queryKey: ['okur'] });
    toast.success(msg);
  };
  const fail = (e: unknown) => toast.error(errText(e, 'İşlem yapılamadı.') ?? '');
  const measure = useMutation({ mutationFn: () => okurApi.measure(id), onSuccess: done('Büyüklük ölçüldü.'), onError: fail });
  const submit = useMutation({ mutationFn: () => okurApi.submit(id), onSuccess: done('Segment KVKK onayına gönderildi.'), onError: fail });
  const withdraw = useMutation({ mutationFn: () => okurApi.withdraw(id), onSuccess: done('Geri çekildi.'), onError: fail });
  const decide = useMutation({
    mutationFn: ({ karar, not }: { karar: 'onayla' | 'reddet'; not: string }) => okurApi.decide(id, karar, not),
    onSuccess: (s) => { done(s.durum === 'onaylandi' ? 'Segment onaylandı.' : 'Segment reddedildi.')(); setAsk(null); },
    onError: fail,
  });
  const del = useMutation({ mutationFn: () => okurApi.deleteSegment(id), onSuccess: () => { done('Segment silindi.')(); onClose(); }, onError: fail });
  const s = seg.data;
  const me = meta.me.username.toLowerCase();
  const own = !!s && [s.yazan, s.gonderen].some((x) => (x ?? '').toLowerCase() === me);
  const busy = measure.isPending || submit.isPending || withdraw.isPending || decide.isPending || del.isPending;
  return (
    <Sheet open modal wide onClose={onClose} title={s?.ad ?? 'Segment'} subtitle={s ? `${s.durumAdi} · sürüm ${s.surum} · yazan ${s.yazan}` : undefined}>
      {seg.isLoading && <div className="py-8 text-center text-[12px] text-canvas-muted">Yükleniyor…</div>}
      {seg.error && <Note tone="err">{errText(seg.error, 'Segment okunamadı.')}</Note>}
      {s && !editing && (
        <div className="flex flex-col gap-3 text-[13px]">
          <div className="flex flex-wrap items-center gap-1.5">
            <Pill tone={SEGMENT_TONE[s.durum]}>{s.durumAdi}</Pill>
            <Pill tone="muted">{s.kanalAdi}</Pill>
            <Pill tone="muted">Süre bitişi {fmtDay(s.sureBitis)}</Pill>
          </div>
          <div>
            <div className={labelCls}>Amaç</div>
            <p className="mt-0.5 whitespace-pre-wrap break-words leading-snug">{s.amac || '—'}</p>
          </div>
          <div>
            <div className={labelCls}>Kural</div>
            {s.kuralCumlesi && <p className="mt-0.5 leading-snug">{s.kuralCumlesi}</p>}
            <pre className="mt-1 max-h-48 overflow-auto rounded-xl bg-slate-50 p-2 font-mono text-[11.5px] leading-snug">{JSON.stringify(s.kural, null, 2)}</pre>
          </div>
          <KvkkNote k={s.kvkk} />
          <div>
            <div className={`${labelCls} mb-1 flex items-center gap-1`}>Son ölçüm {s.sonOlcum?.zaman ? `· ${fmtDay(s.sonOlcum.zaman)}` : ''}<SqlInfo k={s.kaynaklar} alan="sonOlcum" label="Son ölçüm" /></div>
            <MeasureFacts m={s.sonOlcum} />
          </div>
          {s.onayNotu && <Note tone={s.durum === 'reddedildi' ? 'err' : 'info'}>{s.onaylayan}: {s.onayNotu}</Note>}
          {s.durum === 'onaylandi' && <Note tone="ok">{s.onaylayan} onayladı · {fmtDay(s.onayZamani)}. Kişi listesi dışa aktarımı ikinci sürümde, hukuk görüşünden sonra açılır.</Note>}
          {!!s.olcumler?.length && (
            <details className="rounded-xl bg-white/80 px-3 py-2">
              <summary className="cursor-pointer text-[12px] font-bold">Ölçüm geçmişi ({s.olcumler.length})</summary>
              <ul className="mt-1 flex flex-col gap-0.5 font-mono text-[11.5px] tabular-nums">
                {s.olcumler.map((o) => <li key={o.tarih}>{o.tarih}: {fmtInt(o.toplam)} toplam · {fmtInt(o.izinli ?? o.eposta)} izinli</li>)}
              </ul>
              <div className="mt-1 flex items-center gap-1 text-[11px] text-canvas-muted">Günlük ölçüm kaydı<SqlInfo k={s.kaynaklar} alan="olcumler" label="Ölçüm geçmişi" /></div>
            </details>
          )}
          {!!s.programlar?.length && (
            <div className="text-[12px] text-canvas-muted">Bağlı programlar: {s.programlar.map((p) => `${p.ad} (${fmtDay(p.tarih)})`).join(', ')}</div>
          )}
          <div className="flex flex-wrap justify-end gap-2">
            {meta.me.canSegment && s.durum !== 'onay_bekliyor' && (
              <button type="button" className={btnGhost} disabled={busy} onClick={() => setEditing(true)}>Düzenle</button>
            )}
            {meta.me.canSegment && ['taslak', 'reddedildi', 'suresi_doldu'].includes(s.durum) && (
              <button type="button" className={btnGhost} disabled={busy} onClick={() => setAsk('sil')}>Sil</button>
            )}
            {meta.me.canSegment && meta.cekirdek.bagli && s.durum !== 'onay_bekliyor' && (
              <button type="button" className={btnGhost} disabled={busy || !s.kvkk?.ok} onClick={() => measure.mutate()}>
                {measure.isPending && <Loader2 aria-hidden className="h-4 w-4 animate-spin" />}
                Büyüklüğü ölç
              </button>
            )}
            {meta.me.canSegment && ['taslak', 'reddedildi', 'suresi_doldu'].includes(s.durum) && (
              <button type="button" className={btnPrimary} disabled={busy || !s.sonOlcum || !s.kvkk?.ok} onClick={() => submit.mutate()}>
                KVKK onayına gönder
              </button>
            )}
            {meta.me.canSegment && s.durum === 'onay_bekliyor' && (
              <button type="button" className={btnGhost} disabled={busy} onClick={() => withdraw.mutate()}>Geri çek</button>
            )}
            {meta.me.canApprove && s.durum === 'onay_bekliyor' && !own && (
              <>
                <button type="button" className={btnGhost} disabled={busy} onClick={() => setAsk('reddet')}>Reddet</button>
                <button type="button" className={btnPrimary} disabled={busy || !s.kvkk?.ok} onClick={() => setAsk('onayla')}>Onayla</button>
              </>
            )}
          </div>
          {meta.me.canApprove && s.durum === 'onay_bekliyor' && own && (
            <p className="text-right text-[11.5px] text-canvas-muted">Segmenti yazan ya da gönderen onaylayamaz; başka bir KVKK yetkilisi onaylar.</p>
          )}
        </div>
      )}
      {s && editing && <SegmentForm meta={meta} initial={s} onDone={() => setEditing(false)} />}
      <AskSheet
        open={ask === 'onayla' || ask === 'reddet'}
        title={ask === 'onayla' ? 'Segmenti onayla' : 'Segmenti reddet'}
        message={ask === 'onayla'
          ? `«${s?.ad}» ${fmtDay(s?.sureBitis)} tarihine kadar «${s?.amac ?? ''}» amacıyla kullanılabilecek. Onay değişiklik kaydına yazılır.`
          : 'Gerekçe segmenti yazana gösterilir ve kayda geçer.'}
        confirm={ask === 'onayla' ? 'Onayla' : 'Reddet'}
        danger={ask === 'reddet'}
        input={ask === 'onayla' ? 'Not (isteğe bağlı)' : 'Ret gerekçesi'}
        required={ask === 'reddet'}
        busy={decide.isPending}
        onClose={() => setAsk(null)}
        onConfirm={(not) => ask && ask !== 'sil' && decide.mutate({ karar: ask, not })}
      />
      <AskSheet
        open={ask === 'sil'}
        title="Segmenti sil"
        message="Segment ve ölçüm geçmişi silinir; bağlı programlardan bağı kalkar. Silme kayda geçer."
        confirm="Sil"
        danger
        busy={del.isPending}
        onClose={() => setAsk(null)}
        onConfirm={() => del.mutate()}
      />
    </Sheet>
  );
}

function SegmentEditor({ open, meta, onClose }: { open: boolean; meta: OkurMeta; onClose: () => void }) {
  return (
    <Sheet open={open} modal wide onClose={onClose} title="Yeni segment" subtitle="Kişi seçilmez; kural ölçütlerden kurulur. Kaydettikten sonra büyüklüğü ölçüp KVKK onayına gönderirsiniz.">
      {open && <SegmentForm meta={meta} onDone={onClose} />}
    </Sheet>
  );
}

const inFuture = (days: number) => {
  const d = new Date();
  d.setDate(d.getDate() + days);
  return d.toISOString().slice(0, 10);
};

/** Segment formu. Kural, okur veri tabanının kural biçimindedir: hızlı alanlar (ilgi alanı, kayıt tarihi, kaynak) bu nesneye
 *  yazılır; «Kural (gelişmiş)» alanında doğrudan düzenlenebilir. Portal kuralı yorumlamaz, okur veri tabanı sayar. */
function SegmentForm({ meta, initial, onDone }: { meta: OkurMeta; initial?: Segment; onDone: () => void }) {
  const qc = useQueryClient();
  const cats = useQuery({ queryKey: ['okur', 'categories'], queryFn: okurApi.categories, enabled: ENGINE_ENABLED && meta.cekirdek.bagli, staleTime: 60_000 });
  const [ad, setAd] = useState(initial?.ad ?? '');
  const [amac, setAmac] = useState(initial?.amac ?? '');
  const [kanal, setKanal] = useState<Channel>(initial?.kanal ?? 'eposta');
  const [sure, setSure] = useState(initial?.sureBitis ?? inFuture(90));
  const [ruleText, setRuleText] = useState(JSON.stringify(initial?.kural ?? { ilgi_alanlari: [] }, null, 2));
  const [preview, setPreview] = useState<{ olcum: Measure | null; kvkk: Kvkk; kuralCumlesi: string | null; kaynaklar?: Kaynaklar } | null>(null);
  const rule = useMemo(() => {
    try {
      const v = JSON.parse(ruleText);
      return v && typeof v === 'object' && !Array.isArray(v) ? (v as Record<string, unknown>) : null;
    } catch {
      return null;
    }
  }, [ruleText]);
  const picked = new Set(Array.isArray(rule?.ilgi_alanlari) ? (rule?.ilgi_alanlari as unknown[]).map(String) : []);
  const toggle = (id: string) => {
    if (!rule) return;
    const next = new Set(picked);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    setRuleText(JSON.stringify({ ...rule, ilgi_alanlari: [...next] }, null, 2));
    setPreview(null);
  };
  const setRuleField = (k: string, v: string) => {
    if (!rule) return;
    const next = { ...rule } as Record<string, unknown>;
    if (v) next[k] = v;
    else delete next[k];
    setRuleText(JSON.stringify(next, null, 2));
    setPreview(null);
  };
  const doPreview = useMutation({
    mutationFn: () => okurApi.previewRule(rule as Record<string, unknown>),
    onSuccess: setPreview,
    onError: (e) => toast.error(errText(e, 'Ölçülemedi.') ?? ''),
  });
  const save = useMutation({
    mutationFn: () => {
      const b: SegmentInput = { ad: ad.trim(), kural: rule as Record<string, unknown>, amac: amac.trim(), kanal, sureBitis: sure || null };
      return initial ? okurApi.updateSegment(initial.id, b) : okurApi.createSegment(b);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['okur'] });
      toast.success(initial?.durum === 'onaylandi' ? 'Kaydedildi; onaylı segment değiştiği için taslağa döndü.' : 'Segment kaydedildi.');
      onDone();
    },
    onError: (e) => toast.error(errText(e, 'Kaydedilemedi.') ?? ''),
  });
  const items = cats.data?.items ?? [];
  const bad = !ad.trim() || !rule || !Object.keys(rule).length;
  return (
    <div className="flex flex-col gap-3 text-[13px]">
      {initial?.durum === 'onaylandi' && <Note tone="warn">Bu segment onaylı. Değiştirirseniz taslağa döner, yeniden ölçülüp onaya gönderilmesi gerekir.</Note>}
      <label className="flex flex-col gap-1">
        <span className={labelCls}>Segment adı *</span>
        <input className={field} value={ad} onChange={(e) => setAd(e.target.value)} placeholder="Örn. Çocuk ve aile ilgisi, e-posta izinli" />
      </label>
      <label className="flex flex-col gap-1">
        <span className={labelCls}>Amaç (onay için en az {meta.ayarlar.purposeMin} karakter)</span>
        <textarea className={`${field} min-h-[64px]`} value={amac} onChange={(e) => setAmac(e.target.value)} placeholder="Örn. Kasım okuma kulübü duyurusu" />
      </label>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <label className="flex flex-col gap-1">
          <span className={labelCls}>İleti kanalı</span>
          <select className={field} value={kanal} onChange={(e) => setKanal(e.target.value as Channel)}>
            {Object.entries(meta.kanallar).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
        </label>
        <label className="flex flex-col gap-1">
          <span className={labelCls}>Süre bitişi (en çok {meta.ayarlar.segmentMaxDays} gün)</span>
          <input type="date" className={field} value={sure ?? ''} onChange={(e) => setSure(e.target.value)} />
        </label>
      </div>

      <div className="rounded-2xl border border-slate-100 bg-white/70 p-3">
        <div className={`${labelCls} flex items-center gap-1`}>İlgi alanları<SqlInfo k={cats.data?.kaynaklar} alan="items" label="İlgi alanı başına okur" /></div>
        {!meta.cekirdek.bagli && <p className="mt-1 text-[12px] text-canvas-muted">Okur çekirdeği bağlı değil; ilgi alanı listesi gelmiyor. Kuralı aşağıda yazabilirsiniz.</p>}
        {cats.isLoading && <p className="mt-1 text-[12px] text-canvas-muted">Yükleniyor…</p>}
        <div className="mt-2 flex flex-wrap gap-1.5">
          {items.map((i) => (
            <button key={i.id} type="button" disabled={!i.kullanilabilir && !picked.has(i.id)} onClick={() => toggle(i.id)} aria-pressed={picked.has(i.id)}
              title={i.kullanilabilir ? `${fmtInt(i.okur)} okur` : i.isaretAdi}
              className={`inline-flex min-h-11 items-center gap-1 rounded-xl px-2.5 text-[12px] font-bold transition-transform duration-150 ease-out active:scale-[0.97] disabled:cursor-not-allowed disabled:opacity-45 sm:min-h-8 ${
                picked.has(i.id) ? 'bg-canvas-violet text-white' : 'bg-slate-100'
              }`}>
              {!i.kullanilabilir && <ShieldAlert aria-hidden className="h-3.5 w-3.5" />}
              {i.ad}
            </button>
          ))}
        </div>
        <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2">
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Bu tarihten sonra kayıt</span>
            <input type="date" className={field} value={typeof rule?.kayit_tarihi_sonra === 'string' ? rule.kayit_tarihi_sonra : ''}
              onChange={(e) => setRuleField('kayit_tarihi_sonra', e.target.value)} disabled={!rule} />
          </label>
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Kaynak (boşsa hepsi)</span>
            <input className={field} value={typeof rule?.kaynak === 'string' ? rule.kaynak : ''} onChange={(e) => setRuleField('kaynak', e.target.value)}
              placeholder="Örn. Fuar" disabled={!rule} />
          </label>
        </div>
        <details className="mt-3">
          <summary className="cursor-pointer text-[12px] font-bold">Kural (gelişmiş)</summary>
          <textarea className={`${field} mt-1 min-h-[140px] font-mono !text-[12px]`} value={ruleText} onChange={(e) => { setRuleText(e.target.value); setPreview(null); }} spellCheck={false} />
          {!rule && <p className="mt-1 text-[11.5px] text-red-700">Kural geçerli bir nesne değil.</p>}
        </details>
      </div>

      {preview && (
        <div className="flex flex-col gap-2">
          {preview.kuralCumlesi && <p className="leading-snug">{preview.kuralCumlesi}</p>}
          <KvkkNote k={preview.kvkk} />
          {preview.olcum && (
            <>
              <div className="flex items-center gap-1 text-[11.5px] text-canvas-muted">Anlık sayım (kaydedilmez)<SqlInfo k={preview.kaynaklar} alan="olcum" label="Kural büyüklüğü" /></div>
              <MeasureFacts m={preview.olcum} />
            </>
          )}
        </div>
      )}
      <div className="flex flex-wrap justify-end gap-2">
        {meta.cekirdek.bagli && (
          <button type="button" className={btnGhost} disabled={!rule || doPreview.isPending} onClick={() => doPreview.mutate()}>
            {doPreview.isPending && <Loader2 aria-hidden className="h-4 w-4 animate-spin" />}
            Büyüklüğü gör
          </button>
        )}
        <button type="button" className={btnPrimary} disabled={bad || save.isPending} onClick={() => save.mutate()}>
          {save.isPending && <Loader2 aria-hidden className="h-4 w-4 animate-spin" />}
          Kaydet
        </button>
      </div>
    </div>
  );
}

function InterestList({ meta }: { meta: OkurMeta }) {
  const qc = useQueryClient();
  const cats = useQuery({ queryKey: ['okur', 'categories'], queryFn: okurApi.categories, enabled: ENGINE_ENABLED });
  const [ask, setAsk] = useState<{ item: Interest; isaret: Flag } | null>(null);
  const classify = useMutation({
    mutationFn: okurApi.classify,
    onSuccess: (r) => {
      qc.invalidateQueries({ queryKey: ['okur', 'categories'] });
      toast.success(`Zeki AI ${r.sorulan ?? 0} ilgi alanını sınıfladı.`);
    },
    onError: (e) => toast.error(errText(e, 'Sınıflanamadı.') ?? ''),
  });
  const flag = useMutation({
    mutationFn: ({ item, isaret, gerekce }: { item: Interest; isaret: Flag; gerekce: string }) => okurApi.flag(item.id, { ad: item.ad, isaret, gerekce }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['okur'] });
      toast.success('Karar kaydedildi.');
      setAsk(null);
    },
    onError: (e) => toast.error(errText(e, 'Kaydedilemedi.') ?? ''),
  });
  const d = cats.data;
  return (
    <Panel>
      <div className="mb-2 flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <h2 className="flex items-center gap-1 text-[15px] font-extrabold tracking-tight">İlgi alanlarının KVKK işareti<SqlInfo k={d?.kaynaklar} alan="items" label="İlgi alanı okur sayısı, işaret ve olasılık" /></h2>
          <p className="max-w-[80ch] text-[12px] leading-snug text-canvas-muted">
            Bir kişiyi din, inanç, sağlık, siyasi görüş gibi özel nitelikli bir özelliğe bağlayabilecek ilgi alanı segmentte kullanılmaz
            {d?.hassasAcik ? ' (hukuk kararıyla açık; ayrı açık rıza gerekir)' : ''}. Zeki AI önce işaretler, KVKK sorumlusu karar verir; sınıflanmamış alan da kullanılmaz.
          </p>
        </div>
        {meta.me.canSegment && meta.modelVar && d?.bagli && (
          <button type="button" className={btnGhost} disabled={classify.isPending} onClick={() => classify.mutate()}>
            {classify.isPending && <Loader2 aria-hidden className="h-4 w-4 animate-spin" />}
            Sınıflanmamışları Zeki AI'a sor
          </button>
        )}
      </div>
      {cats.isLoading && <div className="py-8 text-center text-[12px] text-canvas-muted">Yükleniyor…</div>}
      {cats.error && <Note tone="err">{errText(cats.error, 'İlgi alanları okunamadı.')}</Note>}
      {d && !d.bagli && <CoreMissing message={d.mesaj} />}
      <div className="flex flex-col gap-1.5">
        {d?.items.map((i) => (
          <div key={i.id} className="flex flex-col gap-2 rounded-xl bg-white/80 px-3 py-2 sm:flex-row sm:items-center sm:justify-between">
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-1.5">
                <span className="break-words text-[13px] font-bold">{i.ad}</span>
                <Pill tone={FLAG_TONE[i.isaret]}>{i.isaretAdi}</Pill>
                {i.isaretKaynak && <span className="text-[11px] text-canvas-muted">{i.isaretKaynak === 'insan' ? `karar: ${i.kararVeren}` : `Zeki AI${i.olasilik !== null ? ` · %${Math.round(i.olasilik * 100)}` : ''}`}</span>}
              </div>
              {i.gerekce && <div className="text-[11.5px] leading-snug text-canvas-muted">{i.gerekce}</div>}
            </div>
            <div className="flex shrink-0 flex-wrap items-center gap-2">
              <span className="font-mono text-[12px] tabular-nums text-canvas-muted">{fmtInt(i.okur)} okur</span>
              {meta.me.canApprove && (
                <>
                  <button type="button" className={btnGhost} disabled={flag.isPending} onClick={() => setAsk({ item: i, isaret: 'degil' })}>Çağrışım yok</button>
                  <button type="button" className={btnGhost} disabled={flag.isPending} onClick={() => setAsk({ item: i, isaret: 'ozel' })}>Özel nitelikli</button>
                </>
              )}
            </div>
          </div>
        ))}
        {d?.bagli && !d.items.length && <div className="py-6 text-center text-[12px] text-canvas-muted">Okur veri tabanı ilgi alanı vermedi.</div>}
      </div>
      <AskSheet
        open={!!ask}
        title={ask?.isaret === 'degil' ? 'Çağrışım yok kararı' : 'Özel nitelikli kararı'}
        message={ask ? `«${ask.item.ad}» için karar KVKK kaydına gerekçesiyle yazılır ve Zeki AI işaretinin yerine geçer.` : ''}
        confirm="Kaydet"
        input="Gerekçe (zorunlu)"
        required
        busy={flag.isPending}
        onClose={() => setAsk(null)}
        onConfirm={(gerekce) => ask && flag.mutate({ item: ask.item, isaret: ask.isaret, gerekce })}
      />
    </Panel>
  );
}
