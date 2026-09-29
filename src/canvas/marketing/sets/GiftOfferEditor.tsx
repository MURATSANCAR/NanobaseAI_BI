import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Download, Loader2, Plus, RefreshCw, Save, Sparkles, Trash2 } from 'lucide-react';
import { ENGINE_ENABLED } from '../../engine';
import { Note, btnGhost, btnPrimary, errText, field, label as labelCls } from '../../admin/ui';
import { Panel } from '../../editorial/kit';
import { fmtDay, fmtInt, fmtMoney, fmtPct, parseNum } from '../../budget/api';
import { AskSheet } from '../../budget/parts';
import { OFFER_TONE, pctToRatio, setsApi, type Offer } from './api';
import { BudgetGap, MarginCell, SetsFrame, Tone } from './parts';
import SqlInfo from '../../components/SqlInfo';

/** Kurumsal hediye teklifi: seçenekler (kod), kademe indirimi, mektup (Zeki AI taslağı), onay (gönderen onaylayamaz), PDF.
 *  Kurumsal satış fırsatı (M32) ile bağ: fırsat numarası teklife yazılır; kalemler M32 teklif satırı biçiminde de alınabilir. */

type Ask = null | 'submit' | 'withdraw' | 'approve' | 'reject';

export default function GiftOfferEditor() {
  const { id = '' } = useParams();
  const qc = useQueryClient();
  const meta = useQuery({ queryKey: ['sets', 'meta'], queryFn: setsApi.meta, enabled: ENGINE_ENABLED, staleTime: 60_000 });
  const offer = useQuery({ queryKey: ['sets', 'offer', id], queryFn: () => setsApi.offer(id), enabled: ENGINE_ENABLED && !!id });
  const [ask, setAsk] = useState<Ask>(null);
  const me = meta.data?.me;
  const o = offer.data;

  const put = (out: Offer, msg: string) => {
    qc.setQueryData(['sets', 'offer', id], out);
    qc.invalidateQueries({ queryKey: ['sets', 'offers'] });
    toast.success(msg);
  };
  const act = useMutation({
    mutationFn: ({ kind, text }: { kind: Exclude<Ask, null>; text: string }) => {
      switch (kind) {
        case 'submit': return setsApi.submitOffer(id);
        case 'withdraw': return setsApi.withdrawOffer(id);
        case 'approve': return setsApi.approveOffer(id, text || undefined);
        case 'reject': return setsApi.rejectOffer(id, text);
      }
    },
    onSuccess: (out, { kind }) => {
      setAsk(null);
      put(out, { submit: 'Teklif onaya gönderildi.', withdraw: 'Teklif taslağa alındı.', approve: 'Teklif onaylandı; PDF gönderilebilir.', reject: 'Teklif geri gönderildi.' }[kind]);
    },
    onError: (e) => toast.error(errText(e, 'İşlem yapılamadı.') ?? ''),
  });
  const patch = useMutation({
    mutationFn: (b: Record<string, unknown>) => setsApi.updateOffer(id, b),
    onSuccess: (out) => put(out, 'Teklif güncellendi.'),
    onError: (e) => toast.error(errText(e, 'Kaydedilemedi.') ?? ''),
  });

  const draft = o?.durum === 'taslak' && !!me?.canWrite;
  const mine = (o?.gonderen ?? '').toLowerCase() === (me?.username ?? '').toLowerCase();

  return (
    <SetsFrame
      title={o?.firmaAdi ?? 'Kurumsal teklif'}
      lead={o ? `Firmaya sunulacak hediye kitap teklifi: kişi sayısı ve bütçeye uyan seçenekler, teklif mektubu ve onay. ${fmtInt(o.adet)} kişi · kişi başı bütçe ${fmtMoney(o.kisiBasiButce)}${o.sezon ? ` · ${o.sezon}` : ''}` : ''}
      back={{ to: '/pazarlama/set-hediye?sekme=teklifler', label: 'Kurumsal teklifler' }}
      source="CRM + Logo"
      presence={o?.durumAdi ?? ''}
    >
      {!ENGINE_ENABLED && <Note tone="warn">Veri bağlantısı kurulu değil; bu ekran şu an veri gösteremez. Sistem yöneticinize haber verin.</Note>}
      {offer.error && <Note tone="err">{errText(offer.error, 'Teklif açılamadı.')}</Note>}
      {o && meta.data && (
        <>
          <div className="flex flex-wrap items-center gap-2 px-1">
            <Tone tone={OFFER_TONE[o.durum]}>{o.durumAdi}</Tone>
            <span className="text-[12px] font-semibold text-canvas-muted">
              {o.hazirlayan} hazırladı · geçerlilik {fmtDay(o.gecerlilik)}{o.onaylayan && o.durum !== 'taslak' ? ` · ${o.onaylayan} onayladı` : ''}
            </span>
            <div className="ml-auto flex flex-wrap gap-2">
              <a className={btnGhost} href={setsApi.offerPdfUrl(o.id)} download><Download aria-hidden className="h-4 w-4" /> PDF{o.durum === 'taslak' || o.durum === 'onayda' ? ' (taslak)' : ''}</a>
              {draft && <button type="button" className={btnPrimary} onClick={() => setAsk('submit')}>Onaya gönder</button>}
              {o.durum === 'onayda' && me?.canWrite && <button type="button" className={btnGhost} onClick={() => setAsk('withdraw')}>Onaydan çek</button>}
              {o.durum === 'onayda' && me?.canApproveOffer && !mine && (
                <>
                  <button type="button" className={btnGhost} onClick={() => setAsk('reject')}>Geri gönder</button>
                  <button type="button" className={btnPrimary} onClick={() => setAsk('approve')}>Onayla</button>
                </>
              )}
              {o.durum === 'onaylandi' && me?.canWrite && <button type="button" className={btnGhost} disabled={patch.isPending} onClick={() => patch.mutate({ durum: 'gonderildi' })}>Gönderildi</button>}
              {o.durum === 'gonderildi' && me?.canWrite && (
                <>
                  <button type="button" className={btnGhost} disabled={patch.isPending} onClick={() => patch.mutate({ durum: 'kaybedildi' })}>Kaybedildi</button>
                  <button type="button" className={btnPrimary} disabled={patch.isPending} onClick={() => patch.mutate({ durum: 'kazanildi' })}>Kazanıldı</button>
                </>
              )}
            </div>
          </div>
          {o.durum === 'taslak' && o.kararNotu && <Note tone="warn">Geri gönderildi ({o.onaylayan}): {o.kararNotu}</Note>}
          {o.durum === 'onayda' && me?.canApproveOffer && mine && <Note tone="info">Bu teklifi siz onaya gönderdiniz; onayı başka bir yetkili verir.</Note>}

          <div className="grid gap-3 xl:grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)]">
            <Terms o={o} editable={draft} busy={patch.isPending} onSave={(b) => patch.mutate(b)} />
            <Options o={o} editable={draft} canSeeCost={!!me?.canSeeCost} busy={patch.isPending} onSave={(b) => patch.mutate(b)} />
          </div>
          <Letter o={o} editable={draft} onSaved={(out) => put(out, 'Mektup kaydedildi.')} />
        </>
      )}
      <AskSheet
        open={ask !== null}
        busy={act.isPending}
        title={{ submit: 'Onaya gönder', withdraw: 'Onaydan çek', approve: 'Teklifi onayla', reject: 'Geri gönder', '': '' }[ask ?? '']}
        message={
          ask === 'submit' ? 'Teklif onaycıya düşer; onayı sizden başka bir yetkili verir. Onayda iken seçenek ve mektup değişmez.'
            : ask === 'withdraw' ? 'Teklif yeniden taslak olur.'
            : ask === 'approve' ? 'Teklif «gönderilebilir» olur; PDF taslak ibaresi olmadan iner. Kuruma gönderimi satış yapar.'
            : 'Teklif gerekçenizle taslağa döner.'
        }
        confirm={{ submit: 'Onaya gönder', withdraw: 'Taslağa al', approve: 'Onayla', reject: 'Geri gönder', '': '' }[ask ?? '']}
        input={ask === 'reject' ? 'Gerekçe' : ask === 'approve' ? 'Not (isteğe bağlı)' : undefined}
        required={ask === 'reject'}
        onClose={() => setAsk(null)}
        onConfirm={(text) => ask && act.mutate({ kind: ask, text })}
      />
    </SetsFrame>
  );
}

