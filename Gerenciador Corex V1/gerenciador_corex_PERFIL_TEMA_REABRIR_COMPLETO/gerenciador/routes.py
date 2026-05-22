from gerenciador import app, database, bcrypt

from flask import (
    render_template,
    redirect,
    url_for,
    abort,
    request,
    flash
)

from gerenciador.forms import (
    FormTarefa,
    FormLogin,
    FormCriarConta,
    FormEditarUsuario,
    FormTransferirTarefa,
    FormComentario,
    FormPerfilUsuario,
    escolhas_setores
)

from gerenciador.models import (
    Tarefa,
    Usuario,
    Comentario,
    SETORES_PADRAO
)

from flask_login import (
    login_required,
    login_user,
    logout_user,
    current_user
)

import os
from datetime import datetime, time
from sqlalchemy import text, or_
from werkzeug.utils import secure_filename


SETOR_PADRAO = "Suporte Técnico"


def normalizar_setor(setor):
    setor = (setor or "").strip()
    return setor if setor in SETORES_PADRAO else SETOR_PADRAO


def migrar_banco_sem_perder_dados():
    """Adiciona novas colunas/tabelas sem apagar o banco existente."""
    with app.app_context():
        database.create_all()

        colunas_usuario = [linha[1] for linha in database.session.execute(text("PRAGMA table_info(usuario)")).fetchall()]
        colunas_tarefa = [linha[1] for linha in database.session.execute(text("PRAGMA table_info(tarefa)")).fetchall()]

        if "principal_admin" not in colunas_usuario:
            database.session.execute(text("ALTER TABLE usuario ADD COLUMN principal_admin BOOLEAN DEFAULT 0"))
        if "setor" not in colunas_usuario:
            database.session.execute(text(f"ALTER TABLE usuario ADD COLUMN setor VARCHAR DEFAULT '{SETOR_PADRAO}'"))
        if "ativo" not in colunas_usuario:
            database.session.execute(text("ALTER TABLE usuario ADD COLUMN ativo BOOLEAN DEFAULT 1"))
        if "foto_perfil" not in colunas_usuario:
            database.session.execute(text("ALTER TABLE usuario ADD COLUMN foto_perfil VARCHAR"))
        if "tema_preferido" not in colunas_usuario:
            database.session.execute(text("ALTER TABLE usuario ADD COLUMN tema_preferido VARCHAR DEFAULT 'escuro'"))

        if "encerrada_forcada" not in colunas_tarefa:
            database.session.execute(text("ALTER TABLE tarefa ADD COLUMN encerrada_forcada BOOLEAN DEFAULT 0"))
        if "setor" not in colunas_tarefa:
            database.session.execute(text(f"ALTER TABLE tarefa ADD COLUMN setor VARCHAR DEFAULT '{SETOR_PADRAO}'"))
        if "data_atualizacao" not in colunas_tarefa:
            database.session.execute(text("ALTER TABLE tarefa ADD COLUMN data_atualizacao DATETIME"))

        database.session.commit()

        primeiro_usuario = Usuario.query.order_by(Usuario.id.asc()).first()
        if primeiro_usuario:
            primeiro_usuario.admin = True
            primeiro_usuario.principal_admin = True
            primeiro_usuario.ativo = True
            primeiro_usuario.setor = normalizar_setor(primeiro_usuario.setor)

        for usuario in Usuario.query.all():
            usuario.setor = normalizar_setor(usuario.setor)
            if usuario.ativo is None:
                usuario.ativo = True
            if not getattr(usuario, "tema_preferido", None):
                usuario.tema_preferido = "escuro"

        for tarefa in Tarefa.query.all():
            if tarefa.setor not in SETORES_PADRAO:
                tarefa.setor = normalizar_setor(tarefa.usuario.setor if tarefa.usuario else None)
            if tarefa.encerrada_forcada is None:
                tarefa.encerrada_forcada = False

        database.session.commit()


migrar_banco_sem_perder_dados()


def is_adm_principal(usuario):
    return bool(usuario.is_authenticated and usuario.admin and (getattr(usuario, "principal_admin", False) or usuario.id == 1))


def setor_usuario(usuario):
    return normalizar_setor(getattr(usuario, "setor", None))


