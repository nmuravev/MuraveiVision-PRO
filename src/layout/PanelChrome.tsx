import React from 'react';
import { Maximize2, Minimize2, X, PanelTop } from 'lucide-react';
import type { ViewId } from './initialLayout';
import { VIEW_TITLES } from './initialLayout';
import { usePanelLayoutStore } from '../store/usePanelLayoutStore';

interface PanelChromeProps {
  id: ViewId;
  children: React.ReactNode;
  extraActions?: React.ReactNode;
  floating?: boolean;
  /** Hide local header when MosaicWindow already provides a draggable toolbar */
  hideHeader?: boolean;
}

export const PanelChrome: React.FC<PanelChromeProps> = ({
  id,
  children,
  extraActions,
  floating = false,
  hideHeader = false,
}) => {
  const maximizePanel = usePanelLayoutStore((s) => s.maximizePanel);
  const undockPanel = usePanelLayoutStore((s) => s.undockPanel);
  const closePanel = usePanelLayoutStore((s) => s.closePanel);
  const redockPanel = usePanelLayoutStore((s) => s.redockPanel);
  const maximizedId = usePanelLayoutStore((s) => s.maximizedId);
  const isMax = maximizedId === id;

  return (
    <div className="panel-chrome" style={{ minHeight: 0, border: hideHeader ? 'none' : undefined }}>
            {!hideHeader && (
        <div className="panel-chrome__header">
          <span className="panel-chrome__title">{VIEW_TITLES[id]}</span>
          <div className="panel-chrome__actions">
            {extraActions}
            {floating ? (
              <button
                type="button"
                className="panel-chrome__btn"
                title="Пристыковать"
                onClick={() => redockPanel(id)}
              >
                <PanelTop size={12} />
              </button>
            ) : (
              <button
                type="button"
                className="panel-chrome__btn"
                title="Открепить"
                onClick={() => undockPanel(id)}
              >
                <PanelTop size={12} />
              </button>
            )}
            <button
              type="button"
              className="panel-chrome__btn"
              title={isMax ? 'Восстановить' : 'Развернуть'}
              onClick={() => maximizePanel(id)}
            >
              {isMax ? <Minimize2 size={12} /> : <Maximize2 size={12} />}
            </button>
            <button
              type="button"
              className="panel-chrome__btn"
              title="Закрыть"
              onClick={() => closePanel(id)}
            >
              <X size={12} />
            </button>
          </div>
        </div>
      )}
      <div className="panel-chrome__body">{children}</div>
    </div>
  );
};

/** Compact icon buttons for MosaicWindow toolbarControls */
export const PanelToolbarButtons: React.FC<{ id: ViewId }> = ({ id }) => {
  const maximizePanel = usePanelLayoutStore((s) => s.maximizePanel);
  const undockPanel = usePanelLayoutStore((s) => s.undockPanel);
  const closePanel = usePanelLayoutStore((s) => s.closePanel);
  const maximizedId = usePanelLayoutStore((s) => s.maximizedId);
  const isMax = maximizedId === id;

  return (
    <div className="flex items-center gap-0.5 pr-1">
      <button
        type="button"
        className="panel-chrome__btn"
        title="Открепить"
        onClick={(e) => {
          e.stopPropagation();
          undockPanel(id);
        }}
      >
        <PanelTop size={12} />
      </button>
      <button
        type="button"
        className="panel-chrome__btn"
        title={isMax ? 'Восстановить' : 'Развернуть'}
        onClick={(e) => {
          e.stopPropagation();
          maximizePanel(id);
        }}
      >
        {isMax ? <Minimize2 size={12} /> : <Maximize2 size={12} />}
      </button>
      <button
        type="button"
        className="panel-chrome__btn"
        title="Закрыть"
        onClick={(e) => {
          e.stopPropagation();
          closePanel(id);
        }}
      >
        <X size={12} />
      </button>
    </div>
  );
};

export default PanelChrome;
