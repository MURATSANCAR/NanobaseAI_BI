import { useState } from 'react';
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Download, Eye, EyeOff, FileSpreadsheet, Link2, X } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import { Loading, Note, Pill, TableWrap, btnGhost, errText, field, label as labelCls, td, th } from '../admin/ui';
import { Pager, Panel, useDebounced } from '../editorial/kit';
import { fmtDay, fmtInt, fmtNum, fmtPct, fmtTl, pazarApi, type MatrixRow, type RakipKaynak } from './api';
import { CategorySelect, Stat, useCategories, useMeta, useRakipKaynak } from './parts';
import SqlInfo, { InfoLabel } from '../components/SqlInfo';
import { kaynakOf } from '../components/kaynakOf';
import { xlsxUrl } from '../components/excel';

/** Rakipler: yayınevi × kategori fiyat, sayfa ve format matrisi (TİMAŞ satırları aynı ölçülerle), izlenen rakipler,
 *  seçilen yayınevinin kayıtları. Rakip satırları seçilen kaynaktan (Başarı kataloğu ya da CRM rakip kayıtları).
 *  Kategori süzgeci yalnız eşlemesi onaylı rakip kayıtlarını sayar. */
export default function CompetitorMatrix() {
  const qc = useQueryClient();
  const meta = useMeta();
  const cats = useCategories();
  const src = useRakipKaynak();
  const [kategori, setKategori] = useState('');
  const [sayfaMin, setSayfaMin] = useState('');
  const [sayfaMax, setSayfaMax] = useState('');
  const [yq, setYq] = useState('');
  const [oneri, setOneri] = useState(false);
  const [izlenen, setIzlenen] = useState(false);
  const [all, setAll] = useState(false);
  const [picked, setPicked] = useState<string | null>(null);
  const dyq = useDebounced(yq, 300);
  const dMin = useDebounced(sayfaMin, 400);
  const dMax = useDebounced(sayfaMax, 400);
  const filter = { kategori, oneri, sayfaMin: Number(dMin) || '', sayfaMax: Number(dMax) || '', yayinevi: dyq, izlenen, kaynak: src.kaynak } as const;
  const m = useQuery({ queryKey: ['pazar', 'matrix', filter], queryFn: () => pazarApi.matrix(filter), enabled: ENGINE_ENABLED && src.ready, placeholderData: keepPreviousData });
  const wl = useQuery({ queryKey: ['pazar', 'watchlist'], queryFn: pazarApi.watchlist, enabled: ENGINE_ENABLED });
  const watchOf = (y: string) => (wl.data?.items ?? []).find((w) => w.yayinevi === y && (w.kategoriId ?? '') === kategori);

  const toggle = useMutation({
    mutationFn: async (row: MatrixRow) => {
      const hit = watchOf(row.yayinevi);
      if (hit) await pazarApi.deleteWatch(hit.id);
      else await pazarApi.addWatch(row.yayinevi, kategori || null);
      return !hit;
    },
    onSuccess: (added, row) => {
      toast.success(added ? `${row.yayinevi} izleniyor${kategori ? ' (bu kategoride)' : ''}.` : `${row.yayinevi} izlemeden çıkarıldı.`);
      qc.invalidateQueries({ queryKey: ['pazar', 'watchlist'] });
      qc.invalidateQueries({ queryKey: ['pazar', 'matrix'] });
    },
    onError: (e) => toast.error(errText(e, 'İzleme listesi güncellenemedi.') ?? ''),
  });
  const unwatch = useMutation({
    mutationFn: pazarApi.deleteWatch,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['pazar', 'watchlist'] });
      qc.invalidateQueries({ queryKey: ['pazar', 'matrix'] });
    },
    onError: (e) => toast.error(errText(e, 'İzleme listesi güncellenemedi.') ?? ''),
  });

  const d = m.data;
  const rows = d ? (all ? d.rows : d.rows.slice(0, 40)) : [];
  const catLabel = d?.kategori?.yol ?? 'Bütün kategoriler';
  return (
    <div className="flex flex-col gap-3 lg:gap-4">
      <Panel>
        <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-[minmax(0,1.4fr)_repeat(2,minmax(0,0.5fr))_minmax(0,1fr)]">
          <label className="flex min-w-0 flex-col gap-1">
            <span className={labelCls}>Timaş kategorisi</span>
            <CategorySelect value={kategori} onChange={setKategori} categories={cats.data?.items ?? []} className={field} />
          </label>
          <label className="flex min-w-0 flex-col gap-1">
            <span className={labelCls}>Sayfa en az</span>
            <input inputMode="numeric" value={sayfaMin} onChange={(e) => setSayfaMin(e.target.value.replace(/\D/g, ''))} className={field} placeholder="örn. 200" />
          </label>
          <label className="flex min-w-0 flex-col gap-1">
            <span className={labelCls}>Sayfa en çok</span>
            <input inputMode="numeric" value={sayfaMax} onChange={(e) => setSayfaMax(e.target.value.replace(/\D/g, ''))} className={field} placeholder="örn. 300" />
          </label>
          <label className="flex min-w-0 flex-col gap-1">
            <span className={labelCls}>Yayınevi ara</span>
            <input value={yq} onChange={(e) => setYq(e.target.value)} className={field} placeholder="Yayınevi adı" />
          </label>
        </div>
        <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-2 text-[12.5px] font-semibold">
          <label className="inline-flex min-h-11 items-center gap-2 sm:min-h-0">
            <input type="checkbox" checked={oneri} onChange={(e) => setOneri(e.target.checked)} className="h-4 w-4 accent-canvas-violet" />
            Onay bekleyen eşleme önerilerini de say
          </label>
          <label className="inline-flex min-h-11 items-center gap-2 sm:min-h-0">
            <input type="checkbox" checked={izlenen} onChange={(e) => setIzlenen(e.target.checked)} className="h-4 w-4 accent-canvas-violet" />
            Yalnız izlenen yayınevleri
          </label>
          {meta.data?.me.canExport && d && (
            <>
              <a href={pazarApi.matrixCsvUrl(filter)} className={`${btnGhost} ml-auto`}>
                <Download aria-hidden className="h-4 w-4" /> CSV
              </a>
              <a href={xlsxUrl(pazarApi.matrixCsvUrl(filter))} className={btnGhost}>
                <FileSpreadsheet aria-hidden className="h-4 w-4" /> Excel
              </a>
            </>
          )}
        </div>
        {(wl.data?.items.length ?? 0) > 0 && (
          <div className="mt-2 flex flex-wrap items-center gap-1.5">
            <span className={labelCls}>İzlenen</span>
            {wl.data!.items.map((w) => (
              <span key={w.id} className="inline-flex items-center gap-1 rounded-lg bg-canvas-violet/10 py-0.5 pl-2 pr-0.5 text-[11.5px] font-bold text-canvas-violet">
                {w.yayinevi}{w.kategoriYol ? ` · ${w.kategoriYol}` : ''}
                <button type="button" aria-label={`${w.yayinevi} izlemeden çıkar`} onClick={() => unwatch.mutate(w.id)} className="grid h-7 w-7 place-items-center rounded-md hover:bg-canvas-violet/15">
                  <X aria-hidden className="h-3.5 w-3.5" />
                </button>
              </span>
            ))}
          </div>
        )}
      </Panel>

      {m.isLoading && <Loading />}
      {m.error && <Note tone="err">{errText(m.error, 'Matris açılamadı.')}</Note>}
      {d && (
        <>
          <div className="grid grid-cols-2 gap-2 lg:grid-cols-5">
            <Stat info={<SqlInfo k={kaynakOf(d)} alan="_hepsi" label="Rakip kitap" />} label="Rakip kitap" value={fmtInt(d.rakipOzet.kitap)} help={`${fmtInt(d.rakipOzet.yayinevi)} yayınevi · ${catLabel}`} />
            <Stat info={<SqlInfo k={kaynakOf(d)} alan="_hepsi" label="Rakip medyan fiyat" />} label="Rakip medyan fiyat" value={fmtTl(d.rakipOzet.medyan)} help={`Çeyrekler ${fmtTl(d.rakipOzet.q1)} – ${fmtTl(d.rakipOzet.q3)}`} explain="Medyan: kitaplar fiyata göre dizildiğinde ortadaki kitabın fiyatı; birkaç çok pahalı kitaptan etkilenmez. Çeyrekler, kitapların ortadaki yarısının fiyat aralığıdır." />
            <Stat info={<SqlInfo k={kaynakOf(d)} alan="_hepsi" label="Timaş medyan fiyat" />} label="Timaş medyan fiyat" value={fmtTl(d.timas[0]?.medyan)} help={`${fmtInt(d.timas[0]?.kitap)} kitap · KDV dahil`} />
            <Stat
              info={<SqlInfo k={kaynakOf(d)} alan="_hepsi" label="Timaş'ın konumu" />}
              label="Timaş'ın konumu"
              value={d.timasKonum === null ? '—' : fmtPct(d.timasKonum, 0)}
              help="Rakip fiyatlarının bu kadarı Timaş medyanının altında"
              explain="Rakip kitapların yüzde kaçının bizim ortadaki fiyatımızdan ucuz olduğu. Yüksekse fiyatlarımız rakiplerin çoğundan pahalıdır."
            />
            <Stat info={<SqlInfo k={kaynakOf(d)} alan="_hepsi" label="Sayfa başı (medyan)" />} label="Sayfa başı (medyan)" explain="Fiyatın sayfa sayısına bölümü; farklı kalınlıktaki kitapları karşılaştırmayı sağlar. Rakiplerin ortadaki değeri, altında bizimki." value={`${fmtNum(round2(d.rakipOzet.sayfaBasiMedyan))} ₺`} help={`Timaş: ${fmtNum(round2(d.timas[0]?.sayfaBasiMedyan))} ₺`} />
          </div>
          {d.eslenmemis !== null && d.eslenmemis > 0 && (
            <Note tone="warn">
              Kategorisi onaylanmamış {fmtInt(d.eslenmemis)} rakip kaydı bu süzgece girmedi. Kapsamı genişletmek için «Kategori eşlemesi» bölümünde kararları verin.
            </Note>
          )}
          <MatrixTable
            k={kaynakOf(d)}
            rows={[...d.timas, ...rows]}
            newDays={d.newDays}
            watched={(y) => !!watchOf(y)}
            onWatch={(r) => toggle.mutate(r)}
            onPick={(y) => setPicked((p) => (p === y ? null : y))}
            picked={picked}
          />
          {d.rows.length > 40 && (
            <button type="button" onClick={() => setAll((v) => !v)} className="min-h-11 self-start text-[12.5px] font-extrabold text-canvas-violet hover:underline sm:min-h-0">
              {all ? 'İlk 40 yayınevini göster' : `Tümünü göster (${fmtInt(d.rows.length)} yayınevi)`}
            </button>
          )}
          <p className="text-[11.5px] leading-snug text-canvas-muted">
            {d.note} Medyan ve çeyrekler fiyatı girilmiş kayıtlardan.{d.yeniNot ? ` ${d.yeniNot}` : ''}
          </p>
          {picked && <PublisherBooks yayinevi={picked} kategori={kategori} kaynak={d.kaynak ?? src.kaynak} onClose={() => setPicked(null)} />}
        </>
      )}
    </div>
  );
}

