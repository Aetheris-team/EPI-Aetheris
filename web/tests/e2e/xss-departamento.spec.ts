import { expect, test } from '@playwright/test';
import {
  FILTROS_ANALISIS_PREDETERMINADOS,
  normalizarEstado,
} from '../../src/lib/analisis-state.ts';

// El parámetro ?dept= es entrada del visitante. Antes llegaba sin validar a
// innerHTML de las gráficas del departamento y se ejecutaba como HTML. La
// raíz es la normalización del estado: solo pasan códigos de departamento.
const CARGA = '<img src=x onerror="alert(1)">';

test.describe('Filtros con entrada hostil', () => {
  test('dept con HTML se descarta', () => {
    const estado = normalizarEstado(FILTROS_ANALISIS_PREDETERMINADOS, {
      departamento: CARGA,
    });
    expect(estado.departamento).toBeNull();
  });

  test('compare descarta lo que no es un código de departamento', () => {
    const estado = normalizarEstado(FILTROS_ANALISIS_PREDETERMINADOS, {
      comparar: [CARGA, 'SV-SS', 'San Salvador'],
    });
    expect(estado.comparar).toEqual(['SV-SS']);
  });

  test('un código válido se conserva', () => {
    const estado = normalizarEstado(FILTROS_ANALISIS_PREDETERMINADOS, {
      departamento: ' SV-SS ',
    });
    expect(estado.departamento).toBe('SV-SS');
  });

  test('la URL con un código válido sigue funcionando', async ({ page }) => {
    await page.goto('/dengue?year=2022&dept=SV-SS&serie=probable');
    await expect(page).toHaveURL(/dept=SV-SS/);
  });
});
