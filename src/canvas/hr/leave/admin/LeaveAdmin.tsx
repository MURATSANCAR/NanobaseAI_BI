import { useEffect, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Download, FileSpreadsheet, Lock, Plus, Search, Trash2 } from 'lucide-react';
import { ENGINE_ENABLED } from '../../../engine';
import { Loading, Note, Pill, TableWrap, btnGhost, btnPrimary, errText, field, label as labelCls, nf, td, th } from '../../../admin/ui';
import Sheet from '../../../editorial/studio/reader/Sheet';
import { EmptyHint } from '../../../components/Explain';
import { FilePick } from '../../../components/FileDrop';
import SqlInfo from '../../../components/SqlInfo';
import { useDebounced } from '../../../editorial/kit';
import { AskSheet, Block } from '../../parts';
import { localIso, longDay, portalApi, type PortalMeta } from '../../portal/portalApi';
import { STATUS_TONE, gun, leaveApi, span, type BalanceRow, type Holiday, type LeaveRequest, type LeaveSettings, type LeaveType, type OpeningResult, type WorkCalendar } from '../leaveApi';

/** İK yönetimi › İzinler / İzin ayarları / E-posta bildirimleri. */
export default function LeaveAdmin({ tab, meta }: { tab: 'izinler' | 'izin-ayarlari' | 'bildirimler'; meta: PortalMeta }) {
  if (tab === 'izinler') return <Requests meta={meta} />;
  if (tab === 'izin-ayarlari') return <Settings />;
  return <Outbox meta={meta} />;
}

const useRefresh = () => {
  const qc = useQueryClient();
  return () => { void qc.invalidateQueries({ queryKey: ['hr', 'leave'] }); void qc.invalidateQueries({ queryKey: ['hr', 'portal', 'home'] }); };
};

/* ------------------------------------------------------------------ talepler + bakiyeler */

