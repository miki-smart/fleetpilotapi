import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { AlertTriangle, CheckCircle2, Clock, Wrench, Zap, TrendingUp, Activity } from 'lucide-react';
import { getDashboard } from '../services/api';
import type { DashboardData } from '../types';
import { Card } from '../components/ui/Card';
import { Badge } from '../components/ui/Badge';
import { LoadingScreen } from '../components/ui/Spinner';
import { severityColor, statusColor, formatMileage, timeAgo } from '../lib/utils';

export function Dashboard() {
  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getDashboard()
      .then(setData)
      .catch(e => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <LoadingScreen />;
  if (error || !data) return (
    <div className="p-8 text-red-600">Failed to load dashboard: {error}</div>
  );

  const { fleet_stats, risk_score, critical_alerts, upcoming_maintenance, recent_agent_actions } = data;

  const riskColor = risk_score >= 70 ? 'text-red-600' : risk_score >= 40 ? 'text-amber-600' : 'text-emerald-600';
  const riskBg = risk_score >= 70 ? 'bg-red-50 border-red-200' : risk_score >= 40 ? 'bg-amber-50 border-amber-200' : 'bg-emerald-50 border-emerald-200';

  return (
    <div className="p-8">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-slate-900">Fleet Dashboard</h1>
        <p className="text-slate-500 text-sm mt-1">Real-time fleet health and AI activity overview</p>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-2 xl:grid-cols-4 gap-4 mb-8">
        <KpiCard
          label="Total Vehicles"
          value={fleet_stats.total}
          icon={<Wrench className="w-5 h-5 text-blue-600" />}
          color="bg-blue-50"
        />
        <KpiCard
          label="Healthy"
          value={fleet_stats.healthy}
          icon={<CheckCircle2 className="w-5 h-5 text-emerald-600" />}
          color="bg-emerald-50"
          sub={`${Math.round((fleet_stats.healthy / fleet_stats.total) * 100)}% of fleet`}
        />
        <KpiCard
          label="Maintenance Due"
          value={fleet_stats.maintenance_due}
          icon={<Clock className="w-5 h-5 text-amber-600" />}
          color="bg-amber-50"
        />
        <KpiCard
          label="Out of Service"
          value={fleet_stats.out_of_service}
          icon={<AlertTriangle className="w-5 h-5 text-red-600" />}
          color="bg-red-50"
        />
      </div>

      {/* Second row */}
      <div className="grid grid-cols-1 xl:grid-cols-3 gap-6 mb-6">
        {/* Risk Score */}
        <Card className={`border ${riskBg}`}>
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <TrendingUp className="w-4 h-4 text-slate-500" />
              <span className="text-sm font-medium text-slate-600">Fleet Risk Score</span>
            </div>
            <span className="text-xs text-slate-400">Operational</span>
          </div>
          <div className={`text-5xl font-bold ${riskColor} mb-2`}>{risk_score}<span className="text-2xl text-slate-400">/100</span></div>
          <div className="w-full bg-slate-200 rounded-full h-2">
            <div
              className={`h-2 rounded-full transition-all ${risk_score >= 70 ? 'bg-red-500' : risk_score >= 40 ? 'bg-amber-500' : 'bg-emerald-500'}`}
              style={{ width: `${risk_score}%` }}
            />
          </div>
          <p className="text-xs text-slate-500 mt-2">Calculated from fleet state, overdue maintenance, and unresolved incidents.</p>
        </Card>

        {/* Pending Approvals */}
        <Card>
          <div className="flex items-center gap-2 mb-3">
            <Activity className="w-4 h-4 text-slate-500" />
            <span className="text-sm font-medium text-slate-600">Pending Approvals</span>
          </div>
          <div className="text-5xl font-bold text-amber-600 mb-1">{fleet_stats.pending_approvals}</div>
          <p className="text-xs text-slate-500">Maintenance tasks awaiting manager approval.</p>
          {fleet_stats.pending_approvals > 0 && (
            <Link to="/maintenance" className="mt-3 inline-flex items-center text-xs text-blue-600 hover:underline font-medium">
              Review tasks →
            </Link>
          )}
        </Card>

        {/* AI Activity */}
        <Card>
          <div className="flex items-center gap-2 mb-3">
            <Zap className="w-4 h-4 text-slate-500" />
            <span className="text-sm font-medium text-slate-600">AI Activity</span>
          </div>
          <div className="text-5xl font-bold text-blue-600 mb-1">{recent_agent_actions.length}</div>
          <p className="text-xs text-slate-500">Recent agent actions recorded.</p>
          <Link to="/agent" className="mt-3 inline-flex items-center text-xs text-blue-600 hover:underline font-medium">
            View AI operations →
          </Link>
        </Card>
      </div>

      {/* Main content grid */}
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
        {/* Critical Alerts */}
        <Card padding={false}>
          <div className="px-6 py-4 border-b border-slate-100">
            <h3 className="text-sm font-semibold text-slate-900 flex items-center gap-2">
              <AlertTriangle className="w-4 h-4 text-red-500" />
              Critical Alerts
            </h3>
          </div>
          <div className="divide-y divide-slate-100">
            {critical_alerts.length === 0 ? (
              <div className="px-6 py-8 text-center text-slate-400 text-sm">No critical alerts.</div>
            ) : (
              critical_alerts.map(alert => (
                <Link
                  key={alert.incident_id}
                  to={`/agent?incident=${alert.incident_id}`}
                  className="flex items-start gap-3 px-6 py-4 hover:bg-slate-50 transition-colors"
                >
                  <div className="w-8 h-8 rounded-lg bg-red-100 flex items-center justify-center shrink-0 mt-0.5">
                    <AlertTriangle className="w-4 h-4 text-red-600" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-0.5">
                      <span className="font-semibold text-sm text-slate-900">{alert.vehicle_fleet_number}</span>
                      <Badge className={severityColor(alert.severity)}>{alert.severity}</Badge>
                    </div>
                    <p className="text-xs text-slate-500 truncate">{alert.description}</p>
                    <p className="text-xs text-slate-400 mt-0.5">{timeAgo(alert.created_at)}</p>
                  </div>
                </Link>
              ))
            )}
          </div>
        </Card>

        {/* Upcoming Maintenance */}
        <Card padding={false}>
          <div className="px-6 py-4 border-b border-slate-100">
            <h3 className="text-sm font-semibold text-slate-900 flex items-center gap-2">
              <Clock className="w-4 h-4 text-amber-500" />
              Upcoming Maintenance
            </h3>
          </div>
          <div className="divide-y divide-slate-100">
            {upcoming_maintenance.length === 0 ? (
              <div className="px-6 py-8 text-center text-slate-400 text-sm">No upcoming maintenance.</div>
            ) : (
              upcoming_maintenance.map(item => (
                <Link
                  key={item.vehicle_id}
                  to={`/vehicles/${item.vehicle_id}`}
                  className="flex items-center justify-between px-6 py-3.5 hover:bg-slate-50 transition-colors"
                >
                  <div className="flex items-center gap-3">
                    <div className={`w-2 h-2 rounded-full ${item.km_until_service <= 500 ? 'bg-red-500' : item.km_until_service <= 1500 ? 'bg-amber-500' : 'bg-blue-500'}`} />
                    <div>
                      <div className="text-sm font-medium text-slate-900">{item.fleet_number}</div>
                      <div className="text-xs text-slate-500">{item.make} {item.model}</div>
                    </div>
                  </div>
                  <div className="text-right">
                    <div className="text-sm font-semibold text-slate-700">{formatMileage(item.km_until_service)}</div>
                    <div className="text-xs text-slate-400">until service</div>
                  </div>
                </Link>
              ))
            )}
          </div>
        </Card>

        {/* Recent Agent Actions */}
        <Card padding={false} className="xl:col-span-2">
          <div className="px-6 py-4 border-b border-slate-100">
            <h3 className="text-sm font-semibold text-slate-900 flex items-center gap-2">
              <Zap className="w-4 h-4 text-blue-500" />
              Recent AI Agent Activity
            </h3>
          </div>
          <div className="divide-y divide-slate-100">
            {recent_agent_actions.length === 0 ? (
              <div className="px-6 py-8 text-center text-slate-400 text-sm">No agent activity yet. Submit an incident to activate the AI agent.</div>
            ) : (
              recent_agent_actions.slice(0, 8).map(action => (
                <div key={action.id} className="flex items-center gap-4 px-6 py-3">
                  <div className={`w-2 h-2 rounded-full shrink-0 ${action.status === 'SUCCESS' ? 'bg-emerald-500' : action.status === 'FAILED' ? 'bg-red-500' : 'bg-amber-500'}`} />
                  <div className="flex-1 min-w-0">
                    <span className="text-xs font-mono text-slate-500 mr-2">{action.action_type}</span>
                    <span className="text-sm text-slate-700 truncate">{action.description}</span>
                  </div>
                  <span className="text-xs text-slate-400 shrink-0">{timeAgo(action.created_at)}</span>
                </div>
              ))
            )}
          </div>
        </Card>
      </div>
    </div>
  );
}

function KpiCard({
  label, value, icon, color, sub,
}: {
  label: string; value: number; icon: React.ReactNode; color: string; sub?: string;
}) {
  return (
    <Card>
      <div className="flex items-start justify-between">
        <div>
          <p className="text-sm text-slate-500 mb-1">{label}</p>
          <p className="text-3xl font-bold text-slate-900">{value}</p>
          {sub && <p className="text-xs text-slate-400 mt-1">{sub}</p>}
        </div>
        <div className={`w-10 h-10 ${color} rounded-lg flex items-center justify-center`}>
          {icon}
        </div>
      </div>
    </Card>
  );
}
