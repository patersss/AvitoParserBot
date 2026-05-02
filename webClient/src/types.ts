export type Platform = "avito" | "cian" | "youla";
export type UserRole = "user" | "admin" | "superadmin";
export type UserStatus = "active" | "banned" | "deleted";
export type NotificationChannelType = "telegram" | "email" | "vk";

export interface UserRead {
  id: string;
  username: string | null;
  avatar_url: string | null;
  login_email: string | null;
  is_email_verified: boolean;
  user_role: UserRole;
  status: UserStatus;
  created_at: string;
}

export interface AuthToken {
  access_token: string;
  token_type: "bearer";
  user: UserRead;
}

export interface TaskRead {
  id: string;
  user_id: string;
  name: string | null;
  platform: Platform;
  url: string;
  interval_minutes: number;
  end_date: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
  deleted_at: string | null;
}

export interface TaskCreate {
  name?: string | null;
  platform: Platform;
  url: string;
  interval_minutes: number;
  end_date?: string | null;
  is_active: boolean;
}

export type TaskUpdate = Partial<TaskCreate>;

export interface ListingRead {
  id: string;
  user_id: string;
  task_id: string;
  platform: Platform;
  external_id: string;
  title: string;
  price: number | null;
  url: string;
  image_url: string | null;
  published_at: string | null;
  created_at: string;
}

export interface NotificationChannelRead {
  id: string;
  user_id: string;
  type: NotificationChannelType;
  config: Record<string, unknown>;
  is_active: boolean;
  created_at: string;
  updated_at: string;
  deleted_at: string | null;
}

export interface EmailStartResponse {
  verification_id: string;
  expires_at: string;
  dev_code: string | null;
}

export interface MessageResponse {
  message: string;
}

export interface ApiErrorPayload {
  detail?: string | Array<{ msg?: string; loc?: Array<string | number> }>;
}
