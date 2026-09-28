import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { ENGINE_ENABLED } from '../engine';
import { Loading, Note, Pill, btnGhost, btnPrimary, errText, field, label as labelCls } from '../admin/ui';
import { AskSheet } from '../budget/parts';
import { fmtDay } from '../field/api';
import { Block, Empty } from '../field/parts';
import {
  SEGMENTS,
  dealersApi,
  distTotal,
  thresholdsOk,
  weightSum,
  type ComponentKey,
  type DealersMeta,
  type Preview,
  type Rule,
  type RuleBody,
} from './api';
import { DistBar } from './parts';

/** Kurallar: skor ağırlıkları, segment eşikleri, kapsam kanalları ve limit önerisi kuralı sürümlüdür (taslak → onaya gönder →
 *  onay → yürürlükte; önceki arşive iner). Hazırlayan ya da gönderen onaylayamaz. Önizleme bugünkü satırların ham girdilerini
 *  taslak kuralla yeniden puanlar ve segment dağılımını yan yana gösterir. */

const STATE_TONE: Record<Rule['durum'], 'ok' | 'warn' | 'muted' | 'violet'> = { yururlukte: 'ok', onayda: 'warn', taslak: 'violet', arsiv: 'muted' };

export default function RulesTab({ meta }: { meta: DealersMeta }) {
  const q = useQuery({ queryKey: ['dealers', 'rules'], queryFn: dealersApi.rules, enabled: ENGINE_ENABLED });
  const [edit, setEdit] = useState<Rule | 'new' | null>(null);
  const err = errText(q.error, 'Kurallar okunamadı.');
  if (q.isLoading) return <Loading />;
  if (err) return <Note tone="err">{err}</Note>;
  const items = q.data?.items ?? [];
  const active = items.find((r) => r.durum === 'yururlukte') ?? meta.rule;
  const open = items.filter((r) => r.durum === 'taslak' || r.durum === 'onayda');

  return (
    <div className="flex flex-col gap-3">
      <RuleView rule={active} meta={meta} />
      {meta.me.canRule && !edit && (
        <button type="button" className={`${btnPrimary} self-start`} onClick={() => setEdit('new')}>
          Yeni sürüm taslağı
        </button>
      )}
      {edit && <RuleEditor meta={meta} base={edit === 'new' ? active : edit} existing={edit === 'new' ? null : edit} onClose={() => setEdit(null)} />}
      {open.length > 0 && (
        <Block title="Taslak ve onay bekleyen sürümler">
          <ul className="flex flex-col gap-2">
            {open.map((r) => (
              <DraftItem key={r.id} r={r} meta={meta} onEdit={() => setEdit(r)} />
            ))}
          </ul>
        </Block>
      )}
      <Block title="Sürüm geçmişi">
        {items.length === 0 ? (
          <Empty>Henüz kural yok; ilk günlük turda başlangıç kuralı yürürlüğe girer.</Empty>
        ) : (
          <ul className="flex flex-col gap-1">
            {items.map((r) => (
              <li key={r.id} className="flex flex-wrap items-baseline justify-between gap-2 rounded-xl bg-slate-50 px-3 py-2 text-[12px]">
                <span className="font-bold">Sürüm {r.surum}</span>
                <span className="min-w-0 flex-1 truncate text-canvas-muted">{r.gerekce || '—'}</span>
                <span className="text-canvas-muted">
                  {r.hazirlayan}
                  {r.onaylayan ? ` → ${r.onaylayan} ${fmtDay(r.onayZamani)}` : ''}
                </span>
                <Pill tone={STATE_TONE[r.durum]}>{r.durumAd}</Pill>
              </li>
            ))}
          </ul>
        )}
      </Block>
    </div>
  );
}

