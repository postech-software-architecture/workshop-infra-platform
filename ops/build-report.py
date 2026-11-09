from pathlib import Path
import json,argparse
from xml.sax.saxutils import escape
from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Table,TableStyle,PageBreak,Flowable,KeepTogether
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet,ParagraphStyle
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

root=next(parent for parent in Path(__file__).resolve().parents if (parent/'fase-4/ops/delivery-links.json').is_file() or (parent/'ops/delivery-links.json').is_file())
project=root/'fase-4' if (root/'fase-4/ops/delivery-links.json').is_file() else root
out=root/'outputs/entrega-fase-4' if project!=root else root/'reports'
out.mkdir(exist_ok=True)
parser=argparse.ArgumentParser();parser.add_argument('--final',action='store_true');parser.add_argument('--participants-file',type=Path);parser.add_argument('--output',type=Path);args=parser.parse_args()
status=json.loads(((out/'evidencias/verificacao-final.json') if project!=root else project/'docs/evidencias/verificacao-final.json').read_text(encoding='utf-8'))
links=json.loads((project/'ops/delivery-links.json').read_text(encoding='utf-8'))
import sys
sys.path.insert(0,str(project/'ops'))
from delivery_validation import participants, final_inputs
people=participants(json.loads((args.participants_file or project/'ops/participants.json').read_text(encoding='utf-8')))
if args.final:
 try: final_inputs(links,people,status)
 except ValueError as error: raise SystemExit(str(error))

if Path('C:/Windows/Fonts/segoeui.ttf').exists():
 pdfmetrics.registerFont(TTFont('Segoe','C:/Windows/Fonts/segoeui.ttf'))
 pdfmetrics.registerFont(TTFont('SegoeBold','C:/Windows/Fonts/segoeuib.ttf'))
else:
 from reportlab.pdfbase.pdfmetrics import Font
 pdfmetrics.registerFont(Font('Segoe','Helvetica','WinAnsiEncoding'))
 pdfmetrics.registerFont(Font('SegoeBold','Helvetica-Bold','WinAnsiEncoding'))
navy=colors.HexColor('#16324F');teal=colors.HexColor('#0B7A75');muted=colors.HexColor('#526578');pale=colors.HexColor('#EDF4F7');orange=colors.HexColor('#AC5B13')
styles=getSampleStyleSheet()
styles.add(ParagraphStyle(name='BodyLocal',fontName='Segoe',fontSize=10,leading=15,textColor=navy,spaceAfter=9))
styles.add(ParagraphStyle(name='SmallLocal',fontName='Segoe',fontSize=8,leading=12,textColor=muted,spaceAfter=6))
styles.add(ParagraphStyle(name='TitleLocal',fontName='SegoeBold',fontSize=27,leading=33,textColor=navy,spaceAfter=16))
styles.add(ParagraphStyle(name='HeadingLocal',fontName='SegoeBold',fontSize=17,leading=23,textColor=teal,spaceAfter=12))
styles.add(ParagraphStyle(name='SubLocal',fontName='SegoeBold',fontSize=11,leading=15,textColor=navy,spaceBefore=9,spaceAfter=7))
story=[]
def p(text,style='BodyLocal'):return Paragraph(text,styles[style])
def add(text,style='BodyLocal'):story.append(p(text,style))
def heading(text):add(text,'HeadingLocal')
def table(rows,widths=None):
 data=[[p(escape(str(cell)),'SmallLocal') for cell in row] for row in rows]
 t=Table(data,colWidths=widths,repeatRows=1,hAlign='LEFT')
 t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),pale),('VALIGN',(0,0),(-1,-1),'TOP'),('LINEBELOW',(0,0),(-1,0),1,teal),('LINEBELOW',(0,1),(-1,-1),.3,colors.HexColor('#D8E2EA')),('LEFTPADDING',(0,0),(-1,-1),7),('RIGHTPADDING',(0,0),(-1,-1),7),('TOPPADDING',(0,0),(-1,-1),7),('BOTTOMPADDING',(0,0),(-1,-1),7)]));story.append(t);story.append(Spacer(1,11))
