import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Download, Search } from 'lucide-react';
import { ENGINE_ENABLED } from '../../engine';
import { Loading, Note, errText, field, label } from '../../admin/ui';
import { Pager, Panel, useDebounced } from '../../editorial/kit';
import { Img } from '../../editorial/studio/shared';
import { copyText } from '../../editorial/studio/marketing/parts';
import { creativeApi, fmtDay } from './api';
import { ApprovalLine, DraftBadge, smallBtn } from './parts';
import { useCreativeMeta } from './useMeta';
import SqlInfo from '../../components/SqlInfo';
import { EmptyHint } from '../../components/Explain';

/** Arşiv: onaylı (ya da süzgeçle bekleyen/reddedilen) güncel varlıklar; kitap, kampanya/etiket, kanal, biçim, tür ve
 *  tarih süzgeci. Tavansız, sayfalı. «Bu kitabın bütün görselleri» tek aramada. */

export default function AssetLibrary({ params, update }: { params: URLSearchParams; update: (n: Record<string, string | null>) => void }) {
  const meta = useCreativeMeta().data;
  const [q, setQ] = useState(params.get('q') ?? '');
  const dq = useDebounced(q, 300);
  const f = {
    durum: params.get('adurum') ?? 'onayli',
    tur: params.get('tur') ?? '',
    kanal: params.get('kanal') ?? '',
    format: params.get('bicim') ?? '',
    etiket: params.get('etiket') ?? '',
    baslangic: params.get('bas') ?? '',
    bitis: params.get('bit') ?? '',
    page: Number(params.get('sayfa') ?? 0) || 0,
  };
  const list = useQuery({
    queryKey: ['creative', 'archive', f, dq],
    queryFn: () => creativeApi.archive({ ...f, q: dq }),
    enabled: ENGINE_ENABLED,
  });
  const items = list.data?.items ?? [];
  const sel = (k: string) => (e: { target: { value: string } }) => update({ [k]: e.target.value || null, sayfa: null });

  return (
    <Panel>
      <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4 xl:grid-cols-8">
        <label className="relative block sm:col-span-2">
          <span className="sr-only">Arşivde ara</span>
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-canvas-muted" aria-hidden />
          <input className={`${field} pl-9`} value={q} onChange={(e) => { setQ(e.target.value); update({ q: e.target.value || null, sayfa: null }); }}
            placeholder="Kitap, stok kodu, kampanya, metin" />
        </label>
        <label className="flex flex-col gap-0.5"><span className={label}>Durum</span>
          <select className={field} value={f.durum} onChange={sel('adurum')}>
            <option value="onayli">Onaylı</option><option value="bekleyen">Onay bekleyen</option>
            <option value="reddedilen">Reddedilen</option><option value="hepsi">Hepsi</option>
          </select></label>
        <label className="flex flex-col gap-0.5"><span className={label}>Tür</span>
          <select className={field} value={f.tur} onChange={sel('tur')}>
            <option value="">Görsel ve metin</option><option value="gorsel">Görsel</option><option value="metin">Metin</option>
          </select></label>
        <label className="flex flex-col gap-0.5"><span className={label}>Kanal</span>
          <select className={field} value={f.kanal} onChange={sel('kanal')}>
            <option value="">Hepsi</option>
            {meta?.kanallar.map((k) => <option key={k.key} value={k.key}>{k.label}</option>)}
          </select></label>
        <label className="flex flex-col gap-0.5"><span className={label}>Biçim</span>
          <select className={field} value={f.format} onChange={sel('bicim')}>
            <option value="">Hepsi</option>
            {meta?.formatlar.map((k) => <option key={k.key} value={k.key}>{k.label}</option>)}
          </select></label>
        <label className="flex flex-col gap-0.5"><span className={label}>Kampanya / etiket</span>
          <input className={field} defaultValue={f.etiket} onBlur={(e) => update({ etiket: e.target.value.trim() || null, sayfa: null })} placeholder="Kampanya adının tamamı" /></label>
        <div className="grid grid-cols-2 gap-1.5">
          <label className="flex min-w-0 flex-col gap-0.5"><span className={label}>Başlangıç</span><input type="date" className={field} value={f.baslangic} onChange={sel('bas')} /></label>
          <label className="flex min-w-0 flex-col gap-0.5"><span className={label}>Bitiş</span><input type="date" className={field} value={f.bitis} onChange={sel('bit')} /></label>
        </div>
      </div>

      {list.error && <div className="mt-2"><Note tone="err">{errText(list.error, 'Arşiv okunamadı.')}</Note></div>}
      {list.isLoading && <Loading />}
      {!list.isLoading && items.length === 0 && <div className="mt-3"><EmptyHint title="Bu süzgeçte dosya yok" why="Arşivde onaylanmış görsel ve metinler durur. Aramayı temizleyin ya da kanal, biçim, tarih süzgeçlerini gevşetin." /></div>}

      <ul className="mt-3 grid min-w-0 grid-cols-1 gap-2.5 sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-4">
        {items.map((a) => (
          <li key={a.id} className="flex min-w-0 flex-col gap-1.5 rounded-2xl border border-slate-200 bg-white/85 p-2.5">
            {a.tur === 'gorsel' ? (
              <a href={creativeApi.fileUrl(a.id)} target="_blank" rel="noreferrer" className="block overflow-hidden rounded-lg bg-slate-100">
                <Img src={creativeApi.fileUrl(a.id, 420)} alt={a.dosyaAdi} fallback="görsel" className="mx-auto max-h-52 w-auto object-contain" />
              </a>
            ) : (
              <p className="line-clamp-6 whitespace-pre-line break-words rounded-lg bg-slate-50 p-2 text-[12.5px] leading-snug">{a.metin}</p>
            )}
            <Link to={`/pazarlama/icerik/${encodeURIComponent(a.requestId)}`} className="line-clamp-1 text-[13px] font-extrabold hover:underline">{a.kitapAdi}</Link>
            <span className="truncate text-[11.5px] text-canvas-muted">
              {[a.tur === 'gorsel' ? a.formatAdi : `${a.metinTuruAdi} · ${a.formatAdi}`, `varyant ${a.varyant}`, `v${a.surum}`, a.kampanya].filter(Boolean).join(' · ')}
            </span>
            <span className="text-[11px] text-canvas-muted">{a.mesajOnay ? `Onay ${fmtDay(a.mesajOnay.at)}` : `Üretim ${fmtDay(a.olusturma)}`}</span>
            <ApprovalLine a={a} />
            {a.taslakLisans && <DraftBadge />}
            <div className="flex flex-wrap gap-1.5">
              {a.onayli && <a className={smallBtn()} href={creativeApi.downloadUrl(a.id)} title={a.dosyaAdi}><Download className="h-4 w-4" aria-hidden />İndir</a>}
              {a.tur === 'metin' && (
                <button type="button" className={smallBtn()} onClick={() => void copyText(a.metin ?? '')}>Kopyala</button>
              )}
            </div>
          </li>
        ))}
      </ul>
      {list.data && list.data.total > 0 && (
        <div className="mt-2 flex items-center gap-1 text-[11.5px] text-canvas-muted">Arşiv sayısı<SqlInfo k={list.data.kaynaklar} alan="total" label="Arşiv" /></div>
      )}
      {list.data && list.data.total > 0 && (
        <Pager page={f.page} pageSize={list.data.pageSize} total={list.data.total} shown={items.length} loading={list.isLoading}
          fetching={list.isFetching} onPage={(p) => update({ sayfa: p ? String(p) : null })} />
      )}
    </Panel>
  );
}
