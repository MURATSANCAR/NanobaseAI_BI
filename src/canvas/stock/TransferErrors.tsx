import { useSearchParams } from 'react-router-dom';
import SqlInfo, { InfoLabel } from '../components/SqlInfo';
import type { Kaynaklar } from '../components/sqlInfo';
import { useQuery } from '@tanstack/react-query';
import { ENGINE_ENABLED } from '../engine';
import { Note, Pill, TableWrap, errText, label as labelCls, td, th } from '../admin/ui';
import { Pager, Panel } from '../editorial/kit';
import { fmtDay } from '../budget/api';
import { n0, stockApi, type Transfer } from './api';
import { Chips, Empty, ExportLink, Loading, SourcesButton, StockFrame, num } from './parts';
import { RULES } from './rules';

/** Logo'ya aktarılamayan hareketler (/stok/aktarim): CRM'de başlayıp Logo'ya fiş olarak geçemeyen malzeme hareketleri,
 *  yaşı ve Logo mesajı. Zeki AI mesajı kapalı kümeye sınıflar (emin değilse «Sınıflanmadı»). Düzeltme Logo/CRM'de insanın işi. */

type Tur = 'hata' | 'bekliyor' | '';

export default function TransferErrors() {
  const [params, setParams] = useSearchParams();
  const tur = (params.get('tur') ?? 'hata') as Tur;
  const sinif = params.get('sinif') ?? '';
  const sayfa = Number(params.get('sayfa') ?? 0) || 0;
  const set = (k: string, v: string | null) => {
    const p = new URLSearchParams(params);
    if (v !== null) p.set(k, v);
    else p.delete(k);
    if (k !== 'sayfa') p.delete('sayfa');
    setParams(p, { replace: true });
  };
  const meta = useQuery({ queryKey: ['stock', 'meta'], queryFn: stockApi.meta, enabled: ENGINE_ENABLED, staleTime: 60_000 });
  const q = useQuery({ queryKey: ['stock', 'transfers', tur, sinif, sayfa], queryFn: () => stockApi.transfers({ tur, sinif, sayfa }), enabled: ENGINE_ENABLED, placeholderData: (p) => p });
  const d = q.data;

  return (
    <StockFrame
      crumb="Aktarım hataları"
      title="Logo’ya aktarılamayan hareketler"
      lead="Depoda CRM’e girilip Logo’ya fiş olarak geçmemiş malzeme hareketleri. Gün içinde düzeltilmezse fatura ve irsaliye kayar; en eski üstte."
      source="CRM canlı"
      aside={
        <>
          <SourcesButton rules={RULES} />
          <ExportLink show={!!meta.data?.me.canExport} href={stockApi.exportUrl('aktarim', { tur })} />
        </>
      }
    >
      <Panel>
        <div className="mb-3 flex flex-col gap-2">
          <Chips<Tur>
            label="Tür"
            items={[
              { key: 'hata', label: 'Hata mesajlı', count: d?.hata ?? null, info: <SqlInfo k={d?.kaynaklar} alan="hata" label="Hata mesajlı hareket sayısı" /> },
              { key: 'bekliyor', label: 'Mesajsız bekleyen', count: d?.bekliyor ?? null, info: <SqlInfo k={d?.kaynaklar} alan="bekliyor" label="Mesajsız bekleyen hareket sayısı" /> },
              { key: '', label: 'Hepsi' },
            ]}
            value={tur}
            onChange={(k) => set('tur', k)}
          />
          {tur !== 'bekliyor' && !!d?.siniflar.length && (
            <Chips<string>
              label="Neden"
              items={[{ key: '', label: 'Bütün nedenler', info: <SqlInfo k={d.kaynaklar} alan="siniflar" label="Neden sayaçları (Zeki AI sınıfı)" /> }, ...d.siniflar.map((s) => ({ key: s.key, label: s.key, count: s.adet }))]}
              value={sinif}
              onChange={(k) => set('sinif', k || null)}
            />
          )}
        </div>
        {q.error && <Note tone="err">{errText(q.error, 'Liste okunamadı.')}</Note>}
        {q.isLoading && <Loading what="Aktarım kayıtları" />}
        {d && !d.items.length && <Empty>Kayıt yok.</Empty>}
        {!!d?.items.length && <Rows items={d.items} k={d.kaynaklar} />}
        {d && <Pager page={d.page} pageSize={d.pageSize} total={d.total} shown={d.items.length} loading={q.isLoading} fetching={q.isFetching} onPage={(p) => set('sayfa', String(p))} />}
      </Panel>
    </StockFrame>
  );
}

