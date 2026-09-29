import { useState, type ReactNode } from 'react';
import { useParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { ClipboardList, FileText, NotebookPen } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import { Loading, Note, Pill, btnGhost, btnPrimary, errText, field, label as labelCls } from '../admin/ui';
import Sheet from '../editorial/studio/reader/Sheet';
import { TONE_LABEL, daysAgo, fmtDay, fmtMoney, fmtPct, fmtShort, istanbulToday, parseTr } from '../field/api';
import { Block, Empty, FieldFrame, KV } from '../field/parts';
import { dealersApi, type Card, type DealersMeta } from './api';
import { ActionItem } from './ActionsTab';
import BriefSheet from './BriefSheet';
import NoteSignalCard from '../signals/NoteSignalCard';
import { ProposalCard } from './LimitsTab';
import { Meter, SegmentBadge, TrendMark, approxNote } from './parts';
import SqlInfo, { InfoLabel } from '../components/SqlInfo';

/** Bayi kartı (telefon önce, tek sayfa kaydırmalı): skor ve bileşenleri · alacak · 12 ay seyri · CRM limit ve risk onayı ·
 *  limit önerisi · aksiyonlar · notlar. Alt çubuk: Risk brifi, not bırak, aksiyon aç. */

export default function DealerCard() {
  const { code = '' } = useParams();
  const meta = useQuery({ queryKey: ['dealers', 'meta'], queryFn: dealersApi.meta, enabled: ENGINE_ENABLED, staleTime: 60_000 });
  const q = useQuery({ queryKey: ['dealers', 'card', code], queryFn: () => dealersApi.card(code), enabled: ENGINE_ENABLED && !!code });
  const [sheet, setSheet] = useState<null | 'brif' | 'not' | 'aksiyon'>(null);
  const c = q.data;
  const m = meta.data;
  const err = errText(q.error, 'Bayi kartı okunamadı; biraz sonra yeniden deneyin.');

  return (
    <FieldFrame
      crumb="Bayi riski"
      title={c?.unvan || code}
      source={c ? `Logo ${fmtDay(c.dataEnd)} tarihine kadar · kural sürüm ${c.kuralSurum}` : 'Logo + CRM'}
      presence={c ? `Skor ${fmtDay(c.gun)}` : 'Bayi kartı'}
      back={{ to: '/bayi-risk?sekme=bayiler', label: 'Bayiler' }}
    >
      {err && <Note tone="err">{err}</Note>}
      {(q.isLoading || meta.isLoading) && <Loading />}
      {c && m && (
        <div className="flex flex-col gap-3 pb-24 lg:pb-6">
          <Header c={c} onBrief={() => setSheet('brif')} />
          <Components c={c} />
          <Receivables c={c} />
          <Series c={c} />
          <Crm c={c} code={code} />
          <div id="limit" className="scroll-mt-20">
            <Block title="Limit önerisi" help="Kural önerir, satış müdürü onaylar; CRM'e insan işler.">
              {c.oneriler.length === 0 ? (
                <Empty>Bu cari için limit önerisi yok.</Empty>
              ) : (
                <ul className="flex flex-col gap-2">
                  {c.oneriler.map((p) => (
                    <ProposalCard key={p.id} p={p} meta={m} compact k={c.kaynaklar} alan="oneriler" />
                  ))}
                </ul>
              )}
            </Block>
          </div>
          <Block
            title="Aksiyonlar"
            action={
              m.me.canAction ? (
                <button type="button" className={btnGhost} onClick={() => setSheet('aksiyon')}>
                  Aksiyon aç
                </button>
              ) : undefined
            }
          >
            {c.aksiyonlar.length === 0 ? (
              <Empty>Bu cari için aksiyon yok.{m.me.canAction ? ' Ziyaret, arama ya da limit işi için «Aksiyon aç»ı kullanın.' : ''}</Empty>
            ) : (
              <ul className="flex flex-col gap-2">
                {c.aksiyonlar.map((a) => (
                  <ActionItem key={a.id} a={a} meta={m} compact />
                ))}
              </ul>
            )}
          </Block>
          <Notes c={c} canNote={m.me.canNote} onAdd={() => setSheet('not')} />

          <nav
            className="fixed inset-x-2 bottom-2 z-30 grid grid-cols-3 gap-1 rounded-2xl border border-slate-100 bg-white/95 p-1 shadow-lg backdrop-blur lg:hidden"
            aria-label="Bayi işlemleri"
          >
            <BarButton icon={<FileText aria-hidden className="h-5 w-5" />} label="Risk brifi" onClick={() => setSheet('brif')} />
            <BarButton icon={<NotebookPen aria-hidden className="h-5 w-5" />} label="Not bırak" disabled={!m.me.canNote} onClick={() => setSheet('not')} />
            <BarButton icon={<ClipboardList aria-hidden className="h-5 w-5" />} label="Aksiyon" disabled={!m.me.canAction} onClick={() => setSheet('aksiyon')} />
          </nav>

          <BriefSheet open={sheet === 'brif'} onClose={() => setSheet(null)} card={c} />
          <NoteSheet open={sheet === 'not'} onClose={() => setSheet(null)} code={code} />
          <ActionSheet open={sheet === 'aksiyon'} onClose={() => setSheet(null)} code={code} meta={m} bmt={c.bmt} />
        </div>
      )}
    </FieldFrame>
  );
}

function Header({ c, onBrief }: { c: Card; onBrief: () => void }) {
  return (
    <section className="rounded-2xl border border-slate-100 bg-white/85 p-3 sm:p-4">
      <div className="flex items-start gap-3">
        <SegmentBadge segment={c.segment} skor={c.skor} size="lg" />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-[13px] font-extrabold">{c.segment ? `Segment ${c.segment}` : 'Hareketsiz'}</span>
            {c.grup === 'anahtar' && <Pill tone="violet">Anahtar hesap</Pill>}
            {c.sorunlu && <Pill tone="err">CRM: Sorunlu müşteri</Pill>}
            <TrendMark egilim={c.egilim} prev={c.oncekiSegment} now={c.segment} />
          </div>
          <div className="mt-0.5 text-[11.5px] text-canvas-muted">
            {[c.code, c.il, c.kanal, c.bmtAd || c.bmt || 'temsilcisiz'].filter(Boolean).join(' · ')}
            {c.skor30 !== null && c.skor !== null ? ` · 30 gün önce skor ${Math.round(c.skor30)}` : ''}
            <SqlInfo k={c.kaynaklar} alan="skor" label="Risk skoru ve segment" className="ml-0.5" />
          </div>
          <p className="mt-1.5 text-[11.5px] leading-snug text-canvas-muted">Skor bir sınıflandırmadır, kredi kararı değildir; bayiye söylenmez.</p>
        </div>
        <button type="button" className={`${btnPrimary} hidden shrink-0 lg:inline-flex`} onClick={onBrief}>
          Risk brifi
        </button>
      </div>
    </section>
  );
}

function Components({ c }: { c: Card }) {
  return (
    <Block
      title="Neden bu segment"
      help="Her bileşen 0–1 arası ölçülür ve kuraldaki ağırlığıyla puana çevrilir; puanların toplamı skordur."
      action={<SqlInfo k={c.kaynaklar} alan="bilesenler" label="Skor bileşenleri" />}
    >
      <ul className="flex flex-col gap-1.5">
        {c.bilesenler.map((b) => (
          <li key={b.key} className="rounded-xl bg-slate-50 px-2.5 py-2">
            <div className="flex items-baseline justify-between gap-2 text-[12.5px]">
              <span className="font-bold">{COMPONENT_NAME[b.key] ?? b.key}</span>
              <span className="shrink-0 font-mono font-extrabold tabular-nums">
                {b.puan.toLocaleString('tr-TR', { maximumFractionDigits: 1 })} <span className="text-canvas-muted">/ {b.agirlik}</span>
              </span>
            </div>
            <div className="mt-1">
              <Meter value={b.deger} tone={b.deger >= 0.66 ? 'err' : b.deger >= 0.33 ? 'warn' : 'violet'} />
            </div>
            <div className="mt-1 text-[11.5px] leading-snug text-canvas-muted">{b.aciklama}</div>
          </li>
        ))}
      </ul>
    </Block>
  );
}

const COMPONENT_NAME: Record<string, string> = {
  gecikme: 'Ödeme gecikmesi', cek: 'Çek/senet olayı', iade: 'İade oranı', limit: 'Limit doluluğu',
  duzensizlik: 'Sipariş düzensizliği', tahsilat_suresi: 'Tahsilat süresi',
};

function Receivables({ c }: { c: Card }) {
  const today = istanbulToday();
  const since = daysAgo(c.sonOdeme, today);
  return (
    <Block title="Alacak" help={`${approxNote} Yaşlandırma günü ${fmtDay(c.agingAsof)}.`}>
      <div className="grid gap-x-6 sm:grid-cols-2">
        <div>
          <KV k="Bakiye" info={<SqlInfo k={c.kaynaklar} alan="bakiye" label="Bakiye" />} v={fmtMoney(c.bakiye)} />
          <KV k="Vadesi gelmemiş" info={<SqlInfo k={c.kaynaklar} alan="gelmemis" label="Vadesi gelmemiş" />} v={fmtMoney(c.gelmemis)} />
          <KV k="1–30 gün" info={<SqlInfo k={c.kaynaklar} alan="kovalar" label="1–30 gün" />} v={fmtMoney(c.kovalar.k_1_30)} />
          <KV k="31–60 gün" info={<SqlInfo k={c.kaynaklar} alan="kovalar" label="31–60 gün" />} v={fmtMoney(c.kovalar.k_31_60)} tone={c.kovalar.k_31_60 ? 'warn' : undefined} />
          <KV k="61–90 gün" info={<SqlInfo k={c.kaynaklar} alan="kovalar" label="61–90 gün" />} v={fmtMoney(c.kovalar.k_61_90)} tone={c.kovalar.k_61_90 ? 'warn' : undefined} />
          <KV k="90+ gün" info={<SqlInfo k={c.kaynaklar} alan="kovalar" label="90+ gün" />} v={fmtMoney(c.kovalar.k_90p)} tone={c.kovalar.k_90p ? 'err' : undefined} />
          {!!c.plansiz && <KV k="Vade planı dışı (plansız)" info={<SqlInfo k={c.kaynaklar} alan="plansiz" label="Plansız bakiye" />} v={fmtMoney(c.plansiz)} />}
        </div>
        <div>
          <KV k="Son ödeme" v={c.sonOdeme ? `${fmtDay(c.sonOdeme)}${since !== null ? ` · ${since} gün` : ''}` : 'yok (12 ay)'} tone={!c.sonOdeme ? 'warn' : undefined} />
          <KV k="12 ay ödeme" info={<SqlInfo k={c.kaynaklar} alan="odeme12" label="12 ay ödeme" />} v={fmtMoney(c.odeme12)} />
          <KV k="Tahsilat süresi (yaklaşık)" info={<SqlInfo k={c.kaynaklar} alan="dso" label="Tahsilat süresi" />} v={c.dso !== null ? `${Math.round(c.dso)} gün` : '—'} />
          <KV k="Karşılıksız / protesto (12 ay)" info={<SqlInfo k={c.kaynaklar} alan="karsiliksiz" label="Çek/senet olayı" />} v={`${c.karsiliksiz ?? 0} / ${c.protesto ?? 0}`} tone={c.karsiliksiz ? 'err' : c.protesto ? 'warn' : undefined} />
          {!!c.cekTutar && <KV k="Olaylı çek/senet tutarı" info={<SqlInfo k={c.kaynaklar} alan="cekTutar" label="Olaylı çek/senet tutarı" />} v={fmtMoney(c.cekTutar)} tone="err" />}
        </div>
      </div>
    </Block>
  );
}

function Series({ c }: { c: Card }) {
  const max = Math.max(1, ...c.seri.map((s) => Math.max(s.satis, s.odeme)));
  return (
    <Block
      title="Son 12 ay"
      action={<SqlInfo k={c.kaynaklar} alan="net12" label="12 ay alım, iade, düzensizlik" />}
      help={`Net alım ${fmtShort(c.net12)} · iade oranı ${fmtPct(c.iadeOrani)} · ${c.aktifAy ?? 0}/12 ay alım${c.buyume6 !== null ? ` · son 6 ay önceki 6 aya ${fmtPct(c.buyume6)}` : ''}`}
    >
      <div className="-mx-1 overflow-x-auto px-1">
        <table className="w-full min-w-[420px] text-[12px]">
          <thead>
            <tr className="text-left text-[10.5px] font-bold uppercase tracking-wide text-canvas-muted">
              <th className="py-1 pr-2">Ay</th>
              <th className="py-1 pr-2"><InfoLabel k={c.kaynaklar} alan="seri" label="Aylık satış">Satış</InfoLabel></th>
              <th className="py-1 pr-2 text-right"><InfoLabel k={c.kaynaklar} alan="seri" label="Aylık iade">İade</InfoLabel></th>
              <th className="py-1 pr-2 text-right"><InfoLabel k={c.kaynaklar} alan="seri" label="Aylık ödeme">Ödeme</InfoLabel></th>
              <th className="py-1 text-right"><InfoLabel k={c.kaynaklar} alan="seri" label="Aylık fatura sayısı">Fatura</InfoLabel></th>
            </tr>
          </thead>
          <tbody>
            {c.seri.map((s) => (
              <tr key={s.ay} className="border-t border-slate-100">
                <td className="py-1 pr-2 font-mono tabular-nums">{s.ay}</td>
                <td className="py-1 pr-2">
                  <div className="flex items-center gap-2">
                    <div className="h-1.5 w-20 overflow-hidden rounded-full bg-slate-100" aria-hidden>
                      <div className="h-full bg-canvas-violet" style={{ width: `${(Math.max(0, s.satis) / max) * 100}%` }} />
                    </div>
                    <span className="font-mono tabular-nums">{fmtShort(s.satis)}</span>
                  </div>
                </td>
                <td className={`py-1 pr-2 text-right font-mono tabular-nums ${s.iade ? 'text-amber-800' : 'text-canvas-muted'}`}>{s.iade ? fmtShort(s.iade) : '—'}</td>
                <td className="py-1 pr-2 text-right font-mono tabular-nums">{s.odeme ? fmtShort(s.odeme) : '—'}</td>
                <td className="py-1 text-right font-mono tabular-nums">{s.fatura || '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Block>
  );
}

function Crm({ c, code }: { c: Card; code: string }) {
  const [open, setOpen] = useState(false);
  const h = useQuery({ queryKey: ['dealers', 'history', code], queryFn: () => dealersApi.history(code), enabled: ENGINE_ENABLED && open });
  const l = c.limit;
  if (!c.crmEsi) {
    return (
      <Block title="CRM limit ve risk">
        <Note tone="info">Bu Logo carisinin CRM'de eşi bulunamadı; limit ve risk alanları CRM cari kartında tutulduğu için gösterilemiyor.</Note>
      </Block>
    );
  }
  const none = 'girilmemiş';
  return (
    <Block
      title="CRM limit ve risk"
      help="CRM cari kartından (salt okuma). Boş limit «limiti yok» değil «girilmemiş» demektir."
      action={<SqlInfo k={c.kaynaklar} alan="limit" label="CRM limit ve risk" />}
    >
      <div className="grid gap-x-6 sm:grid-cols-2">
        <div>
          <KV k="Toplam limit" v={l.limit_toplam ? fmtMoney(l.limit_toplam) : none} tone={!l.limit_toplam ? 'warn' : undefined} />
          <KV k="Açık hesap limiti" v={l.limit_acik ? fmtMoney(l.limit_acik) : none} />
          <KV k="Çek/senet limiti" v={l.limit_cek ? fmtMoney(l.limit_cek) : none} />
          {!!l.ek_limit && <KV k="Ek açık hesap limiti" v={fmtMoney(l.ek_limit)} />}
          {l.vade_gun !== null && l.vade_gun !== undefined && <KV k="Vade günü" v={`${l.vade_gun} gün`} />}
        </div>
        <div>
          <KV k="Toplam risk" v={fmtMoney(l.risk_toplam ?? null)} />
          <KV k="Doluluk" v={fmtPct(l.risk_doluluk ?? null)} tone={(l.risk_doluluk ?? 0) >= 0.9 ? 'err' : (l.risk_doluluk ?? 0) >= 0.7 ? 'warn' : undefined} />
          <KV k="Açık sipariş riski" v={fmtMoney(l.risk_siparis ?? null)} />
          <KV k="Riske takılı sipariş" v={c.siparisRiskte ? `${c.siparisRiskte} · ${fmtMoney(c.siparisRisktetutar)}` : 'yok'} tone={c.siparisRiskte ? 'warn' : undefined} />
          <KV k="Kredi askıda" v={l.kredi_askida ? 'evet' : 'hayır'} tone={l.kredi_askida ? 'err' : undefined} />
        </div>
      </div>
      <button type="button" className={`${btnGhost} mt-2 w-full`} onClick={() => setOpen(!open)}>
        {open ? 'Risk onay geçmişini gizle' : 'Risk onay geçmişi (12 ay, CRM canlı)'}
      </button>
      {open &&
        (h.isLoading ? (
          <Loading />
        ) : h.data?.crmRisk.error ? (
          <Note tone="warn">{h.data.crmRisk.error}</Note>
        ) : (h.data?.crmRisk.items ?? []).length === 0 ? (
          <Empty>Son 12 ayda riske takılan sipariş yok.</Empty>
        ) : (
          <ul className="mt-2 flex flex-col gap-1">
            <li className="flex items-center gap-1 px-1 text-[11px] font-semibold text-canvas-muted">
              Risk onay geçmişi (CRM)
              <SqlInfo k={h.data?.kaynaklar} alan="crmRisk" label="CRM risk onay geçmişi" />
            </li>
            {h.data!.crmRisk.items.map((o, i) => (
              <li key={`${o.no}-${i}`} className="rounded-xl bg-slate-50 px-2.5 py-1.5 text-[12px]">
                <div className="flex items-baseline justify-between gap-2">
                  <span className="font-bold">
                    {o.no || 'Sipariş'} · {fmtDay(o.tarih)}
                  </span>
                  <span className="font-mono font-bold tabular-nums">{fmtMoney(o.tutar)}</span>
                </div>
                <div className="text-canvas-muted">
                  {[o.sebep, o.anlikLimit !== null ? `anlık limit ${fmtShort(o.anlikLimit)}` : null, o.anlikRisk !== null ? `anlık risk ${fmtShort(o.anlikRisk)}` : null,
                    o.riskte ? 'onay bekliyor' : o.onaylayan ? `onaylayan ${o.onaylayan}` : o.reddeden ? `reddeden ${o.reddeden}` : null]
                    .filter(Boolean)
                    .join(' · ')}
                </div>
              </li>
            ))}
          </ul>
        ))}
    </Block>
  );
}

function Notes({ c, canNote, onAdd }: { c: Card; canNote: boolean; onAdd: () => void }) {
  return (
    <Block
      title="Ziyaret ve görüşme notları"
      help="Saha ekranıyla ortak kayıt; gizli not yalnız yazana görünür ve brife girmez."
      action={
        canNote ? (
          <button type="button" className={btnGhost} onClick={onAdd}>
            Not bırak
          </button>
        ) : undefined
      }
    >
      <div className="mb-2">
        <NoteSignalCard code={c.code} screen="bayi" />
      </div>
      {c.ziyaretler.length === 0 ? (
        <Empty>Not yok.</Empty>
      ) : (
        <ul className="flex flex-col gap-1.5">
          {c.ziyaretler.map((v) => (
            <li key={v.id} className="rounded-xl bg-slate-50 px-2.5 py-2 text-[12px]">
              <div className="flex items-baseline justify-between gap-2 text-[11px] text-canvas-muted">
                <span>
                  {fmtDay(v.gerceklesen || v.planlanan)} · {v.sahip}
                  {v.ton ? ` · ${TONE_LABEL[v.ton]}` : ''}
                </span>
                <span>{v.durumAd}</span>
              </div>
              <p className="mt-0.5 leading-snug">{v.gizliNot ? <i className="text-canvas-muted">Gizli not</i> : v.notu || '—'}</p>
              {v.sozOdemeTarihi && (
                <p className="mt-0.5 text-[11.5px] font-bold">
                  Ödeme sözü: {fmtDay(v.sozOdemeTarihi)}
                  {v.sozOdemeTutari ? ` · ${fmtMoney(v.sozOdemeTutari)}` : ''}
                </p>
              )}
            </li>
          ))}
        </ul>
      )}
      {c.ziyaretSayisi > c.ziyaretler.length && <p className="mt-2 text-[11.5px] text-canvas-muted">Son {c.ziyaretler.length} not gösteriliyor; hepsi ({c.ziyaretSayisi}) saha ekranında.</p>}
    </Block>
  );
}

function BarButton({ icon, label, disabled, onClick }: { icon: ReactNode; label: string; disabled?: boolean; onClick: () => void }) {
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onClick}
      className="flex min-h-14 min-w-0 flex-col items-center justify-center gap-0.5 rounded-xl px-1 text-[10.5px] font-extrabold text-canvas-ink transition-transform duration-150 ease-out hover:bg-slate-100 active:scale-[0.97] disabled:opacity-40 disabled:active:scale-100"
    >
      {icon}
      <span className="max-w-full truncate">{label}</span>
    </button>
  );
}

function NoteSheet({ open, onClose, code }: { open: boolean; onClose: () => void; code: string }) {
  const qc = useQueryClient();
  const [notu, setNotu] = useState('');
  const [soz, setSoz] = useState('');
  const [tutar, setTutar] = useState('');
  const [sonraki, setSonraki] = useState('');
  const [gizli, setGizli] = useState(false);
  const amount = parseTr(tutar);
  const save = useMutation({
    mutationFn: () =>
      dealersApi.addNote(code, { notu, sozOdemeTarihi: soz || null, sozOdemeTutari: amount !== null && Number.isFinite(amount) ? amount : null, sonrakiAdim: sonraki || undefined, gizli }),
    onSuccess: () => {
      toast.success('Not kaydedildi');
      setNotu('');
      setSoz('');
      setTutar('');
      setSonraki('');
      setGizli(false);
      void qc.invalidateQueries({ queryKey: ['dealers', 'card', code] });
      void qc.invalidateQueries({ queryKey: ['field'] });
      onClose();
    },
    onError: (e) => toast.error(errText(e, 'Not kaydedilemedi.') ?? 'Not kaydedilemedi.'),
  });
  return (
    <Sheet open={open} modal onClose={onClose} title="Görüşme notu" subtitle="Saha ekranındaki ziyaret kaydıyla aynı yere yazılır.">
      <div className="flex flex-col gap-3">
        <label className="flex flex-col gap-1">
          <span className={labelCls}>Not</span>
          <textarea className={`${field} min-h-[120px]`} value={notu} onChange={(e) => setNotu(e.target.value)} />
        </label>
        <div className="grid grid-cols-2 gap-2">
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Ödeme sözü tarihi</span>
            <input className={field} type="date" value={soz} onChange={(e) => setSoz(e.target.value)} />
          </label>
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Söz tutarı (₺)</span>
            <input className={field} inputMode="decimal" value={tutar} onChange={(e) => setTutar(e.target.value)} />
          </label>
        </div>
        <label className="flex flex-col gap-1">
          <span className={labelCls}>Sonraki adım</span>
          <input className={field} value={sonraki} onChange={(e) => setSonraki(e.target.value)} />
        </label>
        <label className="inline-flex min-h-11 items-center gap-2 text-[12.5px] font-bold">
          <input type="checkbox" className="h-4 w-4" checked={gizli} onChange={(e) => setGizli(e.target.checked)} />
          Gizli not (yalnız ben görürüm, brife girmez)
        </label>
        {Number.isNaN(amount as number) && <Note tone="warn">Tutar sayı olmalı (ör. 20.000,50).</Note>}
        <button type="button" className={btnPrimary} disabled={!notu.trim() || save.isPending || Number.isNaN(amount as number)} onClick={() => save.mutate()}>
          Kaydet
        </button>
      </div>
    </Sheet>
  );
}

function ActionSheet({ open, onClose, code, meta, bmt }: { open: boolean; onClose: () => void; code: string; meta: DealersMeta; bmt: string | null }) {
  const qc = useQueryClient();
  const [tur, setTur] = useState('ziyaret');
  const [sahip, setSahip] = useState(meta.me.canAll && bmt ? bmt : meta.me.username);
  const [termin, setTermin] = useState('');
  const [notu, setNotu] = useState('');
  const save = useMutation({
    mutationFn: () => dealersApi.addAction({ code, tur, sahip, termin: termin || null, notu: notu || undefined }),
    onSuccess: () => {
      toast.success('Aksiyon açıldı');
      setNotu('');
      setTermin('');
      void qc.invalidateQueries({ queryKey: ['dealers'] });
      onClose();
    },
    onError: (e) => toast.error(errText(e, 'Aksiyon açılamadı.') ?? 'Aksiyon açılamadı.'),
  });
  return (
    <Sheet open={open} modal onClose={onClose} title="Aksiyon aç">
      <div className="flex flex-col gap-3">
        <label className="flex flex-col gap-1">
          <span className={labelCls}>Tür</span>
          <select className={field} value={tur} onChange={(e) => setTur(e.target.value)}>
            {meta.actionKinds.map((k) => (
              <option key={k.key} value={k.key}>
                {k.label}
              </option>
            ))}
          </select>
        </label>
        {meta.me.canAll && (
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Kime</span>
            <select className={field} value={sahip} onChange={(e) => setSahip(e.target.value)}>
              <option value={meta.me.username}>Bana</option>
              {meta.bmts
                .filter((b) => b.hesap !== meta.me.username)
                .map((b) => (
                  <option key={b.hesap} value={b.hesap}>
                    {b.ad}
                  </option>
                ))}
            </select>
          </label>
        )}
        <label className="flex flex-col gap-1">
          <span className={labelCls}>Termin</span>
          <input className={field} type="date" value={termin} onChange={(e) => setTermin(e.target.value)} />
        </label>
        <label className="flex flex-col gap-1">
          <span className={labelCls}>Not</span>
          <textarea className={`${field} min-h-[80px]`} value={notu} onChange={(e) => setNotu(e.target.value)} />
        </label>
        <button type="button" className={btnPrimary} disabled={save.isPending} onClick={() => save.mutate()}>
          Aksiyonu aç
        </button>
      </div>
    </Sheet>
  );
}
