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

from gerenciador.models import Usuario, SETORES_PADRAO


def escolhas_setores(com_todos=False):
    opcoes = [(setor, setor) for setor in SETORES_PADRAO]
    if com_todos:
        return [("todos", "Todos os setores")] + opcoes
    return opcoes


class FormLogin(FlaskForm):
    email = StringField("Email", validators=[DataRequired(), Email()])
    senha = PasswordField("Senha", validators=[DataRequired()])
    botao_confirmacao = SubmitField("Login")


class FormCriarConta(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
    username = StringField('Usuário', validators=[DataRequired(), Length(min=3, max=30)])
    senha = PasswordField('Senha', validators=[DataRequired(), Length(min=6, max=32)])
    confirmacao_senha = PasswordField('Confirme a senha', validators=[DataRequired(), EqualTo('senha')])
    admin = BooleanField("Criar como administrador")
    setor = SelectField("Setor", choices=escolhas_setores(), validators=[DataRequired()])
    botao_confirmacao = SubmitField('Confirmar')

    def validate_email(self, email):
        usuario = Usuario.query.filter_by(email=email.data).first()
        if usuario:
            raise ValidationError("Email já cadastrado.")


class FormEditarUsuario(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
    username = StringField('Usuário', validators=[DataRequired(), Length(min=3, max=30)])
    admin = BooleanField("Administrador")
    setor = SelectField("Setor", choices=escolhas_setores(), validators=[DataRequired()])
    ativo = BooleanField("Usuário ativo")
    botao_confirmacao = SubmitField('Salvar alterações')


class FormTarefa(FlaskForm):
    titulo = StringField("Título / Defeito", validators=[DataRequired()])
    descricao = TextAreaField("Descrição", validators=[Optional()])
    setor = SelectField("Setor do chamado", choices=escolhas_setores(), validators=[DataRequired()])
    foto = FileField("Foto (opcional)")
    usuario_destino = SelectField("Usuário responsável", coerce=int)
    botao_confirmacao = SubmitField("Criar Chamado")


class FormTransferirTarefa(FlaskForm):
    setor_destino = SelectField("Setor do chamado", choices=escolhas_setores(), validators=[DataRequired()])
    usuario_destino = SelectField("Transferir para", coerce=int, validators=[Optional()])
    comentario = TextAreaField("Motivo/observação da transferência", validators=[Optional()])
    botao_confirmacao = SubmitField("Salvar transferência")


class FormComentario(FlaskForm):
    texto = TextAreaField("Comentário", validators=[DataRequired(), Length(min=2, max=2000)])
    botao_confirmacao = SubmitField("Adicionar comentário")


class FormPerfilUsuario(FlaskForm):
    username = StringField("Nome", validators=[DataRequired(), Length(min=3, max=30)])
    email = StringField("Email cadastrado", validators=[DataRequired(), Email()])
    senha = PasswordField("Nova senha", validators=[Optional(), Length(min=6, max=32)])
    confirmacao_senha = PasswordField("Confirmar nova senha", validators=[Optional(), EqualTo('senha')])
    foto_perfil = FileField("Foto de perfil")
    admin = BooleanField("Administrador")
    setor = SelectField("Setor", choices=escolhas_setores(), validators=[DataRequired()])
    ativo = BooleanField("Usuário ativo")
    tema_preferido = SelectField("Tema", choices=[("escuro", "Modo escuro"), ("claro", "Modo claro")], validators=[DataRequired()])
    botao_salvar_perfil = SubmitField("Salvar perfil")
