import pymysql
from database import obtener_conexion
from core.security import clean_input_strict, clean_html_entities


# --- MÉTRICAS DEL DASHBOARD Y PANEL ADMIN ---
def obtener_metricas_dashboard():
    conexion = obtener_conexion()
    metrics = {'totales': 0, 'pendientes': 0, 'aprobados': 0, 'propuestas': 0}
    try:
        with conexion.cursor() as cursor:
            # 1. Total de eventos en la tabla principal
            cursor.execute("SELECT COUNT(*) AS total FROM eventos")
            res_totales = cursor.fetchone()
            metrics['totales'] = res_totales['total'] if (res_totales and 'total' in res_totales) else 0

            # 2. Eventos en revisión / pendientes
            cursor.execute("""
                SELECT COUNT(*) AS pendientes 
                FROM eventos 
                WHERE LOWER(estado) IN ('revision', 'pendiente', 'solicitado', 'en revision')
            """)
            res_pendientes = cursor.fetchone()
            metrics['pendientes'] = res_pendientes['pendientes'] if (res_pendientes and 'pendientes' in res_pendientes) else 0

            # 3. Eventos aprobados
            cursor.execute("""
                SELECT COUNT(*) AS aprobados 
                FROM eventos 
                WHERE LOWER(estado) IN ('aprobado', 'aprobada', 'confirmado')
            """)
            res_aprobados = cursor.fetchone()
            metrics['aprobados'] = res_aprobados['aprobados'] if (res_aprobados and 'aprobados' in res_aprobados) else 0

            # 4. Total de Ideas / Propuestas de estudiantes (Cuenta TODAS las propuestas en la tabla)
            cursor.execute("SELECT COUNT(*) AS propuestas FROM propuestas_estudiantes")
            res_propuestas = cursor.fetchone()
            metrics['propuestas'] = res_propuestas['propuestas'] if (res_propuestas and 'propuestas' in res_propuestas) else 0

    except Exception as e:
        print(f"⚠️ Error al obtener métricas del dashboard: {e}")
    finally:
        conexion.close()
        
    return metrics


def obtener_proximos_eventos(limite=5):
    """Retorna los próximos eventos para el panel público/dashboard."""
    conexion = obtener_conexion()
    try:
        with conexion.cursor() as cursor:
            cursor.execute("""
                SELECT e.id, e.titulo, e.tipo_actividad, e.fecha, e.hora_inicio, e.hora_fin, 
                       esp.nombre AS espacio, u.nombre AS responsable
                FROM eventos e
                LEFT JOIN espacios esp ON e.espacio_id = esp.id
                LEFT JOIN usuarios u ON e.responsable_id = u.id
                WHERE e.estado IN ('aprobado', 'programado')
                ORDER BY e.fecha ASC LIMIT %s;
            """, (limite,))
            return cursor.fetchall()
    finally:
        conexion.close()


#------------------NUEVA MODIFICACION
def obtener_eventos_cartelera_publica(usuario_id=None):
    """
    Retorna los eventos aprobados para la cartelera pública con:
    - Nombre del espacio.
    - Total de estudiantes inscritos y capacidad máxima.
    - Enlace virtual.
    - Estado de inscripción del usuario actual (si inició sesión).
    """
    conexion = obtener_conexion()
    try:
        with conexion.cursor() as cursor:
            # Usamos %s para el LEFT JOIN de inscripción del usuario activo
            cursor.execute("""
                SELECT 
                    e.id, 
                    e.titulo, 
                    e.departamento,
                    e.tipo_actividad, 
                    e.fecha, 
                    e.hora_inicio, 
                    e.hora_fin, 
                    e.enlace_virtual,
                    esp.nombre AS espacio, 
                    esp.capacidad AS capacidad_maxima, 
                    u.nombre AS responsable,
                    -- Cuenta el total de inscritos en este evento
                    (SELECT COUNT(*) FROM inscripciones i WHERE i.evento_id = e.id) AS total_inscritos,
                    -- Retorna > 0 si el usuario que está viendo la página ya está inscrito
                    (SELECT COUNT(*) FROM inscripciones i WHERE i.evento_id = e.id AND i.usuario_id = %s) AS esta_inscrito
                FROM eventos e
                LEFT JOIN espacios esp ON e.espacio_id = esp.id
                LEFT JOIN usuarios u ON e.responsable_id = u.id
                WHERE e.estado IN ('aprobado', 'programado')
                ORDER BY e.fecha ASC;
            """, (usuario_id,))
            
            return cursor.fetchall()
    finally:
        conexion.close()
