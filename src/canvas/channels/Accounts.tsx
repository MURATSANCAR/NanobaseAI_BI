import { useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Download, Loader2, Sparkles } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import { Loading, Note, Pill, TableWrap, btnGhost, btnPrimary, errText, field, td, th } from '../admin/ui';
import { Panel } from '../editorial/kit';
import { foldTr } from '../components/SearchSelect';
import { fmtDay, fmtMoney, fmtPct } from '../budget/api';
import { Tabs } from '../budget/parts';
import { channelsApi, platformName, type Account, type ChannelsMeta } from './api';
import { ChannelsFrame, DataBar, useChannelsMeta } from './parts';
import SqlInfo, { InfoLabel } from '../components/SqlInfo';
import { EmptyHint, Explain } from '../components/Explain';

/** M42 cari ↔ platform eşlemesi (/kanallar/eslesme). Zeki AI ya da unvan eşleşmesi aday önerir, kullanıcı onaylar; kanal
 * kodu ve CRM hedef bölgesi de burada platforma bağlanır. Eşleme portal kaydıdır; CRM'e ve Logo'ya yazılmaz. */

const SECTIONS = [
  { key: 'cariler', label: 'Cariler' },
  { key: 'kanal', label: 'Kanal kodları' },
  { key: 'bolge', label: 'Hedef bölgeleri' },
] as const;
type Section = (typeof SECTIONS)[number]['key'];

const DURUM: Record<Account['durum'], { label: string; tone: 'ok' | 'warn' | 'muted' }> = {
  onayli: { label: 'Onaylı', tone: 'ok' },
  aday: { label: 'Aday', tone: 'warn' },
  bekliyor: { label: 'Aday yok', tone: 'muted' },
};
const YONTEM: Record<string, string> = { ad: 'unvan eşleşmesi', zeki: 'Zeki AI', elle: 'elle' };

function PlatformSelect({ meta, value, onChange, disabled, label }: { meta: ChannelsMeta; value: string; onChange: (v: string) => void; disabled?: boolean; label: string }) {
  return (
    <select className={`${field} min-w-[160px]`} value={value} onChange={(e) => onChange(e.target.value)} disabled={disabled} aria-label={label}>
      <option value="">Seçilmedi</option>
      {meta.platforms.map((p) => <option key={p.key} value={p.key}>{p.label}</option>)}
    </select>
  );
}

function AccountRow({ a, meta, onSaved }: { a: Account; meta: ChannelsMeta; onSaved: (started: boolean) => void }) {
  const [choice, setChoice] = useState(a.platform ?? '');
  const save = useMutation({
    mutationFn: (b: { platform?: string | null; onay?: boolean }) => channelsApi.setAccount(a.cariKodu, b),
    onSuccess: (r) => onSaved(r.okumaBasladi),
    onError: (e) => toast.error(errText(e, 'Eşleme kaydedilemedi.') ?? ''),
  });
  const probs = a.aday?.olasiliklar ?? {};
  const top = Object.entries(probs).sort((x, y) => y[1] - x[1]).slice(0, 2);
  const can = meta.me.canMap;
  return (
    <tr className="border-t border-slate-100">
      <td className={`${td} max-w-[300px]`}>
        <div className="font-semibold">{a.unvan || a.cariKodu}</div>
        <div className="font-mono text-[11px] text-canvas-muted">{a.cariKodu}{a.kanal ? ` · ${a.kanal}` : ''}</div>
        {a.crmAd && a.crmAd !== a.unvan && <div className="text-[11px] text-canvas-muted">CRM: {a.crmAd}</div>}
      </td>
      <td className={td}>
        <Pill tone={DURUM[a.durum].tone}>{DURUM[a.durum].label}</Pill>
        {a.platform && <div className="mt-1 text-[12px] font-bold">{platformName(meta, a.platform)}</div>}
        {a.yontem && <div className="text-[11px] text-canvas-muted">{YONTEM[a.yontem] ?? a.yontem}{a.olasilik !== null ? ` · olasılık ${fmtPct(a.olasilik, 0)}` : ''}</div>}
        {a.durum === 'bekliyor' && a.aday && a.aday.emin === false && top.length > 0 && (
          <div className="text-[11px] text-canvas-muted">Zeki AI emin değil; en olası: {top.map(([k, v]) => `${platformName(meta, k)} ${fmtPct(v, 0)}`).join(', ')}</div>
        )}
        {a.onaylayan && <div className="text-[11px] text-canvas-muted">{a.onaylayan} · {fmtDay(a.onayTarihi)}</div>}
      </td>
      <td className={td}>
        {can ? (
          <div className="flex flex-wrap items-center gap-2">
            <PlatformSelect meta={meta} value={choice} onChange={setChoice} disabled={save.isPending} label={`${a.cariKodu} platformu`} />
            <button type="button" className={btnPrimary} disabled={!choice || save.isPending || (a.durum === 'onayli' && choice === a.platform)}
              onClick={() => save.mutate({ platform: choice, onay: true })}>
              {a.durum === 'aday' && choice === a.platform ? 'Adayı onayla' : 'Kaydet'}
            </button>
            {a.durum !== 'bekliyor' && (
              <button type="button" className={btnGhost} disabled={save.isPending} onClick={() => { setChoice(''); save.mutate({ platform: null, onay: false }); }}>Eşlemeyi kaldır</button>
            )}
          </div>
        ) : <span className="text-[12px] text-canvas-muted">Eşleme yetkisi yok</span>}
      </td>
    </tr>
  );
}

