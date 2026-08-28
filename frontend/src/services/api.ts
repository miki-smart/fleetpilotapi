import axios from 'axios';
import type {
  DashboardData, Vehicle, Incident, MaintenanceTask,
  Notification, AgentAction, FleetScanResult,
  AISettings, UpdateAISettingsPayload
} from '../types';

const BASE_URL = import.meta.env.VITE_API_URL || '';

const api = axios.create({
  baseURL: BASE_URL,
  headers: { 'Content-Type': 'application/json' },
});

function unwrap<T>(response: { data: { success: boolean; data: T; error?: { message: string } } }): T {
  if (!response.data.success) {
    throw new Error(response.data.error?.message ?? 'API error');
  }
  return response.data.data;
}

// Dashboard
export const getDashboard = () =>
  api.get<{ success: boolean; data: DashboardData }>('/api/dashboard').then(unwrap);

// Vehicles
export const getVehicles = (status?: string) =>
  api.get<{ success: boolean; data: Vehicle[] }>('/api/vehicles', { params: status ? { status } : {} }).then(unwrap);

export const getVehicle = (id: string) =>
  api.get<{ success: boolean; data: Vehicle & { maintenance_history: any[]; incidents: any[] } }>(`/api/vehicles/${id}`).then(unwrap);

export const decodeVIN = (vin: string, force = false) =>
  api.post<{ success: boolean; source: string; data: any; error?: { message: string } }>(
    '/api/vehicles/decode-vin', { vin, force }
  ).then(r => r.data);

// Incidents
export const getIncidents = () =>
  api.get<{ success: boolean; data: Incident[] }>('/api/incidents').then(unwrap);

export const getIncident = (id: string) =>
  api.get<{ success: boolean; data: Incident }>(`/api/incidents/${id}`).then(unwrap);

export const createIncident = (data: { fleet_number: string; reported_by?: string; description: string }) =>
  api.post<{ success: boolean; data: Incident }>('/api/incidents', data).then(unwrap);

export const analyzeIncident = (id: string) =>
  api.post<{ success: boolean; data: any }>(`/api/incidents/${id}/analyze`).then(unwrap);

// Maintenance
export const getMaintenance = () =>
  api.get<{ success: boolean; data: MaintenanceTask[] }>('/api/maintenance').then(unwrap);

export const approveTask = (id: string) =>
  api.post<{ success: boolean; data: MaintenanceTask }>(`/api/maintenance/tasks/${id}/approve`).then(unwrap);

export const rejectTask = (id: string) =>
  api.post<{ success: boolean; data: MaintenanceTask }>(`/api/maintenance/tasks/${id}/reject`).then(unwrap);

// Notifications
export const getNotifications = () =>
  api.get<{ success: boolean; data: Notification[] }>('/api/notifications').then(unwrap);

export const getAgentActions = () =>
  api.get<{ success: boolean; data: AgentAction[] }>('/api/notifications/agent-actions').then(unwrap);

// Automation
export const runFleetHealthScan = () =>
  api.post<{ success: boolean; data: FleetScanResult }>('/api/automation/fleet-health-scan').then(unwrap);

// AI Settings
export const getAISettings = () =>
  api.get<{ success: boolean; data: AISettings }>('/api/settings/ai').then(unwrap);

export const updateAISettings = (payload: UpdateAISettingsPayload) =>
  api.post<{ success: boolean; data: AISettings }>('/api/settings/ai', payload).then(unwrap);

export const getAIModels = (provider: string) =>
  api.get<{ success: boolean; data: { provider: string; models: string[] } }>(
    '/api/settings/ai/models', { params: { provider } }
  ).then(unwrap);
