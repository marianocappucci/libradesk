# Guía de onboarding — Cliente nuevo en LibraDesk

Esta guía es para vos, Mariano. Describe el proceso completo para dar de alta a un cliente
nuevo de LibraDesk —soporte técnico e IT— desde la contratación hasta que está operando.

> **Qué es LibraDesk y qué no.** Es el sistema de **tickets y soporte técnico**: clientes,
> equipos, incidencias, reparaciones, técnicos, sectores, contratos y activos. No es un ERP: no
> lleva contabilidad ni emite comprobantes fiscales por sí mismo. Lo que sí puede hacer, en el
> plan Premium, es **pasarle lo facturable a la instancia de Contalibra del mismo cliente**.

---

## Resumen del proceso

1. Recopilar datos del cliente
2. Levantar la instancia
3. Primer acceso
4. Configurar sectores, técnicos y categorías
5. Cargar clientes y su parque de equipos
6. Aplicar el plan contratado
7. Configurar integraciones (SMTP, puente con Contalibra) según el plan
8. Crear los usuarios
9. Handoff: primer ingreso con el cliente

---

## 1. Datos a recopilar antes de empezar

| Dato | Para qué sirve |
|------|----------------|
| Razón social / nombre comercial | Aparece en la app y en los informes |
| Slug | Nombre corto sin espacios: define `clientes/<slug>/` y el subdominio |
| Plan contratado | Define qué módulos quedan habilitados |
| Sectores | Cómo divide el trabajo: mesa de ayuda, taller, campo |
| Técnicos | Quiénes atienden y de qué sector es cada uno |
| Categorías de incidencia | Cómo clasifica los tickets |
| Clientes finales | A quién le da soporte, con sus datos de contacto |
| Parque de equipos | Qué equipos administra por cliente: si es grande, pedirlo en Excel |
| ¿Alquila equipos? | Módulo `alquileres`, sólo Premium |
| ¿Tiene Contalibra contratado? | Habilita el puente de facturación — ver punto 7 |
| Usuario y contraseña del admin | Para el primer acceso — comunicar por WhatsApp, no por email |

---

## 2. Levantar la instancia

Cada cliente corre en su propio contenedor, aislado en `clientes/<slug>/`, todos compartiendo
la imagen `libradesk:latest`. El puerto base de este producto es **8089** (los asigna el
provisioning mirando los puertos realmente ocupados del host).

### Setup único del servidor

`nuevo_cliente.py` y `panel_admin.py` son wrappers finos sobre `libracore.provisioning`, y el
Python del sistema del VPS no tiene `pip` por política de Debian (PEP 668). Por eso corren con
un venv dedicado en `/root/libradesk/.venv-scripts`, **gitignored — no se versiona y no llega
por `git pull`**. Si hay que recrearlo:

```bash
apt-get install -y python3-venv
python3 -m venv /root/libradesk/.venv-scripts
/root/libradesk/.venv-scripts/bin/pip install \
  "libracore @ git+ssh://git@github-libracore/marianocappucci/libracore.git@<TAG>"
```

Tres cosas que no son obvias:

- **`<TAG>` es el pin que declara el `pyproject.toml` de *este* repo**, no un número común a
  la familia. Cada producto pinea su propia versión de LibraCore, y el venv del host tiene que
  espejar la suya: si queda atrás, el CLI opera con un motor distinto del que corre la
  instancia. Ya frenó un deploy de Contalibra por eso.
- **La URL va por SSH (`git+ssh://git@github-libracore/…`), no por HTTPS.** En este VPS el
  `https://` del `pyproject.toml` falla: la autenticación es por deploy key con alias en
  `~/.ssh/config`. `httpx` y el resto de las dependencias entran solas con LibraCore.
- **Este venv faltó hasta el 2026-08-08**, así que si encontrás documentación vieja que dice
  que en LibraDesk no se puede usar `panel_admin.py`, está desactualizada. Lo que faltaba era
  el venv, no el código: el wrapper está desde el 2026-08-02.

### Alta de un cliente nuevo

En el servidor, desde `/root/libradesk`:

