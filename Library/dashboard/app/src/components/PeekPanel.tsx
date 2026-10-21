import { useEffect, useRef, type ReactNode } from 'react';
import { X } from 'lucide-react';
import { useI18n } from '../i18n';

type Props = { address: string; label: string; head: ReactNode; onClose: () => void; children: ReactNode };

// The detail panel over or beside the board: opened by the address, closed by
// Esc or its button, and focus goes back to whatever opened it.
export function PeekPanel({ address, label, head, onClose, children }: Props) {
  const { t } = useI18n();
  const ref = useRef<HTMLDivElement>(null);
  const opener = useRef<HTMLElement | null>(null);
  useEffect(() => {
    // A link inside the panel that opens another item keeps the first opener, as
    // does a button the change removed (focus then falls back to the body).
    const active = document.activeElement;
    if (active instanceof HTMLElement && active !== document.body && !ref.current?.contains(active)) opener.current = active;
    ref.current?.focus();
  }, [address]);
  useEffect(() => () => { if (opener.current?.isConnected) opener.current.focus(); }, []);
  useEffect(() => {
    // Esc while an input method is composing belongs to the input method.
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape' && !e.isComposing) onClose(); };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [onClose]);
  return (
    <div ref={ref} className="detail" role="dialog" aria-label={label} tabIndex={-1}>
      <div className="drow">
        {head}
        <span className="grow" />
        <button type="button" className="iconbtn" aria-label={t('peek.close')} title={t('peek.close')} onClick={onClose}><X /></button>
      </div>
      {children}
    </div>
  );
}
