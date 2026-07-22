import os
from flask import Flask, render_template, request, redirect, url_for, flash, session
import pymysql
from datetime import datetime
from flask import jsonify

# 1. Importación de Repositorios (Consolidados)
import repositories.evento_repository as evento_repo
import repositories.usuario_repository as usuario_repo
#import repositories.inscripcion_repository as inscripcion_repo
from database import obtener_conexion
from repositories.inscripcion_repository import registrar_inscripcion_segura
# 2. Importación de Módulos Core y Seguridad
from core.security import (
    hash_password, 
    verificar_password, 
    requerir_rol, 
    obtener_serializer,
    clean_input_strict
)
from core.validators import validar_cedula_institucional, validar_evento_duplicado
from core.broadcaster import generar_ficha_difusion

app = Flask(__name__)
# Clave secreta para cifrar cookies de sesión y firmar los tokens de recuperación
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'clave_secreta_super_segura_facyt_2026')

# Instancia del Serializador para tokens temporales de recuperación
serializer = obtener_serializer(app.secret_key)


# --- RUTA 1: INICIO (DASHBOARD PÚBLICO Y PRIVADO) ---
@app.route('/')
def inicio():
    # SI NO HAY SESIÓN: Mostrar pantalla limpia de bienvenida sin cartelera ni métricas
    if 'usuario_id' not in session:
        return render_template(
            'index.html', 
            anonimo=True, 
            metrics={}, 
            eventos=[], 
            eventos_cartelera=[],
            eventos_inscritos_ids=[]
        )
    
    # SI HAY SESIÓN INICIADA: Cargar métricas/estadísticos y datos del sistema
    usuario_id = session['usuario_id']
    
    try:
        # Obtener lista de IDs de eventos en los que el usuario ya está inscrito
        eventos_inscritos_raw = evento_repo.obtener_eventos_por_usuario(usuario_id)
        # Nos aseguramos de extraer solo los IDs por si la función devuelve diccionarios o tuplas
        eventos_inscritos_ids = [
            ev['id'] if isinstance(ev, dict) else (ev[0] if isinstance(ev, (tuple, list)) else ev)
            for ev in eventos_inscritos_raw
        ] if eventos_inscritos_raw else []

        metrics = evento_repo.obtener_metricas_dashboard()  
        
        # Le pasamos el usuario_id a la consulta para que devuelva 'espacio', 'capacidad' y 'enlace_virtual'
        eventos_proximos = evento_repo.obtener_proximos_eventos(usuario_id) if hasattr(evento_repo, 'obtener_proximos_eventos') else []
        eventos_cartelera = evento_repo.obtener_eventos_cartelera_publica(usuario_id) if hasattr(evento_repo, 'obtener_eventos_cartelera_publica') else []

    except Exception as e:
        print(f"Error al cargar métricas del inicio: {e}")
        metrics = {}
        eventos_proximos = []
        eventos_cartelera = []
        eventos_inscritos_ids = []
        
    return render_template(
        'index.html', 
        metrics=metrics, 
        eventos=eventos_proximos or eventos_cartelera, # Si usas 'eventos' en index.html
        eventos_cartelera=eventos_cartelera, 
        eventos_inscritos_ids=eventos_inscritos_ids,
        anonimo=False
    )

# --- RUTA 2: REGISTRO DE USUARIOS CON VALIDACIÓN INSTITUCIONAL ---
@app.route('/registro', methods=['GET', 'POST'])
def registro():
    if request.method == 'POST':
        nombre = request.form.get('nombre')
        cedula = request.form.get('cedula', '').strip()
        correo = request.form.get('correo')
        password = request.form.get('password')
        rol = request.form.get('rol')

        cedula_clean = clean_input_strict(cedula)
        nombre_clean = clean_input_strict(nombre)

        if not cedula_clean or not nombre_clean:
            flash("❌ Error: Se detectaron caracteres no permitidos en el formulario.", "error")
            return redirect(url_for('registro'))

        # VALIDACIÓN INSTITUCIONAL DE CÉDULA (Solo Administrativos y Ponentes)
        if rol in ['ponente', 'administrativo']:
            autorizado = validar_cedula_institucional(cedula_clean, rol)
            if not autorizado:
                flash(f"❌ Acceso Denegado: La cédula {cedula_clean} no está registrada en la nómina para el rol: {rol}.", "error")
                return redirect(url_for('registro'))

        password_hashed = hash_password(password)
        exito = usuario_repo.crear_usuario(nombre_clean, cedula_clean, correo, password_hashed, rol)
        
        if exito:
            flash("🎉 Cuenta creada con éxito. Ya puedes iniciar sesión.", "success")
            return redirect(url_for('login'))
        else:
            flash("❌ Error: La cédula o el correo ya se encuentran registrados.", "error")

    return render_template('registro.html')


