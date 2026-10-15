import js from '@eslint/js';
import { defineConfig } from 'eslint/config';
import astro from 'eslint-plugin-astro';
import globals from 'globals';
import tseslint from 'typescript-eslint';

// defineConfig de ESLint reemplaza a tseslint.config(), que typescript-eslint
// marcó como obsoleto.
export default defineConfig(
  {
    ignores: ['.astro/**', 'dist/**'],
  },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  ...astro.configs.recommended,
  {
    rules: {
      // El código cartográfico heredado valida estructuras GeoJSON en
      // runtime; tiparlo por completo es un refactor separado del tooling.
      '@typescript-eslint/no-explicit-any': 'off',
    },
  },
  {
    files: ['**/*.{js,mjs,ts}'],
    languageOptions: {
      globals: {
        ...globals.browser,
        ...globals.node,
      },
    },
  },
  {
    files: ['**/*.astro'],
    languageOptions: {
      globals: globals.browser,
      parserOptions: {
        parser: tseslint.parser,
      },
    },
  },
  {
    files: ['**/*.d.ts'],
    rules: {
      // src/env.d.ts usa la referencia generada oficialmente por Astro.
      '@typescript-eslint/triple-slash-reference': 'off',
    },
  },
);