#---------------------------------------------

#def obtener_eventos_cartelera_publica():
#    """Retorna los eventos aprobados para la cartelera de inscripciones públicas."""
 #   conexion = obtener_conexion()
  #  try:
   #     with conexion.cursor() as cursor:
    #        cursor.execute("""
            #    SELECT e.id, e.titulo, e.tipo_actividad, e.fecha, e.hora_inicio, e.hora_fin, 
     #                  esp.nombre AS espacio, esp.capacidad, u.nombre AS responsable
    #            FROM eventos e
      #          LEFT JOIN espacios esp ON e.espacio_id = esp.id
       #         LEFT JOIN usuarios u ON e.responsable_id = u.id
        #        WHERE e.estado IN ('aprobado', 'programado')
         #       ORDER BY e.fecha ASC;
          #  """)
           # return cursor.fetchall()
    #finally:
     #   conexion.close()


def verificar_conflicto_horario(espacio_id, fecha, hora_inicio, hora_fin, evento_id_excluir=None):
    """
    Verifica si existe un traslape de horario en el mismo espacio y fecha.
    Formula: (NuevaInicio < ExistenteFin) AND (NuevaFin > ExistenteInicio)
    """
    conexion = obtener_conexion()
    try:
        with conexion.cursor() as cursor:
            sql = """
                SELECT id, titulo FROM eventos 
                WHERE espacio_id = %s 
                  AND fecha = %s 
                  AND estado NOT IN ('cancelado', 'rechazado')
                  AND (%s < hora_fin AND %s > hora_inicio)
            """
            params = [espacio_id, fecha, hora_inicio, hora_fin]
            
            if evento_id_excluir:
                sql += " AND id != %s"
                params.append(evento_id_excluir)
                
            cursor.execute(sql, tuple(params))
            return cursor.fetchone()
    finally:
        conexion.close()


def crear_solicitud_evento(titulo, responsable_id, tipo_actividad, espacio_id, fecha, hora_inicio, hora_fin, departamento, enlace_virtual=""):
    """Inserta una solicitud formal de evento en espera de aprobación incluyendo departamento y enlace virtual opcional."""
    
    # 1. Validación anti-colisión previa en Python
    conflicto = verificar_conflicto_horario(espacio_id, fecha, hora_inicio, hora_fin)
    if conflicto:
        return {
            "exito": False, 
            "mensaje": f"⚠️ El espacio ya está reservado en ese horario por '{conflicto['titulo']}'."
        }

    # 2. Limpieza estricta de datos de texto
    titulo_limpio = clean_input_strict(titulo)
    departamento_limpio = clean_input_strict(departamento)
    
    conexion = obtener_conexion()
    try:
        with conexion.cursor() as cursor:
            # 3. Consulta SQL con los nuevos campos de la FaCyT
            cursor.execute("""
                INSERT INTO eventos (titulo, departamento, tipo_actividad, fecha, hora_inicio, hora_fin, estado, espacio_id, enlace_virtual, responsable_id)
                VALUES (%s, %s, %s, %s, %s, %s, 'pendiente', %s, %s, %s);
            """, (
                titulo_limpio, 
                departamento_limpio, 
                tipo_actividad, 
                fecha, 
                hora_inicio, 
                hora_fin, 
                espacio_id, 
                enlace_virtual, 
                responsable_id
            ))
        conexion.commit()
        return {"exito": True, "mensaje": "Solicitud creada exitosamente."}
        
    except pymysql.MySQLError as e:
        if e.args[0] == 45000:
            return {"exito": False, "mensaje": e.args[1]}
        return {"exito": False, "mensaje": f"Error de base de datos: {e}"}
        
    finally:
        conexion.close()