function RuleView({ rule, meta }: { rule: Rule; meta: DealersMeta }) {
  const e = rule.esikler;
  return (
    <Block title={`Yürürlükteki kural · sürüm ${rule.surum}`} help={rule.gerekce ?? undefined}>
      <div className="grid gap-3 lg:grid-cols-2">
        <div>
          <div className={labelCls}>Bileşen ağırlıkları (toplam 100)</div>
          <ul className="mt-1 flex flex-col gap-1">
            {meta.components.map((c) => (
              <li key={c.key} className="rounded-xl bg-slate-50 px-2.5 py-1.5 text-[12px]">
                <div className="flex items-baseline justify-between gap-2">
                  <span className="font-bold">{c.label}</span>
                  <span className="font-mono font-extrabold tabular-nums">{rule.agirliklar[c.key]}</span>
                </div>
                <div className="text-[11px] leading-snug text-canvas-muted">{c.help}</div>
              </li>
            ))}
          </ul>
        </div>
        <div className="flex flex-col gap-2 text-[12px]">
          <div className={labelCls}>Segment eşikleri (skor 0–100; yüksek skor = yüksek risk)</div>
          {(['standart', 'anahtar'] as const).map((g) => (
            <div key={g} className="rounded-xl bg-slate-50 px-2.5 py-1.5">
              <span className="font-bold">{g === 'standart' ? 'Kitapçı ve bayi' : 'Anahtar hesap'}: </span>
              A &lt; {e[g].A} · B &lt; {e[g].B} · C &lt; {e[g].C} · D ≥ {e[g].C}
            </div>
          ))}
          <div className="rounded-xl bg-slate-50 px-2.5 py-1.5 leading-snug">
            İade tavanı %{Math.round(e.iadeTavan * 100)} · düzensizlik tavanı {e.duzensizlikTavan} · tahsilat süresi hedefi {e.dsoHedef} gün (+{e.dsoAralik}) ·
            limit eşiği %{Math.round(e.limitEsik * 100)} · protesto katsayısı {e.protestoKatsayi} · eğilim eşiği {e.egilimEsik} puan
          </div>
          <div className="rounded-xl bg-slate-50 px-2.5 py-1.5 leading-snug">
            Kapsam (Logo özel kod 2): {rule.kapsam.kanallar.join(', ') || '—'}
            {rule.kapsam.bosKanal ? ' + kanalı boş cariler' : ''} · anahtar hesap: {rule.kapsam.anahtarKanallar.join(', ') || '—'} ya da ciro payı ≥ %
            {Math.round(rule.kapsam.anahtarPay * 1000) / 10}
          </div>
          <div className="rounded-xl bg-slate-50 px-2.5 py-1.5 leading-snug">
            Limit önerisi: artış %{Math.round(rule.limit.artisOrani * 100)} (doluluk ≥ %{Math.round(rule.limit.artisDoluluk * 100)}), yeni limit {rule.limit.yeniLimitAy} aylık
            alım, {rule.limit.yuvarlama.toLocaleString('tr-TR')} ₺'ye yuvarlı
          </div>
        </div>
      </div>
    </Block>
  );
}

