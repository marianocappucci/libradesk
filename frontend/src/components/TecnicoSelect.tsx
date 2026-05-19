import { useEffect, useState } from 'react';
import { getTecnicos } from '../services/api';

interface Tecnico { id: number; nombre: string; activo: boolean; }

interface Props {
  value: string;
  onChange: (val: string) => void;
  className?: string;
}

export default function TecnicoSelect({ value, onChange, className = 'input' }: Props) {
  const [tecnicos, setTecnicos] = useState<Tecnico[]>([]);

  useEffect(() => {
    getTecnicos().then(r => setTecnicos(r.data.filter((t: Tecnico) => t.activo)));
  }, []);

  return (
    <select className={className} value={value} onChange={e => onChange(e.target.value)}>
      <option value="">Sin asignar</option>
      {tecnicos.map(t => (
        <option key={t.id} value={String(t.id)}>{t.nombre}</option>
      ))}
    </select>
  );
}
