"use client";

// The two small forms of the resources screen: a treatment room (`POST /api/v1/rooms`, `PATCH /rooms/{room_id}`)
// and a room block ("Khóa phòng", `POST /api/v1/room-blocks`). Owner and manager only (`admin.rules`). A block
// stays inside 08:00-18:00 and needs a reason, like the old web's `block()`; the backend checks it again.
import { useState, type FormEvent } from "react";

import { Notice, PrimaryButton, SecondaryButton } from "@/components/ops/ops-ui";
import { Sheet } from "@/components/ops/sheet";
import { useToast } from "@/components/ops/toast";
import { http, unwrap } from "@/lib/api/client";
import {
  BLOCK_WINDOW,
  catalogErrorMessage,
  catalogStale,
  validateBlockForm,
  type BlockForm,
  type RoomRow,
} from "@/lib/catalog/catalog-view";
import { Field, FIELD_CONTROL_CLASS } from "@/ui/field";

const ROOM_NAME_PROBLEM = "Nhập tên phòng và sức chứa từ 1 đến 20.";

export function RoomSheet({
  room,
  onClose,
  onSaved,
  onStale,
}: {
  /** null = add a new room */
  room: RoomRow | null;
  onClose: () => void;
  onSaved: () => void;
  onStale: () => void;
}) {
  const toast = useToast();
  const [name, setName] = useState(room?.name ?? "");
  const [capacity, setCapacity] = useState(String(room?.capacity ?? 1));
  const [active, setActive] = useState(room?.active ?? true);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function save(e: FormEvent) {
    e.preventDefault();
    setError("");
    const seats = Number(capacity);
    if (name.trim() === "" || !Number.isInteger(seats) || seats < 1 || seats > 20) {
      setError(ROOM_NAME_PROBLEM);
      return;
    }
    setBusy(true);
    try {
      if (room === null) {
        await unwrap(http.POST("/api/v1/rooms", { body: { name: name.trim(), capacity: seats } }));
        toast.push("success", "Đã thêm phòng.");
      } else {
        await unwrap(
          http.PATCH("/api/v1/rooms/{room_id}", {
            params: { path: { room_id: room.id } },
            body: { version: room.version, name: name.trim(), capacity: seats, active },
          }),
        );
        toast.push("success", "Đã lưu phòng.");
      }
      onSaved();
    } catch (err) {
      setError(catalogErrorMessage(err));
      if (catalogStale(err)) onStale();
    } finally {
      setBusy(false);
    }
  }

  return (
    <Sheet
      title={room ? "Sửa phòng" : "Thêm phòng"}
      onClose={onClose}
      footer={
        <>
          <SecondaryButton onClick={onClose} disabled={busy}>
            Hủy
          </SecondaryButton>
          <PrimaryButton type="submit" form="room-form" disabled={busy}>
            {busy ? "Đang lưu..." : "Lưu phòng"}
          </PrimaryButton>
        </>
      }
    >
      <form id="room-form" onSubmit={(e) => void save(e)} noValidate>
        <Field label="Tên phòng" required>
          {(control) => (
            <input
              {...control}
              value={name}
              onChange={(e) => setName(e.target.value)}
              maxLength={120}
              autoComplete="off"
              className={FIELD_CONTROL_CLASS}
            />
          )}
        </Field>
        <Field label="Sức chứa (người)">
          {(control) => (
            <input
              {...control}
              type="number"
              inputMode="numeric"
              value={capacity}
              onChange={(e) => setCapacity(e.target.value)}
              className={FIELD_CONTROL_CLASS}
            />
          )}
        </Field>
        {room && (
          <label className="mb-3.5 inline-flex min-h-9 items-center gap-2 text-body text-ink">
            <input
              type="checkbox"
              checked={active}
              onChange={(e) => setActive(e.target.checked)}
              className="h-4 w-4 accent-brand-500"
            />
            Đang dùng (bỏ chọn để tạm ngưng, không đặt lịch vào phòng này)
          </label>
        )}
        {error && <Notice tone="error">{error}</Notice>}
      </form>
    </Sheet>
  );
}

export function BlockSheet({
  rooms,
  defaultDay,
  onClose,
  onSaved,
}: {
  rooms: readonly RoomRow[];
  defaultDay: string;
  onClose: () => void;
  onSaved: () => void;
}) {
  const toast = useToast();
  const [form, setForm] = useState<BlockForm>({
    roomId: rooms.find((r) => r.active)?.id ?? "",
    day: defaultDay,
    start: "14:00",
    end: "15:00",
    reason: "",
  });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const set = <K extends keyof BlockForm>(key: K, value: BlockForm[K]) =>
    setForm((current) => ({ ...current, [key]: value }));

  async function save(e: FormEvent) {
    e.preventDefault();
    const problem = validateBlockForm(form);
    setError(problem);
    if (problem !== "") return;
    setBusy(true);
    try {
      await unwrap(
        http.POST("/api/v1/room-blocks", {
          body: {
            room_id: form.roomId,
            day: form.day,
            start: form.start,
            end: form.end,
            reason: form.reason.trim(),
          },
        }),
      );
      toast.push("success", "Đã khóa phòng.");
      onSaved();
    } catch (err) {
      setError(catalogErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Sheet
      title="Khóa phòng"
      subtitle={`Phòng không đặt lịch được trong khoảng này (${BLOCK_WINDOW.from}–${BLOCK_WINDOW.to}).`}
      onClose={onClose}
      footer={
        <>
          <SecondaryButton onClick={onClose} disabled={busy}>
            Hủy
          </SecondaryButton>
          <PrimaryButton type="submit" form="block-form" disabled={busy}>
            {busy ? "Đang lưu..." : "Khóa phòng"}
          </PrimaryButton>
        </>
      }
    >
      <form id="block-form" onSubmit={(e) => void save(e)} noValidate>
        <Field label="Phòng">
          {(control) => (
            <select
              {...control}
              value={form.roomId}
              onChange={(e) => set("roomId", e.target.value)}
              className={FIELD_CONTROL_CLASS}
            >
              {rooms.map((room) => (
                <option key={room.id} value={room.id}>
                  {room.name}
                </option>
              ))}
            </select>
          )}
        </Field>
        <div className="grid grid-cols-1 gap-x-4 sm:grid-cols-3">
          <Field label="Ngày">
            {(control) => (
              <input
                {...control}
                type="date"
                value={form.day}
                onChange={(e) => set("day", e.target.value)}
                className={FIELD_CONTROL_CLASS}
              />
            )}
          </Field>
          <Field label="Từ">
            {(control) => (
              <input
                {...control}
                type="time"
                value={form.start}
                onChange={(e) => set("start", e.target.value)}
                className={FIELD_CONTROL_CLASS}
              />
            )}
          </Field>
          <Field label="Đến">
            {(control) => (
              <input
                {...control}
                type="time"
                value={form.end}
                onChange={(e) => set("end", e.target.value)}
                className={FIELD_CONTROL_CLASS}
              />
            )}
          </Field>
        </div>
        <Field label="Lý do" required>
          {(control) => (
            <input
              {...control}
              value={form.reason}
              onChange={(e) => set("reason", e.target.value)}
              maxLength={200}
              autoComplete="off"
              className={FIELD_CONTROL_CLASS}
            />
          )}
        </Field>
        {error && <Notice tone="error">{error}</Notice>}
      </form>
    </Sheet>
  );
}
