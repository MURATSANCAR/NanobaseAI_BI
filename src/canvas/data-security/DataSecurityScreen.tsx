import type { ReactNode } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import Shell, { ZoomStage } from '../stitch/Shell';
import { ENGINE_ENABLED } from '../engine';
import { Note, Pill, errText } from '../admin/ui';
import { Kpi, KpiRow, Panel } from '../editorial/kit';
import { Tabs } from '../budget/parts';
import { fmtAt, fmtN, securityApi, type SecurityMeta } from './api';
import AlertsTab from './AlertsTab';
import LoginsTab from './LoginsTab';
import AccessTab from './AccessTab';
import HygieneTab from './HygieneTab';
import InventoryTab from './InventoryTab';
import RetentionTab from './RetentionTab';
import SqlInfo, { InfoLabel } from '../components/SqlInfo';
import { kaynakOf } from '../components/kaynakOf';

/** M49 Veri yönetimi ve güvenlik. Sekme adres çubuğunda (?sekme=); bağlantı paylaşılabilir. Yetkiler ve değişiklik
 *  kaydı Yönetim ekranında kalır; bu ekran onlara bağlantı verir, kopyalamaz. */

const TABS = [
  { key: 'ozet', label: 'Özet' },
  { key: 'uyarilar', label: 'Uyarılar' },
  { key: 'giris', label: 'Giriş ve oturumlar' },
  { key: 'erisim', label: 'Erişim kaydı' },
  { key: 'hijyen', label: 'Hesap hijyeni' },
  { key: 'envanter', label: 'Kişisel veri envanteri' },
  { key: 'saklama', label: 'Saklama süreleri' },
] as const;
type Tab = (typeof TABS)[number]['key'];

export function SecurityFrame({ children }: { children: ReactNode }) {
  return (
    <Shell head={{ tenant: 'Timaş Yayınları', section: 'Altyapı ve destek', crumb: 'Veri güvenliği', source: 'Kaynak: portal kaydı · giriş servisi · AD · CRM', presence: 'Veri güvenliği' }}>
      <main className="absolute bottom-2 left-2 right-2 top-16 overflow-y-auto overscroll-contain sm:bottom-6 sm:left-6 sm:right-6 sm:top-[84px]">
        <ZoomStage>
          <div className="mx-auto flex w-full max-w-[1760px] flex-col gap-3 pb-6 lg:gap-4">
            <header className="relative z-20 px-1">
              <div className="text-[11px] font-bold uppercase tracking-wide text-canvas-violet">Altyapı ve destek · Veri yönetimi ve güvenlik</div>
              <h1 className="mt-0.5 text-[22px] font-extrabold leading-tight tracking-tight sm:text-[28px]">Veri güvenliği</h1>
              <p className="mt-1 max-w-[78ch] text-[12.5px] leading-snug text-canvas-muted">
                Portala kim, ne zaman girdi; kim yetkisi olmayan bir sayfayı denedi, kim ne indirdi. Uyarılar kuraldan gelir ve
                gerekçesiyle yazılır. Kişisel veri envanteri ve saklama süreleri burada; süresi dolan kayıt yalnız yönetici
                açtığında ve önizlemesi görüldükten sonra silinir.
              </p>
            </header>
            {children}
          </div>
        </ZoomStage>
      </main>
    </Shell>
  );
}

