import { useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Loader2, NotebookPen, Phone, Sparkles } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import { Loading, Note, btnGhost, btnPrimary, errText } from '../admin/ui';
import { Block, Chips, Empty, FieldFrame, KV } from '../field/parts';
import { fmtDay, fmtMoney, fmtPct, fmtShort } from '../field/api';
import { INTERVAL_SOURCE, barHeights, fmtChange, fmtMonth, musteriApi, type Action } from './api';
import { ActionItem, ActionSheet, LevelBadge } from './parts';
import { useMusteriMeta } from './CustomersHome';
import NoteSignalCard from '../signals/NoteSignalCard';
import SqlInfo from '../components/SqlInfo';

/** Cari ayrıntısı: risk ve nedeni (2 dokunuş: liste → cari), aylık alım grafiği, aksiyon geçmişi (aksiyon yazmak 3 dokunuş),
 *  kitap dağılımı, CRM siparişleri, ziyaretler (M30 ortak kaydı), tahsilat göstergesi (M30). Arama yalnız portföy sahibine:
 *  numara CRM'den o an okunur ve telefonun kendi uygulamasıyla aranır. */

export default function AccountDetail() {
  const { kod = '' } = useParams();
  const qc = useQueryClient();
  const meta = useMusteriMeta();
  const q = useQuery({ queryKey: ['musteri', 'account', kod], queryFn: () => musteriApi.account(kod), enabled: ENGINE_ENABLED && !!kod });
  const months = useQuery({ queryKey: ['musteri', 'monthly', kod], queryFn: () => musteriApi.monthly(kod), enabled: ENGINE_ENABLED && !!kod });
  const [sheet, setSheet] = useState<null | { edit: Action | null }>(null);
  const [tel, setTel] = useState<string | null | undefined>(undefined);
  const a = q.data;
  const m = meta.data;

  const summary = useMutation({
    mutationFn: () => musteriApi.summary(kod),
    onSuccess: (r) => {
      if (r.not) toast.warning(r.not);
      void qc.invalidateQueries({ queryKey: ['musteri', 'account', kod] });
    },
    onError: (e) => toast.error(errText(e, 'Özet yazılamadı.') ?? 'Özet yazılamadı.'),
  });
  const phone = useMutation({
    mutationFn: () => musteriApi.phone(kod),
    onSuccess: (r) => setTel(r.telefon),
    onError: (e) => toast.error(errText(e, 'Telefon okunamadı.') ?? 'Telefon okunamadı.'),
  });

  const err = errText(q.error, 'Cari açılamadı.');
  const series = months.data?.items ?? [];
  const heights = barHeights(series.map((x) => x.net));

  return (
    <FieldFrame
      crumb="Müşteri ilişkileri"
      title={a?.ad || kod}
      source={a?.kesim ? `Logo ${fmtDay(a.kesim)} tarihine kadar · CRM canlı` : 'Logo + CRM'}
      presence={a?.duzeyAd ? `Risk: ${a.duzeyAd}` : 'Cari'}
      back={{ to: '/musteri-iliskileri/cariler', label: 'Cariler' }}
    >
      {q.isLoading && <Loading />}
      {err && <Note tone="err">{err}</Note>}
      {a && m && (
        <div className="flex flex-col gap-3">
          <div className="flex items-start gap-3 px-1">
            <LevelBadge level={a.duzey} label={a.duzeyAd} puan={a.puan} />
            <div className="min-w-0 flex-1">
              <div className="text-[12px] text-canvas-muted">
                {[a.code, a.logoKanal || a.kanal, a.bolge, a.temsilciAd ? `Temsilci ${a.temsilciAd}` : 'temsilcisi yok', a.segment].filter(Boolean).join(' · ')}
              </div>
              <div className="mt-1.5">
                <Chips chips={a.nedenler} />
              </div>
            </div>
          </div>
          {a.warnings.map((w) => (
            <Note key={w} tone="warn">
              {w}
            </Note>
          ))}

          <section className="rounded-2xl border border-canvas-violet/20 bg-canvas-violet/5 p-3" aria-label="Neden">
            <div className="flex items-center justify-between gap-2">
              <div className="flex items-center gap-1.5 text-[12px] font-extrabold text-canvas-violet">
                <Sparkles aria-hidden className="h-4 w-4" />
                {a.ozetKaynagi === 'zeki' ? 'Zeki AI özeti' : 'Neden'}
              </div>
              {a.nedenler.length > 0 && a.ozetKaynagi !== 'zeki' && (
                <button type="button" className={`${btnGhost} !min-h-9 !bg-white/80`} disabled={summary.isPending} onClick={() => summary.mutate()}>
                  {summary.isPending && <Loader2 aria-hidden className="h-4 w-4 animate-spin" />}
                  Zeki AI yazsın
                </button>
              )}
            </div>
            <p className="mt-1.5 text-[13px] leading-snug">{a.ozet || 'Belirgin bir kayıp işareti yok.'}</p>
          </section>

          <div className="grid grid-cols-2 gap-2 sm:flex sm:flex-wrap">
            {m.me.canAction && (
              <button type="button" className={`${btnPrimary} sm:flex-none`} onClick={() => setSheet({ edit: null })}>
                <NotebookPen aria-hidden className="h-4 w-4" />
                Aksiyon yaz
              </button>
            )}
            {a.sahibim &&
              (tel ? (
                <a className={`${btnGhost} sm:flex-none`} href={`tel:${tel.replace(/[^\d+]/g, '')}`}>
                  <Phone aria-hidden className="h-4 w-4" />
                  {tel}
                </a>
              ) : (
                <button type="button" className={`${btnGhost} sm:flex-none`} disabled={phone.isPending || tel === null} onClick={() => phone.mutate()}>
                  <Phone aria-hidden className="h-4 w-4" />
                  {tel === null ? 'CRM\'de telefon yok' : 'Ara'}
                </button>
              ))}
          </div>

          <Block title="Değer ve alım" help={`Faturalı satır, satış − iade. Pencere Logo kesimi (${fmtDay(a.kesim)}) ile biter.`} action={<SqlInfo k={a.kaynaklar} alan="net12" label="Değer ve alım" />}>
            <KV k="Son 12 ay net" info={<SqlInfo k={a.kaynaklar} alan="net12" label="Son 12 ay net" />} v={fmtMoney(a.net12)} />
            <KV k="Önceki 12 ay net" info={<SqlInfo k={a.kaynaklar} alan="netOnceki" label="Önceki 12 ay net" />} v={fmtMoney(a.netOnceki)} />
            <KV k="Değişim" info={<SqlInfo k={a.kaynaklar} alan="degisim" label="Değişim" />} v={fmtChange(a.degisim)} tone={a.degisim !== null && a.degisim < -0.1 ? 'err' : undefined} />
            <KV k="Bu yıl net" info={<SqlInfo k={a.kaynaklar} alan="netYil" label="Bu yıl net" />} v={fmtMoney(a.netYil)} />
            <KV k="Son 12 ay fatura" info={<SqlInfo k={a.kaynaklar} alan="fatura12" label="Son 12 ay fatura" />} v={a.fatura12 ?? '—'} />
            <KV k="Son fatura" v={fmtDay(a.sonFatura)} />
            <KV k="Son alımdan bu yana" info={<SqlInfo k={a.kaynaklar} alan="gunSonAlim" label="Son alımdan bu yana" />} v={a.gunSonAlim === null ? '—' : `${a.gunSonAlim} gün`} tone={a.duzey === 'kayip' ? 'err' : undefined} />
            <KV info={<SqlInfo k={a.kaynaklar} alan="aralik" label="Olağan alım aralığı" />} k={`Olağan alım aralığı${a.aralikKaynagi ? ` (${INTERVAL_SOURCE[a.aralikKaynagi]})` : ''}`} v={a.aralik === null ? '—' : `${Math.round(a.aralik)} gün`} />
            <KV k="İade oranı (12 ay / önceki)" info={<SqlInfo k={a.kaynaklar} alan="iade12" label="İade oranı" />} v={`${fmtPct(a.iade12)} / ${fmtPct(a.iadeOnceki)}`} />
            <KV k="CRM son sipariş" v={fmtDay(a.sonSiparis)} />
            <KV k="Son ziyaret" v={fmtDay(a.sonZiyaret)} />
          </Block>

          <Block title="Aylık net alım" help="Son 24 ay; iade fazlası olan ay boş çubuk." action={<SqlInfo k={months.data?.kaynaklar} alan="items" label="Aylık net alım" />}>
            {months.isLoading ? (
              <Loading />
            ) : series.length === 0 ? (
              <Empty>Aylık veri okunamadı.</Empty>
            ) : (
              <div
                role="img"
                aria-label={`Son 24 ay aylık net alım; en yüksek ${fmtShort(Math.max(...series.map((x) => x.net)))}`}
                className="flex h-36 items-end gap-[2px] sm:gap-1"
              >
                {series.map((x, i) => (
                  <div key={x.ay} className="flex h-full min-w-0 flex-1 flex-col items-center justify-end" title={`${fmtMonth(x.ay)}: ${fmtMoney(x.net)}`}>
                    <div className={`w-full rounded-t ${x.net < 0 ? 'bg-red-200' : 'bg-canvas-violet/70'}`} style={{ height: `${Math.max(x.net !== 0 ? 2 : 0, heights[i] * 100)}%` }} />
                    <span className="mt-1 h-3 text-[9px] leading-none text-canvas-muted">{i % 3 === 2 ? fmtMonth(x.ay).split(' ')[0] : ''}</span>
                  </div>
                ))}
              </div>
            )}
          </Block>

          <Block
            title="Aksiyonlar"
            help="Yazılan aksiyon ve 30/90 gün sonra ölçülen alım."
            action={
              <span className="flex items-center gap-1">
                <SqlInfo k={a.kaynaklar} alan="aksiyonlar" label="Aksiyonlar ve sonuçları" />
                {m.me.canAction ? (
                  <button type="button" className={`${btnGhost} !min-h-9`} onClick={() => setSheet({ edit: null })}>
                    Yeni
                  </button>
                ) : null}
              </span>
            }
          >
            {a.aksiyonlar.length === 0 ? (
              <Empty>Henüz aksiyon yok.</Empty>
            ) : (
              <ul className="flex flex-col gap-2">
                {a.aksiyonlar.map((x) => (
                  <ActionItem key={x.id} a={x} onEdit={m.me.canAction ? (it) => setSheet({ edit: it }) : undefined} />
                ))}
              </ul>
            )}
          </Block>

          {a.tahsilat && (
            <Block
              title="Tahsilat ve kredi göstergesi"
              help={`Saha ve tahsilat ekranının gece rakamı (${fmtDay(a.tahsilat.asof)}); kredi kararı bu ekranın işi değil.`}
              action={
                <Link className="text-[12px] font-extrabold text-canvas-violet hover:underline" to={`/saha/musteri/${encodeURIComponent(a.code)}`}>
                  Brifing
                </Link>
              }
            >
              <KV k="Bakiye" info={<SqlInfo k={a.kaynaklar} alan="tahsilat" label="Saha tahsilat sinyali" />} v={fmtMoney(a.tahsilat.bakiye)} />
              <KV k="Vadesi geçmiş (yaklaşık)" v={fmtMoney(a.tahsilat.vadesi_gecmis)} tone={(a.tahsilat.vadesi_gecmis ?? 0) > 0 ? 'err' : undefined} />
              <KV k="Risk limiti doluluğu" v={fmtPct(a.tahsilat.risk_doluluk)} />
              <KV k="Son ödeme" v={fmtDay(a.tahsilat.son_odeme_tarihi)} />
            </Block>
          )}

          <Block title="Kitaplar (son 12 ay)" help="Kitap başına net adet ve net tutar, en çok alınan üstte." action={<SqlInfo k={a.kaynaklar} alan="kitaplar" label="Kitap başına alım" />}>
            {a.kitaplar.length === 0 ? (
              <Empty>Son 12 ayda kitap alımı yok.</Empty>
            ) : (
              <ul className="flex flex-col">
                {a.kitaplar.slice(0, 15).map((b) => (
                  <li key={b.stok} className="flex items-baseline justify-between gap-3 border-b border-slate-100 py-1.5 text-[12.5px] last:border-0">
                    <span className="min-w-0 truncate">{b.ad || b.stok}</span>
                    <span className="shrink-0 font-mono font-bold tabular-nums">
                      {Math.round(b.adet).toLocaleString('tr-TR')} ad · {fmtShort(b.ciro)}
                    </span>
                  </li>
                ))}
                {a.kitaplar.length > 15 && <li className="pt-1.5 text-[11.5px] text-canvas-muted">+{a.kitaplar.length - 15} kitap daha</li>}
              </ul>
            )}
          </Block>

          <Block title="Siparişler (CRM, son 12 ay)" action={<SqlInfo k={a.kaynaklar} alan="siparisler" label="CRM siparişleri" />}>
            {a.siparisler.length === 0 ? (
              <Empty>CRM'de son 12 ayda sipariş yok.</Empty>
            ) : (
              <ul className="flex flex-col">
                {a.siparisler.map((o, i) => (
                  <li key={`${o.no}-${i}`} className="flex items-baseline justify-between gap-3 border-b border-slate-100 py-1.5 text-[12.5px] last:border-0">
                    <span className="min-w-0 truncate">
                      {fmtDay(o.tarih)} · {o.no || '—'} · <span className={o.riskte ? 'font-bold text-red-700' : 'text-canvas-muted'}>{o.durum}</span>
                    </span>
                    <span className="shrink-0 font-mono font-bold tabular-nums">{fmtShort(o.tutar)}</span>
                  </li>
                ))}
              </ul>
            )}
          </Block>

          <Block title="Son faturalar (Logo)" action={<SqlInfo k={a.kaynaklar} alan="faturalar" label="Son faturalar" />}>
            {a.faturalar.length === 0 ? (
              <Empty>Fatura yok.</Empty>
            ) : (
              a.faturalar.map((x, i) => <KV key={`${x.no}-${i}`} k={`${fmtDay(x.tarih)} · ${x.no || '—'}`} v={fmtMoney(x.tutar)} />)
            )}
          </Block>

          <Block title="Ziyaretler" help="Saha ekranıyla ortak ziyaret kaydı.">
            <div className="mb-2">
              <NoteSignalCard code={kod} screen="musteri" />
            </div>
            {a.ziyaretler.length === 0 ? (
              <Empty>Kayıtlı ziyaret yok.</Empty>
            ) : (
              <ul className="flex flex-col gap-1.5">
                {a.ziyaretler.slice(0, 10).map((v) => (
                  <li key={v.id} className="rounded-xl bg-slate-50 px-3 py-2 text-[12.5px]">
                    <div className="text-[11px] font-bold text-canvas-muted">
                      {fmtDay(v.gerceklesen || v.planlanan)} · {v.sahip}
                    </div>
                    <div className="break-words">{v.gizliNot ? 'Gizli not' : v.notu || '—'}</div>
                  </li>
                ))}
              </ul>
            )}
          </Block>

          <ActionSheet open={!!sheet} onClose={() => setSheet(null)} code={a.code} ad={a.ad} meta={m} edit={sheet?.edit ?? null} />
        </div>
      )}
    </FieldFrame>
  );
}
