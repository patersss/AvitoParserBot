import React from "react";
import { createRoot } from "react-dom/client";
import {
  Bell,
  Check,
  Edit3,
  Eye,
  Loader2,
  LogOut,
  Pause,
  Play,
  Plus,
  RefreshCw,
  Save,
  Shield,
  Trash2,
  UserRound,
  X,
} from "lucide-react";

import { api, ApiError } from "./api";
import { clearToken, readToken, saveToken } from "./storage";
import { formatDate, formatPrice, fromDateTimeLocal, toDateTimeLocal } from "./format";
import type {
  EmailStartResponse,
  ListingRead,
  NotificationChannelRead,
  Platform,
  TaskCreate,
  TaskRead,
  UserRead,
  UserStatus,
} from "./types";
import "./styles.css";

type Page = "tasks" | "listings" | "notifications" | "account" | "admin";

const platformOptions: Platform[] = ["avito", "cian", "youla"];
const statusOptions: Array<UserStatus | ""> = ["", "active", "banned", "deleted"];

function App() {
  const [token, setToken] = React.useState<string | null>(() => readToken());
  const [user, setUser] = React.useState<UserRead | null>(null);
  const [page, setPage] = React.useState<Page>("tasks");
  const [booting, setBooting] = React.useState(true);
  const [notice, setNotice] = React.useState<string | null>(null);

  const applyAuth = React.useCallback((accessToken: string, nextUser: UserRead) => {
    saveToken(accessToken);
    setToken(accessToken);
    setUser(nextUser);
  }, []);

  const logout = React.useCallback(() => {
    clearToken();
    setToken(null);
    setUser(null);
    setPage("tasks");
  }, []);

  React.useEffect(() => {
    const urlToken = new URLSearchParams(window.location.search).get("token");
    if (urlToken) {
      setBooting(true);
      api
        .loginWithTelegramToken(urlToken)
        .then((auth) => {
          applyAuth(auth.access_token, auth.user);
          window.history.replaceState({}, "", window.location.pathname);
          setNotice(auth.user.login_email ? "Вход через Telegram выполнен" : "Осталось привязать email и пароль");
          setPage(auth.user.login_email ? "tasks" : "account");
        })
        .catch((error) => {
          clearToken();
          setNotice(errorMessage(error));
        })
        .finally(() => setBooting(false));
      return;
    }

    const stored = readToken();
    if (!stored) {
      setBooting(false);
      return;
    }

    api
      .me(stored)
      .then((me) => {
        setToken(stored);
        setUser(me);
        setPage(me.login_email ? "tasks" : "account");
      })
      .catch(() => {
        clearToken();
        setToken(null);
      })
      .finally(() => setBooting(false));
  }, [applyAuth]);

  if (booting) {
    return <LoadingScreen />;
  }

  if (!token || !user) {
    return <AuthScreen onAuth={applyAuth} notice={notice} />;
  }

  const isAdmin = user.user_role === "admin" || user.user_role === "superadmin";

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">
          <span className="brandMark">P</span>
          <div>
            <strong>Parser Monitor</strong>
            <span>{user.user_role}</span>
          </div>
        </div>

        <nav>
          <NavButton active={page === "tasks"} onClick={() => setPage("tasks")}>Задачи</NavButton>
          <NavButton active={page === "listings"} onClick={() => setPage("listings")}>Объявления</NavButton>
          <NavButton active={page === "notifications"} onClick={() => setPage("notifications")}>Уведомления</NavButton>
          <NavButton active={page === "account"} onClick={() => setPage("account")}>Аккаунт</NavButton>
          {isAdmin && <NavButton active={page === "admin"} onClick={() => setPage("admin")}>Админка</NavButton>}
        </nav>

        <div className="sidebarFooter">
          <div className="muted oneLine">{user.login_email || user.username || user.id}</div>
          <button className="ghostButton" onClick={logout} title="Выйти">
            <LogOut size={16} />
            Выйти
          </button>
        </div>
      </aside>

      <main className="content">
        {notice && <Toast message={notice} onClose={() => setNotice(null)} />}
        {!user.login_email && (
          <div className="callout">
            <UserRound size={18} />
            <span>Для входа по email привяжите почту и задайте пароль в аккаунте.</span>
          </div>
        )}

        {page === "tasks" && <TasksPage token={token} onNotice={setNotice} />}
        {page === "listings" && <ListingsPage token={token} />}
        {page === "notifications" && <NotificationsPage token={token} onNotice={setNotice} />}
        {page === "account" && <AccountPage token={token} user={user} onUser={setUser} onNotice={setNotice} />}
        {page === "admin" && isAdmin && <AdminPage token={token} onNotice={setNotice} />}
      </main>
    </div>
  );
}

