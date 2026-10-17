# Firma de candidatas para la ventana prospectiva (Fase 4) (2026-10-03)

> Protocolo propuesto el 2026-10-03, en la rama `feat/mejora-tablero-firma-candidatas` (sale de
> `feat/mejora-tablero-cambio-anio`). Firmado el 2026-10-03 al aprobarlo Eduardo y anotar el commit
> del script (sección Firma). No toca la prueba prospectiva congelada
> (`experimento-nowcast-tendencia.md`, script `40b6ebb78fe670222966a225438155b83ada876d`), la web,
> el backend ni los artefactos de `backend/api/datos/`.

## Pregunta

Tres variantes de C salieron de las Fases 1 y 2 con evidencia que no basta para cambiar el sitio:
sus ganancias se midieron en 2024 y en 2025 a 2026-S37, y esas semanas ya sirvieron para elegir C
y para originar las variantes. ¿Alguna supera a C en semanas objetivo que ninguna de las dos ha
visto?

## Estado de la información al firmar

- La base tiene la serie del tablero hasta 2026-S37, de las capturas del 2026-09-27 (tableros 04,
  05, 06 y 10). No hay capturas posteriores cargadas ni vistas por quien escribe este protocolo.
- Las semanas objetivo 2026-S38 en adelante no están en la base. Las predicciones de las
  candidatas se calculan solo con datos hasta el origen, como en la prueba congelada.
- Cada candidata nueva que se quiera medir en esta ventana tiene que firmarse antes de cargar
  una captura que incluya 2026-S38 o posterior. Después de esa carga, una candidata nueva necesita
  una ventana que empiece después de la última semana cargada.

## Por qué se comparte la ventana

La prueba congelada es la única ventana prospectiva en curso: semanas objetivo de 2026-S38 a
2027-S05 (20 semanas, con el cambio de año), evaluación una sola vez hacia mediados de febrero de
2027. Las candidatas son funciones de los mismos cuantiles de M0 y de T, así que se evalúan sobre
los mismos pares origen-horizonte, sin otro entrenamiento. La evaluación de C no cambia.

## Candidatas

C es el promedio por cuantil, en `log1p`, de M0 y T con peso 0,5 de M0. T es la tendencia
amortiguada con φ = 0,8, pendiente de 3 semanas e historia promediada a 7 semanas.

| id | definición | horizontes que cambia | origen |
|---|---|---|---|
| K1 | C con peso 0,25 de M0 en lugar de 0,5 | h = 3 y 4 | cumple la regla firmada de `experimento-nowcast-peso-horizonte.md` |
| K2 | en h = 1 y 2, la mediana es la de T y la distancia de cada cuantil a la mediana, en `log1p`, es la de C | h = 1 y 2 | exploratoria: se eligió después de ver 2025 a 2026-S37 |
| K3 | C con T calculada con pendiente de 2 semanas en lugar de 3 (φ = 0,8 y la misma historia) | todos | cumple la regla firmada de `experimento-nowcast-tendencia-seleccion.md`, sin ganancia en el tablero |

Fuera de los horizontes que cambia, K1 y K2 son idénticas a C. La combinación de K1 y K2 (C con los
dos cambios, T vigente) se reporta como "C por tramos"; su criterio es el de K1 y K2 por separado.

Evidencia previa, razón de WIS contra C (menor que 1 es mejor), promedio de los horizontes que
cambia:

| candidata | 2024 | 2025 a 2026-S37 | cobertura del 95 % en 2025 a 2026-S37 (candidata contra C) |
|---|---|---|---|
| K1 | 0,904 | 0,959 | 0,907 contra 0,901 |
| K2 | 0,981 | 0,884 | 0,932 contra 0,913 |
| K3 | 0,979 | 0,995 | 0,910 contra 0,907 (medida con `--verificar`) |

Lo que debilita esa evidencia: 2025 a 2026-S37 es dentro de muestra; K2 se eligió mirando esas
semanas; la validación que respalda a K1 y K2 mide contra una serie suavizada mientras M0 se
entrenó con datos crudos, lo que favorece pesos bajos de M0; y K3 no mejora nada en el tablero.
La probabilidad previa de que alguna se confirme es moderada y la de que las tres lo hagan, baja.

## Conjunto de prueba

