from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timedelta

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ========== DATOS EN MEMORIA ==========
servicios = [
    {"id": 1, "nombre": "Consulta General"},
    {"id": 2, "nombre": "Seguimiento"},
    {"id": 3, "nombre": "Urgencia"}
]

# Horarios por día (0=Lunes, 6=Domingo)
horarios = [
    {"dia": 0, "activo": True, "inicio": "09:00", "fin": "18:00"},
    {"dia": 1, "activo": True, "inicio": "09:00", "fin": "18:00"},
    {"dia": 2, "activo": True, "inicio": "09:00", "fin": "18:00"},
    {"dia": 3, "activo": True, "inicio": "09:00", "fin": "18:00"},
    {"dia": 4, "activo": True, "inicio": "09:00", "fin": "18:00"},
    {"dia": 5, "activo": True, "inicio": "09:00", "fin": "13:00"},
    {"dia": 6, "activo": False, "inicio": "00:00", "fin": "00:00"}
]

# Bloqueos (días específicos o rangos)
bloqueos = []

citas = []
contador_servicios = 4
contador_citas = 1
contador_bloqueos = 1

# ========== MODELOS ==========
class ServicioInput(BaseModel):
    nombre: str

class HorarioInput(BaseModel):
    dia: int
    activo: bool
    inicio: str
    fin: str

class BloqueoInput(BaseModel):
    fecha_inicio: str
    fecha_fin: str
    todo_dia: bool
    inicio: Optional[str] = None
    fin: Optional[str] = None
    motivo: str = ""

class CitaInput(BaseModel):
    fecha: str
    hora: str
    nombre: str
    telefono: str = ""
    servicio: str
    motivo: str = ""

# ========== FUNCIÓN: GENERAR HORAS EN PUNTO Y MEDIA ==========
def generar_horas(inicio: str, fin: str):
    """Genera horas en punto (:00) y media (:30) entre inicio y fin"""
    horas = []
    actual = datetime.strptime(inicio, "%H:%M")
    final = datetime.strptime(fin, "%H:%M")
    
    while actual <= final:
        hora_str = actual.strftime("%H:%M")
        horas.append(hora_str)
        # Avanzar 30 minutos
        actual += timedelta(minutes=30)
    
    return horas

# ========== FUNCIÓN: VERIFICAR SI FECHA ESTÁ EN RANGO DE BLOQUEO ==========
def fecha_en_bloqueo(fecha: str):
    """Devuelve el bloqueo que afecta a esta fecha, o None"""
    fecha_obj = datetime.strptime(fecha, "%Y-%m-%d")
    for b in bloqueos:
        inicio = datetime.strptime(b["fecha_inicio"], "%Y-%m-%d")
        fin = datetime.strptime(b["fecha_fin"], "%Y-%m-%d")
        if inicio <= fecha_obj <= fin:
            return b
    return None

# ========== FUNCIÓN PRINCIPAL: OBTENER HORARIOS DISPONIBLES ==========
def obtener_horarios_disponibles(fecha: str):
    """Devuelve lista de horarios disponibles para una fecha (solo :00 y :30)"""
    fecha_obj = datetime.strptime(fecha, "%Y-%m-%d")
    dia_semana = fecha_obj.weekday()
    
    # 1. Verificar si la fecha está dentro de un BLOQUEO
    bloqueo = fecha_en_bloqueo(fecha)
    
    # 2. Si hay bloqueo de DÍA COMPLETO -> no hay horarios
    if bloqueo and bloqueo["todo_dia"]:
        return []
    
    # 3. Obtener horario base
    if bloqueo and not bloqueo["todo_dia"]:
        # Bloqueo parcial: usar el horario restringido del bloqueo
        inicio = bloqueo["inicio"]
        fin = bloqueo["fin"]
    else:
        # Usar horario normal del día
        horario = horarios[dia_semana]
        if not horario["activo"]:
            return []
        inicio = horario["inicio"]
        fin = horario["fin"]
    
    # 4. Obtener todas las horas posibles (en punto y media)
    todas_las_horas = generar_horas(inicio, fin)
    
    # 5. Obtener horas ya ocupadas por citas
    ocupadas = [c["hora"] for c in citas if c["fecha"] == fecha]
    
    # 6. Filtrar horas disponibles
    disponibles = [h for h in todas_las_horas if h not in ocupadas]
    
    return disponibles

