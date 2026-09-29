import { useState } from 'react';
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Check, Sparkles, X } from 'lucide-react';
import { ENGINE_ENABLED } from '../../engine';
import { Loading, Note, Pill, TableWrap, btnGhost, btnPrimary, errText, field, fmtDate, td, th } from '../../admin/ui';
import { Pager, Panel } from '../../editorial/kit';
import { fmtInt } from '../../budget/api';
import { AskSheet } from '../../budget/parts';
import { BookCell, ExportLink, yesNo } from '../platformKit';
import { trendyolApi, type Suggestion } from './api';
import { TrendyolData, TrendyolFrame, useTrendyolMeta } from './parts';
import SqlInfo, { InfoLabel } from '../../components/SqlInfo';
import { EmptyHint, Explain } from '../../components/Explain';

const STATE: Record<Suggestion['durum'], { label: string; tone: 'violet' | 'ok' | 'err' }> = {
  taslak: { label: 'Karar bekliyor', tone: 'violet' },
  onayli: { label: 'Onaylandı', tone: 'ok' },
  red: { label: 'Reddedildi', tone: 'err' },
};

function Suggestions({ canDecide, me }: { canDecide: boolean; me: string }) {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ['trendyol', 'suggestions'], queryFn: trendyolApi.suggestions, enabled: ENGINE_ENABLED });
  const [reject, setReject] = useState<string | null>(null);
  const decide = useMutation({
    mutationFn: ({ id, karar, not }: { id: string; karar: 'onayli' | 'red'; not?: string }) => trendyolApi.decide(id, karar, not),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['trendyol', 'suggestions'] });
      setReject(null);
      toast.success('Karar kaydedildi. Vitrini mağaza panelinden siz düzenlersiniz.');
    },
    onError: (e) => toast.error(errText(e, 'Karar kaydedilemedi.') ?? ''),
  });
  const items = q.data?.items ?? [];
  return (
    <Panel>
      <h2 className="flex items-center gap-1 text-[15px] font-extrabold">Öneriler <SqlInfo k={q.data?.kaynaklar} alan="items" label="Öneriler" /></h2>
      <p className="mb-2 text-[12px] text-canvas-muted">Hazırlanan vitrin önerileri ve kararları. Onay yalnız portalda kayıt olur, Trendyol'a gönderilmez; vitrini mağaza panelinden siz düzenlersiniz. Öneriyi hazırlayan kişi kendi önerisini onaylayamaz.</p>
      {q.isLoading ? <Loading /> : !items.length ? (
        <EmptyHint title="Henüz vitrin önerisi yok" why="Yukarıdaki listeden kitapları işaretleyip «öneri taslağı hazırla» düğmesiyle ilk öneriyi oluşturabilirsiniz." />
      ) : (
        <div className="flex flex-col gap-2">
          {items.map((s) => (
            <div key={s.id} className="rounded-2xl bg-white/70 p-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="font-extrabold">{s.baslik}</div>
                <Pill tone={STATE[s.durum].tone}>{STATE[s.durum].label}</Pill>
              </div>
              <div className="mt-1 text-[12px] text-canvas-muted">{s.olusturan} · {fmtDate(s.olusturma)}{s.kararVeren && ` · karar: ${s.kararVeren}`}{s.kararNotu && ` — ${s.kararNotu}`}</div>
              <div className="mt-1 text-[12.5px]">{(s.payload.kitaplar ?? []).map((k) => k.ad || k.stokKodu).join(' · ')}</div>
              {s.payload.not && <div className="mt-1 text-[12px]">Not: {s.payload.not}</div>}
              {s.gerekce && <p className="mt-1 rounded-xl bg-violet-50 p-2 text-[12.5px]">{s.gerekce}</p>}
              {canDecide && s.durum === 'taslak' && s.olusturan.toLowerCase() !== me.toLowerCase() && (
                <div className="mt-2 flex gap-2">
                  <button type="button" className={btnPrimary} disabled={decide.isPending} onClick={() => decide.mutate({ id: s.id, karar: 'onayli' })}><Check aria-hidden className="h-4 w-4" />Onayla</button>
                  <button type="button" className={btnGhost} onClick={() => setReject(s.id)}><X aria-hidden className="h-4 w-4" />Reddet</button>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
      <AskSheet open={!!reject} title="Öneriyi reddet" message="Ret gerekçesi öneriyi hazırlayana görünür." confirm="Reddet" danger input="Gerekçe" required
        busy={decide.isPending} onClose={() => setReject(null)} onConfirm={(t) => reject && decide.mutate({ id: reject, karar: 'red', not: t })} />
    </Panel>
  );
}

export default function TrendyolShowcase() {
  const meta = useTrendyolMeta();
  const m = meta.data;
  const qc = useQueryClient();
  const [page, setPage] = useState(0);
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const [note, setNote] = useState('');
  const r = useQuery({ queryKey: ['trendyol', 'showcase', page], queryFn: () => trendyolApi.showcase({ page }), enabled: ENGINE_ENABLED, placeholderData: keepPreviousData });
  const d = r.data;
  const suggest = useMutation({
    mutationFn: () => trendyolApi.suggest([...picked], note || undefined),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['trendyol', 'suggestions'] });
      setPicked(new Set());
      setNote('');
      toast.success('Öneri taslağı kaydedildi; karar bekliyor.');
    },
    onError: (e) => toast.error(errText(e, 'Öneri kaydedilemedi.') ?? ''),
  });
  const toggle = (code: string) => setPicked((s) => {
    const n = new Set(s);
    if (n.has(code)) n.delete(code);
    else n.add(code);
    return n;
  });
  return (
    <TrendyolFrame
      title="Vitrin önerisi"
      lead="Trendyol vitrininde (öne çıkan ürünler) yer almaya en uygun kitaplar: Trendyol'da hızlı satan ve depoda uzun süre yetecek stoğu olanlar önde. Kitapları seçip öneri hazırlarsınız; kararı bir yetkili verir."
    >
      <TrendyolData meta={m} />
      <Panel>
        <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
          <p className="text-[12px] text-canvas-muted">
            {d ? <>Satış hızı, sipariş dosyasındaki son {d.pencereGun} günden (son gün {d.veriSonu ?? '—'}) hesaplanır. Yalnız depo stoğu en az {fmtInt(d.minStok)} olan kitaplar listelenir.</> : '…'}
          </p>
          <ExportLink show={!!m?.me.canExport} href={trendyolApi.exportUrl('vitrin')} />
        </div>
        {r.error && <Note tone="err">{errText(r.error, 'Adaylar açılamadı.')}</Note>}
        {r.isLoading ? <Loading /> : d && (!d.total ? (
          <EmptyHint title="Vitrin adayı yok" why="Ya sipariş dosyası yüklenmemiş ya da son dönemde Trendyol'da satan kitapların hiçbirinin depo stoğu alt sınırı geçmiyor. «Dosya yükle» sekmesinden güncel sipariş dosyasını yükleyin." />
        ) : (
          <>
            <TableWrap>
              <thead><tr>{m?.me.canDraft && <th className={th}><span className="sr-only">Seç</span></th>}<th className={th}>Kitap</th><th className={`${th} text-right`}><span className="inline-flex items-center gap-1"><InfoLabel k={d?.kaynaklar} alan="items">Haftalık</InfoLabel><Explain label="Haftalık">Trendyol'da haftada ortalama satılan adet.</Explain></span></th><th className={`${th} text-right`}><InfoLabel k={d?.kaynaklar} alan="items">Depo</InfoLabel></th><th className={`${th} text-right`}><span className="inline-flex items-center gap-1"><InfoLabel k={d?.kaynaklar} alan="items">Kaç hafta</InfoLabel><Explain label="Kaç hafta">Depodaki stok, bugünkü satış hızıyla kaç hafta yeter. Vitrine çıkan kitap daha hızlı satacağı için stoğu uzun yetenler önde.</Explain></span></th><th className={th}>Trendyol'da açık</th></tr></thead>
              <tbody>
                {d.items.map((x) => (
                  <tr key={x.stokKodu} className="border-t border-slate-100">
                    {m?.me.canDraft && (
                      <td className={td}>
                        <input type="checkbox" className="h-5 w-5 accent-canvas-violet" aria-label={`${x.ad} seç`} checked={picked.has(x.stokKodu)} onChange={() => toggle(x.stokKodu)} />
                      </td>
                    )}
                    <td className={td}><BookCell name={x.ad} code={x.stokKodu} /></td>
                    <td className={`${td} text-right font-mono tabular-nums`}>{x.haftalik.toLocaleString('tr-TR')}</td>
                    <td className={`${td} text-right font-mono tabular-nums`}>{fmtInt(x.depoStok)}</td>
                    <td className={`${td} text-right font-mono tabular-nums`}>{x.karsilamaHafta ?? '—'}</td>
                    <td className={td}>{yesNo(x.trendyolAcik)}</td>
                  </tr>
                ))}
              </tbody>
            </TableWrap>
            <Pager page={d.page} pageSize={d.pageSize} total={d.total} shown={d.items.length} loading={r.isLoading} fetching={r.isFetching} onPage={setPage} />
          </>
        ))}
        {m?.me.canDraft && picked.size > 0 && (
          <div className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-[1fr_auto] sm:items-end">
            <input className={field} aria-label="Öneri notu" placeholder="Not (isteğe bağlı), ör. Kasım kampanyası için" value={note} onChange={(e) => setNote(e.target.value)} />
            <button type="button" className={btnPrimary} onClick={() => suggest.mutate()} disabled={suggest.isPending}>
              <Sparkles aria-hidden className="h-4 w-4" />
              {picked.size} kitapla öneri taslağı hazırla
            </button>
          </div>
        )}
      </Panel>
      <Suggestions canDecide={!!m?.me.canDecide} me={m?.me.username ?? ''} />
    </TrendyolFrame>
  );
}
