import { useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Download, FileSpreadsheet, Loader2, Plus, Sparkles, Trash2 } from 'lucide-react';
import { Note, Pill, TableWrap, btnGhost, btnPrimary, errText, field, label as labelCls, td, th } from '../admin/ui';
import { AskSheet } from '../budget/parts';
import { useDebounced } from '../editorial/kit';
import SqlInfo, { InfoLabel } from '../components/SqlInfo';
import type { Kaynaklar } from '../components/sqlInfo';
import { Explain } from '../components/Explain';
import { ENGINE_ENABLED } from '../engine';
import {
  QUOTE_TONE,
  corporateApi,
  fmtDay,
  fmtInt,
  fmtMoney,
  fmtPct,
  marginText,
  parseNum,
  toItems,
  type Meta,
  type Quote,
  type QuoteLine,
} from './api';

export type Draft = Pick<QuoteLine, 'stok' | 'ad' | 'yazar' | 'adet' | 'indirim' | 'listeFiyati' | 'fiyatKaynak' | 'stokMiktar' | 'maliyetBirim' | 'maliyetKaynak' | 'maliyetTahmini' | 'fiyatListe'>;

const lineOf = (l: QuoteLine): Draft => ({
  stok: l.stok, ad: l.ad, yazar: l.yazar, adet: l.adet, indirim: l.indirim, listeFiyati: l.listeFiyati, fiyatKaynak: l.fiyatKaynak,
  stokMiktar: l.stokMiktar, maliyetBirim: l.maliyetBirim, maliyetKaynak: l.maliyetKaynak, maliyetTahmini: l.maliyetTahmini, fiyatListe: l.fiyatListe,
});

/** Sayı hücresi: yazarken metin olarak tutulur (virgül yazılabilsin), alandan çıkınca sayıya çevrilir. */
function NumCell({ value, onCommit, label, width }: { value: number; onCommit: (n: number | null) => void; label: string; width: string }) {
  const show = (n: number) => String(Math.round(n * 100) / 100).replace('.', ',');
  const [text, setText] = useState(show(value));
  useEffect(() => setText(show(value)), [value]);
  return (
    <input
      className={`${field} ${width} text-right font-mono tabular-nums`}
      inputMode="decimal"
      aria-label={label}
      value={text}
      onChange={(e) => setText(e.target.value)}
      onBlur={() => onCommit(parseNum(text))}
      onKeyDown={(e) => {
        if (e.key === 'Enter') (e.target as HTMLInputElement).blur();
      }}
    />
  );
}

