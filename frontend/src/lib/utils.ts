import { clsx, type ClassValue } from 'clsx';
import type { VehicleStatus, IncidentSeverity, TaskStatus } from '../types';

export function cn(...inputs: ClassValue[]) {
  return clsx(inputs);
}

export function statusColor(status: VehicleStatus): string {
  switch (status) {
    case 'ACTIVE': return 'text-emerald-700 bg-emerald-50 border-emerald-200';
    case 'MAINTENANCE_DUE': return 'text-amber-700 bg-amber-50 border-amber-200';
    case 'OUT_OF_SERVICE': return 'text-red-700 bg-red-50 border-red-200';
    default: return 'text-slate-600 bg-slate-100 border-slate-200';
  }
}

export function statusDot(status: VehicleStatus): string {
  switch (status) {
    case 'ACTIVE': return 'bg-emerald-500';
    case 'MAINTENANCE_DUE': return 'bg-amber-500';
    case 'OUT_OF_SERVICE': return 'bg-red-500';
    default: return 'bg-slate-400';
  }
}

export function severityColor(severity?: IncidentSeverity): string {
  switch (severity) {
    case 'LOW': return 'text-emerald-700 bg-emerald-50 border-emerald-200';
    case 'MEDIUM': return 'text-amber-700 bg-amber-50 border-amber-200';
    case 'HIGH': return 'text-orange-700 bg-orange-50 border-orange-200';
    case 'CRITICAL': return 'text-red-700 bg-red-50 border-red-200';
    default: return 'text-slate-600 bg-slate-100 border-slate-200';
  }
}

export function taskStatusColor(status: TaskStatus): string {
  switch (status) {
    case 'PENDING_APPROVAL': return 'text-amber-700 bg-amber-50 border-amber-200';
    case 'APPROVED': return 'text-blue-700 bg-blue-50 border-blue-200';
    case 'IN_PROGRESS': return 'text-indigo-700 bg-indigo-50 border-indigo-200';
    case 'COMPLETED': return 'text-emerald-700 bg-emerald-50 border-emerald-200';
    case 'CANCELLED': return 'text-slate-500 bg-slate-100 border-slate-200';
    default: return 'text-slate-600 bg-slate-100 border-slate-200';
  }
}

export function formatMileage(km: number): string {
  return `${km.toLocaleString()} km`;
}

export function formatDate(dateStr?: string): string {
  if (!dateStr) return '—';
  return new Date(dateStr).toLocaleDateString('en-GB', { year: 'numeric', month: 'short', day: 'numeric' });
}

export function timeAgo(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime();
  const minutes = Math.floor(diff / 60000);
  if (minutes < 1) return 'just now';
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return formatDate(dateStr);
}
