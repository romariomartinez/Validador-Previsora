# Radicador Previsora - MVP local

Aplicacion local para preparar lotes de radicacion Previsora SOAT/AP.

## Que hace

- Permite un Armador automatico: subes todos los archivos en una sola bandeja y la app los separa por caja.
- Valida documentos obligatorios por ramo, amparo y tipo de cuenta.
- Revisa extensiones, nombres de soportes, tamanos de ZIP y tamanos de PDF.
- Valida JSON de CUV/RIPS cuando se cargan archivos `.json`.
- Genera ZIPs por caja de cargue.
- Bloquea la generacion de ZIPs cuando falta un obligatorio o cuando un archivo no se puede clasificar.
- Crea reportes por lote en JSON y Markdown.
- Advierte si detecta una preparacion previa del mismo NIT/factura/filtros dentro de 48 horas.

## Ejecutar

Desde esta carpeta:

```powershell
& "C:\Users\romar\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" app.py
```

Luego abre:

```text
http://127.0.0.1:8765
```

## Cajas de archivo

El modo recomendado es `Armador automatico`. Puedes subir archivos sueltos o una carpeta completa. La app clasifica asi:

- PDFs: Caja de soportes.
- Archivos con nombre `RIPS`: Caja RIPS JSON.
- Archivos con nombre `CUV`: Caja CUV.
- Archivos `Furips 1`, `Furips 2` y `Furtran`: cajas FURIPS/FURTRAN.

Si un JSON no dice CUV o RIPS en el nombre y ambas cajas son necesarias, el sistema lo bloquea para evitar armar un paquete incorrecto.

Tambien esta disponible el modo `Por cajas`, donde seleccionas manualmente cada grupo:

- Caja CUV: TXT o JSON.
- Caja RIPS JSON: JSON.
- Caja FURIPS: TXT de Furips 1 / Furips 2.
- Caja FURTRAN: TXT de Furtran.
- Caja de soportes: PDF.

Puedes subir archivos sueltos o un ZIP por caja. No mezcles ZIP y archivos sueltos en la misma caja.

## Salidas

Cada validacion queda en:

```text
data/runs/<id_del_lote>/
```

Dentro encontraras:

- `ready/`: ZIPs listos para cargar.
- `report.json`: resultado estructurado.
- `reporte_validacion.md`: resumen legible.

## Siguiente fase

Cuando tengamos URL y credenciales de prueba, se puede agregar el robot de navegador para:

- Entrar a la plataforma.
- Seleccionar filtros.
- Cargar los ZIPs generados.
- Capturar el ID de cargue.
- Consultar resultados y descargar reportes.