# --- RUTA 3: ACCESO UNIFICADO (LOGIN) ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        correo = request.form.get('correo')
        contrasena = request.form.get('contrasena')

        if not correo or not contrasena:
            flash("Error: Por favor rellene todos los campos.", "error")
            return redirect(url_for('login'))

        usuario = usuario_repo.obtener_usuario_por_correo(correo)

        if usuario and verificar_password(usuario['contrasena_hash'], contrasena):
            session['usuario_id'] = usuario['id']
            session['usuario_nombre'] = usuario['nombre']
            session['usuario_rol'] = usuario['rol']
            
            flash(f"¡Bienvenido de nuevo, {usuario['nombre']}! 👋", "success")
            return redirect(url_for('inicio'))
        else:
            flash("Error: Credenciales incorrectas.", "error")

    return render_template('login.html')


# --- RUTA 4: RECUPERACIÓN AUTÓNOMA DE ACCESO ---
@app.route('/recuperar-acceso', methods=['GET', 'POST'])
def recuperar_acceso():
    if request.method == 'POST':
        cedula = request.form.get('cedula')
        correo = request.form.get('correo')

        cedula_clean = clean_input_strict(cedula)
        usuario = usuario_repo.obtener_usuario_por_cedula_y_correo(cedula_clean, correo)

        if usuario:
            token = serializer.dumps(usuario['correo'], salt='recuperar-password-salt')
            url_recuperacion = url_for('redefinir_password', token=token, _external=True)
            
            flash(f"🔑 Enlace de recuperación generado: {url_recuperacion}", "success")
            return redirect(url_for('login'))
        else:
            flash("❌ Los datos provistos no coinciden con ningún usuario registrado.", "error")

    return render_template('recuperar.html')


@app.route('/recuperar-acceso/redefinir/<token>', methods=['GET', 'POST'])
def redefinir_password(token):
    try:
        correo = serializer.loads(token, salt='recuperar-password-salt', max_age=600)
    except Exception:
        flash("❌ El enlace de recuperación es inválido o ha expirado.", "error")
        return redirect(url_for('login'))

    if request.method == 'POST':
        nueva_password = request.form.get('password')
        usuario = usuario_repo.obtener_usuario_por_correo(correo)
        
        if usuario:
            nuevo_hash = hash_password(nueva_password)
            usuario_repo.actualizar_contrasena_por_id(usuario['id'], nuevo_hash)
            flash("✅ Tu contraseña ha sido actualizada con éxito. Ya puedes ingresar.", "success")
            return redirect(url_for('login'))
            
    return render_template('redefinir_password.html', token=token)


