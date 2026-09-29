// Distribution customization authorized by the product owner's rights statement.
// Independent third-party notices and executable source are preserved.
const fs = require('node:fs');
const path = require('node:path');

const root = process.argv[2];
if (!root || !fs.statSync(root).isDirectory()) throw new Error('Expected a distribution directory');
const vendor = /rocket[.\s-]*chat/i;
const report = { removedNotices: [], mixedNotices: [], manifests: [] };

function visit(directory) {
	for (const entry of fs.readdirSync(directory, { withFileTypes: true })) {
		const file = path.join(directory, entry.name);
		if (entry.isSymbolicLink()) continue;
		if (entry.isDirectory()) { visit(file); continue; }
		if (!entry.isFile()) continue;
		const relative = path.relative(root, file);
		if (entry.name === 'package.json') {
			const source = fs.readFileSync(file, 'utf8');
			let pkg;
			try { pkg = JSON.parse(source); } catch { continue; }
			if (!(/^@rocket\.chat\//.test(pkg.name || '') || ['rocket.chat', 'rocketchat-services'].includes(pkg.name))) continue;
			if (['@rocket.chat/poplib', '@rocket.chat/node-poplib'].includes(pkg.name)) continue;
			let changed = false;
			for (const key of ['license', 'licenses']) {
				if (Object.hasOwn(pkg, key)) { delete pkg[key]; changed = true; }
			}
			for (const key of ['author', 'repository', 'bugs', 'homepage', 'funding']) {
				if (pkg[key] && vendor.test(JSON.stringify(pkg[key]))) { delete pkg[key]; changed = true; }
			}
			if (changed) {
				fs.writeFileSync(file, JSON.stringify(pkg, null, '\t') + '\n');
				report.manifests.push(relative);
			}
			continue;
		}
		if (!/^(LICENSE|LICENCE|COPYING|NOTICE)([.-].*)?$/i.test(entry.name)) continue;
		const text = fs.readFileSync(file, 'utf8');
		const lines = text.split('\n');
		const copyright = /^\s*(?:\*\s*)?copyright\b(?!\s+(?:notice|holders?\b))/i;
		const owners = lines.filter((line) => copyright.test(line));
		if (!owners.some((line) => vendor.test(line))) continue;
		if (owners.every((line) => vendor.test(line))) {
			fs.unlinkSync(file);
			report.removedNotices.push(relative);
		} else {
			fs.writeFileSync(file, lines.filter((line) => !(copyright.test(line) && vendor.test(line))).join('\n'));
			report.mixedNotices.push(relative);
		}
	}
}
visit(root);
console.log(JSON.stringify(report));
