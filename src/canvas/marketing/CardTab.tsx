import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { RefreshCw } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import { Loading, Note, Pill, TableWrap, btnGhost, errText, td, th } from '../admin/ui';
import { fmtDay, fmtInt, fmtMoney, fmtShortDay, fmtStamp, mktApi, type Meta } from './api';
import { Block, SourceNote } from './parts';

const DATE_LABEL: Record<string, string> = {
  'crm-kitap': 'Kitap kartı',
  'crm-proje': 'Proje kartı',
  'uretim-dagilim': 'Üretim · dağılım planı',
  'uretim-depo': 'Üretim · depo girişi',
};

/** Kitap karnesi: künye, yayın günü (üç kaynak), hedef, emsallerin ilk 3/6/12 ayı, yazar geçmişi, rakipler, özel günler,
 *  CRM'deki bütçe ve metinler. Rakamların hepsi SQL'den ya da mevcut veri kümesinden; model üretmez. */
export default function CardTab({ stok, meta }: { stok: string; meta: Meta }) {
  const qc = useQueryClient();
  const card = useQuery({ queryKey: ['mkt', 'card', stok], queryFn: () => mktApi.card(stok), enabled: ENGINE_ENABLED });
  const refresh = useMutation({
    mutationFn: () => mktApi.card(stok, true),
    onSuccess: (d) => qc.setQueryData(['mkt', 'card', stok], d),
    onError: (e) => toast.error(errText(e, 'Karne yenilenemedi.') ?? ''),
  });
  if (card.isLoading) return <Loading />;
  if (card.error) return <Note tone="err">{errText(card.error, 'Karne açılamadı.')}</Note>;
  const c = card.data;
  if (!c) return null;
  const k = c.kitap;
  const em = c.emsal;
  const pj = c.crmButce;
  const years = c.yazar.yillar.map((y) => y.yil);

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center justify-between gap-2 px-1 text-[11.5px] text-canvas-muted">
        <span>
          Karne {fmtStamp(c.asof)} tarihinde hazırlandı · Logo verisi {fmtDay(c.veriSonu.logo)} tarihinde bitiyor
          {c.veriSonu.emsalAy ? ` · emsal verisi ${c.veriSonu.emsalAy} ayına kadar` : ''}
        </span>
        <button type="button" className={btnGhost} onClick={() => refresh.mutate()} disabled={refresh.isPending}>
          <RefreshCw aria-hidden className={`h-4 w-4 ${refresh.isPending ? 'animate-spin' : ''}`} />
          Karneyi yenile
        </button>
      </div>
      {c.uyarilar.map((u) => <Note key={u} tone="warn">{u}</Note>)}

      <Block title="Kitap ve yayın günü">
        <dl className="grid grid-cols-1 gap-x-6 gap-y-1.5 text-[12.5px] sm:grid-cols-2">
          {[
            ['Kitap', k.ad], ['Yazar', k.yazar], ['Yayınevi', k.yayinevi], ['Kitaplık', k.kitaplik], ['Hedef kitle', k.hedefKitle],
            ['Türler', k.turler], ['Kapak fiyatı', k.fiyat ? fmtMoney(k.fiyat) : null], ['Sayfa', k.sayfa ? fmtInt(k.sayfa) : null],
            ['Proje', k.projeAdi], ['Pazarlama sorumlusu (CRM)', k.sorumlu],
          ].map(([l, v]) => (
            <div key={l as string} className="flex min-w-0 gap-2">
              <dt className="w-[150px] shrink-0 text-canvas-muted">{l}</dt>
              <dd className="min-w-0 break-words font-semibold">{v || '—'}</dd>
            </div>
          ))}
        </dl>
        <div className="mt-3 flex flex-wrap gap-2">
          {Object.entries(c.yayin.tarihler).map(([key, v]) => {
            const used = key === c.yayin.kaynak || (c.yayin.kaynak === 'uretim' && key.startsWith('uretim') && v && (key === 'uretim-depo' || !c.yayin.tarihler['uretim-depo']));
            const label = DATE_LABEL[key] ?? key;
            return (
              <div key={key} className={`rounded-xl px-3 py-2 text-[12px] ${used ? 'bg-canvas-violet/10 ring-1 ring-canvas-violet' : 'bg-white/70'}`}>
                <div className="text-[11px] font-bold text-canvas-muted">{label}{used ? ' · esas' : ''}</div>
                <div className="font-semibold">{fmtShortDay(v)}</div>
              </div>
            );
          })}
        </div>
        <p className="mt-2 text-[11px] text-canvas-muted">Esas alınan sıra: {meta.settings.dateOrder.map((x) => meta.dateSources[x] ?? x).join(' → ')} (Yönetim → Pazarlama planları).</p>
      </Block>

      <Block title="Satış hedefi" help="Bütçe ve hedefler modülünün yürürlükteki planı.">
        {c.hedef.planId && c.hedef.adet != null ? (
          <div className="flex flex-wrap gap-4 text-[13px]">
            <div><span className="text-canvas-muted">Hedef adet</span> <strong className="font-mono">{fmtInt(c.hedef.adet)}</strong></div>
            {meta.me.canSeeBudget && <div><span className="text-canvas-muted">Hedef net ciro</span> <strong className="font-mono">{fmtMoney(c.hedef.ciro)}</strong></div>}
            <div><span className="text-canvas-muted">Plan</span> <strong>{c.hedef.year} · sürüm {c.hedef.version}</strong></div>
          </div>
        ) : (
          <Note tone="info">{c.hedef.not ?? 'Onaylı hedef yok.'}</Note>
        )}
      </Block>

      <Block
        title="Emsal kitaplar"
        help="CRM'de editörün girdiği emsaller ve ilk baskı tahmininin benzerlik puanıyla seçtiği kitaplar. Satış net adettir (iade düşülmüş), ilk yayın ayından itibaren."
      >
        {!em.hazir ? (
          <Note tone="info">{em.not}</Note>
        ) : (
          <>
            {em.tahmin && (
              <div className="mb-2 flex flex-wrap gap-2 text-[12px]">
                <Pill tone="violet">İlk baskı tahmini: ilk 6 ay {fmtInt(em.tahmin.baz6)} adet{em.tahmin.bant6 ? ` (${fmtInt(em.tahmin.bant6.low)}–${fmtInt(em.tahmin.bant6.high)})` : ''}</Pill>
                {em.tahmin.baz12 != null && <Pill tone="violet">ilk 12 ay {fmtInt(em.tahmin.baz12)} adet</Pill>}
                {em.tahmin.ilkBaski != null && <Pill tone="muted">önerilen ilk baskı {fmtInt(em.tahmin.ilkBaski)}</Pill>}
              </div>
            )}
            {em.gerceklesen && (
              <Note tone="info">Kitap {em.gerceklesen.lansman} ayında satışa çıkmış; gerçekleşen aylar: {em.gerceklesen.aylar.map(fmtInt).join(' · ')}</Note>
            )}
            {em.items.length ? (
              <TableWrap>
                <thead>
                  <tr className="border-b border-slate-100">
                    <th className={th}>Kitap</th><th className={th}>Neden</th><th className={th}>Lansman</th>
                    <th className={`${th} text-right`}>İlk 3 ay</th><th className={`${th} text-right`}>İlk 6 ay</th><th className={`${th} text-right`}>İlk 12 ay</th>
                  </tr>
                </thead>
                <tbody>
                  {em.items.map((e) => (
                    <tr key={e.stokKodu} className="border-b border-slate-50 last:border-0">
                      <td className={td}>
                        <div className="max-w-[300px] font-semibold leading-snug">{e.ad ?? e.stokKodu}</div>
                        <div className="text-[11px] text-canvas-muted">{[e.yazar, e.yayinevi].filter(Boolean).join(' · ')}</div>
                      </td>
                      <td className={`${td} text-[11px]`}>
                        <div className="flex max-w-[220px] flex-wrap gap-1">
                          {e.kaynak.map((x) => <Pill key={x} tone={x === 'CRM emsali' ? 'ok' : 'muted'}>{x}</Pill>)}
                        </div>
                        {e.nedenler.length > 0 && <div className="mt-0.5 text-canvas-muted">{e.nedenler.join(', ')}</div>}
                      </td>
                      <td className={`${td} whitespace-nowrap`}>{e.lansman ?? '—'}</td>
                      <td className={`${td} text-right font-mono tabular-nums`}>{fmtInt(e.ilk3)}</td>
                      <td className={`${td} text-right font-mono tabular-nums`}>{fmtInt(e.ilk6)}</td>
                      <td className={`${td} text-right font-mono tabular-nums`}>{fmtInt(e.ilk12)}</td>
                    </tr>
                  ))}
                </tbody>
              </TableWrap>
            ) : (
              <Note tone="info">Emsal bulunamadı: CRM'de emsal girilmemiş ve benzer kitap yok.</Note>
            )}
            <SourceNote text={em.kaynak} />
          </>
        )}
      </Block>

      {!em.crmEmsalSayisi && <EmsalCandidatesBlock stok={stok} />}

      <Block title={`Yazarın diğer kitapları${c.yazar.yazar ? ` · ${c.yazar.yazar}` : ''}`} help="Yıllık net adet ve net ciro Logo faturalı satıştır.">
        {c.yazar.not && <Note tone="info">{c.yazar.not}</Note>}
        {c.yazar.items.length ? (
          <TableWrap>
            <thead>
              <tr className="border-b border-slate-100">
                <th className={th}>Kitap</th><th className={th}>İlk yayın</th><th className={`${th} text-right`}>İlk 12 ay</th>
                {years.map((y) => <th key={y} className={`${th} text-right`}>{y}</th>)}
              </tr>
            </thead>
            <tbody>
              {c.yazar.items.map((b) => (
                <tr key={b.stokKodu} className="border-b border-slate-50 last:border-0">
                  <td className={td}><div className="max-w-[280px] font-semibold leading-snug">{b.ad ?? b.stokKodu}</div></td>
                  <td className={`${td} whitespace-nowrap`}>{fmtShortDay(b.ilkYayin)}</td>
                  <td className={`${td} text-right font-mono tabular-nums`}>{fmtInt(b.ilk12)}</td>
                  {years.map((y) => {
                    const v = b.yillik[String(y)];
                    return (
                      <td key={y} className={`${td} text-right font-mono tabular-nums`}>
                        {v ? <>{fmtInt(v.adet)}{meta.me.canSeeBudget && <div className="text-[10.5px] text-canvas-muted">{fmtMoney(v.ciro)}</div>}</> : '—'}
                      </td>
                    );
                  })}
                </tr>
              ))}
              <tr className="bg-slate-50/70 font-bold">
                <td className={td}>Toplam</td><td className={td} /><td className={td} />
                {c.yazar.yillar.map((y) => (
                  <td key={y.yil} className={`${td} text-right font-mono tabular-nums`}>
                    {fmtInt(y.adet)}{meta.me.canSeeBudget && <div className="text-[10.5px] text-canvas-muted">{fmtMoney(y.ciro)}</div>}
                  </td>
                ))}
              </tr>
            </tbody>
          </TableWrap>
        ) : !c.yazar.not ? <Note tone="info">Yazarın başka kitabı bulunamadı.</Note> : null}
        <SourceNote text={c.yazar.kaynak} sql={c.yazar.sql} />
      </Block>

      {meta.me.canSeeBudget && pj && (
        <Block title="CRM'deki bütçe ve öncelik" help="Proje kartında yayın kurulunda girilen değerler (yalnız okunur).">
          <dl className="grid grid-cols-2 gap-x-6 gap-y-1.5 text-[12.5px] sm:grid-cols-3">
            {[
              ['Toplam pazarlama (kurul)', pj.toplamKurul], ['Toplam pazarlama', pj.toplam], ['Basın', pj.basin], ['Kampanya', pj.kampanya],
              ['İnternet', pj.internet], ['Okul', pj.okul], ['Prestij', pj.prestij],
            ].map(([l, v]) => (
              <div key={l as string} className="flex flex-col">
                <dt className="text-[11px] text-canvas-muted">{l}</dt>
                <dd className="font-mono font-semibold tabular-nums">{typeof v === 'number' ? fmtMoney(v) : '—'}</dd>
              </div>
            ))}
            <div className="flex flex-col">
              <dt className="text-[11px] text-canvas-muted">Pazarlama önceliği</dt>
              <dd className="font-mono font-semibold">{typeof pj.oncelik === 'number' ? `%${pj.oncelik}` : '—'}</dd>
            </div>
          </dl>
          {typeof pj.ayrinti === 'string' && pj.ayrinti && <p className="mt-2 whitespace-pre-line text-[12px] leading-snug">{pj.ayrinti}</p>}
        </Block>
      )}

      {c.rakipler.length > 0 && (
        <Block title="Rakip kitaplar" help="CRM «Rakip Kitap» kayıtları; satış adedinin kaynağı CRM'e girilen değerdir.">
          <ul className="flex flex-col gap-2">
            {c.rakipler.map((r, i) => (
              <li key={`${r.ad}-${i}`} className="rounded-xl bg-white/70 p-2.5 text-[12px]">
                <div className="font-semibold">{r.ad ?? '—'} <span className="font-normal text-canvas-muted">· {[r.yazarlar, r.yayinevi].filter(Boolean).join(' · ')}</span></div>
                <div className="text-[11px] text-canvas-muted">
                  {r.satisAdedi != null ? `Satış adedi (CRM): ${fmtInt(r.satisAdedi)}` : ''}{r.listeFiyati ? ` · liste fiyatı ${fmtMoney(r.listeFiyati)}` : ''}
                </div>
                {r.tanitim && <p className="mt-1 line-clamp-3 leading-snug">{r.tanitim}</p>}
              </li>
            ))}
          </ul>
        </Block>
      )}

      {c.ozelGunler.length > 0 && (
        <Block title="Bağlı özel günler" help="Tarih, SEO sezon takviminin yöntemiyle (kural, CRM tarihi ya da hafta) hesaplandı; takvime iş olarak eklenir.">
          <ul className="flex flex-col gap-1 text-[12.5px]">
            {c.ozelGunler.map((d) => (
              <li key={`${d.ad}-${d.baslangic}`} className="flex flex-wrap items-center justify-between gap-2">
                <span className="font-semibold">{d.ad}</span>
                <span className="text-canvas-muted">{d.baslangic ? `${fmtShortDay(d.baslangic)}${d.bitis && d.bitis !== d.baslangic ? ` – ${fmtShortDay(d.bitis)}` : ''}` : 'tarih bilinmiyor'} · {d.yontem}</span>
              </li>
            ))}
          </ul>
        </Block>
      )}

      <Block title="CRM'deki metinler" help="Kitap kartında yazılı olanlar; plan açılırken ilgili materyal taslağına kaynağıyla alınır, yeniden yazılmaz.">
        {c.metinler.length ? (
          <div className="flex flex-col gap-2">
            {c.metinler.map((t) => (
              <details key={t.alan} className="rounded-xl bg-white/70 p-2.5">
                <summary className="flex min-h-8 cursor-pointer items-center text-[12.5px] font-semibold">{t.ad}</summary>
                <p className="mt-1 whitespace-pre-line text-[12px] leading-snug">{t.metin}</p>
              </details>
            ))}
          </div>
        ) : (
          <Note tone="info">Kitap kartında pazarlama metni girilmemiş.</Note>
        )}
      </Block>
    </div>
  );
}