export default function DataSecurityScreen() {
  const [params, setParams] = useSearchParams();
  const tab: Tab = (TABS.find((t) => t.key === params.get('sekme'))?.key ?? 'ozet') as Tab;
  const meta = useQuery({ queryKey: ['security', 'meta'], queryFn: securityApi.meta, enabled: ENGINE_ENABLED, staleTime: 60_000 });
  const summary = useQuery({ queryKey: ['security', 'summary'], queryFn: securityApi.summary, enabled: ENGINE_ENABLED, refetchInterval: 60_000 });
  const open = summary.data ? summary.data.openAlerts.kritik + summary.data.openAlerts.uyari : null;
  const go = (t: Tab) => setParams(t === 'ozet' ? {} : { sekme: t }, { replace: true });

  return (
    <SecurityFrame>
      <Tabs tabs={TABS.map((t) => ({ ...t, badge: t.key === 'uyarilar' ? open : null }))} value={tab} onChange={go} />
      {meta.error && <Note tone="err">{errText(meta.error, 'Ekran bilgisi okunamadı.')}</Note>}
      {meta.data && !meta.data.loginService.configured && (
        <Note tone="warn">
          Giriş servisine yönetim bağlantısı kurulmamış: giriş kaydı bu ekrana taşınmıyor ve oturum kapatılamıyor. Sunucuda
          giriş servisine ve köprüye aynı yönetim jetonu verilmeli.
        </Note>
      )}
      {tab === 'ozet' && <SummaryTab meta={meta.data} go={go} />}
      {tab === 'uyarilar' && <AlertsTab meta={meta.data} />}
      {tab === 'giris' && <LoginsTab meta={meta.data} />}
      {tab === 'erisim' && <AccessTab />}
      {tab === 'hijyen' && <HygieneTab meta={meta.data} />}
      {tab === 'envanter' && <InventoryTab />}
      {tab === 'saklama' && <RetentionTab meta={meta.data} />}
    </SecurityFrame>
  );
}

function Row({ label, value, tone, help }: { label: string; value: ReactNode; tone?: 'ok' | 'warn' | 'err' | 'muted'; help?: ReactNode }) {
  return (
    <div className="flex flex-col gap-1 border-b border-slate-100 py-2.5 last:border-0 sm:flex-row sm:items-start sm:justify-between sm:gap-4">
      <div className="min-w-0">
        <div className="text-[12.5px] font-bold">{label}</div>
        {help && <div className="text-[11.5px] leading-snug text-canvas-muted">{help}</div>}
      </div>
      <div className="shrink-0">{tone ? <Pill tone={tone}>{value}</Pill> : <span className="text-[12.5px] font-bold">{value}</span>}</div>
    </div>
  );
}

