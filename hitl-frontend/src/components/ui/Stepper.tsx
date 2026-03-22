import { useTranslation } from 'react-i18next';

interface StepDef {
  labelKey: string;
  completed: boolean;
}

interface StepperProps {
  steps: StepDef[];
  activeStep: number;
  onStepClick?: (step: number) => void;
  className?: string;
}

export function Stepper({ steps, activeStep, onStepClick, className = '' }: StepperProps): JSX.Element {
  const { t } = useTranslation();

  return (
    <div className={`flex items-center gap-1 ${className}`}>
      {steps.map((step, idx) => {
        const isActive = idx === activeStep;
        const isCompleted = step.completed;
        const isClickable = onStepClick !== undefined && (isCompleted || idx <= activeStep);

        return (
          <div key={step.labelKey} className="flex items-center gap-1 flex-1 last:flex-none">
            <button
              type="button"
              disabled={!isClickable}
              onClick={() => isClickable && onStepClick?.(idx)}
              className={[
                'flex items-center gap-2 text-xs font-medium transition-colors whitespace-nowrap',
                isActive ? 'text-accent-blue' : isCompleted ? 'text-accent-green' : 'text-content-quaternary',
                isClickable ? 'cursor-pointer hover:text-accent-blue' : 'cursor-default',
              ].join(' ')}
            >
              <span
                className={[
                  'flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-[10px] font-bold border',
                  isActive ? 'border-accent-blue bg-accent-blue text-white' :
                  isCompleted ? 'border-accent-green bg-accent-green text-white' :
                  'border-border bg-surface-tertiary text-content-quaternary',
                ].join(' ')}
              >
                {isCompleted ? '\u2713' : idx + 1}
              </span>
              <span className="hidden sm:inline">{t(step.labelKey)}</span>
            </button>
            {idx < steps.length - 1 && (
              <div className={`flex-1 h-px mx-1 ${isCompleted ? 'bg-accent-green' : 'bg-border'}`} />
            )}
          </div>
        );
      })}
    </div>
  );
}
