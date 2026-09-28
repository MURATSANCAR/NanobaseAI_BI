import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { ENGINE_ENABLED, translationApi } from '../../engine';
import { Loading, Note, Pill, errText, nf } from '../../admin/ui';
import { num } from '../../format';
import { Panel } from '../kit';
import { LANGS, pct } from './parts';
import SqlInfo from '../../components/SqlInfo';
import { kaynakOf } from '../../components/kaynakOf';

/** Çevirmen karnesi: çeviri işlerimize atanmış kişiler; iş, kelime, inceleme puanı ve teslim. Kayıtlar yalnız
 *  bu modülün işlerinden gelir; CRM'deki çevirmen listesi Kişiler ekranındadır. */

const pairText = (p: string) =>
  p
    .split('→')
    .map((c) => LANGS[c] ?? c)
    .join(' → ');

export default function Translators() {
  const q = useQuery({ queryKey: ['translation', 'translators'], queryFn: translationApi.translators, enabled: ENGINE_ENABLED });
  const items = q.data?.items ?? [];
  return (
    <Panel>
      <div className="flex flex-wrap items-baseline justify-between gap-2 px-1">
        <h2 className="flex items-center gap-1 text-[13px] font-extrabold">
          Çevirmen karnesi
          <SqlInfo k={kaynakOf(q.data)} alan="_hepsi" label="Çevirmen karnesi" />
        </h2>
        <Link to="/kisiler?rol=cevirmen" className="text-[11.5px] font-bold text-canvas-violet underline">
          CRM'deki çevirmenler
        </Link>
      </div>
      <p className="mt-0.5 px-1 text-[11.5px] leading-snug text-canvas-muted">
        İnceleme puanı MQM yöntemiyle: onaylanan kelimelere göre hata ağırlıkları (küçük 1, büyük 5, kritik 25). Teslim, işin son segmenti onaylandığı gün ile teslim tarihinin karşılaştırmasıdır.
      </p>
      {q.error && <Note tone="err">{errText(q.error, 'Çevirmenler okunamadı.')}</Note>}
      {q.isLoading && <Loading />}
      {q.data && !items.length && <p className="mt-3 px-1 text-[12px] text-canvas-muted">Henüz çevirmen atanmış iş yok.</p>}
      <ul className="mt-2 grid gap-2 md:grid-cols-2 2xl:grid-cols-3">
        {items.map((t) => (
          <li key={t.username} className="rounded-2xl border border-slate-100 bg-white/85 p-3 text-[12.5px]">
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0">
                <p className="break-words font-extrabold leading-snug">{t.name || t.username}</p>
                <p className="text-[11px] text-canvas-muted">
                  {t.username} · {t.pairs.map(pairText).join(', ')}
                </p>
              </div>
              {t.active > 0 ? <Pill tone="warn">{nf.format(t.active)} süren</Pill> : <Pill tone="muted">Boşta</Pill>}
            </div>
            <dl className="mt-2.5 grid grid-cols-3 gap-2 text-[11px]">
              <div>
                <dt className="text-canvas-muted">İş</dt>
                <dd className="font-mono text-[14px] font-bold tabular-nums">{nf.format(t.jobs)}</dd>
              </div>
              <div>
                <dt className="text-canvas-muted">Çevrilen</dt>
                <dd className="font-mono text-[14px] font-bold tabular-nums">%{pct(t.wordsDone, t.words)}</dd>
              </div>
              <div>
                <dt className="text-canvas-muted">İnceleme puanı</dt>
                <dd className="font-mono text-[14px] font-bold tabular-nums">{t.mqm == null ? '—' : num(t.mqm, 1)}</dd>
              </div>
            </dl>
            <p className="mt-2 text-[11px] leading-snug text-canvas-muted">
              {nf.format(t.wordsDone)} / {nf.format(t.words)} kelime · {nf.format(t.reviewedWords)} kelime incelendi
              {t.completed ? ` · ${nf.format(t.completed)} iş bitti (${nf.format(t.onTime)} zamanında, ${nf.format(t.late)} geç)` : ''}
            </p>
          </li>
        ))}
      </ul>
    </Panel>
  );
}
