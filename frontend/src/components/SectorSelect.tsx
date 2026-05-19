import { useState, useEffect, useRef } from 'react';
import { getSectores } from '../services/api';

interface Sector { id: number; nombre: string; }

interface Props {
  clienteId: string | number;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  className?: string;
  useId?: boolean; // when true, value/onChange use sector id as string
}

export default function SectorSelect({ clienteId, value, onChange, placeholder = 'Sector...', className = '', useId = false }: Props) {
  const [sectores, setSectores] = useState<Sector[]>([]);
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!clienteId) { setSectores([]); return; }
    getSectores(clienteId).then(r => setSectores(r.data as Sector[]));
  }, [clienteId]);

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  if (useId) {
    return (
      <select className={`input w-full text-sm ${className}`} value={value} onChange={e => onChange(e.target.value)}>
        <option value="">Sin sector</option>
        {sectores.map(s => <option key={s.id} value={String(s.id)}>{s.nombre}</option>)}
      </select>
    );
  }

  const names = sectores.map(s => s.nombre);
  const filtered = value ? names.filter(s => s.toLowerCase().includes(value.toLowerCase())) : names;

  return (
    <div ref={ref} className={`relative ${className}`}>
      <input
        className="input w-full text-sm"
        placeholder={placeholder}
        value={value}
        onChange={e => { onChange(e.target.value); setOpen(true); }}
        onFocus={() => { if (sectores.length) setOpen(true); }}
      />
      {open && filtered.length > 0 && (
        <div className="absolute z-50 mt-1 w-full bg-white border border-gray-200 rounded-lg shadow-lg max-h-40 overflow-y-auto">
          {filtered.map(s => (
            <button
              type="button"
              key={s}
              onClick={() => { onChange(s); setOpen(false); }}
              className="w-full text-left px-3 py-2 text-sm text-gray-700 hover:bg-primary-50 hover:text-primary-700"
            >
              {s}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
