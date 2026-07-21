import pymysql
from database import obtener_conexion
from core.security import clean_input_strict

def registrar_inscripcion_segura(evento_id, usuario_id):
    """
    Registra a un usuario manejando bloqueo concurrente (FOR UPDATE)
    y control transaccional estricto mediante usuario_id.
    """
    conexion = obtener_conexion()
    
    try:
        # Inicio explícito de la transacción
        conexion.begin()
        
        with conexion.cursor(pymysql.cursors.DictCursor) as cursor:
            
            # 1. BLOQUEO PESIMISTA: Obtiene la capacidad del espacio
            sql_evento = """
                SELECT e.id, esp.capacidad 
                FROM eventos e
                INNER JOIN espacios esp ON e.espacio_id = esp.id
                WHERE e.id = %s FOR UPDATE;
            """
            cursor.execute(sql_evento, (evento_id,))
            evento = cursor.fetchone()
            
            if not evento:
                conexion.rollback()
                return {"status": "error", "message": "El evento seleccionado no existe."}
                
            # 2. Contar inscritos en este microsegundo (dentro del bloqueo)
            cursor.execute("SELECT COUNT(*) as actuales FROM inscripciones WHERE evento_id = %s;", (evento_id,))
            res_conteo = cursor.fetchone()
            total_inscritos = res_conteo['actuales'] if res_conteo else 0
            
            capacidad_maxima = evento.get('capacidad', 0)
            
            if total_inscritos >= capacidad_maxima:
                conexion.rollback()
                return {"status": "error", "message": "Los cupos para este evento se acaban de agotar."}
                
            # 3. Validar duplicados usando usuario_id (CORREGIDO)
            cursor.execute(
                "SELECT id FROM inscripciones WHERE evento_id = %s AND usuario_id = %s;", 
                (evento_id, usuario_id)
            )
            if cursor.fetchone():
                conexion.rollback()
                return {"status": "warning", "message": "Ya te encuentras registrado en este evento."}
                
            # 4. Insertar inscripción usando usuario_id (CORREGIDO)
            sql_insert = """
                INSERT INTO inscripciones (evento_id, usuario_id)
                VALUES (%s, %s);
            """
            cursor.execute(sql_insert, (evento_id, usuario_id))
            
        # 5. Confirmar transacción
        conexion.commit()
        return {"status": "success", "message": "🎉 ¡Inscripción realizada con éxito! Tu cupo ha sido reservado."}
        
    except Exception as e:
        conexion.rollback()
        return {"status": "error", "message": f"Falla en base de datos: {str(e)}"}
    finally:
        conexion.close()