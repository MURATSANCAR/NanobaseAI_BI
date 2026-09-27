import { useEffect, useMemo, useState } from 'react';
import { useParams, useSearchParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Download, Loader2, RefreshCw, Sparkles } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import { Note, Pill, TableWrap, btnGhost, btnPrimary, errText, field, label as labelCls, th, td } from '../admin/ui';
import { Kpi, KpiRow, Pager, Panel, useDebounced } from '../editorial/kit';
import Sheet from '../editorial/studio/reader/Sheet';
import { fmtDay, fmtPct, parseNum } from '../budget/api';
import { AskSheet, NumField } from '../budget/parts';
import { STATUS_TONE, distApi, type Cell, type Line, type Plan } from './api';
import { DataEnd, DistFrame, Share, n0 } from './parts';

/** Kitabın dağılım planı: özet (hedef, stok, rezerv), ZEKİ AI gerekçesi ve benzer kitaplar, bölge × kanal matrisi,
 *  müşteri listesi (sayfalı, tavan yok). Taslakta satır ve hücre düzeltilir; onay iki göz. Adres: /ilk-dagilim/:stok?plan= */

type Ask = null | 'submit' | 'withdraw' | 'approve' | 'reject' | 'revise' | 'delete';

export default function PlanEditor() {
  const { stok = '' } = useParams();
  const [params, setParams] = useSearchParams();
  const qc = useQueryClient();
  const meta = useQuery({ queryKey: ['dist', 'meta'], queryFn: distApi.meta, enabled: ENGINE_ENABLED, staleTime: 60_000 });
  const me = meta.data?.me;
  const versions = useQuery({ queryKey: ['dist', 'plans', stok], queryFn: () => distApi.plansOf(stok), enabled: ENGINE_ENABLED && !!stok });
  const pick = useMemo(() => {
    const list = versions.data?.items ?? [];
    return list.find((p) => p.id === params.get('plan')) ?? list.find((p) => p.durum !== 'arsiv') ?? list[0];
  }, [versions.data, params]);
  const planId = pick?.id;
  const plan = useQuery({ queryKey: ['dist', 'plan', planId], queryFn: () => distApi.plan(planId!), enabled: ENGINE_ENABLED && !!planId });
  const p = plan.data;
  const [ask, setAsk] = useState<Ask>(null);
  const [cell, setCell] = useState<Cell | null>(null);
  const editable = p?.durum === 'taslak' && !!me?.canPlan;
  const mine = (p?.submittedBy ?? '').toLowerCase() === (me?.username ?? '').toLowerCase();

  const refreshAll = () => qc.invalidateQueries({ queryKey: ['dist'] });
  const open = (id: string) => {
    const n = new URLSearchParams(params);
    n.set('plan', id);
    setParams(n, { replace: true });
  };

  const generate = useMutation({
    mutationFn: () => distApi.generate(stok),
    onSuccess: (out) => { refreshAll(); open(out.id); },
    onError: (e) => toast.error(errText(e, 'Öneri kurulamadı.') ?? ''),
  });
  const act = useMutation({
    mutationFn: async ({ kind, text }: { kind: Exclude<Ask, null>; text: string }) => {
      if (!p) throw new Error('Plan seçili değil.');
      switch (kind) {
        case 'submit': return distApi.submit(p.id);
        case 'withdraw': return distApi.withdraw(p.id);
        case 'approve': return distApi.approve(p.id, text || undefined);
        case 'reject': return distApi.reject(p.id, text);
        case 'revise': return distApi.revise(p.id, text);
        case 'delete': await distApi.deletePlan(p.id); return null;
      }
    },
    onSuccess: (out, { kind }) => {
      setAsk(null);
      refreshAll();
      toast.success({ submit: 'Plan onaya gönderildi.', withdraw: 'Plan taslağa alındı.', approve: 'Plan onaylandı; sevk listesi indirilebilir.', reject: 'Plan gerekçesiyle geri gönderildi.', revise: 'Revizyon taslağı açıldı.', delete: 'Taslak silindi.' }[kind]);
      if (kind === 'revise' && out) open(out.id);
      if (kind === 'delete') setParams(new URLSearchParams(), { replace: true });
    },
    onError: (e) => toast.error(errText(e, 'İşlem yapılamadı.') ?? ''),
  });
  const track = useMutation({
    mutationFn: () => distApi.track(p!.id),
    onSuccess: (r) => { refreshAll(); toast.success(`Takip yenilendi (${n0(r.satir)} satır).`); },
    onError: (e) => toast.error(errText(e, 'Takip yenilenemedi.') ?? ''),
  });

  const title = p?.ad ?? pick?.ad ?? stok;
  return (
    <DistFrame
      back
      title={title}
      lead={p ? `Stok kodu ${p.stokKodu} · depoya giriş ${fmtDay(p.depoGiris)} · sürüm ${p.surum}` : `Stok kodu ${stok}`}
      source={meta.data?.veriSonu ? `Logo · ${fmtDay(meta.data.veriSonu)}'e kadar` : 'Logo + CRM'}
      presence={p ? `${p.durumEtiket}${p.kapsam === 'kendi' ? ' · kendi carileriniz' : ''}` : '…'}
    >
      {meta.data && <DataEnd veriSonu={meta.data.veriSonu} depoSonu={meta.data.depoSonu} />}
      {(versions.error || plan.error) && <Note tone="err">{errText(versions.error ?? plan.error, 'Plan açılamadı.')}</Note>}
      {versions.isSuccess && !versions.data.items.length && (
        <Panel>
          <div className="flex flex-col items-start gap-2">
            <h2 className="text-lg font-extrabold">Bu kitabın dağılım planı yok</h2>
            <p className="max-w-[70ch] text-[12.5px] text-canvas-muted">
              ZEKİ AI benzer kitapların ilk 8 haftadaki müşteri dağılımından, onaylı satış hedefinden ve stoktan bir taslak kurar. Rakamlar Logo ve CRM'den hesaplanır; ZEKİ AI benzer kitapları ayıklar ve gerekçeyi yazar.
            </p>
            {me?.canPlan ? (
              <button type="button" className={btnPrimary} disabled={generate.isPending} onClick={() => generate.mutate()}>
                {generate.isPending ? <Loader2 aria-hidden className="h-4 w-4 animate-spin" /> : <Sparkles aria-hidden className="h-4 w-4" />}
                ZEKİ AI önerisi oluştur
              </button>
            ) : <Note tone="info">Plan hazırlama yetkisi olan biri öneriyi oluşturabilir.</Note>}
          </div>
        </Panel>
      )}
      {!p && planId && <div className="py-8 text-center text-[12px] text-canvas-muted">Okunuyor…</div>}

      {p && (
        <>
          <div className="flex flex-wrap items-center gap-2 px-1">
            <Pill tone={STATUS_TONE[p.durum]}>{p.durumEtiket}</Pill>
            <span className="min-w-0 text-[12px] font-semibold text-canvas-muted">
              {p.createdBy} hazırladı
              {p.durum === 'onayda' && <> · {p.submittedBy} gönderdi</>}
              {p.durum === 'onayli' && p.decidedBy && <> · {p.decidedBy} onayladı, {fmtDay(p.decidedAt)}</>}
              {p.revisionReason && <> · Revizyon: {p.revisionReason}</>}
            </span>
            {(versions.data?.items.length ?? 0) > 1 && (
              <select aria-label="Sürüm" className={`${field} !w-auto`} value={p.id} onChange={(e) => open(e.target.value)}>
                {versions.data!.items.map((v) => <option key={v.id} value={v.id}>Sürüm {v.surum} — {v.durumEtiket}</option>)}
              </select>
            )}
            <div className="flex w-full flex-wrap gap-2 sm:ml-auto sm:w-auto">
              {editable && <button type="button" className={btnGhost} onClick={() => setAsk('delete')}>Taslağı sil</button>}
              {editable && <button type="button" className={btnPrimary} onClick={() => setAsk('submit')} disabled={p.asim}>Onaya gönder</button>}
              {p.durum === 'onayda' && me?.canPlan && <button type="button" className={btnGhost} onClick={() => setAsk('withdraw')}>Onaydan çek</button>}
              {p.durum === 'onayda' && me?.canApprove && !mine && (
                <>
                  <button type="button" className={btnGhost} onClick={() => setAsk('reject')}>Geri gönder</button>
                  <button type="button" className={btnPrimary} onClick={() => setAsk('approve')}>Onayla</button>
                </>
              )}
              {p.durum === 'onayli' && me?.canAll && me.canExport && (
                <a className={btnPrimary} href={distApi.exportUrl(p.id)} download>
                  <Download aria-hidden className="h-4 w-4" />
                  Sevk listesi (Excel)
                </a>
              )}
              {p.durum === 'onayli' && me?.canPlan && (
                <>
                  <button type="button" className={btnGhost} onClick={() => track.mutate()} disabled={track.isPending}>
                    {track.isPending ? <Loader2 aria-hidden className="h-4 w-4 animate-spin" /> : <RefreshCw aria-hidden className="h-4 w-4" />}
                    Takibi yenile
                  </button>
                  <button type="button" className={btnGhost} onClick={() => setAsk('revise')}>Revize et</button>
                </>
              )}
            </div>
          </div>
          {p.durum === 'taslak' && p.decisionNote && <Note tone="warn">Geri gönderildi ({p.decidedBy}): {p.decisionNote}</Note>}
          {p.durum === 'onayda' && me?.canApprove && mine && <Note tone="info">Bu planı siz onaya gönderdiniz; onayı başka bir yetkili verir.</Note>}
          {p.asim && (
            <Note tone="err">
              Dağılım {n0(p.toplam)} + rezerv {n0(p.rezerv)} = {n0(p.toplam + p.rezerv)} adet, {p.guncelStok.tur === 'stok' ? 'stok bakiyesini' : 'baskı adedini'} ({n0(p.guncelStok.adet)}) aşıyor. Onaya gönderilemez.
            </Note>
          )}
          {p.basis.uyarilar?.map((w) => <Note key={w} tone="warn">{w}</Note>)}

          <Summary p={p} editable={editable} onSaved={refreshAll} />
          <Rationale p={p} />
          <MatrixPanel p={p} editable={editable} onCell={setCell} />
          <Lines p={p} editable={editable} onSaved={refreshAll} />
        </>
      )}

      <CellSheet plan={p} cell={cell} onClose={() => setCell(null)} onSaved={() => { setCell(null); refreshAll(); }} />
      <AskSheet
        open={ask !== null}
        busy={act.isPending}
        title={{ submit: 'Onaya gönder', withdraw: 'Onaydan çek', approve: 'Planı onayla', reject: 'Geri gönder', revise: 'Planı revize et', delete: 'Taslağı sil', '': '' }[ask ?? '']}
        message={
          ask === 'submit' ? 'Plan lojistik onayına düşer; onayı sizden başka bir yetkili verir. Onayda iken adetler değiştirilemez.'
            : ask === 'withdraw' ? 'Plan yeniden taslak olur.'
            : ask === 'approve' ? `Plan kitabın yürürlükteki dağılım planı olur; sevk listesi indirilebilir, BMT'ler kendi carilerine düşen adetleri görür. Stok bakiyesi yeniden denetlenir.`
            : ask === 'reject' ? 'Plan gerekçenizle taslağa döner; hazırlayan düzeltip yeniden gönderir.'
            : ask === 'revise' ? 'Onaylı planın kopyası yeni bir taslak sürüm olarak açılır. Onaylanana kadar mevcut plan geçerli kalır.'
            : 'Taslak ve bütün satırları silinir. Bu işlem geri alınmaz.'
        }
        confirm={{ submit: 'Onaya gönder', withdraw: 'Taslağa al', approve: 'Onayla', reject: 'Geri gönder', revise: 'Revizyon aç', delete: 'Sil', '': '' }[ask ?? '']}
        danger={ask === 'delete'}
        input={ask === 'reject' ? 'Gerekçe' : ask === 'revise' ? 'Revizyon gerekçesi (yazar etkinliği, stok değişimi…)' : ask === 'approve' ? 'Not (isteğe bağlı)' : undefined}
        required={ask === 'reject' || ask === 'revise'}
        onClose={() => setAsk(null)}
        onConfirm={(text) => ask && act.mutate({ kind: ask, text })}
      />
    </DistFrame>
  );
}

