// Zentrale Übersetzungen: alle Oberflächentexte stehen in i18n/de.json und
// i18n/en.json. Im Code steht nur noch die Funktion t mit dem Schlüssel.

let messages = {};
let fallback = {};
let language = 'de';

export const LANGUAGES = [['de', 'Deutsch'], ['en', 'English']];

async function loadDictionary(code) {
  const response = await fetch(`/assets/i18n/${code}.json`);
  if (!response.ok) throw new Error(`Sprachdatei ${code}.json fehlt`);
  return response.json();
}

/** Lädt die gewählte Sprache; Deutsch dient als Rückfall für fehlende Schlüssel. */
export async function initI18n(code = 'de') {
  language = LANGUAGES.some(([value]) => value === code) ? code : 'de';
  try {
    fallback = await loadDictionary('de');
    messages = language === 'de' ? fallback : await loadDictionary(language);
  } catch (error) {
    console.error(error);
    messages = fallback;
  }
  document.documentElement.lang = language;
  applyStaticTranslations();
}

export const getLanguage = () => language;

/** Übersetzt einen Schlüssel; {name}-Platzhalter werden ersetzt. Nie null/undefined. */
export function t(key, params = {}) {
  const text = messages[key] ?? fallback[key] ?? key;
  return String(text).replace(/\{(\w+)\}/g, (match, name) => {
    const value = params[name];
    return value === undefined || value === null ? '' : String(value);
  });
}

/** Statische Texte in index.html: data-i18n, data-i18n-title, data-i18n-placeholder, data-i18n-label. */
export function applyStaticTranslations(root = document) {
  for (const node of root.querySelectorAll('[data-i18n]')) node.textContent = t(node.dataset.i18n);
  for (const attribute of ['title', 'placeholder']) {
    for (const node of root.querySelectorAll(`[data-i18n-${attribute}]`)) {
      node.setAttribute(attribute, t(node.dataset[`i18n${attribute[0].toUpperCase()}${attribute.slice(1)}`]));
    }
  }
  for (const node of root.querySelectorAll('[data-i18n-label]')) node.setAttribute('aria-label', t(node.dataset.i18nLabel));
  document.title = t('app.title');
}

const LOCALES = { de: 'de-DE', en: 'en-GB' };
export const locale = () => LOCALES[language] || 'de-DE';
