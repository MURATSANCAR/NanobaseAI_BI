import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Plus } from 'lucide-react';
import { Loading, Note, Pill, btnGhost, btnPrimary, errText, field, label as labelCls } from '../admin/ui';
import { STATUS_TONE, cnApi, fmtDay, fmtStamp, type Meta } from './api';
import { AlertBadge, Block } from './parts';

const DURUM = [
  ['acik', 'Arşiv dışı'],
  ['taslak', 'Taslak'],
  ['onayda', 'Onay bekliyor'],
  ['onayli', 'Onaylı'],
  ['yayinda', 'Yayında'],
  ['arsiv', 'Arşiv'],
] as const;

/** Katalog listesi: durum, kitap sayısı, kritik fiyat/stok uyarısı rozeti; yeni katalog formu. */
export default function CatalogList({ meta }: { meta: Meta }) {
  const qc = useQueryClient();
  const nav = useNavigate();
  const [durum, setDurum] = useState('acik');
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ tur: 'bayi', baslik: '', donem: '', tema: '', fiyatKaynagi: meta.ayarlar.fiyatKaynagi });
  const list = useQuery({ queryKey: ['cn', 'catalogs', durum], queryFn: () => cnApi.catalogs(durum) });
  const create = useMutation({
    mutationFn: () => cnApi.createCatalog(form),
    onSuccess: (c) => {
      qc.invalidateQueries({ queryKey: ['cn'] });
      toast.success('Katalog açıldı.');
      nav(`/katalog-bulten/katalog/${encodeURIComponent(c.id)}`);
    },
    onError: (e) => toast.error(errText(e, 'Katalog açılamadı.') ?? ''),
  });

  return (
    <Block
      title="Kataloglar"
      help="Rozet, kitabın bugünkü fiyatı ya da stoku kataloğa eklendiği andan farklıysa, stok kritikse ya da kitap satıştan kalktıysa kırmızıdır. Uyarılar her sabah ve katalog açıldığında yeniden hesaplanır."
      action={
        <div className="flex flex-wrap gap-2">
          <select className={`${field} w-auto`} value={durum} aria-label="Durum" onChange={(e) => setDurum(e.target.value)}>
            {DURUM.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
          {meta.me.canCatalog && (
            <button type="button" className={btnPrimary} onClick={() => setOpen((o) => !o)} aria-expanded={open}>
              <Plus aria-hidden className="h-4 w-4" />
              Yeni katalog
            </button>
          )}
        </div>
      }
    >
      {open && (
        <form
          className="mb-3 grid gap-2 rounded-2xl border border-slate-100 bg-white/80 p-3 sm:grid-cols-2 lg:grid-cols-5"
          onSubmit={(e) => {
            e.preventDefault();
            create.mutate();
          }}
        >
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Tür</span>
            <select className={field} value={form.tur} onChange={(e) => setForm({ ...form, tur: e.target.value })}>
              {Object.entries(meta.turler).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
          </label>
          <label className="flex flex-col gap-1 lg:col-span-2">
            <span className={labelCls}>Katalog adı</span>
            <input className={field} required value={form.baslik} placeholder="Kış 2026 bayi kataloğu" onChange={(e) => setForm({ ...form, baslik: e.target.value })} />
          </label>
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Dönem</span>
            <input className={field} value={form.donem} placeholder="Kış 2026" onChange={(e) => setForm({ ...form, donem: e.target.value })} />
          </label>
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Tema</span>
            <input className={field} value={form.tema} placeholder="Yarıyıl tatili" onChange={(e) => setForm({ ...form, tema: e.target.value })} />
          </label>
          <label className="flex flex-col gap-1 sm:col-span-2 lg:col-span-3">
            <span className={labelCls}>Fiyat kaynağı</span>
            <select className={field} value={form.fiyatKaynagi} onChange={(e) => setForm({ ...form, fiyatKaynagi: e.target.value })}>
              {Object.entries(meta.fiyatKaynaklari).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
          </label>
          <div className="flex items-end justify-end gap-2 sm:col-span-2">
            <button type="button" className={btnGhost} onClick={() => setOpen(false)}>Vazgeç</button>
            <button type="submit" className={btnPrimary} disabled={create.isPending || !form.baslik.trim()}>Katalog aç</button>
          </div>
          <p className="text-[11px] leading-snug text-canvas-muted sm:col-span-2 lg:col-span-5">{meta.ayarlar.fiyatGerekce}</p>
        </form>
      )}
      {list.error && <Note tone="err">{errText(list.error, 'Liste açılamadı.')}</Note>}
      {list.isLoading && <Loading />}
      {list.data && list.data.items.length === 0 && <p className="py-6 text-[12.5px] text-canvas-muted">Bu süzgeçle katalog yok.</p>}
      <ul className="flex flex-col gap-2">
        {list.data?.items.map((c) => (
          <li key={c.id}>
            <Link to={`/katalog-bulten/katalog/${encodeURIComponent(c.id)}`}
              className="flex flex-col gap-1.5 rounded-2xl border border-slate-100 bg-white/80 p-3 transition-colors duration-150 hover:border-canvas-violet/40 sm:flex-row sm:items-center sm:gap-4">
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="break-words text-[14px] font-extrabold">{c.baslik}</span>
                  <Pill tone={STATUS_TONE[c.durum] ?? 'muted'}>{c.durumAdi}</Pill>
                </div>
                <div className="mt-0.5 text-[11.5px] text-canvas-muted">
                  {c.turAdi}{c.donem ? ` · ${c.donem}` : ''}{c.tema ? ` · ${c.tema}` : ''} · {c.fiyatKaynagiAdi}
                </div>
              </div>
              <div className="flex shrink-0 flex-wrap items-center gap-3 text-[12px]">
                <span className="font-mono tabular-nums">{c.kitap} kitap{c.oneCikan ? ` · ${c.oneCikan} öne çıkan` : ''}</span>
                <AlertBadge n={c.kritik} />
                <span className="text-[11px] text-canvas-muted">{c.stokTarihi ? `stok ${fmtDay(c.stokTarihi)}` : fmtStamp(c.guncelleme)}</span>
              </div>
            </Link>
          </li>
        ))}
      </ul>
    </Block>
  );
}
