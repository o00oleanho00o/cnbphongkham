// Pure rules of the staff screen (`/admin/users`). The backend owns every rule (who may list, who may change,
// no self-lock, one active owner at least, sessions ended on a lock or a role change); this file only decides
// what the screen SHOWS and how it words the backend's answers, so a hidden button is a convenience and never a
// control. Backend: `dashboard_staff_store.py`, `routers/admin_users.py`.
import type { Schemas } from "@/lib/api";
import { ApiError } from "@/lib/api/client";

export type StaffUser = Schemas["StaffUserOut"];
export type StaffRole = Exclude<Schemas["Role"], "patient">;
export type StatusFilter = "all" | "active" | "locked";
export type RoleFilter = "all" | StaffRole;

export const STAFF_ROLES: readonly StaffRole[] = [
  "owner",
  "manager",
  "doctor",
  "cs_staff",
  "reception",
  "accountant",
];

/** The list never holds a patient (the backend filters them out); `reception`, the role with the fewest
 * permissions, is the harmless fallback if a future contract ever sent something else. */
export function asStaffRole(value: string): StaffRole {
  return STAFF_ROLES.find((role) => role === value) ?? "reception";
}

export const MIN_PASSWORD_LENGTH = 8;
export const MAX_NAME_LENGTH = 120;
export const PAGE_SIZE = 50;

const EMAIL_PATTERN = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

/** One line per role, shown under the role picker so the owner knows what they are granting. */
export const ROLE_HINT: Record<StaffRole, string> = {
  owner: "Toàn quyền, kể cả thêm, khóa và đặt lại mật khẩu nhân viên.",
  manager: "Quản trị AI và xem danh sách nhân viên; không sửa được tài khoản nhân viên.",
  doctor: "Hồ sơ bệnh nhân mình phụ trách, duyệt nội dung lâm sàng.",
  cs_staff: "Chăm sóc khách hàng: việc hôm nay, Inbox, duyệt tin thường.",
  reception: "Lễ tân: danh tính bệnh nhân, đặt lịch và check-in.",
  accountant:
    "Kế toán: đối soát và thu ngân, tài chính, chốt kỳ; không duyệt đơn thuốc, không xem hồ sơ lâm sàng.",
};

export const STATUS_FILTER_LABEL: Record<StatusFilter, string> = {
  all: "Mọi trạng thái",
  active: "Đang hoạt động",
  locked: "Đã khóa",
};

const ACTIVE_FILTER: Record<StatusFilter, boolean | undefined> = {
  all: undefined,
  active: true,
  locked: false,
};

/** `active` query parameter of `GET /admin/users` for a status chip (`undefined` = no filter). */
export function activeQuery(status: StatusFilter): boolean | undefined {
  return ACTIVE_FILTER[status];
}

export type RowActions = {
  /** "Sửa": name, and role unless it is your own account. */
  edit: boolean;
  /** Role may be changed in the edit form (the backend refuses it for your own account). */
  editRole: boolean;
  resetPassword: boolean;
  toggleLock: boolean;
};

const NO_ACTIONS: RowActions = {
  edit: false,
  editRole: false,
  resetPassword: false,
  toggleLock: false,
};

/**
 * Which buttons a row shows. Changes need `admin.users` (the owner's alone); the account of the person looking
 * is protected the way the backend protects it: no lock, no role change, and no reset (their own password is
 * changed in "Tài khoản của tôi", which asks for the current one).
 */
export function rowActions(
  user: Pick<StaffUser, "id">,
  viewer: { id: string; canManage: boolean },
): RowActions {
  if (!viewer.canManage) return NO_ACTIONS;
  const own = user.id === viewer.id;
  return { edit: true, editRole: !own, resetPassword: !own, toggleLock: !own };
}

export type StaffForm = {
  displayName: string;
  email: string;
  role: StaffRole;
  password: string;
  passwordAgain: string;
};