function Terms({ o, editable, busy, onSave }: { o: Offer; editable: boolean; busy: boolean; onSave: (b: Record<string, unknown>) => void }) {
  const [adet, setAdet] = useState(String(o.adet));
  const [butce, setButce] = useState(String(o.kisiBasiButce).replace('.', ','));
  const [tiers, setTiers] = useState(o.kademeler.map((t) => ({ adet: String(t.adet), pct: String(t.indirim * 100).replace('.', ',') })));
  const [valid, setValid] = useState(o.gecerlilik ?? '');
  const [m32, setM32] = useState(o.m32FirsatId ?? '');
  useEffect(() => {
    setAdet(String(o.adet));
    setButce(String(o.kisiBasiButce).replace('.', ','));
    setTiers(o.kademeler.map((t) => ({ adet: String(t.adet), pct: String(t.indirim * 100).replace('.', ',') })));
  }, [o.adet, o.kisiBasiButce, o.kademeler]);
  const kademeler = tiers
    .map((t) => ({ adet: Number(t.adet), indirim: pctToRatio(t.pct) }))
    .filter((t): t is { adet: number; indirim: number } => Number.isFinite(t.adet) && t.adet >= 1 && t.indirim !== null);
  return (
    <Panel>
      <h2 className="mb-2 flex items-center gap-1 text-[15px] font-extrabold">Koşullar<SqlInfo k={o.kaynaklar} alan="adet" label="Kişi sayısı, bütçe ve kademeler" /></h2>
      <div className="grid grid-cols-2 gap-2">
        <label className="flex flex-col gap-1">
          <span className={labelCls}>Kişi sayısı</span>
          <input className={`${field} font-mono`} inputMode="numeric" disabled={!editable} value={adet} onChange={(e) => setAdet(e.target.value)} />
        </label>
        <label className="flex flex-col gap-1">
          <span className={labelCls}>Kişi başı bütçe</span>
          <input className={`${field} font-mono`} inputMode="decimal" disabled={!editable} value={butce} onChange={(e) => setButce(e.target.value)} />
        </label>
      </div>
      <div className="mt-3">
        <span className={labelCls}>Adet indirimleri (bu adet ve üstünde → indirim %)</span>
        <ul className="mt-1 flex flex-col gap-1">
          {tiers.map((t, i) => (
            <li key={i} className="flex items-center gap-2">
              <input aria-label="Adet eşiği" className={`${field} w-24 font-mono`} inputMode="numeric" disabled={!editable} value={t.adet}
                onChange={(e) => setTiers((x) => x.map((y, n) => (n === i ? { ...y, adet: e.target.value } : y)))} />
              <span className="text-[12px] text-canvas-muted">ve üstü</span>
              <input aria-label="İndirim yüzdesi" className={`${field} w-20 font-mono`} inputMode="decimal" disabled={!editable} value={t.pct}
                onChange={(e) => setTiers((x) => x.map((y, n) => (n === i ? { ...y, pct: e.target.value } : y)))} />
              <span className="text-[12px] text-canvas-muted">%</span>
              {editable && (
                <button type="button" aria-label="Kademeyi sil" className={btnGhost} onClick={() => setTiers((x) => x.filter((_, n) => n !== i))}>
                  <Trash2 aria-hidden className="h-4 w-4" />
                </button>
              )}
            </li>
          ))}
          {!tiers.length && <li className="text-[12px] text-canvas-muted">Kademe yok (liste fiyatı).</li>}
        </ul>
        {editable && (
          <button type="button" className={`${btnGhost} mt-1`} onClick={() => setTiers((x) => [...x, { adet: '', pct: '' }])}>
            <Plus aria-hidden className="h-4 w-4" /> Kademe ekle
          </button>
        )}
      </div>
      {editable && (
        <button type="button" className={`${btnPrimary} mt-3 w-full`} disabled={busy}
          onClick={() => onSave({ adet: Number(adet), kisiBasiButce: parseNum(butce), kademeler, yenidenHesapla: true })}>
          <RefreshCw aria-hidden className="h-4 w-4" /> Seçenekleri yeniden hesapla
        </button>
      )}
      <div className="mt-3 grid grid-cols-2 gap-2">
        <label className="flex flex-col gap-1">
          <span className={labelCls}>Geçerlilik</span>
          <input type="date" className={field} disabled={!editable} value={valid} onChange={(e) => setValid(e.target.value)} />
        </label>
        <label className="flex flex-col gap-1">
          <span className={labelCls}>Kurumsal satış fırsatı</span>
          <input className={`${field} font-mono`} disabled={!editable} value={m32} placeholder="CRM fırsat numarası (varsa)" onChange={(e) => setM32(e.target.value)} />
        </label>
      </div>
      {editable && (
        <button type="button" className={`${btnGhost} mt-2 w-full`} disabled={busy} onClick={() => onSave({ gecerlilik: valid || null, m32FirsatId: m32 || null })}>
          <Save aria-hidden className="h-4 w-4" /> Kaydet
        </button>
      )}
    </Panel>
  );
}

