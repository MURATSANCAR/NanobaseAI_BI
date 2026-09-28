import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Pencil, Plus } from 'lucide-react';
import Sheet from '../editorial/studio/reader/Sheet';
import { ENGINE_ENABLED } from '../engine';
import { Loading, Note, Pill, btnGhost, btnPrimary, errText, field, label as labelCls } from '../admin/ui';
import { accountColor, socialApi, type Account, type Platform } from './api';
import { Block, SocialFrame } from './parts';

/** Hesaplar: imprint başına platform hesapları (kullanıcı tanımlar). CRM marka kartlarındaki Instagram kullanıcı adları
 *  öneri olarak gelir. Hesabın dili Zeki AI taslağına girer. Portal hesaplara bağlanmaz; yalnız takvim için kayıttır. */

type Draft = Partial<Account> & { platform: Platform; handle: string };
const EMPTY: Draft = { platform: 'instagram', handle: '', ad: '', imprintAd: '', imprintCrmId: null, sahip: '', ton: '', renk: '' };

export default function SocialAccounts() {
  const qc = useQueryClient();
  const meta = useQuery({ queryKey: ['social', 'meta'], queryFn: socialApi.meta, enabled: ENGINE_ENABLED, staleTime: 60_000 });
  const accounts = useQuery({ queryKey: ['social', 'accounts'], queryFn: socialApi.accounts, enabled: ENGINE_ENABLED });
  const sug = useQuery({ queryKey: ['social', 'suggestions'], queryFn: socialApi.suggestions, enabled: ENGINE_ENABLED, staleTime: 10 * 60_000 });
  const [edit, setEdit] = useState<Draft | null>(null);

  const save = useMutation({
    mutationFn: (d: Draft) => {
      const body: Partial<Account> = { platform: d.platform, handle: d.handle, ad: d.ad || undefined, imprintAd: d.imprintAd || null,
        imprintCrmId: d.imprintCrmId || null, sahip: d.sahip || null, ton: d.ton || null, renk: d.renk || null };
      return d.id ? socialApi.updateAccount(d.id, body) : socialApi.addAccount(body);
    },
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['social'] }); setEdit(null); toast.success('Hesap kaydedildi.'); },
    onError: (e) => toast.error(errText(e, 'Hesap kaydedilemedi.') ?? ''),
  });
  const toggle = useMutation({
    mutationFn: (a: Account) => socialApi.updateAccount(a.id, { aktif: !a.aktif }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['social'] }),
    onError: (e) => toast.error(errText(e, 'Değiştirilemedi.') ?? ''),
  });

  const m = meta.data;
  const canEdit = !!m?.me.canEdit;
  const items = accounts.data?.items ?? [];

  return (
    <SocialFrame
      crumb="Hesaplar"
      title="Sosyal medya hesapları"
      lead="İmprint başına hesaplar. Takvim, rapor ve Zeki AI taslağı bu listeyi kullanır; portal hesaplara bağlanmaz ve paylaşım yapmaz."
      source="CRM marka kartları"
      presence={`${items.length} hesap`}
      aside={canEdit ? (
        <div className="flex justify-end">
          <button type="button" className={btnPrimary} onClick={() => setEdit({ ...EMPTY })}>
            <Plus aria-hidden className="h-4 w-4" />
            Hesap ekle
          </button>
        </div>
      ) : null}
    >
      {accounts.error && <Note tone="err">{errText(accounts.error, 'Hesaplar açılamadı.')}</Note>}
      {accounts.isLoading && <Loading />}
      <Block title="Tanımlı hesaplar">
        {items.length === 0 && !accounts.isLoading && <p className="text-[12px] text-canvas-muted">Hesap yok.</p>}
        <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
          {items.map((a) => (
            <div key={a.id} className={`flex flex-col gap-1.5 rounded-xl bg-white/80 p-3 ${a.aktif ? '' : 'opacity-60'}`}>
              <div className="flex items-start justify-between gap-2">
                <div className="flex min-w-0 items-center gap-2">
                  <span aria-hidden className="h-3 w-3 shrink-0 rounded-full" style={{ background: accountColor(a) }} />
                  <span className="min-w-0">
                    <span className="block truncate text-[13px] font-extrabold">{a.ad}</span>
                    <span className="text-[11.5px] text-canvas-muted">{a.platformAdi} · {a.handle}</span>
                  </span>
                </div>
                {!a.aktif && <Pill tone="muted">Pasif</Pill>}
              </div>
              <div className="text-[11.5px] text-canvas-muted">
                {a.imprintAd ? `İmprint: ${a.imprintAd}` : 'İmprint bağlı değil'}{a.sahip ? ` · yöneten ${a.sahip}` : ''}
              </div>
              {a.ton && <p className="line-clamp-2 text-[11.5px] leading-snug">Dil: {a.ton}</p>}
              {canEdit && (
                <div className="mt-1 flex gap-1.5">
                  <button type="button" className={btnGhost} onClick={() => setEdit({ ...a })}>
                    <Pencil aria-hidden className="h-4 w-4" />
                    Düzenle
                  </button>
                  <button type="button" className={btnGhost} disabled={toggle.isPending} onClick={() => toggle.mutate(a)}>
                    {a.aktif ? 'Pasife al' : 'Etkinleştir'}
                  </button>
                </div>
              )}
            </div>
          ))}
        </div>
      </Block>

      <Block title="CRM marka kartları"
        help={sug.data ? `${sug.data.marka} markanın ${sug.data.instagramDolu} tanesinde Instagram kullanıcı adı dolu. Diğer platformların hesapları CRM'de yok; elle eklenir.` : undefined}>
        {sug.error && <Note tone="err">{errText(sug.error, 'CRM okunamadı.')}</Note>}
        {sug.isLoading && <Loading />}
        <ul className="flex flex-col divide-y divide-slate-100">
          {(sug.data?.items ?? []).map((b) => (
            <li key={b.id} className="flex flex-wrap items-center justify-between gap-2 py-1.5">
              <span className="min-w-0 text-[12px]">
                <span className="block truncate font-semibold">{b.ad}</span>
                <span className="text-[11px] text-canvas-muted">{b.instagram ? `Instagram @${b.instagram}` : 'Instagram adı yok'}</span>
              </span>
              {b.ekli ? <Pill tone="ok">Ekli</Pill> : canEdit && (
                <button type="button" className={btnGhost}
                  onClick={() => setEdit({ ...EMPTY, platform: 'instagram', handle: b.instagram ? `@${b.instagram}` : '', ad: b.ad ? `${b.ad} · Instagram` : '',
                    imprintAd: b.ad ?? '', imprintCrmId: b.id })}>
                  <Plus aria-hidden className="h-4 w-4" />
                  {b.instagram ? 'Ekle' : 'Hesap gir'}
                </button>
              )}
            </li>
          ))}
        </ul>
      </Block>

      <Sheet open={!!edit} modal onClose={() => setEdit(null)} title={edit?.id ? 'Hesabı düzenle' : 'Hesap ekle'}>
        {edit && m && (
          <form className="flex flex-col gap-3" onSubmit={(e) => { e.preventDefault(); save.mutate(edit); }}>
            <div className="grid grid-cols-2 gap-2">
              <label className="flex flex-col gap-1">
                <span className={labelCls}>Platform</span>
                <select className={field} value={edit.platform} onChange={(e) => setEdit({ ...edit, platform: e.target.value as Platform })}>
                  {Object.entries(m.platforms).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                </select>
              </label>
              <label className="flex flex-col gap-1">
                <span className={labelCls}>Hesap adı</span>
                <input className={field} required value={edit.handle} placeholder="@timasyayinlari" onChange={(e) => setEdit({ ...edit, handle: e.target.value })} />
              </label>
            </div>
            <label className="flex flex-col gap-1">
              <span className={labelCls}>Ekranda görünen ad</span>
              <input className={field} value={edit.ad ?? ''} placeholder="Timaş Çocuk · Instagram" onChange={(e) => setEdit({ ...edit, ad: e.target.value })} />
            </label>
            <label className="flex flex-col gap-1">
              <span className={labelCls}>İmprint (CRM markası)</span>
              <select className={field} value={edit.imprintCrmId ?? ''}
                onChange={(e) => {
                  const b = sug.data?.items.find((x) => x.id === e.target.value);
                  setEdit({ ...edit, imprintCrmId: e.target.value || null, imprintAd: b?.ad ?? '' });
                }}>
                <option value="">Bağlı değil</option>
                {(sug.data?.items ?? []).map((b) => <option key={b.id} value={b.id}>{b.ad}</option>)}
              </select>
            </label>
            <div className="grid grid-cols-2 gap-2">
              <label className="flex flex-col gap-1">
                <span className={labelCls}>Yöneten (AD hesabı)</span>
                <input className={field} value={edit.sahip ?? ''} onChange={(e) => setEdit({ ...edit, sahip: e.target.value })} />
              </label>
              <label className="flex flex-col gap-1">
                <span className={labelCls}>Takvim rengi</span>
                <input type="color" className={`${field} h-11 p-1`} value={edit.renk || accountColor(edit as Account)}
                  onChange={(e) => setEdit({ ...edit, renk: e.target.value })} />
              </label>
            </div>
            <label className="flex flex-col gap-1">
              <span className={labelCls}>Hesabın dili</span>
              <textarea className={`${field} min-h-[88px]`} value={edit.ton ?? ''} placeholder="Ör. çocuklara ve ebeveynlere sıcak, oyunlu; ünlem az."
                onChange={(e) => setEdit({ ...edit, ton: e.target.value })} />
            </label>
            <div className="flex justify-end gap-2">
              <button type="button" className={btnGhost} onClick={() => setEdit(null)}>Vazgeç</button>
              <button type="submit" className={btnPrimary} disabled={save.isPending || !edit.handle.trim()}>Kaydet</button>
            </div>
          </form>
        )}
      </Sheet>
    </SocialFrame>
  );
}
