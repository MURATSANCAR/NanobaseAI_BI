import { useEffect, useState } from 'react';
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { AlertTriangle, FileText, Loader2, Plus, RefreshCw, Sparkles } from 'lucide-react';
import { ENGINE_ENABLED } from '../../engine';
import { Loading, Note, Pill, btnGhost, btnPrimary, errText, field, label as labelCls } from '../../admin/ui';
import { Kpi, KpiRow } from '../../editorial/kit';
import Sheet from '../../editorial/studio/reader/Sheet';
import { AskSheet, Tabs } from '../../budget/parts';
import { STATUS_TONE, fmtDay, fmtMoney, fmtPct, fmtStamp, parseNum } from '../api';
import { Block, MarketingFrame } from '../parts';
import SqlInfo from '../../components/SqlInfo';
import { isMonth, monthApi, monthLabel, type MonthItem, type MonthView } from './api';
import BudgetPanel from './BudgetPanel';
import CalendarGrid from './CalendarGrid';
import FoyTable from './FoyTable';
import MonthNav from './MonthNav';
import TargetGapsPanel from './TargetGapsPanel';

/** M18 Aylık pazarlama planı: önceki ay şeridi, takvim (hafta × kanal, çakışmalar), bütçe ve öncelik, föyler.
 *  Adres /pazarlama/aylik-plan/:ay?sekme=takvim|butce|foy|ozet. */

const TABS = [
  { key: 'takvim', label: 'Takvim' },
  { key: 'butce', label: 'Bütçe ve öncelik' },
  { key: 'foy', label: 'Föyler' },
  { key: 'ozet', label: 'Özet' },
] as const;
type Tab = (typeof TABS)[number]['key'];
type Ask = null | 'submit' | 'withdraw' | 'approve' | 'upper-approve' | 'reject' | 'revise';

