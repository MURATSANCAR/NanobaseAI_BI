import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Plus, Undo2 } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import SqlInfo from '../components/SqlInfo';
import { Loading, Note, Pill, TableWrap, btnGhost, btnPrimary, errText, field, label as labelCls, td, th } from '../admin/ui';
import { Panel } from '../editorial/kit';
import { Block } from '../marketing/parts';
import { AskSheet } from '../budget/parts';
import { RowsError, adsApi, fileToBase64, fmtDay, fmtMoney2, type ImportRow, type Platform, type Preview } from './api';
import { AdsFrame, useAdsMeta } from './parts';
import { FileDrop } from '../components/FileDrop';
import { MB } from '../components/fileDropRules';

/** Harcama verisinin içe aktarılması: hesap seç → dosyayı bırak → kolon eşlemesini onayla → yükle. Eşleme hesaba kaydedilir;
 *  aynı platformun sonraki dosyası tek tıkla girer. Okunamayan satır varsa dosya yüklenmez (toplam eksik kalmasın). */
export default function AdsImport() {
  const qc = useQueryClient();
  const meta = useAdsMeta();
  const m = meta.data;
  const [accountId, setAccountId] = useState('');
  const [newAcc, setNewAcc] = useState<{ platform: Platform; ad: string } | null>(null);
  const [file, setFile] = useState<{ name: string; b64: string } | null>(null);
  const [pv, setPv] = useState<Preview | null>(null);
  const [rowsErr, setRowsErr] = useState<RowsError | null>(null);
  const [undo, setUndo] = useState<ImportRow | null>(null);
  const imports = useQuery({ queryKey: ['ads', 'imports'], queryFn: adsApi.imports, enabled: ENGINE_ENABLED });
  const acc = m?.accounts.find((a) => a.id === accountId) ?? (m?.accounts.length === 1 ? m.accounts[0] : undefined);

  const createAcc = useMutation({
    mutationFn: adsApi.newAccount,
    onSuccess: (a) => {
      toast.success(`Hesap eklendi: ${a.ad}`);
      setAccountId(a.id);
      setNewAcc(null);
      qc.invalidateQueries({ queryKey: ['ads', 'meta'] });
    },
    onError: (e) => toast.error(errText(e, 'Hesap eklenemedi.') ?? ''),
  });
  const preview = useMutation({
    mutationFn: (b: { name: string; b64: string; eslem?: Record<string, string>; baslikSatiri?: number }) =>
      adsApi.preview({ dosyaAdi: b.name, icerik: b.b64, hesapId: acc?.id, eslem: b.eslem, baslikSatiri: b.baslikSatiri }),
    onSuccess: (p) => { setPv(p); setRowsErr(null); },
    onError: (e) => toast.error(errText(e, 'Dosya okunamadı.') ?? ''),
  });
  const commit = useMutation({
    mutationFn: () => adsApi.commit({ dosyaAdi: file!.name, icerik: file!.b64, hesapId: acc!.id, eslem: pv!.eslem, baslikSatiri: pv!.baslikSatiri }),
    onSuccess: (r) => {
      const tot = Object.entries(r.paraBirimiToplam).map(([k, v]) => `${k} ${v.toLocaleString('tr-TR')}`).join(', ');
      toast.success(`Yüklendi: ${r.kampanyaGun} kampanya-gün, ${tot}. Kitap eşleştirmesi arka planda.`);
      setFile(null);
      setPv(null);
      qc.invalidateQueries({ queryKey: ['ads'] });
    },
    onError: (e) => {
      if (e instanceof RowsError) setRowsErr(e);
      toast.error(errText(e, 'Yüklenemedi.') ?? '');
    },
  });
  const undoImport = useMutation({
    mutationFn: (id: string) => adsApi.undoImport(id),
    onSuccess: (r) => { toast.success(`Geri alındı: ${r.silinenKampanyaGun} kampanya-gün silindi.`); setUndo(null); qc.invalidateQueries({ queryKey: ['ads'] }); },
    onError: (e) => toast.error(errText(e, 'Geri alınamadı.') ?? ''),
  });

  // Tür ve boyut ortak yükleme alanında denetlenir (sınır: Yönetim → ADS_IMPORT_MAX_MB).
  const take = async (f: File) => {
    const b64 = await fileToBase64(f);
    setFile({ name: f.name, b64 });
    preview.mutate({ name: f.name, b64 });
  };
  const maxBytes = m ? m.settings.maxUploadMb * MB : undefined;
  const remap = (field_: string, col: string) => {
    if (!pv || !file) return;
    const eslem = { ...pv.eslem };
    if (col) eslem[field_] = col;
    else delete eslem[field_];
    preview.mutate({ name: file.name, b64: file.b64, eslem, baslikSatiri: pv.baslikSatiri });
  };
  const t = pv?.deneme;
  const canCommit = !!acc && !!pv && pv.eksik.length === 0 && !!t && t.hataSayisi === 0 && t.satir > 0;

  if (m && !m.me.canEdit) {
    return (
      <AdsFrame title="Harcama verisi yükle" meta={m}>
        {/* Yükleme gizlenmez: kilitli görünür ve gereken yetkiyi yazar. */}
        <Block title="Dosya" help="Reklam platformunun günlük kırılımlı raporu (CSV ya da Excel).">
          <FileDrop title="Reklam raporu yükle" accept=".csv,.tsv,.txt,.xlsx,.xlsm" maxBytes={maxBytes} feature="reklam.duzenle" allowed={false} onPick={() => undefined} />
        </Block>
        <History rows={imports.data?.items ?? []} canUndo={false} onUndo={() => undefined} />
      </AdsFrame>
    );
  }

  return (
    <AdsFrame
      title="Harcama verisi yükle"
      lead="Reklam platformunun rapor ekranından günlük kırılımlı raporu CSV ya da Excel olarak indirin ve buraya bırakın. Portal platforma bağlanmaz ve hiçbir şey göndermez."
      meta={m}
    >
      {meta.isLoading && <Loading />}
      {m && (
        <Block title="1 · Reklam hesabı" help="Kolon eşlemesi hesap başına kaydedilir.">
          <div className="flex flex-col gap-2 sm:flex-row sm:items-end">
            <label className="flex min-w-0 flex-1 flex-col gap-1">
              <span className={labelCls}>Hesap</span>
              <select className={field} value={acc?.id ?? ''} onChange={(e) => { setAccountId(e.target.value); setPv(null); setFile(null); }}>
                <option value="">Seçin</option>
                {m.accounts.map((a) => <option key={a.id} value={a.id}>{a.platformAdi} · {a.ad}{a.sonGun ? ` (son gün ${a.sonGun})` : ''}</option>)}
              </select>
            </label>
            <button type="button" className={btnGhost} onClick={() => setNewAcc({ platform: 'google', ad: '' })}><Plus aria-hidden className="h-4 w-4" />Yeni hesap</button>
          </div>
          {newAcc && (
            <div className="mt-2 grid grid-cols-1 gap-2 rounded-2xl bg-slate-50 p-3 sm:grid-cols-[200px_1fr_auto] sm:items-end">
              <label className="flex flex-col gap-1">
                <span className={labelCls}>Platform</span>
                <select className={field} value={newAcc.platform} onChange={(e) => setNewAcc({ ...newAcc, platform: e.target.value as Platform })}>
                  {Object.entries(m.platforms).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                </select>
              </label>
              <label className="flex flex-col gap-1">
                <span className={labelCls}>Hesap adı</span>
                <input className={field} value={newAcc.ad} placeholder="ör. Timaş Google Ads" onChange={(e) => setNewAcc({ ...newAcc, ad: e.target.value })} />
              </label>
              <button type="button" className={btnPrimary} disabled={!newAcc.ad.trim() || createAcc.isPending} onClick={() => createAcc.mutate(newAcc)}>Ekle</button>
            </div>
          )}
        </Block>
      )}

      {/* Dosya alanı hesap seçilmeden de görünür; hesap yoksa pasif ve neyin eksik olduğunu yazar. */}
      {m && (
        <Block title="2 · Dosya" help="CSV (virgül, noktalı virgül ya da sekme) ya da Excel (.xlsx). Satır başına bir kampanya-gün.">
          <FileDrop
            title={file ? `Seçilen: ${file.name} — başka dosya bırakın` : 'Reklam raporu yükle'}
            accept=".csv,.tsv,.txt,.xlsx,.xlsm"
            maxBytes={maxBytes}
            feature="reklam.duzenle"
            disabled={!acc}
            disabledReason="Önce yukarıdan reklam hesabını seçin ya da «Yeni hesap» ile ekleyin; kolon eşlemesi hesaba kaydedilir."
            busy={preview.isPending}
            onPick={(f) => void take(f)}
          />
        </Block>
      )}

      {pv && m && (
        <Block title="3 · Kolon eşlemesi"
          help={`Dosyadaki her kolonun hangi bilgi olduğunu seçin (ör. «Cost» kolonu = Harcama); * işaretliler zorunludur. Başlık ${pv.baslikSatiri}. satırda, ${pv.satirSayisi} veri satırı. Eşleme ${pv.eslemKaynagi === 'kayitli' ? 'hesabın kayıtlı eşlemesinden' : pv.eslemKaynagi === 'elle' ? 'sizin seçiminizden' : 'kolon adlarından'} geldi.`}>
          {pv.zekiHata && <Note tone="warn">{pv.zekiHata}</Note>}
          {Object.keys(pv.zeki ?? {}).length > 0 && (
            <Note tone="info">Zeki AI önerisi: {Object.entries(pv.zeki).map(([f, v]) => `${m.fields[f]} → «${v.kolon}»`).join(', ')}. Kontrol edin.</Note>
          )}
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 xl:grid-cols-3">
            {Object.entries(m.fields).map(([f, lbl]) => (
              <label key={f} className="flex flex-col gap-1">
                <span className={labelCls}>{lbl}{m.required.includes(f) ? ' *' : ''}</span>
                <select className={field} value={pv.eslem[f] ?? ''} disabled={preview.isPending} onChange={(e) => remap(f, e.target.value)}>
                  <option value="">— yok —</option>
                  {pv.kolonlar.map((c, i) => <option key={`${c}-${i}`} value={c}>{c || `(${i + 1}. kolon, adsız)`}</option>)}
                </select>
              </label>
            ))}
          </div>
          {pv.eksik.length > 0 && <div className="mt-2"><Note tone="warn">Eksik zorunlu alan: {pv.eksik.map((f) => m.fields[f]).join(', ')}.</Note></div>}
          {t && (
            <div className="mt-3 flex flex-col gap-2">
              <div className="flex flex-wrap gap-1.5 text-[12px]">
                <Pill tone="violet">{t.satir} satır</Pill>
                <Pill tone="muted">{t.kampanya} kampanya</Pill>
                <Pill tone="muted">{fmtDay(t.bas)} – {fmtDay(t.bit)}</Pill>
                {Object.entries(t.toplam).map(([k, v]) => <Pill key={k} tone="ok">Harcama {k === 'TRY' || k === '?' ? fmtMoney2(v) : `${k} ${v.toLocaleString('tr-TR')}`}</Pill>)}
                {t.ozetSatiri > 0 && <Pill tone="muted">{t.ozetSatiri} özet satırı atlandı</Pill>}
                <Pill tone="muted">ondalık «{t.ondalik}»</Pill>
              </div>
              {t.hataSayisi > 0 && (
                <Note tone="err">
                  {t.hataSayisi} satır okunamadı; bu haliyle yüklenmez. {t.hatalar.length < t.hataSayisi ? `İlk ${t.hatalar.length} örnek:` : ''}
                  <ul className="mt-1 list-disc pl-5 font-normal">{t.hatalar.map((h) => <li key={h}>{h}</li>)}</ul>
                </Note>
              )}
            </div>
          )}
          {rowsErr && <div className="mt-2"><Note tone="err">{rowsErr.message}<ul className="mt-1 list-disc pl-5 font-normal">{rowsErr.hatalar.map((h) => <li key={h}>{h}</li>)}</ul></Note></div>}
          <div className="mt-3 overflow-x-auto rounded-xl border border-slate-100">
            <table className="w-full min-w-[640px] text-[11.5px]">
              <thead><tr>{pv.kolonlar.map((c, i) => <th key={`${c}-${i}`} className={th}>{c}</th>)}</tr></thead>
              <tbody>{pv.ornek.map((r, i) => <tr key={i} className="border-t border-slate-100">{r.map((v, j) => <td key={j} className={`${td} whitespace-nowrap`}>{String(v)}</td>)}</tr>)}</tbody>
            </table>
          </div>
          <div className="mt-3 flex justify-end">
            <button type="button" className={btnPrimary} disabled={!canCommit || commit.isPending} onClick={() => commit.mutate()}>
              {commit.isPending ? 'Yükleniyor…' : `Yükle (${acc?.ad ?? ''})`}
            </button>
          </div>
        </Block>
      )}

      <Panel>
        <h2 className="flex items-center gap-1 text-[15px] font-extrabold tracking-tight">Yüklemeler<SqlInfo k={imports.data?.kaynaklar} alan="items" label="Yüklemeler" /></h2>
        <p className="mt-0.5 text-[11.5px] leading-snug text-canvas-muted">Aynı kampanya-gün yeniden yüklenirse son yükleme geçerlidir. «Geri al» bu yüklemenin hâlâ geçerli satırlarını siler.</p>
        {imports.error && <Note tone="err">{errText(imports.error, 'Liste açılamadı.')}</Note>}
        <History rows={imports.data?.items ?? []} canUndo onUndo={setUndo} />
      </Panel>
      <AskSheet open={!!undo} title="Yüklemeyi geri al" confirm="Geri al" danger busy={undoImport.isPending}
        message={undo ? `${undo.dosya} (${undo.hesap}): bu yüklemenin geçerli ${undo.gecerliKampanyaGun ?? 0} kampanya-gün satırı silinecek. Bu işlem geri alınamaz; gerekirse dosyayı yeniden yüklersiniz.` : ''}
        onClose={() => setUndo(null)} onConfirm={() => undo && undoImport.mutate(undo.id)} />
    </AdsFrame>
  );
}

function History({ rows, canUndo, onUndo }: { rows: ImportRow[]; canUndo: boolean; onUndo: (r: ImportRow) => void }) {
  if (!rows.length) return <p className="py-3 text-[12px] text-canvas-muted">Henüz yükleme yok. Yukarıdan hesabı seçip ilk raporu yükleyin.</p>;
  return (
    <div className="mt-2">
      <TableWrap>
        <thead>
          <tr>
            <th className={th}>Dosya</th><th className={th}>Hesap</th><th className={th}>Dönem</th><th className={`${th} text-right`}>Kampanya-gün</th>
            <th className={`${th} text-right`}>Harcama</th><th className={`${th} text-right`}>Geçerli</th><th className={th}>Yükleyen</th>{canUndo && <th className={th} />}
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.id} className="border-t border-slate-100">
              <td className={`${td} max-w-[240px] break-words font-bold`}>{r.dosya}</td>
              <td className={td}>{r.hesap}</td>
              <td className={`${td} whitespace-nowrap`}>{r.bas} – {r.bit}</td>
              <td className={`${td} text-right font-mono tabular-nums`}>{r.kampanyaGun}</td>
              <td className={`${td} text-right font-mono tabular-nums`}>{Object.entries(r.paraBirimiToplam).map(([k, v]) => (k === 'TRY' ? fmtMoney2(v) : `${k} ${v}`)).join(' · ')}</td>
              <td className={`${td} text-right font-mono tabular-nums`}>{r.gecerliKampanyaGun ?? '—'}</td>
              <td className={`${td} whitespace-nowrap`}>{r.yukleyen}</td>
              {canUndo && (
                <td className={td}>
                  <button type="button" className={btnGhost} disabled={!r.gecerliKampanyaGun} onClick={() => onUndo(r)}><Undo2 aria-hidden className="h-4 w-4" />Geri al</button>
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </TableWrap>
    </div>
  );
}
