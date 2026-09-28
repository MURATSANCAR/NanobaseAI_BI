import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { ChevronLeft, Loader2, Sparkles } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import { Note, Pill, btnGhost, btnPrimary, errText, field, label as labelCls } from '../admin/ui';
import { Panel } from '../editorial/kit';
import { FilePick } from '../tenders/parts';
import { dijitalApi, fmtInt, fmtMoney, lastMonth, type ImportDetail, type SaleRow } from './api';

/** Satış raporu yükleme: dosya → önizleme (kolon eşlemesi, kurallı eşleşme, atılan kişisel kolonlar) → Zeki AI önerisi ve
 *  elle eşleme → kurla onay. Hiçbir satır atılmaz; eşleşmeyen satır onaydan sonra da açık iş olarak eşlenebilir. */

const ROLE_LABEL: Record<string, string> = {
  kimlik: 'Kitap kimliği (ISBN, e-ISBN, stok kodu)', baslik: 'Kitap adı', yazar: 'Yazar', adet: 'Adet', brut: 'Brüt tutar',
  net: 'Net tutar', para: 'Para birimi', tarih: 'Tarih / dönem',
};
const MATCH_LABEL = { kural: 'Kural', zeki: 'Zeki AI (onaylı)', elle: 'Elle' } as const;

export default function ImportWizard({ id, canImport, onDone, onClose }: {
  id: string | null; canImport: boolean; onDone: (id: string) => void; onClose: () => void;
}) {
  return (
    <div className="flex flex-col gap-3">
      <div>
        <button type="button" className={btnGhost} onClick={onClose}>
          <ChevronLeft aria-hidden className="h-4 w-4" />
          Rapor listesi
        </button>
      </div>
      {id ? <Preview id={id} canImport={canImport} /> : canImport ? <UploadStep onDone={onDone} /> : <Note tone="warn">Rapor yükleme rolünüzde yok.</Note>}
    </div>
  );
}

