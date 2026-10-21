import { useI18n } from '../i18n';

// A small tinted chip for a state: working, idle, error, open or offline.
export function Chip({ state }: { state: string }) {
  const { t } = useI18n();
  return <span className={`chip chip-${state}`}>{t(`state.${state}`)}</span>;
}
