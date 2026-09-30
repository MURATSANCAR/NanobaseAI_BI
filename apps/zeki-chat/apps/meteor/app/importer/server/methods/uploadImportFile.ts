import { Import } from '@zeki.chat/core-services';
import type { IUser } from '@zeki.chat/core-typings';
import type { ServerMethods } from '@zeki.chat/ddp-client';
import { Meteor } from 'meteor/meteor';

import { Importers } from '..';
import { hasPermissionAsync } from '../../../authorization/server/functions/hasPermission';
import { ZekiChatFile } from '../../../file/server';
import { ProgressStep } from '../../lib/ImporterProgressStep';
import { ZekiChatImportFileInstance } from '../startup/store';

export const executeUploadImportFile = async (
	userId: IUser['_id'],
	binaryContent: string,
	contentType: string,
	fileName: string,
	importerKey: string,
): Promise<void> => {
	const importer = Importers.get(importerKey);
	if (!importer) {
		throw new Meteor.Error('error-importer-not-defined', `The importer (${importerKey}) has no import class defined.`, 'uploadImportFile');
	}

	const operation = await Import.newOperation(userId, importer.name, importer.key);

	const instance = new importer.importer(importer, operation); // eslint-disable-line new-cap

	const date = new Date();
	const dateStr = `${date.getUTCFullYear()}${date.getUTCMonth()}${date.getUTCDate()}${date.getUTCHours()}${date.getUTCMinutes()}${date.getUTCSeconds()}`;
	const newFileName = `${dateStr}_${userId}_${fileName}`;

	// Store the file name and content type on the imports collection
	await instance.startFileUpload(newFileName, contentType);

	// Save the file on the File Store
	const file = Buffer.from(binaryContent, 'base64');
	const readStream = ZekiChatFile.bufferToStream(file);
	const writeStream = ZekiChatImportFileInstance.createWriteStream(newFileName, contentType);

	await new Promise<void>((resolve, reject) => {
		try {
			writeStream.on('end', () => {
				resolve();
			});
			writeStream.on('error', (e: Error) => {
				reject(e);
			});

			readStream.pipe(writeStream);
		} catch (error) {
			reject(error);
		}
	});

	await instance.updateProgress(ProgressStep.FILE_LOADED);
};

declare module '@zeki.chat/ddp-client' {
	// eslint-disable-next-line @typescript-eslint/naming-convention
	interface ServerMethods {
		uploadImportFile(binaryContent: string, contentType: string, fileName: string, importerKey: string): void;
	}
}

Meteor.methods<ServerMethods>({
	async uploadImportFile(binaryContent, contentType, fileName, importerKey) {
		const userId = Meteor.userId();

		if (!userId) {
			throw new Meteor.Error('error-invalid-user', 'Invalid user', 'uploadImportFile');
		}

		if (!(await hasPermissionAsync(userId, 'run-import'))) {
			throw new Meteor.Error('error-action-not-allowed', 'Importing is not allowed', 'uploadImportFile');
		}

		await executeUploadImportFile(userId, binaryContent, contentType, fileName, importerKey);
	},
});