def obtener_solicitudes_totales_admin():
    """Retorna todas las solicitudes formales para el panel del administrador."""
    conexion = obtener_conexion()
    try:
        with conexion.cursor() as cursor:
            cursor.execute("""
                SELECT e.id, e.titulo, e.tipo_actividad, e.fecha, e.hora_inicio, e.hora_fin, e.estado, 
                       esp.nombre AS espacio, u.nombre AS solicitado_por
                FROM eventos e
                LEFT JOIN espacios esp ON e.espacio_id = esp.id
                LEFT JOIN usuarios u ON e.responsable_id = u.id
                ORDER BY e.fecha ASC;
            """)
            return cursor.fetchall()
    finally:
        conexion.close()


def actualizar_estado_evento(evento_id, nuevo_estado):
    """Actualiza el estado de un evento y captura traslapes de horario si aplica."""
    conexion = obtener_conexion()
    try:
        with conexion.cursor() as cursor:
            cursor.execute("""
                SELECT e.titulo, u.nombre AS solicitante FROM eventos e
                LEFT JOIN usuarios u ON e.responsable_id = u.id WHERE e.id = %s;
            """, (evento_id,))
            evento = cursor.fetchone()
            
            cursor.execute("UPDATE eventos SET estado = %s WHERE id = %s;", (nuevo_estado, evento_id))
        conexion.commit()
        return {"status": "success", "evento": evento}
    except pymysql.MySQLError as e:
        if e.args[0] == 45000:
            return {"status": "error", "message": f"Conflictivo: {e.args[1]}"}
        return {"status": "error", "message": "Error interno en la base de datos."}
    finally:
        conexion.close()


def eliminar_evento(evento_id):
    """Eliminación permanente de un evento (Solo Administrador)."""
    conexion = obtener_conexion()
    try:
        with conexion.cursor() as cursor:
            cursor.execute("DELETE FROM eventos WHERE id = %s;", (evento_id,))
        conexion.commit()
        return True
    except pymysql.MySQLError:
        return False
    finally:
        conexion.close()


def obtener_evento_por_id(evento_id):
    """Busca un evento específico para edición o detalle."""
    conexion = obtener_conexion()
    try:
        with conexion.cursor() as cursor:
            cursor.execute("""
                SELECT e.id, e.titulo, e.tipo_actividad, e.espacio_id, e.fecha, e.hora_inicio, e.hora_fin, e.estado,
                       esp.nombre AS espacio, u.nombre AS responsable
                FROM eventos e
                LEFT JOIN espacios esp ON e.espacio_id = esp.id
                LEFT JOIN usuarios u ON e.responsable_id = u.id
                WHERE e.id = %s;
            """, (evento_id,))
            return cursor.fetchone()
    finally:
        conexion.close()


def actualizar_evento_basico(evento_id, titulo, tipo_actividad):
    """Modifica sólo título y tipo del evento."""
    titulo_limpio = clean_input_strict(titulo)
    conexion = obtener_conexion()
    try:
        with conexion.cursor() as cursor:
            cursor.execute(
                "UPDATE eventos SET titulo = %s, tipo_actividad = %s WHERE id = %s;",
                (titulo_limpio, tipo_actividad, evento_id)
            )
        conexion.commit()
        return True
    except pymysql.MySQLError:
        return False
    finally:
        conexion.close()


def actualizar_evento_completo(evento_id, titulo, tipo_actividad, espacio_id, fecha, hora_inicio, hora_fin):
    """Actualiza un evento re-validando choques de horario."""
    conflicto = verificar_conflicto_horario(espacio_id, fecha, hora_inicio, hora_fin, evento_id_excluir=evento_id)
    if conflicto:
        return {
            "exito": False, 
            "mensaje": f"⚠️ El espacio ya se encuentra reservado por '{conflicto['titulo']}'."
        }

    conexion = obtener_conexion()
    try:
        with conexion.cursor() as cursor:
            sql = """
                UPDATE eventos 
                SET titulo = %s, tipo_actividad = %s, espacio_id = %s, fecha = %s, hora_inicio = %s, hora_fin = %s 
                WHERE id = %s;
            """
            cursor.execute(sql, (clean_input_strict(titulo), tipo_actividad, espacio_id, fecha, hora_inicio, hora_fin, evento_id))
        conexion.commit()
        return {"exito": True, "mensaje": "Evento actualizado correctamente."}
    except Exception as e:
        return {"exito": False, "mensaje": f"Error al actualizar: {str(e)}"}
    finally:
        conexion.close()


