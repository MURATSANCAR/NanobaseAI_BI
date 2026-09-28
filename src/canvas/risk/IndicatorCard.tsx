import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Check, ExternalLink, Loader2, RefreshCw, SlidersHorizontal, X } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import { Loading, Note, btnGhost, btnPrimary, errText } from '../admin/ui';
import { Panel } from '../editorial/kit';
import Sheet from '../editorial/studio/reader/Sheet';
import { fmtDay, fmtTime, fmtValue, parseNum, riskApi, type Indicator, type RiskMeta } from './api';
import SqlInfo from '../components/SqlInfo';
import type { Kaynaklar } from '../components/sqlInfo';
import { AskSheet, Empty, SelectInput, Spark, TextInput, ValuePill } from './parts';

/** Göstergeler: her biri son değer, durum, son 12 ölçüm, eşik ve sahibiyle. Eşik ve sahip taslakla değişir, başka biri
 *  onaylar. Hazır tanımlar eşiksiz gelir (sayı uydurulmaz); eşik girilene kadar gösterge renk almaz. */
export default function IndicatorsTab({ meta }: { meta: RiskMeta }) {
  const q = useQuery({ queryKey: ['risk', 'indicators'], queryFn: riskApi.indicators, enabled: ENGINE_ENABLED });
  const [editing, setEditing] = useState<Indicator | null>(null);
  const [open, setOpen] = useState<string | null>(null);
  if (q.isLoading) return <Loading />;
  if (q.error) return <Note tone="err">{errText(q.error, 'Göstergeler okunamadı.')}</Note>;
  const items = q.data?.items ?? [];
  const pending = items.filter((g) => g.taslak || g.yeni);
  return (
    <>
      <Note tone="info">
        Değerler Logo, CRM ve portalın hazır raporlarından ölçülür (günlük, haftalık ya da aylık; her sabah). Gösterge inceleme adayıdır; hüküm değildir.
        Logo kopyası donmuşsa «son N gün» pencereleri veri son gününe göre kurulur ve değerin yanında yazar.
      </Note>
      {pending.length > 0 && <Note tone="warn">{pending.length} gösterge taslağı onay bekliyor{meta.me.canIndicatorApprove ? '' : ' (onay yetkiniz yok)'}.<SqlInfo k={q.data?.kaynaklar} alan="items[]" label="Gösterge tanımları" className="ml-0.5" /></Note>}
      {items.length === 0 ? <Empty>Gösterge yok.</Empty> : (
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2 2xl:grid-cols-3">
          {items.map((g) => <IndicatorCard key={g.kod} g={g} meta={meta} k={q.data?.kaynaklar} onEdit={() => setEditing(g)} expanded={open === g.kod} onToggle={() => setOpen(open === g.kod ? null : g.kod)} />)}
        </div>
      )}
      {editing && <ThresholdSheet key={editing.kod} g={editing} meta={meta} onClose={() => setEditing(null)} />}
    </>
  );
}

