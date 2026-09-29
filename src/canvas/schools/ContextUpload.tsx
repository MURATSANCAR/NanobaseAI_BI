import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { ENGINE_ENABLED } from '../engine';
import { Loading, Note, errText, field, label as labelCls } from '../admin/ui';
import { FileDrop } from '../components/FileDrop';
import { schoolsApi, type UploadResult } from './api';
import { fmtDay, fmtNum, invalidateSchools, useSchoolsMeta } from './parts';
import SqlInfo from '../components/SqlInfo';

/** Dış veri elle yüklenir (müşteride web taraması kapalı): ilçe gelişmişlik endeksi ve akademik takvim (tatil, sınav
 *  haftası). Kaynağın adı ve tarihi zorunlu; yeni yükleme öncekinin yerine geçer, eskisi silinmez. */

const KINDS = [
  {
    key: 'takvim',
    title: 'Akademik takvim',
    help: 'Tatil ve sınav haftaları. Başlıklar: baslangic; bitis; tur (tatil / sinav / diger); ad; il (boşsa bütün iller). Tarih GG.AA.YYYY ya da YYYY-AA-GG.',
    example: 'baslangic;bitis;tur;ad;il\n17.11.2026;21.11.2026;tatil;1. dönem ara tatili;\n',
  },
  {
    key: 'ilce_endeks',
    title: 'İlçe gelişmişlik endeksi',
    help: 'Başlıklar: il; ilce; endeks (ondalık virgül olabilir); yil. Öncelik puanında ilçe endeksi bileşeni bundan hesaplanır.',
    example: 'il;ilce;endeks;yil\nİstanbul;Kadıköy;4,85;2022\n',
  },
] as const;

function readFile(f: File): Promise<{ csv?: string; xlsx?: string }> {
  return new Promise((resolve, reject) => {
    const r = new FileReader();
    const xlsx = /\.xlsx$/i.test(f.name);
    r.onerror = () => reject(new Error('Dosya okunamadı.'));
    r.onload = () => resolve(xlsx ? { xlsx: String(r.result) } : { csv: String(r.result) });
    if (xlsx) r.readAsDataURL(f);
    else r.readAsText(f, 'utf-8');
  });
}

export default function ContextUpload() {
  const meta = useSchoolsMeta();
  const can = !!meta.data?.me.canUpload;
  const ctx = useQuery({ queryKey: ['schools', 'context'], queryFn: schoolsApi.context, enabled: ENGINE_ENABLED });
  const c = ctx.data;
  return (
    <div className="flex flex-col gap-3">
      <p className="px-1 text-[12px] leading-snug text-canvas-muted">
        Buraya yüklenen akademik takvim, plan önerisinde tatil ve sınav günlerine okul konmamasını sağlar; ilçe gelişmişlik endeksi ise okulların öncelik puanına girer. Dosyayı CSV ya da Excel olarak, örnekteki başlıklarla yükleyin.
      </p>
      {ctx.error && <Note tone="err">{errText(ctx.error, 'Yüklenen veri okunamadı.')}</Note>}
      {ctx.isLoading && <Loading />}
      <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
        {KINDS.map((k) => {
          const up = c?.uploads.find((u) => u.kind === k.key);
          return (
            <section key={k.key} className="glass-panel rounded-2xl p-3 shadow-glass-float sm:rounded-3xl sm:p-4">
              <h2 className="text-[15px] font-extrabold">{k.title}</h2>
              <p className="mt-1 text-[12px] leading-snug text-canvas-muted">{k.help}</p>
              <p className="mt-2 text-[12px] font-semibold">
                {up
                  ? `Yüklü: ${fmtNum(up.rows)} satır · kaynak «${up.source ?? '—'}» (${fmtDay(up.sourceDay)}) · ${up.by}, ${fmtDay(up.at?.slice(0, 10))}`
                  : 'Henüz yüklenmedi.'}
                {up && <SqlInfo k={c?.kaynaklar} alan="uploads" label={`${k.title}: yüklü satır`} />}
              </p>
              {/* Yükleme yetkisizde de görünür: alan kilitli, gereken yetki yazılı. */}
              {meta.data && <UploadForm kind={k.key} example={k.example} can={can} />}
            </section>
          );
        })}
      </div>
      {c && c.calendar.length > 0 && (
        <section className="glass-panel rounded-2xl p-3 shadow-glass-float sm:rounded-3xl sm:p-4">
          <h2 className="text-[11px] font-bold uppercase tracking-wide text-canvas-muted">Takvimdeki günler</h2>
          <ul className="mt-2 space-y-1">
            {c.calendar.map((e) => (
              <li key={`${e.baslangic}-${e.ad}-${e.il ?? ''}`} className="text-[12.5px]">
                <span className="font-bold">{e.ad}</span> · {fmtDay(e.baslangic)}
                {e.bitis !== e.baslangic ? ` – ${fmtDay(e.bitis)}` : ''} · {e.il ?? 'bütün iller'}
              </li>
            ))}
          </ul>
        </section>
      )}
      {c && c.districts.length > 0 && (
        <p className="px-1 text-[12px] text-canvas-muted">
          İlçe endeksi {fmtNum(c.districts.length)} ilçe için yüklü
          {c.range ? ` (en düşük ${c.range[0].toLocaleString('tr-TR')}, en yüksek ${c.range[1].toLocaleString('tr-TR')})` : ''};{' '}
          {fmtNum(c.districts.filter((x) => !x.crmIlceId).length)} satır CRM ilçe listesinde bulunamadı.
          <SqlInfo k={c.kaynaklar} alan="range" label="İlçe endeksi" />
        </p>
      )}
    </div>
  );
}