class Architecture(Flowable):
 def __init__(self):Flowable.__init__(self);self.width=487;self.height=205
 def draw(self):
  c=self.canv
  for x,title,subtitle,db in [(0,'OS','Atendimento / Saga','PostgreSQL OS'),(169,'Billing','Orçamento / pagamento','PostgreSQL Billing'),(338,'Execução','Diagnóstico / reparo','MongoDB rs0')]:
   c.setFillColor(pale);c.setStrokeColor(teal);c.roundRect(x,95,149,65,7,fill=1,stroke=1);c.setFillColor(navy);c.setFont('SegoeBold',12);c.drawCentredString(x+74.5,135,title);c.setFont('Segoe',8);c.drawCentredString(x+74.5,116,subtitle)
   c.setFillColor(colors.white);c.roundRect(x,0,149,34,5,fill=1,stroke=1);c.setFillColor(navy);c.setFont('Segoe',9);c.drawCentredString(x+74.5,13,db)
   c.line(x+74.5,95,x+74.5,34)
  c.setFillColor(teal);c.roundRect(95,48,297,28,5,fill=1,stroke=0);c.setFillColor(colors.white);c.setFont('SegoeBold',9);c.drawCentredString(243,58,'RabbitMQ - comandos, eventos, retry e DLQ')
  for x in [74.5,243.5,412.5]:c.setStrokeColor(teal);c.line(x,95,x,86);c.line(x,86,243,86);c.line(243,86,243,76)
  c.setFillColor(muted);c.setFont('Segoe',9);c.drawString(0,185,'Lambda -> identidade HTTP em OS');c.drawRightString(487,185,'Billing -> Mercado Pago QR/Orders')
def footer(canvas,doc):
 canvas.setStrokeColor(colors.HexColor('#D8E2EA'));canvas.line(42,42,553,42);canvas.setFont('Segoe',8);canvas.setFillColor(muted);canvas.drawString(42,28,'SOAT 4 | Implementação local | 09/11/2026');canvas.drawRightString(553,28,str(doc.page))