function Cariler({ meta }: { meta: ChannelsMeta }) {
  const qc = useQueryClient();
  const [params, setParams] = useSearchParams();
  const durum = params.get('durum') ?? 'aday';
  const [q, setQ] = useState('');
  const r = useQuery({ queryKey: ['channels', 'accounts'], queryFn: channelsApi.accounts, enabled: ENGINE_ENABLED });
  const propose = useMutation({
    mutationFn: () => channelsApi.propose(),
    onSuccess: (o) => {
      qc.invalidateQueries({ queryKey: ['channels', 'accounts'] });
      toast.success(`Aday: unvandan ${o.ad}, Zeki AI ${o.zeki}; emin olunmayan ${o.eminDegil}${o.kalan ? `, kalan ${o.kalan} (sonraki tur)` : ''}.`);
    },
    onError: (e) => toast.error(errText(e, 'Aday üretilemedi.') ?? ''),
  });
  const items = useMemo(() => {
    const all = r.data?.items ?? [];
    const f = foldTr(q.trim());
    return all.filter((a) => (!durum || a.durum === durum) && (!f || foldTr(`${a.cariKodu} ${a.unvan ?? ''} ${a.crmAd ?? ''}`).includes(f)));
  }, [r.data, durum, q]);
  const saved = (started: boolean) => {
    qc.invalidateQueries({ queryKey: ['channels'] });
    toast.success(started ? 'Eşleme kaydedildi; yeni carinin satışları Logo\'dan okunuyor.' : 'Eşleme kaydedildi.');
  };
  const counts = r.data?.counts ?? {};
  return (
    <Panel>
      <div className="mb-2 flex flex-wrap items-end justify-between gap-2">
        <div className="min-w-0">
          <h2 className="flex items-center gap-1 text-[15px] font-extrabold">E-ticaret carileri <SqlInfo k={r.data?.kaynaklar} alan="items" label="E-ticaret carileri: durum sayıları, olasılık" /></h2>
          <p className="text-[12px] text-canvas-muted">
            Logo’da kanal kodu {r.data?.specodes.join(', ') ?? '…'} olan cariler (her gece güncellenir) ve elle eşlenenler. «Aday üret», unvanında platform adı geçen carilere ya da Zeki AI’ın tahminine göre platform önerir; öneri siz onaylayana kadar hesaba girmez.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          {meta.me.canMap && (
            <button type="button" className={btnGhost} onClick={() => propose.mutate()} disabled={propose.isPending}>
              {propose.isPending ? <Loader2 aria-hidden className="h-4 w-4 animate-spin" /> : <Sparkles aria-hidden className="h-4 w-4" />}
              Aday üret
            </button>
          )}
          {meta.me.canExport && (
            <a className={btnGhost} href={channelsApi.exportUrl('eslesme')} download>
              <Download aria-hidden className="h-4 w-4" />
              Excel indir
            </a>
          )}
        </div>
      </div>
      <div className="mb-2 grid grid-cols-1 gap-2 sm:grid-cols-[auto_1fr]">
        <div className="flex items-center gap-1">
        <div className="flex min-w-0 flex-1 gap-1 overflow-x-auto rounded-xl bg-slate-100 p-1">
          {([['aday', 'Onay bekleyen'], ['bekliyor', 'Aday yok'], ['onayli', 'Onaylı'], ['', 'Hepsi']] as const).map(([k, l]) => (
            <button key={k || 'hepsi'} type="button" onClick={() => { const p = new URLSearchParams(params); if (k) p.set('durum', k); else p.set('durum', ''); setParams(p, { replace: true }); }}
              className={`min-h-9 shrink-0 whitespace-nowrap rounded-lg px-2.5 text-[12px] font-extrabold transition-colors duration-150 ${durum === k ? 'bg-white shadow-sm' : 'text-canvas-muted'}`}>
              {l}{k && counts[k] !== undefined ? ` (${counts[k]})` : ''}
            </button>
          ))}
        </div>
        <Explain label="Eşleme durumları" title="Durumlar ne demek?">
          <span className="block"><b>Onay bekleyen (Aday):</b> bir platform önerildi, bir yetkilinin onaylaması gerekiyor.</span>
          <span className="block"><b>Aday yok:</b> henüz öneri çıkmadı ya da Zeki AI emin olamadı; platformu siz seçin.</span>
          <span className="block"><b>Onaylı:</b> cari bu platforma bağlı; satışları karnede o platformda sayılır.</span>
        </Explain>
        </div>
        <input className={field} placeholder="Ara: cari kodu, unvan ya da CRM adı" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Cari ara" />
      </div>
      {r.data?.cards.crmError && <Note tone="warn">CRM okunamadı ({r.data.cards.crmError}); CRM adları eksik.</Note>}
      {r.isLoading ? <Loading /> : r.error ? <Note tone="err">{errText(r.error, 'Eşleme listesi açılamadı.')}</Note> : !items.length ? (
        r.data?.items.length ? (
          <EmptyHint
            title={durum === 'aday' && !q.trim() ? 'Onay bekleyen cari yok' : 'Bu süzgeçte cari yok'}
            why={durum === 'aday' && !q.trim() ? 'Önerilen bütün eşlemeler karara bağlanmış. Yeni cariler için «Aday üret» düğmesini kullanabilirsiniz.' : 'Başka bir durum seçin ya da aramayı temizleyin.'}
          />
        ) : (
          <EmptyHint title="Cari listesi henüz okunmadı" why="E-ticaret carileri Logo’dan henüz okunmamış. Üstteki «Veriyi yenile» düğmesiyle okumayı başlatın." />
        )
      ) : (
        <TableWrap>
          <thead><tr><th className={th}>Cari</th><th className={th}>Durum</th><th className={th}>Platform</th></tr></thead>
          <tbody>{items.map((a) => <AccountRow key={`${a.cariKodu}:${a.platform}:${a.durum}`} a={a} meta={meta} onSaved={saved} />)}</tbody>
        </TableWrap>
      )}
    </Panel>
  );
}

