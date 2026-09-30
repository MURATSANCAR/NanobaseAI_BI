import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { AlertTriangle, CalendarCheck2, Download, Info } from 'lucide-react';
import { ENGINE_ENABLED } from '../../engine';
import { Loading, Note, Pill, btnPrimary, errText, field, label as labelCls } from '../../admin/ui';
import { EmptyHint } from '../../components/Explain';
import { FilePick } from '../../components/FileDrop';
import { useDebounced } from '../../editorial/kit';
import { AskSheet, Block, HrFrame } from '../parts';
import { Stat } from '../portal/parts';
import { localIso } from '../portal/portalApi';
import { STATUS_TONE, gun, leaveApi, shortDay, span, type LeaveRequest } from './leaveApi';

/** İzinlerim (/ik/izin): bakiye, izin isteme (gün sayısı göndermeden hesaplanır), geçmiş, geri alma ve belge. */
export default function MyLeave() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ['hr', 'leave', 'me'], queryFn: leaveApi.me, enabled: ENGINE_ENABLED });
  const d = q.data;
  const s = d?.summary;
  const [cancel, setCancel] = useState<LeaveRequest | null>(null);
  const refresh = () => void qc.invalidateQueries({ queryKey: ['hr', 'leave'] });
  const del = useMutation({
    mutationFn: (id: string) => leaveApi.cancel(id),
    onSuccess: (r) => { setCancel(null); toast.success(r.status === 'iptal' ? 'İzin iptal edildi; günler bakiyenize iade edildi.' : 'Talep geri alındı.'); refresh(); },
    onError: (e) => toast.error(errText(e, 'Geri alınamadı.')),
    onSettled: () => setCancel(null),
  });
  const today = localIso(new Date());
  return (
    <HrFrame crumb="İzinlerim" title="İzinlerim" back={{ to: '/ik', label: 'İK ana sayfası' }}
      lead="Yıllık izin bakiyeniz, izin talebi ve geçmişiniz. Talep yöneticinize gider; kararı e-postayla ve burada görürsünüz."
      aside={d?.rights.admin ? <Link to="/ik/yonetim?sekme=izinler" className="text-[12px] font-bold text-canvas-violet hover:underline">İK yönetimi › İzinler</Link> : undefined}>
      {q.error && <Note tone="err">{errText(q.error, 'İzin bilgisi okunamadı.')}</Note>}
      {q.isLoading && <Loading />}
      {d && !d.linked && (
        <EmptyHint title="Özlük kaydınız bağlı değil" why="İzin isteyebilmeniz için İK'nın portal hesabınızı özlük kaydınıza bağlaması gerekir." />
      )}
      {d?.linked && s && (
        <>
          <section aria-label="Bakiye" className="grid grid-cols-2 gap-2 sm:grid-cols-4 lg:gap-3">
            <Stat label="Kullanılabilir" value={gun(s.available)} help={s.pending ? `${gun(s.pending)} onay bekliyor` : 'Onay bekleyen yok'} />
            <Stat label="Bakiye" value={gun(s.balance)} help={s.hasOpening ? 'Açılış + hakediş − kullanım' : 'Açılış bakiyesi henüz girilmedi'} />
            <Stat label="Bu yıl kullanılan" value={gun(s.usedYear)} help={s.accruedYear ? `Bu yıl hakedilen ${gun(s.accruedYear)}` : undefined} />
            <Stat label="Sıradaki hakediş" value={s.nextAccrual ? gun(s.nextAccrual.days) : '—'}
              help={s.nextAccrual ? `${shortDay(s.nextAccrual.date)} · ${s.nextAccrual.years}. yıl` : 'İşe giriş tarihi girilmemiş'} />
          </section>
          <div className="grid grid-cols-1 gap-3 lg:grid-cols-[minmax(0,460px)_1fr] lg:gap-4">
            <NewRequest onDone={refresh} />
            <Block title="Taleplerim" help={d.manager ? `Onaylayan yöneticiniz: ${d.manager}` : 'Yöneticiniz tanımlı değil; talepleriniz doğrudan İK’ya gider.'}>
              {!d.requests?.length && <EmptyHint icon={<CalendarCheck2 className="h-[18px] w-[18px]" />} title="Henüz izin talebiniz yok" />}
              <ul className="flex flex-col gap-2">
                {(d.requests ?? []).map((r) => (
                  <li key={r.id} className="rounded-xl bg-white/85 px-3 py-2">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <span className="text-[13px] font-bold">{r.typeLabel} · {span(r.start, r.end)}</span>
                      <Pill tone={STATUS_TONE[r.status] ?? 'muted'}>{r.statusLabel}</Pill>
                    </div>
                    <div className="text-[11.5px] text-canvas-muted">{gun(r.days)}{r.half ? ' · yarım gün' : ''}{r.deputy ? ` · vekil ${r.deputy}` : ''}</div>
                    {r.rejectReason && <div className="mt-1 rounded-lg bg-red-50 px-2 py-1 text-[12px] text-red-800"><span className="font-bold">Gerekçe:</span> {r.rejectReason}</div>}
                    <div className="mt-1 flex flex-wrap items-center gap-2">
                      {r.files?.map((f) => (
                        <button key={f.id} type="button" className="inline-flex min-h-11 items-center gap-1 text-[12px] text-canvas-violet hover:underline sm:min-h-0"
                          onClick={() => void leaveApi.file(r.id, f).catch((e) => toast.error(errText(e, 'İndirilemedi.')))}>
                          <Download aria-hidden className="h-3.5 w-3.5" />{f.filename}
                        </button>
                      ))}
                      {r.needsDoc && ['yonetici', 'ik', 'onaylandi'].includes(r.status) && (
                        <FilePick label={r.files?.length ? 'Belge ekle' : 'Belgeyi yükle'} accept=".pdf,.jpg,.jpeg,.png,.webp,.heic"
                          onPick={(f) => void leaveApi.upload(r.id, f).then(() => { toast.success('Belge yüklendi.'); refresh(); }).catch((e) => toast.error(errText(e, 'Yüklenemedi.')))} />
                      )}
                      {(['yonetici', 'ik'].includes(r.status) || (r.status === 'onaylandi' && r.start > today)) && (
                        <button type="button" className="text-[12px] font-bold text-red-700 hover:underline" onClick={() => setCancel(r)}>
                          {r.status === 'onaylandi' ? 'İptal et' : 'Geri al'}
                        </button>
                      )}
                    </div>
                  </li>
                ))}
              </ul>
            </Block>
          </div>
          {d.holidays.length > 0 && (
            <Block title="Yaklaşan resmî tatiller" help={`Çalışma takviminiz: ${d.calendar ?? '—'}. Tatiller ve hafta sonu izin gününden düşülür.`}>
              <ul className="flex flex-wrap gap-2">
                {d.holidays.map((h) => (
                  <li key={h.day} className="rounded-lg bg-white/85 px-2.5 py-1 text-[12px]"><span className="font-bold">{shortDay(h.day)}</span> {h.name}{h.half ? ' (yarım gün)' : ''}</li>
                ))}
              </ul>
            </Block>
          )}
        </>
      )}
      <AskSheet open={!!cancel} title={cancel?.status === 'onaylandi' ? 'Onaylı izni iptal et' : 'Talebi geri al'} danger confirm={cancel?.status === 'onaylandi' ? 'İptal et' : 'Geri al'}
        busy={del.isPending}
        message={<>{cancel ? `${cancel.typeLabel} · ${span(cancel.start, cancel.end)}` : ''} {cancel?.status === 'onaylandi' ? 'iptal edilecek; günler bakiyenize iade edilir ve yöneticinize bilgi gider.' : 'talebi geri alınacak.'} Bu işlem geri alınamaz.</>}
        onClose={() => setCancel(null)} onConfirm={() => cancel && del.mutate(cancel.id)} />
    </HrFrame>
  );
}

