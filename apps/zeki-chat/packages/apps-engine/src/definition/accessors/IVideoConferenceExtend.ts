import type { ZekiChatAssociationModel } from '../metadata';
import type { IVideoConferenceUser, VideoConference } from '../videoConferences';
import type { VideoConferenceMember } from '../videoConferences/IVideoConference';

export interface IVideoConferenceExtender {
	kind: ZekiChatAssociationModel.VIDEO_CONFERENCE;

	setProviderData(value: Record<string, any>): IVideoConferenceExtender;

	setStatus(value: VideoConference['status']): IVideoConferenceExtender;

	setEndedBy(value: IVideoConferenceUser['_id']): IVideoConferenceExtender;

	setEndedAt(value: VideoConference['endedAt']): IVideoConferenceExtender;

	addUser(userId: VideoConferenceMember['_id'], ts?: VideoConferenceMember['ts']): IVideoConferenceExtender;

	setDiscussionRid(rid: VideoConference['discussionRid']): IVideoConferenceExtender;

	getVideoConference(): VideoConference;
}