export default function MonthScreen() {
  const { ay: routeAy } = useParams();
  const nav = useNavigate();
  const qc = useQueryClient();
  const [params, setParams] = useSearchParams();
  const tab: Tab = (TABS.find((t) => t.key === params.get('sekme'))?.key ?? 'takvim') as Tab;
  const [pick, setPick] = useState<MonthItem | null>(null);
  const [adding, setAdding] = useState(false);
  const [ask, setAsk] = useState<Ask>(null);

  const meta = useQuery({ queryKey: ['mkt', 'meta'], queryFn: monthApi.meta, enabled: ENGINE_ENABLED, staleTime: 60_000 });
  const ay = isMonth(routeAy) ? routeAy : meta.data?.monthly?.varsayilanDonem;
  const month = useQuery({ queryKey: ['mkt', 'month', ay], queryFn: () => monthApi.month(ay as string), enabled: ENGINE_ENABLED && !!ay });
  const foys = useQuery({ queryKey: ['mkt', 'foy', ay, ''], queryFn: () => monthApi.foyList(ay as string), enabled: ENGINE_ENABLED && !!ay && tab === 'foy' });
  const setView = (v: MonthView) => qc.setQueryData(['mkt', 'month', ay], v);
  const go = (a: string) => nav(`/pazarlama/aylik-plan/${a}${tab !== 'takvim' ? `?sekme=${tab}` : ''}`);

  const build = useMutation({
    mutationFn: () => monthApi.build(ay as string),
    onSuccess: (v) => { setView(v); toast.success('Taslak kaynaklardan kuruldu; elle düzeltilenler korundu.'); },
    onError: (e) => toast.error(errText(e, 'Taslak kurulamadı.') ?? ''),
  });
  const suggest = useMutation({
    mutationFn: () => monthApi.suggest(ay as string),
    onSuccess: (v) => { setView(v); if (v.uyari) toast.warning(v.uyari); else toast.success('Bütçe önerisi ve Zeki AI gerekçesi hazır.'); },
    onError: (e) => toast.error(errText(e, 'Öneri alınamadı.') ?? ''),
  });
  const act = useMutation({
    mutationFn: ({ kind, text }: { kind: Exclude<Ask, null>; text: string }) => monthApi.flow(ay as string, kind, text),
    onSuccess: (_r, { kind }) => {
      setAsk(null);
      qc.invalidateQueries({ queryKey: ['mkt', 'month', ay] });
      toast.success({ submit: 'Plan onaya gönderildi.', withdraw: 'Plan taslağa geri alındı.', approve: 'Onay kaydedildi.', 'upper-approve': 'Üst onay kaydedildi.', reject: 'Plan gerekçesiyle geri gönderildi.', revise: 'Revizyon taslağı açıldı.' }[kind]);
    },
    onError: (e) => toast.error(errText(e, 'İşlem yapılamadı.') ?? ''),
  });

  const m = meta.data;
  const me = m?.me;
  const v = month.data;
  const p = v?.plan ?? null;
  const editable = !!p && (p.durum === 'taslak' || p.durum === 'geri') && !!me?.canWrite;
  const mine = !!p && (p.gonderen ?? '').toLowerCase() === (me?.username ?? '').toLowerCase();
  const o = v?.oncekiAy;

  const aside = ay ? (
    <div className="flex flex-col gap-2">
      <MonthNav value={ay} onChange={go} />
      <div className="flex flex-wrap gap-2 lg:justify-end">
        {me?.canWrite && (!p || editable) && (
          <button type="button" className={p ? btnGhost : btnPrimary} onClick={() => build.mutate()} disabled={build.isPending}>
            {build.isPending ? <Loader2 aria-hidden className="h-4 w-4 animate-spin" /> : <RefreshCw aria-hidden className="h-4 w-4" />}
            {p ? 'Kaynaklardan yeniden kur' : 'Taslağı kur'}
          </button>
        )}
        {me?.canExport && p && <a className={btnGhost} href={monthApi.summaryUrl(ay)} download><FileText aria-hidden className="h-4 w-4" />Özet PDF indir</a>}
      </div>
    </div>
  ) : null;

  return (
    <MarketingFrame
      crumb="Aylık plan"
      title={ay ? `${monthLabel(ay)} pazarlama planı` : 'Aylık pazarlama planı'}
      lead="Ayın yeni kitap çıkışları, eski kitap (backlist) işleri, özel günler ve bayi kampanyaları tek takvimde; çakışmalar işaretli. Bütçe önerilir, pazarlama müdürü düzeltip onaylar. Dışarıya hiçbir şey kendiliğinden gönderilmez."
      source={p ? `${p.id} · sürüm ${p.surum}` : 'CRM + Logo + bütçe planı'}
      presence={p ? p.durumAdi : v ? 'plan yok' : '…'}
      aside={aside}
    >
      {!ENGINE_ENABLED && <Note tone="warn">Veri bağlantısı kurulu değil; bu ekran şu an veri gösteremez. Sistem yöneticinize haber verin.</Note>}
      {month.error && <Note tone="err">{errText(month.error, 'Ay planı açılamadı.')}</Note>}
      {(month.isLoading || (!ay && meta.isLoading)) && <Loading />}

      {v && m && me && (
        <>
          {o && (
            <KpiRow>
              <Kpi label={`${o.donemAdi} hedefe oran`} value={fmtPct(o.oran)}
                help={o.not ?? (me.canSeeBudget ? `${fmtMoney(o.gercek)} / ${fmtMoney(o.hedef)} (hedefli kitaplar)` : 'Hedefli kitapların net cirosu ÷ ay hedefi')}
                info={<SqlInfo k={v.kaynaklar} alan="oncekiAy" label={`${o.donemAdi} hedefe oran`} />}
                explain="Önceki ay, satış hedefi olan kitapların Logo'daki net cirosunun o ayın hedefine oranı. %100'ün altı hedefin gerisinde kalındığını gösterir; açık bu ayın bütçe önerisine yansır." />
              <Kpi label="Önceki ay işleri" value={o.isler.toplam ? `${o.isler.yapildi} / ${o.isler.toplam}` : '—'}
                help={o.isler.toplam ? `Onaylı planların işleri; ${o.isler.atlandi} atlandı` : 'Önceki ay için onaylı plan işi yok'}
                info={<SqlInfo k={v.kaynaklar} alan="oncekiAy.isler" label="Önceki ay işleri" />}
                explain="Önceki ayın onaylı pazarlama planlarındaki işlerden kaçının «yapıldı» işaretlendiği. Atlanan işler ayrıca yazılır." />
              <Kpi label="Çakışma" value={String(v.cakismaSayisi)} help="Aynı hafta aynı kitaplıkta lansman ya da üst üste kampanya"
                active={tab === 'takvim' && v.cakismaSayisi > 0} onClick={() => setParams({ sekme: 'takvim' }, { replace: true })}
                info={<SqlInfo k={v.kaynaklar} alan="cakismaSayisi" label="Çakışma" />}
                explain="Aynı haftada aynı kitaplıktan birden çok yeni kitap çıkışı ya da aynı kanalda tarihleri örtüşen kampanyalar. Takvimde kırmızıyla işaretlenir; birini kaydırmayı düşünün." />
              <Kpi label="Föy" value={`${v.foy.onayli} / ${v.foy.toplam}`} help={v.foy.eksik || v.foy.uyumsuz ? `${v.foy.eksik} eksik, ${v.foy.uyumsuz} uyumsuz` : 'Onaylı föy / ayın yeni kitabı'}
                active={tab === 'foy'} onClick={() => setParams({ sekme: 'foy' }, { replace: true })}
                info={<SqlInfo k={v.kaynaklar} alan="foy" label="Föy" />}
                explain="Föy, bayilere ve satış ekibine verilen tek sayfalık kitap tanıtımıdır. Kart, bu ay çıkan yeni kitaplardan kaçının föyünün onaylandığını; eksik alanlı ve CRM–Logo bilgisi uyuşmayan föy sayısını gösterir." />
            </KpiRow>
          )}

          {!p && (
            <Note tone="info">
              {monthLabel(v.donem)} için ay planı henüz yok. {me.canWrite ? '«Taslağı kur» CRM yayın tarihlerinden, onaylı yeni kitap ve backlist planlarından, özel günlerden ve CRM kampanyalarından taslağı kurar.' : `Taslak her ayın ${m.monthly?.draftDay ?? 15}'inde kendiliğinden kurulur.`}
            </Note>
          )}

          {p && (
            <div className="flex flex-wrap items-center gap-2 px-1">
              <Pill tone={STATUS_TONE[p.durum]}>{p.durumAdi}</Pill>
              {p.ustOnayGerekli && p.durum !== 'onayli' && <Pill tone="violet">Bütçe eşiğin üstünde: üst onay gerekir</Pill>}
              <span className="text-[12px] font-semibold text-canvas-muted">
                {p.gonderen && p.durum === 'onayda' && <>{p.gonderen} gönderdi ({fmtStamp(p.gonderme)}) · </>}
                {p.onaylayan && <>pazarlama onayı {p.onaylayan} · </>}
                {p.ustOnaylayan && <>üst onay {p.ustOnaylayan} · </>}
                güncelleme {fmtStamp(p.guncelleme)}
              </span>
              <div className="ml-auto flex flex-wrap gap-2">
                {editable && <button type="button" className={btnPrimary} onClick={() => setAsk('submit')}>Onaya gönder</button>}
                {p.durum === 'onayda' && me.canWrite && <button type="button" className={btnGhost} onClick={() => setAsk('withdraw')}>Onaydan çek</button>}
                {p.durum === 'onayda' && !mine && (me.canApprove || me.canUpperApprove) && <button type="button" className={btnGhost} onClick={() => setAsk('reject')}>Geri gönder</button>}
                {p.durum === 'onayda' && !mine && me.canApprove && !p.onaylayan && <button type="button" className={btnPrimary} onClick={() => setAsk('approve')}>Onayla</button>}
                {p.durum === 'onayda' && !mine && me.canUpperApprove && p.ustOnayGerekli && !p.ustOnaylayan && <button type="button" className={btnPrimary} onClick={() => setAsk('upper-approve')}>Üst onay ver</button>}
                {p.durum === 'onayli' && me.canWrite && <button type="button" className={btnGhost} onClick={() => setAsk('revise')}>Revize et</button>}
              </div>
            </div>
          )}
          {p?.durum === 'geri' && p.gerekce && <Note tone="warn">Geri gönderildi: {p.gerekce}</Note>}
          {p?.durum === 'onayda' && mine && (me.canApprove || me.canUpperApprove) && <Note tone="info">Bu planı siz onaya gönderdiniz; onayı başka bir yetkili verir.</Note>}
          {p?.zeki?.notlar?.map((n) => <Note key={n} tone="warn">{n}</Note>)}

          <Tabs tabs={TABS.map((t) => ({ ...t, badge: t.key === 'takvim' ? v.cakismaSayisi || null : t.key === 'foy' ? (v.foy.eksik + v.foy.uyumsuz) || null : null }))}
            value={tab} onChange={(k) => setParams({ sekme: k }, { replace: true })} />

          {tab === 'takvim' && (
            <Block
              title="Takvim"
              help="Kalemler kaynağından gelir (CRM yayın tarihi, onaylı yeni kitap ve backlist planları, CRM özel günleri ve kampanyaları). Karta dokununca ayrıntı; taslakta tarih ve kanal düzeltilir, düzeltme yeniden kurmada korunur."
              action={editable ? <button type="button" className={btnGhost} onClick={() => setAdding(true)}><Plus aria-hidden className="h-4 w-4" />Kalem ekle</button> : undefined}
            >
              <div className="mb-2 flex flex-wrap gap-2 text-[11.5px] font-semibold text-canvas-muted">
                {Object.entries(v.sayilar).filter(([, n]) => n > 0).map(([k, n]) => <span key={k}>{m.monthly?.types[k] ?? k}: {n}</span>)}
                <SqlInfo k={v.kaynaklar} alan="items[]" label="Takvim kalemleri ve sayıları" />
              </div>
              {p ? <CalendarGrid view={v} channels={m.channels} onPick={setPick} /> : <p className="text-[12.5px] text-canvas-muted">Takvim, bu ayın plan taslağı kurulunca dolar.</p>}
            </Block>
          )}

          {tab === 'butce' && (
            <>
              {p && me.canWrite && p.durum !== 'arsiv' && (
                <button type="button" className={`${btnPrimary} self-start`} onClick={() => suggest.mutate()} disabled={suggest.isPending}>
                  {suggest.isPending ? <Loader2 aria-hidden className="h-4 w-4 animate-spin" /> : <Sparkles aria-hidden className="h-4 w-4" />}
                  {editable ? 'Öneriyi yenile ve Zeki AI gerekçesi al' : 'Zeki AI gerekçesi al'}
                </button>
              )}
              {p ? <BudgetPanel view={v} editable={editable && me.canSeeBudget} canSeeBudget={me.canSeeBudget} onSaved={setView} /> : <Note tone="info">Önce taslağı kurun.</Note>}
              <TargetGapsPanel ay={v.donem} canSeeBudget={me.canSeeBudget} />
            </>
          )}

          {tab === 'foy' && (
            <Block title="Ayın föyleri" help="Yayın günü bu aya düşen yeni kitapların satış föyleri." action={<Link className={btnGhost} to={`/pazarlama/foy?ay=${v.donem}`}>Föy ekranına git</Link>}>
              {foys.error && <Note tone="err">{errText(foys.error, 'Föyler açılamadı.')}</Note>}
              {foys.isLoading && <Loading />}
              {foys.data && <FoyTable rows={foys.data.items} fields={m.monthly?.foyFields ?? {}} />}
            </Block>
          )}

          {tab === 'ozet' && (
            <div className="flex flex-col gap-3 lg:flex-row lg:items-start">
              <Block title="Genel müdür özeti" help="Zeki AI üç paragrafta özetler; rakamlar yalnız tablodan, denetimden geçmeyen cümle düşer.">
                {p?.zeki?.ozet ? <p className="whitespace-pre-line text-[12.5px] leading-snug">{p.zeki.ozet}</p>
                  : <p className="text-[12.5px] text-canvas-muted">Özet henüz yok. «Bütçe ve öncelik» sekmesinde Zeki AI gerekçesi alınınca özet de yazılır.</p>}
              </Block>
              <Block title="Zeki AI'a sor" help="Genel bakıştaki soru kutusu açılır.">
                <ul className="flex flex-col gap-1.5">
                  {[
                    `${monthLabel(v.donem)} ayında çıkan yeni kitapların hedef cirosu ayın toplam hedefinin yüzde kaçı?`,
                    `${monthLabel(v.donem)} planında aynı haftaya düşen çocuk kitabı lansmanları hangileri?`,
                    `${o?.donemAdi ?? 'Geçen ay'} hedefin %80 altında kalan kitaplar ve o kitaplar için bu ay planlanan işler?`,
                    'Bu ayın föylerinde fiyatı CRM ile uyuşmayan var mı?',
                    'Geçen ay planlanan sosyal medya işlerinin kaçı yapıldı?',
                  ].map((q) => (
                    <li key={q}>
                      <Link className="block min-h-11 rounded-xl bg-white/70 px-3 py-2 text-[12px] font-semibold leading-snug text-canvas-ink transition-colors duration-150 hover:bg-white" to={`/genel-bakis?soru=${encodeURIComponent(q)}`}>{q}</Link>
                    </li>
                  ))}
                </ul>
              </Block>
            </div>
          )}
        </>
      )}

      <ItemSheet item={pick} view={v} editable={editable} canSeeBudget={!!me?.canSeeBudget} canNewBooks={!!me?.canNewBooks}
        channels={m?.channels ?? {}} onClose={() => setPick(null)}
        onSaved={() => { setPick(null); qc.invalidateQueries({ queryKey: ['mkt', 'month', ay] }); }} />
      <AddSheet open={adding} ay={ay ?? ''} types={m?.monthly?.types ?? {}} channels={m?.channels ?? {}} onClose={() => setAdding(false)}
        onSaved={() => { setAdding(false); qc.invalidateQueries({ queryKey: ['mkt', 'month', ay] }); }} />
      <AskSheet
        open={ask !== null}
        busy={act.isPending}
        title={{ submit: 'Onaya gönder', withdraw: 'Onaydan çek', approve: 'Planı onayla', 'upper-approve': 'Üst onay', reject: 'Geri gönder', revise: 'Planı revize et', '': '' }[ask ?? '']}
        message={
          ask === 'submit' ? 'Ay planı onay bekleyenlere düşer; onayı sizden başka bir yetkili verir. Onayda iken kalemler ve bütçe değiştirilemez.'
            : ask === 'withdraw' ? 'Plan yeniden taslak olur.'
            : ask === 'approve' ? (p?.ustOnayGerekli ? 'Pazarlama onayınız kaydedilir; bütçe eşiğin üstünde olduğu için plan üst onaydan sonra onaylı olur.' : 'Plan onaylanır; içerik takvimi, saha ve B2B modülleri bu takvimi okur.')
            : ask === 'upper-approve' ? 'Bütçe üst onayınız kaydedilir.'
            : ask === 'reject' ? 'Plan gerekçenizle geri döner.'
            : 'Onaylı planın kopyası yeni taslak sürüm olarak açılır; yeni sürüm onaylanana kadar bu plan geçerli kalır.'
        }
        confirm={{ submit: 'Onaya gönder', withdraw: 'Taslağa al', approve: 'Onayla', 'upper-approve': 'Üst onay ver', reject: 'Geri gönder', revise: 'Revizyon aç', '': '' }[ask ?? '']}
        input={ask === 'reject' ? 'Gerekçe' : ask === 'revise' ? 'Revizyon gerekçesi' : ask === 'approve' || ask === 'upper-approve' ? 'Not (isteğe bağlı)' : undefined}
        required={ask === 'reject' || ask === 'revise'}
        onClose={() => setAsk(null)}
        onConfirm={(text) => ask && act.mutate({ kind: ask, text })}
      />
    </MarketingFrame>
  );
}

