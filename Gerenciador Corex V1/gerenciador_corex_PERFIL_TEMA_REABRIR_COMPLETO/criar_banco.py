from gerenciador import database, app
from gerenciador import models

with app.app_context():
    database.create_all()

print("Banco criado com sucesso!")