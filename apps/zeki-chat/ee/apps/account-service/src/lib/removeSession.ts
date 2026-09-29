import { Users } from '@zeki.chat/models';

export async function removeSession(uid: string, loginToken: string): Promise<void> {
	await Users.updateOne(
		{ _id: uid },
		{
			$pull: {
				'services.resume.loginTokens': {
					$or: [{ hashedToken: loginToken }, { token: loginToken }],
				},
			},
		},
	);
}