# ========== ENDPOINTS ==========
@app.get("/")
def root():
    return HTMLResponse(HTML_CONTENT)

# Servicios
@app.get("/api/servicios")
def get_servicios():
    return servicios

@app.post("/api/servicios")
def add_servicio(data: ServicioInput):
    global contador_servicios
    for s in servicios:
        if s["nombre"].lower() == data.nombre.lower():
            raise HTTPException(status_code=400, detail="Servicio ya existe")
    nuevo = {"id": contador_servicios, "nombre": data.nombre}
    servicios.append(nuevo)
    contador_servicios += 1
    return {"success": True}

@app.delete("/api/servicios/{id}")
def delete_servicio(id: int):
    global servicios
    servicios = [s for s in servicios if s["id"] != id]
    return {"success": True}

# Horarios
@app.get("/api/horarios")
def get_horarios():
    return horarios

@app.post("/api/horarios")
def update_horarios(data: List[HorarioInput]):
    global horarios
    for h in data:
        for i, existing in enumerate(horarios):
            if existing["dia"] == h.dia:
                horarios[i] = {
                    "dia": h.dia,
                    "activo": h.activo,
                    "inicio": h.inicio,
                    "fin": h.fin
                }
    return {"success": True}

# Bloqueos (ahora con rango de fechas)
@app.get("/api/bloqueos")
def get_bloqueos():
    return bloqueos

@app.post("/api/bloqueos")
def add_bloqueo(data: BloqueoInput):
    global contador_bloqueos
    
    # Validar fechas
    fecha_inicio_obj = datetime.strptime(data.fecha_inicio, "%Y-%m-%d")
    fecha_fin_obj = datetime.strptime(data.fecha_fin, "%Y-%m-%d")
    hoy = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    
    if fecha_inicio_obj < hoy:
        raise HTTPException(status_code=400, detail="No se puede bloquear fechas pasadas")
    
    if fecha_inicio_obj > fecha_fin_obj:
        raise HTTPException(status_code=400, detail="Fecha inicio no puede ser mayor que fecha fin")
    
    nuevo = {
        "id": contador_bloqueos,
        "fecha_inicio": data.fecha_inicio,
        "fecha_fin": data.fecha_fin,
        "todo_dia": data.todo_dia,
        "inicio": data.inicio,
        "fin": data.fin,
        "motivo": data.motivo
    }
    bloqueos.append(nuevo)
    contador_bloqueos += 1
    return {"success": True}

@app.delete("/api/bloqueos/{id}")
def delete_bloqueo(id: int):
    global bloqueos
    bloqueos = [b for b in bloqueos if b["id"] != id]
    return {"success": True}

# Citas
@app.get("/api/citas")
def get_citas(fecha: Optional[str] = None):
    if fecha:
        resultado = [c for c in citas if c["fecha"] == fecha]
        resultado.sort(key=lambda x: x["hora"])
        return resultado
    todas = sorted(citas, key=lambda x: (x["fecha"], x["hora"]))
    return todas

@app.post("/api/citas")
def add_cita(data: CitaInput):
    global contador_citas
    
    # Validar formato de hora (:00 o :30)
    minutos = int(data.hora.split(":")[1])
    if minutos not in [0, 30]:
        raise HTTPException(status_code=400, detail="Las horas deben ser :00 o :30 (ej: 09:00, 09:30)")
    
    # Validar que el horario esté disponible
    disponibles = obtener_horarios_disponibles(data.fecha)
    if data.hora not in disponibles:
        raise HTTPException(status_code=400, detail="Horario no disponible")
    
    nueva = {
        "id": contador_citas,
        "fecha": data.fecha,
        "hora": data.hora,
        "nombre": data.nombre,
        "telefono": data.telefono,
        "servicio": data.servicio,
        "motivo": data.motivo
    }
    citas.append(nueva)
    contador_citas += 1
    return {"success": True, "id": nueva["id"]}

@app.delete("/api/citas/{id}")
def delete_cita(id: int):
    global citas
    citas = [c for c in citas if c["id"] != id]
    return {"success": True}

@app.get("/api/horarios-disponibles/{fecha}")
def get_horarios_disponibles(fecha: str):
    return {"horarios": obtener_horarios_disponibles(fecha)}

