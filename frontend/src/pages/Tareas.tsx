import { useEffect, useState } from 'react';
import { getTasks, createTask, updateTask, deleteTask } from '../services/api';
import { Plus, CheckCircle2, Circle, Trash2, Calendar, Pencil, X, Check } from 'lucide-react';

interface Task { id: string; title: string; notes?: string; due?: string; status: string }
interface EditForm { title: string; notes: string; due: string }

const emptyForm = { title: '', notes: '', due: '' };

function toDueDate(iso?: string): string {
  if (!iso) return '';
  const d = new Date(iso);
  const pad = (n: number) => n.toString().padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

export default function Tareas() {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [showCompleted, setShowCompleted] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState(emptyForm);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editForm, setEditForm] = useState<EditForm>(emptyForm);

  const load = async () => {
    try {
      const r = await getTasks({ showCompleted });
      setTasks(r.data);
    } catch {
      setTasks([]);
    }
  };

  useEffect(() => { load(); }, [showCompleted]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setError(null);
    try {
      await createTask({
        title: form.title,
        notes: form.notes || undefined,
        due: form.due ? new Date(form.due).toISOString() : undefined,
      });
      setShowForm(false);
      setForm(emptyForm);
      load();
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { error?: string } } })?.response?.data?.error || 'Error al crear tarea';
      setError(msg);
    } finally {
      setSaving(false);
    }
  };

  const toggleComplete = async (task: Task) => {
    const newStatus = task.status === 'completed' ? 'needsAction' : 'completed';
    await updateTask(task.id, { ...task, status: newStatus });
    load();
  };

  const handleDelete = async (id: string) => {
    await deleteTask(id);
    load();
  };

  const startEdit = (task: Task) => {
    setEditingId(task.id);
    setEditForm({
      title: task.title,
      notes: task.notes || '',
      due: toDueDate(task.due),
    });
  };

  const cancelEdit = () => {
    setEditingId(null);
    setEditForm(emptyForm);
  };

  const saveEdit = async (task: Task) => {
    await updateTask(task.id, {
      ...task,
      title: editForm.title,
      notes: editForm.notes || undefined,
      due: editForm.due ? new Date(editForm.due).toISOString() : undefined,
    });
    setEditingId(null);
    load();
  };

  const pending = tasks.filter(t => t.status !== 'completed');
  const completed = tasks.filter(t => t.status === 'completed');

  const TaskRow = ({ task }: { task: Task }) => {
    const isEditing = editingId === task.id;

    if (isEditing) {
      return (
        <div className="p-3 rounded-lg bg-blue-50 border border-primary-200 space-y-2">
          <input
            className="input text-sm"
            autoFocus
            value={editForm.title}
            onChange={e => setEditForm(f => ({ ...f, title: e.target.value }))}
            onKeyDown={e => e.key === 'Escape' && cancelEdit()}
          />
          <textarea
            className="input text-sm"
            rows={2}
            placeholder="Notas..."
            value={editForm.notes}
            onChange={e => setEditForm(f => ({ ...f, notes: e.target.value }))}
          />
          <div className="flex items-center gap-2">
            <input
              type="date"
              className="input text-sm flex-1"
              value={editForm.due}
              onChange={e => setEditForm(f => ({ ...f, due: e.target.value }))}
            />
            <button onClick={() => saveEdit(task)} className="btn-primary py-1.5 px-3">
              <Check size={14} />
            </button>
            <button onClick={cancelEdit} className="btn-secondary py-1.5 px-3">
              <X size={14} />
            </button>
          </div>
        </div>
      );
    }

    return (
      <div
        className="flex items-start gap-3 p-2 rounded-lg hover:bg-gray-50 group cursor-pointer"
        onClick={() => startEdit(task)}
      >
        <button
          onClick={e => { e.stopPropagation(); toggleComplete(task); }}
          className="mt-0.5 text-gray-300 hover:text-green-500 shrink-0 transition-colors"
        >
          <Circle size={18} />
        </button>
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium text-gray-900">{task.title}</p>
          {task.notes && <p className="text-xs text-gray-500 mt-0.5">{task.notes}</p>}
          {task.due && (
            <p className="text-xs text-gray-400 flex items-center gap-1 mt-0.5">
              <Calendar size={10} />
              {new Date(task.due).toLocaleDateString('es-AR')}
            </p>
          )}
        </div>
        <div className="flex gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity shrink-0">
          <button
            onClick={e => { e.stopPropagation(); handleDelete(task.id); }}
            className="p-1.5 text-gray-400 hover:text-red-500 rounded"
          >
            <Trash2 size={13} />
          </button>
        </div>
      </div>
    );
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Tareas</h1>
          <p className="text-sm text-gray-400 mt-0.5">Lista "IT Soporte" en Google Tasks</p>
        </div>
        <button onClick={() => { setShowForm(true); setError(null); }} className="btn-primary">
          <Plus size={16} /> Nueva tarea
        </button>
      </div>

      {/* Modal nueva tarea */}
      {showForm && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
          <div className="bg-white rounded-xl shadow-xl w-full max-w-md p-6">
            <h2 className="text-lg font-semibold mb-4">Nueva tarea · IT Soporte</h2>
            {error && <div className="bg-red-50 text-red-700 text-sm rounded-lg p-3 mb-3">{error}</div>}
            <form onSubmit={handleSubmit} className="space-y-3">
              <div>
                <label className="label">Título *</label>
                <input
                  className="input" required autoFocus
                  value={form.title}
                  onChange={e => setForm(f => ({ ...f, title: e.target.value }))}
                />
              </div>
              <div>
                <label className="label">Notas</label>
                <textarea
                  className="input" rows={2}
                  value={form.notes}
                  onChange={e => setForm(f => ({ ...f, notes: e.target.value }))}
                />
              </div>
              <div>
                <label className="label">Fecha límite</label>
                <input
                  type="date" className="input"
                  value={form.due}
                  onChange={e => setForm(f => ({ ...f, due: e.target.value }))}
                />
              </div>
              <div className="flex gap-2 justify-end pt-2">
                <button type="button" onClick={() => { setShowForm(false); setError(null); }} className="btn-secondary">
                  Cancelar
                </button>
                <button type="submit" disabled={saving} className="btn-primary disabled:opacity-60">
                  {saving ? 'Creando...' : 'Crear tarea'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Pendientes */}
      <div className="card mb-4">
        <h2 className="font-semibold text-gray-800 mb-3">
          Pendientes <span className="text-gray-400 font-normal">({pending.length})</span>
        </h2>
        {pending.length === 0 && <p className="text-sm text-gray-400">Sin tareas pendientes</p>}
        <div className="space-y-1">
          {pending.map(t => <TaskRow key={t.id} task={t} />)}
        </div>
      </div>

      {/* Completadas */}
      <div>
        <button
          onClick={() => setShowCompleted(!showCompleted)}
          className="text-sm text-gray-400 hover:text-gray-600 mb-3 flex items-center gap-1.5 transition-colors"
        >
          <span>{showCompleted ? '▼' : '▶'}</span>
          Completadas ({completed.length})
        </button>
        {showCompleted && (
          <div className="card">
            {completed.length === 0 && <p className="text-sm text-gray-400">Sin tareas completadas</p>}
            <div className="space-y-1">
              {completed.map(t => (
                <div key={t.id} className="flex items-start gap-3 p-2 rounded-lg group">
                  <button onClick={() => toggleComplete(t)} className="mt-0.5 text-green-500 shrink-0">
                    <CheckCircle2 size={18} />
                  </button>
                  <p className="flex-1 text-sm text-gray-400 line-through">{t.title}</p>
                  <button
                    onClick={() => handleDelete(t.id)}
                    className="p-1 text-gray-300 hover:text-red-500 opacity-0 group-hover:opacity-100"
                  >
                    <Trash2 size={13} />
                  </button>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
