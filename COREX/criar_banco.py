from gerenciador import database, app, bcrypt
from gerenciador.models import Usuario

with app.app_context():
    database.create_all()

    admin = Usuario.query.filter_by(email="admin@corex.com").first()

    if not admin:
        admin = Usuario(
            username="Administrador CoreX",
            email="admin@corex.com",
            senha=bcrypt.generate_password_hash("123456").decode("utf-8"),
            admin=True,
            principal_admin=True,
            setor="Suporte Técnico",
            ativo=True,
            tema_preferido="escuro"
        )
        database.session.add(admin)
        database.session.commit()
        print("BANCO CRIADO E ADMIN PADRAO CADASTRADO!")
    else:
        admin.senha = bcrypt.generate_password_hash("123456").decode("utf-8")
        admin.admin = True
        admin.principal_admin = True
        admin.ativo = True
        database.session.commit()
        print("BANCO JA EXISTIA. ADMIN PADRAO ATUALIZADO!")

print("LOGIN: admin@corex.com")
print("SENHA: 123456")