@app.get("/api/resumen")
def get_resumen():
    hoy = datetime.now().strftime("%Y-%m-%d")
    citas_hoy = [c for c in citas if c["fecha"] == hoy]
    return {"citas_hoy": len(citas_hoy), "total_citas": len(citas)}

# ========== FRONTEND COMPLETO CORREGIDO ==========
HTML_CONTENT = '''
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AutoAgenda</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: 'Segoe UI', Arial, sans-serif; background: #f0f2f5; padding: 20px; }
        .container { max-width: 750px; margin: 0 auto; }
        h1 { color: #2E7D32; text-align: center; }
        .sub { text-align: center; color: #666; margin-bottom: 20px; }
        
        .tabs { display: flex; gap: 5px; margin-bottom: 20px; flex-wrap: wrap; }
        .tab { flex: 1; padding: 10px; background: #ddd; text-align: center; cursor: pointer; border-radius: 5px; font-weight: bold; min-width: 80px; }
        .tab.active { background: #2E7D32; color: white; }
        
        .tab-content { display: none; }
        .tab-content.active { display: block; }
        
        .card { background: white; border-radius: 10px; padding: 20px; margin-bottom: 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        .card h2 { color: #2E7D32; margin-bottom: 15px; font-size: 18px; border-left: 4px solid #A8E6CF; padding-left: 10px; }
        
        input, select, textarea { width: 100%; padding: 10px; margin-bottom: 10px; border: 1px solid #ddd; border-radius: 5px; }
        button { width: 100%; padding: 10px; background: #2E7D32; color: white; border: none; border-radius: 5px; cursor: pointer; font-size: 16px; }
        button:hover { opacity: 0.9; }
        button.danger { background: #C62828; width: auto; padding: 5px 10px; }
        button.small { width: auto; padding: 5px 10px; }
        
        .servicio-item, .bloqueo-item { display: flex; justify-content: space-between; align-items: center; padding: 10px; background: #f9f9f9; margin-bottom: 5px; border-radius: 5px; }
        .horario-row { display: flex; gap: 10px; align-items: center; margin-bottom: 10px; flex-wrap: wrap; }
        .horario-row label { display: flex; align-items: center; gap: 5px; min-width: 80px; }
        
        table { width: 100%; border-collapse: collapse; }
        th, td { padding: 10px; text-align: left; border-bottom: 1px solid #ddd; }
        th { background: #A8E6CF; color: #2E7D32; }
        
        .numero-grande { font-size: 48px; color: #2E7D32; font-weight: bold; text-align: center; }
        .text-center { text-align: center; }
        
        .mensaje { background: #A8E6CF; color: #2E7D32; padding: 10px; border-radius: 5px; margin-bottom: 15px; text-align: center; }
        .error { background: #ffebee; color: #C62828; }
        
        .horario-sugerido { background: #e8f5e9; padding: 8px 12px; margin: 3px; border-radius: 5px; cursor: pointer; display: inline-block; min-width: 65px; text-align: center; }
        .horario-sugerido:hover { background: #A8E6CF; }
        .horarios-grid { display: flex; flex-wrap: wrap; gap: 5px; margin-bottom: 10px; }
        
        .checkbox-label { display: flex; align-items: center; gap: 5px; cursor: pointer; }
        
        .info-horario { font-size: 12px; color: #666; margin-bottom: 10px; padding: 5px; background: #f5f5f5; border-radius: 5px; }
        
        .rango-fechas { display: flex; gap: 10px; }
        .rango-fechas input { flex: 1; }
    </style>
</head>
<body>
    <div class="container">
        <h1>📋 AutoAgenda</h1>
        <div class="sub">"Configura una vez. Agenda siempre"</div>
        
        <div class="tabs">
            <div class="tab active" onclick="mostrarTab('servicios')">📝 Servicios</div>
            <div class="tab" onclick="mostrarTab('horarios')">⏰ Horarios</div>
            <div class="tab" onclick="mostrarTab('bloqueos')">🚫 Bloqueos</div>
            <div class="tab" onclick="mostrarTab('agendar')">➕ Agendar</div>
            <div class="tab" onclick="mostrarTab('citas')">📅 Citas</div>
            <div class="tab" onclick="mostrarTab('resumen')">📊 Resumen</div>
        </div>
        
        <div id="mensaje"></div>
        
        <!-- SERVICIOS -->
        <div id="tab-servicios" class="tab-content active">
            <div class="card">
                <h2>➕ Agregar Servicio</h2>
                <input type="text" id="nuevoServicio" placeholder="Ej: Masajes, Consulta, Terapia...">
                <button onclick="agregarServicio()">Agregar Servicio</button>
            </div>
            <div class="card">
                <h2>📋 Mis Servicios</h2>
                <div id="listaServicios"></div>
            </div>
        </div>
        
        <!-- HORARIOS -->
        <div id="tab-horarios" class="tab-content">
            <div class="card">
                <h2>⏰ Configurar Horarios Laborales</h2>
                <div id="listaHorarios"></div>
                <button onclick="guardarHorarios()">💾 Guardar Horarios</button>
            </div>
        </div>
        
        <!-- BLOQUEOS (con rango de fechas) -->
        <div id="tab-bloqueos" class="tab-content">
            <div class="card">
                <h2>🚫 Bloquear Rango de Fechas</h2>
                <div class="rango-fechas">
                    <input type="date" id="bloqueoFechaInicio" placeholder="Fecha inicio">
                    <input type="date" id="bloqueoFechaFin" placeholder="Fecha fin">
                </div>
                <div class="checkbox-label">
                    <input type="checkbox" id="bloqueoTodoDia" checked onchange="toggleBloqueoHorario()">
                    <label>Día completo</label>
                </div>
                <div id="bloqueoHorarioDiv" style="display:none;">
                    <div style="display: flex; gap: 10px;">
                        <input type="time" id="bloqueoInicio" placeholder="Inicio">
                        <input type="time" id="bloqueoFin" placeholder="Fin">
                    </div>
                </div>
                <input type="text" id="bloqueoMotivo" placeholder="Motivo (opcional)">
                <button onclick="agregarBloqueo()">Bloquear Rango</button>
            </div>
            <div class="card">
                <h2>📅 Días Bloqueados</h2>
                <div id="listaBloqueos"></div>
            </div>
        </div>
        
        <!-- AGENDAR -->
        <div id="tab-agendar" class="tab-content">
            <div class="card">
                <h2>➕ Nueva Cita</h2>
                <input type="date" id="citaFecha" onchange="cargarHorariosDisponibles()">
                <div id="infoHorario" class="info-horario"></div>
                <div id="horariosDisponiblesDiv"></div>
                <input type="time" id="citaHora" placeholder="O escribe la hora (ej: 09:00, 09:30)" step="1800">
                <input type="text" id="citaNombre" placeholder="Nombre del cliente *">
                <input type="text" id="citaTelefono" placeholder="Teléfono">
                <select id="citaServicio"></select>
                <textarea id="citaMotivo" placeholder="Motivo / Observación" rows="2"></textarea>
                <button onclick="agendarCita()">Agendar Cita</button>
            </div>
        </div>
        
        <!-- CITAS -->
        <div id="tab-citas" class="tab-content">
            <div class="card">
                <h2>📅 Citas por Fecha</h2>
                <input type="date" id="filtroFecha" onchange="cargarCitas()">
                <div id="listaCitas"></div>
            </div>
        </div>
        
        <!-- RESUMEN -->
        <div id="tab-resumen" class="tab-content">
            <div class="card">
                <h2>📊 Resumen del Día</h2>
                <div class="numero-grande" id="totalHoy">0</div>
                <p class="text-center">Citas para hoy</p>
            </div>
            <div class="card">
                <h2>📋 Todas las Citas</h2>
                <div id="todasCitas"></div>
            </div>
        </div>
    </div>
    
    <script>
        function mostrarMensaje(texto, tipo) {
            const div = document.getElementById('mensaje');
            div.innerHTML = `<div class="mensaje ${tipo}">${texto}</div>`;
            setTimeout(() => div.innerHTML = '', 3000);
        }
        
        function mostrarTab(tab) {
            document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
            document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
            document.getElementById(`tab-${tab}`).classList.add('active');
            event.target.classList.add('active');
            
            if (tab === 'servicios') cargarServicios();
            if (tab === 'horarios') cargarHorarios();
            if (tab === 'bloqueos') { cargarBloqueos(); }
            if (tab === 'agendar') { cargarSelectServicios(); cargarHorariosDisponibles(); }
            if (tab === 'citas') cargarCitas();
            if (tab === 'resumen') cargarResumen();
        }
        
        // ========== SERVICIOS ==========
        async function cargarServicios() {
            const res = await fetch('/api/servicios');
            const servicios = await res.json();
            const container = document.getElementById('listaServicios');
            if (servicios.length === 0) {
                container.innerHTML = '<p style="color:#999;">No hay servicios. Agrega uno.</p>';
            } else {
                container.innerHTML = servicios.map(s => `
                    <div class="servicio-item">
                        <span>📌 ${s.nombre}</span>
                        <button class="danger" onclick="eliminarServicio(${s.id})">Eliminar</button>
                    </div>
                `).join('');
            }
        }
        
        async function cargarSelectServicios() {
            const res = await fetch('/api/servicios');
            const servicios = await res.json();
            const select = document.getElementById('citaServicio');
            if (servicios.length === 0) {
                select.innerHTML = '<option>No hay servicios - Agrega uno</option>';
            } else {
                select.innerHTML = servicios.map(s => `<option value="${s.nombre}">${s.nombre}</option>`).join('');
            }
        }
        
        async function agregarServicio() {
            const nombre = document.getElementById('nuevoServicio').value.trim();
            if (!nombre) { mostrarMensaje('Escribe un nombre', 'error'); return; }
            const res = await fetch('/api/servicios', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({nombre})
            });
            if (res.ok) {
                document.getElementById('nuevoServicio').value = '';
                cargarServicios();
                cargarSelectServicios();
                mostrarMensaje('✅ Servicio agregado', '');
            } else {
                mostrarMensaje('❌ Error o ya existe', 'error');
            }
        }
        
        async function eliminarServicio(id) {
            if (confirm('¿Eliminar este servicio?')) {
                await fetch(`/api/servicios/${id}`, {method: 'DELETE'});
                cargarServicios();
                cargarSelectServicios();
                mostrarMensaje('✅ Servicio eliminado', '');
            }
        }
        
        // ========== HORARIOS ==========
        async function cargarHorarios() {
            const res = await fetch('/api/horarios');
            const horarios = await res.json();
            const dias = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo'];
            const container = document.getElementById('listaHorarios');
            container.innerHTML = horarios.map((h, i) => `
                <div class="horario-row">
                    <span style="width: 80px;"><strong>${dias[i]}</strong></span>
                    <label class="checkbox-label">
                        <input type="checkbox" id="activo_${i}" ${h.activo ? 'checked' : ''}>
                        Activo
                    </label>
                    <input type="time" id="inicio_${i}" value="${h.inicio}" ${!h.activo ? 'disabled' : ''} style="width: 100px;">
                    <span>a</span>
                    <input type="time" id="fin_${i}" value="${h.fin}" ${!h.activo ? 'disabled' : ''} style="width: 100px;">
                </div>
            `).join('');
            
            for (let i = 0; i < 7; i++) {
                const cb = document.getElementById(`activo_${i}`);
                if (cb) {
                    cb.onchange = () => {
                        document.getElementById(`inicio_${i}`).disabled = !cb.checked;
                        document.getElementById(`fin_${i}`).disabled = !cb.checked;
                    };
                }
            }
        }
        
        async function guardarHorarios() {
            const horariosData = [];
            for (let i = 0; i < 7; i++) {
                horariosData.push({
                    dia: i,
                    activo: document.getElementById(`activo_${i}`).checked,
                    inicio: document.getElementById(`inicio_${i}`).value,
                    fin: document.getElementById(`fin_${i}`).value
                });
            }
            const res = await fetch('/api/horarios', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(horariosData)
            });
            if (res.ok) {
                mostrarMensaje('✅ Horarios guardados', '');
            } else {
                mostrarMensaje('❌ Error al guardar', 'error');
            }
        }
        
        // ========== BLOQUEOS (con rango de fechas) ==========
        function toggleBloqueoHorario() {
            const todoDia = document.getElementById('bloqueoTodoDia').checked;
            document.getElementById('bloqueoHorarioDiv').style.display = todoDia ? 'none' : 'block';
        }
        
        async function agregarBloqueo() {
            const fechaInicio = document.getElementById('bloqueoFechaInicio').value;
            const fechaFin = document.getElementById('bloqueoFechaFin').value;
            const todoDia = document.getElementById('bloqueoTodoDia').checked;
            const inicio = document.getElementById('bloqueoInicio')?.value || null;
            const fin = document.getElementById('bloqueoFin')?.value || null;
            const motivo = document.getElementById('bloqueoMotivo').value;
            
            if (!fechaInicio || !fechaFin) { mostrarMensaje('Selecciona el rango de fechas', 'error'); return; }
            
            const res = await fetch('/api/bloqueos', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    fecha_inicio: fechaInicio,
                    fecha_fin: fechaFin,
                    todo_dia: todoDia,
                    inicio: inicio,
                    fin: fin,
                    motivo: motivo
                })
            });
            if (res.ok) {
                document.getElementById('bloqueoFechaInicio').value = '';
                document.getElementById('bloqueoFechaFin').value = '';
                document.getElementById('bloqueoMotivo').value = '';
                cargarBloqueos();
                mostrarMensaje('✅ Rango bloqueado', '');
            } else {
                const err = await res.json();
                mostrarMensaje('❌ ' + err.detail, 'error');
            }
        }
        
        async function cargarBloqueos() {
            const res = await fetch('/api/bloqueos');
            const bloqueos = await res.json();
            const container = document.getElementById('listaBloqueos');
            if (bloqueos.length === 0) {
                container.innerHTML = '<p style="color:#999;">No hay días bloqueados</p>';
            } else {
                container.innerHTML = bloqueos.map(b => `
                    <div class="servicio-item">
                        <span>🚫 ${b.fecha_inicio} a ${b.fecha_fin} - ${b.todo_dia ? 'Día completo' : b.inicio + ' a ' + b.fin} ${b.motivo ? '('+b.motivo+')' : ''}</span>
                        <button class="danger" onclick="eliminarBloqueo(${b.id})">Eliminar</button>
                    </div>
                `).join('');
            }
        }
        
        async function eliminarBloqueo(id) {
            if (confirm('¿Eliminar este bloqueo?')) {
                await fetch(`/api/bloqueos/${id}`, {method: 'DELETE'});
                cargarBloqueos();
                mostrarMensaje('✅ Bloqueo eliminado', '');
            }
        }
        
        // ========== CITAS ==========
        async function cargarHorariosDisponibles() {
            const fecha = document.getElementById('citaFecha').value;
            if (!fecha) return;
            
            const res = await fetch(`/api/horarios-disponibles/${fecha}`);
            const data = await res.json();
            
            const infoDiv = document.getElementById('infoHorario');
            infoDiv.innerHTML = `📅 Fecha: ${fecha} - Horarios cada 30 minutos (:00 y :30)`;
            
            const container = document.getElementById('horariosDisponiblesDiv');
            if (data.horarios.length === 0) {
                container.innerHTML = '<div style="color:#C62828; padding: 10px; background:#ffebee; border-radius:5px;">⚠️ No hay horarios disponibles para esta fecha</div>';
            } else {
                container.innerHTML = `
                    <div style="margin-bottom: 5px; font-size: 12px; color: #666;">📌 Horarios disponibles (haz clic para seleccionar):</div>
                    <div class="horarios-grid">
                        ${data.horarios.map(h => `<div class="horario-sugerido" onclick="document.getElementById('citaHora').value='${h}'">${h}</div>`).join('')}
                    </div>
                `;
            }
        }
        
        async function cargarCitas() {
            const fecha = document.getElementById('filtroFecha').value || new Date().toISOString().split('T')[0];
            document.getElementById('filtroFecha').value = fecha;
            const res = await fetch(`/api/citas?fecha=${fecha}`);
            const citas = await res.json();
            const container = document.getElementById('listaCitas');
            
            if (citas.length === 0) {
                container.innerHTML = '<p style="color:#999; text-align:center;">📭 No hay citas para esta fecha</p>';
            } else {
                container.innerHTML = `
                    <table>
                        <thead><tr><th>Hora</th><th>Cliente</th><th>Servicio</th><th>Teléfono</th><th></th></tr></thead>
                        <tbody>
                            ${citas.map(c => `
                                <tr>
                                    <td><strong>${c.hora}</strong></td>
                                    <td>${c.nombre}</td>
                                    <td>${c.servicio}</td>
                                    <td>${c.telefono || '-'}</td>
                                    <td><button class="danger small" onclick="eliminarCita(${c.id})">X</button></td>
                                </tr>
                            `).join('')}
                        </tbody>
                    </table>
                `;
            }
        }
        
        async function eliminarCita(id) {
            if (confirm('¿Eliminar esta cita?')) {
                await fetch(`/api/citas/${id}`, {method: 'DELETE'});
                cargarCitas();
                cargarResumen();
                if (document.getElementById('citaFecha').value) {
                    cargarHorariosDisponibles();
                }
                mostrarMensaje('✅ Cita eliminada', '');
            }
        }
        
        async function agendarCita() {
            const fecha = document.getElementById('citaFecha').value;
            const hora = document.getElementById('citaHora').value;
            const nombre = document.getElementById('citaNombre').value.trim();
            const telefono = document.getElementById('citaTelefono').value;
            const servicio = document.getElementById('citaServicio').value;
            const motivo = document.getElementById('citaMotivo').value;
            
            if (!fecha) { mostrarMensaje('❌ Selecciona una fecha', 'error'); return; }
            if (!hora) { mostrarMensaje('❌ Selecciona una hora', 'error'); return; }
            if (!nombre) { mostrarMensaje('❌ Escribe el nombre del cliente', 'error'); return; }
            if (!servicio || servicio === 'No hay servicios - Agrega uno') { 
                mostrarMensaje('❌ Primero agrega servicios', 'error'); 
                return;
            }
            
            const minutos = parseInt(hora.split(':')[1]);
            if (minutos !== 0 && minutos !== 30) {
                mostrarMensaje('❌ La hora debe ser :00 o :30 (ej: 09:00, 09:30)', 'error');
                return;
            }
            
            const res = await fetch('/api/citas', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({fecha, hora, nombre, telefono, servicio, motivo})
            });
            
            if (res.ok) {
                document.getElementById('citaNombre').value = '';
                document.getElementById('citaTelefono').value = '';
                document.getElementById('citaMotivo').value = '';
                document.getElementById('citaHora').value = '';
                mostrarMensaje('✅ Cita agendada', '');
                cargarCitas();
                cargarResumen();
                cargarHorariosDisponibles();
            } else {
                const err = await res.json();
                mostrarMensaje('❌ ' + err.detail, 'error');
            }
        }
        
        // ========== RESUMEN ==========
        async function cargarResumen() {
            const hoy = new Date().toISOString().split('T')[0];
            const res = await fetch(`/api/citas?fecha=${hoy}`);
            const citasHoy = await res.json();
            document.getElementById('totalHoy').innerText = citasHoy.length;
            
            const resTodas = await fetch('/api/citas');
            const todas = await resTodas.json();
            const container = document.getElementById('todasCitas');
            
            if (todas.length === 0) {
                container.innerHTML = '<p style="color:#999;">No hay citas agendadas</p>';
            } else {
                container.innerHTML = `
                    <table>
                        <thead><tr><th>Fecha</th><th>Hora</th><th>Cliente</th><th>Servicio</th></tr></thead>
                        <tbody>
                            ${todas.map(c => `
                                <tr>
                                    <td>${c.fecha}</td>
                                    <td><strong>${c.hora}</strong></td>
                                    <td>${c.nombre}</td>
                                    <td>${c.servicio}</td>
                                </tr>
                            `).join('')}
                        </tbody>
                    </table>
                `;
            }
        }
        
        // Inicializar
        const hoy = new Date().toISOString().split('T')[0];
        document.getElementById('citaFecha').value = hoy;
        document.getElementById('filtroFecha').value = hoy;
        
        cargarServicios();
        cargarHorarios();
        cargarBloqueos();
        cargarSelectServicios();
    </script>
</body>
</html>
'''

if __name__ == "__main__":
    import uvicorn
    print("\n" + "="*60)
    print("🚀 AutoAgenda COMPLETA CORREGIDA v2")
    print("📱 Abre: http://localhost:8000")
    print("")
    print("✅ CORRECCIONES:")
    print("   - Horarios: ahora son :00 y :30 (08:00, 08:30, 09:00...)")
    print("   - Bloqueos parciales: NO muestra horarios bloqueados")
    print("   - Bloqueos por RANGO DE FECHAS (semanas completas)")
    print("="*60 + "\n")
    uvicorn.run(app, host="0.0.0.0", port=8000)