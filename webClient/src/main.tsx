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
  ShieldOff,
  Trash2,
  UserMinus,
  UserPlus,
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
  UserRole,
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
          if (auth.user.login_email) setNotice("Вход через Telegram выполнен");
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

  if (!user.login_email) {
    return <RegisterPage token={token} user={user} onUser={setUser} onLogout={logout} />;
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
          {isAdmin && <NavButton active={page === "admin"} onClick={() => setPage("admin")}>Администрирование</NavButton>}
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

        {page === "tasks" && <TasksPage token={token} onNotice={setNotice} />}
        {page === "listings" && <ListingsPage token={token} />}
        {page === "notifications" && <NotificationsPage token={token} onNotice={setNotice} />}
        {page === "account" && <AccountPage token={token} user={user} onUser={setUser} onNotice={setNotice} />}
        {page === "admin" && isAdmin && <AdminPage token={token} userRole={user.user_role} onNotice={setNotice} />}
      </main>
    </div>
  );
}

function RegisterPage({
  token,
  user,
  onUser,
  onLogout,
}: {
  token: string;
  user: UserRead;
  onUser: (user: UserRead) => void;
  onLogout: () => void;
}) {
  const [email, setEmail] = React.useState("");
  const [verification, setVerification] = React.useState<EmailStartResponse | null>(null);
  const [code, setCode] = React.useState("");
  const [password, setPassword] = React.useState("");
  const [confirm, setConfirm] = React.useState("");
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  async function requestCode(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    setLoading(true);
    try {
      setVerification(await api.startLoginEmail(token, email));
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  async function register(event: React.FormEvent) {
    event.preventDefault();
    if (password !== confirm) {
      setError("Пароли не совпадают");
      return;
    }
    if (!verification) return;
    setError(null);
    setLoading(true);
    try {
      onUser(await api.confirmLoginEmail(token, verification.verification_id, code, password));
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
            <span>завершите регистрацию</span>
          </div>
        </div>

        {!verification ? (
          <form className="form" onSubmit={requestCode}>
            <p className="hint" style={{ margin: 0 }}>
              {user.username ? `Привет, ${user.username}! Задайте` : "Задайте"} email и пароль для входа на сайт.
            </p>
            <label>
              Email
              <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required autoFocus />
            </label>
            {error && <p className="errorText">{error}</p>}
            <button className="primaryButton" disabled={loading}>
              {loading ? <Loader2 className="spin" size={16} /> : <Check size={16} />}
              Получить код
            </button>
            <button type="button" className="ghostButton" onClick={onLogout}>
              <LogOut size={16} />
              Выйти
            </button>
          </form>
        ) : (
          <form className="form" onSubmit={register}>
            <p className="hint" style={{ margin: 0 }}>Код подтверждения отправлен на {email}</p>
            <label>
              Код из письма
              <input value={code} onChange={(e) => setCode(e.target.value)} required autoFocus />
            </label>
            {verification.dev_code && <p className="devCode">dev-код: {verification.dev_code}</p>}
            <label>
              Пароль
              <input type="password" minLength={8} value={password} onChange={(e) => setPassword(e.target.value)} required />
            </label>
            <label>
              Повторите пароль
              <input type="password" minLength={8} value={confirm} onChange={(e) => setConfirm(e.target.value)} required />
            </label>
            {error && <p className="errorText">{error}</p>}
            <button className="primaryButton" disabled={loading}>
              {loading ? <Loader2 className="spin" size={16} /> : <Check size={16} />}
              Зарегистрироваться
            </button>
            <button type="button" className="ghostButton" onClick={() => { setVerification(null); setCode(""); setPassword(""); setConfirm(""); setError(null); }}>
              <X size={16} />
              Назад
            </button>
          </form>
        )}
      </section>
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

  function copyUrl(url: string) {
    navigator.clipboard.writeText(url).then(
      () => onNotice("URL скопирован"),
      () => onNotice("Не удалось скопировать URL"),
    );
  }

  return (
    <section>
      <PageHeader title="Задачи" />
      <TaskForm token={token} onCreated={load} onNotice={onNotice} loading={loading} onReload={load} />

      <div className="tableWrap">
        <table className="tasksTable">
          <thead>
            <tr>
              <th>Название / URL</th>
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
                  <span
                    className="subtle taskUrl"
                    title="Двойной клик — скопировать URL"
                    onDoubleClick={() => copyUrl(task.url)}
                  >
                    {task.url}
                  </span>
                </td>
                <td>{task.platform}</td>
                <td>{task.interval_minutes} мин</td>
                <td><StatusBadge active={task.is_active} /></td>
                <td className="actions">
                  <IconButton title="Редактировать" onClick={() => setEditing(task)}><Edit3 size={16} /></IconButton>
                  <IconButton title={task.is_active ? "Пауза" : "Возобновить"} onClick={() => toggle(task)}>
                    {task.is_active ? <Pause size={16} /> : <Play size={16} />}
                  </IconButton>
                  <IconButton title="Парсить сейчас" onClick={() => refresh(task)}><RefreshCw size={16} /></IconButton>
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

function TaskForm({
  token,
  onCreated,
  onNotice,
  loading,
  onReload,
}: {
  token: string;
  onCreated: () => Promise<void>;
  onNotice: (value: string) => void;
  loading: boolean;
  onReload: () => void | Promise<void>;
}) {
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
      <div className="formActions">
        <button className="primaryButton" type="submit">
          <Plus size={16} />
          Создать
        </button>
        <button className="iconButton" type="button" title="Обновить список" aria-label="Обновить список" onClick={() => void onReload()}>
          <RefreshCw className={loading ? "spin" : ""} size={16} />
        </button>
      </div>
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
      onNotice("Email-канал добавлен");
      await load();
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  async function toggle(channel: NotificationChannelRead) {
    try {
      if (channel.type === "telegram") {
        await api.updateNotificationChannel(token, channel.type, !channel.is_active);
      } else {
        await api.updateNotificationChannelById(token, channel.id, !channel.is_active);
      }
      await load();
    } catch (err) {
      onNotice(errorMessage(err));
    }
  }

  async function remove(channel: NotificationChannelRead) {
    try {
      if (channel.type === "telegram") {
        await api.deleteNotificationChannel(token, channel.type);
      } else {
        await api.deleteNotificationChannelById(token, channel.id);
      }
      onNotice("Канал удалён");
      await load();
    } catch (err) {
      onNotice(errorMessage(err));
    }
  }

  return (
    <section className="notifPage">
      <PageHeader title="Уведомления" action={<Bell size={20} />} />

      <div className="notifAddPanel">
        {!verification ? (
          <form className="notifAddForm" onSubmit={startEmail}>
            <input
              type="email"
              placeholder="Email для уведомлений"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              required
            />
            <button className="primaryButton" type="submit">
              <Plus size={16} />
              Добавить email
            </button>
          </form>
        ) : (
          <form className="notifAddForm" onSubmit={confirmEmail}>
            <input
              placeholder={`Код из письма (${email})`}
              value={code}
              onChange={(event) => setCode(event.target.value)}
              required
              autoFocus
            />
            {verification.dev_code && <span className="devCode" style={{ fontSize: 12 }}>dev: {verification.dev_code}</span>}
            <button className="primaryButton" type="submit"><Check size={16} />Подтвердить</button>
            <button type="button" className="ghostButton" onClick={() => { setVerification(null); setCode(""); }}>
              <X size={16} />Отмена
            </button>
          </form>
        )}
        {error && <p className="errorText" style={{ margin: 0 }}>{error}</p>}
      </div>

      <div className="channelList">
        {channels.length === 0 && <p className="empty">Каналы не настроены</p>}
        {channels.map((channel) => {
          const address =
            channel.type === "email"
              ? String(channel.config.email ?? "")
              : channel.type === "telegram"
              ? `chat_id: ${channel.config.chat_id}`
              : JSON.stringify(channel.config);
          const label = channel.type === "email" ? "Email" : channel.type === "telegram" ? "Telegram" : channel.type;
          return (
            <div className="channelCard" key={channel.id}>
              <div className="channelCardIcon">{channel.type === "telegram" ? "TG" : "@"}</div>
              <div className="channelCardInfo">
                <span className="channelType">{label}</span>
                <span className="channelAddress">{address}</span>
              </div>
              <StatusBadge active={channel.is_active} />
              <div className="channelCardActions">
                <IconButton title={channel.is_active ? "Отключить" : "Включить"} onClick={() => toggle(channel)}>
                  {channel.is_active ? <Pause size={16} /> : <Play size={16} />}
                </IconButton>
                <IconButton title="Удалить" danger onClick={() => remove(channel)}>
                  <Trash2 size={16} />
                </IconButton>
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}

function AccountPage({ token, user, onUser, onNotice }: { token: string; user: UserRead; onUser: (user: UserRead) => void; onNotice: (value: string) => void }) {
  const [username, setUsername] = React.useState(user.username || "");
  const [profileEditing, setProfileEditing] = React.useState(false);
  const [profileError, setProfileError] = React.useState<string | null>(null);

  const [loginEmail, setLoginEmail] = React.useState(user.login_email || "");
  const [emailVerification, setEmailVerification] = React.useState<EmailStartResponse | null>(null);
  const [emailStep, setEmailStep] = React.useState<"code" | "password">("code");
  const [emailCode, setEmailCode] = React.useState("");
  const [firstPassword, setFirstPassword] = React.useState("");
  const [emailError, setEmailError] = React.useState<string | null>(null);

  const [currentPassword, setCurrentPassword] = React.useState("");
  const [newPassword, setNewPassword] = React.useState("");
  const [passwordError, setPasswordError] = React.useState<string | null>(null);

  const [taskCount, setTaskCount] = React.useState<number | null>(null);
  const [listingCount, setListingCount] = React.useState<number | null>(null);

  React.useEffect(() => {
    api.listTasks(token, true).then((tasks) => setTaskCount(tasks.length)).catch(() => undefined);
    api.listListings(token).then((listings) => setListingCount(listings.length)).catch(() => undefined);
  }, [token]);

  async function saveProfile(event: React.FormEvent) {
    event.preventDefault();
    setProfileError(null);
    try {
      onUser(await api.updateMe(token, { username: username || null }));
      setProfileEditing(false);
      onNotice("Имя обновлено");
    } catch (err) {
      setProfileError(errorMessage(err));
    }
  }

  function cancelProfileEdit() {
    setUsername(user.username || "");
    setProfileEditing(false);
    setProfileError(null);
  }

  async function startEmail(event: React.FormEvent) {
    event.preventDefault();
    setEmailError(null);
    try {
      setEmailStep("code");
      setEmailCode("");
      setFirstPassword("");
      setEmailVerification(await api.startLoginEmail(token, loginEmail));
    } catch (err) {
      setEmailError(errorMessage(err));
    }
  }

  async function handleCodeNext(event: React.FormEvent) {
    event.preventDefault();
    setEmailError(null);
    if (!user.login_email) {
      setEmailStep("password");
    } else {
      await confirmEmail(event);
    }
  }

  async function confirmEmail(event: React.FormEvent) {
    event.preventDefault();
    if (!emailVerification) return;
    setEmailError(null);
    try {
      const nextUser = await api.confirmLoginEmail(
        token,
        emailVerification.verification_id,
        emailCode,
        user.login_email ? undefined : firstPassword,
      );
      onUser(nextUser);
      setEmailVerification(null);
      setEmailCode("");
      setFirstPassword("");
      setEmailStep("code");
      onNotice("Email подтверждён");
    } catch (err) {
      setEmailError(errorMessage(err));
    }
  }

  async function changePassword(event: React.FormEvent) {
    event.preventDefault();
    setPasswordError(null);
    try {
      await api.changePassword(token, currentPassword, newPassword);
      setCurrentPassword("");
      setNewPassword("");
      onNotice("Пароль изменён");
    } catch (err) {
      setPasswordError(errorMessage(err));
    }
  }

  const initials = (user.username?.[0] || user.login_email?.[0] || "?").toUpperCase();

  return (
    <div className="accountPage">

      {/* Profile */}
      <div className="profileCard panel">
        <div className="profileAvatar">{initials}</div>
        <div className="profileInfo">
          {profileEditing ? (
            <form className="profileEditForm" onSubmit={saveProfile}>
              <input
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                placeholder="Имя пользователя"
                autoFocus
              />
              <button className="iconButton" type="submit" title="Сохранить" aria-label="Сохранить">
                <Check size={16} />
              </button>
              <button className="iconButton" type="button" title="Отмена" aria-label="Отмена" onClick={cancelProfileEdit}>
                <X size={16} />
              </button>
              {profileError && <span className="errorText">{profileError}</span>}
            </form>
          ) : (
            <div className="profileNameRow">
              <span className="profileName">{user.username || "Без имени"}</span>
              <button
                className="iconButton"
                type="button"
                title="Редактировать имя"
                aria-label="Редактировать имя"
                onClick={() => setProfileEditing(true)}
              >
                <Edit3 size={15} />
              </button>
            </div>
          )}
          <span className="muted">{user.login_email || "email не задан"}</span>
        </div>
      </div>

      {/* Stats */}
      <div className="summary">
        <div><span>Задач создано</span><strong>{taskCount ?? "—"}</strong></div>
        <div><span>Объявлений найдено</span><strong>{listingCount ?? "—"}</strong></div>
        <div><span>Роль</span><strong>{user.user_role}</strong></div>
        <div><span>Зарегистрирован</span><strong>{formatDate(user.created_at)}</strong></div>
      </div>

      {/* Email */}
      <div className="panel">
        <h2>Email для входа</h2>
        {!emailVerification ? (
          <form className="form" onSubmit={startEmail}>
            <label>
              Email
              <input type="email" value={loginEmail} onChange={(e) => setLoginEmail(e.target.value)} required />
            </label>
            {emailError && <p className="errorText">{emailError}</p>}
            <button className="primaryButton"><Check size={16} />Получить код</button>
          </form>
        ) : emailStep === "code" ? (
          <form className="form" onSubmit={handleCodeNext}>
            <label>
              Код из письма
              <input value={emailCode} onChange={(e) => setEmailCode(e.target.value)} required autoFocus />
            </label>
            {emailVerification.dev_code && <p className="devCode">dev-код: {emailVerification.dev_code}</p>}
            {emailError && <p className="errorText">{emailError}</p>}
            <button className="primaryButton"><Check size={16} />{user.login_email ? "Подтвердить" : "Далее"}</button>
            <button type="button" className="ghostButton" onClick={() => { setEmailVerification(null); setEmailCode(""); setEmailError(null); }}>
              <X size={16} />Отмена
            </button>
          </form>
        ) : (
          <form className="form" onSubmit={confirmEmail}>
            <label>
              Придумайте пароль
              <input type="password" minLength={8} value={firstPassword} onChange={(e) => setFirstPassword(e.target.value)} required autoFocus />
            </label>
            {emailError && <p className="errorText">{emailError}</p>}
            <button className="primaryButton"><Check size={16} />Подтвердить</button>
            <button type="button" className="ghostButton" onClick={() => { setEmailStep("code"); setEmailError(null); }}>
              <X size={16} />Назад
            </button>
          </form>
        )}
      </div>

      {/* Password */}
      {user.login_email && (
        <div className="panel">
          <h2>Изменить пароль</h2>
          <form className="form" onSubmit={changePassword}>
            <label>
              Текущий пароль
              <input type="password" minLength={8} value={currentPassword} onChange={(e) => setCurrentPassword(e.target.value)} required />
            </label>
            <label>
              Новый пароль
              <input type="password" minLength={8} value={newPassword} onChange={(e) => setNewPassword(e.target.value)} required />
            </label>
            {passwordError && <p className="errorText">{passwordError}</p>}
            <button className="primaryButton"><Save size={16} />Изменить</button>
          </form>
        </div>
      )}

    </div>
  );
}

const userStatusLabels: Record<UserStatus, string> = {
  active: "Активные",
  banned: "Заблокированные",
  deleted: "Удалённые",
};

function AdminPage({ token, userRole, onNotice }: { token: string; userRole: UserRole; onNotice: (value: string) => void }) {
  const [users, setUsers] = React.useState<UserRead[]>([]);
  const [statusFilter, setStatusFilter] = React.useState<UserStatus | "">("");
  const [selectedUser, setSelectedUser] = React.useState<UserRead | null>(null);
  const [tasks, setTasks] = React.useState<TaskRead[]>([]);
  const [taskListings, setTaskListings] = React.useState<Record<string, ListingRead[]>>({});
  const [loading, setLoading] = React.useState(false);

  const isSuperadmin = userRole === "superadmin";

  const load = React.useCallback(async () => {
    setLoading(true);
    try {
      setUsers(await api.adminUsers(token, statusFilter || undefined));
    } finally {
      setLoading(false);
    }
  }, [token, statusFilter]);

  React.useEffect(() => {
    load().catch(() => undefined);
  }, [load]);

  async function openUser(user: UserRead) {
    setSelectedUser(user);
    setTaskListings({});
    setTasks(await api.adminUserTasks(token, user.id, true));
  }

  async function ban(user: UserRead) {
    try {
      await api.adminBanUser(token, user.id, "Moderated from web admin");
      onNotice("Пользователь заблокирован");
      if (selectedUser?.id === user.id) setSelectedUser({ ...user, status: "banned" });
      await load();
    } catch (err) {
      onNotice(errorMessage(err));
    }
  }

  async function unban(user: UserRead) {
    try {
      await api.adminUnbanUser(token, user.id);
      onNotice("Пользователь разблокирован");
      if (selectedUser?.id === user.id) setSelectedUser({ ...user, status: "active" });
      await load();
    } catch (err) {
      onNotice(errorMessage(err));
    }
  }

  async function changeRole(user: UserRead, role: "user" | "admin") {
    try {
      const updated = await api.adminUpdateUserRole(token, user.id, role);
      onNotice(role === "admin" ? "Пользователь повышен до администратора" : "Права администратора сняты");
      setUsers((prev) => prev.map((u) => (u.id === updated.id ? updated : u)));
      if (selectedUser?.id === updated.id) setSelectedUser(updated);
    } catch (err) {
      onNotice(errorMessage(err));
    }
  }

  async function toggleTask(task: TaskRead) {
    try {
      const updated = await api.adminUpdateTask(token, task.id, !task.is_active);
      onNotice(updated.is_active ? "Задача возобновлена" : "Задача приостановлена");
      setTasks((prev) => prev.map((t) => (t.id === task.id ? updated : t)));
    } catch (err) {
      onNotice(errorMessage(err));
    }
  }

  async function removeTask(task: TaskRead) {
    try {
      await api.adminDeleteTask(token, task.id);
      onNotice("Задача удалена");
      setTaskListings((prev) => { const next = { ...prev }; delete next[task.id]; return next; });
      if (selectedUser) {
        setTasks(await api.adminUserTasks(token, selectedUser.id, true));
      }
    } catch (err) {
      onNotice(errorMessage(err));
    }
  }

  async function toggleTaskListings(task: TaskRead) {
    if (task.id in taskListings) {
      setTaskListings((prev) => { const next = { ...prev }; delete next[task.id]; return next; });
      return;
    }
    const items = await api.adminTaskListings(token, task.id);
    setTaskListings((prev) => ({ ...prev, [task.id]: items }));
  }

  function copyUrl(url: string) {
    navigator.clipboard.writeText(url).then(
      () => onNotice("URL скопирован"),
      () => onNotice("Не удалось скопировать URL"),
    );
  }

  return (
    <section className="pageGrid">
      <div className="mainColumn">
        <PageHeader title="Администрирование" action={<ReloadButton loading={loading} onClick={load} />} />
        <div className="filters">
          <select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value as UserStatus | "")}>
            <option value="">Все пользователи</option>
            {(["active", "banned", "deleted"] as UserStatus[]).map((s) => (
              <option key={s} value={s}>{userStatusLabels[s]}</option>
            ))}
          </select>
        </div>
        <div className="tableWrap">
          <table>
            <thead>
              <tr>
                <th>Пользователь</th>
                <th>Роль</th>
                <th>Статус</th>
                <th>Зарегистрирован</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {users.map((item) => (
                <tr key={item.id} className={selectedUser?.id === item.id ? "selectedRow" : ""}>
                  <td>
                    <strong>{item.login_email || "Без email"}</strong>
                    {item.username && <span className="subtle oneLine">{item.username}</span>}
                  </td>
                  <td><RoleBadge role={item.user_role} /></td>
                  <td><UserStatusBadge status={item.status} /></td>
                  <td className="subtle">{formatDate(item.created_at)}</td>
                  <td className="actions">
                    <IconButton title="Задачи пользователя" onClick={() => openUser(item)}><Eye size={16} /></IconButton>
                    {isSuperadmin && item.user_role === "user" && (
                      <IconButton title="Назначить администратором" onClick={() => changeRole(item, "admin")}>
                        <UserPlus size={16} />
                      </IconButton>
                    )}
                    {isSuperadmin && item.user_role === "admin" && (
                      <IconButton title="Снять права администратора" danger onClick={() => changeRole(item, "user")}>
                        <UserMinus size={16} />
                      </IconButton>
                    )}
                    {item.status === "banned" ? (
                      <IconButton title="Разблокировать" onClick={() => unban(item)}><ShieldOff size={16} /></IconButton>
                    ) : item.status === "active" ? (
                      <IconButton title="Заблокировать" danger onClick={() => ban(item)}><Shield size={16} /></IconButton>
                    ) : null}
                  </td>
                </tr>
              ))}
              {!users.length && (
                <tr><td colSpan={5} className="empty">Пользователей не найдено</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      <aside className="sidePanel adminSidePanel">
        {selectedUser ? (
          <>
            <div className="adminUserHeader">
              <div className="adminUserAvatar">
                {(selectedUser.username?.[0] || selectedUser.login_email?.[0] || "?").toUpperCase()}
              </div>
              <div className="adminUserInfo">
                <strong className="oneLine">{selectedUser.login_email || "Без email"}</strong>
                <span className="muted oneLine">{selectedUser.username || selectedUser.id}</span>
              </div>
              <UserStatusBadge status={selectedUser.status} />
            </div>

            <div className="adminSectionHeader">
              <h2>Задачи</h2>
              <span className="badge mutedBadge">{tasks.length}</span>
            </div>
            <div className="compactList">
              {tasks.map((task) => (
                <React.Fragment key={task.id}>
                  <div className={`compactItem adminTaskItem${task.deleted_at ? " adminTaskDeleted" : ""}`}>
                    <div className="adminTaskHeader">
                      <strong className="oneLine">{task.name || "Без названия"}</strong>
                      <AdminTaskStatusBadge task={task} />
                    </div>
                    <div className="adminTaskMeta">
                      <span className="platformTag">{task.platform}</span>
                      <span className="subtle">{task.interval_minutes} мин</span>
                    </div>
                    {task.end_date && (
                      <span className="subtle adminTaskEndDate">до {formatDate(task.end_date)}</span>
                    )}
                    <span
                      className="subtle oneLine taskUrl"
                      title="Двойной клик — скопировать URL"
                      onDoubleClick={() => copyUrl(task.url)}
                    >
                      {task.url}
                    </span>
                    <div className="actions">
                      <IconButton
                        title={task.id in taskListings ? "Скрыть объявления" : "Показать объявления"}
                        onClick={() => toggleTaskListings(task)}
                      >
                        <Eye size={16} />
                      </IconButton>
                      {!task.deleted_at && (
                        <IconButton title={task.is_active ? "Приостановить" : "Возобновить"} onClick={() => toggleTask(task)}>
                          {task.is_active ? <Pause size={16} /> : <Play size={16} />}
                        </IconButton>
                      )}
                      {!task.deleted_at && (
                        <IconButton title="Удалить" danger onClick={() => removeTask(task)}><Trash2 size={16} /></IconButton>
                      )}
                    </div>
                  </div>
                  {task.id in taskListings && (
                    <div className="adminListingsSection">
                      <div className="listingsHeader">
                        <span className="adminListingsTitle">Объявления</span>
                        <IconButton
                          title="Скрыть"
                          onClick={() => setTaskListings((prev) => { const next = { ...prev }; delete next[task.id]; return next; })}
                        >
                          <X size={16} />
                        </IconButton>
                      </div>
                      {(taskListings[task.id] ?? []).length > 0
                        ? <ListingList listings={taskListings[task.id]} compact />
                        : <p className="empty">Объявлений пока нет</p>
                      }
                    </div>
                  )}
                </React.Fragment>
              ))}
              {!tasks.length && <p className="empty">Задач нет</p>}
            </div>
          </>
        ) : (
          <p className="empty adminSidePlaceholder">Выберите пользователя чтобы увидеть его задачи</p>
        )}
      </aside>
    </section>
  );
}

function UserStatusBadge({ status }: { status: UserStatus }) {
  if (status === "active") return <span className="badge success">активен</span>;
  if (status === "banned") return <span className="badge danger">заблокирован</span>;
  return <span className="badge mutedBadge">удалён</span>;
}

function RoleBadge({ role }: { role: string }) {
  if (role === "superadmin") return <span className="badge roleSuperadmin">{role}</span>;
  if (role === "admin") return <span className="badge roleAdmin">{role}</span>;
  return <span className="badge roleUser">{role}</span>;
}

function AdminTaskStatusBadge({ task }: { task: TaskRead }) {
  if (task.deleted_at) return <span className="badge mutedBadge">удалена</span>;
  return <StatusBadge active={task.is_active} />;
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
