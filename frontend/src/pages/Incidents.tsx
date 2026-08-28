import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { AlertTriangle, Filter, ChevronRight } from 'lucide-react';
import { getIncidents } from '../services/api';
import type { Incident } from '../types';
import { Card } from '../components/ui/Card';
import { Badge } from '../components/ui/Badge';
import { LoadingScreen } from '../components/ui/Spinner';
import { severityColor, incidentStatusColor, timeAgo } from '../lib/utils';

const OPEN = new Set(['NEW', 'ANALYZING', 'AWAITING_APPROVAL', 'APPROVED', 'IN_PROGRESS']);
const FILTERS = [
  { label: 'All', value: 'all' },
  { label: 'Open', value: 'open' },
  { label: 'Closed', value: 'closed' },
] as const;

export function Incidents() {
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<'all' | 'open' | 'closed'>('all');

  useEffect(() => {
    getIncidents()
      .then(setIncidents)
      .catch(e => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <LoadingScreen />;

  const filtered = incidents.filter(i =>
    filter === 'all' ? true : filter === 'open' ? OPEN.has(i.status) : !OPEN.has(i.status),
  );

  return (
    <div className="p-4 md:p-8">
      <div className="mb-6 flex flex-col sm:flex-row sm:items-end sm:justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Incidents</h1>
          <p className="text-slate-500 text-sm mt-1">
            {incidents.length} reported · {incidents.filter(i => OPEN.has(i.status)).length} open
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Filter className="w-4 h-4 text-slate-400" />
          {FILTERS.map(f => (
            <button
              key={f.value}
              onClick={() => setFilter(f.value)}
              className={`px-3 py-1.5 text-xs font-medium rounded-full border transition-colors ${
                filter === f.value ? 'bg-blue-600 text-white border-blue-600' : 'bg-white text-slate-600 border-slate-300 hover:bg-slate-50'
              }`}
            >
              {f.label}
            </button>
          ))}
        </div>
      </div>

      {error && (
        <div className="mb-4 flex items-center gap-2 text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2">
          <AlertTriangle className="w-4 h-4 shrink-0" />{error}
        </div>
      )}

      <Card padding={false}>
        {filtered.length === 0 ? (
          <div className="py-16 text-center text-slate-400">
            <AlertTriangle className="w-8 h-8 mx-auto mb-3 text-slate-300" />
            <p>No incidents match this filter.</p>
          </div>
        ) : (
          <div className="divide-y divide-slate-100">
            {filtered.map(i => (
              <Link
                key={i.id}
                to={`/agent?incident=${i.id}`}
                className="flex items-start gap-4 px-4 md:px-6 py-4 hover:bg-slate-50 transition-colors"
              >
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap mb-1">
                    <span className="font-semibold text-sm text-slate-900 font-mono">{i.vehicle_fleet_number}</span>
                    <span className="text-xs text-slate-500">{i.vehicle_make} {i.vehicle_model}</span>
                    {i.severity && <Badge className={severityColor(i.severity)}>{i.severity}</Badge>}
                    {i.category && (
                      <Badge className="text-purple-700 bg-purple-50 border-purple-200">{i.category.replace(/_/g, ' ')}</Badge>
                    )}
                    <Badge className={incidentStatusColor(i.status)}>{i.status.replace(/_/g, ' ')}</Badge>
                  </div>
                  <p className="text-sm text-slate-700 line-clamp-2">{i.description}</p>
                  <p className="text-xs text-slate-400 mt-1">Reported by {i.reported_by} · {timeAgo(i.created_at)}</p>
                </div>
                <ChevronRight className="w-4 h-4 text-slate-300 shrink-0 mt-1" />
              </Link>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}