function DraftItem({ r, meta, onEdit }: { r: Rule; meta: DealersMeta; onEdit: () => void }) {
  const qc = useQueryClient();
  const [ask, setAsk] = useState<null | 'approve' | 'reject'>(null);
  const [preview, setPreview] = useState<Preview | null>(null);
  const me = meta.me.username;
  const done = (msg: string) => {
    toast.success(msg);
    setAsk(null);
    void qc.invalidateQueries({ queryKey: ['dealers'] });
  };
  const fail = (e: unknown) => toast.error(errText(e, 'İşlem yapılamadı.') ?? 'İşlem yapılamadı.');
  const submit = useMutation({ mutationFn: () => dealersApi.submitRule(r.id), onSuccess: () => done('Onaya gönderildi'), onError: fail });
  const approve = useMutation({ mutationFn: (n: string) => dealersApi.approveRule(r.id, n || undefined), onSuccess: () => done('Kural yürürlüğe girdi; yarın sabahki turda uygulanır'), onError: fail });
  const reject = useMutation({ mutationFn: (n: string) => dealersApi.rejectRule(r.id, n), onSuccess: () => done('Taslağa geri çevrildi'), onError: fail });
  const prev = useMutation({ mutationFn: () => dealersApi.previewRule(r.id), onSuccess: setPreview, onError: fail });
  const canDecide = meta.me.canRuleApprove && r.durum === 'onayda' && r.hazirlayan !== me && r.gonderen !== me;

  return (
    <li className="rounded-2xl border border-slate-100 bg-white/85 p-3">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="text-[13.5px] font-extrabold">Sürüm {r.surum}</div>
          <div className="text-[11.5px] text-canvas-muted">
            hazırlayan {r.hazirlayan} · {fmtDay(r.olusturma)}
            {r.gonderen ? ` · gönderen ${r.gonderen}` : ''}
          </div>
        </div>
        <Pill tone={STATE_TONE[r.durum]}>{r.durumAd}</Pill>
      </div>
      <p className="mt-1.5 text-[12px] leading-snug">{r.gerekce || <span className="text-canvas-muted">Gerekçe yazılmadı (onaya göndermeden önce şart).</span>}</p>
      <p className="mt-1 text-[11.5px] text-canvas-muted">
        Ağırlıklar: {meta.components.map((c) => `${c.label} ${r.agirliklar[c.key]}`).join(' · ')}
      </p>
      {r.kararNotu && <p className="mt-1 text-[11.5px]">Karar notu: {r.kararNotu}</p>}
      <div className="mt-2 flex flex-wrap justify-end gap-2">
        <button type="button" className={btnGhost} disabled={prev.isPending} onClick={() => prev.mutate()}>
          {prev.isPending ? 'Hesaplanıyor…' : 'Önizleme'}
        </button>
        {r.durum === 'taslak' && r.hazirlayan === me && (
          <>
            <button type="button" className={btnGhost} onClick={onEdit}>
              Düzenle
            </button>
            <button type="button" className={btnPrimary} disabled={submit.isPending} onClick={() => submit.mutate()}>
              Onaya gönder
            </button>
          </>
        )}
        {canDecide && (
          <>
            <button type="button" className={btnGhost} onClick={() => setAsk('reject')}>
              Geri çevir
            </button>
            <button type="button" className={btnPrimary} onClick={() => setAsk('approve')}>
              Onayla
            </button>
          </>
        )}
      </div>
      {preview && <PreviewView p={preview} />}
      <AskSheet
        open={ask !== null}
        title={ask === 'approve' ? `Sürüm ${r.surum}'i yürürlüğe al` : `Sürüm ${r.surum}'i geri çevir`}
        message={ask === 'approve' ? 'Yürürlükteki sürüm arşive iner; yeni kural sonraki günlük turdan itibaren bütün bayilere uygulanır.' : 'Taslak hazırlayana geri döner.'}
        confirm={ask === 'approve' ? 'Yürürlüğe al' : 'Geri çevir'}
        danger={ask === 'reject'}
        input={ask === 'approve' ? 'Not (isteğe bağlı)' : 'Neden'}
        required={ask === 'reject'}
        busy={approve.isPending || reject.isPending}
        onClose={() => setAsk(null)}
        onConfirm={(t) => (ask === 'approve' ? approve.mutate(t) : reject.mutate(t))}
      />
    </li>
  );
}

function PreviewView({ p }: { p: Preview }) {
  const [all, setAll] = useState(false);
  const rows = all ? p.degisen : p.degisen.slice(0, 10);
  return (
    <div className="mt-3 flex flex-col gap-2 rounded-xl bg-slate-50 p-3">
      <div className="grid gap-3 sm:grid-cols-2">
        <div>
          <div className="mb-1 text-[12px] font-extrabold">Bugünkü kural ({distTotal(p.mevcut)} cari)</div>
          <DistBar dist={p.mevcut} group="standart" />
        </div>
        <div>
          <div className="mb-1 text-[12px] font-extrabold">Taslak ({distTotal(p.taslak)} cari)</div>
          <DistBar dist={p.taslak} before={p.mevcut} group="standart" />
        </div>
      </div>
      <p className="text-[11.5px] text-canvas-muted">
        Anahtar hesap: bugün {SEGMENTS.map((s) => `${s} ${p.mevcut.anahtar[s]}`).join(', ')} → taslak {SEGMENTS.map((s) => `${s} ${p.taslak.anahtar[s]}`).join(', ')}.
        {p.kapsamDisi ? ` Taslakta kapsam dışı kalan: ${p.kapsamDisi} cari.` : ''} {p.not}
      </p>
      <div className="text-[12px] font-extrabold">Segmenti değişen: {p.degisen.length}</div>
      {rows.length > 0 && (
        <ul className="flex flex-col gap-1">
          {rows.map((x) => (
            <li key={x.code} className="flex items-baseline justify-between gap-2 text-[12px]">
              <span className="min-w-0 truncate">{x.unvan || x.code}</span>
              <span className="shrink-0 font-mono font-bold tabular-nums">
                {x.eski ?? '—'} → {x.yeni}
              </span>
            </li>
          ))}
        </ul>
      )}
      {p.degisen.length > 10 && (
        <button type="button" className={btnGhost} onClick={() => setAll(!all)}>
          {all ? 'İlk 10' : `Hepsini göster (${p.degisen.length})`}
        </button>
      )}
    </div>
  );
}