def obtener_mis_solicitudes(responsable_id):
    """Historial específico de solicitudes de un ponente/profesor."""
    conexion = obtener_conexion()
    try:
        with conexion.cursor() as cursor:
            cursor.execute("""
                SELECT e.titulo, e.tipo_actividad, e.fecha, e.hora_inicio, e.hora_fin, e.estado, esp.nombre AS espacio
                FROM eventos e
                LEFT JOIN espacios esp ON e.espacio_id = esp.id
                WHERE e.responsable_id = %s ORDER BY e.fecha DESC;
            """, (responsable_id,))
            return cursor.fetchall()
    finally:
        conexion.close()


# --- SUBMÓDULO: PROPUESTAS DE ESTUDIANTES ---

def crear_propuesta_estudiante(estudiante_id, titulo, tipo_actividad, descripcion):
    """Inserta una idea sugerida por los alumnos."""
    titulo_limpio = clean_input_strict(titulo)
    descripcion_segura = clean_html_entities(descripcion)
    
    conexion = obtener_conexion()
    try:
        with conexion.cursor() as cursor:
            cursor.execute("""
                INSERT INTO propuestas_estudiantes (estudiante_id, titulo, tipo_actividad, descripcion)
                VALUES (%s, %s, %s, %s);
            """, (estudiante_id, titulo_limpio, tipo_actividad, descripcion_segura))
        conexion.commit()
        return True
    except pymysql.MySQLError:
        return False
    finally:
        conexion.close()


def obtener_propuestas_totales_admin():
    """Lista de propuestas estudiantiles para evaluar en el Panel Admin."""
    conexion = obtener_conexion()
    try:
        with conexion.cursor() as cursor:
            cursor.execute("""
                SELECT p.id, p.titulo, p.tipo_actividad, p.descripcion, u.nombre AS estudiante
                FROM propuestas_estudiantes p
                JOIN usuarios u ON p.estudiante_id = u.id ORDER BY p.id DESC;
            """)
            return cursor.fetchall()
    finally:
        conexion.close()


def obtener_mis_propuestas_estudiante(estudiante_id):
    """Historial individual de propuestas de un estudiante."""
    conexion = obtener_conexion()
    try:
        with conexion.cursor() as cursor:
            cursor.execute("""
                SELECT titulo, tipo_actividad, descripcion, fecha_propuesta 
                FROM propuestas_estudiantes WHERE estudiante_id = %s ORDER BY id DESC;
            """, (estudiante_id,))
            return cursor.fetchall()
    finally:
        conexion.close()


# --- SUBMÓDULO: ESTADÍSTICAS AVANZADAS ---

def obtener_top_espacios():
    conexion = obtener_conexion()
    try:
        with conexion.cursor() as cursor:
            cursor.execute("""
                SELECT esp.nombre, COUNT(e.id) as total FROM eventos e
                JOIN espacios esp ON e.espacio_id = esp.id GROUP BY esp.nombre
                ORDER BY total DESC LIMIT 5;
            """)
            return cursor.fetchall()
    finally:
        conexion.close()


def obtener_conteo_estados():
    conexion = obtener_conexion()
    try:
        with conexion.cursor() as cursor:
            cursor.execute("SELECT estado, COUNT(*) as total FROM eventos GROUP BY estado;")
            return cursor.fetchall()
    finally:
        conexion.close()


def obtener_lista_espacios_formulario():
    conexion = obtener_conexion()
    try:
        with conexion.cursor() as cursor:
            cursor.execute("SELECT id, nombre, capacidad FROM espacios;")
            return cursor.fetchall()
    finally:
        conexion.close()



        import pymysql