def pode_gerenciar_usuario(alvo):
    if not current_user.admin:
        return False
    if is_adm_principal(current_user):
        return True
    return (not alvo.admin) and setor_usuario(alvo) == setor_usuario(current_user)


def pode_gerenciar_tarefa(tarefa):
    if not current_user.admin:
        return False
    if is_adm_principal(current_user):
        return True
    return normalizar_setor(tarefa.setor) == setor_usuario(current_user)


def pode_visualizar_tarefa(tarefa):
    if current_user.admin and pode_gerenciar_tarefa(tarefa):
        return True
    if normalizar_setor(tarefa.setor) != setor_usuario(current_user):
        return False
    if tarefa.id_usuario == current_user.id:
        return True
    if tarefa.id_usuario is None and not tarefa.concluida and not tarefa.encerrada_forcada:
        return True
    return False


def aplicar_filtros_tarefas(consulta):
    busca = (request.args.get("q") or "").strip()
    setor_filtro = request.args.get("setor") or "todos"
    status = request.args.get("status") or "todos"

    if busca:
        consulta = consulta.filter(Tarefa.titulo.ilike(f"%{busca}%"))

    # Usuário comum jamais consegue escapar do próprio setor, mesmo tentando alterar URL.
    if current_user.admin:
        if is_adm_principal(current_user):
            if setor_filtro != "todos":
                consulta = consulta.filter(Tarefa.setor == normalizar_setor(setor_filtro))
        else:
            consulta = consulta.filter(Tarefa.setor == setor_usuario(current_user))
    else:
        consulta = consulta.filter(Tarefa.setor == setor_usuario(current_user))

    if status == "abertos":
        consulta = consulta.filter(Tarefa.concluida == False, Tarefa.encerrada_forcada == False)
    elif status == "concluidos":
        consulta = consulta.filter(Tarefa.concluida == True, Tarefa.encerrada_forcada == False)
    elif status == "forcados":
        consulta = consulta.filter(Tarefa.encerrada_forcada == True)
    elif status == "sem_responsavel":
        consulta = consulta.filter(Tarefa.id_usuario == None, Tarefa.concluida == False, Tarefa.encerrada_forcada == False)

    return consulta, busca, setor_filtro, status


def usuarios_do_escopo(apenas_funcionarios=True, setor=None):
    consulta = Usuario.query.filter_by(ativo=True)
    if apenas_funcionarios:
        consulta = consulta.filter_by(admin=False)

    if is_adm_principal(current_user):
        if setor:
            consulta = consulta.filter_by(setor=normalizar_setor(setor))
    else:
        consulta = consulta.filter_by(setor=setor_usuario(current_user))

    return consulta.order_by(Usuario.username.asc()).all()


def registrar_comentario(tarefa, texto):
    texto = (texto or "").strip()
    if texto:
        comentario = Comentario(texto=texto, tarefa=tarefa, usuario=current_user)
        database.session.add(comentario)


def configurar_form_tarefa(form):
    if not is_adm_principal(current_user):
        form.setor.data = setor_usuario(current_user)
        setores_permitidos = [setor_usuario(current_user)]
    else:
        setores_permitidos = SETORES_PADRAO

    setor_escolhido = normalizar_setor(form.setor.data or setor_usuario(current_user))
    if setor_escolhido not in setores_permitidos:
        setor_escolhido = setor_usuario(current_user)
        form.setor.data = setor_escolhido

    usuarios = usuarios_do_escopo(apenas_funcionarios=True, setor=setor_escolhido)
    form.usuario_destino.choices = [(0, "Deixar no feed / sem responsável")] + [(u.id, f"{u.username} - {u.setor}") for u in usuarios]
    return setor_escolhido


@app.context_processor
def inject_corex_context():
    return dict(setores_padrao=SETORES_PADRAO, is_adm_principal=is_adm_principal)


