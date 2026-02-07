interface PageHeaderProps {
  title: string;
  subtitle?: string;
  children?: React.ReactNode;
}

export function PageHeader({ title, subtitle, children }: PageHeaderProps) {
  return (
    <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-3">
      <div>
        <h2 className="page-title">{title}</h2>
        {subtitle && <p className="text-gray-500 mt-1">{subtitle}</p>}
      </div>
      {children}
    </div>
  );
}
