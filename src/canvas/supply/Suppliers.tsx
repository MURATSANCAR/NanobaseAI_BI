import { useCallback, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { ENGINE_ENABLED } from '../engine';
import { Loading, Note, Pill, TableWrap, btnGhost, btnPrimary, errText, field, td, th } from '../admin/ui';
import { Panel } from '../editorial/kit';
import { Tabs } from '../budget/parts';
import { KIND_LABEL, fmtDay, fmtInt, fmtMoney, fmtPct, supplyApi, type Meta, type Suppliers as SuppliersData, type Unbilled } from './api';
import { CardLine, ErrorNote, ExportLink, SupplyFrame, Warnings, useSupplyMeta } from './parts';

/** M52 Tedarikçiler (/tedarik/tedarikciler): matbaa ve kağıtçı listesi (iş + borç + karne), 30/60/90 gün ödeme,
 *  faturası görünmeyen baskı ve kartı görünmeyen fatura, matbaa ↔ Logo carisi eşlemesi. Borç tutarları açıkça verilen
 *  «tedarikçi borç» yetkisiyle görünür; FIFO yaklaşımıdır, kesin borç değildir. */

const TABS = [
  { key: 'liste', label: 'Tedarikçiler' },
  { key: 'odeme', label: 'Ödeme planı' },
  { key: 'fatura', label: 'Fatura eşleşmesi' },
  { key: 'esleme', label: 'Matbaa ↔ cari' },
] as const;
type Tab = (typeof TABS)[number]['key'];

export default function Suppliers() {
  const [params, setParams] = useSearchParams();
  const meta = useSupplyMeta();
  const me = meta.data?.me;
  const tabs = TABS.filter((t) => (t.key === 'odeme' ? me?.canDebt : true));
  const tab: Tab = (tabs.find((t) => t.key === params.get('sekme'))?.key ?? 'liste') as Tab;
  const q = useQuery({ queryKey: ['supply', 'suppliers'], queryFn: supplyApi.suppliers, enabled: ENGINE_ENABLED });

  const update = useCallback(
    (next: Record<string, string | null>) => {
      const n = new URLSearchParams(params);
      for (const [k, v] of Object.entries(next)) {
        if (v) n.set(k, v);
        else n.delete(k);
      }
      setParams(n, { replace: true });
    },
    [params, setParams],
  );

  return (
    <SupplyFrame
      title="Matbaa ve kağıtçılar"
      lead="Logo'daki tedarikçi carileri: matbaa ve kağıtçı özel koduyla ya da baskı faturası kesmiş olmasıyla ayrılır. Her matbaanın açık işi, karnesi (Üretim yönetiminden), borcu ve önümüzdeki ödemeleri bir arada. Logo'da ödeme kapama kullanılmadığı için borç FIFO yaklaşımıyla hesaplanır."
      source={q.data?.logo ? `Logo ${q.data.logo.yil} · veri sonu ${fmtDay(q.data.logo.veriSonu)}` : undefined}
      aside={
        me?.canExport && me.canDebt ? (
          <div className="flex flex-wrap justify-start gap-2 lg:justify-end">
            <ExportLink href={supplyApi.exportUrl('borc')} label="Borç (Excel)" />
            <ExportLink href={supplyApi.exportUrl('odeme')} label="Ödeme (Excel)" />
            <ExportLink href={supplyApi.exportUrl('faturasiz')} label="Faturasız (Excel)" />
          </div>
        ) : undefined
      }
    >
      <ErrorNote error={q.error} fallback="Tedarikçiler okunamadı." />
      <Warnings items={q.data?.uyarilar} />
      {q.data?.borcGorunur && <Note tone="info">{q.data.fifoNotu}</Note>}
      <Tabs tabs={tabs} value={tab} onChange={(k) => update({ sekme: k === 'liste' ? null : k })} />
      {q.isLoading && <Loading />}
      {q.data && tab === 'liste' && <SupplierList data={q.data} />}
      {tab === 'odeme' && me?.canDebt && <PaymentsTab />}
      {tab === 'fatura' && meta.data && <InvoiceTab meta={meta.data} />}
      {q.data && tab === 'esleme' && meta.data && <MappingTab data={q.data} meta={meta.data} />}
    </SupplyFrame>
  );
}

function SupplierList({ data }: { data: SuppliersData }) {
  const [kind, setKind] = useState<'matbaa' | 'kagit' | 'hepsi'>('matbaa');
  const items = data.items.filter((x) => kind === 'hepsi' || x.tur === kind);
  const debt = data.borcGorunur;
  return (
    <Panel>
      <div className="flex flex-wrap items-center gap-2 px-1">
        {(['matbaa', 'kagit', 'hepsi'] as const).map((k) => (
          <button
            key={k}
            type="button"
            aria-pressed={kind === k}
            onClick={() => setKind(k)}
            className={`min-h-11 rounded-xl px-3 text-[12px] font-extrabold transition-colors duration-150 sm:min-h-8 ${kind === k ? 'bg-canvas-violet text-white' : 'bg-slate-100 text-canvas-ink hover:bg-slate-200'}`}
          >
            {k === 'hepsi' ? 'Hepsi' : KIND_LABEL[k]} ({fmtInt(data.items.filter((x) => k === 'hepsi' || x.tur === k).length)})
          </button>
        ))}
      </div>
      {items.length === 0 ? (
        <div className="mt-3">
          <Note tone="info">Bu türde tedarikçi yok. Özel kod yazımını «Matbaa ↔ cari» sekmesinden kontrol edin.</Note>
        </div>
      ) : (
        <div className="mt-3">
          <TableWrap>
            <thead>
              <tr className="border-b border-slate-100">
                <th className={th}>Tedarikçi</th>
                <th className={`${th} text-right`}>Açık iş</th>
                <th className={`${th} text-right`}>Zamanında</th>
                {debt && (
                  <>
                    <th className={`${th} text-right`}>Bakiye</th>
                    <th className={`${th} text-right`}>Vadesi geçmiş</th>
                    <th className={`${th} text-right`}>30 gün içinde</th>
                    <th className={`${th} text-right`}>12 ay alış</th>
                  </>
                )}
              </tr>
            </thead>
            <tbody>
              {items.map((s) => {
                const onTime = s.karne.find((k) => k.onTimeRate !== null)?.onTimeRate ?? null;
                return (
                  <tr key={s.kod} className="border-b border-slate-50 last:border-0">
                    <td className={td}>
                      <Link to={`/tedarik/tedarikci/${encodeURIComponent(s.kod)}`} className="font-bold text-canvas-violet hover:underline">
                        {s.unvan}
                      </Link>
                      <div className="flex flex-wrap items-center gap-1 text-[10.5px] text-canvas-muted">
                        <span>{s.kod}</span>
                        <Pill tone={s.tur === 'matbaa' ? 'violet' : s.tur === 'kagit' ? 'ok' : 'muted'}>{KIND_LABEL[s.tur]}</Pill>
                        {s.crmMatbaa.length > 0 && <span>CRM: {s.crmMatbaa.join(', ')}</span>}
                        {s.turKaynak === 'baski-faturasi' && <span>(özel kodu yok, baskı faturası kesmiş)</span>}
                      </div>
                    </td>
                    <td className={`${td} text-right font-mono tabular-nums`}>{fmtInt(s.acikIs)}</td>
                    <td className={`${td} text-right font-mono tabular-nums`}>{fmtPct(onTime)}</td>
                    {debt && (
                      <>
                        <td className={`${td} text-right font-mono tabular-nums`}>{fmtMoney(s.bakiye)}</td>
                        <td className={`${td} text-right font-mono tabular-nums ${s.vadesiGecmis ? 'text-red-700' : ''}`}>{fmtMoney(s.vadesiGecmis)}</td>
                        <td className={`${td} text-right font-mono tabular-nums`}>{fmtMoney(s.gelecek?.g_0_30)}</td>
                        <td className={`${td} text-right font-mono tabular-nums`}>{fmtMoney(s.alis12)}</td>
                      </>
                    )}
                  </tr>
                );
              })}
            </tbody>
          </TableWrap>
        </div>
      )}
      {!debt && <p className="mt-2 px-1 text-[11.5px] text-canvas-muted">Borç ve ödeme tutarları «tedarikçi borç» yetkisiyle görünür.</p>}
    </Panel>
  );
}

function PaymentsTab() {
  const [days, setDays] = useState(30);
  const [kind, setKind] = useState('');
  const q = useQuery({ queryKey: ['supply', 'payments', days, kind], queryFn: () => supplyApi.payments(days, kind), enabled: ENGINE_ENABLED });
  const p = q.data;
  return (
    <Panel>
      <div className="flex flex-wrap items-end gap-2 px-1">
        <label className="flex flex-col gap-1">
          <span className="text-[11px] font-bold uppercase tracking-wide text-canvas-muted">Süre</span>
          <select className={`${field} w-auto`} value={days} onChange={(e) => setDays(Number(e.target.value))}>
            {[30, 60, 90].map((n) => (
              <option key={n} value={n}>
                Önümüzdeki {n} gün
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-[11px] font-bold uppercase tracking-wide text-canvas-muted">Tür</span>
          <select className={`${field} w-auto`} value={kind} onChange={(e) => setKind(e.target.value)}>
            <option value="">Hepsi</option>
            <option value="matbaa">Matbaa</option>
            <option value="kagit">Kağıtçı</option>
            <option value="diger">Diğer</option>
          </select>
        </label>
      </div>
      <ErrorNote error={q.error} fallback="Ödeme planı okunamadı." />
      {q.isLoading && <Loading />}
      {p && (
        <>
          <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
            <Fact label={`${days} gün ödeme`} value={fmtMoney(p.toplam)} />
            <Fact label="Vadesi geçmiş" value={fmtMoney(p.vadesiGecmisToplam)} />
            <Fact label="Yaşlandırma tarihi" value={fmtDay(p.logo?.yaslandirmaTarihi)} />
            <Fact label="Logo veri sonu" value={fmtDay(p.logo?.veriSonu)} />
          </div>
          {p.haftalik.length > 0 && (
            <div className="mt-3 flex flex-wrap gap-1.5">
              {p.haftalik.map((w) => (
                <div key={w.hafta} className="min-w-[110px] flex-1 rounded-xl bg-slate-50 px-2.5 py-1.5">
                  <div className="text-[10.5px] font-bold uppercase text-canvas-muted">{fmtDay(w.hafta)} haftası</div>
                  <div className="font-mono text-[13px] font-bold tabular-nums">{fmtMoney(w.tutar)}</div>
                </div>
              ))}
            </div>
          )}
          <div className="mt-3">
            <TableWrap>
              <thead>
                <tr className="border-b border-slate-100">
                  <th className={th}>Vade</th>
                  <th className={th}>Tedarikçi</th>
                  <th className={th}>Fatura</th>
                  <th className={`${th} text-right`}>Plan tutarı</th>
                  <th className={`${th} text-right`}>Açık (FIFO)</th>
                </tr>
              </thead>
              <tbody>
                {p.satirlar.map((r, i) => (
                  <tr key={`${r.kod}-${r.vade}-${i}`} className="border-b border-slate-50 last:border-0">
                    <td className={`${td} whitespace-nowrap`}>{fmtDay(r.vade)}</td>
                    <td className={td}>
                      <Link to={`/tedarik/tedarikci/${encodeURIComponent(r.kod)}`} className="font-bold text-canvas-violet hover:underline">
                        {r.unvan}
                      </Link>
                      <div className="text-[10.5px] text-canvas-muted">{KIND_LABEL[r.tur] ?? r.tur}</div>
                    </td>
                    <td className={td}>{r.faturaNo ? `${r.faturaNo} · ${fmtDay(r.faturaTarihi)}` : '—'}</td>
                    <td className={`${td} text-right font-mono tabular-nums`}>{fmtMoney(r.tutar)}</td>
                    <td className={`${td} text-right font-mono font-bold tabular-nums`}>{fmtMoney(r.acik)}</td>
                  </tr>
                ))}
                {p.satirlar.length === 0 && (
                  <tr>
                    <td className={td} colSpan={5}>
                      Bu sürede vadesi gelen açık ödeme satırı yok.
                    </td>
                  </tr>
                )}
              </tbody>
            </TableWrap>
          </div>
          <p className="mt-2 px-1 text-[11.5px] leading-snug text-canvas-muted">{p.fifoNotu}</p>
        </>
      )}
    </Panel>
  );
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0 rounded-xl bg-white/80 px-3 py-2">
      <div className="text-[10.5px] font-bold uppercase tracking-wide text-canvas-muted">{label}</div>
      <div className="mt-0.5 break-words font-mono text-[14px] font-bold tabular-nums">{value}</div>
    </div>
  );
}

function InvoiceTab({ meta }: { meta: Meta }) {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ['supply', 'unbilled'], queryFn: supplyApi.unbilled, enabled: ENGINE_ENABLED });
  const link = useMutation({
    mutationFn: supplyApi.link,
    onSuccess: () => {
      toast.success('Kaydedildi.');
      void qc.invalidateQueries({ queryKey: ['supply'] });
    },
    onError: (e) => toast.error(errText(e, 'Kaydedilemedi.') ?? 'Kaydedilemedi.'),
  });
  const u: Unbilled | undefined = q.data;
  const can = meta.me.canMatch;
  return (
    <div className="flex flex-col gap-3">
      <ErrorNote error={q.error} fallback="Fatura eşleşmesi okunamadı." />
      {q.isLoading && <Loading />}
      {u && (
        <>
          <Panel>
            <h2 className="px-1 text-[13px] font-extrabold">Depoya girmiş, baskı faturası görünmeyen kartlar ({fmtInt(u.kartlar.length)})</h2>
            <p className="mt-1 px-1 text-[11.5px] leading-snug text-canvas-muted">
              Faturanın karta bağlanma kuralı Üretim yönetimininkiyle aynı: fatura satırının özel kodu = kitabın stok kodu, kartın zaman penceresinde. Bekleme süresi {u.bekleme.gun} gün
              {u.bekleme.kaynak === 'veri' ? ` (depo girişinden faturaya gün farkının 3. çeyreği, ${fmtInt(u.bekleme.ornek)} baskıdan ölçüldü)` : ' (ayar; ölçmeye yetecek örnek yok)'}.
            </p>
            <div className="mt-2">
              {u.kartlar.length === 0 ? (
                <Note tone="ok">Bekleme süresini geçmiş faturasız baskı yok.</Note>
              ) : (
                u.kartlar.map((c) => (
                  <CardLine key={c.id} c={c} right={<span className="text-[11px] text-canvas-muted">{c.matbaa ?? '—'} · depo {fmtDay(c.depo)} · {c.bekleyenGun} gün</span>} />
                ))
              )}
            </div>
          </Panel>
          <Panel>
            <h2 className="px-1 text-[13px] font-extrabold">Hiçbir karta bağlanmayan baskı faturası satırları ({fmtInt(u.faturalar.length)})</h2>
            <p className="mt-1 px-1 text-[11.5px] leading-snug text-canvas-muted">
              Son 12 ay. Aday kart her gece önerilir (aynı stok kodu ya da eşlenmiş matbaa + adet ±%15 + depo tarihi yakınlığı; birden çok aday varsa Zeki AI seçer). Öneri onaylanmadan hesaba girmez.
            </p>
            <div className="mt-2 flex flex-col gap-2">
              {u.faturalar.map((f) => (
                <article key={`${f.firma}-${f.satirRef}`} className="rounded-2xl border border-slate-100 bg-white/80 p-3">
                  <div className="flex flex-wrap items-baseline justify-between gap-2">
                    <div className="min-w-0">
                      <div className="text-[13px] font-bold">{f.cari ?? f.cariKod}</div>
                      <div className="text-[11.5px] text-canvas-muted">
                        Fatura {f.faturaNo ?? '—'} · {fmtDay(f.tarih)} · {fmtInt(f.adet)} adet · özel kod «{f.stok || 'boş'}»
                        {u.tutarGorunur && f.tutar !== undefined ? ` · ${fmtMoney(f.tutar)}` : ''}
                      </div>
                    </div>
                    {f.oneri && <Pill tone={f.oneri.durum === 'ret' ? 'muted' : 'violet'}>{f.oneri.durumAdi}</Pill>}
                  </div>
                  {f.oneri && f.oneri.durum === 'oneri' && (
                    <div className="mt-2 rounded-xl bg-slate-50 p-2 text-[12px]">
                      <div>
                        Önerilen:{' '}
                        <b>
                          {f.oneri.kartId
                            ? (f.oneri.adaylar.find((a) => a.kartId === f.oneri?.kartId)?.kitap ?? f.oneri.kartId)
                            : 'Hiçbir kartın değil'}
                        </b>{' '}
                        · {f.oneri.yontemAdi}
                        {f.oneri.olasilik !== null ? ` · olasılık ${fmtPct(f.oneri.olasilik)}` : ''}
                      </div>
                      {f.oneri.adaylar.length > 1 && (
                        <div className="mt-1 text-[11px] text-canvas-muted">
                          Adaylar: {f.oneri.adaylar.map((a) => `${a.kitap ?? '—'} (${fmtInt(a.adet)} adet, depo ${fmtDay(a.depo)})`).join(' · ')}
                        </div>
                      )}
                      {can && (
                        <div className="mt-2 flex flex-wrap justify-end gap-2">
                          <button
                            type="button"
                            className={btnGhost}
                            disabled={link.isPending}
                            onClick={() => link.mutate({ firma: f.firma, satirRef: f.satirRef, kartId: f.oneri?.kartId ?? null, karar: 'ret', faturaNo: f.faturaNo })}
                          >
                            Reddet
                          </button>
                          <button
                            type="button"
                            className={btnPrimary}
                            disabled={link.isPending}
                            onClick={() => link.mutate({ firma: f.firma, satirRef: f.satirRef, kartId: f.oneri?.kartId ?? null, karar: 'onay', faturaNo: f.faturaNo })}
                          >
                            Onayla
                          </button>
                        </div>
                      )}
                    </div>
                  )}
                  {can && !f.oneri && (
                    <div className="mt-2 flex justify-end">
                      <button
                        type="button"
                        className={btnGhost}
                        disabled={link.isPending}
                        onClick={() => link.mutate({ firma: f.firma, satirRef: f.satirRef, kartId: null, karar: 'onay', faturaNo: f.faturaNo })}
                      >
                        Bir baskıya ait değil
                      </button>
                    </div>
                  )}
                </article>
              ))}
              {u.faturalar.length === 0 && <Note tone="ok">Karta bağlanmayan baskı faturası yok.</Note>}
            </div>
          </Panel>
          <Panel>
            <h2 className="px-1 text-[13px] font-extrabold">Matbaa × ay: depoya giren ve faturalanan adet</h2>
            <p className="mt-1 px-1 text-[11.5px] text-canvas-muted">Kaba karşılaştırma: faturayı kesen Logo carisi matbaaya eşlenmişse sayılır.</p>
            <div className="mt-2">
              <TableWrap>
                <thead>
                  <tr className="border-b border-slate-100">
                    <th className={th}>Ay</th>
                    <th className={th}>Matbaa</th>
                    <th className={`${th} text-right`}>Depoya giren</th>
                    <th className={`${th} text-right`}>Faturalanan</th>
                    <th className={`${th} text-right`}>Fark</th>
                  </tr>
                </thead>
                <tbody>
                  {u.aylik.map((r) => (
                    <tr key={`${r.ay}-${r.matbaa}`} className="border-b border-slate-50 last:border-0">
                      <td className={td}>{r.ayAdi}</td>
                      <td className={td}>{r.matbaa}</td>
                      <td className={`${td} text-right font-mono tabular-nums`}>{fmtInt(r.depoAdet)}</td>
                      <td className={`${td} text-right font-mono tabular-nums`}>{fmtInt(r.faturaAdet)}</td>
                      <td className={`${td} text-right font-mono tabular-nums ${r.fark ? 'text-amber-800' : ''}`}>{fmtInt(r.fark)}</td>
                    </tr>
                  ))}
                </tbody>
              </TableWrap>
            </div>
          </Panel>
        </>
      )}
    </div>
  );
}

function MappingTab({ data, meta }: { data: SuppliersData; meta: Meta }) {
  const qc = useQueryClient();
  const [edit, setEdit] = useState<Record<string, string>>({});
  const save = useMutation({
    mutationFn: supplyApi.saveSupplierMap,
    onSuccess: () => {
      toast.success('Eşleme kaydedildi.');
      void qc.invalidateQueries({ queryKey: ['supply'] });
    },
    onError: (e) => toast.error(errText(e, 'Kaydedilemedi.') ?? 'Kaydedilemedi.'),
  });
  const can = meta.me.canMatch;
  const printers = [...new Set([...meta.printers, ...Object.keys(data.eslesme)])].sort((a, b) => a.localeCompare(b, 'tr'));
  const printerCodes = data.items.filter((x) => x.tur === 'matbaa');
  return (
    <div className="flex flex-col gap-3">
      <Panel>
        <h2 className="px-1 text-[13px] font-extrabold">CRM matbaası ↔ Logo carisi</h2>
        <p className="mt-1 px-1 text-[11.5px] leading-snug text-canvas-muted">
          Öneri veriden: kartın CRM matbaası ile o kartın baskı faturasını kesen Logo carisi; en çok işi olan cari, iş sayısı ve payı yeterliyse önerilir, değilse «belirsiz». Elle girilen eşleme öneriyi ezer.
        </p>
        <div className="mt-2">
          <TableWrap>
            <thead>
              <tr className="border-b border-slate-100">
                <th className={th}>CRM matbaası</th>
                <th className={th}>Logo carisi</th>
                <th className={th}>Kaynak</th>
                {can && <th className={th}>Değiştir</th>}
              </tr>
            </thead>
            <tbody>
              {printers.map((p) => {
                const m = data.eslesme[p];
                return (
                  <tr key={p} className="border-b border-slate-50 last:border-0">
                    <td className={`${td} font-bold`}>{p}</td>
                    <td className={td}>
                      {m?.cari ?? <span className="text-canvas-muted">eşlenmedi</span>}
                      {m && m.adaylar.length > 1 && (
                        <div className="text-[10.5px] text-canvas-muted">{m.adaylar.map((a) => `${a.cari} (${a.is})`).join(' · ')}</div>
                      )}
                    </td>
                    <td className={td}>
                      {m ? (m.kaynak === 'elle' ? `elle · ${m.by ?? ''}` : m.kaynak === 'veri' ? `veri · ${fmtInt(m.is)} iş, ${fmtPct(m.pay)}` : 'belirsiz') : '—'}
                    </td>
                    {can && (
                      <td className={td}>
                        <div className="flex flex-wrap gap-1.5">
                          <select className={`${field} w-auto`} value={edit[p] ?? m?.cari ?? ''} onChange={(e) => setEdit({ ...edit, [p]: e.target.value })}>
                            <option value="">Carisi yok</option>
                            {printerCodes.map((s) => (
                              <option key={s.kod} value={s.kod}>
                                {s.kod} · {s.unvan}
                              </option>
                            ))}
                          </select>
                          <button type="button" className={btnGhost} disabled={save.isPending || edit[p] === undefined} onClick={() => save.mutate({ matbaa: p, cari: edit[p] || null })}>
                            Kaydet
                          </button>
                          {m?.kaynak === 'elle' && (
                            <button type="button" className={btnGhost} disabled={save.isPending} onClick={() => save.mutate({ matbaa: p, kaldir: true })}>
                              Öneriye dön
                            </button>
                          )}
                        </div>
                      </td>
                    )}
                  </tr>
                );
              })}
            </tbody>
          </TableWrap>
        </div>
      </Panel>
      <Panel>
        <h2 className="px-1 text-[13px] font-extrabold">Tedarikçi carilerinde özel kod dağılımı</h2>
        <p className="mt-1 px-1 text-[11.5px] leading-snug text-canvas-muted">
          Ayar: matbaa özel kodu «{data.ayar.matbaa.join(', ')}», kağıtçı özel kodu «{data.ayar.kagit.join(', ')}», cari kod öneki {data.ayar.onEk}. Logo'daki yazım farklıysa portal ayarlarından düzeltilir;
          aşağıdaki dağılım Logo'daki gerçek yazımdır.
        </p>
        <div className="mt-2 flex flex-wrap gap-1.5">
          {data.ozelKodlar
            .slice()
            .sort((a, b) => b.cari - a.cari)
            .map((s) => (
              <span key={s.ozelKod ?? '-'} className="rounded-lg bg-slate-100 px-2 py-1 text-[11.5px]">
                {s.ozelKod || '(boş)'} · <b>{fmtInt(s.cari)}</b>
              </span>
            ))}
        </div>
      </Panel>
    </div>
  );
}
