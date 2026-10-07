"""Reglas antifraude por defecto (se siembran al arrancar si no existen).

tipo               umbral                       efecto
monto_maximo       monto por transferencia      BLOQUEA si el monto lo supera
monto_alto         monto por transferencia      pasa, pero genera alerta de revision
rafaga             N transferencias / 10 min    BLOQUEA a la N-esima
acumulado_diario   suma de montos en 24 h       BLOQUEA si se supera
"""

REGLAS_POR_DEFECTO = [
    ("Monto maximo por transferencia", "monto_maximo", 5_000_000),
    ("Monto alto (revision)", "monto_alto", 2_000_000),
    ("Rafaga de transferencias (10 min)", "rafaga", 5),
    ("Acumulado diario por cuenta", "acumulado_diario", 10_000_000),
]

VENTANA_RAFAGA_MIN = 10
