import { Link, useNavigate, useParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { ExternalLink, Loader2 } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import SqlInfo from '../components/SqlInfo';
import { Loading, Note, Pill, btnGhost, btnPrimary, errText } from '../admin/ui';
import { KIT_TONE, fmtDay, prApi } from './api';
import { Block, Empty, PrFrame } from './parts';

/** Kitabın basın geçmişi: PR dosyaları, CRM haber arşivi (2025-06'ya kadar, yalnız okunur), basına tanıtım gönderimi
 *  siparişleri (CRM tip 12). «PR dosyası aç» buradan da açılır. */
export default function PrBook() {
  const { bookId = '' } = useParams();
  const qc = useQueryClient();
  const nav = useNavigate();
  const meta = useQuery({ queryKey: ['pr', 'meta'], queryFn: prApi.meta, enabled: ENGINE_ENABLED, staleTime: 60_000 });
  const q = useQuery({ queryKey: ['pr', 'book', bookId], queryFn: () => prApi.book(bookId), enabled: ENGINE_ENABLED && !!bookId });
  const create = useMutation({
    mutationFn: () => prApi.createKit(bookId),
    onSuccess: (kit) => {
      qc.invalidateQueries({ queryKey: ['pr'] });
      toast.success('PR dosyası açıldı.');
      nav(`/basin-iliskileri/dosya/${encodeURIComponent(kit.id)}`);
    },
    onError: (e) => toast.error(errText(e, 'Dosya açılamadı.') ?? ''),
  });
  const d = q.data;
  const b = d?.book;
  const canEdit = !!meta.data?.me.canEdit;

  return (
    <PrFrame
      crumb="Basın ilişkileri"
      title={b?.ad ?? 'Kitap'}
      lead={b ? `Bu kitabın PR dosyaları, CRM'deki haber kayıtları ve basına gönderilen tanıtım kitapları. ${[b.yazar, b.yayinevi, b.kitaplik, b.hedefKitle, b.yayinTarihi && `ilk baskı ${fmtDay(b.yayinTarihi)}`].filter(Boolean).join(' · ')}` : undefined}
      source="CRM kitap kartı"
      presence={d ? `${d.archive.length} arşiv haberi` : '…'}
      back={{ to: '/basin-iliskileri', label: 'Basın ilişkileri' }}
      aside={
        d && (
          <div className="flex flex-col gap-2">
            {d.openKit ? (
              <Link to={`/basin-iliskileri/dosya/${encodeURIComponent(d.openKit.id)}`} className={btnPrimary}>PR dosyasını aç ({d.openKit.id})</Link>
            ) : canEdit ? (
              <button type="button" className={btnPrimary} disabled={create.isPending} onClick={() => create.mutate()}>
                {create.isPending && <Loader2 aria-hidden className="h-4 w-4 animate-spin" />}
                PR dosyası aç
              </button>
            ) : null}
            {d.m15Release && <Note tone="info">Pazarlama planında onaylı basın bülteni var; dosya açılınca bülten olarak gelir.</Note>}
          </div>
        )
      }
    >
      {q.isLoading && <Loading />}
      {q.error && <Note tone="err">{errText(q.error, 'Kitap açılamadı.')}</Note>}
      {d && (
        <>
          {d.kits.length > 0 && (
            <Block title="PR dosyaları" info={<SqlInfo k={d.kaynaklar} alan="kits" label="PR dosyaları: gönderim ve yansıma" />}>
              <ul className="flex flex-col gap-2">
                {d.kits.map((k) => (
                  <li key={k.id}>
                    <Link to={`/basin-iliskileri/dosya/${encodeURIComponent(k.id)}`} className="flex flex-wrap items-center justify-between gap-2 rounded-2xl border border-slate-100 bg-white/85 p-3 hover:border-canvas-violet/40">
                      <span className="text-[13px] font-extrabold">PR dosyası · {k.id}</span>
                      <span className="flex items-center gap-1.5 text-[11.5px] text-canvas-muted">
                        {k.sentCount ?? 0}/{k.sendCount ?? 0} gönderim · {k.coverageCount ?? 0} yansıma
                        <Pill tone={KIT_TONE[k.status]}>{k.statusLabel}</Pill>
                      </span>
                    </Link>
                  </li>
                ))}
              </ul>
            </Block>
          )}

          <div className="grid grid-cols-1 gap-3 lg:grid-cols-2 lg:gap-4">
            <Block title="CRM haber arşivi" help="CRM «Haber» modülündeki kayıtlar (2025-06'dan beri yeni kayıt girilmiyor; yalnız okunur)." info={<SqlInfo k={d.kaynaklar} alan="archive" label="CRM haber arşivi" />}>
              {d.archiveNote && <Note tone="warn">{d.archiveNote}</Note>}
              {d.archive.length === 0 && !d.archiveNote && <Empty>Bu kitap için CRM'de haber kaydı yok.</Empty>}
              <ul className="flex flex-col divide-y divide-slate-100">
                {d.archive.map((a) => (
                  <li key={a.id} className="py-2">
                    <div className="break-words text-[13px] font-bold leading-snug">
                      {a.link ? (
                        <a href={a.link} target="_blank" rel="noreferrer" className="inline-flex items-start gap-1 hover:underline">
                          {a.baslik ?? '—'}
                          <ExternalLink aria-hidden className="mt-0.5 h-3.5 w-3.5 shrink-0 text-canvas-muted" />
                        </a>
                      ) : (a.baslik ?? '—')}
                    </div>
                    <div className="text-[11.5px] text-canvas-muted">
                      {[fmtDay(a.tarih), a.mecra, a.muhabir && `haberi yapan ${a.muhabir}`].filter((x) => x && x !== '—').join(' · ')}
                    </div>
                  </li>
                ))}
              </ul>
            </Block>
            <Block title="Basına tanıtım gönderimi" help="CRM «Pazarlama (Tanıtım Gönderimi)» siparişleri, bu kitabın stok koduyla. Alıcı sipariş carisidir; gazeteci adı siparişte tutulmuyor." info={<SqlInfo k={d.kaynaklar} alan="promoTotal" label="Tanıtım gönderimi adedi" />}>
              {d.promoNote && <Note tone="warn">{d.promoNote}</Note>}
              {d.promoOrders.length === 0 && !d.promoNote && <Empty>Tanıtım gönderimi siparişi yok.</Empty>}
              {d.promoOrders.length > 0 && (
                <>
                  <div className="mb-2 font-mono text-[22px] font-bold tabular-nums">{d.promoTotal.toLocaleString('tr-TR')} <span className="text-[12px] font-bold text-canvas-muted">adet</span></div>
                  <ul className="flex flex-col divide-y divide-slate-100 text-[12.5px]">
                    {d.promoOrders.map((o, i) => (
                      <li key={`${o.siparisNo}-${i}`} className="flex flex-wrap justify-between gap-2 py-1.5">
                        <span className="min-w-0 break-words">{o.cari ?? '—'} <span className="text-canvas-muted">· {o.siparisNo ?? '—'} · {fmtDay(o.tarih)}</span></span>
                        <span className="font-mono font-bold tabular-nums">{o.adet.toLocaleString('tr-TR')}</span>
                      </li>
                    ))}
                  </ul>
                </>
              )}
            </Block>
          </div>

          <Block title="Kitap kartındaki basın metinleri" help="Zeki AI bülten taslağını yalnız bu metinlere ve künyeye dayanarak yazar.">
            {(b?.metinler ?? []).length === 0 && <Empty>Kitap kartında basın için kullanılacak metin yok; bülteni elle yazmanız gerekecek.</Empty>}
            <div className="flex flex-col gap-2">
              {(b?.metinler ?? []).map((m) => (
                <details key={m.alan} className="rounded-2xl border border-slate-100 bg-white/85 p-3">
                  <summary className="min-h-8 cursor-pointer text-[12.5px] font-extrabold">{m.ad}</summary>
                  <p className="mt-1 whitespace-pre-line text-[12.5px] leading-snug">{m.metin}</p>
                </details>
              ))}
            </div>
            <Link to={`/kitap/${encodeURIComponent(bookId)}`} className={`${btnGhost} mt-2`}>Kitap sayfası</Link>
          </Block>
        </>
      )}
    </PrFrame>
  );
}