function Options({ o, editable, canSeeCost, busy, onSave }: { o: Offer; editable: boolean; canSeeCost: boolean; busy: boolean; onSave: (b: Record<string, unknown>) => void }) {
  const [sel, setSel] = useState<number[]>(o.secili);
  useEffect(() => setSel(o.secili), [o.secili]);
  const dirty = JSON.stringify([...sel].sort()) !== JSON.stringify([...o.secili].sort());
  return (
    <Panel>
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <h2 className="flex items-center gap-1 text-[15px] font-extrabold">Seçenekler<SqlInfo k={o.kaynaklar} alan="secenekler" label="Seçenek fiyatları, indirim ve marj" /></h2>
        {editable && dirty && <button type="button" className={btnPrimary} disabled={busy || !sel.length} onClick={() => onSave({ secili: sel })}><Save aria-hidden className="h-4 w-4" /> Seçimi kaydet</button>}
      </div>
      {!o.secenekler.length && <Note tone="warn">Bu bütçeye ve kişi sayısına uyan, stoğu yeten seçenek bulunamadı. Bütçeyi ya da kademeyi değiştirip yeniden hesaplayın.</Note>}
      <ul className="flex flex-col gap-2">
        {o.secenekler.map((s) => {
          const on = sel.includes(s.no);
          return (
            <li key={s.no}>
              <label className={`flex cursor-pointer gap-3 rounded-2xl border p-3 transition-colors duration-150 ${on ? 'border-canvas-violet bg-canvas-violet/5' : 'border-slate-100 bg-white/80'}`}>
                <input type="checkbox" className="mt-1 h-5 w-5 shrink-0 accent-[#7C5CFF]" disabled={!editable} checked={on}
                  onChange={() => setSel((x) => (on ? x.filter((n) => n !== s.no) : [...x, s.no]))} />
                <span className="min-w-0 flex-1">
                  <span className="flex flex-wrap items-baseline justify-between gap-2">
                    <span className="font-bold">{s.no}. {s.ad}</span>
                    <span className="font-mono text-[13px] font-bold tabular-nums">{fmtMoney(s.birimNet)} <span className="text-[11px] font-normal text-canvas-muted">/ kişi</span></span>
                  </span>
                  <span className="mt-0.5 block text-[12px] text-canvas-muted">
                    {s.kalemler.map((k) => (k.ad ?? k.stok) + (k.yazar ? ` (${k.yazar})` : '')).join(' · ')}
                  </span>
                  <span className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11.5px]">
                    <span className="font-mono tabular-nums">liste {fmtMoney(s.birimListe)} · indirim {fmtPct(s.indirim)} · toplam {fmtMoney(s.toplamNet)}</span>
                    <BudgetGap gap={s.butceFarki} />
                    {canSeeCost && <MarginCell marj={s.marj} oran={s.marjOrani} />}
                  </span>
                </span>
              </label>
            </li>
          );
        })}
      </ul>
    </Panel>
  );
}

