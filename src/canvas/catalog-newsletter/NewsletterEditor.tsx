import { useEffect, useState } from 'react';
import { FileDrop } from '../components/FileDrop';
import { useNavigate, useParams } from 'react-router-dom';
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { ArrowDown, ArrowUp, Download, Plus, Sparkles, Trash2 } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import { Loading, Note, Pill, TableWrap, btnGhost, btnPrimary, errText, field, label as labelCls, td, th } from '../admin/ui';
import { Pager } from '../editorial/kit';
import { AskSheet } from '../budget/parts';
import {
  DROP_REASON, EMPTY_SEGMENT, STATUS_TONE, cnApi, fmtDay, fmtInt, fmtMoney, fmtPct, fmtStamp,
  type Job, type Newsletter, type Segment,
} from './api';
import { Block, CnFrame } from './parts';
import SegmentBuilder from './SegmentBuilder';
import SqlInfo from '../components/SqlInfo';

type ItemEdit = { crmKitapId: string; gerekce?: string; metin?: string | null };
const SOURCE: Record<string, string> = { crm: 'CRM kampanyası', dosya: 'Araç dosyası', elle: 'Elle' };

/** E-bülten: segment (yalnız sayı), kitaplar, Zeki AI gövde ve konu satırı, onay, gönderime hazır HTML, sonuç. */
export default function NewsletterEditor() {
  const { id = '' } = useParams();
  const nav = useNavigate();
  const qc = useQueryClient();
  const meta = useQuery({ queryKey: ['cn', 'meta'], queryFn: cnApi.meta, enabled: ENGINE_ENABLED, staleTime: 60_000 });
  const nlq = useQuery({ queryKey: ['cn', 'newsletter', id], queryFn: () => cnApi.newsletter(id), enabled: ENGINE_ENABLED && !!id });
  const [seg, setSeg] = useState<Segment>(EMPTY_SEGMENT);
  const [ask, setAsk] = useState<null | 'reject' | 'delete'>(null);
  const [job, setJob] = useState<Job | null>(null);
  const [intro, setIntro] = useState('');
  const [head, setHead] = useState({ baslik: '', ozelGun: '', planlanan: '' });
  const d = nlq.data;
  const m = meta.data;
  useEffect(() => {
    if (!d) return;
    setSeg(d.segment);
    setIntro(d.giris ?? '');
    setHead({ baslik: d.baslik, ozelGun: d.ozelGun ?? '', planlanan: d.planlanan ?? '' });
  }, [d?.guncelleme]); // eslint-disable-line react-hooks/exhaustive-deps
  const editable = !!(d && m?.me.canNewsletter && d.durum === 'taslak');
  const put = (x: Newsletter) => qc.setQueryData(['cn', 'newsletter', id], x);
  const segDirty = !!d && JSON.stringify(seg) !== JSON.stringify(d.segment);

  const update = useMutation({
    mutationFn: (b: Parameters<typeof cnApi.updateNewsletter>[1]) => cnApi.updateNewsletter(id, b),
    onSuccess: (x) => { put(x); qc.invalidateQueries({ queryKey: ['cn', 'newsletters'] }); },
    onError: (e) => toast.error(errText(e, 'Kaydedilemedi.') ?? ''),
  });
  const items = useMutation({
    mutationFn: (list: ItemEdit[]) => cnApi.setNlItems(id, list),
    onSuccess: (x) => { put(x); qc.invalidateQueries({ queryKey: ['cn', 'nl-suggest', id] }); },
    onError: (e) => toast.error(errText(e, 'Liste kaydedilemedi.') ?? ''),
  });
  const action = useMutation({
    mutationFn: ({ act, note }: { act: string; note?: string }) => cnApi.nlAction(id, act, note),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['cn'] }); toast.success('Bülten güncellendi.'); setAsk(null); },
    onError: (e) => toast.error(errText(e, 'İşlem yapılamadı.') ?? ''),
  });
  const remove = useMutation({
    mutationFn: () => cnApi.deleteNewsletter(id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['cn'] }); nav('/katalog-bulten?sekme=bulten'); },
    onError: (e) => toast.error(errText(e, 'Silinemedi.') ?? ''),
  });
  const draft = useMutation({
    mutationFn: () => cnApi.draft(id),
    onSuccess: (j) => { setJob(j); toast.success('Zeki AI taslağı yazıyor.'); },
    onError: (e) => toast.error(errText(e, 'Taslak başlatılamadı.') ?? ''),
  });
  const jobQ = useQuery({
    queryKey: ['cn', 'job', job?.id],
    queryFn: () => cnApi.job(job!.id),
    enabled: !!job && (job.durum === 'bekliyor' || job.durum === 'calisiyor'),
    refetchInterval: 3000,
  });
  useEffect(() => {
    const j = jobQ.data;
    if (!j || (j.durum === job?.durum && j.adim === job?.adim)) return;
    setJob(j);
    if (j.durum === 'bitti') {
      qc.invalidateQueries({ queryKey: ['cn', 'newsletter', id] });
      toast.success(`Taslak hazır: ${j.sonuc?.konu ?? 0} konu satırı; denetimde düşen cümle ${j.sonuc?.dusen ?? 0}.`);
    } else if (j.durum === 'hata') toast.error(j.hata ?? 'Taslak yazılamadı.');
  }, [jobQ.data]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!ENGINE_ENABLED) return <CnFrame crumb="Bülten" title="Bülten" source="—" presence="—"><Note tone="warn">Veri bağlantısı kurulu değil; bu ekran şu an veri gösteremez. Sistem yöneticinize haber verin.</Note></CnFrame>;
  const list = d?.kitaplar ?? [];
  const edits: ItemEdit[] = list.map((k) => ({ crmKitapId: k.crmKitapId }));
  const move = (i: number, dir: -1 | 1) => {
    const next = [...edits];
    const j = i + dir;
    if (j < 0 || j >= next.length) return;
    [next[i], next[j]] = [next[j], next[i]];
    items.mutate(next);
  };
  const running = !!job && (job.durum === 'bekliyor' || job.durum === 'calisiyor');
  const sent = d && ['onayli', 'gonderildi', 'arsiv'].includes(d.durum);

  return (
    <CnFrame
      crumb="Bülten"
      title={d?.baslik ?? 'Bülten'}
      lead={d ? `Bültenin kitaplarını seçin, giriş metnini ve konu satırını yazın, onaylatın; onaylı bülten dosyasını şirketin e-posta aracına yüklersiniz. ${d.planlanan ? `Planlanan gönderim ${fmtDay(d.planlanan)}` : 'Gönderim tarihi girilmedi'}${d.konu ? ` · «${d.konu}»` : ''}` : undefined}
      source="CRM + Logo"
      presence={d?.segmentBuyuklugu !== null && d?.segmentBuyuklugu !== undefined ? `${fmtInt(d.segmentBuyuklugu)} izinli okur` : 'segment sayılmadı'}
      back={{ to: '/katalog-bulten?sekme=bulten', label: 'Bültenler' }}
      aside={d && m ? (
        <div className="flex flex-col gap-2">
          <div className="flex flex-wrap items-center justify-end gap-2">
            <Pill tone={STATUS_TONE[d.durum] ?? 'muted'}>{d.durumAdi}</Pill>
            {d.onaylayan && <span className="text-[11.5px] text-canvas-muted">onaylayan {d.onaylayan}</span>}
          </div>
          <div className="flex flex-wrap justify-end gap-2">
            {m.me.canNewsletter && d.durum === 'taslak' && <button type="button" className={btnPrimary} disabled={action.isPending} onClick={() => action.mutate({ act: 'submit' })}>Onaya gönder</button>}
            {m.me.canNewsletter && d.durum === 'onayda' && <button type="button" className={btnGhost} onClick={() => action.mutate({ act: 'withdraw' })}>Geri çek</button>}
            {m.me.canApprove && d.durum === 'onayda' && d.gonderen !== m.me.username && (
              <>
                <button type="button" className={btnPrimary} onClick={() => action.mutate({ act: 'approve' })}>Onayla</button>
                <button type="button" className={btnGhost} onClick={() => setAsk('reject')}>Geri gönder</button>
              </>
            )}
            {m.me.canExport && sent && d.html && <a className={btnPrimary} href={cnApi.htmlUrl(id)}><Download aria-hidden className="h-4 w-4" />Gönderime hazır HTML</a>}
            {m.me.canNewsletter && d.durum === 'onayli' && <button type="button" className={btnGhost} onClick={() => action.mutate({ act: 'mark-sent' })}>Gönderildi işaretle</button>}
            {m.me.canNewsletter && ['onayli', 'arsiv'].includes(d.durum) && <button type="button" className={btnGhost} onClick={() => action.mutate({ act: 'reopen' })}>Taslağa geri al</button>}
            {m.me.canNewsletter && ['taslak', 'onayli', 'gonderildi'].includes(d.durum) && <button type="button" className={btnGhost} onClick={() => action.mutate({ act: 'archive' })}>Arşivle</button>}
            {m.me.canNewsletter && d.durum === 'taslak' && <button type="button" className={btnGhost} aria-label="Bülteni sil" onClick={() => setAsk('delete')}><Trash2 aria-hidden className="h-4 w-4" /></button>}
          </div>
        </div>
      ) : null}
    >
      {nlq.error && <Note tone="err">{errText(nlq.error, 'Bülten açılamadı.')}</Note>}
      {nlq.isLoading && <Loading />}
      {d && m && (
        <>
          {d.not && d.durum === 'taslak' && <Note tone="warn">Geri gönderme gerekçesi: {d.not}</Note>}
          <Note tone="info">Portal bu bülteni göndermez. Onaylanan bülten dosyası şirketin izin yönetimi olan e-posta aracına yüklenir; alıcı listesini araç kendi kaynağından alır.</Note>

          {editable && (
            <Block title="Bülten bilgisi">
              <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
                <label className="flex flex-col gap-1 sm:col-span-2"><span className={labelCls}>Bülten adı</span>
                  <input className={field} value={head.baslik} onChange={(e) => setHead({ ...head, baslik: e.target.value })} /></label>
                <label className="flex flex-col gap-1"><span className={labelCls}>Özel gün</span>
                  <select className={field} value={head.ozelGun} onChange={(e) => setHead({ ...head, ozelGun: e.target.value })}>
                    <option value="">Yok</option>
                    {m.ozelGunler.map((x) => <option key={x.key} value={x.key}>{x.ad}{x.baslangic ? ` · ${fmtDay(x.baslangic)}` : ''}</option>)}
                  </select></label>
                <label className="flex flex-col gap-1"><span className={labelCls}>Planlanan gönderim</span>
                  <input type="date" className={field} value={head.planlanan} onChange={(e) => setHead({ ...head, planlanan: e.target.value })} /></label>
              </div>
              <div className="mt-2 flex justify-end">
                <button type="button" className={btnPrimary} disabled={update.isPending || !head.baslik.trim()}
                  onClick={() => update.mutate({ baslik: head.baslik, ozelGun: head.ozelGun || null, planlanan: head.planlanan || null })}>Kaydet</button>
              </div>
            </Block>
          )}

          <Block title="Okur segmenti" help="Seçilen ilgi alanlarından biri olan, izin kuralını sağlayan kişi sayılır."
            action={editable && segDirty ? <button type="button" className={btnGhost} disabled={update.isPending} onClick={() => update.mutate({ segment: seg })}>Segmenti kaydet</button> : undefined}>
            <SegmentBuilder meta={m} value={seg} editable={editable} newsletterId={id}
              stored={{ size: d.segmentBuyuklugu, at: d.segmentZamani }} k={d.kaynaklar} onChange={setSeg}
              beforeCount={editable && segDirty ? async () => { put(await cnApi.updateNewsletter(id, { segment: seg })); } : undefined}
              onCounted={() => qc.invalidateQueries({ queryKey: ['cn', 'newsletter', id] })} />
          </Block>

          <Block title="Bültendeki kitaplar" info={<SqlInfo k={d.kaynaklar} alan="kitaplar[]" label="Kitap fiyatı" />}
            action={editable && m.modelVar && list.length > 0 ? (
              <button type="button" className={btnPrimary} disabled={draft.isPending || running} onClick={() => draft.mutate()}>
                <Sparkles aria-hidden className="h-4 w-4" />
                {running ? (job?.adim ?? 'Zeki AI yazıyor…') : d.giris ? 'Zeki AI: taslağı yeniden yaz' : 'Zeki AI: taslak yaz'}
              </button>
            ) : undefined}>
            {list.length === 0 && <p className="py-3 text-[12.5px] text-canvas-muted">Henüz kitap yok; aşağıdaki önerilerden ekleyin.</p>}
            <ol className="flex flex-col gap-2">
              {list.map((k, i) => (
                <NlItem key={k.crmKitapId} k={k} i={i} n={list.length} editable={editable} busy={items.isPending}
                  onMove={move} onRemove={() => items.mutate(edits.filter((_, x) => x !== i))}
                  onText={(t) => items.mutate(edits.map((e, x) => (x === i ? { ...e, metin: t } : e)))} />
              ))}
            </ol>
          </Block>

          {editable && <NlSuggest id={id} busy={items.isPending} onAdd={(add) => items.mutate([...edits, ...add])} />}

          <Block title="Giriş ve konu satırı" help="Zeki AI yalnız kitapların CRM tanıtım metinlerini kullanır; kaynaksız rakam, alıntı ya da üstünlük iddiası içeren cümle düşer.">
            {d.konular.length > 0 ? (
              <fieldset disabled={!editable} className="flex flex-col gap-1">
                <legend className={labelCls}>Konu satırı</legend>
                {d.konular.map((s) => (
                  <label key={s} className="inline-flex min-h-9 items-start gap-2 text-[13px]">
                    <input type="radio" name="konu" className="mt-1 h-4 w-4" checked={d.konu === s} onChange={() => update.mutate({ konu: s })} />
                    <span className="break-words">{s}</span>
                  </label>
                ))}
              </fieldset>
            ) : (
              <p className="text-[12px] text-canvas-muted">Konu satırı seçenekleri Zeki AI taslağıyla gelir{editable ? '; elle de yazabilirsiniz.' : '.'}</p>
            )}
            {editable && (
              <label className="mt-2 flex flex-col gap-1"><span className={labelCls}>Konu satırı (elle)</span>
                <input className={field} defaultValue={d.konu ?? ''} key={d.konu ?? ''} maxLength={300}
                  onBlur={(e) => e.target.value.trim() && e.target.value !== (d.konu ?? '') && update.mutate({ konu: e.target.value.trim() })} /></label>
            )}
            <label className="mt-2 flex flex-col gap-1"><span className={labelCls}>Giriş paragrafı</span>
              {editable ? (
                <textarea className={`${field} min-h-[110px]`} value={intro} onChange={(e) => setIntro(e.target.value)}
                  onBlur={() => intro !== (d.giris ?? '') && update.mutate({ giris: intro })} />
              ) : <p className="whitespace-pre-wrap text-[12.5px] leading-snug">{d.giris ?? '—'}</p>}
            </label>
            {d.dusen.length > 0 && (
              <details className="mt-2 text-[11.5px]">
                <summary className="inline-flex min-h-8 cursor-pointer items-center font-bold text-canvas-violet">Denetimde düşen {d.dusen.length} cümle</summary>
                <ul className="mt-1 flex flex-col gap-1">
                  {d.dusen.map((x, i) => <li key={i} className="rounded-lg bg-slate-50 px-2 py-1"><b>{DROP_REASON[x.neden] ?? x.neden}</b>{x.yer ? ` · ${x.yer}` : ''}: {x.cumle}</li>)}
                </ul>
              </details>
            )}
          </Block>

          {d.html && (
            <Block title="Önizleme" help="E-posta aracına yüklenecek bültenin görünümü. Abonelikten çıkma bağlantısını e-posta aracı kendisi ekler.">
              <iframe title="Bülten önizlemesi" sandbox="" srcDoc={d.html} className="h-[560px] w-full rounded-xl border border-slate-100 bg-white" />
            </Block>
          )}

          {sent && <Results d={d} canEdit={!!m.me.canNewsletter} />}
        </>
      )}
      <AskSheet open={ask === 'reject'} title="Geri gönder" message="Bülten hazırlayana gerekçeyle geri gider." confirm="Geri gönder" input="Gerekçe" required
        busy={action.isPending} onClose={() => setAsk(null)} onConfirm={(t) => action.mutate({ act: 'reject', note: t })} />
      <AskSheet open={ask === 'delete'} title="Bülteni sil" message="Taslak bülten silinir. Bu işlem geri alınamaz." confirm="Sil" danger busy={remove.isPending}
        onClose={() => setAsk(null)} onConfirm={() => remove.mutate()} />
    </CnFrame>
  );
}

