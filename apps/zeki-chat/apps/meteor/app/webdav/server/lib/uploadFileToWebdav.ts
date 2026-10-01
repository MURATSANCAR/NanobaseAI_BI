import type { IWebdavAccount } from '@zeki.chat/core-typings';
import { WebdavAccounts } from '@zeki.chat/models';

import { getWebdavCredentials } from './getWebdavCredentials';
import { WebdavClientAdapter } from './webdavClientAdapter';

export const uploadFileToWebdav = async (accountId: IWebdavAccount['_id'], fileData: string | Buffer, name: string): Promise<void> => {
	const account = await WebdavAccounts.findOneById(accountId);
	if (!account) {
		throw new Error('error-invalid-account');
	}

	// Zeki: folder name created on the user's WebDAV server.
	const uploadFolder = 'ZEKI AI CHAT Uploads/';
	const buffer = Buffer.isBuffer(fileData) ? fileData : Buffer.from(fileData);

	const cred = getWebdavCredentials(account);
	const client = new WebdavClientAdapter(account.serverURL, cred);
	// eslint-disable-next-line @typescript-eslint/no-empty-function
	await client.createDirectory(uploadFolder).catch(() => {});
	await client.putFileContents(`${uploadFolder}/${name}`, buffer, { overwrite: false });
};
