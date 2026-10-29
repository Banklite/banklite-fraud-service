-- Datos de ejemplo de fraud-service. Ejecutar despues de schema.sql.
INSERT INTO regla_fraude (id_regla, nombre, tipo, umbral, activa) VALUES
 ('80000000-0000-0000-0000-000000000001','Monto maximo por transferencia','monto_maximo',5000000,true),
 ('80000000-0000-0000-0000-000000000002','Monto alto (revision)','monto_alto',2000000,true),
 ('80000000-0000-0000-0000-000000000003','Rafaga de transferencias (10 min)','rafaga',5,true),
 ('80000000-0000-0000-0000-000000000004','Acumulado diario por cuenta','acumulado_diario',10000000,true)
ON CONFLICT DO NOTHING;
INSERT INTO evaluacion_fraude (id_evaluacion, id_transaccion, id_regla, score_riesgo, resultado, fecha_evaluacion, monto, motivo) VALUES
 ('81000000-0000-0000-0000-000000000001','50000000-0000-0000-0000-000000000001','80000000-0000-0000-0000-000000000002',60,'revision_manual',now(),2500000,'Ejemplo: monto alto')
ON CONFLICT DO NOTHING;
INSERT INTO alerta_fraude (id_alerta, id_evaluacion, estado, prioridad, fecha_generacion) VALUES
 ('82000000-0000-0000-0000-000000000001','81000000-0000-0000-0000-000000000001','abierta','media',now())
ON CONFLICT DO NOTHING;