```bash
./.venv-scripts/bin/python3 scripts/nuevo_cliente.py
```

El wizard pide nombre, slug, puerto, dominio, plan y credenciales de admin; crea
`clientes/<slug>/` (compose + `data/` con base, config y adjuntos aislados), levanta el
contenedor y —si hay dominio— crea el proxy y el certificado en Nginx Proxy Manager.

### Gestión del día a día

```bash
./.venv-scripts/bin/python3 scripts/panel_admin.py            # menú interactivo
./.venv-scripts/bin/python3 scripts/panel_admin.py listar     # instancias, puerto y estado
./.venv-scripts/bin/python3 scripts/panel_admin.py info <slug>
./.venv-scripts/bin/python3 scripts/panel_admin.py backup <slug>
./.venv-scripts/bin/python3 scripts/panel_admin.py actualizar [slug...]   # sin args = todas
./.venv-scripts/bin/python3 scripts/panel_admin.py pausar <slug>          # banner, sin cortar acceso
./.venv-scripts/bin/python3 scripts/panel_admin.py suspender <slug>       # corta el acceso
```

Lo mismo por navegador desde el backoffice, en **https://admin.libradesk.com.ar**.

> **La salud se chequea en `/health`, y el chequeo tiene que mirar el CUERPO.** Con la SPA
> horneada **cualquier** ruta devuelve `200` con HTML, así que un monitoreo que sólo mire el
> código HTTP da verde sin haber tocado la app — incluso apuntado a una ruta inventada. Pedir
> `/health` y verificar que el cuerpo sea un JSON con `status: ok`.
>
> Hasta el 2026-08-12 este producto servía su salud **sólo** en `/api/health`, y esa ruta sigue
> respondiendo como alias de transición. Si aparece un compose o una config de monitoreo que la
> use, es de antes: la canónica es `/health`, la misma que los otros cinco productos.

### DNS y dominio

- El wildcard `*.libradesk.com.ar` ya apunta al VPS: **no hay que tocar DNS** por cliente.
- El subdominio es `<slug>.libradesk.com.ar`, y el proxy + SSL los crea el alta.
- Para gestionarlos a mano: `panel_admin.py npm-crear | npm-eliminar | npm-listar`.

> ⚠️ **Al dar de baja una instancia, el proxy no se va solo.** `eliminar` baja el contenedor y
> borra el directorio, nada más. Correr **`npm-eliminar <slug>` antes**, porque después no
> queda `cliente.json` de donde leer el dominio — y ese comando depende de que el campo
> `domain` esté cargado ahí.

---

## 3. Primer acceso

```
URL: https://<slug>.libradesk.com.ar
Usuario: el que definiste en el alta
Contraseña: la que definiste — comunicarla por WhatsApp
```

---

## 4. Sectores, técnicos y categorías

Es lo primero que hay que cargar: una incidencia se asigna a un sector y a un técnico, así que
sin esto el ticket no se puede rutear.

- [ ] **Sectores**: mesa de ayuda, taller, campo — como los divida el cliente
- [ ] **Técnicos**: cada uno con su sector
- [ ] **Equipos de trabajo**, si agrupa técnicos por cuadrilla
- [ ] **Categorías** de incidencia
- [ ] **Servicios** que factura o presupuesta, si corresponde

---

## 5. Clientes y parque de equipos

- [ ] Cargar los **clientes finales** con sus datos de contacto
- [ ] Cargar los **equipos** de cada uno (si el parque es grande, pedir el listado en Excel)
- [ ] Cargar **contratos** vigentes, si los tiene
- [ ] Cargar **depósitos** si maneja stock de repuestos

> **Cargar también algún caso de borde**: un equipo fuera de servicio, una incidencia cerrada,
> una abierta hace días. Las pantallas que ordenan por estado no se pueden revisar con todo
> en verde.

---

## 6. Plan y módulos