function Summary({ p, editable, onSaved }: { p: Plan; editable: boolean; onSaved: () => void }) {
  const [rez, setRez] = useState(String(p.rezerv));
  useEffect(() => setRez(String(p.rezerv)), [p.rezerv]);
  const save = useMutation({
    mutationFn: () => {
      const v = parseNum(rez);
      if (v === null || v < 0) throw new Error('Rezerv sıfır ya da artı bir sayı olmalı.');
      return distApi.updatePlan(p.id, { rezerv: v });
    },
    onSuccess: () => { onSaved(); toast.success('Rezerv kaydedildi.'); },
    onError: (e) => toast.error(errText(e, 'Kaydedilemedi.') ?? ''),
  });
  const stock = p.guncelStok.adet;
  const hedef = p.hedef.var
    ? `${n0(p.hedef.ikiAyAdet)} (ilk iki ay)`
    : '—';
  return (
    <>
      <KpiRow>
        <Kpi label="Dağıtılacak" value={n0(p.toplam)} help={`ZEKİ AI önerisi ${n0(p.onerilenToplam)} · ${n0(p.musteri)} müşteri${p.elleSatir ? ` · ${n0(p.elleSatir)} satır elle` : ''}`} />
        <Kpi label="Rezerv" value={n0(p.rezerv)} help={`Depoda kalan pay (öneri %${Math.round((p.basis.rezervPay ?? 0) * 100)})`} />
        <Kpi label={p.guncelStok.tur === 'baski' ? 'Baskı adedi' : 'Stok bakiyesi'} value={n0(stock)} help={stock !== null ? `Kalan ${n0(stock - p.toplam - p.rezerv)}` : 'Logo\'da görünmüyor'} />
        <Kpi label="Satış hedefi" value={hedef} help={p.hedef.var ? `Yıllık ${n0(p.hedef.yillikAdet)} · ${p.hedef.planBaslik ?? ''}` : 'Onaylı bütçede bu kitabın hedefi yok'} />
      </KpiRow>
      {editable && (
        <Panel>
          <div className="flex flex-col gap-2 sm:flex-row sm:items-end">
            <div className="sm:w-56"><NumField id="rezerv" label="Rezerv (adet)" value={rez} onChange={setRez} help="Depoda tutulacak adet" /></div>
            <button type="button" className={btnGhost} onClick={() => save.mutate()} disabled={save.isPending || rez === String(p.rezerv)}>Rezervi kaydet</button>
          </div>
        </Panel>
      )}
    </>
  );
}

