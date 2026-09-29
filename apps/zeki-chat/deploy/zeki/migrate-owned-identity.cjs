// Run with the application stopped, using its image on the existing private Mongo network.
// Dry-run by default. Keep a verified mongodump before --apply; never run against another database.
const { MongoClient, EJSON } = (() => {
	const mongodb = require('/app/bundle/programs/server/npm/node_modules/mongodb');
	return { ...mongodb, EJSON: mongodb.BSON.EJSON };
})();
const crypto = require('node:crypto');
const apply = process.argv.includes('--apply');
if (apply && process.env.ZEKI_IDENTITY_BACKUP_VERIFIED !== 'true') throw new Error('A verified database backup is required');
const legacyPrefix = ['rocket', 'chat_'].join('');
const legacyBot = ['rocket', 'cat'].join('.');
const legacySetting = 'LDAP_Groups_To_Rocket_Chat_Teams';
const settingName = 'LDAP_Groups_To_Zeki_Chat_Teams';
const obsoleteSettings = new Set(['Cloud_Workspace_License', 'Had_Trial', 'Trial_End']);
const renameCollection = (name) => name.startsWith(legacyPrefix) ? `zeki_${name.slice(legacyPrefix.length)}` : name;
const client = new MongoClient('mongodb://zeki-mongo:27017/zeki?replicaSet=rs0');

function transform(value, path, collection, changes) {
	if (typeof value === 'string') {
		let next = value;
		// Exact system identifiers only; user message text and attachments are never rewritten.
		if (value === legacyBot && /(^|\.)(_id|userId|uid|username)$/.test(path)) next = 'zeki.bot';
		if (collection.endsWith('_settings') && value === legacySetting && ['_id', 'i18nLabel', 'i18nDescription'].includes(path)) next = settingName;
		if (collection.endsWith('_permissions') && ['_id', 'settingId'].includes(path)) next = next.replace(legacySetting, settingName);
		if (collection.endsWith('_settings')) {
			next = next.replaceAll('RocketChat', 'ZekiChat').replaceAll('Rocket_Chat', 'Zeki_Chat').replaceAll(legacyPrefix, 'zeki_').replaceAll(legacyBot, 'zeki.bot').replaceAll('your-rocket-chat', 'your-chat');
		}
		if (next !== value) changes.push(path);
		return next;
	}
	if (!value || typeof value !== 'object' || value._bsontype || value instanceof Date || Buffer.isBuffer(value)) return value;
	if (Array.isArray(value)) return value.map((item) => transform(item, `${path}[]`, collection, changes));
	return Object.fromEntries(Object.entries(value).map(([key, item]) => [key, transform(item, path ? `${path}.${key}` : key, collection, changes)]));
}

async function main() {
	await client.connect();
	const db = client.db('zeki');
	const names = (await db.listCollections({}, { nameOnly: true }).toArray()).map((x) => x.name).sort();
	for (const name of names) if (renameCollection(name) !== name && names.includes(renameCollection(name))) throw new Error(`Destination exists: ${renameCollection(name)}`);
	const report = { mode: apply ? 'apply' : 'dry-run', database: 'zeki', collections: [], documentsChanged: 0, obsoleteSettingsRemoved: 0 };
	for (const name of names) {
		const collection = db.collection(name);
		const before = crypto.createHash('sha256');
		const expectedHashes = [];
		const indexCount = (await collection.listIndexes().toArray()).length;
		const plans = [];
		let count = 0;
		for await (const doc of collection.find({}).sort({ _id: 1 }).batchSize(100)) {
			count++;
			before.update(EJSON.stringify(doc));
			if (name.endsWith('_settings') && obsoleteSettings.has(doc._id)) {
				plans.push({ id: doc._id, remove: true });
				continue;
			}
			const paths = [];
			const next = transform(doc, '', name, paths);
			if (name.endsWith('_room') && doc.u?._id === legacyBot) {
				next.u.username = 'zeki.bot'; next.u.name = 'ZEKI AI CHAT'; paths.push('u.username', 'u.name');
			}
			if (name === 'instances' && typeof doc.name === 'string' && /rocket[. ]?chat/i.test(doc.name)) {
				next.name = 'ZEKI AI CHAT'; paths.push('name');
			}
			expectedHashes.push(crypto.createHash('sha256').update(EJSON.stringify(next)).digest('hex'));
			if (paths.length) {
				if (String(next._id) !== String(doc._id) && await collection.findOne({ _id: next._id })) throw new Error(`Document ID collision in ${name}`);
				plans.push({ id: doc._id, next, paths });
			}
		}
		if (apply) {
			for (const plan of plans) {
				if (plan.remove) { await collection.deleteOne({ _id: plan.id }); report.obsoleteSettingsRemoved++; }
				else if (String(plan.next._id) !== String(plan.id)) {
					const session = client.startSession();
					try {
						await session.withTransaction(async () => {
							await collection.deleteOne({ _id: plan.id }, { session });
							await collection.insertOne(plan.next, { session });
						});
					} finally { await session.endSession(); }
				} else await collection.replaceOne({ _id: plan.id }, plan.next);
			}
			if (renameCollection(name) !== name) await collection.rename(renameCollection(name), { dropTarget: false });
		}
		report.documentsChanged += plans.filter((x) => !x.remove).length;
		report.collections.push({ from: name, to: renameCollection(name), countBefore: count, countExpected: count - plans.filter((x) => x.remove).length, beforeSha256: before.digest('hex'), expectedSha256: crypto.createHash('sha256').update(expectedHashes.sort().join('')).digest('hex'), indexCount, changedFields: [...new Set(plans.flatMap((x) => x.paths || []))], obsoleteSettings: plans.filter((x) => x.remove).length });
	}
	if (apply) {
		for (const row of report.collections) {
			const hashes = [];
			for await (const doc of db.collection(row.to).find({}).batchSize(100)) hashes.push(crypto.createHash('sha256').update(EJSON.stringify(doc)).digest('hex'));
			row.actualSha256 = crypto.createHash('sha256').update(hashes.sort().join('')).digest('hex');
			row.actualCount = hashes.length;
			row.actualIndexCount = (await db.collection(row.to).listIndexes().toArray()).length;
			if (row.actualSha256 !== row.expectedSha256 || row.actualCount !== row.countExpected || row.actualIndexCount !== row.indexCount) throw new Error(`Post-migration mismatch: ${row.to}`);
		}
	}
	console.log(JSON.stringify(report, null, 2));
}
main().catch((error) => { console.error(error.message); process.exitCode = 1; }).finally(() => client.close());