# --- RUTA 5: SOLICITAR ESPACIOS (SOLO PROFESORES/PONENTES Y ADMIN) ---
@app.route('/solicitar', methods=['GET', 'POST'])
@requerir_rol(['ponente', 'administrativo'])
def solicitar():
    if request.method == 'POST':
        titulo = request.form.get('titulo')
        departamento = request.form.get('departamento') # <--- NUEVO CAMPO AÑADIDO
        tipo_actividad = request.form.get('tipo_actividad')
        espacio_id = request.form.get('espacio_id')
        enlace_virtual = request.form.get('enlace_virtual', '') # <--- NUEVO CAMPO AÑADIDO (Opcional)
        fecha = request.form.get('fecha')
        hora_inicio = request.form.get('hora_inicio')
        hora_fin = request.form.get('hora_fin')
        
        # 1. Validar que ningún campo obligatorio venga vacío (incluyendo departamento)
        if not all([titulo, departamento, tipo_actividad, espacio_id, fecha, hora_inicio, hora_fin]):
            flash("❌ Por favor complete todos los campos requeridos.", "error")
            return redirect(url_for('solicitar'))

        # 2. Verificar que los horarios no vengan vacíos (satisface a Pylance y evita crashes)
        if not hora_inicio or not hora_fin:
            flash("❌ Por favor especifique los horarios de inicio y fin.", "error")
            return redirect(url_for('solicitar'))

        try:
            # 3. Convertir a objetos 'time' para validar lógica de tiempo
            t_inicio = datetime.strptime(hora_inicio, "%H:%M").time()
            t_fin = datetime.strptime(hora_fin, "%H:%M").time()

            # 4. Validar que no comience después de terminar
            if t_inicio >= t_fin:
                flash("❌ La hora de inicio debe ser anterior a la hora de finalización.", "error")
                return redirect(url_for('solicitar'))

        except ValueError:
            flash("❌ Formato de hora inválido.", "error")
            return redirect(url_for('solicitar'))

        # 5. Caso de Borde: Evitar duplicados por título
        if validar_evento_duplicado(titulo):
            flash(f"❌ Error: Ya existe un evento registrado o en revisión con el título '{titulo}'.", "error")
            return redirect(url_for('solicitar'))

        # 6. Crear la solicitud delegando en el Repositorio de Eventos (pasando departamento y enlace_virtual)
        resultado = evento_repo.crear_solicitud_evento(
            titulo, session['usuario_id'], tipo_actividad, espacio_id, fecha, hora_inicio, hora_fin, departamento, enlace_virtual
        )

        if resultado.get('exito'):
            flash("¡Solicitud registrada correctamente! Queda en espera de revisión.", "success")
            return redirect(url_for('inicio'))
        else:
            flash(f"❌ {resultado.get('mensaje', 'Error al procesar la solicitud.')}", "error")

    espacios = evento_repo.obtener_lista_espacios_formulario()
    return render_template('solicitar.html', espacios=espacios)

# --- RUTA 5.1: API DÍAS OCUPADOS (PARA CALENDARIO LATERAL) ---
@app.route('/api/dias-ocupados')
def api_dias_ocupados():
    """Retorna un listado JSON con las fechas ('YYYY-MM-DD') que tienen eventos agendados."""
    conexion = obtener_conexion()
    try:
        with conexion.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute("""
                SELECT DISTINCT DATE_FORMAT(fecha, '%%Y-%%m-%%d') as fecha 
                FROM eventos 
                WHERE estado IN ('aprobado', 'pendiente')
            """)
            resultados = cursor.fetchall()
            fechas = [row['fecha'] for row in resultados]
        return jsonify(fechas)
    except Exception as e:
        print(f"Error en API dias-ocupados: {e}")
        return jsonify([])
    finally:
        conexion.close()


# --- RUTA 5.2: API DISPONIBILIDAD DE HORARIOS POR ESPACIO Y FECHA ---
@app.route('/api/disponibilidad-espacio')
def api_disponibilidad_espacio():
    """Retorna las franjas horarias ocupadas de un espacio especifico en una fecha dada."""
    espacio_id = request.args.get('espacio_id')
    fecha = request.args.get('fecha')

    if not espacio_id or not fecha:
        return jsonify([])

    conexion = obtener_conexion()
    try:
        with conexion.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute("""
                SELECT titulo, 
                       TIME_FORMAT(hora_inicio, '%%H:%%i') as inicio, 
                       TIME_FORMAT(hora_fin, '%%H:%%i') as fin, 
                       estado
                FROM eventos 
                WHERE espacio_id = %s 
                  AND fecha = %s 
                  AND estado IN ('aprobado', 'pendiente')
                ORDER BY hora_inicio ASC
            """, (espacio_id, fecha))
            eventos_ocupados = cursor.fetchall()
        return jsonify(eventos_ocupados)
    except Exception as e:
        print(f"Error en API disponibilidad-espacio: {e}")
        return jsonify([])
    finally:
        conexion.close()


