import logging
import asyncio
import schedule
import pytz
import telegram
from datetime import datetime, timedelta
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, PollAnswerHandler
from flask import Flask  # Importando Flask para manter o Replit ativo

# Configuração do logging com formato estruturado
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# Token e Chat IDs fixos
TOKEN = "8028404342:AAGItd1jbu0wRIa0oYt43_K1kCBSnbJOeFE"
CHAT_IDS = ["1980190204", "454888590"]  # Lista de chat IDs

# Configuração do fuso horário de Brasília
TIMEZONE = pytz.timezone('America/Sao_Paulo')

# Variáveis globais
ultima_enquete_id = None
streaks = {}  # Dicionário para armazenar a streak de cada usuário
respostas = {}
ultimo_offset = 0

# Registrar início do bot
start_time = datetime.now(TIMEZONE)
logger.info(f"Bot iniciando em {start_time.strftime('%Y-%m-%d %H:%M:%S %Z')}")
logger.info(f"Bot token carregado (tamanho: {len(TOKEN)})")
logger.info(f"Chat IDs configurados: {CHAT_IDS}")

# Inicialização do Flask para manter o Replit ativo
app_flask = Flask(__name__)

@app_flask.route('/')
def home():
    """Endpoint simples para manter o Replit ativo."""
    return "Bot está online!"

def run_flask():
    """Função para rodar o Flask em segundo plano."""
    app_flask.run(host='0.0.0.0', port=4000)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /start"""
    chat_id = update.effective_chat.id
    await update.message.reply_text("Olá! Eu sou seu bot de lembrete de medicação.")
    logger.info(f"Comando /start executado - Usuário: {update.effective_user.id}, Chat: {chat_id}")

async def enviar_enquete(chat_id: str, context: Application):
    """Enviar enquete diária"""
    global ultima_enquete_id
    try:
        current_time = datetime.now(TIMEZONE)
        logger.info(f"Iniciando envio de enquete às {current_time.strftime('%H:%M:%S %Z')}")

        message = await context.bot.send_poll(
            chat_id=chat_id,
            question="Você tomou seu medicamento hoje?",
            options=["Sim 🙂", "Não 😔"],
            is_anonymous=False,
            allows_multiple_answers=False,
            open_period=86400  # Enquete aberta por 24 horas (86400 segundos)
        )

        ultima_enquete_id = message.poll.id
        logger.info(f"Enquete enviada com sucesso - ID: {ultima_enquete_id}")
        
        # A enquete já tem open_period configurado para 24 horas,
        # não é necessário agendar fechamento manual

    except Exception as e:
        logger.error(f"Erro ao enviar enquete: {str(e)}", exc_info=True)

async def fechar_enquete(chat_id: str, poll_id: str, context: Application):
    """Fechar a enquete após 24 horas"""
    try:
        await context.bot.stop_poll(chat_id=chat_id, message_id=poll_id)
        logger.info(f"Enquete {poll_id} fechada com sucesso após 24 horas.")
    except Exception as e:
        logger.error(f"Erro ao fechar enquete: {str(e)}", exc_info=True)

async def test(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /test para enviar uma enquete de teste"""
    chat_id = update.effective_chat.id
    logger.info(f"Comando de teste iniciado - Usuário: {update.effective_user.id}")
    await update.message.reply_text("Enviando uma enquete de teste...")
    await enviar_enquete(chat_id, context.application)

async def handle_poll_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lidar com a resposta à enquete"""
    global streaks
    answer = update.poll_answer
    user_id = answer.user.id
    selected_option = answer.option_ids[0]
    current_time = datetime.now(TIMEZONE)

    logger.info(f"Resposta recebida às {current_time.strftime('%H:%M:%S %Z')} - Usuário: {user_id}, Opção: {selected_option}")

    if user_id not in streaks:
        streaks[user_id] = 0

    if selected_option == 0:  # Resposta "Sim"
        streaks[user_id] += 1
        message = f"Você está tomando seu remédio há {streaks[user_id]} dias consecutivos! ✨"
        await context.bot.send_message(chat_id=user_id, text=message)
        await context.bot.send_message(chat_id=user_id, text="Ótimo, Você tomou o remédio hoje ☺️!")
        logger.info(f"Streak atualizada para o usuário {user_id}: {streaks[user_id]} dias")
    else:  # Resposta "Não"
        streaks[user_id] = 0
        message = "Oh não! Você perdeu sua sequência. Vamos recomeçar amanhã! 😔"
        await context.bot.send_message(chat_id=user_id, text=message)
        await context.bot.send_message(chat_id=user_id, text="Vá tomar seu remédio 😡")
        logger.info(f"Streak resetada para o usuário {user_id} devido à resposta negativa")

async def clear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /clear para resetar a contagem de dias consecutivos"""
    global streaks
    user_id = update.effective_user.id
    streaks[user_id] = 0
    await update.message.reply_text("A contagem de dias consecutivos foi redefinida para 0.")
    logger.info(f"Streak resetada manualmente para o usuário {user_id}")

