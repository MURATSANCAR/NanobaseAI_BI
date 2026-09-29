import { useState } from 'react';
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Copy, Loader2, Sparkles } from 'lucide-react';
import { ENGINE_ENABLED } from '../../engine';
import { Loading, Note, Pill, TableWrap, btnGhost, errText, field, td, th } from '../../admin/ui';
import { Kpi, KpiRow, Pager, Panel, useDebounced } from '../../editorial/kit';
import { fmtDay, fmtInt } from '../../budget/api';
import { Tabs } from '../../budget/parts';
import { BookCell, Chips, ExportLink } from '../platformKit';
import { trendyolApi } from './api';
import { TrendyolData, TrendyolFrame, useTrendyolMeta } from './parts';
import { ReaderVoicePanel, TopicChip, useVoiceLabels } from '../../signals/ReaderVoice';
import SqlInfo, { InfoLabel } from '../../components/SqlInfo';
import { EmptyHint } from '../../components/Explain';

/** Taslak kutusu: Zeki AI'dan al, kopyala. Gönderim yok; yanıtı kişi panelden verir. */
function Draft({ kind, id, text, canDraft }: { kind: 'questions' | 'reviews'; id: string; text: string | null; canDraft: boolean }) {
  const qc = useQueryClient();
  const get = useMutation({
    mutationFn: () => trendyolApi.draft(kind, id),
    onSuccess: (r) => {
      qc.invalidateQueries({ queryKey: ['trendyol', kind] });
      if (r.dusen) toast.message(`${r.dusen} cümle denetimden geçmediği için çıkarıldı.`);
    },
    onError: (e) => toast.error(errText(e, 'Taslak alınamadı.') ?? ''),
  });
  const copy = () => {
    if (!text) return;
    navigator.clipboard?.writeText(text).then(() => toast.success('Taslak kopyalandı; yanıtı panelden verin.'), () => toast.error('Kopyalanamadı.'));
  };
  return (
    <div className="flex flex-col gap-1.5">
      {text && <p className="rounded-xl bg-violet-50 p-2 text-[12.5px] leading-snug">{text}</p>}
      <div className="flex flex-wrap gap-1.5">
        {canDraft && (
          <button type="button" className={btnGhost} onClick={() => get.mutate()} disabled={get.isPending}>
            {get.isPending ? <Loader2 aria-hidden className="h-4 w-4 animate-spin" /> : <Sparkles aria-hidden className="h-4 w-4" />}
            {text ? 'Taslağı yeniden yaz' : 'Zeki AI ile taslak yaz'}
          </button>
        )}
        {text && (
          <button type="button" className={btnGhost} onClick={copy}>
            <Copy aria-hidden className="h-4 w-4" />
            Taslağı kopyala
          </button>
        )}
      </div>
    </div>
  );
}