def inscribir_usuario_evento(usuario_id, evento_id):
    """Registra la inscripción de un usuario a un evento si hay cupo y no está duplicado."""
    conexion = obtener_conexion()
    try:
        with conexion.cursor() as cursor:
            # 1. Validar si ya está inscrito
            cursor.execute("""
                SELECT id FROM inscripciones 
                WHERE usuario_id = %s AND evento_id = %s
            """, (usuario_id, evento_id))
            if cursor.fetchone():
                return False, "Ya estás inscrito en este evento."

            # 2. Validar capacidad del espacio
            cursor.execute("""
                SELECT e.id, esp.capacidad, 
                       (SELECT COUNT(*) FROM inscripciones WHERE evento_id = e.id) as total_inscritos
                FROM eventos e
                JOIN espacios esp ON e.espacio_id = esp.id
                WHERE e.id = %s
            """, (evento_id,))
            
            info = cursor.fetchone()
            if info and info['capacidad'] and info['total_inscritos'] >= info['capacidad']:
                return False, "Lo sentimos, el evento ha alcanzado la capacidad máxima de su espacio."

            # 3. Guardar la inscripción
            cursor.execute("""
                INSERT INTO inscripciones (usuario_id, evento_id) 
                VALUES (%s, %s)
            """, (usuario_id, evento_id))
            conexion.commit()
            return True, "¡Inscripción realizada con éxito!"

    except Exception as e:
        print(f"❌ Error al inscribir usuario: {e}")
        return False, "Ocurrió un error al procesar tu inscripción."
    finally:
        conexion.close()

def obtener_eventos_por_usuario(usuario_id):
    """Retorna la lista de eventos a los que se ha inscrito un usuario."""
    conexion = obtener_conexion()
    try:
        with conexion.cursor() as cursor:
            cursor.execute("""
                SELECT e.*, esp.nombre as espacio_nombre, i.fecha_inscripcion 
                FROM inscripciones i
                JOIN eventos e ON i.evento_id = e.id
                JOIN espacios esp ON e.espacio_id = esp.id
                WHERE i.usuario_id = %s
                ORDER BY e.fecha DESC
            """, (usuario_id,))
            return cursor.fetchall()
    finally:
        conexion.close()

def obtener_inscritos_por_evento(evento_id):
    """Devuelve la lista de usuarios inscritos en un evento específico."""
    conexion = obtener_conexion()
    try:
        with conexion.cursor() as cursor:
            cursor.execute("""
                SELECT u.id, u.nombre, u.cedula, u.correo, u.rol, i.fecha_inscripcion
                FROM inscripciones i
                JOIN usuarios u ON i.usuario_id = u.id
                WHERE i.evento_id = %s
                ORDER BY i.fecha_inscripcion ASC
            """, (evento_id,))
            return cursor.fetchall()
    finally:
        conexion.close()

def obtener_eventos_por_profesor(profesor_id):
    """Obtiene los eventos gestionados o creados por un profesor específico."""
    conexion = obtener_conexion()
    try:
        with conexion.cursor() as cursor:
            cursor.execute("""
                SELECT e.*, esp.nombre as espacio_nombre,
                       (SELECT COUNT(*) FROM inscripciones WHERE evento_id = e.id) as total_inscritos
                FROM eventos e
                JOIN espacios esp ON e.espacio_id = esp.id
                WHERE e.usuario_id = %s OR e.responsable_id = %s
                ORDER BY e.fecha DESC
            """, (profesor_id, profesor_id))
            return cursor.fetchall()
    finally:
        conexion.close()

def obtener_todos_los_usuarios():
    """Obtiene la lista de todos los usuarios registrados para el selector del administrador."""
    conexion = obtener_conexion()
    try:
        with conexion.cursor() as cursor:
            cursor.execute("SELECT id, nombre, cedula, correo, rol FROM usuarios ORDER BY nombre ASC")
            return cursor.fetchall()
    finally:
        conexion.close()        