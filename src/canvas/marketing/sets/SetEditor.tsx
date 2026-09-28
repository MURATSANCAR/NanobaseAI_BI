import { useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Download, Link2, Loader2, Save, Sparkles, Trash2 } from 'lucide-react';
import { ENGINE_ENABLED } from '../../engine';
import { Note, TableWrap, btnGhost, btnPrimary, errText, field, label as labelCls, td, th } from '../../admin/ui';
import { Panel, useDebounced } from '../../editorial/kit';
import { fmtDay, fmtInt, fmtMoney, fmtPct, fmtShort, parseNum } from '../../budget/api';
import { AskSheet } from '../../budget/parts';
import { STATUS_TONE, addItem, canEditSet, pctToRatio, setsApi, type ItemInput, type SetRow, type SetsMeta } from './api';
import { MarginCell, SetsFrame, Tone } from './parts';
import BookPicker from './BookPicker';

/** Set ekranı: bileşenler, fiyat–marj hesaplayıcı (kaydetmeden anında), ambalaj, sezon ve kanal, ZEKİ AI metinleri, onay,
 *  «CRM/Logo'ya açılacak kart» listesi ve CRM kartıyla eşleme. */

type Ask = null | 'submit' | 'withdraw' | 'approve' | 'reject' | 'delete';