function SummaryTab({ meta, go }: { meta?: SecurityMeta; go: (t: Tab) => void }) {
  const q = useQuery({ queryKey: ['security', 'summary'], queryFn: securityApi.summary, enabled: ENGINE_ENABLED });
  const s = q.data;
  if (q.error) return <Note tone="err">{errText(q.error, 'Özet okunamadı.')}</Note>;
  if (!s) return <div className="py-10 text-center text-[12px] text-canvas-muted">Yükleniyor…</div>;
  const pull = s.loginPull;
  return (
    <>
      <KpiRow>
        <Kpi label="Açık uyarı" value={fmtN(s.openAlerts.kritik + s.openAlerts.uyari)} help={`${fmtN(s.openAlerts.kritik)} kritik`} onClick={() => go('uyarilar')} info={<SqlInfo k={kaynakOf(s)} alan="openAlerts" label="Açık uyarı" />} />
        <Kpi label="Hatalı giriş · 24 saat" value={fmtN(s.last24h.loginFailed)} help={`${fmtN(s.last24h.loginOk)} başarılı giriş`} onClick={() => go('giris')} info={<SqlInfo k={kaynakOf(s)} alan="last24h" label="Hatalı giriş" />} />
        <Kpi label="Yetkisiz deneme · 24 saat" value={fmtN(s.last24h.forbidden)} help="Sayfa ya da işlem reddi" onClick={() => go('erisim')} info={<SqlInfo k={kaynakOf(s)} alan="last24h" label="Yetkisiz deneme" />} />
        <Kpi label="Dışa aktarma · 24 saat" value={fmtN(s.last24h.export)} help="Excel, CSV, PDF, Word" onClick={() => go('erisim')} info={<SqlInfo k={kaynakOf(s)} alan="last24h" label="Dışa aktarma" />} />
      </KpiRow>
      <div className="grid gap-3 lg:grid-cols-2 lg:gap-4">
        <Panel>
          <h2 className="flex items-center gap-1 text-[16px] font-extrabold tracking-tight">
            Uyum göstergeleri
            <SqlInfo k={kaynakOf(s)} alan="_hepsi" label="Uyum göstergeleri" />
          </h2>
          <div className="mt-1">
            <Row
              label="Saklama süresi"
              value={s.retention.apply ? 'uygulanıyor' : 'yalnız önizleme'}
              tone={s.retention.apply ? 'ok' : 'warn'}
              help={s.retention.apply ? `Son başarılı iş: ${fmtAt(s.retention.lastOk)}` : `Hiçbir kayıt silinmiyor. Son önizleme: ${fmtAt(s.retention.lastPreview)}`}
            />
            <Row
              label="«Herkes» rolünün kapsamı"
              value={s.everyone.all ? 'bütün sayfalar' : `${s.everyone.pages}/${s.everyone.pagesTotal} sayfa`}
              tone={s.everyone.all ? 'err' : s.everyone.pages > 0 ? 'warn' : 'ok'}
              help="Prod öncesi daraltılacak. Kimin neyi kaybedeceği: Hesap hijyeni → «Herkes» daraltma önizlemesi."
            />
            <Row label="Veri alanı atanmamış tablo" value={fmtN(s.unassignedEntities)} tone={s.unassignedEntities ? 'warn' : 'ok'}
              help="ZEKİ AI'ın alan kuralına düşmeyen tablolar; Yönetim → Yetkiler → Veri alanları." />
            <Row label="Kaynakta kişisel veri kolonu" value={fmtN(s.sensitiveColumns)} help="Maskeli: değeri okunmaz, modele gitmez." />
            <Row
              label="Giriş kaydı"
              value={!s.loginService.configured ? 'bağlı değil' : pull?.ok ? 'çalışıyor' : pull ? 'hata' : 'henüz çekilmedi'}
              tone={!s.loginService.configured ? 'err' : pull?.ok ? 'ok' : 'warn'}
              help={pull ? `Son çekiş: ${fmtAt(pull.at)}${pull.error ? ` — ${pull.error}` : ''}` : undefined}
            />
          </div>
        </Panel>
        <Panel>
          <h2 className="text-[16px] font-extrabold tracking-tight">Kurallar</h2>
          {meta ? (
            <ul className="mt-2 space-y-1.5 text-[12.5px] leading-snug">
              <li>Aynı hesaba {meta.rules.failWindowMin} dakikada {meta.rules.failThreshold} ve üzeri hatalı giriş → kritik uyarı.</li>
              <li>Mesai dışında ({meta.rules.workHours} dışı ya da hafta sonu) bir saatte {meta.rules.offhoursExportMin} ve üzeri dışa aktarma → kritik uyarı.</li>
              <li>Yeni yönetici ya da «Herkes» rolüne yetki eklenmesi → kritik uyarı.</li>
              <li>Saklama işi uygulanıyorken 2 gece üst üste çalışmazsa → kritik uyarı.</li>
              <li>Günlük özet (kişi başına 403 ve yetki dışı soru) her gün {meta.rules.dailyAt}'ten sonra.</li>
              <li className="text-canvas-muted">
                {meta.rules.recipients ? `Uyarılar ${meta.rules.recipients} alıcıya e-postayla gider.` : 'Uyarı alıcısı girilmemiş: uyarılar yalnız bu ekranda.'} Eşikler: Yönetim → Ayarlar → Veri güvenliği.
              </li>
            </ul>
          ) : null}
          {meta?.me.isAdmin && (
            <div className="mt-3 flex flex-wrap gap-3 text-[12.5px] font-bold">
              <Link className="text-canvas-violet hover:underline" to="/yonetim?bolum=access">Yetkiler</Link>
              <Link className="text-canvas-violet hover:underline" to="/yonetim?bolum=audit">Değişiklik kaydı</Link>
              <Link className="text-canvas-violet hover:underline" to="/yonetim?bolum=prompts">Soru izleme</Link>
              <Link className="text-canvas-violet hover:underline" to="/yonetim?bolum=settings">Ayarlar</Link>
            </div>
          )}
        </Panel>
      </div>
    </>
  );
}
