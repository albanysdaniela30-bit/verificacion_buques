import sqlite3

# Conectar a la base de datos existente
conn = sqlite3.connect("buques.db")
c = conn.cursor()

# Actualizar todos los registros que tienen tipo_buque = "PASAJES"
c.execute("UPDATE buques SET tipo_buque='PASAJE' WHERE tipo_buque='PASAJES'")

# Guardar los cambios y cerrar la conexión
conn.commit()
conn.close()

print("Actualización completada: 'PASAJES' ahora es 'PASAJE'.")
