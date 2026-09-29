import { createHash } from 'node:crypto';

import type { INPSService, NPSVotePayload, NPSCreatePayload } from '@rocket.chat/core-services';
import { ServiceClassInternal, Banner, Settings } from '@rocket.chat/core-services';
import type { INps } from '@rocket.chat/core-typings';
import { NPSStatus, INpsVoteStatus } from '@rocket.chat/core-typings';
import { Nps, NpsVote } from '@rocket.chat/models';

import { getBannerForAdmins, notifyAdmins } from './notification';
import { SystemLogger } from '../../lib/logger/system';

export class NPSService extends ServiceClassInternal implements INPSService {
	protected name = 'nps';

	async create(nps: NPSCreatePayload): Promise<boolean> {
		const npsEnabled = await Settings.get<boolean>('NPS_survey_enabled');
		if (!npsEnabled) {
			throw new Error('Server opted-out for NPS surveys');
		}

		const any = await Nps.findOne({}, { projection: { _id: 1 } });
		if (!any) {
			if (nps.expireAt < nps.startAt || nps.expireAt < new Date()) {
				throw new Error('NPS already expired');
			}
			await Banner.create(getBannerForAdmins(nps.expireAt));

			await notifyAdmins(nps.startAt);
		}

		const { npsId, startAt, expireAt, createdBy } = nps;

		try {
			await Nps.save({
				_id: npsId,
				startAt,
				expireAt,
				createdBy,
				status: NPSStatus.OPEN,
			});
		} catch (err) {
			SystemLogger.error({ msg: 'Error creating NPS', err });
			throw new Error('Error creating NPS');
		}

		return true;
	}

	// Zeki: NPS results are never sent to Rocket.Chat (nps.rocket.chat). Any open/expired survey is simply closed locally.
	async sendResults(): Promise<void> {
		await Nps.closeAllByStatus(NPSStatus.OPEN);
	}

	async vote({ userId, npsId, roles, score, comment }: NPSVotePayload): Promise<void> {
		const npsEnabled = await Settings.get<boolean>('NPS_survey_enabled');
		if (!npsEnabled) {
			return;
		}

		if (!npsId || typeof npsId !== 'string') {
			throw new Error('Invalid NPS id');
		}

		const nps = await Nps.findOneById<Pick<INps, 'status' | 'startAt' | 'expireAt'>>(npsId, {
			projection: { status: 1, startAt: 1, expireAt: 1 },
		});
		if (!nps) {
			return;
		}

		if (nps.status !== NPSStatus.OPEN) {
			throw new Error('NPS not open for votes');
		}

		const today = new Date();
		if (today > nps.expireAt) {
			throw new Error('NPS expired');
		}

		if (today < nps.startAt) {
			throw new Error('NPS survey not started');
		}

		const identifier = createHash('sha256').update(`${userId}${npsId}`).digest('hex');

		const result = await NpsVote.save({
			ts: new Date(),
			npsId,
			identifier,
			roles,
			score,
			comment,
			status: INpsVoteStatus.NEW,
		});
		if (!result) {
			throw new Error('Error saving NPS vote');
		}
	}

	async closeOpenSurveys(): Promise<void> {
		await Nps.closeAllByStatus(NPSStatus.OPEN);
	}
}
