from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timedelta
import secrets
import hashlib

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ========== DATOS EN MEMORIA (cada usuario tiene sus propios datos) ==========
# Estructura: usuarios[email] = {password, servicios, horarios, bloqueos, citas, contadores}
usuarios = {}

# Tokens de sesión (para mantener login)
sesiones = {}  # token -> email

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

def generar_token():
    return secrets.token_urlsafe(32)

# ========== MODELOS ==========
class RegistroInput(BaseModel):
    email: str
    password: str
    nombre: str

class LoginInput(BaseModel):
    email: str
    password: str

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

# ========== DEPENDENCIA: Obtener usuario autenticado ==========
security = HTTPBearer()

def get_usuario_actual(credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = credentials.credentials
    if token not in sesiones:
        raise HTTPException(status_code=401, detail="No autenticado")
    email = sesiones[token]
    if email not in usuarios:
        raise HTTPException(status_code=401, detail="Usuario no encontrado")
    return usuarios[email]

# ========== FUNCIONES AUXILIARES ==========
def generar_horas(inicio: str, fin: str):
    horas = []
    actual = datetime.strptime(inicio, "%H:%M")
    final = datetime.strptime(fin, "%H:%M")
    while actual <= final:
        horas.append(actual.strftime("%H:%M"))
        actual += timedelta(minutes=30)
    return horas

def fecha_en_bloqueo(usuario: dict, fecha: str):
    fecha_obj = datetime.strptime(fecha, "%Y-%m-%d")
    for b in usuario["bloqueos"]:
        inicio = datetime.strptime(b["fecha_inicio"], "%Y-%m-%d")
        fin = datetime.strptime(b["fecha_fin"], "%Y-%m-%d")
        if inicio <= fecha_obj <= fin:
            return b
    return None

def obtener_horarios_disponibles(usuario: dict, fecha: str):
    fecha_obj = datetime.strptime(fecha, "%Y-%m-%d")
    dia_semana = fecha_obj.weekday()
    
    bloqueo = fecha_en_bloqueo(usuario, fecha)
    if bloqueo and bloqueo["todo_dia"]:
        return []
    
    if bloqueo and not bloqueo["todo_dia"]:
        inicio = bloqueo["inicio"]
        fin = bloqueo["fin"]
    else:
        horario = usuario["horarios"][dia_semana]
        if not horario["activo"]:
            return []
        inicio = horario["inicio"]
        fin = horario["fin"]
    
    todas_las_horas = generar_horas(inicio, fin)
    ocupadas = [c["hora"] for c in usuario["citas"] if c["fecha"] == fecha]
    disponibles = [h for h in todas_las_horas if h not in ocupadas]
    return disponibles

def inicializar_usuario(email: str, nombre: str):
    """Crea un nuevo usuario con datos por defecto"""
    return {
        "email": email,
        "nombre": nombre,
        "password": None,  # ya guardado aparte
        "servicios": [
            {"id": 1, "nombre": "Consulta General"},
            {"id": 2, "nombre": "Seguimiento"},
            {"id": 3, "nombre": "Urgencia"}
        ],
        "horarios": [
            {"dia": 0, "activo": True, "inicio": "09:00", "fin": "18:00"},
            {"dia": 1, "activo": True, "inicio": "09:00", "fin": "18:00"},
            {"dia": 2, "activo": True, "inicio": "09:00", "fin": "18:00"},
            {"dia": 3, "activo": True, "inicio": "09:00", "fin": "18:00"},
            {"dia": 4, "activo": True, "inicio": "09:00", "fin": "18:00"},
            {"dia": 5, "activo": True, "inicio": "09:00", "fin": "13:00"},
            {"dia": 6, "activo": False, "inicio": "00:00", "fin": "00:00"}
        ],
        "bloqueos": [],
        "citas": [],
        "contador_servicios": 4,
        "contador_citas": 1,
        "contador_bloqueos": 1
    }

# ========== ENDPOINTS DE AUTENTICACIÓN ==========
@app.post("/api/registro")
def registro(data: RegistroInput):
    if data.email in usuarios:
        raise HTTPException(status_code=400, detail="Email ya registrado")
    
    usuarios[data.email] = inicializar_usuario(data.email, data.nombre)
    usuarios[data.email]["password"] = hash_password(data.password)
    return {"success": True, "mensaje": "Usuario registrado"}

@app.post("/api/login")
def login(data: LoginInput):
    if data.email not in usuarios:
        raise HTTPException(status_code=401, detail="Email o contraseña incorrectos")
    
    if usuarios[data.email]["password"] != hash_password(data.password):
        raise HTTPException(status_code=401, detail="Email o contraseña incorrectos")
    
    token = generar_token()
    sesiones[token] = data.email
    return {"success": True, "token": token, "email": data.email, "nombre": usuarios[data.email]["nombre"]}

@app.post("/api/logout")
def logout(credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = credentials.credentials
    if token in sesiones:
        del sesiones[token]
    return {"success": True}

@app.get("/api/verificar")
def verificar(usuario: dict = Depends(get_usuario_actual)):
    return {"autenticado": True, "email": usuario["email"], "nombre": usuario["nombre"]}

# ========== ENDPOINTS DE SERVICIOS ==========
@app.get("/api/servicios")
def get_servicios(usuario: dict = Depends(get_usuario_actual)):
    return usuario["servicios"]

@app.post("/api/servicios")
def add_servicio(data: ServicioInput, usuario: dict = Depends(get_usuario_actual)):
    for s in usuario["servicios"]:
        if s["nombre"].lower() == data.nombre.lower():
            raise HTTPException(status_code=400, detail="Servicio ya existe")
    nuevo = {"id": usuario["contador_servicios"], "nombre": data.nombre}
    usuario["servicios"].append(nuevo)
    usuario["contador_servicios"] += 1
    return {"success": True}

@app.delete("/api/servicios/{id}")
def delete_servicio(id: int, usuario: dict = Depends(get_usuario_actual)):
    usuario["servicios"] = [s for s in usuario["servicios"] if s["id"] != id]
    return {"success": True}

# ========== ENDPOINTS DE HORARIOS ==========
@app.get("/api/horarios")
def get_horarios(usuario: dict = Depends(get_usuario_actual)):
    return usuario["horarios"]

@app.post("/api/horarios")
def update_horarios(data: List[HorarioInput], usuario: dict = Depends(get_usuario_actual)):
    for h in data:
        for i, existing in enumerate(usuario["horarios"]):
            if existing["dia"] == h.dia:
                usuario["horarios"][i] = {"dia": h.dia, "activo": h.activo, "inicio": h.inicio, "fin": h.fin}
    return {"success": True}

# ========== ENDPOINTS DE BLOQUEOS ==========
@app.get("/api/bloqueos")
def get_bloqueos(usuario: dict = Depends(get_usuario_actual)):
    return usuario["bloqueos"]

@app.post("/api/bloqueos")
def add_bloqueo(data: BloqueoInput, usuario: dict = Depends(get_usuario_actual)):
    fecha_inicio_obj = datetime.strptime(data.fecha_inicio, "%Y-%m-%d")
    hoy = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    if fecha_inicio_obj < hoy:
        raise HTTPException(status_code=400, detail="No se puede bloquear fechas pasadas")
    
    nuevo = {
        "id": usuario["contador_bloqueos"],
        "fecha_inicio": data.fecha_inicio,
        "fecha_fin": data.fecha_fin,
        "todo_dia": data.todo_dia,
        "inicio": data.inicio,
        "fin": data.fin,
        "motivo": data.motivo
    }
    usuario["bloqueos"].append(nuevo)
    usuario["contador_bloqueos"] += 1
    return {"success": True}

@app.delete("/api/bloqueos/{id}")
def delete_bloqueo(id: int, usuario: dict = Depends(get_usuario_actual)):
    usuario["bloqueos"] = [b for b in usuario["bloqueos"] if b["id"] != id]
    return {"success": True}

# ========== ENDPOINTS DE CITAS ==========
@app.get("/api/citas")
def get_citas(fecha: Optional[str] = None, usuario: dict = Depends(get_usuario_actual)):
    if fecha:
        resultado = [c for c in usuario["citas"] if c["fecha"] == fecha]
        resultado.sort(key=lambda x: x["hora"])
        return resultado
    todas = sorted(usuario["citas"], key=lambda x: (x["fecha"], x["hora"]))
    return todas

@app.post("/api/citas")
def add_cita(data: CitaInput, usuario: dict = Depends(get_usuario_actual)):
    minutos = int(data.hora.split(":")[1])
    if minutos not in [0, 30]:
        raise HTTPException(status_code=400, detail="Las horas deben ser :00 o :30")
    disponibles = obtener_horarios_disponibles(usuario, data.fecha)
    if data.hora not in disponibles:
        raise HTTPException(status_code=400, detail="Horario no disponible")
    
    nueva = {
        "id": usuario["contador_citas"],
        "fecha": data.fecha,
        "hora": data.hora,
        "nombre": data.nombre,
        "telefono": data.telefono,
        "servicio": data.servicio,
        "motivo": data.motivo
    }
    usuario["citas"].append(nueva)
    usuario["contador_citas"] += 1
    return {"success": True}

@app.delete("/api/citas/{id}")
def delete_cita(id: int, usuario: dict = Depends(get_usuario_actual)):
    usuario["citas"] = [c for c in usuario["citas"] if c["id"] != id]
    return {"success": True}

@app.get("/api/horarios-disponibles/{fecha}")
def get_horarios_disponibles(fecha: str, usuario: dict = Depends(get_usuario_actual)):
    return {"horarios": obtener_horarios_disponibles(usuario, fecha)}

@app.get("/api/resumen")
def get_resumen(usuario: dict = Depends(get_usuario_actual)):
    hoy = datetime.now().strftime("%Y-%m-%d")
    citas_hoy = [c for c in usuario["citas"] if c["fecha"] == hoy]
    return {"citas_hoy": len(citas_hoy), "total_citas": len(usuario["citas"])}

# ========== FRONTEND CON LOGIN ==========
HTML_CONTENT = '''<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AutoAgenda</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: Arial, sans-serif; background: #f0f2f5; padding: 20px; }
        .container { max-width: 750px; margin: 0 auto; }
        h1 { color: #2E7D32; text-align: center; }
        .sub { text-align: center; color: #666; margin-bottom: 20px; }
        
        /* Login/Registro */
        .auth-container { max-width: 400px; margin: 50px auto; background: white; padding: 30px; border-radius: 10px; }
        .auth-container h2 { text-align: center; margin-bottom: 20px; color: #2E7D32; }
        .auth-container input { width: 100%; padding: 12px; margin-bottom: 15px; border: 1px solid #ddd; border-radius: 5px; }
        .auth-container button { width: 100%; padding: 12px; background: #2E7D32; color: white; border: none; border-radius: 5px; cursor: pointer; font-size: 16px; }
        .auth-container button.secondary { background: #666; margin-top: 10px; }
        .switch-auth { text-align: center; margin-top: 15px; color: #2E7D32; cursor: pointer; }
        
        .tabs { display: flex; gap: 5px; margin-bottom: 20px; flex-wrap: wrap; }
        .tab { flex: 1; padding: 10px; background: #ddd; text-align: center; cursor: pointer; border-radius: 5px; font-weight: bold; }
        .tab.active { background: #2E7D32; color: white; }
        .tab-content { display: none; }
        .tab-content.active { display: block; }
        .card { background: white; border-radius: 10px; padding: 20px; margin-bottom: 20px; }
        .card h2 { color: #2E7D32; margin-bottom: 15px; }
        input, select, textarea { width: 100%; padding: 10px; margin-bottom: 10px; border: 1px solid #ddd; border-radius: 5px; }
        button { width: 100%; padding: 10px; background: #2E7D32; color: white; border: none; border-radius: 5px; cursor: pointer; }
        button.danger { background: #C62828; width: auto; padding: 5px 10px; }
        .servicio-item { display: flex; justify-content: space-between; padding: 10px; background: #f9f9f9; margin-bottom: 5px; border-radius: 5px; }
        .horario-row { display: flex; gap: 10px; align-items: center; margin-bottom: 10px; flex-wrap: wrap; }
        table { width: 100%; border-collapse: collapse; }
        th, td { padding: 10px; text-align: left; border-bottom: 1px solid #ddd; }
        th { background: #A8E6CF; }
        .numero-grande { font-size: 48px; color: #2E7D32; text-align: center; }
        .horario-sugerido { background: #e8f5e9; padding: 8px 12px; margin: 3px; border-radius: 5px; cursor: pointer; display: inline-block; }
        .horarios-grid { display: flex; flex-wrap: wrap; gap: 5px; }
        .rango-fechas { display: flex; gap: 10px; }
        .rango-fechas input { flex: 1; }
        .header-user { display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px; }
        .logout-btn { background: #C62828; padding: 8px 15px; border-radius: 5px; cursor: pointer; color: white; font-size: 14px; }
    </style>
</head>
<body>
    <div class="container" id="app">
        <!-- Pantalla de Login -->
        <div id="login-screen">
            <div class="auth-container">
                <h2>🔐 AutoAgenda</h2>
                <div id="login-form">
                    <input type="email" id="login-email" placeholder="Email">
                    <input type="password" id="login-password" placeholder="Contraseña">
                    <button onclick="login()">Iniciar Sesión</button>
                    <div class="switch-auth" onclick="mostrarRegistro()">¿No tienes cuenta? Regístrate</div>
                </div>
                <div id="registro-form" style="display:none;">
                    <input type="text" id="reg-nombre" placeholder="Nombre completo">
                    <input type="email" id="reg-email" placeholder="Email">
                    <input type="password" id="reg-password" placeholder="Contraseña">
                    <button onclick="registro()">Registrarse</button>
                    <div class="switch-auth" onclick="mostrarLogin()">¿Ya tienes cuenta? Inicia Sesión</div>
                </div>
            </div>
        </div>
        
        <!-- Pantalla Principal (App) -->
        <div id="app-screen" style="display:none;">
            <div class="header-user">
                <span>📋 AutoAgenda</span>
                <span><span id="userNombre"></span> <span class="logout-btn" onclick="logout()">Cerrar Sesión</span></span>
            </div>
            <div class="sub">"Configura una vez. Agenda siempre"</div>
            
            <div class="tabs">
                <div class="tab active" onclick="mostrarTab('servicios')">Servicios</div>
                <div class="tab" onclick="mostrarTab('horarios')">Horarios</div>
                <div class="tab" onclick="mostrarTab('bloqueos')">Bloqueos</div>
                <div class="tab" onclick="mostrarTab('agendar')">Agendar</div>
                <div class="tab" onclick="mostrarTab('citas')">Citas</div>
                <div class="tab" onclick="mostrarTab('resumen')">Resumen</div>
            </div>
            <div id="mensaje"></div>
            <div id="tab-servicios" class="tab-content active">
                <div class="card"><h2>Agregar Servicio</h2><input id="nuevoServicio" placeholder="Nombre"><button onclick="agregarServicio()">Agregar</button></div>
                <div class="card"><h2>Mis Servicios</h2><div id="listaServicios"></div></div>
            </div>
            <div id="tab-horarios" class="tab-content">
                <div class="card"><h2>Horarios Laborales</h2><div id="listaHorarios"></div><button onclick="guardarHorarios()">Guardar</button></div>
            </div>
            <div id="tab-bloqueos" class="tab-content">
                <div class="card"><h2>Bloquear Rango</h2><div class="rango-fechas"><input type="date" id="bloqueoFechaInicio"><input type="date" id="bloqueoFechaFin"></div>
                <label><input type="checkbox" id="bloqueoTodoDia" checked onchange="toggleBloqueoHorario()"> Día completo</label>
                <div id="bloqueoHorarioDiv" style="display:none"><div class="rango-fechas"><input type="time" id="bloqueoInicio"><input type="time" id="bloqueoFin"></div></div>
                <input id="bloqueoMotivo" placeholder="Motivo"><button onclick="agregarBloqueo()">Bloquear</button></div>
                <div class="card"><h2>Días Bloqueados</h2><div id="listaBloqueos"></div></div>
            </div>
            <div id="tab-agendar" class="tab-content">
                <div class="card"><h2>Nueva Cita</h2><input type="date" id="citaFecha" onchange="cargarHorariosDisponibles()"><div id="horariosDisponiblesDiv"></div>
                <input type="time" id="citaHora" step="1800"><input id="citaNombre" placeholder="Nombre"><input id="citaTelefono" placeholder="Teléfono">
                <select id="citaServicio"></select><textarea id="citaMotivo" rows="2" placeholder="Motivo"></textarea><button onclick="agendarCita()">Agendar</button></div>
            </div>
            <div id="tab-citas" class="tab-content">
                <div class="card"><h2>Citas por Fecha</h2><input type="date" id="filtroFecha" onchange="cargarCitas()"><div id="listaCitas"></div></div>
            </div>
            <div id="tab-resumen" class="tab-content">
                <div class="card"><h2>Resumen</h2><div class="numero-grande" id="totalHoy">0</div><p>Citas para hoy</p></div>
                <div class="card"><h2>Todas las Citas</h2><div id="todasCitas"></div></div>
            </div>
        </div>
    </div>
    
    <script>
        let token = localStorage.getItem('token');
        let convId = 'wa_' + Date.now();
        
        function mostrarMensaje(texto, tipo) {
            const div = document.getElementById('mensaje');
            div.innerHTML = `<div style="background:${tipo==='error'?'#ffebee':'#A8E6CF'};padding:10px;margin-bottom:15px;border-radius:5px;">${texto}</div>`;
            setTimeout(() => div.innerHTML = '', 3000);
        }
        
        async function login() {
            const email = document.getElementById('login-email').value;
            const password = document.getElementById('login-password').value;
            if(!email||!password){mostrarMensaje('Complete todos los campos','error');return;}
            const res = await fetch('/api/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email,password})});
            if(res.ok){
                const data = await res.json();
                token = data.token;
                localStorage.setItem('token', token);
                localStorage.setItem('userNombre', data.nombre);
                await cargarApp();
            }else{
                mostrarMensaje('Email o contraseña incorrectos','error');
            }
        }
        
        async function registro() {
            const nombre = document.getElementById('reg-nombre').value;
            const email = document.getElementById('reg-email').value;
            const password = document.getElementById('reg-password').value;
            if(!nombre||!email||!password){mostrarMensaje('Complete todos los campos','error');return;}
            const res = await fetch('/api/registro',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({nombre,email,password})});
            if(res.ok){
                mostrarMensaje('Registro exitoso. Ahora inicia sesión','');
                mostrarLogin();
            }else{
                mostrarMensaje('Email ya registrado','error');
            }
        }
        
        async function logout() {
            if(token){
                await fetch('/api/logout',{method:'POST',headers:{'Authorization':`Bearer ${token}`}});
            }
            localStorage.removeItem('token');
            localStorage.removeItem('userNombre');
            token = null;
            document.getElementById('app-screen').style.display = 'none';
            document.getElementById('login-screen').style.display = 'block';
        }
        
        function mostrarRegistro() {
            document.getElementById('login-form').style.display = 'none';
            document.getElementById('registro-form').style.display = 'block';
        }
        
        function mostrarLogin() {
            document.getElementById('login-form').style.display = 'block';
            document.getElementById('registro-form').style.display = 'none';
        }
        
        async function cargarApp() {
            if(!token) return;
            const res = await fetch('/api/verificar',{headers:{'Authorization':`Bearer ${token}`}});
            if(!res.ok){logout();return;}
            document.getElementById('login-screen').style.display = 'none';
            document.getElementById('app-screen').style.display = 'block';
            document.getElementById('userNombre').innerText = localStorage.getItem('userNombre') || 'Usuario';
            const hoy = new Date().toISOString().split('T')[0];
            document.getElementById('citaFecha').value = hoy;
            document.getElementById('filtroFecha').value = hoy;
            await cargarServicios();
            await cargarHorarios();
            await cargarBloqueos();
            await cargarSelectServicios();
        }
        
        async function fetchApi(url, options={}) {
            const headers = {'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json'};
            return fetch(url, {...options, headers});
        }
        
        function mostrarTab(tab){
            document.querySelectorAll('.tab-content').forEach(t=>t.classList.remove('active'));
            document.querySelectorAll('.tab').forEach(t=>t.classList.remove('active'));
            document.getElementById(`tab-${tab}`).classList.add('active');
            event.target.classList.add('active');
            if(tab==='servicios') cargarServicios();
            if(tab==='horarios') cargarHorarios();
            if(tab==='bloqueos') cargarBloqueos();
            if(tab==='agendar'){cargarSelectServicios();cargarHorariosDisponibles();}
            if(tab==='citas') cargarCitas();
            if(tab==='resumen') cargarResumen();
        }
        
        async function cargarServicios(){
            const res=await fetchApi('/api/servicios');
            const s=await res.json();
            document.getElementById('listaServicios').innerHTML=s.map(s=>`<div class="servicio-item"><span>📌 ${s.nombre}</span><button class="danger" onclick="eliminarServicio(${s.id})">Eliminar</button></div>`).join('');
        }
        
        async function cargarSelectServicios(){
            const res=await fetchApi('/api/servicios');
            const s=await res.json();
            document.getElementById('citaServicio').innerHTML=s.map(s=>`<option value="${s.nombre}">${s.nombre}</option>`).join('');
        }
        
        async function agregarServicio(){
            const nombre=document.getElementById('nuevoServicio').value.trim();
            if(!nombre) return;
            await fetchApi('/api/servicios',{method:'POST',body:JSON.stringify({nombre})});
            document.getElementById('nuevoServicio').value='';
            cargarServicios();
            cargarSelectServicios();
        }
        
        async function eliminarServicio(id){
            if(confirm('Eliminar?')) await fetchApi(`/api/servicios/${id}`,{method:'DELETE'});
            cargarServicios();
            cargarSelectServicios();
        }
        
        async function cargarHorarios(){
            const res=await fetchApi('/api/horarios');
            const h=await res.json();
            const dias=['Lunes','Martes','Miércoles','Jueves','Viernes','Sábado','Domingo'];
            document.getElementById('listaHorarios').innerHTML=h.map((h,i)=>`<div class="horario-row"><span>${dias[i]}</span><label><input type="checkbox" id="activo_${i}" ${h.activo?'checked':''}> Activo</label><input type="time" id="inicio_${i}" value="${h.inicio}" ${!h.activo?'disabled':''}><span>a</span><input type="time" id="fin_${i}" value="${h.fin}" ${!h.activo?'disabled':''}></div>`).join('');
            for(let i=0;i<7;i++) document.getElementById(`activo_${i}`).onchange=()=>{document.getElementById(`inicio_${i}`).disabled=!document.getElementById(`activo_${i}`).checked;document.getElementById(`fin_${i}`).disabled=!document.getElementById(`activo_${i}`).checked;};
        }
        
        async function guardarHorarios(){
            const data=[];
            for(let i=0;i<7;i++) data.push({dia:i,activo:document.getElementById(`activo_${i}`).checked,inicio:document.getElementById(`inicio_${i}`).value,fin:document.getElementById(`fin_${i}`).value});
            await fetchApi('/api/horarios',{method:'POST',body:JSON.stringify(data)});
            mostrarMensaje('Horarios guardados','');
        }
        
        function toggleBloqueoHorario(){document.getElementById('bloqueoHorarioDiv').style.display=document.getElementById('bloqueoTodoDia').checked?'none':'block';}
        
        async function agregarBloqueo(){
            const fechaInicio=document.getElementById('bloqueoFechaInicio').value,fechaFin=document.getElementById('bloqueoFechaFin').value,todoDia=document.getElementById('bloqueoTodoDia').checked,inicio=document.getElementById('bloqueoInicio')?.value,fin=document.getElementById('bloqueoFin')?.value,motivo=document.getElementById('bloqueoMotivo').value;
            if(!fechaInicio||!fechaFin) return;
            const res=await fetchApi('/api/bloqueos',{method:'POST',body:JSON.stringify({fecha_inicio:fechaInicio,fecha_fin:fechaFin,todo_dia:todoDia,inicio,fin,motivo})});
            if(res.ok){
                document.getElementById('bloqueoFechaInicio').value='';document.getElementById('bloqueoFechaFin').value='';document.getElementById('bloqueoMotivo').value='';
                cargarBloqueos();
                mostrarMensaje('Rango bloqueado','');
            }else mostrarMensaje('Error','error');
        }
        
        async function cargarBloqueos(){
            const res=await fetchApi('/api/bloqueos');
            const b=await res.json();
            document.getElementById('listaBloqueos').innerHTML=b.map(b=>`<div class="servicio-item"><span>🚫 ${b.fecha_inicio} a ${b.fecha_fin} - ${b.todo_dia?'Día completo':b.inicio+' a '+b.fin} ${b.motivo||''}</span><button class="danger" onclick="eliminarBloqueo(${b.id})">Eliminar</button></div>`).join('');
        }
        
        async function eliminarBloqueo(id){await fetchApi(`/api/bloqueos/${id}`,{method:'DELETE'});cargarBloqueos();}
        
        async function cargarHorariosDisponibles(){
            const fecha=document.getElementById('citaFecha').value;
            if(!fecha) return;
            const res=await fetchApi(`/api/horarios-disponibles/${fecha}`);
            const data=await res.json();
            const container=document.getElementById('horariosDisponiblesDiv');
            if(data.horarios.length===0) container.innerHTML='<div>No hay horarios disponibles</div>';
            else container.innerHTML=`<div class="horarios-grid">${data.horarios.map(h=>`<div class="horario-sugerido" onclick="document.getElementById('citaHora').value='${h}'">${h}</div>`).join('')}</div>`;
        }
        
        async function cargarCitas(){
            const fecha=document.getElementById('filtroFecha').value||new Date().toISOString().split('T')[0];
            document.getElementById('filtroFecha').value=fecha;
            const res=await fetchApi(`/api/citas?fecha=${fecha}`);
            const c=await res.json();
            const container=document.getElementById('listaCitas');
            if(c.length===0) container.innerHTML='<p>No hay citas</p>';
            else container.innerHTML=`<tr><thead><tr><th>Hora</th><th>Cliente</th><th>Servicio</th><th></th></tr></thead><tbody>${c.map(c=>`<tr><td>${c.hora}</td><td>${c.nombre}</td><td>${c.servicio}</td><td><button class="danger" onclick="eliminarCita(${c.id})">X</button></td></tr>`).join('')}</tbody></table>`;
        }
        
        async function eliminarCita(id){await fetchApi(`/api/citas/${id}`,{method:'DELETE'});cargarCitas();cargarResumen();cargarHorariosDisponibles();}
        
        async function agendarCita(){
            const fecha=document.getElementById('citaFecha').value,hora=document.getElementById('citaHora').value,nombre=document.getElementById('citaNombre').value.trim(),telefono=document.getElementById('citaTelefono').value,servicio=document.getElementById('citaServicio').value,motivo=document.getElementById('citaMotivo').value;
            if(!fecha||!hora||!nombre){mostrarMensaje('Complete fecha, hora y nombre','error');return;}
            const res=await fetchApi('/api/citas',{method:'POST',body:JSON.stringify({fecha,hora,nombre,telefono,servicio,motivo})});
            if(res.ok){
                document.getElementById('citaNombre').value='';document.getElementById('citaTelefono').value='';document.getElementById('citaMotivo').value='';document.getElementById('citaHora').value='';
                cargarCitas();cargarResumen();cargarHorariosDisponibles();
                mostrarMensaje('Cita agendada','');
            }else mostrarMensaje('Horario no disponible','error');
        }
        
        async function cargarResumen(){
            const hoy=new Date().toISOString().split('T')[0];
            const res=await fetchApi(`/api/citas?fecha=${hoy}`);
            const citasHoy=await res.json();
            document.getElementById('totalHoy').innerText=citasHoy.length;
            const resTodas=await fetchApi('/api/citas');
            const todas=await resTodas.json();
            const container=document.getElementById('todasCitas');
            if(todas.length===0) container.innerHTML='<p>No hay citas</p>';
            else container.innerHTML=`<tr><thead><tr><th>Fecha</th><th>Hora</th><th>Cliente</th><th>Servicio</th></tr></thead><tbody>${todas.map(c=>`<tr><td>${c.fecha}</td><td>${c.hora}</td><td>${c.nombre}</td><td>${c.servicio}</td></tr>`).join('')}</tbody></table>`;
        }
        
        if(token){cargarApp();}
    </script>
</body>
</html>
'''

@app.get("/")
def root():
    return HTMLResponse(HTML_CONTENT)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)