function QuestionList({ q, canDraft, canExport }: { q: string; canDraft: boolean; canExport: boolean }) {
  const [only, setOnly] = useState<'cevapsiz' | ''>('cevapsiz');
  const [page, setPage] = useState(0);
  const r = useQuery({ queryKey: ['trendyol', 'questions', only, q, page], queryFn: () => trendyolApi.questions({ cevapsiz: only === 'cevapsiz', q, page }), enabled: ENGINE_ENABLED, placeholderData: keepPreviousData });
  const topics = useVoiceLabels('trendyol-soru');
  const d = r.data;
  return (
    <>
      {d && (
        <KpiRow>
          <Kpi label="Cevapsız" value={fmtInt(d.cevapsiz)} help={`${fmtInt(d.toplam)} sorudan`}
            explain="Yüklenen soru dosyalarında cevaplanmamış görünen sorular. Cevabı Trendyol panelinden verdikten sonra yeni soru dosyasını yüklerseniz bu sayı düşer."
            info={<SqlInfo k={d?.kaynaklar} alan="cevapsiz" label="Cevapsız" />} />
          <Kpi label="Geciken" value={fmtInt(d.geciken)} help={`${d.esikSaat} saati geçen cevapsız`}
            explain="Sorulduğu andan bu yana altta yazan saatten uzun zaman geçmiş cevapsız sorular. Önce bunlara cevap verin."
            info={<SqlInfo k={d?.kaynaklar} alan="geciken" label="Geciken" />} />
          <Kpi label="Durumu bilinmeyen" value={fmtInt(d.bilinmeyen)} help="Dosyada cevap ya da durum kolonu yok"
            explain="Yüklenen dosyada cevaplanıp cevaplanmadığını gösteren kolon bulunmadığı için durumu anlaşılamayan sorular. Panelden cevap ya da durum kolonunu içeren dosyayı indirin."
            info={<SqlInfo k={d?.kaynaklar} alan="bilinmeyen" label="Durumu bilinmeyen" />} />
          <Kpi label="Listede" value={fmtInt(d.total)} help={only ? 'Cevapsız ya da durumu bilinmeyen sorular' : 'Bütün sorular'}
            info={<SqlInfo k={d?.kaynaklar} alan="total" label="Liste" />} />
        </KpiRow>
      )}
      <Panel>
        <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
          <div className="flex min-w-0 items-center gap-1"><Chips value={only} onChange={(v) => { setOnly(v); setPage(0); }} items={[{ key: 'cevapsiz', label: 'Cevapsız' }, { key: '', label: 'Hepsi' }]} />
          <SqlInfo k={d?.kaynaklar} alan="items" label="Sekme sayıları" /></div>
          <ExportLink show={canExport} href={trendyolApi.exportUrl('sorular', { cevapsiz: only === 'cevapsiz', q })} />
        </div>
        {r.error && <Note tone="err">{errText(r.error, 'Sorular açılamadı.')}</Note>}
        {r.isLoading ? <Loading /> : d && (!d.items.length ? (
          d.toplam ? (
            <EmptyHint title={q ? 'Aramaya uyan soru yok' : 'Cevapsız soru yok'} why={q ? 'Aramayı temizleyin ya da «Hepsi» süzgecini seçin.' : 'Yüklenen dosyadaki bütün sorular cevaplanmış görünüyor.'} />
          ) : (
            <EmptyHint title="Soru dosyası yüklenmemiş" why="Trendyol satıcı panelinden müşteri sorularını Excel olarak indirip «Dosya yükle» sekmesinde yükleyin." />
          )
        ) : (
          <>
            <TableWrap>
              <thead><tr><th className={th}>Soru</th><th className={th}>Kitap</th><th className={th}>Yanıt taslağı</th></tr></thead>
              <tbody>
                {d.items.map((x) => (
                  <tr key={x.id} className="border-t border-slate-100">
                    <td className={`${td} max-w-[46ch]`}>
                      <div className="text-[12.5px]">{x.metin}</div>
                      <div className="mt-1 flex flex-wrap items-center gap-1.5 text-[11px] text-canvas-muted">
                        {fmtDay(x.tarih)}
                        <TopicChip label={topics.data?.items[x.id]} />
                        {x.cevaplandi === true ? <Pill tone="ok">Cevaplandı</Pill> : x.gecikti ? <Pill tone="err">{Math.round(x.saat ?? 0)} saattir cevapsız</Pill> : x.cevaplandi === false ? <Pill tone="warn">Cevapsız</Pill> : null}
                      </div>
                    </td>
                    <td className={td}><BookCell name={x.ad} code={x.stokKodu} sub={x.barkod} /></td>
                    <td className={`${td} min-w-[220px]`}><Draft kind="questions" id={x.id} text={x.taslak} canDraft={canDraft} /></td>
                  </tr>
                ))}
              </tbody>
            </TableWrap>
            <Pager page={d.page} pageSize={d.pageSize} total={d.total} shown={d.items.length} loading={r.isLoading} fetching={r.isFetching} onPage={setPage} />
          </>
        ))}
      </Panel>
    </>
  );
}

