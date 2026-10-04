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

/**
 * Expand an IPv6 literal to its 16 bytes (`::` compression and an embedded dotted IPv4 tail included), or
 * `null` when it is not an address. The WHATWG URL parser writes `[::ffff:127.0.0.1]` as the hex form
 * `[::ffff:7f00:1]`, so the guard must read bytes: matching only the dotted text let that URL through.
 */
function ipv6Bytes(address: string): number[] | null {
  let text = address.toLowerCase().split("%")[0] ?? "";
  const tail: number[] = [];
  const dotted = /^(.*:)(\d+\.\d+\.\d+\.\d+)$/.exec(text);
  if (dotted?.[1] && dotted[2]) {
    const octets = dotted[2].split(".").map(Number);
    if (octets.length !== 4 || octets.some((o) => !Number.isInteger(o) || o < 0 || o > 255))
      return null;
    tail.push((octets[0] ?? 0) * 256 + (octets[1] ?? 0), (octets[2] ?? 0) * 256 + (octets[3] ?? 0));
    text = dotted[1].endsWith("::") ? dotted[1] : dotted[1].slice(0, -1);
  }
  const halves = text.split("::");
  if (halves.length > 2) return null;
  const groups = (part: string | undefined): string[] => (part ? part.split(":") : []);
  const head = groups(halves[0]);
  const rest = halves.length === 2 ? groups(halves[1]) : [];
  const missing = 8 - head.length - rest.length - tail.length;
  if (halves.length === 1 ? missing !== 0 : missing < 0) return null;
  const words = [...head, ...Array<string>(halves.length === 2 ? missing : 0).fill("0"), ...rest];
  const out: number[] = [];
  for (const word of words) {
    if (!/^[0-9a-f]{1,4}$/.test(word)) return null;
    const value = parseInt(word, 16);
    out.push(value >> 8, value & 255);
  }
  for (const word of tail) out.push(word >> 8, word & 255);
  return out.length === 16 ? out : null;
}

function isPrivateIpv6(address: string): boolean {
  const bytes = ipv6Bytes(address);
  if (!bytes) return true; // not an address we can reason about: refuse
  const at = (index: number): number => bytes[index] ?? 0;
  const v4 = (offset: number): string =>
    `${at(offset)}.${at(offset + 1)}.${at(offset + 2)}.${at(offset + 3)}`;
  // ::/96 holds `::` and `::1` and the deprecated IPv4-compatible form: none of it is a public host.
  if (bytes.slice(0, 12).every((b) => b === 0)) return true;
  // ::ffff:0:0/96 (IPv4-mapped) and 64:ff9b::/96 (NAT64): judged by the IPv4 address inside.
  if (bytes.slice(0, 10).every((b) => b === 0) && at(10) === 0xff && at(11) === 0xff)
    return isPrivateIpv4(v4(12));
  if (at(0) === 0 && at(1) === 0x64 && at(2) === 0xff && at(3) === 0x9b) {
    return bytes.slice(4, 12).every((b) => b === 0) ? isPrivateIpv4(v4(12)) : true; // 64:ff9b:1::/48 is local-use
  }
  if (at(0) === 0x20 && at(1) === 0x02) return isPrivateIpv4(v4(2)); // 6to4 embeds an IPv4 address
  if (at(0) === 0x20 && at(1) === 0x01 && at(2) === 0 && at(3) === 0) return true; // Teredo
  if (at(0) === 0x20 && at(1) === 0x01 && at(2) === 0x0d && at(3) === 0xb8) return true; // documentation
  if (at(0) === 0x01 && bytes.slice(1, 8).every((b) => b === 0)) return true; // 100::/64 discard
  if ((at(0) & 0xfe) === 0xfc) return true; // fc00::/7 unique local
  if (at(0) === 0xfe && (at(1) & 0xc0) !== 0x00) return true; // fe80::/10 link-local, fec0::/10 site-local
  return at(0) === 0xff; // ff00::/8 multicast
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