function IndicatorCard({ g, meta, k, onEdit, expanded, onToggle }: { g: Indicator; meta: RiskMeta; k?: Kaynaklar; onEdit: () => void; expanded: boolean; onToggle: () => void }) {
  const qc = useQueryClient();
  const [asking, setAsking] = useState<'approve' | 'reject' | null>(null);
  const measure = useMutation({
    mutationFn: () => riskApi.measure(g.kod),
    onSuccess: (r) => {
      if (r.hata) toast.error(`Ölçülemedi: ${r.hata}`);
      else toast.success(`${g.ad}: ${fmtValue(r.deger, g.birim)}${r.bildirim ? ' — bildirim gönderildi' : ''}`);
      qc.invalidateQueries({ queryKey: ['risk'] });
    },
    onError: (e) => toast.error(errText(e, 'Ölçülemedi.')),
  });
  const decide = useMutation({
    mutationFn: ({ ok, note }: { ok: boolean; note: string }) => (ok ? riskApi.approveIndicator(g.kod, note) : riskApi.rejectIndicator(g.kod, note)),
    onSuccess: (_, v) => {
      toast.success(v.ok ? 'Taslak yürürlüğe alındı' : 'Taslak reddedildi');
      setAsking(null);
      qc.invalidateQueries({ queryKey: ['risk'] });
    },
    onError: (e) => toast.error(errText(e, 'Karar kaydedilemedi.')),
  });
  const son = g.son;
  const draft = g.taslak ?? (g.yeni ? g : null);
  const canDecide = meta.me.canIndicatorApprove && draft && draft.olusturan !== meta.me.username;
  return (
    <Panel>
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <h3 className="break-words text-[14px] font-extrabold tracking-tight">{g.ad}</h3>
          <div className="mt-0.5 text-[11px] text-canvas-muted">{g.siklikAdi} · {g.yonAdi}{g.sahip ? ` · sahibi ${g.sahip}` : ' · sahibi yok'}</div>
        </div>
        <ValuePill state={son?.durum} meta={meta} />
      </div>
      <div className="mt-2 flex flex-wrap items-end justify-between gap-3">
        <div>
          <div className="flex items-center gap-1 font-mono text-[26px] font-bold leading-none tabular-nums tracking-tight">{fmtValue(son?.deger ?? null, g.birim)}<SqlInfo k={k} alan="items[]" row={g.kod} label={`${g.ad}: değer, eşik, geçmiş ve kanıt`} /></div>
          <div className="mt-1 text-[11px] text-canvas-muted">
            {son ? <>ölçüm {fmtTime(son.olcum)}{son.veriSonGunu ? ` · veri ${fmtDay(son.veriSonGunu)}` : ''}</> : 'henüz ölçülmedi'}
          </div>
        </div>
        <Spark points={g.gecmis} sari={g.esikSari} kirmizi={g.esikKirmizi} />
      </div>
      {son?.hata && <div className="mt-2 rounded-lg bg-amber-50 px-2 py-1 text-[11.5px] font-semibold text-amber-800">{son.hata}</div>}
      <div className="mt-2 text-[11.5px] leading-snug">
        {g.esikSari === null && g.esikKirmizi === null ? (
          <span className="text-canvas-muted">Eşik girilmemiş — renk yok, bildirim gitmez.</span>
        ) : (
          <span>Eşik: <b className="text-amber-700">sarı {fmtValue(g.esikSari, g.birim)}</b> · <b className="text-red-700">kırmızı {fmtValue(g.esikKirmizi, g.birim)}</b> <span className="text-canvas-muted">(sürüm {g.surum}, onaylayan {g.onaylayan ?? '—'})</span></span>
        )}
      </div>
      {g.riskler.length > 0 && <div className="mt-1 text-[11.5px] text-canvas-muted">Bağlı risk: {g.riskler.length}</div>}
      {draft && (
        <div className="mt-2 rounded-xl bg-canvas-violet/10 px-3 py-2 text-[12px]">
          <div className="font-bold text-canvas-violet">Onay bekleyen taslak (sürüm {draft.surum}, {draft.olusturan})</div>
          <div className="mt-0.5">sarı {fmtValue(draft.esikSari, draft.birim)} · kırmızı {fmtValue(draft.esikKirmizi, draft.birim)} · {draft.yonAdi} · {draft.siklikAdi}{draft.sahip ? ` · sahibi ${draft.sahip}` : ''}</div>
          {draft.not && <div className="mt-0.5 text-canvas-muted">{draft.not}</div>}
          {canDecide && (
            <div className="mt-2 flex flex-wrap gap-2">
              <button type="button" className={btnPrimary} onClick={() => setAsking('approve')}><Check aria-hidden className="h-4 w-4" />Onayla</button>
              <button type="button" className={btnGhost} onClick={() => setAsking('reject')}><X aria-hidden className="h-4 w-4" />Reddet</button>
            </div>
          )}
        </div>
      )}
      <div className="mt-3 flex flex-wrap gap-2">
        {meta.me.canIndicator && !draft && (
          <button type="button" className={btnGhost} onClick={onEdit}><SlidersHorizontal aria-hidden className="h-4 w-4" />Eşik ve sahip</button>
        )}
        {meta.me.canIndicator && (
          <button type="button" className={btnGhost} disabled={measure.isPending} onClick={() => measure.mutate()}>
            {measure.isPending ? <Loader2 aria-hidden className="h-4 w-4 animate-spin" /> : <RefreshCw aria-hidden className="h-4 w-4" />}
            Şimdi ölç
          </button>
        )}
        <button type="button" className={btnGhost} aria-expanded={expanded} onClick={onToggle}>Kaynak ve kanıt</button>
        {g.ekran && (
          <Link to={g.ekran} className={btnGhost}><ExternalLink aria-hidden className="h-4 w-4" />Kaynak ekranı</Link>
        )}
      </div>
      {expanded && (
        <div className="mt-3 space-y-2 border-t border-slate-100 pt-3 text-[12px] leading-snug">
          {g.aciklama && <p>{g.aciklama}</p>}
          <p className="text-canvas-muted">Kaynak: {g.kaynakRef}</p>
          {son && <Evidence kanit={son.kanit} birim={g.birim} />}
        </div>
      )}
      <AskSheet open={asking !== null} title={asking === 'approve' ? 'Gösterge taslağını onayla' : 'Gösterge taslağını reddet'}
        message={asking === 'approve' ? 'Taslak yürürlüğe girer; önceki sürüm arşive geçer. Sonraki ölçüm yeni eşikle değerlendirilir.' : 'Reddetme gerekçesini yazın; hazırlayan görür.'}
        confirm={asking === 'approve' ? 'Onayla' : 'Reddet'} danger={asking === 'reject'} input="Not" required={asking === 'reject'}
        busy={decide.isPending} onClose={() => setAsking(null)} onConfirm={(note) => decide.mutate({ ok: asking === 'approve', note })} />
    </Panel>
  );
}

