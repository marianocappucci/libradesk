"""La aritmética de períodos de LibraDesk es la del motor (`libracore.periodos`, ADR-086 de libracore).

Subió al motor el 2026-10-26. Acá se fija que los envoltorios que reciben un `Contrato` siguen diciendo lo mismo, y el
caso que el motor corrigió al subirla: con un arranque a fin de mes, el período anclado de las visitas dejaba al ancla
afuera (arranque 31-01: el 28-02 daba el período del 31-01 al 27-02).
"""
from datetime import date
from types import SimpleNamespace

import pytest
from libracore import periodos

from app.services import cuotas, visitas


def test_las_cuotas_usan_el_periodo_del_motor():
    assert cuotas.Periodo is periodos.Periodo
    c = SimpleNamespace(periodicidad="trimestral", dia_vencimiento=31)
    p = cuotas.periodo_de(c, date(2026, 2, 10))
    assert (p.desde, p.hasta) == (date(2026, 1, 1), date(2026, 3, 31))
    assert cuotas.vencimiento_de(SimpleNamespace(dia_vencimiento=31), periodos.Periodo(date(2026, 2, 1), date(2026, 2, 28))) \
        == date(2026, 2, 28)
    assert cuotas.vencimiento_de(SimpleNamespace(dia_vencimiento=None), p) is None


@pytest.mark.parametrize("ancla, desde, hasta", [
    (date(2026, 2, 27), date(2026, 1, 31), date(2026, 2, 27)),
    (date(2026, 2, 28), date(2026, 2, 28), date(2026, 3, 30)),     # antes: 31-01 al 27-02, sin el 28 adentro
    (date(2026, 4, 30), date(2026, 4, 30), date(2026, 5, 30)),     # antes: 31-03 al 29-04, sin el 30 adentro
])
def test_la_visita_anclada_a_fin_de_mes_contiene_al_ancla(ancla, desde, hasta):
    p = visitas.periodo_anclado("mensual", ancla=ancla, arranque=date(2026, 1, 31))
    assert (p.desde, p.hasta) == (desde, hasta)
