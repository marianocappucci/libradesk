import { useState, useRef, useEffect } from 'react';
import { Search, X } from 'lucide-react';

interface Cliente { id: number; nombre: string; empresa?: string }

interface Props {
  clientes: Cliente[];
  value: string;
  onChange: (id: string) => void;
  placeholder?: string;
  required?: boolean;
  allOption?: string;
  className?: string;
}

export default function ClienteSelect({ clientes, value, onChange, placeholder = 'Buscar cliente...', required, allOption, className = '' }: Props) {
  const [search, setSearch] = useState('');
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  const selected = clientes.find(c => String(c.id) === value);

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  const filtered = clientes.filter(c => {
    const q = search.toLowerCase();
    return (c.empresa || c.nombre).toLowerCase().includes(q) || c.nombre.toLowerCase().includes(q);
  });

  const select = (id: string) => { onChange(id); setOpen(false); setSearch(''); };

  if (selected) {
    return (
      <div className={`input flex items-center justify-between gap-2 cursor-default text-sm ${className}`}>
        <span className="truncate">{selected.empresa || selected.nombre}</span>
        <button type="button" onClick={() => { onChange(''); setSearch(''); }} className="shrink-0 text-gray-400 hover:text-gray-600">
          <X size={14} />
        </button>
      </div>
    );
  }

  return (
    <div ref={ref} className={`relative ${className}`}>
      <div className="relative">
        <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-400 pointer-events-none" />
        <input
          className="input w-full text-sm pl-8"
          placeholder={placeholder}
          value={search}
          onChange={e => { setSearch(e.target.value); setOpen(true); }}
          onFocus={() => setOpen(true)}
          required={required && !value}
        />
      </div>
      {open && (
        <div className="absolute z-50 mt-1 w-full bg-white border border-gray-200 rounded-lg shadow-lg max-h-52 overflow-y-auto">
          {allOption && (
            <button type="button" onClick={() => select('')} className="w-full text-left px-3 py-2 text-sm text-gray-500 hover:bg-gray-50 border-b border-gray-100">
              {allOption}
            </button>
          )}
          {filtered.length === 0 ? (
            <p className="px-3 py-2 text-xs text-gray-400">Sin resultados</p>
          ) : (
            filtered.map(c => (
              <button
                type="button"
                key={c.id}
                onClick={() => select(String(c.id))}
                className="w-full text-left px-3 py-2 text-sm text-gray-700 hover:bg-primary-50 hover:text-primary-700"
              >
                {c.empresa || c.nombre}
                {c.empresa && c.nombre !== c.empresa && <span className="text-xs text-gray-400 ml-1.5">({c.nombre})</span>}
              </button>
            ))
          )}
        </div>
      )}
    </div>
  );
}