const KARAR: Record<string, { label: string; tone: 'ok' | 'warn' | 'err' }> = {
  benzer: { label: 'ZEKİ AI: benzer', tone: 'ok' },
  az: { label: 'ZEKİ AI: az benzer', tone: 'warn' },
  degil: { label: 'ZEKİ AI: benzemez', tone: 'err' },
};

function Rationale({ p }: { p: Plan }) {
  const b = p.basis;
  const method = b.yontem === 'kendi' ? 'Baskı tekrarı: kitabın kendi son satışı'
    : b.yontem === 'emsal' ? 'Benzer kitaplar: emsal puanı (CRM emsali, yazar, dizi, kitaplık, fiyat)'
    : b.yontem === 'kitap-karti' ? 'Benzer kitaplar: kitap kartı (yazar, kitaplık, yayınevi)' : 'Benzer kitap yok';
  const total = b.toplamKaynak === 'hedef' ? 'onaylı hedefin ilk iki ayı' : b.toplamKaynak === 'benzer' ? `benzer kitapların ilk ${b.pencereGun ?? 56} gün ortancası (${n0(b.benzerOrtanca)})` : 'kaynak yok';
  return (
    <Panel>
      <div className="flex items-center gap-2 text-[13px] font-extrabold">
        <Sparkles aria-hidden className="h-4 w-4 text-canvas-violet" />
        {p.gerekceKaynak === 'model' ? 'ZEKİ AI gerekçesi' : 'Öneri gerekçesi'}
      </div>
      {p.gerekce && <p className="mt-1.5 max-w-[90ch] text-[13px] leading-relaxed">{p.gerekce}</p>}
      <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-[11.5px] text-canvas-muted">
        <span>{method}</span>
        <span>Toplam: {total}</span>
        {b.modelAyiklama && <span>Benzer kitaplar ZEKİ AI ile ayıklandı</span>}
      </div>
      {!!p.benzerler.length && (
        <div className="mt-3">
          <TableWrap>
            <thead>
              <tr>
                <th className={th}>Benzer kitap</th>
                <th className={th}>Neden</th>
                <th className={`${th} text-right`}>İlk {b.pencereGun ?? 56} gün net</th>
                <th className={`${th} text-right`}>İade</th>
                <th className={`${th} text-right`}>Müşteri</th>
                <th className={`${th} text-right`}>CRM dağılım siparişi</th>
                <th className={th}>Kanal</th>
              </tr>
            </thead>
            <tbody>
              {p.benzerler.map((c) => {
                const top = Object.entries(c.kanallar).sort((x, y) => y[1] - x[1]).slice(0, 3);
                const sum = Object.values(c.kanallar).reduce((a, x) => a + x, 0);
                return (
                  <tr key={c.stokKodu} className={`border-t border-slate-100 ${c.secildi ? '' : 'opacity-55'}`}>
                    <td className={td}>
                      <div className="font-bold">{c.ad ?? c.stokKodu}</div>
                      <div className="font-mono text-[11px] text-canvas-muted">{c.stokKodu}{c.pencere ? ` · ${fmtDay(c.pencere[0])}` : ''}</div>
                      {c.modelKarar && <div className="mt-1"><Pill tone={KARAR[c.modelKarar].tone}>{KARAR[c.modelKarar].label}</Pill></div>}
                    </td>
                    <td className={`${td} max-w-[260px] text-[11.5px]`}>
                      {c.gerekce ?? '—'}
                      {b.modelAyiklama && c.benzerlik !== null && <div className="text-canvas-muted">Benzerlik {fmtPct(c.benzerlik, 0)}</div>}
                      {!c.secildi && <div className="font-bold">Öneriye girmedi</div>}
                    </td>
                    <td className={`${td} text-right font-mono tabular-nums`}>{n0(c.net)}</td>
                    <td className={`${td} text-right font-mono tabular-nums`}>{c.satis ? fmtPct((c.iade ?? 0) / c.satis, 0) : '—'}</td>
                    <td className={`${td} text-right font-mono tabular-nums`}>{n0(c.musteri)}</td>
                    <td className={`${td} text-right font-mono tabular-nums`}>{c.crmDagilimAdet !== null ? `${n0(c.crmDagilimAdet)} (${n0(c.crmDagilimSiparis)})` : '—'}</td>
                    <td className={`${td} text-[11.5px]`}>{top.map(([k, v]) => `${k} ${sum ? Math.round((v / sum) * 100) : 0}%`).join(' · ') || '—'}</td>
                  </tr>
                );
              })}
            </tbody>
          </TableWrap>
        </div>
      )}
    </Panel>
  );
}

