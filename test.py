import telegram
from telegram import InputMediaPhoto
from telegram.ext import Updater, CommandHandler, ConversationHandler, MessageHandler, RegexHandler, Filters, PicklePersistence, CallbackQueryHandler
import logging
import os
import random
from sqlalchemy import create_engine, desc
from sqlalchemy.orm import sessionmaker
from telegram import Update, User, InlineKeyboardButton, InlineKeyboardMarkup


TOKEN = '789364882:AAF6-OLy36xTCZB0Y3KQtK0pfZTUuRe56dM' # TODO Убрать в конфиг

bot = telegram.Bot(token=TOKEN)
updater = Updater(
    token=TOKEN, 
    # persistence=PicklePersistence(filename='persistence_file'), 
    use_context=True
    )
dispatcher = updater.dispatcher

logging.basicConfig(
        format='%(asctime)s - %(levelname)s - %(name)s - %(message)s',
        level=logging.INFO
        )

def test_image_resend(update,context):
    print("============================ gotcha")
    bot.send_photo(
            chat_id=update.message.from_user.id, 
            photo=update.message.photo[0].file_id,
            caption="succ"
        ) # works
    

def test_resend_message(update,context):
    print("============================ gotcha_2")
    print(update.message.text)
    print(update.message[3].text)
    bot.send_message(
        chat_id=update.message.from_user.id, 
        text=update.message[-2].text
        )



def main():
    ## Вставляем фичу в обработчик
    dispatcher.add_handler(MessageHandler(Filters.text, test_resend_message))
    dispatcher.add_handler(MessageHandler(Filters.photo, test_image_resend))

    ## Запускаем мясорубку
    updater.start_polling()
    updater.idle()
    ## Вырубаем мясорубку
    # updater.stop()  # TODO автоматизировать выключалку




if __name__ == '__main__':
    main()