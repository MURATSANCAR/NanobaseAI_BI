import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Loader2, Wand2 } from 'lucide-react';
import { toast } from 'sonner';
import { Note, btnGhost, btnPrimary, field } from '../../admin/ui';
import { Panel } from '../kit';
import { contractApi, type Detail } from './api';
import { errMsg } from './ui';

/** Sözleşme metni: şablondan üretilir, taslakken elle düzenlenir, Word olarak indirilir. İmzadan sonra değişmez. */
export default function TextTab({ d }: { d: Detail }) {
  const qc = useQueryClient();
  const rec = d.record;
  const editable = !!rec && d.can.edit && (d.status === 'taslak' || d.status === 'imzada');
  const tpls = useQuery({ queryKey: ['contracts', 'templates', 'sozlesme'], queryFn: () => contractApi.templates({ target: 'sozlesme' }) });
  const options = tpls.data?.items ?? [];
  const preferred = options.find((t) => t.id === rec?.templateId) ?? options.find((t) => t.kind === d.terms.kind) ?? options[0];
  const [tpl, setTpl] = useState('');
  const [text, setText] = useState(rec?.body ?? '');
  useEffect(() => setText(rec?.body ?? ''), [rec?.body]);
  useEffect(() => {
    if (!tpl && preferred) setTpl(preferred.id);
  }, [tpl, preferred]);
  const done = () => {
    qc.invalidateQueries({ queryKey: ['contracts', 'detail'] });
  };
  const render = useMutation({ mutationFn: () => contractApi.render(rec!.id, tpl), onSuccess: () => { toast.success('Metin şablondan üretildi.'); done(); } });
  const save = useMutation({ mutationFn: () => contractApi.body(rec!.id, text, rec!.version), onSuccess: () => { toast.success('Metin kaydedildi.'); done(); } });
  const dirty = (rec?.body ?? '') !== text;

  if (!rec)
    return (
      <Panel>
        <p className="py-6 text-center text-[12.5px] text-canvas-muted">
          CRM sözleşmenin metnini tutmuyor. Metin portalda şablondan üretilir; önce sözleşmeyi düzenleyip portala alın.
        </p>
      </Panel>
    );
  const selected = options.find((t) => t.id === tpl);
  return (
    <Panel>
      {editable && (
        <div className="mb-3 flex flex-wrap items-end gap-2">
          <label className="min-w-0 flex-1">
            <span className="text-[11px] font-bold uppercase tracking-wide text-canvas-muted">Şablon</span>
            <select value={tpl} onChange={(e) => setTpl(e.target.value)} className={`${field} mt-1`}>
              {options.map((t) => (
                <option key={t.id} value={t.id}>{t.name} · s{t.version}{t.hasDocx ? ' · Word' : ''}</option>
              ))}
            </select>
          </label>
          <button type="button" className={btnGhost} disabled={!tpl || render.isPending} onClick={() => (!rec.body || window.confirm('Mevcut metin şablondan yeniden üretilecek; elle yapılan değişiklikler gider. Devam edilsin mi?')) && render.mutate()}>
            {render.isPending ? <Loader2 aria-hidden className="h-4 w-4 animate-spin" /> : <Wand2 aria-hidden className="h-4 w-4" />}
            Şablondan üret
          </button>
          <Link to="/telif-sozlesme/sablonlar" className="inline-flex min-h-11 items-center text-[12px] font-bold text-canvas-violet hover:underline sm:min-h-0">Şablonlar</Link>
        </div>
      )}
      {selected?.hasDocx && editable && (
        <div className="mb-3"><Note tone="info">Bu şablonun Word dosyası var: «Word» indirmesi Word dosyasını doldurur; buradaki metin yalnız önizlemedir.</Note></div>
      )}
      {rec.bodyEdited && <div className="mb-3"><Note tone="info">Metin şablondan üretildikten sonra elle düzenlendi.</Note></div>}
      {!rec.body && !editable && <p className="py-6 text-center text-[12.5px] text-canvas-muted">Metin üretilmemiş. «Word» indirmesi seçili şablonu şartlarla doldurur.</p>}
      {(rec.body || editable) && (
        <textarea
          aria-label="Sözleşme metni"
          value={text}
          onChange={(e) => setText(e.target.value)}
          readOnly={!editable}
          rows={24}
          placeholder="Şablon seçip «Şablondan üret»e basın ya da metni buraya yazın. «# » ile başlayan satır başlık olur."
          className={`${field} min-h-[50dvh] font-serif text-[14px] leading-relaxed sm:text-[13px]`}
        />
      )}
      {editable && (
        <div className="mt-2 flex flex-wrap items-center justify-end gap-2">
          {dirty && <span className="text-[11.5px] font-semibold text-amber-700">Kaydedilmemiş değişiklik var</span>}
          <button type="button" className={btnPrimary} disabled={!dirty || save.isPending} onClick={() => save.mutate()}>
            {save.isPending && <Loader2 aria-hidden className="h-4 w-4 animate-spin" />}
            Metni kaydet
          </button>
        </div>
      )}
      {(render.error || save.error) && <div className="mt-2"><Note tone="err">{errMsg(render.error || save.error)}</Note></div>}
      {!editable && rec.body && <p className="mt-2 text-[11.5px] text-canvas-muted">İmzalanmış sözleşmenin metni değişmez; değişiklik zeyilnameyle yapılır.</p>}
    </Panel>
  );
}
