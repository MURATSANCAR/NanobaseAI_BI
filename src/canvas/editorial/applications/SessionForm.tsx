import { useEffect, useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Note, btnGhost, btnPrimary, field, label } from '../../admin/ui';
import Sheet from '../studio/reader/Sheet';
import SearchSelect from '../../components/SearchSelect';
import { nowLocal, usePeopleOptions } from '../authors/shared';
import { boardApi, type SessionHead } from './api';
import { errMsg, invalidateApps, useAppMeta } from './shared';

/** Kurul oturumu açma ve düzenleme: tarih, saat, yer, başkan, üyeler. Başkan üyelere kendiliğinden eklenir. */

type Form = { title: string; date: string; time: string; place: string; chair: string; members: string[]; note: string };

export default function SessionForm({
  open,
  onClose,
  session,
  onSaved,
}: {
  open: boolean;
  onClose: () => void;
  session?: SessionHead | null;
  onSaved: (s: SessionHead) => void;
}) {
  const qc = useQueryClient();
  const meta = useAppMeta();
  const people = usePeopleOptions();
  const me = meta.data?.me.username ?? '';
  const init = (): Form =>
    session
      ? { title: session.title, date: session.date, time: session.time ?? '', place: session.place ?? '', chair: session.chair, members: session.members.map((m) => m.username), note: session.note ?? '' }
      : { title: '', date: nowLocal().date, time: '10:00', place: '', chair: me, members: [], note: '' };
  const [f, setF] = useState<Form>(init);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    if (open) {
      setF(init());
      setErr(null);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, session, me]);
  const set = <K extends keyof Form>(k: K, v: Form[K]) => setF((p) => ({ ...p, [k]: v }));
  const name = (u: string) => people.byUser.get(u) ?? (u === me ? meta.data?.me.display ?? u : u);

  const save = useMutation({
    mutationFn: () => {
      const body = {
        title: f.title, date: f.date, time: f.time, place: f.place, note: f.note, chair: f.chair, chairName: name(f.chair),
        members: f.members.map((u) => ({ username: u, display: name(u) })),
      };
      return session ? boardApi.update(session.id, body) : boardApi.create(body);
    },
    onSuccess: async (s) => {
      await invalidateApps(qc);
      toast.success(session ? 'Oturum güncellendi' : 'Kurul oturumu açıldı', { description: s.title });
      onSaved(s);
    },
    onError: (e) => setErr(errMsg(e)),
  });

  return (
    <Sheet open={open} onClose={onClose} modal title={session ? 'Oturumu düzenle' : 'Yeni kurul oturumu'} subtitle="Gündeme «Kurula çıkacak» başvurular eklenir; üyeler kendi puanını ve oyunu girer.">
      <form
        className="space-y-3 text-[12.5px]"
        onSubmit={(e) => {
          e.preventDefault();
          setErr(null);
          save.mutate();
        }}
      >
        <div className="grid grid-cols-2 gap-2">
          <label className="block">
            <span className={label}>Tarih</span>
            <input required type="date" value={f.date} onChange={(e) => set('date', e.target.value)} className={`${field} mt-1`} />
          </label>
          <label className="block">
            <span className={label}>Saat</span>
            <input type="time" value={f.time} onChange={(e) => set('time', e.target.value)} className={`${field} mt-1`} />
          </label>
        </div>
        <label className="block">
          <span className={label}>Başlık</span>
          <input maxLength={200} value={f.title} onChange={(e) => set('title', e.target.value)} placeholder="Boş bırakılırsa «Yayın kurulu · tarih»" className={`${field} mt-1`} />
        </label>
        <label className="block">
          <span className={label}>Yer</span>
          <input maxLength={200} value={f.place} onChange={(e) => set('place', e.target.value)} placeholder="Toplantı odası ya da çevrim içi" className={`${field} mt-1`} />
        </label>
        <div>
          <span className={label}>Başkan</span>
          <div className="mt-1">
            <SearchSelect label="Başkan" placeholder="Kişi seçin" options={people.options} value={f.chair} onChange={(v) => set('chair', v || me)} />
          </div>
        </div>
        <div>
          <span className={label}>Üyeler</span>
          <div className="mt-1">
            <SearchSelect label="Üyeler" multiple placeholder="Kişi ekleyin" options={people.options} value={f.members} onChange={(v) => set('members', v)} />
          </div>
          <p className="mt-0.5 text-[11px] text-canvas-muted">Yalnız üyeler oy verir. Oy vermiş üye çıkarılamaz.</p>
        </div>
        <label className="block">
          <span className={label}>Not</span>
          <textarea rows={2} maxLength={4000} value={f.note} onChange={(e) => set('note', e.target.value)} className={`${field} mt-1`} />
        </label>
        {err && <Note tone="err">{err}</Note>}
        <div className="flex flex-wrap justify-end gap-2">
          <button type="button" className={btnGhost} onClick={onClose}>
            Vazgeç
          </button>
          <button type="submit" className={btnPrimary} disabled={save.isPending}>
            {save.isPending ? 'Kaydediliyor…' : session ? 'Kaydet' : 'Oturumu aç'}
          </button>
        </div>
      </form>
    </Sheet>
  );
}
