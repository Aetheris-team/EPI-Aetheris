# Firma de la candidata K4 (ETS) para la ventana prospectiva (2026-10-03)

> Protocolo propuesto el 2026-10-03, en la rama `feat/mejora-tablero-theta-ets`. Firmado el
> 2026-10-03 al aprobarlo Eduardo y anotar el commit del script (sección Firma). Continúa `firma-candidatas-ventana-prospectiva.md` (K1, K2 y K3, firmadas con el script
> `069eaf9566050e1d001dbeefab52d868cb478c21`), que no se toca, igual que la prueba prospectiva
> congelada (`experimento-nowcast-tendencia.md`, script `40b6ebb78fe670222966a225438155b83ada876d`),
> la web, el backend y los artefactos de `backend/api/datos/`.

## Pregunta

El experimento `experimento-nowcast-theta-ets.md` dejó una variante elegible: un suavizado
exponencial con tendencia amortiguada (ETS) puesto en lugar de T dentro de C. Gana a T en la
historia hasta 2023 y en 2024, pero en 2025 a 2026-S37 no mejora a C. Esas semanas ya sirvieron para
elegir C. ¿Supera ETS a C en semanas objetivo que ninguna de las dos ha visto?

## Estado de la información al firmar

- La base tiene la serie del tablero hasta 2026-S37, de las capturas del 2026-09-27. No hay capturas
  posteriores cargadas ni vistas por quien escribe este protocolo.
- Las semanas objetivo 2026-S38 en adelante no están en la base. La candidata se calcula solo con
  datos hasta el origen, como en la prueba congelada.
- Esta candidata tiene que firmarse antes de cargar una captura que incluya 2026-S38 o posterior.
  Después de esa carga, una candidata nueva necesita una ventana que empiece después de la última
  semana cargada.

## Candidata

C es el promedio por cuantil, en `log1p`, de M0 y T con peso 0,5 de M0. T es la tendencia
amortiguada con φ = 0,8, pendiente de 3 semanas e historia promediada a 7 semanas.

K4: C con ETS en lugar de T, en los ocho horizontes. ETS es el suavizado exponencial con tendencia
aditiva amortiguada del experimento, con los parámetros fijos α = 0,8, β = 1,0 y φ = 0,8, aplicado
a la historia promediada a 7 semanas y en `log1p`:

- l(t) = α · z(t) + (1 − α) · (l(t−1) + φ · b(t−1)) y b(t) = β · (l(t) − l(t−1)) + (1 − β) · φ · b(t−1);
  mediana a h semanas: l(t) + b(t) · (φ + … + φ^h). Inicio: l(0) = z(0), b(0) = 0.
- Cuantiles: la mediana más los 23 cuantiles de los errores de los pares (t, t + h) con objetivo
  anterior al origen, desde 2014, sin 2020 y con dato en el origen y en el objetivo del par. El par
  con origen en la primera semana de la serie no entra.
- Los parámetros no se reajustan. K4 es el promedio por cuantil, en `log1p`, de M0 y de ETS con peso
  0,5 de M0.

Evidencia previa. En la validación de la base (2018 a 2023, con la que se eligieron los parámetros)
ETS puntúa +0,2568 de skill contra +0,2258 de T, y supera a T en 4 de 5 años. Razón de WIS de K4
contra C (menor que 1 es mejor), promedio de los 8 horizontes:

| conjunto | razón | horizontes con razón menor que 1 | cobertura del 95 % de K4 contra C |
|---|---|---|---|
| 2024 | 0,973 | 8 de 8 | 1,000 contra 1,000 |
| 2025 a 2026-S37 (dentro de muestra) | 0,998 | 5 de 8 | 0,907 contra 0,907 |

Con el criterio de abajo, K4 se confirmaría en 2024 y no en 2025 a 2026-S37 (0,998 es mayor que
0,99).

