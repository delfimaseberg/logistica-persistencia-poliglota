-- 017: fechas de tramos cargadas como día, en hora argentina.
--
-- Hasta esta versión, la salida y la llegada estimada que se ingresan como
-- AAAA-MM-DD se guardaban a las 00:00 UTC (21:00 del día anterior en
-- Argentina). Ahora la salida es ese día a las 00:00:00 y la llegada estimada
-- ese día a las 23:59:59, hora de America/Argentina/Buenos_Aires.
--
-- Corrige solo los tramos cuya salida Y llegada estimada están a las 00:00:00
-- UTC exactas (la marca del error); el día que ingresó el usuario es la fecha
-- en UTC. Los tramos con hora real no se tocan.
--
-- Idempotente: una vez corregido, el tramo ya no está a las 00:00 UTC.
-- Después de aplicarla, resincronizar en Neo4j los envíos de esos tramos.
-- Requiere 016.

BEGIN;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_tramo_fechas') THEN
        RAISE EXCEPTION '017 requiere la migración 016';
    END IF;
END $$;

WITH afectados AS (
    SELECT id_tramo,
           (fecha_salida AT TIME ZONE 'UTC')::date AS dia_salida,
           (fecha_estimada_llegada AT TIME ZONE 'UTC')::date AS dia_llegada
    FROM tramo
    WHERE fecha_salida IS NOT NULL
      AND fecha_estimada_llegada IS NOT NULL
      AND (fecha_salida AT TIME ZONE 'UTC')::time = TIME '00:00:00'
      AND (fecha_estimada_llegada AT TIME ZONE 'UTC')::time = TIME '00:00:00'
)
UPDATE tramo t
SET fecha_salida = (a.dia_salida + TIME '00:00:00')
                   AT TIME ZONE 'America/Argentina/Buenos_Aires',
    fecha_estimada_llegada = (a.dia_llegada + TIME '23:59:59')
                             AT TIME ZONE 'America/Argentina/Buenos_Aires'
FROM afectados a
WHERE t.id_tramo = a.id_tramo;

COMMIT;
