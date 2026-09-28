import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { CheckCircle2, ChevronRight, Download, Link2, Lock, LockOpen, Scale } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import { Loading, Note, Pill, TableWrap, btnGhost, btnPrimary, errText, td, th } from '../admin/ui';
import { Panel, Pager } from '../editorial/kit';
import Sheet from '../editorial/studio/reader/Sheet';
import CardSql from '../stitch/CardSql';
import SqlInfo, { InfoLabel } from '../components/SqlInfo';
import { AskSheet } from '../budget/parts';
import { MAP_LABEL, RULE_LABEL, SOURCE_LABEL, financeApi, fmtDay, fmtMoney, fmtNum, fmtPct, type Grain, type Meta, type Period, type PnlRow } from './api';
import { Approx, DataEnd, Money, pressable } from './parts';
import AccountMapSheet from './AccountMapSheet';

/** Gelir tablosu: dönem · önceki dönem · geçen yıl · bütçe. Satır → hesaplar → Logo fiş satırları (iki dokunuş). */

const COLS: Array<[string, string]> = [['donem', 'Bu dönem'], ['onceki', 'Önceki dönem'], ['gecenYil', 'Geçen yıl'], ['butce', 'Bütçe']];

function EntriesSheet({ hesap, period, onClose }: { hesap: string | null; period: Period; onClose: () => void }) {
  const [page, setPage] = useState(0);
  const q = useQuery({
    queryKey: ['finance', 'entries', hesap, period, page],
    queryFn: () => financeApi.entries(hesap!, period, page),
    enabled: ENGINE_ENABLED && !!hesap,
  });
  const d = q.data;
  return (
    <Sheet open={!!hesap} onClose={() => { setPage(0); onClose(); }} modal wide title={`Logo fişleri · ${hesap ?? ''}`}
      subtitle={d ? `${d.donem}. Kapanış ve yansıtma fişindeki satırlar listede durur ama rapora girmez.` : undefined}>
      {q.isLoading ? <Loading /> : q.error ? <Note tone="err">{errText(q.error, "Logo'dan okunamadı.")}</Note> : d && (
        <div className="flex flex-col gap-3">
          <DataEnd data={d} />
          <TableWrap>
            <thead>
              <tr>
                <th className={th}>Tarih</th>
                <th className={th}>Fiş</th>
                <th className={th}>Hesap</th>
                <th className={th}>Açıklama</th>
                <th className={`${th} text-right`}><InfoLabel k={d.kaynaklar} alan="items[]" label="Fiş satırları · borç">Borç</InfoLabel></th>
                <th className={`${th} text-right`}><InfoLabel k={d.kaynaklar} alan="items[]" label="Fiş satırları · alacak">Alacak</InfoLabel></th>
                <th className={th}>Merkez</th>
                <th className={th}>Raporda</th>
              </tr>
            </thead>
            <tbody>
              {d.items.map((e, i) => (
                <tr key={i} className={`border-t border-slate-100 ${e.kural !== 'dahil' ? 'text-canvas-muted' : ''}`}>
                  <td className={`${td} whitespace-nowrap`}>{fmtDay(e.tarih)}</td>
                  <td className={`${td} whitespace-nowrap font-mono`}>{e.fisNo ?? '—'}</td>
                  <td className={`${td} whitespace-nowrap font-mono`}>{e.hesap}</td>
                  <td className={td}>{e.aciklama ?? '—'}</td>
                  <td className={`${td} text-right`}><Money v={e.borc} /></td>
                  <td className={`${td} text-right`}><Money v={e.alacak} /></td>
                  <td className={td}>{e.merkez ?? '—'}</td>
                  <td className={`${td} whitespace-nowrap`}>{RULE_LABEL[e.kural] ?? e.kural}</td>
                </tr>
              ))}
            </tbody>
          </TableWrap>
          <Pager page={d.page} pageSize={d.pageSize} total={d.total} shown={d.items.length} loading={q.isLoading} fetching={q.isFetching} onPage={setPage} />
          <CardSql sql={d.sql} />
        </div>
      )}
    </Sheet>
  );
}