function NewRequest({ onDone }: { onDone: () => void }) {
  const q = useQuery({ queryKey: ['hr', 'leave', 'me'], queryFn: leaveApi.me, enabled: ENGINE_ENABLED });
  const types = q.data?.types ?? [];
  const [type, setType] = useState('');
  const [start, setStart] = useState('');
  const [end, setEnd] = useState('');
  const [half, setHalf] = useState('');
  const [deputyId, setDeputyId] = useState('');
  const [contact, setContact] = useState('');
  const [note, setNote] = useState('');
  useEffect(() => { if (!type && types.length) setType(types[0].key); }, [types, type]);
  const t = types.find((x) => x.key === type);
  const single = !!start && (!end || end === start);
  useEffect(() => { if (!single || !t?.halfDay) setHalf(''); }, [single, t?.halfDay]);
  const input = useMemo(() => ({ type, start, end: end || start, half }), [type, start, end, half]);
  const di = useDebounced(input, 250);
  const calc = useQuery({ queryKey: ['hr', 'leave', 'calc', di], queryFn: () => leaveApi.calc(di), enabled: ENGINE_ENABLED && !!di.type && !!di.start, retry: false });
  const c = calc.data;
  const save = useMutation({
    mutationFn: () => leaveApi.create({ ...input, deputyId: deputyId || undefined, contact, note }),
    onSuccess: (r) => {
      toast.success(r.status === 'ik' ? 'Talebiniz İK’ya iletildi.' : 'Talebiniz yöneticinize iletildi.');
      setStart(''); setEnd(''); setHalf(''); setNote(''); setContact(''); setDeputyId('');
      onDone();
    },
    onError: (e) => toast.error(errText(e, 'Talep gönderilemedi.')),
  });
  if (!types.length) {
    return (
      <Block title="İzin iste">
        <Note tone="info">İzin türleri İK tarafından henüz açılmadı{q.data?.pendingTypes.length ? ` (${q.data.pendingTypes.length} tür onay bekliyor)` : ''}. İK gün sayılarını onaylayınca buradan izin isteyebilirsiniz.</Note>
      </Block>
    );
  }
  return (
    <Block title="İzin iste" help="Tarihleri seçince düşecek gün sayısı hemen hesaplanır; hafta sonu ve resmî tatiller sayılmaz.">
      <form className="flex flex-col gap-3" onSubmit={(e) => { e.preventDefault(); save.mutate(); }}>
        <label className="flex flex-col gap-1">
          <span className={labelCls}>İzin türü</span>
          <select className={field} value={type} onChange={(e) => setType(e.target.value)}>
            {types.map((x) => <option key={x.key} value={x.key}>{x.label}</option>)}
          </select>
          {t?.legal && <span className="text-[11px] leading-snug text-canvas-muted">{t.legal}</span>}
        </label>
        <div className="grid grid-cols-2 gap-2">
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Başlangıç</span>
            <input type="date" className={field} value={start} onChange={(e) => { setStart(e.target.value); if (end && e.target.value > end) setEnd(e.target.value); }} required />
          </label>
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Bitiş (son izin günü)</span>
            <input type="date" className={field} value={end} min={start || undefined} onChange={(e) => setEnd(e.target.value)} />
          </label>
        </div>
        {single && t?.halfDay && (
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Süre</span>
            <select className={field} value={half} onChange={(e) => setHalf(e.target.value)}>
              {Object.entries(q.data?.halfOptions ?? {}).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
          </label>
        )}
        {c && (
          <div className={`rounded-xl px-3 py-2 text-[12.5px] ${c.errors.length ? 'bg-red-50 text-red-900' : 'bg-violet-50 text-canvas-ink'}`} aria-live="polite">
            <div className="font-extrabold">{gun(c.days)} düşer{c.available !== null ? ` · kullanılabilir bakiye ${gun(c.available)}` : ''}</div>
            {c.holidays.length > 0 && <div className="text-[11.5px]">Aradaki tatil: {c.holidays.map((h) => `${shortDay(h.day)}${h.half ? ' (yarım)' : ''}`).join(', ')}</div>}
            {c.errors.map((x) => <div key={x} className="mt-1 flex gap-1.5"><AlertTriangle aria-hidden className="mt-0.5 h-3.5 w-3.5 shrink-0" />{x}</div>)}
            {c.warnings.map((x) => <div key={x} className="mt-1 flex gap-1.5 text-amber-900"><Info aria-hidden className="mt-0.5 h-3.5 w-3.5 shrink-0" />{x}</div>)}
          </div>
        )}
        {calc.error && <Note tone="err">{errText(calc.error, 'Gün hesaplanamadı.')}</Note>}
        <label className="flex flex-col gap-1">
          <span className={labelCls}>Vekil (isteğe bağlı)</span>
          <select className={field} value={deputyId} onChange={(e) => setDeputyId(e.target.value)}>
            <option value="">Yok</option>
            {(q.data?.deputies ?? []).map((p) => <option key={p.id} value={p.id}>{p.adSoyad}{p.departman ? ` · ${p.departman}` : ''}</option>)}
          </select>
        </label>
        <label className="flex flex-col gap-1">
          <span className={labelCls}>İzindeyken ulaşılacak telefon (isteğe bağlı)</span>
          <input type="tel" className={field} value={contact} onChange={(e) => setContact(e.target.value)} autoComplete="tel" />
        </label>
        <label className="flex flex-col gap-1">
          <span className={labelCls}>Not (isteğe bağlı)</span>
          <textarea className={`${field} min-h-[64px]`} value={note} onChange={(e) => setNote(e.target.value)} />
        </label>
        <button type="submit" className={btnPrimary} disabled={!c || !!c.errors.length || calc.isFetching || save.isPending}>
          {save.isPending ? 'Gönderiliyor…' : 'İzin iste'}
        </button>
      </form>
    </Block>
  );
}
