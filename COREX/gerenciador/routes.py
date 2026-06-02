from gerenciador import app, database, bcrypt

from flask import (
    render_template,
    redirect,
    url_for,
    abort,
    request,
    flash,
    make_response,
    send_file
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
    Notificacao,
    SETORES_PADRAO,
    nome_cargo
)

from flask_login import (
    login_required,
    login_user,
    logout_user,
    current_user
)

import os
import uuid
from io import BytesIO
from datetime import datetime, time
from sqlalchemy import text, or_, func
from werkzeug.utils import secure_filename
from werkzeug.exceptions import RequestEntityTooLarge

try:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_LEFT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, PageBreak
    )
    from reportlab.pdfbase.pdfmetrics import stringWidth
    REPORTLAB_DISPONIVEL = True
except Exception:
    REPORTLAB_DISPONIVEL = False


def _pdf_escape_text(valor):
    valor = "" if valor is None else str(valor)
    valor = valor.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    return valor

def gerar_pdf_nativo_chamado(tarefa):
    """Gera um PDF bonito sem dependências externas.
    Mantém o botão Baixar funcionando mesmo quando ReportLab não está instalado.
    """
    PAGE_W, PAGE_H = 595, 842
    MARGIN = 42
    NAVY = "0.02 0.08 0.17"
    BLUE = "0.10 0.35 0.85"
    LIGHT_BLUE = "0.90 0.95 1.00"
    LIGHT = "0.96 0.98 1.00"
    BORDER = "0.78 0.84 0.92"
    TEXT = "0.08 0.12 0.20"
    MUTED = "0.39 0.45 0.55"
    WHITE = "1 1 1"

    def data_fmt(data):
        try:
            return data.strftime('%d/%m/%Y %H:%M')
        except Exception:
            return 'Não informado'

    def limpar(valor):
        valor = '' if valor is None else str(valor)
        return valor.replace('\r', '').replace('\t', '    ').strip()

    def escape(valor):
        valor = '' if valor is None else str(valor)
        valor = valor.encode('latin-1', 'replace').decode('latin-1')
        return valor.replace('\\', '\\\\').replace('(', '\\(').replace(')', '\\)')

    def wrap(texto, limite=82):
        texto = limpar(texto)
        if not texto:
            return ['Não informado']
        linhas = []
        for bloco in texto.split('\n'):
            palavras = bloco.split()
            atual = ''
            for palavra in palavras:
                if len(atual) + len(palavra) + 1 <= limite:
                    atual = (atual + ' ' + palavra).strip()
                else:
                    if atual:
                        linhas.append(atual)
                    while len(palavra) > limite:
                        linhas.append(palavra[:limite])
                        palavra = palavra[limite:]
                    atual = palavra
            if atual:
                linhas.append(atual)
            if not palavras:
                linhas.append('')
        return linhas or ['Não informado']

    ticket = getattr(tarefa, 'numero_ticket', None) or f"CRX-{tarefa.id:06d}"
    solicitante_obj = getattr(tarefa, 'solicitante', None)
    solicitante = solicitante_obj.username if solicitante_obj else 'Não informado'
    responsavel = tarefa.usuario.username if getattr(tarefa, 'usuario', None) else 'Sem responsável / Fila Geral'

    if getattr(tarefa, 'encerrada_forcada', False):
        status = 'Encerrado pelo administrador'
    elif getattr(tarefa, 'concluida', False):
        status = 'Concluído'
    elif getattr(tarefa, 'status', '') == 'aguardando_cliente':
        status = 'Aguardando cliente'
    elif getattr(tarefa, 'usuario', None):
        status = 'Em atendimento'
    else:
        status = 'Aberto / Fila Geral'

    empresa = getattr(solicitante_obj, 'empresa', None) or 'Dados empresariais não cadastrados'
    cnpj = getattr(solicitante_obj, 'cnpj', None) or 'Dados empresariais não cadastrados'
    resp_empresa = getattr(solicitante_obj, 'responsavel_empresa', None) or solicitante
    email = getattr(solicitante_obj, 'email', None) or 'Não informado'

    campos_resumo = [
        ('Ticket', ticket),
        ('Status', status),
        ('Título', getattr(tarefa, 'titulo', '') or 'Não informado'),
        ('Categoria', getattr(tarefa, 'categoria', None) or 'Suporte Geral'),
        ('Prioridade', getattr(tarefa, 'prioridade', None) or 'Média'),
        ('Local/Setor do problema', getattr(tarefa, 'setor_cliente', None) or 'Não informado'),
        ('Solicitante', solicitante),
        ('Responsável CoreX', responsavel),
        ('Data de abertura', data_fmt(getattr(tarefa, 'data_criacao', None))),
    ]

    campos_empresa = [
        ('Empresa', empresa),
        ('CNPJ', cnpj),
        ('Responsável', resp_empresa),
        ('E-mail', email),
    ]

    comentarios = sorted(list(getattr(tarefa, 'comentarios', []) or []), key=lambda c: c.data_criacao or datetime.utcnow())

    paginas = []
    cmds = []
    y = PAGE_H - 42

    def cmd(c):
        cmds.append(c)

    def color_rgb(rgb, stroke=False):
        cmd(f"{rgb} {'RG' if stroke else 'rg'}")

    def rect(x, y, w, h, fill=None, stroke=None, width=1):
        if fill:
            color_rgb(fill)
            cmd(f"{x:.1f} {y:.1f} {w:.1f} {h:.1f} re f")
        if stroke:
            color_rgb(stroke, stroke=True)
            cmd(f"{width:.1f} w {x:.1f} {y:.1f} {w:.1f} {h:.1f} re S")

    def text(x, y, texto, size=10, font='F1', color=TEXT):
        color_rgb(color)
        cmd('BT')
        cmd(f'/{font} {size} Tf')
        cmd(f'{x:.1f} {y:.1f} Td')
        cmd(f'({escape(texto)}) Tj')
        cmd('ET')

    def line(x1, y1, x2, y2, color=BORDER, width=0.6):
        color_rgb(color, stroke=True)
        cmd(f"{width:.1f} w {x1:.1f} {y1:.1f} m {x2:.1f} {y2:.1f} l S")

    def new_page():
        nonlocal cmds, y
        if cmds:
            footer()
            paginas.append(cmds)
        cmds = []
        y = PAGE_H - 42
        header()

    def header():
        nonlocal y
        rect(0, PAGE_H - 96, PAGE_W, 96, fill=NAVY)
        rect(MARGIN, PAGE_H - 76, 44, 44, fill=BLUE)
        text(MARGIN + 11, PAGE_H - 61, 'CX', size=18, font='F2', color=WHITE)
        text(MARGIN + 58, PAGE_H - 48, 'COREX SERVICE DESK', size=17, font='F2', color=WHITE)
        text(MARGIN + 58, PAGE_H - 66, 'Relatório estruturado de chamado', size=9, font='F1', color='0.78 0.84 0.92')
        text(PAGE_W - 205, PAGE_H - 48, ticket, size=13, font='F2', color=WHITE)
        text(PAGE_W - 205, PAGE_H - 66, f'Emitido em {datetime.utcnow().strftime("%d/%m/%Y %H:%M")}', size=8, font='F1', color='0.78 0.84 0.92')
        y = PAGE_H - 122

    def footer():
        rect(0, 0, PAGE_W, 35, fill=LIGHT)
        text(MARGIN, 15, 'Documento gerado automaticamente pelo Portal CoreX', size=8, font='F1', color=MUTED)
        text(PAGE_W - 145, 15, f'Página {len(paginas) + 1}', size=8, font='F1', color=MUTED)

    def ensure(space):
        nonlocal y
        if y - space < 58:
            new_page()

    def section(title):
        nonlocal y
        # Espaçamento maior entre blocos para evitar títulos colados na tabela anterior.
        y -= 12
        ensure(52)
        rect(MARGIN, y - 20, PAGE_W - 2 * MARGIN, 26, fill=LIGHT_BLUE, stroke=BORDER, width=0.4)
        text(MARGIN + 12, y - 11, title.upper(), size=11, font='F2', color=BLUE)
        y -= 38

    def info_table(rows):
        nonlocal y
        row_h = 26
        w_label = 150
        w_val = PAGE_W - (2 * MARGIN) - w_label
        ensure(len(rows) * row_h + 12)
        for i, (label, val) in enumerate(rows):
            x = MARGIN
            yy = y - row_h
            rect(x, yy, w_label, row_h, fill=LIGHT_BLUE, stroke=BORDER, width=0.4)
            rect(x + w_label, yy, w_val, row_h, fill=WHITE, stroke=BORDER, width=0.4)
            text(x + 9, yy + 9, label, size=8, font='F2', color=MUTED)
            valor = limpar(val)
            if len(valor) > 68:
                valor = valor[:65] + '...'
            text(x + w_label + 9, yy + 9, valor, size=9, font='F1', color=TEXT)
            y -= row_h
        # Respiro entre tabela e próxima seção.
        y -= 24

    def paragraph_box(title, body):
        nonlocal y
        linhas = wrap(body, 88)
        box_h = 30 + len(linhas) * 13
        ensure(box_h + 18)
        rect(MARGIN, y - box_h, PAGE_W - 2 * MARGIN, box_h, fill=WHITE, stroke=BORDER, width=0.6)
        rect(MARGIN, y - 24, PAGE_W - 2 * MARGIN, 24, fill=LIGHT_BLUE)
        text(MARGIN + 12, y - 16, title, size=10, font='F2', color=BLUE)
        ty = y - 42
        for linha in linhas:
            text(MARGIN + 12, ty, linha, size=9, font='F1', color=TEXT)
            ty -= 13
        # Mais espaço após caixas de texto longas.
        y -= box_h + 24

    def timeline():
        nonlocal y
        if not comentarios:
            paragraph_box('Histórico e comentários', 'Nenhum comentário registrado.')
            return
        for c in comentarios:
            autor = c.usuario.username if getattr(c, 'usuario', None) else 'Usuário'
            data = data_fmt(getattr(c, 'data_criacao', None))
            linhas = wrap(getattr(c, 'texto', ''), 76)
            h = 42 + len(linhas) * 12
            ensure(h + 8)
            rect(MARGIN + 8, y - h, 2, h, fill=BLUE)
            rect(MARGIN + 2, y - 18, 14, 14, fill=BLUE)
            rect(MARGIN + 24, y - h, PAGE_W - 2 * MARGIN - 24, h, fill=WHITE, stroke=BORDER, width=0.5)
            text(MARGIN + 36, y - 18, f'{data}  •  {autor}', size=9, font='F2', color=TEXT)
            ty = y - 36
            for linha in linhas:
                text(MARGIN + 36, ty, linha, size=8.7, font='F1', color=TEXT)
                ty -= 12
            y -= h + 10

    new_page()
    section('Resumo do chamado')
    info_table(campos_resumo)
    section('Empresa cliente')
    info_table(campos_empresa)
    section('Descrição do problema')
    paragraph_box('Descrição informada no chamado', getattr(tarefa, 'descricao', None) or 'Sem descrição detalhada.')

    if getattr(tarefa, 'imagem', None):
        section('Anexo')
        paragraph_box('Imagem anexada', f'Este chamado possui uma imagem anexada: {tarefa.imagem}. Abra o chamado no Portal CoreX para visualizar o arquivo original.')

    section('Histórico e comentários')
    timeline()

    if cmds:
        footer()
        paginas.append(cmds)

    objetos = []
    page_ids = []
    content_ids = []
    next_id = 5
    for _ in paginas:
        page_ids.append(next_id); next_id += 1
        content_ids.append(next_id); next_id += 1

    for page_num, page_cmds in enumerate(paginas):
        stream = ('\n'.join(page_cmds)).encode('latin-1', 'replace')
        objetos.append((content_ids[page_num], b'<< /Length ' + str(len(stream)).encode() + b' >>\nstream\n' + stream + b'\nendstream'))

    kids = ' '.join(f'{pid} 0 R' for pid in page_ids)
    objetos_base = [
        (1, b'<< /Type /Catalog /Pages 2 0 R >>'),
        (2, f'<< /Type /Pages /Kids [{kids}] /Count {len(page_ids)} >>'.encode()),
        (3, b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>'),
        (4, b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>'),
    ]
    page_objs = []
    for pid, cid in zip(page_ids, content_ids):
        page_objs.append((pid, f'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {PAGE_W} {PAGE_H}] /Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> /Contents {cid} 0 R >>'.encode()))

    all_objs = sorted(objetos_base + page_objs + objetos, key=lambda x: x[0])
    pdf = bytearray(b'%PDF-1.4\n')
    offsets = {0: 0}
    for obj_id, body in all_objs:
        offsets[obj_id] = len(pdf)
        pdf.extend(f'{obj_id} 0 obj\n'.encode())
        pdf.extend(body)
        pdf.extend(b'\nendobj\n')

    xref_pos = len(pdf)
    max_id = max(obj_id for obj_id, _ in all_objs)
    pdf.extend(f'xref\n0 {max_id + 1}\n'.encode())
    pdf.extend(b'0000000000 65535 f \n')
    for obj_id in range(1, max_id + 1):
        pdf.extend(f'{offsets.get(obj_id, 0):010d} 00000 n \n'.encode())
    pdf.extend(f'trailer\n<< /Size {max_id + 1} /Root 1 0 R >>\nstartxref\n{xref_pos}\n%%EOF'.encode())
    return bytes(pdf)


SETOR_PADRAO = "Suporte Técnico"


EXTENSOES_IMAGEM_PERMITIDAS = {"png", "jpg", "jpeg", "gif", "webp"}


def flash_form_errors(form):
    """Mostra erros de validação de forma amigável para o usuário."""
    for campo, erros in form.errors.items():
        rotulo = getattr(getattr(form, campo, None), "label", None)
        nome_campo = rotulo.text if rotulo else campo
        for erro in erros:
            flash(f"{nome_campo}: {erro}", "erro")


def salvar_imagem_upload(arquivo):
    if not arquivo or not getattr(arquivo, "filename", ""):
        return None

    nome_seguro = secure_filename(arquivo.filename)
    if not nome_seguro or "." not in nome_seguro:
        flash("Arquivo ignorado: envie uma imagem válida.", "erro")
        return None

    extensao = nome_seguro.rsplit(".", 1)[1].lower()
    if extensao not in EXTENSOES_IMAGEM_PERMITIDAS:
        flash("Arquivo ignorado: formatos permitidos: PNG, JPG, JPEG, GIF ou WEBP.", "erro")
        return None

    nome_final = f"chamado_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:8]}.{extensao}"
    pasta_upload = os.path.join(os.path.abspath(os.path.dirname(__file__)), app.config['UPLOAD_FOLDER'])
    os.makedirs(pasta_upload, exist_ok=True)
    arquivo.save(os.path.join(pasta_upload, nome_final))
    return nome_final


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
        if "cargo" not in colunas_usuario:
            database.session.execute(text("ALTER TABLE usuario ADD COLUMN cargo VARCHAR DEFAULT 'CLIENTE'"))
        if "setor" not in colunas_usuario:
            database.session.execute(text(f"ALTER TABLE usuario ADD COLUMN setor VARCHAR DEFAULT '{SETOR_PADRAO}'"))
        if "ativo" not in colunas_usuario:
            database.session.execute(text("ALTER TABLE usuario ADD COLUMN ativo BOOLEAN DEFAULT 1"))
        if "data_criacao" not in colunas_usuario:
            database.session.execute(text("ALTER TABLE usuario ADD COLUMN data_criacao DATETIME"))
        if "foto_perfil" not in colunas_usuario:
            database.session.execute(text("ALTER TABLE usuario ADD COLUMN foto_perfil VARCHAR"))
        if "tema_preferido" not in colunas_usuario:
            database.session.execute(text("ALTER TABLE usuario ADD COLUMN tema_preferido VARCHAR DEFAULT 'escuro'"))
        if "empresa" not in colunas_usuario:
            database.session.execute(text("ALTER TABLE usuario ADD COLUMN empresa VARCHAR"))
        if "cnpj" not in colunas_usuario:
            database.session.execute(text("ALTER TABLE usuario ADD COLUMN cnpj VARCHAR"))
        if "responsavel_empresa" not in colunas_usuario:
            database.session.execute(text("ALTER TABLE usuario ADD COLUMN responsavel_empresa VARCHAR"))

        if "encerrada_forcada" not in colunas_tarefa:
            database.session.execute(text("ALTER TABLE tarefa ADD COLUMN encerrada_forcada BOOLEAN DEFAULT 0"))
        if "setor" not in colunas_tarefa:
            database.session.execute(text(f"ALTER TABLE tarefa ADD COLUMN setor VARCHAR DEFAULT '{SETOR_PADRAO}'"))
        if "setor_cliente" not in colunas_tarefa:
            database.session.execute(text("ALTER TABLE tarefa ADD COLUMN setor_cliente VARCHAR"))
        if "data_atualizacao" not in colunas_tarefa:
            database.session.execute(text("ALTER TABLE tarefa ADD COLUMN data_atualizacao DATETIME"))
        if "id_solicitante" not in colunas_tarefa:
            database.session.execute(text("ALTER TABLE tarefa ADD COLUMN id_solicitante INTEGER"))
        if "categoria" not in colunas_tarefa:
            database.session.execute(text("ALTER TABLE tarefa ADD COLUMN categoria VARCHAR DEFAULT 'Suporte Geral'"))
        if "prioridade" not in colunas_tarefa:
            database.session.execute(text("ALTER TABLE tarefa ADD COLUMN prioridade VARCHAR DEFAULT 'Média'"))
        if "status" not in colunas_tarefa:
            database.session.execute(text("ALTER TABLE tarefa ADD COLUMN status VARCHAR DEFAULT 'aberto'"))
        if "numero_ticket" not in colunas_tarefa:
            database.session.execute(text("ALTER TABLE tarefa ADD COLUMN numero_ticket VARCHAR"))

        database.session.commit()

        primeiro_usuario = Usuario.query.order_by(Usuario.id.asc()).first()
        if primeiro_usuario:
            primeiro_usuario.admin = True
            primeiro_usuario.principal_admin = True
            primeiro_usuario.cargo = "SUPER_ADMIN"
            primeiro_usuario.ativo = True
            primeiro_usuario.setor = normalizar_setor(primeiro_usuario.setor)

        for usuario in Usuario.query.all():
            usuario.setor = normalizar_setor(usuario.setor)
            if usuario.ativo is None:
                usuario.ativo = True
            if not getattr(usuario, "data_criacao", None):
                usuario.data_criacao = datetime.utcnow()
            if not getattr(usuario, "tema_preferido", None):
                usuario.tema_preferido = "escuro"
            # Migração automática do modelo antigo admin/principal_admin para cargos profissionais.
            cargo_atual = getattr(usuario, "cargo", None)
            if getattr(usuario, "principal_admin", False) or usuario.id == 1:
                usuario.cargo = "SUPER_ADMIN"
            elif getattr(usuario, "admin", False) and cargo_atual not in ["ADMIN_COREX", "TECNICO_COREX"]:
                usuario.cargo = "ADMIN_COREX"
            elif cargo_atual not in ["SUPER_ADMIN", "ADMIN_COREX", "TECNICO_COREX", "CLIENTE"]:
                usuario.cargo = "CLIENTE"

            if usuario.cargo == "SUPER_ADMIN":
                usuario.admin = True
                usuario.principal_admin = True
            elif usuario.cargo == "ADMIN_COREX":
                usuario.admin = True
                usuario.principal_admin = False
            else:
                usuario.admin = False
                usuario.principal_admin = False

        for tarefa in Tarefa.query.all():
            if tarefa.setor not in SETORES_PADRAO:
                tarefa.setor = normalizar_setor(tarefa.usuario.setor if tarefa.usuario else None)
            if tarefa.encerrada_forcada is None:
                tarefa.encerrada_forcada = False
            # Compatibilidade com chamados antigos: se não havia solicitante salvo,
            # mantém o responsável antigo também como solicitante apenas para não perder acesso.
            if getattr(tarefa, "id_solicitante", None) is None and tarefa.id_usuario is not None:
                tarefa.id_solicitante = tarefa.id_usuario
            if not getattr(tarefa, "categoria", None):
                tarefa.categoria = "Suporte Geral"
            if not getattr(tarefa, "prioridade", None):
                tarefa.prioridade = "Média"
            if not getattr(tarefa, "status", None):
                tarefa.status = "concluido" if tarefa.concluida else "aberto"
            if not getattr(tarefa, "numero_ticket", None):
                tarefa.numero_ticket = f"CRX-{tarefa.data_criacao.year if tarefa.data_criacao else datetime.utcnow().year}-{tarefa.id:06d}"

        database.session.commit()


migrar_banco_sem_perder_dados()


def cargo_usuario(usuario):
    if not usuario or not getattr(usuario, "is_authenticated", False):
        return "CLIENTE"
    if getattr(usuario, "principal_admin", False) or getattr(usuario, "id", None) == 1 or getattr(usuario, "cargo", None) == "SUPER_ADMIN":
        return "SUPER_ADMIN"
    cargo = getattr(usuario, "cargo", None)
    if cargo in ["ADMIN_COREX", "TECNICO_COREX", "CLIENTE"]:
        return cargo
    # Compatibilidade com versões antigas.
    return "ADMIN_COREX" if getattr(usuario, "admin", False) else "CLIENTE"


def sincronizar_flags_usuario(usuario):
    cargo = cargo_usuario(usuario)
    usuario.cargo = cargo
    usuario.admin = cargo in ["SUPER_ADMIN", "ADMIN_COREX"]
    usuario.principal_admin = cargo == "SUPER_ADMIN"


def is_adm_principal(usuario):
    return bool(usuario.is_authenticated and cargo_usuario(usuario) == "SUPER_ADMIN")


def is_admin_corex(usuario):
    return bool(usuario.is_authenticated and cargo_usuario(usuario) in ["SUPER_ADMIN", "ADMIN_COREX"])


def is_tecnico_corex(usuario):
    return bool(usuario.is_authenticated and cargo_usuario(usuario) == "TECNICO_COREX")


def is_equipe_corex(usuario):
    return bool(usuario.is_authenticated and cargo_usuario(usuario) in ["SUPER_ADMIN", "ADMIN_COREX", "TECNICO_COREX"])


def pode_gerenciar_usuarios():
    return is_admin_corex(current_user)


def setor_usuario(usuario):
    return normalizar_setor(getattr(usuario, "setor", None))


def filtro_historico_cliente(usuario):
    """Permite que um novo colaborador da mesma empresa veja o histórico anterior.
    Prioridade: CNPJ quando existir; se não houver, usa o nome da empresa.
    """
    filtros = [Tarefa.id_solicitante == usuario.id]
    cnpj = (getattr(usuario, "cnpj", None) or "").strip()
    empresa = (getattr(usuario, "empresa", None) or "").strip()

    if cnpj:
        filtros.append(Tarefa.solicitante.has(Usuario.cnpj == cnpj))
    elif empresa:
        filtros.append(Tarefa.solicitante.has(Usuario.empresa == empresa))

    return or_(*filtros)


def mesma_empresa_cliente(tarefa, usuario):
    solicitante = getattr(tarefa, "solicitante", None)
    if not solicitante:
        return False

    cnpj_usuario = (getattr(usuario, "cnpj", None) or "").strip()
    cnpj_solicitante = (getattr(solicitante, "cnpj", None) or "").strip()
    if cnpj_usuario and cnpj_solicitante and cnpj_usuario == cnpj_solicitante:
        return True

    empresa_usuario = (getattr(usuario, "empresa", None) or "").strip().lower()
    empresa_solicitante = (getattr(solicitante, "empresa", None) or "").strip().lower()
    return bool(empresa_usuario and empresa_solicitante and empresa_usuario == empresa_solicitante)


def pode_gerenciar_usuario(alvo):
    if not pode_gerenciar_usuarios():
        return False
    if is_adm_principal(current_user):
        return True
    # Admin CoreX gerencia técnicos e clientes do próprio setor. Não gerencia outros admins nem super admin.
    return cargo_usuario(alvo) in ["TECNICO_COREX", "CLIENTE"] and setor_usuario(alvo) == setor_usuario(current_user)


def pode_gerenciar_tarefa(tarefa):
    cargo = cargo_usuario(current_user)
    if cargo == "SUPER_ADMIN":
        return True
    if cargo == "ADMIN_COREX":
        # Admin CoreX pode tratar chamados da própria área e também chamados novos sem responsável da Fila Geral.
        return normalizar_setor(tarefa.setor) == setor_usuario(current_user) or (tarefa.id_usuario is None and not tarefa.concluida and not tarefa.encerrada_forcada)
    if cargo == "TECNICO_COREX":
        return tarefa.id_usuario == current_user.id
    return False


def pode_visualizar_tarefa(tarefa):
    cargo = cargo_usuario(current_user)
    if cargo == "SUPER_ADMIN":
        return True
    if cargo == "ADMIN_COREX" and (normalizar_setor(tarefa.setor) == setor_usuario(current_user) or (tarefa.id_usuario is None and not tarefa.concluida and not tarefa.encerrada_forcada)):
        return True
    if cargo == "TECNICO_COREX" and (tarefa.id_usuario == current_user.id or tarefa.id_solicitante == current_user.id or (tarefa.id_usuario is None and not tarefa.concluida and not tarefa.encerrada_forcada)):
        return True
    if tarefa.id_solicitante == current_user.id:
        return True
    if cargo == "CLIENTE" and mesma_empresa_cliente(tarefa, current_user):
        return True
    return False


def pode_assumir_tarefa(tarefa):
    if not is_equipe_corex(current_user):
        return False
    if tarefa.id_usuario is not None or tarefa.concluida or tarefa.encerrada_forcada:
        return False
    if is_adm_principal(current_user):
        return True
    # Chamado sem responsável fica disponível para toda equipe CoreX assumir.
    return True


def pode_transferir_tarefa(tarefa):
    # Transferência fica com Super Admin e Administrador CoreX. Técnico atende, mas não redistribui equipe.
    return is_admin_corex(current_user) and pode_gerenciar_tarefa(tarefa)


def rotulo_cargo(usuario):
    return nome_cargo(cargo_usuario(usuario))


def aplicar_filtros_tarefas(consulta):
    busca = (request.args.get("q") or "").strip()
    setor_filtro = request.args.get("setor") or "todos"
    status = request.args.get("status") or "todos"

    if busca:
        consulta = consulta.filter(Tarefa.titulo.ilike(f"%{busca}%"))

    # Admin principal vê todos os setores. Admin de setor vê o próprio setor.
    # Cliente/colaborador vê somente chamados que ele abriu, independente do setor escolhido no chamado.
    if is_adm_principal(current_user):
        if setor_filtro != "todos":
            consulta = consulta.filter(Tarefa.setor == normalizar_setor(setor_filtro))
    elif cargo_usuario(current_user) == "ADMIN_COREX":
        # Admin vê chamados do próprio setor e também a fila geral sem responsável.
        consulta = consulta.filter(or_(Tarefa.setor == setor_usuario(current_user), Tarefa.id_usuario == None))
    elif cargo_usuario(current_user) == "TECNICO_COREX":
        # Técnico vê os chamados atribuídos a ele, chamados que ele abriu e a fila geral sem responsável.
        consulta = consulta.filter(or_(Tarefa.id_usuario == current_user.id, Tarefa.id_solicitante == current_user.id, Tarefa.id_usuario == None))
    else:
        consulta = consulta.filter(filtro_historico_cliente(current_user))

    if status == "abertos":
        consulta = consulta.filter(Tarefa.concluida == False, Tarefa.encerrada_forcada == False)
    elif status == "concluidos":
        consulta = consulta.filter(Tarefa.concluida == True, Tarefa.encerrada_forcada == False)
    elif status == "forcados":
        consulta = consulta.filter(Tarefa.encerrada_forcada == True)
    elif status == "sem_responsavel":
        consulta = consulta.filter(Tarefa.id_usuario == None, Tarefa.concluida == False, Tarefa.encerrada_forcada == False)
    elif status == "aguardando_cliente":
        consulta = consulta.filter(Tarefa.status == "aguardando_cliente")

    return consulta, busca, setor_filtro, status


def usuarios_do_escopo(apenas_funcionarios=True, setor=None):
    consulta = Usuario.query.filter_by(ativo=True)
    if apenas_funcionarios:
        consulta = consulta.filter(Usuario.cargo.in_(["TECNICO_COREX", "CLIENTE"]))

    if is_adm_principal(current_user):
        if setor:
            consulta = consulta.filter_by(setor=normalizar_setor(setor))
    else:
        consulta = consulta.filter_by(setor=setor_usuario(current_user))

    return consulta.order_by(Usuario.username.asc()).all()


def responsaveis_corex_do_escopo(setor=None):
    # Responsáveis pelo atendimento: Admin CoreX e Técnico CoreX.
    # Cliente/colaborador nunca aparece para receber chamado.
    consulta = Usuario.query.filter(Usuario.ativo == True, Usuario.cargo.in_(["ADMIN_COREX", "TECNICO_COREX"]))

    if is_adm_principal(current_user):
        if setor:
            consulta = consulta.filter_by(setor=normalizar_setor(setor))
    else:
        consulta = consulta.filter_by(setor=setor_usuario(current_user))

    return consulta.order_by(Usuario.cargo.asc(), Usuario.username.asc()).all()


def registrar_comentario(tarefa, texto):
    texto = (texto or "").strip()
    if texto:
        comentario = Comentario(texto=texto, tarefa=tarefa, usuario=current_user)
        database.session.add(comentario)


def gerar_numero_ticket(tarefa):
    ano = tarefa.data_criacao.year if tarefa.data_criacao else datetime.utcnow().year
    return f"CRX-{ano}-{tarefa.id:06d}"


def atualizar_status_tarefa(tarefa, novo_status):
    tarefa.status = novo_status
    if novo_status == "concluido":
        tarefa.concluida = True
        tarefa.encerrada_forcada = False
    elif novo_status == "encerrado_adm":
        tarefa.concluida = True
        tarefa.encerrada_forcada = True
    else:
        tarefa.concluida = False
        tarefa.encerrada_forcada = False


def criar_notificacao(usuario, titulo, mensagem, tarefa=None):
    if usuario and getattr(usuario, "id", None):
        database.session.add(Notificacao(titulo=titulo, mensagem=mensagem, usuario=usuario, tarefa=tarefa))


def notificar_admins_do_setor(setor, titulo, mensagem, tarefa=None):
    admins = Usuario.query.filter(Usuario.ativo == True, Usuario.cargo.in_(["SUPER_ADMIN", "ADMIN_COREX"])).all()
    for admin in admins:
        if is_adm_principal(admin) or setor_usuario(admin) == normalizar_setor(setor):
            criar_notificacao(admin, titulo, mensagem, tarefa)


def notificar_equipe_corex_geral(titulo, mensagem, tarefa=None, ignorar_usuario_id=None):
    """Notifica toda a equipe Core-X quando um chamado entra na Fila Geral.
    Inclui Super Admin, Administradores CoreX e Técnicos CoreX ativos.
    """
    equipe = Usuario.query.filter(
        Usuario.ativo == True,
        Usuario.cargo.in_(["SUPER_ADMIN", "ADMIN_COREX", "TECNICO_COREX"])
    ).all()
    for usuario in equipe:
        if ignorar_usuario_id and usuario.id == ignorar_usuario_id:
            continue
        criar_notificacao(usuario, titulo, mensagem, tarefa)


def configurar_form_tarefa(form):
    setor_informado = request.form.get("setor") or request.args.get("setor") or form.setor.data or SETOR_PADRAO
    setor_escolhido = normalizar_setor(setor_informado)

    # ADM de setor só pode abrir/encaminhar chamados para o próprio setor.
    if is_admin_corex(current_user) and not is_adm_principal(current_user):
        setor_escolhido = setor_usuario(current_user)

    form.setor.data = setor_escolhido

    responsaveis = responsaveis_corex_do_escopo(setor=setor_escolhido) if is_admin_corex(current_user) else []
    form.usuario_destino.choices = [(0, "Deixar sem responsável para a equipe assumir")] + [
        (u.id, f"{u.username} - {u.setor} - {rotulo_cargo(u)}") for u in responsaveis
    ]
    return setor_escolhido


@app.context_processor
def inject_corex_context():
    notificacoes_nao_lidas = 0
    notificacoes_recentes = []
    if current_user.is_authenticated:
        notificacoes_nao_lidas = Notificacao.query.filter_by(id_usuario=current_user.id, lida=False).count()
        notificacoes_recentes = Notificacao.query.filter_by(id_usuario=current_user.id).order_by(Notificacao.id.desc()).limit(5).all()
    return dict(
        setores_padrao=SETORES_PADRAO,
        is_adm_principal=is_adm_principal,
        is_admin_corex=is_admin_corex,
        is_tecnico_corex=is_tecnico_corex,
        is_equipe_corex=is_equipe_corex,
        cargo_usuario=cargo_usuario,
        rotulo_cargo=rotulo_cargo,
        pode_gerenciar_usuario=pode_gerenciar_usuario,
        notificacoes_nao_lidas=notificacoes_nao_lidas,
        notificacoes_recentes=notificacoes_recentes
    )




_admin_verificado = False

@app.before_request
def garantir_banco_e_admin_padrao():
    global _admin_verificado
    if _admin_verificado:
        return

    database.create_all()
    admin = Usuario.query.filter_by(email="admin@corex.com").first()

    if not admin:
        admin = Usuario(
            username="Administrador CoreX",
            email="admin@corex.com",
            senha=bcrypt.generate_password_hash("123456").decode("utf-8"),
            admin=True,
            principal_admin=True,
            cargo="SUPER_ADMIN",
            setor="Suporte Técnico",
            ativo=True,
            tema_preferido="escuro"
        )
        database.session.add(admin)
        database.session.commit()
    else:
        alterou = False
        if not admin.admin:
            admin.admin = True
            alterou = True
        if not getattr(admin, "principal_admin", False):
            admin.principal_admin = True
            alterou = True
        if getattr(admin, "cargo", None) != "SUPER_ADMIN":
            admin.cargo = "SUPER_ADMIN"
            alterou = True
        if not getattr(admin, "ativo", True):
            admin.ativo = True
            alterou = True
        if alterou:
            database.session.commit()

    _admin_verificado = True



def criar_usuario_demo(username, email, senha, cargo, setor=SETOR_PADRAO, empresa=None, cnpj=None, responsavel_empresa=None):
    usuario = Usuario.query.filter_by(email=email).first()
    if usuario:
        usuario.username = username
        usuario.cargo = cargo
        usuario.setor = normalizar_setor(setor)
        usuario.ativo = True
        usuario.empresa = empresa
        usuario.cnpj = cnpj
        usuario.responsavel_empresa = responsavel_empresa
        sincronizar_flags_usuario(usuario)
        return usuario

    usuario = Usuario(
        username=username,
        email=email,
        senha=bcrypt.generate_password_hash(senha).decode("utf-8"),
        cargo=cargo,
        setor=normalizar_setor(setor),
        ativo=True,
        data_criacao=datetime.utcnow(),
        tema_preferido="escuro",
        empresa=empresa,
        cnpj=cnpj,
        responsavel_empresa=responsavel_empresa,
    )
    sincronizar_flags_usuario(usuario)
    database.session.add(usuario)
    database.session.flush()
    return usuario


def criar_chamado_demo(solicitante, titulo, descricao, categoria, prioridade, setor_cliente=None):
    existente = Tarefa.query.filter_by(titulo=titulo, id_solicitante=solicitante.id).first()
    if existente:
        return existente

    tarefa = Tarefa(
        titulo=titulo,
        descricao=descricao,
        categoria=categoria,
        prioridade=prioridade,
        status="aberto",
        id_usuario=None,
        id_solicitante=solicitante.id,
        setor=SETOR_PADRAO,
        setor_cliente=setor_cliente,
        data_criacao=datetime.utcnow(),
    )
    database.session.add(tarefa)
    database.session.flush()
    tarefa.numero_ticket = gerar_numero_ticket(tarefa)
    database.session.add(Comentario(
        texto=f"Chamado {tarefa.numero_ticket} criado como dado de demonstração para apresentação do sistema.",
        tarefa=tarefa,
        usuario=solicitante
    ))
    return tarefa



@app.errorhandler(403)
def erro_403(error):
    return render_template('erros.html',
        codigo=403,
        titulo='Acesso negado',
        mensagem='Você não tem permissão para acessar esta área do sistema.',
        detalhe='Entre com uma conta autorizada ou volte para o portal.'
    ), 403


@app.errorhandler(404)
def erro_404(error):
    return render_template('erros.html',
        codigo=404,
        titulo='Página não encontrada',
        mensagem='A página que você tentou acessar não existe ou foi movida.',
        detalhe='Confira o endereço digitado ou volte para a página inicial.'
    ), 404


@app.errorhandler(413)
def erro_413(error):
    return render_template('erros.html',
        codigo=413,
        titulo='Arquivo muito grande',
        mensagem='O arquivo enviado ultrapassa o limite permitido.',
        detalhe='Envie imagens de até 5MB nos formatos PNG, JPG, JPEG, GIF ou WEBP.'
    ), 413


@app.errorhandler(500)
def erro_500(error):
    database.session.rollback()
    return render_template('erros.html',
        codigo=500,
        titulo='Erro interno',
        mensagem='Ops, algo deu errado ao processar sua solicitação.',
        detalhe='Tente novamente. Se o erro continuar, acione a equipe CoreX.'
    ), 500


@app.route('/')
def homepage():
    form_login = FormLogin()
    return render_template('site_home.html', form_login=form_login)



@app.route('/sobre')
def site_sobre():
    form_login = FormLogin()
    return render_template('site_sobre.html', form_login=form_login)



@app.route('/login', methods=['GET', 'POST'])
def site_login():
    form = FormLogin()

    if form.validate_on_submit():
        usuario = Usuario.query.filter_by(email=form.email.data).first()
        if usuario and getattr(usuario, "ativo", True) and bcrypt.check_password_hash(usuario.senha, form.senha.data):
            login_user(usuario, remember=True)
            flash(f'Bem-vindo(a), {usuario.username}.', 'ok')
            return redirect(url_for('homepage'))
        flash("Email ou senha inválidos, ou usuário inativo.", "erro")
        return redirect(url_for('homepage', login='1'))

    if request.method == 'POST':
        flash("Preencha email e senha corretamente.", "erro")
        return redirect(url_for('homepage', login='1'))

    return redirect(url_for('homepage', login='1'))


@app.route('/debug-corex')
def debug_corex():
    return 'COREX ORIGINAL DESIGN INTEGRADO OK'


@app.route('/criar-conta', methods=['GET', 'POST'])
@login_required
def criarconta():
    if not pode_gerenciar_usuarios():
        abort(403)

    form = FormCriarConta()

    if not is_adm_principal(current_user):
        form.cargo.choices = [("TECNICO_COREX", "Técnico CoreX"), ("CLIENTE", "Cliente / Colaborador")]
        form.cargo.data = form.cargo.data if form.cargo.data in ["TECNICO_COREX", "CLIENTE"] else "CLIENTE"
        form.admin.data = False
        form.setor.data = setor_usuario(current_user)

    if form.validate_on_submit():
        cargo = form.cargo.data if is_adm_principal(current_user) else form.cargo.data
        if not is_adm_principal(current_user) and cargo not in ["TECNICO_COREX", "CLIENTE"]:
            abort(403)
        if is_adm_principal(current_user) and cargo == "SUPER_ADMIN":
            # Por segurança, o primeiro Super Admin permanece único pela interface simples.
            cargo = "ADMIN_COREX"
        criar_como_admin = cargo in ["SUPER_ADMIN", "ADMIN_COREX"]
        setor = normalizar_setor(form.setor.data if is_adm_principal(current_user) else setor_usuario(current_user))

        senha_criptografada = bcrypt.generate_password_hash(form.senha.data).decode('utf-8')
        usuario = Usuario(
            username=form.username.data,
            email=form.email.data,
            senha=senha_criptografada,
            admin=criar_como_admin,
            cargo=cargo,
            principal_admin=False,
            setor=setor,
            ativo=True,
            data_criacao=datetime.utcnow(),
            tema_preferido="escuro",
            empresa=form.empresa.data,
            cnpj=form.cnpj.data,
            responsavel_empresa=form.responsavel_empresa.data
        )
        database.session.add(usuario)
        database.session.commit()
        flash('Usuário criado com sucesso.', 'ok')
        return redirect(url_for('usuarios'))

    if request.method == 'POST' and form.errors:
        flash_form_errors(form)

    return render_template('criarconta.html', form=form, adm_principal=is_adm_principal(current_user))


@app.route('/usuarios')
@login_required
def usuarios():
    if not pode_gerenciar_usuarios():
        abort(403)

    if is_adm_principal(current_user):
        lista_usuarios = Usuario.query.order_by(Usuario.admin.desc(), Usuario.setor.asc(), Usuario.username.asc()).all()
    else:
        lista_usuarios = Usuario.query.filter(Usuario.setor == setor_usuario(current_user), Usuario.cargo.in_(["TECNICO_COREX", "CLIENTE"])).order_by(Usuario.username.asc()).all()

    return render_template('usuarios.html', usuarios=lista_usuarios, adm_principal=is_adm_principal(current_user))



@app.route('/dados-demonstracao')
@login_required
def dados_demonstracao():
    if not is_adm_principal(current_user):
        abort(403)

    admin = criar_usuario_demo(
        "Admin CoreX Demo",
        "admin.demo@corex.com",
        "Corex123",
        "ADMIN_COREX",
        "Suporte Técnico",
    )
    tecnico = criar_usuario_demo(
        "Técnico CoreX Demo",
        "tecnico.demo@corex.com",
        "Corex123",
        "TECNICO_COREX",
        "Suporte Técnico",
    )
    cliente = criar_usuario_demo(
        "Cliente Demo",
        "cliente.demo@empresa.com",
        "Corex123",
        "CLIENTE",
        "Suporte Técnico",
        empresa="Empresa Demonstração Ltda",
        cnpj="00.000.000/0001-00",
        responsavel_empresa="Cliente Demo",
    )

    criar_chamado_demo(
        cliente,
        "Computador sem acesso à internet",
        "O computador do setor financeiro não consegue acessar sites nem sistemas online. O cabo de rede está conectado, mas a internet não funciona.",
        "Rede / Internet",
        "Alta",
        "Financeiro",
    )
    criar_chamado_demo(
        cliente,
        "Impressora não imprime documentos",
        "A impressora da recepção aparece como disponível, porém os documentos ficam presos na fila de impressão e não são impressos.",
        "Impressora",
        "Média",
        "Recepção",
    )

    database.session.commit()
    flash("Dados de demonstração criados/atualizados. Senha dos usuários demo: Corex123.", "ok")
    return redirect(url_for('usuarios'))


@app.route('/usuarios/<int:id_usuario>/editar', methods=['GET', 'POST'])
@login_required
def editar_usuario(id_usuario):
    if not pode_gerenciar_usuarios():
        abort(403)

    usuario = Usuario.query.get_or_404(id_usuario)
    if not pode_gerenciar_usuario(usuario):
        abort(403)

    form = FormPerfilUsuario(obj=usuario)

    if request.method == "GET":
        form.cargo.data = cargo_usuario(usuario)
    if not is_adm_principal(current_user):
        form.cargo.choices = [("TECNICO_COREX", "Técnico CoreX"), ("CLIENTE", "Cliente / Colaborador")]
        form.admin.data = False
        form.setor.data = setor_usuario(current_user)

    if form.validate_on_submit():
        usuario.username = form.username.data
        usuario.email = form.email.data
        usuario.ativo = bool(form.ativo.data)
        usuario.tema_preferido = form.tema_preferido.data or "escuro"
        usuario.empresa = form.empresa.data
        usuario.cnpj = form.cnpj.data
        usuario.responsavel_empresa = form.responsavel_empresa.data

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
            novo_cargo = form.cargo.data
            if usuario.id == 1 or novo_cargo == "SUPER_ADMIN":
                novo_cargo = "SUPER_ADMIN" if usuario.id == 1 else "ADMIN_COREX"
            usuario.cargo = novo_cargo
            sincronizar_flags_usuario(usuario)
            usuario.setor = normalizar_setor(form.setor.data)
            if usuario.id == 1:
                usuario.cargo = "SUPER_ADMIN"
                sincronizar_flags_usuario(usuario)
                usuario.ativo = True
        else:
            usuario.cargo = form.cargo.data if form.cargo.data in ["TECNICO_COREX", "CLIENTE"] else "CLIENTE"
            sincronizar_flags_usuario(usuario)
            usuario.setor = setor_usuario(current_user)

        database.session.commit()
        flash('Usuário atualizado com sucesso.', 'ok')
        return redirect(url_for('usuarios'))

    if request.method == 'POST' and form.errors:
        flash_form_errors(form)

    return render_template('editar_usuario.html', form=form, usuario=usuario, adm_principal=is_adm_principal(current_user))


@app.route('/chamados')
@app.route('/gerenciador')
@login_required
def gerenciador():
    return redirect(url_for('gerenciador_interno'))


@app.route('/gerenciador/interno', methods=["GET"])
@login_required
def gerenciador_interno():
    consulta = Tarefa.query
    consulta, busca, setor_filtro, status = aplicar_filtros_tarefas(consulta)
    tarefas = consulta.order_by(Tarefa.id.desc()).all()

    base_stats = Tarefa.query
    if is_adm_principal(current_user):
        pass
    elif cargo_usuario(current_user) == "ADMIN_COREX":
        base_stats = base_stats.filter(or_(Tarefa.setor == setor_usuario(current_user), Tarefa.id_usuario == None))
    elif cargo_usuario(current_user) == "TECNICO_COREX":
        base_stats = base_stats.filter(or_(Tarefa.id_usuario == current_user.id, Tarefa.id_solicitante == current_user.id, Tarefa.id_usuario == None))
    else:
        base_stats = base_stats.filter(filtro_historico_cliente(current_user))

    stats = {
        'abertos': base_stats.filter(Tarefa.concluida == False, Tarefa.encerrada_forcada == False).count(),
        'em_andamento': base_stats.filter(Tarefa.status == 'em_andamento').count(),
        'aguardando_cliente': base_stats.filter(Tarefa.status == 'aguardando_cliente').count(),
        'finalizados': base_stats.filter(Tarefa.concluida == True).count(),
    }

    metricas_admin = None
    if is_admin_corex(current_user):
        metricas_admin = {
            'por_prioridade': base_stats.with_entities(Tarefa.prioridade, func.count(Tarefa.id)).group_by(Tarefa.prioridade).all(),
            'por_tecnico': database.session.query(Usuario.username, func.count(Tarefa.id)).join(Tarefa, Tarefa.id_usuario == Usuario.id).filter(Tarefa.id.in_([t.id for t in base_stats.all()] or [0])).group_by(Usuario.username).all(),
            'total': base_stats.count(),
        }

    return render_template(
        'gerenciador_interno.html',
        tarefas=tarefas,
        stats=stats,
        metricas_admin=metricas_admin,
        adm_principal=is_adm_principal(current_user),
        busca=busca,
        setor_filtro=setor_filtro,
        status=status
    )




@app.route('/abrir-chamado', methods=['GET', 'POST'])
@login_required
def abrir_chamado():
    form = FormTarefa()
    setor_escolhido = configurar_form_tarefa(form)

    if form.validate_on_submit():
        # Cliente/colaborador não escolhe o setor técnico da Core-X.
        # O chamado entra na fila geral e qualquer pessoa da equipe CoreX pode assumir.
        if is_equipe_corex(current_user):
            setor_tarefa = normalizar_setor(form.setor.data)
            if is_admin_corex(current_user) and not is_adm_principal(current_user):
                setor_tarefa = setor_usuario(current_user)
        else:
            setor_tarefa = SETOR_PADRAO

        usuario_destino = None
        if is_admin_corex(current_user) and form.usuario_destino.data:
            usuario_destino = Usuario.query.get(form.usuario_destino.data)

        if usuario_destino:
            if not getattr(usuario_destino, "ativo", True) or cargo_usuario(usuario_destino) not in ["ADMIN_COREX", "TECNICO_COREX"]:
                abort(403)
            if setor_usuario(usuario_destino) != setor_tarefa:
                abort(403)
            if not is_adm_principal(current_user) and setor_tarefa != setor_usuario(current_user):
                abort(403)

        nome_imagem = salvar_imagem_upload(form.foto.data)

        tarefa = Tarefa(
            titulo=form.titulo.data,
            descricao=form.descricao.data,
            categoria=form.categoria.data,
            prioridade=form.prioridade.data,
            status="aberto",
            imagem=nome_imagem,
            id_usuario=usuario_destino.id if usuario_destino else None,
            id_solicitante=current_user.id,
            setor=setor_tarefa,
            setor_cliente=(form.setor_cliente.data or "").strip() or None
        )
        database.session.add(tarefa)
        database.session.flush()
        tarefa.numero_ticket = gerar_numero_ticket(tarefa)
        if is_equipe_corex(current_user):
            registrar_comentario(tarefa, f"Chamado {tarefa.numero_ticket} aberto por {current_user.username} para atendimento técnico do setor {setor_tarefa}.")
            if not usuario_destino:
                notificar_admins_do_setor(setor_tarefa, "Novo chamado aberto", f"{tarefa.numero_ticket} - {tarefa.titulo}", tarefa)
        else:
            registrar_comentario(tarefa, f"Chamado {tarefa.numero_ticket} aberto por {current_user.username}. Encaminhado para a Fila Geral Core-X.")
            notificar_equipe_corex_geral(
                "Novo chamado na Fila Geral",
                f"{tarefa.numero_ticket} - {tarefa.titulo}",
                tarefa
            )
        if usuario_destino:
            criar_notificacao(usuario_destino, "Chamado atribuído a você", f"{tarefa.numero_ticket} - {tarefa.titulo}", tarefa)
        database.session.commit()
        flash(f'Chamado {tarefa.numero_ticket} criado com sucesso e enviado para a Fila Geral CoreX.', 'ok')
        return redirect(url_for('detalhe_tarefa', id_tarefa=tarefa.id))

    if request.method == "POST" and form.errors:
        flash_form_errors(form)

    return render_template('abrir_chamado.html', form=form, setor_escolhido=setor_escolhido)


@app.route('/feed')
@login_required
def feed():
    consulta = Tarefa.query.filter_by(concluida=False, encerrada_forcada=False)
    if is_equipe_corex(current_user):
        consulta = consulta.filter_by(id_usuario=None)
    consulta, busca, setor_filtro, status = aplicar_filtros_tarefas(consulta)
    tarefas = consulta.order_by(Tarefa.id.desc()).all()

    return render_template('feed.html', tarefas=tarefas, busca=busca, setor_filtro=setor_filtro, status=status)


@app.route('/assumir-tarefa/<int:id_tarefa>')
@login_required
def assumir_tarefa(id_tarefa):
    tarefa = Tarefa.query.get_or_404(id_tarefa)

    if not pode_assumir_tarefa(tarefa):
        abort(403)

    tarefa.id_usuario = current_user.id
    if not is_adm_principal(current_user):
        tarefa.setor = setor_usuario(current_user)
    atualizar_status_tarefa(tarefa, "em_andamento")
    registrar_comentario(tarefa, f"Chamado assumido por {current_user.username}.")
    criar_notificacao(tarefa.solicitante, "Chamado em atendimento", f"{tarefa.numero_ticket or tarefa.id} foi assumido pela Core-X.", tarefa)
    database.session.commit()

    return redirect(url_for('detalhe_tarefa', id_tarefa=tarefa.id))


@app.route('/perfil/<id_usuario>', methods=["GET"])
@login_required
def perfil(id_usuario):
    usuario = Usuario.query.get_or_404(int(id_usuario))

    if usuario.id != current_user.id and not (pode_gerenciar_usuarios() and pode_gerenciar_usuario(usuario)):
        abort(403)

    form_perfil = FormPerfilUsuario(obj=usuario)

    if request.method == "GET":
        form_perfil.tema_preferido.data = getattr(usuario, "tema_preferido", "escuro") or "escuro"
        form_perfil.ativo.data = getattr(usuario, "ativo", True)
        form_perfil.cargo.data = cargo_usuario(usuario)
        if not is_adm_principal(current_user):
            form_perfil.cargo.choices = [("TECNICO_COREX", "Técnico CoreX"), ("CLIENTE", "Cliente / Colaborador")]

    return render_template(
        'perfil.html',
        usuario=usuario,
        form_perfil=form_perfil,
        adm_principal=is_adm_principal(current_user)
    )


@app.route('/perfil/<int:id_usuario>/atualizar', methods=['POST'])
@login_required
def atualizar_perfil(id_usuario):
    usuario = Usuario.query.get_or_404(id_usuario)

    if usuario.id != current_user.id and not (pode_gerenciar_usuarios() and pode_gerenciar_usuario(usuario)):
        abort(403)

    form = FormPerfilUsuario()
    if form.validate_on_submit():
        # Todos podem alterar o próprio nome, senha, foto e preferência de tema.
        # ADM pode alterar nome/foto/senha/tema do usuário gerenciado.
        usuario.username = form.username.data
        usuario.tema_preferido = form.tema_preferido.data or "escuro"
        usuario.empresa = form.empresa.data
        usuario.cnpj = form.cnpj.data
        usuario.responsavel_empresa = form.responsavel_empresa.data

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

        if pode_gerenciar_usuarios() and pode_gerenciar_usuario(usuario):
            usuario.email = form.email.data
            usuario.ativo = bool(form.ativo.data)
            if is_adm_principal(current_user):
                novo_cargo = form.cargo.data
                if usuario.id == 1 or novo_cargo == "SUPER_ADMIN":
                    novo_cargo = "SUPER_ADMIN" if usuario.id == 1 else "ADMIN_COREX"
                usuario.cargo = novo_cargo
                sincronizar_flags_usuario(usuario)
                usuario.setor = normalizar_setor(form.setor.data)
                if usuario.id == 1:
                    usuario.cargo = "SUPER_ADMIN"
                    sincronizar_flags_usuario(usuario)
                    usuario.ativo = True
            else:
                usuario.cargo = form.cargo.data if form.cargo.data in ["TECNICO_COREX", "CLIENTE"] else "CLIENTE"
                sincronizar_flags_usuario(usuario)
                usuario.setor = setor_usuario(current_user)
        else:
            # Funcionário não altera e-mail, cargo, setor nem status por POST manual.
            usuario.email = usuario.email

        database.session.commit()
        flash("Perfil atualizado com sucesso.", "ok")
    elif request.method == 'POST' and form.errors:
        flash_form_errors(form)

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

    if pode_transferir_tarefa(tarefa):
        form_transferir.setor_destino.data = normalizar_setor(tarefa.setor)
        usuarios = responsaveis_corex_do_escopo(setor=normalizar_setor(tarefa.setor))
        form_transferir.usuario_destino.choices = [(0, "Deixar sem responsável para a equipe assumir")] + [(u.id, f"{u.username} - {u.setor} - {rotulo_cargo(u)}") for u in usuarios]
    else:
        form_transferir.usuario_destino.choices = []

    return render_template(
        'detalhe_tarefa.html',
        tarefa=tarefa,
        form_comentario=form_comentario,
        form_transferir=form_transferir,
        pode_admin=pode_gerenciar_tarefa(tarefa),
        pode_assumir=pode_assumir_tarefa(tarefa),
        pode_transferir=pode_transferir_tarefa(tarefa)
    )



@app.route('/tarefa/<int:id_tarefa>/editar', methods=['GET', 'POST'])
@login_required
def editar_tarefa(id_tarefa):
    tarefa = Tarefa.query.get_or_404(id_tarefa)

    # Apenas Super Admin e Administrador CoreX editam dados escritos pelo cliente.
    # Técnico pode comentar e mudar andamento, mas não reescrever a solicitação original.
    if not is_admin_corex(current_user) or not pode_gerenciar_tarefa(tarefa):
        abort(403)

    form = FormTarefa()

    if request.method == "GET":
        form.titulo.data = tarefa.titulo
        form.descricao.data = tarefa.descricao
        form.setor_cliente.data = getattr(tarefa, "setor_cliente", None)
        form.categoria.data = tarefa.categoria or "Suporte Geral"
        form.prioridade.data = tarefa.prioridade or "Média"
        form.setor.data = normalizar_setor(tarefa.setor)
        form.usuario_destino.data = tarefa.id_usuario or 0

    setor_escolhido = configurar_form_tarefa(form)

    if form.validate_on_submit():
        setor_tarefa = normalizar_setor(form.setor.data)
        if is_admin_corex(current_user) and not is_adm_principal(current_user):
            setor_tarefa = setor_usuario(current_user)

        usuario_destino = Usuario.query.get(form.usuario_destino.data) if form.usuario_destino.data else None
        if usuario_destino:
            if not getattr(usuario_destino, "ativo", True) or cargo_usuario(usuario_destino) not in ["ADMIN_COREX", "TECNICO_COREX"]:
                abort(403)
            if setor_usuario(usuario_destino) != setor_tarefa:
                abort(403)

        imagem_antiga = tarefa.imagem
        nome_imagem = salvar_imagem_upload(form.foto.data)

        tarefa.titulo = form.titulo.data
        tarefa.descricao = form.descricao.data
        tarefa.setor_cliente = (form.setor_cliente.data or "").strip() or None
        tarefa.categoria = form.categoria.data
        tarefa.prioridade = form.prioridade.data
        tarefa.setor = setor_tarefa
        tarefa.id_usuario = usuario_destino.id if usuario_destino else None
        if nome_imagem:
            tarefa.imagem = nome_imagem

        if usuario_destino and tarefa.status == "aberto":
            atualizar_status_tarefa(tarefa, "em_andamento")

        registrar_comentario(tarefa, f"Chamado editado pelo administrador {current_user.username}.")
        if nome_imagem and imagem_antiga:
            registrar_comentario(tarefa, "Anexo do chamado substituído na edição administrativa.")

        # Edição administrativa não gera notificação para evitar excesso de alertas.
        # Notifica somente se o chamado foi atribuído a um responsável novo.
        if usuario_destino:
            criar_notificacao(usuario_destino, "Chamado atribuído a você", f"{tarefa.numero_ticket or tarefa.id} - {tarefa.titulo}", tarefa)
        database.session.commit()
        flash('Chamado atualizado com sucesso. As alterações foram registradas no histórico.', 'ok')
        return redirect(url_for('detalhe_tarefa', id_tarefa=tarefa.id))

    return render_template('editar_tarefa.html', form=form, tarefa=tarefa, setor_escolhido=setor_escolhido)


@app.route('/tarefa/<int:id_tarefa>/comentar', methods=['POST'])
@login_required
def comentar_tarefa(id_tarefa):
    tarefa = Tarefa.query.get_or_404(id_tarefa)
    if not pode_visualizar_tarefa(tarefa):
        abort(403)

    form = FormComentario()
    if form.validate_on_submit():
        registrar_comentario(tarefa, form.texto.data)

        # Notificação contextual:
        # - Resposta da equipe Core-X notifica apenas o cliente/solicitante.
        # - Resposta do cliente notifica apenas o responsável do chamado.
        # - Se ainda não há responsável, não notifica toda a equipe novamente,
        #   pois o chamado já apareceu na Fila Geral quando foi aberto.
        if is_equipe_corex(current_user):
            if tarefa.solicitante and tarefa.solicitante.id != current_user.id:
                criar_notificacao(tarefa.solicitante, "Nova resposta da Core-X", f"{tarefa.numero_ticket or tarefa.id} recebeu uma atualização.", tarefa)
        elif tarefa.usuario:
            criar_notificacao(tarefa.usuario, "Cliente respondeu", f"{tarefa.numero_ticket or tarefa.id} recebeu resposta do cliente.", tarefa)

        database.session.commit()
        flash('Comentário adicionado ao chamado.', 'ok')

    return redirect(url_for('detalhe_tarefa', id_tarefa=tarefa.id))


@app.route('/tarefa/<int:id_tarefa>/transferir', methods=['POST'])
@login_required
def transferir_tarefa(id_tarefa):
    tarefa = Tarefa.query.get_or_404(id_tarefa)
    if not pode_transferir_tarefa(tarefa):
        abort(403)

    form = FormTransferirTarefa()
    setor_destino = normalizar_setor(request.form.get('setor_destino'))

    if not is_adm_principal(current_user) and setor_destino != setor_usuario(current_user):
        abort(403)

    usuarios = responsaveis_corex_do_escopo(setor=setor_destino)
    form.usuario_destino.choices = [(0, "Deixar sem responsável para a equipe assumir")] + [(u.id, f"{u.username} - {u.setor} - {rotulo_cargo(u)}") for u in usuarios]

    if form.validate_on_submit():
        antigo_setor = normalizar_setor(tarefa.setor)
        antigo_resp = tarefa.usuario.username if tarefa.usuario else "sem responsável"
        novo_usuario = Usuario.query.get(form.usuario_destino.data) if form.usuario_destino.data else None

        if novo_usuario:
            # Cliente/colaborador não recebe chamado. Responsável precisa ser Admin CoreX ou Técnico CoreX ativo do setor.
            if (not novo_usuario.ativo) or cargo_usuario(novo_usuario) not in ["ADMIN_COREX", "TECNICO_COREX"] or setor_usuario(novo_usuario) != setor_destino:
                abort(403)

        tarefa.setor = setor_destino
        tarefa.id_usuario = novo_usuario.id if novo_usuario else None
        atualizar_status_tarefa(tarefa, "em_andamento" if novo_usuario else "aberto")

        novo_resp = novo_usuario.username if novo_usuario else "sem responsável"
        registrar_comentario(tarefa, f"Chamado atualizado por {current_user.username}: setor {antigo_setor} → {setor_destino}; responsável {antigo_resp} → {novo_resp}.")
        registrar_comentario(tarefa, form.comentario.data)

        # Transferência/triagem não notifica o cliente automaticamente.
        # Notifica somente o novo responsável, quando houver.
        if novo_usuario:
            criar_notificacao(novo_usuario, "Chamado atribuído a você", f"{tarefa.numero_ticket or tarefa.id} - {tarefa.titulo}", tarefa)
        database.session.commit()
        flash('Transferência salva com sucesso.', 'ok')

    return redirect(url_for('detalhe_tarefa', id_tarefa=tarefa.id))


@app.route('/concluir-tarefa/<int:id_tarefa>')
@login_required
def concluir_tarefa(id_tarefa):
    tarefa = Tarefa.query.get_or_404(id_tarefa)

    if not pode_gerenciar_tarefa(tarefa):
        abort(403)

    atualizar_status_tarefa(tarefa, "concluido")
    registrar_comentario(tarefa, f"Chamado concluído por {current_user.username}.")
    criar_notificacao(tarefa.solicitante, "Chamado finalizado", f"{tarefa.numero_ticket or tarefa.id} foi marcado como concluído.", tarefa)
    database.session.commit()
    flash('Chamado finalizado com sucesso.', 'ok')

    return redirect(url_for('detalhe_tarefa', id_tarefa=tarefa.id))


@app.route('/forcar-encerramento/<int:id_tarefa>')
@login_required
def forcar_encerramento(id_tarefa):
    tarefa = Tarefa.query.get_or_404(id_tarefa)
    if not pode_gerenciar_tarefa(tarefa):
        abort(403)

    atualizar_status_tarefa(tarefa, "encerrado_adm")
    registrar_comentario(tarefa, f"Encerramento forçado pelo administrador {current_user.username}.")
    criar_notificacao(tarefa.solicitante, "Chamado encerrado", f"{tarefa.numero_ticket or tarefa.id} foi encerrado pelo administrador.", tarefa)
    database.session.commit()
    flash('Chamado encerrado pelo administrador.', 'ok')

    return redirect(url_for('detalhe_tarefa', id_tarefa=tarefa.id))



@app.route('/reabrir-tarefa/<int:id_tarefa>')
@login_required
def reabrir_tarefa(id_tarefa):
    tarefa = Tarefa.query.get_or_404(id_tarefa)

    if not pode_gerenciar_tarefa(tarefa):
        abort(403)

    atualizar_status_tarefa(tarefa, "aberto")
    registrar_comentario(tarefa, f"Chamado reaberto por {current_user.username}.")
    criar_notificacao(tarefa.solicitante, "Chamado reaberto", f"{tarefa.numero_ticket or tarefa.id} foi reaberto.", tarefa)
    database.session.commit()
    flash('Chamado reaberto com sucesso.', 'ok')

    return redirect(url_for('detalhe_tarefa', id_tarefa=tarefa.id))


@app.route('/tarefa/<int:id_tarefa>/status/<novo_status>')
@login_required
def alterar_status_tarefa(id_tarefa, novo_status):
    tarefa = Tarefa.query.get_or_404(id_tarefa)
    if not pode_gerenciar_tarefa(tarefa):
        abort(403)

    status_validos = {
        "aberto": "Aberto",
        "em_andamento": "Em atendimento",
        "aguardando_cliente": "Aguardando cliente",
        "concluido": "Concluído",
    }
    if novo_status not in status_validos:
        abort(404)

    atualizar_status_tarefa(tarefa, novo_status)
    registrar_comentario(tarefa, f"Status alterado para {status_validos[novo_status]} por {current_user.username}.")

    # Alterações comuns de status ficam apenas no histórico.
    # Notificação ao cliente é reservada para eventos realmente importantes,
    # como conclusão/encerramento do chamado nas rotas específicas.
    database.session.commit()
    flash(f'Status alterado para {status_validos[novo_status]}.', 'ok')
    return redirect(url_for('detalhe_tarefa', id_tarefa=tarefa.id))


@app.route('/notificacoes')
@login_required
def notificacoes():
    lista = Notificacao.query.filter_by(id_usuario=current_user.id).order_by(Notificacao.id.desc()).limit(50).all()
    Notificacao.query.filter_by(id_usuario=current_user.id, lida=False).update({"lida": True})
    database.session.commit()
    return render_template('notificacoes.html', notificacoes=lista)


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('homepage'))


@app.route('/tarefa/<int:id_tarefa>/download')
@login_required
def download_chamado(id_tarefa):
    tarefa = Tarefa.query.get_or_404(id_tarefa)

    if not pode_visualizar_tarefa(tarefa):
        abort(403)

    if not REPORTLAB_DISPONIVEL:
        ticket_fallback = getattr(tarefa, 'numero_ticket', None) or f"CRX-{tarefa.id:06d}"
        pdf_bytes = gerar_pdf_nativo_chamado(tarefa)
        nome_arquivo = f"chamado_{ticket_fallback.replace('/', '_').replace(' ', '_')}.pdf"
        response = make_response(pdf_bytes)
        response.headers["Content-Type"] = "application/pdf"
        response.headers["Content-Length"] = str(len(pdf_bytes))
        response.headers["Content-Disposition"] = f'attachment; filename="{nome_arquivo}"'
        response.headers["Cache-Control"] = "no-store"
        return response

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=1.5 * cm,
        leftMargin=1.5 * cm,
        topMargin=3.15 * cm,
        bottomMargin=2.35 * cm,
        title=f"Chamado {tarefa.numero_ticket or tarefa.id}"
    )

    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(
        name="CoreTitle",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=22,
        leading=26,
        alignment=TA_CENTER,
        textColor=colors.HexColor("#0f172a"),
        spaceAfter=8,
    ))
    styles.add(ParagraphStyle(
        name="CoreSubtitle",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=10,
        leading=14,
        alignment=TA_CENTER,
        textColor=colors.HexColor("#475569"),
        spaceAfter=18,
    ))
    styles.add(ParagraphStyle(
        name="SectionTitle",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=13,
        leading=16,
        textColor=colors.HexColor("#1d4ed8"),
        spaceBefore=18,
        spaceAfter=12,
    ))
    styles.add(ParagraphStyle(
        name="BodyTextCore",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=10,
        leading=14,
        textColor=colors.HexColor("#1e293b"),
        spaceAfter=6,
    ))
    styles.add(ParagraphStyle(
        name="SmallMuted",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=8,
        leading=11,
        textColor=colors.HexColor("#64748b"),
    ))

    def txt(valor):
        valor = "" if valor is None else str(valor)
        return (valor.replace("&", "&amp;")
                     .replace("<", "&lt;")
                     .replace(">", "&gt;")
                     .replace("\n", "<br/>"))

    def data_fmt(data):
        try:
            return data.strftime('%d/%m/%Y %H:%M')
        except Exception:
            return "Nao informado"

    if getattr(tarefa, 'encerrada_forcada', False):
        status = "Encerrado pelo administrador"
    elif getattr(tarefa, 'concluida', False):
        status = "Concluido"
    elif getattr(tarefa, 'status', '') == 'aguardando_cliente':
        status = "Aguardando cliente"
    elif getattr(tarefa, 'usuario', None):
        status = "Em atendimento"
    else:
        status = "Aberto / Fila Geral"

    ticket = getattr(tarefa, 'numero_ticket', None) or f"CRX-{tarefa.id:06d}"
    solicitante = tarefa.solicitante.username if getattr(tarefa, 'solicitante', None) else "Nao informado"
    responsavel = tarefa.usuario.username if getattr(tarefa, 'usuario', None) else "Sem responsavel"
    cliente = getattr(tarefa, 'solicitante', None)

    story = []
    story.append(Paragraph("Relatório de Chamado", styles["CoreTitle"]))
    story.append(Paragraph(f"Documento técnico gerado pelo Portal CoreX • {txt(ticket)}", styles["CoreSubtitle"]))

    resumo_data = [
        [Paragraph("Ticket", styles["SmallMuted"]), Paragraph(txt(ticket), styles["BodyTextCore"])],
        [Paragraph("Status", styles["SmallMuted"]), Paragraph(txt(status), styles["BodyTextCore"])],
        [Paragraph("Titulo", styles["SmallMuted"]), Paragraph(txt(tarefa.titulo), styles["BodyTextCore"])],
        [Paragraph("Categoria", styles["SmallMuted"]), Paragraph(txt(getattr(tarefa, 'categoria', 'Suporte Geral')), styles["BodyTextCore"])],
        [Paragraph("Prioridade", styles["SmallMuted"]), Paragraph(txt(getattr(tarefa, 'prioridade', 'Media')), styles["BodyTextCore"])],
        [Paragraph("Fila tecnica Core-X", styles["SmallMuted"]), Paragraph(txt(getattr(tarefa, 'setor', 'Suporte Tecnico')), styles["BodyTextCore"])],
        [Paragraph("Local do problema", styles["SmallMuted"]), Paragraph(txt(getattr(tarefa, 'setor_cliente', None) or 'Nao informado'), styles["BodyTextCore"])],
        [Paragraph("Solicitante", styles["SmallMuted"]), Paragraph(txt(solicitante), styles["BodyTextCore"])],
        [Paragraph("Responsavel Core-X", styles["SmallMuted"]), Paragraph(txt(responsavel), styles["BodyTextCore"])],
        [Paragraph("Abertura", styles["SmallMuted"]), Paragraph(txt(data_fmt(getattr(tarefa, 'data_criacao', None))), styles["BodyTextCore"])],
    ]
    tabela_resumo = Table(resumo_data, colWidths=[4.2 * cm, 12.0 * cm])
    tabela_resumo.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#eff6ff")),
        ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#0f172a")),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e1")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(tabela_resumo)
    story.append(Spacer(1, 12))

    story.append(Paragraph("Descricao do chamado", styles["SectionTitle"]))
    story.append(Paragraph(txt(getattr(tarefa, 'descricao', None) or 'Sem descricao detalhada.'), styles["BodyTextCore"]))

    story.append(Paragraph("Empresa cliente", styles["SectionTitle"]))
    empresa_data = [
        ["Empresa", getattr(cliente, 'empresa', None) or "Dados empresariais não cadastrados"],
        ["CNPJ", getattr(cliente, 'cnpj', None) or "Dados empresariais não cadastrados"],
        ["Responsavel", getattr(cliente, 'responsavel_empresa', None) or solicitante],
    ]
    tabela_empresa = Table([[Paragraph(txt(a), styles["SmallMuted"]), Paragraph(txt(b), styles["BodyTextCore"])] for a, b in empresa_data], colWidths=[4.2 * cm, 12.0 * cm])
    tabela_empresa.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e1")),
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f8fafc")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(tabela_empresa)

    caminho_img = None
    if getattr(tarefa, 'imagem', None):
        caminho_img = os.path.join(os.path.abspath(os.path.dirname(__file__)), app.config['UPLOAD_FOLDER'], tarefa.imagem)
        if os.path.exists(caminho_img):
            story.append(Paragraph("Anexo do chamado", styles["SectionTitle"]))
            try:
                img = Image(caminho_img)
                max_w = 15.5 * cm
                max_h = 9.0 * cm
                ratio = min(max_w / float(img.imageWidth), max_h / float(img.imageHeight), 1)
                img.drawWidth = img.imageWidth * ratio
                img.drawHeight = img.imageHeight * ratio
                story.append(img)
                story.append(Paragraph("Imagem anexada ao chamado.", styles["SmallMuted"]))
            except Exception:
                story.append(Paragraph("O anexo existe, mas nao foi possivel renderizar a imagem no PDF.", styles["BodyTextCore"]))

    story.append(Paragraph("Historico e comentarios", styles["SectionTitle"]))
    comentarios = sorted(list(getattr(tarefa, 'comentarios', []) or []), key=lambda c: c.data_criacao or datetime.utcnow())
    if comentarios:
        linhas = [[Paragraph("Data", styles["SmallMuted"]), Paragraph("Autor", styles["SmallMuted"]), Paragraph("Registro", styles["SmallMuted"])]]
        for comentario in comentarios:
            autor = comentario.usuario.username if getattr(comentario, 'usuario', None) else "Usuario"
            linhas.append([
                Paragraph(txt(data_fmt(getattr(comentario, 'data_criacao', None))), styles["SmallMuted"]),
                Paragraph(txt(autor), styles["BodyTextCore"]),
                Paragraph(txt(getattr(comentario, 'texto', '')), styles["BodyTextCore"]),
            ])
        tabela_hist = Table(linhas, colWidths=[3.2 * cm, 3.8 * cm, 9.2 * cm], repeatRows=1)
        tabela_hist.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#dbeafe")),
            ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#cbd5e1")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))
        story.append(tabela_hist)
    else:
        story.append(Paragraph("Nenhum comentario registrado.", styles["BodyTextCore"]))

    story.append(Spacer(1, 14))
    story.append(Paragraph(f"Documento gerado em {datetime.utcnow().strftime('%d/%m/%Y %H:%M')} - Core-X", styles["SmallMuted"]))

    def rodape(canvas, doc_obj):
        canvas.saveState()
        largura, altura = A4

        # Cabeçalho CoreX
        canvas.setFillColor(colors.HexColor("#061225"))
        canvas.rect(0, altura - 2.75 * cm, largura, 2.75 * cm, stroke=0, fill=1)
        canvas.setFillColor(colors.HexColor("#0ea5e9"))
        canvas.roundRect(1.35 * cm, altura - 2.15 * cm, 1.05 * cm, 1.05 * cm, 6, stroke=0, fill=1)
        canvas.setFillColor(colors.white)
        canvas.setFont("Helvetica-Bold", 15)
        canvas.drawCentredString(1.875 * cm, altura - 1.82 * cm, "X")
        canvas.setFillColor(colors.white)
        canvas.setFont("Helvetica-Bold", 20)
        canvas.drawString(2.65 * cm, altura - 1.55 * cm, "COREX")
        canvas.setFillColor(colors.HexColor("#93c5fd"))
        canvas.setFont("Helvetica", 8)
        canvas.drawString(2.68 * cm, altura - 1.92 * cm, "Central de Suporte e Tecnologia")
        canvas.setFillColor(colors.white)
        canvas.setFont("Helvetica-Bold", 12)
        canvas.drawRightString(largura - 1.4 * cm, altura - 1.45 * cm, "RELATÓRIO DE CHAMADO")
        canvas.setFillColor(colors.HexColor("#bfdbfe"))
        canvas.setFont("Helvetica", 8)
        canvas.drawRightString(largura - 1.4 * cm, altura - 1.85 * cm, ticket)
        canvas.setStrokeColor(colors.HexColor("#2563eb"))
        canvas.setLineWidth(1.2)
        canvas.line(1.35 * cm, altura - 2.55 * cm, largura - 1.35 * cm, altura - 2.55 * cm)

        # Marca d'água discreta com identidade CoreX
        canvas.setFillColor(colors.HexColor("#eef6ff"))
        canvas.setFont("Helvetica-Bold", 190)
        canvas.drawCentredString(largura / 2, altura / 2 - 1.4 * cm, "X")

        # Rodapé CoreX
        canvas.setFillColor(colors.HexColor("#061225"))
        canvas.rect(0, 0, largura, 1.55 * cm, stroke=0, fill=1)
        canvas.setFillColor(colors.HexColor("#0ea5e9"))
        canvas.circle(1.65 * cm, 0.78 * cm, 0.32 * cm, stroke=0, fill=1)
        canvas.setFillColor(colors.white)
        canvas.setFont("Helvetica-Bold", 8)
        canvas.drawCentredString(1.65 * cm, 0.70 * cm, "X")
        canvas.setFont("Helvetica-Bold", 9)
        canvas.drawString(2.15 * cm, 0.92 * cm, "CoreX Tecnologia")
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(colors.HexColor("#cbd5e1"))
        canvas.drawString(2.15 * cm, 0.52 * cm, "Documento gerado automaticamente pelo Portal CoreX")
        canvas.drawRightString(largura - 1.35 * cm, 0.92 * cm, "corexinformatica@gmail.com")
        canvas.drawRightString(largura - 1.35 * cm, 0.52 * cm, f"Página {doc_obj.page}")
        canvas.restoreState()

    doc.build(story, onFirstPage=rodape, onLaterPages=rodape)
    buffer.seek(0)

    nome_arquivo = f"chamado_{ticket.replace('/', '_').replace(' ', '_')}.pdf"
    # Retorno feito manualmente para funcionar melhor no PythonAnywhere e em navegadores
    # que às vezes não iniciam o download corretamente com BytesIO + send_file.
    pdf_bytes = buffer.getvalue()
    response = make_response(pdf_bytes)
    response.headers["Content-Type"] = "application/pdf"
    response.headers["Content-Length"] = str(len(pdf_bytes))
    response.headers["Content-Disposition"] = f'attachment; filename="{nome_arquivo}"'
    response.headers["Cache-Control"] = "no-store"
    return response
