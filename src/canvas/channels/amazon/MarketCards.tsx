import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Sparkles } from 'lucide-react';
import { ENGINE_ENABLED } from '../../engine';
import { Loading, Note, Pill, TableWrap, btnGhost, btnPrimary, errText, field, fmtDate, label as labelCls, td, th } from '../../admin/ui';
import { Panel } from '../../editorial/kit';
import { fmtInt, fmtPct, parseNum } from '../../budget/api';
import { AskSheet } from '../../budget/parts';
import { amazonApi, type MarketCard, type Params } from './api';
import { AmazonData, AmazonFrame, tl, useAmazonMeta } from './parts';
import SqlInfo, { InfoLabel } from '../../components/SqlInfo';
import { EmptyHint, Explain } from '../../components/Explain';
import { ShowMoreButton, useShowMore } from '../../components/ShowMore';

const EMPTY = { pazar: '', ad: '', ulkeler: '', doviz: '', kurKaynagi: '', kdvOrani: '', kargoBirim: '', komisyonOrani: '', not: '' };
const pct = (v: string) => { const n = parseNum(v); return n === null ? null : n / 100; };

function ParamsPanel({ canParam }: { canParam: boolean }) {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ['amazon', 'params'], queryFn: amazonApi.params, enabled: ENGINE_ENABLED, retry: false });
  const [f, setF] = useState(EMPTY);
  const save = useMutation({
    mutationFn: () => amazonApi.setParams(f.pazar, {
      ad: f.ad, ulkeler: f.ulkeler.split(',').map((x) => x.trim()).filter(Boolean), doviz: f.doviz || null, kurKaynagi: f.kurKaynagi || null,
      kdvOrani: pct(f.kdvOrani), kargoBirim: parseNum(f.kargoBirim), komisyonOrani: pct(f.komisyonOrani), not: f.not || null,
    }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['amazon', 'params'] });
      setF(EMPTY);
      toast.success('Parametre kaydedildi.');
    },
    onError: (e) => toast.error(errText(e, 'Kaydedilemedi.') ?? ''),
  });
  const edit = (p: Params) => setF({
    pazar: p.pazar, ad: p.ad, ulkeler: p.ulkeler.join(', '), doviz: p.doviz ?? '', kurKaynagi: p.kurKaynagi ?? '',
    kdvOrani: p.kdvOrani === null ? '' : String(p.kdvOrani * 100), kargoBirim: p.kargoBirim === null ? '' : String(p.kargoBirim),
    komisyonOrani: p.komisyonOrani === null ? '' : String(p.komisyonOrani * 100), not: p.not ?? '',
  });
  const inp = (k: keyof typeof EMPTY, lbl: string, ph = '') => (
    <label className="flex flex-col gap-1"><span className={labelCls}>{lbl}</span><input className={field} value={f[k]} placeholder={ph} onChange={(e) => setF((x) => ({ ...x, [k]: e.target.value }))} /></label>
  );
  return (
    <Panel>
      <h2 className="flex items-center gap-1 text-[15px] font-extrabold">Pazar parametreleri (finans) <SqlInfo k={q.data?.kaynaklar} alan="items" label="Pazar parametreleri (finans)" /></h2>
      <p className="mb-2 text-[12px] text-canvas-muted">Finans ekibinin her pazar için girdiği varsayımlar: hangi kur kullanılır, KDV, birim kargo ve pazar yeri komisyonu. Değerlendirme kartlarında olduğu gibi yazılır. «Logo ülke yazımları», o ülkenin Logo cari kartlarında nasıl yazıldığıdır (virgülle ayırın).</p>
      {q.isLoading ? <Loading /> : q.error ? <Note tone="err">{errText(q.error, 'Parametreler açılamadı.')}</Note> : !(q.data?.items ?? []).length ? (
        <EmptyHint title="Henüz pazar parametresi girilmemiş" why={canParam ? 'Aşağıdaki alanlarla ilk pazarın varsayımlarını girin; kartlar bu varsayımlarla hazırlanır.' : 'Finans ekibi varsayımları girdiğinde burada listelenir.'} />
      ) : (
        <TableWrap>
          <thead><tr><th className={th}>Pazar</th><th className={th}>Ülkeler</th><th className={th}>Kur</th><th className={`${th} text-right`}><InfoLabel k={q.data?.kaynaklar} alan="items">KDV</InfoLabel></th><th className={`${th} text-right`}><InfoLabel k={q.data?.kaynaklar} alan="items">Kargo</InfoLabel></th><th className={`${th} text-right`}><InfoLabel k={q.data?.kaynaklar} alan="items">Komisyon</InfoLabel></th><th className={th}><span className="sr-only">İşlem</span></th></tr></thead>
          <tbody>
            {(q.data?.items ?? []).map((p) => (
              <tr key={p.pazar} className="border-t border-slate-100">
                <td className={td}><div className="font-semibold">{p.pazar}</div><div className="text-[11px] text-canvas-muted">{p.ad}</div></td>
                <td className={td}>{p.ulkeler.join(', ') || '—'}</td>
                <td className={`${td} text-[12px]`}>{[p.doviz, p.kurKaynagi].filter(Boolean).join(' · ') || '—'}</td>
                <td className={`${td} text-right font-mono tabular-nums`}>{fmtPct(p.kdvOrani)}</td>
                <td className={`${td} text-right font-mono tabular-nums`}>{p.kargoBirim ?? '—'}</td>
                <td className={`${td} text-right font-mono tabular-nums`}>{fmtPct(p.komisyonOrani)}</td>
                <td className={`${td} text-right`}>{canParam && <button type="button" className={btnGhost} onClick={() => edit(p)}>Düzenle</button>}</td>
              </tr>
            ))}
          </tbody>
        </TableWrap>
      )}
      {canParam && (
        <div className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-4">
          {inp('pazar', 'Pazar kodu', 'DE')}
          {inp('ad', 'Ad', 'Almanya')}
          {inp('ulkeler', 'Logo ülke yazımları', 'ALMANYA, GERMANY')}
          {inp('doviz', 'Döviz', 'EUR')}
          {inp('kurKaynagi', 'Kur kaynağı', 'Logo günlük kur')}
          {inp('kdvOrani', 'KDV (%)', '7')}
          {inp('kargoBirim', 'Birim kargo (TL)')}
          {inp('komisyonOrani', 'Pazar yeri komisyonu (%)')}
          <div className="sm:col-span-2 lg:col-span-4">
            <button type="button" className={btnPrimary} onClick={() => save.mutate()} disabled={save.isPending || !f.pazar.trim() || !f.ad.trim()}>Parametreyi kaydet</button>
            <span className="ml-2 text-[11.5px] text-canvas-muted">Pazar kodu ve ad zorunlu. Aynı pazar kodu yeniden kaydedilirse eskisinin yerine geçer.</span>
          </div>
        </div>
      )}
    </Panel>
  );
}

