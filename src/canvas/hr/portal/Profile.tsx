import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Download, FileText } from 'lucide-react';
import { ENGINE_ENABLED } from '../../engine';
import { Loading, Note, errText } from '../../admin/ui';
import { EmptyHint } from '../../components/Explain';
import { Block, HrFrame } from '../parts';
import { Avatar } from './parts';
import { fileSize, longDay, portalApi, showValue, type PersonField } from './portalApi';

/** Profilim (/ik/profilim): kişinin kendi özlük kaydı; yalnız «profilim» işaretli alanlar. Düzeltme İK'dan istenir. */
export default function Profile() {
  const q = useQuery({ queryKey: ['hr', 'portal', 'me'], queryFn: portalApi.me, enabled: ENGINE_ENABLED });
  const p = q.data?.person;
  const fields = q.data?.fields ?? [];
  const groups = q.data?.groups ?? {};
  const byGroup = new Map<string, PersonField[]>();
  fields.filter((f) => f.type !== 'file' && f.key !== 'fotograf').forEach((f) => byGroup.set(f.group, [...(byGroup.get(f.group) ?? []), f]));
  const docFields = fields.filter((f) => f.type === 'file' && f.key !== 'fotograf');
  const hasPhoto = !!p?.files.some((f) => f.field === 'fotograf');
  return (
    <HrFrame crumb="Profilim" title="Profilim" back={{ to: '/ik', label: 'İK ana sayfası' }}
      lead="İK'daki özlük kaydınızın size açık bölümü. Yanlış ya da eksik bir bilgi varsa Evrak talebi ekranından «Diğer» tipinde not bırakın ya da İK ile görüşün.">
      {q.error && <Note tone="err">{errText(q.error, 'Profiliniz okunamadı.')}</Note>}
      {q.isLoading && <Loading />}
      {q.data && !p && (
        <EmptyHint title="Özlük kaydınız bulunamadı" why="Portal hesabınız henüz İK'daki bir personel kaydına bağlanmamış. İK kaydınıza portal hesabınızı (ya da şirket e-postanızı) girince bu sayfa dolar." />
      )}
      {p && (
        <>
          <section className="glass-panel flex items-center gap-3 rounded-2xl p-3 shadow-glass-float sm:rounded-3xl sm:p-4">
            <Avatar name={p.adSoyad} src={hasPhoto ? '/portal/me/photo' : null} size={64} />
            <div className="min-w-0">
              <div className="truncate text-[20px] font-extrabold tracking-tight">{p.adSoyad}</div>
              <div className="truncate text-[12.5px] text-canvas-muted">{[p.data.unvan, p.data.departman, p.data.ekip].filter(Boolean).join(' · ') || '—'}</div>
              {q.data?.manager && <div className="truncate text-[12px] text-canvas-muted">Yöneticiniz: <span className="font-bold text-canvas-ink">{q.data.manager}</span></div>}
            </div>
          </section>
          <div className="grid grid-cols-1 gap-3 lg:grid-cols-2 lg:gap-4">
            {[...byGroup.entries()].map(([g, fs]) => (
              <Block key={g} title={groups[g] ?? g}>
                <dl className="grid grid-cols-1 gap-x-4 gap-y-2 sm:grid-cols-2">
                  {fs.map((f) => (
                    <div key={f.key} className="min-w-0">
                      <dt className="text-[10.5px] font-bold uppercase tracking-wide text-canvas-muted">{f.label}</dt>
                      <dd className="whitespace-pre-line break-words text-[13px] font-bold">{showValue(f, p.data[f.key])}</dd>
                    </div>
                  ))}
                </dl>
              </Block>
            ))}
          </div>
          {docFields.length > 0 && (
            <Block title="Belgelerim" help="İK'nın dosyanıza yüklediği belgeler. İndirdiğiniz belge yalnız sizin cihazınıza kaydedilir.">
              <ul className="grid grid-cols-1 gap-2 sm:grid-cols-2 xl:grid-cols-3">
                {docFields.map((f) => {
                  const files = p.files.filter((x) => x.field === f.key);
                  return (
                    <li key={f.key} className="rounded-xl bg-white/80 px-3 py-2">
                      <div className="flex items-center gap-1.5 text-[12.5px] font-bold"><FileText aria-hidden className="h-4 w-4 text-canvas-muted" />{f.label}</div>
                      {files.length ? files.map((x) => (
                        <button key={x.id} type="button" onClick={() => void portalApi.myFile(x).catch((e) => toast.error(errText(e, 'İndirilemedi.')))}
                          className="mt-1 flex min-h-11 w-full items-center gap-2 rounded-lg px-2 text-left text-[12px] text-canvas-violet hover:bg-violet-50 sm:min-h-8">
                          <Download aria-hidden className="h-3.5 w-3.5 shrink-0" />
                          <span className="min-w-0 flex-1 truncate">{x.filename}</span>
                          <span className="shrink-0 text-canvas-muted">{fileSize(x.size)} · {longDay(x.uploadedAt)}</span>
                        </button>
                      )) : <div className="mt-1 text-[12px] text-canvas-muted">Yüklenmemiş</div>}
                    </li>
                  );
                })}
              </ul>
            </Block>
          )}
        </>
      )}
      <MailPref />
    </HrFrame>
  );
}

/** E-posta bildirimi tercihi: evrak ve izin sonuçları. Onay isteyen iş e-postaları (yöneticiye/İK'ya) kapatılamaz. */
function MailPref() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ['hr', 'portal', 'mail-pref'], queryFn: portalApi.mailPref, enabled: ENGINE_ENABLED });
  const save = useMutation({
    mutationFn: (off: boolean) => portalApi.setMailPref(off),
    onSuccess: () => { toast.success('Tercih kaydedildi.'); void qc.invalidateQueries({ queryKey: ['hr', 'portal', 'mail-pref'] }); },
    onError: (e) => toast.error(errText(e, 'Kaydedilemedi.')),
  });
  if (!q.data) return null;
  return (
    <Block title="E-posta bildirimleri" help={q.data.mode === 'kapali' ? 'Portal e-posta bildirimleri şu an İK tarafından kapalı.' : 'Evrak talebinizin ve izin talebinizin sonucu şirket e-postanıza gelir.'}>
      <label className="flex min-h-11 items-center gap-2 text-[13px] font-bold">
        <input type="checkbox" className="h-4 w-4" checked={!q.data.off} disabled={save.isPending} onChange={(e) => save.mutate(!e.target.checked)} />
        Evrak ve izin sonuçlarını e-postayla bildir
      </label>
      <p className="text-[11.5px] text-canvas-muted">Yöneticiyseniz onayınızı bekleyen izin e-postaları bu tercihten bağımsız gelir.</p>
    </Block>
  );
}
