import type { JudgmentRecord, KeyFactor } from '@/types';

/**
 * Safely parse JSON fields that might be stored as strings (possibly double-encoded).
 * Extracted from JudgmentPanel for reuse across analytics components.
 */
export function safeParseJson<T>(value: T | string | null | undefined, fallback: T): T {
  if (value === null || value === undefined) return fallback;
  if (typeof value !== 'string') return value;

  // Try parsing up to 2 times because Supabase JSONB columns sometimes
  // arrive as double-encoded strings (e.g. '"{\"key\":\"val\"}"') when
  // the Python backend stores pre-serialized JSON via supabase-py.
  let result: any = value;
  for (let i = 0; i < 2; i++) {
    if (typeof result !== 'string') break;
    try {
      result = JSON.parse(result);
    } catch {
      break;
    }
  }

  if (typeof result !== 'string') {
    return result as T;
  }

  return fallback;
}

export function parseKeyFactors(value: KeyFactor[] | string | null | undefined): KeyFactor[] {
  return safeParseJson(value, []);
}

export function parseRisks(value: string[] | string | null | undefined): string[] {
  return safeParseJson(value, []);
}

export function parseReasoning(
  value: JudgmentRecord['reasoning'] | string | null | undefined
): JudgmentRecord['reasoning'] | null {
  if (!value) return null;
  return safeParseJson(value, null);
}