export default function SetEditor() {
  const { id = '' } = useParams();
  const qc = useQueryClient();
  const nav = useNavigate();
  const meta = useQuery({ queryKey: ['sets', 'meta'], queryFn: setsApi.meta, enabled: ENGINE_ENABLED, staleTime: 60_000 });
  const set = useQuery({ queryKey: ['sets', 'set', id], queryFn: () => setsApi.get(id), enabled: ENGINE_ENABLED && !!id });
  const [ask, setAsk] = useState<Ask>(null);
  const me = meta.data?.me;
  const s = set.data;

  const onSaved = (out: SetRow | null, msg: string) => {
    if (out) qc.setQueryData(['sets', 'set', id], out);
    qc.invalidateQueries({ queryKey: ['sets'] });
    toast.success(msg);
  };
  const act = useMutation({
    mutationFn: async ({ kind, text }: { kind: Exclude<Ask, null>; text: string }) => {
      switch (kind) {
        case 'submit': return setsApi.submit(id);
        case 'withdraw': return setsApi.withdraw(id);
        case 'approve': return setsApi.approve(id, text || undefined);
        case 'reject': return setsApi.reject(id, text);
        case 'delete': await setsApi.remove(id); return null;
      }
    },
    onSuccess: (out, { kind }) => {
      setAsk(null);
      if (kind === 'delete') {
        qc.invalidateQueries({ queryKey: ['sets'] });
        toast.success('Taslak silindi.');
        nav('/pazarlama/set-hediye');
        return;
      }
      onSaved(out, { submit: 'Set onaya gönderildi.', withdraw: 'Set taslağa alındı.', approve: 'Set onaylandı; açılacak kart listesi hazır.', reject: 'Set gerekçesiyle geri gönderildi.', delete: 'Taslak silindi.' }[kind]);
    },
    onError: (e) => toast.error(errText(e, 'İşlem yapılamadı.') ?? ''),
  });
  const status = useMutation({
    mutationFn: (durum: string) => setsApi.update(id, { durum }),
    onSuccess: (out) => onSaved(out, 'Durum güncellendi.'),
    onError: (e) => toast.error(errText(e, 'Durum değişmedi.') ?? ''),
  });

  if (!ENGINE_ENABLED) return <SetsFrame title="Set" lead="" source="CRM + Logo" presence="" back={{ to: '/pazarlama/set-hediye', label: 'Set ve hediye' }}><Note tone="warn">Veri bağlantısı bu derlemede tanımlı değil.</Note></SetsFrame>;

  const editable = !!s && canEditSet(s.durum) && !!me?.canWrite;
  const mine = (s?.gonderen ?? '').toLowerCase() === (me?.username ?? '').toLowerCase();

  return (
    <SetsFrame
      title={s?.ad ?? 'Set'}
      lead={s ? `${s.turAdi} · ${s.kaynakAdi}${s.stokKodu ? ` · stok kodu ${s.stokKodu}` : ''}${s.bilesenKaynak ? ` · bileşenler: ${s.bilesenKaynak === 'crm-set-islemi' ? 'CRM set işlemi' : s.bilesenKaynak === 'logo-recete' ? 'Logo reçetesi' : 'portal'}` : ''}` : ''}
      back={{ to: '/pazarlama/set-hediye', label: 'Set ve hediye' }}
      source="CRM + Logo"
      presence={s?.durumAdi ?? ''}
    >
      {set.error && <Note tone="err">{errText(set.error, 'Set açılamadı.')}</Note>}
      {set.isLoading && <Note tone="info">Yükleniyor…</Note>}
      {s && meta.data && (
        <>
          <div className="flex flex-wrap items-center gap-2 px-1">
            <Tone tone={STATUS_TONE[s.durum]}>{s.durumAdi}</Tone>
            <span className="text-[12px] font-semibold text-canvas-muted">
              {s.olusturan && <>{s.olusturan} açtı</>}
              {s.durum === 'onayda' && s.gonderen && <> · {s.gonderen} onaya gönderdi</>}
              {s.onaylayan && s.decidedAt && s.durum !== 'taslak' && <> · {s.onaylayan} onayladı, {fmtDay(s.decidedAt)}</>}
            </span>
            <div className="ml-auto flex flex-wrap gap-2">
              {editable && s.kaynak !== 'crm' && <button type="button" className={btnGhost} onClick={() => setAsk('delete')}><Trash2 aria-hidden className="h-4 w-4" /> Sil</button>}
              {editable && <button type="button" className={btnPrimary} onClick={() => setAsk('submit')}>Onaya gönder</button>}
              {s.durum === 'onayda' && me?.canWrite && <button type="button" className={btnGhost} onClick={() => setAsk('withdraw')}>Onaydan çek</button>}
              {s.durum === 'onayda' && me?.canApprove && !mine && (
                <>
                  <button type="button" className={btnGhost} onClick={() => setAsk('reject')}>Geri gönder</button>
                  <button type="button" className={btnPrimary} onClick={() => setAsk('approve')}>Onayla</button>
                </>
              )}
              {me?.canWrite && s.durum === 'satista' && <button type="button" className={btnGhost} disabled={status.isPending} onClick={() => status.mutate('kapanacak')}>Kapanacak işaretle</button>}
              {me?.canWrite && s.durum === 'kapanacak' && (
                <>
                  <button type="button" className={btnGhost} disabled={status.isPending} onClick={() => status.mutate('satista')}>Satışta tut</button>
                  <button type="button" className={btnGhost} disabled={status.isPending} onClick={() => status.mutate('kapandi')}>Kapandı</button>
                </>
              )}
            </div>
          </div>
          {s.durum === 'taslak' && s.kararNotu && <Note tone="warn">Geri gönderildi ({s.onaylayan}): {s.kararNotu}</Note>}
          {s.durum === 'onayda' && me?.canApprove && mine && <Note tone="info">Bu seti siz onaya gönderdiniz; onayı başka bir yetkili verir.</Note>}
          {s.durum === 'onayda' && s.marjOrani !== undefined && s.marjOrani !== null && meta.data.settings.marginMinPct !== null && s.marjOrani < meta.data.settings.marginMinPct / 100 && (
            <Note tone="warn">Marj alt sınırın altında (%{(s.marjOrani * 100).toLocaleString('tr-TR', { maximumFractionDigits: 1 })} &lt; %{meta.data.settings.marginMinPct}).</Note>
          )}

          <div className="grid gap-3 xl:grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)]">
            <Components s={s} editable={editable} canSeeCost={!!me?.canSeeCost} onSaved={(o) => onSaved(o, 'Bileşenler kaydedildi.')} />
            <PricePanel s={s} editable={editable} meta={meta.data} onSaved={(o) => onSaved(o, 'Fiyat ve ambalaj kaydedildi.')} />
          </div>
          <div className="grid gap-3 xl:grid-cols-2">
            <DetailsPanel s={s} canWrite={!!me?.canWrite} seasons={meta.data.seasons} onSaved={(o) => onSaved(o, 'Kaydedildi.')} />
            <TextsPanel s={s} canWrite={!!me?.canWrite} onSaved={(o) => onSaved(o, 'Metin kaydedildi.')} />
          </div>
          {(s.durum === 'kart-bekliyor' || s.durum === 'satista') && s.kaynak !== 'crm' && (
            <CardPanel s={s} canWrite={!!me?.canWrite} canExport={!!me?.canExport} onSaved={(o) => onSaved(o, 'CRM kartıyla eşlendi.')} />
          )}
          {s.kaynak === 'crm' && <CrmPanel s={s} />}
        </>
      )}
      <AskSheet
        open={ask !== null}
        busy={act.isPending}
        title={{ submit: 'Onaya gönder', withdraw: 'Onaydan çek', approve: 'Seti onayla', reject: 'Geri gönder', delete: 'Taslağı sil', '': '' }[ask ?? '']}
        message={
          ask === 'submit' ? 'Set ve fiyatı onaycıya düşer; onayı sizden başka bir yetkili verir. Onayda iken bileşen ve fiyat değişmez.'
            : ask === 'withdraw' ? 'Set yeniden taslak olur.'
            : ask === 'approve' ? 'Set onaylanır ve «CRM kartı bekliyor» olur. CRM\'e ve Logo\'ya bir şey yazılmaz; açılacak kart listesi ekibe iner.'
            : ask === 'reject' ? 'Set gerekçenizle taslağa döner.'
            : 'Taslak ve bileşenleri silinir; öneriden geldiyse öneri yeniden açılır.'
        }
        confirm={{ submit: 'Onaya gönder', withdraw: 'Taslağa al', approve: 'Onayla', reject: 'Geri gönder', delete: 'Sil', '': '' }[ask ?? '']}
        danger={ask === 'delete'}
        input={ask === 'reject' ? 'Gerekçe' : ask === 'approve' ? 'Not (isteğe bağlı)' : undefined}
        required={ask === 'reject'}
        onClose={() => setAsk(null)}
        onConfirm={(text) => ask && act.mutate({ kind: ask, text })}
      />
    </SetsFrame>
  );
}

