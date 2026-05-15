export default function Login({ error }: { error?: string }) {
  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50">
      <div className="card max-w-sm w-full text-center">
        <div className="w-16 h-16 bg-primary-100 rounded-2xl flex items-center justify-center mx-auto mb-4">
          <svg className="w-8 h-8 text-primary-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17H4a2 2 0 01-2-2V5a2 2 0 012-2h16a2 2 0 012 2v10a2 2 0 01-2 2h-1" />
          </svg>
        </div>
        <h1 className="text-2xl font-bold text-gray-900 mb-1">IT Support Hub</h1>
        <p className="text-gray-500 text-sm mb-6">Sistema de soporte técnico</p>

        {error === 'unauthorized' && (
          <p className="text-red-600 text-sm mb-4 bg-red-50 rounded-lg p-3">
            Tu cuenta no tiene acceso a esta aplicación.
          </p>
        )}
        {error === 'auth_failed' && (
          <p className="text-red-600 text-sm mb-4 bg-red-50 rounded-lg p-3">
            Error al autenticar. Intentá de nuevo.
          </p>
        )}

        <a
          href="/api/auth/google"
          className="btn-primary w-full justify-center text-base py-3"
        >
          <svg className="w-5 h-5" viewBox="0 0 24 24">
            <path fill="currentColor" d="M12.545,10.239v3.821h5.445c-0.712,2.315-2.647,3.972-5.445,3.972c-3.332,0-6.033-2.701-6.033-6.032s2.701-6.032,6.033-6.032c1.498,0,2.866,0.549,3.921,1.453l2.814-2.814C17.503,2.988,15.139,2,12.545,2C7.021,2,2.543,6.477,2.543,12s4.478,10,10.002,10c8.396,0,10.249-7.85,9.426-11.748L12.545,10.239z"/>
          </svg>
          Iniciar sesión con Google
        </a>
      </div>
    </div>
  );
}
