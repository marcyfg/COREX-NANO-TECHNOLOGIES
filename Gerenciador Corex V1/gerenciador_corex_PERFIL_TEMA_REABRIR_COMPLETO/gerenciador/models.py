from gerenciador import database, login_manager
from flask_login import UserMixin
from datetime import datetime


SETORES_PADRAO = [
    "Administração - Recepção",
    "Administração - Marketing",
    "Administração - Financeiro",
    "Administração - Comercial",
    "Administração - Diretoria",
    "Suporte Técnico",
    "Laboratório de Informática",
    "Servidores e Redes",
    "Segurança da Informação",
    "Desenvolvimento - Devs",
]


@login_manager.user_loader
def load_usuario(id_usuario):
    return Usuario.query.get(int(id_usuario))


class Usuario(database.Model, UserMixin):

    id = database.Column(database.Integer, primary_key=True)
    username = database.Column(database.String, nullable=False)
    email = database.Column(database.String, unique=True, nullable=False)
    senha = database.Column(database.String, nullable=False)

    # Mantido para compatibilidade com o projeto original.
    admin = database.Column(database.Boolean, default=False)

    # O usuário ID 1 também é tratado como ADM principal automaticamente nas rotas.
    principal_admin = database.Column(database.Boolean, default=False)

    # Setor do usuário. Administradores comuns só gerenciam funcionários/chamados do próprio setor.
    setor = database.Column(database.String, default="Suporte Técnico")
    ativo = database.Column(database.Boolean, default=True)

    # Preferências e perfil visual do usuário.
    foto_perfil = database.Column(database.String, nullable=True)
    tema_preferido = database.Column(database.String, default="escuro")

    tarefas = database.relationship("Tarefa", backref="usuario", lazy=True)


class Tarefa(database.Model):

    id = database.Column(database.Integer, primary_key=True)
    titulo = database.Column(database.String, nullable=False)
    descricao = database.Column(database.String)
    imagem = database.Column(database.String, nullable=True)
    concluida = database.Column(database.Boolean, default=False)
    encerrada_forcada = database.Column(database.Boolean, default=False)

    # Setor dono do chamado. Usuários comuns só enxergam chamados do próprio setor.
    setor = database.Column(database.String, default="Suporte Técnico")

    data_criacao = database.Column(database.DateTime, default=datetime.utcnow)
    data_atualizacao = database.Column(database.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    id_usuario = database.Column(database.Integer, database.ForeignKey("usuario.id"), nullable=True)


class Comentario(database.Model):

    id = database.Column(database.Integer, primary_key=True)
    texto = database.Column(database.Text, nullable=False)
    data_criacao = database.Column(database.DateTime, default=datetime.utcnow)
    id_tarefa = database.Column(database.Integer, database.ForeignKey("tarefa.id"), nullable=False)
    id_usuario = database.Column(database.Integer, database.ForeignKey("usuario.id"), nullable=False)

    tarefa = database.relationship("Tarefa", backref=database.backref("comentarios", lazy=True, cascade="all, delete-orphan"))
    usuario = database.relationship("Usuario")
