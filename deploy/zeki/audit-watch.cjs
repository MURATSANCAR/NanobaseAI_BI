// Merkezi denetim kaydı — sohbet veritabanının değişiklik akışı (sohbet konteynerinin içinde, mevcut sürücüyle).
// Girdi (ilk satır): {"resume": <token|null>}. Çıktı: her değişiklik bir JSON satırı.
// Önceki hâl için koleksiyonlarda changeStreamPreAndPostImages açılır (saklama 1 gün; kaybolursa yalnız sonraki hâl).
const { MongoClient } = require('/app/bundle/programs/server/npm/node_modules/meteor/npm-mongo/node_modules/mongodb');
const readline = require('node:readline');

// Kişinin işi olmayan, sürekli dönen kayıtlar: sunucu nabzı, zamanlayıcı kilitleri ve kuyrukları, çevrimiçi durumu,
// okundu bilgisi, oturum nabzı, önizleme önbelleği, dosya parçaları (2026-10-03 ölçümü: `instances` 10 sn'de bir,
// `zeki_cron` kilidi dakikada bir yazıyordu).
const SKIP = /^(instances|_queue|usersSessions|zeki_message_reads|zeki_read_receipts(_archive)?|zeki_instances|zeki_cron|zeki_cron_history|zeki_statistics|zeki_analytics|zeki_apps_logs|zeki_apps_scheduler|zeki_sessions|zeki_nps_vote|zeki_notification_queue|zeki_oembed_cache|zeki_federation_locks|zeki_federation_events_staging|zeki_livechat_agent_activity|omnichannel_.*|system\..*)$|\.chunks$/;

(async () => {
  const first = await new Promise((resolve) => {
    const rl = readline.createInterface({ input: process.stdin });
    rl.once('line', (l) => { rl.close(); resolve(l); });
  });
  const { resume } = JSON.parse(first || '{}');
  const client = await MongoClient.connect(process.env.MONGO_URL);
  const db = client.db();
  try {
    await client.db('admin').command({ setClusterParameter: { changeStreamOptions: { preAndPostImages: { expireAfterSeconds: 86400 } } } });
  } catch (e) { process.stderr.write(`ön-görüntü saklama ayarı: ${e.message}\n`); }
  for (const c of await db.listCollections({}, { nameOnly: true }).toArray()) {
    if (SKIP.test(c.name) || c.type === 'view') continue;
    try { await db.command({ collMod: c.name, changeStreamPreAndPostImages: { enabled: true } }); }
    catch (e) { process.stderr.write(`ön-görüntü açılamadı ${c.name}: ${e.message}\n`); }
  }
  const opts = { fullDocument: 'updateLookup', fullDocumentBeforeChange: 'whenAvailable' };
  if (resume) opts.resumeAfter = resume;
  const stream = db.watch([{ $match: { 'ns.coll': { $not: SKIP } } }], opts);
  process.stdout.write(JSON.stringify({ ready: true }) + '\n');
  for await (const ch of stream) {
    // Yeni koleksiyon açılınca önceki hâli de tutulsun.
    if (ch.operationType === 'create' && ch.ns?.coll && !SKIP.test(ch.ns.coll)) {
      db.command({ collMod: ch.ns.coll, changeStreamPreAndPostImages: { enabled: true } }).catch(() => {});
    }
    process.stdout.write(JSON.stringify({
      token: ch._id,
      op: ch.operationType,
      coll: ch.ns?.coll,
      key: ch.documentKey,
      at: ch.wallTime || (ch.clusterTime ? new Date(ch.clusterTime.getHighBits() * 1000) : new Date()),
      before: ch.fullDocumentBeforeChange ?? null,
      after: ch.fullDocument ?? null,
      changed: ch.updateDescription ? Object.keys(ch.updateDescription.updatedFields || {}).concat(ch.updateDescription.removedFields || []) : null,
    }) + '\n');
  }
})().catch((e) => { process.stderr.write(`izleyici durdu: ${e.stack || e}\n`); process.exit(1); });