@app.route('/', methods=['GET', 'POST'])
def homepage():
    form = FormLogin()

    if form.validate_on_submit():
        usuario = Usuario.query.filter_by(email=form.email.data).first()
        if usuario and getattr(usuario, "ativo", True) and bcrypt.check_password_hash(usuario.senha, form.senha.data):
            login_user(usuario, remember=True)
            return redirect(url_for('homepage'))
        flash("Email ou senha inválidos, ou usuário inativo.", "erro")

    chamados_recentes = []
    if current_user.is_authenticated:
        inicio_hoje = datetime.combine(datetime.utcnow().date(), time.min)
        chamados_recentes = (
            Tarefa.query
            .filter(Tarefa.id_usuario == current_user.id)
            .filter(Tarefa.concluida == False, Tarefa.encerrada_forcada == False)
            .filter(Tarefa.data_atualizacao >= inicio_hoje)
            .order_by(Tarefa.data_atualizacao.desc(), Tarefa.id.desc())
            .limit(8)
            .all()
        )

    return render_template('homepage.html', form=form, chamados_recentes=chamados_recentes)


@app.route('/criar-conta', methods=['GET', 'POST'])
@login_required
def criarconta():
    if not current_user.admin:
        abort(403)

    form = FormCriarConta()

    if not is_adm_principal(current_user):
        form.admin.data = False
        form.setor.data = setor_usuario(current_user)

    if form.validate_on_submit():
        criar_como_admin = bool(form.admin.data and is_adm_principal(current_user))
        setor = normalizar_setor(form.setor.data if is_adm_principal(current_user) else setor_usuario(current_user))

        senha_criptografada = bcrypt.generate_password_hash(form.senha.data).decode('utf-8')
        usuario = Usuario(
            username=form.username.data,
            email=form.email.data,
            senha=senha_criptografada,
            admin=criar_como_admin,
            principal_admin=False,
            setor=setor,
            ativo=True,
            tema_preferido="escuro"
        )
        database.session.add(usuario)
        database.session.commit()
        return redirect(url_for('usuarios'))

    return render_template('criarconta.html', form=form, adm_principal=is_adm_principal(current_user))


@app.route('/usuarios')
@login_required
def usuarios():
    if not current_user.admin:
        abort(403)

    if is_adm_principal(current_user):
        lista_usuarios = Usuario.query.order_by(Usuario.admin.desc(), Usuario.setor.asc(), Usuario.username.asc()).all()
    else:
        lista_usuarios = Usuario.query.filter_by(admin=False, setor=setor_usuario(current_user)).order_by(Usuario.username.asc()).all()

    return render_template('usuarios.html', usuarios=lista_usuarios, adm_principal=is_adm_principal(current_user))


@app.route('/usuarios/<int:id_usuario>/editar', methods=['GET', 'POST'])
@login_required
def editar_usuario(id_usuario):
    if not current_user.admin:
        abort(403)

    usuario = Usuario.query.get_or_404(id_usuario)
    if not pode_gerenciar_usuario(usuario):
        abort(403)

    form = FormPerfilUsuario(obj=usuario)

    if not is_adm_principal(current_user):
        form.admin.data = False
        form.setor.data = setor_usuario(current_user)

    if form.validate_on_submit():
        usuario.username = form.username.data
        usuario.email = form.email.data
        usuario.ativo = bool(form.ativo.data)
        usuario.tema_preferido = form.tema_preferido.data or "escuro"

        if form.senha.data:
            usuario.senha = bcrypt.generate_password_hash(form.senha.data).decode('utf-8')

        if form.foto_perfil.data:
            arquivo = form.foto_perfil.data
            nome_seguro = secure_filename(arquivo.filename)
            if nome_seguro:
                nome_final = f"perfil_{usuario.id}_{nome_seguro}"
                caminho = os.path.join(os.path.abspath(os.path.dirname(__file__)), app.config['UPLOAD_FOLDER'], nome_final)
                os.makedirs(os.path.dirname(caminho), exist_ok=True)
                arquivo.save(caminho)
                usuario.foto_perfil = nome_final

        if is_adm_principal(current_user):
            usuario.admin = bool(form.admin.data)
            usuario.setor = normalizar_setor(form.setor.data)
            if usuario.id == 1:
                usuario.admin = True
                usuario.principal_admin = True
                usuario.ativo = True
        else:
            usuario.admin = False
            usuario.setor = setor_usuario(current_user)

        database.session.commit()
        return redirect(url_for('usuarios'))

    return render_template('editar_usuario.html', form=form, usuario=usuario, adm_principal=is_adm_principal(current_user))


