/**
 * SSRF guard for `send-video`.
 *
 * New module (no TS original; the original guarded its video URLs with a domain whitelist in
 * `tai-video-tool.ts`, which stays in the Python tool). zca-js' `sendVideo` makes a HEAD request to
 * `videoUrl` from THIS host, so a URL that points at loopback, the private network or the cloud metadata
 * address would let a caller probe the clinic's internal network. The bridge therefore accepts only
 * http(s) URLs whose host resolves exclusively to public addresses. (A DNS answer can change between this
 * check and zca-js' request; the API's own guard and the loopback-only bind are the other layers.)
 */
import { lookup } from "node:dns/promises";
import { isIP } from "node:net";

export type HostLookup = (hostname: string) => Promise<string[]>;

export const lookupAddresses: HostLookup = async (hostname) => {
  const results = await lookup(hostname, { all: true });
  return results.map((entry) => entry.address);
};

function isPrivateIpv4(address: string): boolean {
  const [a = 0, b = 0] = address.split(".").map(Number);
  if (a === 0 || a === 10 || a === 127) return true;
  if (a === 169 && b === 254) return true; // link-local, cloud metadata
  if (a === 172 && b >= 16 && b <= 31) return true;
  if (a === 192 && b === 168) return true;
  if (a === 100 && b >= 64 && b <= 127) return true; // carrier-grade NAT
  if (a === 198 && (b === 18 || b === 19)) return true; // benchmarking
  return a >= 224; // multicast and reserved
}

function isPrivateIpv6(address: string): boolean {
  const lower = address.toLowerCase();
  if (lower === "::" || lower === "::1") return true;
  const mapped = /^::ffff:(\d+\.\d+\.\d+\.\d+)$/.exec(lower);
  if (mapped?.[1]) return isPrivateIpv4(mapped[1]);
  if (lower.startsWith("fe8") || lower.startsWith("fe9")) return true;
  if (lower.startsWith("fea") || lower.startsWith("feb")) return true; // fe80::/10 link-local
  return lower.startsWith("fc") || lower.startsWith("fd"); // fc00::/7 unique local
}

export function isPrivateAddress(address: string): boolean {
  const version = isIP(address);
  if (version === 4) return isPrivateIpv4(address);
  if (version === 6) return isPrivateIpv6(address);
  return true; // not an address we can reason about: refuse
}

export type UrlVerdict = { ok: true } | { ok: false; message: string };

export async function checkPublicHttpUrl(raw: string, resolve: HostLookup): Promise<UrlVerdict> {
  const url = URL.parse(raw);
  if (!url) return { ok: false, message: "video_url is not a valid URL" };
  if (url.protocol !== "https:" && url.protocol !== "http:") {
    return { ok: false, message: "video_url must be http or https" };
  }
  if (url.username || url.password) {
    return { ok: false, message: "video_url must not carry credentials" };
  }
  const hostname = url.hostname.replace(/^\[|\]$/g, "");
  if (hostname === "localhost" || hostname.endsWith(".localhost")) {
    return { ok: false, message: "video_url host is not public" };
  }
  try {
    const addresses = isIP(hostname) ? [hostname] : await resolve(hostname);
    if (addresses.length === 0 || addresses.some(isPrivateAddress)) {
      return { ok: false, message: "video_url host is not public" };
    }
    return { ok: true };
  } catch {
    return { ok: false, message: "video_url host could not be resolved" };
  }
}
