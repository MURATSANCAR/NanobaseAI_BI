import { useEffect, useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Loader2, Plus, X } from 'lucide-react';
import { btnGhost, btnPrimary, errText, field, label as labelCls } from '../admin/ui';
import Sheet from '../editorial/studio/reader/Sheet';
import { inflApi, parseNum, type Meta, type PersonDetail, type PersonInput } from './api';
import { MultiPick } from './parts';

type Acc = { platform: string; handle: string; url: string };

/** İçerik üreticisi ekleme ve düzenleme. Ücret aralığı yalnız onay/ödeme yetkisi olana açılır. */
export default function PersonForm({ open, meta, person, onClose, onSaved }: {
  open: boolean; meta: Meta; person?: PersonDetail | null; onClose: () => void; onSaved?: (id: string) => void;
}) {
  const qc = useQueryClient();
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [phone, setPhone] = useState('');
  const [city, setCity] = useState('');
  const [notes, setNotes] = useState('');
  const [topics, setTopics] = useState<string[]>([]);
  const [ages, setAges] = useState<string[]>([]);
  const [pref, setPref] = useState('');
  const [dnc, setDnc] = useState(false);
  const [minor, setMinor] = useState(false);
  const [feeMin, setFeeMin] = useState('');
  const [feeMax, setFeeMax] = useState('');
  const [accs, setAccs] = useState<Acc[]>([{ platform: 'instagram', handle: '', url: '' }]);
  useEffect(() => {
    if (!open) return;
    setName(person?.name ?? '');
    setEmail(person?.email ?? '');
    setPhone(person?.phone ?? '');
    setCity(person?.city ?? '');
    setNotes(person?.notes ?? '');
    setTopics(person?.topics ?? []);
    setAges(person?.ageGroups ?? []);
    setPref(person?.contactPref ?? '');
    setDnc(person?.doNotContact ?? false);
    setMinor(person?.minor ?? false);
    setFeeMin(person?.feeMin?.toString() ?? '');
    setFeeMax(person?.feeMax?.toString() ?? '');
    setAccs(person?.accounts.length ? person.accounts.map((a) => ({ platform: a.platform, handle: a.handle, url: a.url ?? '' })) : [{ platform: 'instagram', handle: '', url: '' }]);
  }, [open, person]);
  const save = useMutation({
    mutationFn: () => {
      const b: PersonInput = {
        name: name.trim(), email: email.trim(), phone: phone.trim(), city: city.trim(), notes: notes.trim(), topics, ageGroups: ages,
        contactPref: pref || null, doNotContact: dnc, minor,
        accounts: accs.filter((a) => a.handle.trim() || a.url.trim()).map((a) => ({ platform: a.platform, handle: a.handle.trim() || a.url.trim(), url: a.url.trim() || null })),
      };
      if (meta.me.canSeeFee) {
        b.feeMin = feeMin.trim() ? parseNum(feeMin) : null;
        b.feeMax = feeMax.trim() ? parseNum(feeMax) : null;
      }
      return person ? inflApi.updatePerson(person.id, b) : inflApi.createPerson(b);
    },
    onSuccess: (r) => {
      qc.invalidateQueries({ queryKey: ['influencers'] });
      toast.success(person ? 'Bilgiler kaydedildi.' : 'İçerik üreticisi eklendi; artık aday listesinde ve yeni işbirliği formunda seçilebilir.');
      onClose();
      onSaved?.(r.id);
    },
    onError: (e) => toast.error(errText(e, 'Kaydedilemedi. Alanları kontrol edip yeniden deneyin.') ?? ''),
  });
  const hint = 'text-[11px] font-medium leading-snug text-canvas-muted';
  const setAcc = (i: number, k: keyof Acc, v: string) => setAccs((xs) => xs.map((a, j) => (j === i ? { ...a, [k]: v } : a)));
  return (
    <Sheet open={open} modal onClose={onClose} title={person ? 'Bilgileri düzenle' : 'Yeni içerik üreticisi'}
      subtitle="Kitaplarımızı tanıtabilecek içerik üreticisinin kaydı. Konu, yaş grubu ve ücret aralığı aday listesindeki sıralamayı etkiler. Takipçi ve etkileşim sayıları otomatik çekilmez; kişi kartından elle girilir. Yalnız ad zorunlu.">
      <div className="flex flex-col gap-3 text-[13px]">
        <label className="flex flex-col gap-1">
          <span className={labelCls}>Ad *</span>
          <input className={field} value={name} placeholder="Ör. Ayşe Yılmaz ya da «Kitap Kurdu Ayşe»" onChange={(e) => setName(e.target.value)} />
          <span className={hint}>Listelerde ve işbirliği kartlarında görünen ad.</span>
        </label>
        <div className="flex flex-col gap-2">
          <span className={labelCls}>Hesaplar</span>
          <span className={hint}>Kişinin paylaşım yaptığı hesaplar. Kullanıcı adı ya da bağlantıdan biri yeterli; ikisi de boş satır kaydedilmez.</span>
          {accs.map((a, i) => (
            <div key={i} className="flex flex-col gap-2 rounded-xl bg-slate-50 p-2">
              <div className="flex gap-2">
                <select className={`${field} w-[120px] shrink-0`} value={a.platform} onChange={(e) => setAcc(i, 'platform', e.target.value)} aria-label="Platform">
                  {Object.entries(meta.platformlar).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                </select>
                <input className={`${field} min-w-0 flex-1`} placeholder="Ör. @kitapkurduayse" value={a.handle} onChange={(e) => setAcc(i, 'handle', e.target.value)} aria-label="Kullanıcı adı" />
                <button type="button" className={`${btnGhost} shrink-0`} aria-label="Hesabı kaldır" onClick={() => setAccs((xs) => xs.filter((_, j) => j !== i))}>
                  <X aria-hidden className="h-4 w-4" />
                </button>
              </div>
              <input className={field} placeholder="Ör. https://instagram.com/kitapkurduayse (isteğe bağlı)" value={a.url} onChange={(e) => setAcc(i, 'url', e.target.value)} aria-label="Bağlantı" />
            </div>
          ))}
          <button type="button" className={`${btnGhost} self-start`} onClick={() => setAccs((xs) => [...xs, { platform: 'instagram', handle: '', url: '' }])}>
            <Plus aria-hidden className="h-4 w-4" /> Hesap ekle
          </button>
        </div>
        <div className="flex flex-col gap-1">
          <span className={labelCls}>Konular</span>
          <span className={hint}>Kişinin hangi tür kitaplardan söz ettiği. Aday listesinde kitabın konusuyla eşleşen kişi üste çıkar; birden çok seçebilirsiniz.</span>
          <MultiPick options={meta.konular} value={topics} onChange={setTopics} />
        </div>
        <div className="flex flex-col gap-1">
          <span className={labelCls}>Kitlesinin yaş grubu</span>
          <span className={hint}>Takipçilerinin çoğunun yaşı. Aday listesinde kitabın hedef yaşıyla karşılaştırılır.</span>
          <MultiPick options={meta.yasGruplari} value={ages} onChange={setAges} />
        </div>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <label className="flex flex-col gap-1"><span className={labelCls}>E-posta</span><input className={field} inputMode="email" placeholder="Ör. ayse@ornek.com" value={email} onChange={(e) => setEmail(e.target.value)} /></label>
          <label className="flex flex-col gap-1"><span className={labelCls}>Telefon</span><input className={field} type="tel" inputMode="tel" placeholder="Ör. 0532 123 45 67" value={phone} onChange={(e) => setPhone(e.target.value)} /></label>
          <label className="flex flex-col gap-1"><span className={labelCls}>Şehir</span><input className={field} placeholder="Ör. İstanbul" value={city} onChange={(e) => setCity(e.target.value)} /></label>
          <label className="flex flex-col gap-1">
            <span className={labelCls}>İletişim tercihi</span>
            <select className={field} value={pref} onChange={(e) => setPref(e.target.value)}>
              <option value="">Belirtilmedi</option>
              {Object.entries(meta.iletisimTercihleri).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
            <span className={hint}>Size hatırlatma içindir; portal kişiye mesaj göndermez.</span>
          </label>
          {meta.me.canSeeFee && (
            <>
              <label className="flex flex-col gap-1"><span className={labelCls}>Ücret alt sınırı (₺)</span><input className={`${field} font-mono`} inputMode="decimal" placeholder="Ör. 2500" value={feeMin} onChange={(e) => setFeeMin(e.target.value)} /></label>
              <label className="flex flex-col gap-1"><span className={labelCls}>Ücret üst sınırı (₺)</span><input className={`${field} font-mono`} inputMode="decimal" placeholder="Ör. 10000" value={feeMax} onChange={(e) => setFeeMax(e.target.value)} /></label>
              <p className={`${hint} sm:col-span-2`}>Kişinin genelde istediği ücret aralığı; aday listesinde bütçe uyumu buna göre hesaplanır. Binlik nokta koymayın. Bu alanları yalnız onay ve ödeme yetkisi olanlar görür.</p>
            </>
          )}
        </div>
        <label className="flex flex-col gap-1">
          <span className={labelCls}>Not</span>
          <textarea className={`${field} min-h-[56px]`} placeholder="Ör. Çocuk kitaplarına odaklı; hafta sonu canlı yayın yapıyor." value={notes} onChange={(e) => setNotes(e.target.value)} />
        </label>
        <label className="flex min-h-10 items-center gap-2"><input type="checkbox" className="h-4 w-4 shrink-0" checked={dnc} onChange={(e) => setDnc(e.target.checked)} /> İletişim kurulmasın: kişiyle yeni işbirliği açılamaz, aday listesinde ayrı görünür</label>
        <label className="flex min-h-10 items-center gap-2"><input type="checkbox" className="h-4 w-4 shrink-0" checked={minor} onChange={(e) => setMinor(e.target.checked)} /> Reşit değil: işbirliğinde veli onayı gerektiği uyarısı gösterilir</label>
        <div className="flex justify-end">
          <button type="button" className={btnPrimary} disabled={!name.trim() || save.isPending} onClick={() => save.mutate()}>
            {save.isPending && <Loader2 aria-hidden className="h-4 w-4 animate-spin" />}
            {person ? 'Değişiklikleri kaydet' : 'İçerik üreticisini ekle'}
          </button>
        </div>
      </div>
    </Sheet>
  );
}