# --- RUTA 6: PANEL ADMINISTRATIVO PRIVILEGIADO ---
@app.route('/admin')
@requerir_rol(['administrativo'])
def admin():
    solicitudes = evento_repo.obtener_solicitudes_totales_admin()
    propuestas = evento_repo.obtener_propuestas_totales_admin()
    top_espacios = evento_repo.obtener_top_espacios()
    conteo_estados = evento_repo.obtener_conteo_estados()
    metrics = evento_repo.obtener_metricas_dashboard()

    return render_template('admin.html', 
                           solicitudes=solicitudes, 
                           propuestas=propuestas, 
                           top_espacios=top_espacios, 
                           conteo_estados=conteo_estados,
                            metrics = metrics)

# --- RUTA 7: CONTROL Y ACTUALIZACIÓN DE ESTADOS ---
@app.route('/admin/actualizar-estado/<int:evento_id>', methods=['POST'])
@requerir_rol(['administrativo'])
def admin_actualizar_estado(evento_id):
    nuevo_estado = request.form.get('estado')
    
    # 1. Validación de seguridad para evitar errores si nuevo_estado es None o está vacío
    if not nuevo_estado:
        flash("❌ Error: No se seleccionó un estado válido.", "error")
        return redirect(url_for('admin'))

    resultado = evento_repo.actualizar_estado_evento(evento_id, nuevo_estado)
    
    if resultado.get('status') == 'success':
        # Convertimos a string por seguridad antes de aplicar .upper()
        estado_texto = str(nuevo_estado).upper()
        flash(f"📢 El estado del evento ID {evento_id} se actualizó a '{estado_texto}'.", "success")
    else:
        flash(f"❌ Error: {resultado.get('message', 'No se pudo actualizar el estado.')}", "error")

    return redirect(url_for('admin'))

# --- RUTA PARA DIFUSIÓN Y PLANTILLA DE INVITACIÓN ---
# --- RUTA CORREGIDA PARA DIFUSIÓN ---
@app.route('/evento/difundir/<int:evento_id>')
def difundir_evento(evento_id):
    if not session.get('usuario_id'):
        flash('Debe iniciar sesión para acceder a esta función.', 'error')
        return redirect(url_for('login'))

    conexion = obtener_conexion()
    try:
        with conexion.cursor(pymysql.cursors.DictCursor) as cursor:
            # Consulta limpia sin escapes conflictivos de %
            cursor.execute("""
                SELECT e.*, 
                       esp.nombre AS espacio_nombre
                FROM eventos e
                LEFT JOIN espacios esp ON e.espacio_id = esp.id
                WHERE e.id = %s
            """, (evento_id,))
            evento = cursor.fetchone()

        if not evento:
            flash('El evento solicitado no existe.', 'error')
            return redirect(url_for('inicio'))

        # Formatear horas y fechas de forma segura en Python por si vienen como objetos timedelta/date
        if evento.get('hora_inicio'):
            evento['inicio_formateado'] = str(evento['hora_inicio'])[:5]
        else:
            evento['inicio_formateado'] = '--:--'

        if evento.get('hora_fin'):
            evento['fin_formateado'] = str(evento['hora_fin'])[:5]
        else:
            evento['fin_formateado'] = '--:--'

        if evento.get('fecha'):
            evento['fecha_formateada'] = str(evento['fecha'])
        else:
            evento['fecha_formateada'] = 'Sin fecha'

        return render_template('difusion_ficha.html', evento=evento)

    except Exception as e:
        # Esto te mostrará el error exacto en la terminal de VS Code / consola de Flask
        print(f"❌ ERROR EXACTO EN DIFUSIÓN: {e}")
        flash('Error al generar la plantilla de difusión.', 'error')
        return redirect(url_for('inicio'))
    finally:
        if conexion:
            conexion.close()


