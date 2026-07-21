-- =====================================================================
-- 1. CREACIÓN DE TABLAS BASE E INFRAESTRUCTURA
-- =====================================================================

-- Tabla: Espacios Físicos de la FaCyT
CREATE TABLE IF NOT EXISTS espacios (
    id INT AUTO_INCREMENT PRIMARY KEY,
    nombre VARCHAR(100) UNIQUE NOT NULL,
    capacidad INT NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Tabla: Nómina del Personal Autorizado (Seguridad Institucional)
-- Controla quiénes pueden registrarse como ponentes o administradores
CREATE TABLE IF NOT EXISTS personal_autorizado (
    cedula VARCHAR(20) PRIMARY KEY,
    rol_permitido ENUM('ponente', 'administrativo', 'profesor') NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Tabla: Registro Único de Usuarios
CREATE TABLE IF NOT EXISTS usuarios (
    id INT AUTO_INCREMENT PRIMARY KEY,
    nombre VARCHAR(150) NOT NULL,
    cedula VARCHAR(20) UNIQUE NOT NULL,
    correo VARCHAR(150) UNIQUE NOT NULL,
    contrasena_hash VARCHAR(255) NOT NULL,
    rol ENUM('estudiante', 'ponente', 'administrativo', 'profesor') NOT NULL,
    creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- =====================================================================
-- 2. GESTIÓN DE SOLICITUDES Y PROPUESTAS ACADÉMICAS
-- =====================================================================

-- Tabla: Solicitudes de Eventos Científicos y Académicos
CREATE TABLE IF NOT EXISTS eventos (
    id INT AUTO_INCREMENT PRIMARY KEY,
    titulo VARCHAR(200) NOT NULL,
    responsable_id INT NOT NULL,
    tipo_actividad VARCHAR(100) NOT NULL,
    fecha DATE NOT NULL,
    hora_inicio TIME NOT NULL,
    hora_fin TIME NOT NULL,
    estado ENUM('pendiente', 'aprobado', 'programado', 'postergado', 'completado', 'rechazado') DEFAULT 'pendiente' NOT NULL,
    espacio_id INT NOT NULL,
    creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (responsable_id) REFERENCES usuarios(id) ON DELETE CASCADE,
    FOREIGN KEY (espacio_id) REFERENCES espacios(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Tabla: Ideas y Propuestas de Estudiantes (Sin espacio físico inicial)
CREATE TABLE IF NOT EXISTS propuestas_estudiantes (
    id INT AUTO_INCREMENT PRIMARY KEY,
    estudiante_id INT NOT NULL,
    titulo VARCHAR(200) NOT NULL,
    tipo_actividad VARCHAR(100) NOT NULL,
    descripcion TEXT NOT NULL,
    fecha_propuesta TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    FOREIGN KEY (estudiante_id) REFERENCES usuarios(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- =====================================================================
-- 3. TRIGGERS DE SEGURIDAD LOGICA (PREVENCIÓN DE COLISIONES)
-- =====================================================================

DELIMITER $$

-- Trigger para validar colisiones horarias antes de INSERTAR un evento aprobado o programado
CREATE TRIGGER tg_prevenir_colision_insercion
BEFORE INSERT ON eventos
FOR EACH ROW
BEGIN
    -- Solo validamos la colisión si el evento entra con estado de ocupación efectivo
    IF NEW.estado IN ('aprobado', 'programado') THEN
        IF EXISTS (
            SELECT 1 FROM eventos
            WHERE espacio_id = NEW.espacio_id
              AND fecha = NEW.fecha
              AND estado IN ('aprobado', 'programado')
              AND (
                  (NEW.hora_inicio >= hora_inicio AND NEW.hora_inicio < hora_fin) OR
                  (NEW.hora_fin > hora_inicio AND NEW.hora_fin <= hora_fin) OR
                  (NEW.hora_inicio <= hora_inicio AND NEW.hora_fin >= hora_fin)
              )
        ) THEN
            SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Conflicto de Horario: El espacio ya se encuentra reservado para esa fecha y rango de horas.';
        END IF;
    END IF;
END$$

-- Trigger para validar colisiones horarias antes de ACTUALIZAR (ej. cuando el administrador aprueba)
CREATE TRIGGER tg_prevenir_colision_actualizacion
BEFORE UPDATE ON eventos
FOR EACH ROW
BEGIN
    -- Validamos únicamente si el estado cambia a reservado efectivo o si se altera el horario
    IF NEW.estado IN ('aprobado', 'programado') THEN
        IF EXISTS (
            SELECT 1 FROM eventos
            WHERE espacio_id = NEW.espacio_id
              AND fecha = NEW.fecha
              AND id <> NEW.id -- Evitar compararse consigo mismo
              AND estado IN ('aprobado', 'programado')
              AND (
                  (NEW.hora_inicio >= hora_inicio AND NEW.hora_inicio < hora_fin) OR
                  (NEW.hora_fin > hora_inicio AND NEW.hora_fin <= hora_fin) OR
                  (NEW.hora_inicio <= hora_inicio AND NEW.hora_fin >= hora_fin)
              )
        ) THEN
            SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Conflicto de Horario: El espacio ya se encuentra ocupado por un evento aprobado en ese bloque horario.';
        END IF;
    END IF;
END$$

DELIMITER ;


-- =====================================================================
-- 4. INSERTAR DATOS SEMILLA (INSTITUCIONALES DE PRUEBA)
-- =====================================================================

-- Cargar espacios comunes de la FaCyT
INSERT INTO espacios (nombre, capacidad) VALUES
('Auditorio Principal FaCyT', 150),
('Laboratorio de Computación L-12', 30),
('Salón de Seminarios de Física', 40),
('Aula 102 - Edificio de Química', 50);

-- Cargar nómina de personal autorizado para validación durante el registro
-- Requisito crítico: No cualquiera puede crearse cuenta de administrativo o ponente
INSERT INTO personal_autorizado (cedula, rol_permitido) VALUES
('V-27894120', 'administrativo'), -- El Administrador Principal del sistema
('V-12345678', 'profesor'),        -- profesor de Computación
('V-11223344', 'ponente'),        -- Profesor Responsable del Depto. de Física
('V-22334455', 'ponente'),        -- Docente del área de computacion
('V-99999999', 'administrativo');  -- Auxiliar de Control de Estudios


ALTER TABLE eventos ADD COLUMN cupos_maximos INTEGER DEFAULT 0;

CREATE TABLE IF NOT EXISTS inscripciones (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    evento_id INTEGER NOT NULL,
    usuario_id INTEGER NOT NULL,
    fecha_inscripcion DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (evento_id) REFERENCES eventos(id) ON DELETE CASCADE,
    FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE CASCADE,
    UNIQUE(evento_id, usuario_id) -- Evita doble inscripción al mismo evento
);

CREATE TABLE IF NOT EXISTS inscripciones (
    id INT AUTO_INCREMENT PRIMARY KEY,
    usuario_id INT NOT NULL,
    evento_id INT NOT NULL,
    fecha_inscripcion DATETIME DEFAULT CURRENT_TIMESTAMP,
    estado VARCHAR(20) DEFAULT 'inscrito',
    FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE CASCADE,
    FOREIGN KEY (evento_id) REFERENCES eventos(id) ON DELETE CASCADE,
    UNIQUE(usuario_id, evento_id) -- Evita inscripciones duplicadas
);