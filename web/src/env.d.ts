interface ImportMetaEnv {
  readonly PUBLIC_ULTIMO_ANIO_CLIMA: number;
  readonly PUBLIC_FECHA_CORTE: string;
  readonly PUBLIC_VERSION_CORTE: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