/* ------------------------------------------------------------------ bileşenler */

function Components({ s, editable, canSeeCost, onSaved }: { s: SetRow; editable: boolean; canSeeCost: boolean; onSaved: (o: SetRow) => void }) {
  const initial = useMemo<ItemInput[]>(() => (s.bilesenler ?? []).map((i) => ({ stok: i.stok, adet: i.adet })), [s.bilesenler]);
  const [items, setItems] = useState<ItemInput[]>(initial);
  const [names, setNames] = useState<Record<string, string>>({});
  useEffect(() => setItems(initial), [initial]);
  const dirty = JSON.stringify(items) !== JSON.stringify(initial);
  const save = useMutation({
    mutationFn: () => setsApi.items(s.id, items),
    onSuccess: onSaved,
    onError: (e) => toast.error(errText(e, 'Bileşenler kaydedilemedi.') ?? ''),
  });
  const byCode = new Map((s.bilesenler ?? []).map((i) => [i.stok, i]));
  return (
    <Panel>
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-[15px] font-extrabold">Bileşenler</h2>
        {editable && dirty && (
          <button type="button" className={btnPrimary} disabled={save.isPending || !items.length} onClick={() => save.mutate()}>
            <Save aria-hidden className="h-4 w-4" /> Bileşenleri kaydet
          </button>
        )}
      </div>
      {editable && <div className="mb-2"><BookPicker onPick={(b) => { setItems((x) => addItem(x, b.stok)); setNames((n) => ({ ...n, [b.stok]: b.ad ?? b.stok })); }} /></div>}
      <TableWrap>
        <thead>
          <tr className="border-b border-slate-100">
            <th className={th}>Kitap</th>
            <th className={`${th} text-right`}>Adet</th>
            <th className={`${th} text-right`}>Liste (KDV dahil)</th>
            <th className={`${th} text-right`}>KDV</th>
            {canSeeCost && <th className={`${th} text-right`}>Birim maliyet</th>}
            <th className={`${th} text-right`}>Logo stoku</th>
            {editable && <th className={th}><span className="sr-only">Çıkar</span></th>}
          </tr>
        </thead>
        <tbody>
          {items.map((it) => {
            const b = byCode.get(it.stok);
            return (
              <tr key={it.stok} className="border-b border-slate-50 last:border-0">
                <td className={td}><span className="font-semibold">{b?.ad ?? names[it.stok] ?? it.stok}</span><div className="text-[11px] text-canvas-muted">{it.stok}{b?.kaynakAdi ? ` · ${b.kaynakAdi}` : b ? '' : ' · kaydedilmedi'}</div></td>
                <td className={`${td} text-right`}>
                  {editable ? (
                    <input aria-label="Adet" className={`${field} ml-auto w-20 text-right font-mono`} inputMode="numeric" value={String(it.adet)}
                      onChange={(e) => setItems((x) => x.map((y) => (y.stok === it.stok ? { ...y, adet: Math.max(1, Number(e.target.value) || 1) } : y)))} />
                  ) : <span className="font-mono tabular-nums">{fmtInt(it.adet)}</span>}
                </td>
                <td className={`${td} text-right font-mono tabular-nums`}>{b ? fmtMoney(b.liste) : '—'}{b && typeof b.listeLogo === 'number' && typeof b.liste === 'number' && Math.abs(b.listeLogo - b.liste) > 0.01 ? <div className="text-[11px] text-canvas-muted">Logo {fmtMoney(b.listeLogo)}</div> : null}</td>
                <td className={`${td} text-right font-mono tabular-nums`}>{b?.kdv === null || b?.kdv === undefined ? '—' : `%${b.kdv}`}</td>
                {canSeeCost && <td className={`${td} text-right font-mono tabular-nums`}>{b?.maliyet === null || b?.maliyet === undefined ? <span className="text-canvas-muted">bilinmiyor</span> : fmtMoney(b.maliyet)}</td>}
                <td className={`${td} text-right font-mono tabular-nums ${b?.stokAdet !== null && b?.stokAdet !== undefined && b.stokAdet <= 0 ? 'font-bold text-red-700' : ''}`}>{b ? fmtInt(b.stokAdet) : '—'}</td>
                {editable && (
                  <td className={td}>
                    <button type="button" aria-label="Çıkar" className={btnGhost} onClick={() => setItems((x) => x.filter((y) => y.stok !== it.stok))}>
                      <Trash2 aria-hidden className="h-4 w-4" />
                    </button>
                  </td>
                )}
              </tr>
            );
          })}
          {!items.length && <tr><td className={`${td} text-canvas-muted`} colSpan={7}>Bileşen yok.</td></tr>}
        </tbody>
      </TableWrap>
      {s.stokKodu && (
        <p className="mt-2 text-[11.5px] text-canvas-muted">
          Set stoğu {fmtInt(s.stok)} · son 12 ay {fmtInt(s.son12Adet)} adet, {fmtShort(s.son12Ciro)} ₺ (setin kendi kodu; bileşenlerin tek satışına eklenmez).
        </p>
      )}
    </Panel>
  );
}