function MatrixPanel({ p, editable, onCell }: { p: Plan; editable: boolean; onCell: (c: Cell) => void }) {
  const m = p.matris;
  const cells = useMemo(() => new Map(m.hucreler.map((h) => [`${h.bolge}|${h.kanal}`, h])), [m]);
  const kanal = m.kanallar.map((k) => k.kanal);
  if (!m.hucreler.length) return null;
  return (
    <Panel>
      <div className="mb-2 flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-[15px] font-extrabold">Bölge × kanal</h2>
        <span className="text-[11.5px] text-canvas-muted">{editable ? 'Hücreye dokunun: toplam, hücredeki müşterilere oranla dağılır.' : `Toplam ${n0(m.toplam)} adet`}</span>
      </div>
      {/* Telefon: bölge kartları */}
      <ul className="flex flex-col gap-2 md:hidden">
        {m.bolgeler.map((b) => (
          <li key={b.bolge} className="rounded-2xl border border-slate-100 bg-white/80 p-3">
            <div className="flex items-baseline justify-between gap-2">
              <span className="text-[13px] font-extrabold">{b.bolge}</span>
              <span className="font-mono text-[13px] font-bold tabular-nums">{n0(b.adet)} <span className="text-[11px] text-canvas-muted">{fmtPct(b.pay, 0)}</span></span>
            </div>
            <div className="mt-1.5"><Share value={b.pay} /></div>
            <div className="mt-2 flex flex-wrap gap-1.5">
              {kanal.map((k) => {
                const h = cells.get(`${b.bolge}|${k}`);
                if (!h) return null;
                return (
                  <button key={k} type="button" disabled={!editable} onClick={() => onCell(h)}
                    className="min-h-11 rounded-xl bg-slate-100 px-2.5 text-[11.5px] font-semibold disabled:cursor-default">
                    {k} <strong className="font-mono tabular-nums">{n0(h.adet)}</strong>
                  </button>
                );
              })}
            </div>
          </li>
        ))}
      </ul>
      {/* Tablet ve masaüstü: matris */}
      <div className="hidden md:block">
        <div className="overflow-x-auto rounded-2xl border border-slate-100 bg-white/80">
          <table className="w-full text-[12px]">
            <thead>
              <tr>
                <th className={`${th} sticky left-0 bg-white`}>Bölge</th>
                {kanal.map((k) => <th key={k} className={`${th} text-right`}>{k}</th>)}
                <th className={`${th} text-right`}>Toplam</th>
              </tr>
            </thead>
            <tbody>
              {m.bolgeler.map((b) => (
                <tr key={b.bolge} className="border-t border-slate-100">
                  <td className={`${td} sticky left-0 bg-white font-bold`}>{b.bolge}</td>
                  {kanal.map((k) => {
                    const h = cells.get(`${b.bolge}|${k}`);
                    if (!h) return <td key={k} className={`${td} text-right text-slate-300`}>·</td>;
                    const changed = h.adet !== h.onerilen;
                    return (
                      <td key={k} className={`${td} text-right`}>
                        {editable ? (
                          <button type="button" onClick={() => onCell(h)} className="rounded-lg px-1.5 py-0.5 font-mono tabular-nums hover:bg-slate-100">
                            {n0(h.adet)}
                          </button>
                        ) : <span className="font-mono tabular-nums">{n0(h.adet)}</span>}
                        {changed && <div className="text-[10.5px] text-canvas-muted">öneri {n0(h.onerilen)}</div>}
                      </td>
                    );
                  })}
                  <td className={`${td} text-right font-mono font-bold tabular-nums`}>{n0(b.adet)}<div className="text-[10.5px] font-normal text-canvas-muted">{fmtPct(b.pay, 0)}</div></td>
                </tr>
              ))}
              <tr className="border-t border-slate-200">
                <td className={`${td} sticky left-0 bg-white font-extrabold`}>Toplam</td>
                {m.kanallar.map((k) => <td key={k.kanal} className={`${td} text-right font-mono font-bold tabular-nums`}>{n0(k.adet)}</td>)}
                <td className={`${td} text-right font-mono font-extrabold tabular-nums`}>{n0(m.toplam)}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </Panel>
  );
}