/** Emsal adayı (CRM'de emsal girilmemişse): katalogda özeti, kategorisi ve teması anlamca en yakın kitaplar. Sıra
 *  benzerliktir, puan gösterilmez; satış sütunları emsal tablosuyla aynı kaynaktan. Seçim insanda: aday CRM kartına
 *  emsal olarak girilince karne yenilenir. */
function EmsalCandidatesBlock({ stok }: { stok: string }) {
  const q = useQuery({ queryKey: ['mkt', 'emsal-adaylari', stok], queryFn: () => mktApi.emsalCandidates(stok), enabled: ENGINE_ENABLED, retry: false });
  return (
    <Block
      title="Emsal adayları (özet benzerliği)"
      help="CRM'de bu kitaba emsal girilmemiş. Katalogda arka kapak metni, kitaplığı, kategorisi ve teması anlamca en yakın kitaplar sırayla listelenir; emsal seçimi sizindir."
    >
      {q.isLoading ? (
        <Loading />
      ) : q.error ? (
        <Note tone="err">{errText(q.error, 'Adaylar okunamadı.')}</Note>
      ) : !q.data?.items.length ? (
        <Note tone="info">{q.data?.not ?? 'Aday bulunamadı.'}</Note>
      ) : (
        <>
          {q.data.not && <Note tone="info">{q.data.not}</Note>}
          <TableWrap>
            <thead>
              <tr className="border-b border-slate-100">
                <th className={th}>Sıra</th><th className={th}>Kitap</th><th className={th}>Neden yakın</th><th className={th}>Lansman</th>
                <th className={`${th} text-right`}>İlk 3 ay</th><th className={`${th} text-right`}>İlk 6 ay</th><th className={`${th} text-right`}>İlk 12 ay</th>
              </tr>
            </thead>
            <tbody>
              {q.data.items.map((e) => (
                <tr key={e.stokKodu} className="border-b border-slate-50 last:border-0">
                  <td className={`${td} font-mono tabular-nums`}>{e.sira}</td>
                  <td className={td}>
                    <div className="max-w-[280px] font-semibold leading-snug">{e.ad}</div>
                    <div className="text-[11px] text-canvas-muted">{[e.yazar, e.stokKodu].filter(Boolean).join(' · ')}</div>
                  </td>
                  <td className={`${td} text-[11px] text-canvas-muted`}><div className="max-w-[240px]">{e.gerekce.join(' · ')}</div></td>
                  <td className={`${td} whitespace-nowrap`}>{e.lansman ?? '—'}</td>
                  <td className={`${td} text-right font-mono tabular-nums`}>{fmtInt(e.ilk3)}</td>
                  <td className={`${td} text-right font-mono tabular-nums`}>{fmtInt(e.ilk6)}</td>
                  <td className={`${td} text-right font-mono tabular-nums`}>{fmtInt(e.ilk12)}</td>
                </tr>
              ))}
            </tbody>
          </TableWrap>
          <p className="mt-2 text-[11px] text-canvas-muted">Aday bir kitabı emsal olarak kullanmak için CRM kitap kartına emsal girin; karne yenilenince «CRM emsali» olarak görünür.</p>
          <SourceNote text={`${q.data.kaynak} ${q.data.satisKaynagi ?? ''}`} sql={q.data.sql} />
        </>
      )}
    </Block>
  );
}
