import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Loader2, Sparkles } from 'lucide-react';
import { Note, Pill, btnGhost, btnPrimary, errText, field, label as labelCls } from '../admin/ui';
import { Panel } from '../editorial/kit';
import { fmtDay, fmtInt, fmtLeft, fmtMoney, fmtPct, parseNum, tendersApi, type TenderDetail, type TenderMeta } from './api';
import { AskSheet, Fact } from './parts';
import SqlInfo from '../components/SqlInfo';

/** Karar: tek sayfa karar özeti (rakamlar SQL'den ve kayıtlardan; Zeki AI yalnız bu rakamlarla metin yazar), başvuru
 *  kararı önerisi ve iki göz onayı. Sonuç: teklif verildi, kazanıldı/kaybedildi/iptal, kazanan firma ve fiyat. */

type Ask = null | 'approve' | 'reject' | 'withdraw';

export default function TenderDecision({ d, meta, view }: { d: TenderDetail; meta: TenderMeta; view: 'karar' | 'sonuc' }) {
  return view === 'karar' ? <DecisionView d={d} meta={meta} /> : <ResultView d={d} meta={meta} />;
}

function DecisionView({ d, meta }: { d: TenderDetail; meta: TenderMeta }) {
  const qc = useQueryClient();
  const [karar, setKarar] = useState<'basvur' | 'basvurma'>('basvur');
  const [gerekce, setGerekce] = useState('');
  const [ask, setAsk] = useState<Ask>(null);
  const f = d.kararOzeti;
  const pending = d.kararlar.find((k) => k.durum === 'onayda') ?? null;
  const me = meta.me;
  const mine = !!pending && pending.oneren.toLowerCase() === me.username.toLowerCase();
  const invalidate = () => qc.invalidateQueries({ queryKey: ['tenders'] });

  const brief = useMutation({
    mutationFn: () => tendersApi.brief(d.id),
    onSuccess: (r) => { invalidate(); if (r.not) toast.message(r.not); },
    onError: (e) => toast.error(errText(e, 'Özet yazılamadı.') ?? ''),
  });
  const submit = useMutation({
    mutationFn: () => tendersApi.submit(d.id, { karar, gerekce: gerekce.trim() || undefined }),
    onSuccess: () => { invalidate(); setGerekce(''); toast.success('Karar onaya gönderildi.'); },
    onError: (e) => toast.error(errText(e, 'Gönderilemedi.') ?? ''),
  });
  const act = useMutation({
    mutationFn: ({ kind, text }: { kind: Exclude<Ask, null>; text: string }) =>
      kind === 'approve' ? tendersApi.approve(d.id, text || undefined) : kind === 'reject' ? tendersApi.reject(d.id, text) : tendersApi.withdraw(d.id),
    onSuccess: (_, { kind }) => {
      setAsk(null);
      invalidate();
      toast.success({ approve: 'Karar onaylandı.', reject: 'Karar gerekçesiyle geri gönderildi.', withdraw: 'Karar geri çekildi.' }[kind]);
    },
    onError: (e) => toast.error(errText(e, 'İşlem yapılamadı.') ?? ''),
  });

  const hk = f.gecmis?.kurumTuru;
  const hc = f.gecmis?.kurum;
  const canSubmit = me.canEdit && !pending && ['yeni', 'inceleniyor'].includes(d.durum);
  return (
    <>
      <Panel>
        <div className="flex flex-wrap items-end justify-between gap-2">
          <div className="min-w-0">
            <h2 className="flex items-center gap-1 text-[16px] font-extrabold tracking-tight">Karar özeti<SqlInfo k={d.kaynaklar} alan="kararOzeti" label="Karar özeti rakamları" /></h2>
            <p className="text-[12px] text-canvas-muted">Rakamlar Logo, CRM ve portal kayıtlarından. Başvuru kararı ve teklif fiyatı insanındır; portal kuruma teklif göndermez.</p>
          </div>
          {me.canEdit && (
            <button type="button" className={btnGhost} disabled={brief.isPending} onClick={() => brief.mutate()}>
              {brief.isPending ? <Loader2 aria-hidden className="h-4 w-4 animate-spin" /> : <Sparkles aria-hidden className="h-4 w-4" />}
              Zeki AI özeti yaz
            </button>
          )}
        </div>
        {d.kararMetni && <p className="mt-2 whitespace-pre-wrap rounded-xl bg-canvas-violet/5 px-3 py-2 text-[13px] leading-relaxed">{d.kararMetni}</p>}
        <div className="mt-3 grid grid-cols-2 gap-2 lg:grid-cols-4">
          <Fact label="Yaklaşık tutar" value={fmtMoney(f.yaklasikTutar)} />
          <Fact label="Uygunluk puanı" value={f.uygunlukPuani != null ? `${Math.round(f.uygunlukPuani)} / 100` : '—'} />
          <Fact label="Eşleşen kalem" value={`${fmtInt(f.eslesen)} / ${fmtInt(f.kalem)}`} help={`Katalogda yok: ${fmtInt(f.katalogdaYok)}`} />
          <Fact label="Stok yetersiz" value={fmtInt(f.stokYetersiz)} help="Eşleşen kalemlerde istenen adetten az" />
          <Fact label="Teklif ara toplamı" value={fmtMoney(f.teklifAraToplam)} help={`Genel toplam ${fmtMoney(f.teklifGenelToplam)}`} />
          <Fact label="Fiyat oranı" value={fmtPct(f.fiyatOrani)} help={`Liste toplamı ${fmtMoney(f.listeToplami)}`} />
          <Fact label="Tahmini marj" value={fmtPct(f.marj)} help={f.maliyetNotu ?? `${f.maliyetKapsam} kalemin maliyetiyle`} />
          <Fact label="Son teklif" value={fmtLeft(f.kalanGun)} help={f.teminatTutari != null ? `Teminat ${fmtMoney(f.teminatTutari)}` : undefined} />
        </div>
        <div className="mt-3 grid grid-cols-1 gap-2 lg:grid-cols-2">
          <Fact label="Bu kurumla geçmiş" value={hc?.sonuc ? `${hc.kazanilan} kazanıldı / ${hc.sonuc} sonuç` : 'Kayıt yok'} help={hc?.kazananOranOrtanca != null ? `Kazanan fiyat liste fiyatının ${fmtPct(hc.kazananOranOrtanca)}'i (ortanca)` : undefined} />
          <Fact label={`${d.kurumTuruAdi} ihalelerinde`} value={hk?.sonuc ? `${hk.kazanilan} kazanıldı / ${hk.sonuc} sonuç` : 'Kayıt yok'} help={hk?.kazananOranOrtanca != null ? `Kazanan fiyat liste fiyatının ${fmtPct(hk.kazananOranOrtanca)}'i (ortanca)` : undefined} />
        </div>
        {(f.riskler.length > 0 || f.eksikBelgeler.length > 0) && (
          <div className="mt-3 flex flex-col gap-1.5">
            {f.riskler.map((r) => <Note key={r} tone="warn">{r}</Note>)}
            {f.eksikBelgeler.length > 0 && <Note tone="warn">Eksik belgeler: {f.eksikBelgeler.join('; ')}</Note>}
          </div>
        )}
      </Panel>

      {pending && (
        <Panel>
          <div className="flex flex-wrap items-center gap-2">
            <Pill tone="warn">Onay bekliyor</Pill>
            <span className="text-[13px] font-extrabold">{pending.kararAdi}</span>
            {pending.teklifToplami != null && <span className="inline-flex items-center gap-0.5 font-mono text-[12.5px] tabular-nums">{fmtMoney(pending.teklifToplami)} (KDV hariç)<SqlInfo k={d.kaynaklar} alan="kararlar[]" label="Önerideki teklif toplamı" /></span>}
          </div>
          <div className="mt-1 text-[12px] text-canvas-muted">Öneren {pending.oneren} · {fmtDay(pending.oneriZamani)}</div>
          {pending.gerekce && <p className="mt-2 whitespace-pre-wrap break-words text-[12.5px]">{pending.gerekce}</p>}
          <div className="mt-3 flex flex-wrap gap-2">
            {me.canDecide && !mine && (
              <>
                <button type="button" className={btnPrimary} onClick={() => setAsk('approve')}>Onayla</button>
                <button type="button" className={btnGhost} onClick={() => setAsk('reject')}>Geri gönder</button>
              </>
            )}
            {mine && <button type="button" className={btnGhost} onClick={() => setAsk('withdraw')}>Geri çek</button>}
          </div>
          {mine && me.canDecide && <div className="mt-2"><Note tone="info">Kararı öneren onaylayamaz; başka bir yetkili onaylamalı.</Note></div>}
          {!me.canDecide && !mine && <div className="mt-2"><Note tone="info">Onay yetkisi rolünüzde yok.</Note></div>}
        </Panel>
      )}

      {canSubmit && (
        <Panel>
          <h2 className="text-[16px] font-extrabold tracking-tight">Karar öner</h2>
          <p className="text-[12px] text-canvas-muted">«Başvur» teklif tablosunun o anki toplamıyla onaya gider; onay teklif fiyatının da onayıdır. Onay bekleyen ya da eşleşmesi seçilmemiş kalem varsa önce onları sonuçlandırın.</p>
          <div className="mt-2 flex flex-wrap gap-2" role="radiogroup" aria-label="Karar">
            {(['basvur', 'basvurma'] as const).map((k) => (
              <button
                key={k}
                type="button"
                role="radio"
                aria-checked={karar === k}
                onClick={() => setKarar(k)}
                className={`inline-flex min-h-11 items-center rounded-xl px-4 text-[12.5px] font-extrabold transition-colors duration-150 sm:min-h-9 ${karar === k ? 'bg-canvas-violet text-white' : 'bg-slate-100 text-canvas-ink hover:bg-slate-200'}`}
              >
                {meta.kararlar[k]}
              </button>
            ))}
          </div>
          <label className="mt-3 flex flex-col gap-1">
            <span className={labelCls}>Gerekçe{karar === 'basvurma' ? ' *' : ''}</span>
            <textarea className={`${field} min-h-[80px]`} value={gerekce} onChange={(e) => setGerekce(e.target.value)} />
          </label>
          <div className="mt-2 flex justify-end">
            <button type="button" className={btnPrimary} disabled={submit.isPending || (karar === 'basvurma' && !gerekce.trim())} onClick={() => submit.mutate()}>
              {submit.isPending && <Loader2 aria-hidden className="h-4 w-4 animate-spin" />}
              Onaya gönder
            </button>
          </div>
        </Panel>
      )}

      {d.kararlar.length > 0 && (
        <Panel>
          <h2 className="flex items-center gap-1 text-[16px] font-extrabold tracking-tight">Karar geçmişi<SqlInfo k={d.kaynaklar} alan="kararlar[]" label="Karar geçmişi teklif toplamları" /></h2>
          <ul className="mt-2 flex flex-col gap-1.5">
            {d.kararlar.map((k) => (
              <li key={k.id} className="rounded-xl border border-slate-100 bg-white/80 px-3 py-2 text-[12.5px]">
                <div className="flex flex-wrap items-center gap-2">
                  <Pill tone={k.durum === 'onaylandi' ? 'ok' : k.durum === 'onayda' ? 'warn' : k.durum === 'reddedildi' ? 'err' : 'muted'}>
                    {{ onaylandi: 'Onaylandı', onayda: 'Onay bekliyor', reddedildi: 'Geri gönderildi', geri_cekildi: 'Geri çekildi' }[k.durum]}
                  </Pill>
                  <b>{k.kararAdi}</b>
                  {k.teklifToplami != null && <span className="font-mono tabular-nums">{fmtMoney(k.teklifToplami)}</span>}
                </div>
                <div className="mt-0.5 text-[11.5px] text-canvas-muted">
                  Öneren {k.oneren} ({fmtDay(k.oneriZamani)}){k.onaylayan ? ` · ${k.durum === 'reddedildi' ? 'geri gönderen' : 'onaylayan'} ${k.onaylayan} (${fmtDay(k.onayZamani)})` : ''}
                </div>
                {k.onayNotu && <div className="mt-0.5 break-words">{k.onayNotu}</div>}
              </li>
            ))}
          </ul>
        </Panel>
      )}

      <AskSheet
        open={!!ask}
        title={ask === 'approve' ? 'Kararı onayla' : ask === 'reject' ? 'Kararı geri gönder' : 'Kararı geri çek'}
        message={
          ask === 'approve'
            ? <>«{pending?.kararAdi}» kararı{pending?.teklifToplami != null ? <> ve {fmtMoney(pending.teklifToplami)} teklif toplamı</> : null} onaylanır.</>
            : ask === 'reject' ? 'Karar öneriyi yapana gerekçeyle döner.' : 'Karar önerisi geri çekilir; kalemler yeniden düzenlenebilir.'
        }
        confirm={ask === 'approve' ? 'Onayla' : ask === 'reject' ? 'Geri gönder' : 'Geri çek'}
        input={ask === 'withdraw' ? undefined : ask === 'reject' ? 'Gerekçe' : 'Not (isteğe bağlı)'}
        required={ask === 'reject'}
        busy={act.isPending}
        onClose={() => setAsk(null)}
        onConfirm={(text) => ask && act.mutate({ kind: ask, text })}
      />
    </>
  );
}