function KanalCodes({ meta }: { meta: ChannelsMeta }) {
  const qc = useQueryClient();
  const r = useQuery({ queryKey: ['channels', 'kanal-codes'], queryFn: channelsApi.kanalCodes, enabled: ENGINE_ENABLED });
  const save = useMutation({
    mutationFn: ({ kod, platform }: { kod: string; platform: string | null }) => channelsApi.setKanalCode(kod, platform),
    onSuccess: (o) => {
      qc.invalidateQueries({ queryKey: ['channels'] });
      toast.success(o.okumaBasladi ? 'Kaydedildi; bu kanal kodunun satışları okunuyor.' : 'Kaydedildi.');
    },
    onError: (e) => toast.error(errText(e, 'Kaydedilemedi.') ?? ''),
  });
  return (
    <Panel>
      <h2 className="flex items-center gap-1 text-[15px] font-extrabold">Kanal kodu ile eşleme <SqlInfo k={r.data?.kaynaklar} alan="items" label="Kanal kodu net cirosu" /></h2>
      <p className="mb-2 text-[12px] text-canvas-muted">
        Kanal kodu, Logo cari kartındaki satış kanalı işaretidir. Tek tek eşlenemeyecek kadar çok carisi olan bir kanal (ör. sitenin bireysel müşterileri) buradan bütünüyle bir platforma bağlanır; o koddaki bütün cariler tek satırda toplanır.
        Bir cari «Cariler» sekmesinde ayrıca eşlendiyse o eşleme geçerli olur. Net ciro {r.data?.yil ?? '—'} yılı.
      </p>
      {r.isLoading ? <Loading /> : r.error ? <Note tone="err">{errText(r.error, 'Kanal kodları okunamadı.')}</Note> : (
        <TableWrap>
          <thead><tr><th className={th}>Kanal kodu</th><th className={`${th} text-right`}><InfoLabel k={r.data?.kaynaklar} alan="items">Net ciro</InfoLabel></th><th className={th}>Platform</th></tr></thead>
          <tbody>
            {(r.data?.items ?? []).map((k) => (
              <tr key={k.kod} className="border-t border-slate-100">
                <td className={`${td} font-semibold`}>{k.kod === '#YOK' ? 'Kodsuz' : k.kod}{k.eticaret && <span className="ml-1.5"><Pill tone="violet">e-ticaret listesi</Pill></span>}</td>
                <td className={`${td} text-right font-mono tabular-nums`}>{fmtMoney(k.netCiro)}</td>
                <td className={td}>
                  {meta.me.canMap && k.kod !== '#YOK' ? (
                    <PlatformSelect meta={meta} value={k.platform ?? ''} label={`${k.kod} platformu`} disabled={save.isPending}
                      onChange={(v) => save.mutate({ kod: k.kod, platform: v || null })} />
                  ) : (k.platform ? platformName(meta, k.platform) : '—')}
                </td>
              </tr>
            ))}
          </tbody>
        </TableWrap>
      )}
    </Panel>
  );
}

