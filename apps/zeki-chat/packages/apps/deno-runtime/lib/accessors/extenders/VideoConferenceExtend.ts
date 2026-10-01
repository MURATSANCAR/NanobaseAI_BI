import type { IVideoConferenceExtender } from '@zeki.chat/apps-engine/definition/accessors/IVideoConferenceExtend';
import type { VideoConference, VideoConferenceMember } from '@zeki.chat/apps-engine/definition/videoConferences/IVideoConference';
import type { IVideoConferenceUser } from '@zeki.chat/apps-engine/definition/videoConferences/IVideoConferenceUser';
import type { ZekiChatAssociationModel as _ZekiChatAssociationModel } from '@zeki.chat/apps-engine/definition/metadata/ZekiChatAssociations';

import { require } from '../../../lib/require.ts';

const { ZekiChatAssociationModel } = require('@zeki.chat/apps-engine/definition/metadata/ZekiChatAssociations.js') as {
	ZekiChatAssociationModel: typeof _ZekiChatAssociationModel;
};

export class VideoConferenceExtender implements IVideoConferenceExtender {
	public kind: _ZekiChatAssociationModel.VIDEO_CONFERENCE;

	constructor(private videoConference: VideoConference) {
		this.kind = ZekiChatAssociationModel.VIDEO_CONFERENCE;
	}

	public setProviderData(value: Record<string, unknown>): IVideoConferenceExtender {
		this.videoConference.providerData = value;

		return this;
	}

	public setStatus(value: VideoConference['status']): IVideoConferenceExtender {
		this.videoConference.status = value;

		return this;
	}

	public setEndedBy(value: IVideoConferenceUser['_id']): IVideoConferenceExtender {
		this.videoConference.endedBy = {
			_id: value,
			// Name and username will be loaded automatically by the bridge
			username: '',
			name: '',
		};

		return this;
	}

	public setEndedAt(value: VideoConference['endedAt']): IVideoConferenceExtender {
		this.videoConference.endedAt = value;

		return this;
	}

	public addUser(userId: VideoConferenceMember['_id'], ts?: VideoConferenceMember['ts']): IVideoConferenceExtender {
		this.videoConference.users.push({
			_id: userId,
			ts,
			// Name and username will be loaded automatically by the bridge
			username: '',
			name: '',
		});

		return this;
	}

	public setDiscussionRid(rid: VideoConference['discussionRid']): IVideoConferenceExtender {
		this.videoConference.discussionRid = rid;

		return this;
	}

	public getVideoConference(): VideoConference {
		return structuredClone(this.videoConference);
	}
}
