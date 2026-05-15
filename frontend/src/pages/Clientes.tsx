import { useEffect, useState } from 'react';
import { getClientes, createCliente, updateCliente, deleteCliente } from '../services/api';
import { Plus, Search, Building2, Phone, Mail, MapPin, Pencil, Trash2 } from 'lucide-react';

interface Cliente {
  id: number; nombre: string; empresa?: string; email?: string;
  telefono?: string; ciudad?: string; observaciones?: string;
}

const emptyForm = { nombre: '', empresa: '', email: '', telefono: '', ciudad: '', observaciones: '' };

export default function Clientes() {
  const [clientes, setClientes] = useState<Cliente[]>([]);
  const [search, setSearch] = useState('');
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState(emptyForm);
  const [editing, setEditing] = useState<number | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = async (q?: string) => {
    const r = await getClientes(q);
    setClientes(r.data);
  };

  useEffect(() => { load(); }, []);

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    load(search || undefined);
  };

  const openNew = () => { setForm(emptyForm); setEditing(null); setError(null); setShowForm(true); };
  const openEdit = (c: Cliente) => {
    setForm({ nombre: c.nombre, empresa: c.empresa || '', email: c.email || '', telefono: c.telefono || '', ciudad: c.ciudad || '', observaciones: c.observaciones || '' });
    setEditing(c.id); setShowForm(true);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setError(null);
    try {
      if (editing) await updateCliente(editing, form);
      else await createCliente(form);
      setShowForm(false);
      load();
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { error?: string } } })?.response?.data?.error || 'Error al guardar cliente';
      setError(msg);
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (id: number) => {
    if (!confirm('¿Eliminar este cliente?')) return;
    await deleteCliente(id);
    load();
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Clientes</h1>
        <button onClick={openNew} className="btn-primary">
          <Plus size={16} /> Nuevo cliente
        </button>
      </div>

      <form onSubmit={handleSearch} className="flex gap-2 mb-6">
        <div className="relative flex-1 max-w-sm">
          <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
          <input
            className="input pl-9"
            placeholder="Buscar por nombre, empresa o email..."
            value={search}
            onChange={e => setSearch(e.target.value)}
          />
        </div>
        <button type="submit" className="btn-secondary">Buscar</button>
        {search && <button type="button" onClick={() => { setSearch(''); load(); }} className="btn-secondary">Limpiar</button>}
      </form>

      {/* Modal */}
      {showForm && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
          <div className="bg-white rounded-xl shadow-xl w-full max-w-lg p-6">
            <h2 className="text-lg font-semibold mb-4">{editing ? 'Editar cliente' : 'Nuevo cliente'}</h2>
            {error && (
              <div className="bg-red-50 text-red-700 text-sm rounded-lg p-3 mb-2">{error}</div>
            )}
            <form onSubmit={handleSubmit} className="space-y-3">
              <div>
                <label className="label">Nombre *</label>
                <input className="input" required value={form.nombre} onChange={e => setForm(f => ({ ...f, nombre: e.target.value }))} />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="label">Empresa</label>
                  <input className="input" value={form.empresa} onChange={e => setForm(f => ({ ...f, empresa: e.target.value }))} />
                </div>
                <div>
                  <label className="label">Ciudad</label>
                  <input className="input" value={form.ciudad} onChange={e => setForm(f => ({ ...f, ciudad: e.target.value }))} />
                </div>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="label">Email</label>
                  <input type="email" className="input" value={form.email} onChange={e => setForm(f => ({ ...f, email: e.target.value }))} />
                </div>
                <div>
                  <label className="label">Teléfono</label>
                  <input className="input" value={form.telefono} onChange={e => setForm(f => ({ ...f, telefono: e.target.value }))} />
                </div>
              </div>
              <div>
                <label className="label">Observaciones</label>
                <textarea className="input" rows={2} value={form.observaciones} onChange={e => setForm(f => ({ ...f, observaciones: e.target.value }))} />
              </div>
              <div className="flex gap-2 justify-end pt-2">
                <button type="button" onClick={() => { setShowForm(false); setError(null); }} className="btn-secondary">Cancelar</button>
                <button type="submit" disabled={saving} className="btn-primary disabled:opacity-60">
                  {saving ? 'Guardando...' : 'Guardar'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
        {clientes.map(c => (
          <div key={c.id} className="card hover:shadow-md transition-shadow">
            <div className="flex items-start justify-between mb-3">
              <div>
                <h3 className="font-semibold text-gray-900">{c.nombre}</h3>
                {c.empresa && <p className="text-sm text-gray-500 flex items-center gap-1"><Building2 size={12} />{c.empresa}</p>}
              </div>
              <div className="flex gap-1">
                <button onClick={() => openEdit(c)} className="p-1.5 text-gray-400 hover:text-primary-600 rounded"><Pencil size={14} /></button>
                <button onClick={() => handleDelete(c.id)} className="p-1.5 text-gray-400 hover:text-red-600 rounded"><Trash2 size={14} /></button>
              </div>
            </div>
            <div className="space-y-1 text-sm text-gray-500">
              {c.email && <p className="flex items-center gap-1.5"><Mail size={12} />{c.email}</p>}
              {c.telefono && <p className="flex items-center gap-1.5"><Phone size={12} />{c.telefono}</p>}
              {c.ciudad && <p className="flex items-center gap-1.5"><MapPin size={12} />{c.ciudad}</p>}
            </div>
          </div>
        ))}
        {clientes.length === 0 && (
          <div className="col-span-full text-center py-12 text-gray-400">
            No hay clientes. ¡Creá el primero!
          </div>
        )}
      </div>
    </div>
  );
}
