import React from 'react';

export interface ToolbarGroupProps {
  children: React.ReactNode;
  className?: string;
  /** Hide trailing divider */
  last?: boolean;
}

export const ToolbarGroup: React.FC<ToolbarGroupProps> = ({
  children,
  className = '',
  last = false,
}) => (
  <div
    className={`inline-flex items-center gap-0.5 shrink-0 ${
      last ? '' : 'pr-1.5 mr-1.5 border-r border-dv-border'
    } ${className}`}
  >
    {children}
  </div>
);

export default ToolbarGroup;
