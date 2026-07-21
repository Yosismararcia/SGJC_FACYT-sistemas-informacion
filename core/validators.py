# core/validators.py
from database import obtener_conexion
from core.security import clean_input_strict

def validar_cedula_institucional(cedula, rol):
    """
    Valida si el personal (ponente/administrativo) está en la nómina autorizada de la FaCyT.
    """
    cedula_limpia = clean_input_strict(cedula)
    conexion = obtener_conexion()
    try:
        with conexion.cursor() as cursor:
            cursor.execute(
                "SELECT * FROM personal_autorizado WHERE cedula = %s AND rol_permitido = %s;", 
                (cedula_limpia, rol)
            )
            return cursor.fetchone() is not None
    finally:
        conexion.close()

def validar_evento_duplicado(titulo):
    """
    Caso de borde: Evita eventos duplicados con el mismo nombre en el sistema.
    """
    titulo_limpio = clean_input_strict(titulo)
    conexion = obtener_conexion()
    try:
        with conexion.cursor() as cursor:
            # Busca si ya existe un evento activo con ese nombre exacto
            cursor.execute(
                "SELECT id FROM eventos WHERE titulo = %s AND estado NOT IN ('cancelado', 'rechazado');", 
                (titulo_limpio,)
            )
            return cursor.fetchone() is not None
    finally:
        conexion.close()