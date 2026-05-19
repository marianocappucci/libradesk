import { useEffect, useState } from 'react';
import { getTecnicos, createTecnico, updateTecnico, deleteTecnico } from '../services/api';
import { Plus, Pencil, Trash2, Check, X } from 'lucide-react';

interface Tecnico { id: number; nombre: string; activo: boolean; created_at: string; }

export default function Tecnicos() {
  const [tecnicos, setTecnicos] = useState<Tecnico[]>([]);
  const [newNombre, setNewNombre] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editNombre, setEditNombre] = useState('');

  const load = () => getTecnicos().then(r => setTecnicos(r.data));
  useEffect(() => { load(); }, []);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newNombre.trim()) return;
    setSaving(true);
    setError(null);
    try {
      await createTecnico({ nombre: newNombre.trim() });
      setNewNombre('');
      load();
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { error?: string } } })?.response?.data?.error || 'Error al crear técnico';
      setError(msg);
    } finally {
      setSaving(false);
    }
  };

  const startEdit = (t: Tecnico) => {
    setEditingId(t.id);
    setEditNombre(t.nombre);
    setError(null);
  };

  const handleUpdate = async (t: Tecnico) => {
    if (!editNombre.trim()) return;
    try {
      await updateTecnico(t.id, { nombre: editNombre.trim() });
      setEditingId(null);
      load();
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { error?: string } } })?.response?.data?.error || 'Error al actualizar';
      setError(msg);
    }
  };

  const handleToggle = async (t: Tecnico) => {
    await updateTecnico(t.id, { activo: !t.activo });
    load();
  };

  const handleDelete = async (t: Tecnico) => {
    if (!confirm(`¿Dar de baja a ${t.nombre}? Las incidencias asignadas no se modifican.`)) return;
    await deleteTecnico(t.id);
    load();
  };

  return (
    <div className="max-w-xl">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Técnicos</h1>
        <p className="text-sm text-gray-400 mt-0.5">Gestión del equipo técnico</p>
      </div>

      {/* Nuevo técnico */}
      <form onSubmit={handleCreate} className="flex gap-2 mb-6">
        <input
          className="input flex-1"
          placeholder="Nombre del técnico..."
          value={newNombre}
          onChange={e => setNewNombre(e.target.value)}
        />
        <button type="submit" disabled={saving || !newNombre.trim()} className="btn-primary disabled:opacity-50">
          <Plus size={16} /> Agregar
        </button>
      </form>
      {error && <p className="text-sm text-red-600 mb-3 -mt-4">{error}</p>}

      {/* Lista */}
      <div className="card divide-y divide-gray-100 !p-0 overflow-hidden">
        {tecnicos.length === 0 && (
          <p className="text-sm text-gray-400 px-4 py-6 text-center">Sin técnicos registrados</p>
        )}
        {tecnicos.map(t => (
          <div key={t.id} className={`flex items-center gap-3 px-4 py-3 ${!t.activo ? 'opacity-50' : ''}`}>
            <div className="flex-1 min-w-0">
              {editingId === t.id ? (
                <input
                  className="input text-sm py-1"
                  value={editNombre}
                  onChange={e => setEditNombre(e.target.value)}
                  autoFocus
                  onKeyDown={e => { if (e.key === 'Enter') handleUpdate(t); if (e.key === 'Escape') setEditingId(null); }}
                />
              ) : (
                <div className="flex items-center gap-2">
                  <span className="font-medium text-gray-800">{t.nombre}</span>
                  {!t.activo && <span className="badge bg-gray-100 text-gray-400">Inactivo</span>}
                </div>
              )}
            </div>
            <div className="flex items-center gap-1 shrink-0">
              {editingId === t.id ? (
                <>
                  <button onClick={() => setEditingId(null)} className="p-1.5 text-gray-400 hover:text-gray-600 rounded"><X size={14} /></button>
                  <button onClick={() => handleUpdate(t)} className="p-1.5 text-green-600 hover:text-green-700 rounded"><Check size={14} /></button>
                </>
              ) : (
                <>
                  <button onClick={() => startEdit(t)} className="p-1.5 text-gray-400 hover:text-primary-600 rounded" title="Editar nombre"><Pencil size={14} /></button>
                  <button onClick={() => handleToggle(t)} className="p-1.5 text-gray-400 hover:text-yellow-600 rounded text-xs font-medium" title={t.activo ? 'Desactivar' : 'Activar'}>
                    {t.activo ? '↓' : '↑'}
                  </button>
                  <button onClick={() => handleDelete(t)} className="p-1.5 text-gray-400 hover:text-red-500 rounded" title="Dar de baja"><Trash2 size={14} /></button>
                </>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
