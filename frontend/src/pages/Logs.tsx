// La pantalla vive en libra-ui desde su v0.12.0 — nació acá el 2026-08-05 y se
// extrajo al día siguiente, al ir a repetirla en Gestiolibra, MedLibra y
// VentaLibra. Mismo patrón que `Usuarios`.
//
// `basePath` porque este producto monta toda su API bajo `/api`, a diferencia
// de los otros tres.
import { ScrollText } from 'lucide-react'
import { Logs as LogsBase } from 'libra-ui/Logs'

export function Logs() {
  return <LogsBase icono={ScrollText} basePath="/api/logs" />
}