async def executar_schedule():
    """Executa o agendador de tarefas"""
    last_check_time = None
    retry_count = 0
    max_retries = 5

    while True:
        try:
            current_time = datetime.now(TIMEZONE)

            # Log apenas quando o minuto mudar para evitar spam
            if last_check_time is None or current_time.minute != last_check_time.minute:
                logger.debug(f"Verificando agendamentos às {current_time.strftime('%H:%M:%S %Z')}")
                last_check_time = current_time

            schedule.run_pending()
            # Aumentar o intervalo entre verificações de agenda
            await asyncio.sleep(5)
            retry_count = 0  # Reset retry count on successful execution

        except Exception as e:
            retry_count += 1
            wait_time = min(10 * retry_count, 60)  # Backoff com máximo de 60 segundos
            logger.error(f"Erro no agendador (tentativa {retry_count}/{max_retries}): {str(e)}", exc_info=True)

            if retry_count >= max_retries:
                logger.critical("Número máximo de tentativas excedido no agendador - reiniciando ciclo")
                retry_count = 0
                await asyncio.sleep(120)  # Espera longa após falhas consecutivas
            else:
                await asyncio.sleep(wait_time)

async def monitorar_respostas():
    """Monitora as respostas das enquetes através dos handlers do bot"""
    # Esta função agora apenas mantém o processo vivo
    # Todas as respostas são processadas pelo handle_poll_answer
    retry_count = 0
    max_retries = 5
    base_sleep_time = 10

    # Log inicial para confirmar que a função está rodando
    logger.info("Iniciando monitoramento de respostas")

    while True:
        try:
            # Apenas manter o processo vivo e verificar o estado
            await asyncio.sleep(10)
            retry_count = 0

        except telegram.error.TimedOut as e:
            # Tratamento específico para timeout
            retry_count += 1
            wait_time = min(base_sleep_time * retry_count, 60)  # Backoff com máximo de 60s
            logger.warning(f"Timeout no monitoramento (tentativa {retry_count}/{max_retries}): {str(e)}")

            if retry_count >= max_retries:
                logger.error("Número máximo de tentativas excedido para timeout - esperando mais tempo")
                await asyncio.sleep(120)  # Espera mais longa após muitas falhas
                retry_count = 0
            else:
                await asyncio.sleep(wait_time)

        except Exception as e:
            retry_count += 1
            wait_time = min(base_sleep_time * retry_count, 60)
            logger.error(f"Erro no monitoramento (tentativa {retry_count}/{max_retries}): {str(e)}", exc_info=True)

            if retry_count >= max_retries:
                logger.critical("Número máximo de tentativas excedido no monitoramento - redefinindo")
                await asyncio.sleep(180)  # Pausa longa após falhas consecutivas
                retry_count = 0
            else:
                await asyncio.sleep(wait_time)

# Inicialização do bot com configurações otimizadas
app = Application.builder().token(TOKEN)\
    .connect_timeout(30.0)\
    .read_timeout(30.0)\
    .write_timeout(30.0)\
    .pool_timeout(60.0)\
    .connection_pool_size(8)\
    .get_updates_connection_pool_size(1)\
    .build()

