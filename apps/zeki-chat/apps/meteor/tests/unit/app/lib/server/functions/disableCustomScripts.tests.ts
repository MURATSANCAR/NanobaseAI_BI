import { expect } from 'chai';
import { disableCustomScripts } from '../../../../../../app/lib/server/functions/disableCustomScripts';

describe('disableCustomScripts', () => {
	let originalDisabled: string | undefined;
	let originalLocal: string | undefined;
	beforeEach(() => {
		originalDisabled = process.env.DISABLE_CUSTOM_SCRIPTS;
		originalLocal = process.env.ZEKI_LOCAL_ONLY;
		delete process.env.DISABLE_CUSTOM_SCRIPTS;
		delete process.env.ZEKI_LOCAL_ONLY;
	});
	afterEach(() => {
		if (originalDisabled === undefined) delete process.env.DISABLE_CUSTOM_SCRIPTS;
		else process.env.DISABLE_CUSTOM_SCRIPTS = originalDisabled;
		if (originalLocal === undefined) delete process.env.ZEKI_LOCAL_ONLY;
		else process.env.ZEKI_LOCAL_ONLY = originalLocal;
	});
	it('leaves scripts enabled when neither policy disables them', () => {
		expect(disableCustomScripts()).to.be.false;
	});
	it('disables scripts in local-only mode', () => {
		process.env.ZEKI_LOCAL_ONLY = 'true';
		expect(disableCustomScripts()).to.be.true;
	});
	it('honors an explicit script prohibition independently of capabilities', () => {
		process.env.DISABLE_CUSTOM_SCRIPTS = 'true';
		expect(disableCustomScripts()).to.be.true;
	});
});