/* ------------------------------------------------------------------ fiyat – marj */

function PricePanel({ s, editable, meta, onSaved }: { s: SetRow; editable: boolean; meta: SetsMeta; onSaved: (o: SetRow) => void }) {
  const [price, setPrice] = useState(s.setFiyati === null ? '' : String(s.setFiyati).replace('.', ','));
  const [disc, setDisc] = useState('');
  const [pack, setPack] = useState(s.ambalajTuru ?? '');
  const [packCost, setPackCost] = useState(s.ambalajBirimMaliyet === null || s.ambalajBirimMaliyet === undefined ? '' : String(s.ambalajBirimMaliyet).replace('.', ','));
  const key = useDebounced(JSON.stringify({ price, disc, packCost }), 300);
  const calc = useQuery({
    queryKey: ['sets', 'price', s.id, key, s.bilesenler?.length],
    queryFn: () => {
      const r = pctToRatio(disc);
      return setsApi.price(s.id, r !== null ? { indirim: r, ambalajBirimMaliyet: parseNum(packCost) } : { setFiyati: parseNum(price), ambalajBirimMaliyet: parseNum(packCost) });
    },
  });
  const save = useMutation({
    mutationFn: () => {
      const b: Record<string, unknown> = { ambalajTuru: pack || null };
      const setPrice = pctToRatio(disc) !== null ? calc.data?.setFiyati ?? null : parseNum(price);
      b.setFiyati = setPrice;
      if (meta.me.canSeeCost) b.ambalajBirimMaliyet = parseNum(packCost);
      return setsApi.update(s.id, b);
    },
    onSuccess: (o) => { setDisc(''); setPrice(o.setFiyati === null ? '' : String(o.setFiyati).replace('.', ',')); onSaved(o); },
    onError: (e) => toast.error(errText(e, 'Kaydedilemedi.') ?? ''),
  });
  const c = calc.data;
  const packOptions = meta.packaging;
  return (
    <Panel>
      <h2 className="mb-2 text-[15px] font-extrabold">Fiyat ve marj</h2>
      <div className="grid grid-cols-2 gap-2">
        <label className="flex flex-col gap-1">
          <span className={labelCls}>Set fiyatı (KDV dahil)</span>
          <input className={`${field} font-mono`} inputMode="decimal" disabled={!editable} value={pctToRatio(disc) !== null ? '' : price}
            placeholder={pctToRatio(disc) !== null && c?.setFiyati ? String(c.setFiyati) : ''} onChange={(e) => { setPrice(e.target.value); setDisc(''); }} />
        </label>
        <label className="flex flex-col gap-1">
          <span className={labelCls}>ya da indirim %</span>
          <input className={`${field} font-mono`} inputMode="decimal" disabled={!editable} value={disc} placeholder="ör. 20" onChange={(e) => setDisc(e.target.value)} />
        </label>
        <label className="flex flex-col gap-1">
          <span className={labelCls}>Ambalaj</span>
          <select className={field} disabled={!editable} value={pack}
            onChange={(e) => {
              setPack(e.target.value);
              const o = packOptions.find((p) => p.tur === e.target.value);
              if (o?.birim && meta.me.canSeeCost) setPackCost(String(o.birim).replace('.', ','));
            }}>
            <option value="">Yok</option>
            {packOptions.map((p) => <option key={p.kod} value={p.tur}>{p.tur}{meta.me.canSeeCost && p.birim ? ` · ${fmtMoney(p.birim)}` : ''}</option>)}
          </select>
        </label>
        {meta.me.canSeeCost && (
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Ambalaj birim maliyeti</span>
            <input className={`${field} font-mono`} inputMode="decimal" disabled={!editable} value={packCost} onChange={(e) => setPackCost(e.target.value)} />
          </label>
        )}
      </div>
      <dl className="mt-3 grid grid-cols-2 gap-x-3 gap-y-1.5 text-[12.5px]">
        <dt className="text-canvas-muted">Liste toplamı</dt>
        <dd className="text-right font-mono tabular-nums">{fmtMoney(c?.listeToplami)}{c && c.eksikFiyat > 0 ? ` (${c.eksikFiyat} fiyatsız)` : ''}</dd>
        <dt className="text-canvas-muted">Set fiyatı</dt>
        <dd className="text-right font-mono tabular-nums">{fmtMoney(c?.setFiyati)}</dd>
        <dt className="text-canvas-muted">İndirim</dt>
        <dd className="text-right font-mono tabular-nums">{fmtPct(c?.indirim ?? null)}</dd>
        {meta.me.canSeeCost && (
          <>
            <dt className="text-canvas-muted">KDV hariç gelir</dt>
            <dd className="text-right font-mono tabular-nums">{fmtMoney(c?.netGelir)}</dd>
            <dt className="text-canvas-muted">Bileşen maliyeti</dt>
            <dd className="text-right font-mono tabular-nums">{c?.maliyetToplami === null ? 'bilinmiyor' : fmtMoney(c?.maliyetToplami)}</dd>
            <dt className="font-bold">Marj</dt>
            <dd className="text-right"><MarginCell marj={c?.marj} oran={c?.marjOrani} floor={meta.settings.marginMinPct} /></dd>
          </>
        )}
      </dl>
      {calc.isFetching && <Loader2 aria-hidden className="mt-1 h-3.5 w-3.5 animate-spin text-canvas-muted" />}
      {c?.marjMesaj && meta.me.canSeeCost && <div className="mt-2"><Note tone="warn">{c.marjMesaj}</Note></div>}
      {c?.marjUyari && <div className="mt-2"><Note tone="warn">Marj alt sınırın (%{meta.settings.marginMinPct}) altında; onaycıya işaretli gider.</Note></div>}
      <p className="mt-2 text-[11px] leading-snug text-canvas-muted">
        KDV, set fiyatı bileşenlerin {c?.kdvYontemi === 'adet' ? 'adet' : 'liste fiyatı'} payına göre dağıtılıp her kalemin Logo KDV oranıyla ayrıştırılır
        {c && c.kdvBilinmeyen > 0 ? ` (${c.kdvBilinmeyen} kalemde oran bilinmiyor, 0 alındı)` : ''}. Birim maliyet: {meta.costSourceLabel}. Vergisel ayrıntı mali işlere doğrulatılmalı.
      </p>
      {editable && (
        <div className="mt-2 flex justify-end">
          <button type="button" className={btnPrimary} disabled={save.isPending} onClick={() => save.mutate()}>
            <Save aria-hidden className="h-4 w-4" /> Fiyatı kaydet
          </button>
        </div>
      )}
    </Panel>
  );
}