export function BookAdder({ onAdd, taken }: { onAdd: (d: Draft) => void; taken: Set<string> }) {
  const [q, setQ] = useState('');
  const dq = useDebounced(q, 250);
  const res = useQuery({ queryKey: ['corporate', 'books', dq], queryFn: () => corporateApi.books(dq), enabled: ENGINE_ENABLED && dq.trim().length >= 2 });
  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-center gap-1">
        <label className={labelCls} htmlFor="corp-book-add">Kitap ekle</label>
        <SqlInfo k={res.data?.kaynaklar} alan="items[]" label="Kitap aramasındaki stok ve liste fiyatı" />
      </div>
      <input id="corp-book-add" className={field} value={q} onChange={(e) => setQ(e.target.value)} placeholder="Kitap adı, stok kodu ya da yazar" autoComplete="off" />
      {res.data && res.data.items.length > 0 && (
        <ul className="max-h-60 overflow-y-auto rounded-xl border border-slate-100 bg-white">
          {res.data.items.map((b) => (
            <li key={b.stokKodu}>
              <button
                type="button"
                disabled={taken.has(b.stokKodu)}
                className="flex min-h-11 w-full items-center justify-between gap-2 px-3 py-2 text-left text-[12.5px] hover:bg-slate-50 disabled:opacity-40"
                onClick={() => {
                  onAdd({
                    stok: b.stokKodu, ad: b.ad, yazar: b.yazar ?? null, adet: 1, indirim: 0, listeFiyati: b.fiyat ?? b.crmFiyat ?? 0,
                    fiyatKaynak: b.fiyat ? 'logo' : b.crmFiyat ? 'crm' : 'elle', stokMiktar: b.stok ?? null, maliyetBirim: null,
                    maliyetKaynak: 'kaydedince', maliyetTahmini: false, fiyatListe: b.fiyatListe ?? null,
                  });
                  setQ('');
                }}
              >
                <span className="min-w-0">
                  <span className="block truncate font-bold">{b.ad ?? b.stokKodu}</span>
                  <span className="block truncate text-[11px] text-canvas-muted">{[b.stokKodu, b.yazar, `stok ${fmtInt(b.stok)}`].filter(Boolean).join(' · ')}</span>
                </span>
                <span className="shrink-0 font-mono text-[12px] tabular-nums">{b.fiyat ? fmtMoney(b.fiyat, true) : 'fiyat yok'}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
      {res.data && res.data.items.length === 0 && <span className="text-[11.5px] text-canvas-muted">Kitap bulunamadı.</span>}
    </div>
  );
}

/** `k`: teklifin geldiği fırsat cevabının sorgu bilgisi (`teklifler[]` kalemleri, `teklifler[].taslak` ekran hesabı). */
export default function QuoteEditor({ quote, meta, oppOpen, k }: { quote: Quote; meta: Meta; oppOpen: boolean; k?: Kaynaklar }) {
  const qc = useQueryClient();
  const editable = quote.durum === 'taslak' && meta.me.canQuote;
  const [lines, setLines] = useState<Draft[]>(() => quote.kalemler.map(lineOf));
  const [letter, setLetter] = useState(quote.mektup ?? '');
  const [bulk, setBulk] = useState('');
  const [ask, setAsk] = useState<null | 'approve' | 'reject' | 'ret' | 'kabul' | 'delete'>(null);
  useEffect(() => {
    setLines(quote.kalemler.map(lineOf));
    setLetter(quote.mektup ?? '');
  }, [quote]);

  const dirtyLines = useMemo(() => JSON.stringify(toItems(lines)) !== JSON.stringify(toItems(quote.kalemler)), [lines, quote.kalemler]);
  const dirtyLetter = letter !== (quote.mektup ?? '');
  const local = useMemo(() => {
    const liste = lines.reduce((s, l) => s + l.listeFiyati * l.adet, 0);
    const net = lines.reduce((s, l) => s + l.listeFiyati * (1 - l.indirim) * l.adet, 0);
    return { liste, net, qty: lines.reduce((s, l) => s + l.adet, 0) };
  }, [lines]);

  const done = (msg: string) => () => {
    qc.invalidateQueries({ queryKey: ['corporate'] });
    toast.success(msg);
  };
  const fail = (fallback: string) => (e: unknown) => toast.error(errText(e, fallback) ?? '');
  const save = useMutation({
    mutationFn: () => corporateApi.updateQuote(quote.id, { ...(dirtyLines ? { kalemler: toItems(lines) } : {}), ...(dirtyLetter ? { mektup: letter || null } : {}) }),
    onSuccess: done('Teklif kaydedildi.'),
    onError: fail('Teklif kaydedilemedi.'),
  });
  const act = useMutation({
    mutationFn: async ({ kind, text }: { kind: string; text?: string }) => {
      switch (kind) {
        case 'submit': return corporateApi.submit(quote.id);
        case 'withdraw': return corporateApi.withdraw(quote.id);
        case 'approve': return corporateApi.approve(quote.id, text || undefined);
        case 'reject': return corporateApi.reject(quote.id, text ?? '');
        case 'sent': return corporateApi.sent(quote.id);
        case 'kabul': return corporateApi.result(quote.id, 'kabul', text);
        case 'ret': return corporateApi.result(quote.id, 'ret', text);
        case 'copy': return corporateApi.createQuote(quote.firsatId, { kopya: quote.id });
        case 'delete': await corporateApi.deleteQuote(quote.id); return null;
        default: throw new Error('Bilinmeyen işlem');
      }
    },
    onSuccess: (out, { kind }) => {
      setAsk(null);
      const msg: Record<string, string> = {
        submit: out && (out as Quote).durum === 'onayda' ? 'Teklif müdür onayına gönderildi.' : 'Onay gerekmiyor; teklif gönderilebilir.',
        withdraw: 'Teklif taslağa alındı.', approve: 'Teklif onaylandı.', reject: 'Teklif gerekçesiyle geri gönderildi.',
        sent: 'Gönderildi olarak işaretlendi.', kabul: 'Kabul kaydedildi; fırsat kazanıldı.', ret: 'Ret kaydedildi.',
        copy: 'Yeni sürüm taslağı açıldı.', delete: 'Taslak silindi.',
      };
      done(msg[kind])();
    },
    onError: fail('İşlem yapılamadı.'),
  });
  const draftLetter = useMutation({
    mutationFn: () => corporateApi.letter(quote.id),
    onSuccess: (r) => {
      setLetter(r.mektup);
      toast.success('Zeki AI taslağı hazır; düzenleyip kaydedin.');
    },
    onError: fail('Mektup taslağı alınamadı.'),
  });

  const set = (i: number, patch: Partial<Draft>) => setLines((ls) => ls.map((l, j) => (j === i ? { ...l, ...patch } : l)));
  const mine = (quote.gonderen ?? '').toLowerCase() === meta.me.username.toLowerCase();
  const busy = act.isPending || save.isPending;
  const canLetter = meta.me.canQuote && (quote.durum === 'taslak' || quote.durum === 'hazir');
  // Kaydedilmemiş değişiklikte toplamlar ekranda hesaplanır: kaynağı o hesabın formülü.
  const totalsPath = dirtyLines ? 'teklifler[].taslak' : 'teklifler[].toplamNet';

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="text-[15px] font-extrabold">Teklif v{quote.surum}</h3>
        <Pill tone={QUOTE_TONE[quote.durum]}>{quote.durumLabel}</Pill>
        <span className="text-[11.5px] text-canvas-muted">
          {quote.createdBy} · {fmtDay(quote.createdAt)}
          {quote.onaylayan ? ` · ${quote.durum === 'taslak' ? 'geri gönderen' : 'onaylayan'} ${quote.onaylayan}` : ''}
        </span>
      </div>
      {quote.onayNotu && <Note tone={quote.durum === 'taslak' ? 'warn' : 'info'}>Onay notu: {quote.onayNotu}</Note>}

      <TableWrap>
        <thead>
          <tr>
            <th className={th}>Kitap</th>
            <th className={`${th} text-right`}><InfoLabel k={k} alan="teklifler[].kalemler[].stokMiktar">Stok</InfoLabel></th>
            <th className={`${th} text-right`}><InfoLabel k={k} alan="teklifler[].kalemler[].adet">Adet</InfoLabel></th>
            <th className={`${th} text-right`}><InfoLabel k={k} alan="teklifler[].kalemler[].listeFiyati">Liste fiyatı</InfoLabel></th>
            <th className={`${th} text-right`}><InfoLabel k={k} alan="teklifler[].kalemler[].indirim">İndirim %</InfoLabel></th>
            <th className={`${th} text-right`}><InfoLabel k={k} alan="teklifler[].taslak">Tutar</InfoLabel></th>
            <th className={`${th} text-right`}><InfoLabel k={k} alan="teklifler[].kalemler[].maliyetBirim">Birim maliyet</InfoLabel></th>
            {editable && <th className={th}><span className="sr-only">Sil</span></th>}
          </tr>
        </thead>
        <tbody>
          {lines.map((l, i) => (
            <tr key={l.stok} className="border-t border-slate-100">
              <td className={td}>
                <div className="font-bold">{l.ad ?? l.stok}</div>
                <div className="text-[11px] text-canvas-muted">
                  {[l.stok, l.yazar, l.fiyatKaynak === 'logo' ? `liste ${l.fiyatListe ?? '—'}` : l.fiyatKaynak === 'crm' ? 'CRM fiyatı' : l.fiyatKaynak === 'elle' ? 'fiyat elle' : null].filter(Boolean).join(' · ')}
                </div>
              </td>
              <td className={`${td} text-right font-mono tabular-nums ${l.stokMiktar !== null && l.stokMiktar < l.adet ? 'font-bold text-red-700' : ''}`}>{fmtInt(l.stokMiktar)}</td>
              <td className={`${td} text-right`}>
                {editable ? (
                  <NumCell width="w-24" label={`${l.ad ?? l.stok} adedi`} value={l.adet} onCommit={(n) => set(i, { adet: Math.max(1, Math.round(n ?? 1)) })} />
                ) : <span className="font-mono tabular-nums">{fmtInt(l.adet)}</span>}
              </td>
              <td className={`${td} text-right`}>
                {editable && l.fiyatKaynak !== 'logo' ? (
                  <NumCell width="w-28" label={`${l.ad ?? l.stok} liste fiyatı`} value={l.listeFiyati} onCommit={(n) => set(i, { listeFiyati: Math.max(0, n ?? 0), fiyatKaynak: 'elle' })} />
                ) : <span className="font-mono tabular-nums">{fmtMoney(l.listeFiyati, true)}</span>}
              </td>
              <td className={`${td} text-right`}>
                {editable ? (
                  <NumCell width="w-20" label={`${l.ad ?? l.stok} indirimi`} value={l.indirim * 100} onCommit={(n) => set(i, { indirim: Math.min(100, Math.max(0, n ?? 0)) / 100 })} />
                ) : <span className="font-mono tabular-nums">{fmtPct(l.indirim)}</span>}
              </td>
              <td className={`${td} text-right font-mono tabular-nums`}>{fmtMoney(l.listeFiyati * (1 - l.indirim) * l.adet, true)}</td>
              <td className={`${td} text-right text-[11.5px]`}>
                {l.maliyetBirim !== null ? (
                  <span className="font-mono tabular-nums">{fmtMoney(l.maliyetBirim, true)}{l.maliyetTahmini ? ' (tahmini)' : ''}</span>
                ) : <span className="text-canvas-muted">{l.maliyetKaynak === 'kaydedince' ? 'kaydedince' : 'bilinmiyor'}</span>}
              </td>
              {editable && (
                <td className={td}>
                  <button type="button" className={`${btnGhost} !min-h-9 !px-2`} aria-label={`${l.ad ?? l.stok} satırını sil`} onClick={() => setLines((ls) => ls.filter((_, j) => j !== i))}>
                    <Trash2 aria-hidden className="h-4 w-4" />
                  </button>
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </TableWrap>

      {editable && (
        <div className="grid gap-3 md:grid-cols-[minmax(0,1fr)_260px]">
          <BookAdder taken={new Set(lines.map((l) => l.stok))} onAdd={(d) => setLines((ls) => [...ls, d])} />
          <div className="flex flex-col gap-1">
            <label className={labelCls} htmlFor="corp-bulk">Bütün satırlara indirim (%)</label>
            <div className="flex gap-2">
              <input id="corp-bulk" className={`${field} font-mono tabular-nums`} inputMode="decimal" value={bulk} onChange={(e) => setBulk(e.target.value)} />
              <button type="button" className={btnGhost} disabled={parseNum(bulk) === null}
                onClick={() => setLines((ls) => ls.map((l) => ({ ...l, indirim: Math.min(100, Math.max(0, parseNum(bulk) ?? 0)) / 100 })))}>
                Uygula
              </button>
            </div>
            <span className="text-[11px] text-canvas-muted">
              Müdür onayı gerekir: indirim %{meta.settings.discountApprovalPct ?? '—'} üstündeyse{meta.settings.marginMinPct !== null ? ` ya da marj %${meta.settings.marginMinPct} altındaysa` : ''}.
              <SqlInfo k={meta.kaynaklar} alan="settings" label="Teklif onay eşikleri (ayar)" className="ml-0.5" />
            </span>
          </div>
        </div>
      )}

      <div className="grid gap-2 rounded-2xl bg-slate-50 p-3 text-[12.5px] sm:grid-cols-4">
        <div>
          <div className={`${labelCls} inline-flex items-center gap-1`}>Liste fiyatıyla<SqlInfo k={k} alan={totalsPath} label="Liste fiyatıyla toplam" /></div>
          <div className="font-mono font-bold tabular-nums">{fmtMoney(dirtyLines ? local.liste : quote.toplamListe)}</div>
        </div>
        <div>
          <div className={`${labelCls} inline-flex items-center gap-1`}>İndirim<SqlInfo k={k} alan={totalsPath} label="Teklifin indirim oranı" /></div>
          <div className="font-mono font-bold tabular-nums">{fmtPct(dirtyLines ? (local.liste ? 1 - local.net / local.liste : null) : quote.indirimOrani)}</div>
        </div>
        <div>
          <div className={`${labelCls} inline-flex items-center gap-1`}>Teklif tutarı<SqlInfo k={k} alan={totalsPath} label="Teklif tutarı" /></div>
          <div className="font-mono text-[15px] font-extrabold tabular-nums">{fmtMoney(dirtyLines ? local.net : quote.toplamNet)}</div>
        </div>
        <div>
          <div className={`${labelCls} inline-flex items-center gap-1`}>Marj<Explain label="Marj">Teklif tutarından kitapların birim maliyeti düşüldükten sonra kalan kâr payı. Maliyeti bilinmeyen kitap varsa marj hesaplanmaz.</Explain><SqlInfo k={k} alan="teklifler[].marj" label="Teklif marjı ve maliyet kapsamı" /></div>
          <div className="font-bold">{dirtyLines ? 'kaydedince hesaplanır' : marginText(quote)}</div>
        </div>
      </div>
      {!dirtyLines && quote.marj === null && <p className="text-[11.5px] text-canvas-muted">Birim maliyet kaynağı: {meta.costSourceLabel}. Maliyet bilinmeden marj tahmin edilmez; bu durumda onay gerekip gerekmediğine yalnız indirim oranına bakılarak karar verilir.</p>}
      {!dirtyLines && quote.onayNedenleri.length > 0 && (
        <Note tone="warn">
          Müdür onayı gerekiyor: {quote.onayNedenleri.map((r) => r.metin).join(' · ')}
        </Note>
      )}
      {lines.some((l) => l.stokMiktar !== null && l.stokMiktar < l.adet) && <Note tone="err">Stoğu adede yetmeyen kitap var (kırmızı). Teklifi göndermeden önce üretim/depo ile teyit edin.</Note>}
      {dirtyLines && <Note tone="info">Değişiklikler kaydedilmedi; tutarlar kaydedince fiyat listesi ve kurallarla yeniden hesaplanır.</Note>}

      <div className="flex flex-col gap-1">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <label className={labelCls} htmlFor={`corp-letter-${quote.id}`}>Teklif mektubu</label>
          {canLetter && (
            <button type="button" className={btnGhost} disabled={draftLetter.isPending} onClick={() => draftLetter.mutate()}>
              {draftLetter.isPending ? <Loader2 aria-hidden className="h-4 w-4 animate-spin" /> : <Sparkles aria-hidden className="h-4 w-4" />}
              Zeki AI ile taslak yaz
            </button>
          )}
        </div>
        <textarea
          id={`corp-letter-${quote.id}`}
          className={`${field} min-h-[140px]`}
          value={letter}
          readOnly={!canLetter}
          onChange={(e) => setLetter(e.target.value)}
          placeholder="Belgenin başına girecek kısa mektup. Rakamlar tablodan gelir."
        />
      </div>

      <div className="flex flex-wrap gap-2">
        {(editable || (canLetter && dirtyLetter)) && (
          <button type="button" className={btnPrimary} disabled={busy || (!dirtyLines && !dirtyLetter) || lines.length === 0} onClick={() => save.mutate()}>
            Kaydet
          </button>
        )}
        {editable && (
          <button type="button" className={btnPrimary} disabled={busy || dirtyLines || dirtyLetter || lines.length === 0} onClick={() => act.mutate({ kind: 'submit' })}
            title={dirtyLines || dirtyLetter ? 'Önce kaydedin' : undefined}>
            Onaya gönder / hazırla
          </button>
        )}
        {editable && (
          <button type="button" className={btnGhost} disabled={busy} onClick={() => setAsk('delete')}>Taslağı sil</button>
        )}
        {meta.me.canQuote && (quote.durum === 'onayda' || quote.durum === 'hazir') && (
          <button type="button" className={btnGhost} disabled={busy} onClick={() => act.mutate({ kind: 'withdraw' })}>Taslağa geri al</button>
        )}
        {quote.durum === 'onayda' && meta.me.canApprove && !mine && (
          <>
            <button type="button" className={btnPrimary} disabled={busy} onClick={() => setAsk('approve')}>Onayla</button>
            <button type="button" className={btnGhost} disabled={busy} onClick={() => setAsk('reject')}>Geri gönder</button>
          </>
        )}
        {quote.durum === 'onayda' && meta.me.canApprove && mine && <span className="self-center text-[11.5px] text-canvas-muted">Onaya siz gönderdiniz; başka bir yetkili onaylar.</span>}
        {meta.me.canQuote && quote.durum === 'hazir' && (
          <button type="button" className={btnPrimary} disabled={busy} onClick={() => act.mutate({ kind: 'sent' })}>Kuruma gönderildi olarak işaretle</button>
        )}
        {meta.me.canQuote && quote.durum === 'gonderildi' && (
          <>
            <button type="button" className={btnPrimary} disabled={busy} onClick={() => setAsk('kabul')}>Kabul edildi</button>
            <button type="button" className={btnGhost} disabled={busy} onClick={() => setAsk('ret')}>Reddedildi</button>
          </>
        )}
        {meta.me.canQuote && oppOpen && quote.durum !== 'taslak' && (
          <button type="button" className={btnGhost} disabled={busy} onClick={() => act.mutate({ kind: 'copy' })}>
            <Plus aria-hidden className="h-4 w-4" /> Yeni sürüm
          </button>
        )}
        {meta.me.canExport && (
          <>
            <a className={btnGhost} href={corporateApi.pdfUrl(quote.id)} download>
              <Download aria-hidden className="h-4 w-4" /> PDF indir{quote.durum === 'taslak' || quote.durum === 'onayda' ? ' (taslak)' : ''}
            </a>
            <a className={btnGhost} href={corporateApi.xlsxUrl(quote.id)} download>
              <FileSpreadsheet aria-hidden className="h-4 w-4" /> Excel indir
            </a>
          </>
        )}
      </div>
      <p className="text-[11px] text-canvas-muted">
        Belge indirilir; kuruma gönderimi temsilci yapar. Kabul edilen teklifin Excel'indeki «Sipariş satırları» CRM'de siparişi açmak içindir — portal CRM'e yazmaz.
      </p>

      <AskSheet
        open={ask !== null}
        title={{ approve: 'Teklifi onayla', reject: 'Geri gönder', kabul: 'Kabul kaydı', ret: 'Ret kaydı', delete: 'Taslağı sil' }[ask ?? 'approve']}
        message={{
          approve: 'Teklif gönderilebilir duruma geçer; onayınız değişiklik kaydına yazılır.',
          reject: 'Teklif taslağa döner; gerekçe temsilciye görünür.',
          kabul: 'Fırsat «Kazanıldı» olur, değeri teklif tutarıdır.',
          ret: 'Fırsat açık kalır; yeni sürümle devam edebilir ya da fırsatı kaybedildi olarak kapatabilirsiniz.',
          delete: 'Bu taslak ve kalemleri silinir. Bu işlem geri alınmaz.',
        }[ask ?? 'approve']}
        confirm={{ approve: 'Onayla', reject: 'Geri gönder', kabul: 'Kaydet', ret: 'Kaydet', delete: 'Sil' }[ask ?? 'approve']}
        danger={ask === 'delete' || ask === 'reject'}
        input={ask === 'approve' ? 'Not (isteğe bağlı)' : ask === 'reject' ? 'Gerekçe' : ask === 'ret' ? 'Kurumun gerekçesi (isteğe bağlı)' : ask === 'kabul' ? 'Not (isteğe bağlı)' : undefined}
        required={ask === 'reject'}
        busy={busy}
        onClose={() => setAsk(null)}
        onConfirm={(text) => ask && act.mutate({ kind: ask, text })}
      />
    </div>
  );
}
