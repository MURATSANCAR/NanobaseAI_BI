import { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Download, Sparkles, Trash2 } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import { Loading, Note, TableWrap, btnGhost, errText, field, label as labelCls, td, th, btnPrimary } from '../admin/ui';
import SqlInfo from '../components/SqlInfo';
import { Kpi, KpiRow } from '../editorial/kit';
import { AskSheet } from '../budget/parts';
import { fmtInt, fmtMonth, fmtPct, fmtStamp, socialApi, todayIso, type ImportRow, type PostStatus } from './api';
import { Block, SocialFrame } from './parts';
import { FileDrop } from '../components/FileDrop';
import { MB } from '../components/fileDropRules';

/** Aylık rapor: içerik türü × etkileşim, hesap bazında erişim/takipçi, onay süresi medyanı; platform dışa aktarım
 *  dosyasının içe aktarılması. Portal platformlara bağlanmaz; sayılar dosyadan ya da elle girilir. */

export default function SocialReport() {
  const qc = useQueryClient();
  const [params, setParams] = useSearchParams();
  const month = params.get('ay') || todayIso().slice(0, 7);
  const meta = useQuery({ queryKey: ['social', 'meta'], queryFn: socialApi.meta, enabled: ENGINE_ENABLED, staleTime: 60_000 });
  const accounts = useQuery({ queryKey: ['social', 'accounts'], queryFn: socialApi.accounts, enabled: ENGINE_ENABLED });
  const rep = useQuery({
    queryKey: ['social', 'report', month],
    queryFn: () => socialApi.report(month),
    enabled: ENGINE_ENABLED,
    refetchInterval: (q) => (q.state.data?.yorum && ['bekliyor', 'calisiyor'].includes(q.state.data.yorum.durum) ? 2500 : false),
  });
  const imports = useQuery({ queryKey: ['social', 'imports'], queryFn: socialApi.imports, enabled: ENGINE_ENABLED });
  const [acc, setAcc] = useState('');
  const [day, setDay] = useState('');
  const [removing, setRemoving] = useState<ImportRow | null>(null);
  useEffect(() => {
    if (!acc && accounts.data?.items.length) setAcc(accounts.data.items[0].id);
  }, [accounts.data, acc]);

  const upload = useMutation({
    mutationFn: (f: File) => socialApi.upload(acc, f, day || undefined),
    onSuccess: (r) => {
      qc.invalidateQueries({ queryKey: ['social'] });
      toast.success(`${fmtInt(r.satir)} satır içe aktarıldı; ${fmtInt(r.eslesen)} tanesi gönderiyle eşleşti.`);
      if (r.atlananKolonlar?.length) toast.message(`Tanınmayan kolonlar atlandı: ${r.atlananKolonlar.slice(0, 8).join(', ')}`);
    },
    onError: (e) => toast.error(errText(e, 'Dosya içe aktarılamadı.') ?? ''),
  });
  const del = useMutation({
    mutationFn: (id: string) => socialApi.deleteImport(id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['social'] }); setRemoving(null); toast.success('İçe aktarma silindi.'); },
    onError: (e) => toast.error(errText(e, 'Silinemedi.') ?? ''),
  });
  const comment = useMutation({
    mutationFn: () => socialApi.commentary(month),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['social', 'report', month] }),
    onError: (e) => toast.error(errText(e, 'Zeki AI yorumu başlatılamadı.') ?? ''),
  });

  const m = meta.data;
  const r = rep.data;
  const t = r?.toplam;
  const y = r?.yorum;
  const yRunning = !!y && ['bekliyor', 'calisiyor'].includes(y.durum);
  const yText = y?.durum === 'bitti' ? ((y.sonuc as { metin?: string | null; uyari?: string } | null)?.metin ?? null) : null;
  const accName = (id: string) => accounts.data?.items.find((a) => a.id === id)?.ad ?? id;

  return (
    <SocialFrame
      crumb="Rapor"
      title="Sosyal medya raporu"
      lead="İçerik türü ve hesap bazında erişim ve etkileşim. Etkileşim = beğeni + yorum + paylaşım + kaydetme; oran = etkileşim ÷ erişim. Rapor kişi adı içermez."
      source="Platform dışa aktarım dosyaları"
      presence={r ? fmtMonth(r.ay) : '…'}
      aside={
        <div className="flex flex-wrap items-end gap-2">
          <label className="flex min-w-[160px] flex-1 flex-col gap-1">
            <span className={labelCls}>Ay</span>
            <input type="month" className={field} value={month} onChange={(e) => { const p = new URLSearchParams(params); if (e.target.value) p.set('ay', e.target.value); setParams(p, { replace: true }); }} />
          </label>
          {m?.me.canExport && (
            <a className={btnGhost} href={socialApi.reportPdfUrl(month)} download>
              <Download aria-hidden className="h-4 w-4" />
              PDF
            </a>
          )}
        </div>
      }
    >
      {rep.error && <Note tone="err">{errText(rep.error, 'Rapor açılamadı.')}</Note>}
      {rep.isLoading && <Loading />}
      {r && t && (
        <>
          <KpiRow>
            <Kpi label="Erişim" value={fmtInt(t.reach)} help={`${fmtInt(r.olcuSatiri)} ölçü satırından`} info={<SqlInfo k={r.kaynaklar} alan="toplam" label="Erişim" />} />
            <Kpi label="Etkileşim" value={fmtInt(t.etkilesim)} help="Beğeni, yorum, paylaşım, kaydetme" info={<SqlInfo k={r.kaynaklar} alan="toplam" label="Etkileşim" />} />
            <Kpi label="Etkileşim oranı" value={fmtPct(t.oran)} help="Etkileşim ÷ erişim" info={<SqlInfo k={r.kaynaklar} alan="toplam" label="Etkileşim oranı" />} />
            <Kpi label="Onay süresi" value={r.onaySuresiSaat === null ? '—' : `${r.onaySuresiSaat.toLocaleString('tr-TR')} sa`}
              help={`Onaya gönderme → onay medyanı, ${r.onaySayisi} gönderi`} info={<SqlInfo k={r.kaynaklar} alan="onaySuresiSaat" label="Onay süresi" />} />
          </KpiRow>
          {r.olcuSatiri === 0 && <Note tone="info">Bu ay için içgörü yok. Aşağıdan platformun dışa aktarım dosyasını yükleyin ya da yayınlanmış gönderiye elle girin.</Note>}

          <Block title="Zeki AI yorumu" help="Yalnız rapordaki sayılarla yazar; başka sayı yazarsa cümle düşer."
            action={m?.me.canEdit && (
              <button type="button" className={btnGhost} disabled={yRunning || comment.isPending || !m.modelReady} onClick={() => comment.mutate()}>
                <Sparkles aria-hidden className="h-4 w-4" />
                {yRunning ? (y?.adim || 'Yazıyor…') : yText ? 'Yeniden yaz' : 'Yorum yaz'}
              </button>
            )}>
            {yText && <p className="whitespace-pre-wrap text-[12.5px] leading-relaxed">{yText}</p>}
            {y?.durum === 'hata' && <Note tone="err">{y.hata}</Note>}
            {!yText && !yRunning && y?.durum !== 'hata' && <p className="text-[12px] text-canvas-muted">Henüz yorum yok.</p>}
          </Block>

          <div className="grid gap-3 xl:grid-cols-2 xl:gap-4">
            <Block title="İçerik türüne göre" info={<SqlInfo k={r.kaynaklar} alan="turler" label="İçerik türüne göre" />} help="Gönderi başına etkileşime göre sıralı; gönderiye bağlanmamış dosya satırları bu tabloya girmez.">
              <TableWrap>
                <thead><tr><th className={th}>Tür</th><th className={th}>Gönderi</th><th className={th}>Erişim</th><th className={th}>Etkileşim</th><th className={th}>Gönderi başına</th><th className={th}>Oran</th></tr></thead>
                <tbody>
                  {r.turler.map((x) => (
                    <tr key={x.tur} className="border-t border-slate-100">
                      <td className={`${td} font-semibold`}>{x.turAdi}</td>
                      <td className={`${td} font-mono tabular-nums`}>{fmtInt(x.gonderi)}</td>
                      <td className={`${td} font-mono tabular-nums`}>{fmtInt(x.reach)}</td>
                      <td className={`${td} font-mono tabular-nums`}>{fmtInt(x.etkilesim)}</td>
                      <td className={`${td} font-mono tabular-nums`}>{fmtInt(x.gonderiBasina)}</td>
                      <td className={`${td} font-mono tabular-nums`}>{fmtPct(x.oran)}</td>
                    </tr>
                  ))}
                  {r.turler.length === 0 && <tr><td className={td} colSpan={6}>Gönderiye bağlı ölçü yok.</td></tr>}
                </tbody>
              </TableWrap>
            </Block>
            <Block title="Hesaba göre" info={<SqlInfo k={r.kaynaklar} alan="hesaplar" label="Hesaba göre" />}>
              <TableWrap>
                <thead><tr><th className={th}>Hesap</th><th className={th}>Erişim</th><th className={th}>Gösterim</th><th className={th}>Etkileşim</th><th className={th}>Takipçi</th></tr></thead>
                <tbody>
                  {r.hesaplar.map((x) => (
                    <tr key={x.accountId} className="border-t border-slate-100">
                      <td className={`${td} font-semibold`}>{x.hesap}</td>
                      <td className={`${td} font-mono tabular-nums`}>{fmtInt(x.reach)}</td>
                      <td className={`${td} font-mono tabular-nums`}>{fmtInt(x.impressions)}</td>
                      <td className={`${td} font-mono tabular-nums`}>{fmtInt(x.etkilesim)}</td>
                      <td className={`${td} font-mono tabular-nums`}>{fmtInt(x.takipci)}{x.takipciGun ? <span className="ml-1 text-[10.5px] text-canvas-muted">({x.takipciGun})</span> : null}</td>
                    </tr>
                  ))}
                  {r.hesaplar.length === 0 && <tr><td className={td} colSpan={5}>Ölçü yok.</td></tr>}
                </tbody>
              </TableWrap>
            </Block>
          </div>
          <p className="px-1 text-[11.5px] text-canvas-muted">
            Bu ay planlanan gönderi: {r.gonderiSayisi} ({Object.entries(r.gonderiDurum).map(([k, v]) => `${m?.statuses[k as PostStatus] ?? k} ${v}`).join(', ') || '—'}).
          </p>
        </>
      )}

      <Block title="İçgörü dosyası içe aktar"
        info={<SqlInfo k={imports.data?.kaynaklar} alan="items" label="İçe aktarmalar" />}
        help="Platformun dışa aktarım dosyası (.csv ya da .xlsx). Tanınan kolonlar: tarih, bağlantı, gösterim, erişim, beğeni, yorum, paylaşım, kaydetme, takipçi (Türkçe ya da İngilizce başlık). Bağlantısı yayınlanmış gönderiyle aynı olan satır o gönderiye bağlanır. Dosyada tarih yoksa gün girin.">
        {/* Yükleme her zaman görünür: yetkisi olmayan kişi kilitli alanı ve gereken yetkiyi görür. */}
        <div className="grid gap-2 sm:grid-cols-[minmax(0,1fr)_180px] sm:items-end">
            <label className="flex flex-col gap-1">
              <span className={labelCls}>Hesap</span>
              <select className={field} value={acc} onChange={(e) => setAcc(e.target.value)}>
                {(accounts.data?.items ?? []).map((a) => <option key={a.id} value={a.id}>{a.ad}</option>)}
              </select>
            </label>
            <label className="flex flex-col gap-1">
              <span className={labelCls}>Gün (dosyada yoksa)</span>
              <input type="date" className={field} value={day} onChange={(e) => setDay(e.target.value)} />
            </label>
        </div>
        <div className="mt-2">
          <FileDrop
            size="sm"
            title="İçgörü dosyası yükle"
            accept=".csv,.xlsx,.txt"
            maxBytes={25 * MB}
            feature="sosyal.duzenle"
            allowed={m ? !!m.me.canEdit : undefined}
            disabled={!acc}
            disabledReason="Önce hesabı seçin; hesap yoksa Sosyal medya → Hesaplar'dan ekleyin."
            busy={upload.isPending}
            onPick={(f) => upload.mutate(f)}
          />
        </div>
        {(imports.data?.items ?? []).length > 0 && (
          <div className="mt-3">
            <TableWrap>
              <thead><tr><th className={th}>Dosya</th><th className={th}>Hesap</th><th className={th}>Satır</th><th className={th}>Eşleşen</th><th className={th}>Erişim</th><th className={th}>Kim · ne zaman</th><th className={th} /></tr></thead>
              <tbody>
                {(imports.data?.items ?? []).map((x) => (
                  <tr key={x.id} className="border-t border-slate-100">
                    <td className={`${td} font-semibold`}>{x.dosya}</td>
                    <td className={td}>{accName(x.accountId)}</td>
                    <td className={`${td} font-mono tabular-nums`}>{fmtInt(x.satir)}</td>
                    <td className={`${td} font-mono tabular-nums`}>{fmtInt(x.eslesen)}</td>
                    <td className={`${td} font-mono tabular-nums`}>{fmtInt(x.ozet.toplam?.reach ?? null)}</td>
                    <td className={td}>{x.kim} · {fmtStamp(x.zaman)}</td>
                    <td className={td}>
                      {m?.me.canEdit && (
                        <button type="button" className={btnGhost} aria-label="İçe aktarmayı sil" onClick={() => setRemoving(x)}>
                          <Trash2 aria-hidden className="h-4 w-4" />
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </TableWrap>
          </div>
        )}
      </Block>

      <AskSheet open={!!removing} title="İçe aktarmayı sil" message={<>«{removing?.dosya}» dosyasından gelen {fmtInt(removing?.satir ?? 0)} ölçü satırı silinir.</>}
        confirm="Sil" danger busy={del.isPending} onClose={() => setRemoving(null)} onConfirm={() => removing && del.mutate(removing.id)} />
    </SocialFrame>
  );
}
