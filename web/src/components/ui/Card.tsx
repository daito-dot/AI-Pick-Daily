interface CardProps {
  variant?: 'default' | 'outlined' | 'highlighted' | 'danger';
  className?: string;
  children: React.ReactNode;
}

const variantClasses: Record<string, string> = {
  default: 'bg-white border-gray-100',
  outlined: 'bg-white border-gray-200',
  highlighted: 'bg-primary-50 border-primary-200',
  danger: 'bg-loss-light border-red-200',
};

export function Card({ variant = 'default', className = '', children }: CardProps) {
  return (
    <div className={`rounded-xl shadow-card p-6 border ${variantClasses[variant]} ${className}`}>
      {children}
    </div>
  );
}
