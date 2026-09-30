import de from "../de.json";
import en from "../en.json";

export type Locale = "de" | "en";

export const dictionaries = { de, en } as const;

type I18nKeysMatch<A, B> = keyof A extends keyof B ? (keyof B extends keyof A ? true : false) : false;

true satisfies I18nKeysMatch<typeof dictionaries.de, typeof dictionaries.en>;

export type TranslationKey = keyof typeof dictionaries.de;

export function t(locale: Locale, key: TranslationKey, vars?: Record<string, string>): string {
  let out: string = dictionaries[locale][key];
  if (vars) {
    for (const [name, value] of Object.entries(vars)) {
      out = out.replaceAll(`{{${name}}}`, value);
    }
  }
  return out;
}
