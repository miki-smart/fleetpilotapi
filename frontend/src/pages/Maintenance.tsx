import { useEffect, useState, useCallback } from 'react';
import { CheckCircle2, XCircle, AlertTriangle, Clock } from 'lucide-react';
import { getMaintenance, approveTask, rejectTask } from '../services/api';
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

export function Maintenance() {
  const [tasks, setTasks] = useState<MaintenanceTask[]>([]);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState<string | null>(null);

  const load = useCallback(() => {
    getMaintenance()
      .then(setTasks)
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleApprove = async (taskId: string) => {
    setActionLoading(taskId);
    try {
      const updated = await approveTask(taskId);
      setTasks(prev => prev.map(t => t.id === updated.id ? updated : t));
    } finally {
      setActionLoading(null);
    }
  };

  const handleReject = async (taskId: string) => {
    setActionLoading(taskId);
    try {
      const updated = await rejectTask(taskId);
      setTasks(prev => prev.map(t => t.id === updated.id ? updated : t));
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
    <div className="p-8">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-slate-900">Maintenance</h1>
        <p className="text-slate-500 text-sm mt-1">{tasks.length} total tasks</p>
      </div>

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
                {group.tasks.map(task => (
                  <Card key={task.id}>
                    <div className="flex items-start justify-between gap-4">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 flex-wrap mb-1">
                          <span className="font-semibold text-sm text-slate-900">{task.title}</span>
                          {task.ai_generated && (
                            <span className="text-xs text-blue-600 bg-blue-50 border border-blue-200 px-2 py-0.5 rounded-full">AI Generated</span>
                          )}
                        </div>
                        <div className="flex items-center gap-2 mb-2">
                          {task.vehicle && (
                            <span className="text-xs font-mono text-slate-500">
                              {task.vehicle.fleet_number} — {task.vehicle.make} {task.vehicle.model}
                            </span>
                          )}
                          <Badge className={severityColor(task.severity)}>{task.severity}</Badge>
                          <Badge className={taskStatusColor(task.status)}>{task.status.replace('_', ' ')}</Badge>
                        </div>
                        {task.description && <p className="text-sm text-slate-600">{task.description}</p>}
                        <p className="text-xs text-slate-400 mt-1">Created {formatDate(task.created_at)}{task.due_date ? ` · Due ${formatDate(task.due_date)}` : ''}</p>
                      </div>

                      {task.status === 'PENDING_APPROVAL' && (
                        <div className="flex gap-2 shrink-0">
                          <Button
                            size="sm"
                            onClick={() => handleApprove(task.id)}
                            loading={actionLoading === task.id}
                            className="flex items-center gap-1"
                          >
                            <CheckCircle2 className="w-3.5 h-3.5" />
                            Approve
                          </Button>
                          <Button
                            size="sm"
                            variant="danger"
                            onClick={() => handleReject(task.id)}
                            loading={actionLoading === task.id}
                            className="flex items-center gap-1"
                          >
                            <XCircle className="w-3.5 h-3.5" />
                            Reject
                          </Button>
                        </div>
                      )}
                    </div>
                  </Card>
                ))}
              </div>
            )}
          </section>
        ))}
      </div>
    </div>
  );
}
