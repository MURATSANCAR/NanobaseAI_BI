import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Plus, Trash2 } from 'lucide-react';
import { ENGINE_ENABLED } from '../../engine';
import { Loading, Note, Pill, btnGhost, btnPrimary, errText, field, label as labelCls } from '../../admin/ui';
import { fmtDay, fmtInt, fmtMoney, parseNum } from '../api';
import { Block } from '../parts';
import SqlInfo from '../../components/SqlInfo';
import { launchApi, type Launch, type LaunchEvent, type LaunchMeta } from './api';

/** Etkinlikler: CRM'de kitaba bağlı etkinlikler (okuma) + portalda girilen sonuç ve elle eklenen etkinlik. CRM'e
 *  yazılmaz; portalda girilenler «CRM'e işlenecek» listesinde durur. Katılımcının kişisel verisi alınmaz, yalnız sayı. */

type Draft = { katilimci: string; satilan: string; gelir: string; gider: string; not: string };
const empty: Draft = { katilimci: '', satilan: '', gelir: '', gider: '', not: '' };
const num = (s: string) => (s.trim() ? parseNum(s) : null);

function ResultForm({ e, launch, money, onDone }: { e: LaunchEvent; launch: Launch; money: boolean; onDone: () => void }) {
  const [d, setD] = useState<Draft>({
    katilimci: e.katilimci != null ? String(e.katilimci) : '', satilan: e.satilan != null ? String(e.satilan) : '',
    gelir: e.gelir != null ? String(e.gelir) : '', gider: e.gider != null ? String(e.gider) : '', not: e.not ?? '',
  });
  const save = useMutation({
    mutationFn: () => launchApi.saveEvent(launch.id, {
      crmId: e.crmId ?? undefined, katilimci: num(d.katilimci), satilan: num(d.satilan),
      ...(money ? { gelir: num(d.gelir), gider: num(d.gider) } : {}), not: d.not || null,
      ...(e.kaynak === 'elle' ? { ad: e.ad, tur: e.tur, tarih: e.tarih, yer: e.yer } : {}),
    }, e.kaynak === 'elle' ? e.id ?? undefined : undefined),
    onSuccess: () => { toast.success('Etkinlik sonucu kaydedildi.'); onDone(); },
    onError: (x) => toast.error(errText(x, 'Kaydedilemedi.') ?? ''),
  });
  const f = (k: keyof Draft, lab: string) => (
    <label className="flex flex-col gap-1">
      <span className={labelCls}>{lab}</span>
      <input className={field} inputMode="decimal" value={d[k]} onChange={(ev) => setD({ ...d, [k]: ev.target.value })} />
    </label>
  );
  return (
    <div className="mt-2 grid grid-cols-2 gap-2 sm:grid-cols-5 sm:items-end">
      {f('katilimci', 'Katılımcı')}
      {f('satilan', 'Satılan kitap')}
      {money && f('gelir', 'Gelir (₺)')}
      {money && f('gider', 'Gider (₺)')}
      <button type="button" className={btnPrimary} disabled={save.isPending} onClick={() => save.mutate()}>Kaydet</button>
    </div>
  );
}

