# -*- coding: utf-8 -*-
import os

def empaquetar_directorio(ruta_origen, archivo_salida="contexto_proyecto.md"):
    # Carpetas y archivos comunes a ignorar para no saturar el contexto
    ignorar_carpetas = {'.git', 'node_modules', '__pycache__', 'venv', '.env', 'dist', 'build'}
    ignorar_extensiones = {'.png', '.jpg', '.jpeg', '.gif', '.ico', '.pdf', '.zip', '.tar', '.gz', '.mp4'}

    print(f"Empaquetando el directorio: {os.path.abspath(ruta_origen)}")
    
    with open(archivo_salida, 'w', encoding='utf-8') as f_out:
        f_out.write("# Contexto del Proyecto\n")
        f_out.write("Este archivo contiene la estructura y el código fuente del proyecto para análisis.\n\n")
        
        # 1. Escribir estructura de archivos
        f_out.write("## Estructura de Directorios\n```text\n")
        for raiz, dirs, archivos in os.walk(ruta_origen):
            # Filtrar carpetas a ignorar sobre la marcha
            dirs[:] = [d for d in dirs if d not in ignorar_carpetas]
            
            nivel = raiz.replace(ruta_origen, '').count(os.sep)
            sangria = ' ' * 4 * (nivel)
            f_out.write(f"{sangria}{os.path.basename(raiz)}/\n")
            sub_sangria = ' ' * 4 * (nivel + 1)
            for archivo in archivos:
                if not any(archivo.endswith(ext) for ext in ignorar_extensiones):
                    f_out.write(f"{sub_sangria}{archivo}\n")
        f_out.write("```\n\n")

        # 2. Escribir el contenido de cada archivo
        f_out.write("## Contenido de los Archivos\n\n")
        for raiz, dirs, archivos in os.walk(ruta_origen):
            dirs[:] = [d for d in dirs if d not in ignorar_carpetas]
            
            for archivo in archivos:
                if any(archivo.endswith(ext) for ext in ignorar_extensiones) or archivo == archivo_salida or archivo == 'empaquetador_codigo.py':
                    continue
                    
                ruta_completa = os.path.join(raiz, archivo)
                ruta_relativa = os.path.relpath(ruta_completa, ruta_origen)
                
                f_out.write(f"### Archivo: {ruta_relativa}\n")
                
                # Intentar detectar la extensión para el bloque de código Markdown
                ext = os.path.splitext(archivo)[1].lstrip('.')
                f_out.write(f"```{ext}\n")
                
                try:
                    with open(ruta_completa, 'r', encoding='utf-8', errors='replace') as f_in:
                        f_out.write(f_in.read())
                except Exception as e:
                    f_out.write(f"[Error leyendo el archivo: {str(e)}]")
                
                f_out.write("\n```\n\n")
                
    print(f"¡Listo! Todo tu código ha sido unificado en: {archivo_salida}")

if __name__ == "__main__":
    # Se ejecuta en el directorio actual
    empaquetar_directorio(".")