const round2 = (v: number | null | undefined) => (v === null || v === undefined ? null : Math.round(v * 100) / 100);

function MatrixTable({ rows, newDays, watched, onWatch, onPick, picked, k }: {
  /** Sorgu bilgisi (matris cevabı): kolonların hesabı ve okumaları. */
  k?: ReturnType<typeof kaynakOf>;
  rows: MatrixRow[];
  newDays: number;
  watched: (y: string) => boolean;
  onWatch: (r: MatrixRow) => void;
  onPick: (y: string) => void;
  picked: string | null;
}) {
  return (
    <TableWrap>
      <thead>
        <tr className="border-b border-slate-100">
          <th className={th}>Yayınevi</th>
          <th className={`${th} text-right`}><InfoLabel k={k} alan="_hepsi">Kitap</InfoLabel></th>
          <th className={`${th} text-right`}>Medyan fiyat</th>
          <th className={`${th} text-right`}>Fiyat bandı (çeyrekler)</th>
          <th className={`${th} text-right`}>Medyan sayfa</th>
          <th className={`${th} text-right`}>Sayfa başı</th>
          <th className={`${th} text-right`}>Son {newDays} gün</th>
          <th className={th}>Cilt</th>
          <th className={th}><span className="sr-only">İzle</span></th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => (
          <tr key={`${r.own ? 't' : 'r'}:${r.yayinevi}`} className={`border-b border-slate-50 last:border-0 ${r.own ? 'bg-canvas-violet/5' : ''} ${picked === r.yayinevi ? 'bg-amber-50/70' : ''}`}>
            <td className={`${td} font-semibold`}>
              {r.own ? (
                <span className={r.total ? 'font-extrabold' : 'pl-3'}>{r.yayinevi}</span>
              ) : (
                <button type="button" onClick={() => onPick(r.yayinevi)} className="min-h-11 text-left hover:text-canvas-violet hover:underline sm:min-h-0">
                  {r.yayinevi}
                </button>
              )}
            </td>
            <td className={`${td} text-right font-mono tabular-nums`}>{fmtInt(r.kitap)}{r.fiyatli !== r.kitap && <span className="text-canvas-muted"> ({fmtInt(r.fiyatli)} fiyatlı)</span>}</td>
            <td className={`${td} text-right font-mono font-bold tabular-nums`}>{fmtTl(r.medyan)}</td>
            <td className={`${td} whitespace-nowrap text-right font-mono tabular-nums text-canvas-muted`}>{r.q1 === null ? '—' : `${fmtTl(r.q1)} – ${fmtTl(r.q3)}`}</td>
            <td className={`${td} text-right font-mono tabular-nums`}>{fmtInt(r.sayfaMedyan)}</td>
            <td className={`${td} text-right font-mono tabular-nums`}>{r.sayfaBasiMedyan === null ? '—' : `${fmtNum(round2(r.sayfaBasiMedyan))} ₺`}</td>
            <td className={`${td} text-right font-mono tabular-nums`}>{fmtInt(r.yeni)}</td>
            <td className={`${td} text-[11.5px] text-canvas-muted`}>{r.cilt.map((c) => `${c.ad} (${fmtInt(c.kitap)})`).join(', ') || '—'}</td>
            <td className={td}>
              {!r.own && (
                <button
                  type="button"
                  aria-pressed={watched(r.yayinevi)}
                  aria-label={watched(r.yayinevi) ? `${r.yayinevi} izlemeyi bırak` : `${r.yayinevi} izle`}
                  onClick={() => onWatch(r)}
                  className="grid h-11 w-11 place-items-center rounded-lg text-canvas-muted transition-transform duration-150 ease-out hover:bg-slate-100 active:scale-[0.95] sm:h-8 sm:w-8"
                >
                  {watched(r.yayinevi) ? <Eye aria-hidden className="h-4 w-4 text-canvas-violet" /> : <EyeOff aria-hidden className="h-4 w-4" />}
                </button>
              )}
            </td>
          </tr>
        ))}
      </tbody>
    </TableWrap>
  );
}