function CellSheet({ plan, cell, onClose, onSaved }: { plan?: Plan; cell: Cell | null; onClose: () => void; onSaved: () => void }) {
  const [v, setV] = useState('');
  const [why, setWhy] = useState('');
  useEffect(() => { setV(cell ? String(cell.adet) : ''); setWhy(''); }, [cell]);
  const save = useMutation({
    mutationFn: () => {
      const n = parseNum(v);
      if (!plan || !cell || n === null || n < 0 || !Number.isInteger(n)) throw new Error('Adet sıfır ya da artı bir tam sayı olmalı.');
      return distApi.updateCell(plan.id, { bolge: cell.bolge, kanal: cell.kanal, adet: n, gerekce: why || undefined });
    },
    onSuccess: () => { toast.success('Hücre güncellendi.'); onSaved(); },
    onError: (e) => toast.error(errText(e, 'Kaydedilemedi.') ?? ''),
  });
  return (
    <Sheet open={!!cell} modal onClose={onClose} title={cell ? `${cell.bolge} · ${cell.kanal}` : ''} subtitle={cell ? `${n0(cell.satir)} müşteri · ZEKİ AI önerisi ${n0(cell.onerilen)} adet` : undefined}>
      <div className="flex flex-col gap-3 text-[13px]">
        <NumField id="hucre" label="Hücre toplamı (adet)" value={v} onChange={setV} help="Hücredeki müşterilere mevcut adetleri oranında dağılır; hepsi sıfırsa önerilen paylarla." />
        <label className="flex flex-col gap-1">
          <span className={labelCls}>Gerekçe</span>
          <textarea className={`${field} min-h-[80px]`} value={why} onChange={(e) => setWhy(e.target.value)} placeholder="Yazar etkinliği, bölge kampanyası…" />
        </label>
        <div className="flex justify-end gap-2">
          <button type="button" className={btnGhost} onClick={onClose}>Vazgeç</button>
          <button type="button" className={btnPrimary} onClick={() => save.mutate()} disabled={save.isPending}>Kaydet</button>
        </div>
      </div>
    </Sheet>
  );
}