@app.route('/gerenciador')
@login_required
def gerenciador():
    return redirect(url_for('gerenciador_interno'))


@app.route('/gerenciador/interno', methods=["GET"])
@login_required
def gerenciador_interno():
    consulta = Tarefa.query

    if not current_user.admin:
        consulta = consulta.filter_by(id_usuario=current_user.id)

    consulta, busca, setor_filtro, status = aplicar_filtros_tarefas(consulta)
    tarefas = consulta.order_by(Tarefa.id.desc()).all()

    return render_template(
        'gerenciador_interno.html',
        tarefas=tarefas,
        adm_principal=is_adm_principal(current_user),
        busca=busca,
        setor_filtro=setor_filtro,
        status=status
    )


@app.route('/feed')
@login_required
def feed():
    consulta = Tarefa.query.filter_by(id_usuario=None, concluida=False, encerrada_forcada=False)
    consulta, busca, setor_filtro, status = aplicar_filtros_tarefas(consulta)
    tarefas = consulta.order_by(Tarefa.id.desc()).all()

    return render_template('feed.html', tarefas=tarefas, busca=busca, setor_filtro=setor_filtro, status=status)


@app.route('/assumir-tarefa/<int:id_tarefa>')
@login_required
def assumir_tarefa(id_tarefa):
    tarefa = Tarefa.query.get_or_404(id_tarefa)

    if current_user.admin:
        return redirect(url_for('detalhe_tarefa', id_tarefa=tarefa.id))

    if tarefa.concluida or tarefa.encerrada_forcada or tarefa.id_usuario is not None:
        abort(403)

    if normalizar_setor(tarefa.setor) != setor_usuario(current_user):
        abort(403)

    tarefa.id_usuario = current_user.id
    registrar_comentario(tarefa, f"Chamado assumido por {current_user.username}.")
    database.session.commit()

    return redirect(url_for('detalhe_tarefa', id_tarefa=tarefa.id))


@app.route('/perfil/<id_usuario>', methods=["GET", "POST"])
@login_required
def perfil(id_usuario):
    usuario = Usuario.query.get_or_404(int(id_usuario))

    if usuario.id != current_user.id and not (current_user.admin and pode_gerenciar_usuario(usuario)):
        abort(403)

    form = None
    form_perfil = FormPerfilUsuario(obj=usuario)

    # Usuário comum vê cargo/setor/e-mail, mas não altera cargo/setor/e-mail/status.
    # ADM de setor só altera funcionários do próprio setor. ADM principal altera todos.
    if request.method == "GET":
        form_perfil.tema_preferido.data = getattr(usuario, "tema_preferido", "escuro") or "escuro"
        form_perfil.ativo.data = getattr(usuario, "ativo", True)

    if current_user.admin:
        form = FormTarefa()
        setor_escolhido = configurar_form_tarefa(form)

        if request.method == "POST" and "botao_confirmacao" in request.form and form.validate_on_submit():
            setor_tarefa = normalizar_setor(form.setor.data if is_adm_principal(current_user) else setor_usuario(current_user))
            usuario_destino = Usuario.query.get(form.usuario_destino.data) if form.usuario_destino.data else None

            if usuario_destino:
                if not usuario_destino.ativo or usuario_destino.admin:
                    abort(403)
                if setor_usuario(usuario_destino) != setor_tarefa:
                    abort(403)
                if not is_adm_principal(current_user) and setor_tarefa != setor_usuario(current_user):
                    abort(403)

            nome_imagem = None
            if form.foto.data:
                arquivo = form.foto.data
                nome_seguro = secure_filename(arquivo.filename)
                if nome_seguro:
                    caminho = os.path.join(os.path.abspath(os.path.dirname(__file__)), app.config['UPLOAD_FOLDER'], nome_seguro)
                    os.makedirs(os.path.dirname(caminho), exist_ok=True)
                    arquivo.save(caminho)
                    nome_imagem = nome_seguro

            tarefa = Tarefa(
                titulo=form.titulo.data,
                descricao=form.descricao.data,
                imagem=nome_imagem,
                id_usuario=usuario_destino.id if usuario_destino else None,
                setor=setor_tarefa
            )
            database.session.add(tarefa)
            database.session.flush()
            registrar_comentario(tarefa, f"Chamado criado por {current_user.username} no setor {setor_tarefa}.")
            database.session.commit()
            return redirect(url_for('detalhe_tarefa', id_tarefa=tarefa.id))

    return render_template('perfil.html', usuario=usuario, form=form, form_perfil=form_perfil, adm_principal=is_adm_principal(current_user))


