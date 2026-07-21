# core/broadcaster.py

def generar_ficha_difusion(evento):
    """
    Genera un bloque formateado en Markdown limpio para la divulgación inmediata
    de eventos aprobados hacia la comunidad estudiantil y profesoral.
    """
    plantilla = (
        "📢 *NUEVO EVENTO CIENTÍFICO EN FaCyT* 🔬\n\n"
        "🎓 *Actividad:* {titulo}\n"
        "📌 *Tipo:* {tipo}\n"
        "📆 *Fecha:* {fecha}\n"
        "⏰ *Horario:* {hora_inicio} - {hora_fin}\n"
        "🏫 *Lugar:* {espacio}\n"
        "👤 *Responsable:* {responsable}\n\n"
        "¡Asiste y expande tus conocimientos! _Plataforma SGC-FaCyT 2026_"
    )
    
    return plantilla.format(
        titulo=evento.get('titulo', 'Sin título').upper(),
        tipo=evento.get('tipo_actividad', 'Conferencia'),
        fecha=evento.get('fecha', ''),
        hora_inicio=evento.get('hora_inicio', ''),
        hora_fin=evento.get('hora_fin', ''),
        espacio=evento.get('espacio', 'Por asignar'),
        responsable=evento.get('responsable', 'Cuerpo Académico')
    )