import { exec } from 'child_process';
import util from 'util';
import path from 'path';
import fs from 'fs';

const execAsync = util.promisify(exec);

class VersionCompiler {
	async processFilesForTarget(files) {
		// Zeki: supported versions are never fetched from releases.rocket.chat at build time.
		const processVersionFile = async function (file) {
			file.addJavaScript({
				data: `exports.supportedVersions = {}`,
				path: `${file.getPathInPackage()}.js`,
			});
		};

		const processFile = async function (file) {
			let output = JSON.parse(file.getContentsAsString());
			output.build = {
				date: new Date().toISOString(),
				nodeVersion: process.version,
				arch: process.arch,
				platform: process.platform,
			};

			output.marketplaceApiVersion = require('@zeki.chat/apps-engine/package.json').version.replace(/^[^0-9]/g, '');
			const minimumClientVersions =
				JSON.parse(fs.readFileSync(path.resolve(process.cwd(), './package.json'), { encoding: 'utf8' }))?.zekichat
					?.minimumClientVersions || {};
			// Zeki: only the short commit hash is embedded. Author, commit message, tag and branch were shipped
			// to every browser before; they are no longer included.
			try {
				const result = await execAsync('git rev-parse --short=10 HEAD');
				output.commit = { hash: result.stdout.trim() };
			} catch (e) {
				// no git: migrations still need a stable hash
				output.commit = { hash: output.version };
			}

			file.addJavaScript({
				data: `exports.Info = ${JSON.stringify(output, null, 4)};
				exports.minimumClientVersions = ${JSON.stringify(minimumClientVersions, null, 4)};`,
				path: `${file.getPathInPackage()}.js`,
			});
		};

		for await (const file of files) {
			console.log('Processing file', file.getDisplayPath());
			switch (true) {
				case file.getDisplayPath().endsWith('zekichat.info'): {
					await processFile(file);
					break;
				}
				case file.getDisplayPath().endsWith('zekichat-supported-versions.info'): {
					await processVersionFile(file);
					break;
				}
				default: {
					throw new Error(`Unexpected file ${file.getDisplayPath()}`);
				}
			}
			console.log('Processed file', file.getDisplayPath());
		}
	}
}

Plugin.registerCompiler(
	{
		extensions: ['info'],
	},
	function () {
		return new VersionCompiler();
	},
);