@app.route('/perfil/<int:id_usuario>/atualizar', methods=['POST'])
@login_required
def atualizar_perfil(id_usuario):
    usuario = Usuario.query.get_or_404(id_usuario)

    if usuario.id != current_user.id and not (current_user.admin and pode_gerenciar_usuario(usuario)):
        abort(403)

    form = FormPerfilUsuario()
    if form.validate_on_submit():
        # Todos podem alterar o próprio nome, senha, foto e preferência de tema.
        # ADM pode alterar nome/foto/senha/tema do usuário gerenciado.
        usuario.username = form.username.data
        usuario.tema_preferido = form.tema_preferido.data or "escuro"

        if form.senha.data:
            usuario.senha = bcrypt.generate_password_hash(form.senha.data).decode('utf-8')

        if form.foto_perfil.data:
            arquivo = form.foto_perfil.data
            nome_seguro = secure_filename(arquivo.filename)
            if nome_seguro:
                nome_final = f"perfil_{usuario.id}_{nome_seguro}"
                caminho = os.path.join(os.path.abspath(os.path.dirname(__file__)), app.config['UPLOAD_FOLDER'], nome_final)
                os.makedirs(os.path.dirname(caminho), exist_ok=True)
                arquivo.save(caminho)
                usuario.foto_perfil = nome_final

        if current_user.admin and pode_gerenciar_usuario(usuario):
            usuario.email = form.email.data
            usuario.ativo = bool(form.ativo.data)
            if is_adm_principal(current_user):
                usuario.admin = bool(form.admin.data)
                usuario.setor = normalizar_setor(form.setor.data)
                if usuario.id == 1:
                    usuario.admin = True
                    usuario.principal_admin = True
                    usuario.ativo = True
            else:
                usuario.admin = False
                usuario.setor = setor_usuario(current_user)
        else:
            # Funcionário não altera e-mail, cargo, setor nem status por POST manual.
            usuario.email = usuario.email

        database.session.commit()
        flash("Perfil atualizado com sucesso.", "ok")

    return redirect(url_for('perfil', id_usuario=usuario.id))


@app.route('/alternar-tema')
@login_required
def alternar_tema():
    atual = getattr(current_user, "tema_preferido", "escuro") or "escuro"
    current_user.tema_preferido = "claro" if atual == "escuro" else "escuro"
    database.session.commit()
    return redirect(request.referrer or url_for('perfil', id_usuario=current_user.id))


@app.route('/tarefa/<int:id_tarefa>', methods=['GET'])
@login_required
def detalhe_tarefa(id_tarefa):
    tarefa = Tarefa.query.get_or_404(id_tarefa)
    if not pode_visualizar_tarefa(tarefa):
        abort(403)

    form_comentario = FormComentario()
    form_transferir = FormTransferirTarefa()

    if current_user.admin:
        form_transferir.setor_destino.data = normalizar_setor(tarefa.setor)
        usuarios = usuarios_do_escopo(apenas_funcionarios=True, setor=normalizar_setor(tarefa.setor))
        form_transferir.usuario_destino.choices = [(0, "Deixar sem responsável no feed do setor")] + [(u.id, f"{u.username} - {u.setor}") for u in usuarios]
    else:
        form_transferir.usuario_destino.choices = []

    return render_template(
        'detalhe_tarefa.html',
        tarefa=tarefa,
        form_comentario=form_comentario,
        form_transferir=form_transferir,
        pode_admin=pode_gerenciar_tarefa(tarefa)
    )