function UploadStep({ onDone }: { onDone: (id: string) => void }) {
  const qc = useQueryClient();
  const plats = useQuery({ queryKey: ['dijital', 'platforms'], queryFn: dijitalApi.platforms, enabled: ENGINE_ENABLED });
  const [platform, setPlatform] = useState(0);
  const [donem, setDonem] = useState(lastMonth());
  const up = useMutation({
    mutationFn: (f: File) => dijitalApi.upload(f, platform, donem),
    onSuccess: (r) => {
      toast.success(`${fmtInt(r.satir)} satır okundu; ${fmtInt(r.eslesen)} kitap kuralla eşleşti.`);
      qc.invalidateQueries({ queryKey: ['dijital', 'imports'] });
      onDone(r.id);
    },
    onError: (e) => toast.error(errText(e, 'Dosya okunamadı.') ?? ''),
  });
  const active = plats.data?.items.filter((p) => p.aktif) ?? [];
  const ok = platform > 0 && /^\d{4}-(0[1-9]|1[0-2])$/.test(donem);
  return (
    <Panel>
      <h2 className="text-[15px] font-extrabold">1. Raporu yükle</h2>
      <p className="mt-0.5 max-w-[80ch] text-[12px] leading-snug text-canvas-muted">
        Platformun ya da dağıtıcının aylık satış raporu (Excel ya da CSV). Kolonlar adlarından tanınır, sonra düzeltebilirsiniz.
        Okur adı, e-posta, telefon, adres gibi kişisel veri kolonları yüklemede atılır ve saklanmaz.
      </p>
      {plats.data && !active.length && <Note tone="warn">Önce Katalog → Platformlar'da platform tanımlanmalı.</Note>}
      <div className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-[minmax(0,260px)_160px_auto] sm:items-end">
        <label className="flex flex-col gap-1">
          <span className={labelCls}>Platform</span>
          <select className={field} value={platform} onChange={(e) => setPlatform(Number(e.target.value))}>
            <option value={0}>Seçin</option>
            {active.map((p) => <option key={p.id} value={p.id}>{p.ad} ({p.paraBirimi})</option>)}
          </select>
        </label>
        <label className="flex flex-col gap-1">
          <span className={labelCls}>Dönem (YYYY-AA)</span>
          <input className={field} value={donem} onChange={(e) => setDonem(e.target.value.trim())} />
        </label>
        <div className="flex items-center gap-2">
          <FilePick label={up.isPending ? 'Okunuyor…' : 'Dosya seç ve yükle'} accept=".xlsx,.csv,.txt" disabled={!ok || up.isPending} onPick={(f) => up.mutate(f)} />
          {up.isPending && <Loader2 aria-hidden className="h-4 w-4 animate-spin" />}
        </div>
      </div>
    </Panel>
  );
}

function Preview({ id, canImport }: { id: string; canImport: boolean }) {
  const qc = useQueryClient();
  const q = useQuery({
    queryKey: ['dijital', 'import', id],
    queryFn: () => dijitalApi.importDetail(id),
    enabled: ENGINE_ENABLED,
    refetchInterval: (query) => (query.state.data?.eslestirme?.durum === 'suruyor' ? 2000 : false),
  });
  const set = (d: ImportDetail) => {
    qc.setQueryData(['dijital', 'import', id], d);
    qc.invalidateQueries({ queryKey: ['dijital', 'imports'] });
    qc.invalidateQueries({ queryKey: ['dijital', 'sales'] });
  };
  const onErr = (e: unknown) => toast.error(errText(e, 'Yapılamadı.') ?? '');
  const remap = useMutation({ mutationFn: (k: Record<string, number | null>) => dijitalApi.remap(id, k), onSuccess: set, onError: onErr });
  const match = useMutation({
    mutationFn: () => dijitalApi.match(id),
    onSuccess: (r) => {
      toast.success(r.started ? (r.model ? 'Zeki AI önerileri hazırlanıyor.' : 'Model şu an yok; adaylar ad benzerliğiyle listelenecek.') : 'Öneri işi zaten sürüyor.');
      qc.invalidateQueries({ queryKey: ['dijital', 'import', id] });
    },
    onError: onErr,
  });
  const strong = useMutation({ mutationFn: () => dijitalApi.acceptStrong(id), onSuccess: (d) => { set(d); toast.success('Güçlü öneriler onaylandı.'); }, onError: onErr });
  const rows = useMutation({
    mutationFn: (b: Array<{ id: number; kitapId: string | null; kaynak: 'zeki' | 'elle' }>) => dijitalApi.rows(id, b),
    onSuccess: set,
    onError: onErr,
  });
  const [rates, setRates] = useState<Record<string, string>>({});
  const commit = useMutation({ mutationFn: () => dijitalApi.commit(id, rates), onSuccess: (d) => { set(d); toast.success('Rapor onaylandı.'); }, onError: onErr });
  const [filter, setFilter] = useState<'acik' | 'hepsi' | 'eslesen'>('acik');
  const d = q.data;
  if (q.isLoading) return <div className="py-8 text-center text-[12px] text-canvas-muted">Yükleniyor…</div>;
  if (q.error || !d) return <Note tone="err">{errText(q.error, 'Rapor okunamadı.')}</Note>;
  const preview = d.durum === 'onizleme';
  const editable = canImport && d.durum !== 'iptal';
  const foreign = d.paraBirimleri.filter((c) => c !== 'TRY');
  const job = d.eslestirme;
  const shown = d.satirlar.filter((r) => (filter === 'hepsi' ? true : filter === 'acik' ? r.tur === 'satir' && !r.kitapId : !!r.kitapId));
  const strongCount = d.satirlar.filter((r) => !r.kitapId && r.olasilik !== null && r.adaylar.some((a) => a.oneri)).length;
  return (
    <>
      <Panel>
        <div className="flex flex-wrap items-center gap-1.5">
          <Pill tone={preview ? 'warn' : d.durum === 'onaylandi' ? 'ok' : 'muted'}>{preview ? 'Önizleme' : d.durum === 'onaylandi' ? 'Onaylı' : 'İptal'}</Pill>
          <span className="font-mono text-[12px]">{d.id}</span>
        </div>
        <h2 className="mt-1 break-words text-[16px] font-extrabold">{d.platform} · {d.donem}</h2>
        <p className="text-[12px] text-canvas-muted">{d.dosya} · {d.yukleyen}</p>
        <div className="mt-2 grid grid-cols-2 gap-2 sm:grid-cols-4">
          <Stat label="Satır" value={fmtInt(d.satir)} help={`${d.ozetSatir} toplam satırı (toplama girmez) · ${d.bosSatir} boş satır`} />
          <Stat label="Eşleşen" value={fmtInt(d.eslesen)} />
          <Stat label="Açık" value={fmtInt(d.eslesmeyen)} />
          {Object.entries(d.toplamlar).map(([cur, t]) => <Stat key={cur} label={`Net (${cur})`} value={fmtMoney(t.net, cur)} help={`${fmtInt(t.adet)} adet`} />)}
        </div>
        {!!d.atilanKolonlar.length && <Note tone="info">Kişisel veri olduğu için atılan kolonlar: {d.atilanKolonlar.join(', ')}. Bu kolonlar saklanmadı.</Note>}
      </Panel>

      {preview && canImport && (
        <Panel>
          <h2 className="text-[15px] font-extrabold">2. Kolonlar</h2>
          <p className="mt-0.5 text-[12px] text-canvas-muted">Yanlış tanınan kolonu düzeltin; satırlar dosyadan yeniden kurulur.</p>
          <div className="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-4">
            {d.roller.map((role) => (
              <label key={role} className="flex flex-col gap-1">
                <span className={labelCls}>{ROLE_LABEL[role] ?? role}</span>
                <select className={field} value={d.kolonlar[role] ?? ''} disabled={remap.isPending}
                  onChange={(e) => remap.mutate({ [role]: e.target.value === '' ? null : Number(e.target.value) })}>
                  <option value="">— yok —</option>
                  {d.baslik.map((h, j) => (h ? <option key={j} value={j}>{h}</option> : null))}
                </select>
              </label>
            ))}
          </div>
        </Panel>
      )}

      <Panel>
        <div className="flex flex-wrap items-end justify-between gap-2">
          <div className="min-w-0">
            <h2 className="text-[15px] font-extrabold">{preview ? '3. Eşleme' : 'Satırlar'}</h2>
            <p className="mt-0.5 max-w-[80ch] text-[12px] leading-snug text-canvas-muted">
              Kurallı eşleme: e-ISBN, e-kitap barkodu, ISBN, barkod, e-kitap stok kodu, stok kodu. Kalan satırlar için Zeki AI aday
              önerir; hiçbir öneri kendiliğinden onaylanmaz.
            </p>
          </div>
          {editable && (
            <div className="flex flex-wrap gap-1.5">
              <button type="button" className={btnGhost} disabled={match.isPending || job?.durum === 'suruyor' || !d.eslesmeyen} onClick={() => match.mutate()}>
                {job?.durum === 'suruyor' ? <Loader2 aria-hidden className="h-4 w-4 animate-spin" /> : <Sparkles aria-hidden className="h-4 w-4" />}
                {job?.durum === 'suruyor' ? `Öneriliyor ${job.bitti ?? 0}/${job.toplam ?? 0}` : 'Zeki AI önerisi al'}
              </button>
              <button type="button" className={btnGhost} disabled={strong.isPending || !strongCount} onClick={() => strong.mutate()}>
                Güçlü önerileri onayla
              </button>
            </div>
          )}
        </div>
        {job?.durum === 'hata' && <Note tone="warn">{job.mesaj}</Note>}
        {job?.durum === 'bitti' && job.model === false && <Note tone="info">Model şu an yok; adaylar yalnız ad/yazar benzerliğiyle sıralandı.</Note>}
        <div className="mt-2 flex flex-wrap gap-1.5">
          {(['acik', 'eslesen', 'hepsi'] as const).map((k) => (
            <button key={k} type="button" onClick={() => setFilter(k)} aria-pressed={filter === k}
              className={`min-h-11 rounded-xl px-3 text-[12px] font-bold sm:min-h-8 ${filter === k ? 'bg-canvas-violet text-white' : 'bg-slate-100'}`}>
              {k === 'acik' ? `Açık (${d.eslesmeyen})` : k === 'eslesen' ? `Eşleşen (${d.eslesen})` : `Hepsi (${d.satir})`}
            </button>
          ))}
        </div>
        <div className="mt-2 flex flex-col gap-2">
          {!shown.length && <div className="py-6 text-center text-[12.5px] text-canvas-muted">Bu süzgeçte satır yok.</div>}
          {shown.map((r) => <RowCard key={r.id} r={r} editable={editable} busy={rows.isPending} onPick={(kitapId, kaynak) => rows.mutate([{ id: r.id, kitapId, kaynak }])} />)}
        </div>
      </Panel>

      {preview && canImport && (
        <Panel>
          <h2 className="text-[15px] font-extrabold">4. Onay</h2>
          <p className="mt-0.5 max-w-[80ch] text-[12px] leading-snug text-canvas-muted">
            Onaydan sonra satırlar satış panosuna girer. Eşleşmeyen {fmtInt(d.eslesmeyen)} satır atılmaz; açık iş olarak kalır ve sonra
            eşlenebilir. Aynı platformun aynı dönemi zaten onaylıysa önce o iptal edilmeli.
          </p>
          {!!foreign.length && (
            <div className="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-3">
              {foreign.map((c) => (
                <label key={c} className="flex flex-col gap-1">
                  <span className={labelCls}>1 {c} = ? TL</span>
                  <input className={field} inputMode="decimal" value={rates[c] ?? ''} onChange={(e) => setRates((x) => ({ ...x, [c]: e.target.value }))} />
                </label>
              ))}
            </div>
          )}
          <div className="mt-3 flex justify-end">
            <button type="button" className={btnPrimary} disabled={commit.isPending || foreign.some((c) => !(rates[c] ?? '').trim())} onClick={() => commit.mutate()}>
              {commit.isPending && <Loader2 aria-hidden className="h-4 w-4 animate-spin" />}
              Raporu onayla
            </button>
          </div>
        </Panel>
      )}
      {!preview && !!Object.keys(d.kurlar).length && (
        <Note tone="info">Onaylayan {d.onaylayan}; kurlar: {Object.entries(d.kurlar).map(([c, k]) => `${c} ${k}`).join(' · ')}.</Note>
      )}
    </>
  );
}

function Stat({ label, value, help }: { label: string; value: string; help?: string }) {
  return (
    <div className="min-w-0 rounded-xl bg-white/80 px-3 py-2">
      <div className="text-[10.5px] font-bold uppercase tracking-wide text-canvas-muted">{label}</div>
      <div className="mt-0.5 font-mono text-[15px] font-bold tabular-nums">{value}</div>
      {help && <div className="mt-0.5 text-[11px] leading-snug text-canvas-muted">{help}</div>}
    </div>
  );
}

function RowCard({ r, editable, busy, onPick }: { r: SaleRow; editable: boolean; busy: boolean; onPick: (kitapId: string | null, kaynak: 'zeki' | 'elle') => void }) {
  const best = r.adaylar.find((a) => a.oneri);
  return (
    <div className={`rounded-2xl border p-3 ${r.tur === 'ozet' ? 'border-dashed border-slate-200 bg-slate-50' : 'border-slate-100 bg-white/80'}`}>
      <div className="grid grid-cols-1 gap-2 md:grid-cols-[minmax(0,1.2fr)_minmax(0,1.2fr)_140px] md:items-start">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-1.5 text-[11px] text-canvas-muted">
            <span className="font-mono">satır {r.sira}</span>
            {r.tur === 'ozet' && <Pill tone="muted">Toplam satırı — toplama girmez</Pill>}
            {r.donem && <span className="font-mono">{r.donem}</span>}
          </div>
          <div className="mt-0.5 break-words text-[13px] font-bold">{r.baslik ?? '—'}</div>
          <div className="break-words text-[11.5px] text-canvas-muted">{[r.yazar, r.kimlik].filter(Boolean).join(' · ')}</div>
        </div>
        <div className="min-w-0 text-[12px]">
          {r.kitapId ? (
            <div className="flex flex-wrap items-center gap-1.5">
              <Pill tone="ok">{r.eslesme ? MATCH_LABEL[r.eslesme] : 'Eşleşti'}{r.anahtar ? ` · ${r.anahtar}` : ''}</Pill>
              <span className="break-words font-bold">{r.kitapAd ?? r.kitapId}</span>
              {editable && r.eslesme !== 'kural' && (
                <button type="button" className="min-h-11 text-[11.5px] font-bold text-canvas-violet hover:underline sm:min-h-0" disabled={busy} onClick={() => onPick(null, 'elle')}>kaldır</button>
              )}
            </div>
          ) : r.tur === 'satir' ? (
            r.adaylar.length ? (
              <div className="flex flex-col gap-1">
                {best && r.olasilik !== null && <span className="text-[11.5px] text-canvas-muted">Zeki AI önerisi: olasılık %{Math.round(r.olasilik * 100)}</span>}
                <select className={field} disabled={!editable || busy} value=""
                  onChange={(e) => e.target.value && onPick(e.target.value, best && e.target.value === best.kitapId ? 'zeki' : 'elle')}>
                  <option value="">Kitap seçin…</option>
                  {r.adaylar.map((a) => (
                    <option key={a.kitapId} value={a.kitapId}>
                      {a.oneri ? '★ ' : ''}{a.ad} — {a.yazar ?? 'yazar yok'} ({a.stokKodu ?? '—'}){a.olasilik !== null ? ` %${Math.round(a.olasilik * 100)}` : ''}
                    </option>
                  ))}
                </select>
              </div>
            ) : (
              <span className="text-[11.5px] text-canvas-muted">Eşleşmedi. Zeki AI önerisi alınınca adaylar burada listelenir.</span>
            )
          ) : null}
        </div>
        <div className="text-right font-mono text-[12px] tabular-nums">
          <div>{fmtInt(r.adet)} adet</div>
          <div>{fmtMoney(r.net, r.paraBirimi ?? '')}</div>
          {r.netTl !== null && <div className="text-canvas-muted">{fmtMoney(r.netTl)}</div>}
        </div>
      </div>
    </div>
  );
}