function Card({ c, canDecide, me, decisions }: { c: MarketCard; canDecide: boolean; me: string; decisions: Record<string, string> }) {
  const qc = useQueryClient();
  const [ask, setAsk] = useState<string | null>(null);
  const books = useShowMore(c.gostergeler.kitaplar, 5);
  const decide = useMutation({
    mutationFn: ({ karar, not }: { karar: string; not?: string }) => amazonApi.decideCard(c.id, karar, not),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['amazon', 'cards'] });
      setAsk(null);
      toast.success('Karar kaydedildi.');
    },
    onError: (e) => toast.error(errText(e, 'Karar kaydedilemedi.') ?? ''),
  });
  const g = c.gostergeler;
  return (
    <div className="rounded-2xl bg-white/70 p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="font-extrabold">{c.pazar} · {g.ulkeler.join(', ')}</div>
        <Pill tone={c.karar === 'girilsin' ? 'ok' : c.karar ? 'muted' : 'violet'}>{c.kararAd ?? 'Karar bekliyor'}</Pill>
      </div>
      <div className="text-[12px] text-canvas-muted">{c.hazirlayan} · {fmtDate(c.tarih)}{c.kararVeren && ` · karar: ${c.kararVeren}`}{c.kararNotu && ` — ${c.kararNotu}`}</div>
      <div className="mt-2 grid grid-cols-1 gap-2 text-[12.5px] sm:grid-cols-3">
        <div>
          <div className={labelCls}>Yurtdışı faturalı satış</div>
          {Object.entries(g.yillar).map(([y, v]) => <div key={y} className="font-mono tabular-nums">{y}: {tl(v.netCiro)} · {fmtInt(v.netAdet)} adet</div>)}
          <div>{fmtInt(g.cariSayisi)} cari</div>
        </div>
        <div>
          <div className={labelCls}>Haklar ve kitaplar</div>
          <div>Hak satılmış kitap: {fmtInt(g.hakSatilanKitap)}</div>
          <div className="mt-0.5 text-[11px] font-semibold text-canvas-muted">Bu ülkelerde en çok satanlar:</div>
          <div className="text-[11.5px] text-canvas-muted">{books.shown.map((k) => k.ad || k.stokKodu).join(' · ') || '—'}</div>
          <ShowMoreButton more={books} noun="kitap" />
        </div>
        <div>
          <div className={labelCls}>Varsayımlar</div>
          {g.parametre ? (
            <div>KDV {fmtPct(g.parametre.kdvOrani)} · komisyon {fmtPct(g.parametre.komisyonOrani)} · kargo {g.parametre.kargoBirim ?? '—'} · kur {g.parametre.kurKaynagi ?? '—'}</div>
          ) : <div className="text-amber-800">Finans parametresi girilmemiş.</div>}
        </div>
      </div>
      {c.gerekce && <p className="mt-2 rounded-xl bg-violet-50 p-2 text-[12.5px]">{c.gerekce}</p>}
      {c.not && <p className="mt-1 text-[12px]">Not: {c.not}</p>}
      <p className="mt-1 text-[11px] text-canvas-muted">{g.not}</p>
      {canDecide && !c.karar && c.hazirlayan.toLowerCase() !== me.toLowerCase() && (
        <div className="mt-2 flex flex-wrap gap-2">
          <button type="button" className={btnPrimary} disabled={decide.isPending} onClick={() => decide.mutate({ karar: 'girilsin' })}>{decisions.girilsin}</button>
          <button type="button" className={btnGhost} onClick={() => setAsk('bekle')}>{decisions.bekle}</button>
          <button type="button" className={btnGhost} onClick={() => setAsk('girilmesin')}>{decisions.girilmesin}</button>
        </div>
      )}
      <AskSheet open={!!ask} title={ask ? decisions[ask] : ''} message="Gerekçe kartı hazırlayana görünür." confirm="Kaydet" input="Gerekçe" required
        busy={decide.isPending} onClose={() => setAsk(null)} onConfirm={(t) => ask && decide.mutate({ karar: ask, not: t })} />
    </div>
  );
}

