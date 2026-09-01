import React from 'react';

type ButtonVariant = 'primary' | 'ghost' | 'danger' | 'toggle';
type ButtonSize = 'sm' | 'md';

const variantClass: Record<ButtonVariant, string> = {
  primary:
    'bg-dv-accent text-black font-medium hover:brightness-110 disabled:opacity-40',
  ghost:
    'bg-dv-surface text-dv-muted hover:text-dv-text hover:bg-dv-hover disabled:opacity-40 data-[active=true]:bg-dv-hover data-[active=true]:text-dv-text',
  danger:
    'bg-dv-surface text-dv-danger hover:bg-[#4a2222] hover:text-white disabled:opacity-40',
  toggle:
    'bg-dv-surface text-dv-muted hover:text-dv-text disabled:opacity-40 data-[active=true]:bg-dv-accent data-[active=true]:text-black data-[active=true]:font-medium',
};

const sizeClass: Record<ButtonSize, string> = {
  sm: 'h-6 px-2 text-[10px] gap-1',
  md: 'h-8 px-2.5 text-[11px] gap-1.5',
};

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  active?: boolean;
}

export const Button: React.FC<ButtonProps> = ({
  variant = 'ghost',
  size = 'md',
  active,
  className = '',
  children,
  type = 'button',
  ...rest
}) => (
  <button
    type={type}
    data-active={active ? 'true' : undefined}
    className={`inline-flex items-center justify-center rounded-sm transition-colors duration-150 shrink-0 ${variantClass[variant]} ${sizeClass[size]} ${className}`}
    {...rest}
  >
    {children}
  </button>
);

export default Button;