function LoadingScreen() {
  return (
    <div className="centerScreen">
      <Loader2 className="spin" size={28} />
    </div>
  );
}

function AuthScreen({ onAuth, notice }: { onAuth: (token: string, user: UserRead) => void; notice: string | null }) {
  const [email, setEmail] = React.useState("");
  const [password, setPassword] = React.useState("");
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(notice);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const auth = await api.login(email, password);
      onAuth(auth.access_token, auth.user);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="authLayout">
      <section className="authPanel">
        <div className="brand authBrand">
          <span className="brandMark">P</span>
          <div>
            <strong>Parser Monitor</strong>
            <span>вход через Telegram или email</span>
          </div>
        </div>

        <form onSubmit={submit} className="form">
          <label>
            Email
            <input type="email" value={email} onChange={(event) => setEmail(event.target.value)} required />
          </label>
          <label>
            Пароль
            <input type="password" value={password} onChange={(event) => setPassword(event.target.value)} minLength={8} required />
          </label>
          {error && <p className="errorText">{error}</p>}
          <button className="primaryButton" disabled={loading}>
            {loading ? <Loader2 className="spin" size={16} /> : <Check size={16} />}
            Войти
          </button>
        </form>

        <p className="hint">
          Новый аккаунт открывается одноразовой ссылкой из Telegram-бота. После первого входа здесь можно задать email и пароль.
        </p>
      </section>
    </div>
  );
}

