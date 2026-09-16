import React, { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import "./style.css";

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
};

function App() {
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
      const rows = await all("/works");
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
  const sourceImage = imageFor === source?.id ? image : "";
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
            <label htmlFor="access">Operatör erişim anahtarı</label>
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
            Bu ilk sürüm operatör erişimi kullanır. Anahtar yalnız açık oturumun
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
                    ? "Hata: " + job.error_code
                    : "Son kaydedilen aşama: " +
                      (stages[job?.progress.stage] ?? "Hazırlanıyor")}
                </small>
              </article>
              <article>
                <span>KAYNAK KAPSAMI</span>
                <strong>
                  {job?.source_coverage.accounted_pages ?? 0} /{" "}
                  {job?.source_coverage.expected_pages ?? "—"} sayfa
                </strong>
                <small>
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
                {count("scenes")} sahne grubu · {count("events")} olay ·{" "}
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
                      </a>
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
                  <article className="paper">
                    <p className="eyebrow">MODELİN GÖRSEL OKUMASI</p>
                    <h2>Gözlem adayı</h2>
                    <span className="badge">Doğrulanmamış model çıktısı</span>
                    <p className="body-copy">
                      {visual?.data.description ??
                        "Bu sayfanın model çıktısı henüz kaydedilmedi."}
                    </p>
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
                {!data.entities?.length && (
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
                {!data.literary?.length && (
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