@app.route('/tarefa/<int:id_tarefa>/comentar', methods=['POST'])
@login_required
def comentar_tarefa(id_tarefa):
    tarefa = Tarefa.query.get_or_404(id_tarefa)
    if not pode_visualizar_tarefa(tarefa):
        abort(403)

    form = FormComentario()
    if form.validate_on_submit():
        registrar_comentario(tarefa, form.texto.data)
        database.session.commit()

    return redirect(url_for('detalhe_tarefa', id_tarefa=tarefa.id))


@app.route('/tarefa/<int:id_tarefa>/transferir', methods=['POST'])
@login_required
def transferir_tarefa(id_tarefa):
    tarefa = Tarefa.query.get_or_404(id_tarefa)
    if not pode_gerenciar_tarefa(tarefa):
        abort(403)

    form = FormTransferirTarefa()
    setor_destino = normalizar_setor(request.form.get('setor_destino'))

    if not is_adm_principal(current_user) and setor_destino != setor_usuario(current_user):
        abort(403)

    usuarios = usuarios_do_escopo(apenas_funcionarios=True, setor=setor_destino)
    form.usuario_destino.choices = [(0, "Deixar sem responsável no feed do setor")] + [(u.id, f"{u.username} - {u.setor}") for u in usuarios]

    if form.validate_on_submit():
        antigo_setor = normalizar_setor(tarefa.setor)
        antigo_resp = tarefa.usuario.username if tarefa.usuario else "sem responsável"
        novo_usuario = Usuario.query.get(form.usuario_destino.data) if form.usuario_destino.data else None

        if novo_usuario:
            if novo_usuario.admin or not novo_usuario.ativo or setor_usuario(novo_usuario) != setor_destino:
                abort(403)

        tarefa.setor = setor_destino
        tarefa.id_usuario = novo_usuario.id if novo_usuario else None
        tarefa.concluida = False
        tarefa.encerrada_forcada = False

        novo_resp = novo_usuario.username if novo_usuario else "sem responsável"
        registrar_comentario(tarefa, f"Chamado atualizado por {current_user.username}: setor {antigo_setor} → {setor_destino}; responsável {antigo_resp} → {novo_resp}.")
        registrar_comentario(tarefa, form.comentario.data)
        database.session.commit()

    return redirect(url_for('detalhe_tarefa', id_tarefa=tarefa.id))


@app.route('/concluir-tarefa/<int:id_tarefa>')
@login_required
def concluir_tarefa(id_tarefa):
    tarefa = Tarefa.query.get_or_404(id_tarefa)

    if tarefa.id_usuario != current_user.id and not pode_gerenciar_tarefa(tarefa):
        abort(403)

    if not current_user.admin and normalizar_setor(tarefa.setor) != setor_usuario(current_user):
        abort(403)

    tarefa.concluida = True
    tarefa.encerrada_forcada = False
    registrar_comentario(tarefa, f"Chamado concluído por {current_user.username}.")
    database.session.commit()

    return redirect(url_for('detalhe_tarefa', id_tarefa=tarefa.id))


@app.route('/forcar-encerramento/<int:id_tarefa>')
@login_required
def forcar_encerramento(id_tarefa):
    tarefa = Tarefa.query.get_or_404(id_tarefa)
    if not pode_gerenciar_tarefa(tarefa):
        abort(403)

    tarefa.concluida = True
    tarefa.encerrada_forcada = True
    registrar_comentario(tarefa, f"Encerramento forçado pelo administrador {current_user.username}.")
    database.session.commit()

    return redirect(url_for('detalhe_tarefa', id_tarefa=tarefa.id))



@app.route('/reabrir-tarefa/<int:id_tarefa>')
@login_required
def reabrir_tarefa(id_tarefa):
    tarefa = Tarefa.query.get_or_404(id_tarefa)

    if tarefa.id_usuario != current_user.id and not pode_gerenciar_tarefa(tarefa):
        abort(403)

    if not current_user.admin and normalizar_setor(tarefa.setor) != setor_usuario(current_user):
        abort(403)

    tarefa.concluida = False
    tarefa.encerrada_forcada = False
    registrar_comentario(tarefa, f"Chamado reaberto por {current_user.username}.")
    database.session.commit()

    return redirect(url_for('detalhe_tarefa', id_tarefa=tarefa.id))


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('homepage'))