add('SOAT 4','SmallLocal');add('Serviços distribuídos<br/>e plano de entrega','TitleLocal')
add('Relatório técnico da implementação local','HeadingLocal')
add('Estado em 09/11/2026. Código das fases de extração, pagamentos/Saga e preparação da entrega desenvolvido. Validações com Docker, Mercado Pago e cloud permanecem pendentes conforme orientação do usuário.')
add('Este documento apresenta o código e as verificações disponíveis. Ainda não equivale ao aceite de um sistema implantado e demonstrado no provedor.','SmallLocal')
table([['Componente','Responsabilidade','Banco próprio'],['OS','Cadastros, composição, estoque e coordenação','PostgreSQL'],['Billing','Proposta, decisão, cobrança e compensação financeira','PostgreSQL'],['Execução','Diagnóstico, fila, itens e trabalho técnico','MongoDB'],['Autenticação','Lambda preservada, com consulta HTTP de identidade','Sem acesso direto a banco']], [88,288,111])
add('Participantes','SubLocal')
if people: table([['Nome','Identificação']]+[[person['name'],person['identification']] for person in people],[300,187])
else: add('Identificação dos participantes pendente. Este relatório local não é a versão institucional.','SmallLocal')
add('Resultado prático','SubLocal');add('O fluxo foi separado por responsabilidade. A aprovação comercial prepara estoque e cobrança. Somente a confirmação financeira verificada autoriza a fila de reparo. A compensação confirma cancelamento técnico e resultado financeiro antes de reverter o estoque.')
add('Pacote de trabalho','SubLocal');add('A distribuição inclui os três serviços, a adaptação da Lambda, infraestrutura de apoio, pipelines, contratos, testes, roteiros HTTP, operação e inventário de hashes. Os projetos originais da entrega anterior foram preservados.')
story.append(PageBreak())
heading('Arquitetura e fluxo de sucesso');story.append(Architecture());story.append(Spacer(1,10))
table([['Etapa','Confirmação e efeito'],['1. Atendimento','OS valida cliente/veículo e grava atendimento, tentativa e comando localmente.'],['2. Diagnóstico','Execução persiste o trabalho e publica progresso; OS mantém a projeção global.'],['3. Composição','OS valida catálogo, quantidade e reservas; Billing recebe snapshot de preço e itens.'],['4. Decisão','Billing decide sobre a versão imutável; rejeição retorna para nova composição.'],['5. Pagamento','Billing registra intenção, chave idempotente e recurso no Mercado Pago.'],['6. Liberação','Recurso externo consultado e validado confirma valor/moeda/referência/conta.'],['7. Reparo','Execução recebe itens autorizados e opera com versão esperada.'],['8. Encerramento','Eventos técnicos finalizam a OS; atendimento registra a entrega.']], [97,390])
add('Fronteiras','SubLocal');add('Não há FK entre bancos nem leitura SQL de outro serviço. Inbox/outbox participam da transação local. ACK ocorre depois do commit; reentrega é tratada por mensagem e identidade de negócio. A Lambda consulta OS por HTTP autenticado.')
story.append(PageBreak())
heading('Falhas, compensação e recuperação')
table([['Situação','Tratamento implementado'],['Resposta de cobrança desconhecida','Persistir incerteza; consultar recurso conhecido ou repetir a mesma identidade idempotente da criação.'],['Evento duplicado ou antigo','Inbox e chaves de negócio evitam repetição; versão financeira impede reabrir compensação com confirmação antiga.'],['Pagamento recusado/expirado','Cancelar/reconciliar tentativa técnica antes de devolver preparação de estoque.'],['Falha após pagamento','Solicitar cancelamento do trabalho; só então solicitar estorno e aguardar confirmação.'],['Reparo já iniciado','Recusa explícita do cancelamento. Não há estorno nem devolução automática de peça física.'],['Estorno aceito, ainda em processamento','Continuar reconciliação. Não publicar estorno concluído antes do recurso confirmado.'],['Retry esgotado ou recurso divergente','Registrar revisão manual/recuperação pendente; a API permite retomada autorizada conservando identidade.'],['Queda entre persistência e entrega','Outbox e lease permitem retomada; confirmação/ACK perdidos não exigem reiniciar o atendimento.']], [149,338])
add('Estoque','SubLocal');add('A reserva já reduz o saldo disponível. Aprovação registra consumo sem nova redução. Liberação/reversão se vincula à reserva original, tentativa e versão. Histórico permanece imutável e a reversão só conclui depois das confirmações exigidas.')
add('Limite físico','SubLocal');add('Uma falha de software não desfaz trabalho mecânico. Progresso técnico é persistido e pode continuar. Impedimentos de negócio após uso físico exigem decisão operacional auditada, preservando estoque e situação financeira reais.')
story.append(PageBreak())
heading('Qualidade e evidências locais')
rows=[['Serviço','Testes','Linhas','Instruções','Análise estática']]
for name,s in status['services'].items():rows.append([name,s['tests'],str(s['coverage']['LINE'])+'%',str(s['coverage']['INSTRUCTION'])+'%','Sem achados no nível alto'])
table(rows,[74,48,67,78,220])
add('Critério de cobertura','SubLocal');add('O CI usa gate mínimo de 80% de linhas por serviço. São excluídos DTOs, entidades JPA de mapeamento e implementações de mapper geradas; domínio, repositories, Saga, mensageria e gateway continuam medidos. O relatório JSON registra se o gate passou na execução final.')
add('O que os testes exercitam','SubLocal');add('Regressão de cadastros por HTTP/JPA, estados e concorrência esperada, orçamento e propriedade, valores decimais, repetição de comandos, cancelamento antes da criação, confirmação financeira, timeout, autenticação do webhook e compensação. Há cenário BDD executável em cada serviço.')
add('Limites das provas','SubLocal');add('H2 nos testes de contexto de OS/Billing não comprova migrations ou locks PostgreSQL. Mongo é substituído nos testes sem Docker; atomicidade, índices e retomada precisam de execução real. O adapter HTTP do provedor foi exercitado contra servidor local de teste; isso não comprova a conta Mercado Pago.')
table([['Evidência','Estado'],['Build/testes/análise estática local','Relatórios e logs no pacote'],['Renderização Kustomize e Terraform fmt','Verificação estática local; sem apply'],['Fluxo integrado SQL/NoSQL/Rabbit','Pendente de execução real'],['Cobrança, webhook e estorno Mercado Pago','Pendente de conta e prova de teste'],['Rollout, recuperação e restauração cloud','Pendente de configuração/aplicação'],['Proteção de branch, CI remoto e vídeo','Pendente de publicação e gravação']], [261,226])
story.append(PageBreak())
heading('Implantação, operação e demonstração')
add('Preparação de implantação','SubLocal');add('Cada serviço possui imagem por SHA, Deployment/Service, probes, recursos, NetworkPolicy, HPA e PDB. O workflow de deploy é independente e manual; rollback automático é restrito à falha do rollout. A plataforma é dona única dos bancos, broker, entrada e collector.')
add('Persistência e isolamento','SubLocal');add('No Academy, OS e Billing usam bancos lógicos e usuários distintos no RDS existente, preservando a instância e o state. Mongo e Rabbit usam PVCs com uma réplica; um membro não oferece alta disponibilidade. A StorageClass existente, backups e restauração precisam de prova real. A entrada mantém API Gateway/VPC Link/NLB e as credenciais temporárias da LabRole.')
add('Roteiro de aceite','SubLocal')
for line in ['1. Configurar secrets e dados demonstrativos em bancos novos; preservar os volumes anteriores.',
             '2. Executar verify-phase3.py: abertura, diagnóstico, composição, rejeição, nova versão e aprovação.',
             '3. Configurar a conta de teste, caixa/loja e webhook; obter e pagar o QR com comprador de teste.',
             '4. Executar verify-phase4.py --action complete: reparo autorizado, itens, finalização e entrega opcional.',
             '5. Em outra OS paga e ainda não iniciada, executar --action cancel e comprovar cancelamento, estorno e reversão.',
             '6. Repetir reinício/reentrega, disputa entre início/cancelamento e restauração; guardar IDs, histórico e traces.']:add(line,'SmallLocal')
