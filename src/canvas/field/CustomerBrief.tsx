import { useState, type ReactNode } from 'react';
import { useParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { CalendarPlus, Copy, HandCoins, Loader2, NotebookPen, Pin, Sparkles } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import { Loading, Note, Pill, btnGhost, btnPrimary, errText, field } from '../admin/ui';
import { AskSheet } from '../budget/parts';
import Sheet from '../editorial/studio/reader/Sheet';
import { daysAgo, fieldApi, fmtDay, fmtMoney, fmtPct, istanbulToday, type Brief, type Visit } from './api';
import { Block, Chips, Empty, FieldFrame, KV, ScoreBadge } from './parts';
import { PlanCard } from './PlansTab';
import VisitNoteSheet from './VisitNoteSheet';
import NoteSignalCard from '../signals/NoteSignalCard';
import SqlInfo from '../components/SqlInfo';
import { Explain } from '../components/Explain';

/** Müşteri brifingi (telefon, tek sayfa, kaydırmalı): Özet · Ödeme · Sipariş · Hedef · Öneri · Notlar. Rakamlar Logo ve
 *  CRM'den; Zeki AI yalnız 3 cümlelik özeti yazar ve özetteki her sayı aşağıdaki olgulardan gelir. Alt çubuk: not bırak,
 *  planla, ödeme planı öner, öne al. */

const SECTIONS = [
  { id: 'odeme', label: 'Ödeme' },
  { id: 'siparis', label: 'Sipariş' },
  { id: 'hedef', label: 'Hedef' },
  { id: 'oneri', label: 'Öneri' },
  { id: 'notlar', label: 'Notlar' },
] as const;

export default function CustomerBrief() {
  const { code = '' } = useParams();
  const qc = useQueryClient();
  const meta = useQuery({ queryKey: ['field', 'meta'], queryFn: fieldApi.meta, enabled: ENGINE_ENABLED, staleTime: 60_000 });
  const q = useQuery({ queryKey: ['field', 'brief', code], queryFn: () => fieldApi.brief(code), enabled: ENGINE_ENABLED && !!code });
  const b = q.data;
  const m = meta.data;
  const [sheet, setSheet] = useState<null | { mode: 'not' | 'plan'; visit?: Visit | null }>(null);
  const [ask, setAsk] = useState<null | 'boost'>(null);
  const [draft, setDraft] = useState<string | null>(null);

  const summary = useMutation({
    mutationFn: () => fieldApi.summary(code),
    onSuccess: (r) => {
      if (r.not) toast.warning(r.not);
      void qc.invalidateQueries({ queryKey: ['field', 'brief', code] });
    },
    onError: (e) => toast.error(errText(e, 'Özet yazılamadı.') ?? 'Özet yazılamadı.'),
  });
  const plan = useMutation({
    mutationFn: () => fieldApi.addPlan({ code }),
    onSuccess: () => {
      toast.success('Ödeme planı taslağı hazır; taksitleri kontrol edip onaya gönderin.');
      void qc.invalidateQueries({ queryKey: ['field'] });
      document.getElementById('odeme-plani')?.scrollIntoView({ block: 'start' });
    },
    onError: (e) => toast.error(errText(e, 'Ödeme planı önerilemedi.') ?? 'Ödeme planı önerilemedi.'),
  });
  const boost = useMutation({
    mutationFn: (neden: string) => fieldApi.addOverride({ code, neden }),
    onSuccess: () => {
      toast.success('Müşteri öne alındı');
      setAsk(null);
      void qc.invalidateQueries({ queryKey: ['field'] });
    },
    onError: (e) => toast.error(errText(e, 'Öne alınamadı.') ?? 'Öne alınamadı.'),
  });
  const followup = useMutation({
    mutationFn: (id: string) => fieldApi.followup(id),
    onSuccess: (r) => setDraft(r.taslak),
    onError: (e) => toast.error(errText(e, 'Taslak yazılamadı.') ?? 'Taslak yazılamadı.'),
  });

  const title = b?.unvan || code;
  const err = errText(q.error, 'Brifing okunamadı.');
  const s = b?.signals;
  const today = istanbulToday();

  return (
    <FieldFrame
      crumb="Saha ve tahsilat"
      title={title}
      source={b ? `Logo ${fmtDay(b.dataEnd)} tarihine kadar · CRM canlı` : 'Logo + CRM'}
      presence={b?.asof ? `Veri ${fmtDay(b.asof)}` : 'Brifing'}
      back={{ to: '/saha', label: 'Bugün' }}
    >
      {q.isLoading && <Loading />}
      {err && <Note tone="err">{err}</Note>}
      {b && s && m && (
        <div className="flex flex-col gap-3">
          <div className="flex items-start gap-3 px-1">
            <ScoreBadge value={b.puan} />
            <span className="pt-2">
              <SqlInfo k={b.kaynaklar} alan="puan" label="Öncelik puanı" />
            </span>
            <div className="min-w-0 flex-1">
              <div className="text-[12px] text-canvas-muted">
                {[b.code, b.il, b.kanal, b.temsilciAd ? `Temsilci ${b.temsilciAd}` : 'temsilcisi yok'].filter(Boolean).join(' · ')}
              </div>
              <div className="mt-1.5">
                <Chips chips={b.gerekce} />
              </div>
            </div>
          </div>
          {b.warnings.map((w) => (
            <Note key={w} tone="warn">
              {w}
            </Note>
          ))}
          {b.sozGecti && (
            <Note tone="err">
              Verilen ödeme sözünün tarihi ({fmtDay(b.sozGecti.tarih)}{b.sozGecti.tutar ? `, ${fmtMoney(b.sozGecti.tutar)}` : ''}) geçti; sonrasında Logo'da ödeme yok.
              <SqlInfo k={b.kaynaklar} alan="sozGecti" label="Geçen ödeme sözü" className="ml-0.5" />
            </Note>
          )}

          <section className="rounded-2xl border border-canvas-violet/20 bg-canvas-violet/5 p-3" aria-label="Özet">
            <div className="flex items-center justify-between gap-2">
              <div className="flex items-center gap-1.5 text-[12px] font-extrabold text-canvas-violet">
                <Sparkles aria-hidden className="h-4 w-4" />
                {b.ozet.kaynak === 'zeki' ? 'Zeki AI özeti' : 'Özet'}
              </div>
              {b.zekiVar && b.ozet.kaynak !== 'zeki' && (
                <button type="button" className={`${btnGhost} !min-h-9 !bg-white/80`} disabled={summary.isPending} onClick={() => summary.mutate()}>
                  {summary.isPending && <Loader2 aria-hidden className="h-4 w-4 animate-spin" />}
                  Zeki AI yazsın
                </button>
              )}
            </div>
            <p className="mt-1.5 text-[13.5px] leading-relaxed">{b.ozet.metin}</p>
          </section>

          <nav aria-label="Bölümler" className="sticky top-0 z-10 -mx-1 overflow-x-auto rounded-2xl bg-white/80 px-1 py-1 backdrop-blur">
            <div className="flex w-max gap-1">
              {SECTIONS.map((x) => (
                <a key={x.id} href={`#${x.id}`} className="inline-flex min-h-9 items-center rounded-xl bg-white/85 px-3 text-[12px] font-extrabold shadow-sm">
                  {x.label}
                </a>
              ))}
            </div>
          </nav>

          <Block id="odeme" title="Ödeme" help={`Vade ve gecikme süreleri yaklaşıktır: Logo'da ödemeler tek tek faturalara kapatılmadığı için bakiye en yeni vadelerden geriye doğru dağıtılır. Hesap ${fmtDay(b.agingAsof)} gününe göre.`}>
            <KV k="Bakiye" info={<SqlInfo k={b.kaynaklar} alan="signals.bakiye" label="Bakiye" />} v={fmtMoney(s.bakiye)} />
            <KV k="Vadesi geçmiş (yaklaşık)" info={<SqlInfo k={b.kaynaklar} alan="signals.vadesi_gecmis" label="Vadesi geçmiş" />} v={fmtMoney(s.vadesi_gecmis)} tone={(s.vadesi_gecmis ?? 0) > 0 ? 'err' : undefined} />
            {m.buckets.map((k) => (
              <KV key={k.key} k={`  ${k.label}`} info={<SqlInfo k={b.kaynaklar} alan={`signals.${k.key}`} label={k.label} />} v={fmtMoney(s[k.key])} tone={k.key === 'k_90p' && (s.k_90p ?? 0) > 0 ? 'err' : undefined} />
            ))}
            <KV k="Vadesi gelmemiş" info={<><Explain label="Vadesi gelmemiş">Bakiyenin henüz ödeme günü gelmemiş kısmı; şu an gecikme sayılmaz.</Explain><SqlInfo k={b.kaynaklar} alan="signals.gelmemis" label="Vadesi gelmemiş" /></>} v={fmtMoney(s.gelmemis)} />
            {(s.plansiz ?? 0) > 0 && <KV k="Vade planı olmayan bakiye" info={<><Explain label="Vade planı olmayan bakiye">Logo'da ödeme günü tanımlanmamış bakiye; bu yüzden vadesi geçmiş ya da gelmemiş diye ayrılamıyor.</Explain><SqlInfo k={b.kaynaklar} alan="signals.plansiz" label="Plansız bakiye" /></>} v={fmtMoney(s.plansiz)} tone="warn" />}
            <KV
              k="Son ödeme"
              info={<SqlInfo k={b.kaynaklar} alan="signals.odeme_12ay" label="Son ödeme" />}
              v={s.son_odeme_tarihi ? `${fmtDay(s.son_odeme_tarihi)} (${daysAgo(s.son_odeme_tarihi, today)} gün)` : '—'}
            />
            <KV k="Son 12 ayda ödeme" info={<SqlInfo k={b.kaynaklar} alan="signals.odeme_12ay" label="12 ayda ödeme" />} v={fmtMoney(s.odeme_12ay)} />
            <KV
              k="Çek/senet olayı (12 ay)"
              info={<SqlInfo k={b.kaynaklar} alan="signals.karsiliksiz_olay_12ay" label="Çek/senet olayı" />}
              v={`${s.karsiliksiz_olay_12ay ?? 0} karşılıksız · ${s.protesto_olay_12ay ?? 0} protesto`}
              tone={(s.karsiliksiz_olay_12ay ?? 0) + (s.protesto_olay_12ay ?? 0) > 0 ? 'err' : undefined}
            />
            <KV k="Risk / limit (CRM)" info={<><Explain label="Risk / limit">Soldaki rakam müşterinin CRM'deki toplam risk tutarı, sağdaki ona tanınan kredi limitidir.</Explain><SqlInfo k={b.kaynaklar} alan="signals.risk_toplam" label="Risk ve limit" /></>} v={`${fmtMoney(s.risk_toplam)} / ${fmtMoney(s.limit_toplam)}`} />
            <KV k="Limit doluluğu" info={<><Explain label="Limit doluluğu">Riskin limite oranı. %75'i geçince turuncu, %90'ı geçince kırmızı yazar; limit dolunca yeni siparişler CRM'de risk onayına takılabilir.</Explain><SqlInfo k={b.kaynaklar} alan="signals.risk_doluluk" label="Limit doluluğu" /></>} v={fmtPct(s.risk_doluluk)} tone={(s.risk_doluluk ?? 0) >= 0.9 ? 'err' : (s.risk_doluluk ?? 0) >= 0.75 ? 'warn' : undefined} />
            {b.odemeler.length > 0 && (
              <div className="mt-2">
                <div className="flex items-center gap-1 text-[11px] font-bold uppercase tracking-wide text-canvas-muted">
                  Son ödemeler (Logo)
                  <SqlInfo k={b.kaynaklar} alan="odemeler" label="Son ödemeler" />
                </div>
                <ul className="mt-1 flex flex-col">
                  {b.odemeler.map((o, i) => (
                    <li key={i} className="flex justify-between gap-2 py-0.5 text-[12px]">
                      <span className="text-canvas-muted">{fmtDay(o.tarih)}</span>
                      <span className="font-mono font-bold tabular-nums">{fmtMoney(o.tutar)}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
            <div className="mt-3">
              <div className="flex items-center gap-1 text-[11px] font-bold uppercase tracking-wide text-canvas-muted">
                CRM tahsilat kayıtları
                <SqlInfo k={b.kaynaklar} alan="tahsilatlar" label="CRM tahsilat kayıtları" />
              </div>
              {b.tahsilatlar.length === 0 ? (
                <p className="mt-1 text-[12px] text-canvas-muted">Son dönemde CRM'e girilmiş tahsilat yok.</p>
              ) : (
                <ul className="mt-1 flex flex-col gap-1.5">
                  {b.tahsilatlar.map((t) => (
                    <li key={t.id ?? t.ad} className="rounded-xl bg-slate-50 px-2.5 py-1.5 text-[12px]">
                      <div className="flex items-baseline justify-between gap-2">
                        <span className="min-w-0 truncate font-bold">
                          {t.tip ?? 'Tahsilat'} · {fmtDay(t.olusturma)}
                        </span>
                        <span className="shrink-0 font-mono font-bold tabular-nums">{fmtMoney(t.tutar)}</span>
                      </div>
                      <div className="mt-0.5 flex flex-wrap items-center gap-1.5">
                        <Pill tone={t.durum === 100000002 ? 'err' : t.durum === 100000000 ? 'warn' : 'ok'}>{t.durumAd}</Pill>
                        {t.redSebebi && <span className="text-red-700">{t.redSebebi}</span>}
                        {t.redMetni && <span className="text-red-700">— {t.redMetni}</span>}
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </div>
            {b.sahaTahsilat.length > 0 && (
              <div className="mt-3">
                <div className="flex items-center gap-1 text-[11px] font-bold uppercase tracking-wide text-canvas-muted">
                  Saha uygulamasına girilen tahsilat
                  <SqlInfo k={b.kaynaklar} alan="sahaTahsilat" label="Saha uygulaması tahsilatı" />
                </div>
                <ul className="mt-1">
                  {b.sahaTahsilat.map((t, i) => (
                    <li key={`${t.no}-${i}`} className="flex justify-between gap-2 py-0.5 text-[12px]">
                      <span className="min-w-0 truncate text-canvas-muted">
                        {fmtDay(t.tarih)} · {t.tur ?? '—'}
                      </span>
                      <span className="shrink-0 font-mono font-bold tabular-nums">{fmtMoney(t.tutar)}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
            <div id="odeme-plani" className="mt-3 scroll-mt-20">
              <div className="text-[11px] font-bold uppercase tracking-wide text-canvas-muted">Ödeme planları</div>
              {b.odemePlanlari.length === 0 ? (
                <p className="mt-1 text-[12px] text-canvas-muted">Kayıtlı ödeme planı yok.</p>
              ) : (
                <ul className="mt-1 flex flex-col gap-2">
                  {b.odemePlanlari.map((p) => (
                    <PlanCard key={p.id} p={p} meta={m} compact k={b.kaynaklar} alan="odemePlanlari" />
                  ))}
                </ul>
              )}
            </div>
          </Block>

          <Block
            id="siparis"
            title="Sipariş"
            help="Son faturalar Logo'dan; siparişler ve risk onayı CRM'den (son 6 ay)."
            action={
              <span className="flex items-center gap-1 text-[11px] font-semibold text-canvas-muted">
                Fatura
                <SqlInfo k={b.kaynaklar} alan="faturalar" label="Son faturalar" />
                Sipariş
                <SqlInfo k={b.kaynaklar} alan="siparisler" label="CRM siparişleri" />
              </span>
            }
          >
            {b.faturalar.length === 0 ? (
              <p className="text-[12px] text-canvas-muted">Bu yıl ve geçen yıl satış faturası yok.</p>
            ) : (
              <ul className="flex flex-col">
                {b.faturalar.map((f, i) => (
                  <li key={`${f.no}-${i}`} className="flex justify-between gap-2 border-b border-slate-100 py-1.5 text-[12.5px] last:border-0">
                    <span className="min-w-0 truncate">
                      {fmtDay(f.tarih)} <span className="text-canvas-muted">· {f.no}</span>
                    </span>
                    <span className="shrink-0 font-mono font-bold tabular-nums">{fmtMoney(f.tutar)}</span>
                  </li>
                ))}
              </ul>
            )}
            {b.siparisler.length > 0 && (
              <ul className="mt-2 flex flex-col gap-1.5">
                {b.siparisler.map((o, i) => (
                  <li key={`${o.no}-${i}`} className={`rounded-xl px-2.5 py-1.5 text-[12px] ${o.riskte ? 'bg-red-50' : 'bg-slate-50'}`}>
                    <div className="flex items-baseline justify-between gap-2">
                      <span className="min-w-0 truncate font-bold">
                        {o.no} · {fmtDay(o.tarih)}
                      </span>
                      <span className="shrink-0 font-mono font-bold tabular-nums">{fmtMoney(o.tutar)}</span>
                    </div>
                    <div className={o.riskte ? 'text-red-700' : 'text-canvas-muted'}>
                      {o.durum}
                      {o.sebep ? ` — ${o.sebep}` : ''}
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </Block>

          <Block
            id="hedef"
            title="Hedef"
            help={
              s.hedef_kaynagi === 'm46'
                ? 'Yürürlükteki bütçe planı, carilere önceki yılın net alım payıyla dağıtılır.'
                : s.hedef_kaynagi === 'crm'
                  ? "CRM'deki cari yıl hedefi."
                  : 'Bu cari için hedef yok (onaylı bütçe planı ya da CRM hedefi yok).'
            }
          >
            <KV k="Yıl başından net alım" info={<SqlInfo k={b.kaynaklar} alan="signals.ytd_net_ciro" label="Yıl başından net alım" />} v={fmtMoney(s.ytd_net_ciro)} />
            <KV k="Geçen yılın aynı dönemi" info={<SqlInfo k={b.kaynaklar} alan="signals.gecen_yil_ayni_donem" label="Geçen yılın aynı dönemi" />} v={fmtMoney(s.gecen_yil_ayni_donem)} />
            <KV k="Geçen yıl toplam" info={<SqlInfo k={b.kaynaklar} alan="signals.gecen_yil_tam" label="Geçen yıl toplam" />} v={fmtMoney(s.gecen_yil_tam)} />
            <KV k="İade oranı" info={<SqlInfo k={b.kaynaklar} alan="signals.iade_orani" label="İade oranı" />} v={fmtPct(s.iade_orani)} />
            {s.hedef_beklenen !== null && <KV k="Bugüne kadar beklenen" info={<SqlInfo k={b.kaynaklar} alan="signals.hedef_beklenen" label="Beklenen" />} v={fmtMoney(s.hedef_beklenen)} />}
            {s.hedef_acigi !== null && <KV k="Hedef açığı" info={<><Explain label="Hedef açığı">Bugüne kadar beklenen alımın ne kadarının eksik kaldığı. %20'yi geçerse kırmızı yazar.</Explain><SqlInfo k={b.kaynaklar} alan="signals.hedef_acigi" label="Hedef açığı" /></>} v={fmtPct(s.hedef_acigi)} tone={(s.hedef_acigi ?? 0) > 0.2 ? 'err' : undefined} />}
            {b.hedefKitaplar.length > 0 && <GapList brief={b} />}
          </Block>

          <Block id="oneri" title="Önerilecek kitaplar" help={b.oneriKurali} action={<SqlInfo k={b.kaynaklar} alan="oneriler" label="Önerilecek kitaplar" />}>
            <SuggestionList brief={b} />
          </Block>

          <Block
            id="notlar"
            title="Görüşme notları"
            help="Ziyaret ve not portalda kalır; CRM'e aktarılmaz. Gizli not yalnız yazana görünür."
            action={<SqlInfo k={b.kaynaklar} alan="ziyaretler" label="Görüşme notları ve ödeme sözleri" />}
          >
            <div className="mb-2">
              <NoteSignalCard code={b.code} screen="saha" />
            </div>
            {b.ziyaretler.length === 0 ? (
              <p className="text-[12px] text-canvas-muted">Henüz not yok. Alttaki «Not bırak» ile ilk görüşme notunu yazabilirsiniz.</p>
            ) : (
              <ul className="flex flex-col gap-2">
                {b.ziyaretler.map((v) => (
                  <li key={v.id} className="rounded-xl bg-slate-50 px-3 py-2 text-[12.5px]">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <span className="font-bold">
                        {fmtDay(v.gerceklesen || v.planlanan)} · {v.sahip}
                      </span>
                      <span className="flex items-center gap-1">
                        {v.ton && <Pill tone={v.ton === 'olumlu' ? 'ok' : v.ton === 'olumsuz' ? 'err' : 'muted'}>{m.tones.find((t) => t.key === v.ton)?.label ?? v.ton}</Pill>}
                        <Pill tone={v.durum === 'yapildi' ? 'ok' : 'muted'}>{v.durumAd}</Pill>
                      </span>
                    </div>
                    {v.gizliNot ? <p className="mt-1 italic text-canvas-muted">Gizli not</p> : v.notu && <p className="mt-1 whitespace-pre-wrap leading-snug">{v.notu}</p>}
                    {v.sonrakiAdim && (
                      <p className="mt-1 text-canvas-muted">
                        Sonraki adım: {v.sonrakiAdim}
                        {v.sonrakiTarih ? ` (${fmtDay(v.sonrakiTarih)})` : ''}
                      </p>
                    )}
                    {v.sozOdemeTarihi && (
                      <p className="mt-1 text-canvas-muted">
                        Ödeme sözü: {fmtDay(v.sozOdemeTarihi)}
                        {v.sozOdemeTutari ? ` · ${fmtMoney(v.sozOdemeTutari)}` : ''}
                      </p>
                    )}
                    {v.sahip === m.me.username && (
                      <div className="mt-1.5 flex flex-wrap gap-1.5">
                        {v.durum === 'planlandi' && m.me.canNote && (
                          <button type="button" className={`${btnGhost} !min-h-9 !bg-white`} onClick={() => setSheet({ mode: 'not', visit: v })}>
                            Not yaz
                          </button>
                        )}
                        {v.durum === 'yapildi' && m.me.canNote && b.zekiVar && (
                          <button type="button" className={`${btnGhost} !min-h-9 !bg-white`} disabled={followup.isPending} onClick={() => followup.mutate(v.id)}>
                            {followup.isPending && followup.variables === v.id && <Loader2 aria-hidden className="h-4 w-4 animate-spin" />}
                            Takip e-postası taslağı yaz
                          </button>
                        )}
                      </div>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </Block>

          <div className="sticky bottom-1 z-20 mx-auto grid w-full max-w-[640px] grid-cols-4 gap-1 rounded-2xl border border-slate-200 bg-white/95 p-1 shadow-glass-float backdrop-blur">
            <BarButton icon={<NotebookPen aria-hidden className="h-5 w-5" />} label="Not bırak" disabled={!m.me.canNote} onClick={() => setSheet({ mode: 'not' })} />
            <BarButton icon={<CalendarPlus aria-hidden className="h-5 w-5" />} label="Planla" disabled={!m.me.canNote} onClick={() => setSheet({ mode: 'plan' })} />
            <BarButton
              icon={plan.isPending ? <Loader2 aria-hidden className="h-5 w-5 animate-spin" /> : <HandCoins aria-hidden className="h-5 w-5" />}
              label="Ödeme planı"
              disabled={!m.me.canNote || (s.vadesi_gecmis ?? 0) <= 0 || plan.isPending}
              onClick={() => plan.mutate()}
            />
            <BarButton icon={<Pin aria-hidden className="h-5 w-5" />} label="Öne al" disabled={!m.me.canOverride} onClick={() => setAsk('boost')} />
          </div>
        </div>
      )}
      {!b && !q.isLoading && !err && <Empty title="Müşteri brifingi bulunamadı">Bu cari kodu için brifing verisi yok. «Bugün» listesinden müşteriyi yeniden seçin.</Empty>}

      {sheet && b && (
        <VisitNoteSheet open onClose={() => setSheet(null)} code={b.code} unvan={b.unvan} mode={sheet.mode} visit={sheet.visit} />
      )}
      <AskSheet
        open={ask === 'boost'}
        title="Müşteriyi öne al"
        message="Müşteri temsilcinin listesinde «Müdür önceliği» gerekçesiyle üste çıkar. Neden listede görünür."
        confirm="Öne al"
        input="Neden"
        required
        busy={boost.isPending}
        onClose={() => setAsk(null)}
        onConfirm={(t) => boost.mutate(t)}
      />
      <Sheet open={draft !== null} modal onClose={() => setDraft(null)} title="Takip e-postası taslağı" subtitle="Portal göndermez; kendi e-postanızdan düzenleyip gönderin.">
        <div className="flex flex-col gap-3">
          <textarea className={`${field} min-h-[220px]`} value={draft ?? ''} onChange={(e) => setDraft(e.target.value)} />
          <div className="flex justify-end gap-2">
            <button type="button" className={btnGhost} onClick={() => setDraft(null)}>
              Kapat
            </button>
            <button
              type="button"
              className={btnPrimary}
              onClick={() => {
                void copyText(draft ?? '').then((ok) => (ok ? toast.success('Kopyalandı') : toast.error('Kopyalanamadı; metni seçip kopyalayın.')));
              }}
            >
              <Copy aria-hidden className="h-4 w-4" />
              Kopyala
            </button>
          </div>
        </div>
      </Sheet>
    </FieldFrame>
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

function GapList({ brief }: { brief: Brief }) {
  const [all, setAll] = useState(false);
  const rows = all ? brief.hedefKitaplar : brief.hedefKitaplar.slice(0, 5);
  return (
    <div className="mt-3">
      <div className="flex items-center gap-1 text-[11px] font-bold uppercase tracking-wide text-canvas-muted">
        Hedef açığı en büyük kitaplar
        <SqlInfo k={brief.kaynaklar} alan="hedefKitaplar" label="Kitap hedef açığı" />
      </div>
      {brief.hedefKurali && <p className="mt-0.5 text-[11px] leading-snug text-canvas-muted">{brief.hedefKurali}</p>}
      <ul className="mt-1 flex flex-col gap-1">
        {rows.map((g) => (
          <li key={g.stok} className="rounded-xl bg-slate-50 px-2.5 py-1.5 text-[12px]">
            <div className="flex items-baseline justify-between gap-2">
              <span className="min-w-0 truncate font-bold">{g.ad || g.stok}</span>
              <span className="shrink-0 font-mono font-bold tabular-nums text-red-700">{fmtMoney(g.acikCiro)}</span>
            </div>
            <div className="text-canvas-muted">
              Beklenen {Math.round(g.beklenen)} · alınan {Math.round(g.gerceklesen)} adet · açık {Math.round(g.acikAdet)}
            </div>
          </li>
        ))}
      </ul>
      {brief.hedefKitaplar.length > 5 && (
        <button type="button" className={`${btnGhost} mt-2 w-full`} onClick={() => setAll(!all)}>
          {all ? 'İlk 5' : `Hepsini göster (${brief.hedefKitaplar.length})`}
        </button>
      )}
    </div>
  );
}

function SuggestionList({ brief }: { brief: Brief }) {
  const [all, setAll] = useState(false);
  if (brief.oneriler.length === 0) return <p className="text-[12px] text-canvas-muted">Öneri çıkmadı (benzer cari bulunamadı ya da hepsini zaten alıyor).</p>;
  const rows = all ? brief.oneriler : brief.oneriler.slice(0, 5);
  return (
    <>
      <ul className="flex flex-col gap-1">
        {rows.map((x) => (
          <li key={x.stok} className="rounded-xl bg-slate-50 px-2.5 py-1.5 text-[12px]">
            <div className="flex items-baseline justify-between gap-2">
              <span className="min-w-0 truncate font-bold">{x.ad || x.stok}</span>
              {x.yeni && <Pill tone="violet">Yeni</Pill>}
            </div>
            <div className="text-canvas-muted">{x.neden.join(' · ')}</div>
          </li>
        ))}
      </ul>
      {brief.oneriler.length > 5 && (
        <button type="button" className={`${btnGhost} mt-2 w-full`} onClick={() => setAll(!all)}>
          {all ? 'İlk 5' : `Hepsini göster (${brief.oneriler.length})`}
        </button>
      )}
    </>
  );
}

async function copyText(t: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(t);
    return true;
  } catch {
    // http'de (müşteri ağı) pano API'si kapalı: seçili alan yoluyla.
    const el = document.createElement('textarea');
    el.value = t;
    el.setAttribute('readonly', '');
    el.style.position = 'fixed';
    el.style.opacity = '0';
    document.body.appendChild(el);
    el.select();
    const ok = document.execCommand('copy');
    document.body.removeChild(el);
    return ok;
  }
}