/** Kanıt: hesapçının döndürdüğü ayrıntı (liste, kova, ilk cariler…). Tavan yok; uzun liste kendi kutusunda kayar. */
function Evidence({ kanit, birim }: { kanit: Record<string, unknown>; birim: string }) {
  const entries = Object.entries(kanit ?? {});
  if (!entries.length) return null;
  return (
    <div className="space-y-2">
      {entries.map(([k, v]) => {
        if (Array.isArray(v)) {
          if (!v.length) return <div key={k}><b>{k}</b>: —</div>;
          if (typeof v[0] !== 'object') return <div key={k}><b>{k}</b>: {v.join(', ')}</div>;
          const cols = Object.keys(v[0] as Record<string, unknown>);
          return (
            <div key={k}>
              <div className="font-bold">{k} ({v.length})</div>
              <div className="mt-1 max-h-64 overflow-auto rounded-xl border border-slate-100 bg-white/80">
                <table className="w-full min-w-[420px] text-[11.5px]">
                  <thead><tr>{cols.map((c) => <th key={c} className="whitespace-nowrap px-2 py-1 text-left font-bold text-canvas-muted">{c}</th>)}</tr></thead>
                  <tbody>
                    {(v as Array<Record<string, unknown>>).map((row, i) => (
                      <tr key={i} className="border-t border-slate-100">
                        {cols.map((c) => <td key={c} className="px-2 py-1 align-top">{typeof row[c] === 'object' ? JSON.stringify(row[c]) : String(row[c] ?? '—')}</td>)}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          );
        }
        return <div key={k}><b>{k}</b>: {typeof v === 'number' && ['tutar', 'toplam', 'tlToplam'].includes(k) ? fmtValue(v, 'tl') : typeof v === 'object' ? JSON.stringify(v) : String(v ?? '—')}</div>;
      })}
      <div className="text-[10.5px] text-canvas-muted">Birim: {birim === 'yuzde' ? '%' : birim}</div>
    </div>
  );
}

function ThresholdSheet({ g, meta, onClose }: { g: Indicator; meta: RiskMeta; onClose: () => void }) {
  const qc = useQueryClient();
  const [sari, setSari] = useState(g.esikSari === null ? '' : String(g.esikSari).replace('.', ','));
  const [kirmizi, setKirmizi] = useState(g.esikKirmizi === null ? '' : String(g.esikKirmizi).replace('.', ','));
  const [yon, setYon] = useState(g.yon);
  const [siklik, setSiklik] = useState(g.siklik);
  const [sahip, setSahip] = useState(g.sahip ?? '');
  const [eposta, setEposta] = useState(g.sahipEposta ?? '');
  const [not, setNot] = useState('');
  const save = useMutation({
    mutationFn: () => riskApi.proposeIndicator({ kod: g.kod, esikSari: parseNum(sari), esikKirmizi: parseNum(kirmizi), yon, siklik, sahip, sahipEposta: eposta, not }),
    onSuccess: () => {
      toast.success('Taslak onaya gönderildi');
      qc.invalidateQueries({ queryKey: ['risk'] });
      onClose();
    },
    onError: (e) => toast.error(errText(e, 'Taslak kaydedilemedi.')),
  });
  const unit = meta.birimler[g.birim] ?? g.birim;
  return (
    <Sheet open modal onClose={onClose} title={`${g.ad}: eşik ve sahip`} subtitle="Yeni sürüm taslak olarak kaydedilir; başka bir yetkili onaylayınca yürürlüğe girer.">
      <form className="flex flex-col gap-3" onSubmit={(e) => { e.preventDefault(); save.mutate(); }}>
        <SelectInput id="th-yon" label="Yön" value={yon} onChange={setYon} options={meta.yonler} />
        <div className="grid grid-cols-2 gap-3">
          <TextInput id="th-sari" label={`Sarı eşik (${unit})`} value={sari} onChange={setSari} />
          <TextInput id="th-kirmizi" label={`Kırmızı eşik (${unit})`} value={kirmizi} onChange={setKirmizi} />
        </div>
        <SelectInput id="th-siklik" label="Ölçüm sıklığı" value={siklik} onChange={setSiklik} options={meta.sikliklar} />
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <TextInput id="th-sahip" label="Sahip (kullanıcı adı)" value={sahip} onChange={setSahip} />
          <TextInput id="th-eposta" label="Sahibin e-postası" type="email" value={eposta} onChange={setEposta} />
        </div>
        <TextInput id="th-not" label="Gerekçe" area value={not} onChange={setNot} help="Eşiğin neden bu değer olduğu; onaylayan görür." />
        <div className="flex flex-wrap justify-end gap-2">
          <button type="button" className={btnGhost} onClick={onClose}>Vazgeç</button>
          <button type="submit" className={btnPrimary} disabled={save.isPending}>
            {save.isPending && <Loader2 aria-hidden className="h-4 w-4 animate-spin" />}
            Onaya gönder
          </button>
        </div>
      </form>
    </Sheet>
  );
}