export default function EventsTab({ launch, meta }: { launch: Launch; meta: LaunchMeta }) {
  const qc = useQueryClient();
  const money = meta.me.canSeeBudget;
  const q = useQuery({ queryKey: ['launch', 'events', launch.id], queryFn: () => launchApi.events(launch.id), enabled: ENGINE_ENABLED });
  const todo = useQuery({ queryKey: ['launch', 'crm-todo', launch.id], queryFn: () => launchApi.crmTodo(launch.id), enabled: ENGINE_ENABLED });
  const [open, setOpen] = useState<string | null>(null);
  const [add, setAdd] = useState({ ad: '', tur: 'İmza günü', tarih: launch.yayinGunu, yer: '', ...empty });
  const refetch = () => { qc.invalidateQueries({ queryKey: ['launch', 'events', launch.id] }); qc.invalidateQueries({ queryKey: ['launch', 'crm-todo', launch.id] }); };
  const create = useMutation({
    mutationFn: () => launchApi.saveEvent(launch.id, { ad: add.ad, tur: add.tur, tarih: add.tarih, yer: add.yer, katilimci: num(add.katilimci), satilan: num(add.satilan) }),
    onSuccess: () => { toast.success('Etkinlik eklendi.'); setAdd({ ...add, ad: '', yer: '', katilimci: '', satilan: '' }); refetch(); },
    onError: (e) => toast.error(errText(e, 'Etkinlik eklenemedi.') ?? ''),
  });
  const remove = useMutation({
    mutationFn: (id: string) => launchApi.deleteEvent(launch.id, id),
    onSuccess: () => { toast.success('Kayıt silindi.'); refetch(); },
    onError: (e) => toast.error(errText(e, 'Silinemedi.') ?? ''),
  });
  const t = q.data?.toplam;
  return (
    <div className="flex flex-col gap-3">
      <Block title="Yazar etkinlikleri" info={<SqlInfo k={q.data?.kaynaklar} alan="toplam" label="Etkinlik toplamları" />} help="CRM'de bu kitaba bağlı etkinlikler; sonucu (katılımcı, satılan kitap) burada girilebilir. Toplamlar tamamlanan etkinliklerden.">
        {q.error && <Note tone="err">{errText(q.error, 'Etkinlikler açılamadı.')}</Note>}
        {q.data?.uyarilar.map((w) => <Note key={w} tone="warn">{w}</Note>)}
        {q.isLoading && <Loading />}
        {t && (
          <p className="mb-2 text-[12px] font-semibold text-canvas-muted">
            {fmtInt(t.tamamlanan)} tamamlanan / {fmtInt(t.etkinlik)} etkinlik · {fmtInt(t.katilimci)} katılımcı · {fmtInt(t.satilan)} kitap satıldı
            {money && t.gelir != null ? ` · gelir ${fmtMoney(t.gelir)}, gider ${fmtMoney(t.gider)}` : ''}
          </p>
        )}
        {q.data && q.data.items.length === 0 && <p className="text-[12.5px] text-canvas-muted">Bu kitaba bağlı etkinlik yok.</p>}
        <ul className="flex flex-col gap-1.5">
          {q.data?.items.map((e) => {
            const key = e.crmId ?? e.id ?? '';
            return (
              <li key={key} className="rounded-2xl border border-slate-100 bg-white/80 p-2.5">
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div className="min-w-0">
                    <div className="break-words text-[13px] font-semibold leading-snug">{e.ad ?? 'Etkinlik'}</div>
                    <div className="mt-0.5 text-[11px] text-canvas-muted">{fmtDay(e.tarih)} · {e.tur ?? '—'}{e.yer ? ` · ${e.yer}` : ''}</div>
                  </div>
                  <div className="flex flex-wrap items-center gap-1.5">
                    <Pill tone={e.kaynak === 'elle' ? 'violet' : 'muted'}>{e.kaynak === 'elle' ? 'Portalda girildi' : e.durumAdi ?? 'CRM'}</Pill>
                    {e.portal && <Pill tone="warn">Sonuç portalda</Pill>}
                  </div>
                </div>
                <div className="mt-1 text-[12px] tabular-nums">
                  {fmtInt(e.katilimci)} katılımcı · {fmtInt(e.satilan)} kitap{money && e.gelir != null ? ` · gelir ${fmtMoney(e.gelir)}` : ''}{money && e.gider != null ? ` · gider ${fmtMoney(e.gider)}` : ''}
                </div>
                {meta.me.canWrite && (
                  <div className="mt-1 flex flex-wrap gap-2">
                    <button type="button" className={btnGhost} onClick={() => setOpen(open === key ? null : key)}>{open === key ? 'Kapat' : 'Sonucu gir'}</button>
                    {e.kaynak === 'elle' && e.id && (
                      <button type="button" className={btnGhost} aria-label="Kaydı sil" onClick={() => remove.mutate(e.id as string)}><Trash2 aria-hidden className="h-4 w-4" /></button>
                    )}
                  </div>
                )}
                {open === key && <ResultForm e={e} launch={launch} money={money} onDone={() => { setOpen(null); refetch(); }} />}
              </li>
            );
          })}
        </ul>
        {meta.me.canWrite && (
          <form className="mt-3 grid grid-cols-1 gap-2 rounded-2xl bg-slate-50 p-2.5 sm:grid-cols-[1fr_150px_150px_1fr_110px_110px_auto] sm:items-end"
            onSubmit={(e) => { e.preventDefault(); if (add.ad.trim()) create.mutate(); }}>
            <label className="flex min-w-0 flex-col gap-1"><span className={labelCls}>CRM'de olmayan etkinlik</span>
              <input className={field} value={add.ad} placeholder="Etkinlik adı" onChange={(e) => setAdd({ ...add, ad: e.target.value })} /></label>
            <label className="flex flex-col gap-1"><span className={labelCls}>Tür</span>
              <input className={field} value={add.tur} onChange={(e) => setAdd({ ...add, tur: e.target.value })} /></label>
            <label className="flex flex-col gap-1"><span className={labelCls}>Tarih</span>
              <input type="date" className={field} value={add.tarih} onChange={(e) => setAdd({ ...add, tarih: e.target.value })} /></label>
            <label className="flex min-w-0 flex-col gap-1"><span className={labelCls}>Yer</span>
              <input className={field} value={add.yer} onChange={(e) => setAdd({ ...add, yer: e.target.value })} /></label>
            <label className="flex flex-col gap-1"><span className={labelCls}>Katılımcı</span>
              <input className={field} inputMode="numeric" value={add.katilimci} onChange={(e) => setAdd({ ...add, katilimci: e.target.value })} /></label>
            <label className="flex flex-col gap-1"><span className={labelCls}>Satılan</span>
              <input className={field} inputMode="numeric" value={add.satilan} onChange={(e) => setAdd({ ...add, satilan: e.target.value })} /></label>
            <button type="submit" className={btnGhost} disabled={!add.ad.trim() || create.isPending}><Plus aria-hidden className="h-4 w-4" />Ekle</button>
          </form>
        )}
      </Block>

      <Block title="CRM'e işlenecek" help="Portalda girilen etkinlik sonuçları ve elle kayıtlar. Portal CRM'e yazmaz; bu kayıtları CRM kullanıcıları elle işler.">
        {todo.error && <Note tone="err">{errText(todo.error, 'Liste açılamadı.')}</Note>}
        {todo.data && todo.data.items.length === 0 && <p className="text-[12.5px] text-canvas-muted">CRM'e işlenecek kayıt yok.</p>}
        <ul className="flex flex-col gap-1.5">
          {todo.data?.items.map((i, n) => (
            <li key={n} className="rounded-xl border border-slate-100 bg-white/80 p-2.5 text-[12px]">
              <div className="font-bold">{i.nereye}</div>
              <div className="break-words">{i.ne ?? '—'} · {fmtDay(i.tarih)}</div>
              <div className="mt-0.5 break-words text-canvas-muted">
                {Object.entries(i.alanlar).filter(([, v]) => v != null && v !== '').map(([k, v]) => `${k}: ${v}`).join(' · ')}
              </div>
            </li>
          ))}
        </ul>
      </Block>
    </div>
  );
}
