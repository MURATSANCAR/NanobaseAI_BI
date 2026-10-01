// Read-only local Mongo adapter, using the chat image's existing driver.
const { MongoClient } = require('/app/bundle/programs/server/npm/node_modules/meteor/npm-mongo/node_modules/mongodb');
const readline = require('node:readline');
(async () => {
  const client = await MongoClient.connect(process.env.MONGO_URL);
  const db = client.db();
  for await (const line of readline.createInterface({ input: process.stdin })) {
    try {
      const q = JSON.parse(line);
      let result;
      if (q.op === 'poll') {
        result = await db.collection('zeki_message').find({
          ts: { $gte: new Date(q.after) }, 'mentions._id': 'zeki.bot',
          'u._id': { $ne: 'zeki.bot' }, t: { $exists: false },
          $or: [{ ts: { $gt: new Date(q.after) } }, { ts: new Date(q.after), _id: { $gt: q.id || '' } }],
        }, { projection: { _id: 1, ts: 1 } }).sort({ ts: 1, _id: 1 }).limit(100).toArray();
      } else if (q.op === 'context') {
        const message = await db.collection('zeki_message').findOne({ _id: q.id });
        const user = message && await db.collection('users').findOne({ _id: message.u?._id },
          { projection: { _id: 1, username: 1, active: 1, type: 1 } });
        const member = message && await db.collection('zeki_subscription').findOne({ rid: message.rid, 'u._id': user?._id },
          { projection: { _id: 1 } });
        result = { message, user, member: Boolean(member) };
      } else if (q.op === 'message') {
        result = await db.collection('zeki_message').findOne({ _id: q.id }, { projection: { _id: 1, rid: 1, msg: 1, u: 1 } });
      } else throw new Error('Unknown operation');
      process.stdout.write(JSON.stringify({ result }) + '\n');
    } catch (e) {
      process.stdout.write(JSON.stringify({ error: e.name }) + '\n');
    }
  }
  await client.close();
})().catch(() => process.exit(1));
