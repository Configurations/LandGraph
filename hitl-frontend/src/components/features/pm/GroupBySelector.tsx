import { useTranslation } from 'react-i18next';
import { Select } from '../../ui/Select';
import type { IssueGroupBy } from '../../../api/types';

interface GroupBySelectorProps {
  value: IssueGroupBy;
  onChange: (value: IssueGroupBy) => void;
  className?: string;
}

export function GroupBySelector({
  value,
  onChange,
  className = '',
}: GroupBySelectorProps): JSX.Element {
  const { t } = useTranslation();

  const options = [
    { value: 'status', label: t('issue.group_status') },
    { value: 'team', label: t('issue.group_team') },
    { value: 'assignee', label: t('issue.group_assignee') },
    { value: 'dependency', label: t('issue.group_dependency') },
  ];

  return (
    <Select
      options={options}
      value={value}
      onChange={(e) => onChange(e.target.value as IssueGroupBy)}
      className={className}
    />
  );
}
