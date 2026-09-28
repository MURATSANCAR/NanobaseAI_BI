import { useQuery } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Copy, Download } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import { Loading, Note, Pill, btnGhost, errText } from '../admin/ui';
import { fmtMoney, fmtShortDay, fmtStamp, mktApi, type Meta, type Plan, type TodoItem } from './api';
import { Block } from './parts';

const EVENT: Record<string, string> = {
  olusturuldu: 'Plan açıldı', duzenlendi: 'Plan düzenlendi', butce: 'Kanal ve bütçe değişti', 'oneri-butce': 'Zeki AI kanal ve bütçe önerisi',
  takvim: 'Takvim değişti', 'takvim-durum': 'İş durumu işlendi', 'takvim-kaydi': 'Takvim yayın gününe göre kaydı', materyal: 'Materyal eklendi',
  'materyal-duzenle': 'Materyal düzenlendi', 'materyal-onay-editoryal': 'Materyale editoryal onay', 'materyal-onay-pazarlama': 'Materyale pazarlama onayı',
  'onaya-gonderildi': 'Onaya gönderildi', 'onaydan-cekildi': 'Onaydan çekildi', 'onay-pazarlama': 'Pazarlama onayı', 'onay-ust': 'Üst onay',
  'geri-gonderildi': 'Geri gönderildi', revizyon: 'Revizyon sürümü', 'revizyon-acildi': 'Revizyon açıldı', arsivlendi: 'Arşive geçti',
  'zeki-oneri': 'Zeki AI gerekçesi ve emsal kontrolü', bildirim: 'Bildirim',
  kitaplar: 'Kitap listesi değişti', 'kitaplar-acilis': 'Plan kitapları eklendi',
};
const MAIL: Record<string, string> = { sent: 'gönderildi', no_smtp: 'gönderilemedi: e-posta ayarı yok', no_recipient: 'gönderilemedi: alıcı yok', failed: 'gönderilemedi' };

function todoText(it: TodoItem): string {
  if (it.tur === 'butce-satiri') {
    return `${it.hedef}\nPazarlama tipi: ${it.tip}${it.altTip ? ` / ${it.altTip}` : ''}\nTutar: ${it.tutar ?? '—'}\nBaşlangıç: ${it.baslangic ?? '—'}\nBitiş: ${it.bitis ?? '—'}\nKitap: ${it.kitap ?? '—'}`;
  }
  return `${it.hedef}\n${it.deger ?? ''}`;
}

