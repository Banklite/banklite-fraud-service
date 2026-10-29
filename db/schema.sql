-- Esquema de fraud-service (PostgreSQL). Generado a partir de los modelos SQLAlchemy.
-- Tambien se crea solo al arrancar el servicio (Base.metadata.create_all).

CREATE TABLE regla_fraude (
	id_regla UUID NOT NULL, 
	nombre VARCHAR(150) NOT NULL, 
	tipo VARCHAR(50) NOT NULL, 
	umbral NUMERIC(12, 2) NOT NULL, 
	activa BOOLEAN NOT NULL, 
	PRIMARY KEY (id_regla), 
	CONSTRAINT chk_regla_umbral_positivo CHECK (umbral >= 0)
);

CREATE TABLE evaluacion_fraude (
	id_evaluacion UUID NOT NULL, 
	id_transaccion UUID NOT NULL, 
	id_regla UUID NOT NULL, 
	score_riesgo NUMERIC(5, 2) NOT NULL, 
	resultado VARCHAR(50) NOT NULL, 
	fecha_evaluacion TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	id_cuenta_origen UUID, 
	monto NUMERIC(14, 2), 
	motivo VARCHAR(255), 
	PRIMARY KEY (id_evaluacion), 
	CONSTRAINT chk_evaluacion_score_positivo CHECK (score_riesgo >= 0), 
	FOREIGN KEY(id_regla) REFERENCES regla_fraude (id_regla)
);
CREATE INDEX idx_evaluacion_regla ON evaluacion_fraude (id_regla);
CREATE INDEX idx_evaluacion_transaccion ON evaluacion_fraude (id_transaccion);
CREATE INDEX ix_evaluacion_fraude_id_cuenta_origen ON evaluacion_fraude (id_cuenta_origen);

CREATE TABLE alerta_fraude (
	id_alerta UUID NOT NULL, 
	id_evaluacion UUID NOT NULL, 
	estado VARCHAR(30) NOT NULL, 
	prioridad VARCHAR(20) NOT NULL, 
	fecha_generacion TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id_alerta), 
	CONSTRAINT chk_alerta_prioridad CHECK (prioridad IN ('baja', 'media', 'alta')), 
	FOREIGN KEY(id_evaluacion) REFERENCES evaluacion_fraude (id_evaluacion)
);
CREATE INDEX idx_alerta_evaluacion ON alerta_fraude (id_evaluacion);
