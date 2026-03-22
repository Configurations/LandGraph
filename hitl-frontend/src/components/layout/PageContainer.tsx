import type { ReactNode } from 'react';

interface PageContainerProps {
  children: ReactNode;
  className?: string;
}

export function PageContainer({ children, className = '' }: PageContainerProps): JSX.Element {
  return (
    <div className={`px-4 py-6 max-w-6xl mx-auto ${className}`}>
      {children}
    </div>
  );
}