function ItemSheet({ item, view, editable, canSeeBudget, canNewBooks, channels, onClose, onSaved }: {
  item: MonthItem | null;
  view: MonthView | undefined;
  editable: boolean;
  canSeeBudget: boolean;
  canNewBooks: boolean;
  channels: Record<string, string>;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [f, setF] = useState({ baslangic: '', bitis: '', kanal: '', aciklama: '', butce: '' });
  useEffect(() => {
    if (item) setF({ baslangic: item.baslangic ?? '', bitis: item.bitis ?? '', kanal: item.kanal ?? '', aciklama: item.aciklama ?? '', butce: item.butce == null ? '' : String(item.butce) });
  }, [item]);
  const save = useMutation({
    mutationFn: () => monthApi.patchItem(view!.donem, item!.id, {
      baslangic: f.baslangic || null, bitis: f.bitis || null, kanal: f.kanal || null, aciklama: f.aciklama || null,
      ...(canSeeBudget ? { butce: parseNum(f.butce) } : {}),
    }),
    onSuccess: () => { toast.success('Kalem düzeltildi; yeniden kurmada korunur.'); onSaved(); },
    onError: (e) => toast.error(errText(e, 'Kaydedilemedi.') ?? ''),
  });
  const remove = useMutation({
    mutationFn: () => monthApi.removeItem(view!.donem, item!.id),
    onSuccess: () => { toast.success('Kalem silindi.'); onSaved(); },
    onError: (e) => toast.error(errText(e, 'Silinemedi.') ?? ''),
  });
  const d = item?.detay;
  return (
    <Sheet open={!!item} modal onClose={onClose} title={item?.baslik ?? ''} subtitle={item ? `${item.turAdi} · ${item.kaynakAdi}` : undefined}>
      {item && d && (
        <div className="flex flex-col gap-3 text-[12.5px]">
          {item.cakisma.map((c, i) => (
            <Note key={i} tone="err">
              <span className="inline-flex items-start gap-1.5"><AlertTriangle aria-hidden className="mt-0.5 h-3.5 w-3.5 shrink-0" />{c.neden}{c.deger ? ` (${c.deger})` : ''}: {c.ileAd.join(', ')}</span>
            </Note>
          ))}
          {d.kaynaktaYok && <Note tone="warn">Bu kalem artık kaynağında yok (elle düzeltildiği için korundu).</Note>}
          <dl className="grid grid-cols-[120px_1fr] gap-x-2 gap-y-1">
            <dt className="text-canvas-muted">Tarih</dt><dd>{fmtDay(item.baslangic)}{item.bitis && item.bitis !== item.baslangic ? ` – ${fmtDay(item.bitis)}` : ''}</dd>
            {item.stokKodu && <><dt className="text-canvas-muted">Stok kodu</dt><dd>{item.stokKodu}</dd></>}
            {d.yazar && <><dt className="text-canvas-muted">Yazar</dt><dd>{d.yazar}</dd></>}
            {item.kitaplik && <><dt className="text-canvas-muted">Kitaplık</dt><dd>{item.kitaplik}</dd></>}
            {item.hedefKitle && <><dt className="text-canvas-muted">Hedef kitle</dt><dd>{item.hedefKitle}</dd></>}
            {d.sorumlu && <><dt className="text-canvas-muted">Sorumlu</dt><dd>{d.sorumlu}</dd></>}
            {d.hedefAy && <><dt className="text-canvas-muted">Bu ayın hedefi</dt><dd>{Math.round(d.hedefAy.adet ?? 0).toLocaleString('tr-TR')} adet{canSeeBudget && d.hedefAy.ciro != null ? ` · ${fmtMoney(d.hedefAy.ciro)}` : ''} (bütçe planı)</dd></>}
            {d.crmBolgeHedefi && <><dt className="text-canvas-muted">CRM bölge hedefi</dt><dd>{Math.round(d.crmBolgeHedefi.adet).toLocaleString('tr-TR')} adet, {d.crmBolgeHedefi.bolge} bölge · yalnız bilgi için; hesaplara girmez</dd></>}
            {d.sapma && <><dt className="text-canvas-muted">Hedef sapması</dt><dd className="font-bold text-red-700">hedefe oran {fmtPct(d.sapma.oran)}</dd></>}
            {d.kitapSayisi != null && <><dt className="text-canvas-muted">Bağlı kitap</dt><dd>{d.kitapSayisi}</dd></>}
            {d.yontem && <><dt className="text-canvas-muted">Tarih yöntemi</dt><dd>{d.yontem}</dd></>}
            {d.mecra && <><dt className="text-canvas-muted">Mecra</dt><dd>{d.mecra}{d.tip ? ` · ${d.tip}` : ''}</dd></>}
            {d.ekIskonto != null && <><dt className="text-canvas-muted">Ek iskonto</dt><dd>%{d.ekIskonto}</dd></>}
            {canSeeBudget && d.planlananCiro != null && <><dt className="text-canvas-muted">Planlanan ciro</dt><dd>{fmtMoney(d.planlananCiro)}</dd></>}
            {d.urunSayisi != null && <><dt className="text-canvas-muted">Ürün</dt><dd>{d.urunSayisi}</dd></>}
          </dl>
          <p className="flex items-center gap-1 text-[11px] text-canvas-muted">Rakamların kaynağı<SqlInfo k={view?.kaynaklar} alan="items[]" label="Kalemin rakamları" /></p>
          <div className="flex flex-wrap gap-2">
            {d.plan && canNewBooks && <Link className={btnGhost} to={`/pazarlama/plan/${encodeURIComponent(d.plan.id)}`}>Planı aç ({d.plan.durumAdi})</Link>}
            {item.tur === 'yeni' && item.stokKodu && <Link className={btnGhost} to={`/pazarlama/foy/${encodeURIComponent(item.stokKodu)}?ay=${view?.donem ?? ''}`}>Föyü aç</Link>}
          </div>
          {editable && (
            <div className="flex flex-col gap-2 border-t border-slate-100 pt-3">
              <div className="grid grid-cols-2 gap-2">
                <label className="flex flex-col gap-1"><span className={labelCls}>Başlangıç</span><input type="date" className={field} value={f.baslangic} onChange={(e) => setF({ ...f, baslangic: e.target.value })} /></label>
                <label className="flex flex-col gap-1"><span className={labelCls}>Bitiş</span><input type="date" className={field} value={f.bitis} onChange={(e) => setF({ ...f, bitis: e.target.value })} /></label>
              </div>
              <label className="flex flex-col gap-1">
                <span className={labelCls}>Kanal</span>
                <select className={field} value={f.kanal} onChange={(e) => setF({ ...f, kanal: e.target.value })}>
                  <option value="">Kanal yok</option>
                  {Object.entries(channels).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
                </select>
              </label>
              {canSeeBudget && <label className="flex flex-col gap-1"><span className={labelCls}>Bütçe (TL)</span><input inputMode="decimal" className={`${field} font-mono`} value={f.butce} onChange={(e) => setF({ ...f, butce: e.target.value })} /></label>}
              <label className="flex flex-col gap-1"><span className={labelCls}>Not</span><textarea className={`${field} min-h-[72px]`} value={f.aciklama} onChange={(e) => setF({ ...f, aciklama: e.target.value })} /></label>
              <div className="flex flex-wrap justify-end gap-2">
                {item.kaynak === 'kullanici' && <button type="button" className={`${btnGhost} !text-red-700`} onClick={() => remove.mutate()} disabled={remove.isPending}>Kalemi sil</button>}
                <button type="button" className={btnPrimary} onClick={() => save.mutate()} disabled={save.isPending}>Kaydet</button>
              </div>
              {item.kaynak !== 'kullanici' && <p className="text-[11px] text-canvas-muted">Kaynaktan gelen kalem silinmez; yayın günü CRM'de ya da ilgili planda değişir.</p>}
            </div>
          )}
        </div>
      )}
    </Sheet>
  );
}

function AddSheet({ open, ay, types, channels, onClose, onSaved }: {
  open: boolean; ay: string; types: Record<string, string>; channels: Record<string, string>; onClose: () => void; onSaved: () => void;
}) {
  const empty = { tur: 'diger', baslik: '', baslangic: '', bitis: '', kanal: '' };
  const [f, setF] = useState(empty);
  const save = useMutation({
    mutationFn: () => monthApi.addItem(ay, { tur: f.tur, baslik: f.baslik, baslangic: f.baslangic, bitis: f.bitis || null, kanal: f.kanal || null }),
    onSuccess: () => { setF(empty); toast.success('Kalem eklendi.'); onSaved(); },
    onError: (e) => toast.error(errText(e, 'Eklenemedi.') ?? ''),
  });
  return (
    <Sheet open={open} modal onClose={onClose} title="Kalem ekle" subtitle={`${ay ? monthLabel(ay) : ''} takvimine elle kalem (ör. fuar, okul kampanyası).`}>
      <div className="flex flex-col gap-2">
        <label className="flex flex-col gap-1">
          <span className={labelCls}>Tür</span>
          <select className={field} value={f.tur} onChange={(e) => setF({ ...f, tur: e.target.value })}>
            {Object.entries(types).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
          </select>
        </label>
        <label className="flex flex-col gap-1"><span className={labelCls}>Başlık</span><input className={field} placeholder="ör. Okul kampanyası, fuar standı" value={f.baslik} onChange={(e) => setF({ ...f, baslik: e.target.value })} /></label>
        <div className="grid grid-cols-2 gap-2">
          <label className="flex flex-col gap-1"><span className={labelCls}>Başlangıç</span><input type="date" className={field} value={f.baslangic} onChange={(e) => setF({ ...f, baslangic: e.target.value })} /></label>
          <label className="flex flex-col gap-1"><span className={labelCls}>Bitiş</span><input type="date" className={field} value={f.bitis} onChange={(e) => setF({ ...f, bitis: e.target.value })} /></label>
        </div>
        <label className="flex flex-col gap-1">
          <span className={labelCls}>Kanal</span>
          <select className={field} value={f.kanal} onChange={(e) => setF({ ...f, kanal: e.target.value })}>
            <option value="">Kanal yok</option>
            {Object.entries(channels).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
          </select>
        </label>
        <div className="flex justify-end gap-2">
          <button type="button" className={btnGhost} onClick={onClose}>Vazgeç</button>
          <button type="button" className={btnPrimary} onClick={() => save.mutate()} disabled={save.isPending || !f.baslik.trim() || !f.baslangic}>Ekle</button>
        </div>
      </div>
    </Sheet>
  );
}
