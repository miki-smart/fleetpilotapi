import { useEffect, useState } from 'react';
import { Bell, Mail, Monitor, CheckCircle2, AlertTriangle } from 'lucide-react';
import { getNotifications } from '../services/api';
import type { Notification, NotificationStatus } from '../types';
import { Card } from '../components/ui/Card';
import { Badge } from '../components/ui/Badge';
import { LoadingScreen } from '../components/ui/Spinner';
import { timeAgo } from '../lib/utils';

function notifStatusColor(status: NotificationStatus): string {
  switch (status) {
    case 'SENT': return 'text-emerald-700 bg-emerald-50 border-emerald-200';
    case 'SIMULATED': return 'text-blue-700 bg-blue-50 border-blue-200';
    case 'FAILED': return 'text-red-700 bg-red-50 border-red-200';
    default: return 'text-slate-600 bg-slate-100 border-slate-200';
  }
}

export function Notifications() {
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getNotifications().then(setNotifications).finally(() => setLoading(false));
  }, []);

  if (loading) return <LoadingScreen />;

  return (
    <div className="p-4 md:p-8">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-slate-900">Notifications</h1>
        <p className="text-slate-500 text-sm mt-1">{notifications.length} notifications</p>
      </div>

      <Card padding={false}>
        {notifications.length === 0 ? (
          <div className="py-16 text-center text-slate-400">
            <Bell className="w-8 h-8 mx-auto mb-3 text-slate-300" />
            <p>No notifications yet.</p>
          </div>
        ) : (
          <div className="divide-y divide-slate-100">
            {notifications.map(n => (
              <div key={n.id} className="flex items-start gap-4 px-6 py-4">
                <div className="w-8 h-8 rounded-lg bg-slate-100 flex items-center justify-center shrink-0 mt-0.5">
                  {n.channel === 'EMAIL' ? <Mail className="w-4 h-4 text-slate-500" /> : <Monitor className="w-4 h-4 text-slate-500" />}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="font-medium text-sm text-slate-900">{n.subject}</span>
                    <Badge className={notifStatusColor(n.status)}>{n.status}</Badge>
                    <span className="text-xs text-slate-400 ml-auto">{timeAgo(n.created_at)}</span>
                  </div>
                  <p className="text-xs text-slate-500">To: {n.recipient} · via {n.channel}</p>
                  <p className="text-sm text-slate-600 mt-1 line-clamp-2">{n.message}</p>
                </div>
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}
