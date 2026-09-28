import { useState, type FormEvent } from 'react';
import { useQuery } from '@tanstack/react-query';
import { ExternalLink, Search } from 'lucide-react';
import { Loading, Note, Pill, TableWrap, btnPrimary, errText, field, td, th } from '../admin/ui';
import { ENGINE_ENABLED } from '../engine';
import { Block, Empty, SourceLine } from './parts';
import { fmtDay, fmtInt, fmtNum, fmtTl, guessQuery, supportApi, type Context, type ContextQuery, type Order } from './api';
import SqlInfo from '../components/SqlInfo';
import { kaynakOf } from '../components/kaynakOf';

/** Müşteri bağlamı: e-posta / telefon / sipariş no / cari kodu → CRM kişi-cari eşleşmesi, siparişler ve durumu, sevkiyat,
 *  kargo takibi, Logo'dan fatura/iade (veri sonu tarihiyle), masadaki önceki talepler. Bağımsız bileşen: destek masasının
 *  paneline de aynı yanıtla taşınabilir (köprü `panel/context`). */
export default function CustomerContext({ initial }: { initial?: ContextQuery }) {
  const [text, setText] = useState(initial?.email ?? initial?.order ?? initial?.phone ?? initial?.code ?? '');
  const [query, setQuery] = useState<ContextQuery | null>(initial ?? null);
  const ctx = useQuery({
    queryKey: ['support', 'context', query],
    queryFn: () => supportApi.context(query as ContextQuery),
    enabled: ENGINE_ENABLED && !!query,
    staleTime: 60_000,
  });
  const submit = (e: FormEvent) => {
    e.preventDefault();
    const q = guessQuery(text);
    if (q) setQuery(q);
  };

  return (
    <div className="flex flex-col gap-3">
      <form onSubmit={submit} className="flex flex-col gap-2 sm:flex-row" role="search">
        <label className="sr-only" htmlFor="support-context-q">
          Müşteri ara
        </label>
        <input
          id="support-context-q"
          className={field}
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="E-posta, telefon, sipariş numarası ya da cari kodu"
          autoComplete="off"
          enterKeyHint="search"
        />
        <button type="submit" className={`${btnPrimary} shrink-0`} disabled={!text.trim() || ctx.isFetching}>
          <Search aria-hidden className="h-4 w-4" />
          Bağlamı getir
        </button>
      </form>
      <SourceLine>
        Yazılanın türü kendiliğinden anlaşılır (e-posta, telefon, «120.…» cari kodu, geri kalanı sipariş numarası). Her arama değişiklik
        kaydına yazılır; e-posta ve telefon kaydedilmez.
      </SourceLine>
      {ctx.isLoading && query && <Loading />}
      {ctx.error && <Note tone="err">{errText(ctx.error, 'Bağlam okunamadı.')}</Note>}
      {ctx.data && <ContextView data={ctx.data} onPick={(id) => setQuery({ ...query, account: id })} onOrder={(no) => { setText(no); setQuery({ order: no }); }} />}
    </div>
  );
}