Lo que debilita esa evidencia: en el tablero, que es lo que se mide en la ventana, la ganancia
desaparece; los parámetros se eligieron con una historia que MINSAL no produjo; la rejilla es gruesa
y la elección usa cinco años; ninguna prueba de Diebold-Mariano resiste la corrección de Holm. La
probabilidad previa de que K4 se confirme es baja. Firmarla cuesta poco: no cambia el sitio y la
evaluación se hace sobre los pares de la prueba congelada, sin entrenar nada.

## Conjunto de prueba

Los pares origen-horizonte de la prueba congelada: semanas objetivo de 2026-S38 en adelante hasta
tener 20 publicadas, h = 1 a 8, con las mismas exclusiones por falta de datos. Se leen de la salida
de la evaluación congelada (`tendencia_prueba.json`), que contiene los cuantiles de M0, T y C de
cada par. Los de ETS se calculan con la serie de la base, con datos hasta el origen.

La evaluación se niega a correr si la evaluación congelada no existe, si esa salida no declara el
commit `40b6ebb78fe670222966a225438155b83ada876d`, si el script de K4 tiene cambios sin commit o si su
propia salida ya existe. Se corre una sola vez.

## Métrica y criterio

Referencia: la persistencia suavizada, como en la prueba congelada. Para cada horizonte se calcula
la razón de WIS de K4 contra C, con el WIS promedio sobre los pares de ese horizonte.

K4 se confirma si cumple las tres:

1. La razón de WIS promedio de los 8 horizontes es menor o igual que 0,99.
2. La razón es menor que 1 en al menos 5 de los 8 horizontes.
3. La cobertura del 95 % agrupada de los 8 horizontes no queda más de 0,03 por debajo de la de C.

Se reportan, sin criterio: el skill contra la persistencia suavizada, las coberturas del 50 % y del
95 %, la prueba de Diebold-Mariano contra C por horizonte (Newey-West con h − 1 rezagos y corrección
de Harvey-Leybourne-Newbold, con Holm entre los 8 horizontes) y la sensibilidad sin las semanas
objetivo de la 50 a la 3. El Holm de K1 a K3 no se rehace; quien lea el conjunto de candidatas tiene
en cuenta que son 20 comparaciones.

## Qué habilita cada resultado

- Si K4 se confirma, reemplaza a C en el sitio solo si C se confirma en la prueba congelada,
  mediante un ADR que enmiende el 0020. La decisión es de Eduardo.
- Si C no se confirma, el sitio vuelve a M0 según el protocolo firmado y K4 queda como hallazgo,
  con sus cifras.
- Si K4 no se confirma se descarta. Otra variante necesita su propia firma y una ventana posterior.
- K4 confirmada no implica su combinación con K1, K2 o K3: la interacción no se prueba aquí.

## Reproducibilidad

- Script `backend/ingestion/experimento_nowcast_candidata_ets.py`, con pruebas en
  `backend/ingestion/tests/test_candidata_ets.py`. Define por sí mismo la fórmula de ETS y la de los
  cuantiles; una prueba compara esas fórmulas con las del experimento.
- `--verificar` calcula K4 con las semanas ya vistas (2024 y 2025 a 2026-S37, de `rangos.json`) y
  debe reproducir las razones de WIS de `theta_ets.json` (0,9725 y 0,9975), con diferencia menor
  que 0,0001. Las reproduce (0,97251 y 0,99752). No mira ninguna semana de prueba. Salida en
  `docs/agentes/mejora-predictor/resultados-nuevos/candidata_ets_verificacion.json`.
- `--evaluar` es la evaluación firmada. Salida en
  `backend/ingestion/data/interim/nowcast/candidata_ets_prueba.json`.

## Firma

Aprobado por Eduardo el 2026-10-03, sin enmiendas. K4 y el criterio de arriba quedan firmados.

Commit del script: `3086b20af5ceb21b0857c5630a2d6137f4cde512`. Los commits posteriores de la rama
solo tocan este documento y la salida de la verificación.

Desde esta firma el protocolo no se enmienda. Una candidata nueva se firma en otro documento y, para
entrar en esta ventana, antes de cargar una captura con 2026-S38 o posterior.
