import { Meteor } from 'meteor/meteor';

import { ZekiChatFile } from '../../../file/server';
import { settings } from '../../../settings/server';

export let ZekiChatImportFileInstance;

Meteor.startup(() => {
	const ZekiChatStore = ZekiChatFile.FileSystem;

	let path = '/tmp/zekichat-importer';
	if (settings.get('ImportFile_FileSystemPath') != null) {
		if (settings.get('ImportFile_FileSystemPath').trim() !== '') {
			path = settings.get('ImportFile_FileSystemPath');
		}
	}

	ZekiChatImportFileInstance = new ZekiChatStore({
		name: 'import_files',
		absolutePath: path,
	});
});