function Requests({ meta }: { meta: PortalMeta }) {
  const refresh = useRefresh();
  const [status, setStatus] = useState('acik');
  const [month, setMonth] = useState('');
  const [q, setQ] = useState('');
  const dq = useDebounced(q, 250);
  const list = useQuery({ queryKey: ['hr', 'leave', 'admin', status, month, dq], queryFn: () => leaveApi.adminRequests({ status, month, q: dq }), enabled: ENGINE_ENABLED });
  const [reject, setReject] = useState<LeaveRequest | null>(null);
  const [cancel, setCancel] = useState<LeaveRequest | null>(null);
  const decide = useMutation({
    mutationFn: (v: { id: string; action: 'onayla' | 'reddet'; reason?: string }) => leaveApi.decide(v.id, v.action, v.reason),
    onSuccess: () => { setReject(null); toast.success('Karar kaydedildi.'); refresh(); },
    onError: (e) => toast.error(errText(e, 'Kaydedilemedi.')),
    onSettled: () => setReject(null),
  });
  const del = useMutation({
    mutationFn: (id: string) => leaveApi.cancel(id),
    onSuccess: () => { setCancel(null); toast.success('İptal edildi.'); refresh(); },
    onError: (e) => toast.error(errText(e, 'İptal edilemedi.')),
    onSettled: () => setCancel(null),
  });
  const [payMonth, setPayMonth] = useState(() => localIso(new Date()).slice(0, 7));
  return (
    <>
      <Block title="İzin talepleri" help="İK onayı bekleyenler ve bütün talepler. Hassas izin türü (rapor, doğum) yalnız «Hassas özlük verisi» yetkisiyle adıyla görünür."
        action={
          <div className="flex flex-wrap items-end gap-2">
            <label className="flex flex-col gap-1">
              <span className={labelCls}>Bordro listesi</span>
              <input type="month" className={field} value={payMonth} onChange={(e) => setPayMonth(e.target.value)} />
            </label>
            <button type="button" className={btnGhost} onClick={() => void leaveApi.payroll(payMonth).catch((e) => toast.error(errText(e, 'İndirilemedi.')))}>
              <FileSpreadsheet aria-hidden className="h-4 w-4" />Excel
            </button>
          </div>
        }>
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Ara</span>
            <span className="relative flex items-center">
              <Search aria-hidden className="pointer-events-none absolute left-3 h-4 w-4 text-canvas-muted" />
              <input className={`${field} pl-9`} value={q} onChange={(e) => setQ(e.target.value)} placeholder="Ad, departman" />
            </span>
          </label>
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Durum</span>
            <select className={field} value={status} onChange={(e) => setStatus(e.target.value)}>
              <option value="acik">Onay bekleyenler</option>
              {Object.entries(list.data?.status ?? {}).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
              <option value="hepsi">Hepsi</option>
            </select>
          </label>
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Ay</span>
            <input type="month" className={field} value={month} onChange={(e) => setMonth(e.target.value)} />
          </label>
        </div>
        {list.error && <Note tone="err">{errText(list.error, 'Talepler okunamadı.')}</Note>}
        {list.isLoading && <Loading />}
        {list.data && !list.data.items.length && <EmptyHint title="Bu süzgece uyan talep yok" />}
        {!!list.data?.items.length && (
          <div className="mt-3">
            <TableWrap>
              <thead><tr><th className={th}>Çalışan</th><th className={th}>Tür</th><th className={th}>Tarih</th><th className={th}>Gün</th><th className={th}>Durum</th><th className={th} /></tr></thead>
              <tbody>
                {list.data.items.map((r) => (
                  <tr key={r.id} className="border-t border-slate-100">
                    <td className={td}><span className="font-bold">{r.adSoyad}</span><span className="block text-[11.5px] text-canvas-muted">{r.departman || '—'}</span></td>
                    <td className={td}>{r.typeLabel}</td>
                    <td className={`${td} whitespace-nowrap`}>{span(r.start, r.end)}</td>
                    <td className={`${td} tabular-nums`}>{gun(r.days)}</td>
                    <td className={td}><Pill tone={STATUS_TONE[r.status] ?? 'muted'}>{r.statusLabel}</Pill>{r.rejectReason && <span className="block text-[11px] text-canvas-muted">{r.rejectReason}</span>}</td>
                    <td className={td}>
                      <div className="flex flex-wrap gap-1.5">
                        {['yonetici', 'ik'].includes(r.status) && (
                          <>
                            <button type="button" className={btnGhost} onClick={() => setReject(r)}>Reddet</button>
                            <button type="button" className={btnPrimary} disabled={decide.isPending} onClick={() => decide.mutate({ id: r.id, action: 'onayla' })}>Onayla</button>
                          </>
                        )}
                        {r.status === 'onaylandi' && <button type="button" className={`${btnGhost} !text-red-700`} onClick={() => setCancel(r)}>İptal</button>}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </TableWrap>
          </div>
        )}
      </Block>
      <Balances meta={meta} />
      <AskSheet open={!!reject} title="Talebi reddet" danger confirm="Reddet" input="Gerekçe (çalışan görür)" required busy={decide.isPending}
        message={<>{reject ? `${reject.adSoyad} · ${span(reject.start, reject.end)}` : ''} talebi reddedilecek.</>}
        onClose={() => setReject(null)} onConfirm={(reason) => reject && decide.mutate({ id: reject.id, action: 'reddet', reason })} />
      <AskSheet open={!!cancel} title="Onaylı izni iptal et" danger confirm="İptal et" busy={del.isPending}
        message={<>{cancel ? `${cancel.adSoyad} · ${span(cancel.start, cancel.end)}` : ''} izni iptal edilecek; yıllık izinse günler bakiyeye iade edilir. Bu işlem geri alınamaz.</>}
        onClose={() => setCancel(null)} onConfirm={() => cancel && del.mutate(cancel.id)} />
    </>
  );
}

function Balances({ meta }: { meta: PortalMeta }) {
  const q = useQuery({ queryKey: ['hr', 'leave', 'balances'], queryFn: leaveApi.balances, enabled: ENGINE_ENABLED });
  const [open, setOpen] = useState<BalanceRow | null>(null);
  const [importing, setImporting] = useState<File | null>(null);
  const [text, setText] = useState('');
  const t = text.trim().toLocaleLowerCase('tr-TR');
  const items = (q.data?.items ?? []).filter((b) => !t || `${b.adSoyad} ${b.idNo} ${b.departman ?? ''}`.toLocaleLowerCase('tr-TR').includes(t));
  const st = q.data?.stats;
  return (
    <Block title="Yıllık izin bakiyeleri" info={<SqlInfo k={q.data?.kaynaklar} alan="items[]" label="İzin bakiyeleri" />}
      help="Bakiye izin defterinin toplamıdır (açılış + hakediş − kullanım + iade ± düzeltme). Geçmiş yılların bakiyesini bir kez açılış Excel'iyle girin; sonraki yıldönümlerini gece işi yazar."
      action={
        <>
          <FilePick label="Açılış bakiyesi yükle" accept=".xlsx" maxBytes={meta.fileMaxMb * 1024 * 1024} onPick={setImporting} hint="Başlıklar: id_no, gun, tarih, aciklama" />
          <button type="button" className={btnGhost} onClick={() => void leaveApi.openingTemplate().catch((e) => toast.error(errText(e, 'İndirilemedi.')))}>
            <Download aria-hidden className="h-4 w-4" />Açılış şablonu
          </button>
        </>
      }>
      {st && (
        <div className="mb-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
          <MiniStat label="Bugün izinde" value={nf.format(st.onLeaveToday)} />
          <MiniStat label="Onay bekleyen" value={nf.format(st.waiting)} />
          <MiniStat label="Bakiyesi 30+ gün" value={nf.format(st.highBalance.length)} />
          <MiniStat label="30 gün içinde hakediş" value={nf.format(st.accrualSoon.length)} />
        </div>
      )}
      <input className={`${field} mb-2 max-w-[360px]`} value={text} onChange={(e) => setText(e.target.value)} placeholder="Ad, personel no, departman" aria-label="Bakiye ara" />
      {q.error && <Note tone="err">{errText(q.error, 'Bakiyeler okunamadı.')}</Note>}
      {q.isLoading && <Loading />}
      {q.data && !q.data.items.length && <EmptyHint title="Aktif personel kaydı yok" />}
      {!!items.length && (
        <TableWrap>
          <thead><tr><th className={th}>Çalışan</th><th className={th}>Bakiye</th><th className={th}>Bekleyen</th><th className={th}>Kullanılabilir</th><th className={th}>Bu yıl kullanılan</th><th className={th}>Sıradaki hakediş</th></tr></thead>
          <tbody>
            {items.map((b) => (
              <tr key={b.id} className="border-t border-slate-100">
                <td className={td}>
                  <button type="button" className="text-left font-bold text-canvas-violet hover:underline" onClick={() => setOpen(b)}>{b.adSoyad}</button>
                  <span className="block text-[11.5px] text-canvas-muted">{b.idNo}{b.departman ? ` · ${b.departman}` : ''}{!b.hasOpening ? ' · açılış yok' : ''}</span>
                </td>
                <td className={`${td} tabular-nums`}>{gun(b.balance)}</td>
                <td className={`${td} tabular-nums`}>{b.pending ? gun(b.pending) : '—'}</td>
                <td className={`${td} font-bold tabular-nums ${b.available < 0 ? 'text-red-700' : ''}`}>{gun(b.available)}</td>
                <td className={`${td} tabular-nums`}>{gun(b.usedYear)}</td>
                <td className={`${td} whitespace-nowrap`}>{b.nextAccrual ? `${longDay(b.nextAccrual.date)} · ${gun(b.nextAccrual.days)}` : 'İşe giriş tarihi yok'}</td>
              </tr>
            ))}
          </tbody>
        </TableWrap>
      )}
      <LedgerSheet row={open} onClose={() => setOpen(null)} />
      <OpeningSheet file={importing} onClose={() => setImporting(null)} />
    </Block>
  );
}

function MiniStat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl bg-white/85 px-3 py-2">
      <div className="text-[10.5px] font-bold uppercase tracking-wide text-canvas-muted">{label}</div>
      <div className="text-[18px] font-extrabold tabular-nums">{value}</div>
    </div>
  );
}

function LedgerSheet({ row, onClose }: { row: BalanceRow | null; onClose: () => void }) {
  const refresh = useRefresh();
  const q = useQuery({ queryKey: ['hr', 'leave', 'ledger', row?.id], queryFn: () => leaveApi.ledger(row!.id), enabled: !!row });
  const [days, setDays] = useState('');
  const [note, setNote] = useState('');
  const save = useMutation({
    mutationFn: () => leaveApi.adjust({ personId: row!.id, days: Number(days.replace(',', '.')), note }),
    onSuccess: () => { toast.success('Düzeltme deftere yazıldı.'); setDays(''); setNote(''); refresh(); },
    onError: (e) => toast.error(errText(e, 'Kaydedilemedi.')),
  });
  return (
    <Sheet open={!!row} modal wide onClose={onClose} title={row ? `İzin defteri · ${row.adSoyad}` : ''} subtitle={q.data ? `Bakiye ${gun(q.data.summary.balance)} · kullanılabilir ${gun(q.data.summary.available)}` : undefined}>
      {q.isLoading && <Loading />}
      {q.data && (
        <div className="flex flex-col gap-4">
          <form className="grid grid-cols-1 gap-2 rounded-xl bg-slate-50 p-3 sm:grid-cols-[120px_1fr_auto] sm:items-end" onSubmit={(e) => { e.preventDefault(); save.mutate(); }}>
            <label className="flex flex-col gap-1">
              <span className={labelCls}>Gün (±)</span>
              <input className={field} inputMode="decimal" value={days} onChange={(e) => setDays(e.target.value)} placeholder="ör. 2 ya da -1,5" required />
            </label>
            <label className="flex flex-col gap-1">
              <span className={labelCls}>Neden (defterde görünür)</span>
              <input className={field} value={note} onChange={(e) => setNote(e.target.value)} required />
            </label>
            <button type="submit" className={btnPrimary} disabled={save.isPending}>Düzeltme yaz</button>
          </form>
          {q.data.items.length ? (
            <TableWrap>
              <thead><tr><th className={th}>Tarih</th><th className={th}>Hareket</th><th className={th}>Gün</th><th className={th}>Açıklama</th><th className={th}>Yazan</th></tr></thead>
              <tbody>
                {q.data.items.map((x) => (
                  <tr key={x.id} className="border-t border-slate-100">
                    <td className={`${td} whitespace-nowrap`}>{longDay(x.onDate)}</td>
                    <td className={td}>{x.reasonLabel}</td>
                    <td className={`${td} font-mono tabular-nums ${x.days < 0 ? 'text-red-700' : 'text-emerald-700'}`}>{x.days > 0 ? '+' : ''}{String(x.days).replace('.', ',')}</td>
                    <td className={`${td} text-[12px]`}>{x.note || '—'}</td>
                    <td className={`${td} text-[12px]`}>{x.actor || '—'}</td>
                  </tr>
                ))}
              </tbody>
            </TableWrap>
          ) : <EmptyHint title="Defterde hareket yok" why="Açılış bakiyesini Excel'le yükleyin ya da düzeltme yazın." />}
        </div>
      )}
    </Sheet>
  );
}

function OpeningSheet({ file, onClose }: { file: File | null; onClose: () => void }) {
  const refresh = useRefresh();
  const pre = useQuery({ queryKey: ['hr', 'leave', 'opening', file?.name, file?.size, file?.lastModified], queryFn: () => leaveApi.opening(file as File, false), enabled: !!file, retry: false, gcTime: 0 });
  const apply = useMutation({
    mutationFn: () => leaveApi.opening(file as File, true),
    onSuccess: (r: OpeningResult) => { toast.success(`${r.applied} kişinin açılış bakiyesi yazıldı.`); refresh(); onClose(); },
    onError: (e) => toast.error(errText(e, 'Yazılamadı.')),
  });
  const d = pre.data;
  return (
    <Sheet open={!!file} modal wide onClose={onClose} title="Açılış bakiyesi" subtitle={file?.name}>
      {pre.isLoading && <Loading />}
      {pre.error && <Note tone="err">{errText(pre.error, 'Dosya okunamadı.')}</Note>}
      {d && (
        <div className="flex flex-col gap-3">
          <p className="text-[12.5px]">{d.counts.ok} satır yazılabilir, {d.counts.error} satırda hata var. Kişi başına bir açılış satırı olur; farkı sonra düzeltmeyle girin. Hiçbir şey henüz yazılmadı.</p>
          <TableWrap>
            <thead><tr><th className={th}>Satır</th><th className={th}>Personel</th><th className={th}>Gün</th><th className={th}>Tarih</th><th className={th}>Sonuç</th></tr></thead>
            <tbody>
              {d.rows.map((r) => (
                <tr key={r.row} className="border-t border-slate-100">
                  <td className={td}>{r.row}</td>
                  <td className={td}>{r.adSoyad || r.idNo}</td>
                  <td className={`${td} tabular-nums`}>{gun(r.days)}</td>
                  <td className={td}>{longDay(r.onDate)}</td>
                  <td className={`${td} text-[12px]`}>{r.errors.length ? <span className="text-red-700">{r.errors.join(' ')}</span> : <Pill tone="ok">Yazılacak</Pill>}</td>
                </tr>
              ))}
            </tbody>
          </TableWrap>
          <div className="flex justify-end gap-2">
            <button type="button" className={btnGhost} onClick={onClose}>Vazgeç</button>
            <button type="button" className={btnPrimary} disabled={!!d.counts.error || !d.counts.ok || apply.isPending} onClick={() => apply.mutate()}>{d.counts.ok} satırı yaz</button>
          </div>
        </div>
      )}
    </Sheet>
  );
}

/* ------------------------------------------------------------------ ayarlar */

function Settings() {
  const q = useQuery({ queryKey: ['hr', 'leave', 'settings'], queryFn: leaveApi.settings, enabled: ENGINE_ENABLED });
  if (q.error) return <Note tone="err">{errText(q.error, 'İzin ayarları okunamadı.')}</Note>;
  if (!q.data) return <Loading />;
  return (
    <>
      <Flow s={q.data} />
      <Types s={q.data} />
      <Holidays s={q.data} />
      <Calendars s={q.data} />
    </>
  );
}

function Flow({ s }: { s: LeaveSettings }) {
  const refresh = useRefresh();
  const [f, setF] = useState(s.settings);
  useEffect(() => setF(s.settings), [s.settings]);
  const save = useMutation({
    mutationFn: () => leaveApi.saveSettings({ flow: f.flow, advance: f.advance, tiers: f.tiers, ageRule: f.ageRule, startField: f.startField, conflictPct: f.conflictPct, reminderWorkdays: f.reminderWorkdays }),
    onSuccess: () => { toast.success('İzin ayarları kaydedildi.'); refresh(); },
    onError: (e) => toast.error(errText(e, 'Kaydedilemedi.')),
  });
  const num = (v: string) => Number(v.replace(',', '.')) || 0;
  return (
    <Block title="Onay akışı ve hakediş" help={`Hakediş gece işi ${s.settings.accrualFrom ? `${longDay(s.settings.accrualFrom)} tarihinden sonraki` : 'ilk koşusundan sonraki'} işe giriş yıldönümlerini yazar; öncesi açılış bakiyesiyle girilir.`}>
      <form className="flex flex-col gap-3" onSubmit={(e) => { e.preventDefault(); save.mutate(); }}>
        <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-2 lg:grid-cols-4">
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Onay akışı</span>
            <select className={field} value={f.flow} onChange={(e) => setF({ ...f, flow: e.target.value as 'yonetici' | 'yonetici_ik' })}>
              <option value="yonetici">Yalnız yönetici</option>
              <option value="yonetici_ik">Yönetici, sonra İK</option>
            </select>
          </label>
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Kıdem başlangıcı</span>
            <select className={field} value={f.startField} onChange={(e) => setF({ ...f, startField: e.target.value })}>
              <option value="f_ise_giris_tarihi">İlk işe giriş tarihi</option>
              <option value="s_ise_giris_tarihi">Son işe giriş tarihi</option>
            </select>
          </label>
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Çakışma uyarısı (% ekip)</span>
            <input className={field} inputMode="numeric" value={f.conflictPct} onChange={(e) => setF({ ...f, conflictPct: num(e.target.value) })} />
          </label>
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Hatırlatma (iş günü sonra)</span>
            <input className={field} inputMode="numeric" value={f.reminderWorkdays} onChange={(e) => setF({ ...f, reminderWorkdays: num(e.target.value) })} />
          </label>
        </div>
        <label className="flex items-center gap-2 text-[12.5px] font-bold">
          <input type="checkbox" className="h-4 w-4" checked={f.advance} onChange={(e) => setF({ ...f, advance: e.target.checked })} />
          Avans izin: yıllık izin bakiyesi yetmese de talep açılabilir (bakiye eksiye düşer)
        </label>
        <fieldset className="rounded-xl bg-slate-50 p-3">
          <legend className="px-1 text-[12.5px] font-extrabold">Yıllık izin basamakları (tamamlanan hizmet yılı → gün)</legend>
          <div className="flex flex-col gap-2">
            {f.tiers.map((t, i) => (
              <div key={i} className="flex flex-wrap items-center gap-2 text-[12.5px]">
                <input className={`${field} !w-24`} inputMode="numeric" value={t.minYears} aria-label="En az yıl" onChange={(e) => setF({ ...f, tiers: f.tiers.map((x, j) => (j === i ? { ...x, minYears: num(e.target.value) } : x)) })} />
                <span>. yıldan itibaren</span>
                <input className={`${field} !w-24`} inputMode="decimal" value={t.days} aria-label="Gün" onChange={(e) => setF({ ...f, tiers: f.tiers.map((x, j) => (j === i ? { ...x, days: num(e.target.value) } : x)) })} />
                <span>gün</span>
                {f.tiers.length > 1 && <button type="button" aria-label="Basamağı sil" className="inline-flex h-11 w-11 items-center justify-center rounded-lg text-red-700 hover:bg-red-50 sm:h-8 sm:w-8" onClick={() => setF({ ...f, tiers: f.tiers.filter((_, j) => j !== i) })}><Trash2 aria-hidden className="h-4 w-4" /></button>}
              </div>
            ))}
            <button type="button" className={`${btnGhost} self-start`} onClick={() => setF({ ...f, tiers: [...f.tiers, { minYears: (f.tiers[f.tiers.length - 1]?.minYears ?? 0) + 1, days: f.tiers[f.tiers.length - 1]?.days ?? 14 }] })}><Plus aria-hidden className="h-4 w-4" />Basamak ekle</button>
            <div className="flex flex-wrap items-center gap-2 text-[12.5px]">
              <span>Yaşı</span>
              <input className={`${field} !w-20`} inputMode="numeric" value={f.ageRule.maxYoungAge} aria-label="Genç yaş sınırı" onChange={(e) => setF({ ...f, ageRule: { ...f.ageRule, maxYoungAge: num(e.target.value) } })} />
              <span>ve altı ya da</span>
              <input className={`${field} !w-20`} inputMode="numeric" value={f.ageRule.minOldAge} aria-label="Yaşlı yaş sınırı" onChange={(e) => setF({ ...f, ageRule: { ...f.ageRule, minOldAge: num(e.target.value) } })} />
              <span>ve üstü olana en az</span>
              <input className={`${field} !w-20`} inputMode="decimal" value={f.ageRule.days} aria-label="Yaş kuralı gün" onChange={(e) => setF({ ...f, ageRule: { ...f.ageRule, days: num(e.target.value) } })} />
              <span>gün</span>
            </div>
            <p className="text-[11px] text-canvas-muted">Başlangıç değerleri 4857 sayılı Kanun md. 53'e göredir; İK/hukuk doğrulamalıdır.</p>
          </div>
        </fieldset>
        <div className="flex justify-end"><button type="submit" className={btnPrimary} disabled={save.isPending}>Kaydet</button></div>
      </form>
    </Block>
  );
}

function Types({ s }: { s: LeaveSettings }) {
  const [edit, setEdit] = useState<LeaveType | 'new' | null>(null);
  const pending = s.types.filter((t) => t.active && !t.approved).length;
  return (
    <Block title="İzin türleri" help="Onaylanmamış türle talep açılamaz. Gün sınırı ya da ücret kuralı değişince onay düşer ve yeniden onaylanır."
      action={<button type="button" className={btnPrimary} onClick={() => setEdit('new')}><Plus aria-hidden className="h-4 w-4" />Tür ekle</button>}>
      {pending > 0 && <Note tone="warn">{pending} izin türü İK/hukuk onayı bekliyor; çalışanlar bu türlerle henüz izin isteyemez.</Note>}
      <TableWrap>
        <thead><tr><th className={th}>Tür</th><th className={th}>Sayım</th><th className={th}>Sınır</th><th className={th}>Kural</th><th className={th}>Durum</th></tr></thead>
        <tbody>
          {s.types.map((t) => (
            <tr key={t.key} className={`border-t border-slate-100 ${t.active ? '' : 'opacity-50'}`}>
              <td className={td}>
                <button type="button" className="text-left font-bold text-canvas-violet hover:underline" onClick={() => setEdit(t)}>{t.label}</button>
                {t.sensitive && <Lock aria-label="Hassas" className="ml-1 inline h-3.5 w-3.5 text-amber-700" />}
              </td>
              <td className={td}>{s.countModes[t.countMode]}</td>
              <td className={`${td} text-[12px]`}>{[t.maxRequest ? `talepte ${t.maxRequest}` : '', t.maxYear ? `yılda ${t.maxYear}` : ''].filter(Boolean).join(' · ') || '—'}</td>
              <td className={`${td} text-[12px]`}>{[t.paid ? 'ücretli' : 'ücretsiz', t.fromBalance ? 'bakiyeden' : '', t.payroll ? 'bordroya' : '', t.needsDoc ? 'belge' : '', t.halfDay ? 'yarım gün' : ''].filter(Boolean).join(' · ')}</td>
              <td className={td}>{!t.active ? <Pill tone="muted">Kapalı</Pill> : t.approved ? <Pill tone="ok">Onaylı</Pill> : <Pill tone="warn">Onay bekliyor</Pill>}</td>
            </tr>
          ))}
        </tbody>
      </TableWrap>
      <TypeSheet t={edit} s={s} onClose={() => setEdit(null)} />
    </Block>
  );
}

function TypeSheet({ t, s, onClose }: { t: LeaveType | 'new' | null; s: LeaveSettings; onClose: () => void }) {
  const refresh = useRefresh();
  const cur = t && t !== 'new' ? t : null;
  const blank = { key: '', label: '', paid: true, fromBalance: false, payroll: false, sensitive: false, needsDoc: false, halfDay: false, countMode: 'is_gunu' as string,
    maxRequest: '' as string | number, maxYear: '' as string | number, legal: '', active: true, approved: false };
  const [f, setF] = useState(blank);
  useEffect(() => {
    setF(cur ? { key: cur.key, label: cur.label, paid: cur.paid, fromBalance: cur.fromBalance, payroll: cur.payroll, sensitive: cur.sensitive, needsDoc: cur.needsDoc,
      halfDay: cur.halfDay, countMode: cur.countMode as string, maxRequest: cur.maxRequest ?? '', maxYear: cur.maxYear ?? '', legal: cur.legal ?? '', active: cur.active, approved: cur.approved } : blank);
  }, [t]); // eslint-disable-line react-hooks/exhaustive-deps
  const save = useMutation({
    mutationFn: () => {
      const body = { ...f, maxRequest: f.maxRequest === '' ? null : Number(String(f.maxRequest).replace(',', '.')),
        maxYear: f.maxYear === '' ? null : Number(String(f.maxYear).replace(',', '.')) } as unknown as Partial<LeaveType>;
      return cur ? leaveApi.updateType(cur.key, body) : leaveApi.createType(body);
    },
    onSuccess: () => { toast.success('İzin türü kaydedildi.'); refresh(); onClose(); },
    onError: (e) => toast.error(errText(e, 'Kaydedilemedi.')),
  });
  const box = (k: 'paid' | 'fromBalance' | 'payroll' | 'sensitive' | 'needsDoc' | 'halfDay' | 'active' | 'approved', text: string) => (
    <label className="flex items-center gap-2 text-[12.5px]"><input type="checkbox" className="h-4 w-4" checked={f[k]} onChange={(e) => setF({ ...f, [k]: e.target.checked })} />{text}</label>
  );
  return (
    <Sheet open={!!t} modal onClose={onClose} title={cur ? cur.label : 'Yeni izin türü'} subtitle={cur?.approvedBy ? `Onaylayan ${cur.approvedBy} · ${longDay(cur.approvedAt)}` : undefined}>
      <form className="flex flex-col gap-3" onSubmit={(e) => { e.preventDefault(); save.mutate(); }}>
        {!cur && (
          <label className="flex flex-col gap-1"><span className={labelCls}>Anahtar</span>
            <input className={`${field} font-mono`} value={f.key} onChange={(e) => setF({ ...f, key: e.target.value.toLowerCase() })} required pattern="[a-z][a-z0-9_]{1,39}" /></label>
        )}
        <label className="flex flex-col gap-1"><span className={labelCls}>Ad</span><input className={field} value={f.label} onChange={(e) => setF({ ...f, label: e.target.value })} required /></label>
        <div className="grid grid-cols-3 gap-2">
          <label className="flex flex-col gap-1"><span className={labelCls}>Sayım</span>
            <select className={field} value={f.countMode} onChange={(e) => setF({ ...f, countMode: e.target.value })}>
              {Object.entries(s.countModes).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select></label>
          <label className="flex flex-col gap-1"><span className={labelCls}>Talepte en çok</span><input className={field} inputMode="decimal" value={f.maxRequest} onChange={(e) => setF({ ...f, maxRequest: e.target.value })} /></label>
          <label className="flex flex-col gap-1"><span className={labelCls}>Yılda en çok</span><input className={field} inputMode="decimal" value={f.maxYear} onChange={(e) => setF({ ...f, maxYear: e.target.value })} /></label>
        </div>
        <div className="grid grid-cols-1 gap-1.5 rounded-xl bg-slate-50 p-3 sm:grid-cols-2">
          {box('paid', 'Ücretli')}{box('fromBalance', 'Yıllık izin bakiyesinden düşer')}{box('payroll', 'Bordro listesine girer')}{box('needsDoc', 'Belge ister')}
          {box('halfDay', 'Yarım gün olabilir')}{box('sensitive', 'Hassas (yönetici yalnız «izinli» görür)')}{box('active', 'Açık')}
        </div>
        <label className="flex flex-col gap-1"><span className={labelCls}>Yasal dayanak / açıklama (çalışan görür)</span>
          <textarea className={`${field} min-h-[72px]`} value={f.legal} onChange={(e) => setF({ ...f, legal: e.target.value })} /></label>
        <label className="flex items-start gap-2 rounded-xl bg-amber-50 p-3 text-[12.5px]">
          <input type="checkbox" className="mt-0.5 h-4 w-4" checked={f.approved} onChange={(e) => setF({ ...f, approved: e.target.checked })} />
          <span><span className="font-bold">Gün sayısı ve kurallar doğrulandı (İK/hukuk)</span><span className="block text-[11.5px] text-canvas-muted">Onaylı olmayan türle talep açılamaz; onay değişiklik kaydına adınızla düşer.</span></span>
        </label>
        <div className="flex justify-end gap-2"><button type="button" className={btnGhost} onClick={onClose}>Vazgeç</button><button type="submit" className={btnPrimary} disabled={save.isPending}>Kaydet</button></div>
      </form>
    </Sheet>
  );
}

function Holidays({ s }: { s: LeaveSettings }) {
  const refresh = useRefresh();
  const year = new Date().getFullYear();
  const [row, setRow] = useState<Holiday>({ day: '', name: '', half: false });
  const [ask, setAsk] = useState<Holiday | null>(null);
  const save = useMutation({
    mutationFn: (days: (Holiday & { delete?: boolean })[]) => leaveApi.saveHolidays(days),
    onSuccess: () => { setAsk(null); setRow({ day: '', name: '', half: false }); toast.success('Tatil takvimi güncellendi.'); refresh(); },
    onError: (e) => toast.error(errText(e, 'Kaydedilemedi.')),
    onSettled: () => setAsk(null),
  });
  const fixed = useMutation({
    mutationFn: (y: number) => leaveApi.fixedHolidays(y),
    onSuccess: (r) => { toast.success(r.added ? `${r.added} sabit tatil eklendi.` : 'Sabit tatillerin hepsi zaten var.'); refresh(); },
    onError: (e) => toast.error(errText(e, 'Eklenemedi.')),
  });
  return (
    <Block title="Resmî tatiller" help="İzin gününden düşülür; arife yarım gündür. Sabit günleri düğmeyle ekleyin, Ramazan ve Kurban bayramı günlerini her yıl elle girin."
      action={
        <>
          <button type="button" className={btnGhost} disabled={fixed.isPending} onClick={() => fixed.mutate(year)}>{year} sabit günleri ekle</button>
          <button type="button" className={btnGhost} disabled={fixed.isPending} onClick={() => fixed.mutate(year + 1)}>{year + 1} sabit günleri ekle</button>
        </>
      }>
      <form className="mb-3 grid grid-cols-1 gap-2 sm:grid-cols-[160px_1fr_auto_auto] sm:items-end" onSubmit={(e) => { e.preventDefault(); save.mutate([row]); }}>
        <label className="flex flex-col gap-1"><span className={labelCls}>Gün</span><input type="date" className={field} value={row.day} onChange={(e) => setRow({ ...row, day: e.target.value })} required /></label>
        <label className="flex flex-col gap-1"><span className={labelCls}>Ad</span><input className={field} value={row.name} onChange={(e) => setRow({ ...row, name: e.target.value })} placeholder="ör. Ramazan Bayramı 1. gün" required /></label>
        <label className="flex min-h-11 items-center gap-2 text-[12.5px]"><input type="checkbox" className="h-4 w-4" checked={row.half} onChange={(e) => setRow({ ...row, half: e.target.checked })} />Yarım gün (arife)</label>
        <button type="submit" className={btnPrimary} disabled={save.isPending}><Plus aria-hidden className="h-4 w-4" />Ekle</button>
      </form>
      {s.holidays.length ? (
        <ul className="grid grid-cols-1 gap-1.5 sm:grid-cols-2 xl:grid-cols-3">
          {s.holidays.map((h) => (
            <li key={h.day} className="flex items-center justify-between gap-2 rounded-lg bg-white/85 px-3 py-1.5 text-[12.5px]">
              <span className="min-w-0"><span className="font-bold">{longDay(h.day)}</span> · {h.name}{h.half ? ' (yarım)' : ''}</span>
              <button type="button" aria-label={`${h.name} tatilini sil`} className="inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-lg text-red-700 hover:bg-red-50 sm:h-8 sm:w-8" onClick={() => setAsk(h)}><Trash2 aria-hidden className="h-4 w-4" /></button>
            </li>
          ))}
        </ul>
      ) : <EmptyHint title="Tatil takvimi boş" why="Sabit günleri düğmeyle ekleyin." />}
      <AskSheet open={!!ask} title="Tatili sil" danger confirm="Sil" busy={save.isPending}
        message={<>«{ask?.name}» ({ask ? longDay(ask.day) : ''}) takvimden silinecek; o gün iş günü sayılır. Açılmış taleplerin gün sayısı değişmez.</>}
        onClose={() => setAsk(null)} onConfirm={() => ask && save.mutate([{ ...ask, delete: true }])} />
    </Block>
  );
}

function Calendars({ s }: { s: LeaveSettings }) {
  const refresh = useRefresh();
  const [items, setItems] = useState<WorkCalendar[]>(s.calendars);
  useEffect(() => setItems(s.calendars), [s.calendars]);
  const save = useMutation({
    mutationFn: () => leaveApi.saveCalendars(items),
    onSuccess: () => { toast.success('Çalışma takvimleri kaydedildi.'); refresh(); },
    onError: (e) => toast.error(errText(e, 'Kaydedilemedi.')),
  });
  const set = (i: number, patch: Partial<WorkCalendar>) => setItems(items.map((x, j) => (j === i ? { ...x, ...patch } : x)));
  return (
    <Block title="Çalışma takvimleri" help="Hangi günlerin iş günü sayılacağı. Cumartesi çalışan şube/lokasyon için ayrı takvim ekleyin; eşleşmeyen herkes varsayılan takvimdedir."
      action={<button type="button" className={btnGhost} onClick={() => setItems([...items, { id: '', name: 'Cumartesi dahil', days: '123456', matchField: 'sube', matchValues: [], isDefault: false }])}><Plus aria-hidden className="h-4 w-4" />Takvim ekle</button>}>
      <form className="flex flex-col gap-3" onSubmit={(e) => { e.preventDefault(); save.mutate(); }}>
        {items.map((c, i) => (
          <fieldset key={c.id || `yeni-${i}`} className="flex flex-col gap-2 rounded-xl bg-slate-50 p-3">
            <div className="flex flex-wrap items-end gap-2">
              <label className="flex min-w-[200px] flex-1 flex-col gap-1"><span className={labelCls}>Ad</span><input className={field} value={c.name} onChange={(e) => set(i, { name: e.target.value })} /></label>
              <label className="flex min-h-11 items-center gap-2 text-[12.5px]"><input type="radio" name="varsayilan" checked={c.isDefault} onChange={() => setItems(items.map((x, j) => ({ ...x, isDefault: j === i })))} />Varsayılan</label>
              {!c.isDefault && <button type="button" aria-label="Takvimi sil" className="inline-flex h-11 w-11 items-center justify-center rounded-lg text-red-700 hover:bg-red-50" onClick={() => setItems(items.filter((_, j) => j !== i))}><Trash2 aria-hidden className="h-4 w-4" /></button>}
            </div>
            <div className="flex flex-wrap gap-1.5" role="group" aria-label="Çalışılan günler">
              {s.weekdays.map((w, k) => {
                const on = c.days.includes(String(k + 1));
                return (
                  <button key={w} type="button" aria-pressed={on} onClick={() => set(i, { days: on ? c.days.replace(String(k + 1), '') : [...c.days, String(k + 1)].sort().join('') })}
                    className={`min-h-11 rounded-lg px-2.5 text-[12px] font-bold transition-colors duration-150 sm:min-h-8 ${on ? 'bg-canvas-violet text-white' : 'bg-white text-canvas-ink hover:bg-slate-100'}`}>{w.slice(0, 3)}</button>
                );
              })}
            </div>
            {!c.isDefault && (
              <div className="grid grid-cols-1 gap-2 sm:grid-cols-[200px_1fr]">
                <label className="flex flex-col gap-1"><span className={labelCls}>Eşleşen alan</span>
                  <select className={field} value={c.matchField ?? 'sube'} onChange={(e) => set(i, { matchField: e.target.value })}>
                    <option value="sube">Şube</option><option value="ofis_lokasyon">Ofis lokasyonu</option><option value="departman">Departman</option><option value="firma">Firma</option>
                  </select></label>
                <label className="flex flex-col gap-1"><span className={labelCls}>Değerler (virgülle)</span>
                  <input className={field} value={c.matchValues.join(', ')} onChange={(e) => set(i, { matchValues: e.target.value.split(',').map((x) => x.trim()).filter(Boolean) })} placeholder="ör. Depo" /></label>
              </div>
            )}
          </fieldset>
        ))}
        <div className="flex justify-end"><button type="submit" className={btnPrimary} disabled={save.isPending}>Kaydet</button></div>
      </form>
    </Block>
  );
}

/* ------------------------------------------------------------------ e-posta kuyruğu */

function Outbox({ meta }: { meta: PortalMeta }) {
  const q = useQuery({ queryKey: ['hr', 'portal', 'mail'], queryFn: () => portalApi.mail(), enabled: ENGINE_ENABLED, refetchInterval: 60_000 });
  const [open, setOpen] = useState<number | null>(null);
  const m = meta.mail;
  return (
    <Block title="E-posta bildirimleri"
      help="Evrak talebi ve izin olaylarının e-postaları. Yalnız şirket içi adreslere gider; gövdede hassas bilgi ve ek yoktur. Kipi ve alan adlarını Yönetim → Portal ayarları › İnsan kaynakları'ndan (HR_MAIL_MODE, HR_MAIL_DOMAINS, HR_PORTAL_LINK) değiştirin.">
      <div className="mb-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
        <MiniStat label="Kip" value={m.modes[m.mode] ?? m.mode} />
        <MiniStat label="Alan adları" value={m.domains.join(', ') || '—'} />
        <MiniStat label="Gönderilecek" value={nf.format(q.data?.waiting ?? 0)} />
        <MiniStat label="Son 24 saatte hata" value={nf.format(q.data?.failed24h ?? 0)} />
      </div>
      {m.mode === 'kapali' && <Note tone="info">Bildirimler kapalı: olaylar kuyruğa «Bildirim kapalı» diye yazılır, kimseye e-posta gitmez.</Note>}
      {!m.linkSet && <Note tone="warn">Portal adresi ayarlanmadı (HR_PORTAL_LINK ya da ALERT_LINK); e-postadaki bağlantılar eksik olur.</Note>}
      {!m.hrRecipients && <Note tone="warn">İK dağıtım adresi yok (HR_ALERT_RECIPIENTS); İK'ya giden bildirimler yazılmaz.</Note>}
      {q.error && <Note tone="err">{errText(q.error, 'Kuyruk okunamadı.')}</Note>}
      {q.data && !q.data.items.length && <EmptyHint title="Henüz bildirim yok" />}
      {!!q.data?.items.length && (
        <TableWrap>
          <thead><tr><th className={th}>Zaman</th><th className={th}>Alıcı</th><th className={th}>Konu</th><th className={th}>Durum</th></tr></thead>
          <tbody>
            {q.data.items.map((x) => (
              <tr key={x.id} className="border-t border-slate-100 align-top">
                <td className={`${td} whitespace-nowrap text-[12px]`}>{longDay(x.createdAt)}</td>
                <td className={`${td} text-[12px]`}>{x.recipient || '—'}</td>
                <td className={td}>
                  <button type="button" className="text-left text-[12.5px] font-bold text-canvas-violet hover:underline" onClick={() => setOpen(open === x.id ? null : x.id)}>{x.subject}</button>
                  {open === x.id && <pre className="mt-1 whitespace-pre-wrap break-words rounded-lg bg-slate-50 p-2 font-sans text-[12px]">{x.body}</pre>}
                </td>
                <td className={td}><Pill tone={x.state === 'gonderildi' ? 'ok' : x.state === 'hata' ? 'err' : x.state === 'bekliyor' ? 'violet' : 'muted'}>{x.stateLabel}</Pill>{x.error && <span className="block text-[11px] text-red-700">{x.error}</span>}</td>
              </tr>
            ))}
          </tbody>
        </TableWrap>
      )}
    </Block>
  );
}
