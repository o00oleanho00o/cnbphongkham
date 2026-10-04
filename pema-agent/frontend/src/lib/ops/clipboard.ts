/**
 * Copy text for a staff member to paste into Zalo or SMS by hand. `navigator.clipboard` only exists in a
 * secure context (HTTPS or localhost); the clinic may open the dashboard over plain HTTP on the LAN, so
 * fall back to a hidden textarea and `execCommand("copy")`. Resolves to whether the copy worked.
 */
export async function copyText(text: string): Promise<boolean> {
  if (typeof navigator !== "undefined" && navigator.clipboard && window.isSecureContext) {
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch {
      /* permission denied: try the fallback */
    }
  }
  return copyWithTextarea(text);
}

function copyWithTextarea(text: string): boolean {
  const area = document.createElement("textarea");
  area.value = text;
  area.setAttribute("readonly", "");
  area.style.position = "fixed";
  area.style.opacity = "0";
  document.body.appendChild(area);
  area.select();
  try {
    return document.execCommand("copy");
  } catch {
    return false;
  } finally {
    document.body.removeChild(area);
  }
}

const QUOTED = /[“"]([^”"]{8,})[”"]/;

/**
 * The text to paste for a hand-sent task. The rules write the message between typographic quotes inside
 * `suggested_action` ("Nhắn Zalo ...: “Chào chị ...”"); without a quote the whole instruction is copied.
 * Open item for B1: a dedicated `message_body` on the task.
 */
export function messageToCopy(suggestedAction: string): string {
  return QUOTED.exec(suggestedAction)?.[1]?.trim() ?? suggestedAction.trim();
}
