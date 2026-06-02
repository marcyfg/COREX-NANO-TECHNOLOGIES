from gerenciador import database, login_manager
from flask_login import UserMixin
from datetime import datetime


CARGOS_USUARIO = [
    ("SUPER_ADMIN", "Super Admin CoreX"),
    ("ADMIN_COREX", "Administrador CoreX"),
    ("TECNICO_COREX", "Técnico CoreX"),
    ("CLIENTE", "Cliente / Colaborador"),
]


def nome_cargo(cargo):
    mapa = dict(CARGOS_USUARIO)
    return mapa.get(cargo or "CLIENTE", "Cliente / Colaborador")


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

    # Nova regra profissional de cargos:
    # SUPER_ADMIN = controle total
    # ADMIN_COREX = gerencia chamados/equipe do setor
    # TECNICO_COREX = atende chamados atribuídos
    # CLIENTE = abre e acompanha os próprios chamados
    cargo = database.Column(database.String, default="CLIENTE")

    # O usuário ID 1 também é tratado como Super Admin automaticamente nas rotas.
    principal_admin = database.Column(database.Boolean, default=False)

    # Setor do usuário. Administradores comuns só gerenciam funcionários/chamados do próprio setor.
    setor = database.Column(database.String, default="Suporte Técnico")
    ativo = database.Column(database.Boolean, default=True)
    data_criacao = database.Column(database.DateTime, default=datetime.utcnow)

    # Preferências e perfil visual do usuário.
    foto_perfil = database.Column(database.String, nullable=True)
    tema_preferido = database.Column(database.String, default="escuro")

    # Dados da empresa cliente.
    empresa = database.Column(database.String, nullable=True)
    cnpj = database.Column(database.String, nullable=True)
    responsavel_empresa = database.Column(database.String, nullable=True)

    # Chamados em que este usuário é o responsável pelo atendimento.
    tarefas = database.relationship("Tarefa", foreign_keys="Tarefa.id_usuario", backref="usuario", lazy=True)

    # Chamados que este usuário abriu como solicitante/cliente.
    chamados_abertos = database.relationship("Tarefa", foreign_keys="Tarefa.id_solicitante", backref="solicitante", lazy=True)


class Tarefa(database.Model):

    id = database.Column(database.Integer, primary_key=True)
    titulo = database.Column(database.String, nullable=False)
    descricao = database.Column(database.String)
    imagem = database.Column(database.String, nullable=True)
    concluida = database.Column(database.Boolean, default=False)
    encerrada_forcada = database.Column(database.Boolean, default=False)

    # Dados profissionais do chamado.
    categoria = database.Column(database.String, default="Suporte Geral")
    prioridade = database.Column(database.String, default="Média")
    status = database.Column(database.String, default="aberto")
    numero_ticket = database.Column(database.String, unique=True, nullable=True)

    # Setor técnico/Core-X responsável pelo atendimento.
    # Chamados abertos por clientes entram inicialmente na Fila Geral e depois podem ser direcionados.
    setor = database.Column(database.String, default="Suporte Técnico")

    # Setor/local informado pelo cliente onde o problema aconteceu.
    # Ex: Financeiro, RH, Recepção, Estoque, Sala 2 etc.
    setor_cliente = database.Column(database.String, nullable=True)

    data_criacao = database.Column(database.DateTime, default=datetime.utcnow)
    data_atualizacao = database.Column(database.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    # Responsável pelo atendimento do chamado. Normalmente será alguém da equipe Core-X.
    id_usuario = database.Column(database.Integer, database.ForeignKey("usuario.id"), nullable=True)

    # Usuário que abriu o chamado. Normalmente será o colaborador/cliente.
    id_solicitante = database.Column(database.Integer, database.ForeignKey("usuario.id"), nullable=True)


class Comentario(database.Model):

    id = database.Column(database.Integer, primary_key=True)
    texto = database.Column(database.Text, nullable=False)
    data_criacao = database.Column(database.DateTime, default=datetime.utcnow)
    id_tarefa = database.Column(database.Integer, database.ForeignKey("tarefa.id"), nullable=False)
    id_usuario = database.Column(database.Integer, database.ForeignKey("usuario.id"), nullable=False)

    tarefa = database.relationship("Tarefa", backref=database.backref("comentarios", lazy=True, cascade="all, delete-orphan"))
    usuario = database.relationship("Usuario")


class Notificacao(database.Model):

    id = database.Column(database.Integer, primary_key=True)
    titulo = database.Column(database.String, nullable=False)
    mensagem = database.Column(database.String, nullable=False)
    lida = database.Column(database.Boolean, default=False)
    data_criacao = database.Column(database.DateTime, default=datetime.utcnow)
    id_usuario = database.Column(database.Integer, database.ForeignKey("usuario.id"), nullable=False)
    id_tarefa = database.Column(database.Integer, database.ForeignKey("tarefa.id"), nullable=True)

    usuario = database.relationship("Usuario", backref=database.backref("notificacoes", lazy=True, cascade="all, delete-orphan"))
    tarefa = database.relationship("Tarefa")