function ReviewList({ q, canDraft, canExport }: { q: string; canDraft: boolean; canExport: boolean }) {
  const [max, setMax] = useState<'3' | ''>('3');
  const [page, setPage] = useState(0);
  const r = useQuery({ queryKey: ['trendyol', 'reviews', max, q, page], queryFn: () => trendyolApi.reviews({ maxPuan: max ? Number(max) : undefined, q, page }), enabled: ENGINE_ENABLED, placeholderData: keepPreviousData });
  const topics = useVoiceLabels('trendyol-yorum');
  const d = r.data;
  return (
    <>
      <Panel>
        <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
          <div className="flex min-w-0 items-center gap-1"><Chips value={max} onChange={(v) => { setMax(v); setPage(0); }} items={[{ key: '3', label: '3 ve altı', count: d?.dusuk }, { key: '', label: 'Hepsi', count: d?.toplam }]} />
          <SqlInfo k={d?.kaynaklar} alan="items" label="Sekme sayıları" /></div>
          <ExportLink show={canExport} href={trendyolApi.exportUrl('yorumlar', { maxPuan: max || undefined, q })} />
        </div>
        {r.error && <Note tone="err">{errText(r.error, 'Yorumlar açılamadı.')}</Note>}
        {r.isLoading ? <Loading /> : d && (!d.items.length ? (
          d.toplam ? (
            <EmptyHint title={q ? 'Aramaya uyan yorum yok' : 'Düşük puanlı yorum yok'} why={q ? 'Aramayı temizleyin ya da «Hepsi» süzgecini seçin.' : 'Yüklenen yorumların hiçbiri 3 ya da daha düşük puanlı değil.'} />
          ) : (
            <EmptyHint title="Yorum dosyası yüklenmemiş" why="Trendyol satıcı panelinden ürün yorumlarını Excel olarak indirip «Dosya yükle» sekmesinde yükleyin." />
          )
        ) : (
          <>
            <TableWrap>
              <thead><tr><th className={th}>Puan</th><th className={th}>Yorum</th><th className={th}>Kitap</th><th className={th}>Yanıt taslağı</th></tr></thead>
              <tbody>
                {d.items.map((x) => (
                  <tr key={x.id} className="border-t border-slate-100">
                    <td className={`${td} font-mono text-[15px] font-bold tabular-nums`}>{x.puan ?? '—'}</td>
                    <td className={`${td} max-w-[46ch] text-[12.5px]`}>{x.metin ?? '—'}<div className="mt-1 flex flex-wrap items-center gap-1.5 text-[11px] text-canvas-muted">{fmtDay(x.tarih)}<TopicChip label={topics.data?.items[x.id]} /></div></td>
                    <td className={td}><BookCell name={x.ad} code={x.stokKodu} sub={x.barkod} /></td>
                    <td className={`${td} min-w-[220px]`}>{x.metin ? <Draft kind="reviews" id={x.id} text={x.taslak} canDraft={canDraft} /> : '—'}</td>
                  </tr>
                ))}
              </tbody>
            </TableWrap>
            <Pager page={d.page} pageSize={d.pageSize} total={d.total} shown={d.items.length} loading={r.isLoading} fetching={r.isFetching} onPage={setPage} />
          </>
        ))}
      </Panel>
      {d && d.kitaplar.length > 0 && (
        <Panel>
          <h2 className="flex items-center gap-1 text-[15px] font-extrabold">Kitap bazında puan <SqlInfo k={d?.kaynaklar} alan="items" label="Kitap bazında puan" /></h2>
          <TableWrap>
            <thead><tr><th className={th}>Kitap</th><th className={`${th} text-right`}><InfoLabel k={d?.kaynaklar} alan="items">Yorum</InfoLabel></th><th className={`${th} text-right`}><InfoLabel k={d?.kaynaklar} alan="items">Ortalama</InfoLabel></th><th className={`${th} text-right`}><InfoLabel k={d?.kaynaklar} alan="items">3 ve altı</InfoLabel></th></tr></thead>
            <tbody>
              {d.kitaplar.map((b, i) => (
                <tr key={`${b.stokKodu ?? b.ad}-${i}`} className="border-t border-slate-100">
                  <td className={td}><BookCell name={b.ad} code={b.stokKodu} /></td>
                  <td className={`${td} text-right font-mono tabular-nums`}>{fmtInt(b.yorum)}</td>
                  <td className={`${td} text-right font-mono tabular-nums`}>{b.ortalama ?? '—'}</td>
                  <td className={`${td} text-right font-mono tabular-nums`}>{fmtInt(b.dusuk)}</td>
                </tr>
              ))}
            </tbody>
          </TableWrap>
        </Panel>
      )}
    </>
  );
}

export default function TrendyolQuestions() {
  const meta = useTrendyolMeta();
  const m = meta.data;
  const [tab, setTab] = useState<'soru' | 'yorum'>('soru');
  const [text, setText] = useState('');
  const q = useDebounced(text, 300);
  return (
    <TrendyolFrame
      title="Soru ve yorum"
      lead="Cevap bekleyen müşteri soruları ve düşük puanlı yorumlar. Zeki AI yanıt taslağı yazar; taslağı kopyalayıp yanıtı Trendyol panelinden siz verirsiniz. E-posta, telefon ve uzun numaralar gizlenir."
      aside={<input className={field} aria-label="Ara" placeholder="Ara: kitap, barkod ya da metin" value={text} onChange={(e) => setText(e.target.value)} />}
    >
      <TrendyolData meta={m} />
      <ReaderVoicePanel sources={['trendyol-soru', 'trendyol-yorum']} />
      <Tabs value={tab} onChange={setTab} tabs={[{ key: 'soru', label: 'Müşteri soruları' }, { key: 'yorum', label: 'Yorumlar' }]} />
      {tab === 'soru'
        ? <QuestionList q={q} canDraft={!!m?.me.canDraft} canExport={!!m?.me.canExport} />
        : <ReviewList q={q} canDraft={!!m?.me.canDraft} canExport={!!m?.me.canExport} />}
    </TrendyolFrame>
  );
}