add('Observabilidade','SubLocal');add('Aplicações produzem logs JSON com correlação e exportam traces/métricas por OTLP. O collector preparado exporta para New Relic por configuração externa. A coleta stdout, dashboards, alertas e credenciais devem ser confirmados no cluster.')
add('Operação','SubLocal');add('O pacote ops contém smoke somente leitura, redrive com publisher confirms e procedimentos de retomada. Nunca substituir timeout por outra chave financeira ou marcar compensação concluída enquanto houver resultado externo desconhecido.')
story.append(PageBreak())
heading('Publicação e fechamento da entrega')
table([['Item','Referência atual'],['Repositório OS',links['repositories']['os'] or 'Ainda não publicado'],['Repositório Billing',links['repositories']['billing'] or 'Ainda não publicado'],['Repositório Execução',links['repositories']['execution'] or 'Ainda não publicado'],['Vídeo de demonstração',links['video'] or 'Ainda não gravado/publicado']], [156,331])
add('Antes do envio institucional','SubLocal');add('Publicar os repositórios, configurar branches protegidas e os ambientes de deploy. Executar os workflows reais, preencher as referências em ops/delivery-links.json e anexar as provas de pagamento, compensação, persistência e rollout. O gerador recusa o modo final enquanto essas confirmações e a cobertura mínima estiverem ausentes.')
add('Roteiro do vídeo - até 15 minutos','SubLocal');add('Apresentar arquitetura e donos dos dados; executar o sucesso com QR de teste; demonstrar falha após efeito e compensação confirmada; mostrar reentrega/retomada, relatórios de qualidade e operação independente. Reservar os minutos finais para links e limites do ambiente.')
add('Fontes técnicas consultadas','SubLocal')
for label,url in [('Mercado Pago: processamento QR/Orders','https://www.mercadopago.com.br/developers/pt/docs/qr-code/payment-processing'),('Mercado Pago: notificações e autenticação','https://www.mercadopago.com.br/developers/pt/docs/qr-code/notifications'),('Mercado Pago: referência de criação de order','https://www.mercadopago.com.br/developers/en/reference/in-person-payments/qr-code/orders/create-order/post')]:
 add('<link href="'+escape(url)+'" color="#0B7A75">'+escape(label)+'</link>','SmallLocal')
add('A documentação de QR e o SDK possuem orientações que exigem confirmação no ambiente de teste quanto à assinatura efetivamente recebida. O endpoint implementado exige assinatura válida e consulta do recurso; não aceita confirmação financeira fornecida pelo navegador.','SmallLocal')
add('Origem do desenvolvimento','SubLocal');add('Código de OS reaproveitado da baseline 0e654a37da763dbf1e1c85d56f37921c6cfd2a8a. Arquivos da Lambda foram copiados de forma isolada e possuem inventário de origem. O pacote inclui hashes do código e evidencia separadamente o que foi executado localmente e o que está pendente.','SmallLocal')
document=SimpleDocTemplate(str(args.output or out/'relatorio-tecnico-soat4.pdf'),pagesize=A4,rightMargin=54,leftMargin=54,topMargin=48,bottomMargin=56,title='SOAT 4 - Implementação local e roteiro de entrega',author='Equipe SOAT')
document.build(story,onFirstPage=footer,onLaterPages=footer)
print(str(args.output or out/'relatorio-tecnico-soat4.pdf'))
