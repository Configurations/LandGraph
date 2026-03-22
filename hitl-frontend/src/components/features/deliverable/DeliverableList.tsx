import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { DeliverableCard } from './DeliverableCard';
import { Spinner } from '../../ui/Spinner';
import type { DeliverableResponse } from '../../../api/types';

interface DeliverableListProps {
  deliverables: DeliverableResponse[];
  loading: boolean;
  onSelect: (id: string) => void;
  className?: string;
}

export function DeliverableList({
  deliverables,
  loading,
  onSelect,
  className = '',
}: DeliverableListProps): JSX.Element {
  const { t } = useTranslation();

  const grouped = useMemo(() => {
    const map = new Map<string, DeliverableResponse[]>();
    for (const d of deliverables) {
      const list = map.get(d.phase) ?? [];
      list.push(d);
      map.set(d.phase, list);
    }
    return map;
  }, [deliverables]);

  if (loading) {
    return (
      <div className={`flex items-center justify-center py-12 ${className}`}>
        <Spinner />
      </div>
    );
  }

  if (deliverables.length === 0) {
    return (
      <div className={`text-center py-12 text-content-tertiary ${className}`}>
        <p className="text-sm">{t('deliverable.no_deliverables')}</p>
      </div>
    );
  }

  return (
    <div className={`flex flex-col gap-6 ${className}`}>
      {Array.from(grouped.entries()).map(([phase, items]) => (
        <div key={phase}>
          <h3 className="text-xs font-semibold uppercase tracking-wider text-content-quaternary mb-2 px-1">
            {phase}
          </h3>
          <div className="flex flex-col gap-2">
            {items.map((d) => (
              <DeliverableCard
                key={d.id}
                deliverable={d}
                onClick={() => onSelect(d.id)}
              />
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
