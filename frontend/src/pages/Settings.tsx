import { useEffect, useState, useCallback } from 'react';
import { Bot, Cpu, KeyRound, Check, RefreshCw, AlertTriangle, Zap } from 'lucide-react';
import { getAISettings, updateAISettings, getAIModels } from '../services/api';
import type { AISettings, AIProvider } from '../types';
import { Card } from '../components/ui/Card';
import { Badge } from '../components/ui/Badge';
import { Button } from '../components/ui/Button';
import { LoadingScreen } from '../components/ui/Spinner';

const PROVIDERS: { value: AIProvider; label: string; hint: string }[] = [
  { value: 'groq', label: 'Groq', hint: 'Fast inference, OpenAI-compatible tool calling' },
  { value: 'gemini', label: 'Google Gemini', hint: 'Gemini Flash / Pro models' },
];

export function Settings() {
  const [settings, setSettings] = useState<AISettings | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Editable form state
  const [provider, setProvider] = useState<AIProvider>('groq');
  const [model, setModel] = useState('');
  const [apiKey, setApiKey] = useState('');
  const [models, setModels] = useState<string[]>([]);
  const [modelsLoading, setModelsLoading] = useState(false);
  const [customModel, setCustomModel] = useState(false);

  const loadSettings = useCallback(async () => {
    try {
      const s = await getAISettings();
      setSettings(s);
      setProvider(s.provider);
      setModel(s.provider === 'groq' ? s.groq.model : s.gemini.model);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadSettings(); }, [loadSettings]);

  const fetchModels = useCallback(async (p: AIProvider) => {
    setModelsLoading(true);
    try {
      const res = await getAIModels(p);
      setModels(res.models);
    } catch {
      setModels([]);
    } finally {
      setModelsLoading(false);
    }
  }, []);

  // When provider changes, sync the model field and auto-load the model list
  useEffect(() => {
    if (!settings) return;
    setModel(provider === 'groq' ? settings.groq.model : settings.gemini.model);
    setApiKey('');
    setCustomModel(false);
    const keyConfigured = provider === 'groq' ? settings.groq.key_configured : settings.gemini.key_configured;
    if (keyConfigured) {
      fetchModels(provider);
    } else {
      setModels([]);
    }
  }, [provider, settings, fetchModels]);

  const handleSave = async () => {
    setSaving(true);
    setSaved(false);
    setError(null);
    try {
      const payload =
        provider === 'groq'
          ? { provider, groq_model: model || undefined, groq_api_key: apiKey || undefined }
          : { provider, gemini_model: model || undefined, gemini_api_key: apiKey || undefined };
      const updated = await updateAISettings(payload);
      setSettings(updated);
      setApiKey('');
      setSaved(true);
      setTimeout(() => setSaved(false), 2500);
    } catch (e: any) {
      setError(e.message ?? 'Failed to save settings.');
    } finally {
      setSaving(false);
    }
  };

  if (loading) return <LoadingScreen />;
  if (!settings) return <div className="p-8 text-red-600">Failed to load settings.</div>;

  const providerCfg = provider === 'groq' ? settings.groq : settings.gemini;
  const activeProvider = settings.provider;

  return (
    <div className="p-8 max-w-3xl">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-slate-900 flex items-center gap-2">
          <Bot className="w-6 h-6 text-blue-600" />
          AI Settings
        </h1>
        <p className="text-slate-500 text-sm mt-1">Choose your LLM provider, model, and API key. Applied immediately — no restart needed.</p>
      </div>

      {/* Active provider banner */}
      <Card className="mb-6 border-blue-200 bg-blue-50/50">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-blue-100 flex items-center justify-center">
              <Zap className="w-5 h-5 text-blue-600" />
            </div>
            <div>
              <div className="text-sm font-medium text-slate-900">
                Active provider: <span className="font-bold">{activeProvider === 'groq' ? 'Groq' : 'Google Gemini'}</span>
              </div>
              <div className="text-xs text-slate-500">
                Model: {activeProvider === 'groq' ? settings.groq.model : settings.gemini.model}
              </div>
            </div>
          </div>
          {settings.active_key_configured ? (
            <Badge className="text-emerald-700 bg-emerald-50 border-emerald-200">
              <Check className="w-3 h-3 mr-1" /> Key configured
            </Badge>
          ) : (
            <Badge className="text-amber-700 bg-amber-50 border-amber-200">
              <AlertTriangle className="w-3 h-3 mr-1" /> No key — demo mode
            </Badge>
          )}
        </div>
      </Card>

      <Card>
        {/* Provider toggle */}
        <div className="mb-6">
          <label className="block text-sm font-medium text-slate-700 mb-2">Provider</label>
          <div className="grid grid-cols-2 gap-3">
            {PROVIDERS.map(p => {
              const isActive = provider === p.value;
              const cfg = p.value === 'groq' ? settings.groq : settings.gemini;
              return (
                <button
                  key={p.value}
                  onClick={() => setProvider(p.value)}
                  className={`text-left px-4 py-3 rounded-lg border-2 transition-colors ${
                    isActive ? 'border-blue-500 bg-blue-50' : 'border-slate-200 hover:border-slate-300 bg-white'
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <span className="font-semibold text-slate-900">{p.label}</span>
                    {cfg.key_configured && (
                      <Check className="w-4 h-4 text-emerald-500" />
                    )}
                  </div>
                  <p className="text-xs text-slate-500 mt-0.5">{p.hint}</p>
                </button>
              );
            })}
          </div>
        </div>

        {/* Model selection */}
        <div className="mb-6">
          <div className="flex items-center justify-between mb-2">
            <label className="text-sm font-medium text-slate-700 flex items-center gap-1.5">
              <Cpu className="w-4 h-4 text-slate-400" /> Model
            </label>
            <button
              onClick={() => fetchModels(provider)}
              className="text-xs text-blue-600 hover:underline flex items-center gap-1"
            >
              <RefreshCw className={`w-3 h-3 ${modelsLoading ? 'animate-spin' : ''}`} />
              Refresh models
            </button>
          </div>

          {customModel ? (
            <input
              type="text"
              value={model}
              onChange={e => setModel(e.target.value)}
              placeholder={provider === 'groq' ? 'e.g. openai/gpt-oss-120b' : 'e.g. gemini-flash-latest'}
              className="w-full px-3 py-2 text-sm border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 font-mono"
              autoFocus
            />
          ) : (
            <select
              value={model}
              onChange={e => {
                if (e.target.value === '__custom__') {
                  setCustomModel(true);
                } else {
                  setModel(e.target.value);
                }
              }}
              className="w-full px-3 py-2 text-sm border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 font-mono bg-white"
            >
              {/* Ensure the current model is always selectable even if not in the fetched list */}
              {model && !models.includes(model) && <option value={model}>{model}</option>}
              {models.map(m => (
                <option key={m} value={m}>{m}</option>
              ))}
              <option value="__custom__">✎ Enter a custom model…</option>
            </select>
          )}

          <div className="flex items-center justify-between mt-1">
            <p className="text-xs text-slate-400">
              {modelsLoading
                ? 'Fetching models…'
                : models.length > 0
                ? `${models.length} models available for this key.`
                : 'No models loaded — save a valid API key, then Refresh.'}
            </p>
            {customModel && (
              <button onClick={() => setCustomModel(false)} className="text-xs text-blue-600 hover:underline">
                Choose from list
              </button>
            )}
          </div>
        </div>

        {/* API key */}
        <div className="mb-6">
          <label className="text-sm font-medium text-slate-700 mb-2 flex items-center gap-1.5">
            <KeyRound className="w-4 h-4 text-slate-400" /> API Key
          </label>
          <input
            type="password"
            value={apiKey}
            onChange={e => setApiKey(e.target.value)}
            placeholder={providerCfg.key_configured ? `Configured (${providerCfg.key_hint}) — leave blank to keep` : 'Paste your API key'}
            className="w-full px-3 py-2 text-sm border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 font-mono"
          />
          <p className="text-xs text-slate-400 mt-1">
            Keys are stored server-side only and never returned to the browser. Leave blank to keep the existing key.
          </p>
        </div>

        {error && (
          <div className="flex items-center gap-2 text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2 mb-4">
            <AlertTriangle className="w-4 h-4 shrink-0" />
            {error}
          </div>
        )}

        <div className="flex items-center gap-3">
          <Button onClick={handleSave} loading={saving}>
            Save Settings
          </Button>
          {saved && (
            <span className="text-sm text-emerald-600 flex items-center gap-1">
              <Check className="w-4 h-4" /> Saved
            </span>
          )}
        </div>
      </Card>

      <p className="text-xs text-slate-400 mt-4">
        Tip: for faster analyses on Groq, try <span className="font-mono">openai/gpt-oss-20b</span>. For deeper reasoning, use <span className="font-mono">openai/gpt-oss-120b</span>.
      </p>
    </div>
  );
}
