import React from 'react';

export interface IconButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  active?: boolean;
  label: string;
  size?: 'sm' | 'md';
}

export const IconButton: React.FC<IconButtonProps> = ({
  active,
  label,
  size = 'sm',
  className = '',
  children,
  type = 'button',
  ...rest
}) => {
  const dim = size === 'sm' ? 'h-6 w-6' : 'h-8 w-8';
  return (
    <button
      type={type}
      title={label}
      aria-label={label}
      data-active={active ? 'true' : undefined}
      className={`inline-flex items-center justify-center rounded-sm transition-colors duration-150 shrink-0 ${dim} bg-dv-surface text-dv-muted hover:text-dv-text hover:bg-dv-hover disabled:opacity-40 data-[active=true]:bg-dv-accent data-[active=true]:text-black ${className}`}
      {...rest}
    >
      {children}
    </button>
  );
};

export default IconButton;
