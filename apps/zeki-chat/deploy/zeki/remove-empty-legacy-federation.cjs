// Stop the application and verify a fresh backup before applying this cleanup.
const { MongoClient, BSON } = require('/app/bundle/programs/server/npm/node_modules/mongodb');
const { createHash } = require('node:crypto');
const apply = process.argv.includes('--apply');
if (apply && process.env.ZEKI_IDENTITY_BACKUP_VERIFIED !== 'true') throw new Error('Verified backup required');
const client = new MongoClient('mongodb://zeki-mongo:27017/zeki?replicaSet=rs0');
const prefix = ['rocket', 'chat_'].join('');
const legacy = ['federation_events_staging', 'federation_locks'].map(name => prefix + name);

async function snapshot(db, names) {
	const result = {};
	for (const name of names) {
		const hashes = [];
		for await (const document of db.collection(name).find({}).batchSize(100)) {
			hashes.push(createHash('sha256').update(BSON.EJSON.stringify(document)).digest('hex'));
		}
		result[name] = { count: hashes.length, sha256: createHash('sha256').update(hashes.sort().join('')).digest('hex'), indexes: (await db.collection(name).listIndexes().toArray()).length };
	}
	return result;
}

(async () => {
	await client.connect();
	const db = client.db('zeki');
	const names = (await db.listCollections({}, { nameOnly: true }).toArray()).map(row => row.name).sort();
	const present = legacy.filter(name => names.includes(name));
	for (const name of present) {
		if (!names.includes(name.replace(prefix, 'zeki_'))) throw new Error('Expected migrated destination missing');
		if (await db.collection(name).countDocuments()) throw new Error('Refusing to drop a non-empty collection');
	}
	const retained = names.filter(name => !legacy.includes(name));
	const before = await snapshot(db, retained);
	if (apply) for (const name of present) await db.collection(name).drop();
	const after = await snapshot(db, retained);
	if (JSON.stringify(before) !== JSON.stringify(after)) throw new Error('Retained database content changed');
	console.log(JSON.stringify({ mode: apply ? 'apply' : 'dry-run', removedEmptyCollections: apply ? present : [], plannedEmptyCollections: present, retainedCollections: retained.length, retainedContentMatches: true, collections: after }, null, 2));
})().catch(error => { console.error(error.name === 'Error' ? error.message : error.name); process.exitCode = 1; }).finally(() => client.close());
