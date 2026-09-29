import { useCallback, useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Loader2, RefreshCw } from 'lucide-react';
import { Loading, Note, btnGhost, errText } from '../admin/ui';
import { Tabs } from '../budget/parts';
import { Kpi, KpiRow } from '../editorial/kit';
import SqlInfo from '../components/SqlInfo';
import { ENGINE_ENABLED } from '../engine';
import AccountsTab from './AccountsTab';
import DealerPanel from './DealerPanel';
import PackageBuilder from './PackageBuilder';
import Pipeline from './Pipeline';
import { ApprovalsTab, RemindersTab, ThemesTab } from './WorkTabs';
import { CorporateFrame } from './parts';
import { corporateApi, fmtDay, fmtInt, fmtPct, fmtShort, growth } from './api';

/** M32 Kurumsal satış ve B2B. Sekme adres çubuğunda (?sekme=); paket oluşturucu `?firsat=` ile bir fırsata teklif ekler. */

type Tab = 'firsat' | 'paket' | 'kurum' | 'hatirlatma' | 'onay' | 'tema' | 'bayi';

export default function CorporateScreen() {
  const qc = useQueryClient();
  const [params, setParams] = useSearchParams();
  const meta = useQuery({ queryKey: ['corporate', 'meta'], queryFn: corporateApi.meta, enabled: ENGINE_ENABLED, staleTime: 60_000 });
  const sum = useQuery({ queryKey: ['corporate', 'summary'], queryFn: corporateApi.summary, enabled: ENGINE_ENABLED });
  const m = meta.data;
  const s = sum.data;

  const tabs: Array<{ key: Tab; label: string; badge?: number | null }> = [
    { key: 'firsat', label: 'Fırsatlar' },
    { key: 'paket', label: 'Paket oluşturucu' },
    { key: 'kurum', label: 'Kurumlar' },
    { key: 'hatirlatma', label: 'Hatırlatmalar', badge: s?.hatirlatma || null },
    ...(m?.me.canApprove ? [{ key: 'onay' as Tab, label: 'Onay bekleyen', badge: s?.onayBekleyen || null }] : []),
    ...(m?.me.canTheme ? [{ key: 'tema' as Tab, label: 'Kitap temaları', badge: s?.temaOnerisi || null }] : []),
    ...(m?.me.canB2b ? [{ key: 'bayi' as Tab, label: 'Bayi paneli' }] : []),
  ];
  const tab: Tab = (tabs.find((t) => t.key === params.get('sekme'))?.key ?? 'firsat') as Tab;
  const go = useCallback(
    (t: Tab) => {
      const p = new URLSearchParams(params);
      if (t === 'firsat') p.delete('sekme');
      else p.set('sekme', t);
      if (t !== 'paket') {
        p.delete('firsat');
        p.delete('tema');
      }
      setParams(p, { replace: true });
    },
    [params, setParams],
  );

  // Veri yenilenirken durum yoklanır; bitince bütün görünümler tazelenir.
  const running = m?.status.running;
  const status = useQuery({
    queryKey: ['corporate', 'status'],
    queryFn: corporateApi.status,
    enabled: ENGINE_ENABLED && !!running,
    refetchInterval: (q) => (q.state.data && !q.state.data.running ? false : 4000),
  });
  useEffect(() => {
    if (running && status.data && !status.data.running) {
      qc.invalidateQueries({ queryKey: ['corporate'] });
      if (status.data.error) toast.error(status.data.error);
      else toast.success('Logo ve CRM verileri güncellendi.');
    }
  }, [running, status.data, qc]);
  const refresh = useMutation({
    mutationFn: corporateApi.refresh,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['corporate', 'meta'] }),
    onError: (e) => toast.error(errText(e, 'Yenileme başlatılamadı.') ?? ''),
  });

  const err = errText(meta.error, 'Ekran bilgisi okunamadı.') ?? errText(sum.error, 'Özet okunamadı.');
  const g = s ? growth(s.kurumCiro, s.kurumCiroGecenYil) : null;
  const last = m?.status.last;
  const busy = !!(running || refresh.isPending);

  return (
    <CorporateFrame
      title="Kurumsal satış ve B2B"
      lead="Kurumlara toplu kitap satışını takip edersiniz: fırsatlar, tema paketi ve teklif, geçen yıl bu dönemde alım yapan kurumların hatırlatması ve sipariş vermeyen bayiler. Veriler Logo ve CRM'den okunur; hiçbir sisteme yazılmaz, teklifi temsilci gönderir."
      source={s?.dataEnd ? `Logo · ${fmtDay(s.dataEnd)} tarihine kadar` : 'Logo + CRM'}
      presence={busy ? (status.data?.step ?? m?.status.step ?? 'Okunuyor') : last?._at ? `Son okuma ${fmtDay(last._at)}` : 'Henüz okunmadı'}
      aside={
        m?.me.canQuote ? (
          <div className="flex flex-col items-stretch gap-1 lg:items-end">
            <button type="button" className={btnGhost} disabled={busy} onClick={() => refresh.mutate()}>
              {busy ? <Loader2 aria-hidden className="h-4 w-4 animate-spin" /> : <RefreshCw aria-hidden className="h-4 w-4" />}
              {busy ? (status.data?.step ?? m.status.step ?? 'Okunuyor…') : 'Verileri yenile'}
            </button>
            <span className="text-[11px] text-canvas-muted lg:text-right">Her gece 04:00'te kendiliğinden yenilenir.</span>
          </div>
        ) : undefined
      }
    >
      {!ENGINE_ENABLED && <Note tone="warn">Bu ekranın veri bağlantısı kurulmamış; liste açılamaz. Lütfen sistem yöneticinize bildirin.</Note>}
      {err && <Note tone="err">{err}</Note>}
      {last && last.ok === false && <Note tone="err">Son okuma başarısız: {last.error}</Note>}
      {last?.warnings?.map((w) => <Note key={w} tone="warn">{w}</Note>)}
      {!s?.dataEnd && s && !busy && <Note tone="info">Veriler henüz okunmadı. «Verileri yenile» ile Logo ve CRM okunur (birkaç dakika sürebilir).</Note>}

      <KpiRow>
        <Kpi
          label={s?.window ? `Kurum cirosu ${s.window.year} ${s.window.label}` : 'Kurum cirosu'}
          value={s ? fmtShort(s.kurumCiro) : '—'}
          help={s ? `Geçen yıl aynı dönem ${fmtShort(s.kurumCiroGecenYil)}${g !== null ? ` · ${g >= 0 ? '+' : ''}${fmtPct(g)}` : ''}` : 'Kurum kanalı net satış'}
          explain="Logo'da kurum kanalındaki müşterilere kesilen faturaların, iadeler düşüldükten sonraki toplamı; yılın bugüne kadarki dönemi geçen yılın aynı dönemiyle karşılaştırılır."
          active={tab === 'kurum'}
          onClick={() => go('kurum')}
          info={<SqlInfo k={s?.kaynaklar} alan="kurumCiroBuyume" label="Kurum cirosu, geçen yıl aynı dönem ve büyüme" />}
        />
        <Kpi
          label="Açık fırsat"
          value={s ? fmtInt(s.acikFirsat) : '—'}
          help={s ? `Tahmini ${fmtShort(s.acikFirsatDeger)}${m && !m.me.seeAll ? ' · sizin' : ''}` : 'Aday → Karar'}
          explain="Henüz kazanılmamış ya da kaybedilmemiş fırsatlar (aday, görüşüldü, teklif, karar aşamaları). Altında bu fırsatların tahmini toplam değeri yazar."
          active={tab === 'firsat'}
          onClick={() => go('firsat')}
          info={<SqlInfo k={s?.kaynaklar} alan="acikFirsat" label="Açık fırsat ve tahmini değer" />}
        />
        <Kpi
          label="Hatırlatma"
          value={s ? fmtInt(s.hatirlatma) : '—'}
          help={s ? `Geçen yıl bu dönemde ${fmtShort(s.hatirlatmaTutar)} alan kurumlar` : 'Dönemsel alım'}
          explain={`Geçen yıl önümüzdeki aylarda alım yapmış kurumlar. Hatırlatma, alım ayından ${m?.settings.reminderLeadDays ?? 45} gün önce açılır; kuruma zamanında teklif götürmeniz içindir.`}
          active={tab === 'hatirlatma'}
          onClick={() => go('hatirlatma')}
          info={<SqlInfo k={s?.kaynaklar} alan="hatirlatma" label="Hatırlatma ve geçen yıl tutarı" />}
        />
        {m?.me.canB2b ? (
          <Kpi
            label="Sipariş vermeyen bayi"
            value={s ? fmtInt(s.sessizBayi) : '—'}
            help={s && m ? `${m.settings.silentDays} gündür faturası yok · ${fmtInt(s.bayi)} bayiden` : 'Bayi kanalı'}
            explain={`Bayi kanalındaki carilerden ${m?.settings.silentDays ?? ''} gündür Logo'da faturası olmayanlar. Karta dokununca bayi paneli açılır.`}
            active={tab === 'bayi'}
            onClick={() => go('bayi')}
            info={<SqlInfo k={s?.kaynaklar} alan="sessizBayi" label="Sipariş vermeyen bayi ve bayi sayısı" />}
          />
        ) : (
          <Kpi label="Onay bekleyen" value={s ? fmtInt(s.onayBekleyen) : '—'} help="İndirim/marj eşiğini aşan teklif"
            explain="İndirimi izin verilen sınırı aşan ya da kâr payı alt sınırın altına düşen teklifler müdür onayı bekler; onaya gönderen kişi aynı teklifi onaylayamaz."
            info={<SqlInfo k={s?.kaynaklar} alan="onayBekleyen" label="Onay bekleyen teklif" />} />
        )}
      </KpiRow>

      <Tabs tabs={tabs} value={tab} onChange={go} />
      {/* Sekme rozetlerindeki sayıların kaynağı: rozet düğmenin içinde olduğundan «i» burada, sekme şeridinin altında. */}
      {s && tabs.some((t) => t.badge) && (
        <div className="-mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 px-1 text-[11px] text-canvas-muted">
          <span>Sekme rozetleri:</span>
          {tabs.filter((t) => t.badge).map((t) => (
            <span key={t.key} className="inline-flex items-center">
              {t.label} <span className="ml-1 font-mono tabular-nums">{fmtInt(t.badge)}</span>
              <SqlInfo
                k={s.kaynaklar}
                alan={t.key === 'hatirlatma' ? 'hatirlatma' : t.key === 'onay' ? 'onayBekleyen' : 'temaOnerisi'}
                label={`${t.label} rozeti`}
                className="ml-0.5"
              />
            </span>
          ))}
        </div>
      )}
      {meta.isLoading && <Loading />}
      {m && tab === 'firsat' && <Pipeline meta={m} onReminders={() => go('hatirlatma')} />}
      {m && tab === 'paket' && <PackageBuilder meta={m} />}
      {m && tab === 'kurum' && <AccountsTab meta={m} />}
      {m && tab === 'hatirlatma' && <RemindersTab meta={m} />}
      {m && tab === 'onay' && <ApprovalsTab />}
      {m && tab === 'tema' && <ThemesTab meta={m} />}
      {m && tab === 'bayi' && <DealerPanel meta={m} />}
    </CorporateFrame>
  );
}