# --- RUTA 9: PROPUESTAS DE ESTUDIANTES ---
@app.route('/proponer', methods=['GET', 'POST'])
@requerir_rol(['estudiante'])
def proponer():
    if request.method == 'POST':
        titulo = request.form.get('titulo')
        tipo_actividad = request.form.get('tipo_actividad')
        descripcion = request.form.get('descripcion')

        # Validar que los campos obligatorios no vengan vacíos
        if not all([titulo, tipo_actividad, descripcion]):
            flash("❌ Por favor complete todos los campos requeridos.", "error")
            return redirect(url_for('proponer'))
        
        if validar_evento_duplicado(titulo):
            flash(f"❌ La idea '{titulo}' ya se encuentra registrada en el buzón.", "error")
            return redirect(url_for('proponer'))
        
        # Llamar al repositorio para guardar la propuesta
        exito = evento_repo.crear_propuesta_estudiante(
            estudiante_id=session['usuario_id'],
            titulo=titulo,
            tipo_actividad=tipo_actividad,
            descripcion=descripcion
        )

        if exito:
            flash("💡 ¡Tu propuesta ha sido enviada al equipo administrativo para su evaluación!", "success")
            return redirect(url_for('mis_propuestas'))
        else:
            flash("❌ Ocurrió un error al guardar tu propuesta.", "error")
            return redirect(url_for('proponer'))
    return render_template('proponer.html')


# --- RUTA 10: MIS PROPUESTAS (ESTUDIANTES) ---
@app.route('/mis_propuestas')
@requerir_rol(['estudiante'])
def mis_propuestas():
    mis_propuestas = evento_repo.obtener_mis_propuestas_estudiante(session['usuario_id'])
    return render_template('mis_propuestas.html', mis_propuestas=mis_propuestas)


# --- RUTA 11: HISTORIAL DE SOLICITUDES (PONENTES / RESPONSABLES) ---
@app.route('/mis_solicitudes')  # O '/mis-solicitudes' según cómo la tengas en tus enlaces
@requerir_rol(['ponente', 'administrativo'])
def mis_solicitudes():
    usuario_id = session.get('usuario_id')
    
    # Obtener las solicitudes creadas por este usuario desde el repositorio
    solicitudes = evento_repo.obtener_mis_solicitudes(usuario_id)
    
    return render_template('mis_solicitudes.html', solicitudes=solicitudes)


# --- RUTA 12: ELIMINAR ESPACIOS Y EVENTOS (ADMIN) ---
@app.route('/admin/espacios/eliminar/<int:id>', methods=['POST'])
@requerir_rol(['administrativo'])
def eliminar_espacio(id):
    try:
        conexion = obtener_conexion()
        with conexion.cursor() as cursor:
            cursor.execute("DELETE FROM espacios WHERE id = %s", (id,))
        conexion.commit()
        conexion.close()
        flash('🗑️ Espacio eliminado correctamente.', 'success')
    except Exception as e:
        flash(f'❌ No se pudo eliminar el espacio (puede tener eventos asignados): {str(e)}', 'error')

    return redirect('/admin/espacios')


@app.route('/admin/eliminar-evento/<int:evento_id>', methods=['POST'])
@requerir_rol(['administrativo'])
def admin_eliminar_evento(evento_id):
    if evento_repo.eliminar_evento(evento_id):
        flash("🗑️ El evento ha sido eliminado permanentemente.", "success")
    else:
        flash("❌ No se pudo eliminar el evento.", "error")
    return redirect(url_for('admin'))


# --- RUTA 13: EDITAR EVENTO (COMPLETO) ---
@app.route('/admin/editar-evento/<int:evento_id>', methods=['GET', 'POST'])
@requerir_rol(['administrativo'])
def admin_editar_evento(evento_id):
    if request.method == 'POST':
        titulo = request.form.get('titulo')
        tipo_actividad = request.form.get('tipo_actividad')
        espacio_id = request.form.get('espacio_id')
        fecha = request.form.get('fecha')
        hora_inicio = request.form.get('hora_inicio')
        hora_fin = request.form.get('hora_fin')
        
        resultado = evento_repo.actualizar_evento_completo(
            evento_id, titulo, tipo_actividad, espacio_id, fecha, hora_inicio, hora_fin
        )
        
        if resultado.get('exito'):
            flash("✏️ " + resultado['mensaje'], "success")
            return redirect(url_for('admin'))
        else:
            flash(resultado['mensaje'], "error")

    evento = evento_repo.obtener_evento_por_id(evento_id)
    espacios = evento_repo.obtener_lista_espacios_formulario()
    if not evento:
        flash("El evento no existe.", "error")
        return redirect(url_for('admin'))

    return render_template('editar_evento.html', evento=evento, espacios=espacios)