type Form = RuleBody & { gerekce: string; kanallarText: string; anahtarText: string };

function toForm(r: Rule): Form {
  return {
    agirliklar: { ...r.agirliklar },
    esikler: { ...r.esikler, standart: { ...r.esikler.standart }, anahtar: { ...r.esikler.anahtar } },
    kapsam: { ...r.kapsam },
    limit: { ...r.limit },
    gerekce: '',
    kanallarText: r.kapsam.kanallar.join(', '),
    anahtarText: r.kapsam.anahtarKanallar.join(', '),
  };
}

function RuleEditor({ meta, base, existing, onClose }: { meta: DealersMeta; base: Rule; existing: Rule | null; onClose: () => void }) {
  const qc = useQueryClient();
  const [f, setF] = useState<Form>(() => ({ ...toForm(base), gerekce: existing?.gerekce ?? '' }));
  const sum = weightSum(f.agirliklar);
  const okT = thresholdsOk(f.esikler.standart) && thresholdsOk(f.esikler.anahtar);
  const body = () => ({
    agirliklar: f.agirliklar,
    esikler: f.esikler,
    kapsam: { ...f.kapsam, kanallar: split(f.kanallarText), anahtarKanallar: split(f.anahtarText) },
    limit: f.limit,
    gerekce: f.gerekce,
  });
  const save = useMutation({
    mutationFn: () => (existing ? dealersApi.editRule(existing.id, body()) : dealersApi.createRule(body())),
    onSuccess: (r) => {
      toast.success(`Sürüm ${r.surum} taslağı kaydedildi; önizleyip onaya gönderin.`);
      void qc.invalidateQueries({ queryKey: ['dealers'] });
      onClose();
    },
    onError: (e) => toast.error(errText(e, 'Taslak kaydedilemedi.') ?? 'Taslak kaydedilemedi.'),
  });
  const setW = (k: ComponentKey, v: number) => setF({ ...f, agirliklar: { ...f.agirliklar, [k]: v } });
  const setE = <K extends keyof Form['esikler']>(k: K, v: Form['esikler'][K]) => setF({ ...f, esikler: { ...f.esikler, [k]: v } });
  const setT = (g: 'standart' | 'anahtar', s: 'A' | 'B' | 'C', v: number) => setE(g, { ...f.esikler[g], [s]: v });
  const setL = <K extends keyof Form['limit']>(k: K, v: number) => setF({ ...f, limit: { ...f.limit, [k]: v } });

  return (
    <Block title={existing ? `Sürüm ${existing.surum} taslağını düzenle` : 'Yeni sürüm taslağı'} help="Değerler yürürlükteki kuraldan başlar. Kaydettikten sonra önizleme ile segment dağılımının nasıl değiştiğini görün.">
      <div className="flex flex-col gap-3">
        <fieldset className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6">
          <legend className={`${labelCls} mb-1`}>
            Ağırlıklar · toplam <span className={sum === 100 ? 'text-emerald-700' : 'text-red-700'}>{sum}</span> / 100
          </legend>
          {meta.components.map((c) => (
            <Num key={c.key} label={c.label} value={f.agirliklar[c.key]} step={1} onChange={(v) => setW(c.key, v)} />
          ))}
        </fieldset>
        <fieldset className="grid grid-cols-3 gap-2 sm:grid-cols-6">
          <legend className={`${labelCls} mb-1`}>Segment eşikleri {okT ? '' : '· A < B < C olmalı'}</legend>
          {(['standart', 'anahtar'] as const).flatMap((g) =>
            (['A', 'B', 'C'] as const).map((s) => (
              <Num key={g + s} label={`${g === 'standart' ? 'Bayi' : 'Anahtar'} ${s} <`} value={f.esikler[g][s]} step={1} onChange={(v) => setT(g, s, v)} />
            )),
          )}
        </fieldset>
        <fieldset className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          <legend className={`${labelCls} mb-1`}>Bileşen ölçekleri</legend>
          <Num label="İade tavanı (oran)" value={f.esikler.iadeTavan} step={0.05} onChange={(v) => setE('iadeTavan', v)} />
          <Num label="Düzensizlik tavanı" value={f.esikler.duzensizlikTavan} step={0.1} onChange={(v) => setE('duzensizlikTavan', v)} />
          <Num label="Tahsilat hedefi (gün)" value={f.esikler.dsoHedef} step={5} onChange={(v) => setE('dsoHedef', v)} />
          <Num label="Tahsilat aralığı (gün)" value={f.esikler.dsoAralik} step={5} onChange={(v) => setE('dsoAralik', v)} />
          <Num label="Limit eşiği (oran)" value={f.esikler.limitEsik} step={0.05} onChange={(v) => setE('limitEsik', v)} />
          <Num label="Protesto katsayısı" value={f.esikler.protestoKatsayi} step={0.1} onChange={(v) => setE('protestoKatsayi', v)} />
          <Num label="Eğilim eşiği (puan)" value={f.esikler.egilimEsik} step={1} onChange={(v) => setE('egilimEsik', v)} />
        </fieldset>
        <fieldset className="grid gap-2 sm:grid-cols-2">
          <legend className={`${labelCls} mb-1`}>Kapsam (Logo özel kod 2)</legend>
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Kanallar (virgülle)</span>
            <input className={field} value={f.kanallarText} onChange={(e) => setF({ ...f, kanallarText: e.target.value })} />
          </label>
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Anahtar hesap kanalları</span>
            <input className={field} value={f.anahtarText} onChange={(e) => setF({ ...f, anahtarText: e.target.value })} />
          </label>
          <Num label="Anahtar hesap ciro payı (oran)" value={f.kapsam.anahtarPay} step={0.005} onChange={(v) => setF({ ...f, kapsam: { ...f.kapsam, anahtarPay: v } })} />
          <label className="inline-flex min-h-11 items-center gap-2 text-[12.5px] font-bold">
            <input type="checkbox" className="h-4 w-4" checked={f.kapsam.bosKanal} onChange={(e) => setF({ ...f, kapsam: { ...f.kapsam, bosKanal: e.target.checked } })} />
            Kanalı boş carileri de kapsa
          </label>
        </fieldset>
        <fieldset className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          <legend className={`${labelCls} mb-1`}>Limit önerisi</legend>
          <Num label="Artış oranı" value={f.limit.artisOrani} step={0.05} onChange={(v) => setL('artisOrani', v)} />
          <Num label="Artış için doluluk" value={f.limit.artisDoluluk} step={0.05} onChange={(v) => setL('artisDoluluk', v)} />
          <Num label="Yeni limit (ay alım)" value={f.limit.yeniLimitAy} step={0.5} onChange={(v) => setL('yeniLimitAy', v)} />
          <Num label="Yuvarlama (₺)" value={f.limit.yuvarlama} step={100} onChange={(v) => setL('yuvarlama', v)} />
        </fieldset>
        <label className="flex flex-col gap-1">
          <span className={labelCls}>Gerekçe (onaya göndermek için şart)</span>
          <textarea className={`${field} min-h-[72px]`} value={f.gerekce} onChange={(e) => setF({ ...f, gerekce: e.target.value })} />
        </label>
        <div className="flex flex-wrap justify-end gap-2">
          <button type="button" className={btnGhost} onClick={onClose}>
            Vazgeç
          </button>
          <button type="button" className={btnPrimary} disabled={sum !== 100 || !okT || save.isPending} onClick={() => save.mutate()}>
            Taslağı kaydet
          </button>
        </div>
      </div>
    </Block>
  );
}

function Num({ label, value, step, onChange }: { label: string; value: number; step: number; onChange: (v: number) => void }) {
  return (
    <label className="flex min-w-0 flex-col gap-1">
      <span className={`${labelCls} truncate`} title={label}>
        {label}
      </span>
      <input
        className={`${field} font-mono tabular-nums`}
        type="number"
        inputMode="decimal"
        step={step}
        value={Number.isFinite(value) ? value : ''}
        onChange={(e) => onChange(e.target.value === '' ? Number.NaN : Number(e.target.value))}
      />
    </label>
  );
}

const split = (s: string) =>
  s
    .split(',')
    .map((x) => x.trim().toUpperCase())
    .filter(Boolean);