function LineSheet({ row, period, onClose, onAccount }: { row: PnlRow | null; period: Period; onClose: () => void; onAccount: (h: string) => void }) {
  const q = useQuery({
    queryKey: ['finance', 'line', row?.kod, period],
    queryFn: () => financeApi.lineAccounts(row!.kod, period),
    enabled: ENGINE_ENABLED && !!row,
  });
  const d = q.data;
  return (
    <Sheet open={!!row} onClose={onClose} modal wide title={row?.ad ?? ''}
      subtitle={d ? `${d.donem} · ${d.items.length} hesap · kâr etkisi ${fmtMoney(d.toplam)}. Hesaba dokununca Logo fişleri açılır.` : undefined}>
      {q.isLoading ? <Loading /> : q.error ? <Note tone="err">{errText(q.error, 'Hesaplar okunamadı.')}</Note> : d && (
        !d.items.length ? <Note tone="info">Bu dönemde bu satıra düşen hareket yok.</Note> : (
          <ul className="flex flex-col gap-1.5">
            <li className="flex items-center justify-end px-1 text-[11.5px] font-semibold text-canvas-muted">
              <InfoLabel k={d.kaynaklar} alan="items[]" label={`${row?.ad ?? 'Satır'} · hesaplar`}>Hesap tutarlarının kaynağı</InfoLabel>
            </li>
            {d.items.map((a) => (
              <li key={a.hesap}>
                <button type="button" onClick={() => onAccount(a.hesap)}
                  className={`flex min-h-11 w-full items-center gap-3 rounded-xl border border-slate-100 bg-white/80 px-3 py-2 text-left hover:bg-white ${pressable}`}>
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-[12.5px] font-bold"><span className="font-mono">{a.hesap}</span> · {a.ad ?? '—'}</div>
                    <div className="mt-0.5 flex flex-wrap gap-1.5 text-[11px] text-canvas-muted">
                      <Pill tone={MAP_LABEL[a.esleme.durum].tone}>{MAP_LABEL[a.esleme.durum].label}</Pill>
                      <span>{a.esleme.kaynak ? SOURCE_LABEL[a.esleme.kaynak] : ''}{a.esleme.kayit && a.esleme.kayit !== a.hesap ? ` (${a.esleme.kayit})` : ''}</span>
                      <span>{fmtNum(a.satirSayisi)} fiş satırı</span>
                    </div>
                  </div>
                  <Money v={a.etki} strong />
                  <ChevronRight aria-hidden className="h-4 w-4 shrink-0 text-canvas-muted" />
                </button>
              </li>
            ))}
          </ul>
        )
      )}
    </Sheet>
  );
}

function Reconcile({ period }: { period: Period }) {
  const q = useQuery({ queryKey: ['finance', 'recon', period], queryFn: () => financeApi.reconciliation(period), enabled: ENGINE_ENABLED });
  const d = q.data;
  if (!d) return q.error ? <Note tone="err">{errText(q.error, 'Mutabakat okunamadı.')}</Note> : null;
  return (
    <Panel>
      <h3 className="text-[15px] font-extrabold">Net satış mutabakatı · {d.donem}</h3>
      <p className="mb-2 max-w-[80ch] text-[12px] text-canvas-muted">
        Muhasebedeki satış hesapları (eşlemeyle A + B satırları) ile fatura satırlarından hesaplanan net satış (satır iskontosu ve iade düşülmüş) iki ayrı kaynaktır; fark görünür durur.
      </p>
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
        <div className="rounded-xl bg-white/80 p-3">
          <div className="text-[11px] font-bold uppercase text-canvas-muted"><InfoLabel k={d.kaynaklar} alan="muhasebe">Muhasebe net satış</InfoLabel></div>
          <div className="mt-1 text-[18px] font-bold"><Money v={d.muhasebe.netSatis} /></div>
          <div className="text-[11.5px] text-canvas-muted">Brüt <Money v={d.muhasebe.brutSatis} /> · indirim <Money v={d.muhasebe.satisIndirimleri} /></div>
        </div>
        <div className="rounded-xl bg-white/80 p-3">
          <div className="text-[11px] font-bold uppercase text-canvas-muted"><InfoLabel k={d.kaynaklar} alan="fatura">Fatura net satış</InfoLabel></div>
          <div className="mt-1 text-[18px] font-bold"><Money v={d.fatura?.netSatis} /></div>
          <div className="text-[11.5px] text-canvas-muted">Satış <Money v={d.fatura?.satis} /> · iade <Money v={d.fatura?.iade} /> · iskonto <Money v={d.fatura?.iskonto} /></div>
        </div>
        <div className={`rounded-xl p-3 ${d.fark !== null && Math.abs(d.fark) >= 0.01 ? 'bg-amber-50' : 'bg-emerald-50'}`}>
          <div className="text-[11px] font-bold uppercase text-canvas-muted"><InfoLabel k={d.kaynaklar} alan="fark" label="Mutabakat farkı">Fark (muhasebe − fatura)</InfoLabel></div>
          <div className="mt-1 text-[18px] font-bold"><Money v={d.fark} /></div>
        </div>
      </div>
      {d.fark !== null && Math.abs(d.fark) >= 0.01 && (
        <ul className="mt-2 list-disc pl-5 text-[12px] leading-snug text-canvas-muted">
          {d.olasiNedenler.map((n) => <li key={n}>{n}</li>)}
        </ul>
      )}
    </Panel>
  );
}

