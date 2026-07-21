import os
import pymysql
import pymysql.cursors

def obtener_conexion():
    # 1. Aseguramos valores por defecto si no existen en el .env (evita el error de None)
    host = os.getenv('DB_HOST', 'localhost')
    user = os.getenv('DB_USER', 'root')
    password = os.getenv('DB_PASSWORD', '')
    database = os.getenv('DB_NAME', '')
    port = int(os.getenv('DB_PORT', 3306))

    # 2. Configuración de SSL
    ssl_config = None
    if os.path.exists('ca.pem'):
        ssl_config = {'ca': 'ca.pem', 'check_hostname': False}

    # 3. Retornar conexión limpia
    return pymysql.connect(
        host=host,
        user=user,
        password=password,
        port=port,
        database=database,
        cursorclass=pymysql.cursors.DictCursor,
        ssl=ssl_config
    )