/* ------------------------------------------------------------------ ayrıntılar ve metinler */

function DetailsPanel({ s, canWrite, seasons, onSaved }: { s: SetRow; canWrite: boolean; seasons: { id: string; ad: string; sonraki: string | null }[]; onSaved: (o: SetRow) => void }) {
  const [sezon, setSezon] = useState(s.sezonId ?? '');
  const [kanal, setKanal] = useState((s.kanal ?? []).join(', '));
  const [hedef, setHedef] = useState(s.hedefAdet === null ? '' : String(s.hedefAdet));
  const [notlar, setNotlar] = useState(s.notlar ?? '');
  const save = useMutation({
    mutationFn: () => setsApi.update(s.id, { sezonId: sezon || null, kanal: kanal.split(',').map((x) => x.trim()).filter(Boolean), hedefAdet: parseNum(hedef), notlar }),
    onSuccess: onSaved,
    onError: (e) => toast.error(errText(e, 'Kaydedilemedi.') ?? ''),
  });
  return (
    <Panel>
      <h2 className="mb-2 text-[15px] font-extrabold">Sezon, kanal ve hedef</h2>
      <div className="grid grid-cols-2 gap-2">
        <label className="col-span-2 flex flex-col gap-1 sm:col-span-1">
          <span className={labelCls}>Özel gün</span>
          <select className={field} disabled={!canWrite} value={sezon} onChange={(e) => setSezon(e.target.value)}>
            <option value="">—</option>
            {seasons.map((x) => <option key={x.id} value={x.id}>{x.ad}{x.sonraki ? ` · ${fmtDay(x.sonraki)}` : ''}</option>)}
          </select>
        </label>
        <label className="col-span-2 flex flex-col gap-1 sm:col-span-1">
          <span className={labelCls}>Hedef set adedi</span>
          <input className={`${field} font-mono`} inputMode="numeric" disabled={!canWrite} value={hedef} onChange={(e) => setHedef(e.target.value)} />
        </label>
        <label className="col-span-2 flex flex-col gap-1">
          <span className={labelCls}>Satış kanalları (virgülle)</span>
          <input className={field} disabled={!canWrite} value={kanal} placeholder="ör. B2C Toplama Set, Toptan & Eticaret" onChange={(e) => setKanal(e.target.value)} />
        </label>
        <label className="col-span-2 flex flex-col gap-1">
          <span className={labelCls}>Not</span>
          <textarea className={`${field} min-h-[72px]`} disabled={!canWrite} value={notlar} onChange={(e) => setNotlar(e.target.value)} />
        </label>
      </div>
      {s.gerekce && <p className="mt-2 text-[12px] leading-snug text-canvas-muted"><strong className="text-canvas-ink">Gerekçe:</strong> {s.gerekce}</p>}
      {canWrite && (
        <div className="mt-2 flex justify-end">
          <button type="button" className={btnPrimary} disabled={save.isPending} onClick={() => save.mutate()}><Save aria-hidden className="h-4 w-4" /> Kaydet</button>
        </div>
      )}
    </Panel>
  );
}

