// Formatters that know nothing of the vault (ARCHITECTURE.md §2.1, shared).

/** "1 line", "2 lines", "0 lines". */
export function plural(n: number, word: string): string {
  return `${n} ${word}${n === 1 ? '' : 's'}`
}

export function isLink(s: string): boolean {
  return /^https?:\/\//.test(s)
}

/** An obsidian:// link to a vault path. */
export function obsidianLink(path: string): string {
  return `obsidian://open?file=${encodeURIComponent(path)}`
}

/** Lower case, each run of other characters one "-", none at the ends. */
export function slug(s: string): string {
  return s.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '')
}