| Plan | Precio | Qué habilita |
|------|--------|--------------|
| Básico | $15.000 | Clientes, equipos, incidencias, reparaciones, técnicos y sectores |
| Estándar | $25.000 | Todo lo anterior + **dashboard** y **reportes** |
| Premium | $40.000 | Todo lo anterior + **remitos**, **presupuestos**, **alquileres** y **facturación externa** |

> **El core de tickets no se gatea.** Clientes, equipos, incidencias, técnicos y sectores están
> en todos los planes: un LibraDesk sin incidencias no es un plan más barato, es otra cosa. La
> fuente de verdad es `plans.py` de este repo.

---

## 7. Integraciones

### Correo saliente (SMTP)

Se configura por instancia desde el backoffice (**Configuración → SMTP** en
`admin.libradesk.com.ar`), no dentro de la app. Para Gmail hay que usar una contraseña de
aplicación.

### Puente de facturación con Contalibra (módulo `facturacion_externa`, Premium)

LibraDesk no factura: lo que hace este módulo es **mandarle lo facturable a la instancia de
Contalibra del mismo cliente**. Dos condiciones, y las dos hacen falta:

1. El cliente tiene que tener **Contalibra contratado**, con su propia instancia.
2. Hay que cargar la **configuración de emparejamiento** entre las dos instancias.

> Sin esa configuración el módulo queda **prendido y el puente apagado**, sin error visible: no
> hay a dónde mandar nada. Si el cliente contrató Premium pero no tiene Contalibra, decírselo
> explícitamente en el handoff en vez de dejarle un botón que no hace nada.

---

## 8. Usuarios

Los roles de LibraDesk son dos:

| Rol | Puede hacer |
|-----|-------------|
| `admin` | Todo: configuración, usuarios, sectores, técnicos, facturación |
| `staff` | El día a día: incidencias, equipos, clientes, reparaciones |

- [ ] Crear un `admin` para el responsable del área
- [ ] Crear un `staff` por cada técnico
- [ ] Comunicar las credenciales de forma segura, una por persona — la incidencia queda
      registrada a nombre de quien la trabajó, y con usuarios compartidos eso se pierde

---

## 9. Handoff con el cliente

1. **Ingresar** — URL, usuario, contraseña
2. **Dar de alta un cliente final** y uno de sus equipos
3. **Abrir una incidencia** sobre ese equipo, asignarla a un sector y a un técnico
4. **Registrar el trabajo** y cerrarla
5. **Ver el historial** del equipo
6. **Emitir un presupuesto o un remito** (si es Premium)
7. **Dashboard y reportes** (si es Estándar o Premium)

Al terminar:

- [ ] Cambiar la contraseña del admin por una que defina el cliente
- [ ] Confirmar que puede abrir y cerrar una incidencia sin ayuda
- [ ] Dejar el número de soporte

---

## 10. Post-onboarding (primera semana)

- [ ] Contactarlo a los 2-3 días
- [ ] Revisar que las incidencias se estén asignando y cerrando, no sólo abriendo
- [ ] Verificar que cada técnico entre con **su** usuario
- [ ] Si tiene el puente con Contalibra, confirmar que algo haya llegado del otro lado

---

## Checklist resumen

```
DATOS
[ ] Razón social, slug y plan definidos
[ ] Sectores, técnicos y categorías recopilados
[ ] Parque de equipos conseguido

INSTANCIA
[ ] Levantada y accesible por HTTPS
[ ] Login funciona

CONFIGURACIÓN
[ ] Sectores, técnicos y categorías cargados
[ ] Clientes finales y equipos cargados
[ ] Contratos y depósitos cargados (si aplica)
[ ] Plan aplicado y módulos correctos
[ ] SMTP configurado y probado
[ ] Puente con Contalibra configurado y probado (si aplica)

USUARIOS
[ ] admin creado
[ ] Un staff por técnico, sin usuarios compartidos

CAPACITACIÓN
[ ] Handoff hecho
[ ] El cliente abre y cierra una incidencia solo

POST-ONBOARDING
[ ] Seguimiento a los 3 días
[ ] Incidencias circulando de verdad
```

---

## Contacto de soporte

- WhatsApp: +54 9 11 2775-2983
- Email: soporte@libradesk.com.ar
