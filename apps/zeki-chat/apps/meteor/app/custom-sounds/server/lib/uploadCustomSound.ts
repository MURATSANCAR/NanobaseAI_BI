import { api } from '@zeki.chat/core-services';
import type { RequiredField } from '@zeki.chat/core-typings';
import { CustomSounds } from '@zeki.chat/models';

import { ZekiChatFile } from '../../../file/server';
import type { ICustomSoundData } from '../methods/insertOrUpdateSound';
import { ZekiChatFileCustomSoundsInstance } from '../startup/custom-sounds';

export const uploadCustomSound = async (
	buffer: Buffer,
	contentType: string,
	soundData: RequiredField<ICustomSoundData, '_id'>,
): Promise<void> => {
	const rs = ZekiChatFile.bufferToStream(buffer);

	if (soundData.previousExtension) {
		await ZekiChatFileCustomSoundsInstance.deleteFile(`${soundData._id}.${soundData.previousExtension}`);
	}

	return new Promise((resolve, reject) => {
		const ws = ZekiChatFileCustomSoundsInstance.createWriteStream(`${soundData._id}.${soundData.extension}`, contentType);

		ws.on('error', (err: Error) => {
			reject(err);
		});

		rs.on('error', (err: Error) => {
			ws.destroy();
			reject(err);
		});

		ws.on('end', () => {
			setTimeout(async () => {
				const sound = await CustomSounds.findOneById(soundData._id);
				if (sound) {
					void api.broadcast('notify.updateCustomSound', { soundData: sound });
				}
			}, 500);
			resolve();
		});

		rs.pipe(ws);
	});
};
