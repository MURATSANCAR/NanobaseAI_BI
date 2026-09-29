import { useEffect, useRef, useState } from 'react';
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Download, FileArchive, FileSpreadsheet, FileText, Loader2, Sparkles } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import { Loading, Note, Pill, btnGhost, btnPrimary, errText } from '../admin/ui';
import { Kpi, KpiRow } from '../editorial/kit';
import { AskSheet, Tabs } from '../budget/parts';
import { STATUS_TONE, fmtDay, fmtInt, fmtMoney, fmtStamp, mktApi, type Plan } from './api';
import { Block, MarketingFrame } from './parts';
import SqlInfo from '../components/SqlInfo';
import { Explain } from '../components/Explain';
import CardTab from './CardTab';
import ChannelsTab from './ChannelsTab';
import CalendarTab from './CalendarTab';
import MaterialsTab from './MaterialsTab';
import HistoryTab from './HistoryTab';
import PlanBooks from './backlist/PlanBooks';
import { xlsxUrl } from '../components/excel';

/** Plan ekranı: Karne · Kanal ve bütçe · Takvim · Materyaller · Onay ve geçmiş; sağda Zeki AI önerisi. */

const TABS = [
  { key: 'karne', label: 'Karne' },
  { key: 'kanal', label: 'Kanal ve bütçe' },
  { key: 'takvim', label: 'Takvim' },
  { key: 'materyal', label: 'Materyaller' },
  { key: 'onay', label: 'Onay ve geçmiş' },
] as const;
type Tab = (typeof TABS)[number]['key'];
type Ask = null | 'submit' | 'withdraw' | 'approve' | 'upper' | 'reject' | 'revise' | 'delete';

const daysLeft = (iso: string | null) => (iso ? Math.round((Date.parse(iso) - Date.parse(new Date().toISOString().slice(0, 10))) / 86_400_000) : null);

