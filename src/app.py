import telegram
from telegram.ext import Updater, CommandHandler, ConversationHandler, MessageHandler, Filters
import logging
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from telegram import Update, User

from error_handler import error_callback
from models import *

from db_enums.game_states import GameStates
from configs.texts import RegistrationTexts, CreationTexts, CommandsList


## Constants
TOKEN = '789364882:AAF6-OLy36xTCZB0Y3KQtK0pfZTUuRe56dM' # TODO Убрать в конфиг
BEGIN, CREATE, PLAY, PREPARE, AWAIT, START = range(6)

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






def get_user_info(update, context):
    
    user_id = update.message.from_user.id
    user_data = context.user_data
    user_message = update.message.text
    data = {}
    for variable in ['user_id', "user_data", "user_message"]:
        data[variable] = eval(variable)
    return data




















#==================================================================================================#
#======================================  Прописываем фичи  ========================================#
#==================================================================================================#


def start(update, context):
    """
    Проверяем наличие пользователя
    Если есть, игнорируем
    Если нету, то:
    Спрашиваем имя
    Создаем пользователя
    """
    # get user data
    user_data = get_user_info(update, context)
    # init DB session
    session = Session()


    def check_existing_user(session, telegram_id):
        """
        Проверки на наличие пользователя
        """
        # TODO Добавить всякие проверки на бота
        player = session.query(Player).filter_by(id=telegram_id).first()
        if not player:
            logging.info(f"User {user_data.get('user_id')} first time")
            return False
        else:
            logging.info(f"User {user_data.get('user_id')} exist")
    session.close()

    if check_existing_user(session, user_data.get('user_id')) == False:
        update.message.reply_text(RegistrationTexts.hello)
        return BEGIN
    else:
        update.message.reply_text(CommandsList.commandslist)
        return PREPARE

        

def create_user(update, context):
    """
    Создание пользователя, после получения его имени
    """
    # get user data
    user_data = get_user_info(update, context)
    # init DB session
    session = Session()

    session.add(Player(id=int(user_data.get('user_id')),name=user_data.get('user_message'),points=0))
    session.commit() 
    # reply and log
    update.message.reply_text(CommandsList.commandslist)
    logging.info(f"User {user_data.get('user_id')} added")
    # next state
    return PREPARE
    



def create_game(update,context):
    """
    Проверяется на созданные и подключенные игры,
    Создается игра,
    Прописывается начальный статус
    Создатель присоединяется к игре
    Возвращается ID игры
    """
    # get user data
    user_data = get_user_info(update, context)
    # init DB session
    session = Session()

    last_game = session.query(Game,Players2Game)\
        .join(Players2Game, Players2Game.game_id == Game.id)\
        .filter_by(player_id=user_data.get('user_id'))\
        .first() # Получаем статус последней игры пользователя

    if last_game == None or last_game.Game.state == GameStates.ended:
        new_game = Game(state=GameStates.begin,creator=user_data.get('user_id'))                        # Новый объект игры
        session.add(new_game)                                                                           # Создаем игру
        session.flush()                                                                                 # Отправляем
        # game_id = session.query(Game).filter_by(creator=user_data.get('user_id')).first().id          # Получаем ID игры
        session.add(Players2Game(game_id=new_game.id,player_id=user_data.get('user_id'),position=0))    # Привязываем игрока к игре
        session.commit()                                                                                # Отправляем
        update.message.reply_text(CreationTexts.connectlink.format(game_id=str(new_game.id)))           # Присылаем создателю ID игры
        logging.info(f"User {user_data.get('user_id')} create game")
        return START
    elif last_game.Game.state == GameStates.begin:
        update.message.reply_text(CreationTexts.remindconnectlink.format(game_id=str(str(last_game.Game.id))))
    elif last_game.Game.state == GameStates.in_progress:
        update.message.reply_text(CreationTexts.already_in_game)
    else:
        logging.debug(f"Unknown game {last_game.Game.id} state")




def join_game(update,context):
    """
    Получение данных пользователя
    Получение последней игры пользователя
    Проверка статуса последней игры пользователя
    Присоединение к игре, если она в статусе начинающейся
    """
    # get user data
    user_data = get_user_info(update, context)
    game_id = user_data.get('user_message').split(" ")[1] # Отрезаем команду /join
    # init DB session
    session = Session()

    # get existed games
    last_game = session.query(Game,Players2Game)\
        .join(Players2Game, Players2Game.game_id == Game.id)\
        .filter_by(player_id=user_data.get('user_id'))\
        .first()

    if last_game == None or last_game.Game.state == GameStates.ended:
        session.add(Players2Game(game_id=game_id,player_id=user_data.get('user_id'),position=0))        # Привязываем игрока к игре
        session.flush()                                                                                 # Отправляем
        update.message.reply_text(CreationTexts.succesfully_connected)                                  # Текст успеха
        creator = session.query(Game(id=game_id)).first().creator
        bot.send_message(chat_id=creator, text="I'm sorry Dave I'm afraid I can't do that.")
        logging.info(f"User {user_data.get('user_id')} join game")
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
    user_data = get_user_info(update, context)
    # init DB session
    session = Session()

    # check number of players
    created_game = session.query(Game,Players2Game)\
        .join(Players2Game, Players2Game.game_id == Game.id)\
        .filter_by(creator=user_data.get('user_id'),state=GameStates.begin)\
        .all()

    print(created_game.Game.id)
    pass

def end_game(update,context):
    pass





#==================================================================================================#
#==================================================================================================#
#==================================================================================================#











def main():
    ## Вставляем фичу в обработчик
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],

        states={

            BEGIN: [
                    CommandHandler('start', start), 
                    MessageHandler(Filters.text, create_user)
                    ],

            PREPARE:[
                    CommandHandler('create', create_game),
                    CommandHandler('join', join_game)
                    ],

            START:  [
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

        fallbacks=[CommandHandler('cancel', end_game)]
    )
    dispatcher.add_handler(conv_handler)

    ## Запускаем мясорубку
    updater.start_polling()
    updater.idle()
    ## Вырубаем мясорубку
    # updater.stop()  # TODO автоматизировать выключалку

if __name__ == '__main__':
    main()