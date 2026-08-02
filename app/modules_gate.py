"""Gating por módulo habilitado según el plan — shim sobre
`libracore.modules_gate`, igual que en Gestiolibra, MedLibra y VentaLibra.

Agregado el 2026-08-02 al normalizar los seis productos: LibraDesk era el único
sin módulos ni planes."""
from libracore.modules_gate import get_module_repository, require_module

__all__ = ["get_module_repository", "require_module"]
