-- 012: usuarios de proveedores, operadores logísticos o internos.
--
-- Un usuario pertenece como mucho a una parte: cliente, proveedor u
-- operador. Sin ninguna, es un usuario interno (por ejemplo, el
-- administrador). Los usuarios existentes tienen cliente y siguen siendo
-- válidos. Aditiva e idempotente; no modifica filas.

BEGIN;

ALTER TABLE usuario ALTER COLUMN id_cliente DROP NOT NULL;
ALTER TABLE usuario ADD COLUMN IF NOT EXISTS id_proveedor BIGINT;
ALTER TABLE usuario ADD COLUMN IF NOT EXISTS id_operador BIGINT;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'fk_usuario_proveedor'
          AND conrelid = 'usuario'::regclass
    ) THEN
        ALTER TABLE usuario ADD CONSTRAINT fk_usuario_proveedor
            FOREIGN KEY (id_proveedor) REFERENCES proveedor(id_proveedor);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'fk_usuario_operador'
          AND conrelid = 'usuario'::regclass
    ) THEN
        ALTER TABLE usuario ADD CONSTRAINT fk_usuario_operador
            FOREIGN KEY (id_operador) REFERENCES operador_logistico(id_operador);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'chk_usuario_una_parte'
          AND conrelid = 'usuario'::regclass
    ) THEN
        ALTER TABLE usuario ADD CONSTRAINT chk_usuario_una_parte
            CHECK (num_nonnulls(id_cliente, id_proveedor, id_operador) <= 1);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_usuario_proveedor ON usuario (id_proveedor);
CREATE INDEX IF NOT EXISTS idx_usuario_operador ON usuario (id_operador);

COMMIT;
