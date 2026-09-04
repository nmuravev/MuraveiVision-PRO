import React from 'react';
import { Modal, Button } from './ui';
import type { ApiErrorDetails } from '../lib/apiError';

export type ErrorDetailsModalProps = {
  error: ApiErrorDetails | null;
  onClose: () => void;
};

export const ErrorDetailsModal: React.FC<ErrorDetailsModalProps> = ({ error, onClose }) => {
  if (!error) return null;

  return (
    <Modal
      open
      wide
      title={`Ошибка ${error.code}: ${error.title}`}
      onClose={onClose}
      footer={
        <Button size="sm" variant="primary" onClick={onClose}>
          Понятно
        </Button>
      }
    >
      <div className="space-y-3 text-xs text-dv-text" data-testid="error-details-modal">
        {error.message ? (
          <p className="text-[11px] text-dv-muted font-mono break-words">{error.message}</p>
        ) : null}

        {error.causes.length > 0 ? (
          <div>
            <h4 className="dv-section-label mb-1">Возможные причины</h4>
            <ul className="list-disc pl-4 space-y-0.5 text-[11px] text-dv-text">
              {error.causes.map((cause) => (
                <li key={cause}>{cause}</li>
              ))}
            </ul>
          </div>
        ) : null}

        {error.solutions.length > 0 ? (
          <div>
            <h4 className="dv-section-label mb-1">Что сделать</h4>
            <ol className="list-decimal pl-4 space-y-0.5 text-[11px] text-dv-text">
              {error.solutions.map((sol) => (
                <li key={sol}>{sol}</li>
              ))}
            </ol>
          </div>
        ) : null}

        {error.docs_url ? (
          <a
            href={error.docs_url}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-block text-[11px] text-dv-accent hover:underline"
          >
            Подробнее в документации →
          </a>
        ) : null}
      </div>
    </Modal>
  );
};

export default ErrorDetailsModal;