function Regions({ meta }: { meta: ChannelsMeta }) {
  const qc = useQueryClient();
  const r = useQuery({ queryKey: ['channels', 'regions'], queryFn: channelsApi.regions, enabled: ENGINE_ENABLED });
  const save = useMutation({
    mutationFn: ({ kod, platform }: { kod: string; platform: string | null }) => channelsApi.setRegion(kod, platform),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['channels'] });
      toast.success('Hedef bölgesi kaydedildi.');
    },
    onError: (e) => toast.error(errText(e, 'Kaydedilemedi.') ?? ''),
  });
  return (
    <Panel>
      <h2 className="flex items-center gap-1 text-[15px] font-extrabold">CRM satış hedefi bölgeleri <SqlInfo k={r.data?.kaynaklar} alan="items" label="CRM satış hedefi bölgeleri" /></h2>
      <p className="mb-2 text-[12px] text-canvas-muted">CRM'deki satış hedefi bölgesi (D&amp;R, Hepsiburada, Kitapyurdu, B2C …) hangi platformun hedefi? Karnede «CRM hedef gerçekleşme» bu eşlemeyle hesaplanır.</p>
      {r.data?.crmError && <Note tone="warn">CRM okunamadı: {r.data.crmError}</Note>}
      {r.isLoading ? <Loading /> : r.error ? <Note tone="err">{errText(r.error, 'Bölgeler okunamadı.')}</Note> : !r.data?.items.length ? (
        <EmptyHint title="CRM satış hedefleri henüz okunmadı" why="Üstteki «Veriyi yenile» düğmesiyle okumayı başlatın; hedef bölgeleri okunduktan sonra burada listelenir." />
      ) : (
        <TableWrap>
          <thead><tr><th className={th}>Bölge</th><th className={`${th} text-right`}><InfoLabel k={r.data?.kaynaklar} alan="items">Yıllık hedef (adet)</InfoLabel></th><th className={th}>Platform</th></tr></thead>
          <tbody>
            {r.data.items.map((b) => (
              <tr key={b.kod} className="border-t border-slate-100">
                <td className={td}>
                  <div className="font-semibold">{b.ad}</div>
                  <div className="text-[11px] text-canvas-muted">kod {b.kod}{b.yil ? ` · ${b.yil}` : ''}{!b.platform && b.aday ? ` · öneri: ${platformName(meta, b.aday)}` : ''}</div>
                </td>
                <td className={`${td} text-right font-mono tabular-nums`}>{b.yillik.toLocaleString('tr-TR')}</td>
                <td className={td}>
                  {meta.me.canMap ? (
                    <PlatformSelect meta={meta} value={b.platform ?? ''} label={`${b.ad} platformu`} disabled={save.isPending}
                      onChange={(v) => save.mutate({ kod: b.kod, platform: v || null })} />
                  ) : (b.platform ? platformName(meta, b.platform) : '—')}
                </td>
              </tr>
            ))}
          </tbody>
        </TableWrap>
      )}
    </Panel>
  );
}

export default function Accounts() {
  const meta = useChannelsMeta();
  const m = meta.data;
  const [params, setParams] = useSearchParams();
  const section: Section = (SECTIONS.find((s) => s.key === params.get('bolum'))?.key ?? 'cariler') as Section;
  return (
    <ChannelsFrame
      title="Cari eşleme"
      lead="Logo’daki hangi carinin hangi pazar yerine (Trendyol, Amazon, Hepsiburada…) ait olduğunu burada belirlersiniz; kanal ekranlarındaki bütün rakamlar bu eşlemeye göre toplanır. Eşleme yalnız portalda tutulur; CRM'e ve Logo'ya yazılmaz."
    >
      <DataBar meta={m} yil={m?.defaultYear ?? undefined} />
      <Tabs tabs={SECTIONS} value={section} onChange={(k) => { const p = new URLSearchParams(params); p.set('bolum', k); setParams(p, { replace: true }); }} />
      {m && section === 'cariler' && <Cariler meta={m} />}
      {m && section === 'kanal' && <KanalCodes meta={m} />}
      {m && section === 'bolge' && <Regions meta={m} />}
    </ChannelsFrame>
  );
}
