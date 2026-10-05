"use client";

// One live region for "đã sao chép", "đã lưu", "đã gửi". Every timer is cleared on unmount.
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";

type ToastTone = "success" | "error" | "info";
type ToastItem = { id: number; tone: ToastTone; text: string };

const TOAST_MS = 4000;

const TONE_CLASS: Record<ToastTone, string> = {
  success: "bg-success text-surface",
  error: "bg-danger text-surface",
  info: "bg-ink text-surface",
};

type ToastApi = { push: (tone: ToastTone, text: string) => void };

const ToastContext = createContext<ToastApi>({ push: () => undefined });

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);
  const nextId = useRef(1);
  const timers = useRef(new Map<number, ReturnType<typeof setTimeout>>());

  const push = useCallback((tone: ToastTone, text: string) => {
    const id = nextId.current;
    nextId.current += 1;
    setItems((current) => [...current.slice(-2), { id, tone, text }]);
    timers.current.set(
      id,
      setTimeout(() => {
        setItems((current) => current.filter((item) => item.id !== id));
        timers.current.delete(id);
      }, TOAST_MS),
    );
  }, []);

  useEffect(() => {
    const pending = timers.current;
    return () => {
      pending.forEach((timer) => clearTimeout(timer));
      pending.clear();
    };
  }, []);

  const api = useMemo(() => ({ push }), [push]);

  return (
    <ToastContext.Provider value={api}>
      {children}
      <div
        aria-live="polite"
        className="pointer-events-none fixed inset-x-0 bottom-20 z-[70] flex flex-col items-center gap-2 px-4 lg:bottom-6"
      >
        {items.map((item) => (
          <div
            key={item.id}
            className={`pointer-events-auto max-w-sm rounded-tile px-4 py-2.5 text-small font-medium shadow-lg ${TONE_CLASS[item.tone]}`}
          >
            {item.text}
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast(): ToastApi {
  return useContext(ToastContext);
}