export default function PlanScreen() {
  const { id = '' } = useParams();
  const nav = useNavigate();
  const qc = useQueryClient();
  const [params, setParams] = useSearchParams();
  const [ask, setAsk] = useState<Ask>(null);
  const tab: Tab = (TABS.find((t) => t.key === params.get('sekme'))?.key ?? 'karne') as Tab;

  const meta = useQuery({ queryKey: ['mkt', 'meta'], queryFn: mktApi.meta, enabled: ENGINE_ENABLED, staleTime: 60_000 });
  const plan = useQuery({ queryKey: ['mkt', 'plan', id], queryFn: () => mktApi.plan(id), enabled: ENGINE_ENABLED && !!id });
  const jobs = useQuery({
    queryKey: ['mkt', 'jobs', id],
    queryFn: () => mktApi.jobs(id),
    enabled: ENGINE_ENABLED && !!id,
    refetchInterval: (q) => (q.state.data?.items.some((j) => j.durum === 'bekliyor' || j.durum === 'calisiyor') ? 3000 : false),
  });
  const running = jobs.data?.items.find((j) => j.durum === 'bekliyor' || j.durum === 'calisiyor');
  const lastJob = jobs.data?.items[0];
  const jobWarning = lastJob?.durum === 'bitti' ? (lastJob.sonuc?.uyari as string | undefined) : undefined;

  // İş bitince plan tazelenir (satırlar, materyaller, gerekçe).
  const wasRunning = useRef(false);
  useEffect(() => {
    if (running) wasRunning.current = true;
    else if (wasRunning.current && lastJob) {
      wasRunning.current = false;
      qc.invalidateQueries({ queryKey: ['mkt', 'plan', id] });
      if (lastJob.durum === 'hata') toast.error(lastJob.hata ?? 'Zeki AI önerisi tamamlanamadı.');
      else toast.success('Zeki AI önerisi hazır.');
    }
  }, [running, lastJob, qc, id]);

  const setPlan = (p: Plan) => qc.setQueryData(['mkt', 'plan', id], p);

  const suggest = useMutation({
    mutationFn: () => mktApi.suggest(id),
    onSuccess: (out) => {
      setPlan({ ...out.plan, ustOnayGerekli: plan.data?.ustOnayGerekli, eksikMateryal: plan.data?.eksikMateryal });
      qc.invalidateQueries({ queryKey: ['mkt', 'jobs', id] });
      qc.invalidateQueries({ queryKey: ['mkt', 'plan', id] });
      toast.success('Kanal ve bütçe önerisi kuruldu; gerekçe ve metin taslakları hazırlanıyor.');
    },
    onError: (e) => toast.error(errText(e, 'Öneri başlatılamadı.') ?? ''),
  });

  const act = useMutation({
    mutationFn: async ({ kind, text }: { kind: Exclude<Ask, null>; text: string }) => {
      switch (kind) {
        case 'submit': return mktApi.submit(id);
        case 'withdraw': return mktApi.withdraw(id);
        case 'approve': return mktApi.approve(id, text || undefined);
        case 'upper': return mktApi.upperApprove(id, text || undefined);
        case 'reject': return mktApi.reject(id, text);
        case 'revise': return mktApi.revise(id, text);
        case 'delete': await mktApi.remove(id); return null;
      }
    },
    onSuccess: (out, { kind }) => {
      setAsk(null);
      qc.invalidateQueries({ queryKey: ['mkt'] });
      const msg = { submit: 'Plan onaya gönderildi.', withdraw: 'Plan taslağa geri alındı.', approve: 'Onay kaydedildi.', upper: 'Üst onay kaydedildi.', reject: 'Plan gerekçesiyle geri gönderildi.', revise: 'Revizyon taslağı açıldı.', delete: 'Taslak silindi.' }[kind];
      toast.success(msg);
      if (kind === 'revise' && out) nav(`/pazarlama/plan/${encodeURIComponent(out.id)}`);
      if (kind === 'delete') nav(bl ? '/pazarlama/backlist?sekme=aktivasyonlar' : '/pazarlama/yeni-kitap');
    },
    onError: (e) => toast.error(errText(e, 'İşlem yapılamadı.') ?? ''),
  });

  const m = meta.data;
  const p = plan.data;
  const me = m?.me;
  const editable = !!p && (p.durum === 'taslak' || p.durum === 'geri') && !!me?.canWrite;
  const mine = !!p && (p.gonderen ?? '').toLowerCase() === (me?.username ?? '').toLowerCase();
  const left = p ? daysLeft(p.yayinTarihi) : null;
  const approvedMaterials = p ? p.materials.filter((x) => x.durum === 'onayli').length : 0;
  // M17: backlist planı aynı ekranda; ilk sekme kitap listesi, öneri ve taslaklar Backlist uçlarından.
  const bl = p?.kind === 'backlist';
  const tabs = bl ? TABS.map((t) => (t.key === 'karne' ? { ...t, label: 'Kitaplar' } : t)) : TABS;
  const home = bl ? { to: '/pazarlama/backlist?sekme=aktivasyonlar', label: 'Backlist planları' } : { to: '/pazarlama/yeni-kitap', label: 'Yeni kitap planları' };

  const aside = p && me ? (
    <div className="flex flex-wrap gap-2 lg:justify-end">
      {me.canExport && (
        <>
          <a className={btnGhost} href={mktApi.pdfUrl(p.id)} download><FileText aria-hidden className="h-4 w-4" />PDF indir</a>
          <a className={btnGhost} href={mktApi.csvUrl(p.id)} download><Download aria-hidden className="h-4 w-4" />Tabloyu indir (CSV)</a>
          <a className={btnGhost} href={xlsxUrl(mktApi.csvUrl(p.id))} download><FileSpreadsheet aria-hidden className="h-4 w-4" />Tabloyu indir (Excel)</a>
          <a className={btnGhost} href={mktApi.packageUrl(p.id)} download><FileArchive aria-hidden className="h-4 w-4" />Yayına hazır paketi indir</a>
        </>
      )}
    </div>
  ) : undefined;

  return (
    <MarketingFrame
      crumb={bl ? 'Backlist' : 'Yeni kitap planı'}
      title={p?.baslik ?? 'Pazarlama planı'}
      lead={bl
        ? 'Seçilen backlist kitaplarını yeniden hareketlendirme planı: kitaplar, kanal ve bütçe, iş takvimi ve tanıtım metinleri. Plan onaylanınca değişmez; değişiklik için «Revize et» yeni sürüm açar.'
        : 'Bu kitabın pazarlama planı: satış karnesi, kanal ve bütçe, yayın gününe göre iş takvimi ve tanıtım metinleri. Plan onaylanınca değişmez; değişiklik için «Revize et» yeni sürüm açar.'}
      source={p ? `${p.id} · sürüm ${p.surum}` : ''}
      presence={p ? p.durumAdi : '…'}
      detail={p?.baslik}
      back={home}
      aside={aside}
    >
      {plan.error && <Note tone="err">{errText(plan.error, 'Plan açılamadı.')}</Note>}
      {plan.isLoading && <Loading />}
      {p && m && me && (
        <>
          <div className="flex flex-wrap items-center gap-2 px-1">
            <Pill tone={STATUS_TONE[p.durum]}>{p.durumAdi}</Pill>
            {p.ustOnayGerekli && p.durum !== 'onayli' && <Pill tone="violet">Bütçe eşiğin üstünde: üst onay gerekir</Pill>}
            <span className="text-[12px] font-semibold text-canvas-muted">
              Sahibi {p.sahip ?? '—'}
              {p.gonderen && p.durum === 'onayda' && <> · {p.gonderen} gönderdi ({fmtStamp(p.gonderme)})</>}
              {p.onaylayan && <> · pazarlama onayı {p.onaylayan}</>}
              {p.ustOnaylayan && <> · üst onay {p.ustOnaylayan}</>}
              {p.oncekiId && <> · önceki sürüm {p.oncekiId}</>}
            </span>
            <div className="ml-auto flex flex-wrap gap-2">
              {p.durum === 'taslak' && me.canWrite && <button type="button" className={btnGhost} onClick={() => setAsk('delete')}>Taslağı sil</button>}
              {editable && <button type="button" className={btnPrimary} onClick={() => setAsk('submit')}>Onaya gönder</button>}
              {p.durum === 'onayda' && me.canWrite && <button type="button" className={btnGhost} onClick={() => setAsk('withdraw')}>Onaydan çek</button>}
              {p.durum === 'onayda' && !mine && (me.canApprove || me.canUpperApprove) && (
                <button type="button" className={btnGhost} onClick={() => setAsk('reject')}>Geri gönder</button>
              )}
              {p.durum === 'onayda' && !mine && me.canApprove && !p.onaylayan && (
                <button type="button" className={btnPrimary} onClick={() => setAsk('approve')}>Onayla</button>
              )}
              {p.durum === 'onayda' && !mine && me.canUpperApprove && p.ustOnayGerekli && !p.ustOnaylayan && (
                <button type="button" className={btnPrimary} onClick={() => setAsk('upper')}>Üst onay ver</button>
              )}
              {p.durum === 'onayli' && me.canWrite && <button type="button" className={btnGhost} onClick={() => setAsk('revise')}>Revize et</button>}
            </div>
          </div>
          {p.durum === 'geri' && p.gerekce && <Note tone="warn">Geri gönderildi: {p.gerekce}</Note>}
          {p.durum === 'onayda' && mine && (me.canApprove || me.canUpperApprove) && <Note tone="info">Bu planı siz onaya gönderdiniz; onayı başka bir yetkili verir.</Note>}
          {p.durum === 'arsiv' && <Note tone="info">Bu sürüm arşivde; yerini yeni onaylı sürüm aldı.</Note>}

          <KpiRow>
            <Kpi label={bl ? 'Aktivasyon başlangıcı' : 'Yayın günü'} value={left === null ? '—' : left < 0 ? `${-left} gün önce` : `${left} gün`} help={`${fmtDay(p.yayinTarihi)} · ${p.yayinTarihiKaynakAdi ?? 'kaynak yok'}`}
              info={<SqlInfo k={p.kaynaklar} alan="yayinTarihi" label={bl ? 'Aktivasyon başlangıcı' : 'Yayın günü'} />}
              explain={bl ? 'Aktivasyonun başlayacağı güne kaç gün kaldığı. Alt satırda tarih ve tarihin nereden alındığı yazar.' : 'Kitabın yayın gününe kaç gün kaldığı. Alt satırda tarih ve tarihin hangi CRM alanından alındığı yazar; takvimdeki işler bu güne göre dizilir.'} />
            <Kpi label="Satış hedefi" value={p.hedef?.adet != null ? `${fmtInt(p.hedef.adet)} adet` : '—'}
              help={p.hedef?.planId ? (me.canSeeBudget && p.hedef.ciro != null ? `${fmtMoney(p.hedef.ciro)} net ciro · ${p.hedef.year}` : `${p.hedef.year} bütçe planı`) : (p.hedef?.not ?? 'Onaylı hedef yok')}
              info={<SqlInfo k={p.kaynaklar} alan="hedef" label="Satış hedefi" />}
              explain="Bütçe planında bu kitap için onaylanmış satış adedi. Zeki AI hedef üretmez; onaylı hedef yoksa kart boş kalır." />
            <Kpi label="Plan bütçesi" value={me.canSeeBudget ? fmtMoney(p.butceToplam) : '—'}
              help={me.canSeeBudget ? (p.butceCerceve != null ? `Çerçeve ${fmtMoney(p.butceCerceve)}` : 'Bütçe çerçevesi yok') : 'Bütçe görme yetkiniz yok'}
              active={tab === 'kanal'} onClick={() => setParams({ sekme: 'kanal' }, { replace: true })}
              info={<SqlInfo k={p.kaynaklar} alan="butceToplam" label="Plan bütçesi" />}
              explain="Kanal ve bütçe sekmesindeki satırların toplamı. «Çerçeve», bu kitap için ayrılabilecek üst tutardır; plan toplamı onu aşmamalıdır." />
            <Kpi label="Onaylı materyal" value={`${approvedMaterials} / ${p.materials.length}`}
              help={p.eksikMateryal?.length ? `Eksik: ${p.eksikMateryal.map((t) => m.materials[t] ?? t).join(', ')}` : 'Zorunlu materyaller tamam'}
              active={tab === 'materyal'} onClick={() => setParams({ sekme: 'materyal' }, { replace: true })}
              info={<SqlInfo k={p.kaynaklar} alan="materials" label="Onaylı materyal" />}
              explain="Tanıtım metinlerinden (bülten, föy, sosyal medya metni gibi) kaçının son onayı aldığı. Zorunlu olanlardan biri eksikse alt satırda yazar." />
          </KpiRow>

          <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:gap-4">
            <div className="flex min-w-0 flex-1 flex-col gap-3">
              <Tabs tabs={tabs} value={tab} onChange={(k) => setParams({ sekme: k }, { replace: true })} />
              {tab === 'karne' && !bl && p.stokKodu && <CardTab stok={p.stokKodu} meta={m} />}
              {tab === 'karne' && bl && <PlanBooks plan={p} editable={editable} />}
              {tab === 'kanal' && <ChannelsTab plan={p} meta={m} editable={editable} onSaved={setPlan} />}
              {tab === 'takvim' && <CalendarTab plan={p} meta={m} editable={editable} canMark={me.canWrite && p.durum !== 'arsiv'} onSaved={setPlan} />}
              {tab === 'materyal' && <MaterialsTab plan={p} meta={m} running={!!running} />}
              {tab === 'onay' && <HistoryTab plan={p} meta={m} />}
            </div>

            <aside className="flex w-full shrink-0 flex-col gap-3 lg:sticky lg:top-0 lg:w-[380px]">
              <Block
                title="Zeki AI önerisi"
                help="Kanal ve bütçe kural ve emsal oranlarıyla hesaplanır; Zeki AI yalnız gerekçeyi, konumlamayı ve metin taslaklarını yazar. Rakam üretmez; kaynakta olmayan alıntı ve rakam düşer."
              >
                {!m.modelReady && <Note tone="warn">Zeki AI şu an bağlı değil: öneri yalnız kurallar ve emsal kitapların oranıyla kurulur, gerekçe ve metin taslağı yazılmaz.</Note>}
                {bl && (
                  <p className="mt-1 text-[12px] leading-snug text-canvas-muted">
                    Kanal ve bütçe plan açılırken kural ve kitapların geçmiş pazarlama harcamasıyla kuruldu. «Neden şimdi oku»
                    gönderileri, e-bülten bölümü ve toplu alım mektubu Materyaller sekmesinden Zeki AI'a yazdırılır.
                  </p>
                )}
                {!bl && me.canWrite && p.durum !== 'arsiv' && (
                  <button type="button" className={`${btnPrimary} mt-2 w-full`} onClick={() => suggest.mutate()} disabled={!!running || suggest.isPending}>
                    {running || suggest.isPending ? <Loader2 aria-hidden className="h-4 w-4 animate-spin" /> : <Sparkles aria-hidden className="h-4 w-4" />}
                    {running ? (running.adim ?? 'Hazırlanıyor…') : 'Zeki AI önerisi al'}
                  </button>
                )}
                {!bl && !editable && p.durum !== 'arsiv' && me.canWrite && (
                  <p className="mt-1.5 text-[11px] text-canvas-muted">Plan onayda ya da onaylı: öneri bütçe satırlarına dokunmaz, yalnız materyal taslağı yazar.</p>
                )}
                {lastJob?.durum === 'hata' && <div className="mt-2"><Note tone="err">{lastJob.hata}</Note></div>}
                {jobWarning && <div className="mt-2"><Note tone="warn">{jobWarning}</Note></div>}
                {p.zeki?.konumlama && (
                  <div className="mt-3">
                    <div className="text-[11px] font-bold uppercase tracking-wide text-canvas-muted">Hedef okur ve konumlama</div>
                    <p className="mt-1 whitespace-pre-line text-[12.5px] leading-snug">{p.zeki.konumlama}</p>
                  </div>
                )}
                {p.zeki?.kanalGerekce && (
                  <div className="mt-3">
                    <div className="text-[11px] font-bold uppercase tracking-wide text-canvas-muted">Kanal önceliğinin gerekçesi</div>
                    <p className="mt-1 whitespace-pre-line text-[12.5px] leading-snug">{p.zeki.kanalGerekce}</p>
                  </div>
                )}
                {!!p.zeki?.emsal?.length && (
                  <div className="mt-3">
                    <div className="flex items-center gap-1 text-[11px] font-bold uppercase tracking-wide text-canvas-muted">Emsal kontrolü (CRM'de emsal girilmemiş)<SqlInfo k={p.kaynaklar} alan="zeki" label="Emsal kontrolü olasılığı" /><Explain label="Emsal kontrolü">Emsal, bu kitaba benzeyen ve daha önce yayımlanmış kitaptır; karnede satışı örnek alınır. CRM'de emsal girilmediği için Zeki AI adayların benzer olup olmadığını tahmin eder; yüzde, bu tahminin gücüdür.</Explain></div>
                    <ul className="mt-1 flex flex-col gap-1 text-[12px]">
                      {p.zeki.emsal.map((e) => (
                        <li key={e.stokKodu} className="flex items-start justify-between gap-2">
                          <span className="min-w-0 break-words">{e.ad ?? e.stokKodu}</span>
                          <Pill tone={e.karar === 'emsal' ? 'ok' : e.karar === 'degil' ? 'err' : 'muted'}>
                            {e.karar === 'emsal' ? 'emsal' : e.karar === 'degil' ? 'emsal değil' : 'belirsiz'}
                            {e.olasilik != null ? ` · %${Math.round(e.olasilik * 100)}` : ''}
                          </Pill>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
                {!!p.zeki?.dusen && <p className="mt-2 text-[11px] text-canvas-muted">Denetimde {p.zeki.dusen} cümle düştü (kaynaksız rakam, bulunamayan alıntı ya da kanıtsız iddia).<SqlInfo k={p.kaynaklar} alan="zeki" label="Denetimde düşen cümle" className="ml-0.5" /></p>}
              </Block>
              {p.stokKodu && !bl && (
                <Block title="Zeki AI'a sor" help="Genel bakıştaki soru kutusu açılır; cevap satış verisinden gelir.">
                  <ul className="flex flex-col gap-1.5">
                    {[
                      `${p.stokKodu} stok kodlu kitabın emsallerinden hangisi ilk üç ayda en çok sattı?`,
                      `${p.stokKodu} stok kodlu kitabın yazarının önceki kitaplarının geçen yıl net satışı ve iade oranı ne?`,
                      'Önümüzdeki ay yayımlanacak yeni kitapların toplam pazarlama bütçesi ve hedef cirosu ne?',
                    ].map((q) => (
                      <li key={q}>
                        <Link className="block min-h-11 rounded-xl bg-white/70 px-3 py-2 text-[12px] font-semibold leading-snug text-canvas-ink transition-colors duration-150 hover:bg-white" to={`/genel-bakis?soru=${encodeURIComponent(q)}`}>
                          {q}
                        </Link>
                      </li>
                    ))}
                  </ul>
                </Block>
              )}
            </aside>
          </div>
        </>
      )}

      <AskSheet
        open={ask !== null}
        busy={act.isPending}
        title={{ submit: 'Onaya gönder', withdraw: 'Onaydan çek', approve: 'Planı onayla', upper: 'Üst onay', reject: 'Geri gönder', revise: 'Planı revize et', delete: 'Taslağı sil', '': '' }[ask ?? '']}
        message={
          ask === 'submit' ? 'Plan onay bekleyenlere düşer ve onaycılara e-posta gider; onayı sizden başka bir yetkili verir. Onayda iken satırlar değiştirilemez.'
            : ask === 'withdraw' ? 'Plan yeniden taslak olur; değişiklikten sonra tekrar gönderilebilir.'
            : ask === 'approve' ? (p?.ustOnayGerekli ? 'Pazarlama onayınız kaydedilir. Bütçe eşiğin üstünde olduğu için plan üst onaydan sonra onaylı olur.' : 'Plan onaylanır; lansman, aylık plan ve içerik modülleri bu planı okur.')
            : ask === 'upper' ? 'Bütçe üst onayınız kaydedilir. Pazarlama onayı da verilmişse plan onaylanır.'
            : ask === 'reject' ? 'Plan gerekçenizle geri döner; hazırlayan düzeltip yeniden gönderir.'
            : ask === 'revise' ? 'Onaylı planın kopyası yeni bir taslak sürüm olarak açılır. Yeni sürüm onaylanana kadar bu plan geçerli kalır.'
            : 'Taslak, satırları, takvimi ve materyalleri silinir. Bu işlem geri alınmaz.'
        }
        confirm={{ submit: 'Onaya gönder', withdraw: 'Taslağa al', approve: 'Onayla', upper: 'Üst onay ver', reject: 'Geri gönder', revise: 'Revizyon aç', delete: 'Sil', '': '' }[ask ?? '']}
        danger={ask === 'delete'}
        input={ask === 'reject' ? 'Gerekçe' : ask === 'revise' ? 'Revizyon gerekçesi (hedef değişti, yayın ertelendi…)' : ask === 'approve' || ask === 'upper' ? 'Not (isteğe bağlı)' : undefined}
        required={ask === 'reject' || ask === 'revise'}
        onClose={() => setAsk(null)}
        onConfirm={(text) => ask && act.mutate({ kind: ask, text })}
      />
    </MarketingFrame>
  );
}