# --- RUTA 14: ADMINISTRAR ESPACIOS ---
@app.route('/admin/espacios/nuevo', methods=['POST'])
@requerir_rol(['administrativo'])
def registrar_espacio():
    nombre = request.form.get('nombre')
    capacidad = request.form.get('capacidad')
    descripcion = request.form.get('descripcion')

    try:
        conexion = obtener_conexion()
        with conexion.cursor() as cursor:
            sql = "INSERT INTO espacios (nombre, capacidad, descripcion) VALUES (%s, %s, %s)"
            cursor.execute(sql, (nombre, capacidad, descripcion))
        conexion.commit()
        conexion.close()
        flash('✅ Espacio registrado exitosamente.', 'success')
    except Exception as e:
        flash(f'❌ Ocurrió un error al guardar el espacio: {str(e)}', 'error')

    return redirect('/admin/espacios')


@app.route('/admin/espacios')
@requerir_rol(['administrativo'])
def administrar_espacios():
    try:
        conexion = obtener_conexion()
        with conexion.cursor() as cursor:
            cursor.execute("SELECT id, nombre, capacidad, descripcion FROM espacios")
            lista_espacios = cursor.fetchall()
        conexion.close()
    except Exception:
        lista_espacios = []

    return render_template('admin_espacios.html', espacios=lista_espacios)


# --- RUTA 15: INSCRIPCIÓN DE ESTUDIANTES ---
@app.route('/inscribir-evento/<int:evento_id>', methods=['POST'])
def inscribir_evento(evento_id):
    if 'usuario_id' not in session:
        flash("Debe iniciar sesión para inscribirse a los eventos.", "warning")
        return redirect(url_for('login'))

    usuario_id = session['usuario_id']

    # Llamada limpia usando únicamente usuario_id
    resultado = registrar_inscripcion_segura(evento_id, usuario_id)

    status = resultado.get('status', 'error')
    mensaje = str(resultado.get('message', 'Ocurrió un error inesperado.'))

    if status == 'success':
        flash(mensaje, "success")
    elif status == 'warning':
        flash(mensaje, "warning")
    else:
        flash(f"❌ {mensaje}", "error")

    return redirect(request.referrer or url_for('inicio'))

"""@app.route('/inscribir-evento/<int:evento_id>', methods=['POST'])
def inscribir_evento(evento_id):
    if 'usuario_id' not in session:
        flash("Debe iniciar sesión para inscribirse a los eventos.", "warning")
        return redirect(url_for('login'))

    usuario_id = session['usuario_id']
    exito, mensaje = evento_repo.inscribir_usuario_evento(usuario_id, evento_id)

    if exito:
        flash(f"✅ {mensaje}", "success")
    else:
        flash(f"⚠️ {mensaje}", "error")

    return redirect(request.referrer or url_for('dashboard'))
"""
# -------------------------------------------------------------
# 👨‍🏫 VISTA PROFESOR: Ver sus eventos y la lista de inscritos
# -------------------------------------------------------------
@app.route('/profesor/eventos')
def mis_eventos_profesor():
    if session.get('usuario_rol') not in ['profesor', 'administrativo', 'admin', 'Administrativo', 'ponente']:
        flash("Acceso restringido.", "error")
        return redirect(url_for('inicio'))

    profesor_id = session['usuario_id']
    mis_eventos = evento_repo.obtener_eventos_por_profesor(profesor_id)
    
    return render_template('profesor_eventos.html', eventos=mis_eventos)

