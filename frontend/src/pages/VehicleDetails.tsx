import { useEffect, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { ArrowLeft, Calendar, Gauge, Fuel, Hash, RefreshCw, Cloud, Database, AlertTriangle } from 'lucide-react';
import { getVehicle, decodeVIN } from '../services/api';
import { Card } from '../components/ui/Card';
import { Badge } from '../components/ui/Badge';
import { Button } from '../components/ui/Button';
import { LoadingScreen } from '../components/ui/Spinner';
import { statusColor, statusDot, severityColor, formatMileage, formatDate } from '../lib/utils';
import type { Vehicle, MaintenanceRecord, Incident } from '../types';

type VehicleDetail = Vehicle & {
  maintenance_history: MaintenanceRecord[];
  incidents: Incident[];
};

interface VinDecodeResult {
  source: string;
  make?: string;
  model?: string;
  year?: string;
  body_class?: string;
  fuel_type?: string;
  engine_displacement?: string;
  drive_type?: string;
  manufacturer?: string;
  plant_country?: string;
  vehicle_type?: string;
  error_text?: string;
}

export function VehicleDetails() {
  const { id } = useParams<{ id: string }>();
  const [data, setData] = useState<VehicleDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [vinLoading, setVinLoading] = useState(false);
  const [vinResult, setVinResult] = useState<VinDecodeResult | null>(null);
  const [vinError, setVinError] = useState<string | null>(null);

  useEffect(() => {
    if (!id) return;
    getVehicle(id)
      .then(d => setData(d as VehicleDetail))
      .catch(e => setError(e.message))
      .finally(() => setLoading(false));
  }, [id]);

  const handleDecodeVin = async () => {
    if (!data?.vin) return;
    setVinLoading(true);
    setVinError(null);
    setVinResult(null);
    try {
      const res = await decodeVIN(data.vin, true);
      if (!res.success) {
        setVinError(res.error?.message ?? 'Decode failed.');
      } else if (res.data?.error && !res.data?.make) {
        setVinError(res.data.error);
      } else {
        setVinResult({ source: res.source, ...res.data });
      }
    } catch (e: any) {
      setVinError(e.message ?? 'NHTSA API unavailable.');
    } finally {
      setVinLoading(false);
    }
  };

  if (loading) return <LoadingScreen />;
  if (error || !data) return <div className="p-8 text-red-600">Vehicle not found.</div>;

  return (
    <div className="p-4 md:p-8">
      <Link to="/vehicles" className="flex items-center gap-1.5 text-sm text-slate-500 hover:text-slate-700 mb-6">
        <ArrowLeft className="w-4 h-4" />
        Back to Fleet
      </Link>

      {/* Vehicle header */}
      <div className="flex items-start justify-between mb-8">
        <div>
          <div className="text-xs font-mono text-blue-600 font-bold mb-1">{data.fleet_number}</div>
          <h1 className="text-2xl font-bold text-slate-900">{data.year} {data.make} {data.model}</h1>
        </div>
        <Badge className={statusColor(data.status)}>
          <span className={`w-1.5 h-1.5 rounded-full mr-1.5 ${statusDot(data.status)}`} />
          {data.status.replace('_', ' ')}
        </Badge>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
        {/* Vehicle info */}
        <div className="space-y-4">
          <Card>
            <h3 className="text-sm font-semibold text-slate-700 mb-4">Vehicle Information</h3>
            <dl className="space-y-3">
              <InfoRow icon={<Hash className="w-4 h-4" />} label="VIN" value={data.vin ?? 'Not recorded'} mono />
              <InfoRow icon={<Gauge className="w-4 h-4" />} label="Mileage" value={formatMileage(data.mileage)} />
              <InfoRow icon={<Fuel className="w-4 h-4" />} label="Fuel Type" value={data.fuel_type ?? '—'} />
              <InfoRow icon={<Calendar className="w-4 h-4" />} label="Last Service" value={formatDate(data.last_service_date)} />
              {data.next_service_mileage && (
                <InfoRow icon={<Gauge className="w-4 h-4" />} label="Next Service" value={formatMileage(data.next_service_mileage)} />
              )}
              {data.km_until_service !== undefined && data.km_until_service !== null && (
                <InfoRow
                  icon={<Gauge className="w-4 h-4" />}
                  label="Until Service"
                  value={data.km_until_service <= 0 ? `OVERDUE by ${formatMileage(Math.abs(data.km_until_service))}` : formatMileage(data.km_until_service)}
                  className={data.km_until_service <= 0 ? 'text-red-600 font-semibold' : data.km_until_service <= 2000 ? 'text-amber-600 font-semibold' : undefined}
                />
              )}
            </dl>

            {data.vin && (
              <div className="mt-4 pt-4 border-t border-slate-100">
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={handleDecodeVin}
                  loading={vinLoading}
                  className="w-full flex items-center justify-center gap-2"
                >
                  <Cloud className="w-4 h-4" />
                  {vinLoading ? 'Syncing from NHTSA...' : 'Sync VIN from NHTSA API'}
                </Button>
              </div>
            )}
          </Card>

          {/* NHTSA VIN decode result */}
          {(vinResult || vinError) && (
            <Card>
              <div className="flex items-center justify-between mb-3">
                <h3 className="text-sm font-semibold text-slate-700 flex items-center gap-2">
                  <Cloud className="w-4 h-4 text-blue-600" />
                  VIN Decode
                </h3>
                {vinResult && (
                  <Badge className={vinResult.source === 'nhtsa' ? 'text-blue-700 bg-blue-50 border-blue-200' : 'text-slate-600 bg-slate-100 border-slate-200'}>
                    {vinResult.source === 'nhtsa' ? (
                      <><Cloud className="w-3 h-3 mr-1" /> NHTSA API</>
                    ) : (
                      <><Database className="w-3 h-3 mr-1" /> Local DB</>
                    )}
                  </Badge>
                )}
              </div>

              {vinError ? (
                <div className="flex items-start gap-2 text-sm text-amber-700 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2">
                  <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
                  <span>{vinError}</span>
                </div>
              ) : vinResult ? (
                <dl className="space-y-2.5">
                  <VinRow label="Manufacturer" value={vinResult.manufacturer} />
                  <VinRow label="Make" value={vinResult.make} />
                  <VinRow label="Model" value={vinResult.model} />
                  <VinRow label="Model Year" value={vinResult.year} />
                  <VinRow label="Vehicle Type" value={vinResult.vehicle_type} />
                  <VinRow label="Body Class" value={vinResult.body_class} />
                  <VinRow label="Engine (L)" value={vinResult.engine_displacement} />
                  <VinRow label="Drive Type" value={vinResult.drive_type} />
                  <VinRow label="Fuel Type" value={vinResult.fuel_type} />
                  <VinRow label="Plant Country" value={vinResult.plant_country} />
                  {vinResult.error_text && (
                    <p className="text-xs text-slate-400 pt-1 border-t border-slate-100">NHTSA note: {vinResult.error_text}</p>
                  )}
                </dl>
              ) : null}
            </Card>
          )}
        </div>

        {/* Maintenance history */}
        <div className="xl:col-span-2 space-y-4">
          <Card padding={false}>
            <div className="px-6 py-4 border-b border-slate-100">
              <h3 className="text-sm font-semibold text-slate-900">Maintenance History</h3>
            </div>
            {data.maintenance_history.length === 0 ? (
              <div className="px-6 py-8 text-slate-400 text-sm text-center">No maintenance records.</div>
            ) : (
              <div className="divide-y divide-slate-100">
                {data.maintenance_history.map(record => (
                  <div key={record.id} className="flex items-start gap-4 px-6 py-4">
                    <div className="w-2 h-2 rounded-full bg-blue-400 mt-2 shrink-0" />
                    <div className="flex-1">
                      <div className="flex items-center justify-between">
                        <span className="font-medium text-sm text-slate-900">{record.maintenance_type}</span>
                        <span className="text-xs text-slate-400">{formatDate(record.performed_at)}</span>
                      </div>
                      {record.description && <p className="text-xs text-slate-500 mt-0.5">{record.description}</p>}
                      {record.mileage && <p className="text-xs text-slate-400 mt-0.5">at {formatMileage(record.mileage)}</p>}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </Card>

          {/* Active incidents */}
          {data.incidents.length > 0 && (
            <Card padding={false}>
              <div className="px-6 py-4 border-b border-slate-100">
                <h3 className="text-sm font-semibold text-slate-900">Incidents</h3>
              </div>
              <div className="divide-y divide-slate-100">
                {data.incidents.map(incident => (
                  <div key={incident.id} className="flex items-start gap-4 px-6 py-4">
                    <div className="flex-1">
                      <div className="flex items-center gap-2 mb-1">
                        {incident.severity && <Badge className={severityColor(incident.severity)}>{incident.severity}</Badge>}
                        <span className="text-xs text-slate-400">{incident.status}</span>
                      </div>
                      <p className="text-sm text-slate-700">{incident.description}</p>
                      <p className="text-xs text-slate-400 mt-0.5">{formatDate(incident.created_at)}</p>
                    </div>
                  </div>
                ))}
              </div>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}

function InfoRow({
  icon, label, value, mono, className,
}: {
  icon: React.ReactNode; label: string; value: string; mono?: boolean; className?: string;
}) {
  return (
    <div className="flex items-center gap-2">
      <span className="text-slate-400">{icon}</span>
      <dt className="text-xs text-slate-400 w-24 shrink-0">{label}</dt>
      <dd className={`text-sm text-slate-700 ${mono ? 'font-mono text-xs' : ''} ${className ?? ''}`}>{value}</dd>
    </div>
  );
}

function VinRow({ label, value }: { label: string; value?: string }) {
  if (!value) return null;
  return (
    <div className="flex items-center justify-between gap-2">
      <dt className="text-xs text-slate-400 shrink-0">{label}</dt>
      <dd className="text-sm text-slate-700 text-right">{value}</dd>
    </div>
  );
}
