import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Plus } from 'lucide-react';
import { Loading, Note, Pill, btnGhost, btnPrimary, errText, field, label as labelCls } from '../admin/ui';
import { STATUS_TONE, cnApi, fmtDay, fmtInt, fmtPct, type Meta } from './api';
import { Block } from './parts';
import SqlInfo from '../components/SqlInfo';

const DURUM = [
  ['acik', 'Arşiv dışı'],
  ['taslak', 'Taslak'],
  ['onayda', 'Onay bekliyor'],
  ['onayli', 'Onaylı'],
  ['gonderildi', 'Gönderildi'],
  ['arsiv', 'Arşiv'],
] as const;

/** Bülten listesi: planlanan tarih, segment büyüklüğü (yalnız sayı), son sonuç. */
export default function NewsletterList({ meta }: { meta: Meta }) {
  const qc = useQueryClient();
  const nav = useNavigate();
  const [durum, setDurum] = useState('acik');
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ baslik: '', ozelGun: '', planlanan: '' });
  const list = useQuery({ queryKey: ['cn', 'newsletters', durum], queryFn: () => cnApi.newsletters(durum) });
  const create = useMutation({
    mutationFn: () => cnApi.createNewsletter({ baslik: form.baslik, ozelGun: form.ozelGun || null, planlanan: form.planlanan || null }),
    onSuccess: (n) => {
      qc.invalidateQueries({ queryKey: ['cn'] });
      toast.success('Bülten açıldı.');
      nav(`/katalog-bulten/bulten/${encodeURIComponent(n.id)}`);
    },
    onError: (e) => toast.error(errText(e, 'Bülten açılamadı.') ?? ''),
  });
  const days = meta.ozelGunler;

  return (
    <Block
      title="E-bültenler"
      info={<SqlInfo k={list.data?.kaynaklar} alan="items[]" label="Kitap, izinli okur ve sonuç oranları" />}
      help="Portal bülteni göndermez: onaylanan bültenin dosyası indirilir ve şirketin izin yönetimi olan e-posta aracından gönderilir. Hedef kitle (segment) sayısı yalnız izin vermiş kişileri sayar; kişi listesi portalda hiç görünmez."
      action={
        <div className="flex flex-wrap gap-2">
          <select className={`${field} w-auto`} value={durum} aria-label="Durum" onChange={(e) => setDurum(e.target.value)}>
            {DURUM.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
          {meta.me.canNewsletter && (
            <button type="button" className={btnPrimary} onClick={() => setOpen((o) => !o)} aria-expanded={open}>
              <Plus aria-hidden className="h-4 w-4" />
              Yeni bülten
            </button>
          )}
        </div>
      }
    >
      {open && (
        <form className="mb-3 grid gap-2 rounded-2xl border border-slate-100 bg-white/80 p-3 sm:grid-cols-2 lg:grid-cols-4"
          onSubmit={(e) => { e.preventDefault(); create.mutate(); }}>
          <label className="flex flex-col gap-1 sm:col-span-2">
            <span className={labelCls}>Bülten adı</span>
            <input className={field} required value={form.baslik} placeholder="Öğretmenler Günü bülteni" onChange={(e) => setForm({ ...form, baslik: e.target.value })} />
          </label>
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Özel gün</span>
            <select className={field} value={form.ozelGun} onChange={(e) => setForm({ ...form, ozelGun: e.target.value })}>
              <option value="">Yok</option>
              {days.map((d) => <option key={d.key} value={d.key}>{d.ad}{d.baslangic ? ` · ${fmtDay(d.baslangic)}` : ''}</option>)}
            </select>
          </label>
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Planlanan gönderim</span>
            <input type="date" className={field} value={form.planlanan} onChange={(e) => setForm({ ...form, planlanan: e.target.value })} />
          </label>
          <div className="flex justify-end gap-2 sm:col-span-2 lg:col-span-4">
            <button type="button" className={btnGhost} onClick={() => setOpen(false)}>Vazgeç</button>
            <button type="submit" className={btnPrimary} disabled={create.isPending || !form.baslik.trim()}>Bülten aç</button>
          </div>
        </form>
      )}
      {list.error && <Note tone="err">{errText(list.error, 'Liste açılamadı.')}</Note>}
      {list.isLoading && <Loading />}
      {list.data && list.data.items.length === 0 && <p className="py-6 text-[12.5px] text-canvas-muted">Bu süzgeçle bülten yok. Süzgeci değiştirin ya da yukarıdaki formla yeni bülten açın.</p>}
      <ul className="flex flex-col gap-2">
        {list.data?.items.map((n) => (
          <li key={n.id}>
            <Link to={`/katalog-bulten/bulten/${encodeURIComponent(n.id)}`}
              className="flex flex-col gap-1.5 rounded-2xl border border-slate-100 bg-white/80 p-3 transition-colors duration-150 hover:border-canvas-violet/40 sm:flex-row sm:items-center sm:gap-4">
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="break-words text-[14px] font-extrabold">{n.baslik}</span>
                  <Pill tone={STATUS_TONE[n.durum] ?? 'muted'}>{n.durumAdi}</Pill>
                </div>
                <div className="mt-0.5 break-words text-[11.5px] text-canvas-muted">
                  {n.konu ? `«${n.konu}»` : 'Konu satırı seçilmedi'}{n.planlanan ? ` · plan ${fmtDay(n.planlanan)}` : ''}
                  {n.gonderimTarihi ? ` · gönderim ${fmtDay(n.gonderimTarihi)}` : ''}
                </div>
              </div>
              <div className="flex shrink-0 flex-wrap items-center gap-3 font-mono text-[12px] tabular-nums">
                <span>{n.kitap} kitap</span>
                <span>{n.segmentBuyuklugu === null ? 'segment sayılmadı' : `${fmtInt(n.segmentBuyuklugu)} izinli okur`}</span>
                {n.sonuc && <span>açılma {fmtPct(n.sonuc.acilmaOrani)} · tıklama {fmtPct(n.sonuc.tiklamaOrani)}</span>}
              </div>
            </Link>
          </li>
        ))}
      </ul>
    </Block>
  );
}