function TasksPage({ token, onNotice }: { token: string; onNotice: (value: string) => void }) {
  const [tasks, setTasks] = React.useState<TaskRead[]>([]);
  const [selectedTask, setSelectedTask] = React.useState<TaskRead | null>(null);
  const [taskListings, setTaskListings] = React.useState<ListingRead[]>([]);
  const [loading, setLoading] = React.useState(false);
  const [editing, setEditing] = React.useState<TaskRead | null>(null);

  const load = React.useCallback(async () => {
    setLoading(true);
    try {
      setTasks(await api.listTasks(token, true));
    } finally {
      setLoading(false);
    }
  }, [token]);

  React.useEffect(() => {
    load().catch(() => undefined);
  }, [load]);

  async function remove(task: TaskRead) {
    await api.deleteTask(token, task.id);
    onNotice("Задача удалена");
    setSelectedTask(null);
    await load();
  }

  async function refresh(task: TaskRead) {
    await api.refreshTask(token, task.id);
    onNotice("Запрос на обновление отправлен");
  }

  async function toggle(task: TaskRead) {
    await api.updateTask(token, task.id, { is_active: !task.is_active });
    await load();
  }

  async function openListings(task: TaskRead) {
    setSelectedTask(task);
    setTaskListings(await api.listTaskListings(token, task.id));
  }

  return (
    <section className="pageGrid">
      <div className="mainColumn">
        <PageHeader title="Задачи" action={<ReloadButton loading={loading} onClick={load} />} />
        <TaskForm token={token} onCreated={load} onNotice={onNotice} />

        <div className="tableWrap">
          <table>
            <thead>
              <tr>
                <th>Название</th>
                <th>Площадка</th>
                <th>Интервал</th>
                <th>Статус</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {tasks.map((task) => (
                <tr key={task.id}>
                  <td>
                    <strong>{task.name || "Без названия"}</strong>
                    <span className="subtle oneLine">{task.url}</span>
                  </td>
                  <td>{task.platform}</td>
                  <td>{task.interval_minutes} мин</td>
                  <td><StatusBadge active={task.is_active} /></td>
                  <td className="actions">
                    <IconButton title="Объявления" onClick={() => openListings(task)}><Eye size={16} /></IconButton>
                    <IconButton title="Редактировать" onClick={() => setEditing(task)}><Edit3 size={16} /></IconButton>
                    <IconButton title={task.is_active ? "Пауза" : "Возобновить"} onClick={() => toggle(task)}>
                      {task.is_active ? <Pause size={16} /> : <Play size={16} />}
                    </IconButton>
                    <IconButton title="Обновить сейчас" onClick={() => refresh(task)}><RefreshCw size={16} /></IconButton>
                    <IconButton title="Удалить" danger onClick={() => remove(task)}><Trash2 size={16} /></IconButton>
                  </td>
                </tr>
              ))}
              {!tasks.length && (
                <tr>
                  <td colSpan={5} className="empty">Задач пока нет</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      <aside className="sidePanel">
        <h2>{selectedTask ? selectedTask.name || selectedTask.platform : "История задачи"}</h2>
        <ListingList listings={taskListings} compact />
      </aside>

      {editing && (
        <TaskEditModal
          task={editing}
          token={token}
          onClose={() => setEditing(null)}
          onSaved={async () => {
            setEditing(null);
            await load();
          }}
        />
      )}
    </section>
  );
}

function TaskForm({ token, onCreated, onNotice }: { token: string; onCreated: () => Promise<void>; onNotice: (value: string) => void }) {
  const [form, setForm] = React.useState<TaskCreate>({
    name: "",
    platform: "avito",
    url: "",
    interval_minutes: 30,
    end_date: null,
    is_active: true,
  });
  const [endDate, setEndDate] = React.useState("");
  const [error, setError] = React.useState<string | null>(null);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    try {
      await api.createTask(token, { ...form, name: form.name || null, end_date: fromDateTimeLocal(endDate) });
      setForm({ name: "", platform: "avito", url: "", interval_minutes: 30, end_date: null, is_active: true });
      setEndDate("");
      onNotice("Задача создана");
      await onCreated();
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  return (
    <form className="inlineForm" onSubmit={submit}>
      <input placeholder="Название" value={form.name || ""} onChange={(event) => setForm({ ...form, name: event.target.value })} />
      <select value={form.platform} onChange={(event) => setForm({ ...form, platform: event.target.value as Platform })}>
        {platformOptions.map((platform) => <option key={platform}>{platform}</option>)}
      </select>
      <input className="wideInput" placeholder="URL" value={form.url} onChange={(event) => setForm({ ...form, url: event.target.value })} required />
      <input type="number" min={1} value={form.interval_minutes} onChange={(event) => setForm({ ...form, interval_minutes: Number(event.target.value) })} />
      <input type="datetime-local" value={endDate} onChange={(event) => setEndDate(event.target.value)} />
      <button className="primaryButton">
        <Plus size={16} />
        Создать
      </button>
      {error && <span className="errorText formError">{error}</span>}
    </form>
  );
}

function TaskEditModal({ task, token, onClose, onSaved }: { task: TaskRead; token: string; onClose: () => void; onSaved: () => Promise<void> }) {
  const [name, setName] = React.useState(task.name || "");
  const [platform, setPlatform] = React.useState<Platform>(task.platform);
  const [url, setUrl] = React.useState(task.url);
  const [interval, setInterval] = React.useState(task.interval_minutes);
  const [endDate, setEndDate] = React.useState(toDateTimeLocal(task.end_date));
  const [isActive, setIsActive] = React.useState(task.is_active);
  const [error, setError] = React.useState<string | null>(null);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    try {
      await api.updateTask(token, task.id, {
        name: name || null,
        platform,
        url,
        interval_minutes: interval,
        end_date: fromDateTimeLocal(endDate),
        is_active: isActive,
      });
      await onSaved();
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  return (
    <div className="modalBackdrop">
      <form className="modal" onSubmit={submit}>
        <PageHeader title="Редактирование" action={<IconButton title="Закрыть" onClick={onClose}><X size={16} /></IconButton>} />
        <label>Название<input value={name} onChange={(event) => setName(event.target.value)} /></label>
        <label>Площадка<select value={platform} onChange={(event) => setPlatform(event.target.value as Platform)}>{platformOptions.map((item) => <option key={item}>{item}</option>)}</select></label>
        <label>URL<input value={url} onChange={(event) => setUrl(event.target.value)} required /></label>
        <label>Интервал<input type="number" min={1} value={interval} onChange={(event) => setInterval(Number(event.target.value))} /></label>
        <label>Окончание<input type="datetime-local" value={endDate} onChange={(event) => setEndDate(event.target.value)} /></label>
        <label className="checkbox"><input type="checkbox" checked={isActive} onChange={(event) => setIsActive(event.target.checked)} /> Активна</label>
        {error && <p className="errorText">{error}</p>}
        <button className="primaryButton"><Save size={16} />Сохранить</button>
      </form>
    </div>
  );
}

function ListingsPage({ token }: { token: string }) {
  const [tasks, setTasks] = React.useState<TaskRead[]>([]);
  const [listings, setListings] = React.useState<ListingRead[]>([]);
  const [taskId, setTaskId] = React.useState("");
  const [platform, setPlatform] = React.useState<Platform | "">("");
  const [loading, setLoading] = React.useState(false);

  const load = React.useCallback(async () => {
    setLoading(true);
    try {
      const [nextTasks, nextListings] = await Promise.all([
        api.listTasks(token, true),
        api.listListings(token, { task_id: taskId || undefined, platform: platform || undefined }),
      ]);
      setTasks(nextTasks);
      setListings(nextListings);
    } finally {
      setLoading(false);
    }
  }, [token, taskId, platform]);

  React.useEffect(() => {
    load().catch(() => undefined);
  }, [load]);

  return (
    <section>
      <PageHeader title="Объявления" action={<ReloadButton loading={loading} onClick={load} />} />
      <div className="filters">
        <select value={taskId} onChange={(event) => setTaskId(event.target.value)}>
          <option value="">Все задачи</option>
          {tasks.map((task) => <option key={task.id} value={task.id}>{task.name || task.url}</option>)}
        </select>
        <select value={platform} onChange={(event) => setPlatform(event.target.value as Platform | "")}>
          <option value="">Все площадки</option>
          {platformOptions.map((item) => <option key={item}>{item}</option>)}
        </select>
      </div>
      <ListingList listings={listings} />
    </section>
  );
}

function NotificationsPage({ token, onNotice }: { token: string; onNotice: (value: string) => void }) {
  const [channels, setChannels] = React.useState<NotificationChannelRead[]>([]);
  const [email, setEmail] = React.useState("");
  const [verification, setVerification] = React.useState<EmailStartResponse | null>(null);
  const [code, setCode] = React.useState("");
  const [error, setError] = React.useState<string | null>(null);

  const load = React.useCallback(async () => {
    setChannels(await api.listNotificationChannels(token));
  }, [token]);

  React.useEffect(() => {
    load().catch(() => undefined);
  }, [load]);

  async function startEmail(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    try {
      setVerification(await api.startNotificationEmail(token, email));
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  async function confirmEmail(event: React.FormEvent) {
    event.preventDefault();
    if (!verification) return;
    setError(null);
    try {
      await api.confirmNotificationEmail(token, verification.verification_id, code);
      setVerification(null);
      setCode("");
      setEmail("");
      onNotice("Email-канал подключен");
      await load();
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  async function toggle(channel: NotificationChannelRead) {
    await api.updateNotificationChannel(token, channel.type, !channel.is_active);
    await load();
  }

  async function remove(channel: NotificationChannelRead) {
    await api.deleteNotificationChannel(token, channel.type);
    await load();
  }

  return (
    <section className="pageGrid">
      <div className="mainColumn">
        <PageHeader title="Уведомления" action={<Bell size={20} />} />
        <div className="tableWrap">
          <table>
            <thead>
              <tr><th>Канал</th><th>Адрес</th><th>Статус</th><th></th></tr>
            </thead>
            <tbody>
              {channels.map((channel) => (
                <tr key={channel.id}>
                  <td>{channel.type}</td>
                  <td>{String(channel.config.email || channel.config.chat_id || "-")}</td>
                  <td><StatusBadge active={channel.is_active} /></td>
                  <td className="actions">
                    <IconButton title={channel.is_active ? "Отключить" : "Включить"} onClick={() => toggle(channel)}>
                      {channel.is_active ? <Pause size={16} /> : <Play size={16} />}
                    </IconButton>
                    <IconButton title="Удалить" danger onClick={() => remove(channel)}><Trash2 size={16} /></IconButton>
                  </td>
                </tr>
              ))}
              {!channels.length && <tr><td colSpan={4} className="empty">Каналы не настроены</td></tr>}
            </tbody>
          </table>
        </div>
      </div>
      <aside className="sidePanel">
        <h2>Email</h2>
        {!verification ? (
          <form className="form" onSubmit={startEmail}>
            <label>Email для уведомлений<input type="email" value={email} onChange={(event) => setEmail(event.target.value)} required /></label>
            <button className="primaryButton"><Check size={16} />Получить код</button>
          </form>
        ) : (
          <form className="form" onSubmit={confirmEmail}>
            <label>Код<input value={code} onChange={(event) => setCode(event.target.value)} required /></label>
            {verification.dev_code && <p className="devCode">dev-код: {verification.dev_code}</p>}
            <button className="primaryButton"><Check size={16} />Подтвердить</button>
          </form>
        )}
        {error && <p className="errorText">{error}</p>}
      </aside>
    </section>
  );
}

function AccountPage({ token, user, onUser, onNotice }: { token: string; user: UserRead; onUser: (user: UserRead) => void; onNotice: (value: string) => void }) {
  const [username, setUsername] = React.useState(user.username || "");
  const [avatarUrl, setAvatarUrl] = React.useState(user.avatar_url || "");
  const [loginEmail, setLoginEmail] = React.useState(user.login_email || "");
  const [emailVerification, setEmailVerification] = React.useState<EmailStartResponse | null>(null);
  const [emailCode, setEmailCode] = React.useState("");
  const [firstPassword, setFirstPassword] = React.useState("");
  const [currentPassword, setCurrentPassword] = React.useState("");
  const [newPassword, setNewPassword] = React.useState("");
  const [error, setError] = React.useState<string | null>(null);

  async function saveProfile(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    try {
      onUser(await api.updateMe(token, { username: username || null, avatar_url: avatarUrl || null }));
      onNotice("Профиль обновлен");
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  async function startEmail(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    try {
      setEmailVerification(await api.startLoginEmail(token, loginEmail));
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  async function confirmEmail(event: React.FormEvent) {
    event.preventDefault();
    if (!emailVerification) return;
    setError(null);
    try {
      const nextUser = await api.confirmLoginEmail(token, emailVerification.verification_id, emailCode, user.login_email ? undefined : firstPassword);
      onUser(nextUser);
      setEmailVerification(null);
      setEmailCode("");
      setFirstPassword("");
      onNotice("Email подтвержден");
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  async function changePassword(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    try {
      await api.changePassword(token, currentPassword, newPassword);
      setCurrentPassword("");
      setNewPassword("");
      onNotice("Пароль изменен");
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  return (
    <section className="settingsGrid">
      <div>
        <PageHeader title="Аккаунт" action={<UserRound size={20} />} />
        <div className="summary">
          <div><span>ID</span><strong>{user.id}</strong></div>
          <div><span>Роль</span><strong>{user.user_role}</strong></div>
          <div><span>Статус</span><strong>{user.status}</strong></div>
          <div><span>Создан</span><strong>{formatDate(user.created_at)}</strong></div>
        </div>
      </div>

      <form className="panel form" onSubmit={saveProfile}>
        <h2>Профиль</h2>
        <label>Имя<input value={username} onChange={(event) => setUsername(event.target.value)} /></label>
        <label>Аватар URL<input value={avatarUrl} onChange={(event) => setAvatarUrl(event.target.value)} /></label>
        <button className="primaryButton"><Save size={16} />Сохранить</button>
      </form>

      <div className="panel">
        <h2>Email для входа</h2>
        {!emailVerification ? (
          <form className="form" onSubmit={startEmail}>
            <label>Email<input type="email" value={loginEmail} onChange={(event) => setLoginEmail(event.target.value)} required /></label>
            <button className="primaryButton"><Check size={16} />Получить код</button>
          </form>
        ) : (
          <form className="form" onSubmit={confirmEmail}>
            <label>Код<input value={emailCode} onChange={(event) => setEmailCode(event.target.value)} required /></label>
            {!user.login_email && <label>Пароль<input type="password" minLength={8} value={firstPassword} onChange={(event) => setFirstPassword(event.target.value)} required /></label>}
            {emailVerification.dev_code && <p className="devCode">dev-код: {emailVerification.dev_code}</p>}
            <button className="primaryButton"><Check size={16} />Подтвердить</button>
          </form>
        )}
      </div>

      {user.login_email && (
        <form className="panel form" onSubmit={changePassword}>
          <h2>Пароль</h2>
          <label>Текущий пароль<input type="password" minLength={8} value={currentPassword} onChange={(event) => setCurrentPassword(event.target.value)} required /></label>
          <label>Новый пароль<input type="password" minLength={8} value={newPassword} onChange={(event) => setNewPassword(event.target.value)} required /></label>
          <button className="primaryButton"><Save size={16} />Изменить</button>
        </form>
      )}

      {error && <p className="errorText">{error}</p>}
    </section>
  );
}

function AdminPage({ token, onNotice }: { token: string; onNotice: (value: string) => void }) {
  const [users, setUsers] = React.useState<UserRead[]>([]);
  const [status, setStatus] = React.useState<UserStatus | "">("");
  const [selectedUser, setSelectedUser] = React.useState<UserRead | null>(null);
  const [tasks, setTasks] = React.useState<TaskRead[]>([]);
  const [listings, setListings] = React.useState<ListingRead[]>([]);
  const [loading, setLoading] = React.useState(false);

  const load = React.useCallback(async () => {
    setLoading(true);
    try {
      setUsers(await api.adminUsers(token, status || undefined));
    } finally {
      setLoading(false);
    }
  }, [token, status]);

  React.useEffect(() => {
    load().catch(() => undefined);
  }, [load]);

  async function openUser(user: UserRead) {
    setSelectedUser(user);
    setListings([]);
    setTasks(await api.adminUserTasks(token, user.id, true));
  }

  async function ban(user: UserRead) {
    await api.adminBanUser(token, user.id, "Moderated from web admin");
    onNotice("Пользователь забанен");
    await load();
  }

  async function unban(user: UserRead) {
    await api.adminUnbanUser(token, user.id);
    onNotice("Пользователь разбанен");
    await load();
  }

  async function removeTask(task: TaskRead) {
    await api.adminDeleteTask(token, task.id);
    onNotice("Задача удалена");
    if (selectedUser) {
      setTasks(await api.adminUserTasks(token, selectedUser.id, true));
    }
  }

  async function openTaskListings(task: TaskRead) {
    setListings(await api.adminTaskListings(token, task.id));
  }

  return (
    <section className="pageGrid">
      <div className="mainColumn">
        <PageHeader title="Админка" action={<ReloadButton loading={loading} onClick={load} />} />
        <div className="filters">
          <select value={status} onChange={(event) => setStatus(event.target.value as UserStatus | "")}>
            {statusOptions.map((item) => <option key={item || "all"} value={item}>{item || "Все статусы"}</option>)}
          </select>
        </div>
        <div className="tableWrap">
          <table>
            <thead><tr><th>Пользователь</th><th>Роль</th><th>Статус</th><th></th></tr></thead>
            <tbody>
              {users.map((item) => (
                <tr key={item.id}>
                  <td>
                    <strong>{item.login_email || item.username || "Без email"}</strong>
                    <span className="subtle oneLine">{item.id}</span>
                  </td>
                  <td>{item.user_role}</td>
                  <td>{item.status}</td>
                  <td className="actions">
                    <IconButton title="Задачи" onClick={() => openUser(item)}><Eye size={16} /></IconButton>
                    {item.status === "banned" ? (
                      <IconButton title="Разбанить" onClick={() => unban(item)}><Shield size={16} /></IconButton>
                    ) : (
                      <IconButton title="Бан" danger onClick={() => ban(item)}><Shield size={16} /></IconButton>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
      <aside className="sidePanel">
        <h2>{selectedUser ? selectedUser.login_email || selectedUser.id : "Задачи пользователя"}</h2>
        <div className="compactList">
          {tasks.map((task) => (
            <div className="compactItem" key={task.id}>
              <strong>{task.name || task.platform}</strong>
              <span className="oneLine">{task.url}</span>
              <div className="actions">
                <IconButton title="Объявления" onClick={() => openTaskListings(task)}><Eye size={16} /></IconButton>
                <IconButton title="Удалить" danger onClick={() => removeTask(task)}><Trash2 size={16} /></IconButton>
              </div>
            </div>
          ))}
          {!tasks.length && <p className="empty">Нет выбранных задач</p>}
        </div>
        {!!listings.length && <ListingList listings={listings} compact />}
      </aside>
    </section>
  );
}

function ListingList({ listings, compact = false }: { listings: ListingRead[]; compact?: boolean }) {
  if (!listings.length) {
    return <p className="empty">Объявлений пока нет</p>;
  }

  return (
    <div className={compact ? "listingList compact" : "listingList"}>
      {listings.map((listing) => (
        <article className="listingCard" key={listing.id}>
          {listing.image_url && <img src={listing.image_url} alt="" />}
          <div>
            <a href={listing.url} target="_blank" rel="noreferrer">{listing.title || listing.external_id}</a>
            <strong>{formatPrice(listing.price)}</strong>
            <span>{listing.platform} · {formatDate(listing.created_at)}</span>
          </div>
        </article>
      ))}
    </div>
  );
}

function PageHeader({ title, action }: { title: string; action?: React.ReactNode }) {
  return (
    <header className="pageHeader">
      <h1>{title}</h1>
      {action}
    </header>
  );
}

function NavButton({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return <button className={active ? "navButton active" : "navButton"} onClick={onClick}>{children}</button>;
}

function IconButton({ title, onClick, children, danger = false }: { title: string; onClick: () => void; children: React.ReactNode; danger?: boolean }) {
  return (
    <button className={danger ? "iconButton danger" : "iconButton"} type="button" title={title} aria-label={title} onClick={onClick}>
      {children}
    </button>
  );
}

function ReloadButton({ loading, onClick }: { loading: boolean; onClick: () => void | Promise<void> }) {
  return (
    <IconButton title="Обновить" onClick={() => void onClick()}>
      <RefreshCw className={loading ? "spin" : ""} size={16} />
    </IconButton>
  );
}

function StatusBadge({ active }: { active: boolean }) {
  return <span className={active ? "badge success" : "badge mutedBadge"}>{active ? "активна" : "пауза"}</span>;
}

function Toast({ message, onClose }: { message: string; onClose: () => void }) {
  return (
    <div className="toast">
      <span>{message}</span>
      <button onClick={onClose} aria-label="Закрыть"><X size={14} /></button>
    </div>
  );
}

function errorMessage(error: unknown) {
  if (error instanceof ApiError) {
    return error.message;
  }
  if (error instanceof Error) {
    return error.message;
  }
  return "Не удалось выполнить запрос";
}

createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