/** Onay durumu, «CRM'e işlenecek» listesi (CRM'e yazma yok: müşterinin kullanıcıları elle işler) ve plan geçmişi. */
export default function HistoryTab({ plan, meta }: { plan: Plan; meta: Meta }) {
  const todo = useQuery({ queryKey: ['mkt', 'todo', plan.id, plan.surum, plan.durum], queryFn: () => mktApi.todo(plan.id), enabled: ENGINE_ENABLED });
  const events = useQuery({ queryKey: ['mkt', 'events', plan.id, plan.durum, plan.surum], queryFn: () => mktApi.events(plan.id), enabled: ENGINE_ENABLED });
  const copy = async (s: string) => {
    try {
      await navigator.clipboard.writeText(s);
      toast.success('Kopyalandı.');
    } catch {
      toast.error('Kopyalanamadı; metni seçip kopyalayın.');
    }
  };

  return (
    <div className="flex flex-col gap-3">
      <Block title="Onay">
        <ul className="flex flex-col gap-1 text-[12.5px]">
          <li>Gönderen: <strong>{plan.gonderen ?? '—'}</strong> {plan.gonderme && <span className="text-canvas-muted">({fmtStamp(plan.gonderme)})</span>}</li>
          <li>Pazarlama onayı: <strong>{plan.onaylayan ?? '—'}</strong> {plan.onayZamani && <span className="text-canvas-muted">({fmtStamp(plan.onayZamani)})</span>}</li>
          <li>
            Üst onay: <strong>{plan.ustOnaylayan ?? (plan.ustOnayGerekli ? 'bekleniyor' : 'gerekmiyor')}</strong>
            {plan.ustOnayZamani && <span className="text-canvas-muted"> ({fmtStamp(plan.ustOnayZamani)})</span>}
            {!meta.settings.thresholdSet && <span className="text-canvas-muted"> · eşik Yönetim'de girilmemiş</span>}
          </li>
          {plan.gerekce && <li>Gerekçe: {plan.gerekce}</li>}
        </ul>
      </Block>

      <Block
        title="CRM'e işlenecek"
        help="Portalda onaylanan ama CRM'de olmayan ya da farklı olan bilgiler. Portal CRM'e yazmaz; bu listeyi CRM'e ekibiniz işler."
        action={meta.me.canExport && <a className={btnGhost} href={mktApi.todoCsvUrl(plan.id)} download><Download aria-hidden className="h-4 w-4" />CSV</a>}
      >
        {todo.isLoading && <Loading />}
        {todo.error && <Note tone="err">{errText(todo.error, 'Liste açılamadı.')}</Note>}
        {todo.data && !todo.data.planOnayli && todo.data.items.length > 0 && <Note tone="info">Plan henüz onaylı değil; liste onaydan sonra CRM'e işlenmeli.</Note>}
        {todo.data && todo.data.items.length === 0 && <Note tone="ok">CRM'e işlenecek bir şey yok.</Note>}
        <ul className="mt-2 flex flex-col gap-2">
          {todo.data?.items.map((it, i) => (
            <li key={i} className="rounded-xl bg-white/75 p-2.5 text-[12px]">
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div className="min-w-0">
                  <div className="font-bold">{it.hedef}</div>
                  {it.tur === 'butce-satiri' ? (
                    <div className="text-canvas-muted">{it.tip}{it.altTip ? ` / ${it.altTip}` : ''} · {meta.me.canSeeBudget ? fmtMoney(it.tutar) : 'tutar gizli'} · {fmtShortDay(it.baslangic)} – {fmtShortDay(it.bitis)}</div>
                  ) : (
                    <>
                      <p className="mt-1 line-clamp-4 whitespace-pre-line leading-snug">{String(it.deger ?? '—')}</p>
                      <div className="mt-0.5 text-[11px] text-canvas-muted">CRM'de şu an: {it.crmDeger ? <span className="line-clamp-2">{String(it.crmDeger)}</span> : 'boş'}</div>
                    </>
                  )}
                </div>
                <button type="button" className={btnGhost} onClick={() => copy(todoText(it))}><Copy aria-hidden className="h-4 w-4" />Kopyala</button>
              </div>
            </li>
          ))}
        </ul>
      </Block>

      <Block title="Geçmiş">
        {events.isLoading && <Loading />}
        <ol className="flex flex-col gap-1.5">
          {events.data?.items.map((e) => {
            const y = (e.yeni ?? {}) as Record<string, unknown>;
            const sonuc = typeof y.sonuc === 'string' ? String(y.sonuc) : null;
            const gerekce = typeof y.gerekce === 'string' ? String(y.gerekce) : null;
            return (
              <li key={e.id} className="flex flex-wrap items-baseline gap-x-2 text-[12px]">
                <span className="font-mono text-[11px] text-canvas-muted">{fmtStamp(e.zaman)}</span>
                <span className="font-semibold">{EVENT[e.ne] ?? e.ne}</span>
                <span className="text-canvas-muted">{e.kim}</span>
                {e.ne === 'bildirim' && sonuc && <Pill tone={sonuc === 'sent' ? 'ok' : 'warn'}>{MAIL[sonuc] ?? sonuc}</Pill>}
                {gerekce && <span className="basis-full text-canvas-muted">{gerekce}</span>}
              </li>
            );
          })}
        </ol>
      </Block>
    </div>
  );
}
