// ported from: web/src/pages/change-password-section.tsx
"use client";

import { useState } from "react";
import { IconLock } from "@/components/admin/shared/dashboard-icons";
import { SecretInput } from "@/components/admin/shared/secret-input";

/**
 * Port note: the OpenAPI contract has no change-password operation yet (open item for B1), so the form is
 * shown but disabled with a plain explanation instead of calling an endpoint that does not exist.
 *
 * Đổi mật khẩu dashboard. Nằm ở trang Cấu hình vì đây cũng là một thứ trước
 * đây chỉ sửa được bằng cách mở `.env` rồi khởi động lại bot.
 *
 * Bắt nhập lại mật khẩu hiện tại (server cũng kiểm, đây chỉ là lớp giao diện):
 * người ngồi vào máy đang mở sẵn dashboard không được phép đổi mật khẩu rồi
 * khoá chủ thật ra ngoài.
 */
/** Flip to true when the BE adds `POST /auth/password` (and regenerate the types). */
const CHANGE_PASSWORD_SUPPORTED = false;

export function ChangePasswordSection() {
  const [hienTai, setHienTai] = useState("");
  const [moi, setMoi] = useState("");
  const [nhapLai, setNhapLai] = useState("");
  const [loi, setLoi] = useState("");
  const [xong, setXong] = useState("");
  const [dangGui, setDangGui] = useState(false);

  const chuaDu = !CHANGE_PASSWORD_SUPPORTED || !hienTai || !moi || !nhapLai;

  async function doiMatKhau() {
    setLoi("");
    setXong("");

    // Kiểm ở đây chứ không gửi lên: đây là lỗi gõ nhầm, không phải việc của
    // server - và server không có cách nào biết người dùng định gõ gì
    if (moi !== nhapLai) {
      setLoi("Hai ô mật khẩu mới không giống nhau.");
      return;
    }
    if (moi.length < 8) {
      setLoi("Mật khẩu mới phải từ 8 ký tự.");
      return;
    }

    setDangGui(true);
    try {
      if (!CHANGE_PASSWORD_SUPPORTED)
        throw new Error("Máy chủ chưa hỗ trợ đổi mật khẩu từ giao diện.");
      setHienTai("");
      setMoi("");
      setNhapLai("");
      setXong("Đã đổi mật khẩu. Các thiết bị khác đang đăng nhập sẽ phải đăng nhập lại.");
    } catch (e) {
      setLoi((e as Error).message);
    } finally {
      setDangGui(false);
    }
  }

  return (
    <section>
      <div className="mb-4">
        <div className="flex items-center gap-2 text-[15px] font-semibold text-ink">
          <IconLock size={16} className="text-ink-soft" />
          Mật khẩu dashboard
        </div>
        <p className="mt-1.5 max-w-3xl text-[13px] leading-[1.7] text-ink-soft">
          Đổi mật khẩu đăng nhập trang này. Đổi xong, mọi thiết bị khác đang đăng nhập sẽ bị đăng
          xuất.
        </p>
      </div>

      {!CHANGE_PASSWORD_SUPPORTED && (
        <div className="mb-3 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-[13px] text-amber-800 dark:border-amber-900/50 dark:bg-amber-950/40 dark:text-amber-200">
          Chức năng đổi mật khẩu đang chờ máy chủ cung cấp. Trong lúc này, nhờ chủ phòng khám đặt
          lại mật khẩu.
        </div>
      )}

      {loi && (
        <div className="mb-3 rounded-lg border border-red-100 bg-red-50 px-3 py-2 text-[13px] text-red-700 dark:border-red-900/50 dark:bg-red-950/40 dark:text-red-300">
          {loi}
        </div>
      )}
      {xong && (
        <div className="mb-3 rounded-lg border border-emerald-100 bg-emerald-50 px-3 py-2 text-[13px] text-emerald-800 dark:border-emerald-900/50 dark:bg-emerald-950/40 dark:text-emerald-200">
          {xong}
        </div>
      )}

      <div className="max-w-2xl">
        <label className="block">
          <span className="mb-2 block text-[13px] font-medium text-ink">Mật khẩu hiện tại</span>
          {/* Ô này để MỘT MÌNH một hàng: nó xác minh danh tính, khác vai với cặp
              "mật khẩu mới" bên dưới - xếp chung hàng làm ba ô trông như một bộ */}
          <SecretInput
            className="sm:max-w-md"
            value={hienTai}
            onChange={setHienTai}
            placeholder="Nhập mật khẩu hiện tại"
          />
        </label>

        {/* Mật khẩu mới + nhập lại nằm CẠNH nhau: chúng phải khớp nhau nên đặt
            sát để mắt so được, thay vì cuộn dọc qua ba ô rời rạc */}
        <div className="mt-4 grid gap-4 sm:grid-cols-2">
          <label className="block">
            <span className="mb-2 block text-[13px] font-medium text-ink">Mật khẩu mới</span>
            <SecretInput value={moi} onChange={setMoi} placeholder="Nhập mật khẩu mới" />
            <span className="mt-2 block text-[12px] text-ink-soft">Tối thiểu 8 ký tự.</span>
          </label>
          <label className="block">
            <span className="mb-2 block text-[13px] font-medium text-ink">
              Nhập lại mật khẩu mới
            </span>
            <SecretInput
              value={nhapLai}
              onChange={setNhapLai}
              placeholder="Nhập lại mật khẩu mới"
            />
          </label>
        </div>

        <button
          type="button"
          onClick={() => void doiMatKhau()}
          disabled={dangGui || chuaDu}
          className="mt-5 inline-flex items-center gap-2 rounded-xl bg-brand-500 px-4 py-2.5 text-[13px] font-semibold text-white hover:bg-brand-600 disabled:opacity-50"
        >
          <IconLock size={15} />
          {dangGui ? "Đang đổi..." : "Đổi mật khẩu"}
        </button>
      </div>
    </section>
  );
}
