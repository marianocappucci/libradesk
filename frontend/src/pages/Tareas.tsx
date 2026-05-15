import { useEffect, useState } from 'react';
import { getTasks, createTask, updateTask, deleteTask, getAttachments, addAttachment, deleteAttachment } from '../services/api';
import {
  Plus, CheckCircle2, Circle, Trash2, Calendar, Pencil, X, Check,
  Paperclip, ExternalLink, ChevronDown, ChevronRight, CornerDownRight,
} from 'lucide-react';

interface Task {
  id: string; title: string; notes?: string; due?: string; updated?: string;
  status: string; parent?: string;
  subtasks?: Task[];
}
interface Attachment { id: number; google_task_id: string; nombre: string; url: string; created_at: string }
interface EditForm { title: string; notes: string; due: string }

const emptyForm = { title: '', notes: '', due: '' };

function toDueDate(iso?: string): string {
  if (!iso) return '';
  const d = new Date(iso);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

function buildTree(flat: Task[]): Task[] {
  const map: Record<string, Task> = {};
  const roots: Task[] = [];
  flat.forEach(t => { map[t.id] = { ...t, subtasks: [] }; });
  flat.forEach(t => {
    if (t.parent && map[t.parent]) {
      map[t.parent].subtasks!.push(map[t.id]);
    } else if (!t.parent) {
      roots.push(map[t.id]);
    }
  });
  return roots;
}

export default function Tareas() {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [showCompleted, setShowCompleted] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState(emptyForm);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Edición inline
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editForm, setEditForm] = useState<EditForm>(emptyForm);

  // Subtarea nueva
  const [addingSubOf, setAddingSubOf] = useState<string | null>(null);
  const [subForm, setSubForm] = useState(emptyForm);

  // Adjuntos
  const [attachments, setAttachments] = useState<Record<string, Attachment[]>>({});
  const [expandedAttach, setExpandedAttach] = useState<Set<string>>(new Set());
  const [addingAttachOf, setAddingAttachOf] = useState<string | null>(null);
  const [attachForm, setAttachForm] = useState({ nombre: '', url: '' });

  const load = async () => {
    try {
      const r = await getTasks({ showCompleted: showCompleted ? 'true' : 'false', showHidden: 'true' });
      setTasks(r.data);
    } catch { setTasks([]); }
  };

  useEffect(() => { load(); }, [showCompleted]);

  const tree = buildTree(tasks);
  const pending = tree.filter(t => t.status !== 'completed');
  const completed = tree.filter(t => t.status === 'completed');

  // --- Acciones ---
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true); setError(null);
    try {
      await createTask({ title: form.title, notes: form.notes || undefined, due: form.due ? new Date(form.due).toISOString() : undefined });
      setShowForm(false); setForm(emptyForm); load();
    } catch (err: unknown) {
      setError((err as { response?: { data?: { error?: string } } })?.response?.data?.error || 'Error al crear tarea');
    } finally { setSaving(false); }
  };

  const toggleComplete = async (task: Task) => {
    await updateTask(task.id, { ...task, status: task.status === 'completed' ? 'needsAction' : 'completed' });
    load();
  };

  const handleDelete = async (id: string) => {
    if (!confirm('¿Eliminar esta tarea?')) return;
    await deleteTask(id);
    setAttachments(prev => { const n = { ...prev }; delete n[id]; return n; });
    load();
  };

  const startEdit = (task: Task) => {
    setEditingId(task.id);
    setEditForm({ title: task.title, notes: task.notes || '', due: toDueDate(task.due) });
    setAddingSubOf(null); setAddingAttachOf(null);
  };

  const saveEdit = async (task: Task) => {
    await updateTask(task.id, { ...task, title: editForm.title, notes: editForm.notes || undefined, due: editForm.due ? new Date(editForm.due).toISOString() : undefined });
    setEditingId(null); load();
  };

  const handleAddSub = async (parentId: string) => {
    if (!subForm.title.trim()) return;
    await createTask({ title: subForm.title, notes: subForm.notes || undefined, due: subForm.due ? new Date(subForm.due).toISOString() : undefined, parent: parentId });
    setAddingSubOf(null); setSubForm(emptyForm); load();
  };

  // --- Adjuntos ---
  const loadAttachments = async (taskId: string) => {
    if (attachments[taskId]) return;
    try {
      const r = await getAttachments(taskId);
      setAttachments(prev => ({ ...prev, [taskId]: r.data }));
    } catch { setAttachments(prev => ({ ...prev, [taskId]: [] })); }
  };

  const toggleAttach = (taskId: string) => {
    setExpandedAttach(prev => {
      const s = new Set(prev);
      if (s.has(taskId)) { s.delete(taskId); } else { s.add(taskId); loadAttachments(taskId); }
      return s;
    });
  };

  const handleAddAttach = async (taskId: string) => {
    if (!attachForm.nombre.trim() || !attachForm.url.trim()) return;
    await addAttachment(taskId, { nombre: attachForm.nombre, url: attachForm.url });
    setAttachForm({ nombre: '', url: '' }); setAddingAttachOf(null);
    const r = await getAttachments(taskId);
    setAttachments(prev => ({ ...prev, [taskId]: r.data }));
  };

  const handleDeleteAttach = async (taskId: string, attachId: number) => {
    await deleteAttachment(taskId, attachId);
    setAttachments(prev => ({ ...prev, [taskId]: (prev[taskId] || []).filter(a => a.id !== attachId) }));
  };

  // --- TaskRow ---
  const TaskRow = ({ task, depth = 0 }: { task: Task; depth?: number }) => {
    const isEditing = editingId === task.id;
    const isCompleted = task.status === 'completed';
    const attachList = attachments[task.id] || [];
    const attachExpanded = expandedAttach.has(task.id);
    const attachCount = attachList.length;

    return (
      <div className={depth > 0 ? 'ml-5 border-l-2 border-gray-100 pl-3' : ''}>
        {/* Fila principal */}
        {isEditing ? (
          <div className="p-3 rounded-lg bg-blue-50 border border-primary-200 space-y-2 mb-1">
            <input className="input text-sm" autoFocus value={editForm.title} onChange={e => setEditForm(f => ({ ...f, title: e.target.value }))} onKeyDown={e => e.key === 'Escape' && setEditingId(null)} />
            <textarea className="input text-sm" rows={2} placeholder="Notas..." value={editForm.notes} onChange={e => setEditForm(f => ({ ...f, notes: e.target.value }))} />
            <div className="flex items-center gap-2">
              <input type="date" className="input text-sm flex-1" value={editForm.due} onChange={e => setEditForm(f => ({ ...f, due: e.target.value }))} />
              <button onClick={() => saveEdit(task)} className="btn-primary !py-1.5 !px-3"><Check size={14} /></button>
              <button onClick={() => setEditingId(null)} className="btn-secondary !py-1.5 !px-3"><X size={14} /></button>
            </div>
          </div>
        ) : (
          <div
            className={`flex items-start gap-3 px-2 py-2 rounded-lg hover:bg-gray-50 group cursor-pointer ${isCompleted ? 'opacity-60' : ''}`}
            onClick={() => !isCompleted && startEdit(task)}
          >
            <button onClick={e => { e.stopPropagation(); toggleComplete(task); }} className={`mt-0.5 shrink-0 transition-colors ${isCompleted ? 'text-green-500' : 'text-gray-300 hover:text-green-500'}`}>
              {isCompleted ? <CheckCircle2 size={18} /> : <Circle size={18} />}
            </button>
            <div className="flex-1 min-w-0">
              <p className={`text-sm font-medium ${isCompleted ? 'line-through text-gray-400' : 'text-gray-900'}`}>{task.title}</p>
              {task.notes && <p className="text-xs text-gray-500 mt-0.5">{task.notes}</p>}
              <div className="flex gap-3 flex-wrap mt-0.5">
                {task.updated && <p className="text-xs text-gray-400 flex items-center gap-1"><Calendar size={9} />Creada {new Date(task.updated).toLocaleDateString('es-AR', { day: '2-digit', month: '2-digit', year: '2-digit' })}</p>}
                {task.due && <p className="text-xs text-orange-500 font-medium flex items-center gap-1"><Calendar size={9} />Vence {new Date(task.due).toLocaleDateString('es-AR', { day: '2-digit', month: '2-digit', year: '2-digit' })}</p>}
              </div>
            </div>
            <div className="flex gap-0.5 shrink-0 items-center">
              {!isCompleted && (
                <>
                  {/* Adjuntos toggle */}
                  <button
                    onClick={e => { e.stopPropagation(); toggleAttach(task.id); }}
                    className={`p-1.5 rounded text-xs flex items-center gap-0.5 transition-colors ${attachExpanded ? 'text-primary-600' : 'text-gray-400 hover:text-primary-600'}`}
                    title="Adjuntos"
                  >
                    <Paperclip size={13} />
                    {attachCount > 0 && <span className="text-[10px]">{attachCount}</span>}
                  </button>
                  {/* Subtarea */}
                  {depth === 0 && (
                    <button
                      onClick={e => { e.stopPropagation(); setAddingSubOf(task.id); setSubForm(emptyForm); setEditingId(null); }}
                      className="p-1.5 text-gray-400 hover:text-primary-600 rounded opacity-0 group-hover:opacity-100 transition-opacity"
                      title="Nueva subtarea"
                    >
                      <CornerDownRight size={13} />
                    </button>
                  )}
                  <button onClick={e => { e.stopPropagation(); startEdit(task); }} className="p-1.5 text-gray-400 hover:text-primary-600 rounded opacity-0 group-hover:opacity-100 transition-opacity"><Pencil size={13} /></button>
                </>
              )}
              <button onClick={e => { e.stopPropagation(); handleDelete(task.id); }} className="p-1.5 text-gray-400 hover:text-red-500 rounded opacity-0 group-hover:opacity-100 transition-opacity"><Trash2 size={13} /></button>
            </div>
          </div>
        )}

        {/* Panel adjuntos */}
        {attachExpanded && (
          <div className="ml-9 mb-2 space-y-1">
            {attachList.map(a => (
              <div key={a.id} className="flex items-center gap-2 bg-gray-50 rounded px-2 py-1 text-xs group/att">
                <Paperclip size={10} className="text-gray-400 shrink-0" />
                <a href={a.url} target="_blank" rel="noopener noreferrer" className="flex-1 text-primary-600 hover:underline truncate flex items-center gap-1">
                  {a.nombre} <ExternalLink size={9} />
                </a>
                <button onClick={() => handleDeleteAttach(task.id, a.id)} className="p-0.5 text-gray-300 hover:text-red-500 opacity-0 group-hover/att:opacity-100 transition-opacity"><X size={10} /></button>
              </div>
            ))}
            {addingAttachOf === task.id ? (
              <div className="space-y-1 bg-gray-50 rounded p-2">
                <input className="input text-xs" placeholder="Nombre del archivo..." value={attachForm.nombre} onChange={e => setAttachForm(f => ({ ...f, nombre: e.target.value }))} autoFocus />
                <input className="input text-xs" placeholder="URL o enlace de Google Drive..." value={attachForm.url} onChange={e => setAttachForm(f => ({ ...f, url: e.target.value }))} />
                <div className="flex gap-1">
                  <button onClick={() => handleAddAttach(task.id)} disabled={!attachForm.nombre || !attachForm.url} className="btn-primary !py-0.5 !px-2 text-xs disabled:opacity-40"><Check size={11} /></button>
                  <button onClick={() => setAddingAttachOf(null)} className="btn-secondary !py-0.5 !px-2 text-xs"><X size={11} /></button>
                </div>
              </div>
            ) : (
              <button onClick={() => setAddingAttachOf(task.id)} className="text-xs text-gray-400 hover:text-primary-600 flex items-center gap-1 px-2 py-0.5">
                <Plus size={10} /> Agregar adjunto
              </button>
            )}
          </div>
        )}

        {/* Form nueva subtarea */}
        {addingSubOf === task.id && (
          <div className="ml-9 mb-2 p-2 bg-gray-50 rounded-lg border border-gray-200 space-y-1.5">
            <input className="input text-sm" autoFocus placeholder="Título de la subtarea..." value={subForm.title} onChange={e => setSubForm(f => ({ ...f, title: e.target.value }))} onKeyDown={e => { if (e.key === 'Enter') handleAddSub(task.id); if (e.key === 'Escape') setAddingSubOf(null); }} />
            <div className="flex gap-1.5 items-center">
              <input type="date" className="input text-xs flex-1" value={subForm.due} onChange={e => setSubForm(f => ({ ...f, due: e.target.value }))} />
              <button onClick={() => handleAddSub(task.id)} disabled={!subForm.title.trim()} className="btn-primary !py-1 !px-2 text-xs disabled:opacity-40"><Check size={12} /></button>
              <button onClick={() => setAddingSubOf(null)} className="btn-secondary !py-1 !px-2 text-xs"><X size={12} /></button>
            </div>
          </div>
        )}

        {/* Subtareas */}
        {(task.subtasks || []).length > 0 && (
          <div className="mt-0.5 mb-1 space-y-0.5">
            {task.subtasks!.map(sub => (
              <TaskRow key={sub.id} task={sub} depth={depth + 1} />
            ))}
          </div>
        )}
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
                <input className="input" required autoFocus value={form.title} onChange={e => setForm(f => ({ ...f, title: e.target.value }))} />
              </div>
              <div>
                <label className="label">Notas</label>
                <textarea className="input" rows={2} value={form.notes} onChange={e => setForm(f => ({ ...f, notes: e.target.value }))} />
              </div>
              <div>
                <label className="label">Fecha límite</label>
                <input type="date" className="input" value={form.due} onChange={e => setForm(f => ({ ...f, due: e.target.value }))} />
              </div>
              <div className="flex gap-2 justify-end pt-2">
                <button type="button" onClick={() => { setShowForm(false); setError(null); }} className="btn-secondary">Cancelar</button>
                <button type="submit" disabled={saving} className="btn-primary disabled:opacity-60">{saving ? 'Creando...' : 'Crear tarea'}</button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Pendientes */}
      <div className="card mb-4">
        <h2 className="font-semibold text-gray-800 mb-1">
          Pendientes <span className="text-gray-400 font-normal">({pending.length})</span>
        </h2>
        <p className="text-xs text-gray-400 mb-3">Click en una tarea para editarla · <CornerDownRight size={10} className="inline" /> para agregar subtarea · <Paperclip size={10} className="inline" /> para adjuntos</p>
        {pending.length === 0 && <p className="text-sm text-gray-400">Sin tareas pendientes</p>}
        <div className="space-y-0.5">
          {pending.map(t => <TaskRow key={t.id} task={t} />)}
        </div>
      </div>

      {/* Completadas */}
      <div>
        <button onClick={() => setShowCompleted(!showCompleted)} className="text-sm text-gray-400 hover:text-gray-600 mb-3 flex items-center gap-1.5 transition-colors">
          {showCompleted ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
          Completadas ({completed.length})
        </button>
        {showCompleted && (
          <div className="card">
            {completed.length === 0 && <p className="text-sm text-gray-400">Sin tareas completadas</p>}
            <div className="space-y-0.5">
              {completed.map(t => <TaskRow key={t.id} task={t} />)}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