export function ContextView({ data, onPick, onOrder }: { data: Context; onPick?: (accountId: string) => void; onOrder?: (no: string) => void }) {
  const c = data;
  const person = c.match.contacts[0]?.ad || c.match.webusers[0]?.ad;
  return (
    <div className="flex flex-col gap-3">
      {c.warnings.map((w) => (
        <Note key={w} tone="warn">{w}</Note>
      ))}
      {c.hidden.map((w) => (
        <Note key={w} tone="info">{w}</Note>
      ))}
      {c.needsChoice && (
        <Block title="Birden çok cari eşleşti" help="Bu bilgiler birden çok CRM carisine bağlı. Hangisi olduğunu seçin; Zeki AI seçmez.">
          <div className="flex flex-wrap gap-2">
            {c.match.accounts.map((a) => (
              <button key={a.id} type="button" className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-left text-[12.5px] font-bold transition-transform duration-150 ease-out active:scale-[0.97]" onClick={() => onPick?.(a.id)}>
                {a.unvan ?? 'Adsız cari'}
                <span className="block text-[11px] font-semibold text-canvas-muted">
                  {a.cariKodu ?? 'kodsuz'} · {a.kanal ?? 'kanal yok'}
                </span>
              </button>
            ))}
          </div>
        </Block>
      )}
      {!c.needsChoice && (
        <div className="flex flex-wrap items-center gap-2 px-1">
          {person && <span className="text-[14px] font-extrabold">{person}</span>}
          {c.account && (
            <span className="text-[12.5px] font-semibold text-canvas-muted">
              {c.account.unvan} · {c.account.cariKodu ?? 'cari kodu yok'} {c.account.kanal ? `· ${c.account.kanal}` : ''}
            </span>
          )}
          {c.summary && (
            <>
              <Pill tone="muted">{fmtInt(c.summary.orders)} sipariş</Pill>
              {c.summary.open > 0 && <Pill tone="warn">{fmtInt(c.summary.open)} açık · {fmtNum(c.summary.pending)} adet bekliyor</Pill>}
              {c.summary.risk > 0 && <Pill tone="err">{fmtInt(c.summary.risk)} risk onayında</Pill>}
            </>
          )}
        </div>
      )}
      {c.orderHints && c.orderHints.length > 0 && (
        <div className="flex flex-wrap items-center gap-1.5 px-1 text-[12px]">
          <span className="font-semibold text-canvas-muted">Talepte geçen sipariş numarası olabilir:</span>
          {c.orderHints.map((h) => (
            <button key={h} type="button" className="rounded-md bg-canvas-violet/10 px-1.5 py-0.5 font-mono text-[11.5px] font-bold text-canvas-violet" onClick={() => onOrder?.(h)}>
              {h}
            </button>
          ))}
        </div>
      )}
      {!c.needsChoice && c.hidden.length === 0 && (
        <>
          <Block info={<SqlInfo k={kaynakOf(c)} alan="_hepsi" label="Siparişler" />} title="Siparişler" help="Canlı CRM. Açık = bekleyen adedi olan ve tamamlanmamış/iptal edilmemiş sipariş (CRM kuralı).">
            {c.orders.length === 0 ? <Empty title="Sipariş yok">Bu müşteri için penceredeki CRM siparişi bulunamadı.</Empty> : <OrderTable orders={c.orders} />}
          </Block>
          <Block info={<SqlInfo k={kaynakOf(c)} alan="_hepsi" label="Kargo" />} title="Kargo" help="Kargo firmasının gönderi kaydı CRM'de; takip numarası ya da irsaliye numarasıyla eşlenir.">
            {c.cargo.length === 0 ? (
              <Empty title="Kargo kaydı yok">Siparişlerde kargo firmasının gönderi kaydı bulunamadı.</Empty>
            ) : (
              <TableWrap>
                <thead>
                  <tr>
                    <th className={th}>Takip no</th>
                    <th className={th}>Firma</th>
                    <th className={th}>Çıkış → varış</th>
                    <th className={th}>Teslim</th>
                    <th className={th}>İade durumu</th>
                    <th className={`${th} text-right`}>Desi</th>
                  </tr>
                </thead>
                <tbody>
                  {c.cargo.map((k, i) => (
                    <tr key={`${k.takipNo}-${i}`} className="border-t border-slate-100">
                      <td className={`${td} font-mono`}>{k.takipNo ?? k.irsaliyeNo ?? '—'}</td>
                      <td className={td}>{k.firma ?? '—'}</td>
                      <td className={td}>
                        {k.cikisSube ?? '—'} → {k.varisSube ?? k.aliciSehir ?? '—'}
                      </td>
                      <td className={td}>{k.teslimTarihi ? `${k.teslimTarihi} ${k.teslimSaati ?? ''}` : 'Teslim kaydı yok'}</td>
                      <td className={td}>{k.iadeDurumu ?? '—'}</td>
                      <td className={`${td} text-right font-mono tabular-nums`}>{fmtNum(k.desi)}</td>
                    </tr>
                  ))}
                </tbody>
              </TableWrap>
            )}
          </Block>
          <Block
            info={<SqlInfo k={kaynakOf(c)} alan="_hepsi" label="Fatura ve iade" />}
            title="Fatura ve iade (Logo)"
            help={c.logo?.dataEnd ? `Logo verisi ${fmtDay(c.logo.dataEnd)} tarihine kadar; sonrası için «fatura kesilmedi» denmez.` : 'Logo kaydı'}
          >
            {c.invoices.length === 0 ? (
              <Empty title="Fatura yok">{c.account?.cariKodu ? 'Pencerede bu cari koduna fatura yok.' : 'Cari kodu olmadığı için Logo aranamadı.'}</Empty>
            ) : (
              <TableWrap>
                <thead>
                  <tr>
                    <th className={th}>Tarih</th>
                    <th className={th}>Belge no</th>
                    <th className={th}>Tür</th>
                    <th className={`${th} text-right`}>Net tutar</th>
                  </tr>
                </thead>
                <tbody>
                  {c.invoices.map((f, i) => (
                    <tr key={`${f.no}-${i}`} className="border-t border-slate-100">
                      <td className={td}>{fmtDay(f.tarih)}</td>
                      <td className={`${td} font-mono`}>{f.no ?? '—'}</td>
                      <td className={td}>{f.iade ? <Pill tone="warn">İade</Pill> : 'Satış'}</td>
                      <td className={`${td} text-right font-mono tabular-nums`}>{fmtTl(f.tutar)}</td>
                    </tr>
                  ))}
                </tbody>
              </TableWrap>
            )}
          </Block>
          {c.tickets.length > 0 && (
            <Block title="Önceki talepler" help="Destek masasında aynı adresten açılmış talepler.">
              <ul className="divide-y divide-slate-100">
                {c.tickets.map((t) => (
                  <li key={t.ref} className="flex flex-wrap items-center justify-between gap-2 py-2 text-[12.5px]">
                    <span className="min-w-0 flex-1 truncate font-semibold">{t.subject ?? t.ref}</span>
                    <span className="text-canvas-muted">
                      {fmtDay(t.opened)} · {t.status ?? '—'}
                    </span>
                    {t.url && (
                      <a href={t.url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 font-bold text-canvas-violet">
                        Masada aç <ExternalLink aria-hidden className="h-3.5 w-3.5" />
                      </a>
                    )}
                  </li>
                ))}
              </ul>
            </Block>
          )}
        </>
      )}
    </div>
  );
}

export function OrderTable({ orders }: { orders: Order[] }) {
  return (
    <TableWrap>
      <thead>
        <tr>
          <th className={th}>Sipariş</th>
          <th className={th}>Tarih</th>
          <th className={th}>Durum</th>
          <th className={`${th} text-right`}>Adet / bekleyen</th>
          <th className={th}>Sevk</th>
          <th className={th}>Kargo</th>
          <th className={`${th} text-right`}>Tutar</th>
        </tr>
      </thead>
      <tbody>
        {orders.map((o) => (
          <tr key={o.id} className="border-t border-slate-100">
            <td className={`${td} font-mono`}>
              {o.no ?? '—'}
              {o.tip && <span className="block font-sans text-[11px] text-canvas-muted">{o.tip}</span>}
            </td>
            <td className={td}>{fmtDay(o.tarih)}</td>
            <td className={td}>
              <span className="flex flex-wrap gap-1">
                <Pill tone={o.riskte ? 'err' : o.acik ? 'warn' : 'muted'}>{o.durumAd}</Pill>
                {o.riskSebep && o.riskte && <span className="text-[11px] text-canvas-muted">{o.riskSebep}</span>}
              </span>
            </td>
            <td className={`${td} text-right font-mono tabular-nums`}>
              {fmtNum(o.adet)} / {fmtNum(o.bekleyen)}
            </td>
            <td className={td}>{fmtDay(o.sevkTarihi)}</td>
            <td className={td}>
              {o.kargoFirma ?? ''} {o.takipNo && <span className="font-mono">{o.takipNo}</span>}
              {o.takipUrl && (
                <a href={o.takipUrl} target="_blank" rel="noreferrer" className="ml-1 inline-flex items-center gap-0.5 font-bold text-canvas-violet">
                  takip <ExternalLink aria-hidden className="h-3 w-3" />
                </a>
              )}
              {!o.kargoFirma && !o.takipNo && '—'}
            </td>
            <td className={`${td} text-right font-mono tabular-nums`}>{fmtTl(o.kdvliTutar ?? o.tutar)}</td>
          </tr>
        ))}
      </tbody>
    </TableWrap>
  );
}
