import { useMemo } from 'react';
import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { ENGINE_ENABLED } from '../engine';
import SqlInfo, { InfoLabel } from '../components/SqlInfo';
import { Note, Pill, TableWrap, errText, td, th } from '../admin/ui';
import { Kpi, KpiRow, Panel } from '../editorial/kit';
import { PROGRAM_TONE, fmtDay, fmtInt, fmtShare, okurApi, type InventoryRow, type TrendPoint } from './api';
import { CoreMissing, OkurFrame, ShareBar } from './parts';

/** M37 «Okur kitlesi» (ilk açılış): kaynak ve kayıt tipine göre okur sayısı, KVKK/İYS/kanal izin oranları, izin çelişkileri,
 *  aylık eğilim, yaklaşan programlar, segment ve yorum durumu. Yalnız sayı; kişi adı hiçbir yerde yok. */
export default function AudienceScreen() {
  const ov = useQuery({ queryKey: ['okur', 'overview'], queryFn: okurApi.overview, enabled: ENGINE_ENABLED, staleTime: 60_000 });
  const d = ov.data;
  const inv = d?.envanter;
  const rows = inv && inv.bagli ? inv.satirlar : [];
  const sum = (k: keyof InventoryRow) => {
    const vals = rows.map((r) => r[k]).filter((x): x is number => typeof x === 'number');
    return vals.length ? vals.reduce((a, b) => a + b, 0) : null;
  };
  const total = inv && inv.bagli ? inv.toplam : null;
  const consent = d?.izin;
  const consentTotal = consent && consent.bagli ? consent.toplam : null;
  const monthly = useMemo(() => lastPerMonth(d?.egilim.noktalar ?? []), [d]);
  const segs = d?.segmentSayilari ?? {};
  const k = d?.kaynaklar;

  return (
    <OkurFrame
      crumb="Okur kitlesi"
      title="Okur kitlesi ve izin sağlığı"
      lead="Kime ulaşabileceğimizin sayısı: okur kayıtlarının kaynağı, KVKK ve İYS onayı, e-posta ve SMS izni, ilgi alanı doluluğu ve izin çelişkileri. Yalnız toplam sayılar gösterilir; kişi listesi yoktur. Düzeltme CRM'de yapılır."
      source="Kaynak: okur veri tabanı · CRM · portal kaydı"
    >
      {!ENGINE_ENABLED && <Note tone="warn">Bu kurulumda veri bağlantısı tanımlı değil.</Note>}
      {ov.error && <Note tone="err">{errText(ov.error, 'Özet okunamadı.')}</Note>}
      {ov.isLoading && <div className="py-8 text-center text-[12px] text-canvas-muted">Yükleniyor…</div>}
      {inv && !inv.bagli && <CoreMissing message={inv.mesaj} />}
      {d && (
        <KpiRow>
          <Kpi label="Okur kaydı" value={fmtInt(total)} help={inv && inv.bagli && inv.tekil !== null ? `Tekil ${fmtInt(inv.tekil)}` : 'Kaynak kayıtları toplamı'} info={<SqlInfo k={k} alan="envanter" label="Okur kaydı" />} />
          <Kpi label="KVKK onaylı" value={fmtShare(sum('kvkkOnayli'), total)} help={`${fmtInt(sum('kvkkOnayli'))} kayıt`} info={<SqlInfo k={k} alan="envanter" label="KVKK onaylı" />} />
          <Kpi label="E-posta izinli" value={fmtInt(sum('epostaIzinli'))} help={`SMS izinli ${fmtInt(sum('smsIzinli'))}`} info={<SqlInfo k={k} alan="envanter" label="E-posta ve SMS izinli" />} />
          <Kpi label="İzin çelişkisi" value={fmtInt(consentTotal)} help={consent && consent.bagli && consent.onceki !== undefined && consent.onceki !== null ? `Önceki ölçüm ${fmtInt(consent.onceki)}` : 'Hedef: 0'} info={<SqlInfo k={k} alan="izin" label="İzin çelişkisi" />} />
        </KpiRow>
      )}

      {inv && inv.bagli && (
        <Panel>
          <h2 className="flex items-center gap-1 text-[15px] font-extrabold tracking-tight">Kaynak ve kayıt tipi<SqlInfo k={k} alan="envanter" label="Kaynak ve kayıt tipi, tazelik" /></h2>
          <p className="mb-2 text-[12px] text-canvas-muted">Her satır okur veri tabanının verdiği sayıdır; oran satırın toplamına göredir.</p>
          <TableWrap>
            <thead>
              <tr>
                <th className={th}>Kaynak</th>
                <th className={th}>Kayıt tipi</th>
                <th className={`${th} text-right`}><InfoLabel k={k} alan="envanter.satirlar">Kayıt</InfoLabel></th>
                <th className={th}><InfoLabel k={k} alan="envanter.satirlar">KVKK onayı</InfoLabel></th>
                <th className={th}><InfoLabel k={k} alan="envanter.satirlar">İYS onayı</InfoLabel></th>
                <th className={th}><InfoLabel k={k} alan="envanter.satirlar">E-posta izni</InfoLabel></th>
                <th className={th}><InfoLabel k={k} alan="envanter.satirlar">SMS izni</InfoLabel></th>
                <th className={th}><InfoLabel k={k} alan="envanter.satirlar">İlgi alanı dolu</InfoLabel></th>
                <th className={`${th} text-right`}><InfoLabel k={k} alan="envanter.satirlar">Silinebilir</InfoLabel></th>
                <th className={`${th} text-right`}><InfoLabel k={k} alan="envanter.satirlar">18 yaş altı olası</InfoLabel></th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={`${r.kaynak}|${r.kayitTipi}`} className="border-t border-slate-100">
                  <td className={`${td} font-bold`}>{r.kaynak}</td>
                  <td className={td}>{r.kayitTipi || '—'}</td>
                  <td className={`${td} text-right font-mono tabular-nums`}>{fmtInt(r.toplam)}</td>
                  <td className={td}><ShareBar part={r.kvkkOnayli} total={r.toplam} /></td>
                  <td className={td}><ShareBar part={r.iysOnayli} total={r.toplam} /></td>
                  <td className={td}><ShareBar part={r.epostaIzinli} total={r.toplam} /></td>
                  <td className={td}><ShareBar part={r.smsIzinli} total={r.toplam} /></td>
                  <td className={td}><ShareBar part={r.ilgiAlaniDolu} total={r.toplam} /></td>
                  <td className={`${td} text-right font-mono tabular-nums`}>{fmtInt(r.silinebilir)}</td>
                  <td className={`${td} text-right font-mono tabular-nums`}>{fmtInt(r.cocukOlasi)}</td>
                </tr>
              ))}
              {!rows.length && (
                <tr><td className={`${td} text-canvas-muted`} colSpan={10}>Okur veri tabanı kaynak kırılımı vermedi.</td></tr>
              )}
            </tbody>
          </TableWrap>
          {inv.tazelik.length > 0 && (
            <div className="mt-2 flex flex-wrap gap-2 text-[11.5px] text-canvas-muted">
              {inv.tazelik.map((t, i) => <span key={i}>{t.kaynak ?? 'kaynak'}: {t.sonOkuma ? fmtDay(t.sonOkuma) : 'okunmadı'}</span>)}
            </div>
          )}
        </Panel>
      )}

      <div className="grid grid-cols-1 gap-3 lg:grid-cols-2 lg:gap-4">
        {consent && consent.bagli && (
          <Panel>
            <h2 className="flex items-center gap-1 text-[15px] font-extrabold tracking-tight">İzin sağlığı<SqlInfo k={k} alan="izin" label="İzin sağlığı" /></h2>
            <p className="mb-2 text-[12px] text-canvas-muted">Çelişki türü başına kayıt sayısı. Kişiler burada listelenmez; düzeltme CRM'de yapılır.</p>
            <ul className="flex flex-col gap-1.5">
              {consent.items.map((c) => (
                <li key={c.tur} className="flex items-start justify-between gap-3 rounded-xl bg-white/80 px-3 py-2">
                  <div className="min-w-0">
                    <div className="text-[12.5px] font-bold">{c.ad}</div>
                    {c.aciklama && <div className="text-[11.5px] leading-snug text-canvas-muted">{c.aciklama}</div>}
                  </div>
                  <span className={`shrink-0 font-mono text-[14px] font-bold tabular-nums ${c.sayi ? 'text-amber-700' : 'text-emerald-700'}`}>{fmtInt(c.sayi)}</span>
                </li>
              ))}
              {!consent.items.length && <li className="text-[12px] text-canvas-muted">Çelişki türü yok.</li>}
            </ul>
          </Panel>
        )}

        <Panel>
          <h2 className="flex items-center gap-1 text-[15px] font-extrabold tracking-tight">Aylık eğilim<SqlInfo k={k} alan="egilim" label="Aylık eğilim" /></h2>
          <p className="mb-2 text-[12px] text-canvas-muted">Her ayın son gece ölçümü (son 12 ay). İlk ölçüm gece turunda alınır.</p>
          {monthly.length ? (
            <TableWrap>
              <thead>
                <tr>
                  <th className={th}>Ay</th>
                  <th className={`${th} text-right`}><InfoLabel k={k} alan="egilim">Okur kaydı</InfoLabel></th>
                  <th className={`${th} text-right`}><InfoLabel k={k} alan="egilim">KVKK onaylı</InfoLabel></th>
                  <th className={`${th} text-right`}><InfoLabel k={k} alan="egilim">E-posta izinli</InfoLabel></th>
                  <th className={`${th} text-right`}><InfoLabel k={k} alan="egilim">İzin çelişkisi</InfoLabel></th>
                </tr>
              </thead>
              <tbody>
                {monthly.map((p) => (
                  <tr key={p.tarih} className="border-t border-slate-100">
                    <td className={td}>{p.tarih.slice(0, 7)}</td>
                    <td className={`${td} text-right font-mono tabular-nums`}>{fmtInt(p.toplam)}</td>
                    <td className={`${td} text-right font-mono tabular-nums`}>{fmtInt(p.kvkkOnayli)}</td>
                    <td className={`${td} text-right font-mono tabular-nums`}>{fmtInt(p.epostaIzinli)}</td>
                    <td className={`${td} text-right font-mono tabular-nums`}>{fmtInt(p.izinCeliskisi)}</td>
                  </tr>
                ))}
              </tbody>
            </TableWrap>
          ) : (
            <div className="py-4 text-[12px] text-canvas-muted">Henüz gece ölçümü yok.</div>
          )}
        </Panel>

        <Panel>
          <div className="flex items-baseline justify-between gap-2">
            <h2 className="flex items-center gap-1 text-[15px] font-extrabold tracking-tight">Yaklaşan programlar<SqlInfo k={k} alan="yaklasanProgramlar" label="Yaklaşan programlar" /></h2>
            <Link to="/okur-toplulugu/programlar" className="text-[12px] font-bold text-canvas-violet hover:underline">Takvim</Link>
          </div>
          <p className="mb-2 text-[12px] text-canvas-muted">Önümüzdeki 30 gün.</p>
          <ul className="flex flex-col gap-1.5">
            {(d?.yaklasanProgramlar ?? []).map((p) => (
              <li key={p.id} className="flex flex-wrap items-center gap-2 rounded-xl bg-white/80 px-3 py-2">
                <span className="font-mono text-[12px] font-bold tabular-nums">{fmtDay(p.tarih)}</span>
                <Pill tone={PROGRAM_TONE[p.durum]}>{p.turAdi}</Pill>
                <span className="min-w-0 break-words text-[12.5px] font-bold">{p.ad}</span>
                {p.sehir && <span className="text-[11.5px] text-canvas-muted">{p.sehir}</span>}
              </li>
            ))}
            {d && !d.yaklasanProgramlar.length && <li className="text-[12px] text-canvas-muted">30 gün içinde program yok.</li>}
          </ul>
        </Panel>

        <Panel>
          <h2 className="flex items-center gap-1 text-[15px] font-extrabold tracking-tight">Segment ve yorum durumu<SqlInfo k={k} alan="segmentSayilari" label="Segment sayıları" /><SqlInfo k={k} alan="yorum" label="Gece yorum özeti" /></h2>
          <div className="mt-2 grid grid-cols-2 gap-2">
            <Link to="/okur-toplulugu/segmentler?durum=onay_bekliyor" className="rounded-xl bg-white/80 px-3 py-2 transition-transform duration-150 ease-out active:scale-[0.98]">
              <div className="text-[10.5px] font-bold uppercase tracking-wide text-canvas-muted">Onay bekleyen segment</div>
              <div className="font-mono text-[18px] font-bold tabular-nums">{fmtInt(segs.onay_bekliyor ?? 0)}</div>
            </Link>
            <Link to="/okur-toplulugu/segmentler?durum=onaylandi" className="rounded-xl bg-white/80 px-3 py-2 transition-transform duration-150 ease-out active:scale-[0.98]">
              <div className="text-[10.5px] font-bold uppercase tracking-wide text-canvas-muted">Onaylı segment</div>
              <div className="font-mono text-[18px] font-bold tabular-nums">{fmtInt(segs.onaylandi ?? 0)}</div>
            </Link>
            <Link to="/okur-toplulugu/yorumlar" className="rounded-xl bg-white/80 px-3 py-2 transition-transform duration-150 ease-out active:scale-[0.98]">
              <div className="text-[10.5px] font-bold uppercase tracking-wide text-canvas-muted">Cevapsız yorum</div>
              <div className="font-mono text-[18px] font-bold tabular-nums">{d?.yorum ? fmtInt(d.yorum.cevapsiz) : '—'}</div>
            </Link>
            <div className="rounded-xl bg-white/80 px-3 py-2">
              <div className="text-[10.5px] font-bold uppercase tracking-wide text-canvas-muted">Cevaplanan yorum</div>
              <div className="font-mono text-[18px] font-bold tabular-nums">{d?.yorum ? fmtInt(d.yorum.cevaplandi) : '—'}</div>
            </div>
          </div>
          {!d?.yorum && <p className="mt-2 text-[11.5px] text-canvas-muted">Yorum sayısı gece turunda ölçülür; anlık liste Yorumlar bölümünde.</p>}
        </Panel>
      </div>
    </OkurFrame>
  );
}

function lastPerMonth(points: TrendPoint[]): TrendPoint[] {
  const by = new Map<string, TrendPoint>();
  for (const p of points) by.set(p.tarih.slice(0, 7), p);
  return [...by.values()].sort((a, b) => (a.tarih < b.tarih ? 1 : -1));
}