function Letter({ o, editable, onSaved }: { o: Offer; editable: boolean; onSaved: (o: Offer) => void }) {
  const [text, setText] = useState(o.mektup ?? '');
  useEffect(() => setText(o.mektup ?? ''), [o.mektup]);
  const draft = useMutation({
    mutationFn: () => setsApi.letter(o.id),
    onSuccess: (r) => { setText(r.text); toast.success(`Zeki AI mektup taslağı hazır${r.dusenSayisi ? ` (denetimde ${r.dusenSayisi} cümle çıkarıldı)` : ''}; düzenleyip kaydedin.`); },
    onError: (e) => toast.error(errText(e, 'Mektup yazılamadı.') ?? ''),
  });
  const save = useMutation({
    mutationFn: () => setsApi.updateOffer(o.id, { mektup: text }),
    onSuccess: onSaved,
    onError: (e) => toast.error(errText(e, 'Kaydedilemedi.') ?? ''),
  });
  return (
    <Panel>
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-[15px] font-extrabold">Teklif mektubu</h2>
        {editable && (
          <button type="button" className={btnGhost} disabled={draft.isPending} onClick={() => draft.mutate()}>
            {draft.isPending ? <Loader2 aria-hidden className="h-4 w-4 animate-spin" /> : <Sparkles aria-hidden className="h-4 w-4" />}
            Zeki AI ile taslak yaz
          </button>
        )}
      </div>
      <textarea className={`${field} min-h-[180px]`} disabled={!editable} value={text} onChange={(e) => setText(e.target.value)} />
      <p className="mt-1 text-[11px] text-canvas-muted">Mektupta rakam yer almaz; fiyat ve adet belgedeki tablodan gelir. Kişi bilgisi yazılmaz, yalnız firma adı.</p>
      {editable && (
        <div className="mt-2 flex justify-end">
          <button type="button" className={btnPrimary} disabled={save.isPending || text === (o.mektup ?? '')} onClick={() => save.mutate()}>
            <Save aria-hidden className="h-4 w-4" /> Mektubu kaydet
          </button>
        </div>
      )}
    </Panel>
  );
}
