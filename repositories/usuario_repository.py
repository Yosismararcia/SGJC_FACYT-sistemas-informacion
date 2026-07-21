# repositories/usuario_repository.py
import pymysql
from database import obtener_conexion
from core.security import clean_input_strict

def obtener_usuario_por_correo(correo):
    """Busca un usuario por su correo electrónico institucional."""
    conexion = obtener_conexion()
    try:
        with conexion.cursor() as cursor:
            cursor.execute("SELECT * FROM usuarios WHERE correo = %s;", (correo,))
            return cursor.fetchone()
    finally:
        conexion.close()

def obtener_usuario_por_cedula_y_correo(cedula, correo):
    """Busca coincidencia exacta para el proceso de recuperación de acceso."""
    cedula_limpia = clean_input_strict(cedula)
    conexion = obtener_conexion()
    try:
        with conexion.cursor() as cursor:
            cursor.execute(
                "SELECT * FROM usuarios WHERE cedula = %s AND correo = %s;",
                (cedula_limpia, correo)
            )
            return cursor.fetchone()
    finally:
        conexion.close()

def crear_usuario(nombre, cedula, correo, password_hashed, rol):
    """Registra un nuevo usuario en el sistema."""
    nombre_limpio = clean_input_strict(nombre)
    cedula_limpia = clean_input_strict(cedula)
    
    conexion = obtener_conexion()
    try:
        with conexion.cursor() as cursor:
            cursor.execute("""
                INSERT INTO usuarios (nombre, cedula, correo, contrasena_hash, rol)
                VALUES (%s, %s, %s, %s, %s);
            """, (nombre_limpio, cedula_limpia, correo, password_hashed, rol))
        conexion.commit()
        return True
    except pymysql.MySQLError:
        return False
    finally:
        conexion.close()

def actualizar_contrasena_por_id(usuario_id, nueva_password_hashed):
    """Modifica de forma segura el hash de la contraseña de un usuario."""
    conexion = obtener_conexion()
    try:
        with conexion.cursor() as cursor:
            cursor.execute(
                "UPDATE usuarios SET contrasena_hash = %s WHERE id = %s;",
                (nueva_password_hashed, usuario_id)
            )
        conexion.commit()
        return True
    except pymysql.MySQLError:
        return False
    finally:
        conexion.close()