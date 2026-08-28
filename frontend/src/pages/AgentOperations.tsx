import { useState, useEffect, useRef, useCallback } from 'react';
import { useSearchParams, Link } from 'react-router-dom';
import {
  Bot, Send, Zap, CheckCircle2, XCircle, Loader2, AlertTriangle, RefreshCw,
  Mail, ShieldAlert, Sparkles, Clock,
} from 'lucide-react';
import {
  getVehicles, createIncident, analyzeIncident, getIncident, runFleetHealthScan, getAISettings,
} from '../services/api';
import type { Vehicle, Incident, AgentAction, FleetScanResult, AnalyzeResult, AISettings } from '../types';
import { Card } from '../components/ui/Card';
import { Badge } from '../components/ui/Badge';
import { Button } from '../components/ui/Button';
import { Spinner } from '../components/ui/Spinner';
import { severityColor, statusColor, timeAgo } from '../lib/utils';

const POLL_MS = 1500;

export function AgentOperations() {
  const [searchParams] = useSearchParams();
  const [vehicles, setVehicles] = useState<Vehicle[]>([]);
  const [aiSettings, setAiSettings] = useState<AISettings | null>(null);
  const [selectedFleet, setSelectedFleet] = useState('ET-042');
  const [reportedBy, setReportedBy] = useState('Mechanic');
  const [description, setDescription] = useState('');
  const [analyzing, setAnalyzing] = useState(false);
  const [currentIncident, setCurrentIncident] = useState<Incident | null>(null);
  const [lastResult, setLastResult] = useState<AnalyzeResult | null>(null);
  const [scanResult, setScanResult] = useState<FleetScanResult | null>(null);
  const [scanning, setScanning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const pollRef = useRef<number | null>(null);

  const stopPolling = useCallback(() => {
    if (pollRef.current !== null) {
      window.clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, []);

  useEffect(() => {
    getVehicles().then(setVehicles).catch(() => {});
    getAISettings().then(setAiSettings).catch(() => {});
    const incidentId = searchParams.get('incident');
    if (incidentId) {
      getIncident(incidentId).then(setCurrentIncident).catch(e => setError(e.message));
    }
    return stopPolling;
  }, [searchParams, stopPolling]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!description.trim()) return;
    setError(null);
    setLastResult(null);
    setAnalyzing(true);
    setCurrentIncident(null);

    try {
      const incident = await createIncident({ fleet_number: selectedFleet, reported_by: reportedBy, description });
      setCurrentIncident(incident);

      // Each agent action is committed as it happens — poll so the timeline streams in live.
      pollRef.current = window.setInterval(async () => {
        try {
          const fresh = await getIncident(incident.id);
          setCurrentIncident(fresh);
        } catch { /* transient — keep polling */ }
      }, POLL_MS);

      const result = await analyzeIncident(incident.id);
      setLastResult(result);
      stopPolling();
      setCurrentIncident(await getIncident(incident.id));
    } catch (e: any) {
      setError(e.message ?? 'Analysis failed.');
      stopPolling();
      if (currentIncident) {
        getIncident(currentIncident.id).then(setCurrentIncident).catch(() => {});
      }
    } finally {
      stopPolling();
      setAnalyzing(false);
    }
  };

  const handleFleetScan = async () => {
    setScanning(true);
    setScanResult(null);
    setError(null);
    try {
      setScanResult(await runFleetHealthScan());
    } catch (e: any) {
      setError(e.message);
    } finally {
      setScanning(false);
    }
  };

  const noKey = aiSettings ? !aiSettings.active_key_configured : false;

  return (
    <div className="p-4 md:p-8">
      <div className="mb-6 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 flex items-center gap-2">
            <Bot className="w-6 h-6 text-blue-600" />
            AI Operations
          </h1>
          <p className="text-slate-500 text-sm mt-1">Submit maintenance reports and run the proactive fleet scan</p>
        </div>
        <Button variant="secondary" onClick={handleFleetScan} loading={scanning} className="flex items-center gap-2">
          <RefreshCw className="w-4 h-4" />
          Run Fleet Health Scan
        </Button>
      </div>

      {noKey && (
        <div className="mb-6 flex items-start gap-3 text-sm text-amber-800 bg-amber-50 border border-amber-200 rounded-lg px-4 py-3">
          <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
          <div>
            <span className="font-semibold">No AI provider key configured — analyses run in demo mode</span> (keyword rules,
            not an LLM). Add a Gemini key in <Link to="/settings" className="underline font-medium">Settings</Link> for live AI.
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
        {/* Incident input */}
        <div className="space-y-4">
          <Card>
            <h3 className="text-sm font-semibold text-slate-900 mb-4 flex items-center gap-2">
              <Send className="w-4 h-4 text-blue-600" />
              Submit Maintenance Incident
            </h3>
            <form onSubmit={handleSubmit} className="space-y-4">
              <div>
                <label className="block text-xs font-medium text-slate-600 mb-1.5">Vehicle</label>
                <select
                  value={selectedFleet}
                  onChange={e => setSelectedFleet(e.target.value)}
                  className="w-full px-3 py-2 text-sm border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 bg-white"
                  disabled={analyzing}
                >
                  {vehicles.map(v => (
                    <option key={v.id} value={v.fleet_number}>
                      {v.fleet_number} — {v.year} {v.make} {v.model} ({v.status.replace('_', ' ')})
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-600 mb-1.5">Reported By</label>
                <input
                  type="text"
                  value={reportedBy}
                  onChange={e => setReportedBy(e.target.value)}
                  className="w-full px-3 py-2 text-sm border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                  placeholder="Mechanic name"
                  disabled={analyzing}
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-600 mb-1.5">Maintenance Report</label>
                <textarea
                  value={description}
                  onChange={e => setDescription(e.target.value)}
                  rows={5}
                  className="w-full px-3 py-2 text-sm border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none"
                  placeholder="e.g. Vehicle ET-042 has a grinding noise when braking and the brake pedal feels softer than usual."
                  disabled={analyzing}
                />
              </div>

              {/* Quick demo buttons */}
              <div className="flex gap-2 flex-wrap">
                <button
                  type="button"
                  onClick={() => { setSelectedFleet('ET-042'); setDescription('Vehicle ET-042 has a grinding noise when braking and the brake pedal feels softer than usual.'); }}
                  className="text-xs text-blue-600 border border-blue-200 bg-blue-50 px-2 py-1 rounded hover:bg-blue-100"
                >
                  Demo: Critical Brake Issue
                </button>
                <button
                  type="button"
                  onClick={() => { setSelectedFleet('ET-019'); setDescription('Engine temperature warning light is on. Vehicle is overheating during long routes and coolant level drops every few days.'); }}
                  className="text-xs text-amber-600 border border-amber-200 bg-amber-50 px-2 py-1 rounded hover:bg-amber-100"
                >
                  Demo: Engine Overheating (Ford Transit)
                </button>
                <button
                  type="button"
                  onClick={() => { setSelectedFleet('ET-014'); setDescription('Driver reports a slow puncture on the rear left tyre and slight vibration above 80 km/h.'); }}
                  className="text-xs text-emerald-600 border border-emerald-200 bg-emerald-50 px-2 py-1 rounded hover:bg-emerald-100"
                >
                  Demo: Minor Tyre Issue
                </button>
              </div>

              {error && (
                <div className="flex items-center gap-2 text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2">
                  <AlertTriangle className="w-4 h-4 shrink-0" />
                  {error}
                </div>
              )}

              <Button type="submit" loading={analyzing} className="w-full" disabled={!description.trim()}>
                {analyzing ? 'Analyzing with FleetPilot...' : 'Analyze with FleetPilot'}
              </Button>
            </form>
          </Card>

          {/* Fleet scan results */}
          {scanResult && <ScanResultCard result={scanResult} />}
        </div>

        {/* Agent activity panel */}
        <div>
          {analyzing && !currentIncident && (
            <Card className="flex flex-col items-center justify-center py-12 gap-3">
              <Spinner size="lg" />
              <p className="text-sm text-slate-600 font-medium">FleetPilot is analyzing the incident...</p>
              <p className="text-xs text-slate-400">Retrieving vehicle data and calling AI tools</p>
            </Card>
          )}

          {currentIncident && (
            <div className="space-y-4">
              {lastResult?.demo_mode && (
                <div className="flex items-start gap-2 text-sm text-amber-800 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2">
                  <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
                  <span>
                    <span className="font-semibold">Demo mode:</span> this analysis used keyword rules, not an LLM
                    {lastResult.demo_reason ? ` (${lastResult.demo_reason})` : ''}. Check your provider key in{' '}
                    <Link to="/settings" className="underline">Settings</Link>.
                  </span>
                </div>
              )}

              {lastResult?.analysis_source === 'synthesized_from_actions' && (
                <div className="flex items-start gap-2 text-sm text-blue-800 bg-blue-50 border border-blue-200 rounded-lg px-3 py-2">
                  <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
                  <span>
                    {lastResult.provider} was rate-limited before submitting its final verdict — the task, parts, status change
                    and notification below were executed by the model; the summary was assembled from those actions.
                  </span>
                </div>
              )}

              {/* Analysis result */}
              {currentIncident.ai_analysis && (
                <Card>
                  <div className="flex items-center justify-between mb-4">
                    <h3 className="text-sm font-semibold text-slate-900 flex items-center gap-2">
                      <Bot className="w-4 h-4 text-blue-600" />
                      AI Analysis
                    </h3>
                    {lastResult?.provider && !lastResult.demo_mode && (
                      <Badge className="text-blue-700 bg-blue-50 border-blue-200">
                        <Sparkles className="w-3 h-3 mr-1" /> {lastResult.provider}
                      </Badge>
                    )}
                  </div>
                  <div className="space-y-3">
                    <div className="flex flex-wrap gap-2">
                      <Badge className={severityColor(currentIncident.ai_analysis.severity)}>
                        {currentIncident.ai_analysis.severity}
                      </Badge>
                      <Badge className="text-purple-700 bg-purple-50 border-purple-200">
                        {currentIncident.ai_analysis.category.replace(/_/g, ' ')}
                      </Badge>
                      <Badge className={statusColor(currentIncident.ai_analysis.vehicle_status)}>
                        {currentIncident.ai_analysis.vehicle_status.replace(/_/g, ' ')}
                      </Badge>
                      {currentIncident.ai_analysis.requires_manager_approval && (
                        <Badge className="text-amber-700 bg-amber-50 border-amber-200">
                          Requires Approval
                        </Badge>
                      )}
                    </div>

                    <p className="text-sm text-slate-700">{currentIncident.ai_analysis.summary}</p>

                    {currentIncident.ai_analysis.possible_causes.length > 0 && (
                      <div>
                        <p className="text-xs font-medium text-slate-500 mb-1">Possible Causes</p>
                        <ul className="text-sm text-slate-600 space-y-1">
                          {currentIncident.ai_analysis.possible_causes.map((c, i) => (
                            <li key={i} className="flex items-start gap-1.5">
                              <span className="text-slate-400 mt-0.5">•</span>{c}
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}

                    {currentIncident.ai_analysis.recommended_actions.length > 0 && (
                      <div>
                        <p className="text-xs font-medium text-slate-500 mb-1">Recommended Actions</p>
                        <ul className="text-sm text-slate-600 space-y-1">
                          {currentIncident.ai_analysis.recommended_actions.map((a, i) => (
                            <li key={i} className="flex items-start gap-1.5">
                              <span className="text-slate-400 mt-0.5">{i + 1}.</span>{a}
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}

                    {currentIncident.ai_analysis.required_parts.length > 0 && (
                      <div>
                        <p className="text-xs font-medium text-slate-500 mb-1">Required Parts</p>
                        <div className="flex flex-wrap gap-1">
                          {currentIncident.ai_analysis.required_parts.map((p, i) => (
                            <span key={i} className="text-xs bg-slate-100 text-slate-600 px-2 py-1 rounded">
                              {p.name} ×{p.quantity}
                            </span>
                          ))}
                        </div>
                      </div>
                    )}

                    {(currentIncident.ai_analysis.related_recalls?.length ?? 0) > 0 && (
                      <div className="flex items-start gap-2 text-xs text-red-700 bg-red-50 border border-red-200 rounded-lg px-3 py-2">
                        <ShieldAlert className="w-4 h-4 shrink-0" />
                        <span>
                          Related open NHTSA recall{currentIncident.ai_analysis.related_recalls!.length > 1 ? 's' : ''}:{' '}
                          <span className="font-mono font-medium">{currentIncident.ai_analysis.related_recalls!.join(', ')}</span>
                        </span>
                      </div>
                    )}
                  </div>
                </Card>
              )}

              {/* Agent activity timeline */}
              {currentIncident.agent_actions && currentIncident.agent_actions.length > 0 && (
                <Card padding={false}>
                  <div className="px-5 py-4 border-b border-slate-100 flex items-center justify-between">
                    <h3 className="text-sm font-semibold text-slate-900 flex items-center gap-2">
                      <Zap className="w-4 h-4 text-blue-600" />
                      FleetPilot Agent Activity
                    </h3>
                    <span className="text-xs text-slate-400">{currentIncident.agent_actions.length} tool calls</span>
                  </div>
                  <div className="divide-y divide-slate-50">
                    {currentIncident.agent_actions.map((action, i) => (
                      <AgentActionRow key={action.id} action={action} isLast={i === currentIncident.agent_actions!.length - 1 && !analyzing} />
                    ))}
                    {analyzing && (
                      <div className="flex items-center gap-3 px-5 py-3">
                        <Loader2 className="w-4 h-4 text-blue-500 animate-spin" />
                        <span className="text-sm text-slate-500">Reasoning about next step...</span>
                      </div>
                    )}
                  </div>
                </Card>
              )}
            </div>
          )}

          {!analyzing && !currentIncident && (
            <div className="card p-8 flex flex-col items-center justify-center gap-3 border-dashed">
              <Bot className="w-10 h-10 text-slate-300" />
              <p className="text-sm text-slate-400 text-center">
                Submit a maintenance report to activate the FleetPilot agent.
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function AgentActionRow({ action, isLast }: { action: AgentAction; isLast: boolean }) {
  const icon = action.status === 'SUCCESS'
    ? <CheckCircle2 className="w-4 h-4 text-emerald-500" />
    : action.status === 'FAILED'
    ? <XCircle className="w-4 h-4 text-red-500" />
    : <Loader2 className="w-4 h-4 text-blue-500 animate-spin" />;

  return (
    <div className="flex items-start gap-3 px-5 py-3">
      <div className="w-5 shrink-0 flex flex-col items-center mt-0.5">
        {icon}
        {!isLast && <div className="w-px flex-1 bg-slate-200 mt-1.5 mb-0" style={{ minHeight: '12px' }} />}
      </div>
      <div className="flex-1 min-w-0 pb-0.5">
        <div className="flex items-center gap-2">
          <span className="text-xs font-mono text-slate-500">{action.tool_name ?? action.action_type}</span>
          <span className="text-xs text-slate-400">{timeAgo(action.created_at)}</span>
        </div>
        <p className="text-sm text-slate-700 mt-0.5">{action.description}</p>
      </div>
    </div>
  );
}

function ScanResultCard({ result }: { result: FleetScanResult }) {
  const emailStatus = result.digest_email_status;
  const emailColor =
    emailStatus === 'SENT' ? 'text-emerald-700 bg-emerald-50 border-emerald-200'
    : emailStatus === 'SIMULATED' ? 'text-blue-700 bg-blue-50 border-blue-200'
    : emailStatus === 'FAILED' ? 'text-red-700 bg-red-50 border-red-200'
    : 'text-slate-600 bg-slate-100 border-slate-200';

  return (
    <Card>
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold text-slate-900 flex items-center gap-2">
          <Zap className="w-4 h-4 text-blue-600" />
          Fleet Health Scan Results
        </h3>
        <span className="text-xs text-slate-400 flex items-center gap-1">
          <Clock className="w-3 h-3" /> {result.triggered_by}
        </span>
      </div>
      <div className="grid grid-cols-2 sm:grid-cols-5 gap-3 mb-4">
        <ScanStat label="Scanned" value={result.vehicles_scanned} />
        <ScanStat label="Overdue" value={result.overdue_found} color="text-red-600" />
        <ScanStat label="Upcoming" value={result.upcoming_found} color="text-amber-600" />
        <ScanStat label="Open Recalls" value={result.recalls_found} color="text-purple-600" />
        <ScanStat label="Tasks Created" value={result.tasks_created} color="text-blue-600" />
      </div>

      {result.findings.length > 0 && (
        <div className="border-t border-slate-100 pt-3 space-y-2 mb-4">
          {result.findings.slice(0, 10).map((f, i) => (
            <div key={i} className="flex items-start justify-between gap-3 text-xs">
              <div className="flex items-start gap-2 min-w-0">
                <span className={`w-1.5 h-1.5 mt-1.5 shrink-0 rounded-full ${f.type === 'OVERDUE' ? 'bg-red-500' : f.type === 'RECALL' ? 'bg-purple-500' : 'bg-amber-500'}`} />
                <div className="min-w-0">
                  <span className="font-mono font-medium">{f.fleet_number}</span>
                  <span className="text-slate-500 ml-2">{f.make} {f.model}</span>
                  {f.type === 'RECALL' && (
                    <p className="text-slate-500 truncate">
                      <span className="font-mono">{f.campaign_number}</span> · {f.component}
                    </p>
                  )}
                </div>
              </div>
              <span className={`shrink-0 ${f.type === 'OVERDUE' ? 'text-red-600 font-medium' : f.type === 'RECALL' ? 'text-purple-600 font-medium' : 'text-amber-600'}`}>
                {f.type === 'OVERDUE' && `${f.km_overdue?.toLocaleString()} km overdue`}
                {f.type === 'UPCOMING' && `${f.km_remaining?.toLocaleString()} km left`}
                {f.type === 'RECALL' && `${f.recall_count} open recall${(f.recall_count ?? 0) !== 1 ? 's' : ''}`}
              </span>
            </div>
          ))}
        </div>
      )}

      {result.digest && (
        <div className="border-t border-slate-100 pt-4">
          <div className="flex items-center justify-between mb-2 flex-wrap gap-2">
            <p className="text-xs font-semibold text-slate-700 flex items-center gap-1.5">
              <Mail className="w-3.5 h-3.5 text-slate-400" /> Manager digest
              {result.digest_provider && <span className="font-normal text-slate-400">· written by {result.digest_provider}</span>}
            </p>
            {emailStatus && <Badge className={emailColor}>Email {emailStatus.toLowerCase()}</Badge>}
          </div>
          <pre className="text-xs text-slate-700 whitespace-pre-wrap font-sans bg-slate-50 rounded-lg p-3 max-h-64 overflow-auto">{result.digest}</pre>
          {result.reminders_sent > 0 && (
            <p className="text-xs text-amber-700 mt-2">Reminder sent for {result.reminders_sent} task(s) waiting for approval.</p>
          )}
        </div>
      )}
    </Card>
  );
}

function ScanStat({ label, value, color = 'text-slate-900' }: { label: string; value: number; color?: string }) {
  return (
    <div className="bg-slate-50 rounded-lg p-3">
      <div className={`text-2xl font-bold ${color}`}>{value}</div>
      <div className="text-xs text-slate-500 mt-0.5">{label}</div>
    </div>
  );
}