export default function AmazonMarketCards() {
  const meta = useAmazonMeta();
  const m = meta.data;
  const qc = useQueryClient();
  const cards = useQuery({ queryKey: ['amazon', 'cards'], queryFn: amazonApi.cards, enabled: ENGINE_ENABLED });
  const [form, setForm] = useState({ pazar: '', ulkeler: '', not: '' });
  const create = useMutation({
    mutationFn: () => amazonApi.createCard({ pazar: form.pazar, ulkeler: form.ulkeler.split(',').map((x) => x.trim()).filter(Boolean), not: form.not || undefined }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['amazon', 'cards'] });
      setForm({ pazar: '', ulkeler: '', not: '' });
      toast.success('Değerlendirme kartı hazır; karar bekliyor.');
    },
    onError: (e) => toast.error(errText(e, 'Kart açılamadı.') ?? ''),
  });
  return (
    <AmazonFrame
      title="Pazar değerlendirmesi"
      lead="Yeni bir yurtdışı pazara (ör. Almanya) girilip girilmeyeceğini değerlendirmek için kart: o ülkelere şimdiye kadarki satışımız, sattığımız haklar ve finansın maliyet varsayımları. Zeki AI kısa gerekçe yazar; kararı kartı hazırlayandan başka bir yetkili verir."
    >
      <AmazonData meta={m} />
      {m?.me.canDraft && (
        <Panel>
          <h2 className="flex items-center gap-1 text-[15px] font-extrabold">Yeni kart</h2>
          <p className="mb-2 text-[12px] text-canvas-muted">Pazar kodunu ve o pazarın ülke(ler)ini Logo cari kartındaki yazımla girin; birden çok ülkeyi virgülle ayırın.</p>
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-[0.6fr_1.4fr_1.4fr_auto] sm:items-end">
            <label className="flex flex-col gap-1"><span className={labelCls}>Pazar</span><input className={field} value={form.pazar} placeholder="ör. DE" onChange={(e) => setForm((f) => ({ ...f, pazar: e.target.value }))} /></label>
            <label className="flex flex-col gap-1"><span className={labelCls}>Ülkeler (Logo yazımı)</span><input className={field} value={form.ulkeler} placeholder="ör. ALMANYA, GERMANY" onChange={(e) => setForm((f) => ({ ...f, ulkeler: e.target.value }))} /></label>
            <label className="flex flex-col gap-1"><span className={labelCls}>Not (isteğe bağlı)</span><input className={field} value={form.not} placeholder="ör. fuar görüşmesinden sonra" onChange={(e) => setForm((f) => ({ ...f, not: e.target.value }))} /></label>
            <button type="button" className={btnPrimary} onClick={() => create.mutate()} disabled={create.isPending || !form.pazar.trim() || !form.ulkeler.trim()}>
              <Sparkles aria-hidden className="h-4 w-4" />Kart hazırla
            </button>
          </div>
        </Panel>
      )}
      <Panel>
        <h2 className="flex items-center gap-1 mb-2 text-[15px] font-extrabold">
          Kartlar <SqlInfo k={cards.data?.kaynaklar} alan="items" label="Kartlar" />
          <Explain label="Kararlar" title="Karar nasıl verilir?">
            Kartı hazırlayan dışındaki bir yetkili «Pazara girilsin», «Bekle / yeniden değerlendir» ya da «Girilmesin» der. «Bekle» ve «Girilmesin» için gerekçe yazmak zorunludur. Karar yalnız portalda kayıt olur, Amazon'a bir şey gönderilmez.
          </Explain>
        </h2>
        {cards.error && <Note tone="err">{errText(cards.error, 'Kartlar açılamadı.')}</Note>}
        {cards.isLoading ? <Loading /> : !cards.data?.items.length ? (
          <EmptyHint title="Henüz değerlendirme kartı yok" why={m?.me.canDraft ? 'Yukarıdaki «Yeni kart» alanından bir pazar için ilk kartı hazırlayın.' : 'Kart hazırlama yetkisi olan bir kişi kart açtığında burada görünür.'} />
        ) : (
          <div className="flex flex-col gap-2">
            {cards.data.items.map((c) => <Card key={c.id} c={c} canDecide={!!m?.me.canDecide} me={m?.me.username ?? ''} decisions={cards.data.decisions} />)}
          </div>
        )}
      </Panel>
      <ParamsPanel canParam={!!m?.me.canParam} />
    </AmazonFrame>
  );
}
