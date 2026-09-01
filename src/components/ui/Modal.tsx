import React, { useEffect } from 'react';

export interface ModalProps {
  open: boolean;
  title: string;
  onClose: () => void;
  children: React.ReactNode;
  /** Max width class, default max-w-sm */
  wide?: boolean;
  footer?: React.ReactNode;
}

export const Modal: React.FC<ModalProps> = ({
  open,
  title,
  onClose,
  children,
  wide,
  footer,
}) => {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div
      className="modal fixed inset-0 z-[999] flex items-center justify-center bg-black/60 p-4 animate-[dvFade_180ms_ease]"
      role="dialog"
      aria-modal="true"
      aria-labelledby="dv-modal-title"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        className={`bg-dv-panel border border-dv-border shadow-xl w-full ${
          wide ? 'max-w-md' : 'max-w-sm'
        } rounded-sm animate-[dvRise_180ms_ease]`}
      >
        <div className="flex items-center justify-between px-4 py-2.5 border-b border-dv-border">
          <h2 id="dv-modal-title" className="text-sm font-semibold text-dv-text">
            {title}
          </h2>
          <button
            type="button"
            className="text-dv-muted hover:text-dv-text text-lg leading-none px-1"
            onClick={onClose}
            aria-label="Закрыть"
          >
            ×
          </button>
        </div>
        <div className="px-4 py-3">{children}</div>
        {footer ? (
          <div className="px-4 py-2.5 border-t border-dv-border flex justify-end gap-2">
            {footer}
          </div>
        ) : null}
      </div>
      <style>{`
        @keyframes dvFade { from { opacity: 0 } to { opacity: 1 } }
        @keyframes dvRise { from { opacity: 0; transform: translateY(6px) } to { opacity: 1; transform: none } }
      `}</style>
    </div>
  );
};

export default Modal;
