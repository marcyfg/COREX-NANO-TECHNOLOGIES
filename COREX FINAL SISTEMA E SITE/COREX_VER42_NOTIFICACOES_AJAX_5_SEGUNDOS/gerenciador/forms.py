from flask_wtf import FlaskForm

from wtforms import (
    StringField,
    PasswordField,
    SubmitField,
    FileField,
    BooleanField,
    SelectField,
    TextAreaField
)

from wtforms.validators import (
    DataRequired,
    Email,
    EqualTo,
    Length,
    ValidationError,
    Optional
)

from gerenciador.models import Usuario, SETORES_PADRAO, CARGOS_USUARIO, CATEGORIAS_CHAMADO, PRIORIDADES_CHAMADO


def escolhas_setores(com_todos=False):
    opcoes = [(setor, setor) for setor in SETORES_PADRAO]
    if com_todos:
        return [("todos", "Todos os setores")] + opcoes
    return opcoes


SETORES_LOCAL_PROBLEMA = [
    ("", "Selecione o setor/local do problema"),
    ("Administração", "Administração"),
    ("Financeiro", "Financeiro"),
    ("Recursos Humanos", "Recursos Humanos"),
    ("Comercial", "Comercial"),
    ("Recepção", "Recepção"),
    ("Estoque", "Estoque"),
    ("Expedição", "Expedição"),
    ("Produção", "Produção"),
    ("Mecânica", "Mecânica"),
    ("Laboratório de Informática", "Laboratório de Informática"),
    ("Sala de Reunião", "Sala de Reunião"),
    ("Diretoria", "Diretoria"),
    ("Outros", "Outros"),
]


def senha_segura(form, field):
    """Validação simples para evitar senhas fracas na apresentação do sistema."""
    senha = field.data or ""
    if not senha:
        return
    tem_letra = any(c.isalpha() for c in senha)
    tem_numero = any(c.isdigit() for c in senha)
    if len(senha) < 8 or not tem_letra or not tem_numero:
        raise ValidationError("A senha deve ter pelo menos 8 caracteres, contendo letras e números.")


class FormLogin(FlaskForm):
    email = StringField("Email", validators=[DataRequired(), Email()])
    senha = PasswordField("Senha", validators=[DataRequired()])
    botao_confirmacao = SubmitField("Login")


class FormCriarConta(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
    username = StringField('Usuário', validators=[DataRequired(), Length(min=3, max=30)])
    senha = PasswordField('Senha', validators=[DataRequired(), Length(min=8, max=32), senha_segura])
    confirmacao_senha = PasswordField('Confirme a senha', validators=[DataRequired(), EqualTo('senha')])
    cargo = SelectField("Cargo / Perfil de acesso", choices=CARGOS_USUARIO, validators=[DataRequired()])
    admin = BooleanField("Criar como ADM operacional")  # mantido apenas para compatibilidade
    empresa = StringField("Razão Social", validators=[Optional(), Length(max=120)])
    cnpj = StringField("CNPJ", validators=[Optional(), Length(max=30)])
    responsavel_empresa = StringField("Nome da pessoa / responsável", validators=[Optional(), Length(max=120)])
    setor = SelectField("Setor", choices=escolhas_setores(), validators=[DataRequired()])
    botao_confirmacao = SubmitField('Confirmar')

    def validate_email(self, email):
        usuario = Usuario.query.filter_by(email=email.data).first()
        if usuario:
            raise ValidationError("Email já cadastrado.")


class FormEditarUsuario(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
    username = StringField('Usuário', validators=[DataRequired(), Length(min=3, max=30)])
    cargo = SelectField("Cargo / Perfil de acesso", choices=CARGOS_USUARIO, validators=[DataRequired()])
    admin = BooleanField("ADM operacional")  # mantido apenas para compatibilidade
    setor = SelectField("Setor", choices=escolhas_setores(), validators=[DataRequired()])
    ativo = BooleanField("Usuário ativo")
    botao_confirmacao = SubmitField('Salvar alterações')


class FormTarefa(FlaskForm):
    titulo = StringField("Título / Defeito", validators=[DataRequired(message="Informe um título para o chamado."), Length(min=6, max=120, message="O título deve ter entre 6 e 120 caracteres.")])
    descricao = TextAreaField("Descrição", validators=[DataRequired(message="Descreva o problema para que a equipe consiga entender."), Length(min=15, max=2500, message="A descrição deve ter entre 15 e 2500 caracteres.")])
    categoria = SelectField("Categoria", choices=CATEGORIAS_CHAMADO, validators=[DataRequired()])
    # A prioridade é uma decisão da equipe CoreX, não do cliente.
    # Por isso o campo fica opcional no formulário: cliente não vê, admin/técnico pode definir.
    prioridade = SelectField("Prioridade", choices=PRIORIDADES_CHAMADO, validators=[Optional()])
    setor_cliente_opcao = SelectField("Setor/local onde ocorre o problema", choices=SETORES_LOCAL_PROBLEMA, validators=[DataRequired(message="Selecione o setor/local onde ocorre o problema.")])
    setor_cliente_outros = StringField("Informe o setor/local", validators=[Optional(), Length(max=120, message="O local do problema deve ter no máximo 120 caracteres.")])
    setor = SelectField("Setor responsável", choices=escolhas_setores(), validators=[DataRequired()])
    foto = FileField("Foto (opcional)")
    usuario_destino = SelectField("Usuário responsável", coerce=int)
    botao_confirmacao = SubmitField("Criar Chamado")


class FormTransferirTarefa(FlaskForm):
    setor_destino = SelectField("Fila técnica Core-X", choices=escolhas_setores(), validators=[DataRequired()])
    usuario_destino = SelectField("Transferir para", coerce=int, validators=[Optional()])
    comentario = TextAreaField("Comentário obrigatório para salvar a transferência", validators=[DataRequired(message="Informe um comentário para justificar a ação."), Length(min=3, max=2000)])
    botao_confirmacao = SubmitField("Salvar transferência")


class FormComentario(FlaskForm):
    texto = TextAreaField("Comentário", validators=[DataRequired(), Length(min=2, max=2000)])
    botao_confirmacao = SubmitField("Adicionar comentário")


class FormPerfilUsuario(FlaskForm):
    username = StringField("Nome", validators=[DataRequired(), Length(min=3, max=30)])
    email = StringField("Email cadastrado", validators=[DataRequired(), Email()])
    senha = PasswordField("Nova senha", validators=[Optional(), Length(min=8, max=32), senha_segura])
    confirmacao_senha = PasswordField("Confirmar nova senha", validators=[Optional(), EqualTo('senha')])
    foto_perfil = FileField("Foto de perfil")
    cargo = SelectField("Cargo / Perfil de acesso", choices=CARGOS_USUARIO, validators=[DataRequired()])
    admin = BooleanField("ADM operacional")  # mantido apenas para compatibilidade
    setor = SelectField("Setor", choices=escolhas_setores(), validators=[DataRequired()])
    ativo = BooleanField("Usuário ativo")
    tema_preferido = SelectField("Tema", choices=[("escuro", "Modo escuro"), ("claro", "Modo claro")], validators=[DataRequired()])
    empresa = StringField("Razão Social", validators=[Optional(), Length(max=120)])
    cnpj = StringField("CNPJ", validators=[Optional(), Length(max=30)])
    responsavel_empresa = StringField("Nome da pessoa / responsável", validators=[Optional(), Length(max=120)])
    botao_salvar_perfil = SubmitField("Salvar perfil")