function TextsPanel({ s, canWrite, onSaved }: { s: SetRow; canWrite: boolean; onSaved: (o: SetRow) => void }) {
  const [tanitim, setTanitim] = useState(s.tanitim ?? '');
  const [brief, setBrief] = useState(s.brief ?? '');
  useEffect(() => { setTanitim(s.tanitim ?? ''); setBrief(s.brief ?? ''); }, [s.tanitim, s.brief]);
  const draft = useMutation({
    mutationFn: (kind: 'tanitim' | 'brief') => setsApi.text(s.id, kind),
    onSuccess: (r, kind) => { if (kind === 'tanitim') setTanitim(r.text); else setBrief(r.text); toast.success('ZEKİ AI taslağı hazır; düzenleyip kaydedin.'); },
    onError: (e) => toast.error(errText(e, 'Taslak yazılamadı.') ?? ''),
  });
  const save = useMutation({
    mutationFn: () => setsApi.update(s.id, { tanitim, brief }),
    onSuccess: onSaved,
    onError: (e) => toast.error(errText(e, 'Kaydedilemedi.') ?? ''),
  });
  const box = (label: string, value: string, set: (v: string) => void, kind: 'tanitim' | 'brief', help: string) => (
    <label className="flex flex-col gap-1">
      <span className="flex items-center justify-between gap-2">
        <span className={labelCls}>{label}</span>
        {canWrite && (
          <button type="button" className={btnGhost} disabled={draft.isPending} onClick={() => draft.mutate(kind)}>
            {draft.isPending && draft.variables === kind ? <Loader2 aria-hidden className="h-4 w-4 animate-spin" /> : <Sparkles aria-hidden className="h-4 w-4" />}
            ZEKİ AI taslağı
          </button>
        )}
      </span>
      <textarea className={`${field} min-h-[120px]`} disabled={!canWrite} value={value} onChange={(e) => set(e.target.value)} />
      <span className="text-[11px] text-canvas-muted">{help}</span>
    </label>
  );
  return (
    <Panel>
      <h2 className="mb-2 text-[15px] font-extrabold">Tanıtım ve sunum</h2>
      <div className="flex flex-col gap-3">
        {box('E-ticaret açıklaması', tanitim, setTanitim, 'tanitim', 'SEO önerisi olarak kalır; siteye gönderilmez.')}
        {box('Ambalaj ve sunum brief\'i', brief, setBrief, 'brief', 'Tasarım ve üretim ekibine.')}
      </div>
      {canWrite && (
        <div className="mt-2 flex justify-end">
          <button type="button" className={btnPrimary} disabled={save.isPending} onClick={() => save.mutate()}><Save aria-hidden className="h-4 w-4" /> Metinleri kaydet</button>
        </div>
      )}
    </Panel>
  );
}

