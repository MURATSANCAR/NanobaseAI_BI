import { MessageFooterCallout, MessageFooterCalloutContent } from '@rocket.chat/ui-composer';
import type { ReactElement } from 'react';
import { Trans } from 'react-i18next';


const ComposerFederationInvalidVersion = (): ReactElement => {
	return (
		<MessageFooterCallout>
			<MessageFooterCalloutContent>
				<Trans
					i18nKey='Federation_Matrix_Federated_Description_invalid_version'
					components={{
						1: <span />, // Zeki: vendor federation docs link removed
					}}
				/>
			</MessageFooterCalloutContent>
		</MessageFooterCallout>
	);
};

export default ComposerFederationInvalidVersion;
