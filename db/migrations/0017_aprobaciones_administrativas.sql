-- ============================================================================
-- EPI-Aetheris — Migración 0017
-- Respalda: ADR 0024 (cuentas de usuario y publicación con identidad)
--
-- Aprobaciones de una segunda persona para acciones administrativas sobre
-- cuentas de administrador. Hoy solo cubre el restablecimiento de segundo
-- factor: una solicitud la crea un administrador y solo otro administrador,
-- distinto del solicitante y del objetivo, puede confirmarla.
-- ============================================================================

BEGIN;

CREATE TABLE aprobaciones_administrativas (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    accion         TEXT NOT NULL CHECK (accion IN ('restablecer_factores')),
    objetivo_id    UUID NOT NULL REFERENCES usuarios (id),
    solicitante_id UUID NOT NULL REFERENCES usuarios (id),
    motivo         TEXT NOT NULL CHECK (char_length(motivo) BETWEEN 5 AND 500),
    creada_en      TIMESTAMPTZ NOT NULL DEFAULT now(),
    caduca_en      TIMESTAMPTZ NOT NULL,
    estado         TEXT NOT NULL DEFAULT 'pendiente'
        CHECK (estado IN ('pendiente', 'aprobada', 'rechazada', 'cancelada', 'caducada')),
    resuelta_por   UUID REFERENCES usuarios (id),
    resuelta_en    TIMESTAMPTZ,
    -- Nadie aprueba una solicitud sobre su propia cuenta ni la suya.
    CONSTRAINT aprobaciones_solicitante_distinto_del_objetivo
        CHECK (solicitante_id <> objetivo_id),
    CONSTRAINT aprobaciones_aprobador_independiente
        CHECK (estado <> 'aprobada'
               OR (resuelta_por IS NOT NULL
                   AND resuelta_por <> solicitante_id
                   AND resuelta_por <> objetivo_id)),
    CONSTRAINT aprobaciones_resuelta_completa
        CHECK ((estado = 'pendiente') = (resuelta_en IS NULL)),
    CONSTRAINT aprobaciones_caduca_despues
        CHECK (caduca_en > creada_en)
);

-- Una sola solicitud pendiente por acción y objetivo.
CREATE UNIQUE INDEX aprobaciones_pendiente_unica
    ON aprobaciones_administrativas (accion, objetivo_id) WHERE estado = 'pendiente';

COMMENT ON TABLE aprobaciones_administrativas IS
    'Solicitudes que necesitan la aprobación de otro administrador. ADR 0024.';

COMMIT;