/* ------------------------------------------------------------------ açılacak kart ve eşleme */

function CardPanel({ s, canWrite, canExport, onSaved }: { s: SetRow; canWrite: boolean; canExport: boolean; onSaved: (o: SetRow) => void }) {
  const todo = useQuery({ queryKey: ['sets', 'card', s.id, s.durum], queryFn: () => setsApi.cardTodo(s.id) });
  const [code, setCode] = useState('');
  const link = useMutation({
    mutationFn: () => setsApi.link(s.id, code.trim()),
    onSuccess: onSaved,
    onError: (e) => toast.error(errText(e, 'Eşlenemedi.') ?? ''),
  });
  const t = todo.data;
  return (
    <Panel>
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-[15px] font-extrabold">CRM ve Logo'da açılacak kart</h2>
        {canExport && (
          <div className="flex gap-2">
            <a className={btnGhost} href={setsApi.cardUrl(s.id, 'csv')} download><Download aria-hidden className="h-4 w-4" /> CSV</a>
            <a className={btnGhost} href={setsApi.cardUrl(s.id, 'pdf')} download><Download aria-hidden className="h-4 w-4" /> PDF</a>
          </div>
        )}
      </div>
      {todo.error && <Note tone="err">{errText(todo.error, 'Kart listesi açılamadı.')}</Note>}
      {t && (
        <div className="grid gap-3 lg:grid-cols-2">
          <dl className="grid grid-cols-[140px_1fr] gap-x-3 gap-y-1 text-[12.5px]">
            <dt className="text-canvas-muted">Set tipi</dt><dd>{t.setTipi}</dd>
            <dt className="text-canvas-muted">Satış kanalı</dt><dd>{t.satisKanallari.join(', ') || '—'}</dd>
            <dt className="text-canvas-muted">Fiyat (KDV dahil)</dt><dd className="font-mono">{fmtMoney(t.onerilenFiyat)}</dd>
            <dt className="text-canvas-muted">Hedef adet</dt><dd className="font-mono">{fmtInt(t.hedefAdet)}</dd>
            <dt className="text-canvas-muted">Ambalaj</dt><dd>{t.ambalaj ?? '—'}</dd>
            <dt className="text-canvas-muted">Barkod</dt><dd>{t.barkod}</dd>
          </dl>
          <ol className="list-decimal space-y-1 pl-5 text-[12.5px] leading-snug">
            {t.adimlar.map((a, i) => <li key={i}>{a}</li>)}
          </ol>
        </div>
      )}
      {s.durum === 'kart-bekliyor' && canWrite && (
        <div className="mt-3 flex flex-wrap items-end gap-2">
          <label className="flex min-w-[200px] flex-1 flex-col gap-1">
            <span className={labelCls}>CRM'de açılan set kartının stok kodu</span>
            <input className={`${field} font-mono`} value={code} onChange={(e) => setCode(e.target.value)} />
          </label>
          <button type="button" className={btnPrimary} disabled={!code.trim() || link.isPending} onClick={() => link.mutate()}>
            <Link2 aria-hidden className="h-4 w-4" /> Eşle
          </button>
          <p className="w-full text-[11px] text-canvas-muted">Kod CRM'de (etkin, «Set» türünde) doğrulanır. Bileşenleri birebir tutan kart açılırsa gece kendiliğinden eşlenir.</p>
        </div>
      )}
    </Panel>
  );
}