const ONLY = [
  { key: '', label: 'Hepsi' },
  { key: 'adetli', label: 'Adedi olan' },
  { key: 'elle', label: 'Elle düzeltilen' },
  { key: 'dagilim', label: 'Dağılım carisi' },
];

function Lines({ p, editable, onSaved }: { p: Plan; editable: boolean; onSaved: () => void }) {
  const [q, setQ] = useState('');
  const [bolge, setBolge] = useState('');
  const [kanal, setKanal] = useState('');
  const [yalniz, setYalniz] = useState('adetli');
  const [page, setPage] = useState(0);
  const dq = useDebounced(q, 250);
  useEffect(() => setPage(0), [dq, bolge, kanal, yalniz]);
  const lines = useQuery({
    queryKey: ['dist', 'lines', p.id, dq, bolge, kanal, yalniz, page],
    queryFn: () => distApi.lines(p.id, { q: dq, bolge, kanal, yalniz, page }),
    enabled: ENGINE_ENABLED,
    placeholderData: (prev) => prev,
  });
  const d = lines.data;
  const tracked = p.durum === 'onayli' || p.durum === 'arsiv';
  return (
    <Panel>
      <div className="mb-2 flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-[15px] font-extrabold">Müşteriler</h2>
        <span className="text-[11.5px] text-canvas-muted">{n0(p.satirSayisi)} satır; liste kesilmez, sayfalanır.</span>
      </div>
      <div className="mb-3 grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-4">
        <label className="flex flex-col gap-1"><span className={labelCls}>Ara</span>
          <input className={field} value={q} onChange={(e) => setQ(e.target.value)} placeholder="Unvan, cari kodu, il, BMT" /></label>
        <label className="flex flex-col gap-1"><span className={labelCls}>Bölge</span>
          <select className={field} value={bolge} onChange={(e) => setBolge(e.target.value)}>
            <option value="">Bütün bölgeler</option>
            {p.matris.bolgeler.map((b) => <option key={b.bolge} value={b.bolge}>{b.bolge}</option>)}
          </select></label>
        <label className="flex flex-col gap-1"><span className={labelCls}>Kanal</span>
          <select className={field} value={kanal} onChange={(e) => setKanal(e.target.value)}>
            <option value="">Bütün kanallar</option>
            {p.matris.kanallar.map((k) => <option key={k.kanal} value={k.kanal}>{k.kanal}</option>)}
          </select></label>
        <label className="flex flex-col gap-1"><span className={labelCls}>Göster</span>
          <select className={field} value={yalniz} onChange={(e) => setYalniz(e.target.value)}>
            {ONLY.map((o) => <option key={o.key} value={o.key}>{o.label}</option>)}
          </select></label>
      </div>
      {lines.error && <Note tone="err">{errText(lines.error, 'Müşteriler okunamadı.')}</Note>}
      {d && !d.items.length && <div className="py-6 text-center text-[12.5px] text-canvas-muted">Bu süzgeçte müşteri yok.</div>}
      <ul className="flex flex-col gap-1.5">
        {d?.items.map((ln) => <LineRow key={ln.no} plan={p} ln={ln} editable={editable} tracked={tracked} onSaved={onSaved} />)}
      </ul>
      {d && d.total > 0 && (
        <Pager page={page} pageSize={d.pageSize} total={d.total} shown={d.items.length} loading={lines.isLoading} fetching={lines.isFetching} onPage={setPage} />
      )}
    </Panel>
  );
}