function NlItem({ k, i, n, editable, busy, onMove, onRemove, onText }: {
  k: Newsletter['kitaplar'][number]; i: number; n: number; editable: boolean; busy: boolean;
  onMove: (i: number, d: -1 | 1) => void; onRemove: () => void; onText: (t: string | null) => void;
}) {
  const [text, setText] = useState(k.metin ?? '');
  useEffect(() => setText(k.metin ?? ''), [k.metin]);
  return (
    <li className={`rounded-2xl border bg-white/80 p-3 ${k.satistanKalkti || k.havuzdaYok ? 'border-red-200' : 'border-slate-100'}`}>
      <div className="flex flex-col gap-2 sm:flex-row sm:items-start">
        <div className="flex shrink-0 items-center gap-1 sm:flex-col">
          <span className="w-8 text-center font-mono text-[13px] font-bold tabular-nums">{k.sira}</span>
          {editable && (
            <>
              <button type="button" aria-label="Yukarı taşı" disabled={busy || i === 0} onClick={() => onMove(i, -1)}
                className="grid h-9 w-9 place-items-center rounded-lg bg-slate-100 transition-transform duration-150 ease-out active:scale-[0.97] disabled:opacity-40"><ArrowUp aria-hidden className="h-4 w-4" /></button>
              <button type="button" aria-label="Aşağı taşı" disabled={busy || i === n - 1} onClick={() => onMove(i, 1)}
                className="grid h-9 w-9 place-items-center rounded-lg bg-slate-100 transition-transform duration-150 ease-out active:scale-[0.97] disabled:opacity-40"><ArrowDown aria-hidden className="h-4 w-4" /></button>
            </>
          )}
        </div>
        <div className="min-w-0 flex-1">
          <div className="break-words text-[14px] font-extrabold">{k.ad ?? k.stokKodu} <span className="text-[12px] font-normal text-canvas-muted">{k.yazar}</span></div>
          <div className="mt-0.5 font-mono text-[12px] tabular-nums">{fmtMoney(k.fiyat)}{k.webUrl ? '' : ' · web sayfası bulunamadı'}</div>
          {k.satistanKalkti && <Note tone="err">Kitap satıştan kalkmış görünüyor; bültenden çıkarın.</Note>}
          {k.havuzdaYok && <Note tone="err">Kitap CRM'de etkin kart olarak bulunamadı.</Note>}
          {k.gerekce && <p className="mt-1 text-[11.5px] text-canvas-muted">Neden: {k.gerekce}</p>}
          {editable ? (
            <textarea className={`${field} mt-1.5 min-h-[72px]`} value={text} placeholder="Kitap tanıtımı (Zeki AI taslağıyla dolar ya da elle yazılır)"
              onChange={(e) => setText(e.target.value)} onBlur={() => text !== (k.metin ?? '') && onText(text || null)} />
          ) : <p className="mt-1 whitespace-pre-wrap text-[12.5px] leading-snug">{k.metin ?? '—'}</p>}
        </div>
        {editable && <button type="button" className={btnGhost} disabled={busy} onClick={onRemove}><Trash2 aria-hidden className="h-4 w-4" />Çıkar</button>}
      </div>
    </li>
  );
}

function NlSuggest({ id, busy, onAdd }: { id: string; busy: boolean; onAdd: (add: ItemEdit[]) => void }) {
  const [on, setOn] = useState(false);
  const [page, setPage] = useState(0);
  const q = useQuery({ queryKey: ['cn', 'nl-suggest', id, page], queryFn: () => cnApi.suggestNl(id, page), enabled: on, placeholderData: keepPreviousData });
  const d = q.data;
  return (
    <Block title="Segment için önerilen kitaplar" info={<SqlInfo k={d?.kaynaklar} alan="items[]" label="Aday puanı, ilgi eşleşmesi ve fiyat" />} help="Segmentin ilgi alanı kitabın tür ve kategori metninde aranır; satış hızı, stok, yenilik ve özel gün bağı puana eklenir."
      action={!on ? <button type="button" className={btnPrimary} onClick={() => setOn(true)}>Önerileri getir</button> : undefined}>
      {q.error && <Note tone="err">{errText(q.error, 'Öneri listesi hazırlanamadı.')}</Note>}
      {on && q.isLoading && <Loading />}
      {d && (
        <>
          <div className="mb-2 flex flex-wrap gap-2 text-[12px] text-canvas-muted">
            <span className="font-mono tabular-nums">{fmtInt(d.total)} aday</span>
            {d.ilgiEslesen !== null && d.ilgiEslesen !== undefined && <span>· ilgi alanıyla eşleşen {fmtInt(d.ilgiEslesen)}</span>}
            {Object.entries(d.elenen).map(([k, v]) => <span key={k}>· {fmtInt(v)} {k} (önerilmedi)</span>)}
          </div>
          <ul className="flex flex-col gap-1.5">
            {d.items.map((x) => (
              <li key={x.id} className="flex flex-col gap-1.5 rounded-xl border border-slate-100 bg-white/80 p-2.5 sm:flex-row sm:items-center">
                <span className="w-12 shrink-0 font-mono text-[13px] font-bold tabular-nums text-canvas-violet">{x.puan.toLocaleString('tr-TR')}</span>
                <div className="min-w-0 flex-1">
                  <div className="break-words text-[13px] font-bold">{x.ad} <span className="font-normal text-canvas-muted">{x.yazar}</span></div>
                  <div className="text-[11.5px] leading-snug text-canvas-muted">{x.gerekce || '—'}</div>
                </div>
                <button type="button" className={btnGhost} disabled={busy} onClick={() => onAdd([{ crmKitapId: x.id, gerekce: x.gerekce }])}>
                  <Plus aria-hidden className="h-4 w-4" />Ekle
                </button>
              </li>
            ))}
          </ul>
          <Pager page={page} pageSize={d.pageSize} total={d.total} shown={d.items.length} loading={q.isLoading} fetching={q.isFetching} onPage={setPage} />
        </>
      )}
    </Block>
  );
}

function Results({ d, canEdit }: { d: Newsletter; canEdit: boolean }) {
  const qc = useQueryClient();
  const [crm, setCrm] = useState(d.crmKampanya ?? '');
  const [day, setDay] = useState(d.gonderimTarihi ?? '');
  const [n, setN] = useState({ sent: '', opened: '', clicked: '', unsubscribed: '', bounced: '' });
  const done = () => qc.invalidateQueries({ queryKey: ['cn', 'newsletter', d.id] });
  const link = useMutation({
    mutationFn: () => cnApi.updateNewsletter(d.id, { crmKampanya: crm.trim(), gonderimTarihi: day }),
    onSuccess: () => { done(); toast.success('Gönderim bilgisi kaydedildi.'); },
    onError: (e) => toast.error(errText(e, 'Kaydedilemedi.') ?? ''),
  });
  const add = useMutation({
    mutationFn: (b: Parameters<typeof cnApi.addResult>[1]) => cnApi.addResult(d.id, b),
    onSuccess: () => { done(); toast.success('Sonuç eklendi.'); },
    onError: (e) => toast.error(errText(e, 'Sonuç eklenemedi.') ?? ''),
  });
  const del = useMutation({ mutationFn: (rid: string) => cnApi.deleteResult(d.id, rid), onSuccess: done });
  const toNum = (v: string) => (v.trim() === '' ? null : Number(v.replace(/\./g, '')));
  return (
    <Block title="Gönderim ve sonuç" info={<SqlInfo k={d.kaynaklar} alan="sonuclar[]" label="Gönderim sonuçları" />} help="Sonuç e-posta aracının dışa aktarım dosyasından (yalnız toplamlar alınır; kişi satırlı dosyada satırlar sayılır, adresler okunmaz ve saklanmaz), bağlı CRM kampanyasından ya da elle girilir.">
      {/* Araç dosyası yükleme yetkisizde de görünür (kilitli, gereken yetki yazılı). */}
      <div className="mb-2">
        <FileDrop
          size="sm"
          title="E-posta aracının sonuç dosyasını yükle (CSV)"
          accept=".csv,.txt,text/csv"
          feature="bulten.duzenle"
          allowed={canEdit}
          busy={add.isPending}
          onPick={(f) => void f.text().then((dosya) => add.mutate({ kaynak: 'dosya', dosya }))}
        />
      </div>
      {canEdit && (
        <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
          <label className="flex flex-col gap-1 sm:col-span-2"><span className={labelCls}>CRM kampanya kimliği (isteğe bağlı)</span>
            <input className={field} value={crm} placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx" onChange={(e) => setCrm(e.target.value)} /></label>
          <label className="flex flex-col gap-1"><span className={labelCls}>Gönderim tarihi</span>
            <input type="date" className={field} value={day} onChange={(e) => setDay(e.target.value)} /></label>
          <div className="flex items-end gap-2">
            <button type="button" className={btnGhost} disabled={link.isPending} onClick={() => link.mutate()}>Kaydet</button>
            <button type="button" className={btnGhost} disabled={add.isPending || !d.crmKampanya} onClick={() => add.mutate({ kaynak: 'crm' })}>CRM'den oku</button>
          </div>
          <div className="grid grid-cols-2 gap-2 sm:col-span-2 lg:col-span-4 lg:grid-cols-6">
            {([['sent', 'Gönderilen'], ['opened', 'Açılan'], ['clicked', 'Tıklanan'], ['unsubscribed', 'Abonelikten çıkan'], ['bounced', 'Geri dönen']] as const).map(([k, l]) => (
              <label key={k} className="flex flex-col gap-1"><span className={labelCls}>{l}</span>
                <input className={field} inputMode="numeric" value={n[k]} onChange={(e) => setN({ ...n, [k]: e.target.value })} /></label>
            ))}
            <div className="flex items-end">
              <button type="button" className={btnPrimary} disabled={add.isPending || !n.sent.trim()}
                onClick={() => add.mutate({ kaynak: 'elle', sayilar: Object.fromEntries(Object.entries(n).map(([k, v]) => [k, toNum(v)])) })}>Elle ekle</button>
            </div>
          </div>
        </div>
      )}
      {d.sonuclar.length > 0 && (
        <div className="mt-3">
          <TableWrap>
            <thead><tr>
              <th className={th}>Zaman</th><th className={th}>Kaynak</th><th className={`${th} text-right`}>Gönderilen</th>
              <th className={`${th} text-right`}>Açılma</th><th className={`${th} text-right`}>Tıklama</th><th className={`${th} text-right`}>Abonelikten çıkan</th><th className={th} />
            </tr></thead>
            <tbody>
              {d.sonuclar.map((r) => (
                <tr key={r.id} className="border-t border-slate-100">
                  <td className={td}>{fmtStamp(r.zaman)}<div className="text-[11px] text-canvas-muted">{r.not}</div></td>
                  <td className={td}>{SOURCE[r.kaynak]}</td>
                  <td className={`${td} text-right font-mono tabular-nums`}>{fmtInt(r.gonderilen)}</td>
                  <td className={`${td} text-right font-mono tabular-nums`}>{fmtInt(r.acilan)} · {fmtPct(r.acilmaOrani)}</td>
                  <td className={`${td} text-right font-mono tabular-nums`}>{fmtInt(r.tiklanan)} · {fmtPct(r.tiklamaOrani)}</td>
                  <td className={`${td} text-right font-mono tabular-nums`}>{fmtInt(r.abonelikIptal)}</td>
                  <td className={td}>{canEdit && <button type="button" className={btnGhost} aria-label="Sonucu sil" onClick={() => del.mutate(r.id)}><Trash2 aria-hidden className="h-4 w-4" /></button>}</td>
                </tr>
              ))}
            </tbody>
          </TableWrap>
        </div>
      )}
    </Block>
  );
}
