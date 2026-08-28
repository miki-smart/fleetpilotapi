import { useEffect, useState, useCallback } from 'react';
import { CheckCircle2, XCircle, AlertTriangle, Clock, Play, Check } from 'lucide-react';
import { getMaintenance, approveTask, rejectTask, startTask, completeTask } from '../services/api';
import type { MaintenanceTask, TaskStatus } from '../types';
import { Card } from '../components/ui/Card';
import { Badge } from '../components/ui/Badge';
import { Button } from '../components/ui/Button';
import { LoadingScreen } from '../components/ui/Spinner';
import { severityColor, taskStatusColor, formatDate } from '../lib/utils';

const STATUS_GROUPS: { label: string; statuses: TaskStatus[] }[] = [
  { label: 'Pending Approval', statuses: ['PENDING_APPROVAL'] },
  { label: 'Active', statuses: ['APPROVED', 'ASSIGNED', 'IN_PROGRESS'] },
  { label: 'Completed / Cancelled', statuses: ['COMPLETED', 'CANCELLED'] },
];

type Action = 'approve' | 'reject' | 'start' | 'complete';

export function Maintenance() {
  const [tasks, setTasks] = useState<MaintenanceTask[]>([]);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const load = useCallback(() => {
    getMaintenance()
      .then(setTasks)
      .catch(e => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { load(); }, [load]);

  const run = async (taskId: string, action: Action) => {
    setActionLoading(taskId);
    setError(null);
    setNotice(null);
    try {
      const fn = { approve: approveTask, reject: rejectTask, start: startTask, complete: completeTask }[action];
      const updated = await fn(taskId);
      setTasks(prev => prev.map(t => (t.id === updated.id ? { ...t, ...updated } : t)));
      if (action === 'complete') {
        setNotice(
          updated.vehicle_restored
            ? `${updated.vehicle?.fleet_number ?? 'Vehicle'} returned to ACTIVE service and the maintenance record was logged.`
            : 'Task completed and logged in the vehicle history.',
        );
      }
      if (action === 'approve') setNotice('Approved — the workshop has been notified and parts moved to ORDERED.');
      // Cross-effects (vehicle status, incident status) — refresh quietly
      load();
    } catch (e: any) {
      setError(e.message ?? 'Action failed.');
    } finally {
      setActionLoading(null);
    }
  };

  if (loading) return <LoadingScreen />;

  const grouped = STATUS_GROUPS.map(group => ({
    ...group,
    tasks: tasks.filter(t => group.statuses.includes(t.status)),
  }));

  return (
    <div className="p-4 md:p-8">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-slate-900">Maintenance</h1>
        <p className="text-slate-500 text-sm mt-1">{tasks.length} total tasks · approve, start and complete work orders</p>
      </div>

      {error && (
        <div className="mb-4 flex items-center gap-2 text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2">
          <AlertTriangle className="w-4 h-4 shrink-0" />{error}
        </div>
      )}
      {notice && (
        <div className="mb-4 flex items-center gap-2 text-sm text-emerald-700 bg-emerald-50 border border-emerald-200 rounded-lg px-3 py-2">
          <CheckCircle2 className="w-4 h-4 shrink-0" />{notice}
        </div>
      )}

      <div className="space-y-8">
        {grouped.map(group => (
          <section key={group.label}>
            <h2 className="text-sm font-semibold text-slate-500 uppercase tracking-wide mb-3 flex items-center gap-2">
              {group.label === 'Pending Approval' && <AlertTriangle className="w-4 h-4 text-amber-500" />}
              {group.label === 'Active' && <Clock className="w-4 h-4 text-blue-500" />}
              {group.label === 'Completed / Cancelled' && <CheckCircle2 className="w-4 h-4 text-emerald-500" />}
              {group.label}
              <span className="font-normal text-slate-400 normal-case tracking-normal">({group.tasks.length})</span>
            </h2>

            {group.tasks.length === 0 ? (
              <div className="text-slate-400 text-sm py-4">None.</div>
            ) : (
              <div className="space-y-3">
                {group.tasks.map(task => {
                  const busy = actionLoading === task.id;
                  return (
                    <Card key={task.id}>
                      <div className="flex flex-col md:flex-row md:items-start md:justify-between gap-4">
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2 flex-wrap mb-1">
                            <span className="font-semibold text-sm text-slate-900">{task.title}</span>
                            {task.ai_generated && (
                              <span className="text-xs text-blue-600 bg-blue-50 border border-blue-200 px-2 py-0.5 rounded-full">AI Generated</span>
                            )}
                          </div>
                          <div className="flex items-center gap-2 mb-2 flex-wrap">
                            {task.vehicle && (
                              <span className="text-xs font-mono text-slate-500">
                                {task.vehicle.fleet_number} — {task.vehicle.make} {task.vehicle.model}
                              </span>
                            )}
                            <Badge className={severityColor(task.severity)}>{task.severity}</Badge>
                            <Badge className={taskStatusColor(task.status)}>{task.status.replace(/_/g, ' ')}</Badge>
                            {(task.parts_count ?? 0) > 0 && (
                              <span className="text-xs text-slate-400">{task.parts_count} part{task.parts_count === 1 ? '' : 's'}</span>
                            )}
                          </div>
                          {task.description && <p className="text-sm text-slate-600 whitespace-pre-line">{task.description}</p>}
                          <p className="text-xs text-slate-400 mt-1">Created {formatDate(task.created_at)}{task.due_date ? ` · Due ${formatDate(task.due_date)}` : ''}</p>
                        </div>

                        <div className="flex gap-2 shrink-0 flex-wrap">
                          {task.status === 'PENDING_APPROVAL' && (
                            <>
                              <Button size="sm" onClick={() => run(task.id, 'approve')} loading={busy} className="flex items-center gap-1">
                                <CheckCircle2 className="w-3.5 h-3.5" /> Approve
                              </Button>
                              <Button size="sm" variant="danger" onClick={() => run(task.id, 'reject')} loading={busy} className="flex items-center gap-1">
                                <XCircle className="w-3.5 h-3.5" /> Reject
                              </Button>
                            </>
                          )}
                          {(task.status === 'APPROVED' || task.status === 'ASSIGNED') && (
                            <>
                              <Button size="sm" variant="secondary" onClick={() => run(task.id, 'start')} loading={busy} className="flex items-center gap-1">
                                <Play className="w-3.5 h-3.5" /> Start
                              </Button>
                              <Button size="sm" onClick={() => run(task.id, 'complete')} loading={busy} className="flex items-center gap-1">
                                <Check className="w-3.5 h-3.5" /> Complete
                              </Button>
                            </>
                          )}
                          {task.status === 'IN_PROGRESS' && (
                            <Button size="sm" onClick={() => run(task.id, 'complete')} loading={busy} className="flex items-center gap-1">
                              <Check className="w-3.5 h-3.5" /> Complete
                            </Button>
                          )}
                        </div>
                      </div>
                    </Card>
                  );
                })}
              </div>
            )}
          </section>
        ))}
      </div>
    </div>
  );
}
