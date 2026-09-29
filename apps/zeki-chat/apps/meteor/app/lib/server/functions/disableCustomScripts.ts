export const disableCustomScripts = () => process.env.ZEKI_LOCAL_ONLY === 'true' || process.env.DISABLE_CUSTOM_SCRIPTS === 'true';
