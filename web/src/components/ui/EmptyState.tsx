interface EmptyStateProps {
  message: string;
  icon?: string;
}

export function EmptyState({ message, icon = '📭' }: EmptyStateProps) {
  return (
    <div className="text-center py-12">
      <p className="text-3xl mb-3">{icon}</p>
      <p className="text-gray-500">{message}</p>
    </div>
  );
}
