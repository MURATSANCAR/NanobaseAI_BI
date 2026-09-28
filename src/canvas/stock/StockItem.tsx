import { useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import SqlInfo, { InfoLabel } from '../components/SqlInfo';
import type { Kaynaklar } from '../components/sqlInfo';
import { Trash2 } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import { Note, Pill, TableWrap, btnGhost, btnPrimary, errText, field, label as labelCls, td, th } from '../admin/ui';
import { Kpi, KpiRow, Panel } from '../editorial/kit';
import { canOpenRoute, usePageAccess } from '../useAdmin';
import { fmtDay } from '../budget/api';
import { gunText, n0, n1, stockApi, tl, type Suggestion } from './api';
import { DataDay, Empty, Loading, SourcesButton, StatePill, StockFrame, num } from './parts';
import { RULES } from './rules';
import { SuggestionActions } from './decisions';

/** Kitap stok kartı (/stok/:stokKodu): tek bakışta Logo stoğu, raf dağılımı, kaç gün yeter, açık baskı ve tahmini depo
 *  girişi; talep, güvenlik stoku, öneriler, notlar ve gece fotoğrafı. */

export default function StockItem() {
  const { stokKodu = '' } = useParams();
  const qc = useQueryClient();
  const pages = usePageAccess();
  const meta = useQuery({ queryKey: ['stock', 'meta'], queryFn: stockApi.meta, enabled: ENGINE_ENABLED, staleTime: 60_000 });
  const q = useQuery({ queryKey: ['stock', 'item', stokKodu], queryFn: () => stockApi.item(stokKodu), enabled: ENGINE_ENABLED && !!stokKodu });
  const me = meta.data?.me;
  const it = q.data;
  const [note, setNote] = useState('');
  const [gun, setGun] = useState('');
  const [adet, setAdet] = useState('');
  const [why, setWhy] = useState('');
  const refresh = () => qc.invalidateQueries({ queryKey: ['stock'] });

  const addNote = useMutation({
    mutationFn: () => stockApi.addNote(stokKodu, note),
    onSuccess: () => { setNote(''); refresh(); },
    onError: (e) => toast.error(errText(e, 'Not kaydedilemedi.') ?? ''),
  });
  const delNote = useMutation({ mutationFn: stockApi.deleteNote, onSuccess: refresh, onError: (e) => toast.error(errText(e, 'Not silinemedi.') ?? '') });
  const save = useMutation({
    mutationFn: (onayla: boolean) =>
      stockApi.saveThreshold({ stokKodu, guvenlikGun: Number(gun || it?.esikOnerisi?.guvenlikGun || 0), yenidenSiparisAdet: adet ? Number(adet.replace(/\./g, '')) : it?.esikOnerisi?.yenidenSiparisAdet ?? null,
        gerekce: why || it?.esikOnerisi?.gerekce, kaynak: gun || adet ? 'elle' : 'oneri', onayla }),
    onSuccess: (t) => { toast.success(t.durum === 'onayli' ? 'Güvenlik stoku onaylandı.' : 'Taslak kaydedildi; onay bekliyor.'); setGun(''); setAdet(''); setWhy(''); refresh(); },
    onError: (e) => toast.error(errText(e, 'Kaydedilemedi.') ?? ''),
  });
  const approve = useMutation({ mutationFn: (id: string) => stockApi.approveThreshold(id), onSuccess: refresh, onError: (e) => toast.error(errText(e, 'Onaylanamadı.') ?? '') });

  return (
    <StockFrame
      crumb="Stok"
      title={it?.ad ?? stokKodu}
      lead={it ? `${stokKodu}${it.yazar ? ` · ${it.yazar}` : ''}${it.yayinevi ? ` · ${it.yayinevi}` : ''}` : 'Kitap stok kartı'}
      source={it?.veriSonu ? `Logo · ${fmtDay(it.veriSonu)}` : 'Logo + CRM'}
      back={{ to: '/stok', label: 'Depo ve stok' }}
      aside={<SourcesButton rules={RULES} />}
    >
      {q.error && <Note tone="err">{errText(q.error, 'Kitap okunamadı.')}</Note>}
      {q.isLoading && <Loading what="Kitap" />}
      {it && (
        <>
          <DataDay day={it.veriSonu} />
          <div className="flex flex-wrap items-center gap-2">
            <StatePill state={it.durum} label={it.durumEtiket} />
            {it.baskiOneri && <Pill tone="violet">Baskı öneri: {it.baskiOneri}</Pill>}
            {it.rspAltinda && <Pill tone="warn">Yeniden sipariş noktasının altında</Pill>}
          </div>
          <KpiRow>
            <Kpi label="Logo stok" value={n0(it.bakiye)} help={it.logoVar ? `${it.ambarlar.length} ambarda` : 'Bu yıl Logo’da hareketi yok'}
              info={<SqlInfo k={it.kaynaklar} alan="bakiye" label="Logo stok" />} />
            <Kpi label="CRM raf" value={n0(it.crmRaf)} help={it.fark ? `Fark ${it.fark > 0 ? '+' : ''}${n0(it.fark)} · ${it.farkEtiket}` : `${it.rafSayisi} raf`}
              info={<SqlInfo k={it.kaynaklar} alan={it.fark ? 'fark' : 'crmRaf'} label={it.fark ? 'CRM raf ve Logo–CRM farkı' : 'CRM raf'} />} />
            <Kpi label="Kaç gün yeter" value={gunText(it.gun)} help={it.tukenmeTarihi ? `Tahmini tükenme ${fmtDay(it.tukenmeTarihi)}` : 'Satış hızı yok'}
              info={<SqlInfo k={it.kaynaklar} alan="gun" label="Kaç gün yeter" />} />
            <Kpi label="Aylık satış hızı" value={n1(it.satisHizi)} help={`Kritik: ${it.kritikGun} gün (baskı ${it.baskiSuresi} + güvenlik)`}
              info={<SqlInfo k={it.kaynaklar} alan="satisHizi" label="Aylık satış hızı" />} />
          </KpiRow>

          <div className="grid gap-3 lg:grid-cols-2 lg:gap-4">
            <Panel>
              <h2 className="mb-2 text-[13px] font-extrabold"><InfoLabel k={it.kaynaklar} alan="raflar" label="Depo ve raf adetleri">Depo ve raf</InfoLabel></h2>
              <div className="mb-3 flex flex-wrap items-center gap-2">
                <SqlInfo k={it.kaynaklar} alan="ambarlar" label="Logo ambar adetleri" />
                {it.ambarlar.length ? it.ambarlar.map((a) => (
                  <span key={a.no} className="rounded-xl bg-slate-100 px-3 py-1.5 text-[12px] font-semibold">
                    {a.ad}: <span className="font-mono tabular-nums">{n0(a.adet)}</span>
                  </span>
                )) : <span className="text-[12px] text-canvas-muted">Logo ambar kırılımı yok.</span>}
              </div>
              {it.raflar.length ? (
                <TableWrap>
                  <thead>
                    <tr>
                      <th className={th}>Depo</th>
                      <th className={th}>Raf</th>
                      <th className={th}>Tür</th>
                      <th className={`${th} text-right`}><InfoLabel k={it.kaynaklar} alan="raflar">Adet</InfoLabel></th>
                    </tr>
                  </thead>
                  <tbody>
                    {it.raflar.map((r) => (
                      <tr key={`${r.rafId}-${r.depoId}`} className="border-t border-slate-100">
                        <td className={td}>{r.depo ?? '—'}</td>
                        <td className={td}>{r.raf ?? 'Rafsız lot'}{r.satisaAcik ? '' : <span className="ml-1 text-[11px] text-canvas-muted">(satışa kapalı)</span>}</td>
                        <td className={td}>{r.rafTipi ?? '—'}</td>
                        <td className={`${td} ${num}`}>{n0(r.adet)}</td>
                      </tr>
                    ))}
                  </tbody>
                </TableWrap>
              ) : (
                <Empty>CRM’de bu kitabın raf kaydı yok.</Empty>
              )}
            </Panel>

            <Panel>
              <h2 className="mb-2 text-[13px] font-extrabold"><InfoLabel k={it.kaynaklar} alan="bekleyenCrm">Talep ve hareket</InfoLabel></h2>
              <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-[12.5px]">
                <Fact k="Bekleyen sipariş (CRM)" v={n0(it.bekleyenCrm)} ks={it.kaynaklar} a="bekleyenCrm" />
                <Fact k="Bekleyen sipariş (Logo)" v={n0(it.bekleyenLogo)} ks={it.kaynaklar} a="bekleyenLogo" />
                <Fact k="Bekleyen ürün talebi" v={n0(it.bekleyenUrun)} ks={it.kaynaklar} a="bekleyenUrun" />
                <Fact k="Son 12 ay net satış" v={n0(it.netSatis12)} ks={it.kaynaklar} a="netSatis12" />
                <Fact k="Stok devir hızı" v={it.devirHizi === null ? '—' : n1(it.devirHizi)} ks={it.kaynaklar} a="devirHizi" />
                <Fact k="Son hareket" v={it.sonHareket ? fmtDay(it.sonHareket) : 'pencerede yok'} />
                <Fact k="Mevcut rapordaki depo stoku" v={n0(it.eosStok)} ks={it.kaynaklar} a="eosStok" />
                <Fact k="Logo’ya geçmemiş (net)" v={it.aktarimBekleyen ? `${n0(it.aktarimBekleyen)} · ${it.aktarimFis} fiş` : '—'} ks={it.kaynaklar} a="aktarimBekleyen" />
                {it.stokDegeri !== undefined && <Fact k="Birim maliyet" v={it.birimMaliyet ? tl(it.birimMaliyet) : 'bilinmiyor'} ks={it.kaynaklar} a="birimMaliyet" />}
                {it.stokDegeri !== undefined && <Fact k="Stok değeri" v={it.stokDegeri === null ? 'maliyet yok' : tl(it.stokDegeri)} ks={it.kaynaklar} a="stokDegeri" />}
              </dl>
              <div className="mt-3 rounded-xl bg-violet-50/70 p-3 text-[12px]">
                <div className="flex flex-wrap items-center gap-1.5 font-extrabold">
                  Zeki AI talep tahmini
                  <SqlInfo k={it.kaynaklar} alan="tahmin" label="Talep tahmini" />
                  <span className="rounded-md bg-white/80 px-1.5 py-0.5 text-[10px] font-extrabold uppercase tracking-wide text-canvas-violet">tahmin</span>
                </div>
                {it.tahmin ? (
                  <div className="mt-1.5 grid grid-cols-3 gap-2">
                    {(['g30', 'g60', 'g90'] as const).map((k, idx) => {
                      const band = it.tahminAralik?.[k];
                      return (
                        <div key={k} className="min-w-0 rounded-lg bg-white/70 px-2 py-1.5">
                          <div className="text-[10.5px] font-bold text-canvas-muted">{(idx + 1) * 30} gün</div>
                          <div className="font-mono text-[14px] font-bold tabular-nums">{n0(it.tahmin?.[k])}</div>
                          {band?.aralik && (
                            <div className="font-mono text-[10.5px] tabular-nums text-canvas-muted" title="Muhafazakâr (p10) – iyimser (p90)">
                              {n0(band.p10)}–{n0(band.p90)}
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                ) : (
                  <div className="mt-1 text-canvas-muted">Bu kitap için tahmin yok.</div>
                )}
                {it.tahmin && (
                  <div className="mt-1.5 text-[11px] leading-snug text-canvas-muted">
                    {it.tahminAralik?.aralik
                      ? 'Büyük sayı temel tahmin (p50); altındaki aralık muhafazakâr (p10) – iyimser (p90), aylık aralıkların toplamı. '
                      : 'Bu tahminde aralık yok; yalnız temel tahmin (p50) gösteriliyor. '}
                    {it.tahmin.baslangic ? `Tahmin ${fmtDay(it.tahmin.baslangic)} ayından başlar; okul sezonu zirvesini eksik tahmin ettiği biliniyor.` : ''}
                  </div>
                )}
              </div>
            </Panel>

            <Panel>
              <h2 className="mb-2 text-[13px] font-extrabold"><InfoLabel k={it.kaynaklar} alan="uretimKartlari" label="Açık üretim kartları">Üretim (baskı tekrarı)</InfoLabel></h2>
              {it.uretimKartlari.length ? (
                <ul className="flex flex-col gap-2">
                  {it.uretimKartlari.map((c) => (
                    <li key={c.kartId} className="rounded-xl border border-slate-100 bg-white/80 p-3 text-[12.5px]">
                      <div className="font-bold">{c.ad ?? c.kartId}{c.baskiNo ? ` · ${c.baskiNo}. baskı` : ''}</div>
                      <div className="text-canvas-muted">{c.asamaEtiket}{c.adet ? ` · ${n0(c.adet)} adet` : ''} · baskı {c.baskiPlan ? fmtDay(c.baskiPlan) : '—'} · depo {c.depoPlan ? fmtDay(c.depoPlan) : 'planı yok'}</div>
                    </li>
                  ))}
                </ul>
              ) : (
                <Empty>Açık üretim kartı yok.</Empty>
              )}
              {canOpenRoute(pages, '/uretim') && (
                <Link to="/uretim" className="mt-2 inline-flex min-h-11 items-center text-[12px] font-bold text-canvas-violet hover:underline sm:min-h-0">Üretim yönetimini aç</Link>
              )}
              <div className="mt-1 flex items-center gap-1 text-[11px] text-canvas-muted">
                Baskı süresi: {it.baskiSuresi} gün ({it.baskiSuresiKaynak}).
                <SqlInfo k={it.kaynaklar} alan="baskiSuresi" label="Baskı süresi" />
              </div>
            </Panel>

            <Panel>
              <h2 className="mb-2 text-[13px] font-extrabold"><InfoLabel k={it.kaynaklar} alan="esik" label="Onaylı eşik">Güvenlik stoku</InfoLabel></h2>
              {it.esik ? (
                <p className="text-[12.5px]">
                  Onaylı: <strong>{it.esik.guvenlikGun} gün</strong>
                  {it.esik.yenidenSiparisAdet !== null && <> · yeniden sipariş noktası <strong>{n0(it.esik.yenidenSiparisAdet)}</strong> adet</>}
                  <span className="text-canvas-muted"> — {it.esik.onaylayan ?? '—'}{it.esik.onayTarihi ? `, ${fmtDay(it.esik.onayTarihi)}` : ''}</span>
                </p>
              ) : (
                <p className="text-[12.5px] text-canvas-muted">Onaylı eşik yok; varsayılan güvenlik günü kullanılıyor. Logo’da asgari seviye girilmemiş.</p>
              )}
              {it.esikOnerisi && (
                <p className="mt-2 rounded-xl bg-slate-50 p-2 text-[12px]">
                  Öneri: {it.esikOnerisi.gerekce}
                  <SqlInfo k={it.kaynaklar} alan="esikOnerisi" label="Eşik önerisi" className="ml-0.5" />
                </p>
              )}
              {me?.canDecide && (
                <div className="mt-3 grid gap-2 sm:grid-cols-3">
                  <label className="flex flex-col gap-1">
                    <span className={labelCls}>Güvenlik günü</span>
                    <input className={field} inputMode="numeric" value={gun} placeholder={String(it.esikOnerisi?.guvenlikGun ?? '')} onChange={(e) => setGun(e.target.value.replace(/\D/g, ''))} />
                  </label>
                  <label className="flex flex-col gap-1">
                    <span className={labelCls}>Yeniden sipariş adedi</span>
                    <input className={field} inputMode="numeric" value={adet} placeholder={it.esikOnerisi ? n0(it.esikOnerisi.yenidenSiparisAdet) : ''} onChange={(e) => setAdet(e.target.value.replace(/[^\d.]/g, ''))} />
                  </label>
                  <label className="flex flex-col gap-1 sm:col-span-1">
                    <span className={labelCls}>Gerekçe</span>
                    <input className={field} value={why} onChange={(e) => setWhy(e.target.value)} placeholder="Boşsa hesap metni" />
                  </label>
                  <div className="flex flex-wrap gap-2 sm:col-span-3">
                    <button type="button" className={btnGhost} disabled={save.isPending || (!gun && !it.esikOnerisi)} onClick={() => save.mutate(false)}>Taslak kaydet</button>
                    {me.canApprove && (
                      <button type="button" className={btnPrimary} disabled={save.isPending || (!gun && !it.esikOnerisi)} onClick={() => save.mutate(true)}>Kaydet ve onayla</button>
                    )}
                  </div>
                </div>
              )}
              {!!it.esikler.length && (
                <ul className="mt-3 divide-y divide-slate-100 text-[12px]">
                  <li className="py-1 text-[11px] font-semibold text-canvas-muted"><InfoLabel k={it.kaynaklar} alan="esikler">Eşik kayıtları</InfoLabel></li>
                  {it.esikler.map((t) => (
                    <li key={t.id} className="flex flex-wrap items-center justify-between gap-2 py-1.5">
                      <span>
                        <Pill tone={t.durum === 'onayli' ? 'ok' : t.durum === 'taslak' ? 'warn' : 'muted'}>{t.durumEtiket}</Pill>{' '}
                        {t.guvenlikGun} gün{t.yenidenSiparisAdet !== null ? ` · ${n0(t.yenidenSiparisAdet)} adet` : ''} · {t.olusturan}
                      </span>
                      {t.durum === 'taslak' && me?.canApprove && (
                        <button type="button" className={btnGhost} disabled={approve.isPending} onClick={() => approve.mutate(t.id)}>Onayla</button>
                      )}
                    </li>
                  ))}
                </ul>
              )}
            </Panel>
          </div>

          <Panel>
            <h2 className="mb-2 text-[13px] font-extrabold"><InfoLabel k={it.kaynaklar} alan="oneriler" label="Öneri rakamları">Öneriler</InfoLabel></h2>
            {it.oneriler.length ? (
              <ul className="flex flex-col gap-2">
                {it.oneriler.map((s: Suggestion) => (
                  <li key={s.id} className="rounded-xl border border-slate-100 bg-white/80 p-3 text-[12.5px]">
                    <div className="flex flex-wrap items-center gap-2">
                      <strong>{s.turEtiket}</strong>
                      <Pill tone={s.durum === 'acik' ? 'warn' : s.durum === 'kabul' ? 'ok' : 'muted'}>{s.durumEtiket}</Pill>
                      {s.hedefEtiket && <span className="text-canvas-muted">→ {s.hedefEtiket}</span>}
                    </div>
                    <p className="mt-1 text-canvas-muted">{s.gerekce}</p>
                    {s.durum === 'acik' && <SuggestionActions s={s} canDecide={!!me?.canDecide} />}
                    {s.kararVeren && <p className="mt-1 text-[11px] text-canvas-muted">{s.kararVeren}{s.kararNotu ? ` · ${s.kararNotu}` : ''}</p>}
                  </li>
                ))}
              </ul>
            ) : (
              <Empty>Bu kitap için öneri yok.</Empty>
            )}
          </Panel>

          <div className="grid gap-3 lg:grid-cols-2 lg:gap-4">
            <Panel>
              <h2 className="mb-2 text-[13px] font-extrabold">Sayım ve düzeltme notları</h2>
              <div className="flex flex-col gap-2 sm:flex-row">
                <input className={`${field} flex-1`} value={note} onChange={(e) => setNote(e.target.value)} placeholder="Örn. sayımda merkez depoda 5 eksik" />
                <button type="button" className={btnPrimary} disabled={!note.trim() || addNote.isPending} onClick={() => addNote.mutate()}>Not ekle</button>
              </div>
              {it.notlar.length ? (
                <ul className="mt-2 divide-y divide-slate-100 text-[12.5px]">
                  {it.notlar.map((n) => (
                    <li key={n.id} className="flex items-start justify-between gap-2 py-2">
                      <div className="min-w-0">
                        <p className="break-words">{n.not}</p>
                        <p className="text-[11px] text-canvas-muted">{n.yazanAd ?? n.yazan} · {n.tarih ? fmtDay(n.tarih) : ''}</p>
                      </div>
                      {n.yazan === me?.username && (
                        <button type="button" className={btnGhost} aria-label="Notu sil" onClick={() => delNote.mutate(n.id)}>
                          <Trash2 aria-hidden className="h-4 w-4" />
                        </button>
                      )}
                    </li>
                  ))}
                </ul>
              ) : (
                <Empty>Not yok.</Empty>
              )}
            </Panel>
            <Panel>
              <h2 className="mb-2 text-[13px] font-extrabold"><InfoLabel k={it.kaynaklar} alan="gecmis">Gece fotoğrafı</InfoLabel></h2>
              {it.gecmis.length ? (
                <TableWrap>
                  <thead>
                    <tr>
                      <th className={th}>Gün</th>
                      <th className={`${th} text-right`}>Logo</th>
                      <th className={`${th} text-right`}>CRM raf</th>
                      <th className={`${th} text-right`}>Satış hızı</th>
                    </tr>
                  </thead>
                  <tbody>
                    {[...it.gecmis].reverse().map((g) => (
                      <tr key={g.gun} className="border-t border-slate-100">
                        <td className={td}>{fmtDay(g.gun)}</td>
                        <td className={`${td} ${num}`}>{n0(g.bakiye)}</td>
                        <td className={`${td} ${num}`}>{n0(g.crmRaf)}</td>
                        <td className={`${td} ${num}`}>{n1(g.satisHizi)}</td>
                      </tr>
                    ))}
                  </tbody>
                </TableWrap>
              ) : (
                <Empty>Gece fotoğrafı henüz yok; her sabah 06:30’da alınır.</Empty>
              )}
            </Panel>
          </div>
        </>
      )}
    </StockFrame>
  );
}

/** `ks` + `a`: sorgu bilgisi (cevabın `kaynaklar`ı ve alan adı); yoksa rakam değil. */
function Fact({ k, v, ks, a }: { k: string; v: string; ks?: Kaynaklar; a?: string }) {
  return (
    <div className="min-w-0">
      <dt className={labelCls}>{a ? <InfoLabel k={ks} alan={a}>{k}</InfoLabel> : k}</dt>
      <dd className="font-mono tabular-nums">{v}</dd>
    </div>
  );
}
