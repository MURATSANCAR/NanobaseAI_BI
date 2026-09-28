import { useState, type ReactNode } from 'react';
import { useParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Copy, ExternalLink, Loader2, Trash2 } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import SqlInfo, { InfoLabel } from '../components/SqlInfo';
import { Note, Pill, TableWrap, btnGhost, btnPrimary, errText, field, td, th } from '../admin/ui';
import { Panel } from '../editorial/kit';
import { fmtDay, fmtDays, fmtMoney, fmtNum, shippingApi, type Draft, type DraftType, type Meta, type ShipmentCard } from './api';
import { Empty, FreshNote, ShippingFrame, StatusPill } from './parts';

/** M44 Gönderi kartı (/kargo/gonderi/:id): sipariş → depo → kutulama → sevk → kargo → teslim zaman çizelgesi, entegrasyon
 *  sonucu, kargo kaydı, CRM sevkiyatı ve Logo karşılığı, Zeki AI mesaj taslakları. Alıcı adı yalnız `kargo.alici` ile,
 *  tutar/desi yalnız `kargo.maliyet` ile sunucudan gelir. */

export default function Shipment() {
  const { id = '' } = useParams();
  const meta = useQuery({ queryKey: ['shipping', 'meta'], queryFn: shippingApi.meta, enabled: ENGINE_ENABLED, staleTime: 60_000 });
  const card = useQuery({ queryKey: ['shipping', 'shipment', id], queryFn: () => shippingApi.shipment(id), enabled: ENGINE_ENABLED && !!id });
  const d = card.data;
  const o = d?.siparis;
  return (
    <ShippingFrame
      back
      crumb="Kargo"
      detail={o?.no ?? undefined}
      title={o ? `Sipariş ${o.no ?? ''}` : 'Gönderi'}
      lead={o ? `${o.musteri ?? 'Müşteri yok'}${o.cariKodu ? ` · ${o.cariKodu}` : ''}${o.il ? ` · ${o.il}` : ''}` : 'Sipariş okunuyor…'}
      meta={meta.data}
    >
      {card.isLoading && <Note tone="info">CRM sipariş, sevkiyat ve kargo kaydı okunuyor…</Note>}
      {card.error && <Note tone="err">{errText(card.error, 'Gönderi okunamadı.')}</Note>}
      {d && o && (
        <>
          <Panel>
            <div className="flex flex-wrap items-center gap-2">
              <StatusPill o={o} />
              {o.tipAdi && <Pill tone="muted">{o.tipAdi}</Pill>}
              {o.etiket ? <Pill tone="ok">Etiket basıldı</Pill> : <Pill tone="warn">Etiket basılmadı</Pill>}
              {o.odeme && <Pill tone="muted">{o.odeme}</Pill>}
            </div>
            <div className="mt-3 grid grid-cols-2 gap-2 lg:grid-cols-4">
              <Fact label="Kargo firması" value={o.firma ?? 'Seçilmemiş'} />
              <Fact
                label="Takip no"
                value={
                  o.takipNo ? (
                    o.takipUrl ? (
                      <a className="inline-flex items-center gap-1 font-mono text-canvas-violet hover:underline" href={o.takipUrl} target="_blank" rel="noreferrer noopener">
                        {o.takipNo}
                        <ExternalLink aria-hidden className="h-3.5 w-3.5" />
                      </a>
                    ) : (
                      <span className="font-mono">{o.takipNo}</span>
                    )
                  ) : (
                    'Yok'
                  )
                }
              />
              <Fact label="Koli" value={fmtNum(o.kutu)} info={<SqlInfo k={d.kaynaklar} alan="siparis.kutu" label="Koli" />} />
              <Fact label="Sipariş → sevk" value={fmtDays(o.sevkeKadarGun)} info={<SqlInfo k={d.kaynaklar} alan="siparis.sevkeKadarGun" label="Sipariş → sevk" />} />
            </div>
          </Panel>
          <div className="grid grid-cols-1 gap-3 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)] lg:gap-4">
            <Panel>
              <h2 className="text-[14px] font-extrabold"><InfoLabel k={d.kaynaklar} alan="zamanCizelgesi">Zaman çizelgesi</InfoLabel></h2>
              <ol className="mt-2 flex flex-col">
                {d.zamanCizelgesi.map((s, i) => (
                  <li key={`${s.asama}-${i}`} className="relative flex gap-3 pb-3 pl-1 last:pb-0">
                    <span aria-hidden className="relative mt-1 flex w-3 shrink-0 justify-center">
                      <span className="h-2.5 w-2.5 rounded-full bg-canvas-violet" />
                      {i < d.zamanCizelgesi.length - 1 && <span className="absolute top-3 h-[calc(100%+2px)] w-px bg-slate-200" />}
                    </span>
                    <div className="min-w-0">
                      <div className="text-[12.5px] font-bold">{s.asama}</div>
                      <div className="font-mono text-[11.5px] tabular-nums text-canvas-muted">
                        {s.zaman ? fmtDay(s.zaman) : 'tarih yok'} · {s.kaynak}
                        {s.oncekindenGun !== null && s.oncekindenGun > 0 && ` · +${s.oncekindenGun} gün`}
                      </div>
                    </div>
                  </li>
                ))}
              </ol>
              {d.kargo.length === 0 && (
                <p className="mt-2 text-[11.5px] text-canvas-muted">Bu siparişe bağlanan kargo kaydı yok (eşleme: {d.eslemeYolu}). Teslim bilgisi bu yüzden görünmüyor olabilir.</p>
              )}
            </Panel>
            <Panel>
              <h2 className="text-[14px] font-extrabold">Entegrasyon sonucu</h2>
              {d.hatalar.length === 0 ? (
                <Empty>Kargo firması servisinden hata kaydı yok.</Empty>
              ) : (
                <div className="mt-2 flex flex-col gap-2">
                  {d.hatalar.map((f) => (
                    <div key={f.mesajHash} className="rounded-xl bg-red-50/70 p-2.5">
                      <div className="flex flex-wrap items-center gap-1.5">
                        <Pill tone="err">{f.entegrasyon}</Pill>
                        {f.sonuc && <span className="text-[12px] font-bold">{f.sonuc}</span>}
                        {f.sinif && <Pill tone="violet">Zeki AI: {f.sinif}</Pill>}
                      </div>
                      {f.mesaj && <p className="mt-1 break-words text-[12px] leading-snug">{f.mesaj}</p>}
                    </div>
                  ))}
                </div>
              )}
              <h3 className="mt-3 text-[12px] font-extrabold uppercase tracking-wide text-canvas-muted">Takip kayıtları</h3>
              {d.takip.length === 0 ? (
                <p className="text-[12px] text-canvas-muted">Yok.</p>
              ) : (
                <ul className="mt-1 flex flex-col gap-1 text-[12px]">
                  {d.takip.map((t, i) => (
                    <li key={i} className="flex flex-wrap gap-x-3 font-mono">
                      <span>{t.takipNo ?? '—'}</span>
                      <span className="text-canvas-muted">{t.belgeNo ?? ''}</span>
                    </li>
                  ))}
                </ul>
              )}
            </Panel>
          </div>
          <Panel>
            <h2 className="text-[14px] font-extrabold"><InfoLabel k={d.kaynaklar} alan="kargo">Kargo kaydı</InfoLabel></h2>
            <p className="text-[11.5px] text-canvas-muted">
              Kargo firmasının gönderi kaydı (eşleme: {d.eslemeYolu}).{!d.aliciGorunur && ' Alıcı adı yetkiyle görünür.'}
              {!d.maliyetGorunur && ' Tutar ve desi yetkiyle görünür.'}
            </p>
            {d.kargo.length === 0 ? (
              <Empty>Bağlı kargo kaydı yok.</Empty>
            ) : (
              <div className="mt-2">
                <TableWrap>
                  <thead>
                    <tr>
                      <th className={th}>Firma</th>
                      <th className={th}>Takip no</th>
                      <th className={th}>İrsaliye</th>
                      <th className={th}>Teslim</th>
                      <th className={th}>Şehir / şube</th>
                      {d.aliciGorunur && <th className={th}>Alıcı / teslim alan</th>}
                      {d.maliyetGorunur && <th className={`${th} text-right`}><InfoLabel k={d.kaynaklar} alan="kargo">Desi</InfoLabel></th>}
                      {d.maliyetGorunur && <th className={`${th} text-right`}><InfoLabel k={d.kaynaklar} alan="kargo">Tutar</InfoLabel></th>}
                    </tr>
                  </thead>
                  <tbody>
                    {d.kargo.map((c) => (
                      <tr key={c.id} className="border-t border-slate-100">
                        <td className={td}>{c.firma}</td>
                        <td className={`${td} font-mono`}>{c.takipNo ?? '—'}</td>
                        <td className={`${td} font-mono tabular-nums`}>{fmtDay(c.irsTarihi)}</td>
                        <td className={td}>
                          {c.teslimTarihi ? (
                            <span className="font-mono tabular-nums">{fmtDay(c.teslimTarihi)}{c.gun !== null && ` (${c.gun} gün)`}</span>
                          ) : c.iade ? (
                            <Pill tone="err">İade: {c.iadeDurumu}</Pill>
                          ) : (
                            <Pill tone="warn">Teslim yok</Pill>
                          )}
                        </td>
                        <td className={td}>{[c.sehir, c.varisSube].filter(Boolean).join(' · ') || '—'}</td>
                        {d.aliciGorunur && <td className={td}>{[c.alici, c.teslimAlan].filter(Boolean).join(' / ') || '—'}</td>}
                        {d.maliyetGorunur && <td className={`${td} text-right font-mono tabular-nums`}>{fmtNum(c.desi)}</td>}
                        {d.maliyetGorunur && <td className={`${td} text-right font-mono tabular-nums`}>{fmtMoney(c.tutar)}</td>}
                      </tr>
                    ))}
                  </tbody>
                </TableWrap>
              </div>
            )}
          </Panel>
          <Panel>
            <h2 className="text-[14px] font-extrabold">CRM sevkiyatı ve Logo</h2>
            {d.logoNotu && <div className="mt-1"><Note tone="warn">{d.logoNotu}</Note></div>}
            {d.sevkiyatlar.length === 0 ? (
              <Empty>Bu siparişin sevkiyat kaydı yok.</Empty>
            ) : (
              <div className="mt-2">
                <TableWrap>
                  <thead>
                    <tr>
                      <th className={th}>Sevkiyat</th>
                      <th className={th}>Tarih</th>
                      <th className={th}>Tür</th>
                      <th className={th}>Fatura no</th>
                      <th className={th}>Logo</th>
                      <th className={th}>Müşteriye e-posta</th>
                    </tr>
                  </thead>
                  <tbody>
                    {d.sevkiyatlar.map((s) => (
                      <tr key={s.id} className="border-t border-slate-100">
                        <td className={`${td} font-mono`}>{s.no ?? '—'}</td>
                        <td className={`${td} font-mono tabular-nums`}>{fmtDay(s.tarih)}</td>
                        <td className={td}>{s.tur ?? '—'}</td>
                        <td className={`${td} font-mono`}>{s.faturaNo ?? '—'}</td>
                        <td className={td}>
                          {s.logo ? <Pill tone="ok">Faturada · {fmtDay(s.logo.tarih)}</Pill> : s.logoyaAktarildi ? <Pill tone="warn">Aktarıldı, Logo'da bulunamadı</Pill> : <Pill tone="muted">Aktarılmadı</Pill>}
                        </td>
                        <td className={td}>{s.epostaGitti === null ? '—' : s.epostaGitti ? 'Gitti' : 'Gitmedi'}</td>
                      </tr>
                    ))}
                  </tbody>
                </TableWrap>
              </div>
            )}
          </Panel>
          {meta.data && <DraftsPanel meta={meta.data} card={d} />}
          <FreshNote f={d.kargoVeri} k={d.kaynaklar} />
        </>
      )}
    </ShippingFrame>
  );
}

function Fact({ label, value, info }: { label: string; value: ReactNode; info?: ReactNode }) {
  return (
    <div className="min-w-0 rounded-xl bg-white/80 px-3 py-2">
      <div className="flex items-center gap-1 text-[10.5px] font-bold uppercase tracking-wide text-canvas-muted">{label}{info}</div>
      <div className="mt-0.5 break-words text-[13.5px] font-bold">{value}</div>
    </div>
  );
}

function DraftsPanel({ meta, card }: { meta: Meta; card: ShipmentCard }) {
  const qc = useQueryClient();
  const key = ['shipping', 'shipment', card.siparis.id];
  const create = useMutation({
    mutationFn: (tur: DraftType) => shippingApi.createDraft(card.siparis.id, tur),
    onSuccess: (dr) => {
      qc.invalidateQueries({ queryKey: key });
      toast.success(dr.kaynak === 'zeki' ? 'Zeki AI taslağı hazır.' : 'Taslak hazır (kural metni).');
    },
    onError: (e) => toast.error(errText(e, 'Taslak üretilemedi.') ?? ''),
  });
  return (
    <Panel>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <h2 className="text-[14px] font-extrabold">Müşteri mesajı taslakları</h2>
          <p className="max-w-[80ch] text-[11.5px] text-canvas-muted">
            Zeki AI yalnız sipariş numarası, durum, firma ve aşama günlerinden yazar; müşteri adı ve adresi modele gitmez. Portal mesaj göndermez: metni kopyalayıp kendi e-postanızdan gönderin.
          </p>
        </div>
        {meta.me.taslak && (
          <div className="flex flex-wrap gap-1.5">
            {(Object.keys(meta.taslakTurleri) as DraftType[]).map((t) => (
              <button key={t} type="button" className={btnGhost} disabled={create.isPending} onClick={() => create.mutate(t)}>
                {create.isPending && create.variables === t && <Loader2 aria-hidden className="h-4 w-4 animate-spin" />}
                {meta.taslakTurleri[t]}
              </button>
            ))}
          </div>
        )}
      </div>
      {card.taslaklar.length === 0 ? (
        <Empty>Henüz taslak yok.</Empty>
      ) : (
        <div className="mt-2 flex flex-col gap-2">
          {card.taslaklar.map((dr) => <DraftItem key={dr.id} dr={dr} canEdit={meta.me.taslak} onChanged={() => qc.invalidateQueries({ queryKey: key })} />)}
        </div>
      )}
    </Panel>
  );
}

function DraftItem({ dr, canEdit, onChanged }: { dr: Draft; canEdit: boolean; onChanged: () => void }) {
  const [text, setText] = useState(dr.metin);
  const dirty = text.trim() !== dr.metin;
  const save = useMutation({
    mutationFn: (b: { metin?: string; durum?: 'taslak' | 'kullanildi' }) => shippingApi.updateDraft(dr.id, b),
    onSuccess: () => {
      onChanged();
      toast.success('Kaydedildi.');
    },
    onError: (e) => toast.error(errText(e, 'Kaydedilemedi.') ?? ''),
  });
  const del = useMutation({
    mutationFn: () => shippingApi.deleteDraft(dr.id),
    onSuccess: onChanged,
    onError: (e) => toast.error(errText(e, 'Silinemedi.') ?? ''),
  });
  const copy = () =>
    navigator.clipboard
      ?.writeText(text)
      .then(() => toast.success('Metin kopyalandı.'))
      .catch(() => toast.error('Kopyalanamadı; metni seçip kopyalayın.'));
  return (
    <div className="rounded-xl border border-slate-100 bg-white/80 p-2.5">
      <div className="flex flex-wrap items-center gap-1.5 text-[11.5px]">
        <Pill tone="violet">{dr.turAdi}</Pill>
        <Pill tone={dr.durum === 'kullanildi' ? 'ok' : 'muted'}>{dr.durumAdi}</Pill>
        <span className="text-canvas-muted">{dr.kaynak === 'zeki' ? 'Zeki AI' : 'Kural metni'} · {dr.yazan} · {fmtDay(dr.olusturma)}</span>
      </div>
      <textarea className={`${field} mt-2 min-h-[96px]`} value={text} readOnly={!canEdit} onChange={(e) => setText(e.target.value)} />
      <div className="mt-2 flex flex-wrap justify-end gap-1.5">
        <button type="button" className={btnGhost} onClick={copy}>
          <Copy aria-hidden className="h-4 w-4" />
          Kopyala
        </button>
        {canEdit && dirty && (
          <button type="button" className={btnPrimary} disabled={save.isPending} onClick={() => save.mutate({ metin: text.trim() })}>
            Metni kaydet
          </button>
        )}
        {canEdit && dr.durum === 'taslak' && (
          <button type="button" className={btnGhost} disabled={save.isPending} onClick={() => save.mutate({ durum: 'kullanildi' })}>
            Gönderdim, kullanıldı
          </button>
        )}
        {canEdit && (
          <button type="button" className={btnGhost} aria-label="Taslağı sil" disabled={del.isPending} onClick={() => del.mutate()}>
            <Trash2 aria-hidden className="h-4 w-4" />
          </button>
        )}
      </div>
    </div>
  );
}
