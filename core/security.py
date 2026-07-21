# core/security.py
import re
import html
from functools import wraps
from flask import session, flash, redirect, url_for
from werkzeug.security import generate_password_hash, check_password_hash
from itsdangerous import URLSafeTimedSerializer

# Serializador para tokens criptográficos (Recuperación de contraseña)
def obtener_serializer(secret_key):
    return URLSafeTimedSerializer(secret_key)

def hash_password(password):
    """Crea un hash seguro de la contraseña."""
    return generate_password_hash(password)

def verificar_password(password_hash, password):
    """Verifica si la contraseña coincide con el hash almacenado."""
    return check_password_hash(password_hash, password)

def clean_input_strict(texto):
    """
    Caso de Borde: Bloquea y remueve símbolos peligrosos de inputs estrictos 
    como Cédulas, Nombres o Títulos (Evita XSS e Inyecciones SQL lógicas).
    SÓLO permite caracteres alfanuméricos, espacios, guiones y acentos.
    """
    if not texto:
        return ""
    # Remueve todo lo que no sea letras, números, espacios, guiones o letras con acentos
    limpio = re.sub(r'[^\w\s\-\u00C0-\u017F]', '', str(texto))
    return limpio.strip()

def clean_html_entities(texto):
    """
    Caso de Borde: Para campos largos como 'Justificaciones' o 'Descripciones'.
    Permite símbolos pero los transforma en texto plano inofensivo (escapa HTML).
    """
    if not texto:
        return ""
    return html.escape(str(texto).strip())

# --- DECORADOR DE CONTROL DE ACCESO BASADO EN ROLES (RBAC) ---
def requerir_rol(roles_permitidos):
    """
    Middleware corporativo para evitar la escalación de privilegios.
    Evita que estudiantes o profesores accedan a funciones privilegiadas de admin.
    """
    def decorador(f):
        @wraps(f)
        def funcion_decorada(*args, **kwargs):
            # 1. Verificar inicio de sesión activo
            if 'usuario_id' not in session:
                flash("🔒 Por favor, inicia sesión para acceder a esta sección.", "error")
                return redirect(url_for('login'))
            
            # 2. Verificar rol autorizado
            rol_actual = session.get('usuario_rol') or session.get('rol')
            if not rol_actual or rol_actual not in roles_permitidos:
                # Caso de borde: Intento de violación de seguridad -> Destrucción de sesión por prevención
                session.clear()
                flash("🛑 Acceso denegado. Intento de violación de privilegios detectado. Sesión cerrada.", "error")
                return redirect(url_for('login'))
            return f(*args, **kwargs)
        return funcion_decorada
    return decorador