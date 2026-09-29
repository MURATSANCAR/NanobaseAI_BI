// Run with the application stopped, using its image on the existing private Mongo network.
// Dry-run by default. Keep a verified mongodump before --apply; never run against another database.
const { MongoClient, EJSON } = (() => {
	const mongodb = require('/app/bundle/programs/server/npm/node_modules/mongodb');
	return { ...mongodb, EJSON: mongodb.BSON.EJSON };
})();
const crypto = require('node:crypto');
const checkpoint = (event, detail = {}) => console.error(JSON.stringify({ event, ...detail }));
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
		if (value === legacyBot) {
			const knownReference = collection.endsWith('_settings') || /(^|\.)(_id|userId|uid|username)$/.test(path) || /(^|\.)(uids|usernames)\[\]$/.test(path);
			// Preserve authored content; report only field paths, never message values.
			const authoredContent = /(^|\.)(msg|text|body|description|name|title|value)$/.test(path) || /(^|\.)attachments(\[\]|\.)/.test(path);
			if (knownReference) next = 'zeki.bot';
			else if (authoredContent) checkpoint('excluded-authored-content', { collection, path });
			else throw new Error(`Unmapped bot reference in ${collection}:${path}`);
		}
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
	const collectionPlans = [];
	for (const name of names) {
		const collection = db.collection(name);
		const before = crypto.createHash('sha256');
		const expectedHashes = [];
		const indexes = await collection.listIndexes().toArray();
		const indexCount = indexes.length;
		const plannedIds = new Set();
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
			const nextId = EJSON.stringify(next._id);
			if (plannedIds.has(nextId)) throw new Error(`Planned document ID collision in ${name}`);
			plannedIds.add(nextId);
			expectedHashes.push(crypto.createHash('sha256').update(EJSON.stringify(next)).digest('hex'));
			if (paths.length) {
				if (String(next._id) !== String(doc._id) && await collection.findOne({ _id: next._id })) throw new Error(`Document ID collision in ${name}`);
				// Detect existing secondary-key conflicts without writes. MongoDB itself remains
				// authoritative for multikey, partial, and collation index semantics at commit.
				for (const index of indexes.filter((item) => item.unique)) {
					const keyValue = (object, key) => key.split('.').reduce((value, part) => value?.[part], object);
					const keys = Object.keys(index.key);
					if (keys.every((key) => EJSON.stringify(keyValue(doc, key)) === EJSON.stringify(keyValue(next, key)))) continue;
					if (keys.some((key) => Array.isArray(keyValue(next, key)))) throw new Error(`Changed multikey unique index requires explicit review in ${name}`);
					const query = Object.fromEntries(keys.map((key) => [key, keyValue(next, key) ?? null]));
					const conditions = [query, { _id: { $ne: doc._id } }];
					if (index.partialFilterExpression) conditions.push(index.partialFilterExpression);
					const collation = index.collation && Object.fromEntries(Object.entries(index.collation).filter(([key]) => key !== 'version'));
					const conflict = await collection.findOne({ $and: conditions }, { projection: { _id: 1 }, ...(collation ? { collation } : {}) });
					if (conflict) throw new Error(`Unique key conflict in ${name}`);
				}
				if (String(next._id) !== String(doc._id)) checkpoint('identity-transaction-required', { collection: name, uniqueIndexes: indexes.filter((index) => index.unique).length });
				plans.push({ id: doc._id, next, paths });
			}
		}
		collectionPlans.push({ name, plans });
		checkpoint('collection-preflight-complete', { collection: name, changes: plans.length });
		report.documentsChanged += plans.filter((x) => !x.remove).length;
		report.collections.push({ from: name, to: renameCollection(name), countBefore: count, countExpected: count - plans.filter((x) => x.remove).length, beforeSha256: before.digest('hex'), expectedSha256: crypto.createHash('sha256').update(expectedHashes.sort().join('')).digest('hex'), indexCount, changedFields: [...new Set(plans.flatMap((x) => x.paths || []))], obsoleteSettings: plans.filter((x) => x.remove).length });
	}
	checkpoint('all-collections-preflight-complete', { collections: collectionPlans.length });
	for (const { name, plans } of collectionPlans) {
		const collection = db.collection(name);
		if (apply) {
			for (const plan of plans) {
				if (plan.remove) { if ((await collection.deleteOne({ _id: plan.id })).deletedCount !== 1) throw new Error('Delete precondition failed'); report.obsoleteSettingsRemoved++; }
				else if (String(plan.next._id) !== String(plan.id)) {
					const session = client.startSession();
					try {
						await session.withTransaction(async () => {
							if ((await collection.deleteOne({ _id: plan.id }, { session })).deletedCount !== 1) throw new Error('Identity delete precondition failed');
							await collection.insertOne(plan.next, { session });
						});
					} finally { await session.endSession(); }
				} else if ((await collection.replaceOne({ _id: plan.id }, plan.next)).matchedCount !== 1) throw new Error('Replace precondition failed');
				checkpoint('document-applied', { collection: name, operation: plan.remove ? 'delete' : 'replace' });
			}
			if (renameCollection(name) !== name) await collection.rename(renameCollection(name), { dropTarget: false });
		}
		if (apply) checkpoint('collection-applied', { from: name, to: renameCollection(name) });
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
main().catch((error) => { checkpoint('migration-failed', { message: error.name === 'Error' ? error.message : 'Database operation failed; details suppressed to protect document values', code: error.code, recovery: 'Keep application stopped. Restore verified backup including removal of partially renamed destination collections before retrying.' }); process.exitCode = 1; }).finally(() => client.close());