function LineRow({ plan, ln, editable, tracked, onSaved }: { plan: Plan; ln: Line; editable: boolean; tracked: boolean; onSaved: () => void }) {
  const [v, setV] = useState(String(ln.adet));
  const [why, setWhy] = useState(ln.gerekce ?? '');
  useEffect(() => { setV(String(ln.adet)); setWhy(ln.gerekce ?? ''); }, [ln.adet, ln.gerekce]);
  const dirty = v !== String(ln.adet) || why !== (ln.gerekce ?? '');
  const save = useMutation({
    mutationFn: () => {
      const n = parseNum(v);
      if (n === null || n < 0 || !Number.isInteger(n)) throw new Error('Adet sıfır ya da artı bir tam sayı olmalı.');
      return distApi.updateLine(plan.id, ln.no, { adet: n, gerekce: why });
    },
    onSuccess: () => onSaved(),
    onError: (e) => { toast.error(errText(e, 'Kaydedilemedi.') ?? ''); setV(String(ln.adet)); },
  });
  return (
    <li className="rounded-xl border border-slate-100 bg-white/80 px-3 py-2">
      <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
        <div className="min-w-0 md:flex-1">
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="break-words text-[12.5px] font-bold">{ln.unvan}</span>
            {ln.dagilimCarisi && <Pill tone="violet">Dağılım carisi</Pill>}
            {ln.elle && <Pill tone="warn">Elle</Pill>}
          </div>
          <div className="text-[11px] text-canvas-muted">
            <span className="font-mono">{ln.cariKodu ?? 'Logo kodu yok'}</span> · {ln.il ?? 'il yok'} · {ln.bolge} · {ln.kanal}{ln.bmt ? ` · BMT ${ln.bmt}` : ''}
          </div>
          <div className="text-[11px] text-canvas-muted">
            Pay {fmtPct(ln.pay, 1)} · benzerlerde net {n0(ln.gecmisNet)}{ln.gecmisIadeOrani !== null ? ` · iade ${fmtPct(ln.gecmisIadeOrani, 0)}` : ''} · öneri {n0(ln.onerilen)}
          </div>
          {!editable && ln.gerekce && <div className="text-[11px] italic text-canvas-muted">«{ln.gerekce}»</div>}
        </div>
        {tracked && ln.takip && (
          <div className="grid grid-cols-3 gap-3 text-right text-[11px] md:w-56">
            <div><div className={labelCls}>Sevk</div><span className="font-mono text-[12.5px] tabular-nums">{n0(ln.takip.sevk)}</span></div>
            <div><div className={labelCls}>Fatura</div><span className="font-mono text-[12.5px] tabular-nums">{n0(ln.takip.fatura)}</span></div>
            <div><div className={labelCls}>İade</div><span className="font-mono text-[12.5px] tabular-nums">{n0(ln.takip.iade)}</span></div>
          </div>
        )}
        {editable && ln.cariKodu !== null ? (
          <div className="flex flex-col gap-1.5 sm:flex-row sm:items-center md:w-[380px]">
            <input aria-label={`${ln.unvan} gerekçe`} className={`${field} sm:flex-1`} value={why} onChange={(e) => setWhy(e.target.value)} placeholder="Gerekçe (isteğe bağlı)" />
            <div className="flex gap-1.5">
              <input aria-label={`${ln.unvan} adet`} inputMode="numeric" className={`${field} w-24 text-right font-mono tabular-nums`} value={v}
                onChange={(e) => setV(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && dirty && save.mutate()} />
              <button type="button" className={btnGhost} disabled={!dirty || save.isPending} onClick={() => save.mutate()}>Kaydet</button>
            </div>
          </div>
        ) : (
          <div className="text-right font-mono text-[15px] font-bold tabular-nums md:w-24">{n0(ln.adet)}</div>
        )}
      </div>
    </li>
  );
}
