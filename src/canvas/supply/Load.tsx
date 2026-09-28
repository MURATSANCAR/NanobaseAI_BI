import { useCallback, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { FileText, Mail } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import SqlInfo, { InfoLabel } from '../components/SqlInfo';
import { Loading, Note, TableWrap, btnGhost, field, td, th } from '../admin/ui';
import { Panel } from '../editorial/kit';
import Sheet from '../editorial/studio/reader/Sheet';
import { Tabs } from '../budget/parts';
import { fmtDay, fmtInt, fmtPct, fmtUnit, supplyApi, type Cell, type LoadTable } from './api';
import { CardLine, DraftSheet, ErrorNote, ExportLink, StatePill, SuggestionList, SupplyFrame, Warnings, cellTone, useDraft, useSupplyMeta } from './parts';

/** M52 Baskı yükü (/tedarik/yuk): ay × matbaa ısı tablosu, eşik aşımı listesi, yük dengeleme önerileri, kartı açılmamış
 *  baskı ihtiyacı ve baskı planı değişiklikleri. Sekme ve ufuk adres çubuğunda (?sekme=, ?aylar=). */

const TABS = [
  { key: 'tablo', label: 'Yük tablosu' },
  { key: 'cakisma', label: 'Eşik aşımı' },
  { key: 'oneri', label: 'Dengeleme önerileri' },
  { key: 'plan', label: 'Kartı açılmamış ihtiyaç' },
  { key: 'degisiklik', label: 'Plan değişiklikleri' },
] as const;
type Tab = (typeof TABS)[number]['key'];

export default function Load() {
  const [params, setParams] = useSearchParams();
  const tab: Tab = (TABS.find((t) => t.key === params.get('sekme'))?.key ?? 'tablo') as Tab;
  const months = Number(params.get('aylar') || 0) || undefined;
  const meta = useSupplyMeta();
  const me = meta.data?.me;
  const q = useQuery({ queryKey: ['supply', 'load', months ?? 0], queryFn: () => supplyApi.load(months), enabled: ENGINE_ENABLED });
  const [open, setOpen] = useState<{ printer: string; month: string; cell: Cell } | null>(null);
  const draft = useDraft();

  const update = useCallback(
    (next: Record<string, string | null>) => {
      const p = new URLSearchParams(params);
      for (const [k, v] of Object.entries(next)) {
        if (v) p.set(k, v);
        else p.delete(k);
      }
      setParams(p, { replace: true });
    },
    [params, setParams],
  );

  const t = q.data;
  const conflicts = t?.cakismalar.length ?? null;
  return (
    <SupplyFrame
      title="Baskı yükü"
      lead="Baskıdan henüz çıkmamış kartların baskı ayı × matbaa yükü (adet, iş, forma). Eşik: matbaanın girilen aylık kapasitesi; girilmemişse son 12 ayın en yüksek aylık yükü yalnız referanstır. Dengeleme önerisini kabul etmek CRM kartını değiştirmez; değişikliği Üretim yönetiminde ve CRM'de siz yaparsınız."
      aside={
        <div className="flex flex-wrap items-end justify-start gap-2 lg:justify-end">
          <label className="flex flex-col gap-1">
            <span className="text-[11px] font-bold uppercase tracking-wide text-canvas-muted">Ufuk</span>
            <select className={`${field} w-auto`} value={String(months ?? meta.data?.settings.loadMonths ?? 6)} onChange={(e) => update({ aylar: e.target.value })}>
              {[3, 4, 6, 9, 12].map((n) => (
                <option key={n} value={n}>
                  {n} ay
                </option>
              ))}
            </select>
          </label>
          <Link to="/tedarik/kapasite" className={btnGhost}>
            Matbaa kapasitesi
          </Link>
          {me?.canExport && <ExportLink href={supplyApi.exportUrl('yuk')} />}
        </div>
      }
    >
      <ErrorNote error={q.error} fallback="Baskı yükü okunamadı." />
      <Warnings items={t?.uyarilar} />
      <Tabs
        tabs={TABS.map((x) => ({ ...x, badge: x.key === 'cakisma' ? conflicts : null }))}
        value={tab}
        onChange={(k) => update({ sekme: k === 'tablo' ? null : k })}
      />
      {q.isLoading && <Loading />}
      {t && tab === 'tablo' && <HeatTable t={t} onOpen={(printer, month, cell) => setOpen({ printer, month, cell })} />}
      {t && tab === 'cakisma' && (
        <Panel>
          {t.cakismalar.length === 0 ? (
            <Note tone="ok">Eşiği aşan ay × matbaa yok.</Note>
          ) : (
            <div className="flex flex-col gap-3">
              {t.cakismalar.map((c) => (
                <article key={`${c.matbaa}-${c.ay}`} className="rounded-2xl border border-slate-100 bg-white/80 p-3">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <h3 className="flex items-center gap-1 text-[14px] font-extrabold">
                      {c.matbaa} · {c.ayAdi}
                      <SqlInfo k={t.kaynaklar} alan="cakismalar" label={`${c.matbaa} · ${c.ayAdi} yük ve eşik`} />
                    </h3>
                    <StatePill state={c.durum} />
                  </div>
                  <p className="mt-1 text-[12.5px] text-canvas-muted">
                    {fmtInt(c.jobs)} iş, {fmtInt(c.adet)} adet
                    {c.forma ? `, ${fmtInt(c.forma)} forma-baskı` : ''} ·{' '}
                    {c.kapasite
                      ? `kapasite ${fmtInt(c.kapasite.kapasiteAdet)} adet (${fmtPct(c.oran)})`
                      : `referans ${fmtInt(c.referans?.adet)} adet — ${fmtPct(c.oran)} (kapasite değil)`}
                  </p>
                  <div className="mt-2">
                    {c.cards.map((card) => (
                      <CardLine key={card.id} c={card} right={<span className="text-[11px] text-canvas-muted">{fmtDay(card.planBaski)}</span>} />
                    ))}
                  </div>
                </article>
              ))}
            </div>
          )}
        </Panel>
      )}
      {tab === 'oneri' && (
        <Panel>
          <p className="mb-3 px-1 text-[12px] leading-snug text-canvas-muted">
            Her gece eşiği aşan hücrelerden, hücre eşik altına inene kadar: baskı dosyası henüz matbaaya gitmemiş, matbaa onayı verilmemiş kart önce aynı matbaanın sonraki ayına (yayın ayını geçmeden), olmazsa zamanında teslimi daha düşük olmayan başka matbaaya önerilir. Sayılar kural hesabıdır.
          </p>
          <SuggestionList tur="yuk" canDecide={!!me?.canDecide} empty="Bekleyen yük dengeleme önerisi yok." />
        </Panel>
      )}
      {t && tab === 'plan' && (
        <Panel>
          {t.plan.hata && <Note tone="warn">{t.plan.hata}</Note>}
          <h2 className="flex items-center gap-1 px-1 text-[13px] font-extrabold">
            Baskı önerisi: {t.plan.seviyeler.join(', ')} — açık kartı yok
            <SqlInfo k={t.kaynaklar} alan="plan" label="Baskı önerisi ve ilk baskı girdisi" />
          </h2>
          <div className="mt-2">
            <TableWrap>
              <thead>
                <tr className="border-b border-slate-100">
                  <th className={th}>Kitap</th>
                  <th className={th}>Öneri</th>
                  <th className={`${th} text-right`}><InfoLabel k={t.kaynaklar} alan="plan.baskiOneri">Tükenme (ay)</InfoLabel></th>
                  <th className={`${th} text-right`}><InfoLabel k={t.kaynaklar} alan="plan.baskiOneri">Stok</InfoLabel></th>
                  <th className={`${th} text-right`}><InfoLabel k={t.kaynaklar} alan="plan.baskiOneri">Önerilen adet</InfoLabel></th>
                </tr>
              </thead>
              <tbody>
                {t.plan.baskiOneri.map((b) => (
                  <tr key={b.stokKodu} className="border-b border-slate-50 last:border-0">
                    <td className={td}>
                      <div className="font-bold">{b.kitap ?? '—'}</div>
                      <div className="text-[11px] text-canvas-muted">{b.stokKodu} · {b.yayinevi ?? ''}</div>
                    </td>
                    <td className={td}>{b.oneri}</td>
                    <td className={`${td} text-right font-mono tabular-nums`}>{b.tukenme === null ? '—' : b.tukenme.toFixed(1).replace('.', ',')}</td>
                    <td className={`${td} text-right font-mono tabular-nums`}>{fmtInt(b.stok)}</td>
                    <td className={`${td} text-right font-mono tabular-nums`}>{fmtInt(b.oneriAdet)}</td>
                  </tr>
                ))}
                {t.plan.baskiOneri.length === 0 && (
                  <tr>
                    <td className={td} colSpan={5}>
                      {t.plan.raporVar ? 'Kartı açılmamış riskli kitap yok.' : 'Baskı önerisi raporunun verisi henüz hazır değil.'}
                    </td>
                  </tr>
                )}
              </tbody>
            </TableWrap>
          </div>
          <h2 className="mt-4 px-1 text-[13px] font-extrabold">Onaylı ilk baskı — üretim kartı yok</h2>
          <div className="mt-2">
            {t.plan.ilkBaski.length === 0 ? (
              <Note tone="info">Kartı açılmamış onaylı ilk baskı kararı yok.</Note>
            ) : (
              <TableWrap>
                <thead>
                  <tr className="border-b border-slate-100">
                    <th className={th}>Kitap</th>
                    <th className={th}>Yayın ayı</th>
                    <th className={`${th} text-right`}><InfoLabel k={t.kaynaklar} alan="plan.ilkBaski">Adet</InfoLabel></th>
                  </tr>
                </thead>
                <tbody>
                  {t.plan.ilkBaski.map((b, i) => (
                    <tr key={`${b.stokKodu ?? 'yeni'}-${i}`} className="border-b border-slate-50 last:border-0">
                      <td className={td}>
                        <div className="font-bold">{b.kitap ?? '—'}</div>
                        <div className="text-[11px] text-canvas-muted">{b.stokKodu ?? 'stok kodu açılmamış'}</div>
                      </td>
                      <td className={td}>{b.yayinAyi ?? '—'}</td>
                      <td className={`${td} text-right font-mono tabular-nums`}>{fmtInt(b.adet)}</td>
                    </tr>
                  ))}
                </tbody>
              </TableWrap>
            )}
          </div>
        </Panel>
      )}
      {t && tab === 'degisiklik' && (
        <Panel>
          <p className="px-1 text-[12.5px]">
            <SqlInfo k={t.kaynaklar} alan="degisiklikler" label="Plan değişiklikleri" className="mr-1" />
            Son 12 ayda CRM'de {fmtInt(t.degisiklikler.toplam)} baskı tarihi değişikliği;{' '}
            {fmtInt(Object.keys(t.degisiklikler.acikKartDegisiklik).length)} açık kartta en az bir değişiklik var
            {t.degisiklikler.kartsiz ? `, ${fmtInt(t.degisiklikler.kartsiz)} kayıt karta bağlı değil` : ''}.
          </p>
          <ul className="mt-2 flex flex-col gap-1">
            {t.degisiklikler.sebepler.map((s) => (
              <li key={s.sebep} className="flex items-center justify-between rounded-xl bg-white/80 px-3 py-2 text-[12.5px]">
                <span>{s.sebep}</span>
                <span className="font-mono font-bold tabular-nums">{fmtInt(s.adet)}</span>
              </li>
            ))}
          </ul>
        </Panel>
      )}

      <Sheet
        open={!!open}
        onClose={() => setOpen(null)}
        wide
        title={open ? `${open.printer} · ${t?.aylar.find((m) => m.key === open.month)?.label ?? open.month}` : ''}
        subtitle={
          open
            ? `${fmtInt(open.cell.jobs)} iş · ${fmtInt(open.cell.adet)} adet${open.cell.forma ? ` · ${fmtInt(open.cell.forma)} forma-baskı` : ''}${
                open.cell.gecenYil ? ` · geçen yıl aynı ay ${fmtInt(open.cell.gecenYil.adet)} adet` : ''
              }`
            : undefined
        }
      >
        {open && (
          <div className="flex flex-col">
            <div className="flex items-center gap-1 pb-1 text-[11px] font-semibold text-canvas-muted">
              <InfoLabel k={t?.kaynaklar} alan="satirlar[].hucreler" label="Hücre: iş, adet, forma ve birim maliyet">Rakamların sorgusu</InfoLabel>
            </div>
            {open.cell.cards.map((c) => (
              <div key={c.id} className="border-b border-slate-100 py-2 last:border-0">
                <CardLine c={c} />
                <div className="flex flex-wrap items-center justify-between gap-2 text-[11.5px] text-canvas-muted">
                  <span>
                    Baskı planı {fmtDay(c.planBaski)} · dosya {fmtDay(c.planDosya)}
                    {c.yayin ? ` · hedef yayın ${fmtDay(c.yayin)}` : ''}
                    {c.m9Maliyet && c.m9Maliyet.maliyet !== null ? ` · birim maliyet ${fmtUnit(c.m9Maliyet.maliyet)} (${c.m9Maliyet.kaynak ?? ''})` : ''}
                  </span>
                  <span className="flex gap-1.5">
                    <Link to={`/uretim?kart=${c.id}`} className={btnGhost}>
                      Üretim kartı
                    </Link>
                    {me?.canDecide && (
                      <>
                        <button type="button" className={btnGhost} disabled={draft.make.isPending} onClick={() => draft.make.mutate({ tur: 'sartname', kartId: c.id })}>
                          <FileText aria-hidden className="h-4 w-4" />
                          Şartname
                        </button>
                        {c.gecikme > 0 && (
                          <button type="button" className={btnGhost} disabled={draft.make.isPending} onClick={() => draft.make.mutate({ tur: 'eskalasyon', kartId: c.id })}>
                            <Mail aria-hidden className="h-4 w-4" />
                            Gecikme yazısı
                          </button>
                        )}
                      </>
                    )}
                  </span>
                </div>
              </div>
            ))}
          </div>
        )}
      </Sheet>
      <DraftSheet draft={draft.draft} onClose={draft.close} />
    </SupplyFrame>
  );
}

function HeatTable({ t, onOpen }: { t: LoadTable; onOpen: (printer: string, month: string, cell: Cell) => void }) {
  if (!t.satirlar.length) return <Note tone="info">Baskıdan çıkmamış açık kart yok.</Note>;
  return (
    <Panel>
      <TableWrap>
        <thead>
          <tr className="border-b border-slate-100">
            <th className={th}><InfoLabel k={t.kaynaklar} alan="satirlar" label="Baskı yükü (hücreler)">Matbaa</InfoLabel></th>
            {t.aylar.map((m) => (
              <th key={m.key} className={`${th} text-right`}>
                {m.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {t.satirlar.map((r) => (
            <tr key={r.matbaa} className="border-b border-slate-50 last:border-0">
              <td className={td}>
                <div className="font-bold">{r.matbaa}</div>
                <div className="flex items-center gap-1 text-[10.5px] text-canvas-muted">
                  {r.kapasiteVar ? 'kapasite girili' : r.referans ? `referans ${fmtInt(r.referans.adet)} adet/ay` : 'eşik ölçülemedi'}
                  {r.referans && <SqlInfo k={t.kaynaklar} alan="satirlar[].referans" label={`${r.matbaa} referans yükü`} />}
                </div>
              </td>
              {t.aylar.map((m) => {
                const c = r.hucreler[m.key];
                return (
                  <td key={m.key} className={`${td} text-right`}>
                    {c.jobs ? (
                      <button
                        type="button"
                        onClick={() => onOpen(r.matbaa, m.key, c)}
                        aria-label={`${r.matbaa}, ${m.label}: ${c.jobs} iş, ${fmtInt(c.adet)} adet`}
                        className={`inline-flex min-h-11 min-w-[76px] flex-col items-end justify-center rounded-lg px-2 py-1 transition-transform duration-150 ease-out active:scale-[0.97] sm:min-h-0 ${cellTone(c.durum, c.oran)}`}
                      >
                        <span className="font-mono text-[12.5px] font-bold tabular-nums">{fmtInt(c.adet)}</span>
                        <span className="text-[10.5px]">{c.jobs} iş</span>
                      </button>
                    ) : (
                      <span className="text-canvas-muted">·</span>
                    )}
                  </td>
                );
              })}
            </tr>
          ))}
          <tr className="bg-slate-50/80">
            <td className={`${td} font-extrabold`}><InfoLabel k={t.kaynaklar} alan="toplam" label="Ay toplamı">Toplam</InfoLabel></td>
            {t.aylar.map((m) => (
              <td key={m.key} className={`${td} text-right font-mono font-bold tabular-nums`}>
                {fmtInt(t.toplam[m.key]?.adet)}
                <div className="text-[10.5px] font-semibold text-canvas-muted">{fmtInt(t.toplam[m.key]?.jobs)} iş</div>
              </td>
            ))}
          </tr>
        </tbody>
      </TableWrap>
      <p className="mt-2 px-1 text-[11.5px] leading-snug text-canvas-muted">
        {t.referansNotu} Ufuk dışında kalan (daha ileri ayda planlı) {fmtInt(t.ufukDisi)} kart tabloda yok.
        <SqlInfo k={t.kaynaklar} alan="ufukDisi" label="Ufuk dışı kart" className="ml-0.5" />
      </p>
    </Panel>
  );
}