function Rows({ items, k }: { items: Transfer[]; k?: Kaynaklar }) {
  return (
    <>
      <div className="mb-2 flex flex-wrap gap-x-3 gap-y-1 text-[11px] font-semibold text-canvas-muted md:hidden" aria-label="Rakamların sorgu bilgisi">
        <InfoLabel k={k} alan="items[].yasGun">Yaş</InfoLabel>
        <InfoLabel k={k} alan="items[].satir">Satır ve miktar</InfoLabel>
      </div>
      <ul className="flex flex-col gap-2 md:hidden">
        {items.map((t) => (
          <li key={t.id} className="rounded-2xl border border-slate-100 bg-white/80 p-3 text-[12px]">
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0">
                <div className="break-words font-bold">{t.fisNo ?? '—'} · {t.islemTuruEtiket}</div>
                <div className="text-canvas-muted">{t.depo ?? '—'} · {t.fisTarihi ? fmtDay(t.fisTarihi) : '—'}</div>
              </div>
              <span className="shrink-0 font-mono tabular-nums">{t.yasGun ?? '—'} gün</span>
            </div>
            {t.hata && <div className="mt-1"><Pill tone={t.sinif ? 'warn' : 'muted'}>{t.sinif ?? 'Sınıflanmadı'}</Pill></div>}
            {t.mesaj && <p className="mt-1 break-words text-canvas-muted">{t.mesaj}</p>}
            <dl className="mt-1 grid grid-cols-2 gap-2">
              <div><dt className={labelCls}>Satır</dt><dd className="font-mono">{n0(t.satir)}</dd></div>
              <div><dt className={labelCls}>Miktar</dt><dd className="font-mono">{n0(t.miktar)}</dd></div>
            </dl>
          </li>
        ))}
      </ul>
      <div className="hidden md:block">
        <TableWrap>
          <thead>
            <tr>
              <th className={th}>Fiş</th>
              <th className={th}>İşlem</th>
              <th className={th}>Depo</th>
              <th className={`${th} text-right`}><InfoLabel k={k} alan="items[].yasGun">Yaş</InfoLabel></th>
              <th className={`${th} text-right`}><InfoLabel k={k} alan="items[].miktar">Miktar</InfoLabel></th>
              <th className={th}>Neden (Zeki AI)</th>
              <th className={th}>Logo mesajı</th>
            </tr>
          </thead>
          <tbody>
            {items.map((t) => (
              <tr key={t.id} className="border-t border-slate-100">
                <td className={td}>
                  <div className="font-bold">{t.fisNo ?? '—'}</div>
                  <div className="text-[11px] text-canvas-muted">{t.fisTarihi ? fmtDay(t.fisTarihi) : '—'} · {t.durumEtiket}</div>
                </td>
                <td className={td}>{t.islemTuruEtiket}{t.islemTipiEtiket ? <div className="text-[11px] text-canvas-muted">{t.islemTipiEtiket}</div> : null}</td>
                <td className={td}>{t.depo ?? '—'}</td>
                <td className={`${td} ${num}`}>{t.yasGun ?? '—'} gün</td>
                <td className={`${td} ${num}`}>{n0(t.miktar)}<div className="text-[11px] text-canvas-muted">{n0(t.satir)} satır</div></td>
                <td className={td}>{t.hata ? <Pill tone={t.sinif ? 'warn' : 'muted'}>{t.sinif ?? 'Sınıflanmadı'}</Pill> : 'Bekliyor'}</td>
                <td className={`${td} max-w-[420px] break-words text-[12px] text-canvas-muted`}>{t.mesaj ?? '—'}</td>
              </tr>
            ))}
          </tbody>
        </TableWrap>
      </div>
    </>
  );
}
