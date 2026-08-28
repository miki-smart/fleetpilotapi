import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Search, Filter } from 'lucide-react';
import { getVehicles } from '../services/api';
import type { Vehicle, VehicleStatus } from '../types';
import { Card } from '../components/ui/Card';
import { Badge } from '../components/ui/Badge';
import { LoadingScreen } from '../components/ui/Spinner';
import { statusColor, statusDot, formatMileage } from '../lib/utils';

const STATUS_FILTERS: { label: string; value: VehicleStatus | '' }[] = [
  { label: 'All', value: '' },
  { label: 'Active', value: 'ACTIVE' },
  { label: 'Maintenance Due', value: 'MAINTENANCE_DUE' },
  { label: 'Out of Service', value: 'OUT_OF_SERVICE' },
];

export function Vehicles() {
  const [vehicles, setVehicles] = useState<Vehicle[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState<VehicleStatus | ''>('');

  useEffect(() => {
    getVehicles()
      .then(setVehicles)
      .finally(() => setLoading(false));
  }, []);

  const filtered = vehicles.filter(v => {
    const matchesSearch =
      v.fleet_number.toLowerCase().includes(search.toLowerCase()) ||
      v.make.toLowerCase().includes(search.toLowerCase()) ||
      v.model.toLowerCase().includes(search.toLowerCase()) ||
      (v.vin ?? '').toLowerCase().includes(search.toLowerCase());
    const matchesStatus = !statusFilter || v.status === statusFilter;
    return matchesSearch && matchesStatus;
  });

  if (loading) return <LoadingScreen />;

  return (
    <div className="p-8">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-slate-900">Fleet Vehicles</h1>
        <p className="text-slate-500 text-sm mt-1">{vehicles.length} vehicles registered</p>
      </div>

      {/* Search & Filter */}
      <div className="flex items-center gap-3 mb-6">
        <div className="relative flex-1 max-w-sm">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
          <input
            type="text"
            placeholder="Search fleet number, make, model..."
            value={search}
            onChange={e => setSearch(e.target.value)}
            className="w-full pl-9 pr-4 py-2 text-sm border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
          />
        </div>
        <div className="flex items-center gap-2">
          <Filter className="w-4 h-4 text-slate-400" />
          {STATUS_FILTERS.map(f => (
            <button
              key={f.value}
              onClick={() => setStatusFilter(f.value)}
              className={`px-3 py-1.5 text-xs font-medium rounded-full border transition-colors ${
                statusFilter === f.value
                  ? 'bg-blue-600 text-white border-blue-600'
                  : 'bg-white text-slate-600 border-slate-300 hover:bg-slate-50'
              }`}
            >
              {f.label}
            </button>
          ))}
        </div>
      </div>

      {/* Vehicle Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
        {filtered.map(vehicle => (
          <Link key={vehicle.id} to={`/vehicles/${vehicle.id}`}>
            <Card className="hover:shadow-md transition-shadow cursor-pointer h-full">
              <div className="flex items-start justify-between mb-3">
                <div>
                  <div className="text-xs font-mono text-blue-600 font-semibold mb-1">{vehicle.fleet_number}</div>
                  <div className="font-semibold text-slate-900">{vehicle.year} {vehicle.make} {vehicle.model}</div>
                </div>
                <Badge className={statusColor(vehicle.status)}>
                  <span className={`w-1.5 h-1.5 rounded-full mr-1.5 ${statusDot(vehicle.status)}`} />
                  {vehicle.status.replace('_', ' ')}
                </Badge>
              </div>
              <div className="grid grid-cols-2 gap-y-2 text-sm">
                <div>
                  <div className="text-xs text-slate-400">Mileage</div>
                  <div className="font-medium text-slate-700">{formatMileage(vehicle.mileage)}</div>
                </div>
                <div>
                  <div className="text-xs text-slate-400">Fuel</div>
                  <div className="font-medium text-slate-700">{vehicle.fuel_type ?? '—'}</div>
                </div>
                {vehicle.km_until_service !== null && vehicle.km_until_service !== undefined && (
                  <div className="col-span-2">
                    <div className="text-xs text-slate-400">Next Service</div>
                    <div className={`font-medium text-sm ${(vehicle.km_until_service ?? 0) <= 0 ? 'text-red-600' : (vehicle.km_until_service ?? 0) <= 2000 ? 'text-amber-600' : 'text-slate-700'}`}>
                      {(vehicle.km_until_service ?? 0) <= 0
                        ? `Overdue by ${formatMileage(Math.abs(vehicle.km_until_service ?? 0))}`
                        : `In ${formatMileage(vehicle.km_until_service ?? 0)}`}
                    </div>
                  </div>
                )}
              </div>
            </Card>
          </Link>
        ))}
        {filtered.length === 0 && (
          <div className="col-span-3 py-16 text-center text-slate-400">No vehicles match your search.</div>
        )}
      </div>
    </div>
  );
}
