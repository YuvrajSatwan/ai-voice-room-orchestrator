const NAME_KEY = 'roxstar.name';

/** The last name used, so it's prefilled next time. Private mode just means no prefill. */
export function storedName(): string {
  try {
    return localStorage.getItem(NAME_KEY) ?? '';
  } catch {
    return '';
  }
}

export function rememberName(name: string): void {
  try {
    localStorage.setItem(NAME_KEY, name);
  } catch {
    /* only a convenience */
  }
}
