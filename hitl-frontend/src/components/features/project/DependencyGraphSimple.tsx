import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import type { IssueResponse, RelationType } from '../../../api/types';

interface Relation {
  sourceId: string;
  targetId: string;
  type: RelationType;
}

interface DependencyGraphSimpleProps {
  issues: IssueResponse[];
  relations: Relation[];
  className?: string;
}

const NODE_W = 160;
const NODE_H = 48;
const GAP_X = 40;
const GAP_Y = 24;
const COLS = 4;

interface NodePos {
  issue: IssueResponse;
  x: number;
  y: number;
}

export function DependencyGraphSimple({
  issues,
  relations,
  className = '',
}: DependencyGraphSimpleProps): JSX.Element {
  const { t } = useTranslation();
  const navigate = useNavigate();

  const nodes = useMemo<NodePos[]>(() => {
    return issues.map((issue, idx) => ({
      issue,
      x: (idx % COLS) * (NODE_W + GAP_X) + 20,
      y: Math.floor(idx / COLS) * (NODE_H + GAP_Y) + 20,
    }));
  }, [issues]);

  const posMap = useMemo(() => {
    const map = new Map<string, NodePos>();
    nodes.forEach((n) => map.set(n.issue.id, n));
    return map;
  }, [nodes]);

  const svgWidth = COLS * (NODE_W + GAP_X) + 40;
  const rows = Math.ceil(issues.length / COLS);
  const svgHeight = rows * (NODE_H + GAP_Y) + 40;

  if (issues.length === 0) {
    return (
      <p className={`text-sm text-content-tertiary ${className}`}>
        {t('project_detail.no_dependencies')}
      </p>
    );
  }

  return (
    <div className={`overflow-auto ${className}`}>
      <svg
        width={svgWidth}
        height={svgHeight}
        className="min-w-full"
        aria-label={t('project_detail.dependency_graph')}
      >
        {relations.map((rel, idx) => {
          const src = posMap.get(rel.sourceId);
          const tgt = posMap.get(rel.targetId);
          if (!src || !tgt) return null;
          const isBlock = rel.type === 'blocks';
          const x1 = src.x + NODE_W;
          const y1 = src.y + NODE_H / 2;
          const x2 = tgt.x;
          const y2 = tgt.y + NODE_H / 2;
          return (
            <line
              key={idx}
              x1={x1}
              y1={y1}
              x2={x2}
              y2={y2}
              stroke={isBlock ? '#ef4444' : '#6b7280'}
              strokeWidth={isBlock ? 2 : 1}
              strokeDasharray={isBlock ? undefined : '4 4'}
              markerEnd={isBlock ? 'url(#arrow-red)' : 'url(#arrow-gray)'}
            />
          );
        })}

        <defs>
          <marker id="arrow-red" markerWidth="8" markerHeight="6" refX="8" refY="3" orient="auto">
            <path d="M0,0 L8,3 L0,6 Z" fill="#ef4444" />
          </marker>
          <marker id="arrow-gray" markerWidth="8" markerHeight="6" refX="8" refY="3" orient="auto">
            <path d="M0,0 L8,3 L0,6 Z" fill="#6b7280" />
          </marker>
        </defs>

        {nodes.map((node) => (
          <g
            key={node.issue.id}
            onClick={() => navigate(`/issues?id=${node.issue.id}`)}
            className="cursor-pointer"
          >
            <rect
              x={node.x}
              y={node.y}
              width={NODE_W}
              height={NODE_H}
              rx={8}
              className="fill-surface-secondary stroke-border"
              strokeWidth={1}
            />
            <text
              x={node.x + 8}
              y={node.y + 16}
              className="fill-content-tertiary text-[10px] font-mono"
            >
              {node.issue.id}
            </text>
            <text
              x={node.x + 8}
              y={node.y + 34}
              className="fill-content-primary text-xs"
            >
              {node.issue.title.length > 16
                ? `${node.issue.title.slice(0, 16)}...`
                : node.issue.title}
            </text>
          </g>
        ))}
      </svg>
    </div>
  );
}