export function validatePasswordPair(password: string, again: string): string | null {
  if (password.length < MIN_PASSWORD_LENGTH) {
    return `Mật khẩu cần ít nhất ${MIN_PASSWORD_LENGTH} ký tự.`;
  }
  if (password !== again) return "Hai ô mật khẩu chưa giống nhau.";
  return null;
}

/** Client-side check of the create form; the backend checks again and its message wins. */
export function validateCreate(form: StaffForm): string | null {
  if (!form.displayName.trim()) return "Hãy nhập họ tên.";
  if (!EMAIL_PATTERN.test(form.email.trim()))
    return "Email đăng nhập chưa đúng dạng, ví dụ ten@phongkham.vn.";
  return validatePasswordPair(form.password, form.passwordAgain);
}

export type StaffUpdate = {
  version: number;
  display_name?: string;
  role?: StaffRole;
};

/** Only what changed; `null` = nothing to save. The role is left out when the caller may not change it. */
export function buildUpdate(
  original: StaffUser,
  form: Pick<StaffForm, "displayName" | "role">,
  canEditRole: boolean,
): StaffUpdate | null {
  const name = form.displayName.trim();
  const nameChange = name !== "" && name !== original.display_name ? { display_name: name } : {};
  const roleChange = canEditRole && form.role !== original.role ? { role: form.role } : {};
  const changes = { ...nameChange, ...roleChange };
  return Object.keys(changes).length === 0 ? null : { version: original.version, ...changes };
}

export function lastLoginLabel(
  user: Pick<StaffUser, "last_login_at">,
  format: (iso: string) => string,
): string {
  return user.last_login_at
    ? `Đăng nhập cuối ${format(user.last_login_at)}`
    : "Chưa đăng nhập lần nào";
}

const STATUS_MESSAGE: Partial<Record<number, string>> = {
  403: "Bạn không có quyền thực hiện thao tác này.",
  404: "Không tìm thấy tài khoản này. Danh sách đã được tải lại.",
  429: "Bạn thao tác quá nhanh. Hãy đợi một phút rồi thử lại.",
};

const CONFLICT_MESSAGE =
  "Tài khoản vừa được người khác thay đổi. Danh sách đã được tải lại, hãy thử lại.";

/**
 * Words an answer of the backend. 409 (taken e-mail, stale version) and 422 (own account, last owner, short
 * password, bad body) carry a specific Vietnamese sentence from the backend, which is the clearest thing to
 * show; 403, 404 and 429 get a fixed sentence so a proxy's wording never reaches the person.
 */
export function staffErrorMessage(error: unknown): string {
  if (!(error instanceof ApiError)) return "Có lỗi xảy ra. Hãy thử lại.";
  if (error.code === "version_conflict") return CONFLICT_MESSAGE;
  const fixed = STATUS_MESSAGE[error.status];
  if (fixed) return fixed;
  if (error.status === 409 || error.status === 422) return error.message;
  if (error.status === 0) return error.message;
  return "Có lỗi xảy ra. Hãy thử lại.";
}

/** The answers after which the list on screen is stale and should be reloaded. */
export function staleAfter(error: unknown): boolean {
  if (!(error instanceof ApiError)) return false;
  return error.code === "version_conflict" || error.status === 404;
}

export function lockConfirmation(user: Pick<StaffUser, "display_name" | "active">): {
  title: string;
  message: string;
  confirmLabel: string;
  tone: "danger" | "normal";
} {
  if (user.active) {
    return {
      title: `Khóa tài khoản của ${user.display_name}?`,
      message:
        "Người này sẽ bị đăng xuất khỏi mọi thiết bị ngay và không đăng nhập được cho đến khi bạn mở khóa. Dữ liệu và nhật ký của họ được giữ nguyên.",
      confirmLabel: "Khóa tài khoản",
      tone: "danger",
    };
  }
  return {
    title: `Mở khóa tài khoản của ${user.display_name}?`,
    message:
      "Người này đăng nhập lại được bằng mật khẩu hiện tại. Mọi phiên cũ đã bị đăng xuất khi khóa, nên họ cần đăng nhập mới.",
    confirmLabel: "Mở khóa",
    tone: "normal",
  };
}
