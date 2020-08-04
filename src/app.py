import telegram
from telegram.ext import Updater
import logging
from telegram.ext import CommandHandler

TOKEN = '789364882:AAF6-OLy36xTCZB0Y3KQtK0pfZTUuRe56dM' # TODO Убрать в конфиг



bot = telegram.Bot(token=TOKEN)
updater = Updater(token=TOKEN, use_context=True)
dispatcher = updater.dispatcher

# print(bot.get_me())   #Для отладки


## Настройка логирования
logging.basicConfig(
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        level=logging.INFO)
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


## Прописываем фичу
def start(update, context):
    logger.info("reply for %s" % update.effective_chat.id)
    context.bot.send_message(chat_id=update.effective_chat.id, text="Привет лунатикам")

def create(update,context):
    pass

def join(update,context):
    pass

def main():
    ## Вставляем фичу в обработчик
    dispatcher.add_handler(CommandHandler('start', start))

    ## Запускаем мясорубку
    updater.start_polling()
    updater.idle()
    ## Вырубаем мясорубку
    # updater.stop()  # TODO автоматизировать выключалку

if __name__ == '__main__':
    main()