export default function PnlTab({ meta, year, month, grain }: { meta: Meta; year: number; month: number; grain: Grain }) {
  const qc = useQueryClient();
  const period: Period = { year, month, grain };
  const [line, setLine] = useState<PnlRow | null>(null);
  const [account, setAccount] = useState<string | null>(null);
  const [mapOpen, setMapOpen] = useState(false);
  const [ask, setAsk] = useState<null | 'close' | 'reopen'>(null);
  const q = useQuery({ queryKey: ['finance', 'pnl', period], queryFn: () => financeApi.pnl(period), enabled: ENGINE_ENABLED });
  const act = useMutation({
    mutationFn: (text: string) => (ask === 'close' ? financeApi.close(year, month, text || undefined) : financeApi.reopen(year, month, text)),
    onSuccess: () => {
      toast.success(ask === 'close' ? 'Ay kapandı.' : 'Ay yeniden açıldı.');
      setAsk(null);
      qc.invalidateQueries({ queryKey: ['finance', 'pnl'] });
    },
    onError: (e) => toast.error(errText(e, 'İşlem yapılamadı.') ?? ''),
  });
  if (q.isLoading) return <Loading />;
  if (q.error) return <Note tone="err">{errText(q.error, 'Gelir tablosu açılamadı.')}</Note>;
  const d = q.data;
  if (!d) return null;
  const cols = COLS.filter(([k]) => d.columns[k]);
  const cur = d.columns.donem;
  const close = d.kapanis;
  return (
    <div className="flex flex-col gap-3">
      <DataEnd data={d} extra={!cur.complete ? <span className="text-amber-800">Dönemin son ayı henüz tamamlanmadı.</span> : null} />
      <div className="flex flex-wrap items-center gap-2 px-1">
        {d.mizan.durum === 'denk' ? (
          <span className="inline-flex items-center gap-1 rounded-md bg-emerald-50 px-2 py-1 text-[12px] font-bold text-emerald-700" title="Dönemin bütün muhasebe satırlarında Σ borç = Σ alacak (0,01 ₺ toleransla)">
            <Scale aria-hidden className="h-3.5 w-3.5" /> Mizan denk
          </span>
        ) : d.mizan.durum === 'fark' ? (
          <span className="inline-flex items-center gap-1 rounded-md bg-red-50 px-2 py-1 text-[12px] font-bold text-red-700">
            <Scale aria-hidden className="h-3.5 w-3.5" /> Mizan farkı {fmtMoney(d.mizan.fark)}
          </span>
        ) : <Pill tone="muted">Mizan okunmadı</Pill>}
        <SqlInfo k={d.kaynaklar} alan="mizan" label="Mizan denkliği" />
        {grain === 'ay' && close?.durum === 'kapandi' && (
          <span className="inline-flex items-center gap-1 rounded-md bg-slate-100 px-2 py-1 text-[12px] font-bold">
            <Lock aria-hidden className="h-3.5 w-3.5" /> Kapandı · {close.kapatan}, {fmtDay(close.kapanisTarihi)}
          </span>
        )}
        {close?.degisti && <Pill tone="warn">Kapanıştan sonra Logo'daki tutarlar değişti</Pill>}
        <div className="ml-auto flex flex-wrap gap-2">
          <button type="button" className={btnGhost} onClick={() => setMapOpen(true)}>
            <Link2 aria-hidden className="h-4 w-4" /> Hesap eşlemesi
          </button>
          {meta.me.canExport && (
            <a className={btnGhost} href={financeApi.pnlExportUrl(period)} download>
              <Download aria-hidden className="h-4 w-4" /> Excel
            </a>
          )}
          {grain === 'ay' && meta.me.canClose && close?.durum !== 'kapandi' && cur.complete && (
            <button type="button" className={btnPrimary} onClick={() => setAsk('close')}>
              <CheckCircle2 aria-hidden className="h-4 w-4" /> Ayı kapat
            </button>
          )}
          {grain === 'ay' && meta.me.canClose && close?.durum === 'kapandi' && (
            <button type="button" className={btnGhost} onClick={() => setAsk('reopen')}>
              <LockOpen aria-hidden className="h-4 w-4" /> Yeniden aç
            </button>
          )}
        </div>
      </div>
      {(d.esleme.eslenmemis > 0 || (d.esleme.onaysizTutar ?? 0) > 0.005) && (
        <Note tone="warn">
          {d.esleme.eslenmemis > 0 && <>{d.esleme.eslenmemis} hesap eşlenmemiş ({fmtMoney(d.esleme.eslenmemisTutar)}); «Eşlenmemiş hesaplar» satırında durur ve net kâra katılır. </>}
          {(d.esleme.onaysizTutar ?? 0) > 0.005 && <>Eşlemesi muhasebece onaylanmamış hesap tutarı {fmtMoney(d.esleme.onaysizTutar)}: tablo onaylanana kadar taslaktır.</>}
          <SqlInfo k={d.kaynaklar} alan="esleme" label="Eşleme durumu" className="ml-1" />
        </Note>
      )}
      {d.maliyet.yaklasik && (
        <Note tone="warn">
          Bu dönemin satışlarının {fmtPct(1 - (d.maliyet.maliyetliPay ?? 0))}'inde ({fmtNum(d.maliyet.maliyetsizSatir)} / {fmtNum(d.maliyet.satisSatir)} satır) maliyet işlenmemiş.
          Satışların maliyeti ve brüt kâr eksik okunur: <strong>yaklaşık</strong>.<SqlInfo k={d.kaynaklar} alan="maliyet" label="Maliyet kapsamı" className="ml-1" />
        </Note>
      )}

      {/* Masaüstü: tablo; telefonda kart listesi. */}
      <div className="hidden sm:block">
        <TableWrap>
          <thead>
            <tr>
              <th className={th}>Gelir tablosu</th>
              {cols.map(([k, label]) => (
                <th key={k} className={`${th} text-right`}>
                  <div className="inline-flex items-center gap-1">{label}<SqlInfo k={d.kaynaklar} alan={`rows[].values.${k}`} label={`Gelir tablosu · ${label} (${d.columns[k].label})`} /></div>
                  <div className="font-semibold normal-case tracking-normal">{d.columns[k].label}</div>
                </th>
              ))}
              {d.columns.butce && <th className={`${th} text-right`}><InfoLabel k={d.kaynaklar} alan="rows[].values.fark" label="Bütçeden fark (dönem − bütçe)">Bütçeden fark</InfoLabel></th>}
            </tr>
          </thead>
          <tbody>
            {d.rows.map((r) => {
              const sub = r.tur === 'ara_toplam';
              const b = r.values.butce;
              const diff = b !== null && b !== undefined && r.values.donem !== null ? (r.values.donem ?? 0) - b : null;
              return (
                <tr key={r.kod} className={`border-t border-slate-100 ${sub ? 'bg-slate-50/70' : ''} cursor-pointer hover:bg-white`} onClick={() => setLine(r)}>
                  <td className={`${td} ${sub ? 'font-extrabold' : r.ust ? 'pl-7' : 'font-semibold'}`}>
                    <div className="flex items-center gap-1.5">
                      <span>{r.ad}</span>
                      {r.yaklasik && <Approx title={r.notlar.join(' ')} />}
                      {r.onaysiz ? <Pill tone="warn">onaysız</Pill> : null}
                    </div>
                  </td>
                  {cols.map(([k]) => (
                    <td key={k} className={`${td} whitespace-nowrap text-right`}><Money v={r.values[k]} strong={sub} /></td>
                  ))}
                  {d.columns.butce && <td className={`${td} whitespace-nowrap text-right`}><Money v={diff} /></td>}
                </tr>
              );
            })}
          </tbody>
        </TableWrap>
      </div>
      <ul className="flex flex-col gap-1.5 sm:hidden">
        <li className="flex flex-wrap items-center justify-end gap-x-3 gap-y-1 px-1 text-[11.5px] font-semibold text-canvas-muted">
          <InfoLabel k={d.kaynaklar} alan="rows[].values.donem" label={`Gelir tablosu · ${cur.label}`}>Tutarların kaynağı</InfoLabel>
          {d.columns.gecenYil && <InfoLabel k={d.kaynaklar} alan="rows[].values.gecenYil" label={`Gelir tablosu · geçen yıl (${d.columns.gecenYil.label})`}>Geçen yıl</InfoLabel>}
          {d.columns.butce && <InfoLabel k={d.kaynaklar} alan="rows[].values.butce" label="Gelir tablosu · bütçe">Bütçe</InfoLabel>}
        </li>
        {d.rows.map((r) => (
          <li key={r.kod}>
            <button type="button" onClick={() => setLine(r)}
              className={`flex min-h-12 w-full items-center gap-2 rounded-xl px-3 py-2 text-left ${r.tur === 'ara_toplam' ? 'bg-slate-100' : 'bg-white/80'} ${pressable}`}>
              <div className="min-w-0 flex-1">
                <div className={`text-[12.5px] ${r.tur === 'ara_toplam' ? 'font-extrabold' : 'font-semibold'}`}>{r.ad} {r.yaklasik && <Approx />}</div>
                <div className="mt-0.5 text-[11px] text-canvas-muted">
                  {d.columns.gecenYil && <>Geçen yıl {fmtMoney(r.values.gecenYil)} · </>}
                  {d.columns.butce && r.values.butce !== null && r.values.butce !== undefined && <>Bütçe {fmtMoney(r.values.butce)}</>}
                </div>
              </div>
              <span className="text-[13px]"><Money v={r.values.donem} strong /></span>
            </button>
          </li>
        ))}
      </ul>

      <p className="px-1 text-[11.5px] leading-snug text-canvas-muted">
        Tutar = hesabın kâr etkisi (alacak − borç): gelir artı, gider eksi. Rapor dışı: dışlanan hesaplar {fmtMoney(d.dislanan)}<SqlInfo k={d.kaynaklar} alan="dislanan" label="Dışlanan hesaplar" className="ml-0.5" />,
        yansıtma satırları {d.kurallar.yansitma.hesap} hesap, kapanış fişi satırları {d.kurallar.kapanis.hesap} hesap<SqlInfo k={d.kaynaklar} alan="kurallar" label="Yansıtma ve kapanış satırları" className="ml-0.5" /> (7/A'da gider 7 ile başlayan hesapta bir kez sayılır).
        {d.columns.butce?.plan ? ` Bütçe: ${d.columns.butce.plan.title}.` : d.columns.butce?.note ? ` ${d.columns.butce.note}` : ''}
      </p>

      <Reconcile period={period} />

      <LineSheet row={line} period={period} onClose={() => setLine(null)} onAccount={(h) => setAccount(h)} />
      <EntriesSheet hesap={account} period={period} onClose={() => setAccount(null)} />
      <AccountMapSheet open={mapOpen} meta={meta} year={year} onClose={() => setMapOpen(false)} />
      <AskSheet
        open={ask !== null}
        busy={act.isPending}
        title={ask === 'close' ? `${meta.months[month - 1]} ${year} kapanışı` : `${meta.months[month - 1]} ${year} yeniden açılsın`}
        message={ask === 'close'
          ? 'Ayın gelir tablosu bu haliyle saklanır; Logo\'da sonradan değişen tutar «kapanıştan sonra değişti» olarak görünür.'
          : 'Kapanış kaldırılır; gerekçe değişiklik kaydına yazılır.'}
        confirm={ask === 'close' ? 'Ayı kapat' : 'Yeniden aç'}
        input={ask === 'close' ? 'Not (isteğe bağlı)' : 'Gerekçe'}
        required={ask === 'reopen'}
        onClose={() => setAsk(null)}
        onConfirm={(text) => act.mutate(text)}
      />
    </div>
  );
}
