import React, { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import "./style.css";
import { UploadBook } from "./UploadBook";
import { AccessPanel } from "./AccessPanel";

type Row = { id: string; record_key: string; data: Record<string, any> };
type Work = { id: string; title: string };
type Run = {
  id: string;
  generation_id: string;
  status: string;
  created_at: string;
  edition_label: string;
};
type Job = {
  status: string;
  progress: Record<string, any>;
  error_code: string | null;
  counts: { kind: string; count: number }[];
  source_coverage: {
    expected_pages: number;
    accounted_pages: number;
    visual_read_pages: number;
    ocr_processed_pages?: number;
    checked_pages?: number;
  };
  editorial_status: string;
};
const statuses: Record<string, string> = {
  RUNNING: "İşleniyor",
  QUEUED: "Sırada",
  COMPLETED: "İşleme tamamlandı",
  FAILED: "İşlem hatası",
  CANCELLED: "İptal edildi",
  PENDING: "İnceleme bekliyor",
  NEEDS_REVIEW: "İnceleme gerekiyor",
  TEXT_AGREED: "Metin okumaları uyuşuyor",
  NO_TEXT_DETECTED: "Metin saptanmadı; görsel inceleme bekliyor",
  ACCEPTED: "Editör kabulü var",
};
const modes: Record<string, string> = {
  ACTUAL: "Gerçekleşmiş",
  REPORTED: "Aktarılan",
  PLANNED: "Plan",
  HYPOTHETICAL: "Hayal / varsayım",
  DREAM: "Rüya",
  JOKE: "Şaka",
  METAPHOR: "Benzetme",
};
const entityTypes: Record<string, string> = {
  CHARACTER: "Karakter",
  AUTHOR: "Eser katkıcısı",
  OBJECT: "Nesne",
  PLACE: "Mekân",
};
const stages: Record<string, string> = {
  evidence: "Kaynak hazırlama",
  visuals: "Görsel okuma",
  scenes: "Sahne çıkarımı",
  event_merges: "Olay birleştirme",
  validation: "Kaynak desteği",
  book_synthesis: "Kitap sentezi",
  literary: "Edebî yorum",
  passages: "Arama indeksi",
  complete: "İşleme tamamlandı",
  source_spans: "Konumlu metin okuma",
  region_rereads: "Metin bölgeleri yeniden okunuyor",
  layout_regions: "Sayfa yerleşimi",
  page_readings: "Sayfa OCR kontrolü",
  visual_observations: "Bölgesel görsel gözlem",
  page_claims: "Metne bağlı iddia adayları",
  character_evidence: "Kaynaklı konuşma atıfları",
  page_checks: "Sayfa kabul kontrolü",
  source_fragments: "Küçük metin bölgeleri okunuyor",
  fragment_checks: "Küçük bölge okumaları denetleniyor",
  page_context_roles: "Sayfaların amacı kaynaklardan denetleniyor",
  cross_page_attributions: "Sayfalar arası konuşma bağlantıları denetleniyor",
  figure_comparisons: "Figürler karşılaştırılıyor",
  figure_identity: "Figür ve konuşmacı kanıtları denetleniyor",
  semantic_reviews: "İddiaların anlam ve kaynak desteği denetleniyor",
  semantic_synthesis: "Kaynaklı analiz taslağı hazırlanıyor",
  source_analysis: "Kaynak ve analiz denetimi tamamlandı",
};
const answerStatuses: Record<string, string> = {
  ANSWERED: "Kaynaklı cevap adayı",
  PARTIAL: "Kısmi cevap",
  INSUFFICIENT_EVIDENCE: "Yeterli kaynak bulunamadı",
  NEEDS_CLARIFICATION: "Açıklığa kavuşturulmalı",
};

function App() {
  const [identity, setIdentity] = useState<any>(null);
  const [token, setToken] = useState(""),
    [signed, setSigned] = useState(false),
    [error, setError] = useState("");
  const [works, setWorks] = useState<Work[]>([]),
    [work, setWork] = useState(""),
    [runs, setRuns] = useState<Run[]>([]),
    [run, setRun] = useState("");
  const [job, setJob] = useState<Job | null>(null),
    [tab, setTab] = useState("source"),
    [page, setPage] = useState(1),
    [image, setImage] = useState(""),
    [imageFor, setImageFor] = useState("");
  const [data, setData] = useState<Record<string, Row[]>>({}),
    [questions, setQuestions] = useState<any[]>([]),
    [updated, setUpdated] = useState("");
  const [pageSpans, setPageSpans] = useState<Row[]>([]);
  const [pageSourcesLoading, setPageSourcesLoading] = useState(false);
  const [sourceReview, setSourceReview] = useState<any>(null);
  const [selectedSpan, setSelectedSpan] = useState<string | null>(null);
  const [sourceText, setSourceText] = useState("ocr"),
    [busy, setBusy] = useState(false);
  const selected = runs.find((r) => r.id === run),
    gen = selected?.generation_id;
  async function api(path: string) {
    const r = await fetch("/v1" + path, {
      headers: { Authorization: "Bearer " + token },
      cache: "no-store",
    });
    if (!r.ok)
      throw new Error(
        r.status === 401
          ? "Oturum doğrulanamadı. Erişim anahtarını kontrol edin."
          : `Veri alınamadı (${r.status}). Son gösterilen kayıtlar korunuyor.`,
      );
    return r.json();
  }
  async function all(path: string) {
    let result: any[] = [];
    for (let offset = 0; ; ) {
      const p = await api(
        path + (path.includes("?") ? "&" : "?") + `offset=${offset}&limit=100`,
      );
      result.push(...p.items);
      if (!p.has_more) return result;
      offset += p.items.length;
      if (!p.items.length) throw new Error("Sayfalama ilerlemedi.");
    }
  }
  async function signIn(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const who = await api('/me');
      const rows = await all("/works");
      setIdentity(who);
      setWorks(rows);
      setWork(rows[0]?.id ?? "");
      setSigned(true);
    } catch (e) {
      setError(String((e as Error).message));
    } finally {
      setBusy(false);
    }
  }
  useEffect(() => {
    if (!signed || !work) return;
    let active = true;
    setRuns([]);
    setRun("");
    setJob(null);
    setData({});
    all(`/works/${work}/analyses`)
      .then((rows) => {
        if (active) {
          setRuns(rows);
          setRun(rows[0]?.id ?? "");
        }
      })
      .catch((e) => active && setError(e.message));
    return () => {
      active = false;
    };
  }, [signed, work]);
  useEffect(() => {
    if (!run || !gen) return;
    let active = true,
      inflight = false,
      lastCounts = "";
    setJob(null);
    setData({});
    setPage(1);
    setQuestions([]);
    setError("");
    async function refresh() {
      if (inflight) return;
      inflight = true;
      try {
        const j = await api("/jobs/" + run);
        if (!active) return;
        setJob(j);
        setRuns((previous) => previous.map((r) => r.id === run ? { ...r, status: j.status } : r));
        setUpdated(new Date().toLocaleTimeString("tr-TR"));
        const signature = JSON.stringify(j.counts);
        if (signature !== lastCounts) {
          const kinds = [
            "evidence",
            "visuals",
            "scenes",
            "entities",
            "events",
            "literary",
            "validation",
            "page_readings", "visual_observations", "page_claims", "page_checks", "character_evidence", "figure_identity", "semantic_reviews", "semantic_synthesis", "source_fragments", "fragment_checks", "page_context_roles", "cross_page_attributions",
          ];
          const entries = await Promise.all(
            kinds.map(async (k) => [k, await all(`/generations/${gen}/${k}`)]),
          );
          if (active) {
            setData(Object.fromEntries(entries));
            lastCounts = signature;
          }
        }
        const q = await all("/question-jobs?generation_id=" + gen);
        if (active) {
          setQuestions(q);
          setError("");
        }
      } catch (e) {
        if (active) setError((e as Error).message);
      } finally {
        inflight = false;
      }
    }
    refresh();
    const timer = setInterval(refresh, 10000);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, [run, gen]);
  const evidence = data.evidence ?? [],
    visuals = data.visuals ?? [],
    source = evidence.find((r) => r.data.pdf_page === page),
    visual = visuals.find((r) => r.data.pdf_page === page);
  const pageReading = data.page_readings?.find((r) => r.data.pdf_page === page);
  const pageObservation = data.visual_observations?.find((r) => r.data.pdf_page === page);
  const pageClaims = data.page_claims?.find((r) => r.data.pdf_page === page);
  const pageCharacters = data.character_evidence?.find((r) => r.data.pdf_page === page);
  const pageFragments = (data.source_fragments ?? []).filter((r) => r.data.pdf_page === page);
  const fragmentCheck = data.fragment_checks?.find((r) => r.data.pdf_page === page);
  const pageContext = data.page_context_roles?.find((r) => r.data.pdf_page === page);
  const pageIdentity = data.figure_identity?.find((r) => r.data.pdf_page === page);
  const pageSemantic = data.semantic_reviews?.find((r) => r.data.pdf_page === page);
  const pageCandidates = [...(pageClaims?.data.claims ?? []), ...(pageClaims?.data.blocked_claims ?? [])];
  const namedMentions = Array.from((data.character_evidence ?? []).reduce((map, row) => {
    for (const mention of row.data.named_mentions ?? []) {
      const item = map.get(mention.label_key) ?? { label: mention.label, pages: [] as number[] };
      if (!item.pages.includes(row.data.pdf_page)) item.pages.push(row.data.pdf_page);
      map.set(mention.label_key, item);
    }
    return map;
  }, new Map<string, { label: string; pages: number[] }>()).entries());
  useEffect(() => {
    let active = true; setPageSpans([]); setSelectedSpan(null); setSourceReview(null);
    setPageSourcesLoading(Boolean(gen && signed));
    if (gen && signed) Promise.all([
      all(`/generations/${gen}/source_spans?pdf_page=${page}`),
      api(`/generations/${gen}/source-review?pdf_page=${page}`),
    ])
      .then(([rows, review]) => { if (active) { setPageSpans(rows); setSourceReview(review.pages[0] ?? null); setPageSourcesLoading(false); } })
      .catch((e) => { if (active) { setError(e.message); setPageSourcesLoading(false); } });
    return () => { active = false; };
  }, [gen, page, signed, pageReading?.id]);
  const sourceImage = imageFor === source?.id ? image : "";
  const highlighted = [...pageSpans, ...pageFragments].find((r) => r.id === selectedSpan);
  useEffect(() => {
    setImage("");
    if (!source) return;
    let active = true,
      url = "";
    const controller = new AbortController();
    fetch("/v1/visuals/" + source.id, {
      headers: { Authorization: "Bearer " + token },
      signal: controller.signal,
      cache: "no-store",
    })
      .then((r) => {
        if (!r.ok) throw new Error("Kaynak görüntüsü alınamadı.");
        return r.blob();
      })
      .then((blob) => {
        if (active) {
          url = URL.createObjectURL(blob);
          setImageFor(source.id);
          setImage(url);
        }
      })
      .catch((e) => {
        if (active && e.name !== "AbortError") setError(e.message);
      });
    return () => {
      active = false;
      controller.abort();
      if (url) URL.revokeObjectURL(url);
    };
  }, [source?.id]);
  const pageById = Object.fromEntries(
    evidence.map((r) => [r.id, r.data.pdf_page]),
  );
  function refs(ids: string[] = []) {
    return (
      <div className="refs">
        {[...new Set(ids.map((id) => pageById[id]).filter(Boolean))]
          .sort((a, b) => a - b)
          .map((n) => (
            <button
              key={n}
              onClick={() => {
                setPage(n);
                setTab("source");
              }}
            >
              PDF {n} ↗
            </button>
          ))}
      </div>
    );
  }
  const count = (kind: string) =>
    job?.counts.find((c) => c.kind === kind)?.count ?? 0;
  function logout() {
    setSigned(false);
    setToken("");
    setWorks([]);
    setWork("");
    setRuns([]);
    setRun("");
    setJob(null);
    setData({});
    setQuestions([]);
    setImage("");
    setError("");
  }
  if (!signed)
    return (
      <main className="login">
        <div className="brand">
          e<span>ditör</span>
          <i>Kaynaklı kitap inceleme</i>
        </div>
        <section className="login-card">
          <p className="eyebrow">ÇALIŞMA ALANINA GİRİŞ</p>
          <h1>
            Kitabı kaynağıyla
            <br />
            birlikte inceleyin.
          </h1>
          <p>
            İşleme durumunu, özgün sayfaları ve sistemin ürettiği analiz
            adaylarını aynı yerde görün.
          </p>
          <form onSubmit={signIn}>
            <label htmlFor="access">Erişim anahtarı</label>
            <input
              id="access"
              type="password"
              autoComplete="off"
              required
              value={token}
              onChange={(e) => setToken(e.target.value)}
            />
            <button className="primary" disabled={busy}>
              {busy ? "Bağlanıyor…" : "Çalışma alanını aç →"}
            </button>
          </form>
          <p className="hint">
            Anahtar, kullanıcı ve kitap yetkilerinizle çalışır. Yalnız açık oturumun
            belleğinde tutulur.
          </p>
          {error && (
            <p role="alert" className="error">
              {error}
            </p>
          )}
        </section>
      </main>
    );
  return (
    <div className="app">
      <header className="topbar">
        <a className="brand" href="/editor/">
          e<span>ditör</span>
        </a>
        <span className="top-note">Kaynağı gör. Bulguyu değerlendir.</span>
        <button onClick={logout}>Çıkış</button>
      </header>
      <main className="workspace">
        {identity?.can_manage_access && <AccessPanel token={token} works={works} />}
        {identity?.can_create_work && <UploadBook token={token} onStarted={async id => {
          const rows = await all('/works'); setWorks(rows); setWork(id);
          const analyses = await all(`/works/${id}/analyses`); setRuns(analyses); setRun(analyses[0]?.id ?? '');
        }} />}
        <section className="heading">
          <div>
            <p className="eyebrow">KİTAP İNCELEME</p>
            <h1>
              {works.find((w) => w.id === work)?.title ?? "Çalışma alanı"}
            </h1>
            <p className="sub">Özgün kaynaklar ve sistemin gerçek çıktıları</p>
          </div>
          <div className="selectors">
            <label>
              Kitap
              <select value={work} onChange={(e) => setWork(e.target.value)}>
                {works.map((w) => (
                  <option key={w.id} value={w.id}>
                    {w.title}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Analiz sürümü
              <select value={run} onChange={(e) => setRun(e.target.value)}>
                {runs.map((r, i) => (
                  <option key={r.id} value={r.id}>
                    {i === 0 ? "Son koşu · " : ""}
                    {new Date(r.created_at).toLocaleString("tr-TR")} ·{" "}
                    {statuses[r.status] ?? r.status}
                  </option>
                ))}
              </select>
            </label>
          </div>
        </section>
        {error && (
          <div className="error" role="alert">
            {error}
          </div>
        )}
        {!works.length ? (
          <div className="empty">Henüz kitap kaydı yok.</div>
        ) : !runs.length ? (
          <div className="empty">Bu kitap için analiz kaydı bulunamadı.</div>
        ) : (
          <>
            <section className="stats" aria-label="Üç ayrı kabul durumu">
              <article>
                <span>İŞLEME</span>
                <strong>{statuses[job?.status ?? ""] ?? "Bağlanıyor…"}</strong>
                <small>
                  {job?.error_code
                    ? job.error_code === "PIPELINE_VERSION_CHANGED_NEW_GENERATION_REQUIRED"
                      ? "Yeni sürümle yeni bir analiz gerekiyor. Önceki sonuçlar korundu."
                      : "İşleme tamamlanamadı. Kaydedilen sonuçlar korundu."
                    : "Son kaydedilen aşama: " +
                      (stages[job?.progress.stage] ?? "Hazırlanıyor")}
                </small>
                {job?.error_code && <details><summary>Hata ayrıntısı</summary><code>{job.error_code}</code></details>}
              </article>
              <article>
                <span>KAYNAK DOSYALARI</span>
                <strong>
                  {job?.source_coverage.accounted_pages ?? 0} /{" "}
                  {job?.source_coverage.expected_pages ?? "—"} sayfa
                </strong>
                <small>
                  {job?.source_coverage.ocr_processed_pages ?? 0} sayfa OCR kontrol kaydı · {" "}
                  {job?.source_coverage.visual_read_pages ?? 0} görsel okuma
                  kaydı · doğruluk oranı değildir
                </small>
              </article>
              <article>
                <span>EDİTÖR İNCELEMESİ</span>
                <strong>
                  {statuses[job?.editorial_status ?? ""] ?? "Bekliyor"}
                </strong>
                <small>İşlemenin bitmesi editör kabulü anlamına gelmez</small>
              </article>
            </section>
            <div className="activity">
              <span
                className={"dot " + (job?.status === "RUNNING" ? "live" : "")}
              />
              <span>
                {count("page_readings")} sayfa OCR kontrolü · {count("page_checks")} sayfa inceleme kaydı · {count("scenes")} sahne grubu · {count("events")} olay ·{" "}
                {count("entities")} varlık
              </span>
              <small>Son güncelleme {updated || "—"}</small>
            </div>
            <nav className="tabs" aria-label="İnceleme alanları">
              {[
                ["source", "Kaynak & görsel"],
                ["scenes", "Sahneler"],
                ["entities", "Karakter & varlık"],
                ["events", "Olaylar"],
                ["literary", "Kitap yorumu"],
                ["questions", "Soru & cevap"],
              ].map(([key, title]) => (
                <button
                  key={key}
                  aria-current={tab === key ? "page" : undefined}
                  onClick={() => setTab(key)}
                >
                  {title}
                </button>
              ))}
            </nav>
            {tab === "source" && (
              <section className="source-layout">
                <article className="paper">
                  <div className="section-head">
                    <div>
                      <p className="eyebrow">ÖZGÜN KAYNAK</p>
                      <h2>PDF sayfası {page}</h2>
                    </div>
                    <div className="page-control">
                      <button
                        aria-label="Önceki sayfa"
                        disabled={page <= 1}
                        onClick={() => setPage(page - 1)}
                      >
                        ←
                      </button>
                      <label className="sr-only" htmlFor="page">
                        PDF sayfası
                      </label>
                      <select
                        id="page"
                        value={page}
                        onChange={(e) => setPage(Number(e.target.value))}
                      >
                        {evidence.map((r) => (
                          <option key={r.id} value={r.data.pdf_page}>
                            {r.data.pdf_page} / {evidence.length}
                          </option>
                        ))}
                      </select>
                      <button
                        aria-label="Sonraki sayfa"
                        disabled={page >= evidence.length}
                        onClick={() => setPage(page + 1)}
                      >
                        →
                      </button>
                    </div>
                  </div>
                  {sourceImage ? (
                    <>
                      <a
                        className="source-frame"
                        id="source-frame"
                        href={sourceImage}
                        target="_blank"
                        rel="noreferrer"
                        aria-label={`PDF ${page} özgün görüntüsünü büyüt`}
                      >
                        <img
                          className="source-image"
                          src={sourceImage}
                          alt={`Kitabın özgün PDF ${page}. sayfası`}
                        />
                        {highlighted && <span className="source-highlight" aria-hidden="true"
                          style={{left: `${highlighted.data.bbox[0]*100}%`, top: `${highlighted.data.bbox[1]*100}%`,
                            width: `${highlighted.data.bbox[2]*100}%`, height: `${highlighted.data.bbox[3]*100}%`}} />}
                      </a>
                      {highlighted && <p className="hint" role="status">Seçili metin bölgesi kaynak üzerinde işaretlendi. Okuma adayı: {highlighted.data.text}</p>}
                      <p className="hint">
                        Görüntüye dokunarak özgün boyutta açın. PDF sırası,
                        basılı sayfa etiketiyle aynı olmayabilir.
                      </p>
                    </>
                  ) : (
                    <div className="empty">Kaynak görüntüsü hazırlanıyor…</div>
                  )}
                </article>
                <aside className="source-notes">
                  {pageReading && <article className="paper">
                    <p className="eyebrow">SAYFA OKUMA KONTROLÜ</p>
                    <h2>{statuses[pageReading.data.status] ?? "İnceleme bekliyor"}</h2>
                    <p>{pageReading.data.agreed_spans} uyumlu bölge · {pageReading.data.review_spans} inceleme gereken bölge</p>
                    <p className="hint">Okumaların uyuşması, olayın veya konuşmacının doğrulandığı anlamına gelmez.</p>
                    {pageReading.data.measurement_reused && <p className="hint">Kaynak ölçümleri önceki koşudan alındı; bu sürümde yeniden karşılaştırıldı.</p>}
                    {pageSpans.map((r) => {
                      const review = sourceReview?.regions.find((region: any) => region.span_id === r.id);
                      return <details key={r.id} data-span-id={r.id}>
                      <summary>{r.data.status === "TEXT_AGREED" ? "✓" : "⚠"} {r.data.text}</summary>
                      <button className="show-region" aria-pressed={selectedSpan === r.id} onClick={() => {
                        setSelectedSpan(r.id);
                        document.getElementById("source-frame")?.scrollIntoView({block: "center", behavior: "smooth"});
                      }}>Kaynakta göster</button>
                      {r.data.selected_reader === "REGIONAL_OCR" && <div data-testid="regional-source-selection">
                        <p>Kaynak metin, diğer okumalarla uyuşan bölgesel okumadan alındı.</p>
                        <p>İlk tam sayfa okuması: {r.data.raw_text}</p>
                        <p className="hint">İlk okuma korunur; bu uyuşma olay veya karakter doğrulaması değildir.</p>
                      </div>}
                      {r.data.selected_reader === "PADDLEOCR_VL" && <div data-testid="ocr-vl-source-selection">
                        <p>Kaynak metin, diğer okumalarla uyuşan ek bölgesel OCR okumadan alındı.</p>
                        <p data-testid="ocr-vl-selected-text">Seçilen metin: {r.data.text}</p>
                        <p data-testid="ocr-vl-original-text">İlk tam sayfa okuması: {r.data.raw_text}</p>
                        <p data-testid="ocr-vl-reader">Okuyucu: {r.data.ocr_vl_measurement?.model || "PaddleOCR-VL"}</p>
                        <p>Uyuşan kaynaklar: {(r.data.ocr_vl_selection?.supporting_readers || []).map((reader: string) =>
                          (({NATIVE_PDF: "PDF metni", TESSERACT_CROP: "Tesseract bölgesel yeniden okuma", PPOCR_REGION: "PaddleOCR bölgesel okuma"} as Record<string, string>)[reader] || reader)
                        ).join(", ") || "Kaynak ayrıntısı kaydedilmedi"}</p>
                        <p className="hint">İlk okuma korunur; bu uyuşma olay, konuşmacı veya karakter kimliği doğrulaması değildir.</p>
                      </div>}
                      <p>İkinci okuma: {r.data.secondary_text || "Metin bulunamadı"}</p>
                      <p>Bölgesel okuma: {r.data.region_text || "Bekliyor"}</p>
                      <p>PDF metni: {r.data.pdf_usable ? r.data.pdf_text : "Kullanılamıyor; metin kanıtı sayılmadı"}</p>
                      {r.data.reread_measurement?.readings.map((reading: any) => <p key={reading.psm}>
                        Yeniden okuma ({reading.psm}): {reading.text || "Metin bulunamadı"}
                      </p>)}
                      {r.data.reread_measurement && <p className="hint">Yeniden okumalar aynı OCR motorunun iki yöntemidir; ayrı editör onayı değildir.</p>}
                      {review?.reading_class === "SYMBOLS_ONLY" && <p className="hint">Sembol adayı; inceleme bekliyor.</p>}
                      {review?.ocr_vl && r.data.selected_reader !== "PADDLEOCR_VL" && <div className="ocr-fallback">
                        <p>Ek bölgesel OCR: {review.ocr_vl.text || "Metin bulunamadı"}</p>
                        <p className="hint">{!review.ocr_vl.complete ? "Tamamlanmayan çıktı; kaynak olarak kullanılamaz."
                          : review.ocr_vl.reading_class === "NON_LATIN_TEXT_CANDIDATE" ? "Latin dışı yazı adayı; kaynakla doğrulanmadı."
                          : "Ek okuyucu adayı; kaynak metni olarak kabul edilmedi."}</p>
                      </div>}
                      <small>{statuses[r.data.status] ?? r.data.status}</small>
                    </details>})}
                  </article>}
                  {pageClaims && <article className="paper">
                    <h2>Metne bağlı adaylar</h2>
                    <p className="hint">Henüz doğrulanmış olay değildir. Kaynaksız alıntılar ve kimliği belirsiz varlıklar incelemeye ayrılır.</p>
                    {pageClaims.data.claims.map((c: any, i: number) => <div key={i}><p>{c.text}</p>
                      {c.speaker_status === "EXPLICIT_TEXT_ATTRIBUTION" && <small>Metindeki konuşmacı: {c.speaker}</small>}
                    </div>)}
                    <p>{pageClaims.data.blocked_claims.length} bloke edilmiş aday · Görsel figürlerin kimlik eşleştirmesi bekliyor</p>
                  </article>}
                  {(pageFragments.length > 0 || fragmentCheck) && <article className="paper" data-testid="source-fragments">
                    <h2>Küçük bölge okumaları</h2>
                    <p className="hint">İlk satır okuması korunur. Küçük bölgedeki okuyucu uyumu, bütün satırın veya anlamın doğrulandığı anlamına gelmez.</p>
                    {fragmentCheck && <p>{fragmentCheck.data.agreed_fragments} uyumlu · {fragmentCheck.data.review_fragments} inceleme gereken küçük bölge</p>}
                    {pageFragments.map((fragment) => {
                      const parent = pageSpans.find((row) => row.id === fragment.data.parent_source_span_id);
                      return <details key={fragment.id} data-fragment-id={fragment.id}>
                        <summary>{fragment.data.status === "TEXT_AGREED" ? "Doğrulanan küçük bölge" : "Küçük bölge inceleme bekliyor"}</summary>
                        <p data-testid="fragment-raw-text">{fragment.data.raw_text}</p>
                        <p data-testid="fragment-reader">Okuyucu: {({PPOCR_FRAGMENT: "PaddleOCR bölgesel okuma", TESSERACT_PSM7_FRAGMENT: "Tesseract bölgesel okuma"} as Record<string, string>)[fragment.data.selected_reader] || fragment.data.selected_reader}</p>
                        <p data-testid="fragment-parent" data-source-loaded={!pageSourcesLoading}>İlk satır: {pageSourcesLoading ? "Kaynak satırı yükleniyor…" : parent ? parent.data.raw_text : "Üst kaynak kaydı bu sayfada bulunamadı"}</p>
                        <button className="show-region" onClick={() => {setSelectedSpan(fragment.id); document.getElementById("source-frame")?.scrollIntoView({block: "center", behavior: "smooth"});}}>Küçük bölgeyi kaynakta göster</button>
                        {parent && <button className="show-region" onClick={() => setSelectedSpan(parent.id)}>İlk satırı kaynakta göster</button>}
                      </details>;
                    })}
                  </article>}
                  {pageContext && <article className="paper" data-testid="page-context-role">
                    <h2>Sayfanın amacı</h2>
                    <p>{({NARRATIVE: "Öykü anlatısı", ACTIVITY: "Etkinlik", FRONT_MATTER: "Ön bilgi / künye", APPENDIX: "Ek", MIXED: "Birden fazla amaç", UNKNOWN: "Belirsiz"} as Record<string, string>)[pageContext.data.page_role] || "Belirsiz"}</p>
                    <p className="hint">Kaynak ve komşu sayfa bağlamından üretilen otomatik sınıflandırmadır; ilk sayfa kaydını değiştirmez, karakter kimliği veya editör onayı değildir.</p>
                    {source && refs([source.id])}
                  </article>}
                  {pageIdentity && <article className="paper" data-testid="figure-identity">
                    <h2>Figür ve konuşmacı eşleştirmesi</h2>
                    <p className="hint">Bu sayfadaki kaynak bağı incelenir; sayfalar arasında aynı karakter olduğu veya kitabın tamamı doğrulanmış değildir.</p>
                    {(pageIdentity.data.links ?? []).map((link: any, i: number) => <div className="claim" key={i}>
                      <b>{link.visual_identity_verified ? link.speaker : "Konuşmacı kimliği bilinmiyor"}</b>
                      <p>{link.visual_identity_verified ? "Bu sayfadaki söz ve balon yönü kimliği destekliyor; genel karakter kimliği onayı değildir." : "Figür adayı bir karakter adıyla yeterli kaynak üzerinden eşleştirilemedi."}</p>
                    </div>)}
                    {(pageIdentity.data.cross_page_dialogue_links ?? []).filter((link: any) => link.dialogue_link_verified).map((link: any, i: number) => <div className="claim" key={"dialogue-"+i} data-testid="cross-page-dialogue">
                      <b>{link.speaker || "Konuşmacı kimliği bilinmiyor"}</b>
                      <blockquote>{link.supported_quote || link.quote}</blockquote>
                      <p className="hint">Yalnız bu söz parçasının kaynaklı konuşmacı bağıdır; figürün bütün kimliği ve aynı adlı karakterlerin birliği doğrulanmış değildir.</p>
                      {refs((link.identity_evidence ?? []).map((item: any) => item.evidence_ref).filter(Boolean))}
                    </div>)}
                    {!pageIdentity.data.links?.length && <p>Bu sayfada bağlanabilecek konuşmacı kaydı bulunmadı.</p>}
                    {pageIdentity.data.unprocessed_pairs > 0 && <p>{pageIdentity.data.unprocessed_pairs} figür karşılaştırması henüz yapılmadı.</p>}
                    {source && refs([source.id])}
                  </article>}
                  {pageSemantic && <article className="paper" data-testid="semantic-review">
                    <h2>Sayfanın anlam denetimi</h2>
                    <p>{pageSemantic.data.candidate_count} adayın {pageSemantic.data.machine_supported_count} tanesinde kaynak desteği bulundu.</p>
                    <p className="hint">Otomatik denetim sonucudur; editör onayı veya kitabın tamamının anlamsal kabulü değildir.</p>
                    {(pageSemantic.data.claims ?? []).map((verdict: any, i: number) => {
                      const candidate = pageCandidates[verdict.candidate_ordinal];
                      return <div className="claim" key={verdict.claim_id || i}>
                        <span className="badge">{verdict.status === "MACHINE_SUPPORTED_CANDIDATE" ? "Kaynakla desteklenen aday" : "İnceleme gerekiyor"}</span>
                        {candidate && <p>{candidate.text}</p>}
                        {verdict.identity_gate === "IDENTITY_REVIEW_REQUIRED" && <p>İlgili kişinin kimliği henüz doğrulanmadı.</p>}
                        {candidate && refs(candidate.evidence_refs)}
                      </div>;
                    })}
                    {source && refs([source.id])}
                  </article>}
                  {pageCharacters && pageCharacters.data.attributions.length > 0 && <article className="paper" data-testid="text-attributions">
                    <h2>Metindeki konuşmacılar</h2>
                    <p className="hint">Metinde açıkça kime atfedildiği belirtilen sözler. Resimdeki figürün kimliği ayrıca doğrulanır.</p>
                    {pageCharacters.data.attributions.map((a: any, i: number) => <div className="claim" key={i}>
                      <b>{a.label}</b><blockquote>{a.quote}</blockquote>
                      <button className="show-region" onClick={() => {
                        setSelectedSpan(a.source_span_refs[0]);
                        document.getElementById("source-frame")?.scrollIntoView({ block: "center", behavior: "smooth" });
                      }}>Kaynakta göster</button>
                    </div>)}
                  </article>}
                  <article className="paper">
                    <p className="eyebrow">MODELİN GÖRSEL OKUMASI</p>
                    <h2>Gözlem adayı</h2>
                    <span className="badge">Doğrulanmamış model çıktısı</span>
                    <p className="body-copy">
                      {pageObservation ? (pageObservation.data.observations.flatMap((o: any) => o.figures.map((f: any) => `${f.appearance}: ${f.visible_action}`)).join("\n") || "Bu sayfada figür gözlemi kaydedilmedi.") : visual?.data.description ??
                        "Bu sayfanın model çıktısı henüz kaydedilmedi."}
                    </p>
                    {pageObservation && <p className="hint">Bölgesel gözlem adayıdır; alıntı veya iddia kaynağı olarak kullanılmaz. Konuşmacı: bilinmiyor.</p>}
                    {pageObservation && <p className="hint" data-testid="visual-coverage">
                      {pageObservation.data.coverage
                        ? `${pageObservation.data.coverage.declared_picture_regions} görsel bölge saptandı; ${pageObservation.data.coverage.unobserved_picture_regions} bölgenin gözlemi eksik.`
                        : "Bu koşuda görsel bölge kapsamı ölçülmedi."}
                      {" "}Sayfanın tüm görsellerinin incelendiği henüz doğrulanmadı.
                    </p>}
                    {visual && (
                      <small>
                        {visual.data.reused_from
                          ? "Önceki koşudan aynı istem sürümüyle yeniden kullanılan çıktı."
                          : "Bu koşuda üretilen çıktı."}
                      </small>
                    )}
                  </article>
                  <article className="paper">
                    <h2>Kaynak metin adayları</h2>
                    <div className="segmented">
                      <button
                        aria-pressed={sourceText === "ocr"}
                        onClick={() => setSourceText("ocr")}
                      >
                        OCR okuması
                      </button>
                      <button
                        aria-pressed={sourceText === "pdf"}
                        onClick={() => setSourceText("pdf")}
                      >
                        PDF metni
                      </button>
                    </div>
                    <p className="hint">
                      Özgün görüntü korunur; iki okuma birbiriyle uyuşmayabilir.
                    </p>
                    <pre className="source-text">
                      {source?.data[
                        sourceText === "ocr" ? "ocr_text" : "text_layer"
                      ] || "Bu adayda metin yok."}
                    </pre>
                  </article>
                </aside>
              </section>
            )}
            {tab === "scenes" && (
              <section className="cards">
                {(data.scenes ?? []).map((r) => (
                  <article className="paper" key={r.id}>
                    <p className="eyebrow">PDF {r.data.pdf_pages.join("–")}</p>
                    <h2>Sahne grubu</h2>
                    <p>{r.data.summary}</p>
                    {refs(r.data.evidence_refs)}
                    <details>
                      <summary>Sahneden çıkarılan adaylar</summary>
                      <p className="hint">
                        Bunlar bu kaynak grubunun çıktılarıdır; kitap genelinde
                        birleştirilmiş karakter ve olay kayıtları henüz farklı olabilir.
                      </p>
                      {(r.data.entities ?? []).map((item: any, i: number) => (
                        <div className="claim" key={"entity" + i}>
                          <b>{item.name}</b>
                          <p>{entityTypes[item.type] ?? item.type} · {item.description}</p>
                          {refs(item.evidence_refs)}
                        </div>
                      ))}
                      {(r.data.events ?? []).map((item: any, i: number) => (
                        <div className="claim" key={"event" + i}>
                          <span className="badge">{modes[item.narrative_mode] ?? item.narrative_mode}</span>
                          <p>{item.description}</p>
                          <small>Fail: {item.actor ?? "Belirsiz"} · Konuşmacı: {item.speaker ?? "Belirtilmemiş"}</small>
                          {refs(item.evidence_refs)}
                        </div>
                      ))}
                    </details>
                    {r.data.uncertainties?.length > 0 && (
                      <details>
                        <summary>
                          Belirsizlikler ({r.data.uncertainties.length})
                        </summary>
                        <ul>
                          {r.data.uncertainties.map((x: string, i: number) => (
                            <li key={i}>{x}</li>
                          ))}
                        </ul>
                      </details>
                    )}
                    <span className="badge">
                      Kaynak grubu adayı · editör kabulü yok
                    </span>
                  </article>
                ))}
                {!data.scenes?.length && (
                  <Empty
                    title="Sahneler hazırlanıyor"
                    text="Modelin kaydettiği sahne grupları burada görünecek."
                  />
                )}
              </section>
            )}
            {tab === "entities" && (
              <section className="cards">
                {namedMentions.map(([key, mention]) => <article className="paper" key={"mention-"+key} data-testid="named-mention">
                  <span className="badge">Metinde konuşmacı olarak geçen ad</span>
                  <h2>{mention.label}</h2>
                  <p>Görsel kimlik ve karakter özellikleri henüz doğrulanmadı.</p>
                  <div className="segmented">{mention.pages.map((p) => <button key={p} onClick={() => {
                    setPage(p); setTab("source");
                  }}>Kaynak: sayfa {p}</button>)}</div>
                </article>)}
                {(data.entities ?? []).map((r) => (
                  <article className="paper" key={r.id}>
                    <span className="badge">
                      {entityTypes[r.data.type] ?? r.data.type}
                    </span>
                    <h2>{r.data.name}</h2>
                    <p>{r.data.description}</p>
                    {refs(r.data.evidence_refs)}
                  </article>
                ))}
                {!data.entities?.length && !namedMentions.length && (
                  <Empty
                    title="Varlık kayıtları henüz oluşmadı"
                    text="Karakterler ve diğer varlıklar kitap sentezinden sonra kaydedilir."
                  />
                )}
              </section>
            )}
            {tab === "events" && (
              <section className="cards">
                {(data.events ?? []).map((r) => (
                  <article className="paper" key={r.id}>
                    <span className="badge">
                      {modes[r.data.narrative_mode] ?? r.data.narrative_mode}
                    </span>
                    <h2>{r.data.actor ?? "Fail belirsiz"}</h2>
                    <p>{r.data.description}</p>
                    {refs(r.data.evidence_refs)}
                    <small>
                      {r.data.verification_status === "SOURCE_SUPPORTED"
                        ? "Ayrı model geçişinde destek bulundu; insan onayı değil."
                        : "Kaynakla ilişkili aday; destek ve kapsam incelenmeli."}
                    </small>
                  </article>
                ))}
                {!data.events?.length && (
                  <Empty
                    title="Olay kayıtları hazırlanıyor"
                    text="Gerçekleşmiş olaylar, planlar, şakalar ve hayaller ayrı etiketlerle gösterilecek."
                  />
                )}
              </section>
            )}
            {tab === "literary" && (
              <section className="cards">
                {(data.semantic_synthesis ?? []).map((r) => <article className="paper wide" key={r.id} data-testid="semantic-synthesis">
                  <p className="eyebrow">KAYNAKLI ANALİZ TASLAĞI</p>
                  <h2>Kısmi kitap yorumu</h2>
                  <p className="hint">Kitabın tamamı henüz kabul edilmedi. Aşağıdaki ifadeler kaynakla denetlenen adaylardan üretildi; editör onayı değildir.</p>
                  {(r.data.statements ?? []).map((statement: any, i: number) => <div className="claim" key={i} data-testid="semantic-statement">
                    <span className="badge">{({SCENE: "Sahne taslağı", RELATIONSHIP: "İlişki taslağı", THEME: "Tema taslağı", SUMMARY: "Özet taslağı"} as Record<string, string>)[statement.kind] || "Yorum taslağı"}</span>
                    <p>{statement.text}</p>
                    {refs(statement.evidence_refs)}
                  </div>)}
                  {!r.data.statements?.length && <p>Kaynak denetiminden geçerek gösterilebilen yorum henüz yok.</p>}
                  {r.data.blocked_statements?.length > 0 && <p>{r.data.blocked_statements.length} yorum yeterli destek bulunmadığı için taslağa alınmadı.</p>}
                  {r.data.missing_review_pages?.length > 0 && <p>{r.data.missing_review_pages.length} sayfanın anlam denetimi eksik.</p>}
                </article>)}
                {(data.literary ?? []).map((r) => (
                  <React.Fragment key={r.id}>
                    <article className="paper wide">
                      <p className="eyebrow">KİTAP SENTEZİ · ADAY</p>
                      <h2>Kitabın özeti</h2>
                      <p>{r.data.book_summary}</p>
                    </article>
                    {(r.data.character_change ?? []).map(
                      (c: any, i: number) => (
                        <article className="paper" key={"c" + i}>
                          <h2>{c.character}</h2>
                          <p>
                            <b>Başlangıç:</b> {c.initial}
                          </p>
                          <p>
                            <b>Sonraki durum:</b> {c.later}
                          </p>
                          <p>
                            <b>Tetikleyici:</b> {c.trigger}
                          </p>
                          <p>
                            <b>Alternatif okuma:</b> {c.alternative}
                          </p>
                          {refs(c.evidence_refs)}
                        </article>
                      ),
                    )}
                    {(r.data.themes ?? []).map((t: any, i: number) => (
                      <article className="paper" key={"t" + i}>
                        <h2>Tema yorumu</h2>
                        <p>{t.interpretation}</p>
                        <p>
                          <b>Alternatif okuma:</b> {t.alternative}
                        </p>
                        {refs(t.evidence_refs)}
                      </article>
                    ))}
                  </React.Fragment>
                ))}
                {!data.literary?.length && !data.semantic_synthesis?.length && (
                  <Empty
                    title="Kitap yorumu henüz oluşmadı"
                    text="Karakter değişimi ve tema yorumları kaynakları ve alternatif okumalarıyla gösterilecek."
                  />
                )}
              </section>
            )}
            {tab === "questions" && (
              <section className="cards">
                {questions.map((q) => (
                  <article className="paper wide" key={q.id}>
                    <span className="badge">
                      {statuses[q.status] ?? q.status}
                    </span>
                    <h2>{q.question}</h2>
                    {q.answer && (
                      <p className="eyebrow">
                        {answerStatuses[q.answer.status] ?? q.answer.status}
                      </p>
                    )}
                    <p>
                      {q.answer?.answer ??
                        (q.error_code
                          ? "Cevap üretilemedi: " + q.error_code
                          : "Cevap bekleniyor.")}
                    </p>
                    {q.answer?.claims?.map((c: any, i: number) => (
                      <div className="claim" key={i}>
                        <p>{c.text}</p>
                        {refs(c.evidence_refs)}
                      </div>
                    ))}
                    {q.answer?.limitations?.length > 0 && (
                      <div className="claim">
                        <b>Cevabın sınırları</b>
                        <ul>
                          {q.answer.limitations.map((item: string, i: number) => (
                            <li key={i}>{item}</li>
                          ))}
                        </ul>
                      </div>
                    )}
                    <small>Taslak cevap · insan editör onayı yok</small>
                  </article>
                ))}
                {!questions.length && (
                  <Empty
                    title="Soru koşusu henüz başlamadı"
                    text="Analiz ve arama indeksi hazır olduğunda gerçek soru-cevap sonuçları burada görünecek."
                  />
                )}
              </section>
            )}
            <footer>
              <span>
                İçerik ve geçmiş kayıtlar korunur. Bu ekran salt okunur.
              </span>
              <details>
                <summary>Analiz kimliği</summary>
                <code>{gen}</code>
              </details>
            </footer>
          </>
        )}
      </main>
    </div>
  );
}
function Empty({ title, text }: { title: string; text: string }) {
  return (
    <article className="empty wide">
      <span className="empty-symbol">◌</span>
      <h2>{title}</h2>
      <p>{text}</p>
    </article>
  );
}
createRoot(document.getElementById("root")!).render(<App />);
