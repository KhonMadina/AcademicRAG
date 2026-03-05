import { useEffect, useState } from 'react';
import { chatAPI, ModelsResponse } from '@/lib/api';

interface Props {
  value: string | undefined;
  onChange: (v: string) => void;
  type: 'generation' | 'embedding';
  className?: string;
  placeholder?: string;
}

export function ModelSelect({ value, onChange, type, className, placeholder }: Props) {
  const [models, setModels] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let mounted = true;
    chatAPI
      .getModels()
      .then((res: ModelsResponse) => {
        if (!mounted) return;
        const list = type === 'generation' ? res.generation_models : res.embedding_models;
        setModels(list);
        // Auto-select default gemma3:4b-cloud if available and not chosen yet
        if(!value && list.includes('gemma3:4b-cloud')){
          onChange('gemma3:4b-cloud');
        }
        setLoading(false);
      })
      .catch((e) => {
        if (!mounted) return;
        setError(String(e));
        setLoading(false);
      });
    return () => {
      mounted = false;
    };
  }, [type]);

  if (loading) {
    return (
      <select className={className} disabled>
        <option>Loading</option>
      </select>
    );
  }
  if (error || models.length === 0) {
    return (
      <select className={className} disabled>
        <option>No models</option>
      </select>
    );
  }

  return (
    <select
      className={`w-full px-2 py-2 bg-white/50 border border-white-600 text-black/70 rounded-sm text-xs focus:outline-none focus:ring-2 focus:ring-gray-200 focus:border-transparent hover:cursor-pointer ${className || ''}`}
      value={value || ''}
      onChange={(e) => onChange(e.target.value)}
    >
      <option value="" disabled>
        {placeholder || `Select ${type === 'generation' ? 'LLM' : 'embed model'}`}
      </option>
      {models.map((m) => (
        <option key={m} value={m}>
          {m}
        </option>
      ))}
    </select>
  );
} 