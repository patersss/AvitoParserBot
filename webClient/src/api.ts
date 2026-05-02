import type {
  AuthToken,
  EmailStartResponse,
  ListingRead,
  MessageResponse,
  NotificationChannelRead,
  NotificationChannelType,
  Platform,
  TaskCreate,
  TaskRead,
  TaskUpdate,
  UserRead,
  UserStatus,
} from "./types";

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || "http://localhost:8000").replace(/\/$/, "");

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

type QueryValue = string | number | boolean | null | undefined;

function query(params: Record<string, QueryValue>) {
  const search = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") {
      search.set(key, String(value));
    }
  });
  const value = search.toString();
  return value ? `?${value}` : "";
}

async function request<T>(path: string, options: RequestInit = {}, token?: string | null): Promise<T> {
  const headers = new Headers(options.headers);
  if (!(options.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers,
  });

  if (!response.ok) {
    let message = `HTTP ${response.status}`;
    try {
      const payload = await response.json();
      const detail = payload.detail;
      if (typeof detail === "string") {
        message = detail;
      } else if (Array.isArray(detail)) {
        message = detail.map((item) => item.msg || "Validation error").join("; ");
      }
    } catch {
      message = response.statusText || message;
    }
    throw new ApiError(response.status, message);
  }

  if (response.status === 204) {
    return undefined as T;
  }
  return response.json() as Promise<T>;
}

export const api = {
  login(email: string, password: string) {
    return request<AuthToken>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    });
  },

  loginWithTelegramToken(token: string) {
    return request<AuthToken>("/auth/telegram-token", {
      method: "POST",
      body: JSON.stringify({ token }),
    });
  },

  me(token: string) {
    return request<UserRead>("/account/me", {}, token);
  },

  updateMe(token: string, payload: { username?: string | null; avatar_url?: string | null }) {
    return request<UserRead>("/account/me", { method: "PATCH", body: JSON.stringify(payload) }, token);
  },

  startLoginEmail(token: string, email: string) {
    return request<EmailStartResponse>("/account/email/start", {
      method: "POST",
      body: JSON.stringify({ email }),
    }, token);
  },

  confirmLoginEmail(token: string, verification_id: string, code: string, password?: string) {
    return request<UserRead>("/account/email/confirm", {
      method: "POST",
      body: JSON.stringify({ verification_id, code, password: password || undefined }),
    }, token);
  },

  setPassword(token: string, password: string) {
    return request<MessageResponse>("/account/password/set", {
      method: "POST",
      body: JSON.stringify({ password }),
    }, token);
  },

  changePassword(token: string, current_password: string, new_password: string) {
    return request<MessageResponse>("/account/password/change", {
      method: "POST",
      body: JSON.stringify({ current_password, new_password }),
    }, token);
  },

  listTasks(token: string, includeInactive = true) {
    return request<TaskRead[]>(`/tasks${query({ include_inactive: includeInactive, limit: 100 })}`, {}, token);
  },

  createTask(token: string, payload: TaskCreate) {
    return request<TaskRead>("/tasks", { method: "POST", body: JSON.stringify(payload) }, token);
  },

  updateTask(token: string, taskId: string, payload: TaskUpdate) {
    return request<TaskRead>(`/tasks/${taskId}`, { method: "PATCH", body: JSON.stringify(payload) }, token);
  },

  refreshTask(token: string, taskId: string) {
    return request<MessageResponse>(`/tasks/${taskId}/refresh`, { method: "POST" }, token);
  },

  deleteTask(token: string, taskId: string) {
    return request<MessageResponse>(`/tasks/${taskId}`, { method: "DELETE" }, token);
  },

  listTaskListings(token: string, taskId: string, platform?: Platform) {
    return request<ListingRead[]>(`/tasks/${taskId}/listings${query({ platform, limit: 100 })}`, {}, token);
  },

  listListings(token: string, params: { task_id?: string; platform?: Platform } = {}) {
    return request<ListingRead[]>(`/listings${query({ ...params, limit: 100 })}`, {}, token);
  },

  listNotificationChannels(token: string) {
    return request<NotificationChannelRead[]>("/notification-channels", {}, token);
  },

  updateNotificationChannel(token: string, type: NotificationChannelType, is_active: boolean) {
    return request<NotificationChannelRead>(`/notification-channels/${type}`, {
      method: "PATCH",
      body: JSON.stringify({ is_active }),
    }, token);
  },

  deleteNotificationChannel(token: string, type: NotificationChannelType) {
    return request<MessageResponse>(`/notification-channels/${type}`, { method: "DELETE" }, token);
  },

  startNotificationEmail(token: string, email: string) {
    return request<EmailStartResponse>("/notification-channels/email/start", {
      method: "POST",
      body: JSON.stringify({ email }),
    }, token);
  },

  confirmNotificationEmail(token: string, verification_id: string, code: string) {
    return request<NotificationChannelRead>("/notification-channels/email/confirm", {
      method: "POST",
      body: JSON.stringify({ verification_id, code }),
    }, token);
  },

  adminUsers(token: string, status_filter?: UserStatus) {
    return request<UserRead[]>(`/admin/users${query({ status_filter, limit: 100 })}`, {}, token);
  },

  adminUserTasks(token: string, userId: string, includeDeleted = true) {
    return request<TaskRead[]>(`/admin/users/${userId}/tasks${query({ include_deleted: includeDeleted, limit: 100 })}`, {}, token);
  },

  adminBanUser(token: string, userId: string, reason?: string) {
    return request<MessageResponse>(`/admin/users/${userId}/ban`, {
      method: "PATCH",
      body: JSON.stringify({ reason: reason || undefined }),
    }, token);
  },

  adminUnbanUser(token: string, userId: string) {
    return request<MessageResponse>(`/admin/users/${userId}/unban`, { method: "PATCH" }, token);
  },

  adminDeleteTask(token: string, taskId: string) {
    return request<MessageResponse>(`/admin/tasks/${taskId}`, { method: "DELETE" }, token);
  },

  adminTaskListings(token: string, taskId: string) {
    return request<ListingRead[]>(`/admin/tasks/${taskId}/listings${query({ limit: 100 })}`, {}, token);
  },
};
