import React from 'react';

export interface MenuProps {
  open: boolean;
  children: React.ReactNode;
  className?: string;
  align?: 'left' | 'right';
}

export const Menu: React.FC<MenuProps> = ({
  open,
  children,
  className = '',
  align = 'right',
}) => {
  if (!open) return null;
  return (
    <div
      className={`absolute top-full mt-1 py-1 z-50 bg-dv-panel border border-dv-border shadow-xl min-w-[11rem] ${
        align === 'right' ? 'right-0' : 'left-0'
      } ${className}`}
      role="menu"
    >
      {children}
    </div>
  );
};

export interface MenuItemProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  danger?: boolean;
}

export const MenuItem: React.FC<MenuItemProps> = ({
  danger,
  className = '',
  children,
  type = 'button',
  ...rest
}) => (
  <button
    type={type}
    role="menuitem"
    className={`w-full text-left px-3 py-1.5 text-xs hover:bg-dv-hover flex items-center gap-2 ${
      danger ? 'text-dv-hot' : 'text-dv-text'
    } ${className}`}
    {...rest}
  >
    {children}
  </button>
);

export default Menu;