# -------------------------------------------------------------
# 📋 VISTA DETALLE DE INSCRITOS (Profesor y Admin)
# -------------------------------------------------------------
@app.route('/evento/<int:evento_id>/inscritos')
def ver_inscritos_evento(evento_id):
    # 1. Validar sesión
    if 'usuario_id' not in session:
        flash("Debes iniciar sesión para acceder.", "warning")
        return redirect('/login')

    # 2. Validar rol (Soporta 'admin', 'administrativo', 'profesor' y 'ponente')
    # Se añade fallback por si el rol se almacenó como 'usuario_rol' o 'rol'
    rol_bruto = session.get('usuario_rol') or session.get('rol') or ''
    rol_actual = str(rol_bruto).lower()
    
    if rol_actual not in ['admin', 'administrativo', 'profesor', 'ponente']:
        flash("No tienes permisos para ver esta lista.", "error")
        return redirect('/')

    # 3. Obtener datos del evento y sus inscritos desde el Repositorio
    evento = evento_repo.obtener_evento_por_id(evento_id)
    if not evento:
        flash("El evento solicitado no existe.", "error")
        return redirect('/')

    inscritos = evento_repo.obtener_inscritos_por_evento(evento_id) or []
    
    # 4. Cargar lista de usuarios no inscritos para la selección del admin
    todos_usuarios = []
    if rol_actual in ['admin', 'administrativo', 'profesor']:
        usuarios_totales = evento_repo.obtener_todos_los_usuarios() or []
        
        # Extraer IDs de usuarios ya inscritos para no mostrarlos repetidos en el select
        ids_inscritos = [i.get('usuario_id') or i.get('id') for i in inscritos]
        
        # Filtrar solo a los usuarios disponibles
        todos_usuarios = [u for u in usuarios_totales if u.get('id') not in ids_inscritos]

    # Renderiza directamente tu archivo ver_inscritos.html
    return render_template('ver_inscritos.html', 
                           evento=evento, 
                           inscritos=inscritos, 
                           usuarios=todos_usuarios)


# -------------------------------------------------------------
# ➕ INSCRIPCIÓN MANUAL POR PARTE DEL ADMINISTRADOR
# -------------------------------------------------------------
@app.route('/admin/inscribir_manual/<int:evento_id>', methods=['POST'])
def admin_inscribir_manual(evento_id):
    rol_bruto = session.get('usuario_rol') or session.get('rol') or ''
    rol_actual = str(rol_bruto).lower()
    
    if rol_actual not in ['admin', 'administrativo', 'profesor']:
        flash("Solo los administradores y personal autorizado pueden realizar inscripciones manuales.", "error")
        return redirect('/')

    usuario_id = request.form.get('usuario_id')
    if not usuario_id:
        flash("Debes seleccionar un usuario válido.", "warning")
        return redirect(url_for('ver_inscritos_evento', evento_id=evento_id))

    # Intento de inscripción a través de tu repositorio
    exito, mensaje = evento_repo.inscribir_usuario_evento(usuario_id, evento_id)

    if exito:
        flash("✅ Usuario inscrito manualmente con éxito.", "success")
    else:
        flash(f"⚠️ {mensaje}", "error")

    # Corrección aquí: Se llama a 'ver_inscritos_evento' (en singular)
    return redirect(url_for('ver_inscritos_evento', evento_id=evento_id))

# -------------------------------------------------------------
# 🎓 VISTA EXCLUSIVA DE INSCRITOS PARA PONENTES / PROFESORES
# -------------------------------------------------------------
@app.route('/ponente/evento/<int:evento_id>/inscritos')
def ponente_ver_inscritos(evento_id):
    # 1. Validar sesión de usuario
    if 'usuario_id' not in session:
        flash("Debes iniciar sesión para acceder.", "warning")
        return redirect(url_for('login'))

    # 2. Validar que tenga un rol autorizado (ponente, profesor, administrativo o admin)
    rol_actual = str(session.get('usuario_rol') or session.get('rol') or '').lower()
    if rol_actual not in ['ponente', 'profesor', 'administrativo', 'admin']:
        flash("Acceso denegado: Esta vista es solo para ponentes y profesores.", "error")
        return redirect(url_for('inicio'))

    # 3. Obtener el evento
    evento = evento_repo.obtener_evento_por_id(evento_id)
    if not evento:
        flash("El evento solicitado no existe.", "error")
        return redirect(url_for('mis_solicitudes'))

    # 4. Obtener la lista de alumnos/participantes inscritos
    inscritos = evento_repo.obtener_inscritos_por_evento(evento_id) or []

    return render_template(
        'ponente_inscritos.html', 
        evento=evento, 
        inscritos=inscritos,
        total_inscritos=len(inscritos)
    )



# --- RUTA 16: CERRAR SESIÓN ---
@app.route('/logout')
def logout():
    session.clear()
    flash("Has cerrado sesión de forma segura.", "success")
    return redirect(url_for('inicio'))


if __name__ == '__main__':
    app.run(debug=True)