function CrmPanel({ s }: { s: SetRow }) {
  const c = s.crm as { setTipi?: string; ozellik?: string; kanal?: string; setAdet?: number; projeSetAdi?: string; projeSetBarkodu?: string;
    setIslemi?: { tarih?: string; islemAdet?: number } };
  return (
    <Panel>
      <h2 className="mb-2 text-[15px] font-extrabold">CRM set kartı</h2>
      <dl className="grid grid-cols-[160px_1fr] gap-x-3 gap-y-1 text-[12.5px]">
        <dt className="text-canvas-muted">Set tipi</dt><dd>{c.setTipi ?? '—'}</dd>
        <dt className="text-canvas-muted">Satış kanalı</dt><dd>{c.kanal ?? '—'}</dd>
        <dt className="text-canvas-muted">Set özellikleri</dt><dd>{c.ozellik ?? '—'}</dd>
        <dt className="text-canvas-muted">Proje set adı / barkod</dt><dd>{c.projeSetAdi ?? '—'} · {c.projeSetBarkodu ?? '—'}</dd>
        <dt className="text-canvas-muted">Son set yapma</dt><dd>{c.setIslemi?.tarih ? `${fmtDay(c.setIslemi.tarih)} · ${fmtInt(c.setIslemi.islemAdet ?? null)} adet` : '—'}</dd>
      </dl>
      <p className="mt-2 text-[11px] text-canvas-muted">CRM'deki değerler burada yalnız okunur; değişiklik CRM'de yapılır.</p>
    </Panel>
  );
}