function PublisherBooks({ yayinevi, kategori, kaynak, onClose }: { yayinevi: string; kategori: string; kaynak: RakipKaynak; onClose: () => void }) {
  const [page, setPage] = useState(0);
  const basari = kaynak === 'basari';
  const q = useQuery({
    queryKey: ['pazar', 'competitors', kaynak, yayinevi, kategori, page],
    queryFn: () => pazarApi.competitors({ yayinevi, kategori, page, kaynak }),
    enabled: ENGINE_ENABLED,
    placeholderData: keepPreviousData,
  });
  return (
    <Panel>
      <div className="flex items-center justify-between gap-2">
        <h2 className="flex min-w-0 items-center gap-1 truncate text-[15px] font-extrabold">
          {yayinevi} — kayıtlar
          <SqlInfo k={kaynakOf(q.data)} alan="_hepsi" label={`${yayinevi}: fiyat ve sayfa`} />
        </h2>
        <button type="button" onClick={onClose} className={btnGhost} aria-label="Kapat">
          <X aria-hidden className="h-4 w-4" />
        </button>
      </div>
      {q.error && <Note tone="err">{errText(q.error, 'Kayıtlar açılamadı.')}</Note>}
      <ul className="mt-2 divide-y divide-slate-100">
        {(q.data?.items ?? []).map((b) => (
          <li key={b.crmId} className="flex flex-col gap-0.5 py-2 sm:flex-row sm:items-start sm:justify-between sm:gap-3">
            <div className="min-w-0">
              <div className="text-[12.5px] font-bold leading-snug">
                {b.ad}
                {b.emsalBagi && (
                  <span className="ml-1.5 inline-flex items-center gap-0.5 align-middle">
                    <Pill tone="violet"><Link2 aria-hidden className="mr-0.5 h-3 w-3" />CRM emsali</Pill>
                  </span>
                )}
              </div>
              <div className="text-[11.5px] text-canvas-muted">
                {[b.yazarlar, b.kategoriHam, b.cilt, b.dil, basari && b.basimYili ? `${b.basimYili} basımı` : null].filter(Boolean).join(' · ')}
              </div>
            </div>
            <div className="shrink-0 text-[11.5px] text-canvas-muted sm:text-right">
              <span className="font-mono text-[12.5px] font-bold tabular-nums text-canvas-ink">{fmtTl(b.fiyat)}</span> · {b.sayfa ? `${fmtInt(b.sayfa)} s.` : 's. —'} ·{' '}
              {basari ? <>Başarı deposu {fmtInt(b.stok)}</> : <>CRM {fmtDay(b.olusturma)}</>}
            </div>
          </li>
        ))}
      </ul>
      {q.data && (
        <Pager page={page} pageSize={q.data.pageSize} total={q.data.total} shown={q.data.items.length} loading={q.isLoading} fetching={q.isFetching} onPage={setPage} />
      )}
      <p className="mt-2 text-[11px] leading-snug text-canvas-muted">
        {basari
          ? 'Başarı Dağıtım kataloğunun son görüntüsü: fiyat liste fiyatıdır, stok dağıtımcı deposudur (okura satış değildir).'
          : "«Satış adedi» alanlarının CRM'deki anlamı bilinmediği için gösterilmez ve hiçbir hesapta kullanılmaz."}
      </p>
    </Panel>
  );
}
