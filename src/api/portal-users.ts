export type PortalUserRecord = {
  id: string;
  username: string;
  display_name: string;
  modules: Array<'bi' | 'test' | 'contracts'>;
  locale: 'tr' | 'en' | 'ru' | 'uz';
  role: string;
  tenant_ids?: string[];
  project_ids?: string[];
  default_project_id?: string | null;
  is_user_admin: boolean;
  active: boolean;
};

export type PortalUserUpsert = {
  username?: string;
  display_name?: string;
  password?: string;
  modules?: Array<'bi' | 'test' | 'contracts'>;
  locale?: 'tr' | 'en' | 'ru' | 'uz';
  role?: string;
  tenant_ids?: string[];
  project_ids?: string[];
  default_project_id?: string | null;
  is_user_admin?: boolean;
  active?: boolean;
};

export type PortalUserPrefs = {
  locale?: 'tr' | 'en' | 'ru' | 'uz';
  default_project_id?: string | null;
};