async def info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /info para verificar o status do bot"""
    current_time = datetime.now(TIMEZONE)
    uptime = current_time - start_time
    user_id = update.effective_user.id
    user_streak = streaks.get(user_id, 0)

    await update.message.reply_text(
        f"🤖 *Status do Bot*\n"
        f"✅ Bot está ativo\n"
        f"⏱️ Online há: {uptime.days} dias, {uptime.seconds//3600} horas\n"
        f"🔄 Streak atual: {user_streak} dias\n"
        f"⏰ Próxima enquete: 07:00\n\n"
        f"📝 *Comandos*\n"
        f"/start - Iniciar o bot\n"
        f"/test - Enviar enquete de teste\n"
        f"/clear - Resetar sequência\n"
        f"/info - Ver este status",
        parse_mode="Markdown"
    )
    logger.info(f"Comando /info executado - Usuário: {update.effective_user.id}")

# Adicionar handlers
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("test", test))
app.add_handler(CommandHandler("clear", clear))
app.add_handler(CommandHandler("info", info))
app.add_handler(PollAnswerHandler(handle_poll_answer))

async def main():
    """Função principal do bot"""
    tasks = []

    try:
        # Configurar horário para 7:00 AM no fuso horário de Brasília
        schedule_time = "07:00"
        logger.info(f"Configurando envio diário de enquete para {schedule_time} {TIMEZONE}")

        # Agendar enquete para 7:00 AM horário de Brasília
        for chat_id in CHAT_IDS:
            schedule.every().day.at(schedule_time).do(
                lambda chat_id=chat_id: asyncio.create_task(enviar_enquete(chat_id, app))
            )

        # Inicializar e iniciar o bot antes de criar as tarefas
        await app.initialize()
        await app.start()

        # Configurações de polling otimizadas
        await app.updater.start_polling(
            poll_interval=1.0,  # Reduzido para maior responsividade
            timeout=10,         # Reduzido para evitar longos bloqueios
            drop_pending_updates=False,  # Não ignorar atualizações pendentes
            read_timeout=10,
            write_timeout=10,
            allowed_updates=["message", "poll_answer"]  # Explicitamente permitir mensagens e respostas de enquete
        )

        # Iniciar tarefas assíncronas com referências para controle
        tasks.append(asyncio.create_task(monitorar_respostas()))
        tasks.append(asyncio.create_task(executar_schedule()))

        # Iniciar o Flask em segundo plano para manter o Replit ativo
        import threading
        flask_thread = threading.Thread(target=run_flask)
        flask_thread.daemon = True  # O thread será encerrado quando o programa principal terminar
        flask_thread.start()

        logger.info(f"Bot iniciado com sucesso às {start_time.strftime('%H:%M:%S %Z')}")
        logger.info("Comandos disponíveis: /start, /test, /clear")

        # Loop principal com recuperação de erros
        while True:
            try:
                await asyncio.sleep(10)

                # Verificar se as tarefas estão ativas
                for i, task in enumerate(tasks):
                    if task.done():
                        exception = None
                        try:
                            exception = task.exception()
                        except (asyncio.CancelledError, asyncio.InvalidStateError):
                            logger.warning(f"Tarefa {i} foi cancelada")

                        if exception:
                            logger.error(f"Tarefa {i} terminou com erro: {exception}")
                        else:
                            logger.warning(f"Tarefa {i} terminou inesperadamente")

                        # Deixar um intervalo antes de reiniciar para evitar conflitos
                        await asyncio.sleep(5)

                        # Reiniciar tarefa que terminou
                        if i == 0:  # monitorar_respostas
                            tasks[i] = asyncio.create_task(monitorar_respostas())
                            logger.info("Tarefa monitorar_respostas reiniciada")
                        elif i == 1:  # executar_schedule
                            tasks[i] = asyncio.create_task(executar_schedule())
                            logger.info("Tarefa executar_schedule reiniciada")

            except asyncio.CancelledError:
                logger.info("Processo principal cancelado")
                break
            except Exception as e:
                logger.error(f"Erro no loop principal: {str(e)}", exc_info=True)
                await asyncio.sleep(30)  # Aguardar antes de continuar

    except Exception as e:
        logger.error(f"Erro crítico na inicialização do bot: {str(e)}", exc_info=True)

    finally:
        # Cancelar todas as tarefas
        for task in tasks:
            if not task.done():
                task.cancel()

        # Aguardar o cancelamento das tarefas
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        logger.info("Encerrando bot...")
        await app.updater.stop()
        await app.stop()
        logger.info("Bot encerrado com sucesso")

if __name__ == "__main__":
    asyncio.run(main())