function UploadForm({ kind, example, can }: { kind: string; example: string; can: boolean }) {
  const qc = useQueryClient();
  const [source, setSource] = useState('');
  const [day, setDay] = useState('');
  const [res, setRes] = useState<UploadResult | null>(null);
  const run = useMutation({
    mutationFn: async (file: File) => {
      const body = await readFile(file);
      return schoolsApi.upload({ tur: kind, kaynak: source, kaynakTarihi: day || undefined, ...body });
    },
    onSuccess: (r) => {
      setRes(r);
      toast.success(`${r.saved} satır kaydedildi.`);
      invalidateSchools(qc);
    },
    onError: (e) => toast.error(errText(e, 'Yüklenemedi.') ?? 'Yüklenemedi.'),
  });
  return (
    <div className="mt-3 flex flex-col gap-2">
      <label className="flex flex-col gap-1">
        <span className={labelCls}>Kaynak</span>
        <input className={field} value={source} onChange={(e) => setSource(e.target.value)} placeholder="Ör. MEB 2026-2027 çalışma takvimi" />
      </label>
      <label className="flex flex-col gap-1">
        <span className={labelCls}>Kaynağın tarihi</span>
        <input type="date" className={field} value={day} onChange={(e) => setDay(e.target.value)} />
      </label>
      <details>
        <summary className="min-h-11 cursor-pointer text-[12px] font-bold text-canvas-violet sm:min-h-0">Örnek dosya</summary>
        <pre className="mt-1 overflow-x-auto rounded-xl bg-slate-50 p-2 text-[11.5px]">{example}</pre>
      </details>
      <FileDrop
        size="sm"
        title="Dosyayı yükle"
        hint="Yeni yükleme öncekinin yerine geçer; eskisi silinmez."
        accept=".csv,.txt,.xlsx"
        feature="okul.baglam-yukle"
        allowed={can}
        disabled={!source.trim()}
        disabledReason="Önce kaynağın adını yazın (ör. MEB çalışma takvimi)."
        busy={run.isPending}
        onPick={(f) => run.mutate(f)}
      />
      {res && (
        <div className="text-[12px]">
          {res.read} satır okundu, {res.saved} satır kaydedildi.
          {res.problems.length > 0 && (
            <ul className="mt-1 max-h-48 overflow-y-auto rounded-xl bg-amber-50 p-2 text-amber-800">
              {res.problems.map((p) => (
                <li key={`${p.satir}-${p.neden}`}>
                  {p.satir}. satır: {p.neden}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
