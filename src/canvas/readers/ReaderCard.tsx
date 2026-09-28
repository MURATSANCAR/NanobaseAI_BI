import { useEffect, useState } from 'react';
import { Link, Navigate, useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { ArrowLeft, Eye, Loader2 } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import { Loading, Note, Pill, btnGhost, errText } from '../admin/ui';
import { Panel } from '../editorial/kit';
import { CHANNELS, fmtDay, fmtInt, readersApi, type ReaderCard as Card } from './api';
import { ConsentPill, ROOT, ReadersFrame, useMeta } from './parts';

const ATTR_LABELS: Record<string, string> = {
  form_tipi: 'Form tipi', kayit_tipi: 'Kayıt tipi', departman: 'İlgili departman', katilim_kaynagi: 'Katılım kaynağı',
  alt_kaynak: 'Alt kaynak', utm_kaynak: 'Kampanya kaynağı', utm_kampanya: 'Kampanya adı', etkinlik_adi: 'Katıldığı etkinlik',
};
const RULE_LABELS: Record<string, string> = { tek: 'Tek kayıt', email: 'Aynı e-posta', phone: 'Aynı telefon', kaynak: 'Adayın bağlı kişisi', manual: 'İnsan kararı' };

/** Okur kartı: kaynaklar, izinler (kaynak + tarih), ilgi alanları, zaman çizelgesi. Kişisel veri yalnız yetkiyle, istenince. */
export default function ReaderCard() {
  const { id = '' } = useParams();
  const meta = useMeta();
  const [personal, setPersonal] = useState(false);
  useEffect(() => setPersonal(false), [id]);
  const q = useQuery({
    queryKey: ['readers', 'item', id, personal],
    queryFn: () => readersApi.item(id, personal),
    enabled: ENGINE_ENABLED && !!id,
  });
  const c = q.data;
  if (c?.redirect) return <Navigate replace to={`${ROOT}/kisi/${c.redirect}`} />;
  const labels = meta.data?.channels ?? { email: 'E-posta', sms: 'SMS', call: 'Arama', kvkk: 'KVKK açık rıza' };
  return (
    <ReadersFrame presence={id}>
      <Link to={`${ROOT}/ara`} className="inline-flex items-center gap-1 px-1 text-[12.5px] font-extrabold text-canvas-violet hover:underline">
        <ArrowLeft aria-hidden className="h-3.5 w-3.5" /> Okur ara
      </Link>
      {q.isLoading && <Loading />}
      {q.error && <Note tone="err">{errText(q.error, 'Okur kartı açılamadı.')}</Note>}
      {c && <CardBody c={c} labels={labels} canPersonal={!!meta.data?.me.canPersonal} personal={personal} loadingPersonal={q.isFetching && personal} onPersonal={() => setPersonal(true)} />}
    </ReadersFrame>
  );
}

function CardBody({ c, labels, canPersonal, personal, loadingPersonal, onPersonal }: {
  c: Card; labels: Record<string, string>; canPersonal: boolean; personal: boolean; loadingPersonal: boolean; onPersonal: () => void;
}) {
  const attrs = Object.entries(c.attrs).filter(([k]) => ATTR_LABELS[k]);
  return (
    <div className="flex flex-col gap-3 lg:gap-4">
      <Panel>
        <div className="flex flex-wrap items-center gap-2">
          <h2 className="font-mono text-[17px] font-extrabold">{c.id}</h2>
          {c.status !== 'aktif' && <Pill tone="muted">{c.status === 'pasif' ? 'Kaynakta kaydı kalmadı' : c.status}</Pill>}
          {c.minor && <Pill tone="warn">18 yaş altı</Pill>}
          {c.attrs.uyari?.includes('ortak_iletisim') && <Pill tone="warn">Ortak iletişim bilgisi</Pill>}
          {c.pendingCandidates > 0 && (
            <Link to={`${ROOT}/birlestirme`}><Pill tone="violet">{c.pendingCandidates} birleştirme adayı</Pill></Link>
          )}
        </div>
        <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-2 text-[12.5px] sm:grid-cols-4">
          <Fact k="İl" v={c.city ?? '—'} />
          <Fact k="Doğum yılı" v={c.birthYear ? `${c.birthYear} (${c.age} yaş)` : '—'} />
          <Fact k="İlk kayıt" v={fmtDay(c.firstSeen)} />
          <Fact k="Son temas" v={fmtDay(c.lastTouch)} />
          <Fact k="Cinsiyet" v={c.gender ?? '—'} />
          <Fact k="Etkinlik katılımı" v={fmtInt(c.events)} />
          <Fact k="Kaynak kaydı" v={fmtInt(c.sources.length)} />
          <Fact k="Segment" v={c.segments.length ? c.segments.map((s) => s.name).join(', ') : '—'} />
        </dl>
        {canPersonal && !personal && (
          <button type="button" className={`${btnGhost} mt-3`} onClick={onPersonal}>
            <Eye aria-hidden className="h-4 w-4" /> Ad, e-posta ve telefonu göster (kayda geçer)
          </button>
        )}
        {loadingPersonal && <p className="mt-2 flex items-center gap-1.5 text-[12px] text-canvas-muted"><Loader2 aria-hidden className="h-3.5 w-3.5 animate-spin" />CRM'den okunuyor…</p>}
        {c.personal && (
          <ul className="mt-3 flex flex-col gap-1.5">
            {c.personal.map((p) => (
              <li key={p.sourceId} className="rounded-xl bg-amber-50/60 p-2.5 text-[12.5px]">
                <div className="font-bold">{p.name ?? '(ad yok)'} <span className="font-normal text-canvas-muted">· {p.source}{p.active ? '' : ' (etkin değil)'}</span></div>
                <div className="break-all text-canvas-muted">{[p.email, p.email2, p.phone].filter(Boolean).join(' · ') || 'İletişim bilgisi yok'}</div>
              </li>
            ))}
          </ul>
        )}
      </Panel>

      <div className="grid gap-3 lg:grid-cols-[1.1fr_1fr] lg:gap-4">
        <Panel>
          <h2 className="text-[15px] font-extrabold">İzinler</h2>
          <p className="mt-0.5 text-[11.5px] text-canvas-muted">Ret her zaman kazanır; izinli yalnız İYS onayıyla. Kanıtlar eskiden yeniye.</p>
          <div className="mt-2 flex flex-col divide-y divide-slate-100">
            {[...CHANNELS, 'kvkk' as const].map((ch) => {
              const x = c.consents[ch];
              return (
                <div key={ch} className="py-2">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <span className="text-[12.5px] font-bold">{labels[ch]}</span>
                    <span className="flex items-center gap-2">
                      {x.at && <span className="font-mono text-[11px] text-canvas-muted">{fmtDay(x.at)}{x.sourceLabel ? ` · ${x.sourceLabel}` : ''}</span>}
                      <ConsentPill status={x.status} />
                      {ch !== 'kvkk' && c.exportable[ch] && <Pill tone="violet">Listeye girebilir</Pill>}
                    </span>
                  </div>
                  {x.evidence.length > 0 && (
                    <ul className="mt-1 space-y-0.5 text-[11.5px] text-canvas-muted">
                      {x.evidence.map((e, i) => (
                        <li key={i}>{fmtDay(e.at)} — {e.status === 'ret' ? 'ret' : 'izinli'} ({e.sourceLabel}{e.detail && e.detail !== 'İYS' ? `: ${e.detail}` : ''}; {e.record})</li>
                      ))}
                    </ul>
                  )}
                </div>
              );
            })}
          </div>
        </Panel>
        <div className="flex flex-col gap-3 lg:gap-4">
          <Panel>
            <h2 className="text-[15px] font-extrabold">Kaynaklar</h2>
            <ul className="mt-2 space-y-1 text-[12.5px]">
              {c.sources.map((s, i) => (
                <li key={i} className="flex flex-wrap justify-between gap-2">
                  <span className="font-bold">{s.label}</span>
                  <span className="text-canvas-muted">{RULE_LABELS[s.rule] ?? s.rule}{s.decidedBy ? ` (${s.decidedBy})` : ''} · {fmtDay(s.created)}</span>
                </li>
              ))}
            </ul>
          </Panel>
          <Panel>
            <h2 className="text-[15px] font-extrabold">İlgi alanları ve etiketler</h2>
            {c.interests.length === 0 && attrs.length === 0 && <p className="mt-1 text-[12.5px] text-canvas-muted">Kayıtlarda ilgi alanı yok.</p>}
            {c.interests.length > 0 && (
              <div className="mt-2 flex flex-wrap gap-1">{c.interests.map((i) => <Pill key={i.ad} tone="violet">{i.ad}</Pill>)}</div>
            )}
            <dl className="mt-2 space-y-1 text-[12px]">
              {attrs.map(([k, v]) => (
                <div key={k} className="flex flex-wrap gap-x-2"><dt className="font-bold">{ATTR_LABELS[k]}:</dt><dd className="text-canvas-muted">{v.join(', ')}</dd></div>
              ))}
            </dl>
          </Panel>
        </div>
      </div>

      <Panel>
        <h2 className="text-[15px] font-extrabold">Zaman çizelgesi</h2>
        <ol className="mt-2 space-y-1.5">
          {c.timeline.map((t, i) => (
            <li key={i} className="flex gap-3 text-[12.5px]">
              <span className="w-24 shrink-0 font-mono text-[11.5px] text-canvas-muted">{fmtDay(t.at)}</span>
              <span>{t.text}</span>
            </li>
          ))}
        </ol>
      </Panel>
    </div>
  );
}

function Fact({ k, v }: { k: string; v: string }) {
  return (
    <div className="min-w-0">
      <dt className="text-[11px] font-bold uppercase tracking-wide text-canvas-muted">{k}</dt>
      <dd className="truncate font-semibold" title={v}>{v}</dd>
    </div>
  );
}
