import { useEffect, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { CalendarClock, FilePlus2, Library, Search } from 'lucide-react';
import { ENGINE_ENABLED, type Contract, type ContractSummary } from '../engine';
import { contractsListOptions, contractsSummaryOptions } from './queries';
import { Note, Pill, btnGhost, btnPrimary, errText, field, nf } from '../admin/ui';
import { crmLabel, dateTime, pct } from '../format';
import { Kpi, KpiRow, ModuleFrame, Pager, Panel, useDebounced } from './kit';
import { contractApi, metaOptions } from './contracts/api';
import { Tabs, day, errMsg, statusTone as portalTone } from './contracts/ui';
import SqlInfo, { InfoLabel } from '../components/SqlInfo';
import type { Kaynaklar } from '../components/sqlInfo';
import { RightChips } from './crmRights';
import { EmptyHint, Explain } from '../components/Explain';
import { TERM } from './contracts/glossary';

/** Köprü cevabındaki sorgu bilgisi (tipler engine.ts'te ortak; bu ekran yalnız okur). */
type WithK<T> = T & { kaynaklar?: Kaynaklar };

/** M6 Telif & Sözleşme. Portföy CRM'den okunur (salt okunur). Yeni taslak, düzenleme, zeyilname, ödeme
 *  takvimi, hakediş ve şablonlar portalda tutulur (bkz. `backend/semantic_bridge/contracts.py`); satıra
 *  dokununca sözleşmenin sayfası açılır. */

const money = new Intl.NumberFormat('tr-TR', { maximumFractionDigits: 0 });

const statusTone = (s: string | null): 'ok' | 'warn' | 'err' | 'muted' => {
  const t = (s || '').toLocaleLowerCase('tr');
  if (t.includes('yenileme')) return 'warn';
  if (t.startsWith('aktif')) return 'ok';
  if (t.includes('fesih') || t.includes('iptal')) return 'err';
  return 'muted';
};

function DaysLeft({ c, warnDays }: { c: Contract; warnDays: number }) {
  if (c.openEnded) return <Pill tone="muted">Süresiz</Pill>;
  if (c.daysLeft == null) return null;
  if (c.daysLeft < 0) return <Pill tone="muted">{nf.format(-c.daysLeft)} gün önce bitti</Pill>;
  return <Pill tone={c.daysLeft <= warnDays ? 'err' : 'muted'}>{nf.format(c.daysLeft)} gün kaldı</Pill>;
}

function Parties({ c }: { c: Contract }) {
  if (!c.parties.length) return <span className="text-canvas-muted">Taraf kaydı yok</span>;
  return (
    <ul className="space-y-0.5">
      {c.parties.map((p, i) => (
        <li key={`${p.name}-${i}`} className="flex flex-wrap items-baseline gap-x-1.5">
          <span className="font-semibold">{p.name}</span>
          {p.share != null && <span className="font-mono text-[11px] tabular-nums text-canvas-muted">{pct(p.share, 0)}</span>}
          {p.viaAgent && <span className="text-[11px] text-canvas-muted">aracılı</span>}
        </li>
      ))}
    </ul>
  );
}

function Rates({ c }: { c: Contract }) {
  if (!c.rates.length) return <span className="text-canvas-muted">Oran girilmemiş</span>;
  return (
    <div className="flex flex-wrap gap-1">
      {c.rates.map((r) => (
        <span key={r.format} className="inline-flex items-baseline gap-1 rounded-md bg-slate-100 px-1.5 py-0.5 text-[11px]">
          <span className="text-canvas-muted">{r.format}</span>
          <span className="font-mono font-bold tabular-nums">{pct(r.percent, 0)}</span>
        </span>
      ))}
    </div>
  );
}

function Title({ c }: { c: Contract }) {
  const books = c.books.map((b) => b.title);
  return (
    <div className="min-w-0">
      <Link to={`/telif-sozlesme/${c.id}`} className="break-words font-extrabold leading-snug hover:text-canvas-violet hover:underline">
        {books.length ? books.join(' · ') : 'Kitap bağlanmamış'}
      </Link>
      <div className="mt-0.5 flex flex-wrap items-center gap-1.5 font-mono text-[11px] text-canvas-muted">
        {c.no || c.code || '—'}
        {c.portal && <Pill tone="violet">Portalda: {c.portal.statusLabel}{c.portal.diff ? ` · CRM'e işlenecek ${c.portal.diff} fark` : ''}</Pill>}
      </div>
    </div>
  );
}

function Terms({ c }: { c: Contract }) {
  const advance = c.advance ? `Avans ${money.format(c.advance)}${c.currency ? ` ${c.currency}` : ''}` : null;
  const parts = [c.kind && crmLabel(c.kind), c.payment, c.basis, advance].filter(Boolean);
  return <div className="text-[11px] leading-snug text-canvas-muted">{parts.join(' · ') || '—'}</div>;
}

function Period({ c }: { c: Contract }) {
  if (!c.start && !c.end) return <span className="text-canvas-muted">Tarih girilmemiş</span>;
  return (
    <span className="whitespace-nowrap font-mono text-[11.5px] tabular-nums">
      {dateTime(c.start)} – {c.openEnded ? 'süresiz' : dateTime(c.end)}
    </span>
  );
}

function Kpis({ s, expiring, onExpiring }: { s: WithK<ContractSummary>; expiring: boolean; onExpiring: () => void }) {
  const k = s.kaynaklar;
  return (
    <KpiRow>
      <Kpi
        label="Yürürlükte"
        value={nf.format(s.active)}
        help={`${nf.format(s.total)} etkin kayıt içinde`}
        explain="CRM'de durumu aktif olan sözleşmeler (yenilemede olanlar dahil). Alttaki sayı, pasife alınmamış bütün CRM sözleşmeleridir."
        info={<SqlInfo k={k} alan="active" label="Yürürlükte" />}
      />
      <Kpi label="Yenilemede" value={nf.format(s.renewal)} help="Durumu “Aktif - Yenileme”" explain="CRM'de durumu «Aktif - Yenileme» olan sözleşmeler." info={<SqlInfo k={k} alan="renewal" label="Yenilemede" />} />
      <Kpi
        label={`${s.warnDays} günde bitiyor`}
        value={nf.format(s.expiring)}
        help={expiring ? 'Süzgeç açık; kapatmak için dokunun' : 'Listede görmek için dokunun'}
        active={expiring}
        onClick={onExpiring}
        explain={`Yürürlükte, süresiz olmayan ve bitiş tarihi bugünden itibaren ${s.warnDays} gün içinde olan sözleşmeler. Karta dokununca liste bunlara süzülür.`}
        info={<SqlInfo k={k} alan="expiring" label={`${s.warnDays} günde bitiyor`} />}
      />
      <Kpi
        label="Ortalama telif"
        value={pct(s.avgRoyalty, 1)}
        help={`Karton kapak oranı dolu ${nf.format(s.avgRoyaltyOver)} yürürlükteki sözleşme`}
        explain="Yürürlükteki sözleşmelerde karton kapak telif oranının basit ortalaması. Oranı girilmemiş sözleşmeler hesaba katılmaz."
        info={<SqlInfo k={k} alan="avgRoyalty" label="Ortalama telif" />} />
    </KpiRow>
  );
}

function PortalRecords() {
  const [text, setText] = useState('');
  const [status, setStatus] = useState('');
  const q = useDebounced(text.trim(), 300);
  const meta = useQuery(metaOptions());
  const list = useQuery({ queryKey: ['contracts', 'records', q, status], queryFn: () => contractApi.records({ q, status }) });
  const items = list.data?.items ?? [];
  return (
    <Panel>
      <div className="grid gap-2 sm:grid-cols-[minmax(0,1fr)_220px]">
        <label className="relative block">
          <span className="sr-only">Portal kayıtlarında ara</span>
          <Search aria-hidden className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-canvas-muted" />
          <input type="search" value={text} onChange={(e) => setText(e.target.value)} placeholder="No, ad, taraf ya da kitap" className={`${field} pl-9`} />
        </label>
        <select aria-label="Durum" value={status} onChange={(e) => setStatus(e.target.value)} className={field}>
          <option value="">Tüm durumlar</option>
          {Object.entries(meta.data?.statuses ?? {}).map(([k, v]) => (
            <option key={k} value={k}>{v}</option>
          ))}
        </select>
      </div>
      {list.data && items.length > 0 && (
        <div className="mt-3 text-[11.5px] font-semibold text-canvas-muted">
          <InfoLabel k={list.data.kaynaklar} alan="sayac.kayit" label="Portal kayıtları (sayı, geciken ödeme, sıradaki vade)">{`${nf.format(items.length)} kayıt`}</InfoLabel>
        </div>
      )}
      {list.error && <div className="mt-3"><Note tone="err">{errMsg(list.error)}</Note></div>}
      {list.isLoading && <p className="py-10 text-center text-[12.5px] text-canvas-muted">Okunuyor…</p>}
      {list.data && !items.length && (
        <div className="mt-3">
          {q || status ? (
            <EmptyHint title="Süzgece uyan portal kaydı yok" why="Aramayı temizleyin ya da durumu «Tüm durumlar» yapın." />
          ) : (
            <EmptyHint
              title="Portalda açılmış ya da düzenlenmiş sözleşme yok"
              why="«Yeni sözleşme» ile taslak açın ya da CRM listesinden bir sözleşmeyi açıp «Düzenle»ye basın; kayıt burada görünür."
            />
          )}
        </div>
      )}
      <ul className="mt-3 space-y-2">
        {items.map((r) => (
          <li key={r.id}>
            <Link to={`/telif-sozlesme/${r.crmId ?? r.id}`} className="block rounded-2xl border border-slate-100 bg-white/85 p-3 text-[12.5px] transition-transform duration-150 ease-out hover:border-canvas-violet/40 active:scale-[0.99]">
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-extrabold">{r.terms.title || r.no}</span>
                <Pill tone={portalTone(r.status)}>{r.statusLabel}</Pill>
                {r.crmId ? <Pill tone="muted">CRM</Pill> : <Pill tone="violet">Portalda açıldı</Pill>}
                {r.expired && <Pill tone="warn">Bitiş geçti</Pill>}
                {r.payments?.overdue ? <Pill tone="err">{r.payments.overdue} ödeme gecikti</Pill> : null}
              </div>
              <div className="mt-1 text-[11.5px] text-canvas-muted">
                <span className="font-mono">{r.no}</span>
                {r.terms.parties.length ? ` · ${r.terms.parties.map((p) => p.name).join(', ')}` : ''}
                {r.payments?.next ? ` · sıradaki ödeme ${day(r.payments.next)}` : ''}
                {` · ${r.updatedBy}`}
              </div>
            </Link>
          </li>
        ))}
      </ul>
    </Panel>
  );
}

export default function ContractsScreen() {
  const nav = useNavigate();
  const [params, setParams] = useSearchParams();
  const source = params.get('kaynak') === 'portal' ? 'portal' : 'crm';
  const meta = useQuery(metaOptions());
  const records = useQuery({ queryKey: ['contracts', 'records', '', ''], queryFn: () => contractApi.records({}) });
  const [text, setText] = useState('');
  const [status, setStatus] = useState('');
  const [kind, setKind] = useState('');
  const [expiring, setExpiring] = useState(false);
  const [order, setOrder] = useState('bitis');
  const [page, setPage] = useState(0);
  const q = useDebounced(text.trim(), 350);

  useEffect(() => setPage(0), [q, status, kind, expiring, order]);

  const summary = useQuery(contractsSummaryOptions());
  const list = useQuery(contractsListOptions(q, status, kind, expiring, order, page));

  const s = summary.data as WithK<ContractSummary> | undefined;
  const data = list.data as WithK<NonNullable<typeof list.data>> | undefined;
  const items = data?.items ?? [];
  const warnDays = s?.warnDays ?? 60;
  const err = errText(summary.error || list.error, 'Sözleşmeler okunamadı.');

  return (
    <ModuleFrame
      route="/telif-sozlesme"
      crumb="Telif & Sözleşme"
      title="Telif ve lisans sözleşmeleri"
      lead="Telif ve lisans sözleşmelerinin listesi: CRM'deki sözleşmeler ve portalda açılan taslaklar. Sözleşmeye dokununca ayrıntısı açılır. Portal CRM'e yazmaz; farklar «CRM'e işlenmesi gereken» diye gösterilir."
      source={s ? `${nf.format(s.active)} yürürlükte sözleşme` : 'CRM sözleşmeleri'}
      aside={
        <div className="flex flex-wrap justify-start gap-1.5 lg:justify-end">
          {meta.data?.can.edit && (
            <button type="button" className={btnPrimary} onClick={() => nav('/telif-sozlesme/yeni')}>
              <FilePlus2 aria-hidden className="h-4 w-4" />
              Yeni sözleşme
            </button>
          )}
          <Link to="/telif-sozlesme/odemeler" className={btnGhost}>
            <CalendarClock aria-hidden className="h-4 w-4" />
            Ödeme takvimi
          </Link>
          <Link to="/telif-sozlesme/sablonlar" className={btnGhost}>
            <Library aria-hidden className="h-4 w-4" />
            Şablonlar
          </Link>
        </div>
      }
    >
            {!ENGINE_ENABLED && <Note tone="warn">Zeki AI bağlantısı bu kurulumda açık değil; sözleşmeler okunamaz. Sistem yöneticinize haber verin.</Note>}
            {err && <Note tone="err">{err}</Note>}
            {s && <Kpis s={s} expiring={expiring} onExpiring={() => setExpiring((v) => !v)} />}

            <Tabs
              value={source}
              onChange={(v) => setParams((p) => {
                const n = new URLSearchParams(p);
                if (v === 'portal') n.set('kaynak', 'portal');
                else n.delete('kaynak');
                return n;
              }, { replace: true })}
              items={[
                { id: 'crm', label: 'CRM sözleşmeleri' },
                { id: 'portal', label: 'Portal kayıtları', count: records.data?.items.length },
              ]}
            />

            {source === 'portal' ? <PortalRecords /> : (
            <Panel>
              <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-[minmax(0,1fr)_200px_180px_170px]">
                <label className="relative block">
                  <span className="sr-only">Sözleşmelerde ara</span>
                  <Search aria-hidden className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-canvas-muted" />
                  <input
                    type="search"
                    value={text}
                    onChange={(e) => setText(e.target.value)}
                    placeholder="Kitap, hak sahibi ya da sözleşme no"
                    className={`${field} pl-9`}
                  />
                </label>
                <select aria-label="Durum" value={status} onChange={(e) => setStatus(e.target.value)} className={field}>
                  <option value="">Tüm durumlar</option>
                  {s?.statuses.map((o) => (
                    <option key={o.code} value={o.code}>
                      {crmLabel(o.label)} ({nf.format(o.count)})
                    </option>
                  ))}
                </select>
                <select aria-label="Sözleşme tipi" value={kind} onChange={(e) => setKind(e.target.value)} className={field}>
                  <option value="">Tüm tipler</option>
                  {s?.kinds.map((o) => (
                    <option key={o.code} value={o.code}>
                      {crmLabel(o.label)} ({nf.format(o.count)})
                    </option>
                  ))}
                </select>
                <select aria-label="Sıralama" value={order} onChange={(e) => setOrder(e.target.value)} className={field}>
                  <option value="bitis">Bitişi en yakın</option>
                  <option value="yeni">Son değişen</option>
                  <option value="no">Sözleşme no</option>
                </select>
              </div>

              <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-[11.5px] font-semibold text-canvas-muted">
                <InfoLabel k={s?.kaynaklar} alan="statuses[]" label="Durum süzgecindeki sayılar">Durum sayıları</InfoLabel>
                <InfoLabel k={s?.kaynaklar} alan="kinds[]" label="Tip süzgecindeki sayılar">Tip sayıları</InfoLabel>
                <InfoLabel k={data?.kaynaklar} alan="total" label="Süzgece uyan sözleşme sayısı">Süzgeçteki toplam</InfoLabel>
              </div>

              <Pager
                page={page}
                pageSize={data?.pageSize ?? 50}
                total={data?.total ?? 0}
                shown={items.length}
                loading={list.isLoading}
                fetching={list.isFetching}
                db={data?.db}
                onPage={setPage}
              />

              {!list.isLoading && !items.length && !err && (
                <div className="mt-3">
                  <EmptyHint title="Bu süzgece uyan sözleşme yok" why="Aramayı temizleyin, durum ve tip süzgeçlerini «Tüm» yapın ya da «günde bitiyor» kartındaki süzgeci kapatın." />
                </div>
              )}

              {/* Telefon ve tablet: kart listesi. */}
              <ul className="mt-3 space-y-2 lg:hidden">
                {items.map((c) => (
                  <li key={c.id} className="rounded-2xl border border-slate-100 bg-white/85 p-3 text-[12.5px]">
                    <div className="flex items-start justify-between gap-2">
                      <Title c={c} />
                      <div className="flex shrink-0 items-center gap-1">
                        {c.status && <Pill tone={statusTone(c.status)}>{crmLabel(c.status)}</Pill>}
                        <SqlInfo k={data?.kaynaklar} alan="items[]" label="Sözleşme (oran, pay, avans, kalan gün)" />
                      </div>
                    </div>
                    <div className="mt-2">
                      <Parties c={c} />
                    </div>
                    <div className="mt-2">
                      <Rates c={c} />
                    </div>
                    <div className="mt-1.5">
                      <Terms c={c} />
                    </div>
                    <div className="mt-2">
                      <RightChips rights={c.rights} compact />
                    </div>
                    <div className="mt-2 flex flex-wrap items-center gap-2">
                      <Period c={c} />
                      <DaysLeft c={c} warnDays={warnDays} />
                    </div>
                  </li>
                ))}
              </ul>

              {/* Masaüstü: tablo. */}
              {items.length > 0 && (
                <div className="mt-3 hidden overflow-x-auto rounded-2xl border border-slate-100 bg-white/85 lg:block">
                  <table className="w-full text-[12.5px]">
                    <thead>
                      <tr className="border-b border-slate-100 text-left text-[11px] font-bold uppercase tracking-wide text-canvas-muted">
                        <th className="px-3 py-2.5"><InfoLabel k={data?.kaynaklar} alan="items[].portal" label="Portal rozeti ve fark sayısı">Kitap ve sözleşme no</InfoLabel></th>
                        <th className="px-3 py-2.5">
                          <span className="inline-flex items-center gap-1">
                            <InfoLabel k={data?.kaynaklar} alan="items[].parties" label="Hak sahibi payı">Hak sahibi</InfoLabel>
                            <Explain label="Hak sahibi">Yüzde, kişinin telifteki payıdır. «aracılı», hak sahibine ajans ya da temsilci üzerinden bağlanıldığını gösterir.</Explain>
                          </span>
                        </th>
                        <th className="px-3 py-2.5">
                          <span className="inline-flex items-center gap-1">
                            <InfoLabel k={data?.kaynaklar} alan="items[].rates" label="Telif oranları ve avans">Telif oranları ve haklar</InfoLabel>
                            <Explain label="Telif oranı">{TERM.telifOrani} Altında ödeme şekli, telif esası ve avans yazar; renkli etiketler sözleşmedeki hakları gösterir.</Explain>
                          </span>
                        </th>
                        <th className="px-3 py-2.5"><InfoLabel k={data?.kaynaklar} alan="items[].daysLeft" label="Kalan gün">Süre</InfoLabel></th>
                        <th className="px-3 py-2.5">Durum</th>
                      </tr>
                    </thead>
                    <tbody>
                      {items.map((c) => (
                        <tr key={c.id} className="border-b border-slate-100 align-top last:border-0">
                          <td className="max-w-[340px] px-3 py-2.5">
                            <Title c={c} />
                          </td>
                          <td className="max-w-[280px] px-3 py-2.5">
                            <Parties c={c} />
                          </td>
                          <td className="max-w-[320px] px-3 py-2.5">
                            <Rates c={c} />
                            <div className="mt-1">
                              <Terms c={c} />
                            </div>
                            <div className="mt-1.5">
                              <RightChips rights={c.rights} compact />
                            </div>
                          </td>
                          <td className="px-3 py-2.5">
                            <Period c={c} />
                            <div className="mt-1">
                              <DaysLeft c={c} warnDays={warnDays} />
                            </div>
                          </td>
                          <td className="px-3 py-2.5">
                            {c.status && <Pill tone={statusTone(c.status)}>{crmLabel(c.status)}</Pill>}
                            {c.stage && <div className="mt-1 text-[11px] leading-snug text-canvas-muted">{c.stage}</div>}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </Panel>
            )}
    </ModuleFrame>
  );
}
