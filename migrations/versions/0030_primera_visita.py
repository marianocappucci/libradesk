"""La visita se ancla al acuerdo con el cliente, no al año calendario.

## Qué estaba mal

La revisión `0027` resolvió los períodos de visita con la misma aritmética que
las cuotas, y ahí los bloques están **pegados al año calendario**: un trimestral
cae siempre ene-mar, abr-jun, jul-sep, oct-dic, y la visita se agenda en el
primer mes de cada bloque.

Eso hace imposible expresar el acuerdo real con un cliente. Si con Lagrace se
pactó visitar en **febrero, mayo, agosto y noviembre**, el sistema agendaba
enero, abril, julio y octubre — y no había forma de decirle otra cosa.

🔴 **Y el motivo por el que estaba así no aplicaba acá.** En las cuotas los
períodos **tienen** que ser de calendario: es lo que hace posible el prorrateo
del primer mes, que fue una decisión explícita del humano. Una visita no se
prorratea. La aritmética se copió sin preguntarse si la razón venía con ella.

## Un campo, no dos

El pedido nombró dos cosas —*"desde cuándo arranca y cada cuánto"* y *"un día
propio de la visita"*— y las dos las resuelve **una fecha**:

- Su **mes** ancla la cadencia: un trimestral que arranca el 15-02 devenga
  feb-abr, may-jul, ago-oct, nov-ene.
- Su **día** es el día de la visita, que era el punto del segundo pedido:
  independiente del `dia_vencimiento`, que es cuándo se **cobra**.

Con dos columnas —un ancla y un `dia_visita`— podrían contradecirse (el ancla
dice 15, el día dice 20) y habría que inventar cuál gana. Una sola no puede.

## NULL cae a `fecha_inicio`, y no a los bloques de calendario

Un contrato sin `primera_visita` se ancla a **cuándo empezó el contrato**, que es
el dato que siempre está y el que mejor aproxima el acuerdo. No se conserva el
comportamiento de calendario como segundo camino: sería mantener dos aritméticas
para que una siga haciendo lo que se acaba de decidir que está mal.

⚠️ **Esto cambia qué mes le toca a los contratos que ya tengan frecuencia
cargada.** Al 2026-08-16 son los de `libradesk-dev` y ninguno de producción —las
instancias reales tienen `frecuencia_visita` en NULL, o sea que no generan
visitas—. El cambio es el arreglo, no un efecto colateral.
"""
from alembic import op
import sqlalchemy as sa

revision = "0030_primera_visita"
down_revision = "0029_cargos_mano_de_obra"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "contratos",
        sa.Column("primera_visita", sa.Date(), nullable=True),
    )


def downgrade():
    op.drop_column("contratos", "primera_visita")
