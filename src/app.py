import telegram
from telegram.ext import Updater, CommandHandler, ConversationHandler, MessageHandler, Filters
import logging
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from telegram import Update, User

from error_handler import error_callback
from models import *

from game_states import GameStates
from configs.texts import RegistrationTexts, CreationTexts, CommandsList


## Constants
TOKEN = '789364882:AAF6-OLy36xTCZB0Y3KQtK0pfZTUuRe56dM' # TODO Убрать в конфиг
BEGIN, CREATE, PLAY, PREPARE, AWAIT = range(5)

## SqlAlchemy objects
engine = create_engine('sqlite:///'+os.path.abspath(os.getcwd())+'\database.db', echo=True)
Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)


## Telegram objects
bot = telegram.Bot(token=TOKEN)
updater = Updater(token=TOKEN, use_context=True)
dispatcher = updater.dispatcher
dispatcher.add_error_handler(error_callback)
# import sqlalchemy
# print(bot.get_me())   #Для отладки


## Настройка логирования
logging.basicConfig(
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
logging.getLogger("telegram").setLevel(logging.INFO)
# logging.getLogger("sqlalchemy").setLevel(logging.INFO)
# logging.getLogger("urllib3").setLevel(logging.NOTSET)



## Прописываем фичу
def start(update, context):
    """
    Проверяем наличие пользователя
    Если есть, игнорируем
    Если нету, то:
    Спрашиваем имя
    Создаем пользователя
    """
    logging.info("User %s starting bot" % update.effective_chat.id)
    session = Session()

    # TODO Добавить всякие проверки на бота

    user_id = update.effective_user.id

    def check_user(session, telegram_id):
        player = session.query(Player).filter_by(id=telegram_id).first()
        if not player:
            logging.info("User %s first time" % update.effective_chat.id)
            return False
        else:
            logging.info("User %s exist" % update.effective_chat.id)
    session.close()

    if check_user(session, user_id) == False:
        update.message.reply_text(RegistrationTexts.hello)
        return BEGIN
    else:
        update.message.reply_text(CommandsList.commandslist)
        return CREATE

        

def create_user(update, context):
    # get user data
    user_id = update.message.from_user.id
    user_data = context.user_data
    name = update.message.text
    # send data to base
    session = Session()
    session.add(Player(id=int(user_id),name=name,points=0))
    session.commit() 
    # reply and log
    update.message.reply_text(CommandsList.commandslist)
    logging.info("User %s added" % user_id)
    # next state
    return CREATE
    



def create_game(update,context):
    """
    Проверяется на созданные и подключенные игры,
    Создается игра,
    Прописывается начальный статус
    Создатель присоединяется к игре
    Возвращается ID игры
    """
    # get user data
    user_id = update.message.from_user.id
    user_data = context.user_data
    # send data to base
    session = Session()

    last_game = session.query(Game,Players2Game)\
        .join(Players2Game, Players2Game.game_id == Game.id)\
        .filter_by(player_id=user_id)\
        .first()
    
    print(last_game.Game.state)

    if last_game == None or last_game.Game.state == GameStates.ended:
        session.add(Game(state=GameStates.begin,creator=user_id))
        session.flush()
        game_id = session.query(Game).filter_by(creator=user_id).first().id
        session.add(Players2Game(game_id=game_id,player_id=user_id,position=0))
        session.commit()
        # reply and log
        update.message.reply_text(CreationTexts.connectlink.format(game_id=str(game_id)))
        logging.info(f"User {user_id} create game")
        return PREPARE
    elif last_game.Game.state == GameStates.begin:
        update.message.reply_text(CreationTexts.remindconnectlink.format(game_id=str(str(last_game.Game.id))))
    elif last_game.Game.state == GameStates.in_progress:
        update.message.reply_text(CreationTexts.already_in_game)
    else:
        logging.debug(f"Unknown game {last_game.Game.id} state")
    pass

def join_game(update,context):
    # get user data
    user_id = update.message.from_user.id
    user_data = context.user_data
    game_id = update.message.text.split(" ")[1]

    # create db session
    session = Session()

    # get existed games
    last_game = session.query(Game,Players2Game)\
        .join(Players2Game, Players2Game.game_id == Game.id)\
        .filter_by(player_id=user_id)\
        .first()

    # check for in_progress games
    if last_game == None or last_game.Game.state == GameStates.ended:
        session.add(Players2Game(game_id=game_id,player_id=user_id,position=0))
        session.flush()
        update.message.reply_text(CreationTexts.succesfully_connected)
        logging.info(f"User {user_id} join game")
        return AWAIT
    elif last_game.Game.state == GameStates.begin:
        update.message.reply_text(CreationTexts.remindconnectlink.format(game_id=str(str(last_game.Game.id))))
    elif last_game.Game.state == GameStates.in_progress:
        update.message.reply_text(CreationTexts.already_started)
    else:
        logging.debug(f"Unknown game {last_game.Game.id} state")
    session.commit()


def start_game(update,context):
    # get user data
    user_id = update.message.from_user.id
    user_data = context.user_data
    # send data to base
    session = Session()
    # check number of players
    created_game = session.query(Game,Players2Game)\
        .join(Players2Game, Players2Game.game_id == Game.id)\
        .filter_by(creator=user_id,state=GameStates.begin)\
        .all()

    print(created_game.Game.id)
    pass

def cancel(update,context):
    pass

















def main():
    ## Вставляем фичу в обработчик
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],

        states={

            BEGIN: [
                    CommandHandler('start', start), 
                    MessageHandler(Filters.text, create_user)
                    ],

            CREATE: [
                    CommandHandler('create', create_game),
                    CommandHandler('join', join_game)
                    ],

            PREPARE:[
                    CommandHandler('begin', start_game)
                    ],

            AWAIT:  [
                    CommandHandler('create', create_game),
                    CommandHandler('join', join_game)
                    ],

            PLAY:   [
                    CommandHandler('start', start), 
                    MessageHandler(Filters.text, create_game)
                    ]

        },

        fallbacks=[CommandHandler('cancel', cancel)]
    )
    dispatcher.add_handler(conv_handler)

    ## Запускаем мясорубку
    updater.start_polling()
    updater.idle()
    ## Вырубаем мясорубку
    # updater.stop()  # TODO автоматизировать выключалку

if __name__ == '__main__':
    main()