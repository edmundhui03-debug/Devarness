import { describe, expect, it } from 'vitest';
import { act, renderHook } from '@testing-library/react';
import en from './en.json';
import zh from './zh-HK.json';
import { errorCode } from '../api';
import { I18nProvider, translate, useI18n } from '.';

describe('the two string tables', () => {
  it('hold the same keys, none empty', () => {
    expect(Object.keys(zh).sort()).toEqual(Object.keys(en).sort());
    for (const [k, v] of Object.entries({ ...en, ...zh })) expect(v.trim(), k).not.toBe('');
  });
  it('translate every English string with words in it', () => {
    const same = Object.keys(en).filter((k) => (en as Record<string, string>)[k] === (zh as Record<string, string>)[k] && /[a-z]{4,}/.test((en as Record<string, string>)[k]));
    expect(same).toEqual([]);
  });
  it('word every error code the server sends, and make any other code \'other\'', () => {
    for (const code of ['forbidden', 'internal', 'thread-busy', 'not-found', 'bad-request']) expect(errorCode({ code })).toBe(code);
    for (const err of [{ code: 'no-such-code' }, { code: 404 }, new TypeError('offline'), null]) expect(errorCode(err)).toBe('other');
  });
  it('fill named values and fall back to English, then to the key', () => {
    expect(translate('en', 'agent.questions', { n: 2 })).toBe('Open questions: 2');
    expect(translate('zh-HK', 'no.such.key')).toBe('no.such.key');
  });
});

describe('the language provider', () => {
  it('keeps <html lang> in step with the saved language and with every switch', () => {
    localStorage.setItem('dash.lang', 'zh-HK');
    const { result } = renderHook(() => useI18n(), { wrapper: I18nProvider });
    expect(document.documentElement.lang).toBe('zh-HK');
    act(() => result.current.setLang('en'));
    expect(document.documentElement.lang).toBe('en');
  });
});
