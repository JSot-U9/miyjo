# MIYJO — prototipo funcional

Plataforma web (PWA) para que madres y padres de Cusco encuentren, reserven y sigan actividades físicas
verificadas para sus hijos. Stack: **Python 3.11+ · FastAPI · SQLAlchemy/SQLite · Jinja2 · HTML/CSS/JS sin frameworks**.

## Ejecutar (2 minutos)
```bash
./run.sh          # Linux/Mac      (Windows: run.bat)
```
Abre http://localhost:8000 → botón **Demo** (arriba). Desde ahí entras con un clic como:
familia nueva · familia con historial · proveedor · equipo MIYJO (métricas).
**/demo/mensajes** muestra en vivo los mensajes de WhatsApp que se enviarían (códigos, confirmaciones, asistencia).

Probar desde el celular (misma red Wi-Fi): `http://IP-DE-TU-PC:8000` y "Añadir a pantalla de inicio".

## Novedades de esta versión
- **Más opciones para la familia:** catálogo de 18 proveedores y 51 actividades en 19 deportes (nuevos: taekwondo, judo, ballet,
  tenis, tenis de mesa, patinaje, ciclismo, escalada, yoga y multideporte), con horarios para todas las edades de 3 a 17 años.
  Cada padre ve **3 opciones** con la razón de cada una, un botón **«Ver más opciones»** (siguientes 6) y la pantalla
  **Explorar** con filtros por deporte, zona y día. En el cuestionario existe «No sé, muéstrame variedad».
- **Interfaz más clara y con alto contraste:** paleta con contraste mínimo 7:1 en texto (verificado por `tests/test_contrast.py`),
  barra inferior con 5 secciones (Inicio, Sugeridas, Explorar, Reservas, Ayuda), selección con casillas visibles (no solo color),
  indicador de pasos con nombre, «Mejor opción» destacada, botón **A+** para cambiar el tamaño de letra.
- **Si ya tenías datos de la versión anterior**, el catálogo nuevo se carga con: `python -m app.seed --reset`.


## Rediseño de experiencia MIYJO 2.0

Esta versión incorpora una renovación visual y de navegación sin reemplazar FastAPI, SQLAlchemy, Jinja2 ni las rutas existentes:

- Nueva identidad visual: verde profundo, tonos cálidos, superficies suaves y marca MIYJO.
- Landing page orientada a familias de Cusco, con propuesta de valor y explicación del servicio.
- Inicio familiar reorganizado: perfil por hijo, próximas actividades, reservas pendientes y accesos rápidos.
- Recomendaciones presentadas como tarjetas comparables, con compatibilidad, razones, horarios, zona y precio.
- Catálogo con filtros más claros y filas de actividad adaptadas a móvil.
- Renovación de acceso, consentimiento, cuestionario, detalle de actividad y agenda.
- Navegación inferior simplificada: Inicio, Para ti, Explorar, Agenda y Ayuda.
- Ajustes de responsive, accesibilidad, foco visible, contraste y áreas táctiles.
- Avisos explícitos en modo demo para no confundir los datos ficticios con proveedores realmente verificados.

La lógica de reservas, confirmación de pagos, asistencia, recomendador y métricas se conserva. Se ejecutó la suite automatizada: **58 pruebas aprobadas**.

**Importante para el piloto:** el rediseño no convierte los datos de ejemplo en proveedores verificados. Antes de abrir el servicio a familias reales, sustituye el catálogo de demostración, completa la revisión documental de cada proveedor y conecta el canal real de OTP/notificaciones.

## Qué incluye (alcance del prototipo)
| Flujo | Dónde |
|---|---|
| Ingreso por celular + código (sin contraseña) | `/entrar` |
| Consentimiento parental en lenguaje simple | `/consentimiento` |
| Cuestionario de 5 pasos (edad, gustos, horarios, zona, presupuesto) | `/cuestionario/1..5` |
| Catálogo completo con filtros | `/explorar` |
| **3 recomendaciones explicadas** (motor de reglas, `app/recommender.py`) | `/recomendaciones/{hijo}` |
| Clase de prueba / mensualidad, pago por Yape confirmado por el proveedor | `/actividad/{id}`, `/reservas` |
| Panel del proveedor: confirmar pagos, asistencia, nuevas actividades | `/proveedor` |
| **Métricas para patrocinadores** + calculadora de negocio (LTV/CAC) + CSV | `/metricas` (rol equipo) |

Métricas medidas: familias, embudo, familias que repiten, prueba→mensual, minutos de actividad por niño,
proveedores activos, tiempo hasta la primera reserva, asistencia, ingresos por comisión.

## IMPORTANTE para la presentación
1. **Los datos incluidos son FICTICIOS** (proveedores en `app/data/catalogo.json`, 30 familias de demostración).
   El panel lo avisa y tiene el botón **«Solo datos reales»**, que muestra únicamente lo medido en el piloto.
2. **Reemplaza el catálogo** por proveedores reales de Cusco (misma estructura JSON, pon `"demo": false`) y ejecuta:
   ```bash
   python -m app.seed --reset --sin-demo      # catálogo real, sin familias de ejemplo
   MIYJO_DEMO=0 ./run.sh                      # piloto real
   ```
3. Con `MIYJO_DEMO=0` el código de ingreso **ya no se muestra en pantalla**: hay que conectar el envío real
   en `app/services.py → notify()` (WhatsApp Business API, Twilio o SMS). Hoy escribe en la bandeja interna.
4. Presenta los números de la calculadora como **supuestos**, y los del panel como **resultados del piloto**.

## Variables de entorno
`MIYJO_DEMO` (1/0) · `MIYJO_COMISION` (0.12) · `MIYJO_SOPORTE_WHATSAPP` (51987654321) ·
`MIYJO_SECRET` · `DATABASE_URL` (por defecto SQLite en `data/`) · `PORT`.

## Pruebas
```bash
. .venv/bin/activate && python -m pytest -q      # recomendador + flujo completo padre→proveedor→métricas
```

## Seguridad y datos de menores (ya incluido)
Consentimiento explícito con fecha · datos mínimos del niño (nombre y edad, sin apellidos ni fecha de nacimiento) ·
códigos de un solo uso con vencimiento, límite de intentos y de envíos · sesión firmada · cada padre solo accede
a sus hijos y reservas · roles separados (padre / proveedor / equipo) · plantillas con escape automático.
Pendiente antes de producción: HTTPS, protección CSRF por token, política de privacidad legal revisada,
borrado de datos a solicitud, y copias de seguridad.

## Próximos pasos sugeridos
Editar preferencias del niño · pagos con pasarela · reseñas verificadas · lista de espera · traslados ·
app envuelta (Capacitor) cuando haya retención · recomendador con ML cuando existan datos reales.

## Estructura
```
app/main.py          rutas y roles          app/recommender.py   motor explicable (puntaje 0-100)
app/services.py      reglas de negocio      app/metrics.py       métricas para patrocinadores
app/models.py        base de datos          app/seed.py          carga de catálogo y datos demo
app/templates/       pantallas              app/static/          CSS, JS, PWA (manifest, service worker)
tests/               pruebas automáticas    app/data/catalogo.json  proveedores y actividades
```
