import type { IUser, IRoom } from '@zeki.chat/core-typings';

type WorkDetails = {
	rid: IRoom['_id'];
	userId: IUser['_id'];
};

type WorkDetailsWithSource = WorkDetails & {
	from: string;
};

export interface IOmnichannelTranscriptService {
	workOnPdf({ details }: { details: WorkDetailsWithSource }): Promise<void>;
}