Los pares origen-horizonte de la prueba congelada: semanas objetivo de 2026-S38 en adelante hasta
tener 20 publicadas, h = 1 a 8, con las mismas exclusiones por falta de datos. Se leen de la salida
de la evaluación congelada (`tendencia_prueba.json`), que contiene los cuantiles de M0, T y C de
cada par. K1 y K2 se calculan de esos cuantiles. K3 necesita T con pendiente de 2 semanas y se
calcula con la serie de la base, con datos hasta el origen y con la misma regla de errores
empíricos que T.

La evaluación de las candidatas se niega a correr si la evaluación congelada no existe, si esa
salida no declara el commit `40b6ebb78fe670222966a225438155b83ada876d`, si el script de las
candidatas tiene cambios sin commit o si su propia salida ya existe. Se corre una sola vez.

## Métrica y criterio

Referencia: la persistencia suavizada, como en la prueba congelada. Para cada candidata y cada
horizonte que cambia se calcula la razón de WIS contra C, con el WIS promedio sobre los pares de
ese horizonte.

Una candidata se confirma si cumple las tres:

1. La razón de WIS promedio de los horizontes que cambia es menor o igual que 0,99.
2. La razón es menor que 1 en más de la mitad de esos horizontes (en K1 y K2, los dos; en K3, al
   menos 5 de 8).
3. La cobertura del 95 % agrupada de esos horizontes no queda más de 0,03 por debajo de la de C.

Se reportan, sin criterio, el skill contra la persistencia suavizada, las coberturas del 50 % y del
95 % de cada candidata, la prueba de Diebold-Mariano contra C por horizonte (Newey-West con h − 1
rezagos y corrección de Harvey-Leybourne-Newbold, con Holm entre las 12 comparaciones) y la
sensibilidad sin las semanas objetivo de la 50 a la 3.

Con 20 semanas correlacionadas entre sí, la regla puede confirmar por azar una candidata sin
ventaja, y puede no confirmar una con ventaja chica. Las candidatas difieren de C entre 0,5 % y
12 % de WIS en 2025 a 2026-S37, así que el costo de un error en K1 o K2 es pequeño.
K3 cambia todos los horizontes con evidencia nula en el tablero y es la primera en salir si hay que
limitar candidatas.

## Qué habilita cada resultado

- Una candidata confirmada reemplaza a C en sus horizontes en el sitio solo si C se confirma en la
  prueba congelada, mediante un ADR que enmiende el 0020. La decisión es de Eduardo.
- Si C no se confirma, el sitio vuelve a M0 según el protocolo firmado y las candidatas quedan
  como hallazgo, con sus cifras.
- Una candidata no confirmada se descarta. Otra variante necesita su propia firma y una ventana
  posterior a ella.
- K3 confirmada no implica su combinación con K1 o K2: la interacción no se prueba aquí.

## Reproducibilidad

- Script `backend/ingestion/experimento_nowcast_candidatas.py`, con pruebas en
  `backend/ingestion/tests/test_candidatas.py`.
- `--verificar` calcula las tres candidatas con las semanas ya vistas (2024 a 2026-S37, de
  `rangos.json`) y debe reproducir las razones de la tabla de evidencia previa, con diferencia
  menor que 0,001. Las reproduce (diferencia máxima 0,0004). No mira ninguna semana de prueba. Salida en `docs/agentes/mejora-predictor/resultados-nuevos/candidatas_verificacion.json`.
- `--evaluar` es la evaluación firmada. Salida en
  `backend/ingestion/data/interim/nowcast/candidatas_prueba.json`.
- Las fórmulas de las candidatas están dentro del script, que no depende de los scripts de los
  experimentos para lo que define; una prueba compara esas fórmulas con las de los experimentos.

## Firma

Aprobado por Eduardo el 2026-10-03, sin enmiendas. Las tres candidatas (K1, K2 y K3) y el criterio
de arriba quedan firmados.

Commit del script: `069eaf9566050e1d001dbeefab52d868cb478c21`. Los commits posteriores de la rama
solo tocan las pruebas y este documento.

Desde esta firma el protocolo no se enmienda. Una candidata nueva se firma en otro documento y,
para entrar en esta ventana, antes de cargar una captura con 2026-S38 o posterior.