function ResultView({ d, meta }: { d: TenderDetail; meta: TenderMeta }) {
  const qc = useQueryClient();
  const last = d.kararlar.find((k) => k.durum === 'onaylandi' && k.karar === 'basvur');
  const [sonuc, setSonuc] = useState<string>(d.sonuc?.sonuc ?? 'kaybedildi');
  const [kazanan, setKazanan] = useState(d.sonuc?.kazanan ?? '');
  const [kazananFiyat, setKazananFiyat] = useState(d.sonuc?.kazananFiyat != null ? String(d.sonuc.kazananFiyat).replace('.', ',') : '');
  const [bizim, setBizim] = useState(d.sonuc?.bizimFiyat != null ? String(d.sonuc.bizimFiyat).replace('.', ',') : last?.teklifToplami != null ? String(last.teklifToplami).replace('.', ',') : '');
  const [neden, setNeden] = useState(d.sonuc?.neden ?? '');
  const [kaynak, setKaynak] = useState(d.sonuc?.kaynak ?? '');
  const invalidate = () => qc.invalidateQueries({ queryKey: ['tenders'] });
  const offered = useMutation({
    mutationFn: () => tendersApi.update(d.id, { durum: 'teklif_verildi' }),
    onSuccess: () => { invalidate(); toast.success('Teklif verildi olarak işaretlendi.'); },
    onError: (e) => toast.error(errText(e, 'Kaydedilemedi.') ?? ''),
  });
  const save = useMutation({
    mutationFn: () => tendersApi.result(d.id, {
      sonuc, kazanan: kazanan.trim() || undefined, kazananFiyat: parseNum(kazananFiyat), bizimFiyat: parseNum(bizim),
      neden: neden.trim() || undefined, kaynak: kaynak.trim() || undefined,
    }),
    onSuccess: () => { invalidate(); toast.success('Sonuç kaydedildi.'); },
    onError: (e) => toast.error(errText(e, 'Kaydedilemedi.') ?? ''),
  });
  const r = d.sonuc;
  const canResult = meta.me.canEdit && (['teklif_verildi', 'kazanildi', 'kaybedildi'].includes(d.durum) || sonuc === 'iptal');
  return (
    <>
      {d.durum === 'basvurulacak' && meta.me.canEdit && (
        <Panel>
          <h2 className="text-[16px] font-extrabold tracking-tight">Teklif verildi mi?</h2>
          <p className="text-[12px] text-canvas-muted">Teklif kuruma e-imzayla ya da elden verildikten sonra işaretleyin; portal teklif göndermez.</p>
          <div className="mt-2">
            <button type="button" className={btnPrimary} disabled={offered.isPending} onClick={() => offered.mutate()}>Teklif verildi</button>
          </div>
        </Panel>
      )}
      {r && (
        <Panel>
          <div className="flex flex-wrap items-center gap-2">
            <Pill tone={r.sonuc === 'kazanildi' ? 'ok' : r.sonuc === 'kaybedildi' ? 'err' : 'muted'}>{r.sonucAdi}</Pill>
            <span className="text-[12px] text-canvas-muted">{r.kaydeden} · {fmtDay(r.zaman)}</span>
          </div>
          <div className="mt-2 grid grid-cols-2 gap-2 lg:grid-cols-4">
            <Fact label="Kazanan" value={r.kazanan ?? '—'} />
            <Fact label="Kazanan fiyat" info={<SqlInfo k={d.kaynaklar} alan="sonuc" label="Sonuç kaydı" />} value={fmtMoney(r.kazananFiyat)} help={r.kazananListeOrani != null ? `Liste fiyatının ${fmtPct(r.kazananListeOrani)}'i` : undefined} />
            <Fact label="Bizim teklif" info={<SqlInfo k={d.kaynaklar} alan="sonuc" label="Bizim teklif" />} value={fmtMoney(r.bizimFiyat)} />
            <Fact label="Kaynak" value={r.kaynak ?? '—'} />
          </div>
          {r.neden && <p className="mt-2 whitespace-pre-wrap break-words text-[12.5px]"><b>Neden:</b> {r.neden}</p>}
        </Panel>
      )}
      {meta.me.canEdit && (
        <Panel>
          <h2 className="text-[16px] font-extrabold tracking-tight">{r ? 'Sonucu düzelt' : 'Sonuç kaydı'}</h2>
          {!canResult && <Note tone="info">Kazanıldı/kaybedildi, teklif verildi işaretlendikten sonra girilir. İptal her aşamada girilebilir.</Note>}
          <div className="mt-2 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
            <label className="flex flex-col gap-1">
              <span className={labelCls}>Sonuç</span>
              <select className={field} value={sonuc} onChange={(e) => setSonuc(e.target.value)}>
                {Object.entries(meta.sonuclar).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
              </select>
            </label>
            <label className="flex flex-col gap-1">
              <span className={labelCls}>Kazanan firma</span>
              <input className={field} value={kazanan} onChange={(e) => setKazanan(e.target.value)} placeholder={sonuc === 'kazanildi' ? 'Boşsa TİMAŞ' : 'İlan sonucundaki firma'} />
            </label>
            <label className="flex flex-col gap-1">
              <span className={labelCls}>Kazanan fiyat (KDV hariç ₺)</span>
              <input className={field} inputMode="decimal" value={kazananFiyat} onChange={(e) => setKazananFiyat(e.target.value)} />
            </label>
            <label className="flex flex-col gap-1">
              <span className={labelCls}>Bizim teklif (KDV hariç ₺)</span>
              <input className={field} inputMode="decimal" value={bizim} onChange={(e) => setBizim(e.target.value)} />
            </label>
            <label className="flex flex-col gap-1">
              <span className={labelCls}>Bilginin kaynağı</span>
              <input className={field} value={kaynak} onChange={(e) => setKaynak(e.target.value)} placeholder="Örn. sonuç ilanı, kurum yazısı" />
            </label>
          </div>
          <label className="mt-3 flex flex-col gap-1">
            <span className={labelCls}>Neden{sonuc === 'kaybedildi' ? ' *' : ''}</span>
            <textarea className={`${field} min-h-[72px]`} value={neden} onChange={(e) => setNeden(e.target.value)} />
          </label>
          <div className="mt-2 flex justify-end">
            <button type="button" className={btnPrimary} disabled={!canResult || save.isPending || (sonuc === 'kaybedildi' && !neden.trim())} onClick={() => save.mutate()}>
              {save.isPending && <Loader2 aria-hidden className="h-4 w-4 animate-spin" />}
              Kaydet
            </button>
          </div>
        </Panel>
      )}
      {!meta.me.canEdit && !r && <Panel><div className="py-6 text-center text-[12.5px] text-canvas-muted">Sonuç kaydı yok.</div></Panel>}
    </>
  );
}
